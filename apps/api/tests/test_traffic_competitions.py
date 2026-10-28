from __future__ import annotations

from simulation import SimulationError, SimulationLimits, SimulationMetrics as EngineMetrics, SimulationResult

from app import simulation_jobs
from app.schemas import TrafficCompetitionRequest


def request() -> TrafficCompetitionRequest:
    return TrafficCompetitionRequest(
        city_id="aurora-base-v1",
        window_id="weekday_am_peak",
        seed=42,
        drain_limit_seconds=3600,
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


def metrics(*, completed: int, travel_time: float, speed: float, queue: float) -> EngineMetrics:
    return EngineMetrics(
        trips_requested=930,
        trips_completed=completed,
        trips_not_completed=930 - completed,
        mean_travel_time_seconds=travel_time,
        mean_speed_kmh=speed,
        mean_queue_length_meters=queue,
    )


def test_company_strategies_preserve_signal_cycle_and_all_red_durations():
    inputs = simulation_jobs.load_aurora_input("aurora-base-v1", "weekday_am_peak")

    companies = simulation_jobs._company_strategies(inputs)

    assert len(companies) == 5
    assert [company.company_id for company in companies] == [
        "via-equilibrio",
        "eixo-norte-sul",
        "eixo-leste-oeste",
        "corredor-norte",
        "corredor-leste",
    ]
    for company in companies:
        phases = company.intervention.phases
        assert [phase.movement for phase in phases] == [
            "north_south", "all_red", "east_west", "all_red"
        ]
        assert sum(phase.duration_seconds for phase in phases) == 66
        assert [phase.duration_seconds for phase in phases if phase.movement == "all_red"] == [3, 3]

    assert [[phase.duration_seconds for phase in company.intervention.phases] for company in companies] == [
        [30, 3, 30, 3],
        [36, 3, 24, 3],
        [24, 3, 36, 3],
        [42, 3, 18, 3],
        [18, 3, 42, 3],
    ]


def test_competition_runs_five_paired_strategies_and_publishes_deltas(monkeypatch):
    competition = simulation_jobs.create_traffic_competition(request())
    captured = []
    company_runs = 0

    def fake_run_simulation(**kwargs):
        nonlocal company_runs
        captured.append(kwargs)
        inputs = kwargs["inputs"]
        intervention = kwargs.get("signal_timing_intervention")
        if intervention is None:
            return result(inputs, run_id="baseline-run", metrics=metrics(
                completed=900, travel_time=60, speed=30, queue=10
            ))

        company_runs += 1
        return result(inputs, run_id=f"company-run-{company_runs}", metrics=metrics(
            completed=900 + company_runs,
            travel_time=60 - company_runs,
            speed=30 + company_runs,
            queue=10 - company_runs,
        ))

    monkeypatch.setattr(simulation_jobs, "run_simulation", fake_run_simulation)
    monkeypatch.setattr(simulation_jobs, "_has_route_exposure", lambda *_args: "exposed")

    simulation_jobs.run_traffic_competition(competition.competition_id)
    final = simulation_jobs.get_traffic_competition(competition.competition_id)

    assert final.status == "succeeded"
    assert len(captured) == 6
    assert captured[0].get("signal_timing_intervention") is None
    assert all(call["inputs"] is captured[0]["inputs"] for call in captured)
    assert all(call["city_id"] == "aurora-base-v1" for call in captured)
    assert all(call["window_id"] == "weekday_am_peak" for call in captured)
    assert all(call["seed"] == 42 for call in captured)
    assert all(call["limits"].drain_limit_seconds == 3600 for call in captured)
    assert all(call["limits"] == captured[0]["limits"] for call in captured)
    assert [company.result.simulation_id for company in final.companies] == [
        "company-run-1", "company-run-2", "company-run-3", "company-run-4", "company-run-5"
    ]
    assert final.baseline_result.simulation_id == "baseline-run"
    assert final.baseline_metrics.trips_requested == 930
    assert [company.deltas_vs_baseline.trips_completed for company in final.companies] == [1, 2, 3, 4, 5]
    assert [company.deltas_vs_baseline.mean_travel_time_seconds for company in final.companies] == [-1, -2, -3, -4, -5]
    assert all(company.route_exposure == "exposed" for company in final.companies)


def test_failed_company_does_not_publish_partial_competition_metrics(monkeypatch):
    competition = simulation_jobs.create_traffic_competition(request())
    company_runs = 0

    def fail_third_company(**kwargs):
        nonlocal company_runs
        inputs = kwargs["inputs"]
        if kwargs.get("signal_timing_intervention") is None:
            return result(inputs, run_id="baseline-run", metrics=metrics(
                completed=900, travel_time=60, speed=30, queue=10
            ))

        company_runs += 1
        if company_runs == 3:
            raise SimulationError("sumo_execution_error", "company SUMO failed")
        return result(inputs, run_id=f"company-run-{company_runs}", metrics=metrics(
            completed=900, travel_time=60, speed=30, queue=10
        ))

    monkeypatch.setattr(simulation_jobs, "run_simulation", fail_third_company)

    simulation_jobs.run_traffic_competition(competition.competition_id)
    final = simulation_jobs.get_traffic_competition(competition.competition_id)

    assert final.status == "failed"
    assert final.error.code == "sumo_execution_error"
    assert final.error.scenario == "company"
    assert final.error.company_id == "eixo-leste-oeste"
    assert final.baseline_result.simulation_id == "baseline-run"
    assert final.baseline_metrics is None
    assert all(company.metrics is None for company in final.companies)
    assert all(company.deltas_vs_baseline is None for company in final.companies)
    assert all(company.result is None for company in final.companies)


def test_unexpected_failure_is_logged_but_client_message_stays_generic(monkeypatch, caplog):
    competition = simulation_jobs.create_traffic_competition(request())

    def fail_internally(**kwargs):
        raise RuntimeError("sensitive internal detail")

    monkeypatch.setattr(simulation_jobs, "run_simulation", fail_internally)

    simulation_jobs.run_traffic_competition(competition.competition_id)
    final = simulation_jobs.get_traffic_competition(competition.competition_id)

    assert final.status == "failed"
    assert final.error.code == "competition_failed"
    assert "sensitive internal detail" not in final.error.message
    assert "Traffic competition" in caplog.text
    assert "sensitive internal detail" in caplog.text
