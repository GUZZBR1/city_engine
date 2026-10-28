"""Closed registry for the deterministic policies used by the API benchmark."""

from __future__ import annotations

import hashlib
import inspect
import json
from dataclasses import dataclass

import urban_arena.actions as action_contracts
import urban_arena.policies as policy_implementations
from urban_arena.policies import (
    AgentPolicy,
    DeterministicReferencePolicy,
    FixedSignalTimingPolicy,
    PolicyCategory,
    PolicyVersion,
)


@dataclass(frozen=True, slots=True)
class PolicyRegistration:
    policy_id: str
    agent_id: str
    version: str
    category: PolicyCategory
    implementation: str
    configuration_json: str


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _signal_configuration(changes: tuple[tuple[str, tuple[tuple[str, int], ...]], ...]) -> str:
    return _canonical({
        "signal_changes": [
            {"node_id": node_id, "phases": [
                {"movement": movement, "duration_seconds": seconds}
                for movement, seconds in phases
            ]}
            for node_id, phases in changes
        ]
    })


_NS_PRIORITY = (("north_south", 40), ("all_red", 3), ("east_west", 20), ("all_red", 3))
_EW_PRIORITY = (("north_south", 30), ("all_red", 3), ("east_west", 30), ("all_red", 3))

_SIGNAL_POLICIES = (
    PolicyRegistration(
        "heuristic-ns-node-0200-v1", "signal-ns-node-0200", "synthetic-signal-heuristic-v1",
        PolicyCategory.DETERMINISTIC_RULE, "fixed_signal_timing", _signal_configuration((("node:02:00", _NS_PRIORITY),)),
    ),
    PolicyRegistration(
        "heuristic-ew-node-0200-v1", "signal-ew-node-0200", "synthetic-signal-heuristic-v1",
        PolicyCategory.DETERMINISTIC_RULE, "fixed_signal_timing", _signal_configuration((("node:02:00", _EW_PRIORITY),)),
    ),
    PolicyRegistration(
        "heuristic-ns-node-0204-v1", "signal-ns-node-0204", "synthetic-signal-heuristic-v1",
        PolicyCategory.DETERMINISTIC_RULE, "fixed_signal_timing", _signal_configuration((("node:02:04", _NS_PRIORITY),)),
    ),
    PolicyRegistration(
        "heuristic-coordinated-two-nodes-v1", "signal-coordinated-two-nodes", "synthetic-signal-heuristic-v1",
        PolicyCategory.DETERMINISTIC_RULE, "fixed_signal_timing",
        _signal_configuration((("node:02:00", _NS_PRIORITY), ("node:02:04", _EW_PRIORITY))),
    ),
)
_BASELINE_POLICIES = tuple(
    PolicyRegistration(
        f"deterministic-reference-{index:02d}", f"reference-agent-{index:02d}", "1",
        PolicyCategory.BASELINE_NO_ACTION, "deterministic_reference", "{}",
    )
    for index in range(1, 6)
)
_SUMO_BASELINE = PolicyRegistration(
    "baseline-no-action-v1", "baseline-no-action", "1",
    PolicyCategory.BASELINE_NO_ACTION, "deterministic_reference", "{}",
)
_REGISTRATIONS = {item.policy_id: item for item in (*_BASELINE_POLICIES, _SUMO_BASELINE, *_SIGNAL_POLICIES)}
_IMPLEMENTATIONS = {
    "deterministic_reference": DeterministicReferencePolicy,
    "fixed_signal_timing": FixedSignalTimingPolicy,
}


class UnknownPolicyError(ValueError):
    """Raised when a caller asks for a policy absent from the fixed registry."""


class InvalidPolicyConfigurationError(ValueError):
    """Raised when a requested policy config differs from its registered config."""


def _artifact_hash(implementation: str) -> str:
    source_bundle = {
        "implementation": implementation,
        "policy_module": inspect.getsource(policy_implementations),
        "action_contracts": inspect.getsource(action_contracts),
    }
    return hashlib.sha256(_canonical(source_bundle).encode("utf-8")).hexdigest()


def policy_version(policy_id: str) -> PolicyVersion:
    registration = _REGISTRATIONS.get(policy_id)
    if registration is None:
        raise UnknownPolicyError(f"política desconhecida: {policy_id}")
    return PolicyVersion.build(
        policy_id=registration.policy_id,
        version=registration.version,
        category=registration.category,
        artifact_sha256=_artifact_hash(registration.implementation),
        configuration=json.loads(registration.configuration_json),
    )


def instantiate_policy(policy_id: str, *, configuration: object | None = None) -> AgentPolicy:
    """Instantiate one registered policy; callers cannot supply behavior/config."""
    registration = _REGISTRATIONS.get(policy_id)
    if registration is None:
        raise UnknownPolicyError(f"política desconhecida: {policy_id}")
    if configuration is not None:
        try:
            matches_registered_config = _canonical(configuration) == registration.configuration_json
        except (TypeError, ValueError):
            matches_registered_config = False
        if not matches_registered_config:
            raise InvalidPolicyConfigurationError(f"configuração inválida para política: {policy_id}")

    version = policy_version(policy_id)
    if not version.verify_hash():
        raise InvalidPolicyConfigurationError(f"hash inválido no registro de política: {policy_id}")
    if registration.implementation == "deterministic_reference":
        return DeterministicReferencePolicy(
            agent_id=registration.agent_id,
            policy_id=registration.policy_id,
            policy_version=registration.version,
        )

    # Configuration is read from the immutable registry definition, never from a request.
    config = json.loads(registration.configuration_json)["signal_changes"]
    if not isinstance(config, list):
        raise InvalidPolicyConfigurationError(f"configuração inválida no registro de política: {policy_id}")
    changes: list[tuple[str, tuple[tuple[str, int], ...]]] = []
    try:
        for item in config:
            if not isinstance(item, dict):
                raise TypeError
            phases = item["phases"]
            if not isinstance(phases, list):
                raise TypeError
            changes.append((
                str(item["node_id"]),
                tuple((str(phase["movement"]), int(phase["duration_seconds"])) for phase in phases),
            ))
        return FixedSignalTimingPolicy(
            agent_id=registration.agent_id,
            policy_id=registration.policy_id,
            signal_changes=tuple(changes),
            policy_version=registration.version,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise InvalidPolicyConfigurationError(f"configuração inválida no registro de política: {policy_id}") from exc


def benchmark_policy_ids(*, sumo_available: bool) -> tuple[str, ...]:
    if sumo_available:
        return (_SUMO_BASELINE.policy_id, *(item.policy_id for item in _SIGNAL_POLICIES))
    return tuple(item.policy_id for item in _BASELINE_POLICIES)


def build_benchmark_policies(*, sumo_available: bool) -> tuple[AgentPolicy, ...]:
    return tuple(instantiate_policy(policy_id) for policy_id in benchmark_policy_ids(sumo_available=sumo_available))


def registered_policy_hash(policy_id: str) -> str:
    """Return the verified content identity supplied by the registry."""
    return policy_version(policy_id).policy_sha256
