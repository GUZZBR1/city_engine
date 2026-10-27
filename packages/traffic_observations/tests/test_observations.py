from __future__ import annotations

import csv
from datetime import datetime

import pytest

from traffic_observations import replay as replay_module
from traffic_observations import (
    BoundingBox,
    DatasetManifest,
    DatasetSourceError,
    ObservationType,
    ProvenanceKind,
    ReplayControlError,
    ReplayCapacityError,
    ReplayFilters,
    ReplayManager,
    ReplayNotFoundError,
    ReplaySession,
    ReplayStatus,
    SmartCityTrafficCsvAdapter,
    TrafficObservation,
    UnsupportedSourceFilter,
)


HEADERS = [
    "timestamp", "sensor_id", "location", "direction", "vehicle_count", "average_speed_kmh",
    "occupancy_rate", "congestion_level", "car_count", "motorcycle_count", "truck_count",
    "bus_count", "day_of_week", "is_holiday", "hour",
]


def write_dataset(path, rows):
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=HEADERS)
        writer.writeheader()
        writer.writerows(rows)


def row(timestamp, sensor_id, count=10):
    return {
        "timestamp": timestamp,
        "sensor_id": sensor_id,
        "location": f"Location {sensor_id}",
        "direction": "East",
        "vehicle_count": str(count),
        "average_speed_kmh": "31.5",
        "occupancy_rate": "0.25",
        "congestion_level": "Low",
        "car_count": str(count - 1),
        "motorcycle_count": "1",
        "truck_count": "0",
        "bus_count": "0",
        "day_of_week": "0",
        "is_holiday": "0",
        "hour": timestamp[11:13],
    }


def test_adapter_preserves_supported_fields_and_sorts_timestamp_without_inventing_data(tmp_path):
    path = tmp_path / "traffic_sensor_data.csv"
    write_dataset(path, [
        row("2024-01-01T00:30:00", "S2", 11),
        row("2024-01-01T00:00:00", "S1", 10),
    ])

    adapter = SmartCityTrafficCsvAdapter(path)
    observations = list(adapter.iter_observations())

    assert [item.timestamp for item in observations] == [
        datetime(2024, 1, 1, 0, 0), datetime(2024, 1, 1, 0, 30),
    ]
    first = observations[0]
    assert first.source_id == first.location_id == "S1"
    assert first.dataset_id == adapter.manifest.dataset_id
    assert first.vehicle_count == 10
    assert first.mean_speed_kmh == 31.5
    assert first.congestion_level == "Low"
    assert first.provenance_kind == ProvenanceKind.SIMULATED
    assert first.latitude is first.longitude is None
    assert first.road_segment_id is first.intersection_id is None
    assert first.flow_veh_h is first.density is first.confidence is None
    assert first.weather is first.event_type is None
    assert first.metadata["source_occupancy_rate"] == 0.25
    assert first.metadata["timestamp_timezone"] == "unspecified; source timestamps are naive"


def test_adapter_marks_internal_count_mismatch_without_correcting_source_value(tmp_path):
    path = tmp_path / "traffic_sensor_data.csv"
    bad = row("2024-01-01T00:00:00", "S1", 20)
    bad["car_count"] = "9"
    write_dataset(path, [bad])

    adapter = SmartCityTrafficCsvAdapter(path)
    observation = next(adapter.iter_observations())

    assert observation.vehicle_count == 20
    assert observation.metadata["data_quality_flags"] == ("vehicle_count_subtype_sum_mismatch",)


