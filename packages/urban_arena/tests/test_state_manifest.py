from __future__ import annotations

import copy
import math

import pytest
from pydantic import ValidationError
from urban_arena import generate_snapshot, load_city_config
from urban_arena.manifest import ExperimentManifest, build_aurora_synthetic_v1_manifest
from urban_arena.state import (
    CityState,
    CityStateDelta,
    DomainDelta,
    EffectiveEvent,
    StateFactory,
    StateTransitionResult,
    canonical_hash,
    canonical_json,
)


def _inputs():
    config = load_city_config()
    snapshot = generate_snapshot(config)
    return config, snapshot


def _manifest(config, snapshot, *, experiment_id="exp-1"):
    return build_aurora_synthetic_v1_manifest(config, snapshot, experiment_id=experiment_id)


def test_state_factory_materializes_evolutive_state_without_changing_snapshot() -> None:
    config, snapshot = _inputs()
    manifest = _manifest(config, snapshot)
    snapshot_before = snapshot.model_dump(mode="json")

    state = StateFactory.from_snapshot(snapshot, manifest=manifest, instance_id="city-1")

    assert isinstance(state, CityState)
    assert state.experiment_id == "exp-1"
    assert state.instance_id == "city-1"
    assert state.round_index == 0
    assert state.snapshot_hash == snapshot.hash
    assert state.parent_city_state_hash is None
    assert state.population.residents_by_district == {district["id"]: district["residents"] for district in snapshot.districts}
    assert state.population.total_residents == 67250
    assert state.population.urban_residents == 58783
    assert state.population.rural_catchment_residents == 8467
    assert state.employment.jobs_by_district == {district["id"]: district["jobs"] for district in snapshot.districts}
    assert state.employment.total_jobs == 24000
    assert state.housing.occupied_households_reference_total == 24104
    assert state.housing.occupied_households_urban == 21069
    assert state.housing.total_units == 22178
    assert sum(state.housing.units_by_district.values()) == state.housing.total_units
    assert "entorno_rural" not in state.housing.units_by_district
    assert state.services.school.demand_by_district["centro"] == pytest.approx(8817 * 0.18)
    assert state.services.school.capacity_by_district["centro"] == pytest.approx(8817 * 0.16)
    assert state.services.primary_health.demand_by_district["centro"] == pytest.approx(8817 * 2.4)
    assert state.services.primary_health.capacity_by_district["centro"] == pytest.approx(8817 * 2.0)
    assert state.environment.public_green_area_m2_by_district["centro"] == pytest.approx(8817 * 2.0)
    assert state.budget.credits_per_round == 100
    assert state.budget.fixed_operations + state.budget.reserve + state.budget.discretionary_budget == 100
    assert state.city_state_hash == canonical_hash(state.payload())
    assert snapshot.model_dump(mode="json") == snapshot_before


def test_state_factory_copies_and_candidates_do_not_share_nested_collections() -> None:
    config, snapshot = _inputs()
    manifest = _manifest(config, snapshot)
    copies = StateFactory.copies(
        snapshot,
        manifest=manifest,
        instance_ids=["city-1", "city-2", "city-3", "city-4", "city-5"],
    )
    initial_hash = copies[0].city_state_hash
    assert len(copies) == 5
    assert {state.city_state_hash for state in copies} == {initial_hash}

    copies[0].housing.units_by_district["centro"] = -1
    copies[0].services.school.demand_by_district["centro"] = -1
    assert copies[1].housing.units_by_district["centro"] >= 0
    assert copies[1].services.school.demand_by_district["centro"] >= 0
    assert copies[0].city_state_hash != copies[1].city_state_hash

    parent = copies[1]
    candidate = StateFactory.candidate(parent, round_index=1)
    candidate.environment.public_green_area_m2_by_district["centro"] += 1
    candidate.services.primary_health.capacity_by_district["centro"] += 1
    assert candidate.parent_city_state_hash == parent.city_state_hash
    assert candidate.round_index == 1
    assert candidate.environment.public_green_area_m2_by_district["centro"] != parent.environment.public_green_area_m2_by_district["centro"]
    assert candidate.services.primary_health.capacity_by_district["centro"] != parent.services.primary_health.capacity_by_district["centro"]
    assert candidate.city_state_hash != parent.city_state_hash


def test_candidate_requires_forward_round_index() -> None:
    config, snapshot = _inputs()
    parent = StateFactory.from_snapshot(snapshot, manifest=_manifest(config, snapshot), instance_id="city-1")

    with pytest.raises(ValueError, match="round_index"):
        StateFactory.candidate(parent, round_index=0)


