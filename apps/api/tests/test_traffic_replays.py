from __future__ import annotations

import csv

from fastapi import HTTPException
from pydantic import ValidationError
import pytest

from app.main import app, city_metadata
from app import traffic_replays
from app.traffic_replays import (
    TrafficReplayControlRequest,
    TrafficReplayCreateRequest,
    control_traffic_replay,
    create_traffic_replay,
    get_traffic_replay_state,
)
from traffic_observations import ReplayManager


HEADERS = [
    "timestamp", "sensor_id", "location", "direction", "vehicle_count", "average_speed_kmh",
    "occupancy_rate", "congestion_level", "car_count", "motorcycle_count", "truck_count",
    "bus_count", "day_of_week", "is_holiday", "hour",
]


def write_dataset(path):
    rows = [
        {"timestamp": "2024-01-01T00:00:00", "sensor_id": "S1", "location": "A", "direction": "East",
         "vehicle_count": "10", "average_speed_kmh": "30", "occupancy_rate": "0.2", "congestion_level": "Low",
         "car_count": "9", "motorcycle_count": "1", "truck_count": "0", "bus_count": "0",
         "day_of_week": "0", "is_holiday": "0", "hour": "0"},
        {"timestamp": "2024-01-01T00:30:00", "sensor_id": "S1", "location": "A", "direction": "East",
         "vehicle_count": "12", "average_speed_kmh": "25", "occupancy_rate": "0.3", "congestion_level": "Medium",
         "car_count": "10", "motorcycle_count": "1", "truck_count": "1", "bus_count": "0",
         "day_of_week": "0", "is_holiday": "0", "hour": "0"},
    ]
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=HEADERS)
        writer.writeheader()
        writer.writerows(rows)


def test_api_routes_create_control_and_expose_separate_replay_state(tmp_path, monkeypatch):
    path = tmp_path / "traffic_sensor_data.csv"
    write_dataset(path)
    monkeypatch.setattr(traffic_replays, "_traffic_file_path", lambda: path)
    monkeypatch.setattr(traffic_replays, "_manager", ReplayManager())
    request = TrafficReplayCreateRequest.model_validate({
        "dataset_id": "kaggle:rauffauzanrambe/smart-city-traffic-flow-prediction-dataset",
        "observations_per_second": 10,
    })
    replay = create_traffic_replay(request)
    assert replay.status == "paused"
    assert replay.dataset.provenance_kind == "simulated"
    assert replay.emitted_count == 0

    advanced = control_traffic_replay(replay.replay_id, TrafficReplayControlRequest(action="step", count=1))
    assert advanced.advanced_observations[0].vehicle_count == 10
    assert advanced.replay.latest_by_location[0].latitude is None
    assert advanced.replay.latest_by_location[0].road_segment_id is None

    state = get_traffic_replay_state(replay.replay_id)
    assert state.emitted_count == 1
    city = city_metadata("aurora-base-v1")
    assert city.provenance == "synthetic"

    reset = control_traffic_replay(replay.replay_id, TrafficReplayControlRequest(action="reset"))
    assert reset.replay.latest_by_location == ()
    documented_paths = app.openapi()["paths"]
    assert "/api/v1/traffic-replays" in documented_paths
    assert "/api/v1/traffic-replays/{replay_id}/controls" in documented_paths


def test_api_rejects_region_filter_for_this_unverified_source(tmp_path, monkeypatch):
    path = tmp_path / "traffic_sensor_data.csv"
    write_dataset(path)
    monkeypatch.setattr(traffic_replays, "_traffic_file_path", lambda: path)
    monkeypatch.setattr(traffic_replays, "_manager", ReplayManager())

    request = TrafficReplayCreateRequest.model_validate({
        "filters": {"region": {
            "min_longitude": 106, "min_latitude": -7, "max_longitude": 107, "max_latitude": -6,
        }}
    })
    try:
        create_traffic_replay(request)
    except HTTPException as response:
        assert response.status_code == 422
        assert "coordenadas verificadas" in response.detail
    else:
        raise AssertionError("o filtro regional deveria ser rejeitado para esta fonte")


def test_api_reports_missing_local_dataset_without_accepting_arbitrary_paths(monkeypatch, tmp_path):
    monkeypatch.setattr(traffic_replays, "_traffic_file_path", lambda: tmp_path / "missing.csv")
    monkeypatch.setattr(traffic_replays, "_manager", ReplayManager())

    with pytest.raises(ValidationError):
        TrafficReplayCreateRequest.model_validate({
            "dataset_id": "kaggle:rauffauzanrambe/smart-city-traffic-flow-prediction-dataset",
            "path": "/etc/passwd",
        })
    missing = TrafficReplayCreateRequest.model_validate({
        "dataset_id": "kaggle:rauffauzanrambe/smart-city-traffic-flow-prediction-dataset",
    })
    try:
        create_traffic_replay(missing)
    except HTTPException as response:
        assert response.status_code == 503
        assert str(tmp_path) not in response.detail
    else:
        raise AssertionError("arquivo ausente deveria retornar 503")


def test_api_reports_malformed_optional_sidecar_as_client_error(monkeypatch, tmp_path):
    path = tmp_path / "traffic_sensor_data.csv"
    write_dataset(path)
    (tmp_path / "sensor_locations.json").write_text("[]", encoding="utf-8")
    monkeypatch.setattr(traffic_replays, "_traffic_file_path", lambda: path)
    monkeypatch.setattr(traffic_replays, "_manager", ReplayManager())

    with pytest.raises(HTTPException) as error:
        create_traffic_replay(TrafficReplayCreateRequest())
    assert error.value.status_code == 422


def test_api_reports_invalid_csv_encoding_as_client_error(monkeypatch, tmp_path):
    path = tmp_path / "traffic_sensor_data.csv"
    path.write_bytes(b"timestamp,sensor_id\xff\n")
    monkeypatch.setattr(traffic_replays, "_traffic_file_path", lambda: path)
    monkeypatch.setattr(traffic_replays, "_manager", ReplayManager())

    with pytest.raises(HTTPException) as error:
        create_traffic_replay(TrafficReplayCreateRequest())
    assert error.value.status_code == 422
