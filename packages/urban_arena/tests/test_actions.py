import pytest
from pydantic import ValidationError
from urban_arena.actions import (
    ActionCatalog,
    ActionDefinition,
    ActionProposal,
    ArbitrationContext,
    DEFAULT_ACTION_CATALOG,
    ProposedAction,
    SignalTarget,
    arbitrate_proposal,
)


def signal_action(action_id: str = "signal-1", node_id: str = "node:01:01") -> ProposedAction:
    return ProposedAction(
        action_id=action_id,
        action_type="signal_timing_change",
        target_id=node_id,
        parameters={
            "phases": [
                {"movement": "north_south", "duration_s": 30},
                {"movement": "all_red", "duration_s": 2},
                {"movement": "east_west", "duration_s": 25},
                {"movement": "all_red", "duration_s": 2},
            ]
        },
    )


def proposal(*actions: ProposedAction, budget_request: int | None = None) -> ActionProposal:
    return ActionProposal(
        experiment_id="experiment-1",
        proposal_id="proposal-1",
        idempotency_key="proposal-1",
        agent_id="policy-1",
        instance_id="instance-1",
        round_index=1,
        observed_city_state_hash="parent-hash",
        actions=actions,
        budget_request=budget_request,
    )


def context(*targets: SignalTarget, **overrides: object) -> ArbitrationContext:
    fields: dict[str, object] = {
        "experiment_id": "experiment-1",
        "agent_id": "policy-1",
        "instance_id": "instance-1",
        "round_index": 1,
        "observed_city_state_hash": "parent-hash",
        "signal_targets": targets,
    }
    fields.update(overrides)
    return ArbitrationContext(**fields)


def enabled_signal_catalog() -> ActionCatalog:
    return ActionCatalog(actions=(
        ActionDefinition(
            action_type="signal_timing_change",
            enabled=True,
            setup_cost_cs=2,
            operation_cost_cs=1,
        ),
        ActionDefinition(
            action_type="housing_add_units",
            enabled=False,
            unavailable_reason="housing_inventory_unavailable",
            setup_cost_cs=8,
        ),
        ActionDefinition(
            action_type="service_capacity_contract",
            enabled=False,
            unavailable_reason="service_inventory_unavailable",
            setup_cost_cs=6,
            operation_cost_cs=2,
        ),
    ))


def existing_signal(node_id: str = "node:01:01") -> SignalTarget:
    return SignalTarget(
        node_id=node_id,
        phases=(
            {"movement": "north_south", "duration_s": 25},
            {"movement": "all_red", "duration_s": 2},
            {"movement": "east_west", "duration_s": 30},
            {"movement": "all_red", "duration_s": 2},
        ),
    )


def test_proposal_contract_is_strict_and_agent_cost_is_only_annotation() -> None:
    with pytest.raises(ValidationError):
        ActionProposal.model_validate({
            **proposal(signal_action()).model_dump(),
            "cost_cs": 0,
        })

    decision = arbitrate_proposal(
        proposal(signal_action(), budget_request=0),
        context(existing_signal()),
    )
    assert not decision.accepted
    assert decision.actions[0].code == "signal_execution_adapter_not_configured"
    assert decision.budget is None

    distinct_idempotency_key = proposal(signal_action()).model_copy(
        update={"idempotency_key": "retry-key-1"}
    )
    assert distinct_idempotency_key.idempotency_key == "retry-key-1"


def test_disabled_housing_and_service_actions_are_not_available() -> None:
    housing = ProposedAction(
        action_id="housing-1",
        action_type="housing_add_units",
        target_id="district:centro",
        parameters={"units": 10},
    )
    service = ProposedAction(
        action_id="service-1",
        action_type="service_capacity_contract",
        target_id="clinic:centro",
        parameters={"service_type": "primary_health", "unit": "consultas/ano", "capacity_units": 10},
    )
    results = [
        arbitrate_proposal(proposal(action), context())
        for action in (housing, service)
    ]

    assert [result.actions[0].code for result in results] == [
        "housing_inventory_unavailable",
        "service_inventory_unavailable",
    ]
    assert all(not result.accepted and result.budget is None for result in results)


def test_empty_proposal_is_no_action_and_budget_request_does_not_change_budget() -> None:
    result = arbitrate_proposal(
        proposal(budget_request=30),
        context(existing_commitments_cs={2: 4}),
    )

    assert result.accepted
    assert result.decision == "no_action"
    assert result.budget is not None
    assert result.budget.rounds[0].round_index == 2
    assert result.budget.rounds[0].already_committed_cs == 4
    assert result.budget.rounds[0].available_cs == 26


def test_signal_phase_validation_rejects_missing_target_and_changed_cycle() -> None:
    missing = arbitrate_proposal(proposal(signal_action()), context(), catalog=enabled_signal_catalog())
    assert not missing.accepted
    assert missing.actions[0].code == "target_unavailable"

    bad_cycle = ProposedAction.model_validate({
        **signal_action().model_dump(),
        "parameters": {
            "phases": [
                {"movement": "north_south", "duration_s": 31},
                {"movement": "all_red", "duration_s": 2},
                {"movement": "east_west", "duration_s": 25},
                {"movement": "all_red", "duration_s": 2},
            ]
        }
    })
    result = arbitrate_proposal(
        proposal(bad_cycle),
        context(existing_signal()),
        catalog=enabled_signal_catalog(),
    )
    assert not result.accepted
    assert result.actions[0].code == "invalid_cycle_duration"


def test_signal_action_cost_is_server_calculated_and_package_is_atomic() -> None:
    result = arbitrate_proposal(
        proposal(signal_action(), budget_request=0),
        context(existing_signal()),
        catalog=enabled_signal_catalog(),
    )

    assert result.accepted
    assert result.budget is not None and result.budget.accepted
    assert result.budget.rounds[0].proposed_cs == 3
    assert [charge.amount_cs for charge in result.actions[0].charges] == [2, 1]

    conflict = arbitrate_proposal(
        proposal(signal_action("signal-1"), signal_action("signal-2")),
        context(existing_signal()),
        catalog=enabled_signal_catalog(),
    )
    assert not conflict.accepted
    assert conflict.code == "atomic_validation_failed"
    assert all(not receipt.accepted for receipt in conflict.actions)
    assert conflict.budget is None


def test_custom_catalog_enables_signal_only_with_valid_target() -> None:
    assert not DEFAULT_ACTION_CATALOG.get("signal_timing_change").enabled
    result = arbitrate_proposal(
        proposal(signal_action()),
        context(),
        catalog=enabled_signal_catalog(),
    )

    assert not result.accepted
    assert result.actions[0].code == "target_unavailable"

    accepted = arbitrate_proposal(
        proposal(signal_action()),
        context(existing_signal()),
        catalog=enabled_signal_catalog(),
    )
    assert accepted.accepted
    assert accepted.actions[0].accepted


def test_proposal_identity_must_match_frozen_observation() -> None:
    result = arbitrate_proposal(
        proposal(signal_action()),
        context(existing_signal(), observed_city_state_hash="other-hash"),
    )

    assert not result.accepted
    assert result.code == "observation_mismatch"

    wrong_agent = ArbitrationContext(
        experiment_id="experiment-1",
        agent_id="another-policy",
        instance_id="instance-1",
        round_index=1,
        observed_city_state_hash="parent-hash",
    )
    wrong_author = arbitrate_proposal(proposal(signal_action()), wrong_agent)
    assert not wrong_author.accepted
    assert wrong_author.code == "observation_mismatch"
