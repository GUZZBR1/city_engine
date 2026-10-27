from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from app import main, multiseed_experiments as service
from app.multiseed_schemas import MultiSeedManifestRequest
from fastapi import BackgroundTasks
from simulation import SimulationError, SimulationResult, load_aurora_input
from simulation import SimulationMetrics as EngineMetrics
from urban_arena import load_aurora_snapshot


@pytest.fixture(autouse=True)
def isolated_store(tmp_path, monkeypatch):
    service.configure_store(tmp_path / "experiments.sqlite3", tmp_path / "artifacts")
    monkeypatch.setattr(service, "_probe_sumo_environment", lambda: {
        "status": "available", "engine": "fake-sumo",
        "sumo": {"path": "fixture/sumo", "version": "1.28.0", "sha256": "a" * 64},
        "netconvert": {"path": "fixture/netconvert", "version": "1.28.0", "sha256": "b" * 64},
    })


def request(**changes):
    inputs = load_aurora_input("aurora-base-v1", "weekday_am_peak")
    signal = inputs.traffic_signals[0]
    durations = [phase.duration_seconds for phase in signal.phases]
    intervention = {"node_id": signal.node_id, "phases": [
        {"movement": "north_south", "duration_seconds": durations[0] + 1},
        {"movement": "all_red", "duration_seconds": durations[1]},
        {"movement": "east_west", "duration_seconds": durations[2] - 1},
        {"movement": "all_red", "duration_seconds": durations[3]},
    ]}
    data = {
        "arena_manifest_id": "arena-manifest-v1", "arena_manifest_sha256": "a" * 64,
        "round_index": 1, "instance_id": "instance-1", "city_id": "aurora-base-v1",
        "window_ids": ["weekday_am_peak", "weekday_off_peak"], "seeds": [11, 17],
        "strategies": [{"strategy_id": "strategy-one", "policy_version": "v1", "policy_sha256": service._hash({"policy_id": "strategy-one", "policy_version": "v1", "intervention": intervention}),
            "intervention": intervention}],
        "baseline_id": "baseline", "baseline_version": "v1", "baseline_sha256": service._hash({"policy_id": "baseline", "policy_version": "v1", "intervention": None}),
        "drain_limit_seconds": 3600,
        "metrics": ["trips_requested", "trips_completed", "trips_not_completed", "mean_travel_time_seconds", "mean_queue_length_meters"],
        "metric_tolerances": {"trips_requested": {"exact": True}, "trips_completed": {"exact": True}, "trips_not_completed": {"exact": True}, "mean_travel_time_seconds": {"absolute": 0.1, "relative": 0.01}, "mean_queue_length_meters": {"absolute": 0.1, "relative": 0.01}},
        "primary_metrics": ["mean_travel_time_seconds"],
        "budget": {"max_sumo_runs": 16, "max_attempts_per_execution": 2, "max_reproducibility_checks": 0,
            "max_wall_clock_seconds_per_run": 10, "max_total_wall_clock_seconds": 160},
    }
    data.update(changes)
    return MultiSeedManifestRequest.model_validate(data)


def sim_result(*, window_id, seed, value, run_id, artifact_root=None):
    _, snapshot = load_aurora_snapshot()
    root = Path(artifact_root or ".")
    root.mkdir(parents=True, exist_ok=True)
    files = {}
    for name in ("network_file", "routes_file", "tripinfo_file", "queue_file"):
        path = root / f"{run_id}-{name}.xml"
        path.write_text("<fixture />", encoding="utf-8")
        files[name] = str(path)
    return SimulationResult(
        simulation_id=run_id, city_id="aurora-base-v1", snapshot_id=snapshot.snapshot_id, snapshot_hash=snapshot.hash,
        city_schema_version="1", city_generator_version="test", window_id=window_id, seed=seed,
        engine="fake-sumo", engine_version="1.28.0",
        metrics=EngineMetrics(trips_requested=20, trips_completed=18, trips_not_completed=2,
            mean_travel_time_seconds=value, mean_speed_kmh=25, mean_queue_length_meters=value / 2),
        metric_methods={"mean_travel_time_seconds": "fixture-v1"}, warnings=(),
        artifacts=files,
    )


