from __future__ import annotations

import pytest
from urban_arena import generate_snapshot, load_city_config
from urban_arena.manifest import build_aurora_synthetic_v1_manifest
from urban_arena.state import CityState, CityStateDelta, StateFactory
from urban_arena.transitions.employment import (
    calculate_employment,
    transition_employment,
)
from urban_arena.transitions.housing import (
    calculate_housing,
    initialize_urban_housing,
    transition_housing,
)
from urban_arena.transitions.population import (
    calculate_population,
    transition_population,
)


def test_population_transition_is_repeatable_and_balanced() -> None:
    inputs = (
        (("b", 1_000), ("a", 2_000)),
        500,
    )
    kwargs = {
        "birth_rate": "0.012",
        "death_rate": "0.008",
        "net_migration_rate": "0.002",
        "urban_net_migration_share": "0.8",
    }
    first = calculate_population(*inputs, **kwargs)
    second = calculate_population(*inputs, **kwargs)
    assert first == second
    (
        districts,
        rural,
        (
            urban_births,
            urban_deaths,
            rural_births,
            rural_deaths,
            migration,
            urban_migration,
            rural_migration,
            urban_applied,
            rural_applied,
            blocked,
        ),
    ) = first
    assert (
        sum(value for _, value in districts)
        == 3_000 + urban_births - urban_deaths + urban_applied
    )
    assert rural == 500 + rural_births - rural_deaths + rural_applied
    assert migration == urban_migration + rural_migration
    assert migration == urban_applied + rural_applied + blocked
    assert urban_births == 36 and urban_deaths == 24
    assert rural_births == 6 and rural_deaths == 4


def test_negative_migration_is_capped_to_prevent_negative_population() -> None:
    districts, rural, flows = calculate_population(
        (("district", 1),),
        0,
        birth_rate=0,
        death_rate=0,
        net_migration_rate=-1,
        urban_net_migration_share=1,
    )
    assert districts == (("district", 0),)
    assert rural == 0
    assert flows[4:] == (-1, -1, 0, -1, 0, 0)


def test_rural_migration_cap_uses_population_after_births_and_deaths() -> None:
    _, rural, flows = calculate_population(
        (("district", 0),),
        1,
        birth_rate=1,
        death_rate=0,
        net_migration_rate=-2,
        urban_net_migration_share=0,
    )
    assert rural == 0
    assert flows[6:] == (-2, 0, -2, 0)


def test_rural_migration_caps_hold_across_stock_rate_and_migration_cases() -> None:
    for rural in (1, 2, 11, 250):
        for birth_rate in (0, 0.05, 0.5, 1):
            for death_rate in (0, 0.03, 0.25, 1):
                for migration_rate in (-0.1, -1, -3):
                    _, next_rural, flows = calculate_population(
                        (("urban", 0),),
                        rural,
                        birth_rate=birth_rate,
                        death_rate=death_rate,
                        net_migration_rate=migration_rate,
                        urban_net_migration_share=0,
                    )
                    natural = rural + flows[2] - flows[3]
                    applied = flows[8]
                    blocked = flows[9]
                    assert applied >= -natural
                    assert next_rural == natural + applied >= 0
                    assert flows[4] == flows[5] + flows[6]
                    assert flows[4] == flows[7] + flows[8] + blocked


def test_initial_housing_uses_synthetic_urban_derivation_and_largest_remainders() -> (
    None
):
    occupied, stock, allocation = initialize_urban_housing(
        (("b", 20_000), ("a", 38_783)),
        household_size=2.79,
        vacancy_rate_target=0.05,
    )
    assert occupied == 21_069
    assert stock == 22_178
    assert sum(units for _, units in allocation) == stock
    assert dict(allocation)["a"] + dict(allocation)["b"] == stock


def test_housing_shortfall_does_not_change_population_and_capacity_is_bounded() -> None:
    result = calculate_housing(
        10_000,
        100,
        100,
        household_size=2,
        vacancy_rate_target=0.05,
        annual_capacity_rate=0.02,
        annual_retirement_rate=0.003,
    )
    need, retired, capacity, built, next_stock, unmet = result
    assert need == 5_000
    assert retired == 0
    assert capacity == 2
    assert built == 2
    assert next_stock == 102
    assert unmet > 0


def test_housing_annual_capacity_rate_can_exceed_one() -> None:
    _, _, capacity, built, next_stock, _ = calculate_housing(
        10_000,
        0,
        100,
        household_size=2,
        vacancy_rate_target=0.05,
        annual_capacity_rate=1.5,
        annual_retirement_rate=0,
    )
    assert capacity == built == next_stock == 150


@pytest.mark.parametrize(
    ("growth", "expected"),
    [("-0.5", 5), ("0", 10), ("0.5", 15)],
)
def test_employment_growth_and_external_zero(growth: str, expected: int) -> None:
    district_jobs, before, after, net = calculate_employment(
        (("b", "urban", 5), ("a", "urban", 5), ("rural", "external_catchment", 0)),
        annual_growth_rate=growth,
    )
    assert before == 10
    assert after == expected
    assert net == expected - 10
    assert sum(jobs for _, jobs in district_jobs) == expected
    assert dict(district_jobs)["rural"] == 0


def test_employment_remainder_tie_uses_lexicographic_district_id() -> None:
    districts, _, after, _ = calculate_employment(
        (("z", "urban", 1), ("a", "urban", 0)),
        annual_growth_rate=0,
        district_allocation=(("z", "0.5"), ("a", "0.5")),
    )
    assert after == 1
    assert dict(districts) == {"z": 0, "a": 1}


