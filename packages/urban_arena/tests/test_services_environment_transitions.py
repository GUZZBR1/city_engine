from __future__ import annotations

import copy

import pytest
from urban_arena import generate_snapshot, load_city_config
from urban_arena.manifest import build_aurora_synthetic_v1_manifest
from urban_arena.state import (
    CityState,
    DomainDelta,
    EnvironmentState,
    PopulationState,
    StateFactory,
)
from urban_arena.transitions import (
    aggregate_urban_green_area,
    estimate_annual_co2e,
    transition_environment,
    transition_services,
    urban_green_area_per_resident,
)


def _inputs():
    config = load_city_config()
    snapshot = generate_snapshot(config)
    manifest = build_aurora_synthetic_v1_manifest(config, snapshot, experiment_id="transition-test")
    state = StateFactory.from_snapshot(snapshot, manifest=manifest, instance_id="city-1")
    return manifest, state


def _candidate(
    parent: CityState,
    round_index: int,
    *,
    population_changes: dict[str, int] | None = None,
) -> CityState:
    candidate = StateFactory.candidate(parent, round_index=round_index)
    residents = dict(candidate.population.residents_by_district)
    residents.update(population_changes or {})
    urban_ids = set(parent.housing.units_by_district)
    urban_residents = sum(residents[district_id] for district_id in urban_ids)
    rural_residents = sum(value for district_id, value in residents.items() if district_id not in urban_ids)
    population = PopulationState(
        residents_by_district=residents,
        total_residents=urban_residents + rural_residents,
        urban_residents=urban_residents,
        rural_catchment_residents=rural_residents,
    )
    values = candidate.model_dump(mode="python")
    values["population"] = population
    return CityState.model_validate(values)


def _apply(candidate: CityState, delta: DomainDelta) -> CityState:
    values = candidate.model_dump(mode="python")
    values[delta.domain] = copy.deepcopy(delta.values)
    return CityState.model_validate(values)


def test_services_recalculate_candidate_demand_and_preserve_typed_capacity() -> None:
    manifest, parent = _inputs()
    candidate = _candidate(parent, 1, population_changes={"centro": parent.population.residents_by_district["centro"] + 100})
    before = parent.model_dump(mode="python")

    delta = transition_services(parent, candidate, manifest)
    updated = _apply(candidate, delta)

    assert delta.domain == "services"
    assert set(delta.values) == {"school", "primary_health"}
    assert "entorno_rural" not in delta.values["school"]["demand_by_district"]
    assert "entorno_rural" not in delta.values["primary_health"]["capacity_by_district"]
    assert delta.values["school"]["demand_by_district"]["centro"] == pytest.approx(
        candidate.population.residents_by_district["centro"] * manifest.parameters.services.school.eligible_share
    )
    assert delta.values["school"]["capacity_by_district"] == parent.services.school.capacity_by_district
    assert delta.values["primary_health"]["demand_by_district"]["centro"] == pytest.approx(
        candidate.population.residents_by_district["centro"] * manifest.parameters.services.health.annual_visits_per_resident
    )
    assert updated.services.school.demand_by_district == delta.values["school"]["demand_by_district"]
    assert parent.model_dump(mode="python") == before


def test_service_capacity_carries_forward_and_zero_population_has_zero_demand() -> None:
    manifest, parent = _inputs()
    first_candidate = _candidate(parent, 1)
    first = _apply(first_candidate, transition_services(parent, first_candidate, manifest))
    second_candidate = _candidate(first, 2, population_changes={"centro": 0})
    delta = transition_services(first, second_candidate, manifest)

    assert delta.values["school"]["capacity_by_district"] == first.services.school.capacity_by_district
    assert delta.values["school"]["demand_by_district"]["centro"] == 0


def test_environment_transition_preserves_typed_green_area_stock() -> None:
    manifest, parent = _inputs()
    candidate = _candidate(parent, 1)
    delta = transition_environment(parent, candidate, manifest)
    updated = _apply(candidate, delta)

    assert delta.domain == "environment"
    assert delta.values["public_green_area_m2_by_district"] == parent.environment.public_green_area_m2_by_district
    assert updated.environment.public_green_area_m2_by_district == parent.environment.public_green_area_m2_by_district
    assert "entorno_rural" not in delta.values["public_green_area_m2_by_district"]


