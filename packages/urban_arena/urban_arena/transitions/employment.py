"""Deterministic annual employment totals and urban district allocation."""

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
    _largest_remainder,
    _round_half_up,
    _validate_transition_version,
)


def calculate_employment(
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
        if abs(sum(allocation.values(), Decimal(0)) - Decimal(1)) > Decimal("1e-12"):
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


def transition_employment(
    state: CityState, manifest: ExperimentManifest
) -> CityStateDelta:
    """Return the public employment replacement delta for the next round."""
    if state.experiment_id != manifest.experiment_id:
        raise ValueError("CityState e manifesto pertencem a experimentos diferentes")
    if state.snapshot_hash != manifest.snapshot_hash:
        raise ValueError("CityState e manifesto devem apontar para o mesmo snapshot")
    _validate_transition_version(state.transition_version, manifest.transition_version)
    round_index = state.round_index + 1
    if round_index > manifest.horizon_rounds:
        raise ValueError("transição excede o horizonte do manifesto")
    urban_ids = tuple(state.housing.units_by_district)
    district_jobs = tuple(
        (
            district_id,
            "urban" if district_id in urban_ids else "external_catchment",
            jobs,
        )
        for district_id, jobs in state.employment.jobs_by_district.items()
    )
    result, before, after, net_change = calculate_employment(
        district_jobs,
        annual_growth_rate=manifest.parameters.employment.annual_growth_rate,
        district_allocation=tuple(
            manifest.parameters.employment.district_allocation.items()
        ),
    )
    ledger = {"jobs_before": before, "jobs_after": after, "jobs_net_change": net_change}
    digest = canonical_hash(
        {
            "parent_city_state_hash": state.city_state_hash,
            "event_type": "employment_annual_flows",
            "effective_round": round_index,
            "payload": ledger,
        }
    )
    event = EffectiveEvent(
        event_id=f"employment_annual_flows:{digest[:24]}",
        event_type="employment_annual_flows",
        effective_round=round_index,
        payload=ledger,
    )
    return CityStateDelta(
        parent_city_state_hash=state.city_state_hash,
        domains=(
            DomainDelta(
                domain="employment",
                values={"jobs_by_district": dict(result), "total_jobs": after},
            ),
        ),
        effective_events=(event,),
    )
