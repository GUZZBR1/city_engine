"""Load Aurora's YAML source and generate a deterministic local city snapshot."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from .models import (
    CityConfigFile,
    CitySnapshot,
    LocalFeature,
    LocalFeatureCollection,
    LocalGeometry,
    PopulationTotals,
)

GENERATOR_VERSION = "0.3.0"
DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[3] / "configs/cities/aurora-base-v1.yaml"


class CityConfigError(ValueError):
    """Invalid or unreadable city configuration, with actionable context."""


def load_city_config(path: str | Path = DEFAULT_CONFIG_PATH) -> CityConfigFile:
    config_path = Path(path)
    try:
        with config_path.open("r", encoding="utf-8") as stream:
            raw = yaml.safe_load(stream)
    except OSError as exc:
        raise CityConfigError(f"Não foi possível ler a configuração '{config_path}': {exc}") from exc
    except yaml.YAMLError as exc:
        raise CityConfigError(f"YAML inválido em '{config_path}': {exc}") from exc
    try:
        return CityConfigFile.model_validate(raw)
    except ValidationError as exc:
        details = "; ".join(
            f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
            for error in exc.errors()
        )
        raise CityConfigError(f"Configuração de cidade inválida em '{config_path}': {details}") from exc


def _feature_collection(features: list[LocalFeature]) -> LocalFeatureCollection:
    return LocalFeatureCollection(features=sorted(features, key=lambda feature: feature.id))


def _polygon(bounds: tuple[int, int, int, int]) -> LocalGeometry:
    left, bottom, right, top = bounds
    return LocalGeometry(
        type="Polygon",
        coordinates=[[[left, bottom], [right, bottom], [right, top], [left, top], [left, bottom]]],
    )


def _district_features(config: CityConfigFile) -> list[LocalFeature]:
    width_m = round((config.urban_footprint.area_km2**0.5) * 1000)
    half = width_m // 2
    # A five-cell partition follows the YAML's district names while covering the square.
    boxes = {
        "oeste_verde": (0, 0, half - width_m // 6, width_m),
        "centro": (half - width_m // 6, half - width_m // 6, half + width_m // 6, half + width_m // 6),
        "norte_residencial": (half - width_m // 6, half + width_m // 6, half + width_m // 6, width_m),
        "sul_misto": (half - width_m // 6, 0, half + width_m // 6, half - width_m // 6),
        "leste_logistico": (half + width_m // 6, 0, width_m, width_m),
    }
    features: list[LocalFeature] = []
    for district in config.districts:
        common: dict[str, str | int | float | bool | None] = {
            "district_type": district.type,
            "residents": district.residents,
            "jobs": district.jobs,
            "land_use": district.land_use,
            "provenance_kind": "synthetic_generated",
            "synthetic": True,
        }
        if district.type == "urban":
            geometry = _polygon(boxes[district.id])
        else:
            # The catchment is outside the modeled footprint; its point marks the south
            # gateway without inventing an out-of-bounds local territory polygon.
            geometry = LocalGeometry(type="Point", coordinates=[half, 0])
            common["geometry_role"] = "external_zone_gateway_marker"
        features.append(LocalFeature(id=f"district:{district.id}", geometry=geometry, properties=common))
    return features


def _network_features(config: CityConfigFile) -> tuple[list[LocalFeature], list[LocalFeature]]:
    cols, rows = config.mobility.network.grid_intersections
    width_m = round((config.urban_footprint.area_km2**0.5) * 1000)
    xs = [round(index * width_m / (cols - 1)) for index in range(cols)]
    ys = [round(index * width_m / (rows - 1)) for index in range(rows)]
    nodes: list[LocalFeature] = []
    edges: list[LocalFeature] = []
    for row, y in enumerate(ys):
        for col, x in enumerate(xs):
            node_id = f"node:{row:02d}:{col:02d}"
            nodes.append(LocalFeature(
                id=node_id,
                geometry=LocalGeometry(type="Point", coordinates=[x, y]),
                properties={"row": row, "column": col, "provenance_kind": "synthetic_generated", "synthetic": True},
            ))

    # Put the barrier through the center of a grid cell so it separates nodes and
    # crossing links can be identified without changing the configured 5x5 grid.
    barrier_x = (xs[cols // 2 - 1] + xs[cols // 2]) // 2 if config.mobility.network.barrier.orientation == "north_south" else None
    barrier_y = (ys[rows // 2 - 1] + ys[rows // 2]) // 2 if config.mobility.network.barrier.orientation == "east_west" else None
    crossing_rows = [round(i * (rows - 1) / (config.mobility.network.barrier.crossings + 1)) for i in range(1, config.mobility.network.barrier.crossings + 1)]
    crossing_cols = [round(i * (cols - 1) / (config.mobility.network.barrier.crossings + 1)) for i in range(1, config.mobility.network.barrier.crossings + 1)]
    crossing_types = config.mobility.network.barrier.crossing_types

    def add_edge(row_a: int, col_a: int, row_b: int, col_b: int, crossing_type: str | None = None) -> None:
        a_id, b_id = f"node:{row_a:02d}:{col_a:02d}", f"node:{row_b:02d}:{col_b:02d}"
        a_xy, b_xy = [xs[col_a], ys[row_a]], [xs[col_b], ys[row_b]]
        pair = [(a_id, b_id, a_xy, b_xy), (b_id, a_id, b_xy, a_xy)]
        for source, target, start, end in pair:
            edge_id = f"edge:{source.removeprefix('node:')}->{target.removeprefix('node:')}"
            properties: dict[str, str | int | float | bool | None] = {
                "from_node": source,
                "to_node": target,
                "road_class": config.mobility.network.crossing_road_classes.get(
                    crossing_type, config.mobility.network.default_road_class
                ),
                "provenance_kind": "synthetic_generated",
                "synthetic": True,
            }
            road_class = properties["road_class"]
            profile = config.mobility.network.road_classes[road_class]
            properties.update({
                "speed_limit_kmh": profile.speed_limit_kmh,
                "lanes": profile.lanes,
                "capacity_vehicles_per_hour": profile.capacity_vehicles_per_hour,
                "capacity_unit": "vehicles/hour/directed_edge",
            })
            if crossing_type:
                properties["crossing_type"] = crossing_type
                properties["barrier_orientation"] = config.mobility.network.barrier.orientation
            edges.append(LocalFeature(id=edge_id, geometry=LocalGeometry(type="LineString", coordinates=[start, end]), properties=properties))

    for row in range(rows):
        for col in range(cols - 1):
            crossing_type = None
            crosses_barrier = barrier_x is not None and xs[col] < barrier_x < xs[col + 1]
            if crosses_barrier:
                if row not in crossing_rows:
                    continue
                crossing_type = crossing_types[crossing_rows.index(row)]
            add_edge(row, col, row, col + 1, crossing_type)
    for row in range(rows - 1):
        for col in range(cols):
            crossing_type = None
            crosses_barrier = barrier_y is not None and ys[row] < barrier_y < ys[row + 1]
            if crosses_barrier:
                if col not in crossing_cols:
                    continue
                crossing_type = crossing_types[crossing_cols.index(col)]
            add_edge(row, col, row + 1, col, crossing_type)

    if len(edges) != config.mobility.network.directed_edges_derived:
        raise CityConfigError(
            "A grade gerada produziu "
            f"{len(edges)} arestas direcionadas; configuração exige "
            f"{config.mobility.network.directed_edges_derived}."
        )
    return edges, nodes


def _canonical_json(payload: dict[str, Any]) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def generate_snapshot(config: CityConfigFile) -> CitySnapshot:
    """Pure deterministic projection of a validated YAML configuration."""
    district_features = _district_features(config)
    edge_features, node_features = _network_features(config)
    width_m = round((config.urban_footprint.area_km2**0.5) * 1000)
    source_config = config.model_dump(mode="json")
    source_config["districts"] = sorted(source_config["districts"], key=lambda item: item["id"])
    source_config["mobility"]["simulation_windows"] = sorted(
        source_config["mobility"]["simulation_windows"], key=lambda item: item["id"]
    )
    source_config["provenance"]["sources"] = sorted(
        source_config["provenance"]["sources"], key=lambda item: item["id"]
    )
    source_config["arena"]["reference_policies"] = sorted(source_config["arena"]["reference_policies"])
    payload: dict[str, Any] = {
        "city_id": config.city.id,
        "name": config.city.name,
        "schema_version": str(config.schema_version),
        "generator_version": GENERATOR_VERSION,
        "provenance": "synthetic",
        "population": {
            "total": config.population.total_residents,
            "urban": config.population.urban_rural.urban_residents_derived,
            "rural_catchment": config.population.urban_rural.rural_catchment_residents_derived,
        },
        "jobs": config.employment.total_jobs,
        "household": config.population.household.model_dump(mode="json"),
        "finance": config.finance.model_dump(mode="json"),
        "commute_main_mode_share": dict(sorted(
            config.mobility.commute_main_mode_share.model_dump(exclude={"source_scope", "note"}).items()
        )),
        "districts": [
            {**district.model_dump(mode="json"), "provenance_kind": "synthetic_config", "synthetic": True}
            for district in sorted(config.districts, key=lambda item: item.id)
        ],
        "mobility": source_config["mobility"],
        # Keep all source values and reference metadata available to downstream
        # consumers without re-encoding YAML parameters in application code.
        "source_config": source_config,
        "coordinate_space": "synthetic_local_cartesian_m",
        "bounds_m": [0, 0, width_m, width_m],
        "layers": {
            "districts": _feature_collection(district_features).model_dump(mode="json"),
            "edges": _feature_collection(edge_features).model_dump(mode="json"),
            "nodes": _feature_collection(node_features).model_dump(mode="json"),
        },
    }
    digest = hashlib.sha256(_canonical_json(payload)).hexdigest()
    payload["hash"] = digest
    payload["snapshot_id"] = f"{config.city.id}:{digest}"
    return CitySnapshot.model_validate(payload)


def create_agent_copies(snapshot: CitySnapshot, config: CityConfigFile) -> list[CitySnapshot]:
    """Create isolated state copies while retaining their common initial hash."""
    copies = config.arena.ai_agent_copies
    if copies < 1:
        raise ValueError("arena.ai_agent_copies deve ser positivo.")
    return [snapshot.model_copy(deep=True) for _ in range(copies)]


def load_aurora_snapshot(path: str | Path = DEFAULT_CONFIG_PATH) -> tuple[CityConfigFile, CitySnapshot]:
    config = load_city_config(path)
    snapshot = generate_snapshot(config)
    return config, snapshot


def build_simulation_input(
    config: CityConfigFile,
    snapshot: CitySnapshot,
    window_id: str,
    seed: int | None = None,
) -> "SimulationInput":
    """Build the public, versioned engine input without exposing generator internals."""
    from .models import (
        SimulationInput,
        SimulationNodeContract,
        SimulationODFlowContract,
        SimulationRoadContract,
        SimulationSignalContract,
        SimulationWindowContract,
    )

    if snapshot.city_id != config.city.id:
        raise CityConfigError("snapshot e configuração pertencem a cidades diferentes")
    if snapshot.hash != generate_snapshot(config).hash:
        raise CityConfigError("snapshot não corresponde à configuração fornecida")
    window = next((item for item in config.mobility.simulation_windows if item.id == window_id), None)
    if window is None:
        raise CityConfigError(f"Janela de simulação desconhecida: '{window_id}'.")
    demand_window = next(item for item in config.mobility.demand.windows if item.window_id == window_id)
    start_hour, start_minute = (int(part) for part in window.start.split(":"))
    end_hour, end_minute = (int(part) for part in window.end.split(":"))
    duration_seconds = ((end_hour * 60 + end_minute) - (start_hour * 60 + start_minute)) * 60

    nodes = tuple(
        SimulationNodeContract(id=feature.id, x_m=feature.geometry.coordinates[0], y_m=feature.geometry.coordinates[1])
        for feature in snapshot.layers["nodes"].features
    )
    roads = []
    for feature in snapshot.layers["edges"].features:
        properties = feature.properties
        start, end = feature.geometry.coordinates
        length_m = ((end[0] - start[0]) ** 2 + (end[1] - start[1]) ** 2) ** 0.5
        roads.append(SimulationRoadContract(
            id=feature.id,
            from_node=str(properties["from_node"]),
            to_node=str(properties["to_node"]),
            length_m=length_m,
            road_class=properties["road_class"],
            speed_limit_kmh=properties["speed_limit_kmh"],
            lanes=properties["lanes"],
            capacity_vehicles_per_hour=properties["capacity_vehicles_per_hour"],
            crossing_type=properties.get("crossing_type"),
            assumption=config.mobility.network.road_classes[properties["road_class"]].assumption,
        ))
    return SimulationInput(
        city_id=config.city.id,
        snapshot_id=snapshot.snapshot_id,
        snapshot_hash=snapshot.hash,
        seed=config.mobility.demand.seed if seed is None else seed,
        window=SimulationWindowContract(
            id=window.id,
            start=window.start,
            end=window.end,
            duration_seconds=duration_seconds,
        ),
        nodes=nodes,
        roads=tuple(roads),
        traffic_signals=tuple(
            SimulationSignalContract(
                node_id=signal.node_id,
                program_id=signal.program_id,
                offset_seconds=signal.offset_s,
                initial_phase_index=signal.initial_phase_index,
                phases=signal.phases,
                assumption=signal.assumption,
            )
            for signal in config.mobility.network.traffic_signals
        ),
        demand=tuple(
            SimulationODFlowContract(
                id=flow.id,
                from_node=flow.from_node,
                to_node=flow.to_node,
                vehicle_type=flow.vehicle_type,
                rate_vehicles_per_hour=flow.rate_vehicles_per_hour,
                assumption=flow.assumption,
            )
            for flow in demand_window.od_flows
        ),
    )


def create_configured_agent_copies(config: CityConfigFile, snapshot: CitySnapshot) -> list[CitySnapshot]:
    return create_agent_copies(snapshot, config)