def test_aggregate_green_area_uses_only_configured_urban_districts() -> None:
    manifest, parent = _inputs()

    value, reason = aggregate_urban_green_area(parent, manifest)

    assert reason is None
    assert value == pytest.approx(sum(parent.environment.public_green_area_m2_by_district.values()))
    ratio, ratio_reason = urban_green_area_per_resident(parent, manifest)
    assert ratio_reason is None
    assert ratio == pytest.approx(value / parent.population.urban_residents)


def test_green_area_per_resident_returns_not_applicable_for_zero_denominator() -> None:
    manifest, parent = _inputs()
    urban_ids = set(parent.housing.units_by_district)
    residents = PopulationState.model_construct(
        residents_by_district={
            district_id: 0 if district_id in urban_ids else value
            for district_id, value in parent.population.residents_by_district.items()
        },
        total_residents=parent.population.rural_catchment_residents,
        urban_residents=0,
        rural_catchment_residents=parent.population.rural_catchment_residents,
    )
    empty_urban_state = CityState.model_construct(**{**parent.__dict__, "population": residents})

    value, reason = urban_green_area_per_resident(empty_urban_state, manifest)

    assert value is None
    assert reason == "not_applicable"


def test_green_area_aggregate_returns_null_for_missing_inventory_entry() -> None:
    manifest, parent = _inputs()
    incomplete_environment = EnvironmentState.model_construct(
        public_green_area_m2_by_district={
            district_id: area
            for district_id, area in parent.environment.public_green_area_m2_by_district.items()
            if district_id != "centro"
        }
    )
    incomplete_state = CityState.model_construct(**{**parent.__dict__, "environment": incomplete_environment})

    value, reason = aggregate_urban_green_area(incomplete_state, manifest)
    ratio, ratio_reason = urban_green_area_per_resident(incomplete_state, manifest)

    assert value is None
    assert reason == "missing_input"
    assert ratio is None
    assert ratio_reason == "missing_input"


def test_co2e_uses_exogenous_annual_activity_and_excludes_rural_population() -> None:
    manifest, parent = _inputs()
    urban_ids = set(parent.housing.units_by_district)
    residents_by_district = parent.population.residents_by_district
    expected = sum(
        residents_by_district[district_id]
        * manifest.parameters.emissions.annual_vehicle_km_per_resident
        * manifest.parameters.emissions.co2e_kg_per_vehicle_km
        for district_id in urban_ids
    )

    total, reason = estimate_annual_co2e(parent, manifest)
    centro, district_reason = estimate_annual_co2e(parent, manifest, district_id="centro")
    rural, rural_reason = estimate_annual_co2e(parent, manifest, district_id="entorno_rural")

    assert total == pytest.approx(expected)
    assert reason is None
    assert centro == pytest.approx(
        residents_by_district["centro"]
        * manifest.parameters.emissions.annual_vehicle_km_per_resident
        * manifest.parameters.emissions.co2e_kg_per_vehicle_km
    )
    assert district_reason is None
    assert rural is None
    assert rural_reason == "unknown_coverage"


def test_co2e_nulls_missing_district_input_with_reason() -> None:
    manifest, parent = _inputs()
    population = PopulationState.model_construct(
        residents_by_district={
            district_id: residents
            for district_id, residents in parent.population.residents_by_district.items()
            if district_id != "centro"
        },
        total_residents=parent.population.total_residents,
        urban_residents=parent.population.urban_residents,
        rural_catchment_residents=parent.population.rural_catchment_residents,
    )
    incomplete_state = CityState.model_construct(
        **{**parent.__dict__, "population": population}
    )

    value, reason = estimate_annual_co2e(incomplete_state, manifest)
    district_value, district_reason = estimate_annual_co2e(incomplete_state, manifest, district_id="centro")

    assert value is None
    assert reason == "missing_input"
    assert district_value is None
    assert district_reason == "missing_input"


def test_transition_rejects_candidate_with_wrong_parent_hash() -> None:
    manifest, parent = _inputs()
    values = _candidate(parent, 1).model_dump(mode="python")
    values["parent_city_state_hash"] = "0" * 64
    wrong_parent = CityState.model_validate(values)

    with pytest.raises(ValueError, match="como pai"):
        transition_environment(parent, wrong_parent, manifest)


def test_transition_rejects_incomplete_urban_parameter_coverage() -> None:
    manifest, parent = _inputs()
    raw = manifest.model_dump(mode="python")
    raw["parameters"]["green"]["public_area_m2_per_resident"].pop("oeste_verde")
    incomplete_manifest = type(manifest).model_validate(raw)
    candidate = _candidate(parent, 1)

    with pytest.raises(ValueError, match="mesmo conjunto completo"):
        transition_services(parent, candidate, incomplete_manifest)
