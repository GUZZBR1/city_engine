"""Process-local simulation jobs for the local MVP."""

from __future__ import annotations

import hashlib
import json
import logging
import xml.etree.ElementTree as ET
from threading import RLock
from typing import Literal
from uuid import uuid4

from simulation import (
    SimulationError,
    SimulationInput,
    SimulationLimits,
    SimulationResult,
    SignalTimingPhase,
    SignalTimingIntervention,
    apply_signal_timing_intervention,
    load_aurora_input,
    run_simulation,
)
from simulation.compiler import sumo_identifier
from urban_arena import load_aurora_snapshot

from .schemas import (
    SimulationFailure,
    SimulationJob,
    SimulationMetrics,
    SimulationRequest,
    ComparisonCommonParameters,
    ComparisonFailure,
    ComparisonRequest,
    ComparisonResultIdentity,
    SimulationComparison,
    SimulationMetricDeltas,
    TrafficCompanyResult,
    TrafficCompetition,
    TrafficCompetitionFailure,
    TrafficCompetitionRequest,
)

logger = logging.getLogger(__name__)


class SimulationNotFoundError(LookupError):
    pass


class UnknownSimulationWindowError(ValueError):
    pass


_jobs: dict[str, SimulationJob] = {}
_comparisons: dict[str, SimulationComparison] = {}
_competitions: dict[str, TrafficCompetition] = {}
_comparison_inputs: dict[str, SimulationInput] = {}
_competition_inputs: dict[str, SimulationInput] = {}
_jobs_lock = RLock()

RouteExposure = Literal["exposed", "not_exposed", "unknown"]

_COMPANY_SPLITS = (
    ("via-equilibrio", "Via Equilíbrio", "Divide o tempo verde entre os dois eixos", 30),
    ("eixo-norte-sul", "Eixo Norte-Sul", "Prioriza o fluxo norte-sul", 36),
    ("eixo-leste-oeste", "Eixo Leste-Oeste", "Prioriza o fluxo leste-oeste", 24),
    ("corredor-norte", "Corredor Norte", "Concentra verde no eixo norte-sul", 42),
    ("corredor-leste", "Corredor Leste", "Concentra verde no eixo leste-oeste", 18),
)


def _company_strategies(inputs: SimulationInput) -> list[TrafficCompanyResult]:
    signal = next((item for item in inputs.traffic_signals if item.node_id == "node:02:04"), None)
    if signal is None:
        raise InvalidComparisonScenario("O cruzamento de competição não possui controlador semafórico.")
    red_seconds = sum(phase.duration_seconds for phase in signal.phases if phase.movement == "all_red")
    green_seconds = sum(phase.duration_seconds for phase in signal.phases if phase.movement != "all_red")
    strategies = []
    for company_id, name, description, north_south_seconds in _COMPANY_SPLITS:
        intervention = SignalTimingIntervention(
            node_id=signal.node_id,
            phases=(
                SignalTimingPhase(movement="north_south", duration_seconds=north_south_seconds),
                SignalTimingPhase(movement="all_red", duration_seconds=signal.phases[1].duration_seconds),
                SignalTimingPhase(movement="east_west", duration_seconds=green_seconds - north_south_seconds),
                SignalTimingPhase(movement="all_red", duration_seconds=signal.phases[3].duration_seconds),
            ),
        )
        try:
            apply_signal_timing_intervention(inputs, intervention)
        except SimulationError as exc:
            raise InvalidComparisonScenario(str(exc)) from exc
        if sum(phase.duration_seconds for phase in intervention.phases if phase.movement == "all_red") != red_seconds:
            raise InvalidComparisonScenario("As estratégias precisam preservar os tempos de segurança do cruzamento.")
        strategies.append(TrafficCompanyResult(
            company_id=company_id,
            name=name,
            strategy=description,
            intervention=intervention,
        ))
    return strategies


