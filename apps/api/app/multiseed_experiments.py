"""Durable, window-scoped Aurora paired multi-seed experiments."""

from __future__ import annotations

import hashlib
from importlib import metadata as package_metadata
import json
import math
import os
import re
import sqlite3
import shutil
import statistics
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock
from typing import Any

from simulation import SimulationError, SimulationInput, SimulationLimits, SimulationResult, SignalTimingIntervention, apply_signal_timing_intervention, load_aurora_input, run_simulation
from urban_arena import load_aurora_snapshot

from .multiseed_schemas import (
    ArmDTO, AttemptDTO, ConfidenceInterval, DerivedMetric, ExperimentDTO, MetricValue,
    MultiSeedManifestRequest, NumericSummary, PairDTO, WindowSummary,
)
from .simulation_jobs import _has_route_exposure

PROTOCOL_ID = "aurora-paired-multiseed-v1"
REQUIRED_LIMITATIONS = {
    "synthetic_aurora", "window_only", "network_aggregated", "not_causal", "not_real_world_validated",
}
RECOVERABLE_ERRORS = {"sumo_timeout", "timeout", "worker_lost", "sumo_unavailable", "executor_unavailable", "temporary_executor_unavailable"}
_RETRY_SCOPE_UNSET = object()
_lock = RLock()
_initialized = False
_sumo_probe_cache: tuple[tuple[Any, ...], dict[str, Any]] | None = None
_db_path = Path(os.getenv("AURORA_EXPERIMENT_DB", str(Path(__file__).resolve().parents[1] / ".data" / "aurora-experiments.sqlite3")))
_data_root = Path(os.getenv("AURORA_EXPERIMENT_DATA", str(Path(__file__).resolve().parents[1] / ".data" / "experiments")))


def _process_start_token(pid: int) -> str | None:
    try:
        fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
        return fields[19]
    except (OSError, IndexError):
        return None


_worker_owner = f"{os.getpid()}:{_process_start_token(os.getpid()) or 'unknown'}"


def _owner_is_alive(owner: str | None) -> bool:
    if not owner:
        return False
    try:
        pid_text, start_token = owner.split(":", 1)
        current_token = _process_start_token(int(pid_text))
    except (ValueError, OSError):
        return False
    return current_token is not None and current_token == start_token


class ExperimentNotFoundError(LookupError):
    pass


class ExperimentConflictError(ValueError):
    pass


class ExperimentBudgetError(ValueError):
    pass


class ExperimentStateError(ValueError):
    pass


def configure_store(path: Path | str, data_root: Path | str | None = None) -> None:
    """Test/operator hook for selecting an isolated durable store."""
    global _db_path, _data_root, _initialized
    _db_path = Path(path)
    if data_root is not None:
        _data_root = Path(data_root)
    _initialized = False
    _initialize()


