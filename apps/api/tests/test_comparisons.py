from __future__ import annotations

from simulation import SimulationError, SimulationMetrics as EngineMetrics, SimulationResult

from app import simulation_jobs
from app.schemas import ComparisonRequest


def request() -> ComparisonRequest:
    return ComparisonRequest(
        city_id="aurora-base-v1",
        window_id="weekday_am_peak",
        seed=42,
        drain_limit_seconds=3600,
        intervention={
            "node_id": "node:02:00",
            "phases": [
                {"movement": "north_south", "duration_seconds": 40},
                {"movement": "all_red", "duration_seconds": 3},
                {"movement": "east_west", "duration_seconds": 20},
                {"movement": "all_red", "duration_seconds": 3},
            ],
        },
    )


def result(inputs, *, run_id: str, metrics: EngineMetrics) -> SimulationResult:
    return SimulationResult(
        simulation_id=run_id,
        city_id=inputs.city_id,
        snapshot_id=inputs.snapshot_id,
        snapshot_hash=inputs.snapshot_hash,
        city_schema_version=inputs.city_schema_version,
        city_generator_version=inputs.city_generator_version,
        window_id=inputs.window.id,
        seed=42,
        engine="sumo",
        engine_version="1.28.0",
        metrics=metrics,
        metric_methods={},
        artifacts={"network_file": "network.xml", "routes_file": "routes.xml"},
    )


def test_comparison_runs_paired_inputs_and_publishes_engine_metrics_and_deltas(monkeypatch):
    comparison = simulation_jobs.create_comparison(request())
    captured = []

    def fake_run_simulation(**kwargs):
        captured.append(kwargs)
        base = kwargs["inputs"]
        if kwargs.get("signal_timing_intervention") is not None:
            target = next(signal for signal in base.traffic_signals if signal.node_id == "node:02:00")
            assert [phase.duration_seconds for phase in target.phases] == [35, 3, 25, 3]
            return result(base, run_id="intervention-run", metrics=EngineMetrics(
                trips_requested=930, trips_completed=900, trips_not_completed=30,
                mean_travel_time_seconds=60, mean_speed_kmh=31, mean_queue_length_meters=9,
            ))
        assert kwargs["limits"].drain_limit_seconds == 3600
        return result(base, run_id="base-run", metrics=EngineMetrics(
            trips_requested=930, trips_completed=890, trips_not_completed=40,
            mean_travel_time_seconds=62, mean_speed_kmh=30, mean_queue_length_meters=10,
        ))

    monkeypatch.setattr(simulation_jobs, "run_simulation", fake_run_simulation)
    simulation_jobs.run_comparison(comparison.comparison_id)
    final = simulation_jobs.get_comparison(comparison.comparison_id)

    assert final.status == "succeeded"
    assert final.base_result.simulation_id == "base-run"
    assert final.intervention_result.simulation_id == "intervention-run"
    assert final.base_metrics.trips_requested == final.intervention_metrics.trips_requested == 930
    assert final.deltas.trips_completed == 10
    assert final.deltas.trips_not_completed == -10
    assert final.deltas.mean_travel_time_seconds == -2
    assert final.deltas.mean_queue_length_meters == -1
    assert captured[0]["inputs"] is captured[1]["inputs"]
    assert captured[0]["seed"] == captured[1]["seed"] == 42
    assert captured[0]["limits"] == captured[1]["limits"]
    assert any("Não foi possível verificar" in warning for warning in final.intervention_warnings)


def test_route_exposure_distinguishes_missing_routes_from_no_exposure(tmp_path):
    inputs = simulation_jobs.load_aurora_input("aurora-base-v1", "weekday_am_peak")
    intervention = request().intervention
    base = result(inputs, run_id="base-run", metrics=EngineMetrics(
        trips_requested=930, trips_completed=890, trips_not_completed=40,
        mean_travel_time_seconds=62, mean_speed_kmh=30, mean_queue_length_meters=10,
    ))

    assert simulation_jobs._has_route_exposure(inputs, intervention, base) is None

    routes_file = tmp_path / "routes.xml"
    routes_file.write_text('<routes><vehicle id="v0"><route edges="edge-a edge-b"/></vehicle></routes>')
    valid_base = base.model_copy(update={
        "artifacts": base.artifacts.model_copy(update={"routes_file": str(routes_file)})
    })
    assert simulation_jobs._has_route_exposure(inputs, intervention, valid_base) is False

    routes_file.write_text("not xml")
    invalid_base = base.model_copy(update={
        "artifacts": base.artifacts.model_copy(update={"routes_file": str(routes_file)})
    })
    assert simulation_jobs._has_route_exposure(inputs, intervention, invalid_base) is None


def test_failed_intervention_does_not_publish_partial_metrics_or_deltas(monkeypatch):
    comparison = simulation_jobs.create_comparison(request())
    calls = 0

    def fail_second(**kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise SimulationError("sumo_execution_error", "intervention SUMO failed")
        inputs = kwargs["inputs"]
        return result(inputs, run_id="base-run", metrics=EngineMetrics(
            trips_requested=930, trips_completed=890, trips_not_completed=40,
            mean_travel_time_seconds=62, mean_speed_kmh=30, mean_queue_length_meters=10,
        ))

    monkeypatch.setattr(simulation_jobs, "run_simulation", fail_second)
    simulation_jobs.run_comparison(comparison.comparison_id)
    final = simulation_jobs.get_comparison(comparison.comparison_id)
    assert final.status == "failed"
    assert final.error.scenario == "intervention"
    assert final.base_result.simulation_id == "base-run"
    assert final.base_metrics is final.intervention_metrics is final.deltas is None
