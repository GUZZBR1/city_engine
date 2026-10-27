"""Deterministic annual population accounting (no state or manifest ownership)."""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from . import _decimal, _integer, _round_half_up, _signed_largest_remainder


def transition_population(
    urban_districts: Sequence[tuple[str, int]],
    rural_residents: int,
    *,
    birth_rate: float | str,
    death_rate: float | str,
    net_migration_rate: float | str,
    urban_net_migration_share: float | str,
) -> tuple[tuple[tuple[str, int], ...], int, tuple[int, ...]]:
    """Return (urban district residents, rural residents, flow ledger).

    Flow ledger order: births, deaths, gross net migration, urban migration
    allocated, rural migration applied, blocked migration. Required parameters
    are supplied by the caller from its frozen manifest.
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
        births_urban + births_rural,
        deaths_urban + deaths_rural,
        migration,
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
        != total_before + flows[0] - flows[1] + urban_applied + rural_applied
    ):
        raise ValueError("balanço populacional total não fecha")
    return next_urban, next_rural, flows