def _connect() -> sqlite3.Connection:
    _db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(_db_path, timeout=30, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


def _initialize() -> None:
    global _initialized
    if _initialized:
        return
    with _connect() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS mobility_experiments (
            experiment_id TEXT PRIMARY KEY,
            manifest_sha256 TEXT NOT NULL UNIQUE,
            dto_json TEXT NOT NULL,
            cancel_requested INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            worker_owner TEXT,
            worker_start_token TEXT,
            retry_pair_ids_json TEXT
        )""")
        columns = {row["name"] for row in db.execute("PRAGMA table_info(mobility_experiments)")}
        if "worker_owner" not in columns:
            db.execute("ALTER TABLE mobility_experiments ADD COLUMN worker_owner TEXT")
        if "worker_start_token" not in columns:
            db.execute("ALTER TABLE mobility_experiments ADD COLUMN worker_start_token TEXT")
        if "retry_pair_ids_json" not in columns:
            db.execute("ALTER TABLE mobility_experiments ADD COLUMN retry_pair_ids_json TEXT")
        db.execute("""CREATE TABLE IF NOT EXISTS mobility_experiment_inputs (
            experiment_id TEXT NOT NULL,
            common_input_sha256 TEXT NOT NULL,
            input_json TEXT NOT NULL,
            PRIMARY KEY (experiment_id, common_input_sha256),
            FOREIGN KEY (experiment_id) REFERENCES mobility_experiments(experiment_id)
        )""")
        # An interrupted process cannot have produced a complete result record.
        for row in db.execute("SELECT experiment_id, dto_json, worker_owner, worker_start_token FROM mobility_experiments").fetchall():
            dto = json.loads(row["dto_json"])
            changed = False
            if dto["status"] == "running" and _owner_is_alive(row["worker_owner"]):
                continue
            running_arms = 0
            for pair in dto["pairs"]:
                for arm_name in ("baseline", "strategy"):
                    arm = pair["executions"][arm_name]
                    if arm["status"] == "running":
                        running_arms += 1
                        arm["status"] = "failed"
                        last = arm["attempts"][-1]
                        last.update(status="failed", error="worker_lost", finished_at=_now())
                        last["wall_clock_seconds"] = dto["manifest"]["budget"]["max_wall_clock_seconds_per_run"]
                        dto["reserved_wall_clock_seconds"] = max(
                            0,
                            dto.get("reserved_wall_clock_seconds", 0)
                            - dto["manifest"]["budget"]["max_wall_clock_seconds_per_run"],
                        )
                        dto["wall_clock_seconds_used"] += dto["manifest"]["budget"]["max_wall_clock_seconds_per_run"]
                        changed = True
                if pair["status"] == "running":
                    pair["status"] = "failed"
                    changed = True
            if dto["status"] == "running" and not running_arms:
                # The worker may have stopped between marking the experiment
                # running and claiming its first pair.
                dto["status"] = "partial" if any(p["status"] in {"succeeded", "failed"} for p in dto["pairs"]) else "queued"
                changed = True
            if changed:
                if dto["status"] == "running":
                    dto["status"] = "partial" if any(p["status"] in {"succeeded", "failed", "cancelled"} for p in dto["pairs"]) else "queued"
                _refresh_counts(dto)
                recoverable_worker_loss = any(
                    attempt.get("error") == "worker_lost"
                    and len(arm.get("attempts", [])) < dto["manifest"]["budget"]["max_attempts_per_execution"]
                    for pair in dto["pairs"] for arm in pair["executions"].values()
                    for attempt in arm.get("attempts", [])[-1:]
                )
                if recoverable_worker_loss:
                    dto["status"] = "partial"
                db.execute("UPDATE mobility_experiments SET dto_json=?, worker_owner=NULL, worker_start_token=NULL WHERE experiment_id=?", (_dump(dto), row["experiment_id"]))
    _initialized = True


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _git_head_sha() -> str:
    try:
        root = Path(__file__).resolve().parents[3]
        completed = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True, check=True, timeout=2)
        return completed.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "unavailable"


def _executor_code_sha256() -> str:
    """Fingerprint executable Python sources that define the frozen runner."""
    root = Path(__file__).resolve().parents[3]
    source_roots = (
        root / "apps/api/app",
        root / "packages/simulation/simulation",
        root / "packages/urban_arena/urban_arena",
    )
    digest = hashlib.sha256()
    for source_root in source_roots:
        for path in sorted(source_root.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            digest.update(path.relative_to(root).as_posix().encode("utf-8"))
            digest.update(b"\0")
            digest.update(path.read_bytes())
            digest.update(b"\0")
    return digest.hexdigest()


def _runtime_dependencies() -> dict[str, str]:
    return {name: package_metadata.version(name) for name in ("fastapi", "pydantic", "urban-simulation", "urban-arena")}


def _probe_sumo_environment() -> dict[str, Any]:
    """Freeze SUMO and netconvert executable identity when they are installed."""
    global _sumo_probe_cache
    executable_paths = {name: shutil.which(name) for name in ("sumo", "netconvert")}
    if any(path is None for path in executable_paths.values()):
        return {"status": "unavailable", "engine": "sumo", "sumo": None, "netconvert": None}
    try:
        stats = {name: Path(path).stat() for name, path in executable_paths.items()}
    except OSError:
        return {"status": "unavailable", "engine": "sumo", "sumo": None, "netconvert": None}
    cache_key = tuple((name, executable_paths[name], stats[name].st_ino, stats[name].st_size,
                       stats[name].st_mtime_ns, stats[name].st_ctime_ns) for name in sorted(executable_paths))
    if _sumo_probe_cache is not None and _sumo_probe_cache[0] == cache_key:
        return _sumo_probe_cache[1]
    binaries: dict[str, dict[str, str | None]] = {}
    for name, path in executable_paths.items():
        try:
            completed = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=3, check=False)
        except (OSError, subprocess.TimeoutExpired):
            result = {"status": "unavailable", "engine": "sumo", "sumo": None, "netconvert": None}
            _sumo_probe_cache = (cache_key, result)
            return result
        output = (completed.stdout or "") + "\n" + (completed.stderr or "")
        match = re.search(r"\b(?:sumo(?:\s+netconvert)?\s+|netconvert\s+|Version\s+)([0-9]+(?:\.[0-9A-Za-z_-]+)+)", output, re.IGNORECASE)
        if completed.returncode != 0 or match is None:
            result = {"status": "unavailable", "engine": "sumo", "sumo": None, "netconvert": None}
            _sumo_probe_cache = (cache_key, result)
            return result
        digest = hashlib.sha256()
        try:
            with Path(path).open("rb") as binary:
                for chunk in iter(lambda: binary.read(1024 * 1024), b""):
                    digest.update(chunk)
        except OSError:
            result = {"status": "unavailable", "engine": "sumo", "sumo": None, "netconvert": None}
            _sumo_probe_cache = (cache_key, result)
            return result
        binaries[name] = {"path": path, "version": match.group(1), "sha256": digest.hexdigest()}
    result = {"status": "available", "engine": "sumo", "sumo": binaries["sumo"], "netconvert": binaries["netconvert"]}
    _sumo_probe_cache = (cache_key, result)
    return result


class ExecutionEnvironmentMismatch(RuntimeError):
    pass


def _assert_frozen_executor(manifest: dict[str, Any]) -> None:
    if (not manifest.get("backend_code_sha256")
            or _executor_code_sha256() != manifest["backend_code_sha256"]
            or sys.version.split()[0] != manifest["python_runtime"]
            or os.getenv("CONTAINER_DIGEST", "unavailable") != manifest["container_digest"]
            or _runtime_dependencies() != manifest.get("runtime_dependencies")
            or _probe_sumo_environment() != manifest.get("sumo_environment")
            or "urban-simulation-0.1" != manifest["sumo_adapter_version"]):
        raise ExecutionEnvironmentMismatch("O executor atual difere do código/ambiente congelado no manifesto.")


def _result_matches_frozen_sumo(result: SimulationResult, manifest: dict[str, Any]) -> bool:
    environment = manifest.get("sumo_environment") or {}
    return (environment.get("status") == "available"
            and result.engine == environment.get("engine")
            and result.engine_version == (environment.get("sumo") or {}).get("version"))


def _canonical(value: Any) -> bytes:
    """Canonical JSON for the I-JSON values accepted by these API models.

    Keys are Unicode-sorted, non-finite values and duplicate keys are impossible
    after Pydantic parsing, and output uses compact UTF-8 JSON.
    """
    def number(item: float) -> str:
        if not math.isfinite(item):
            raise ValueError("JCS rejeita NaN e Infinity.")
        if item == 0:
            return "0"
        raw = repr(item).lower()
        if "e" in raw:
            mantissa, exponent_text = raw.split("e")
            exponent = int(exponent_text)
            digits = mantissa.replace("-", "").replace(".", "")
            decimal_position = (mantissa.replace("-", "").find(".") if "." in mantissa else len(mantissa.replace("-", ""))) + exponent
        else:
            mantissa = raw
            digits = mantissa.replace("-", "").replace(".", "")
            decimal_position = mantissa.replace("-", "").find(".") if "." in mantissa else len(mantissa.replace("-", ""))
        sign = "-" if item < 0 else ""
        digits = digits.lstrip("0") or "0"
        digits = digits.rstrip("0") or "0"
        # `decimal_position` is relative to the original digit sequence; account for
        # leading zeros removed from the mantissa.
        original_digits = raw.split("e")[0].replace("-", "").replace(".", "")
        leading = len(original_digits) - len(original_digits.lstrip("0"))
        decimal_position -= leading
        if 0 < decimal_position <= 21:
            if decimal_position >= len(digits):
                return sign + digits + "0" * (decimal_position - len(digits))
            return sign + digits[:decimal_position] + "." + digits[decimal_position:]
        if -6 < decimal_position <= 0:
            return sign + "0." + "0" * (-decimal_position) + digits
        scientific_exponent = decimal_position - 1
        fraction = digits[1:].rstrip("0")
        mantissa_text = digits[0] + ("." + fraction if fraction else "")
        return sign + mantissa_text + "e" + ("+" if scientific_exponent >= 0 else "") + str(scientific_exponent)

    def encode(item: Any) -> str:
        if item is None: return "null"
        if item is True: return "true"
        if item is False: return "false"
        if isinstance(item, int):
            if abs(item) > 9007199254740991:
                raise ValueError("JCS aceita somente inteiros no intervalo seguro I-JSON.")
            return str(item)
        if isinstance(item, float): return number(item)
        if isinstance(item, str): return json.dumps(item, ensure_ascii=False, separators=(",", ":"))
        if isinstance(item, list): return "[" + ",".join(encode(part) for part in item) + "]"
        if isinstance(item, dict):
            ordered = sorted(item, key=lambda key: key.encode("utf-16be"))
            return "{" + ",".join(encode(key) + ":" + encode(item[key]) for key in ordered) + "}"
        raise TypeError(f"Tipo não suportado por JCS: {type(item).__name__}")

    return encode(value).encode("utf-8")


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _dump(value: Any) -> str:
    return _canonical(value).decode("utf-8")


def _stable_id(prefix: str, *parts: Any) -> str:
    return f"{prefix}_{_hash(list(parts))[:32]}"


def _common_input_payload(inputs: SimulationInput, request: MultiSeedManifestRequest, seed: int) -> dict[str, Any]:
    return {
        "snapshot_id": inputs.snapshot_id, "snapshot_sha256": inputs.snapshot_hash,
        "network": [item.model_dump(mode="json") for item in inputs.nodes + inputs.edges + inputs.traffic_signals],
        "demand": [trip.model_dump(mode="json") for trip in inputs.trips],
        "demand_hash": _hash([trip.model_dump(mode="json") for trip in inputs.trips]),
        "window": inputs.window.model_dump(mode="json"), "drain_limit_seconds": request.drain_limit_seconds,
        "metric_ids": sorted(request.metrics), "metric_method_version": request.method_version,
        "seed": seed, "max_wall_clock_seconds_per_run": request.budget.max_wall_clock_seconds_per_run,
        "sumo_config_version": "sumo-adapter-config-v1",
    }


def create_experiment(request: MultiSeedManifestRequest) -> ExperimentDTO:
    config, snapshot = load_aurora_snapshot()
    configured = {window.id: window for window in config.mobility.simulation_windows}
    if not set(request.window_ids) <= set(configured):
        raise ValueError("Uma ou mais janelas solicitadas não estão configuradas.")
    windows = sorted(request.window_ids)
    strategies = sorted(request.strategies, key=lambda item: item.strategy_id)
    seeds = sorted(request.seeds)
    if request.city_id != snapshot.city_id:
        raise ValueError("Cidade não corresponde ao snapshot Aurora configurado.")
    expected_baseline_hash = _hash({"policy_id": request.baseline_id, "policy_version": request.baseline_version, "intervention": None})
    if request.baseline_sha256 != expected_baseline_hash:
        raise ValueError("baseline_sha256 não corresponde ao payload do baseline sem intervenção.")
    for strategy in request.strategies:
        expected_policy_hash = _hash({"policy_id": strategy.strategy_id, "policy_version": strategy.policy_version,
                                      "intervention": strategy.intervention.model_dump(mode="json")})
        if strategy.policy_sha256 != expected_policy_hash:
            raise ValueError(f"policy_sha256 divergente para a estratégia '{strategy.strategy_id}'.")
    plan_pairs = len(strategies) * len(windows) * len(seeds)
    max_attempts = request.budget.max_attempts_per_execution
    max_runs_required = plan_pairs * 2 * max_attempts + request.reproducibility_checks
    max_wall_required = (plan_pairs * 2 * max_attempts + request.reproducibility_checks) * request.budget.max_wall_clock_seconds_per_run
    if max_runs_required > request.budget.max_sumo_runs and not request.budget.admit_incomplete:
        raise ExperimentBudgetError("O teto max_sumo_runs não comporta a matriz e as tentativas declaradas.")
    if max_wall_required > request.budget.max_total_wall_clock_seconds and not request.budget.admit_incomplete:
        raise ExperimentBudgetError("O teto max_total_wall_clock_seconds não comporta a matriz declarada.")

    sumo_environment = _probe_sumo_environment()
    limitations = set(request.limitations) | REQUIRED_LIMITATIONS
    if sumo_environment["status"] != "available":
        limitations.add("sumo_environment_unavailable")
    normalized = request.model_dump(mode="json")
    normalized["limitations"] = sorted(limitations)
    normalized["window_ids"] = windows
    normalized["seeds"] = seeds
    normalized["metrics"] = sorted(request.metrics)
    normalized["primary_metrics"] = sorted(request.primary_metrics)
    normalized["strategies"] = [item.model_dump(mode="json") for item in strategies]
    normalized.update(protocol_id=PROTOCOL_ID, protocol_version=1, created_at=_now(), city_configuration_version=str(config.schema_version),
                      snapshot_id=snapshot.snapshot_id, snapshot_sha256=snapshot.hash,
                      city_configuration_sha256=_hash(config.model_dump(mode="json")),
                      backend_commit_sha=_git_head_sha(), python_runtime=sys.version.split()[0],
                      backend_code_sha256=_executor_code_sha256(),
                      runtime_dependencies=_runtime_dependencies(),
                      container_digest=os.getenv("CONTAINER_DIGEST", "unavailable"),
                      sumo_environment=sumo_environment,
                      sumo_adapter_version="urban-simulation-0.1",
                      demand_scope="fixed_across_operational_seeds", seed_scope="sumo_operational_randomness",
                      selection_method=request.selection_method, baseline={"id": request.baseline_id, "version": request.baseline_version, "sha256": request.baseline_sha256},
                      cost_ceiling={"planned_upper_bound_sumo_runs": max_runs_required, "planned_upper_bound_wall_clock_seconds": max_wall_required},
                      arena_reference_verification="caller_asserted_unverified")
    requested_experiment_id = normalized.pop("experiment_id", None)
    identity_content = {key: value for key, value in normalized.items() if key != "created_at"}
    experiment_id = requested_experiment_id or _stable_id("aurora_ms", identity_content)
    normalized["experiment_id"] = experiment_id
    manifest_hash = _hash(normalized)
    pairs: list[dict[str, Any]] = []
    input_payloads: dict[str, dict[str, Any]] = {}
    for window_id in windows:
        raw_input = load_aurora_input(request.city_id, window_id)
        if raw_input.snapshot_hash != snapshot.hash:
            raise ValueError("A entrada SUMO não corresponde ao snapshot Aurora congelado.")
        for strategy in strategies:
            apply_signal_timing_intervention(raw_input, strategy.intervention)
        normalized.setdefault("demand_by_window", {})[window_id] = {
            "window": raw_input.window.model_dump(mode="json"),
            "demand_sha256": _hash([trip.model_dump(mode="json") for trip in raw_input.trips]),
            "trips": [trip.model_dump(mode="json") for trip in raw_input.trips],
            "city_schema_version": raw_input.city_schema_version,
            "city_generator_version": raw_input.city_generator_version,
            "provenance": raw_input.provenance,
            "warnings": list(raw_input.warnings),
        }
        for seed in seeds:
            for strategy in strategies:
                pair_id = _stable_id("pair", manifest_hash, window_id, seed, strategy.strategy_id, request.baseline_id)
                common_payload = _common_input_payload(raw_input, request, seed)
                common_hash = _hash(common_payload)
                input_payloads[common_hash] = common_payload
                base_arm_hash = _hash({"common_input_sha256": common_hash, "policy_id": request.baseline_id, "policy_sha256": request.baseline_sha256, "intervention": None})
                strategy_arm_hash = _hash({"common_input_sha256": common_hash, "policy_id": strategy.strategy_id, "policy_sha256": strategy.policy_sha256, "intervention": strategy.intervention.model_dump(mode="json")})
                pairs.append(PairDTO(
                    pair_id=pair_id, strategy_id=strategy.strategy_id,
                    baseline_execution_id=_stable_id("exec", pair_id, "baseline"), strategy_execution_id=_stable_id("exec", pair_id, "strategy"),
                    window_id=window_id, seed=seed, common_input_sha256=common_hash,
                    baseline_arm_input_sha256=base_arm_hash, strategy_arm_input_sha256=strategy_arm_hash,
                    status="queued", route_exposure="unknown",
                    executions={"baseline": ArmDTO(execution_id=_stable_id("exec", pair_id, "baseline"), status="queued", attempts=[]),
                                "strategy": ArmDTO(execution_id=_stable_id("exec", pair_id, "strategy"), status="queued", attempts=[])},
                ).model_dump(mode="json"))
    # Demand payload is part of the frozen manifest identity, so hash only after
    # expansion for each explicitly selected window is recorded.
    manifest_hash = _hash(normalized)
    if requested_experiment_id is None:
        experiment_id = _stable_id("aurora_ms", {k: v for k, v in normalized.items() if k not in {"experiment_id", "created_at"}})
        normalized["experiment_id"] = experiment_id
        manifest_hash = _hash(normalized)
    else:
        normalized["experiment_id"] = experiment_id
    for pair in pairs:
        pair["pair_id"] = _stable_id("pair", manifest_hash, pair["window_id"], pair["seed"], pair["strategy_id"], request.baseline_id)
        pair["baseline_execution_id"] = _stable_id("exec", pair["pair_id"], "baseline")
        pair["strategy_execution_id"] = _stable_id("exec", pair["pair_id"], "strategy")
        pair["executions"]["baseline"]["execution_id"] = pair["baseline_execution_id"]
        pair["executions"]["strategy"]["execution_id"] = pair["strategy_execution_id"]
    initial = {
        "experiment_id": experiment_id, "manifest_sha256": manifest_hash,
        "arena_manifest_id": request.arena_manifest_id, "arena_manifest_sha256": request.arena_manifest_sha256,
        "status": "queued", "planned_pairs": plan_pairs, "completed_pairs": 0, "failed_pairs": 0,
        "running_pairs": 0, "missing_pairs": plan_pairs, "planned_executions": plan_pairs * 2,
        "attempts": 0, "sumo_runs_used": 0, "wall_clock_seconds_used": 0,
        "reserved_wall_clock_seconds": 0,
        "limitations": sorted(set(normalized["limitations"]) | {"arena_manifest_reference_unverified"}),
        "manifest": normalized,
        "pairs": pairs, "summaries_by_window": [],
    }
    _refresh_counts(initial)
    dto = ExperimentDTO.model_validate(initial)
    _initialize()
    with _connect() as db:
        db.execute("BEGIN IMMEDIATE")
        same_id = db.execute("SELECT dto_json FROM mobility_experiments WHERE experiment_id=?", (experiment_id,)).fetchone()
        if same_id:
            current = ExperimentDTO.model_validate(json.loads(same_id["dto_json"]))
            current_manifest = dict(current.manifest)
            candidate_manifest = dict(normalized)
            current_manifest.pop("created_at", None)
            candidate_manifest.pop("created_at", None)
            if current_manifest != candidate_manifest:
                db.rollback()
                raise ExperimentConflictError("experiment_id já existe com conteúdo divergente.")
            db.commit()
            return current
        existing = db.execute("SELECT dto_json FROM mobility_experiments WHERE manifest_sha256=?", (manifest_hash,)).fetchone()
        if existing:
            current = ExperimentDTO.model_validate(json.loads(existing["dto_json"]))
            if current.manifest != normalized:
                db.rollback()
                raise ExperimentConflictError("A mesma identidade de manifesto já existe com conteúdo divergente.")
            db.commit()
            return current
        try:
            db.execute(
                "INSERT INTO mobility_experiments (experiment_id, manifest_sha256, dto_json, cancel_requested, created_at) VALUES (?, ?, ?, 0, ?)",
                (experiment_id, manifest_hash, _dump(dto.model_dump(mode="json")), _now()),
            )
            db.executemany("INSERT INTO mobility_experiment_inputs VALUES (?, ?, ?)",
                           [(experiment_id, key, _dump(value)) for key, value in input_payloads.items()])
            db.commit()
        except sqlite3.IntegrityError as exc:
            db.rollback()
            raise ExperimentConflictError("Conflito ao criar identidade de experimento.") from exc
    return dto


def get_experiment(experiment_id: str) -> ExperimentDTO:
    _initialize()
    with _connect() as db:
        row = db.execute("SELECT dto_json FROM mobility_experiments WHERE experiment_id=?", (experiment_id,)).fetchone()
    if row is None:
        raise ExperimentNotFoundError(experiment_id)
    return ExperimentDTO.model_validate(json.loads(row["dto_json"]))


def list_resumable_experiments() -> list[str]:
    """Return durable queued/partial jobs for the API startup dispatcher."""
    _initialize()
    with _connect() as db:
        rows = db.execute("SELECT experiment_id, dto_json, retry_pair_ids_json FROM mobility_experiments ORDER BY created_at").fetchall()
    resumable = []
    for row in rows:
        dto = json.loads(row["dto_json"])
        scope = json.loads(row["retry_pair_ids_json"]) if row["retry_pair_ids_json"] else None
        if (dto["status"] in {"queued", "partial"} and not dto.get("cancellation_requested")
                and dto.get("stop_reason") != "budget_exhausted" and _has_runnable_pairs(dto, scope)):
            resumable.append(row["experiment_id"])
    return resumable


def _has_runnable_pairs(dto: dict[str, Any], pair_scope: list[str] | None) -> bool:
    selected = set(pair_scope) if pair_scope is not None else None
    for pair in dto["pairs"]:
        if selected is not None and pair["pair_id"] not in selected:
            continue
        if pair["status"] == "queued":
            return True
        if pair["status"] == "failed" and any(
            arm["status"] == "failed" and arm["attempts"]
            and arm["attempts"][-1].get("error") in RECOVERABLE_ERRORS
            and len(arm["attempts"]) < dto["manifest"]["budget"]["max_attempts_per_execution"]
            for arm in pair["executions"].values()
        ):
            return True
    return False


def _mutate(experiment_id: str, fn, *, retry_pair_ids=_RETRY_SCOPE_UNSET):
    with _connect() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT dto_json, cancel_requested FROM mobility_experiments WHERE experiment_id=?", (experiment_id,)).fetchone()
        if row is None:
            db.rollback()
            raise ExperimentNotFoundError(experiment_id)
        dto = json.loads(row["dto_json"])
        result = fn(dto, bool(row["cancel_requested"]))
        _refresh_counts(dto)
        if retry_pair_ids is _RETRY_SCOPE_UNSET:
            db.execute("UPDATE mobility_experiments SET dto_json=? WHERE experiment_id=?", (_dump(dto), experiment_id))
        else:
            scope_json = _dump(sorted(retry_pair_ids)) if retry_pair_ids is not None else None
            db.execute("UPDATE mobility_experiments SET dto_json=?, retry_pair_ids_json=? WHERE experiment_id=?",
                       (_dump(dto), scope_json, experiment_id))
        db.commit()
        return result, ExperimentDTO.model_validate(dto)


def _refresh_counts(dto: dict[str, Any]) -> None:
    pairs = dto["pairs"]
    dto["planned_pairs"] = len(pairs)
    dto["completed_pairs"] = sum(p["status"] == "succeeded" for p in pairs)
    dto["failed_pairs"] = sum(p["status"] in {"failed", "cancelled"} for p in pairs)
    dto["running_pairs"] = sum(p["status"] == "running" for p in pairs)
    dto["missing_pairs"] = sum(p["status"] == "queued" for p in pairs)
    dto["missing_pair_ids"] = [p["pair_id"] for p in pairs if p["status"] == "queued"]
    dto["attempts"] = sum(len(a["attempts"]) for p in pairs for a in p["executions"].values())
    if dto["status"] not in {"cancelled", "failed"}:
        if dto["running_pairs"]:
            dto["status"] = "running"
        elif dto["completed_pairs"] == dto["planned_pairs"]:
            dto["status"] = "succeeded"
            dto["stop_reason"] = None
        elif dto["failed_pairs"] or dto.get("stop_reason") == "budget_exhausted" or dto["sumo_runs_used"] >= dto["manifest"]["budget"]["max_sumo_runs"]:
            dto["status"] = "failed" if dto["failed_pairs"] == dto["planned_pairs"] else "partial"
            if dto["sumo_runs_used"] >= dto["manifest"]["budget"]["max_sumo_runs"]:
                dto["stop_reason"] = "budget_exhausted"
        elif dto["missing_pairs"] == dto["planned_pairs"] and dto["status"] == "queued":
            dto["status"] = "queued"


def cancel_experiment(experiment_id: str) -> ExperimentDTO:
    _initialize()
    with _connect() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT dto_json FROM mobility_experiments WHERE experiment_id=?", (experiment_id,)).fetchone()
        if row is None:
            db.rollback()
            raise ExperimentNotFoundError(experiment_id)
        dto = json.loads(row["dto_json"])
        if dto["status"] in {"succeeded", "failed", "cancelled"}:
            db.rollback()
            raise ExperimentStateError("O experimento está em estado terminal.")
        has_active_attempt = False
        for pair in dto["pairs"]:
            if pair["status"] == "queued":
                pair["status"] = "cancelled"
                for arm in pair["executions"].values():
                    if arm["status"] == "queued": arm["status"] = "cancelled"
            if pair["status"] == "running" or any(arm["status"] == "running" for arm in pair["executions"].values()):
                has_active_attempt = True
        dto["cancellation_requested"] = True
        dto["status"] = "running" if has_active_attempt else "cancelled"
        _refresh_counts(dto)
        if not has_active_attempt:
            dto["status"] = "cancelled"
        db.execute("UPDATE mobility_experiments SET dto_json=?, cancel_requested=1 WHERE experiment_id=?", (_dump(dto), experiment_id))
        db.commit()
    return ExperimentDTO.model_validate(dto)


def retry_experiment(experiment_id: str, pair_ids: list[str] | None = None) -> ExperimentDTO:
    if pair_ids is not None and (not pair_ids or len(pair_ids) != len(set(pair_ids))):
        raise ValueError("pair_ids deve ser não vazio e sem duplicatas.")
    chosen = set(pair_ids) if pair_ids is not None else None
    def retry(dto, cancelled):
        if cancelled or dto["status"] == "cancelled":
            raise ExperimentStateError("Experimento cancelado não pode ser retomado.")
        if dto.get("error_code") == "execution_environment_mismatch":
            raise ExperimentStateError("O executor mudou; crie um novo experimento para preservar a proveniência.")
        if dto["status"] not in {"partial", "failed"}:
            if dto["status"] == "succeeded": return
            raise ExperimentStateError("Somente experimentos parciais/falhos podem ser retomados.")
        if chosen is not None:
            selected_pairs = [pair for pair in dto["pairs"] if pair["pair_id"] in chosen]
            if len(selected_pairs) != len(chosen):
                raise ValueError("pair_ids contém identidade desconhecida.")
            if all(pair["status"] == "succeeded" for pair in selected_pairs):
                raise ExperimentStateError("Todos os pares selecionados já foram concluídos.")
        found = set()
        for pair in dto["pairs"]:
            if chosen is not None and pair["pair_id"] not in chosen: continue
            found.add(pair["pair_id"])
            if pair["status"] == "succeeded": continue
            if pair["status"] == "cancelled": raise ExperimentStateError("Par cancelado não pode ser retomado.")
            failed_arms = [arm for arm in pair["executions"].values() if arm["status"] == "failed"]
            if pair["status"] == "failed" and not failed_arms:
                raise ExperimentStateError("Par falhou sem braço recuperável para nova tentativa.")
            for arm in pair["executions"].values():
                if arm["status"] == "failed":
                    if not arm["attempts"] or arm["attempts"][-1]["error"] not in RECOVERABLE_ERRORS:
                        raise ExperimentStateError("A falha não está na lista estável de erros recuperáveis.")
                    if len(arm["attempts"]) >= dto["manifest"]["budget"]["max_attempts_per_execution"]:
                        raise ExperimentStateError("O braço já consumiu o limite de tentativas do manifesto.")
            pair["status"] = "queued"
            for arm in pair["executions"].values():
                if arm["status"] == "failed": arm["status"] = "queued"
        if chosen is not None and found != chosen:
            raise ValueError("pair_ids contém identidade desconhecida.")
        dto["status"] = "queued"
        dto["error_code"] = None
        dto["stop_reason"] = None
    _, result = _mutate(experiment_id, retry,
                        retry_pair_ids=sorted(chosen) if chosen is not None else None)
    return result


def _start_worker(experiment_id: str) -> tuple[bool, ExperimentDTO | None]:
    _initialize()
    with _connect() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT dto_json, cancel_requested, worker_owner, retry_pair_ids_json FROM mobility_experiments WHERE experiment_id=?", (experiment_id,)).fetchone()
        if row is None:
            db.rollback()
            raise ExperimentNotFoundError(experiment_id)
        dto = json.loads(row["dto_json"])
        if row["cancel_requested"] or _owner_is_alive(row["worker_owner"]):
            db.rollback()
            return False, ExperimentDTO.model_validate(dto)
        if dto["status"] not in {"queued", "partial", "failed"}:
            db.rollback()
            return False, ExperimentDTO.model_validate(dto)
        pair_scope = json.loads(row["retry_pair_ids_json"]) if row["retry_pair_ids_json"] else None
        selected = set(pair_scope) if pair_scope is not None else None
        for pair in dto["pairs"]:
            if selected is not None and pair["pair_id"] not in selected:
                continue
            recoverable = False
            for arm in pair["executions"].values():
                if arm["status"] == "failed" and arm["attempts"] and arm["attempts"][-1]["error"] in RECOVERABLE_ERRORS:
                    if len(arm["attempts"]) < dto["manifest"]["budget"]["max_attempts_per_execution"]:
                        arm["status"] = "queued"
                        recoverable = True
            if recoverable:
                pair["status"] = "queued"
        dto["status"] = "running"
        db.execute("UPDATE mobility_experiments SET dto_json=?, worker_owner=?, worker_start_token=? WHERE experiment_id=?",
                   (_dump(dto), _worker_owner, _process_start_token(os.getpid()), experiment_id))
        db.commit()
    return True, ExperimentDTO.model_validate(dto)


def _release_worker(experiment_id: str) -> None:
    with _connect() as db:
        db.execute("UPDATE mobility_experiments SET worker_owner=NULL, worker_start_token=NULL WHERE experiment_id=? AND worker_owner=?",
                   (experiment_id, _worker_owner))


def _recover_owned_worker_failure(experiment_id: str) -> None:
    def recover(dto, cancelled):
        recovered_attempts = 0
        for pair in dto["pairs"]:
            for arm in pair["executions"].values():
                if arm["status"] == "running":
                    recovered_attempts += 1
                    arm["status"] = "failed"
                    arm["attempts"][-1].update(status="failed", error="worker_lost", finished_at=_now())
                    arm["attempts"][-1]["wall_clock_seconds"] = dto["manifest"]["budget"]["max_wall_clock_seconds_per_run"]
                    dto["reserved_wall_clock_seconds"] = max(0, dto.get("reserved_wall_clock_seconds", 0) - dto["manifest"]["budget"]["max_wall_clock_seconds_per_run"])
                    dto["wall_clock_seconds_used"] += dto["manifest"]["budget"]["max_wall_clock_seconds_per_run"]
            if pair["status"] == "running":
                pair["status"] = "queued"
        if recovered_attempts:
            dto["status"] = "partial" if any(p["status"] != "queued" for p in dto["pairs"]) else "queued"
            dto["error_code"] = None
        else:
            dto["status"] = "failed"
            dto["error_code"] = "worker_failed_without_active_attempt"
            dto["stop_reason"] = "worker_failed_without_active_attempt"
    _mutate(experiment_id, recover)


def _mark_environment_mismatch(experiment_id: str, pair_id: str | None = None) -> None:
    def mark(dto, cancelled):
        for pair in dto["pairs"]:
            if pair_id is not None and pair["pair_id"] == pair_id:
                pair["status"] = "failed"
                pair["error"] = "execution_environment_mismatch"
            elif pair["status"] == "running" and not any(arm["status"] == "running" for arm in pair["executions"].values()):
                pair["status"] = "queued"
        dto["status"] = "failed"
        dto["error_code"] = "execution_environment_mismatch"
        dto["stop_reason"] = "execution_environment_mismatch"
    _mutate(experiment_id, mark)


def run_experiment(experiment_id: str) -> None:
    claimed, dto = _start_worker(experiment_id)
    if not claimed:
        return
    try:
        with _connect() as db:
            row = db.execute("SELECT retry_pair_ids_json FROM mobility_experiments WHERE experiment_id=?", (experiment_id,)).fetchone()
        pair_scope = json.loads(row["retry_pair_ids_json"]) if row and row["retry_pair_ids_json"] else None
        _assert_frozen_executor(dto.manifest)
        _run_experiment_body(experiment_id, dto, pair_scope)
    except ExecutionEnvironmentMismatch:
        _mark_environment_mismatch(experiment_id)
    except Exception:
        _recover_owned_worker_failure(experiment_id)
    finally:
        _release_worker(experiment_id)


def _run_experiment_body(experiment_id: str, dto: ExperimentDTO, pair_scope: list[str] | None = None) -> None:
    _assert_frozen_executor(dto.manifest)
    _data_root.mkdir(parents=True, exist_ok=True)
    for pair_snapshot in dto.pairs:
        _assert_frozen_executor(dto.manifest)
        if pair_scope is not None and pair_snapshot.pair_id not in pair_scope:
            continue
        current = get_experiment(experiment_id)
        pair = next(p for p in current.pairs if p.pair_id == pair_snapshot.pair_id)
        if pair.status == "succeeded": continue
        if _is_cancelled(experiment_id): break
        for arm_name in ("baseline", "strategy"):
            current = get_experiment(experiment_id)
            pair = next(p for p in current.pairs if p.pair_id == pair_snapshot.pair_id)
            arm = pair.executions[arm_name]
            if arm.status == "succeeded": continue
            if arm.status == "failed" and arm.attempts and arm.attempts[-1].error not in RECOVERABLE_ERRORS:
                continue
            strategy = next(s for s in current.manifest["strategies"] if s["strategy_id"] == pair.strategy_id)
            request = MultiSeedManifestRequest.model_validate({k: v for k, v in current.manifest.items() if k not in {
                "protocol_id", "protocol_version", "created_at", "city_configuration_version", "snapshot_id", "snapshot_sha256",
                "city_configuration_sha256", "backend_commit_sha", "python_runtime", "container_digest", "sumo_adapter_version",
                "backend_code_sha256", "runtime_dependencies", "sumo_environment", "demand_scope", "seed_scope", "baseline", "cost_ceiling", "demand_by_window", "arena_reference_verification"
            }})
            _assert_frozen_executor(current.manifest)
            if not _claim_attempt(experiment_id, pair.pair_id, arm_name):
                _rebuild_summaries(experiment_id)
                return
            attempt_no = len(arm.attempts) + 1
            started = time.monotonic()
            storage_key = _hash(experiment_id)[:40]
            output_dir = _data_root / storage_key / pair.pair_id / arm_name / str(attempt_no)
            try:
                base_input = load_aurora_input(request.city_id, pair.window_id)
                if base_input.snapshot_hash != current.manifest["snapshot_sha256"] or _hash(_common_input_payload(base_input, request, pair.seed)) != pair.common_input_sha256:
                    raise SimulationError("comparison_pair_mismatch", "A entrada comum não corresponde ao hash congelado.")
                if arm_name == "strategy":
                    run_input = apply_signal_timing_intervention(base_input, SignalTimingIntervention.model_validate(strategy["intervention"]))
                else:
                    run_input = base_input
                result = run_simulation(city_id=request.city_id, window_id=pair.window_id, seed=pair.seed,
                    inputs=run_input, limits=SimulationLimits(drain_limit_seconds=request.drain_limit_seconds,
                    wall_timeout_seconds=request.budget.max_wall_clock_seconds_per_run, output_directory=str(output_dir)))
                if not _result_matches_frozen_sumo(result, current.manifest):
                    _finish_attempt(experiment_id, pair.pair_id, arm_name, result=result,
                        error="execution_environment_mismatch", elapsed=time.monotonic() - started)
                    _mark_environment_mismatch(experiment_id, pair.pair_id)
                    return
                _finish_attempt(experiment_id, pair.pair_id, arm_name, result=result, elapsed=time.monotonic() - started)
            except SimulationError as exc:
                pre_sumo_errors = {"sumo_unavailable", "invalid_input", "invalid_scenario", "invalid_limits", "comparison_pair_mismatch"}
                _finish_attempt(experiment_id, pair.pair_id, arm_name, error=exc.code, elapsed=time.monotonic() - started, consumes_run=exc.code not in pre_sumo_errors)
            except Exception:
                _finish_attempt(experiment_id, pair.pair_id, arm_name, error="execution_failed", elapsed=time.monotonic() - started)
            if _is_cancelled(experiment_id): break
        _complete_pair(experiment_id, pair.pair_id)
        current = get_experiment(experiment_id)
        if current.status == "partial" and current.stop_reason == "budget_exhausted": return
    _rebuild_summaries(experiment_id)


def _is_cancelled(experiment_id: str) -> bool:
    with _connect() as db:
        row = db.execute("SELECT cancel_requested FROM mobility_experiments WHERE experiment_id=?", (experiment_id,)).fetchone()
    return bool(row and row["cancel_requested"])


def _claim_attempt(experiment_id: str, pair_id: str, arm_name: str) -> bool:
    def claim(dto, cancelled):
        if cancelled: return False
        pair = next(p for p in dto["pairs"] if p["pair_id"] == pair_id)
        arm = pair["executions"][arm_name]
        budget = dto["manifest"]["budget"]
        if arm["status"] == "succeeded": return True
        if len(arm["attempts"]) >= budget["max_attempts_per_execution"]:
            arm["status"] = "failed"
            pair["status"] = "failed"
            return False
        if arm["status"] == "running": return False
        if dto["sumo_runs_used"] >= budget["max_sumo_runs"] or dto["wall_clock_seconds_used"] + dto.get("reserved_wall_clock_seconds", 0) + budget["max_wall_clock_seconds_per_run"] > budget["max_total_wall_clock_seconds"]:
            dto["stop_reason"] = "budget_exhausted"
            pair["status"] = "queued"
            return False
        arm["status"] = "running"
        pair["status"] = "running"
        arm_input_hash = pair["baseline_arm_input_sha256"] if arm_name == "baseline" else pair["strategy_arm_input_sha256"]
        arm.update(seed=pair["seed"], window_id=pair["window_id"], common_input_sha256=pair["common_input_sha256"], arm_input_sha256=arm_input_hash)
        sumo_environment = dto["manifest"]["sumo_environment"]
        arm["attempts"].append(AttemptDTO(attempt=len(arm["attempts"])+1, status="running", started_at=_now(),
            seed=pair["seed"], window_id=pair["window_id"], common_input_sha256=pair["common_input_sha256"], arm_input_sha256=arm_input_hash,
            backend_code_sha256=dto["manifest"]["backend_code_sha256"], python_runtime=dto["manifest"]["python_runtime"],
            container_digest=dto["manifest"]["container_digest"], sumo_adapter_version=dto["manifest"]["sumo_adapter_version"],
            runtime_dependencies=dto["manifest"]["runtime_dependencies"],
            sumo_binary_sha256=(sumo_environment.get("sumo") or {}).get("sha256"),
            netconvert_binary_sha256=(sumo_environment.get("netconvert") or {}).get("sha256")).model_dump(mode="json"))
        dto["sumo_runs_used"] += 1
        dto["reserved_wall_clock_seconds"] = dto.get("reserved_wall_clock_seconds", 0) + budget["max_wall_clock_seconds_per_run"]
        return True
    claimed, _ = _mutate(experiment_id, claim)
    return claimed


def _artifact_data(result: SimulationResult, required: set[str]) -> tuple[str, dict[str, Any]]:
    files: dict[str, Any] = {}
    for name, path_value in result.artifacts.model_dump().items():
        if not path_value: continue
        path = Path(path_value)
        try:
            data = path.read_bytes()
        except OSError:
            continue
        if not data:
            continue
        files[name] = {"path": str(path), "sha256": hashlib.sha256(data).hexdigest(), "size_bytes": len(data)}
    missing = required - set(files)
    if missing:
        raise SimulationError("artifact_missing", "Artefatos obrigatórios ausentes ou vazios: " + ", ".join(sorted(missing)))
    return _hash(files), files


def _finish_attempt(experiment_id: str, pair_id: str, arm_name: str, *, result: SimulationResult | None = None, error: str | None = None, elapsed: float, consumes_run: bool = True) -> None:
    if result:
        current = get_experiment(experiment_id)
        required_artifacts = {"network_file", "routes_file", "tripinfo_file"}
        if "mean_queue_length_meters" in current.manifest["metrics"]:
            required_artifacts.add("queue_file")
        artifact_hash, files = _artifact_data(result, required_artifacts)
    else:
        artifact_hash, files = None, {}
    def finish(dto, cancelled):
        pair = next(p for p in dto["pairs"] if p["pair_id"] == pair_id)
        arm = pair["executions"][arm_name]
        attempt = arm["attempts"][-1]
        if cancelled:
            status, err = "cancelled", "cancelled"
        elif result is not None and error is None:
            status, err = "succeeded", None
        else:
            status, err = "failed", error or "execution_failed"
        attempt.update(status=status, error=err, artifact_sha256=artifact_hash, artifacts=files, finished_at=_now(), wall_clock_seconds=elapsed)
        if result is not None:
            attempt["sumo_engine"] = result.engine
            attempt["sumo_version"] = result.engine_version
        arm["status"] = status
        dto["reserved_wall_clock_seconds"] = max(0, dto.get("reserved_wall_clock_seconds", 0) - dto["manifest"]["budget"]["max_wall_clock_seconds_per_run"])
        if not consumes_run:
            dto["sumo_runs_used"] = max(0, dto["sumo_runs_used"] - 1)
        else:
            dto["wall_clock_seconds_used"] += elapsed
        if result is not None and status == "succeeded":
            arm["result_metrics"] = result.metrics.model_dump(mode="json")
            arm["engine_version"] = result.engine_version
            arm["metric_methods"] = result.metric_methods
            arm["artifact_sha256"] = artifact_hash
            arm["artifacts"] = files
            arm["result_identity"] = {"city_id": result.city_id, "snapshot_id": result.snapshot_id,
                "snapshot_hash": result.snapshot_hash, "window_id": result.window_id, "seed": result.seed,
                "engine": result.engine, "engine_version": result.engine_version}
            if arm_name == "baseline":
                strategy = next(s for s in dto["manifest"]["strategies"] if s["strategy_id"] == pair["strategy_id"])
                raw_input = load_aurora_input(dto["manifest"]["city_id"], pair["window_id"])
                pair["route_exposure"] = _has_route_exposure(raw_input, SignalTimingIntervention.model_validate(strategy["intervention"]), result)
        if error and len(arm["attempts"]) >= dto["manifest"]["budget"]["max_attempts_per_execution"]:
            pair["status"] = "failed"
        elif error:
            pair["status"] = "queued"
        else:
            pair["status"] = "running"
    _mutate(experiment_id, finish)


def _complete_pair(experiment_id: str, pair_id: str) -> None:
    def complete(dto, cancelled):
        pair = next(p for p in dto["pairs"] if p["pair_id"] == pair_id)
        base = pair["executions"]["baseline"]
        strategy = pair["executions"]["strategy"]
        if cancelled:
            pair["status"] = "cancelled"
            for arm in pair["executions"].values():
                if arm["status"] == "queued": arm["status"] = "cancelled"
            return
        if base["status"] == "failed" or strategy["status"] == "failed":
            attempts_cap = dto["manifest"]["budget"]["max_attempts_per_execution"]
            exhausted = any(arm["status"] == "failed" and len(arm["attempts"]) >= attempts_cap for arm in pair["executions"].values())
            pair["status"] = "failed" if exhausted else "queued"
            return
        if base["status"] != "succeeded" or strategy["status"] != "succeeded":
            pair["status"] = "queued"
            return
        base_identity = base.get("result_identity") or {}
        strategy_identity = strategy.get("result_identity") or {}
        paired_fields = ("city_id", "snapshot_id", "snapshot_hash", "window_id", "seed", "engine", "engine_version")
        if (pair["baseline_arm_input_sha256"] == pair["strategy_arm_input_sha256"] or
            any(base_identity.get(field) != strategy_identity.get(field) for field in paired_fields) or
            base_identity.get("city_id") != dto["manifest"]["city_id"] or
            base_identity.get("window_id") != pair["window_id"] or base_identity.get("seed") != pair["seed"] or
            base_identity.get("snapshot_hash") != dto["manifest"]["snapshot_sha256"]):
            pair["status"] = "failed"
            pair["error"] = "comparison_pair_mismatch"
            return
        strategy_id = pair["strategy_id"]
        selected = next(s for s in dto["manifest"]["strategies"] if s["strategy_id"] == strategy_id)
        base_metrics = base["result_metrics"]
        strategy_metrics = strategy["result_metrics"]
        artifact_base = base.get("artifact_sha256")
        artifact_strategy = strategy.get("artifact_sha256")
        files_base = base.get("artifacts", {})
        files_strategy = strategy.get("artifacts", {})
        units = {"trips_requested": "trips", "trips_completed": "trips", "trips_not_completed": "trips", "mean_travel_time_seconds": "seconds", "mean_speed_kmh": "km/h", "mean_queue_length_meters": "meters"}
        periods = {"trips_requested": "demand_window", "trips_completed": "completed_trips_through_drain", "trips_not_completed": "completed_trips_through_drain", "mean_travel_time_seconds": "completed_trips_through_drain", "mean_speed_kmh": "completed_trips_through_drain", "mean_queue_length_meters": "demand_window"}
        metric_ids = dto["manifest"]["metrics"]
        demand_hash = dto["manifest"]["demand_by_window"][pair["window_id"]]["demand_sha256"]
        def metric_artifact(metric: str, files: dict[str, Any], fallback: str) -> str:
            if metric == "trips_requested": return demand_hash
            source = "queue_file" if metric == "mean_queue_length_meters" else "tripinfo_file"
            return files[source]["sha256"] if source in files else fallback
        pair["baseline_metrics"] = {m: MetricValue(value=base_metrics.get(m), unit=units[m], period=periods[m], provenance_kind="synthetic_generated" if m == "trips_requested" else "simulated", method_version=dto["manifest"]["method_version"], artifact_sha256=metric_artifact(m, files_base, artifact_base)).model_dump(mode="json") for m in metric_ids}
        pair["strategy_metrics"] = {m: MetricValue(value=strategy_metrics.get(m), unit=units[m], period=periods[m], provenance_kind="synthetic_generated" if m == "trips_requested" else "simulated", method_version=dto["manifest"]["method_version"], artifact_sha256=metric_artifact(m, files_strategy, artifact_strategy)).model_dump(mode="json") for m in metric_ids}
        pair["deltas"] = {m: DerivedMetric(value=(strategy_metrics[m] - base_metrics[m]) if strategy_metrics.get(m) is not None and base_metrics.get(m) is not None else None, unit=units[m], method_version="paired-delta-v1", source_artifact_sha256=[metric_artifact(m, files_base, artifact_base), metric_artifact(m, files_strategy, artifact_strategy)]).model_dump(mode="json") for m in metric_ids}
        pair["status"] = "succeeded"
        pair["artifact_files"] = {"baseline": files_base, "strategy": files_strategy}
    _mutate(experiment_id, complete)


def _summary(values: list[float]) -> NumericSummary:
    if not values: return NumericSummary()
    ordered = sorted(values)
    q1, _, q3 = _quartiles(ordered)
    return NumericSummary(mean=statistics.mean(values), sd=statistics.stdev(values) if len(values) >= 2 else None,
        median=statistics.median(values), iqr=q3 - q1 if len(values) >= 2 else None, min=min(values), max=max(values))


def _quartiles(values: list[float]) -> tuple[float, float, float]:
    if len(values) == 1: return values[0], values[0], values[0]
    median = statistics.median(values)
    lower = values[:len(values)//2]
    upper = values[(len(values)+1)//2:]
    return statistics.median(lower), median, statistics.median(upper)


def _regularized_beta(x: float, a: float, b: float) -> float:
    # Continued fraction (Numerical Recipes), sufficient for Student-t quantiles.
    def cf(aa, bb, xx):
        qab, qap, qam = aa + bb, aa + 1, aa - 1
        c, d = 1.0, 1.0 - qab * xx / qap
        d = 1e-300 if abs(d) < 1e-300 else d
        d = 1.0 / d
        h = d
        for m in range(1, 201):
            m2 = 2 * m
            term = m * (bb - m) * xx / ((qam + m2) * (aa + m2))
            d = 1 + term * d; d = 1e-300 if abs(d) < 1e-300 else d
            c = 1 + term / c; c = 1e-300 if abs(c) < 1e-300 else c
            d = 1 / d; h *= d * c
            term = -(aa + m) * (qab + m) * xx / ((aa + m2) * (qap + m2))
            d = 1 + term * d; d = 1e-300 if abs(d) < 1e-300 else d
            c = 1 + term / c; c = 1e-300 if abs(c) < 1e-300 else c
            d = 1 / d; delta = d * c; h *= delta
            if abs(delta - 1) < 3e-14: break
        return h
    if x <= 0: return 0.0
    if x >= 1: return 1.0
    front = math.exp(math.lgamma(a+b)-math.lgamma(a)-math.lgamma(b)+a*math.log(x)+b*math.log1p(-x))
    if x < (a+1)/(a+b+2): return front * cf(a,b,x) / a
    return 1 - front * cf(b,a,1-x) / b


def _student_t_critical(df: int, level: float) -> float:
    target = (1 + level) / 2
    low, high = 0.0, 1000.0
    for _ in range(100):
        mid = (low + high) / 2
        cdf = 1 - 0.5 * _regularized_beta(df / (df + mid * mid), df / 2, 0.5)
        if cdf < target: low = mid
        else: high = mid
    return (low + high) / 2


def _rebuild_summaries(experiment_id: str) -> None:
    def rebuild(dto, cancelled):
        result = []
        for window_id in dto["manifest"]["window_ids"]:
            for strategy in dto["manifest"]["strategies"]:
                relevant = [p for p in dto["pairs"] if p["window_id"] == window_id and p["strategy_id"] == strategy["strategy_id"]]
                complete = [p for p in relevant if p["status"] == "succeeded"]
                for metric in dto["manifest"]["metrics"]:
                    valid = [p for p in complete if p["baseline_metrics"][metric]["value"] is not None
                             and p["strategy_metrics"][metric]["value"] is not None
                             and p["deltas"][metric]["value"] is not None]
                    base_values = [p["baseline_metrics"][metric]["value"] for p in valid]
                    strategy_values = [p["strategy_metrics"][metric]["value"] for p in valid]
                    deltas = [p["deltas"][metric]["value"] for p in valid]
                    metric_complete = len(valid) == len(relevant)
                    tol = dto["manifest"]["metric_tolerances"][metric]
                    def differs(a, b):
                        if a is None or b is None: return False
                        if tol.get("exact"): return a != b
                        return abs(a-b) > tol.get("absolute", 0) and abs(a-b) / max(abs(a), abs(b), 1e-300) > tol.get("relative", 0)
                    sensitivity = "insufficient_data"
                    delta_sensitivity = "insufficient_data"
                    if len(valid) >= 2 and metric_complete:
                        observed = any(
                            differs(valid[i][arm + "_metrics"][metric]["value"], valid[j][arm + "_metrics"][metric]["value"])
                            for i in range(len(valid)) for j in range(i + 1, len(valid)) for arm in ("baseline", "strategy")
                        )
                        sensitivity = "observed_variation" if observed else "no_variation_observed"
                        delta_observed = any(
                            differs(valid[i]["deltas"][metric]["value"], valid[j]["deltas"][metric]["value"])
                            for i in range(len(valid)) for j in range(i + 1, len(valid))
                        )
                        delta_sensitivity = "observed_variation" if delta_observed else "no_variation_observed"
                    avg = statistics.mean(deltas) if len(deltas) >= 2 else None
                    sd = statistics.stdev(deltas) if len(deltas) >= 2 else None
                    half = _student_t_critical(len(deltas)-1, dto["manifest"]["confidence_level"]) * sd / math.sqrt(len(deltas)) if sd is not None and metric_complete else None
                    _, period = _metric_unit_period(metric)
                    result.append(WindowSummary(window_id=window_id, strategy_id=strategy["strategy_id"], metric_id=metric,
                        unit=_metric_unit_period(metric)[0], period=period, method_version="summary-student-t-v1", n_planned=len(relevant), n_complete=len(valid),
                        arm_summary={"baseline": _summary([float(v) for v in base_values]),
                                     "strategy": _summary([float(v) for v in strategy_values])}, paired_delta_summary=_summary([float(v) for v in deltas]),
                        confidence_interval=ConfidenceInterval(level=dto["manifest"]["confidence_level"], lower=avg-half if half is not None else None,
                            upper=avg+half if half is not None else None, n=len(deltas), degrees_of_freedom=len(deltas)-1 if len(deltas)>=2 else None),
                        selection="complete_pairs_only", seed_sensitivity=sensitivity,
                        arm_seed_sensitivity=sensitivity, paired_delta_seed_sensitivity=delta_sensitivity).model_dump(mode="json"))
        dto["summaries_by_window"] = result
        if cancelled:
            dto["status"] = "cancelled"
        elif dto["status"] == "running":
            dto["status"] = "succeeded" if dto["completed_pairs"] == dto["planned_pairs"] else "partial"
    _mutate(experiment_id, rebuild)


def _metric_unit_period(metric: str) -> tuple[str, str]:
    return {
        "trips_requested": ("trips", "demand_window"),
        "trips_completed": ("trips", "completed_trips_through_drain"),
        "trips_not_completed": ("trips", "completed_trips_through_drain"),
        "mean_travel_time_seconds": ("seconds", "completed_trips_through_drain"),
        "mean_speed_kmh": ("km/h", "completed_trips_through_drain"),
        "mean_queue_length_meters": ("meters", "demand_window"),
    }[metric]


_initialize()
