from urban_arena import build_simulation_input, create_agent_copies, generate_snapshot, load_city_config
from urban_arena.models import CityConfigFile


def test_snapshot_is_deterministic_and_balanced() -> None:
    config_a = load_city_config()
    config_b = load_city_config()
    snapshot_a = generate_snapshot(config_a)
    snapshot_b = generate_snapshot(config_b)

    assert snapshot_a.hash == snapshot_b.hash
    assert snapshot_a.population.total == config_a.population.total_residents
    assert snapshot_a.population.urban == config_a.population.urban_rural.urban_residents_derived
    assert snapshot_a.population.rural_catchment == config_a.population.urban_rural.rural_catchment_residents_derived
    assert snapshot_a.jobs == config_a.employment.total_jobs
    assert sum(d["residents"] for d in snapshot_a.districts) == snapshot_a.population.total
    assert sum(d["jobs"] for d in snapshot_a.districts) == snapshot_a.jobs
    assert sum(snapshot_a.commute_main_mode_share.values()) == 1
    assert sum(snapshot_a.finance[key] for key in ("fixed_operations", "reserve", "discretionary_budget")) == snapshot_a.finance["credits_per_round"]
    assert len(snapshot_a.layers["nodes"].features) == 25
    assert len(snapshot_a.layers["edges"].features) == config_a.mobility.network.directed_edges_derived == 74
    assert len(snapshot_a.layers["districts"].features) == len(config_a.districts)
    crossings = [feature for feature in snapshot_a.layers["edges"].features if "crossing_type" in feature.properties]
    assert len(crossings) == 2 * config_a.mobility.network.barrier.crossings
    assert {feature.properties["crossing_type"] for feature in crossings} == set(config_a.mobility.network.barrier.crossing_types)

    reordered = config_a.model_dump(mode="python")
    reordered["districts"] = tuple(reversed(reordered["districts"]))
    reordered["provenance"]["sources"] = tuple(reversed(reordered["provenance"]["sources"]))
    reordered["mobility"]["simulation_windows"] = tuple(reversed(reordered["mobility"]["simulation_windows"]))
    assert generate_snapshot(CityConfigFile.model_validate(reordered)).hash == snapshot_a.hash


def test_agent_copies_have_same_initial_hash_and_independent_nested_state() -> None:
    config = load_city_config()
    snapshot = generate_snapshot(config)
    copies = create_agent_copies(snapshot, config)

    assert len(copies) == config.arena.ai_agent_copies == 5
    assert {copy.hash for copy in copies} == {snapshot.hash}
    copies[0].layers["districts"].features[0].properties["residents"] = -1
    assert copies[1].layers["districts"].features[0].properties["residents"] >= 0
    assert snapshot.layers["districts"].features[0].properties["residents"] >= 0


def test_local_features_are_stable_and_synthetic() -> None:
    snapshot = generate_snapshot(load_city_config())
    for layer in snapshot.layers.values():
        assert layer.type == "LocalFeatureCollection"
        assert layer.coordinate_space == "synthetic_local_cartesian_m"
        assert [feature.id for feature in layer.features] == sorted(feature.id for feature in layer.features)
        assert all(feature.properties["synthetic"] is True for feature in layer.features)
        assert all(feature.properties["provenance_kind"] == "synthetic_generated" for feature in layer.features)
    assert snapshot.bounds_m == (0, 0, 6000, 6000)
    for feature in (item for layer in snapshot.layers.values() for item in layer.features):
        geometry = feature.geometry
        assert geometry.type in {"Point", "LineString", "Polygon"}
        flat_points = [geometry.coordinates] if geometry.type == "Point" else geometry.coordinates
        if geometry.type == "Polygon":
            flat_points = geometry.coordinates[0]
        elif geometry.type == "LineString":
            flat_points = geometry.coordinates
        assert all(0 <= point[0] <= snapshot.bounds_m[2] and 0 <= point[1] <= snapshot.bounds_m[3] for point in flat_points)


def test_simulation_input_is_versioned_complete_and_window_scoped() -> None:
    config = load_city_config()
    snapshot = generate_snapshot(config)
    engine_input = build_simulation_input(config, snapshot, "weekday_am_peak")
    serialized = engine_input.model_dump(mode="json")

    assert serialized["contract_version"] == "1.0"
    assert serialized["snapshot_id"] == snapshot.snapshot_id
    assert serialized["provenance"] == "synthetic"
    assert serialized["seed"] == 42
    assert serialized["window"]["duration_seconds"] == 7200
    assert len(serialized["nodes"]) == 25
    assert len(serialized["roads"]) == 74
    assert len(serialized["traffic_signals"]) == 2
    assert len(serialized["demand"]) == 4
    assert {road["road_class"] for road in serialized["roads"]} == {"local", "collector", "arterial"}
    assert all(road["speed_limit_kmh"] > 0 and road["lanes"] > 0 for road in serialized["roads"])
    assert {road["crossing_type"] for road in serialized["roads"] if road["crossing_type"]} == {
        "arterial_bridge",
        "lower_capacity_collector",
    }
    assert build_simulation_input(config, snapshot, "weekday_off_peak").demand[0].id == "off-od-001"


def test_invalid_demand_reference_fails_typed_config_validation() -> None:
    raw = load_city_config().model_dump(mode="python")
    raw["mobility"]["demand"]["windows"][0]["od_flows"][0]["from_node"] = "node:99:99"

    try:
        CityConfigFile.model_validate(raw)
    except ValueError as exc:
        assert "OD am-od-001 referencia nó inexistente" in str(exc)
    else:
        raise AssertionError("referência de demanda inválida deveria falhar")