def _is_strategy(city_id, window_id, inputs):
    return inputs.traffic_signals != load_aurora_input(city_id, window_id).traffic_signals


def test_manifest_is_canonical_and_collection_order_idempotent():
    first = request()
    second = request(window_ids=list(reversed(first.window_ids)), seeds=list(reversed(first.seeds)))
    a = service.create_experiment(first)
    b = service.create_experiment(second)
    assert (a.experiment_id, a.manifest_sha256) == (b.experiment_id, b.manifest_sha256)
    assert [p.pair_id for p in a.pairs] == [p.pair_id for p in b.pairs]
    assert service._canonical({"b": 1.0, "a": 0.000001}).decode() == '{"a":0.000001,"b":1}'
    assert service._student_t_critical(1, 0.95) == pytest.approx(12.706204736, rel=1e-8)


def test_metric_list_order_does_not_change_manifest_identity():
    metrics = ["trips_requested", "trips_completed"]
    primary = ["trips_requested", "trips_completed"]
    first = service.create_experiment(request(window_ids=["weekday_am_peak"], seeds=[11],
        metrics=metrics, primary_metrics=primary))
    second = service.create_experiment(request(window_ids=["weekday_am_peak"], seeds=[11],
        metrics=list(reversed(metrics)), primary_metrics=list(reversed(primary))))
    assert (first.experiment_id, first.manifest_sha256) == (second.experiment_id, second.manifest_sha256)


def test_required_scientific_limitations_cannot_be_removed_by_request():
    created = service.create_experiment(request(limitations=[]))
    assert set(service.REQUIRED_LIMITATIONS) <= set(created.manifest["limitations"])
    assert set(service.REQUIRED_LIMITATIONS) <= set(created.limitations)


def test_invalid_intervention_is_rejected_before_experiment_creation():
    payload = request(window_ids=["weekday_am_peak"], seeds=[11]).model_dump(mode="json")
    strategy = payload["strategies"][0]
    strategy["intervention"]["node_id"] = "node-without-signal"
    strategy["policy_sha256"] = service._hash({
        "policy_id": strategy["strategy_id"],
        "policy_version": strategy["policy_version"],
        "intervention": strategy["intervention"],
    })
    with pytest.raises(SimulationError, match="não existe no snapshot"):
        service.create_experiment(MultiSeedManifestRequest.model_validate(payload))


def test_sqlite_submission_is_idempotent_under_concurrency():
    payload = request()
    with ThreadPoolExecutor(max_workers=8) as pool:
        created = list(pool.map(service.create_experiment, [payload] * 8))
    assert len({item.experiment_id for item in created}) == 1
    assert len({item.manifest_sha256 for item in created}) == 1


def test_same_client_identity_with_changed_content_conflicts():
    first = service.create_experiment(request(experiment_id="client-exp-1"))
    with pytest.raises(service.ExperimentConflictError):
        service.create_experiment(request(experiment_id="client-exp-1", seeds=[11, 19]))
    assert service.get_experiment(first.experiment_id).manifest_sha256 == first.manifest_sha256


def test_client_id_cannot_escape_artifact_storage():
    with pytest.raises(Exception):
        request(experiment_id="../outside")


def test_supplied_policy_hash_must_match_canonical_applied_payload():
    with pytest.raises(ValueError, match="policy_sha256 divergente"):
        service.create_experiment(request(strategies=[{**request().strategies[0].model_dump(mode="json"), "policy_sha256": "b" * 64}]))


def test_budget_rejects_plan_before_creation():
    payload = request(budget={"max_sumo_runs": 1, "max_attempts_per_execution": 1,
        "max_reproducibility_checks": 0, "max_wall_clock_seconds_per_run": 10,
        "max_total_wall_clock_seconds": 100})
    with pytest.raises(service.ExperimentBudgetError):
        service.create_experiment(payload)


def test_time_and_speed_metrics_require_trip_completion_counts():
    data = request().model_dump(mode="json")
    data["metrics"] = ["mean_travel_time_seconds"]
    data["primary_metrics"] = ["mean_travel_time_seconds"]
    data["metric_tolerances"] = {"mean_travel_time_seconds": {"absolute": 0.1, "relative": 0.01}}
    with pytest.raises(ValueError, match="trips_requested, trips_completed e trips_not_completed"):
        MultiSeedManifestRequest.model_validate(data)


