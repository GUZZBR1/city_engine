"""Process-local simulation jobs for the local MVP."""

from __future__ import annotations

import hashlib
import json
import xml.etree.ElementTree as ET
from threading import RLock
from typing import Literal
from uuid import uuid4

from simulation import (
    SimulationError,
    SimulationInput,
    SimulationLimits,
    SimulationResult,
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
)


class SimulationNotFoundError(LookupError):
    pass


class UnknownSimulationWindowError(ValueError):
    pass


_jobs: dict[str, SimulationJob] = {}
_comparisons: dict[str, SimulationComparison] = {}
_comparison_inputs: dict[str, SimulationInput] = {}
_jobs_lock = RLock()

RouteExposure = Literal["exposed", "not_exposed", "unknown"]


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
