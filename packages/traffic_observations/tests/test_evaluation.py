from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timedelta

import pytest

from traffic_observations import (
    EvaluationManifest,
    InputArtifact,
    IntervalMeasurement,
    compare_intervals,
    evaluate_csv_files,
    write_evaluation_artifact,
)


def manifest() -> EvaluationManifest:
    return EvaluationManifest(
        input_artifacts=(InputArtifact(role="unit_fixture", path="fixture.csv", sha256="a" * 64),),
        seeds=(17,),
        sumo_version="1.20.0",
    )


def measurement(start, *, detector="D1", segment="S1", volume, speed):
    start_at = datetime.fromisoformat(f"2026-10-27T{start}:00+00:00")
    return IntervalMeasurement(
        detector_id=detector,
        segment_id=segment,
        interval_start=start_at,
        interval_end=start_at + timedelta(minutes=15),
        volume_vehicles=volume,
        mean_speed_kmh=speed,
    )


def test_comparison_computes_volume_speed_metrics_and_spatial_window_groups():
    observed = [measurement("08:00", volume=0, speed=0), measurement("08:15", volume=10, speed=40)]
    simulated = [measurement("08:00", volume=0, speed=2), measurement("08:15", volume=7, speed=46)]

    result = compare_intervals(observed, simulated, manifest=manifest())

    volume = result.overall.volume_vehicles
    speed = result.overall.mean_speed_kmh
    assert volume is not None and speed is not None
    assert volume.n == speed.n == 2
    assert volume.mae == pytest.approx(1.5)
    assert volume.rmse == pytest.approx(math.sqrt(4.5))
    assert volume.bias == pytest.approx(-1.5)
    assert volume.geh_mean == pytest.approx(math.sqrt(72 / 17) / 2)
    assert speed.mae == pytest.approx(4)
    assert speed.rmse == pytest.approx(math.sqrt(20))
    assert speed.bias == pytest.approx(4)
    assert speed.geh_mean is None
    assert result.by_detector["D1"].volume_vehicles == volume
    assert result.by_segment["S1"].mean_speed_kmh == speed
    assert len(result.by_window) == 2
    assert result.intervals[0].volume_geh == 0
    assert result.intervals[0].volume_error == 0


def test_comparison_rejects_unmatched_or_duplicate_interval_keys():
    one = measurement("08:00", volume=2, speed=None)
    duplicate = measurement("08:00", volume=3, speed=None)
    with pytest.raises(ValueError, match="duplicate observed"):
        compare_intervals([one, duplicate], [one], manifest=manifest())
    with pytest.raises(ValueError, match="interval keys differ"):
        compare_intervals([one], [measurement("08:15", volume=2, speed=None)], manifest=manifest())


def test_15_minute_geh_uses_hourly_equivalent_volumes():
    observed = measurement("08:00", volume=5, speed=None)
    simulated = measurement("08:00", volume=7, speed=None)

    result = compare_intervals([observed], [simulated], manifest=manifest())

    volume = result.overall.volume_vehicles
    assert volume is not None
    assert volume.mae == 2  # actual vehicles per 15-minute interval
    assert volume.bias == 2
    assert result.intervals[0].volume_geh == pytest.approx(math.sqrt(8 / 3))


def test_csv_harness_hashes_inputs_and_writes_explicit_report(tmp_path):
    headers = "detector_id,segment_id,interval_start,interval_end,volume_vehicles,mean_speed_kmh\n"
    observed = tmp_path / "observed.csv"
    simulated = tmp_path / "sumo.csv"
    demand = tmp_path / "independent-demand.json"
    observed.write_text(headers + "D1,S1,2026-10-27T08:00:00Z,2026-10-27T08:15:00Z,5,30\n", encoding="utf-8")
    simulated.write_text(headers + "D1,S1,2026-10-27T08:00:00Z,2026-10-27T08:15:00Z,7,28\n", encoding="utf-8")
    demand.write_text('{"definition":"independent test input"}\n', encoding="utf-8")

    artifact = evaluate_csv_files(
        observed,
        simulated,
        seed=23,
        sumo_version="1.26.0",
        additional_inputs={"independent_demand": demand},
    )

    assert artifact.manifest.seeds == (23,)
    assert artifact.manifest.sumo_version == "1.26.0"
    hashes = {item.role: item.sha256 for item in artifact.manifest.input_artifacts}
    assert hashes["observed"] == hashlib.sha256(observed.read_bytes()).hexdigest()
    assert hashes["sumo_measurements"] == hashlib.sha256(simulated.read_bytes()).hexdigest()
    assert hashes["independent_demand"] == hashlib.sha256(demand.read_bytes()).hexdigest()
    output = write_evaluation_artifact(artifact, tmp_path / "report.json")
    serialized = json.loads(output.read_text(encoding="utf-8"))
    assert serialized["overall"]["volume_vehicles"]["bias"] == 2
    assert serialized["intervals"][0]["volume_geh"] == pytest.approx(math.sqrt(8 / 3))
    assert len(serialized["intervals"]) == 1


def test_measurements_reject_non_finite_values():
    with pytest.raises(ValueError):
        measurement("08:00", volume=float("nan"), speed=None)
    with pytest.raises(ValueError, match="finite"):
        measurement("08:00", volume=float("inf"), speed=None)


def test_csv_empty_metric_is_missing_and_mismatched_inputs_are_not_zero_filled(tmp_path):
    headers = "detector_id,segment_id,interval_start,interval_end,volume_vehicles,mean_speed_kmh\n"
    observed = tmp_path / "observed.csv"
    simulated = tmp_path / "sumo.csv"
    observed.write_text(headers + "D1,S1,2026-10-27T08:00:00Z,2026-10-27T08:15:00Z,,30\n", encoding="utf-8")
    simulated.write_text(headers + "D1,S1,2026-10-27T08:00:00Z,2026-10-27T08:15:00Z,0,\n", encoding="utf-8")

    with pytest.raises(ValueError, match="no comparable observed/simulated measurements"):
        evaluate_csv_files(observed, simulated, seed=1, sumo_version="1.26.0")
