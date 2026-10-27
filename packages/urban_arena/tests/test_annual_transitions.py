from __future__ import annotations

import pytest
from urban_arena.transitions.employment import transition_employment
from urban_arena.transitions.housing import initialize_urban_housing, transition_housing
from urban_arena.transitions.population import transition_population


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
    first = transition_population(*inputs, **kwargs)
    second = transition_population(*inputs, **kwargs)
    assert first == second
    (
        districts,
        rural,
        (births, deaths, migration, urban_migration, rural_migration, blocked),
    ) = first
    assert sum(value for _, value in districts) == 3_000 + 36 - 24 + urban_migration
    assert rural == 500 + 6 - 4 + rural_migration
    assert migration == urban_migration + rural_migration + blocked
    assert births == 42 and deaths == 28


def test_negative_migration_is_capped_to_prevent_negative_population() -> None:
    districts, rural, flows = transition_population(
        (("district", 1),),
        0,
        birth_rate=0,
        death_rate=0,
        net_migration_rate=-1,
        urban_net_migration_share=1,
    )
    assert districts == (("district", 0),)
    assert rural == 0
    assert flows[2:] == (-1, -1, 0, 0)


def test_rural_migration_cap_uses_population_after_births_and_deaths() -> None:
    _, rural, flows = transition_population(
        (("district", 0),),
        1,
        birth_rate=1,
        death_rate=0,
        net_migration_rate=-2,
        urban_net_migration_share=0,
    )
    assert rural == 0
    assert flows[4:] == (-2, 0)


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
    result = transition_housing(
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
    _, _, capacity, built, next_stock, _ = transition_housing(
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
    district_jobs, before, after, net = transition_employment(
        (("b", "urban", 5), ("a", "urban", 5), ("rural", "external_catchment", 0)),
        annual_growth_rate=growth,
    )
    assert before == 10
    assert after == expected
    assert net == expected - 10
    assert sum(jobs for _, jobs in district_jobs) == expected
    assert dict(district_jobs)["rural"] == 0


def test_employment_remainder_tie_uses_lexicographic_district_id() -> None:
    districts, _, after, _ = transition_employment(
        (("z", "urban", 1), ("a", "urban", 0)),
        annual_growth_rate=0,
        district_allocation=(("z", "0.5"), ("a", "0.5")),
    )
    assert after == 1
    assert dict(districts) == {"z": 0, "a": 1}


def test_invalid_null_and_nonfinite_parameters_fail() -> None:
    with pytest.raises(ValueError, match="birth_rate"):
        transition_population(
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
        transition_employment((("a", "urban", 1),), annual_growth_rate=float("nan"))