def test_adapter_keeps_unverified_sensor_coordinates_as_metadata_only(tmp_path):
    path = tmp_path / "traffic_sensor_data.csv"
    write_dataset(path, [row("2024-01-01T00:00:00", "S1")])
    (tmp_path / "sensor_locations.json").write_text(
        '{"dataset_info":{"coordinate_system":"WGS84"},"sensors":[{"sensor_id":"S1",'
        '"coordinates":{"latitude":-6.2,"longitude":106.8},"road_segment_id":"RD-1",'
        '"sampling_rate_seconds":300,"district":"Central"}]}',
        encoding="utf-8",
    )
    (tmp_path / "traffic_prediction_config.json").write_text(
        '{"data_sources":{"primary":{"update_frequency":"30 minutes"}}}', encoding="utf-8"
    )

    adapter = SmartCityTrafficCsvAdapter(path)
    observation = next(adapter.iter_observations())

    assert observation.latitude is observation.longitude is None
    assert observation.road_segment_id is None
    assert observation.metadata["reported_coordinates"]["latitude"] == -6.2
    assert observation.metadata["reported_road_segment_id"] == "RD-1"
    assert observation.metadata["reported_sensor_sampling_rate_seconds"] == 300
    assert observation.metadata["declared_sampling_interval_minutes"] == 30

    assert {artifact.artifact for artifact in adapter.manifest.supporting_artifacts} == {
        "sensor_locations.json", "traffic_prediction_config.json"
    }
    assert all(len(artifact.sha256) == 64 for artifact in adapter.manifest.supporting_artifacts)


def test_adapter_rejects_changed_sidecar_after_manifest_hash(tmp_path):
    path = tmp_path / "traffic_sensor_data.csv"
    write_dataset(path, [row("2024-01-01T00:00:00", "S1")])
    sensor_path = tmp_path / "sensor_locations.json"
    sensor_path.write_text(
        '{"sensors":[{"sensor_id":"S1","coordinates":{"latitude":-6.2,"longitude":106.8}}]}',
        encoding="utf-8",
    )
    adapter = SmartCityTrafficCsvAdapter(path)
    sensor_path.write_text('{"sensors":[]}', encoding="utf-8")

    with pytest.raises(DatasetSourceError, match="sidecar mudou depois"):
        next(adapter.iter_observations())


def test_adapter_rejects_malformed_sensor_metadata_root(tmp_path):
    path = tmp_path / "traffic_sensor_data.csv"
    write_dataset(path, [row("2024-01-01T00:00:00", "S1")])
    (tmp_path / "sensor_locations.json").write_text("[]", encoding="utf-8")

    with pytest.raises(DatasetSourceError, match="objeto na raiz"):
        SmartCityTrafficCsvAdapter(path)


def test_adapter_does_not_disclose_local_path_after_source_file_disappears(tmp_path):
    path = tmp_path / "private" / "traffic_sensor_data.csv"
    path.parent.mkdir()
    write_dataset(path, [row("2024-01-01T00:00:00", "S1")])
    adapter = SmartCityTrafficCsvAdapter(path)
    path.unlink()

    with pytest.raises(DatasetSourceError) as error:
        next(adapter.iter_observations())
    assert str(path) not in str(error.value)


def test_adapter_rejects_file_changed_after_manifest_hash(tmp_path):
    path = tmp_path / "traffic_sensor_data.csv"
    write_dataset(path, [row("2024-01-01T00:00:00", "S1")])
    adapter = SmartCityTrafficCsvAdapter(path)
    write_dataset(path, [row("2024-01-01T00:00:00", "S1", 99)])

    with pytest.raises(DatasetSourceError, match="mudou depois da criação"):
        next(adapter.iter_observations())


def test_adapter_converts_invalid_utf8_to_controlled_source_error(tmp_path):
    path = tmp_path / "traffic_sensor_data.csv"
    path.write_bytes(b"timestamp,sensor_id\xff\n")

    with pytest.raises(DatasetSourceError, match="codificação UTF-8"):
        SmartCityTrafficCsvAdapter(path)


