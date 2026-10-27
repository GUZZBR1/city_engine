"""Isolated SUMO command-line adapter. No SUMO import is needed to import this package."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import time
import xml.etree.ElementTree as ET
from pathlib import Path

from .compiler import compile_sumo_inputs, sumo_identifier
from .models import (
    ArtifactReferences,
    SimulationError,
    SimulationInput,
    SimulationLimits,
    SimulationMetrics,
    SimulationResult,
)


class SumoEngine:
    engine_name = "sumo"

    def __init__(self, *, sumo_binary: str = "sumo", netconvert_binary: str = "netconvert"):
        self.sumo_binary = sumo_binary
        self.netconvert_binary = netconvert_binary

    def run(
        self,
        inputs: SimulationInput,
        *,
        seed: int,
        limits: SimulationLimits | None = None,
    ) -> SimulationResult:
        limits = limits or SimulationLimits()
        if seed < 0:
            raise SimulationError("invalid_seed", "A semente deve ser um inteiro não negativo.")
        if not inputs.trips:
            raise SimulationError("missing_demand", "A demanda OD da janela está vazia; o motor não cria viagens.")
        sumo = shutil.which(self.sumo_binary)
        netconvert = shutil.which(self.netconvert_binary)
        if not sumo or not netconvert:
            missing = [name for name, path in ((self.sumo_binary, sumo), (self.netconvert_binary, netconvert)) if not path]
            raise SimulationError("sumo_unavailable", "Executáveis SUMO ausentes: " + ", ".join(missing))

        deadline = time.monotonic() + limits.wall_timeout_seconds
        version_text = self._execute([sumo, "--version"], timeout=_remaining(deadline, "sumo_version"), stage="sumo_version")
        engine_version = _version(version_text)

        root = Path(limits.output_directory) if limits.output_directory else Path(tempfile.mkdtemp(prefix="aurora-simulation-"))
        root.mkdir(parents=True, exist_ok=True)
        identity = hashlib.sha256(json.dumps({
            "snapshot": inputs.snapshot_id,
            "window": inputs.window.id,
            "seed": seed,
            "engine_version": engine_version,
            "input": inputs.model_dump(mode="json"),
        }, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:20]
        run_dir = root / identity
        run_dir.mkdir(parents=True, exist_ok=True)

        node_file, edge_file, route_file = compile_sumo_inputs(inputs, run_dir, limits)
        net_file = run_dir / "aurora.net.xml"
        self._execute(
            [netconvert, "--node-files", str(node_file), "--edge-files", str(edge_file), "--tls.guess-signals", "--output-file", str(net_file)],
            timeout=_remaining(deadline, "netconvert"),
            stage="netconvert",
        )
        if inputs.traffic_signals:
            _apply_signal_programs(net_file, inputs)
            _verify_signal_programs(net_file, inputs)

        tripinfo = run_dir / "tripinfo.xml"
        queue = run_dir / "queue.xml"
        # Each configured city window runs on its own relative clock. Trip
        # departures from the input contract are offsets from window start.
        demand_end = inputs.window.duration_seconds
        end = demand_end + limits.drain_limit_seconds
        self._execute([
            sumo,
            "--net-file", str(net_file),
            "--route-files", str(route_file),
            "--begin", "0",
            "--end", str(end),
            "--seed", str(seed),
            "--tripinfo-output", str(tripinfo),
            "--queue-output", str(queue),
        ], timeout=_remaining(deadline, "sumo"), stage="sumo")

        completed = _tripinfo_metrics(tripinfo)
        if completed["count"] > len(inputs.trips):
            raise SimulationError("invalid_sumo_output", "SUMO reportou mais viagens concluídas do que foram solicitadas.")
        not_completed = len(inputs.trips) - completed["count"]
        queue_mean = _mean_queue_length(queue, through_seconds=demand_end)
        warnings: list[str] = list(inputs.warnings)
        if not_completed:
            warnings.append(f"{not_completed} viagem(ns) solicitada(s) não concluíram até o limite de escoamento de {limits.drain_limit_seconds} s.")
        if queue_mean is None:
            warnings.append("SUMO não produziu amostras de fila legíveis; a métrica de fila está indisponível.")
        return SimulationResult(
            simulation_id=identity,
            city_id=inputs.city_id,
            snapshot_id=inputs.snapshot_id,
            snapshot_hash=inputs.snapshot_hash,
            city_schema_version=inputs.city_schema_version,
            city_generator_version=inputs.city_generator_version,
            window_id=inputs.window.id,
            seed=seed,
            engine=self.engine_name,
            engine_version=engine_version,
            metrics=SimulationMetrics(
                trips_requested=len(inputs.trips),
                trips_completed=completed["count"],
                trips_not_completed=not_completed,
                mean_travel_time_seconds=completed["mean_duration"],
                mean_speed_kmh=completed["mean_speed_kmh"],
                mean_queue_length_meters=queue_mean,
            ),
            metric_methods={
                "trips_requested": "Count of vehicles expanded from synthetic OD hourly rates within the demand window, rounded and evenly spaced by the adapter.",
                "trips_completed": "Count of SUMO tripinfo arrival records through the end of the drain period (demand-window duration plus configured drain limit).",
                "trips_not_completed": "Requested trips without a SUMO arrival record by the end of the drain period; equals trips_requested minus trips_completed.",
                "mean_travel_time_seconds": "Arithmetic mean of SUMO tripinfo duration for trips completed by the end of the drain period; null when none complete.",
                "mean_speed_kmh": "Distance-weighted mean for trips completed by the end of the drain period: total SUMO tripinfo routeLength divided by total duration, converted from m/s to km/h; null when none complete or total time is zero.",
                "mean_queue_length_meters": "Mean, over queue-output timesteps from the demand window only, of summed lane queueing_length in meters. SUMO default queued-vehicle threshold is 1.39 m/s.",
            },
            warnings=tuple(warnings),
            artifacts=ArtifactReferences(
                network_file=str(net_file),
                routes_file=str(route_file),
                tripinfo_file=str(tripinfo),
                queue_file=str(queue),
            ),
        )

    @staticmethod
    def _execute(command: list[str], *, timeout: float, stage: str) -> str:
        try:
            completed = subprocess.run(command, check=False, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            raise SimulationError("timeout", f"Tempo limite excedido durante {stage} ({timeout:g}s).") from exc
        except OSError as exc:
            raise SimulationError("sumo_execution_error", f"Não foi possível executar {stage}: {exc}") from exc
        if completed.returncode:
            detail = (completed.stderr or completed.stdout).strip().splitlines()
            summary = detail[-1][:500] if detail else "sem detalhes"
            raise SimulationError("sumo_execution_error", f"{stage} terminou com código {completed.returncode}: {summary}")
        return completed.stdout + "\n" + completed.stderr


def _version(output: str) -> str:
    match = re.search(r"\bsumo\s+([0-9]+(?:\.[0-9A-Za-z_-]+)+)", output, re.IGNORECASE)
    if not match:
        match = re.search(r"\bVersion\s+([0-9]+(?:\.[0-9A-Za-z_-]+)+)", output, re.IGNORECASE)
    if not match:
        raise SimulationError("sumo_execution_error", "Não foi possível identificar a versão do SUMO.")
    return match.group(1)


def _remaining(deadline: float, stage: str) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise SimulationError("timeout", f"Tempo limite excedido antes de iniciar {stage}.")
    return remaining


def _tripinfo_metrics(path: Path) -> dict[str, float | int | None]:
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError) as exc:
        raise SimulationError("invalid_sumo_output", f"Saída tripinfo inválida: {exc}") from exc
    trips = root.findall("tripinfo")
    if not trips:
        return {"count": 0, "mean_duration": None, "mean_speed_kmh": None}
    durations: list[float] = []
    distances: list[float] = []
    for trip in trips:
        try:
            durations.append(float(trip.attrib["duration"]))
            distances.append(float(trip.attrib["routeLength"]))
        except (KeyError, ValueError) as exc:
            raise SimulationError("invalid_sumo_output", "tripinfo não contém duration/routeLength numéricos.") from exc
    total_duration = sum(durations)
    return {
        "count": len(trips),
        "mean_duration": sum(durations) / len(durations),
        "mean_speed_kmh": (sum(distances) / total_duration * 3.6) if total_duration > 0 else None,
    }


def _mean_queue_length(path: Path, *, through_seconds: int) -> float | None:
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError):
        return None
    samples: list[float] = []
    for step in root.findall("data"):
        try:
            sample_time = step.attrib.get("begin", step.attrib.get("timestep"))
            if sample_time is not None and float(sample_time) >= through_seconds:
                continue
        except (KeyError, ValueError):
            pass
        lane_values = [float(lane.attrib["queueing_length"]) for lane in step.findall("./lanes/lane") if "queueing_length" in lane.attrib]
        samples.append(sum(lane_values))
    return sum(samples) / len(samples) if samples else None


def _apply_signal_programs(net_file: Path, inputs: SimulationInput) -> None:
    """Attach YAML plans to netconvert's actual controlled-link ordering."""
    tree = ET.parse(net_file)
    root = tree.getroot()
    coordinates = {node.id: (node.x_m, node.y_m) for node in inputs.nodes}
    edges = {sumo_identifier(edge.id): edge for edge in inputs.edges}
    signal_ids = {signal.node_id: sumo_identifier(signal.node_id) for signal in inputs.traffic_signals}
    for signal in inputs.traffic_signals:
        signal_id = signal_ids[signal.node_id]
        controlled: dict[int, str] = {}
        for connection in root.findall("connection"):
            if connection.get("tl") != signal_id:
                continue
            try:
                index = int(connection.attrib["linkIndex"])
                edge = edges[connection.attrib["from"]]
                start, end = coordinates[edge.from_node], coordinates[edge.to_node]
            except (KeyError, ValueError) as exc:
                raise SimulationError("invalid_sumo_network", f"Conexão semafórica inválida no nó '{signal.node_id}'.") from exc
            axis = "north_south" if abs(end[1] - start[1]) >= abs(end[0] - start[0]) else "east_west"
            controlled[index] = axis
        if not controlled or sorted(controlled) != list(range(max(controlled) + 1)):
            raise SimulationError("invalid_sumo_network", f"SUMO não gerou índices contíguos de links para '{signal.node_id}'.")

        if not any(item.get("id") == signal_id for item in root.findall("junction")):
            raise SimulationError("invalid_sumo_network", f"Cruzamento semaforizado '{signal.node_id}' não existe na rede compilada.")
        for logic in list(root.findall("tlLogic")):
            if logic.get("id") == signal_id:
                root.remove(logic)
        logic = ET.Element("tlLogic", {
            "id": signal_id,
            "type": "static",
            "programID": signal.program_id,
            "offset": str(signal.offset_seconds),
        })
        phases = signal.phases
        if not phases or signal.initial_phase_index >= len(phases):
            raise SimulationError("invalid_signal_plan", f"Fase inicial inválida no nó '{signal.node_id}'.")
        ordered = phases[signal.initial_phase_index:] + phases[:signal.initial_phase_index]
        for phase in ordered:
            state = "".join(
                "G" if phase.movement != "all_red" and axis == phase.movement else "r"
                for _, axis in sorted(controlled.items())
            )
            ET.SubElement(logic, "phase", {"duration": str(phase.duration_seconds), "state": state})
        junction_index = next(index for index, item in enumerate(root) if item.tag == "junction")
        root.insert(junction_index, logic)

    ET.indent(root, space="  ")
    tree.write(net_file, encoding="utf-8", xml_declaration=True)


