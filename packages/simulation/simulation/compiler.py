"""Pure compiler from the public city snapshot projection to SUMO XML."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from collections import defaultdict, deque
from pathlib import Path

from .models import SimulationError, SimulationInput, SimulationLimits


def sumo_identifier(value: str) -> str:
    """SUMO IDs exclude separators used by the public city contract."""
    safe = "".join(character if character.isalnum() or character in "_.-" else "_" for character in value)
    return f"id_{safe}"


def compile_sumo_inputs(
    inputs: SimulationInput, directory: str | Path, limits: SimulationLimits
) -> tuple[Path, Path]:
    if not inputs.nodes or not inputs.edges:
        raise SimulationError("invalid_network", "A rede de entrada não contém nós e arestas.")
    if len(inputs.trips) > limits.max_requested_trips:
        raise SimulationError("input_limit_exceeded", "A demanda excede max_requested_trips.")
    if inputs.window.duration_seconds > limits.max_window_seconds:
        raise SimulationError("input_limit_exceeded", "A janela excede max_window_seconds.")
    if any(trip.departure_seconds >= inputs.window.duration_seconds for trip in inputs.trips):
        raise SimulationError("invalid_demand", "Há partida fora da janela de simulação.")

    node_ids = {node.id for node in inputs.nodes}
    signal_nodes = {signal.node_id for signal in inputs.traffic_signals}
    if signal_nodes - node_ids:
        raise SimulationError("invalid_network", "Um controlador semafórico referencia nó ausente.")
    edge_ids = {edge.id for edge in inputs.edges}
    for edge in inputs.edges:
        if edge.from_node not in node_ids or edge.to_node not in node_ids:
            raise SimulationError("invalid_network", f"A aresta '{edge.id}' referencia nó ausente.")
    for trip in inputs.trips:
        if trip.from_edge not in edge_ids or trip.to_edge not in edge_ids:
            raise SimulationError("invalid_demand", f"A viagem '{trip.id}' referencia aresta ausente.")

    out = Path(directory)
    out.mkdir(parents=True, exist_ok=True)
    node_file, edge_file, route_file = out / "aurora.nod.xml", out / "aurora.edg.xml", out / "aurora.rou.xml"

    nodes = ET.Element("nodes")
    for node in sorted(inputs.nodes, key=lambda item: item.id):
        attributes = {"id": node.id, "x": _number(node.x_m), "y": _number(node.y_m)}
        if node.id in signal_nodes:
            attributes["type"] = "traffic_light"
        attributes["id"] = sumo_identifier(node.id)
        ET.SubElement(nodes, "node", attributes)
    _write_xml(node_file, nodes)

    edges = ET.Element("edges")
    for edge in sorted(inputs.edges, key=lambda item: item.id):
        ET.SubElement(edges, "edge", {
            "id": sumo_identifier(edge.id),
            "from": sumo_identifier(edge.from_node),
            "to": sumo_identifier(edge.to_node),
            "numLanes": str(edge.lane_count),
            "speed": _number(edge.speed_mps),
        })
    _write_xml(edge_file, edges)

    edge_map = {edge.id: edge for edge in inputs.edges}
    graph: dict[str, list[str]] = defaultdict(list)
    for edge in inputs.edges:
        graph[edge.from_node].append(edge.id)
    for edge_list in graph.values():
        edge_list.sort()

    routes = ET.Element("routes")
    ET.SubElement(routes, "vType", {"id": "default", "accel": "2.6", "decel": "4.5", "length": "5", "maxSpeed": _number(max(e.speed_mps for e in inputs.edges))})
    for trip in sorted(inputs.trips, key=lambda item: (item.departure_seconds, item.id)):
        path = _edge_path(edge_map, graph, trip.from_edge, trip.to_edge)
        if path is None:
            raise SimulationError("invalid_demand", f"Não há caminho entre as arestas da viagem '{trip.id}'.")
        vehicle = ET.SubElement(routes, "vehicle", {
            "id": trip.id,
            "type": "default",
            "depart": _number(trip.departure_seconds),
        })
        ET.SubElement(vehicle, "route", {"edges": " ".join(sumo_identifier(edge_id) for edge_id in path)})
    _write_xml(route_file, routes)
    return node_file, edge_file, route_file


def _edge_path(edge_map, graph, first: str, last: str) -> list[str] | None:
    if first == last:
        return [first]
    first_edge, last_edge = edge_map[first], edge_map[last]
    todo = deque([(first_edge.to_node, [first])])
    visited = {first_edge.to_node}
    while todo:
        node, path = todo.popleft()
        if node == last_edge.from_node:
            return [*path, last]
        for edge_id in graph.get(node, ()):
            edge = edge_map[edge_id]
            if edge.to_node not in visited:
                visited.add(edge.to_node)
                todo.append((edge.to_node, [*path, edge_id]))
    return None


def _number(value: float) -> str:
    return format(value, ".12g")


def _write_xml(path: Path, root: ET.Element) -> None:
    ET.indent(root, space="  ")
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)
