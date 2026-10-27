"""Pure annual service demand transitions using the shared typed city state."""

from __future__ import annotations

import math

from ..manifest import ExperimentManifest
from ..state import CityState, DomainDelta


def transition_services(
    previous_state: CityState,
    candidate_state: CityState,
    manifest: ExperimentManifest,
) -> DomainDelta:
    """Recalculate candidate demand and preserve typed capacity stocks.

    Candidate population must already reflect this year's demographic
    transition. V1 has no enabled service-capacity action, so each capacity is
    carried forward from the parent state. Rural zones are excluded because
    service state covers only the urban districts.
    """
    _validate_transition(previous_state, candidate_state, manifest)
    urban_ids = _urban_district_ids(previous_state, manifest)
    residents = candidate_state.population.residents_by_district
    service_parameters = manifest.parameters.services

    school = _service_delta(
        district_ids=urban_ids,
        previous_capacity=previous_state.services.school.capacity_by_district,
        candidate_population=residents,
        demand_rate=service_parameters.school.eligible_share,
        label="school",
    )
    health = _service_delta(
        district_ids=urban_ids,
        previous_capacity=previous_state.services.primary_health.capacity_by_district,
        candidate_population=residents,
        demand_rate=service_parameters.health.annual_visits_per_resident,
        label="primary_health",
    )
    return DomainDelta(domain="services", values={"school": school, "primary_health": health})


def _service_delta(
    *,
    district_ids: tuple[str, ...],
    previous_capacity: dict[str, float],
    candidate_population: dict[str, int],
    demand_rate: float,
    label: str,
) -> dict[str, dict[str, float]]:
    _nonnegative_finite(demand_rate, f"{label}.demand_rate")
    capacity: dict[str, float] = {}
    demand: dict[str, float] = {}
    for district_id in district_ids:
        if district_id not in previous_capacity:
            raise ValueError(f"estoque de capacidade ausente para {label}/{district_id}")
        if district_id not in candidate_population:
            raise ValueError(f"população candidata ausente para {label}/{district_id}")
        capacity_value = previous_capacity[district_id]
        _nonnegative_finite(capacity_value, f"{label}.{district_id}.capacity")
        capacity[district_id] = capacity_value
        demand[district_id] = candidate_population[district_id] * demand_rate
    return {"demand_by_district": demand, "capacity_by_district": capacity}


def _urban_district_ids(state: CityState, manifest: ExperimentManifest) -> tuple[str, ...]:
    housing_ids = set(state.housing.units_by_district)
    employment_ids = set(manifest.parameters.employment.district_allocation)
    green_ids = set(manifest.parameters.green.public_area_m2_per_resident)
    if not housing_ids or housing_ids != employment_ids or housing_ids != green_ids:
        raise ValueError("estado e manifesto devem declarar o mesmo conjunto completo de distritos urbanos")
    if set(state.services.school.capacity_by_district) != housing_ids:
        raise ValueError("capacidade escolar não cobre exatamente os distritos urbanos")
    if set(state.services.primary_health.capacity_by_district) != housing_ids:
        raise ValueError("capacidade de saúde não cobre exatamente os distritos urbanos")
    return tuple(sorted(housing_ids))


def _validate_transition(previous_state: CityState, candidate_state: CityState, manifest: ExperimentManifest) -> None:
    if candidate_state.round_index != previous_state.round_index + 1:
        raise ValueError("candidate_state deve avançar exatamente uma rodada em relação a previous_state")
    if candidate_state.parent_city_state_hash != previous_state.city_state_hash:
        raise ValueError("candidate_state deve referenciar previous_state como pai")
    if candidate_state.experiment_id != previous_state.experiment_id or candidate_state.instance_id != previous_state.instance_id:
        raise ValueError("estados pai e candidato devem pertencer à mesma instância")
    if candidate_state.experiment_id != manifest.experiment_id:
        raise ValueError("estado e manifesto devem pertencer ao mesmo experimento")
    if candidate_state.round_index > manifest.horizon_rounds:
        raise ValueError("candidate_state excede o horizonte do manifesto")
    if previous_state.snapshot_hash != manifest.snapshot_hash or candidate_state.snapshot_hash != manifest.snapshot_hash:
        raise ValueError("estado e manifesto devem apontar para o mesmo snapshot")


def _nonnegative_finite(value: float, label: str) -> None:
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"{label} deve ser finito e não negativo")
