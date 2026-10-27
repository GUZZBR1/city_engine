"""Comparable interval metrics for observed and SUMO traffic measurements.

This module deliberately does not select a network, create demand, calibrate
SUMO, or infer detector-to-segment mappings. Callers must provide already
aligned measurements and the artifacts that produced them.
"""

from __future__ import annotations

import csv
import hashlib
import io
import math
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import Field, field_validator, model_validator

from .models import ContractModel


class IntervalMeasurement(ContractModel):
    """One observed or simulated value for an interval and spatial key.

    ``volume_vehicles`` is an actual count over this row's interval. MAE, RMSE,
    and bias retain that interval-count unit; volume GEH uses hourly-equivalent
    rates derived from the interval duration.
    """

    detector_id: str | None = None
    segment_id: str | None = None
    interval_start: datetime
    interval_end: datetime
    volume_vehicles: float | None = Field(default=None, ge=0)
    mean_speed_kmh: float | None = Field(default=None, ge=0)

    @field_validator("detector_id", "segment_id")
    @classmethod
    def normalize_ids(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            return None
        return value.strip() if value is not None else None

    @field_validator("volume_vehicles", "mean_speed_kmh")
    @classmethod
    def require_finite_measurements(cls, value: float | None) -> float | None:
        if value is not None and not math.isfinite(value):
            raise ValueError("measurement values must be finite")
        return value

    @model_validator(mode="after")
    def validate_interval(self) -> "IntervalMeasurement":
        if self.detector_id is None and self.segment_id is None:
            raise ValueError("at least one of detector_id or segment_id is required")
        if self.interval_start >= self.interval_end:
            raise ValueError("interval_start must be before interval_end")
        if self.volume_vehicles is None and self.mean_speed_kmh is None:
            raise ValueError("provide volume_vehicles, mean_speed_kmh, or both")
        return self


class InputArtifact(ContractModel):
    role: str
    path: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class EvaluationManifest(ContractModel):
    schema_version: str = "1.0"
    input_artifacts: tuple[InputArtifact, ...]
    seeds: tuple[int, ...]
    sumo_version: str = Field(min_length=1)

    @field_validator("seeds")
    @classmethod
    def validate_seeds(cls, values: tuple[int, ...]) -> tuple[int, ...]:
        if not values or any(seed < 0 for seed in values):
            raise ValueError("at least one non-negative SUMO seed is required")
        return values


class MetricSummary(ContractModel):
    n: int = Field(ge=1)
    mae: float = Field(ge=0)
    rmse: float = Field(ge=0)
    bias: float
    geh_mean: float | None = Field(default=None, ge=0)


class MeasurementMetrics(ContractModel):
    volume_vehicles: MetricSummary | None = None
    mean_speed_kmh: MetricSummary | None = None


class IntervalError(ContractModel):
    detector_id: str | None
    segment_id: str | None
    interval_start: str
    interval_end: str
    volume_observed: float | None
    volume_simulated: float | None
    volume_error: float | None
    volume_geh: float | None = Field(
        description="GEH from observed and simulated hourly-equivalent volume rates (veh/h)"
    )
    speed_observed_kmh: float | None
    speed_simulated_kmh: float | None
    speed_error_kmh: float | None


class EvaluationArtifact(ContractModel):
    manifest: EvaluationManifest
    overall: MeasurementMetrics
    by_detector: dict[str, MeasurementMetrics]
    by_segment: dict[str, MeasurementMetrics]
    by_window: dict[str, MeasurementMetrics]
    intervals: tuple[IntervalError, ...]


def compare_intervals(
    observed: tuple[IntervalMeasurement, ...] | list[IntervalMeasurement],
    simulated: tuple[IntervalMeasurement, ...] | list[IntervalMeasurement],
    *,
    manifest: EvaluationManifest,
) -> EvaluationArtifact:
    """Compare exact detector/segment/window matches without imputing gaps.

    Error signs are simulated minus observed. MAE, RMSE, and bias for volume
    remain in actual vehicles per matched interval. GEH applies only to volume
    after each count is normalized to veh/h using its matched interval duration;
    when both hourly-equivalent rates are zero its value is defined as zero.
    """
    observed_by_key = _index_measurements(observed, "observed")
    simulated_by_key = _index_measurements(simulated, "simulated")
    if observed_by_key.keys() != simulated_by_key.keys():
        missing_simulated = sorted(observed_by_key.keys() - simulated_by_key.keys(), key=repr)
        missing_observed = sorted(simulated_by_key.keys() - observed_by_key.keys(), key=repr)
        raise ValueError(
            "observed and simulated interval keys differ; "
            f"missing simulated={missing_simulated[:5]!r}, missing observed={missing_observed[:5]!r}"
        )

    records: list[IntervalError] = []
    buckets: dict[str, dict[str, list[tuple[float, float, float]]]] = defaultdict(lambda: defaultdict(list))
    all_values: dict[str, list[tuple[float, float, float]]] = defaultdict(list)
    groups: dict[str, dict[str, dict[str, list[tuple[float, float, float]]]]] = {
        "detector": defaultdict(lambda: defaultdict(list)),
        "segment": defaultdict(lambda: defaultdict(list)),
        "window": defaultdict(lambda: defaultdict(list)),
    }

    for key in sorted(observed_by_key, key=repr):
        left, right = observed_by_key[key], simulated_by_key[key]
        interval_seconds = (left.interval_end - left.interval_start).total_seconds()
        if not math.isfinite(interval_seconds) or interval_seconds <= 0:
            raise ValueError("matched interval duration must be a finite positive number of seconds")
        volume_error = _error(left.volume_vehicles, right.volume_vehicles)
        speed_error = _error(left.mean_speed_kmh, right.mean_speed_kmh)
        volume_geh = _geh(left.volume_vehicles, right.volume_vehicles, interval_seconds)
        records.append(IntervalError(
            detector_id=left.detector_id,
            segment_id=left.segment_id,
            interval_start=left.interval_start.isoformat(),
            interval_end=left.interval_end.isoformat(),
            volume_observed=left.volume_vehicles,
            volume_simulated=right.volume_vehicles,
            volume_error=volume_error,
            volume_geh=volume_geh,
            speed_observed_kmh=left.mean_speed_kmh,
            speed_simulated_kmh=right.mean_speed_kmh,
            speed_error_kmh=speed_error,
        ))
        window_key = f"{left.interval_start.isoformat()}/{left.interval_end.isoformat()}"
        dimension_keys = {
            "detector": left.detector_id,
            "segment": left.segment_id,
            "window": window_key,
        }
        for metric, a, b in (
            ("volume_vehicles", left.volume_vehicles, right.volume_vehicles),
            ("mean_speed_kmh", left.mean_speed_kmh, right.mean_speed_kmh),
        ):
            if a is None or b is None:
                continue
            all_values[metric].append((a, b, interval_seconds))
            for dimension, group_key in dimension_keys.items():
                if group_key is not None:
                    groups[dimension][group_key][metric].append((a, b, interval_seconds))

    for metric in ("volume_vehicles", "mean_speed_kmh"):
        buckets[metric] = all_values[metric]
    if not any(buckets.values()):
        raise ValueError("matched intervals contain no comparable observed/simulated measurements")
    return EvaluationArtifact(
        manifest=manifest,
        overall=_measurement_metrics(buckets),
        by_detector={key: _measurement_metrics(value) for key, value in sorted(groups["detector"].items())},
        by_segment={key: _measurement_metrics(value) for key, value in sorted(groups["segment"].items())},
        by_window={key: _measurement_metrics(value) for key, value in sorted(groups["window"].items())},
        intervals=tuple(records),
    )


def evaluate_csv_files(
    observed_csv: str | Path,
    simulated_csv: str | Path,
    *,
    seed: int,
    sumo_version: str,
    additional_inputs: dict[str, str | Path] | None = None,
) -> EvaluationArtifact:
    """Read canonical interval CSVs, hash all inputs, and compute the report.

    CSV columns are ``detector_id``, ``segment_id``, ``interval_start``,
    ``interval_end``, ``volume_vehicles``, and ``mean_speed_kmh``. Empty cells
    mean unavailable; they are not interpreted as zero.
    """
    observed, observed_ref = _read_csv(Path(observed_csv), "observed")
    simulated, simulated_ref = _read_csv(Path(simulated_csv), "sumo_measurements")
    refs = [observed_ref, simulated_ref]
    for role, path_value in sorted((additional_inputs or {}).items()):
        path = Path(path_value).resolve()
        payload = path.read_bytes()
        refs.append(InputArtifact(role=role, path=str(path), sha256=hashlib.sha256(payload).hexdigest()))
    manifest = EvaluationManifest(
        input_artifacts=tuple(refs), seeds=(seed,), sumo_version=sumo_version
    )
    return compare_intervals(observed, simulated, manifest=manifest)


def write_evaluation_artifact(artifact: EvaluationArtifact, output_path: str | Path) -> Path:
    """Write the JSON report to a caller-selected path and return that path."""
    path = Path(output_path)
    path.write_text(artifact.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return path


def _index_measurements(
    values: tuple[IntervalMeasurement, ...] | list[IntervalMeasurement], label: str
) -> dict[tuple[Any, ...], IntervalMeasurement]:
    result: dict[tuple[Any, ...], IntervalMeasurement] = {}
    for item in values:
        key = _key(item)
        if key in result:
            raise ValueError(f"duplicate {label} interval key: {key!r}")
        result[key] = item
    return result


def _key(item: IntervalMeasurement) -> tuple[Any, ...]:
    return item.detector_id, item.segment_id, item.interval_start, item.interval_end


def _error(observed: float | None, simulated: float | None) -> float | None:
    if observed is None or simulated is None:
        return None
    return simulated - observed


def _geh(observed: float | None, simulated: float | None, interval_seconds: float) -> float | None:
    if observed is None or simulated is None:
        return None
    hourly_scale = 3600.0 / interval_seconds
    observed_hourly = observed * hourly_scale
    simulated_hourly = simulated * hourly_scale
    if not math.isfinite(observed_hourly) or not math.isfinite(simulated_hourly):
        raise ValueError("hourly-equivalent volume rates must be finite")
    largest_rate = max(observed_hourly, simulated_hourly)
    if largest_rate == 0:
        return 0.0
    observed_ratio = observed_hourly / largest_rate
    simulated_ratio = simulated_hourly / largest_rate
    # This is algebraically the usual GEH formula, scaled to avoid overflow in
    # squaring otherwise finite hourly-equivalent rates.
    geh = (
        math.sqrt(2)
        * math.sqrt(largest_rate)
        * abs(simulated_ratio - observed_ratio)
        / math.sqrt(simulated_ratio + observed_ratio)
    )
    if not math.isfinite(geh):
        raise ValueError("GEH must be finite")
    return geh


def _summary(values: list[tuple[float, float, float]], *, volume: bool) -> MetricSummary | None:
    if not values:
        return None
    errors = [simulated - observed for observed, simulated, _ in values]
    geh_values = [_geh(observed, simulated, duration) for observed, simulated, duration in values] if volume else []
    return MetricSummary(
        n=len(errors),
        mae=sum(abs(error) for error in errors) / len(errors),
        rmse=math.sqrt(sum(error * error for error in errors) / len(errors)),
        bias=sum(errors) / len(errors),
        geh_mean=(sum(value for value in geh_values if value is not None) / len(geh_values)) if geh_values else None,
    )


def _measurement_metrics(values: dict[str, list[tuple[float, float, float]]]) -> MeasurementMetrics:
    return MeasurementMetrics(
        volume_vehicles=_summary(values.get("volume_vehicles", []), volume=True),
        mean_speed_kmh=_summary(values.get("mean_speed_kmh", []), volume=False),
    )


def _read_csv(path: Path, role: str) -> tuple[list[IntervalMeasurement], InputArtifact]:
    path = path.resolve()
    payload = path.read_bytes()
    try:
        text = payload.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{role} CSV must be UTF-8: {path}") from exc
    reader = csv.DictReader(io.StringIO(text))
    required = {
        "detector_id", "segment_id", "interval_start", "interval_end",
        "volume_vehicles", "mean_speed_kmh",
    }
    if reader.fieldnames is None or not required.issubset(reader.fieldnames):
        raise ValueError(f"{role} CSV must contain columns: {', '.join(sorted(required))}")
    measurements: list[IntervalMeasurement] = []
    for row_number, row in enumerate(reader, start=2):
        try:
            measurements.append(IntervalMeasurement(
                detector_id=_cell(row.get("detector_id")),
                segment_id=_cell(row.get("segment_id")),
                interval_start=row["interval_start"],
                interval_end=row["interval_end"],
                volume_vehicles=_number(row.get("volume_vehicles")),
                mean_speed_kmh=_number(row.get("mean_speed_kmh")),
            ))
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"invalid {role} CSV row {row_number}: {exc}") from exc
    return measurements, InputArtifact(
        role=role,
        path=str(path),
        sha256=hashlib.sha256(payload).hexdigest(),
    )


def _cell(value: str | None) -> str | None:
    return value.strip() if value and value.strip() else None


def _number(value: str | None) -> float | None:
    return float(value) if value is not None and value.strip() else None
