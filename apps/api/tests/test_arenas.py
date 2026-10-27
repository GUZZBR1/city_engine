from __future__ import annotations

import pytest
from app import arena_jobs, main
from app.arena_schemas import ArenaRequest
from fastapi import BackgroundTasks, HTTPException


@pytest.fixture(autouse=True)
def isolated_arena_jobs(monkeypatch):
    # The API store is process-local; each test owns a fresh mapping.
    monkeypatch.setattr(arena_jobs, "_jobs", {})


def _post_arena(horizon_rounds: int = 1):
    background_tasks = BackgroundTasks()
    response = main.start_arena(ArenaRequest(horizon_rounds=horizon_rounds), background_tasks)
    return response, background_tasks


def test_arena_endpoint_queues_then_publishes_complete_real_runner_result():
    post_route = next(
        route for route in main.app.routes
        if getattr(route, "path", None) == "/api/v1/arenas" and "POST" in route.methods
    )
    assert post_route.status_code == 202
    get_route = next(
        route for route in main.app.routes
        if getattr(route, "path", None) == "/api/v1/arenas/{arena_id}" and "GET" in route.methods
    )
    assert 404 in get_route.responses
    openapi = main.app.openapi()
    assert "202" in openapi["paths"]["/api/v1/arenas"]["post"]["responses"]
    assert "404" in openapi["paths"]["/api/v1/arenas/{arena_id}"]["get"]["responses"]
    request_schema = openapi["components"]["schemas"]["ArenaRequest"]["properties"]["horizon_rounds"]
    assert request_schema["minimum"] == 1
    assert request_schema["maximum"] == 10

    created, background_tasks = _post_arena(1)
    queued = created.arena

    assert queued.status == "queued"
    assert queued.completed_rounds == 0
    assert queued.horizon_rounds == 1
    assert len(background_tasks.tasks) == 1
    task = background_tasks.tasks[0]
    assert task.func is arena_jobs.run_arena
    assert task.args == (queued.arena_id,)

    task.func(*task.args, **task.kwargs)
    published = main.arena_status(queued.arena_id).arena
    payload = published.model_dump(mode="json")

    assert published.status == "succeeded"
    assert published.completed_rounds == 1
    assert published.experiment_id
    assert published.snapshot_id
    assert len(published.snapshot_hash) == 64
    assert len(published.manifest_hash) == 64
    assert published.manifest.profile_id == "aurora_synthetic_v1"
    assert published.manifest.horizon_rounds == published.horizon_rounds
    assert published.manifest.manifest_hash == published.manifest_hash
    assert payload["manifest"]["parameters"]["emissions"]["activity_scope"]
    assert len(published.instances) == 5
    assert {item.current_round_index for item in published.instances} == {1}
    assert len({item.agent_id for item in published.instances}) == 5
    assert len({item.policy_id for item in published.instances}) == 5
    assert all(item.current_state.city_state_hash == item.current_city_state_hash for item in published.instances)
    assert all(item.current_state.population.total_residents > 0 for item in published.instances)
    assert len(published.rounds) == 1
    round_payload = payload["rounds"][0]
    assert round_payload["round_index"] == 1
    assert len(round_payload["instances"]) == 5
    for item in round_payload["instances"]:
        assert item["proposal"]["experiment_id"] == published.experiment_id
        assert item["proposal"]["round_index"] == 1
        assert len(item["proposal"]["proposal_record_hash"]) == 64
        assert item["decision"]["proposal_id"] == item["proposal"]["proposal_id"]
        assert item["decision"]["decision"] in {"accepted", "rejected", "no_action"}
        assert item["indicators"]
        assert item["city_state_hash"]
        assert item["manifest_hash"] == published.manifest_hash
        assert len(item["round_record_hash"]) == 64
        assert all("indicator_id" in indicator and "coverage" in indicator for indicator in item["indicators"])


def test_arena_accepts_minimum_and_maximum_horizons_and_uses_five_unique_policies():
    minimum, _ = _post_arena(1)
    maximum, _ = _post_arena(10)

    assert minimum.arena.horizon_rounds == 1
    assert maximum.arena.status == "queued"
    assert maximum.arena.horizon_rounds == 10
    record = arena_jobs._jobs[maximum.arena.arena_id]
    assert len(record.policies) == 5
    assert len({policy.agent_id for policy in record.policies}) == 5
    assert len({policy.policy_id for policy in record.policies}) == 5
    assert all(policy.policy_version for policy in record.policies)
    assert {item.current_round_index for item in maximum.arena.instances} == {0}
    assert len({item.instance_id for item in maximum.arena.instances}) == 5
    arena_jobs.run_arena(maximum.arena.arena_id)
    completed = arena_jobs.get_arena(maximum.arena.arena_id)
    assert completed.status == "succeeded"
    assert completed.completed_rounds == 10
    assert {item.current_round_index for item in completed.instances} == {10}
    assert len(completed.rounds) == 10


@pytest.mark.parametrize("horizon_rounds", [0, 11])
def test_arena_rejects_horizon_outside_one_through_ten(horizon_rounds):
    with pytest.raises(ValueError):
        ArenaRequest(horizon_rounds=horizon_rounds)


def test_arena_rejects_non_integer_horizon():
    with pytest.raises(ValueError):
        ArenaRequest(horizon_rounds=1.5)


def test_arena_status_returns_404_for_unknown_id():
    with pytest.raises(HTTPException) as exc_info:
        main.arena_status("missing-arena")

    assert exc_info.value.status_code == 404


def test_participant_failure_is_reported_without_publishing_any_round():
    created, _ = _post_arena(1)
    arena_id = created.arena.arena_id
    record = arena_jobs._jobs[arena_id]

    class FailingPolicy:
        agent_id = "failing-agent"
        policy_id = "failing-policy"
        policy_version = "1"

        def propose(self, observation):
            raise RuntimeError("participant failed")

    record.policies = (*record.policies[:4], FailingPolicy())
    arena_jobs.run_arena(arena_id)
    failed = arena_jobs.get_arena(arena_id)

    assert failed.status == "failed"
    assert failed.error.code == "participant_failed"
    assert failed.error.round_index == 1
    assert failed.error.instance_id == record.runner.instances[4].instance_id
    assert failed.rounds == []
    assert failed.completed_rounds == 0
    assert {item.current_round_index for item in failed.instances} == {0}


def test_round_failure_preserves_previous_committed_round_without_partial_publication(monkeypatch):
    created, _ = _post_arena(2)
    arena_id = created.arena.arena_id
    record = arena_jobs._jobs[arena_id]
    real_run_round = record.runner.run_round

    def fail_second_round(round_index, policies):
        if round_index == 2:
            raise RuntimeError("round failed after prior commit")
        return real_run_round(round_index, policies)

    monkeypatch.setattr(record.runner, "run_round", fail_second_round)
    arena_jobs.run_arena(arena_id)
    failed = arena_jobs.get_arena(arena_id)

    assert failed.status == "failed"
    assert failed.error.code == "arena_round_failed"
    assert failed.error.round_index == 2
    assert failed.error.instance_id is None
    assert failed.completed_rounds == 1
    assert len(failed.rounds) == 1
    assert failed.rounds[0].round_index == 1
    assert {item.current_round_index for item in failed.instances} == {1}
    assert len(failed.rounds[0].instances) == 5
