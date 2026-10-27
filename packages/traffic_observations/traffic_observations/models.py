"""Versionable canonical observation and replay contracts."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from collections.abc import Mapping
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class FrozenDict(dict[str, Any]):
    """JSON-serializable mapping that also blocks nested in-place mutation."""

    @staticmethod
    def _immutable(*args: object, **kwargs: object) -> None:
        raise TypeError("mapping is immutable")

    __setitem__ = _immutable
    __delitem__ = _immutable
    clear = _immutable
    pop = _immutable
    popitem = _immutable
    setdefault = _immutable
    update = _immutable
    __ior__ = _immutable


def _freeze_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return FrozenDict({key: _freeze_json(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_json(item) for item in value)
    return value


class ProvenanceKind(StrEnum):
    OBSERVED = "observed"
    ESTIMATED = "estimated"
    SYNTHETIC = "synthetic"
    SIMULATED = "simulated"
    DERIVED = "derived"
    UNKNOWN = "unknown"


class ObservationType(StrEnum):
    TRAFFIC = "traffic"
    EVENT = "event"


class TrafficObservation(ContractModel):
    """One source observation; absent source fields remain ``None``."""

    schema_version: Literal["1.0"] = "1.0"
    observation_id: str = Field(min_length=1)
    observation_type: ObservationType = ObservationType.TRAFFIC
    timestamp: datetime
    source_id: str = Field(min_length=1)
    dataset_id: str = Field(min_length=1)
    location_id: str | None = None
    road_segment_id: str | None = None
    intersection_id: str | None = None
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    vehicle_count: int | None = Field(default=None, ge=0)
    flow_veh_h: float | None = Field(default=None, ge=0)
    mean_speed_kmh: float | None = Field(default=None, ge=0)
    density: float | None = Field(default=None, ge=0)
    congestion_level: str | None = None
    weather: dict[str, Any] | None = None
    event_type: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    provenance_kind: ProvenanceKind
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("weather", "metadata", mode="after")
    @classmethod
    def freeze_nested_data(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        return _freeze_json(value) if value is not None else None

    @model_validator(mode="after")
    def validate_coordinate_pair(self) -> "TrafficObservation":
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("latitude e longitude devem ser informadas juntas")
        return self


class SupportingArtifact(ContractModel):
    """A sidecar whose contents affect interpretation of the primary artifact."""

    artifact: str
    sha256: str


class DatasetManifest(ContractModel):
    dataset_id: str
    source_uri: str
    artifact: str
    artifact_sha256: str | None = None
    supporting_artifacts: tuple[SupportingArtifact, ...] = ()
    declared_license: str | None = None
    license_status: Literal["declared_unverified", "verified", "conflicting", "unknown"]
    provenance_kind: ProvenanceKind
    provenance_note: str
    limitations: tuple[str, ...] = ()


class BoundingBox(ContractModel):
    min_longitude: float = Field(ge=-180, le=180)
    min_latitude: float = Field(ge=-90, le=90)
    max_longitude: float = Field(ge=-180, le=180)
    max_latitude: float = Field(ge=-90, le=90)

    @model_validator(mode="after")
    def validate_bounds(self) -> "BoundingBox":
        if self.min_longitude >= self.max_longitude or self.min_latitude >= self.max_latitude:
            raise ValueError("bounding box deve ter limites mínimos menores que os máximos")
        return self


class ReplayFilters(ContractModel):
    start_at: datetime | None = None
    end_at: datetime | None = None
    location_ids: tuple[str, ...] = ()
    region: BoundingBox | None = None
    observation_types: tuple[ObservationType, ...] = (ObservationType.TRAFFIC,)

    @model_validator(mode="after")
    def validate_time_range(self) -> "ReplayFilters":
        if self.start_at and self.end_at:
            if self.start_at.tzinfo != self.end_at.tzinfo:
                raise ValueError("start_at e end_at devem usar a mesma convenção de fuso horário")
            if self.start_at > self.end_at:
                raise ValueError("start_at deve ser anterior ou igual a end_at")
        return self


class ReplayStatus(StrEnum):
    PAUSED = "paused"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ReplaySnapshot(ContractModel):
    replay_id: str
    status: ReplayStatus
    dataset: DatasetManifest
    filters: ReplayFilters
    observations_per_second: float = Field(gt=0)
    emitted_count: int = Field(ge=0)
    current_timestamp: datetime | None = None
    error: str | None = None
    latest_by_location: tuple[TrafficObservation, ...] = ()