def test_two_windows_have_paired_runs_and_separate_summaries(monkeypatch):
    created = service.create_experiment(request())
    calls = []
    def fake_run(*, city_id, window_id, seed, inputs, limits, signal_timing_intervention=None):
        strategy = _is_strategy(city_id, window_id, inputs)
        calls.append((window_id, seed, inputs.snapshot_hash, tuple(trip.model_dump_json() for trip in inputs.trips), strategy))
        value = 60 + seed + (100 if window_id == "weekday_off_peak" else 0) + (4 if strategy else 0)
        return sim_result(window_id=window_id, seed=seed, value=value, run_id=f"run-{len(calls)}", artifact_root=limits.output_directory)
    monkeypatch.setattr(service, "run_simulation", fake_run)
    monkeypatch.setattr(service, "_has_route_exposure", lambda *args: "exposed")
    service.run_experiment(created.experiment_id)
    result = service.get_experiment(created.experiment_id)
    assert result.status == "succeeded"
    assert (result.planned_pairs, result.completed_pairs, result.planned_executions, result.attempts) == (4, 4, 8, 8)
    assert result.completed_pairs + result.failed_pairs + result.running_pairs + result.missing_pairs == result.planned_pairs
    assert len(result.manifest["backend_code_sha256"]) == 64
    assert {s.window_id for s in result.summaries_by_window} == {"weekday_am_peak", "weekday_off_peak"}
    assert all(s.n_planned == s.n_complete == 2 for s in result.summaries_by_window)
    for pair in result.pairs:
        assert pair.strategy_metrics["mean_travel_time_seconds"].value - pair.baseline_metrics["mean_travel_time_seconds"].value == 4
        assert pair.deltas["mean_travel_time_seconds"].value == 4
        assert pair.baseline_arm_input_sha256 != pair.strategy_arm_input_sha256
        assert pair.common_input_sha256
        assert pair.route_exposure == "exposed"
        assert pair.deltas["mean_travel_time_seconds"].method_version == "paired-delta-v1"
        assert len(pair.deltas["mean_travel_time_seconds"].source_artifact_sha256) == 2
        assert pair.baseline_metrics["mean_travel_time_seconds"].method_version == result.manifest["method_version"]
        assert pair.baseline_metrics["mean_travel_time_seconds"].method_version != pair.executions["baseline"].metric_methods.get("mean_travel_time_seconds")
        for attempt in pair.executions["baseline"].attempts + pair.executions["strategy"].attempts:
            assert attempt.backend_code_sha256 == result.manifest["backend_code_sha256"]
            assert attempt.python_runtime == result.manifest["python_runtime"]
            assert attempt.runtime_dependencies == result.manifest["runtime_dependencies"]
            assert attempt.sumo_binary_sha256 == result.manifest["sumo_environment"]["sumo"]["sha256"]
            assert attempt.netconvert_binary_sha256 == result.manifest["sumo_environment"]["netconvert"]["sha256"]
            assert attempt.sumo_engine == "fake-sumo" and attempt.sumo_version == "1.28.0"
    assert len(calls) == 8
    assert result.manifest["arena_reference_verification"] == "caller_asserted_unverified"
    assert "arena_manifest_reference_unverified" in result.limitations


def test_partial_retry_preserves_successful_arm_and_failed_metrics_are_null(monkeypatch):
    created = service.create_experiment(request(window_ids=["weekday_am_peak"], seeds=[11]))
    calls = []
    def flaky(*, city_id, window_id, seed, inputs, limits, signal_timing_intervention=None):
        strategy = _is_strategy(city_id, window_id, inputs)
        calls.append(strategy)
        if strategy and calls.count(True) == 1:
            raise SimulationError("sumo_timeout", "temporary timeout")
        return sim_result(window_id=window_id, seed=seed, value=64 if strategy else 60, run_id=f"run-{len(calls)}", artifact_root=limits.output_directory)
    monkeypatch.setattr(service, "run_simulation", flaky)
    service.run_experiment(created.experiment_id)
    partial = service.get_experiment(created.experiment_id)
    pair = partial.pairs[0]
    assert partial.status == "partial" and pair.status == "queued"
    assert pair.strategy_metrics == {}
    service.retry_experiment(created.experiment_id)
    service.run_experiment(created.experiment_id)
    done = service.get_experiment(created.experiment_id)
    assert done.status == "succeeded"
    assert len(done.pairs[0].executions["baseline"].attempts) == 1
    assert len(done.pairs[0].executions["strategy"].attempts) == 2


