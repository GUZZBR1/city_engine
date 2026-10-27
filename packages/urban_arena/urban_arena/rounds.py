"""Protocol-only deterministic round coordination for the no-action baseline.

This module records the Arena clock and an atomic round receipt. It deliberately
does not model annual city-domain changes or produce annual indicators.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from threading import RLock
from typing import Literal

from pydantic import Field, model_validator

from .city import generate_snapshot
from .models import CityConfigFile, CitySnapshot, StrictModel


def _canonical_json(payload: dict[str, object]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _canonical_hash(payload: dict[str, object]) -> str:
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


class RoundBudgetEnvelope(StrictModel):
    """Configured per-round envelope; not a persistent cash ledger."""

    currency: Literal["simulated_urban_credits"]
    total_cs: int = Field(ge=0)
    fixed_operations_cs: int = Field(ge=0)
    reserve_cs: int = Field(ge=0)
    discretionary_limit_cs: int = Field(ge=0)
    discretionary_spent_cs: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_envelope(self) -> RoundBudgetEnvelope:
        if self.fixed_operations_cs + self.reserve_cs + self.discretionary_limit_cs != self.total_cs:
            raise ValueError("parcelas do envelope devem fechar com total_cs")
        if self.discretionary_spent_cs > self.discretionary_limit_cs:
            raise ValueError("gasto discricionário excede o limite da rodada")
        return self


class RoundCandidate(StrictModel):
    """Validated isolated candidate for a no-action protocol cycle."""

    contract_version: Literal["1.0"] = "1.0"
    experiment_id: str = Field(min_length=1)
    instance_id: str = Field(min_length=1)
    round_index: int = Field(ge=1)
    synthetic_year: int = Field(ge=1)
    initial_snapshot_id: str
    parent_state_hash: str
    parent_round_hash: str | None = None
    candidate_city_state_hash: str
    candidate_city_state_json: str
    policy_id: Literal["no_action"] = "no_action"
    actions: tuple[()] = ()
    domain_transition: Literal["not_run"] = "not_run"
    budget: RoundBudgetEnvelope
    provenance: Literal["synthetic"] = "synthetic"

    @model_validator(mode="after")
    def validate_no_action_candidate(self) -> RoundCandidate:
        if self.synthetic_year != self.round_index:
            raise ValueError("synthetic_year deve corresponder a round_index")
        if self.candidate_city_state_hash != self.parent_state_hash:
            raise ValueError("no_action não pode alterar o hash do estado da cidade")
        if self.budget.discretionary_spent_cs != 0:
            raise ValueError("no_action não pode gastar orçamento discricionário")
        return self


class RoundRecord(StrictModel):
    """Committed, deterministic record for the coordination cycle."""

    contract_version: Literal["1.0"] = "1.0"
    experiment_id: str
    instance_id: str
    round_index: int = Field(ge=1)
    synthetic_year: int = Field(ge=1)
    initial_snapshot_id: str
    parent_state_hash: str
    city_state_hash: str
    parent_round_hash: str | None = None
    policy_id: Literal["no_action"] = "no_action"
    actions: tuple[()] = ()
    domain_transition: Literal["not_run"] = "not_run"
    budget: RoundBudgetEnvelope
    metrics: tuple[()] = ()
    provenance: Literal["synthetic"] = "synthetic"
    status: Literal["committed"] = "committed"
    record_hash: str

    @model_validator(mode="after")
    def validate_committed_record(self) -> RoundRecord:
        if self.synthetic_year != self.round_index:
            raise ValueError("synthetic_year deve corresponder a round_index")
        if self.city_state_hash != self.parent_state_hash:
            raise ValueError("no_action deve preservar o hash do estado da cidade")
        if self.budget.discretionary_spent_cs != 0:
            raise ValueError("no_action não pode gastar orçamento discricionário")
        expected = _canonical_hash(self.model_dump(mode="json", exclude={"record_hash"}))
        if self.record_hash != expected:
            raise ValueError("record_hash não confere com o conteúdo canônico")
        return self


class RoundConflictError(ValueError):
    """Raised when a candidate is stale or reuses a round identity differently."""


@dataclass(frozen=True)
class _CommittedArenaState:
    city_state_json: str
    city_state_hash: str
    records: tuple[RoundRecord, ...]


def prepare_no_action_round(
    config: CityConfigFile,
    snapshot: CitySnapshot,
    *,
    experiment_id: str,
    instance_id: str,
    round_index: int,
    parent_round_hash: str | None = None,
) -> RoundCandidate:
    """Build a deterministic no-action candidate without changing city domains."""
    canonical_snapshot = generate_snapshot(config)
    if snapshot.city_id != config.city.id or snapshot.hash != canonical_snapshot.hash:
        raise ValueError("snapshot não corresponde à configuração fornecida")
    if _canonical_json(snapshot.model_dump(mode="json")) != _canonical_json(
        canonical_snapshot.model_dump(mode="json")
    ):
        raise ValueError("conteúdo do snapshot diverge do payload canônico")
    if "no_action" not in config.arena.reference_policies:
        raise ValueError("política de referência no_action não está configurada")
    if round_index > config.arena.default_horizon_rounds:
        raise ValueError("round_index excede o horizonte configurado")

    # Recheck only balances with defined semantics. No annual domain equations
    # exist yet, so the candidate is an independent serialized copy of its parent.
    if snapshot.population.total != config.population.total_residents:
        raise ValueError("total populacional do snapshot diverge da configuração")
    if sum(int(district["residents"]) for district in snapshot.districts) != snapshot.population.total:
        raise ValueError("residentes distritais não fecham com o snapshot")
    if sum(int(district["jobs"]) for district in snapshot.districts) != snapshot.jobs:
        raise ValueError("empregos distritais não fecham com o snapshot")

    budget = RoundBudgetEnvelope(
        currency=config.finance.currency,
        total_cs=config.finance.credits_per_round,
        fixed_operations_cs=config.finance.fixed_operations,
        reserve_cs=config.finance.reserve,
        discretionary_limit_cs=config.finance.discretionary_budget,
        discretionary_spent_cs=0,
    )
    snapshot_json = _canonical_json(snapshot.model_dump(mode="json"))
    return RoundCandidate(
        experiment_id=experiment_id,
        instance_id=instance_id,
        round_index=round_index,
        synthetic_year=round_index,
        initial_snapshot_id=snapshot.snapshot_id,
        parent_state_hash=snapshot.hash,
        parent_round_hash=parent_round_hash,
        candidate_city_state_hash=snapshot.hash,
        candidate_city_state_json=snapshot_json,
        budget=budget,
    )


class RoundStore:
    """In-memory atomic/CAS store for protocol records, not durable persistence."""

    def __init__(self, snapshot: CitySnapshot) -> None:
        self._lock = RLock()
        state_json = _canonical_json(snapshot.model_dump(mode="json"))
        self._committed = _CommittedArenaState(state_json, snapshot.hash, ())

    @property
    def city_state(self) -> CitySnapshot:
        """Return a fresh model so callers cannot mutate the stored representation."""
        with self._lock:
            return CitySnapshot.model_validate(json.loads(self._committed.city_state_json))

    @property
    def city_state_hash(self) -> str:
        with self._lock:
            return self._committed.city_state_hash

    @property
    def records(self) -> tuple[RoundRecord, ...]:
        with self._lock:
            return self._committed.records

    def commit(self, candidate: RoundCandidate) -> RoundRecord:
        """Atomically append a validated receipt after parent/hash checks."""
        with self._lock:
            record_payload = {
                "contract_version": candidate.contract_version,
                "experiment_id": candidate.experiment_id,
                "instance_id": candidate.instance_id,
                "round_index": candidate.round_index,
                "synthetic_year": candidate.synthetic_year,
                "initial_snapshot_id": candidate.initial_snapshot_id,
                "parent_state_hash": candidate.parent_state_hash,
                "city_state_hash": candidate.candidate_city_state_hash,
                "parent_round_hash": candidate.parent_round_hash,
                "policy_id": candidate.policy_id,
                "actions": [],
                "domain_transition": candidate.domain_transition,
                "budget": candidate.budget.model_dump(mode="json"),
                "metrics": [],
                "provenance": candidate.provenance,
                "status": "committed",
            }
            record = RoundRecord(**record_payload, record_hash=_canonical_hash(record_payload))

            if candidate.round_index <= len(self._committed.records):
                existing = self._committed.records[candidate.round_index - 1]
                if existing.record_hash == record.record_hash:
                    return existing
                raise RoundConflictError("identidade de rodada reutilizada com conteúdo diferente")

            if candidate.round_index != len(self._committed.records) + 1:
                raise RoundConflictError("round_index não é a próxima rodada esperada")
            if self._committed.records:
                first_record = self._committed.records[0]
                if (candidate.experiment_id, candidate.instance_id) != (
                    first_record.experiment_id,
                    first_record.instance_id,
                ):
                    raise RoundConflictError("store não pode misturar experimentos ou instâncias")
            if candidate.parent_state_hash != self._committed.city_state_hash:
                raise RoundConflictError("hash do estado pai está obsoleto")
            expected_parent_round_hash = self._committed.records[-1].record_hash if self._committed.records else None
            if candidate.parent_round_hash != expected_parent_round_hash:
                raise RoundConflictError("hash do registro de rodada pai está obsoleto")
            if candidate.candidate_city_state_json != self._committed.city_state_json:
                raise RoundConflictError("candidato alterou o estado da cidade na política no_action")

            # One pointer replacement publishes the receipt and candidate state together.
            self._committed = _CommittedArenaState(
                city_state_json=candidate.candidate_city_state_json,
                city_state_hash=candidate.candidate_city_state_hash,
                records=self._committed.records + (record,),
            )
            return record
