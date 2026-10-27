"""Deterministic urban housing stock and unmet-demand calculations."""

from __future__ import annotations

from collections.abc import Sequence
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal

from . import _decimal, _integer, _largest_remainder, _round_half_up


def initialize_urban_housing(
    urban_districts: Sequence[tuple[str, int]],
    *,
    household_size: float | str,
    vacancy_rate_target: float | str,
    initial_units: int | None = None,
) -> tuple[int, int, tuple[tuple[str, int], ...]]:
    """Return (occupied household need, initial units, district unit allocation)."""
    if not urban_districts:
        raise ValueError("é necessário ao menos um distrito urbano")
    ids = [district_id for district_id, _ in urban_districts]
    residents = [
        _integer(value, f"districts[{district_id}].residents")
        for district_id, value in urban_districts
    ]
    if len(set(ids)) != len(ids):
        raise ValueError("IDs de distritos devem ser únicos")
    size = _decimal(household_size, "household_size")
    vacancy = _decimal(vacancy_rate_target, "vacancy_rate_target")
    if size <= 0:
        raise ValueError("household_size deve ser positivo")
    if not Decimal(0) <= vacancy < Decimal(1):
        raise ValueError("vacancy_rate_target deve estar no intervalo [0, 1)")
    occupied_need = _round_half_up(Decimal(sum(residents)) / size)
    units = (
        _integer(initial_units, "initial_units")
        if initial_units is not None
        else int(
            (Decimal(occupied_need) / (Decimal(1) - vacancy)).to_integral_value(
                rounding=ROUND_CEILING
            )
        )
    )
    allocated = _largest_remainder(units, ids, [Decimal(value) for value in residents])
    return occupied_need, units, tuple(zip(ids, allocated, strict=True))


def transition_housing(
    urban_population_after_transition: int,
    housing_stock: int,
    housing_stock_initial: int,
    *,
    household_size: float | str,
    vacancy_rate_target: float | str,
    annual_capacity_rate: float | str,
    annual_retirement_rate: float | str,
) -> tuple[int, int, int, int, int, int]:
    """Return need, retired, capacity, built, final stock, unmet demand."""
    population = _integer(
        urban_population_after_transition, "urban_population_after_transition"
    )
    stock = _integer(housing_stock, "housing_stock")
    initial_stock = _integer(housing_stock_initial, "housing_stock_initial")
    size = _decimal(household_size, "household_size")
    vacancy = _decimal(vacancy_rate_target, "vacancy_rate_target")
    capacity_rate = _decimal(annual_capacity_rate, "annual_capacity_rate")
    retirement_rate = _decimal(annual_retirement_rate, "annual_retirement_rate")
    if size <= 0:
        raise ValueError("household_size deve ser positivo")
    if not Decimal(0) <= vacancy < Decimal(1):
        raise ValueError("vacancy_rate_target deve estar no intervalo [0, 1)")
    if capacity_rate < 0:
        raise ValueError("annual_capacity_rate deve ser >= 0")
    if not Decimal(0) <= retirement_rate <= Decimal(1):
        raise ValueError("annual_retirement_rate deve estar no intervalo [0, 1]")

    need = _round_half_up(Decimal(population) / size)
    retirement = min(stock, _round_half_up(Decimal(stock) * retirement_rate))
    after_retirement = stock - retirement
    capacity = int(
        (Decimal(initial_stock) * capacity_rate).to_integral_value(rounding=ROUND_FLOOR)
    )
    required = int(
        (Decimal(need) / (Decimal(1) - vacancy)).to_integral_value(
            rounding=ROUND_CEILING
        )
    )
    built = min(max(0, required - after_retirement), capacity)
    next_stock = after_retirement + built
    occupancy_capacity = int(
        (Decimal(next_stock) * (Decimal(1) - vacancy)).to_integral_value(
            rounding=ROUND_FLOOR
        )
    )
    unmet = max(0, need - occupancy_capacity)
    if (
        next_stock != after_retirement + built
        or built < 0
        or built > capacity
        or occupancy_capacity > next_stock
    ):
        raise ValueError("balanço habitacional não fecha")
    return need, retirement, capacity, built, next_stock, unmet
