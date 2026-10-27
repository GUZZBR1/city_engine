from __future__ import annotations

import pytest
from app import main, simulation_jobs
from app.schemas import SimulationRequest
from fastapi import BackgroundTasks
from simulation import SimulationError, SimulationLimits, SimulationResult
from simulation import SimulationMetrics as EngineMetrics


@pytest.fixture(autouse=True)
def isolated_jobs(monkeypatch):
    monkeypatch.setattr(simulation_jobs, "_jobs", {})


def request() -> SimulationRequest:
    return SimulationRequest(
        city_id="aurora-base-v1",
        window_id="weekday_off_peak",
        seed=137,
        drain_limit_seconds=517,
    )


def result(*, window_id: str, seed: int) -> SimulationResult:
    return SimulationResult(
        simulation_id="engine-run-1",
        city_id="aurora-base-v1",
        snapshot_id="snapshot-1",
        snapshot_hash="a" * 64,
        city_schema_version="1",
        city_generator_version="test",
        window_id=window_id,
        seed=seed,
        engine="sumo",
        engine_version="1.28.0",
        metrics=EngineMetrics(
            trips_requested=17,
            trips_completed=12,
            trips_not_completed=5,
            mean_travel_time_seconds=83.25,
            mean_speed_kmh=27.5,
            mean_queue_length_meters=14.75,
        ),
        metric_methods={},
        warnings=("synthetic fixture",),
        artifacts={"network_file": "network.xml", "routes_file": "routes.xml"},
    )


def test_job_runs_with_requested_window_seed_and_drain_limit_and_keeps_window_metrics(monkeypatch):
    job = simulation_jobs.create_job(request())
    observed = []

    def fake_run_simulation(*, city_id, window_id, seed, limits):
        observed.append({
            "city_id": city_id,
            "window_id": window_id,
            "seed": seed,
            "limits": limits,
            "status": simulation_jobs.get_job(job.simulation_id).status,
        })
        return result(window_id=window_id, seed=seed)

    monkeypatch.setattr(simulation_jobs, "run_simulation", fake_run_simulation)

    assert job.status == "queued"
    simulation_jobs.run_job(job.simulation_id)

    final = simulation_jobs.get_job(job.simulation_id)
    assert observed == [{
        "city_id": "aurora-base-v1",
        "window_id": "weekday_off_peak",
        "seed": 137,
        "limits": SimulationLimits(drain_limit_seconds=517),
        "status": "running",
    }]
    assert final.status == "succeeded"
    assert final.window_id == "weekday_off_peak"
    assert final.seed == 137
    assert final.drain_limit_seconds == 517
    assert final.engine_version == "1.28.0"
    assert final.metrics.model_dump() == {
        "trips_requested": 17,
        "trips_completed": 12,
        "trips_not_completed": 5,
        "mean_travel_time_seconds": 83.25,
        "mean_speed_kmh": 27.5,
        "mean_queue_length_meters": 14.75,
    }
    assert final.warnings == ["synthetic fixture"]
    assert final.error is None


def test_job_failure_keeps_stable_engine_error_code(monkeypatch):
    job = simulation_jobs.create_job(request())
    observed_statuses = []

    def fail_run_simulation(**kwargs):
        observed_statuses.append(simulation_jobs.get_job(job.simulation_id).status)
        assert kwargs["window_id"] == "weekday_off_peak"
        assert kwargs["seed"] == 137
        assert kwargs["limits"] == SimulationLimits(drain_limit_seconds=517)
        raise SimulationError("sumo_execution_error", "SUMO exited with code 1")

    monkeypatch.setattr(simulation_jobs, "run_simulation", fail_run_simulation)

    assert job.status == "queued"
    simulation_jobs.run_job(job.simulation_id)

    final = simulation_jobs.get_job(job.simulation_id)
    assert observed_statuses == ["running"]
    assert final.status == "failed"
    assert final.engine_version == "unknown"
    assert final.metrics is None
    assert final.error.code == "sumo_execution_error"
    assert final.error.message == "SUMO exited with code 1"


def test_simulation_endpoints_expose_queued_job_then_window_result(monkeypatch):
    def fake_run_simulation(*, city_id, window_id, seed, limits):
        return result(window_id=window_id, seed=seed)

    monkeypatch.setattr(simulation_jobs, "run_simulation", fake_run_simulation)
    background_tasks = BackgroundTasks()

    created = main.start_simulation(request(), background_tasks)

    assert created.simulation.status == "queued"
    assert len(background_tasks.tasks) == 1
    task = background_tasks.tasks[0]
    task.func(*task.args, **task.kwargs)
    published = main.simulation_status(created.simulation.simulation_id).simulation

    assert published.status == "succeeded"
    assert published.window_id == "weekday_off_peak"
    assert published.metrics.trips_requested == 17
    assert published.metrics.mean_travel_time_seconds == 83.25


def test_simulation_endpoint_exposes_job_error(monkeypatch):
    def fail_run_simulation(**kwargs):
        raise SimulationError("sumo_unavailable", "SUMO is not installed")

    monkeypatch.setattr(simulation_jobs, "run_simulation", fail_run_simulation)
    background_tasks = BackgroundTasks()

    created = main.start_simulation(request(), background_tasks)
    assert created.simulation.status == "queued"
    task = background_tasks.tasks[0]
    task.func(*task.args, **task.kwargs)
    failed = main.simulation_status(created.simulation.simulation_id).simulation

    assert failed.status == "failed"
    assert failed.metrics is None
    assert failed.error.model_dump() == {"code": "sumo_unavailable", "message": "SUMO is not installed"}