def test_invalid_null_and_nonfinite_parameters_fail() -> None:
    with pytest.raises(ValueError, match="birth_rate"):
        calculate_population(
            (("a", 1),),
            0,
            birth_rate=None,
            death_rate=0,
            net_migration_rate=0,
            urban_net_migration_share=0.8,
        )
    with pytest.raises(ValueError, match="vacancy_rate_target"):
        initialize_urban_housing((("a", 10),), household_size=2, vacancy_rate_target=1)
    with pytest.raises(ValueError, match="annual_growth_rate"):
        calculate_employment((("a", "urban", 1),), annual_growth_rate=float("nan"))


def test_public_transitions_accept_factory_state_and_v1_manifest() -> None:
    config = load_city_config()
    snapshot = generate_snapshot(config)
    manifest = build_aurora_synthetic_v1_manifest(
        config, snapshot, experiment_id="annual-test"
    )
    parent = StateFactory.from_snapshot(
        snapshot, manifest=manifest, instance_id="city-1"
    )

    population_delta = transition_population(parent, manifest)
    employment_delta = transition_employment(parent, manifest)
    assert isinstance(population_delta, CityStateDelta)
    assert isinstance(employment_delta, CityStateDelta)
    assert population_delta.parent_city_state_hash == parent.city_state_hash
    assert employment_delta.parent_city_state_hash == parent.city_state_hash
    assert population_delta.domains[0].domain == "population"
    assert employment_delta.domains[0].domain == "employment"
    assert population_delta.effective_events[0].effective_round == 1
    assert (
        population_delta.effective_events
        == transition_population(parent, manifest).effective_events
    )
    assert employment_delta.effective_events[0].effective_round == 1

    housing_delta = transition_housing(parent, manifest, population_delta)
    assert housing_delta.parent_city_state_hash == parent.city_state_hash
    assert housing_delta.domains[0].domain == "housing"
    housing_values = housing_delta.domains[0].values
    assert housing_values["total_units"] >= 0
    assert housing_values["total_units"] != parent.housing.total_units
    assert (
        sum(housing_values["units_by_district"].values())
        == housing_values["total_units"]
    )
    assert housing_delta.effective_events[0].effective_round == 1
    assert (
        housing_delta.effective_events
        == transition_housing(parent, manifest, population_delta).effective_events
    )
    stale_population_delta = population_delta.model_copy(
        update={"parent_city_state_hash": "0" * 64}
    )
    with pytest.raises(ValueError, match="estado pai recebido"):
        transition_housing(parent, manifest, stale_population_delta)
    same_content_next_round = StateFactory.candidate(parent, round_index=1)
    assert same_content_next_round.city_state_hash == parent.city_state_hash
    with pytest.raises(ValueError, match="evento demográfico da rodada"):
        transition_housing(same_content_next_round, manifest, population_delta)
    flows = population_delta.effective_events[0].payload
    population_values = population_delta.domains[0].values
    assert sum(population_values["residents_by_district"].values()) == (
        parent.population.total_residents
        + flows["urban_births"]
        + flows["rural_births"]
        - flows["urban_deaths"]
        - flows["rural_deaths"]
        + flows["urban_migration_applied"]
        + flows["rural_migration_applied"]
    )

    candidate = StateFactory.candidate(parent, round_index=1)
    candidate_values = candidate.model_dump(mode="python")
    candidate_values["population"] = population_delta.domains[0].values
    candidate_values["employment"] = employment_delta.domains[0].values
    candidate_values["housing"] = housing_values
    candidate = CityState.model_validate(candidate_values)
    assert candidate.parent_city_state_hash == parent.city_state_hash
    assert candidate.population.model_dump() == population_values
    assert candidate.employment.model_dump() == employment_delta.domains[0].values
    assert population_values != parent.population.model_dump()

    second_population_delta = transition_population(candidate, manifest)
    second_housing_delta = transition_housing(
        candidate, manifest, second_population_delta
    )
    assert second_housing_delta.effective_events[0].effective_round == 2
    assert (
        sum(second_housing_delta.domains[0].values["units_by_district"].values())
        == second_housing_delta.domains[0].values["total_units"]
    )


def test_public_transitions_reject_manifest_transition_version_mismatch() -> None:
    config = load_city_config()
    snapshot = generate_snapshot(config)
    manifest = build_aurora_synthetic_v1_manifest(
        config, snapshot, experiment_id="version-test"
    )
    parent = StateFactory.from_snapshot(
        snapshot, manifest=manifest, instance_id="city-1"
    )
    population_delta = transition_population(parent, manifest)
    mismatched = manifest.model_copy(update={"transition_version": "2.0"})

    with pytest.raises(ValueError, match="versão de transição"):
        transition_population(parent, mismatched)
    with pytest.raises(ValueError, match="versão de transição"):
        transition_employment(parent, mismatched)
    with pytest.raises(ValueError, match="versão de transição"):
        transition_housing(parent, mismatched, population_delta)

    unsupported_state = parent.model_copy(update={"transition_version": "2.0"})
    unsupported_manifest = manifest.model_copy(update={"transition_version": "2.0"})
    with pytest.raises(ValueError, match="não suportada"):
        transition_population(unsupported_state, unsupported_manifest)
    with pytest.raises(ValueError, match="não suportada"):
        transition_employment(unsupported_state, unsupported_manifest)
    with pytest.raises(ValueError, match="não suportada"):
        transition_housing(unsupported_state, unsupported_manifest, population_delta)
