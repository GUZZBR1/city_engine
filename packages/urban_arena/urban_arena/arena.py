"""Proposal collection for five isolated Aurora benchmark instances.

This module intentionally stops before action arbitration or annual transitions:
those shared domain contracts are not present in this package yet.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, TypeAlias

from .models import CitySnapshot

if TYPE_CHECKING:
    from .policies import AgentPolicy


FrozenJSON: TypeAlias = type(None) | bool | int | float | str | tuple["FrozenJSON", ...] | Mapping[str, "FrozenJSON"]
INSTANCE_COUNT = 5
DEFAULT_HORIZON_ROUNDS = 10


def _freeze(value: Any) -> FrozenJSON:
    """Copy JSON data into recursively immutable containers."""
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("observações e propostas devem conter apenas números JSON finitos")
        return value
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise TypeError("chaves de observação devem ser strings")
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    raise TypeError(f"valor não JSON não permitido na observação/proposta: {type(value).__name__}")


def _thaw(value: FrozenJSON) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


@dataclass(frozen=True, slots=True)
class Observation:
    """Immutable policy input for one instance and round."""

    instance_id: str
    round_index: int
    city_state_hash: str
    state_view: Mapping[str, FrozenJSON]
    available_actions: tuple[FrozenJSON, ...] = ()
    budget_view: FrozenJSON = None
    indicator_values: Mapping[str, FrozenJSON] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.round_index, int) or isinstance(self.round_index, bool):
            raise TypeError("round_index deve ser inteiro")
        if not 1 <= self.round_index <= DEFAULT_HORIZON_ROUNDS:
            raise ValueError(f"round_index deve estar entre 1 e {DEFAULT_HORIZON_ROUNDS}")
        object.__setattr__(self, "state_view", _freeze(self.state_view))
        object.__setattr__(self, "available_actions", _freeze(self.available_actions))
        object.__setattr__(self, "budget_view", _freeze(self.budget_view))
        object.__setattr__(self, "indicator_values", _freeze(self.indicator_values))


@dataclass(frozen=True, slots=True)
class ActionProposal:
    """Agent-authored proposal; action items stay opaque to the arena."""

    proposal_id: str
    agent_id: str
    instance_id: str
    round_index: int
    observed_city_state_hash: str
    actions: tuple[FrozenJSON, ...]
    policy_id: str
    policy_version: str

    def __post_init__(self) -> None:
        required = (self.proposal_id, self.agent_id, self.instance_id, self.observed_city_state_hash,
                    self.policy_id, self.policy_version)
        if any(not item for item in required):
            raise ValueError("identidades e hashes da proposta devem ser não vazios")
        if not isinstance(self.round_index, int) or isinstance(self.round_index, bool):
            raise TypeError("round_index deve ser inteiro")
        if not 1 <= self.round_index <= DEFAULT_HORIZON_ROUNDS:
            raise ValueError(f"round_index deve estar entre 1 e {DEFAULT_HORIZON_ROUNDS}")
        if not isinstance(self.actions, (list, tuple)):
            raise TypeError("actions deve ser uma lista ou tupla")
        object.__setattr__(self, "actions", _freeze(self.actions))


@dataclass(frozen=True, slots=True)
class ArenaInstance:
    """Public identity only; mutable snapshot copies remain private to the runner."""

    experiment_id: str
    instance_id: str
    initial_city_state_hash: str


class ProposalConflictError(ValueError):
    """The same proposal identity was reused with different proposal content."""


class ParticipantFailure(RuntimeError):
    """A policy failed; the round is incomplete and must be paused/retried."""

    def __init__(self, instance_id: str, round_index: int, cause: Exception) -> None:
        super().__init__(f"política falhou para {instance_id} na rodada {round_index}: {cause}")
        self.instance_id = instance_id
        self.round_index = round_index
        self.__cause__ = cause


class ArenaRunner:
    """Create five isolated instances and collect/replay their proposals.

    Annual transition and action evaluation are explicit downstream integration
    dependencies; this runner does not mutate an evolving CityState.
    """

    transition_dependency = "CityState/ObservationBuilder, ActionArbiter e AnnualTransitionEngine"

    def __init__(self, snapshot: CitySnapshot, experiment_id: str) -> None:
        if not experiment_id:
            raise ValueError("experiment_id deve ser não vazio")
        self.experiment_id = experiment_id
        self._instances: tuple[ArenaInstance, ...] = tuple(
            ArenaInstance(
                experiment_id=experiment_id,
                instance_id=f"{experiment_id}:instance:{index:02d}",
                initial_city_state_hash=snapshot.hash,
            )
            for index in range(1, INSTANCE_COUNT + 1)
        )
        self._states = {
            instance.instance_id: snapshot.model_copy(deep=True)
            for instance in self._instances
        }
        self._recorded: dict[tuple[str, str, int, str, str, str], ActionProposal] = {}

    @property
    def instances(self) -> tuple[ArenaInstance, ...]:
        return self._instances

    def state_copy(self, instance_id: str) -> CitySnapshot:
        """Return a defensive deep copy for inspection, never the runner's state."""
        try:
            return self._states[instance_id].model_copy(deep=True)
        except KeyError as exc:
            raise KeyError(f"instância desconhecida: {instance_id}") from exc

    @property
    def recorded_proposals(self) -> tuple[ActionProposal, ...]:
        return tuple(self._recorded[key] for key in sorted(self._recorded))

    def observation(self, instance_id: str, round_index: int) -> Observation:
        """Build a frozen snapshot observation; no annual candidate is implied."""
        self._validate_round(round_index)
        try:
            state = self._states[instance_id]
        except KeyError as exc:
            raise KeyError(f"instância desconhecida: {instance_id}") from exc
        state_view = _freeze(state.model_dump(mode="json"))
        assert isinstance(state_view, Mapping)
        budget_view = state_view.get("finance", {})
        return Observation(
            instance_id=instance_id,
            round_index=round_index,
            city_state_hash=state.hash,
            state_view=state_view,
            available_actions=(),
            budget_view=budget_view,
            indicator_values={},
        )

    def record_proposal(self, proposal: ActionProposal) -> ActionProposal:
        """Persist one original proposal in the process-local idempotency journal."""
        self._validate_round(proposal.round_index)
        instance = next((item for item in self._instances if item.instance_id == proposal.instance_id), None)
        if instance is None:
            raise ValueError(f"proposta referencia instância desconhecida: {proposal.instance_id}")
        if proposal.observed_city_state_hash != instance.initial_city_state_hash:
            raise ValueError("proposta referencia hash de estado diferente da observação da instância")
        key = (self.experiment_id, proposal.instance_id, proposal.round_index,
               proposal.agent_id, proposal.policy_id, proposal.policy_version)
        current = self._recorded.get(key)
        if current is not None:
            if current != proposal:
                raise ProposalConflictError(f"identidade de proposta reutilizada com conteúdo diferente: {key}")
            return current
        if any(
            recorded_key[:3] == key[:3]
            for recorded_key in self._recorded
        ):
            raise ProposalConflictError(
                "já existe uma proposta gravada para esta instância/rodada"
            )
        self._recorded[key] = proposal
        return proposal

    def collect_proposals(
        self, round_index: int, policies: Sequence[AgentPolicy]
    ) -> tuple[ActionProposal, ...]:
        """Collect one proposal per instance; saved retries do not reinvoke policies."""
        self._validate_round(round_index)
        if len(policies) != INSTANCE_COUNT:
            raise ValueError(f"são necessárias exatamente {INSTANCE_COUNT} políticas, uma por instância")
        proposals: list[ActionProposal] = []
        for instance, policy in zip(self._instances, policies, strict=True):
            key = (self.experiment_id, instance.instance_id, round_index,
                   policy.agent_id, policy.policy_id, policy.policy_version)
            recorded = self._recorded.get(key)
            if recorded is not None:
                proposals.append(recorded)
                continue
            observation = self.observation(instance.instance_id, round_index)
            try:
                proposal = policy.propose(observation)
            except Exception as exc:
                raise ParticipantFailure(instance.instance_id, round_index, exc) from exc
            if not isinstance(proposal, ActionProposal):
                raise ParticipantFailure(
                    instance.instance_id, round_index,
                    TypeError("AgentPolicy.propose deve retornar ActionProposal"),
                )
            if (proposal.agent_id, proposal.policy_id, proposal.policy_version) != (
                policy.agent_id, policy.policy_id, policy.policy_version
            ):
                raise ParticipantFailure(
                    instance.instance_id, round_index,
                    ValueError("identidade da proposta não corresponde à política"),
                )
            if proposal.instance_id != instance.instance_id or proposal.round_index != round_index:
                raise ParticipantFailure(
                    instance.instance_id, round_index,
                    ValueError("proposta não corresponde à instância/rodada observada"),
                )
            if proposal.observed_city_state_hash != observation.city_state_hash:
                raise ParticipantFailure(
                    instance.instance_id, round_index,
                    ValueError("proposta referencia hash diferente do observado"),
                )
            proposals.append(self.record_proposal(proposal))
        return tuple(proposals)

    @staticmethod
    def _validate_round(round_index: int) -> None:
        if not isinstance(round_index, int) or isinstance(round_index, bool):
            raise TypeError("round_index deve ser inteiro")
        if not 1 <= round_index <= DEFAULT_HORIZON_ROUNDS:
            raise ValueError(f"round_index deve estar entre 1 e {DEFAULT_HORIZON_ROUNDS}")
        if round_index != 1:
            raise ValueError(
                "ArenaRunner só coleta a rodada 1 até integrar CityState/ObservationBuilder "
                "e AnnualTransitionEngine"
            )

    def run_round(self, round_index: int, policies: Sequence[AgentPolicy]) -> tuple[ActionProposal, ...]:
        """Collect proposals only; evaluation/transitions are not yet integrated."""
        return self.collect_proposals(round_index, policies)


def proposal_content_hash(proposal: ActionProposal) -> str:
    """Canonical content digest useful to persistence adapters and diagnostics."""
    payload = {
        "proposal_id": proposal.proposal_id,
        "agent_id": proposal.agent_id,
        "instance_id": proposal.instance_id,
        "round_index": proposal.round_index,
        "observed_city_state_hash": proposal.observed_city_state_hash,
        "actions": _thaw(proposal.actions),
        "policy_id": proposal.policy_id,
        "policy_version": proposal.policy_version,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