def test_selected_retry_runs_only_selected_pairs(monkeypatch):
    created = service.create_experiment(request(window_ids=["weekday_am_peak"], seeds=[11, 17]))
    with service._connect() as db:
        raw = __import__("json").loads(db.execute("SELECT dto_json FROM mobility_experiments WHERE experiment_id=?",
            (created.experiment_id,)).fetchone()[0])
        raw["status"] = "partial"
        for pair in raw["pairs"]:
            pair["status"] = "failed"
            baseline = pair["executions"]["baseline"]
            baseline["status"] = "failed"
            baseline["attempts"] = [{"attempt": 1, "status": "failed", "error": "sumo_timeout"}]
        db.execute("UPDATE mobility_experiments SET dto_json=? WHERE experiment_id=?",
            (service._dump(raw), created.experiment_id))
    selected_id, skipped_id = [pair.pair_id for pair in created.pairs]
    service.retry_experiment(created.experiment_id, [selected_id])
    def fake_run(*, city_id, window_id, seed, inputs, limits, signal_timing_intervention=None):
        return sim_result(window_id=window_id, seed=seed, value=60,
            run_id=f"selected-{seed}-{_is_strategy(city_id, window_id, inputs)}", artifact_root=limits.output_directory)
    monkeypatch.setattr(service, "run_simulation", fake_run)
    service.run_experiment(created.experiment_id)
    result = service.get_experiment(created.experiment_id)
    selected = next(pair for pair in result.pairs if pair.pair_id == selected_id)
    skipped = next(pair for pair in result.pairs if pair.pair_id == skipped_id)
    assert selected.status == "succeeded"
    assert skipped.status == "failed"
    assert skipped.executions["baseline"].status == "failed"
    assert skipped.executions["baseline"].attempts[0].error == "sumo_timeout"
    assert len(skipped.executions["baseline"].attempts) == 1
    assert result.status == "partial" and result.failed_pairs == 1 and result.missing_pairs == 0
    assert created.experiment_id not in service.list_resumable_experiments()


def test_retry_of_only_succeeded_pair_is_rejected_without_changing_scope():
    created = service.create_experiment(request(window_ids=["weekday_am_peak"], seeds=[11, 17]))
    with service._connect() as db:
        raw = __import__("json").loads(db.execute("SELECT dto_json FROM mobility_experiments WHERE experiment_id=?",
            (created.experiment_id,)).fetchone()[0])
        raw["status"] = "partial"
        raw["pairs"][0]["status"] = "succeeded"
        db.execute("UPDATE mobility_experiments SET dto_json=? WHERE experiment_id=?",
            (service._dump(raw), created.experiment_id))
    with pytest.raises(service.ExperimentStateError, match="já foram concluídos"):
        service.retry_experiment(created.experiment_id, [created.pairs[0].pair_id])
    with service._connect() as db:
        scope = db.execute("SELECT retry_pair_ids_json FROM mobility_experiments WHERE experiment_id=?",
            (created.experiment_id,)).fetchone()[0]
    assert scope is None


def test_executor_code_change_blocks_resume_and_preserves_provenance(monkeypatch):
    created = service.create_experiment(request(window_ids=["weekday_am_peak"], seeds=[11]))
    monkeypatch.setattr(service, "_executor_code_sha256", lambda: "0" * 64)
    service.run_experiment(created.experiment_id)
    result = service.get_experiment(created.experiment_id)
    assert result.status == "failed"
    assert result.error_code == "execution_environment_mismatch"
    assert result.attempts == 0 and result.missing_pairs == result.planned_pairs
    with pytest.raises(service.ExperimentStateError, match="executor mudou"):
        service.retry_experiment(created.experiment_id)


