"""Typed configuration and snapshot contracts for the Urban Arena city core."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CityConfig(StrictModel):
    id: str
    name: str
    description: str
    status: str
    country_reference: str
    census_reference_year: int


class StatisticalBasis(StrictModel):
    unit: str
    operational_size_range: tuple[int, int]
    municipalities_in_sample: int
    sum_residents_in_sample: int
    arithmetic_mean_residents: float
    note: str


class HouseholdConfig(StrictModel):
    mean_residents_per_occupied_household: float
    occupied_households_derived: int
    source_scope: str


class UrbanRuralConfig(StrictModel):
    urban_share_reference: float
    rural_share_reference: float
    urban_residents_derived: int
    rural_catchment_residents_derived: int
    source_scope: str
    note: str


class PopulationConfig(StrictModel):
    total_residents: int
    statistical_basis: StatisticalBasis
    household: HouseholdConfig
    urban_rural: UrbanRuralConfig


class UrbanFootprint(StrictModel):
    area_km2: float
    geometry: str
    urban_resident_density_per_km2_derived: int
    statistical_status: str


class DistrictConfig(StrictModel):
    id: str
    type: Literal["urban", "external_catchment"]
    residents: int
    jobs: int
    land_use: str


class EmploymentConfig(StrictModel):
    total_jobs: int
    statistical_status: str
    note: str


class BarrierConfig(StrictModel):
    orientation: Literal["north_south", "east_west"]
    crossings: int
    crossing_types: tuple[str, ...]


RoadClass = Literal["local", "collector", "arterial"]


class RoadClassConfig(StrictModel):
    speed_limit_kmh: float = Field(gt=0)
    lanes: int = Field(gt=0)
    capacity_vehicles_per_hour: int = Field(gt=0)
    synthetic: Literal[True] = True
    assumption: str


class SignalPhase(StrictModel):
    movement: Literal["north_south", "east_west", "all_red"]
    duration_s: int = Field(gt=0)


class TrafficSignalConfig(StrictModel):
    node_id: str
    program_id: str
    offset_s: int = Field(ge=0)
    initial_phase_index: int = Field(ge=0)
    phases: tuple[SignalPhase, ...] = Field(min_length=2)
    synthetic: Literal[True] = True
    assumption: str

    @model_validator(mode="after")
    def validate_initial_phase(self) -> "TrafficSignalConfig":
        if self.initial_phase_index >= len(self.phases):
            raise ValueError("initial_phase_index deve referenciar uma fase existente")
        return self


class ODFlowConfig(StrictModel):
    id: str
    from_node: str
    to_node: str
    vehicle_type: Literal["passenger"] = "passenger"
    rate_vehicles_per_hour: float = Field(gt=0)
    synthetic: Literal[True] = True
    assumption: str


class WindowDemandConfig(StrictModel):
    window_id: str
    od_flows: tuple[ODFlowConfig, ...] = Field(min_length=1)


class DemandConfig(StrictModel):
    seed: int = Field(ge=0)
    seed_scope: str
    generation_method: str
    windows: tuple[WindowDemandConfig, ...] = Field(min_length=1)
    synthetic: Literal[True] = True


class NetworkConfig(StrictModel):
    grid_intersections: tuple[int, int]
    directed_edges_derived: int
    arterial_corridors: int
    barrier: BarrierConfig
    road_classes: dict[RoadClass, RoadClassConfig]
    default_road_class: RoadClass
    crossing_road_classes: dict[str, RoadClass]
    traffic_signals: tuple[TrafficSignalConfig, ...] = ()


class TransitConfig(StrictModel):
    bus_routes: int
    route: tuple[str, ...]
    peak_headway_minutes: int
    off_peak_headway_minutes: int
    statistical_status: str


class SimulationWindow(StrictModel):
    id: str
    start: str
    end: str


class CommuteModeShare(StrictModel):
    automobile: float
    bus: float
    walking: float
    motorcycle: float
    bicycle: float
    other: float
    source_scope: str
    note: str


class MobilityConfig(StrictModel):
    network: NetworkConfig
    transit: TransitConfig
    commute_main_mode_share: CommuteModeShare
    simulation_windows: tuple[SimulationWindow, ...]
    simulation_windows_note: str
    demand: DemandConfig


class FinanceConfig(StrictModel):
    currency: str
    credits_per_round: int
    fixed_operations: int
    reserve: int
    discretionary_budget: int
    statistical_status: str


class ArenaConfig(StrictModel):
    round_duration: str
    default_horizon_rounds: int
    ai_agent_copies: int
    reference_policies: tuple[str, ...]
    initial_state_immutable: bool
    common_random_scenarios: bool
    paired_replicates_required: bool
    default_scoring: str
    universal_single_score: bool


class ProvenanceSource(StrictModel):
    id: str
    url: str
    used_for: str


class ProvenanceConfig(StrictModel):
    synthetic_city: bool
    sources: tuple[ProvenanceSource, ...]
    empirical_validation_status: str


class CityConfigFile(StrictModel):
    schema_version: int
    city: CityConfig
    population: PopulationConfig
    urban_footprint: UrbanFootprint
    districts: tuple[DistrictConfig, ...]
    employment: EmploymentConfig
    mobility: MobilityConfig
    finance: FinanceConfig
    arena: ArenaConfig
    provenance: ProvenanceConfig

    @model_validator(mode="after")
    def validate_city_balances(self) -> "CityConfigFile":
        errors: list[str] = []
        urban_residents = sum(d.residents for d in self.districts if d.type == "urban")
        catchment_residents = sum(d.residents for d in self.districts if d.type == "external_catchment")
        total_residents = sum(d.residents for d in self.districts)
        total_jobs = sum(d.jobs for d in self.districts)
        if urban_residents != self.population.urban_rural.urban_residents_derived:
            errors.append("distritos urbanos não fecham com urban_residents_derived")
        if catchment_residents != self.population.urban_rural.rural_catchment_residents_derived:
            errors.append("entorno rural não fecha com rural_catchment_residents_derived")
        if total_residents != self.population.total_residents:
            errors.append("residentes dos distritos não fecham com total_residents")
        if total_jobs != self.employment.total_jobs:
            errors.append("empregos dos distritos não fecham com employment.total_jobs")
        if round(self.population.urban_rural.urban_share_reference + self.population.urban_rural.rural_share_reference, 12) != 1:
            errors.append("urban_share_reference + rural_share_reference deve ser 1")
        shares = self.mobility.commute_main_mode_share.model_dump(exclude={"source_scope", "note"})
        if round(sum(shares.values()), 12) != 1:
            errors.append("commute_main_mode_share deve somar 1")
        if self.finance.fixed_operations + self.finance.reserve + self.finance.discretionary_budget != self.finance.credits_per_round:
            errors.append("componentes financeiros não fecham com credits_per_round")
        if len({district.id for district in self.districts}) != len(self.districts):
            errors.append("districts contém IDs duplicados")
        cols, rows = self.mobility.network.grid_intersections
        full_grid_edges = 2 * (cols * (rows - 1) + rows * (cols - 1))
        if cols < 2 or rows < 2:
            errors.append("grid_intersections deve ter ao menos duas linhas e duas colunas")
        barrier = self.mobility.network.barrier
        crossing_positions = rows if barrier.orientation == "north_south" else cols
        if barrier.crossings > crossing_positions:
            errors.append("barrier.crossings não pode exceder as posições da grade")
        expected_edges = full_grid_edges - 2 * max(0, crossing_positions - barrier.crossings)
        if self.mobility.network.directed_edges_derived != expected_edges:
            errors.append(f"directed_edges_derived deve corresponder à grade e às travessias da barreira ({expected_edges})")
        if barrier.crossings != len(barrier.crossing_types):
            errors.append("cada travessia da barreira deve ter exatamente um crossing_type")
        if len({window.id for window in self.mobility.simulation_windows}) != len(self.mobility.simulation_windows):
            errors.append("simulation_windows contém IDs duplicados")
        window_ids = {window.id for window in self.mobility.simulation_windows}
        node_ids = {f"node:{row:02d}:{col:02d}" for row in range(rows) for col in range(cols)}
        road_classes = self.mobility.network.road_classes
        if set(road_classes) != {"local", "collector", "arterial"}:
            errors.append("road_classes deve definir local, collector e arterial")
        if set(self.mobility.network.crossing_road_classes) != set(self.mobility.network.barrier.crossing_types):
            errors.append("crossing_road_classes deve mapear cada crossing_type configurado")
        if {"local", "collector", "arterial"}.issubset(road_classes) and not (
            road_classes["collector"].capacity_vehicles_per_hour < road_classes["arterial"].capacity_vehicles_per_hour
        ):
            errors.append("capacidade da classe collector deve ser menor que arterial")
        signals = self.mobility.network.traffic_signals
        if len({signal.node_id for signal in signals}) != len(signals):
            errors.append("traffic_signals contém nós duplicados")
        for signal in signals:
            if signal.node_id not in node_ids:
                errors.append(f"semáforo referencia nó inexistente: {signal.node_id}")
            if signal.offset_s >= sum(phase.duration_s for phase in signal.phases):
                errors.append(f"offset_s do semáforo {signal.node_id} deve ser menor que o ciclo")
            movements = {phase.movement for phase in signal.phases}
            if not {"north_south", "east_west"}.issubset(movements):
                errors.append(f"semáforo {signal.node_id} deve ter fases norte-sul e leste-oeste")
        demand = self.mobility.demand
        demand_window_ids = [window.window_id for window in demand.windows]
        if set(demand_window_ids) != window_ids or len(demand_window_ids) != len(set(demand_window_ids)):
            errors.append("demand.windows deve definir exatamente uma entrada para cada simulation_window")
        for window_demand in demand.windows:
            flow_ids = [flow.id for flow in window_demand.od_flows]
            if len(flow_ids) != len(set(flow_ids)):
                errors.append(f"demanda {window_demand.window_id} contém IDs OD duplicados")
            for flow in window_demand.od_flows:
                if flow.from_node not in node_ids or flow.to_node not in node_ids:
                    errors.append(f"OD {flow.id} referencia nó inexistente")
                if flow.from_node == flow.to_node:
                    errors.append(f"OD {flow.id} deve ter origem e destino diferentes")
        for window in self.mobility.simulation_windows:
            try:
                start_hour, start_minute = (int(part) for part in window.start.split(":"))
                end_hour, end_minute = (int(part) for part in window.end.split(":"))
                if not (0 <= start_hour < 24 and 0 <= end_hour < 24 and 0 <= start_minute < 60 and 0 <= end_minute < 60):
                    raise ValueError
                if end_hour * 60 + end_minute <= start_hour * 60 + start_minute:
                    raise ValueError
            except ValueError:
                errors.append(f"janela {window.id} deve ter horários HH:MM válidos e fim posterior ao início")
        if self.arena.ai_agent_copies < 1:
            errors.append("arena.ai_agent_copies deve ser positivo")
        if errors:
            raise ValueError("Configuração de cidade inválida: " + "; ".join(errors))
        return self


Coordinate = tuple[float, ...]
GeometryType = Literal["Point", "LineString", "Polygon"]


class LocalGeometry(StrictModel):
    type: GeometryType
    coordinates: list[float] | list[list[float]] | list[list[list[float]]]


class LocalFeature(StrictModel):
    type: Literal["Feature"] = "Feature"
    id: str
    geometry: LocalGeometry
    properties: dict[str, str | int | float | bool | None]


class LocalFeatureCollection(StrictModel):
    """Local metric geometry contract; deliberately not RFC 7946 GeoJSON."""

    type: Literal["LocalFeatureCollection"] = "LocalFeatureCollection"
    coordinate_space: Literal["synthetic_local_cartesian_m"] = "synthetic_local_cartesian_m"
    features: list[LocalFeature]


class PopulationTotals(StrictModel):
    total: int
    urban: int
    rural_catchment: int


class CitySnapshot(StrictModel):
    city_id: str
    snapshot_id: str
    name: str
    schema_version: str
    generator_version: str
    provenance: Literal["synthetic"]
    hash: str
    population: PopulationTotals
    jobs: int
    household: dict[str, int | float | str]
    finance: dict[str, int | str]
    commute_main_mode_share: dict[str, float]
    districts: list[dict[str, str | int]]
    mobility: dict[str, object]
    source_config: dict[str, object]
    coordinate_space: Literal["synthetic_local_cartesian_m"]
    bounds_m: tuple[int, int, int, int]
    layers: dict[str, LocalFeatureCollection]


class SimulationWindowContract(StrictModel):
    id: str
    start: str
    end: str
    duration_seconds: int = Field(gt=0)


class SimulationNodeContract(StrictModel):
    id: str
    x_m: float
    y_m: float


class SimulationRoadContract(StrictModel):
    id: str
    from_node: str
    to_node: str
    length_m: float = Field(gt=0)
    road_class: RoadClass
    speed_limit_kmh: float = Field(gt=0)
    lanes: int = Field(gt=0)
    capacity_vehicles_per_hour: int = Field(gt=0)
    crossing_type: str | None = None
    synthetic: Literal[True] = True
    assumption: str


class SimulationSignalContract(StrictModel):
    node_id: str
    program_id: str
    offset_seconds: int = Field(ge=0)
    initial_phase_index: int = Field(ge=0)
    phases: tuple[SignalPhase, ...]
    synthetic: Literal[True] = True
    assumption: str


class SimulationODFlowContract(StrictModel):
    id: str
    from_node: str
    to_node: str
    vehicle_type: Literal["passenger"]
    rate_vehicles_per_hour: float = Field(gt=0)
    synthetic: Literal[True] = True
    assumption: str


class SimulationInput(StrictModel):
    """Versioned, JSON-serializable boundary consumed by a simulation engine."""

    contract_version: Literal["1.0"] = "1.0"
    city_id: str
    snapshot_id: str
    snapshot_hash: str
    provenance: Literal["synthetic"] = "synthetic"
    seed: int = Field(ge=0)
    window: SimulationWindowContract
    nodes: tuple[SimulationNodeContract, ...]
    roads: tuple[SimulationRoadContract, ...]
    traffic_signals: tuple[SimulationSignalContract, ...]
    demand: tuple[SimulationODFlowContract, ...]
    coordinate_unit: Literal["m"] = "m"
    speed_unit: Literal["km/h"] = "km/h"
    flow_unit: Literal["vehicles/hour"] = "vehicles/hour"

    @model_validator(mode="after")
    def validate_references(self) -> "SimulationInput":
        node_ids = {node.id for node in self.nodes}
        if len(node_ids) != len(self.nodes):
            raise ValueError("nodes contém IDs duplicados")
        road_ids = {road.id for road in self.roads}
        if len(road_ids) != len(self.roads):
            raise ValueError("roads contém IDs duplicados")
        if any(road.from_node not in node_ids or road.to_node not in node_ids for road in self.roads):
            raise ValueError("roads referencia nó ausente")
        if any(signal.node_id not in node_ids for signal in self.traffic_signals):
            raise ValueError("traffic_signals referencia nó ausente")
        if any(flow.from_node not in node_ids or flow.to_node not in node_ids for flow in self.demand):
            raise ValueError("demand referencia nó ausente")
        if len({flow.id for flow in self.demand}) != len(self.demand):
            raise ValueError("demand contém IDs duplicados")
        adjacency: dict[str, set[str]] = {node_id: set() for node_id in node_ids}
        for road in self.roads:
            adjacency[road.from_node].add(road.to_node)
        for flow in self.demand:
            visited = {flow.from_node}
            frontier = [flow.from_node]
            while frontier:
                current = frontier.pop()
                for neighbor in adjacency[current] - visited:
                    visited.add(neighbor)
                    frontier.append(neighbor)
            if flow.to_node not in visited:
                raise ValueError(f"demanda {flow.id} não possui caminho direcionado na rede")
        return self
