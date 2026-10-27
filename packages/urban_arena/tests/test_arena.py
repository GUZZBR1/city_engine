from __future__ import annotations

from dataclasses import dataclass

import pytest

from urban_arena.arena import (
    ActionProposal,
    ArenaRunner,
    ParticipantFailure,
    ProposalConflictError,
    proposal_content_hash,
)
from urban_arena.city import generate_snapshot, load_city_config
from urban_arena.policies import DeterministicReferencePolicy


def _runner() -> tuple[ArenaRunner, object]:
    snapshot = generate_snapshot(load_city_config())
    return ArenaRunner(snapshot, "test-experiment"), snapshot


@dataclass
class CountingPolicy:
    agent_id: str
    calls: int = 0
    policy_id: str = "counting"
    policy_version: str = "1"

    def propose(self, observation):
        self.calls += 1
        return ActionProposal(
            proposal_id=f"{self.agent_id}-{observation.round_index}",
            agent_id=self.agent_id,
            instance_id=observation.instance_id,
            round_index=observation.round_index,
            observed_city_state_hash=observation.city_state_hash,
            actions=(),
            policy_id=self.policy_id,
            policy_version=self.policy_version,
        )


def test_runner_creates_five_isolated_snapshot_copies() -> None:
    runner, snapshot = _runner()
    assert len(runner.instances) == 5
    assert len({item.instance_id for item in runner.instances}) == 5
    assert {item.initial_city_state_hash for item in runner.instances} == {snapshot.hash}

    first, second = runner.instances[:2]
    first_state = runner.state_copy(first.instance_id)
    first_state.layers["districts"].features[0].properties["residents"] = -1
    assert runner.state_copy(second.instance_id).layers["districts"].features[0].properties["residents"] >= 0
    assert snapshot.layers["districts"].features[0].properties["residents"] >= 0


def test_observations_are_frozen_and_share_the_same_snapshot_version() -> None:
    runner, _ = _runner()
    observations = [runner.observation(item.instance_id, 1) for item in runner.instances]

    assert {item.city_state_hash for item in observations} == {runner.instances[0].initial_city_state_hash}
    assert all(item.round_index == 1 for item in observations)
    assert all(item.state_view["population"] == observations[0].state_view["population"] for item in observations)
    with pytest.raises(TypeError):
        observations[0].state_view["population"]["total"] = -1
    with pytest.raises(AttributeError):
        observations[0].state_view["districts"][0].append({})


def test_reference_policy_is_deterministic_and_empty_proposal_means_no_action() -> None:
    runner, _ = _runner()
    observation = runner.observation(runner.instances[0].instance_id, 1)
    policy = DeterministicReferencePolicy()
    first = policy.propose(observation)
    second = policy.propose(observation)

    assert first == second
    assert first.actions == ()
    assert len(first.proposal_id) == 64
    assert proposal_content_hash(first) == proposal_content_hash(second)


def test_identical_retry_replays_saved_proposals_without_reinvoking_policies() -> None:
    runner, _ = _runner()
    policies = [CountingPolicy(agent_id=f"agent-{index}") for index in range(5)]
    first = runner.run_round(1, policies)
    retry = runner.run_round(1, policies)

    assert first == retry
    assert [policy.calls for policy in policies] == [1] * 5
    assert len(runner.recorded_proposals) == 5


def test_same_proposal_identity_with_changed_content_is_a_conflict() -> None:
    runner, _ = _runner()
    original = runner.run_round(1, [CountingPolicy(agent_id=f"agent-{index}") for index in range(5)])[0]
    changed = ActionProposal(
        proposal_id=original.proposal_id,
        agent_id=original.agent_id,
        instance_id=original.instance_id,
        round_index=original.round_index,
        observed_city_state_hash=original.observed_city_state_hash,
        actions=({"action": "changed"},),
        policy_id=original.policy_id,
        policy_version=original.policy_version,
    )
    with pytest.raises(ProposalConflictError):
        runner.record_proposal(changed)


def test_policy_failure_is_visible_and_never_becomes_empty_proposal() -> None:
    class FailingPolicy(CountingPolicy):
        def propose(self, observation):
            raise RuntimeError("participant unavailable")

    runner, _ = _runner()
    policies = [CountingPolicy(agent_id=f"agent-{index}") for index in range(5)]
    policies[2] = FailingPolicy(agent_id="agent-2")

    with pytest.raises(ParticipantFailure, match="participant unavailable"):
        runner.run_round(1, policies)
    assert len(runner.recorded_proposals) == 2


def test_default_horizon_rejects_round_eleven_and_non_array_actions() -> None:
    runner, _ = _runner()
    instance_id = runner.instances[0].instance_id
    with pytest.raises(ValueError, match="entre 1 e 10"):
        runner.observation(instance_id, 11)
    with pytest.raises(ValueError, match="entre 1 e 10"):
        runner.run_round(11, [CountingPolicy(agent_id=f"agent-{index}") for index in range(5)])
    with pytest.raises(ValueError, match="só coleta a rodada 1"):
        runner.observation(instance_id, 2)
    with pytest.raises(ValueError, match="só coleta a rodada 1"):
        runner.run_round(2, [CountingPolicy(agent_id=f"agent-{index}") for index in range(5)])

    with pytest.raises(TypeError, match="actions deve ser uma lista ou tupla"):
        ActionProposal(
            proposal_id="invalid",
            agent_id="agent",
            instance_id=instance_id,
            round_index=1,
            observed_city_state_hash=runner.instances[0].initial_city_state_hash,
            actions=None,
            policy_id="test",
            policy_version="1",
        )


def test_arena_has_no_universal_ranking_and_exposes_transition_dependency() -> None:
    runner, _ = _runner()
    assert "TransitionEngine" in runner.transition_dependency
    assert not hasattr(runner, "ranking")
    assert not hasattr(runner, "winner")
