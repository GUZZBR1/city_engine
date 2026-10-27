from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from simulation import SignalTimingIntervention


class HealthResponse(BaseModel):
    status: Literal["ok"]


class PopulationTotals(BaseModel):
    total: int = Field(ge=0)
    urban: int = Field(ge=0)
    rural_catchment: int = Field(ge=0)


class CityMetadata(BaseModel):
    city_id: str
    snapshot_id: str
    name: str
    schema_version: str
    provenance: Literal["synthetic"]
    hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    population: PopulationTotals
    jobs: int = Field(ge=0)


class LocalGeometry(BaseModel):
    """Geometry coordinates are local meters, not geographic coordinates."""

    model_config = ConfigDict(extra="allow")

    type: str
    coordinates: Any


class LocalFeature(BaseModel):
    model_config = ConfigDict(extra="allow")

    type: Literal["Feature"]
    id: str | int | None = None
    geometry: LocalGeometry
    properties: dict[str, Any] = Field(default_factory=dict)


class LocalFeatureCollection(BaseModel):
    """Project contract; deliberately distinct from GeoJSON RFC 7946."""

    type: Literal["LocalFeatureCollection"]
    coordinate_space: Literal["synthetic_local_cartesian_m"]
    features: list[LocalFeature]


class CityLayers(BaseModel):
    districts: LocalFeatureCollection
    edges: LocalFeatureCollection
    nodes: LocalFeatureCollection


class CityMap(BaseModel):
    city_id: str
    snapshot_id: str
    hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    provenance: Literal["synthetic"]
    coordinate_space: Literal["synthetic_local_cartesian_m"]
    bounds_m: tuple[float, float, float, float]
    layers: CityLayers


class ErrorResponse(BaseModel):
    detail: str


class SimulationRequest(BaseModel):
    city_id: Literal["aurora-base-v1"]
    window_id: str
    seed: int = Field(default=42, ge=0)
    drain_limit_seconds: int = Field(default=3600, ge=0, le=604800)


class SimulationMetrics(BaseModel):
    trips_requested: int = Field(ge=0)
    trips_completed: int = Field(ge=0)
    trips_not_completed: int = Field(ge=0)
    mean_travel_time_seconds: float | None = Field(default=None, ge=0)
    mean_speed_kmh: float | None = Field(default=None, ge=0)
    mean_queue_length_meters: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_trip_totals(self) -> SimulationMetrics:
        if self.trips_completed + self.trips_not_completed != self.trips_requested:
            raise ValueError("Viagens concluídas e não concluídas devem somar as solicitadas.")
        return self


class SimulationFailure(BaseModel):
    code: str
    message: str


class SimulationJob(BaseModel):
    simulation_id: str
    status: Literal["queued", "running", "succeeded", "failed", "cancelled"]
    city_id: str
    snapshot_id: str
    window_id: str
    seed: int = Field(ge=0)
    drain_limit_seconds: int = Field(ge=0, le=604800)
    engine_version: str
    metrics: SimulationMetrics | None = None
    warnings: list[str] = Field(default_factory=list)
    error: SimulationFailure | None = None


class SimulationResponse(BaseModel):
    simulation: SimulationJob


class ComparisonRequest(BaseModel):
    city_id: Literal["aurora-base-v1"]
    window_id: str
    seed: int = Field(default=42, ge=0)
    drain_limit_seconds: int = Field(default=3600, ge=0, le=604800)
    intervention: SignalTimingIntervention


class ComparisonCommonParameters(BaseModel):
    city_id: str
    snapshot_id: str
    snapshot_hash: str
    window_id: str
    seed: int = Field(ge=0)
    drain_limit_seconds: int = Field(ge=0, le=604800)
    trips_requested: int = Field(ge=0)
    demand_hash: str


class ComparisonResultIdentity(BaseModel):
    simulation_id: str
    engine: str
    engine_version: str


class SimulationMetricDeltas(BaseModel):
    trips_requested: int
    trips_completed: int
    trips_not_completed: int
    mean_travel_time_seconds: float | None
    mean_speed_kmh: float | None
    mean_queue_length_meters: float | None


class ComparisonFailure(BaseModel):
    code: str
    scenario: Literal["base", "intervention"] | None = None
    message: str


class SimulationComparison(BaseModel):
    comparison_id: str
    status: Literal["queued", "running", "succeeded", "failed"]
    common_parameters: ComparisonCommonParameters
    intervention: SignalTimingIntervention
    route_exposure: Literal["exposed", "not_exposed", "unknown"] | None = None
    base_result: ComparisonResultIdentity | None = None
    intervention_result: ComparisonResultIdentity | None = None
    base_metrics: SimulationMetrics | None = None
    intervention_metrics: SimulationMetrics | None = None
    deltas: SimulationMetricDeltas | None = None
    base_warnings: list[str] = Field(default_factory=list)
    intervention_warnings: list[str] = Field(default_factory=list)
    error: ComparisonFailure | None = None


class ComparisonResponse(BaseModel):
    comparison: SimulationComparison
