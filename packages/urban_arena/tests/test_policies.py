from __future__ import annotations

import json

from pydantic import ValidationError
import pytest

from urban_arena.actions import ArbitrationContext
from urban_arena.observations import Observation
from urban_arena.policies import (
    ObservationContract,
    PolicyCategory,
    PolicyVersion,
    validate_and_decide,
)


ARTIFACT_HASH = "a" * 64


def test_policy_version_is_content_addressed_and_categories_are_distinct() -> None:
    rule_policy = PolicyVersion.build(
        policy_id="timing-rule",
        version="1.0.0",
        category=PolicyCategory.DETERMINISTIC_RULE,
        artifact_sha256=ARTIFACT_HASH,
        configuration={"changes": [{"target": "node:01:01", "duration_s": 25}]},
    )
    same_policy = PolicyVersion.build(
        policy_id="timing-rule",
        version="1.0.0",
        category=PolicyCategory.DETERMINISTIC_RULE,
        artifact_sha256=ARTIFACT_HASH,
        configuration={"changes": [{"duration_s": 25, "target": "node:01:01"}]},
    )
    baseline = PolicyVersion.build(
        policy_id="baseline",
        version="1",
        category=PolicyCategory.BASELINE_NO_ACTION,
        artifact_sha256=ARTIFACT_HASH,
    )

    assert rule_policy.policy_sha256 == same_policy.policy_sha256
    assert rule_policy.verify_hash()
    assert rule_policy.policy_sha256 != baseline.policy_sha256
    assert {
        PolicyCategory.BASELINE_NO_ACTION,
        PolicyCategory.DETERMINISTIC_RULE,
        PolicyCategory.SEARCH_OPTIMIZATION,
        PolicyCategory.LEARNED,
    } == set(PolicyCategory)
    assert json.loads(rule_policy.model_dump_json())["schema_version"] == "1.0"


def test_policy_version_rejects_malformed_hash() -> None:
    with pytest.raises(ValidationError, match="SHA-256"):
        PolicyVersion.build(
            policy_id="bad",
            version="1",
            category=PolicyCategory.BASELINE_NO_ACTION,
            artifact_sha256="not-a-hash",
        )


def test_policy_version_rejects_a_hash_that_does_not_match_its_configuration() -> None:
    policy = PolicyVersion.build(
        policy_id="baseline",
        version="1",
        category=PolicyCategory.BASELINE_NO_ACTION,
        artifact_sha256=ARTIFACT_HASH,
    )
    payload = policy.model_dump(mode="json")
    payload["configuration"] = {"unexpected": True}

    with pytest.raises(ValidationError, match="não corresponde"):
        PolicyVersion.model_validate(payload)


def test_observation_contract_serializes_immutable_observation() -> None:
    observation = Observation(
        instance_id="instance-1",
        round_index=1,
        city_state_hash="state-hash",
        state_view={"experiment_id": "experiment-1", "nested": {"value": 3}},
        available_actions=(),
        budget_view={"discretionary_limit_cs": 10},
        indicator_values={},
    )

    with pytest.raises(TypeError):
        observation.state_view["new"] = True  # type: ignore[index]
    with pytest.raises(TypeError):
        observation.state_view["nested"]["value"] = 4  # type: ignore[index]

    contract = ObservationContract.from_observation(observation)
    with pytest.raises(TypeError):
        contract.state_view["new"] = True  # type: ignore[index]
    with pytest.raises(TypeError):
        contract.state_view["nested"]["value"] = 4  # type: ignore[index]
    encoded = json.loads(contract.model_dump_json())
    assert encoded["schema_version"] == "1.0"
    assert encoded["state_view"]["nested"]["value"] == 3


def test_malformed_action_is_explicitly_rejected_and_cost_is_not_trusted() -> None:
    context = ArbitrationContext(
        experiment_id="experiment-1",
        agent_id="agent-1",
        instance_id="instance-1",
        round_index=1,
        observed_city_state_hash="state-hash",
    )
    malformed = validate_and_decide(
        {
            "experiment_id": "experiment-1",
            "proposal_id": "proposal-1",
            "idempotency_key": "retry-1",
            "agent_id": "agent-1",
            "instance_id": "instance-1",
            "round_index": 1,
            "observed_city_state_hash": "state-hash",
            "actions": [{"action_id": "bad", "action_type": "unknown", "target_id": "x", "parameters": {}}],
        },
        context,
    )
    assert not malformed.valid
    assert malformed.code == "malformed_action"
    assert malformed.issues
    assert malformed.model_dump(mode="json")["issues"]

    no_action_payload = {
        "experiment_id": "experiment-1",
        "proposal_id": "proposal-2",
        "idempotency_key": "retry-2",
        "agent_id": "agent-1",
        "instance_id": "instance-1",
        "round_index": 1,
        "observed_city_state_hash": "state-hash",
        "actions": [],
        "budget_request": 0,
    }
    no_action = validate_and_decide(no_action_payload, context)
    inflated_request = validate_and_decide(
        {**no_action_payload, "budget_request": 500_000},
        context,
    )
    assert no_action.valid
    assert no_action.decision is not None
    assert no_action.decision.decision == "no_action"
    assert inflated_request.decision is not None
    assert inflated_request.decision.budget == no_action.decision.budget