def create_traffic_competition(request: TrafficCompetitionRequest) -> TrafficCompetition:
    try:
        inputs = load_aurora_input(request.city_id, request.window_id)
        companies = _company_strategies(inputs)
    except SimulationError as exc:
        raise InvalidComparisonScenario(str(exc)) from exc
    except (ValueError, TypeError, StopIteration) as exc:
        raise InvalidComparisonScenario(str(exc)) from exc

    demand_payload = [trip.model_dump(mode="json") for trip in inputs.trips]
    demand_hash = hashlib.sha256(json.dumps(
        demand_payload, sort_keys=True, separators=(",", ":")
    ).encode()).hexdigest()
    competition_id = str(uuid4())
    competition = TrafficCompetition(
        competition_id=competition_id,
        status="queued",
        common_parameters=ComparisonCommonParameters(
            city_id=inputs.city_id,
            snapshot_id=inputs.snapshot_id,
            snapshot_hash=inputs.snapshot_hash,
            window_id=inputs.window.id,
            seed=request.seed,
            drain_limit_seconds=request.drain_limit_seconds,
            trips_requested=len(inputs.trips),
            demand_hash=demand_hash,
        ),
        companies=companies,
    )
    with _jobs_lock:
        _competitions[competition_id] = competition
        _competition_inputs[competition_id] = inputs
    return competition


def get_traffic_competition(competition_id: str) -> TrafficCompetition:
    with _jobs_lock:
        competition = _competitions.get(competition_id)
    if competition is None:
        raise SimulationNotFoundError(competition_id)
    return competition


def run_traffic_competition(competition_id: str) -> None:
    with _jobs_lock:
        current = _competitions.get(competition_id)
        inputs = _competition_inputs.get(competition_id)
        if current is None or inputs is None:
            return
        _competitions[competition_id] = current.model_copy(update={"status": "running"})

    baseline: SimulationResult | None = None
    failing_company: TrafficCompanyResult | None = None
    scenario = "baseline"
    try:
        limits = SimulationLimits(drain_limit_seconds=current.common_parameters.drain_limit_seconds)
        baseline = run_simulation(
            city_id=current.common_parameters.city_id,
            window_id=current.common_parameters.window_id,
            seed=current.common_parameters.seed,
            inputs=inputs,
            limits=limits,
        )
        updated_companies = []
        for company in current.companies:
            scenario = "company"
            failing_company = company
            result = run_simulation(
                city_id=current.common_parameters.city_id,
                window_id=current.common_parameters.window_id,
                seed=current.common_parameters.seed,
                inputs=inputs,
                limits=limits,
                signal_timing_intervention=company.intervention,
            )
            _assert_paired_results(baseline, result, current.common_parameters)
            exposure = _has_route_exposure(inputs, company.intervention, baseline)
            warnings = list(result.warnings)
            if exposure == "not_exposed":
                warnings.append("Nenhuma rota solicitada atravessa este cruzamento; os deltas não medem efeito da estratégia nesta janela.")
            elif exposure == "unknown":
                warnings.append("Não foi possível verificar a exposição das rotas ao cruzamento; interprete os deltas com cautela.")
            updated_companies.append(company.model_copy(update={
                "route_exposure": exposure,
                "result": _result_identity(result),
                "metrics": _api_metrics(result),
                "deltas_vs_baseline": _metric_deltas(baseline.metrics, result.metrics),
                "warnings": warnings,
            }))
        updated = current.model_copy(update={
            "status": "succeeded",
            "baseline_result": _result_identity(baseline),
            "baseline_metrics": _api_metrics(baseline),
            "companies": updated_companies,
            "error": None,
        })
    except SimulationError as exc:
        updated = current.model_copy(update={
            "status": "failed",
            "baseline_result": _result_identity(baseline) if baseline else None,
            "baseline_metrics": None,
            "companies": [company.model_copy(update={"metrics": None, "deltas_vs_baseline": None, "result": None}) for company in current.companies],
            "error": TrafficCompetitionFailure(code=exc.code, scenario=scenario,
                company_id=failing_company.company_id if failing_company else None, message=str(exc)),
        })
    except Exception:
        logger.exception(
            "Traffic competition %s failed during %s (company_id=%s)",
            competition_id,
            scenario,
            failing_company.company_id if failing_company else None,
        )
        updated = current.model_copy(update={
            "status": "failed",
            "baseline_result": _result_identity(baseline) if baseline else None,
            "baseline_metrics": None,
            "companies": [company.model_copy(update={"metrics": None, "deltas_vs_baseline": None, "result": None}) for company in current.companies],
            "error": TrafficCompetitionFailure(
                code="competition_failed", scenario=scenario,
                company_id=failing_company.company_id if failing_company else None,
                message="A competição falhou por um erro interno; resultados parciais não foram publicados.",
            ),
        })
    with _jobs_lock:
        _competitions[competition_id] = updated
        _competition_inputs.pop(competition_id, None)


