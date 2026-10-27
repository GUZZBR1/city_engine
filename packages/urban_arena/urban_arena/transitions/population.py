"""Deterministic annual population accounting (no state or manifest ownership)."""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from ..manifest import ExperimentManifest
from ..state import (
    CityState,
    CityStateDelta,
    DomainDelta,
    EffectiveEvent,
    canonical_hash,
)
from . import (
    _decimal,
    _integer,
    _round_half_up,
    _signed_largest_remainder,
    _validate_transition_version,
)


def calculate_population(
    urban_districts: Sequence[tuple[str, int]],
    rural_residents: int,
    *,
    birth_rate: float | str,
    death_rate: float | str,
    net_migration_rate: float | str,
    urban_net_migration_share: float | str,
) -> tuple[tuple[tuple[str, int], ...], int, tuple[int, ...]]:
    """Return (urban district residents, rural residents, flow ledger).

    Flow ledger order: urban births/deaths, rural births/deaths, gross migration,
    intended urban/rural migration, applied urban/rural migration, blocked
    migration. Parameters come from the caller's frozen manifest.
    """
    ids = [item[0] for item in urban_districts]
    residents = [
        _integer(item[1], f"districts[{item[0]}].residents") for item in urban_districts
    ]
    if not ids or len(set(ids)) != len(ids):
        raise ValueError("distritos urbanos devem ser não vazios e ter IDs únicos")
    rural = _integer(rural_residents, "rural_residents")
    births_rate = _decimal(birth_rate, "birth_rate")
    deaths_rate = _decimal(death_rate, "death_rate")
    migration_rate = _decimal(net_migration_rate, "net_migration_rate")
    urban_share = _decimal(urban_net_migration_share, "urban_net_migration_share")
    if not Decimal(0) <= births_rate <= Decimal(1) or not Decimal(
        0
    ) <= deaths_rate <= Decimal(1):
        raise ValueError("birth_rate e death_rate devem estar entre 0 e 1")
    if not Decimal(0) <= urban_share <= Decimal(1):
        raise ValueError("urban_net_migration_share deve estar entre 0 e 1")

    urban_before = sum(residents)
    total_before = urban_before + rural
    weights = [Decimal(value) for value in residents]
    births_urban = _round_half_up(Decimal(urban_before) * births_rate)
    deaths_urban = _round_half_up(Decimal(urban_before) * deaths_rate)
    urban_births = _signed_largest_remainder(births_urban, ids, weights)
    urban_deaths = _signed_largest_remainder(deaths_urban, ids, weights)
    natural = [
        resident + birth - death
        for resident, birth, death in zip(
            residents, urban_births, urban_deaths, strict=True
        )
    ]

    migration = _round_half_up(Decimal(total_before) * migration_rate)
    urban_migration = _round_half_up(Decimal(migration) * urban_share)
    rural_migration = migration - urban_migration
    urban_applied = max(urban_migration, -sum(natural))
    births_rural = _round_half_up(Decimal(rural) * births_rate)
    deaths_rural = _round_half_up(Decimal(rural) * deaths_rate)
    rural_after_natural_change = rural + births_rural - deaths_rural
    rural_applied = max(rural_migration, -rural_after_natural_change)
    urban_migration_by_district = _signed_largest_remainder(
        urban_applied, ids, weights, caps=natural if urban_applied < 0 else None
    )
    next_urban = tuple(
        (district_id, count + birth - death + migration_delta)
        for district_id, count, birth, death, migration_delta in zip(
            ids,
            residents,
            urban_births,
            urban_deaths,
            urban_migration_by_district,
            strict=True,
        )
    )
    next_rural = rural + births_rural - deaths_rural + rural_applied
    blocked = (urban_migration - urban_applied) + (rural_migration - rural_applied)
    flows = (
        births_urban,
        deaths_urban,
        births_rural,
        deaths_rural,
        migration,
        urban_migration,
        rural_migration,
        urban_applied,
        rural_applied,
        blocked,
    )
    if any(count < 0 for _, count in next_urban) or next_rural < 0:
        raise ValueError("transição produziu população negativa")
    if (
        sum(count for _, count in next_urban)
        != urban_before + births_urban - deaths_urban + urban_applied
    ):
        raise ValueError("balanço populacional urbano não fecha")
    if (
        sum(count for _, count in next_urban) + next_rural
        != total_before
        + births_urban
        + births_rural
        - deaths_urban
        - deaths_rural
        + urban_applied
        + rural_applied
    ):
        raise ValueError("balanço populacional total não fecha")
    return next_urban, next_rural, flows


