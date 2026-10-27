"""Immutable policy observations built from the evolutive city state."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import TypeAlias

from .actions import DEFAULT_ACTION_CATALOG, ActionCatalog
from .indicators import IndicatorValue
from .manifest import ExperimentManifest
from .state import CityState

FrozenJSON: TypeAlias = (
    type(None)
    | bool
    | int
    | float
    | str
    | tuple["FrozenJSON", ...]
    | Mapping[str, "FrozenJSON"]
)


def _freeze(value: object) -> FrozenJSON:
    """Copy JSON-shaped data into recursively immutable containers."""
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("observação deve conter apenas números finitos")
        return value
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise TypeError("chaves de observação devem ser strings")
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    raise TypeError(f"valor não JSON na observação: {type(value).__name__}")


@dataclass(frozen=True, slots=True)
class Observation:
    """Frozen view of one candidate state delivered to a policy."""

    instance_id: str
    round_index: int
    city_state_hash: str
    state_view: Mapping[str, FrozenJSON]
    available_actions: tuple[FrozenJSON, ...]
    budget_view: Mapping[str, FrozenJSON]
    indicator_values: Mapping[str, FrozenJSON]

    def __post_init__(self) -> None:
        if not self.instance_id or not self.city_state_hash:
            raise ValueError("identidade da instância e hash observado são obrigatórios")
        if type(self.round_index) is not int or self.round_index < 1:
            raise ValueError("round_index deve ser um inteiro positivo")
        state_view = _freeze(self.state_view)
        available_actions = _freeze(self.available_actions)
        budget_view = _freeze(self.budget_view)
        indicator_values = _freeze(self.indicator_values)
        if not all(isinstance(value, Mapping) for value in (state_view, budget_view, indicator_values)):
            raise TypeError("state_view, budget_view e indicator_values devem ser objetos JSON")
        if not isinstance(available_actions, tuple):
            raise TypeError("available_actions deve ser uma lista JSON")
        object.__setattr__(self, "state_view", state_view)
        object.__setattr__(self, "available_actions", available_actions)
        object.__setattr__(self, "budget_view", budget_view)
        object.__setattr__(self, "indicator_values", indicator_values)


def build_observation(
    state: CityState,
    manifest: ExperimentManifest,
    *,
    previous_indicators: Sequence[IndicatorValue] = (),
    catalog: ActionCatalog = DEFAULT_ACTION_CATALOG,
) -> Observation:
    """Freeze the candidate and only actions enabled in its canonical catalog."""
    if state.experiment_id != manifest.experiment_id:
        raise ValueError("CityState e manifesto pertencem a experimentos diferentes")
    if state.snapshot_hash != manifest.snapshot_hash:
        raise ValueError("CityState e manifesto devem apontar para o mesmo snapshot")
    if not 1 <= state.round_index <= manifest.horizon_rounds:
        raise ValueError("observação deve referenciar uma rodada dentro do horizonte")

    indicators: dict[str, FrozenJSON] = {}
    for indicator in previous_indicators:
        if indicator.indicator_id in indicators:
            raise ValueError("indicator_id duplicado na observação")
        indicators[indicator.indicator_id] = _freeze(indicator.model_dump(mode="json"))

    state_view = state.model_dump(mode="json")
    # Fixed operations and the reserve are not agent-controlled budget.
    state_view.pop("budget", None)
    return Observation(
        instance_id=state.instance_id,
        round_index=state.round_index,
        city_state_hash=state.city_state_hash,
        state_view=state_view,
        available_actions=tuple(
            definition.model_dump(mode="json") for definition in catalog.actions if definition.enabled
        ),
        budget_view={
            "discretionary_limit_cs": state.budget.discretionary_budget,
            "currency": "CS",
        },
        indicator_values=indicators,
    )