def create_job(request: SimulationRequest) -> SimulationJob:
    config, snapshot = load_aurora_snapshot()
    if request.window_id not in {window.id for window in config.mobility.simulation_windows}:
        raise UnknownSimulationWindowError(f"Janela de simulação desconhecida: '{request.window_id}'.")
    job = SimulationJob(
        simulation_id=str(uuid4()),
        status="queued",
        city_id=snapshot.city_id,
        snapshot_id=snapshot.snapshot_id,
        window_id=request.window_id,
        seed=request.seed,
        drain_limit_seconds=request.drain_limit_seconds,
        engine_version="pending",
    )
    with _jobs_lock:
        _jobs[job.simulation_id] = job
    return job


def get_job(simulation_id: str) -> SimulationJob:
    with _jobs_lock:
        job = _jobs.get(simulation_id)
    if job is None:
        raise SimulationNotFoundError(simulation_id)
    return job


def create_comparison(request: ComparisonRequest) -> SimulationComparison:
    try:
        inputs = load_aurora_input(request.city_id, request.window_id)
        apply_signal_timing_intervention(inputs, request.intervention)
    except SimulationError as exc:
        raise InvalidComparisonScenario(str(exc)) from exc
    except (ValueError, TypeError) as exc:
        raise InvalidComparisonScenario(str(exc)) from exc

    demand_payload = [trip.model_dump(mode="json") for trip in inputs.trips]
    demand_hash = hashlib.sha256(json.dumps(
        demand_payload, sort_keys=True, separators=(",", ":")
    ).encode()).hexdigest()
    comparison_id = str(uuid4())
    comparison = SimulationComparison(
        comparison_id=comparison_id,
        status="queued",
        common_parameters=ComparisonCommonParameters(
            city_id=inputs.city_id,
            snapshot_id=inputs.snapshot_id,
            snapshot_hash=inputs.snapshot_hash,
            window_id=inputs.window.id,
            seed=request.seed,
            drain_limit_seconds=request.drain_limit_seconds,
            trips_requested=len(inputs.trips),
            demand_hash=demand_hash,
        ),
        intervention=request.intervention,
    )
    with _jobs_lock:
        _comparisons[comparison_id] = comparison
        _comparison_inputs[comparison_id] = inputs
    return comparison


def get_comparison(comparison_id: str) -> SimulationComparison:
    with _jobs_lock:
        comparison = _comparisons.get(comparison_id)
    if comparison is None:
        raise SimulationNotFoundError(comparison_id)
    return comparison


class InvalidComparisonScenario(ValueError):
    pass


