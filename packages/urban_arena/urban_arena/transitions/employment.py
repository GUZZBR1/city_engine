"""Deterministic annual employment totals and urban district allocation."""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from . import _decimal, _integer, _largest_remainder, _round_half_up


def transition_employment(
    district_jobs: Sequence[tuple[str, str, int]],
    *,
    annual_growth_rate: float | str,
    district_allocation: Sequence[tuple[str, float | str]] | None = None,
) -> tuple[tuple[tuple[str, int], ...], int, int, int]:
    """Return (district jobs, jobs before, jobs after, net change).

    `district_allocation` may be omitted to use initial urban employment quotas.
    External districts are always required to have zero jobs and remain zero.
    """
    if not district_jobs:
        raise ValueError("district_jobs não pode ser vazio")
    ids = [district_id for district_id, _, _ in district_jobs]
    if len(set(ids)) != len(ids):
        raise ValueError("IDs de distritos devem ser únicos")
    urban = [
        (district_id, _integer(jobs, f"districts[{district_id}].jobs"))
        for district_id, kind, jobs in district_jobs
        if kind == "urban"
    ]
    external = [
        (district_id, _integer(jobs, f"districts[{district_id}].jobs"))
        for district_id, kind, jobs in district_jobs
        if kind == "external_catchment"
    ]
    if len(urban) + len(external) != len(district_jobs):
        raise ValueError("tipo de distrito desconhecido")
    if any(jobs != 0 for _, jobs in external):
        raise ValueError("distritos externos devem permanecer com zero empregos")
    if not urban:
        raise ValueError("é necessário ao menos um distrito urbano")
    growth = _decimal(annual_growth_rate, "annual_growth_rate")
    if growth < Decimal(-1):
        raise ValueError("annual_growth_rate deve ser >= -1")
    before = sum(jobs for _, jobs in urban)
    after = max(0, _round_half_up(Decimal(before) * (Decimal(1) + growth)))

    urban_ids = [district_id for district_id, _ in urban]
    if district_allocation is None:
        weights = [Decimal(jobs) for _, jobs in urban]
    else:
        allocation_ids = [district_id for district_id, _ in district_allocation]
        if len(set(allocation_ids)) != len(allocation_ids) or set(
            allocation_ids
        ) != set(urban_ids):
            raise ValueError(
                "district_allocation deve conter exatamente os distritos urbanos"
            )
        allocation = {
            district_id: _decimal(share, f"district_allocation[{district_id}]")
            for district_id, share in district_allocation
        }
        if any(share < 0 for share in allocation.values()):
            raise ValueError("frações de alocação não podem ser negativas")
        if sum(allocation.values(), Decimal(0)) != Decimal(1):
            raise ValueError("frações de alocação devem somar 1")
        weights = [allocation[district_id] for district_id in urban_ids]
    if sum(weights, Decimal(0)) <= 0:
        raise ValueError("soma dos empregos urbanos iniciais deve ser positiva")
    allocated = _largest_remainder(after, urban_ids, weights)
    by_id = dict(zip(urban_ids, allocated, strict=True))
    result = tuple((district_id, by_id.get(district_id, 0)) for district_id in ids)
    if sum(jobs for _, jobs in result) != after or any(
        jobs != 0
        for district_id, jobs in result
        if district_id in {key for key, _ in external}
    ):
        raise ValueError("balanço de empregos não fecha")
    return result, before, after, after - before