def _verify_signal_programs(net_file: Path, inputs: SimulationInput) -> None:
    root = ET.parse(net_file).getroot()
    for signal in inputs.traffic_signals:
        signal_id = sumo_identifier(signal.node_id)
        logic = next((item for item in root.findall("tlLogic") if item.get("id") == signal_id and item.get("programID") == signal.program_id), None)
        connections = [item for item in root.findall("connection") if item.get("tl") == signal_id]
        phases = [] if logic is None else logic.findall("phase")
        if not connections or logic is None or len(phases) != len(signal.phases):
            raise SimulationError("invalid_sumo_network", f"Controlador '{signal.node_id}' ausente ou incompleto na rede compilada.")
        link_count = max(int(item.attrib["linkIndex"]) for item in connections) + 1
        if any(len(phase.get("state", "")) != link_count for phase in phases):
            raise SimulationError("invalid_sumo_network", f"Fase semafórica tem estado incompatível com links em '{signal.node_id}'.")
        if [int(phase.attrib["duration"]) for phase in phases] != [phase.duration_seconds for phase in signal.phases[signal.initial_phase_index:] + signal.phases[:signal.initial_phase_index]]:
            raise SimulationError("invalid_sumo_network", f"Durações das fases não correspondem ao contrato em '{signal.node_id}'.")
