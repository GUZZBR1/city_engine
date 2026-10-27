"""SUMO evaluation adapter for annual Arena signal timing actions.

The evidence is scoped to one configured simulation window. It is deliberately
kept out of annual city indicators and state transitions.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from itertools import pairwise
from typing import Any

from simulation import run_simulation
from simulation.compiler import sumo_identifier
from simulation.models import (
    SignalTimingIntervention,
    SignalTimingPhase,
    SimulationEngine,
    SimulationInput,
    SimulationLimits,
)
from urban_arena.actions import (
    ActionExecutionEvidence,
    ActionProposal,
    ArbitrationContext,
)
from urban_arena.observations import Observation


class ArenaSignalSumoEvaluator:
    """Run a paired, same-input SUMO comparison for accepted signal actions."""

    def __init__(
        self,
        inputs: SimulationInput,
        *,
        seed: int = 42,
        limits: SimulationLimits | None = None,
        engine: SimulationEngine | None = None,
    ) -> None:
        self.inputs = inputs
        self.seed = seed
        self.limits = limits
        self.engine = engine
        self._baseline = None

    def __call__(
        self,
        proposal: ActionProposal,
        observation: Observation,
        context: ArbitrationContext,
    ) -> ActionExecutionEvidence:
        if observation.state_view.get("snapshot_hash") != self.inputs.snapshot_hash:
            raise ValueError("entrada SUMO não corresponde ao snapshot da observação")
        if context.observed_city_state_hash != observation.city_state_hash:
            raise ValueError("contexto SUMO não corresponde à observação congelada")

        actions = tuple(
            action for action in proposal.actions if action.action_type == "signal_timing_change"
        )
        if not actions or len(actions) != len(proposal.actions):
            raise ValueError("o executor SUMO aceita somente ações semafóricas")
        interventions = tuple(
            SignalTimingIntervention(
                node_id=action.target_id,
                phases=tuple(
                    SignalTimingPhase(
                        movement=phase.movement,
                        duration_seconds=phase.duration_s,
                    )
                    for phase in action.parameters.phases
                ),
            )
            for action in actions
        )

        if self._baseline is None:
            self._baseline = run_simulation(
                city_id=self.inputs.city_id,
                window_id=self.inputs.window.id,
                seed=self.seed,
                inputs=self.inputs,
                engine=self.engine,
                limits=self.limits,
            )
        intervention = run_simulation(
            city_id=self.inputs.city_id,
            window_id=self.inputs.window.id,
            seed=self.seed,
            inputs=self.inputs,
            engine=self.engine,
            limits=self.limits,
            signal_timing_interventions=interventions,
        )

        baseline_metrics = _metric_payload(self._baseline)
        intervention_metrics = _metric_payload(intervention)
        route_exposure = _route_exposure(
            self.inputs,
            self._baseline.artifacts.routes_file,
            {action.target_id for action in actions},
        )
        deltas = {
            key: (
                intervention_metrics[key] - baseline_metrics[key]
                if baseline_metrics[key] is not None and intervention_metrics[key] is not None
                else None
            )
            for key in baseline_metrics
        }
        limitations = [
            "Aurora e a demanda são sintéticas; esta comparação não é observação de tráfego real.",
            "As métricas descrevem somente a janela configurada e não são anualizadas.",
            "As métricas são agregadas para a rede e a janela; exposição confirma rota por nó alterado, não isola o efeito nos veículos expostos.",
        ]
        if route_exposure == "not_exposed":
            limitations.append("Nenhuma rota solicitada atravessa os controladores alterados nesta janela; os deltas não medem efeito sobre veículos expostos.")
        elif route_exposure == "unknown":
            limitations.append("A exposição das rotas aos controladores alterados não pôde ser verificada; os deltas têm efeito indeterminado.")
        return ActionExecutionEvidence(
            executor_id="sumo-arena-signal-v1",
            evidence_type="paired_sumo_window_comparison",
            action_ids=tuple(action.action_id for action in actions),
            details={
                "scope": "simulation_window",
                "provenance": self.inputs.provenance,
                "city_id": self.inputs.city_id,
                "snapshot_id": self.inputs.snapshot_id,
                "snapshot_hash": self.inputs.snapshot_hash,
                "window_id": self.inputs.window.id,
                "route_exposure": route_exposure,
                "seed": self.seed,
                "engine": intervention.engine,
                "engine_version": intervention.engine_version,
                "base_simulation_id": self._baseline.simulation_id,
                "intervention_simulation_id": intervention.simulation_id,
                "base_metrics": baseline_metrics,
                "intervention_metrics": intervention_metrics,
                "deltas": deltas,
                "limitations": limitations,
            },
        )


def _metric_payload(result: Any) -> dict[str, int | float | None]:
    metrics = result.metrics
    return {
        "trips_requested": metrics.trips_requested,
        "trips_completed": metrics.trips_completed,
        "trips_not_completed": metrics.trips_not_completed,
        "mean_travel_time_seconds": metrics.mean_travel_time_seconds,
        "mean_speed_kmh": metrics.mean_speed_kmh,
        "mean_queue_length_meters": metrics.mean_queue_length_meters,
    }


def _route_exposure(
    inputs: SimulationInput,
    routes_file: str,
    target_nodes: set[str],
) -> str:
    """Verify route completeness before classifying whether any target is used."""
    try:
        routes = ET.parse(routes_file).getroot()
    except (OSError, ET.ParseError, TypeError, ValueError):
        return "unknown"
    if routes.tag != "routes":
        return "unknown"

    trips_by_id = {trip.id: trip for trip in inputs.trips}
    vehicles = routes.findall("vehicle")
    if len(vehicles) != len(trips_by_id):
        return "unknown"
    edges_by_id = {sumo_identifier(edge.id): edge for edge in inputs.edges}
    verified: set[str] = set()
    exposed = False
    for vehicle in vehicles:
        vehicle_id = vehicle.get("id")
        trip = trips_by_id.get(vehicle_id or "")
        route_elements = vehicle.findall("route")
        if trip is None or vehicle_id in verified or len(route_elements) != 1:
            return "unknown"
        tokens = (route_elements[0].get("edges") or "").split()
        route_edges = [edges_by_id.get(token) for token in tokens]
        if not tokens or any(edge is None for edge in route_edges):
            return "unknown"
        concrete_edges = [edge for edge in route_edges if edge is not None]
        if concrete_edges[0].id != trip.from_edge or concrete_edges[-1].id != trip.to_edge:
            return "unknown"
        if any(left.to_node != right.from_node for left, right in pairwise(concrete_edges)):
            return "unknown"
        verified.add(vehicle_id)
        if any(
            incoming.to_node in target_nodes and outgoing.from_node in target_nodes
            and incoming.to_node == outgoing.from_node
            for incoming, outgoing in pairwise(concrete_edges)
        ):
            exposed = True
    if verified != set(trips_by_id):
        return "unknown"
    return "exposed" if exposed else "not_exposed"