def test_state_hash_tracks_content_but_not_experiment_instance_or_round_metadata() -> None:
    config, snapshot = _inputs()
    first = StateFactory.from_snapshot(snapshot, manifest=_manifest(config, snapshot), instance_id="city-1")
    second = StateFactory.from_snapshot(snapshot, manifest=_manifest(config, snapshot, experiment_id="exp-2"), instance_id="city-2")
    later = StateFactory.candidate(first, round_index=1)

    assert first.city_state_hash == second.city_state_hash == later.city_state_hash
    changed = copy.deepcopy(first.model_dump(mode="python"))
    changed["environment"]["public_green_area_m2_by_district"]["centro"] += 1
    changed_state = CityState.model_validate(changed)
    assert changed_state.city_state_hash != first.city_state_hash


def test_manifest_materializes_the_versioned_aurora_synthetic_profile() -> None:
    config, snapshot = _inputs()
    snapshot_before = snapshot.model_dump(mode="json")

    manifest = build_aurora_synthetic_v1_manifest(config, snapshot, experiment_id="exp-1")
    params = manifest.model_dump(mode="python")["parameters"]

    assert manifest.profile_id == "aurora_synthetic_v1"
    assert manifest.profile_version == "1.0"
    assert manifest.horizon_rounds == 10
    assert manifest.snapshot_id == snapshot.snapshot_id
    assert manifest.snapshot_hash == snapshot.hash
    assert manifest.generator_version
    assert manifest.transition_version
    assert manifest.catalog_version
    assert manifest.rules_version
    assert manifest.provenance == "synthetic_config"
    assert manifest.seeds["mobility_demand"] == 42
    assert params["demography"] == {
        "birth_rate": 0.012,
        "death_rate": 0.008,
        "net_migration_rate": 0.002,
        "urban_net_migration_share": 0.8,
        "household_size": 2.79,
    }
    assert params["housing"]["vacancy_rate_target"] == 0.05
    assert params["housing"]["annual_capacity_rate"] == 0.02
    assert params["housing"]["annual_retirement_rate"] == 0.003
    assert params["housing"]["initial_units"] is None
    assert params["employment"]["annual_growth_rate"] == 0.01
    assert sum(params["employment"]["district_allocation"].values()) == pytest.approx(1.0)
    assert params["services"] == {
        "school": {"eligible_share": 0.18, "initial_seats_per_resident": 0.16},
        "health": {"annual_visits_per_resident": 2.4, "initial_visits_per_resident_year": 2.0},
    }
    assert params["green"]["public_area_m2_per_resident"] == {
        "centro": 2.0,
        "norte_residencial": 4.0,
        "sul_misto": 3.0,
        "leste_logistico": 1.0,
        "oeste_verde": 8.0,
    }
    assert params["emissions"] == {
        "annual_vehicle_km_per_resident": 2500.0,
        "co2e_kg_per_vehicle_km": 0.18,
        "activity_scope": "exogenous_urban_resident_vehicle_km_per_year",
    }
    assert snapshot.model_dump(mode="json") == snapshot_before


def test_manifest_hash_is_deterministic_and_sensitive_to_materialized_content() -> None:
    config, snapshot = _inputs()
    left = build_aurora_synthetic_v1_manifest(config, snapshot, experiment_id="exp-1")
    right = build_aurora_synthetic_v1_manifest(config, snapshot, experiment_id="exp-1")

    assert left.manifest_hash == right.manifest_hash
    changed = left.model_dump(mode="python")
    changed["parameters"]["demography"]["birth_rate"] += 0.001
    assert ExperimentManifest.model_validate(changed).manifest_hash != left.manifest_hash


def test_manifest_rejects_horizon_beyond_contract_and_missing_materialization() -> None:
    config, snapshot = _inputs()
    with pytest.raises(ValidationError):
        build_aurora_synthetic_v1_manifest(
            config, snapshot, experiment_id="exp-1", horizon_rounds=11
        )

    manifest = build_aurora_synthetic_v1_manifest(config, snapshot, experiment_id="exp-1")
    incomplete = manifest.model_dump(mode="python")
    incomplete["parameters"] = {}
    with pytest.raises(ValidationError):
        ExperimentManifest.model_validate(incomplete)


def test_state_factory_uses_housing_parameters_from_manifest() -> None:
    config, snapshot = _inputs()
    baseline = _manifest(config, snapshot)
    configured = baseline.model_dump(mode="python")
    configured["parameters"]["housing"]["initial_units"] = 23000
    custom_manifest = ExperimentManifest.model_validate(configured)

    state = StateFactory.from_snapshot(snapshot, manifest=custom_manifest, instance_id="city-1")

    assert state.housing.total_units == 23000
    assert sum(state.housing.units_by_district.values()) == 23000


def test_state_factory_uses_manifest_household_size_and_vacancy_when_deriving_units() -> None:
    config, snapshot = _inputs()
    configured = _manifest(config, snapshot).model_dump(mode="python")
    configured["parameters"]["demography"]["household_size"] = 3.0
    configured["parameters"]["housing"]["vacancy_rate_target"] = 0.10
    manifest = ExperimentManifest.model_validate(configured)

    state = StateFactory.from_snapshot(snapshot, manifest=manifest, instance_id="city-1")

    expected_occupied = math.floor(snapshot.population.urban / 3.0 + 0.5)
    assert state.housing.occupied_households_urban == expected_occupied
    assert state.housing.vacancy_rate_target == 0.10
    assert state.housing.total_units == math.ceil(expected_occupied / 0.90)


