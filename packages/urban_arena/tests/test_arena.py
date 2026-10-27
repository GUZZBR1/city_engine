from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace

import pytest

from urban_arena.actions import ActionProposal, HousingParameters, ProposedAction
from urban_arena.arena import ArenaRunner, ParticipantFailure, ProposalConflictError
from urban_arena.city import generate_snapshot, load_city_config
from urban_arena.policies import DeterministicReferencePolicy
from urban_arena.repository import ProposalRecord
from urban_arena.state import CityState, StateTransitionResult


def _snapshot():
    return generate_snapshot(load_city_config())


def _policies():
    return [DeterministicReferencePolicy(agent_id=f"agent-{index}") for index in range(5)]


@dataclass
class CountingPolicy:
    agent_id: str
    action: bool = False
    calls: int = 0
    policy_id: str = "counting"
    policy_version: str = "1"

    def propose(self, observation) -> ActionProposal:
        self.calls += 1
        identity = {
            "experiment_id": observation.state_view["experiment_id"],
            "instance_id": observation.instance_id,
            "round_index": observation.round_index,
            "agent_id": self.agent_id,
            "policy_id": self.policy_id,
            "policy_version": self.policy_version,
        }
        action_list = (
            [
                ProposedAction(
                    action_id="housing-1",
                    action_type="housing_add_units",
                    target_id="centro",
                    parameters=HousingParameters(units=10),
                )
            ]
            if self.action
            else []
        )
        content = {**identity, "actions": [item.model_dump(mode="json") for item in action_list]}
        canonical = json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        proposal_id = hashlib.sha256(canonical.encode()).hexdigest()
        idempotency_key = hashlib.sha256(
            json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return ActionProposal(
            experiment_id=str(identity["experiment_id"]),
            proposal_id=proposal_id,
            idempotency_key=idempotency_key,
            agent_id=self.agent_id,
            instance_id=observation.instance_id,
            round_index=observation.round_index,
            observed_city_state_hash=observation.city_state_hash,
            actions=tuple(action_list),
        )


def test_runner_owns_five_isolated_evolutive_city_states() -> None:
    snapshot = _snapshot()
    runner = ArenaRunner(snapshot, "test-experiment")
    states = [runner.state_copy(instance.instance_id) for instance in runner.instances]

    assert len(states) == 5
    assert all(isinstance(state, CityState) for state in states)
    assert {state.round_index for state in states} == {0}
    assert len({state.city_state_hash for state in states}) == 1
    assert {state.snapshot_hash for state in states} == {snapshot.hash}
    states[0].population.residents_by_district["centro"] = -1
    assert runner.state_copy(runner.instances[1].instance_id).population.residents_by_district["centro"] >= 0
    assert snapshot.population.total == 67_250


def test_observation_is_deeply_frozen_and_uses_only_enabled_actions() -> None:
    runner = ArenaRunner(_snapshot(), "test-experiment")
    observation = runner.observation(runner.instances[0].instance_id, 1)

    assert observation.round_index == 1
    assert observation.city_state_hash == runner.instances[0].initial_city_state_hash
    assert observation.available_actions == ()
    assert "budget" not in observation.state_view
    assert observation.budget_view == {"discretionary_limit_cs": 30, "currency": "CS"}
    with pytest.raises(TypeError):
        observation.state_view["population"]["total_residents"] = -1
    with pytest.raises(TypeError):
        observation.budget_view["credits_per_round"] = 0


def test_reference_policy_produces_shared_no_action_contract() -> None:
    runner = ArenaRunner(_snapshot(), "test-experiment")
    observation = runner.observation(runner.instances[0].instance_id, 1)
    policy = DeterministicReferencePolicy(agent_id="reference-1")

    first = policy.propose(observation)
    second = policy.propose(observation)
    assert isinstance(first, ActionProposal)
    assert first == second
    assert first.actions == ()
    assert first.idempotency_key == second.idempotency_key


def test_no_action_runs_ten_annual_rounds_for_five_instances_deterministically() -> None:
    snapshot = _snapshot()
    first = ArenaRunner(snapshot, "test-experiment")
    second = ArenaRunner(snapshot, "test-experiment")

    for round_index in range(1, 11):
        first_records = first.run_round(round_index, _policies())
        second_records = second.run_round(round_index, _policies())
        assert len(first_records) == 5
        assert all(record.decision.decision == "no_action" for record in first_records)
        assert [record.round_record_hash for record in first_records] == [
            record.round_record_hash for record in second_records
        ]
        for record in first_records:
            assert record.state_transition.domain_transition == "applied"
            assert record.state_transition.candidate_state.round_index == round_index
            assert [item.domain for item in record.state_transition.delta.domains] == [
                "population",
                "housing",
                "employment",
                "services",
                "environment",
            ]
            assert record.state_transition.candidate_state.city_state_hash == record.state_transition.city_state_hash
            assert len(record.indicator_results) == 25

    assert {state.round_index for state in first.repository.load_states()} == {10}
    with pytest.raises(ValueError, match="horizonte"):
        first.run_round(11, _policies())


def test_round_retry_replays_commit_without_reinvoking_policy() -> None:
    runner = ArenaRunner(_snapshot(), "test-experiment")
    policies = [CountingPolicy(agent_id=f"agent-{index}") for index in range(5)]
    first = runner.run_round(1, policies)
    retry = runner.run_round(1, policies)

    assert [record.round_record_hash for record in first] == [record.round_record_hash for record in retry]
    assert [policy.calls for policy in policies] == [1] * 5


def test_disabled_action_is_rejected_atomically_but_no_action_year_transitions() -> None:
    runner = ArenaRunner(_snapshot(), "test-experiment")
    before = [runner.state_copy(instance.instance_id).city_state_hash for instance in runner.instances]
    records = runner.run_round(1, [CountingPolicy(agent_id=f"agent-{index}", action=True) for index in range(5)])

    assert all(record.decision.decision == "rejected" for record in records)
    assert all(record.decision.code == "atomic_validation_failed" for record in records)
    assert all(record.state_transition.domain_transition == "applied" for record in records)
    assert [runner.state_copy(instance.instance_id).city_state_hash for instance in runner.instances] != before


def test_failed_transition_rolls_back_all_states_and_retries_saved_proposals(monkeypatch) -> None:
    runner = ArenaRunner(_snapshot(), "test-experiment")
    policies = [CountingPolicy(agent_id=f"agent-{index}") for index in range(5)]
    before = [runner.state_copy(instance.instance_id).city_state_hash for instance in runner.instances]

    def fail(*args, **kwargs):
        raise RuntimeError("injected transition fault")

    monkeypatch.setattr("urban_arena.round_engine.transition_housing", fail)
    with pytest.raises(RuntimeError, match="injected transition fault"):
        runner.run_round(1, policies)
    assert [runner.state_copy(instance.instance_id).city_state_hash for instance in runner.instances] == before
    assert len(runner.recorded_proposals) == 5

    monkeypatch.undo()
    results = runner.run_round(1, policies)
    assert len(results) == 5
    assert [policy.calls for policy in policies] == [1] * 5


def test_same_policy_identity_with_changed_proposal_content_conflicts() -> None:
    runner = ArenaRunner(_snapshot(), "test-experiment")
    policies = [CountingPolicy(agent_id=f"agent-{index}") for index in range(5)]
    runner.run_round(1, policies)
    saved = runner.recorded_proposals[0]
    changed = saved.proposal.model_copy(update={"budget_request": 1})

    with pytest.raises(ProposalConflictError):
        runner.repository.record_proposal(
            ProposalRecord(
                proposal=changed,
                policy_id=saved.policy_id,
                policy_version=saved.policy_version,
            )
        )


def test_repository_rejects_stale_parent_for_complete_round_commit() -> None:
    runner = ArenaRunner(_snapshot(), "test-experiment")
    committed = runner.run_round(1, _policies())
    stale_parent_hash = "f" * 64
    stale_records = []
    for record in committed:
        transition_data = record.state_transition.model_dump(mode="python")
        transition_data["parent_city_state_hash"] = stale_parent_hash
        transition_data["delta"]["parent_city_state_hash"] = stale_parent_hash
        transition_data["candidate_state"]["parent_city_state_hash"] = stale_parent_hash
        stale_transition = StateTransitionResult.model_validate(transition_data)
        stale_records.append(replace(record, state_transition=stale_transition))

    with pytest.raises(ProposalConflictError, match="compare-and-swap falhou"):
        runner.repository.commit_round(stale_records)
    assert {state.round_index for state in runner.repository.load_states()} == {1}


def test_agent_failure_pauses_before_any_instance_commit() -> None:
    class FailingPolicy(CountingPolicy):
        def propose(self, observation):
            raise RuntimeError("participant unavailable")

    runner = ArenaRunner(_snapshot(), "test-experiment")
    policies = [CountingPolicy(agent_id=f"agent-{index}") for index in range(5)]
    policies[3] = FailingPolicy(agent_id="agent-3")
    before = [runner.state_copy(instance.instance_id).city_state_hash for instance in runner.instances]

    with pytest.raises(ParticipantFailure, match="participant unavailable"):
        runner.run_round(1, policies)
    assert [runner.state_copy(instance.instance_id).city_state_hash for instance in runner.instances] == before
    assert len(runner.repository.recorded_proposals) == 3


def test_round_engine_produces_no_universal_ranking_or_winner() -> None:
    runner = ArenaRunner(_snapshot(), "test-experiment")
    records = runner.run_round(1, _policies())

    assert not hasattr(runner, "ranking")
    assert not hasattr(runner, "winner")
    assert not any(hasattr(record, "score") for record in records)
