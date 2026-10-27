"""Stable public contracts for simulations and their engine inputs."""

from __future__ import annotations

from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class RoadNode(ContractModel):
    id: str
    x_m: float
    y_m: float


class RoadEdge(ContractModel):
    id: str
    from_node: str
    to_node: str
    speed_mps: float = Field(gt=0)
    lane_count: int = Field(ge=1)


class SignalPhase(ContractModel):
    movement: str
    duration_seconds: int = Field(gt=0)


class SignalTimingPhase(ContractModel):
    movement: Literal["north_south", "all_red", "east_west"]
    duration_seconds: int = Field(gt=0, strict=True)


class SignalTimingIntervention(ContractModel):
    """Declarative phase durations for one existing traffic signal."""

    node_id: str
    phases: tuple[SignalTimingPhase, ...]


class TrafficSignal(ContractModel):
    node_id: str
    program_id: str
    offset_seconds: int = Field(ge=0)
    initial_phase_index: int = Field(ge=0)
    phases: tuple[SignalPhase, ...]


class RequestedTrip(ContractModel):
    id: str
    from_edge: str
    to_edge: str
    departure_seconds: float = Field(ge=0)


class SimulationWindow(ContractModel):
    id: str
    start: str
    end: str

    @field_validator("start", "end")
    @classmethod
    def validate_clock(cls, value: str) -> str:
        _clock_seconds(value)
        return value

    @property
    def duration_seconds(self) -> int:
        start = _clock_seconds(self.start)
        end = _clock_seconds(self.end)
        return end - start if end > start else end + 86400 - start


class SimulationInput(ContractModel):
    """Engine-neutral projection of the Chat 1 network/demand contract."""

    city_id: str
    snapshot_id: str
    snapshot_hash: str
    city_schema_version: str
    city_generator_version: str
    provenance: str
    window: SimulationWindow
    nodes: tuple[RoadNode, ...]
    edges: tuple[RoadEdge, ...]
    traffic_signals: tuple[TrafficSignal, ...] = ()
    trips: tuple[RequestedTrip, ...]
    warnings: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_unique_ids(self) -> SimulationInput:
        for label, values in (
            ("nós", [node.id for node in self.nodes]),
            ("arestas", [edge.id for edge in self.edges]),
            ("viagens", [trip.id for trip in self.trips]),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"Contrato contém IDs duplicados em {label}.")
        return self


class SimulationLimits(ContractModel):
    wall_timeout_seconds: float = Field(default=120, gt=0, le=3600)
    max_window_seconds: int = Field(default=86400, gt=0, le=604800)
    drain_limit_seconds: int = Field(default=3600, ge=0, le=604800)
    max_requested_trips: int = Field(default=100_000, gt=0, le=1_000_000)
    output_directory: str | None = None


class SimulationMetrics(ContractModel):
    trips_requested: int = Field(ge=0)
    trips_completed: int = Field(ge=0)
    trips_not_completed: int = Field(ge=0)
    mean_travel_time_seconds: float | None = Field(ge=0)
    mean_speed_kmh: float | None = Field(ge=0)
    mean_queue_length_meters: float | None = Field(ge=0)

    @model_validator(mode="after")
    def validate_trip_totals(self) -> SimulationMetrics:
        if self.trips_completed + self.trips_not_completed != self.trips_requested:
            raise ValueError("Viagens concluídas e não concluídas devem somar as solicitadas.")
        return self


class ArtifactReferences(ContractModel):
    network_file: str
    routes_file: str
    tripinfo_file: str | None = None
    queue_file: str | None = None


class SimulationResult(ContractModel):
    simulation_id: str
    city_id: str
    snapshot_id: str
    snapshot_hash: str
    city_schema_version: str
    city_generator_version: str
    window_id: str
    seed: int = Field(ge=0)
    engine: str
    engine_version: str
    metrics: SimulationMetrics
    metric_methods: dict[str, str]
    warnings: tuple[str, ...] = ()
    artifacts: ArtifactReferences


class SimulationError(RuntimeError):
    """Stable public failure carrying a machine-readable code."""

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


@runtime_checkable
class SimulationEngine(Protocol):
    engine_name: str

    def run(
        self,
        inputs: SimulationInput,
        *,
        seed: int,
        limits: SimulationLimits | None = None,
    ) -> SimulationResult: ...


def _clock_seconds(value: str) -> int:
    try:
        if len(value) != 5 or value[2] != ":":
            raise ValueError
        hour_text, minute_text = value.split(":", 1)
        hour, minute = int(hour_text), int(minute_text)
    except (ValueError, AttributeError) as exc:
        raise ValueError(f"Horário inválido '{value}'; esperado HH:MM.") from exc
    if not (0 <= hour < 24 and 0 <= minute < 60):
        raise ValueError(f"Horário inválido '{value}'; esperado HH:MM.")
    return hour * 3600 + minute * 60