def test_state_factory_rejects_manifest_for_different_snapshot() -> None:
    config, snapshot = _inputs()
    manifest = _manifest(config, snapshot)
    changed = manifest.model_dump(mode="python")
    changed["snapshot_hash"] = "0" * 64
    mismatched = ExperimentManifest.model_validate(changed)

    with pytest.raises(ValueError, match="snapshot"):
        StateFactory.from_snapshot(snapshot, manifest=mismatched, instance_id="city-1")


def test_state_factory_rejects_nested_snapshot_mutation_after_manifest_creation() -> None:
    config, snapshot = _inputs()
    manifest = _manifest(config, snapshot)
    snapshot.layers["districts"].features[0].properties["residents"] += 1

    with pytest.raises(ValueError, match="hash declarado"):
        StateFactory.from_snapshot(snapshot, manifest=manifest, instance_id="city-1")


def test_effective_event_requires_round_inside_contract_horizon() -> None:
    event = EffectiveEvent(
        event_id="event-1",
        event_type="housing_capacity",
        effective_round=10,
        payload={"units": 10},
    )
    assert event.effective_round == 10

    for invalid_round in (0, 11):
        with pytest.raises(ValidationError):
            EffectiveEvent(
                event_id="event-invalid",
                event_type="housing_capacity",
                effective_round=invalid_round,
                payload={},
            )


def test_city_state_delta_rejects_duplicate_domain_entries() -> None:
    with pytest.raises(ValidationError, match="mesmo domínio"):
        CityStateDelta(
            parent_city_state_hash="a" * 64,
            domains=(
                DomainDelta(domain="services", values={"schools": 1}),
                DomainDelta(domain="services", values={"clinics": 1}),
            ),
        )


def test_not_run_transition_result_has_no_domain_delta_and_matches_candidate_identity() -> None:
    config, snapshot = _inputs()
    manifest = _manifest(config, snapshot)
    parent = StateFactory.from_snapshot(snapshot, manifest=manifest, instance_id="city-1")
    candidate = StateFactory.candidate(parent, round_index=1)
    delta = CityStateDelta(parent_city_state_hash=parent.city_state_hash)

    result = StateTransitionResult(
        experiment_id=manifest.experiment_id,
        instance_id="city-1",
        round_index=1,
        manifest_hash=manifest.manifest_hash,
        parent_city_state_hash=parent.city_state_hash,
        city_state_hash=candidate.city_state_hash,
        domain_transition="not_run",
        delta=delta,
        candidate_state=candidate,
    )

    assert result.domain_transition == "not_run"
    assert result.delta.domains == ()
    assert result.candidate_state.city_state_hash == result.city_state_hash
    assert result.candidate_state.parent_city_state_hash == result.parent_city_state_hash

    with pytest.raises(ValidationError, match="not_run"):
        StateTransitionResult(
            experiment_id=manifest.experiment_id,
            instance_id="city-1",
            round_index=1,
            manifest_hash=manifest.manifest_hash,
            parent_city_state_hash=parent.city_state_hash,
            city_state_hash=candidate.city_state_hash,
            domain_transition="not_run",
            delta=CityStateDelta(
                parent_city_state_hash=parent.city_state_hash,
                domains=(DomainDelta(domain="services", values={"schools": 1}),),
            ),
            candidate_state=candidate,
        )


def test_transition_result_rejects_mismatched_candidate_hash() -> None:
    config, snapshot = _inputs()
    manifest = _manifest(config, snapshot)
    parent = StateFactory.from_snapshot(snapshot, manifest=manifest, instance_id="city-1")
    candidate = StateFactory.candidate(parent, round_index=1)
    with pytest.raises(ValidationError, match="city_state_hash"):
        StateTransitionResult(
            experiment_id=manifest.experiment_id,
            instance_id="city-1",
            round_index=1,
            manifest_hash=manifest.manifest_hash,
            parent_city_state_hash=parent.city_state_hash,
            city_state_hash="0" * 64,
            domain_transition="applied",
            delta=CityStateDelta(parent_city_state_hash=parent.city_state_hash),
            candidate_state=candidate,
        )


def test_canonical_json_orders_keys_and_rejects_non_finite_values() -> None:
    assert canonical_json({"b": 2, "a": "á"}) == canonical_json({"a": "á", "b": 2})
    assert canonical_hash({"b": 2, "a": "á"}) == canonical_hash({"a": "á", "b": 2})
    with pytest.raises(ValueError):
        canonical_json({"invalid": float("nan")})