def run_comparison(comparison_id: str) -> None:
    with _jobs_lock:
        current = _comparisons.get(comparison_id)
        inputs = _comparison_inputs.get(comparison_id)
        if current is None or inputs is None:
            return
        _comparisons[comparison_id] = current.model_copy(update={"status": "running"})

    base_result: SimulationResult | None = None
    intervention_result: SimulationResult | None = None
    scenario = "base"
    try:
        limits = SimulationLimits(drain_limit_seconds=current.common_parameters.drain_limit_seconds)
        base_result = run_simulation(
            city_id=current.common_parameters.city_id,
            window_id=current.common_parameters.window_id,
            seed=current.common_parameters.seed,
            inputs=inputs,
            limits=limits,
        )
        scenario = "intervention"
        intervention_result = run_simulation(
            city_id=current.common_parameters.city_id,
            window_id=current.common_parameters.window_id,
            seed=current.common_parameters.seed,
            inputs=inputs,
            limits=limits,
            signal_timing_intervention=current.intervention,
        )
        _assert_paired_results(base_result, intervention_result, current.common_parameters)
        intervention_warnings = list(intervention_result.warnings)
        route_exposure = _has_route_exposure(inputs, current.intervention, base_result)
        if route_exposure == "not_exposed":
            intervention_warnings.append(
                f"Nenhuma rota solicitada atravessa '{current.intervention.node_id}'; "
                "os deltas não medem efeito dessa intervenção sobre o tráfego nesta janela."
            )
        elif route_exposure == "unknown":
            intervention_warnings.append(
                "Não foi possível verificar se as rotas solicitadas atravessam a intervenção; "
                "os deltas não podem ser interpretados como efeito confirmado sobre o tráfego."
            )
        updated = current.model_copy(update={
            "status": "succeeded",
            "base_result": _result_identity(base_result),
            "intervention_result": _result_identity(intervention_result),
            "route_exposure": route_exposure,
            "base_metrics": _api_metrics(base_result),
            "intervention_metrics": _api_metrics(intervention_result),
            "deltas": _metric_deltas(base_result.metrics, intervention_result.metrics),
            "base_warnings": list(base_result.warnings),
            "intervention_warnings": intervention_warnings,
            "error": None,
        })
    except SimulationError as exc:
        updated = current.model_copy(update={
            "status": "failed",
            "base_result": _result_identity(base_result) if base_result else None,
            "intervention_result": _result_identity(intervention_result) if intervention_result else None,
            "base_metrics": None,
            "intervention_metrics": None,
            "deltas": None,
            "base_warnings": list(base_result.warnings) if base_result else [],
            "intervention_warnings": list(intervention_result.warnings) if intervention_result else [],
            "error": ComparisonFailure(code=exc.code, scenario=scenario, message=str(exc)),
        })
    except Exception:
        updated = current.model_copy(update={
            "status": "failed",
            "base_result": _result_identity(base_result) if base_result else None,
            "intervention_result": _result_identity(intervention_result) if intervention_result else None,
            "base_metrics": None,
            "intervention_metrics": None,
            "deltas": None,
            "base_warnings": list(base_result.warnings) if base_result else [],
            "intervention_warnings": list(intervention_result.warnings) if intervention_result else [],
            "error": ComparisonFailure(
                code="comparison_failed",
                scenario=scenario,
                message="A comparação falhou por um erro interno; métricas parciais não foram publicadas.",
            ),
        })
    with _jobs_lock:
        _comparisons[comparison_id] = updated
        _comparison_inputs.pop(comparison_id, None)


def _assert_paired_results(base: SimulationResult, intervention: SimulationResult, common: ComparisonCommonParameters) -> None:
    common_base = (base.city_id, base.snapshot_id, base.snapshot_hash, base.window_id, base.seed, base.engine_version)
    common_intervention = (intervention.city_id, intervention.snapshot_id, intervention.snapshot_hash, intervention.window_id, intervention.seed, intervention.engine_version)
    expected = (common.city_id, common.snapshot_id, common.snapshot_hash, common.window_id, common.seed, base.engine_version)
    if common_base != common_intervention or common_base != expected:
        raise SimulationError("comparison_pair_mismatch", "Os resultados não compartilham snapshot, janela, semente e versão do motor.")
    if base.metrics.trips_requested != intervention.metrics.trips_requested or base.metrics.trips_requested != common.trips_requested:
        raise SimulationError("comparison_pair_mismatch", "A demanda solicitada divergiu entre os cenários.")


def _api_metrics(result: SimulationResult) -> SimulationMetrics:
    return SimulationMetrics(**result.metrics.model_dump())


def _result_identity(result: SimulationResult) -> ComparisonResultIdentity:
    return ComparisonResultIdentity(
        simulation_id=result.simulation_id,
        engine=result.engine,
        engine_version=result.engine_version,
    )


