"""Deterministic urban housing stock and unmet-demand calculations."""

from __future__ import annotations

from collections.abc import Sequence
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal

from ..manifest import ExperimentManifest
from ..state import (
    CityState,
    CityStateDelta,
    DomainDelta,
    EffectiveEvent,
    allocate_housing_stock,
    canonical_hash,
)
from . import (
    _decimal,
    _integer,
    _largest_remainder,
    _round_half_up,
    _validate_transition_version,
)


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


def calculate_housing(
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


def transition_housing(
    state: CityState,
    manifest: ExperimentManifest,
    population_delta: CityStateDelta,
) -> CityStateDelta:
    """Return a balanced housing-state delta using the shared allocation rule."""
    if state.experiment_id != manifest.experiment_id:
        raise ValueError("CityState e manifesto pertencem a experimentos diferentes")
    if state.snapshot_hash != manifest.snapshot_hash:
        raise ValueError("CityState e manifesto devem apontar para o mesmo snapshot")
    _validate_transition_version(state.transition_version, manifest.transition_version)
    if state.round_index + 1 > manifest.horizon_rounds:
        raise ValueError("transição excede o horizonte do manifesto")
    if population_delta.parent_city_state_hash != state.city_state_hash:
        raise ValueError("population_delta deve referenciar o estado pai recebido")
    if len(population_delta.domains) != 1:
        raise ValueError("population_delta deve conter somente o domínio population")
    population_domains = [
        delta for delta in population_delta.domains if delta.domain == "population"
    ]
    if len(population_domains) != 1:
        raise ValueError(
            "population_delta deve conter exatamente um domínio population"
        )
    round_index = state.round_index + 1
    if (
        len(population_delta.effective_events) != 1
        or population_delta.effective_events[0].event_type != "population_annual_flows"
        or population_delta.effective_events[0].effective_round != round_index
    ):
        raise ValueError("population_delta deve conter o evento demográfico da rodada")
    urban_ids = tuple(state.housing.units_by_district)
    population_values = population_domains[0].values["residents_by_district"]
    if not set(urban_ids).issubset(population_values):
        raise ValueError("population_delta não contém todos os distritos urbanos")
    if manifest.parameters.housing.initial_units is not None:
        initial_stock = manifest.parameters.housing.initial_units
    else:
        initial_occupied = _integer(
            state.housing.occupied_households_urban,
            "housing.occupied_households_urban",
        )
        initial_stock = int(
            (
                Decimal(initial_occupied)
                / (
                    Decimal(1)
                    - Decimal(str(manifest.parameters.housing.vacancy_rate_target))
                )
            ).to_integral_value(rounding=ROUND_CEILING)
        )
    params = manifest.parameters
    need, retired, capacity, built, next_stock, unmet = calculate_housing(
        sum(population_values[district_id] for district_id in urban_ids),
        state.housing.total_units,
        initial_stock,
        household_size=params.demography.household_size,
        vacancy_rate_target=params.housing.vacancy_rate_target,
        annual_capacity_rate=params.housing.annual_capacity_rate,
        annual_retirement_rate=params.housing.annual_retirement_rate,
    )
    allocation_method = params.housing.district_allocation_method
    if allocation_method != "proportional_to_existing_stock_largest_remainder":
        raise ValueError("método de alocação habitacional não suportado")
    units_by_district = allocate_housing_stock(
        next_stock, state.housing.units_by_district
    )
    values = state.housing.model_dump(mode="python")
    values.update(total_units=next_stock, units_by_district=units_by_district)
    ledger = {
        "occupied_households_need": need,
        "units_retired": retired,
        "annual_building_capacity": capacity,
        "units_built": built,
        "total_units_after": next_stock,
        "unserved_housing_demand": unmet,
    }
    digest = canonical_hash(
        {
            "parent_city_state_hash": state.city_state_hash,
            "event_type": "housing_annual_flows",
            "effective_round": round_index,
            "payload": ledger,
        }
    )
    event = EffectiveEvent(
        event_id=f"housing_annual_flows:{digest[:24]}",
        event_type="housing_annual_flows",
        effective_round=round_index,
        payload=ledger,
    )
    return CityStateDelta(
        parent_city_state_hash=state.city_state_hash,
        domains=(DomainDelta(domain="housing", values=values),),
        effective_events=(event,),
    )