def transition_population(
    state: CityState, manifest: ExperimentManifest
) -> CityStateDelta:
    """Return the public population delta and this year's deterministic flow event."""
    round_index = _validate_context(state, manifest)
    urban_ids = tuple(state.housing.units_by_district)
    rural_ids = tuple(
        district_id
        for district_id in state.population.residents_by_district
        if district_id not in urban_ids
    )
    if len(rural_ids) != 1 or set(urban_ids) | set(rural_ids) != set(
        state.population.residents_by_district
    ):
        raise ValueError(
            "CityState.population deve separar os distritos urbanos do entorno rural"
        )
    urban, rural, flows = calculate_population(
        tuple(
            (district_id, state.population.residents_by_district[district_id])
            for district_id in urban_ids
        ),
        state.population.residents_by_district[rural_ids[0]],
        birth_rate=manifest.parameters.demography.birth_rate,
        death_rate=manifest.parameters.demography.death_rate,
        net_migration_rate=manifest.parameters.demography.net_migration_rate,
        urban_net_migration_share=manifest.parameters.demography.urban_net_migration_share,
    )
    by_district = dict(state.population.residents_by_district)
    by_district.update(urban)
    by_district[rural_ids[0]] = rural
    urban_total = sum(by_district[district_id] for district_id in urban_ids)
    values = {
        "residents_by_district": by_district,
        "total_residents": urban_total + rural,
        "urban_residents": urban_total,
        "rural_catchment_residents": rural,
    }
    ledger = {
        "urban_births": flows[0],
        "urban_deaths": flows[1],
        "rural_births": flows[2],
        "rural_deaths": flows[3],
        "gross_net_migration": flows[4],
        "urban_migration_intended": flows[5],
        "rural_migration_intended": flows[6],
        "urban_migration_applied": flows[7],
        "rural_migration_applied": flows[8],
        "migration_blocked": flows[9],
    }
    event = _ledger_event(
        state.city_state_hash, "population_annual_flows", round_index, ledger
    )
    return CityStateDelta(
        parent_city_state_hash=state.city_state_hash,
        domains=(DomainDelta(domain="population", values=values),),
        effective_events=(event,),
    )


def _validate_context(state: CityState, manifest: ExperimentManifest) -> int:
    if state.experiment_id != manifest.experiment_id:
        raise ValueError("CityState e manifesto pertencem a experimentos diferentes")
    if state.snapshot_hash != manifest.snapshot_hash:
        raise ValueError("CityState e manifesto devem apontar para o mesmo snapshot")
    _validate_transition_version(state.transition_version, manifest.transition_version)
    round_index = state.round_index + 1
    if round_index > manifest.horizon_rounds:
        raise ValueError("transição excede o horizonte do manifesto")
    return round_index


def _ledger_event(
    parent_city_state_hash: str,
    event_type: str,
    round_index: int,
    payload: dict[str, int],
) -> EffectiveEvent:
    digest = canonical_hash(
        {
            "parent_city_state_hash": parent_city_state_hash,
            "event_type": event_type,
            "effective_round": round_index,
            "payload": payload,
        }
    )
    return EffectiveEvent(
        event_id=f"{event_type}:{digest[:24]}",
        event_type=event_type,
        effective_round=round_index,
        payload=payload,
    )
