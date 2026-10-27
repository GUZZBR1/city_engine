"""Versioned annual city state and isolated factories.

The initial CitySnapshot remains the immutable root input. CityState is a
separate, JSON-compatible representation intended for future transition code.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import TYPE_CHECKING, Any, Literal

from pydantic import Field, model_validator

from .city import generate_snapshot
from .models import CityConfigFile, CitySnapshot, StrictModel

if TYPE_CHECKING:
    from .manifest import ExperimentManifest


def canonical_json(payload: Any) -> bytes:
    """Serialize JSON data with the canonical rules shared by state/manifest hashes."""
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def canonical_hash(payload: Any) -> str:
    return hashlib.sha256(canonical_json(payload)).hexdigest()


class CityState(StrictModel):
    """Evolutive data copied from an immutable snapshot; contains no transition logic."""

    experiment_id: str
    instance_id: str
    round_index: int = Field(ge=0, le=10)
    schema_version: str = "1.0"
    transition_version: str = "1.0"
    parent_city_state_hash: str | None = None
    snapshot_hash: str
    population: dict[str, int]
    housing: dict[str, Any]
    employment: dict[str, int]
    services: dict[str, Any] = Field(default_factory=dict)
    environment: dict[str, Any] = Field(default_factory=dict)
    budget: dict[str, int | str]
    pending_effects: list[EffectiveEvent] = Field(default_factory=list)
    active_signal_plans: list[EffectiveEvent] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_counts(self) -> CityState:
        if not self.experiment_id.strip() or not self.instance_id.strip():
            raise ValueError("experiment_id e instance_id não podem ser vazios")
        if not self._is_sha256(self.snapshot_hash):
            raise ValueError("snapshot_hash deve ser SHA-256 hexadecimal")
        if self.parent_city_state_hash is not None and not self._is_sha256(self.parent_city_state_hash):
            raise ValueError("parent_city_state_hash deve ser SHA-256 hexadecimal")
        if any(not isinstance(value, int) or value < 0 for value in self.population.values()):
            raise ValueError("population deve conter contagens inteiras não negativas")
        if any(not isinstance(value, int) or value < 0 for value in self.employment.values()):
            raise ValueError("employment deve conter contagens inteiras não negativas")
        return self

    @staticmethod
    def _is_sha256(value: str) -> bool:
        return len(value) == 64 and all(char in "0123456789abcdef" for char in value)

    @property
    def city_state_hash(self) -> str:
        """Hash state content; identity/chain metadata is excluded by contract."""
        return canonical_hash(self.payload())

    def payload(self) -> dict[str, Any]:
        data = self.model_dump(mode="json", exclude={"parent_city_state_hash"})
        # Hash represents city content and its schema, not experiment bookkeeping.
        for key in ("experiment_id", "instance_id", "round_index", "snapshot_hash"):
            data.pop(key, None)
        return data


class StateFactory:
    """Build evolutive states and deep isolated copies from the initial snapshot."""

    @staticmethod
    def from_snapshot(
        snapshot: CitySnapshot,
        *,
        manifest: ExperimentManifest,
        instance_id: str,
    ) -> CityState:
        try:
            source_config = CityConfigFile.model_validate(snapshot.source_config)
            verified_snapshot = generate_snapshot(source_config)
        except Exception as exc:
            raise ValueError("snapshot não pode ser validado contra sua configuração raiz") from exc
        snapshot_payload = snapshot.model_dump(mode="json", exclude={"hash", "snapshot_id"})
        verified_payload = verified_snapshot.model_dump(mode="json", exclude={"hash", "snapshot_id"})
        if (
            verified_snapshot.hash != snapshot.hash
            or verified_snapshot.snapshot_id != snapshot.snapshot_id
            or snapshot_payload != verified_payload
        ):
            raise ValueError("payload do snapshot não corresponde ao hash declarado")
        if manifest.snapshot_hash != verified_snapshot.hash or manifest.snapshot_id != verified_snapshot.snapshot_id:
            raise ValueError("manifesto e snapshot devem apontar para o mesmo snapshot raiz")
        districts = snapshot.districts
        urban_districts = {d["id"]: d for d in districts if d["type"] == "urban"}
        params = manifest.parameters
        occupied_urban = math.floor(
            snapshot.population.urban / params.demography.household_size + 0.5
        )
        vacancy = params.housing.vacancy_rate_target
        total_units = params.housing.initial_units
        initialization_method = "configured_initial_units"
        if total_units is None:
            total_units = math.ceil(occupied_urban / (1 - vacancy))
            initialization_method = params.housing.initial_units_method
        weights = {district_id: int(district["residents"]) for district_id, district in urban_districts.items()}
        allocation = StateFactory._allocate(total_units, weights)
        return CityState(
            experiment_id=manifest.experiment_id,
            instance_id=instance_id,
            round_index=0,
            schema_version="1.0",
            transition_version="1.0",
            parent_city_state_hash=None,
            snapshot_hash=snapshot.hash,
            population={d["id"]: int(d["residents"]) for d in districts},
            housing={
                "initialization_method": initialization_method,
                "occupied_households_reference_total": int(snapshot.household["occupied_households_derived"]),
                "occupied_households_urban": occupied_urban,
                "vacancy_rate_target": vacancy,
                "units_by_district": allocation,
                "total_units": total_units,
            },
            employment={d["id"]: int(d["jobs"]) for d in districts},
            services={},
            environment={},
            budget={str(key): int(value) if isinstance(value, int) else str(value) for key, value in snapshot.finance.items()},
        )

    @staticmethod
    def copies(
        snapshot: CitySnapshot,
        *,
        manifest: ExperimentManifest,
        instance_ids: list[str],
    ) -> list[CityState]:
        """Return equivalent independent states; no mutable nested collection is shared."""
        if not instance_ids or len(instance_ids) != len(set(instance_ids)):
            raise ValueError("instance_ids deve conter IDs únicos e pelo menos uma instância")
        states = [StateFactory.from_snapshot(snapshot, manifest=manifest, instance_id=instance_id) for instance_id in instance_ids]
        # Validate equivalence while preserving the caller's instance identities.
        if len({state.city_state_hash for state in states}) > 1:
            raise ValueError("cópias iniciais devem ter o mesmo city_state_hash")
        return states

    @staticmethod
    def candidate(parent: CityState, *, round_index: int) -> CityState:
        """Create a deep candidate shell without applying any domain transition."""
        if round_index != parent.round_index + 1:
            raise ValueError("round_index do candidato deve avançar exatamente uma rodada")
        values = parent.model_dump(mode="python")
        values.update(round_index=round_index, parent_city_state_hash=parent.city_state_hash)
        return CityState.model_validate(values)

    @staticmethod
    def _allocate(total: int, weights: dict[str, int]) -> dict[str, int]:
        denominator = sum(weights.values())
        if denominator <= 0:
            raise ValueError("não é possível ratear estoque sem população urbana positiva")
        floors = {key: total * weight // denominator for key, weight in weights.items()}
        remainder = total - sum(floors.values())
        order = sorted(weights, key=lambda key: (-(total * weights[key] % denominator), key))
        for key in order[:remainder]:
            floors[key] += 1
        return floors


class EffectiveEvent(StrictModel):
    """A versioned event scheduled to become effective in one synthetic round."""

    event_id: str
    event_type: str
    effective_round: int = Field(ge=1, le=10)
    payload: dict[str, Any]
    source_action_id: str | None = None

    @model_validator(mode="after")
    def validate_identity(self) -> EffectiveEvent:
        if not self.event_id.strip() or not self.event_type.strip():
            raise ValueError("event_id e event_type não podem ser vazios")
        return self


class DomainDelta(StrictModel):
    """Partial replacement values for exactly one CityState domain."""

    domain: Literal["population", "housing", "employment", "services", "environment", "budget"]
    values: dict[str, Any]


class CityStateDelta(StrictModel):
    """Deterministic state changes and events emitted by a domain transition."""

    parent_city_state_hash: str
    domains: tuple[DomainDelta, ...] = ()
    effective_events: tuple[EffectiveEvent, ...] = ()

    @model_validator(mode="after")
    def validate_unique_domains(self) -> CityStateDelta:
        if not CityState._is_sha256(self.parent_city_state_hash):
            raise ValueError("parent_city_state_hash deve ser SHA-256 hexadecimal")
        names = [change.domain for change in self.domains]
        if len(names) != len(set(names)):
            raise ValueError("delta não pode conter o mesmo domínio mais de uma vez")
        return self


class StateTransitionResult(StrictModel):
    """Shared result envelope; this schema performs no transition or commit."""

    experiment_id: str
    instance_id: str
    round_index: int = Field(ge=1, le=10)
    manifest_hash: str
    parent_city_state_hash: str
    city_state_hash: str
    domain_transition: Literal["applied", "not_run"]
    delta: CityStateDelta
    candidate_state: CityState | None = None

    @model_validator(mode="after")
    def validate_result_identity(self) -> StateTransitionResult:
        if not self.experiment_id.strip() or not self.instance_id.strip():
            raise ValueError("experiment_id e instance_id não podem ser vazios")
        if any(not CityState._is_sha256(value) for value in (self.manifest_hash, self.parent_city_state_hash, self.city_state_hash)):
            raise ValueError("hashes do resultado devem ser SHA-256 hexadecimal")
        if self.delta.parent_city_state_hash != self.parent_city_state_hash:
            raise ValueError("delta e resultado devem referenciar o mesmo estado pai")
        if self.candidate_state is not None:
            if self.candidate_state.experiment_id != self.experiment_id:
                raise ValueError("candidate_state pertence a outro experimento")
            if self.candidate_state.instance_id != self.instance_id:
                raise ValueError("candidate_state pertence a outra instância")
            if self.candidate_state.round_index != self.round_index:
                raise ValueError("candidate_state pertence a outra rodada")
            if self.candidate_state.city_state_hash != self.city_state_hash:
                raise ValueError("city_state_hash não corresponde ao candidato")
        if self.domain_transition == "not_run" and self.delta.domains:
            raise ValueError("domain_transition=not_run não pode publicar deltas de domínio")
        return self