def test_sumo_binary_change_blocks_resume(monkeypatch):
    created = service.create_experiment(request(window_ids=["weekday_am_peak"], seeds=[11]))
    monkeypatch.setattr(service, "_probe_sumo_environment", lambda: {
        "status": "available", "engine": "fake-sumo",
        "sumo": {"path": "fixture/sumo", "version": "1.29.0", "sha256": "c" * 64},
        "netconvert": {"path": "fixture/netconvert", "version": "1.29.0", "sha256": "d" * 64},
    })
    service.run_experiment(created.experiment_id)
    result = service.get_experiment(created.experiment_id)
    assert result.status == "failed" and result.error_code == "execution_environment_mismatch"
    assert result.attempts == 0 and result.missing_pairs == result.planned_pairs


def test_unavailable_sumo_version_is_limited_and_fails_closed(monkeypatch):
    unavailable = {"status": "unavailable", "engine": "sumo", "sumo": None, "netconvert": None}
    monkeypatch.setattr(service, "_probe_sumo_environment", lambda: unavailable)
    created = service.create_experiment(request(window_ids=["weekday_am_peak"], seeds=[11]))
    assert created.manifest["sumo_environment"] == unavailable
    assert "sumo_environment_unavailable" in created.limitations
    def unexpected_success(*, city_id, window_id, seed, inputs, limits, signal_timing_intervention=None):
        return sim_result(window_id=window_id, seed=seed, value=60,
            run_id="unverified-sumo", artifact_root=limits.output_directory)
    monkeypatch.setattr(service, "run_simulation", unexpected_success)
    service.run_experiment(created.experiment_id)
    result = service.get_experiment(created.experiment_id)
    assert result.error_code == "execution_environment_mismatch"
    assert result.pairs[0].baseline_metrics == {}
    assert result.pairs[0].executions["baseline"].attempts[0].error == "execution_environment_mismatch"


def test_sumo_result_version_mismatch_is_not_published(monkeypatch):
    created = service.create_experiment(request(window_ids=["weekday_am_peak"], seeds=[11]))
    def changed_sumo(*, city_id, window_id, seed, inputs, limits, signal_timing_intervention=None):
        result = sim_result(window_id=window_id, seed=seed, value=60,
            run_id="changed-sumo", artifact_root=limits.output_directory)
        return result.model_copy(update={"engine_version": "1.29.0"})
    monkeypatch.setattr(service, "run_simulation", changed_sumo)
    service.run_experiment(created.experiment_id)
    result = service.get_experiment(created.experiment_id)
    pair = result.pairs[0]
    assert result.status == "failed" and result.error_code == "execution_environment_mismatch"
    assert pair.baseline_metrics == {} and pair.deltas == {}
    attempt = pair.executions["baseline"].attempts[0]
    assert attempt.error == "execution_environment_mismatch"
    assert (attempt.sumo_engine, attempt.sumo_version) == ("fake-sumo", "1.29.0")


def test_retry_rejects_recoverable_failure_at_attempt_cap(monkeypatch):
    payload = request(window_ids=["weekday_am_peak"], seeds=[11], budget={
        "max_sumo_runs": 2, "max_attempts_per_execution": 1,
        "max_reproducibility_checks": 0, "max_wall_clock_seconds_per_run": 10,
        "max_total_wall_clock_seconds": 20,
    })
    created = service.create_experiment(payload)
    def timeout(*, city_id, window_id, seed, inputs, limits, signal_timing_intervention=None):
        raise SimulationError("sumo_timeout", "fixture timeout")
    monkeypatch.setattr(service, "run_simulation", timeout)
    service.run_experiment(created.experiment_id)
    failed = service.get_experiment(created.experiment_id)
    assert failed.pairs[0].executions["baseline"].status == "failed"
    assert len(failed.pairs[0].executions["baseline"].attempts) == 1
    with pytest.raises(service.ExperimentStateError, match="limite de tentativas"):
        service.retry_experiment(created.experiment_id)