def test_adapter_rejects_missing_required_columns_and_unparseable_values(tmp_path):
    path = tmp_path / "traffic_sensor_data.csv"
    path.write_text("timestamp,sensor_id\n2024-01-01T00:00:00,S1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="ausentes:"):
        SmartCityTrafficCsvAdapter(path)

    write_dataset(path, [row("not-a-timestamp", "S1")])
    adapter = SmartCityTrafficCsvAdapter(path)
    with pytest.raises(ValueError, match="Timestamp inválido"):
        next(adapter.iter_observations())


def test_adapter_rejects_extra_headers_and_out_of_domain_values(tmp_path):
    path = tmp_path / "traffic_sensor_data.csv"
    write_dataset(path, [row("2024-01-01T00:00:00", "S1")])
    path.write_text(path.read_text(encoding="utf-8").replace("hour\n", "hour,unexpected\n"), encoding="utf-8")
    with pytest.raises(DatasetSourceError, match="inesperadas: unexpected"):
        SmartCityTrafficCsvAdapter(path)

    invalid_values = [
        ("vehicle_count", "-1"),
        ("occupancy_rate", "1.2"),
        ("day_of_week", "7"),
        ("is_holiday", "2"),
        ("hour", "24"),
    ]
    for field, value in invalid_values:
        invalid = row("2024-01-01T00:00:00", "S1")
        invalid[field] = value
        write_dataset(path, [invalid])
        with pytest.raises(DatasetSourceError, match="Valor inválido"):
            next(SmartCityTrafficCsvAdapter(path).iter_observations())


def test_replay_filters_time_location_and_observation_type(tmp_path):
    path = tmp_path / "traffic_sensor_data.csv"
    write_dataset(path, [
        row("2024-01-01T00:00:00", "S1"),
        row("2024-01-01T00:30:00", "S2"),
        row("2024-01-01T01:00:00", "S1"),
    ])
    source = SmartCityTrafficCsvAdapter(path)
    session = ReplaySession(
        "replay-test",
        source,
        ReplayFilters(
            start_at=datetime(2024, 1, 1, 0, 30),
            end_at=datetime(2024, 1, 1, 1, 0),
            location_ids=("S1",),
            observation_types=(ObservationType.TRAFFIC,),
        ),
        2.0,
    )

    emitted = session.step(10)
    assert len(emitted) == 1
    assert emitted[0].timestamp == datetime(2024, 1, 1, 1, 0)
    assert session.snapshot().emitted_count == 1
    assert session.snapshot().latest_by_location[0].source_id == "S1"
    assert session.status == ReplayStatus.COMPLETED


def test_replay_controls_pause_resume_reset_step_and_speed(tmp_path):
    path = tmp_path / "traffic_sensor_data.csv"
    write_dataset(path, [row("2024-01-01T00:00:00", "S1"), row("2024-01-01T00:30:00", "S1", 12)])
    manager = ReplayManager()
    created = manager.create(SmartCityTrafficCsvAdapter(path), observations_per_second=2.0)

    assert created.status == ReplayStatus.PAUSED
    stepped = manager.control(created.replay_id, "step", count=1)
    assert len(stepped) == 1
    assert manager.get(created.replay_id).emitted_count == 1
    manager.control(created.replay_id, "set_speed", observations_per_second=4.0)
    manager.control(created.replay_id, "resume")
    assert manager.get(created.replay_id).status == ReplayStatus.RUNNING
    with pytest.raises(ReplayControlError, match="pause o replay"):
        manager.control(created.replay_id, "step")
    manager.control(created.replay_id, "pause")
    assert manager.get(created.replay_id).status == ReplayStatus.PAUSED
    manager.control(created.replay_id, "reset")
    reset = manager.get(created.replay_id)
    assert reset.status == ReplayStatus.PAUSED
    assert reset.emitted_count == 0
    assert reset.latest_by_location == ()


def test_replay_timer_advances_deterministically_and_stops_after_pause(tmp_path, monkeypatch):
    path = tmp_path / "traffic_sensor_data.csv"
    write_dataset(path, [row("2024-01-01T00:00:00", "S1"), row("2024-01-01T00:30:00", "S1", 12)])
    timers = []

    class FakeTimer:
        def __init__(self, interval, function, args=()):
            self.interval = interval
            self.function = function
            self.args = args
            self.daemon = False

        def start(self):
            timers.append(self)

        def cancel(self):
            pass

    monkeypatch.setattr(replay_module, "Timer", FakeTimer)
    manager = ReplayManager()
    replay = manager.create(SmartCityTrafficCsvAdapter(path), observations_per_second=4.0)
    manager.control(replay.replay_id, "resume")
    assert timers[-1].interval == 0.25
    stale_timer = timers[-1]
    manager.control(replay.replay_id, "pause")
    manager.control(replay.replay_id, "resume")
    current_timer = timers[-1]
    stale_timer.function(*stale_timer.args)
    assert manager.get(replay.replay_id).emitted_count == 0
    assert manager._timers[replay.replay_id] is current_timer

    current_timer.function(*current_timer.args)
    assert manager.get(replay.replay_id).emitted_count == 1

    manager.control(replay.replay_id, "pause")
    timer_count = len(timers)
    timers[-1].function(*timers[-1].args)
    assert manager.get(replay.replay_id).status == ReplayStatus.PAUSED
    assert manager.get(replay.replay_id).emitted_count == 1
    assert len(timers) == timer_count


def test_replay_registry_is_bounded_and_evicts_only_non_running_sessions(tmp_path):
    path = tmp_path / "traffic_sensor_data.csv"
    write_dataset(path, [row("2024-01-01T00:00:00", "S1")])
    source = SmartCityTrafficCsvAdapter(path)
    manager = ReplayManager(max_sessions=1)
    first = manager.create(source)
    second = manager.create(source)

    with pytest.raises(ReplayNotFoundError):
        manager.get(first.replay_id)
    assert manager.get(second.replay_id).status == ReplayStatus.PAUSED

    running = manager.create(source)
    manager.control(running.replay_id, "resume")
    with pytest.raises(ReplayCapacityError):
        manager.create(source)
    manager.control(running.replay_id, "pause")


def test_stale_timer_callback_after_eviction_is_ignored(tmp_path, monkeypatch):
    path = tmp_path / "traffic_sensor_data.csv"
    write_dataset(path, [row("2024-01-01T00:00:00", "S1")])
    timers = []

    class FakeTimer:
        def __init__(self, interval, function, args=()):
            self.function = function
            self.args = args
            self.daemon = False

        def start(self):
            timers.append(self)

        def cancel(self):
            pass

    monkeypatch.setattr(replay_module, "Timer", FakeTimer)
    manager = ReplayManager(max_sessions=1)
    old = manager.create(SmartCityTrafficCsvAdapter(path))
    manager.control(old.replay_id, "resume")
    stale_timer = timers[-1]
    manager.control(old.replay_id, "pause")
    new = manager.create(SmartCityTrafficCsvAdapter(path))

    stale_timer.function(*stale_timer.args)
    assert manager.get(new.replay_id).status == ReplayStatus.PAUSED


def test_current_dataset_rejects_region_filter_without_verified_coordinates(tmp_path):
    path = tmp_path / "traffic_sensor_data.csv"
    write_dataset(path, [row("2024-01-01T00:00:00", "S1")])
    with pytest.raises(UnsupportedSourceFilter, match="coordenadas verificadas"):
        ReplayManager().create(
            SmartCityTrafficCsvAdapter(path),
            ReplayFilters(region=BoundingBox(
                min_longitude=106.0, min_latitude=-7.0, max_longitude=107.0, max_latitude=-6.0,
            )),
        )


def test_canonical_contract_rejects_partial_coordinates_but_keeps_unknown_fields_optional():
    with pytest.raises(ValueError, match="latitude e longitude"):
        TrafficObservation(
            observation_id="obs-1", timestamp=datetime(2024, 1, 1), source_id="S1", dataset_id="test",
            latitude=-6.2, provenance_kind=ProvenanceKind.UNKNOWN,
        )
    observation = TrafficObservation(
        observation_id="obs-2", timestamp=datetime(2024, 1, 1), source_id="S1", dataset_id="test",
        provenance_kind=ProvenanceKind.UNKNOWN,
    )
    assert observation.vehicle_count is None
    assert observation.flow_veh_h is None


def test_canonical_contract_freezes_nested_metadata():
    observation = TrafficObservation(
        observation_id="obs-3", timestamp=datetime(2024, 1, 1), source_id="S1", dataset_id="test",
        provenance_kind=ProvenanceKind.UNKNOWN,
        metadata={"nested": {"values": [1, 2]}},
    )
    with pytest.raises(TypeError, match="immutable"):
        observation.metadata["new"] = "value"
    with pytest.raises(TypeError, match="immutable"):
        observation.metadata["nested"]["new"] = "value"
    with pytest.raises(AttributeError):
        observation.metadata["nested"]["values"].append(3)
    payload = observation.model_dump(mode="json")
    assert payload["metadata"] == {"nested": {"values": [1, 2]}}