def _has_route_exposure(
    inputs: SimulationInput,
    intervention: SignalTimingIntervention,
    result: SimulationResult,
) -> RouteExposure:
    if intervention.node_id not in {node.id for node in inputs.nodes}:
        return "unknown"
    try:
        routes = ET.parse(result.artifacts.routes_file).getroot()
    except (OSError, ET.ParseError, TypeError, ValueError):
        return "unknown"
    if routes.tag != "routes":
        return "unknown"

    trips_by_id = {trip.id: trip for trip in inputs.trips}
    vehicles = routes.findall("vehicle")
    if len(vehicles) != len(trips_by_id):
        return "unknown"
    encoded_edges = {sumo_identifier(edge.id): edge for edge in inputs.edges}
    verified_trip_ids: set[str] = set()
    exposure = False
    for vehicle in vehicles:
        vehicle_id = vehicle.get("id")
        trip = trips_by_id.get(vehicle_id or "")
        route_elements = vehicle.findall("route")
        if trip is None or vehicle_id in verified_trip_ids or len(route_elements) != 1:
            return "unknown"
        route_tokens = (route_elements[0].get("edges") or "").split()
        route_edges = [encoded_edges.get(token) for token in route_tokens]
        if not route_tokens or any(edge is None for edge in route_edges):
            return "unknown"
        concrete_edges = [edge for edge in route_edges if edge is not None]
        if concrete_edges[0].id != trip.from_edge or concrete_edges[-1].id != trip.to_edge:
            return "unknown"
        if any(left.to_node != right.from_node for left, right in zip(concrete_edges, concrete_edges[1:])):
            return "unknown"
        verified_trip_ids.add(vehicle_id)
        if any(
            incoming.to_node == intervention.node_id and outgoing.from_node == intervention.node_id
            for incoming, outgoing in zip(concrete_edges, concrete_edges[1:])
        ):
            exposure = True
    if verified_trip_ids != set(trips_by_id):
        return "unknown"
    return "exposed" if exposure else "not_exposed"


def _metric_deltas(base: SimulationMetrics, intervention: SimulationMetrics) -> SimulationMetricDeltas:
    def delta(first: float | int | None, second: float | int | None) -> float | None:
        return None if first is None or second is None else second - first

    return SimulationMetricDeltas(**{
        name: delta(getattr(base, name), getattr(intervention, name))
        for name in SimulationMetrics.model_fields
    })


def run_job(simulation_id: str) -> None:
    with _jobs_lock:
        current = _jobs.get(simulation_id)
        if current is None:
            return
        _jobs[simulation_id] = current.model_copy(update={"status": "running"})

    try:
        result = run_simulation(
            city_id=current.city_id,
            window_id=current.window_id,
            seed=current.seed,
            limits=SimulationLimits(drain_limit_seconds=current.drain_limit_seconds),
        )
        updated = current.model_copy(update={
            "status": "succeeded",
            "snapshot_id": result.snapshot_id,
            "engine_version": result.engine_version,
            "metrics": SimulationMetrics(
                trips_requested=result.metrics.trips_requested,
                trips_completed=result.metrics.trips_completed,
                trips_not_completed=result.metrics.trips_not_completed,
                mean_travel_time_seconds=result.metrics.mean_travel_time_seconds,
                mean_speed_kmh=result.metrics.mean_speed_kmh,
                mean_queue_length_meters=result.metrics.mean_queue_length_meters,
            ),
            "warnings": list(result.warnings),
            "error": None,
        })
    except SimulationError as exc:
        updated = current.model_copy(update={
            "status": "failed",
            "engine_version": "unavailable" if exc.code == "sumo_unavailable" else "unknown",
            "metrics": None,
            "error": SimulationFailure(code=exc.code, message=str(exc)),
        })
    except Exception:
        updated = current.model_copy(update={
            "status": "failed",
            "engine_version": "unknown",
            "metrics": None,
            "error": SimulationFailure(
                code="simulation_failed",
                message="A execução falhou por um erro interno.",
            ),
        })

    with _jobs_lock:
        _jobs[simulation_id] = updated