def test_parity_mismatch_invalidates_pair_and_suppresses_delta(monkeypatch):
    created = service.create_experiment(request(window_ids=["weekday_am_peak"], seeds=[11]))
    def mismatched(*, city_id, window_id, seed, inputs, limits, signal_timing_intervention=None):
        run_seed = seed + (1 if _is_strategy(city_id, window_id, inputs) else 0)
        return sim_result(window_id=window_id, seed=run_seed, value=60, run_id=f"run-{run_seed}", artifact_root=limits.output_directory)
    monkeypatch.setattr(service, "run_simulation", mismatched)
    service.run_experiment(created.experiment_id)
    final = service.get_experiment(created.experiment_id)
    assert final.status == "failed"
    assert final.pairs[0].status == "failed"
    assert final.pairs[0].error == "comparison_pair_mismatch"
    assert final.pairs[0].baseline_metrics == final.pairs[0].strategy_metrics == final.pairs[0].deltas == {}


@pytest.mark.parametrize("identity_change,expected_error", [
    ({"engine": "different-sumo"}, "execution_environment_mismatch"),
    ({"city_id": "unexpected-city"}, "comparison_pair_mismatch"),
])
def test_parity_rejects_engine_or_manifest_city_mismatch(monkeypatch, identity_change, expected_error):
    created = service.create_experiment(request(window_ids=["weekday_am_peak"], seeds=[11]))
    def mismatched(*, city_id, window_id, seed, inputs, limits, signal_timing_intervention=None):
        result = sim_result(window_id=window_id, seed=seed, value=60,
            run_id=f"parity-{_is_strategy(city_id, window_id, inputs)}", artifact_root=limits.output_directory)
        return result.model_copy(update=identity_change) if _is_strategy(city_id, window_id, inputs) else result
    monkeypatch.setattr(service, "run_simulation", mismatched)
    service.run_experiment(created.experiment_id)
    pair = service.get_experiment(created.experiment_id).pairs[0]
    assert pair.status == "failed" and pair.error == expected_error
    assert pair.deltas == {}


def test_null_metric_values_do_not_inflate_samples_or_claim_seed_stability(monkeypatch):
    created = service.create_experiment(request(window_ids=["weekday_am_peak"], seeds=[11, 17]))
    def with_one_null_metric(*, city_id, window_id, seed, inputs, limits, signal_timing_intervention=None):
        result = sim_result(window_id=window_id, seed=seed, value=60 if seed == 11 else 70,
            run_id=f"null-{seed}-{_is_strategy(city_id, window_id, inputs)}", artifact_root=limits.output_directory)
        if seed == 11:
            metrics = result.metrics.model_copy(update={"mean_queue_length_meters": None})
            result = result.model_copy(update={"metrics": metrics})
        return result
    monkeypatch.setattr(service, "run_simulation", with_one_null_metric)
    service.run_experiment(created.experiment_id)
    summary = next(s for s in service.get_experiment(created.experiment_id).summaries_by_window
        if s.metric_id == "mean_queue_length_meters")
    assert summary.n_planned == 2 and summary.n_complete == 1
    assert summary.seed_sensitivity == "insufficient_data"
    assert summary.paired_delta_seed_sensitivity == "insufficient_data"


def test_atomic_attempt_claim_and_nonrecoverable_retry_rejection():
    created = service.create_experiment(request(window_ids=["weekday_am_peak"], seeds=[11]))
    pair = created.pairs[0]
    with ThreadPoolExecutor(max_workers=8) as pool:
        claims = list(pool.map(lambda _: service._claim_attempt(created.experiment_id, pair.pair_id, "baseline"), range(8)))
    assert sum(claims) == 1
    running = service.get_experiment(created.experiment_id)
    assert len(running.pairs[0].executions["baseline"].attempts) == 1


