"""Pure annual green-area transition and conditional synthetic CO2e estimate."""

from __future__ import annotations

import math

from ..manifest import ExperimentManifest
from ..state import CityState, DomainDelta


def transition_environment(
    previous_state: CityState,
    candidate_state: CityState,
    manifest: ExperimentManifest,
) -> DomainDelta:
    """Carry forward the explicit public-green-area stock for the urban districts.

    Aurora v1 has no enabled green-area actions. The transition therefore
    preserves the configured area stock; it never reads ``land_use`` or infers
    polygons. The annual CO2e estimate is exposed separately because the
    shared CityState/DomainDelta schemas contain no emissions-indicator field.
    """
    _validate_transition(previous_state, candidate_state, manifest)
    urban_ids = _urban_district_ids(previous_state, manifest)
    area_by_district = previous_state.environment.public_green_area_m2_by_district
    if set(area_by_district) != set(urban_ids):
        raise ValueError("estoque de área verde não cobre exatamente os distritos urbanos")
    for district_id in urban_ids:
        _nonnegative_finite(area_by_district[district_id], f"green_area.{district_id}")
    return DomainDelta(
        domain="environment",
        values={"public_green_area_m2_by_district": dict(area_by_district)},
    )


def aggregate_urban_green_area(state: CityState, manifest: ExperimentManifest) -> tuple[float | None, str | None]:
    """Return total configured urban green area and an optional null reason."""
    urban_ids = _urban_district_ids(state, manifest)
    areas = state.environment.public_green_area_m2_by_district
    if any(district_id not in areas for district_id in urban_ids):
        return None, "missing_input"
    values = [areas[district_id] for district_id in urban_ids]
    for district_id, value in zip(urban_ids, values, strict=True):
        _nonnegative_finite(value, f"green_area.{district_id}")
    return sum(values), None


def urban_green_area_per_resident(state: CityState, manifest: ExperimentManifest) -> tuple[float | None, str | None]:
    """Return aggregated m² per urban resident, or its explicit null reason."""
    total_area, area_reason = aggregate_urban_green_area(state, manifest)
    if total_area is None:
        return None, area_reason or "missing_input"
    urban_ids = _urban_district_ids(state, manifest)
    residents = state.population.residents_by_district
    if any(district_id not in residents for district_id in urban_ids):
        return None, "missing_input"
    total_residents = sum(residents[district_id] for district_id in urban_ids)
    if total_residents == 0:
        return None, "not_applicable"
    return total_area / total_residents, None


def estimate_annual_co2e(
    state: CityState,
    manifest: ExperimentManifest,
    *,
    district_id: str | None = None,
) -> tuple[float | None, str | None]:
    """Estimate annual vehicle CO2e in kg for one urban district or all urban.

    The activity is the manifest's exogenous vehicle-km per resident per year.
    This estimate never consumes SUMO window outputs and cannot be interpreted
    as a traffic-intervention effect or atmospheric concentration.
    """
    urban_ids = _urban_district_ids(state, manifest)
    if district_id is not None:
        if district_id not in urban_ids:
            return None, "unknown_coverage"
        target_ids = (district_id,)
    else:
        target_ids = urban_ids

    activity_rate = manifest.parameters.emissions.annual_vehicle_km_per_resident
    factor = manifest.parameters.emissions.co2e_kg_per_vehicle_km
    if activity_rate is None or factor is None:
        return None, "missing_input"
    _nonnegative_finite(activity_rate, "emissions.annual_vehicle_km_per_resident")
    _nonnegative_finite(factor, "emissions.co2e_kg_per_vehicle_km")

    residents_by_district = state.population.residents_by_district
    if any(zone_id not in residents_by_district for zone_id in target_ids):
        return None, "missing_input"
    total = 0.0
    for zone_id in target_ids:
        residents = residents_by_district[zone_id]
        vehicle_km = residents * activity_rate
        total += vehicle_km * factor
    return total, None


def _urban_district_ids(state: CityState, manifest: ExperimentManifest) -> tuple[str, ...]:
    housing_ids = set(state.housing.units_by_district)
    employment_ids = set(manifest.parameters.employment.district_allocation)
    green_ids = set(manifest.parameters.green.public_area_m2_per_resident)
    if not housing_ids or housing_ids != employment_ids or housing_ids != green_ids:
        raise ValueError("estado e manifesto devem declarar o mesmo conjunto completo de distritos urbanos")
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
