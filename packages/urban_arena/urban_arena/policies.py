"""Policy boundary and deterministic reference policy for Aurora proposals."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Literal, Protocol, runtime_checkable

from pydantic import Field, JsonValue, StrictInt, ValidationError, field_serializer, field_validator, model_validator

from .actions import (
    ActionProposal,
    ArbitrationContext,
    ArbitrationDecision,
    ProposedAction,
    SignalPhaseProposal,
    arbitrate_proposal,
)
from .budget import BudgetEnvelope
from .models import StrictModel
from .observations import Observation as FrozenObservation


class PolicyCategory(StrEnum):
    """Kinds of policy competitors supported by the domain contract."""

    BASELINE_NO_ACTION = "baseline_no_action"
    DETERMINISTIC_RULE = "deterministic_rule"
    SEARCH_OPTIMIZATION = "search_optimization"
    LEARNED = "learned"


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _thaw_json(value: object) -> JsonValue:
    """Copy recursively frozen observation data into standard JSON containers."""
    if isinstance(value, Mapping):
        return {str(key): _thaw_json(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_thaw_json(item) for item in value]
    return value  # type: ignore[return-value]  # Observation already enforces JSON primitives.


def _freeze_json(value: JsonValue) -> JsonValue:
    """Recursively freeze a JSON value held by a Pydantic contract."""
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze_json(item) for key, item in value.items()})  # type: ignore[return-value]
    if isinstance(value, list):
        return tuple(_freeze_json(item) for item in value)  # type: ignore[return-value]
    return value


class PolicyVersion(StrictModel):
    """Serializable, content-addressed identity for a policy artifact/config."""

    schema_version: Literal["1.0"] = "1.0"
    policy_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    category: PolicyCategory
    artifact_sha256: str
    configuration: Mapping[str, JsonValue] = Field(default_factory=dict)
    policy_sha256: str

    @field_validator("configuration")
    @classmethod
    def freeze_configuration(cls, value: Mapping[str, JsonValue]) -> Mapping[str, JsonValue]:
        return MappingProxyType({key: _freeze_json(item) for key, item in value.items()})

    @field_serializer("configuration")
    def serialize_configuration(self, value: Mapping[str, JsonValue]) -> JsonValue:
        return _thaw_json(value)

    @model_validator(mode="after")
    def validate_policy_hash(self) -> PolicyVersion:
        if not self.verify_hash():
            raise ValueError("policy_sha256 não corresponde à versão/configuração")
        return self

    @field_validator("artifact_sha256", "policy_sha256")
    @classmethod
    def validate_sha256(cls, value: str) -> str:
        if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
            raise ValueError("hash deve ser SHA-256 hexadecimal em minúsculas")
        return value

    @classmethod
    def build(
        cls,
        *,
        policy_id: str,
        version: str,
        category: PolicyCategory,
        artifact_sha256: str,
        configuration: dict[str, JsonValue] | None = None,
    ) -> PolicyVersion:
        config = configuration or {}
        identity = {
            "schema_version": "1.0",
            "policy_id": policy_id,
            "version": version,
            "category": category.value,
            "artifact_sha256": artifact_sha256,
            "configuration": config,
        }
        return cls(**identity, policy_sha256=_sha256(_canonical_json(identity)))

    def verify_hash(self) -> bool:
        identity = self.model_dump(mode="json", exclude={"policy_sha256"})
        return self.policy_sha256 == _sha256(_canonical_json(identity))


class ObservationContract(StrictModel):
    """Serializable view of the existing recursively immutable observation."""

    schema_version: Literal["1.0"] = "1.0"
    instance_id: str = Field(min_length=1)
    round_index: StrictInt = Field(ge=1)
    city_state_hash: str = Field(min_length=1)
    state_view: Mapping[str, JsonValue]
    available_actions: tuple[JsonValue, ...]
    budget_view: Mapping[str, JsonValue]
    indicator_values: Mapping[str, JsonValue]

    @field_validator("state_view", "budget_view", "indicator_values")
    @classmethod
    def freeze_mapping(cls, value: Mapping[str, JsonValue]) -> Mapping[str, JsonValue]:
        return MappingProxyType({key: _freeze_json(item) for key, item in value.items()})

    @field_validator("available_actions")
    @classmethod
    def freeze_actions(cls, value: tuple[JsonValue, ...]) -> tuple[JsonValue, ...]:
        return tuple(_freeze_json(item) for item in value)

    @field_serializer("state_view", "available_actions", "budget_view", "indicator_values")
    def serialize_frozen_json(self, value: object) -> JsonValue:
        return _thaw_json(value)

    @classmethod
    def from_observation(cls, observation: FrozenObservation) -> ObservationContract:
        # model_validate copies nested immutable mappings into JSON-shaped Pydantic fields.
        return cls.model_validate({
            "instance_id": observation.instance_id,
            "round_index": observation.round_index,
            "city_state_hash": observation.city_state_hash,
            "state_view": _thaw_json(observation.state_view),
            "available_actions": _thaw_json(observation.available_actions),
            "budget_view": _thaw_json(observation.budget_view),
            "indicator_values": _thaw_json(observation.indicator_values),
        })


class ValidationIssue(StrictModel):
    path: str
    code: str
    message: str


class PolicyDecisionResult(StrictModel):
    """Serializable validation result and, when valid, the stateless arbiter decision."""

    schema_version: Literal["1.0"] = "1.0"
    valid: bool
    code: str
    issues: tuple[ValidationIssue, ...] = ()
    decision: ArbitrationDecision | None = None


def validate_and_decide(
    payload: object,
    context: ArbitrationContext,
    *,
    budget_envelope: BudgetEnvelope | None = None,
) -> PolicyDecisionResult:
    """Reject malformed action payloads explicitly, then use the existing arbiter."""
    try:
        proposal = ActionProposal.model_validate(payload)
    except ValidationError as exc:
        issues = tuple(
            ValidationIssue(
                path=".".join(str(part) for part in error["loc"]),
                code=str(error["type"]),
                message=str(error["msg"]),
            )
            for error in exc.errors()
        )
        return PolicyDecisionResult(valid=False, code="malformed_action", issues=issues)
    return PolicyDecisionResult(
        valid=True,
        code="validated",
        decision=arbitrate_proposal(proposal, context, envelope=budget_envelope),
    )


@runtime_checkable
class AgentPolicy(Protocol):
    """A policy converts one frozen observation into a proposal."""

    agent_id: str
    policy_id: str
    policy_version: str

    def propose(self, observation: FrozenObservation) -> ActionProposal:
        """Return exactly one proposal for the supplied observation."""


@dataclass(frozen=True, slots=True)
class DeterministicReferencePolicy:
    """Stable baseline that makes no discretionary intervention."""

    agent_id: str = "reference-agent"
    policy_id: str = "deterministic-reference"
    policy_version: str = "1"

    def propose(self, observation: FrozenObservation) -> ActionProposal:
        experiment_id = str(observation.state_view["experiment_id"])
        payload = {
            "experiment_id": experiment_id,
            "agent_id": self.agent_id,
            "instance_id": observation.instance_id,
            "round_index": observation.round_index,
            "observed_city_state_hash": observation.city_state_hash,
            "policy_id": self.policy_id,
            "policy_version": self.policy_version,
            "actions": [],
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
        proposal_id = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        identity = json.dumps(
            {
                "experiment_id": experiment_id,
                "instance_id": observation.instance_id,
                "round_index": observation.round_index,
                "agent_id": self.agent_id,
                "policy_id": self.policy_id,
                "policy_version": self.policy_version,
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        return ActionProposal(
            experiment_id=experiment_id,
            proposal_id=proposal_id,
            idempotency_key=hashlib.sha256(identity.encode("utf-8")).hexdigest(),
            agent_id=self.agent_id,
            instance_id=observation.instance_id,
            round_index=observation.round_index,
            observed_city_state_hash=observation.city_state_hash,
            actions=(),
        )


@dataclass(frozen=True, slots=True)
class FixedSignalTimingPolicy:
    """Deterministic benchmark policy for explicitly configured signal plans.

    This is a reproducible rule baseline for exercising Arena/SUMO wiring; it
    is not a trained or autonomous AI policy.
    """

    agent_id: str
    policy_id: str
    signal_changes: tuple[tuple[str, tuple[tuple[str, int], ...]], ...]
    policy_version: str = "synthetic-signal-heuristic-v1"

    def propose(self, observation: FrozenObservation) -> ActionProposal:
        experiment_id = str(observation.state_view["experiment_id"])
        actions = tuple(
            ProposedAction(
                action_id=f"{self.policy_id}:r{observation.round_index}:s{index}",
                action_type="signal_timing_change",
                target_id=node_id,
                parameters={
                    "phases": tuple(
                        SignalPhaseProposal(movement=movement, duration_s=seconds)
                        for movement, seconds in phases
                    ),
                },
                rationale="Política heurística de benchmark sintético; não calibrada com tráfego observado.",
            )
            for index, (node_id, phases) in enumerate(self.signal_changes, start=1)
        )
        payload = {
            "experiment_id": experiment_id,
            "agent_id": self.agent_id,
            "instance_id": observation.instance_id,
            "round_index": observation.round_index,
            "observed_city_state_hash": observation.city_state_hash,
            "actions": [action.model_dump(mode="json") for action in actions],
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
        proposal_id = hashlib.sha256(canonical.encode()).hexdigest()
        identity = json.dumps(
            {
                "experiment_id": experiment_id,
                "instance_id": observation.instance_id,
                "round_index": observation.round_index,
                "agent_id": self.agent_id,
                "policy_id": self.policy_id,
                "policy_version": self.policy_version,
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        return ActionProposal(
            experiment_id=experiment_id,
            proposal_id=proposal_id,
            idempotency_key=hashlib.sha256(identity.encode()).hexdigest(),
            agent_id=self.agent_id,
            instance_id=observation.instance_id,
            round_index=observation.round_index,
            observed_city_state_hash=observation.city_state_hash,
            actions=actions,
        )