def test_restart_recovers_orphaned_attempt_and_dispatches_persisted_job(monkeypatch, tmp_path):
    created = service.create_experiment(request(window_ids=["weekday_am_peak"], seeds=[11]))
    pair_id = created.pairs[0].pair_id
    assert service._claim_attempt(created.experiment_id, pair_id, "baseline")
    db_path = service._db_path
    data_root = service._data_root
    service.configure_store(db_path, data_root)
    recovered = service.get_experiment(created.experiment_id)
    assert recovered.pairs[0].executions["baseline"].attempts[0].error == "worker_lost"
    assert recovered.reserved_wall_clock_seconds == 0
    assert recovered.wall_clock_seconds_used == recovered.manifest["budget"]["max_wall_clock_seconds_per_run"]
    assert created.experiment_id in service.list_resumable_experiments()

    def fake_run(*, city_id, window_id, seed, inputs, limits, signal_timing_intervention=None):
        return sim_result(window_id=window_id, seed=seed, value=60, run_id=f"restart-{seed}", artifact_root=limits.output_directory)
    monkeypatch.setattr(service, "run_simulation", fake_run)
    service.run_experiment(created.experiment_id)
    final = service.get_experiment(created.experiment_id)
    assert final.status == "succeeded", final.model_dump(mode="json")
    assert len(final.pairs[0].executions["baseline"].attempts) == 2


def test_live_owner_is_not_recovered_by_another_api_initializer():
    created = service.create_experiment(request(window_ids=["weekday_am_peak"], seeds=[11]))
    claimed, _ = service._start_worker(created.experiment_id)
    assert claimed
    db_path, data_root = service._db_path, service._data_root
    service.configure_store(db_path, data_root)
    live = service.get_experiment(created.experiment_id)
    assert live.status == "running"
    assert live.pairs[0].executions["baseline"].status == "queued"
    with service._connect() as db:
        owner = db.execute("SELECT worker_owner FROM mobility_experiments WHERE experiment_id=?", (created.experiment_id,)).fetchone()[0]
    assert service._owner_is_alive(owner)


def test_recovery_reconciles_running_without_active_attempt():
    import json
    created = service.create_experiment(request(window_ids=["weekday_am_peak"], seeds=[11]))
    with service._connect() as db:
        raw = json.loads(db.execute("SELECT dto_json FROM mobility_experiments WHERE experiment_id=?", (created.experiment_id,)).fetchone()[0])
        raw["status"] = "running"
        db.execute("UPDATE mobility_experiments SET dto_json=?, worker_owner=NULL WHERE experiment_id=?",
            (service._dump(raw), created.experiment_id))
    service.configure_store(service._db_path, service._data_root)
    recovered = service.get_experiment(created.experiment_id)
    assert recovered.status == "queued" and recovered.running_pairs == 0
    assert created.experiment_id in service.list_resumable_experiments()


def test_owned_worker_failure_releases_and_charges_reservation_once():
    created = service.create_experiment(request(window_ids=["weekday_am_peak"], seeds=[11]))
    claimed, _ = service._start_worker(created.experiment_id)
    assert claimed
    assert service._claim_attempt(created.experiment_id, created.pairs[0].pair_id, "baseline")
    service._recover_owned_worker_failure(created.experiment_id)
    first = service.get_experiment(created.experiment_id)
    cap = first.manifest["budget"]["max_wall_clock_seconds_per_run"]
    assert first.reserved_wall_clock_seconds == 0 and first.wall_clock_seconds_used == cap
    service._recover_owned_worker_failure(created.experiment_id)
    second = service.get_experiment(created.experiment_id)
    assert second.reserved_wall_clock_seconds == 0 and second.wall_clock_seconds_used == cap


def test_worker_failure_before_first_attempt_is_visible(tmp_path):
    created = service.create_experiment(request(window_ids=["weekday_am_peak"], seeds=[11]))
    blocked_root = tmp_path / "artifact-root-file"
    blocked_root.write_text("not a directory", encoding="utf-8")
    service._data_root = blocked_root
    service.run_experiment(created.experiment_id)
    failed = service.get_experiment(created.experiment_id)
    assert failed.status == "failed"
    assert failed.error_code == "worker_failed_without_active_attempt"
    assert failed.attempts == 0 and failed.completed_pairs == 0
    assert failed.missing_pairs == failed.planned_pairs


def test_retry_route_dispatches_selected_partial_work(monkeypatch):
    created = service.create_experiment(request(window_ids=["weekday_am_peak"], seeds=[11]))
    partial = created.model_copy(update={"status": "partial", "missing_pairs": 1})
    monkeypatch.setattr(main, "retry_experiment", lambda *args: partial)
    background = BackgroundTasks()
    main.resume_mobility_experiment(created.experiment_id, main.ExperimentRetryRequest(), background)
    assert len(background.tasks) == 1
    assert background.tasks[0].func is main.run_experiment
    assert background.tasks[0].args == (created.experiment_id,)


