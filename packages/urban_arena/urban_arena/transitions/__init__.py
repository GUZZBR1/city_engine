"""Pure annual domain transitions for population, housing, and employment."""

from __future__ import annotations

from collections.abc import Sequence
from decimal import ROUND_FLOOR, ROUND_HALF_UP, Decimal, InvalidOperation

SUPPORTED_TRANSITION_VERSION = "1.0"


def _validate_transition_version(state_version: str, manifest_version: str) -> None:
    if state_version != manifest_version:
        raise ValueError("CityState e manifesto devem usar a mesma versão de transição")
    if manifest_version != SUPPORTED_TRANSITION_VERSION:
        raise ValueError(f"versão de transição não suportada: {manifest_version}")


def _decimal(value: object, name: str) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise ValueError(f"{name} deve ser um número finito")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{name} deve ser um número finito") from exc
    if not result.is_finite():
        raise ValueError(f"{name} deve ser um número finito")
    return result


def _integer(value: object, name: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{name} deve ser inteiro >= {minimum}")
    return value


def _round_half_up(value: Decimal) -> int:
    return int(value.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def _largest_remainder(
    total: int, ids: Sequence[str], weights: Sequence[Decimal]
) -> list[int]:
    if total < 0 or len(ids) != len(weights) or len(set(ids)) != len(ids):
        raise ValueError("parâmetros inválidos para rateio")
    if not ids:
        if total:
            raise ValueError("não há distritos para ratear um total positivo")
        return []
    if any(weight < 0 for weight in weights):
        raise ValueError("pesos de rateio não podem ser negativos")
    denominator = sum(weights, Decimal(0))
    if total == 0:
        return [0] * len(ids)
    if denominator <= 0:
        raise ValueError("soma dos pesos deve ser positiva")
    exact = [Decimal(total) * weight / denominator for weight in weights]
    allocated = [int(value.to_integral_value(rounding=ROUND_FLOOR)) for value in exact]
    remainder = total - sum(allocated)
    order = sorted(
        range(len(ids)),
        key=lambda index: (-(exact[index] - allocated[index]), ids[index]),
    )
    for index in order[:remainder]:
        allocated[index] += 1
    return allocated


def _signed_largest_remainder(
    total: int,
    ids: Sequence[str],
    weights: Sequence[Decimal],
    caps: Sequence[int] | None = None,
) -> list[int]:
    if total >= 0:
        return _largest_remainder(total, ids, weights)
    loss = -total
    limits = list(caps or [loss] * len(ids))
    if loss > sum(limits):
        raise ValueError("migração excede a população disponível nos distritos")
    result = [0] * len(ids)
    active = set(range(len(ids)))
    remaining = loss
    while remaining:
        if not active:
            raise ValueError("migração excede a população disponível nos distritos")
        indices = sorted(active)
        proposals = _largest_remainder(
            remaining, [ids[i] for i in indices], [weights[i] for i in indices]
        )
        overflow = 0
        for index, proposal in zip(indices, proposals, strict=True):
            accepted = min(proposal, limits[index] - result[index])
            result[index] += accepted
            overflow += proposal - accepted
        remaining = overflow
        active = {i for i in active if result[i] < limits[i]}
    return [-value for value in result]
