"""Typed API contracts for the isolated Aurora paired multi-seed protocol."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from simulation import SignalTimingIntervention


Hash = str
MAX_WINDOWS_PER_EXPERIMENT = 2
MAX_SEEDS_PER_EXPERIMENT = 50
MAX_STRATEGIES_PER_EXPERIMENT = 10
MAX_PLANNED_PAIRS_PER_EXPERIMENT = 100
MAX_ATTEMPTS_PER_EXECUTION = 3
MAX_SUMO_RUNS_PER_EXPERIMENT = 600
MAX_WALL_CLOCK_SECONDS_PER_EXPERIMENT = 86_400


class StrictDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MultiSeedBudget(StrictDTO):
    max_sumo_runs: int = Field(gt=0, le=MAX_SUMO_RUNS_PER_EXPERIMENT)
    max_attempts_per_execution: int = Field(ge=1, le=MAX_ATTEMPTS_PER_EXECUTION)
    max_reproducibility_checks: int = Field(ge=0, default=0)
    max_wall_clock_seconds_per_run: float = Field(gt=0, le=3600)
    max_total_wall_clock_seconds: float = Field(gt=0, le=MAX_WALL_CLOCK_SECONDS_PER_EXPERIMENT)
    admit_incomplete: bool = False


class MultiSeedStrategy(StrictDTO):
    strategy_id: str = Field(min_length=1)
    policy_version: str = Field(min_length=1)
    policy_sha256: Hash = Field(pattern=r"^[0-9a-f]{64}$")
    intervention: SignalTimingIntervention


class MultiSeedManifestRequest(StrictDTO):
    """Inputs frozen before execution; windows and seeds are always explicit."""

    experiment_id: str | None = Field(default=None, min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    arena_manifest_id: str = Field(min_length=1)
    arena_manifest_sha256: Hash = Field(pattern=r"^[0-9a-f]{64}$")
    round_index: int = Field(ge=0)
    instance_id: str = Field(min_length=1)
    proposal_id: str | None = None
    action_id: str | None = None
    action_sha256: Hash | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    city_id: Literal["aurora-base-v1"]
    window_ids: list[str] = Field(min_length=1, max_length=MAX_WINDOWS_PER_EXPERIMENT)
    seeds: list[int] = Field(min_length=1, max_length=MAX_SEEDS_PER_EXPERIMENT)
    strategies: list[MultiSeedStrategy] = Field(min_length=1, max_length=MAX_STRATEGIES_PER_EXPERIMENT)
    baseline_id: str = Field(min_length=1)
    baseline_version: str = Field(min_length=1)
    baseline_sha256: Hash = Field(pattern=r"^[0-9a-f]{64}$")
    drain_limit_seconds: int = Field(ge=0, le=604800)
    metrics: list[str] = Field(min_length=1)
    metric_tolerances: dict[str, dict[str, float | bool]]
    method_version: str = "sumo-metrics-v1"
    budget: MultiSeedBudget
    reproducibility_checks: int = Field(ge=0, default=0)
    selection_method: str = "externally_predeclared"
    master_seed: int | None = Field(default=None, ge=0)
    primary_metrics: list[str] = Field(min_length=1)
    confidence_level: float = Field(gt=0, lt=1, default=0.95)
    limitations: list[str] = Field(default_factory=lambda: [
        "synthetic_aurora", "window_only", "network_aggregated", "not_causal", "not_real_world_validated"
    ])

    @model_validator(mode="after")
    def validate_plan(self) -> "MultiSeedManifestRequest":
        if len(self.window_ids) != len(set(self.window_ids)):
            raise ValueError("window_ids não pode conter duplicatas.")
        if len(self.seeds) != len(set(self.seeds)) or any(seed < 0 for seed in self.seeds):
            raise ValueError("seeds devem ser inteiras, não negativas e sem duplicatas.")
        if any(isinstance(seed, bool) for seed in self.seeds):
            raise ValueError("seeds não podem ser booleanas.")
        if len({item.strategy_id for item in self.strategies}) != len(self.strategies):
            raise ValueError("strategy_id duplicado.")
        planned_pairs = len(self.window_ids) * len(self.seeds) * len(self.strategies)
        if planned_pairs > MAX_PLANNED_PAIRS_PER_EXPERIMENT:
            raise ValueError(
                f"A matriz excede o limite absoluto de {MAX_PLANNED_PAIRS_PER_EXPERIMENT} pares por experimento."
            )
        supported_metrics = {"trips_requested", "trips_completed", "trips_not_completed", "mean_travel_time_seconds", "mean_speed_kmh", "mean_queue_length_meters"}
        if not set(self.metrics) <= supported_metrics:
            raise ValueError("metrics contém identificadores não suportados pelo executor SUMO.")
        if len(self.metrics) != len(set(self.metrics)) or len(self.primary_metrics) != len(set(self.primary_metrics)):
            raise ValueError("metrics e primary_metrics não podem conter duplicatas.")
        if {"mean_travel_time_seconds", "mean_speed_kmh"} & set(self.metrics):
            required_trip_counts = {"trips_requested", "trips_completed", "trips_not_completed"}
            if not required_trip_counts <= set(self.metrics):
                raise ValueError("Métricas de tempo/velocidade exigem trips_requested, trips_completed e trips_not_completed.")
        if not set(self.primary_metrics) <= set(self.metrics):
            raise ValueError("primary_metrics deve ser subconjunto de metrics.")
        if not set(self.metrics) <= set(self.metric_tolerances):
            raise ValueError("cada métrica precisa de tolerância pré-declarada.")
        for key, tolerance in self.metric_tolerances.items():
            if "exact" not in tolerance and not {"absolute", "relative"} <= set(tolerance):
                raise ValueError(f"Tolerância incompleta para {key}.")
            if any(v < 0 for k, v in tolerance.items() if k != "exact"):
                raise ValueError(f"Tolerância negativa para {key}.")
        if self.reproducibility_checks != self.budget.max_reproducibility_checks:
            raise ValueError("reproducibility_checks deve corresponder ao teto congelado.")
        if self.reproducibility_checks:
            raise ValueError("Esta versão não agenda technical checks; declare zero até a rota de reprodutibilidade estar disponível.")
        return self


class MetricValue(StrictDTO):
    value: float | int | None
    unit: str
    period: Literal["demand_window", "completed_trips_through_drain"]
    provenance_kind: Literal["synthetic_config", "synthetic_generated", "simulated"] = "simulated"
    method_version: str
    artifact_sha256: Hash


class DerivedMetric(StrictDTO):
    value: float | int | None
    unit: str
    direction: Literal["strategy_minus_baseline"] = "strategy_minus_baseline"
    provenance_kind: Literal["derived"] = "derived"
    method_version: str
    source_artifact_sha256: list[Hash] = Field(min_length=2, max_length=2)


class AttemptDTO(StrictDTO):
    attempt: int
    status: Literal["queued", "running", "succeeded", "failed", "cancelled"]
    error: str | None = None
    artifact_sha256: Hash | None = None
    started_at: str | None = None
    finished_at: str | None = None
    wall_clock_seconds: float = 0
    artifacts: dict[str, Any] = Field(default_factory=dict)
    seed: int | None = None
    window_id: str | None = None
    common_input_sha256: Hash | None = None
    arm_input_sha256: Hash | None = None
    backend_code_sha256: Hash | None = None
    python_runtime: str | None = None
    container_digest: str | None = None
    sumo_adapter_version: str | None = None
    runtime_dependencies: dict[str, str] = Field(default_factory=dict)
    sumo_binary_sha256: Hash | None = None
    netconvert_binary_sha256: Hash | None = None
    sumo_engine: str | None = None
    sumo_version: str | None = None


class ArmDTO(StrictDTO):
    execution_id: str
    status: Literal["queued", "running", "succeeded", "failed", "cancelled"]
    attempts: list[AttemptDTO]
    result_metrics: dict[str, float | int | None] | None = None
    engine_version: str | None = None
    metric_methods: dict[str, str] = Field(default_factory=dict)
    artifact_sha256: Hash | None = None
    artifacts: dict[str, Any] = Field(default_factory=dict)
    result_identity: dict[str, Any] | None = None
    seed: int | None = None
    window_id: str | None = None
    common_input_sha256: Hash | None = None
    arm_input_sha256: Hash | None = None


class PairDTO(StrictDTO):
    pair_id: str
    strategy_id: str
    baseline_execution_id: str
    strategy_execution_id: str
    window_id: str
    seed: int
    common_input_sha256: Hash
    baseline_arm_input_sha256: Hash
    strategy_arm_input_sha256: Hash
    status: Literal["queued", "running", "succeeded", "failed", "cancelled"]
    baseline_metrics: dict[str, MetricValue] = Field(default_factory=dict)
    strategy_metrics: dict[str, MetricValue] = Field(default_factory=dict)
    deltas: dict[str, DerivedMetric] = Field(default_factory=dict)
    route_exposure: Literal["exposed", "not_exposed", "unknown"] = "unknown"
    error: str | None = None
    artifact_files: dict[str, Any] = Field(default_factory=dict)
    executions: dict[str, ArmDTO]


class NumericSummary(StrictDTO):
    mean: float | None = None
    sd: float | None = None
    median: float | None = None
    iqr: float | None = None
    min: float | None = None
    max: float | None = None


class ConfidenceInterval(StrictDTO):
    method: Literal["student_t_paired"] = "student_t_paired"
    level: float = 0.95
    lower: float | None = None
    upper: float | None = None
    n: int
    degrees_of_freedom: int | None = None
    interpretation: Literal["conditional_monte_carlo_only"] = "conditional_monte_carlo_only"
    multiplicity: Literal["marginal_descriptive"] = "marginal_descriptive"


class WindowSummary(StrictDTO):
    window_id: str
    strategy_id: str
    metric_id: str
    unit: str
    period: Literal["demand_window", "completed_trips_through_drain"]
    provenance_kind: Literal["derived"] = "derived"
    method_version: str
    n_planned: int
    n_complete: int
    arm_summary: dict[str, NumericSummary]
    paired_delta_summary: NumericSummary
    confidence_interval: ConfidenceInterval
    selection: Literal["complete_pairs_only"] = "complete_pairs_only"
    seed_sensitivity: Literal["observed_variation", "no_variation_observed", "insufficient_data"] = "insufficient_data"
    arm_seed_sensitivity: Literal["observed_variation", "no_variation_observed", "insufficient_data"] = "insufficient_data"
    paired_delta_seed_sensitivity: Literal["observed_variation", "no_variation_observed", "insufficient_data"] = "insufficient_data"


class ExperimentDTO(StrictDTO):
    experiment_id: str
    dto_schema_version: Literal["1.0"] = "1.0"
    protocol_id: Literal["aurora-paired-multiseed-v1"] = "aurora-paired-multiseed-v1"
    protocol_version: Literal[1] = 1
    manifest_sha256: Hash
    arena_manifest_id: str
    arena_manifest_sha256: Hash
    status: Literal["queued", "running", "succeeded", "partial", "failed", "cancelled"]
    cancellation_requested: bool = False
    planned_pairs: int
    completed_pairs: int
    failed_pairs: int
    running_pairs: int
    missing_pairs: int
    missing_pair_ids: list[str] = Field(default_factory=list)
    planned_executions: int
    attempts: int
    sumo_runs_used: int
    wall_clock_seconds_used: float
    reserved_wall_clock_seconds: float = 0
    stop_reason: str | None = None
    error_code: str | None = None
    limitations: list[str]
    manifest: dict[str, Any]
    pairs: list[PairDTO]
    summaries_by_window: list[WindowSummary]


class ExperimentResponse(StrictDTO):
    experiment: ExperimentDTO


class ExperimentCreateResponse(StrictDTO):
    experiment: ExperimentDTO


class ExperimentRetryRequest(StrictDTO):
    pair_ids: list[str] | None = Field(default=None, min_length=1)


class ExperimentCancelResponse(StrictDTO):
    experiment_id: str
    status: Literal["running", "cancelled"]
    cancellation_requested: bool
