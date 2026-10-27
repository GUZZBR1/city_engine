"""Public Python entry point used by local callers and the API package."""

from __future__ import annotations

from collections import deque
from typing import Any

from .models import (
    RequestedTrip,
    RoadEdge,
    RoadNode,
    SimulationEngine,
    SimulationError,
    SimulationInput,
    SimulationLimits,
    SimulationResult,
    SimulationWindow,
    SignalTimingIntervention,
    SignalPhase,
    TrafficSignal,
)
from .sumo import SumoEngine


def run_simulation(
    city_id: str = "aurora-base-v1",
    window_id: str = "weekday_am_peak",
    seed: int = 42,
    *,
    inputs: SimulationInput | None = None,
    engine: SimulationEngine | None = None,
    limits: SimulationLimits | None = None,
    signal_timing_intervention: SignalTimingIntervention | None = None,
) -> SimulationResult:
    """Run one simulation without FastAPI; this is the package's stable call surface.

    When inputs are omitted, the city snapshot is loaded through ``urban_arena``'s
    public function. No network or demand values are generated in this package.
    """
    if inputs is None:
        inputs = load_aurora_input(city_id, window_id)
    if inputs.city_id != city_id:
        raise SimulationError("invalid_input", f"O contrato pertence a '{inputs.city_id}', não a '{city_id}'.")
    if signal_timing_intervention is not None:
        inputs = apply_signal_timing_intervention(inputs, signal_timing_intervention)
    return (engine or SumoEngine()).run(inputs, seed=seed, limits=limits)


def apply_signal_timing_intervention(
    inputs: SimulationInput,
    intervention: SignalTimingIntervention,
) -> SimulationInput:
    """Return a copy changing only declared phase durations on one signal."""
    if intervention.node_id not in {node.id for node in inputs.nodes}:
        raise SimulationError("invalid_scenario", f"Nó '{intervention.node_id}' não existe no snapshot.")
    signal_index = next((i for i, signal in enumerate(inputs.traffic_signals) if signal.node_id == intervention.node_id), None)
    if signal_index is None:
        raise SimulationError("invalid_scenario", f"O nó '{intervention.node_id}' não possui controlador semafórico.")

    signal = inputs.traffic_signals[signal_index]
    expected_order = ("north_south", "all_red", "east_west", "all_red")
    if tuple(phase.movement for phase in intervention.phases) != expected_order:
        raise SimulationError("invalid_scenario", "As fases devem seguir a ordem norte-sul, todos vermelhos, leste-oeste, todos vermelhos.")
    if tuple(phase.movement for phase in signal.phases) != expected_order:
        raise SimulationError("invalid_scenario", f"O programa-base de '{intervention.node_id}' não corresponde à ordem de fases esperada.")
    base_cycle = sum(phase.duration_seconds for phase in signal.phases)
    if sum(phase.duration_seconds for phase in intervention.phases) != base_cycle:
        raise SimulationError("invalid_scenario", f"A intervenção deve preservar o ciclo total de {base_cycle} segundos.")

    changed_signal = signal.model_copy(update={
        "phases": tuple(
            SignalPhase(movement=base_phase.movement, duration_seconds=override.duration_seconds)
            for base_phase, override in zip(signal.phases, intervention.phases, strict=True)
        ),
    })
    signals = list(inputs.traffic_signals)
    signals[signal_index] = changed_signal
    return inputs.model_copy(update={"traffic_signals": tuple(signals)})


def load_aurora_input(city_id: str, window_id: str) -> SimulationInput:
    """Adapt the public city contract, including OD rates, to engine trips."""
    if city_id != "aurora-base-v1":
        raise SimulationError("unknown_city", f"Cidade não suportada: '{city_id}'.")
    try:
        from urban_arena import build_simulation_input, load_aurora_snapshot
    except ImportError as exc:
        raise SimulationError("city_contract_unavailable", "Instale packages/urban_arena para carregar o snapshot público.") from exc
    config, snapshot = load_aurora_snapshot()
    try:
        public_input = build_simulation_input(config, snapshot, window_id)
        nodes = tuple(RoadNode(id=node.id, x_m=node.x_m, y_m=node.y_m) for node in public_input.nodes)
        edges = tuple(
            RoadEdge(
                id=road.id,
                from_node=road.from_node,
                to_node=road.to_node,
                speed_mps=road.speed_limit_kmh / 3.6,
                lane_count=road.lanes,
            )
            for road in public_input.roads
        )
        traffic_signals = tuple(
            TrafficSignal(
                node_id=signal.node_id,
                program_id=signal.program_id,
                offset_seconds=signal.offset_seconds,
                initial_phase_index=signal.initial_phase_index,
                phases=tuple(
                    SignalPhase(movement=phase.movement, duration_seconds=phase.duration_s)
                    for phase in signal.phases
                ),
            )
            for signal in public_input.traffic_signals
        )
        trips = _expand_od_flows(public_input, edges)
        return SimulationInput(
            city_id=public_input.city_id,
            snapshot_id=snapshot.snapshot_id,
            snapshot_hash=snapshot.hash,
            city_schema_version=snapshot.schema_version,
            city_generator_version=snapshot.generator_version,
            provenance=snapshot.provenance,
            window=SimulationWindow(
                id=public_input.window.id,
                start=public_input.window.start,
                end=public_input.window.end,
            ),
            nodes=nodes,
            edges=edges,
            traffic_signals=traffic_signals,
            trips=trips,
            warnings=(),
        )
    except (ValueError, TypeError, StopIteration) as exc:
        raise SimulationError("invalid_input_contract", f"Contrato de rede/demanda de Aurora inválido: {exc}") from exc


def _expand_od_flows(public_input: Any, edges: tuple[RoadEdge, ...]) -> tuple[RequestedTrip, ...]:
    """Convert fixed hourly OD rates to evenly spaced vehicles in the window."""
    outgoing: dict[str, list[RoadEdge]] = {}
    for edge in edges:
        outgoing.setdefault(edge.from_node, []).append(edge)
    for items in outgoing.values():
        items.sort(key=lambda edge: edge.id)

    expanded: list[RequestedTrip] = []
    duration = public_input.window.duration_seconds
    for flow in public_input.demand:
        route = _node_path_edges(flow.from_node, flow.to_node, outgoing)
        if not route:
            raise ValueError(f"A demanda '{flow.id}' não tem caminho direcionado.")
        count = round(flow.rate_vehicles_per_hour * duration / 3600)
        for index in range(count):
            departure = (index + 1) * duration / (count + 1)
            expanded.append(RequestedTrip(
                id=f"{flow.id}-trip-{index + 1:05d}",
                from_edge=route[0],
                to_edge=route[-1],
                departure_seconds=departure,
            ))
    return tuple(expanded)


def _node_path_edges(
    start: str,
    destination: str,
    outgoing: dict[str, list[RoadEdge]],
) -> list[str] | None:
    parents: dict[str, tuple[str, str] | None] = {start: None}
    pending = deque([start])
    while pending:
        node = pending.popleft()
        if node == destination:
            break
        for edge in outgoing.get(node, []):
            if edge.to_node not in parents:
                parents[edge.to_node] = (node, edge.id)
                pending.append(edge.to_node)
    if destination not in parents:
        return None
    path: list[str] = []
    node = destination
    while (parent := parents[node]) is not None:
        previous, edge_id = parent
        path.append(edge_id)
        node = previous
    path.reverse()
    return path