def test_api_startup_dispatches_persisted_queued_work(monkeypatch):
    scheduled = []
    class Pool:
        def submit(self, function, experiment_id):
            scheduled.append((function, experiment_id))
    monkeypatch.setattr(main, "list_resumable_experiments", lambda: ["persisted-queued-1"])
    monkeypatch.setattr(main, "_mobility_recovery_pool", Pool())
    main._dispatch_persisted_mobility_experiments()
    assert scheduled == [(main.run_experiment, "persisted-queued-1")]


def test_missing_audit_artifacts_fail_arm_instead_of_publishing_metrics(monkeypatch):
    created = service.create_experiment(request(window_ids=["weekday_am_peak"], seeds=[11]))
    def missing(*, city_id, window_id, seed, inputs, limits, signal_timing_intervention=None):
        return SimulationResult(
            simulation_id="without-artifacts", city_id=city_id, snapshot_id=inputs.snapshot_id, snapshot_hash=inputs.snapshot_hash,
            city_schema_version=inputs.city_schema_version, city_generator_version=inputs.city_generator_version,
            window_id=window_id, seed=seed, engine="fake-sumo", engine_version="1.28.0",
            metrics=EngineMetrics(trips_requested=len(inputs.trips), trips_completed=0, trips_not_completed=len(inputs.trips),
                mean_travel_time_seconds=None, mean_speed_kmh=None, mean_queue_length_meters=None), metric_methods={}, warnings=(),
            artifacts={"network_file": "missing", "routes_file": "missing", "tripinfo_file": "missing", "queue_file": "missing"},
        )
    monkeypatch.setattr(service, "run_simulation", missing)
    service.run_experiment(created.experiment_id)
    partial = service.get_experiment(created.experiment_id)
    assert partial.status == "partial"
    assert partial.pairs[0].baseline_metrics == partial.pairs[0].deltas == {}
    assert partial.pairs[0].executions["baseline"].attempts[0].error == "artifact_missing"


def test_cancel_during_active_run_stays_running_until_acknowledged(monkeypatch):
    created = service.create_experiment(request(window_ids=["weekday_am_peak"], seeds=[11]))
    responses = []
    def cancellable(*, city_id, window_id, seed, inputs, limits, signal_timing_intervention=None):
        if not _is_strategy(city_id, window_id, inputs):
            responses.append(service.cancel_experiment(created.experiment_id))
        return sim_result(window_id=window_id, seed=seed, value=60, run_id="cancel-test", artifact_root=limits.output_directory)
    monkeypatch.setattr(service, "run_simulation", cancellable)
    service.run_experiment(created.experiment_id)
    assert responses[0].status == "running" and responses[0].cancellation_requested
    final = service.get_experiment(created.experiment_id)
    assert final.status == "cancelled" and final.cancellation_requested
    assert final.pairs[0].executions["baseline"].result_metrics is None


def test_routes_openapi_poll_missing_ids_and_cancel():
    paths = main.app.openapi()["paths"]
    assert {"post"} <= paths["/api/v1/mobility-experiments"].keys()
    assert {"get"} <= paths["/api/v1/mobility-experiments/{experiment_id}"].keys()
    assert {"post"} <= paths["/api/v1/mobility-experiments/{experiment_id}/retry"].keys()
    assert {"post"} <= paths["/api/v1/mobility-experiments/{experiment_id}/cancel"].keys()
    background = BackgroundTasks()
    created = main.start_mobility_experiment(request(), background).experiment
    polled = main.mobility_experiment_status(created.experiment_id).experiment
    assert polled.missing_pairs == 4 and polled.missing_pair_ids == [p.pair_id for p in polled.pairs]
    assert main.stop_mobility_experiment(created.experiment_id).status == "cancelled"
    final = service.get_experiment(created.experiment_id)
    assert final.status == "cancelled" and final.completed_pairs == 0
    assert all(pair.status == "cancelled" for pair in final.pairs)
