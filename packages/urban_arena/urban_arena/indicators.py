"""Versioned indicator cards aligned with the integrated Aurora v1 catalog.

This module describes indicator definitions and result metadata. It deliberately
does not calculate domain indicators: calculation belongs to the domain models
and a shared result interface has not been established yet.
"""

from __future__ import annotations

from math import isfinite
from typing import Literal

from pydantic import Field, StrictFloat, StrictInt, model_validator

from .models import StrictModel

SourceKind = Literal["synthetic_config", "synthetic_generated", "external_dataset", "observed"]
ProductionMethod = Literal["measured", "derived", "simulated", "estimated"]
NullReason = Literal["missing_input", "unknown_coverage", "not_applicable"]
CoverageStatus = Literal["complete", "partial", "unknown"]
PeriodType = Literal[
    "simulation_window",
    "annual_round",
    "fiscal_period",
    "reference_date",
    "observation_period",
    "follow_up",
]
UnitPolicy = Literal["fixed", "source_declared"]
UnitBasis = Literal["catalog", "source_declared"]


class IndicatorDefinition(StrictModel):
    """Immutable catalog card; formula changes require a new version."""

    indicator_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    title: str = Field(min_length=1)
    unit: str = Field(min_length=1)
    unit_policy: UnitPolicy = "fixed"
    period_scope: str = Field(min_length=1)
    period_type: PeriodType
    formula_version: str = Field(min_length=1)
    base_indicator_id: str | None = None


class IndicatorCoverage(StrictModel):
    """Spatial and temporal extent represented by a result."""

    status: CoverageStatus
    spatial: str = Field(min_length=1)
    temporal: str = Field(min_length=1)
    numerator: StrictInt | StrictFloat | None = None
    denominator: StrictInt | StrictFloat | None = None
    filters: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_counts(self) -> IndicatorCoverage:
        if (self.numerator is None) != (self.denominator is None):
            raise ValueError("numerator e denominator de cobertura devem ser informados em conjunto")
        if (
            self.numerator is not None
            and self.denominator is not None
            and (
                not isfinite(self.numerator)
                or not isfinite(self.denominator)
                or self.numerator < 0
                or self.denominator < 0
                or self.numerator > self.denominator
            )
        ):
            raise ValueError("contagens de cobertura devem satisfazer 0 <= numerador <= denominador")
        return self


class IndicatorValue(StrictModel):
    """One published value, or a null value carrying an explicit reason."""

    indicator_id: str = Field(min_length=1)
    indicator_version: str = Field(min_length=1)
    value: StrictInt | StrictFloat | None
    null_reason: NullReason | None = None
    unit: str = Field(min_length=1)
    unit_basis: UnitBasis = "catalog"
    period: str = Field(min_length=1)
    period_type: PeriodType
    territory: str = Field(min_length=1)
    coverage: IndicatorCoverage
    formula_version: str = Field(min_length=1)
    source_kind: SourceKind | None = None
    production_method: ProductionMethod | None = None
    source_id: str | None = None
    source_license: str | None = None
    producer: str = Field(min_length=1)
    producer_version: str = Field(min_length=1)
    parent_state_hash: str | None = None
    result_hash: str | None = None
    seed: int | None = Field(default=None, ge=0)
    limitations: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_result(self) -> IndicatorValue:
        try:
            definition = indicator_definition(self.indicator_id)
        except KeyError as exc:
            raise ValueError(str(exc)) from exc
        if self.indicator_version != definition.version:
            raise ValueError("indicator_version deve corresponder à versão do catálogo")
        if definition.unit_policy == "fixed":
            if self.unit != definition.unit or self.unit_basis != "catalog":
                raise ValueError("unit deve corresponder à unidade fixa da ficha catalogada")
        elif self.unit_basis == "catalog" and self.unit != definition.unit:
            raise ValueError("unit deve corresponder à unidade catalogada ou ser declarada pela fonte")
        elif self.unit_basis == "source_declared":
            if self.source_kind not in {"observed", "external_dataset"}:
                raise ValueError("unidade declarada exige origem de dados com unidade auditável")
            if not self.source_id or not self.source_license:
                raise ValueError("unidade declarada exige fonte e licença/base de uso")
        if self.period_type != definition.period_type:
            raise ValueError("period_type deve corresponder ao escopo temporal da ficha catalogada")
        if self.formula_version != definition.formula_version:
            raise ValueError("formula_version deve corresponder à ficha catalogada")
        if self.value is None and self.null_reason is None:
            raise ValueError("valor null exige null_reason")
        if self.value is not None and self.null_reason is not None:
            raise ValueError("valor disponível não pode ter null_reason")
        if self.value is not None and self.source_kind is None:
            raise ValueError("valor disponível exige source_kind e production_method")
        if (self.source_kind is None) != (self.production_method is None):
            raise ValueError("source_kind e production_method devem ser informados separadamente em conjunto")
        if self.source_kind == "observed" and self.value is not None:
            if not self.source_id or not self.source_license:
                raise ValueError("valor observado exige fonte e licença/base de uso")
            if self.coverage.status == "unknown":
                raise ValueError("valor observado exige cobertura auditável")
        if isinstance(self.value, float) and not (-float("inf") < self.value < float("inf")):
            raise ValueError("valor do indicador deve ser finito")
        return self


# IDs, units, periods, and parent links below follow catalog-indicadores-v1.md
# and contrato-evolucao-urbana-v1.md. Values are supplied by domain models.
_DEFINITIONS = (
    ("MOB-01", "Viagens solicitadas", "veículos/viagens por execução e janela", "janela de demanda"),
    ("MOB-02", "Viagens concluídas", "veículos/viagens por execução e janela", "janela de demanda e período de escoamento"),
    ("MOB-03", "Viagens não concluídas", "veículos/viagens por execução e janela", "janela de demanda e período de escoamento"),
    ("MOB-04", "Taxa de conclusão de viagens", "%", "janela de demanda e período de escoamento"),
    ("MOB-05", "Duração média das viagens concluídas", "s/viagem", "janela de demanda e período de escoamento"),
    ("MOB-06", "Velocidade média ponderada pela distância", "km/h", "janela de demanda e período de escoamento"),
    ("MOB-07", "Comprimento médio de fila", "m", "janela de demanda"),
    ("FIN-01", "Saldo operacional do período", "CS/rodada-ano sintético", "rodada fiscal declarada"),
    ("FIN-02", "Cobertura do serviço da dívida", "razão (x)", "período fiscal compatível"),
    ("FIN-03", "Passivo de manutenção pendente", "CS", "posição na data de referência"),
    ("HAB-01", "Ônus habitacional dos domicílios", "% da renda domiciliar disponível", "período comum de custo e renda"),
    ("HAB-02", "Domicílios em moradia inadequada", "% dos domicílios elegíveis", "data/período da referência domiciliar"),
    ("HAB-03", "Domicílios deslocados involuntariamente", "domicílios e % da coorte elegível", "período de acompanhamento declarado"),
    ("SER-01", "População sem acesso dentro do critério configurado", "% da população elegível", "período populacional e operacional declarado"),
    ("SER-02a", "Demanda escolar não atendida", "vagas/ano letivo", "ano letivo declarado", "SER-02"),
    ("SER-02b", "Demanda de atenção primária não atendida", "consultas/ano", "ano/período de operação declarado", "SER-02"),
    ("SER-03", "Utilização da capacidade instalada", "%", "mesma janela operacional para volume e capacidade"),
    ("AMB-01", "Massa de poluente emitida no cenário", "g de espécie identificada", "janela de mobilidade efetivamente simulada"),
    ("AMB-01a", "Estimativa anual sintética de CO₂e", "kg CO₂e/ano sintético", "ano/rodada sintética" , "AMB-01"),
    ("AMB-02", "Concentração ambiente de poluente", "µg/m³", "resolução e janela da estação"),
    ("AMB-03", "Área verde pública por residente", "m²/residente", "data do inventário e referência populacional"),
    ("AMB-03a", "Área verde agregada sintética por residente", "m²/residente", "rodada sintética", "AMB-03"),
    ("EQU-01", "Diferença de acesso entre grupos", "pontos percentuais", "mesmo período e janela de serviço"),
    ("EQU-02", "Diferença de ônus habitacional entre grupos", "pontos percentuais de renda domiciliar", "mesmo período e base monetária"),
    ("EQU-03", "Lacuna de nível mínimo de serviço por grupo", "unidade do nível de serviço configurado", "período do nível e do padrão"),
)

_PERIOD_TYPES: dict[str, PeriodType] = {
    **{f"MOB-{index:02d}": "simulation_window" for index in range(1, 8)},
    "FIN-01": "fiscal_period",
    "FIN-02": "fiscal_period",
    "FIN-03": "reference_date",
    "HAB-01": "observation_period",
    "HAB-02": "reference_date",
    "HAB-03": "follow_up",
    "SER-01": "observation_period",
    "SER-02a": "annual_round",
    "SER-02b": "annual_round",
    "SER-03": "observation_period",
    "AMB-01": "simulation_window",
    "AMB-01a": "annual_round",
    "AMB-02": "observation_period",
    "AMB-03": "reference_date",
    "AMB-03a": "annual_round",
    "EQU-01": "observation_period",
    "EQU-02": "observation_period",
    "EQU-03": "observation_period",
}
_UNIT_POLICIES: dict[str, UnitPolicy] = {"AMB-02": "source_declared"}


INDICATOR_CATALOG: tuple[IndicatorDefinition, ...] = tuple(
    IndicatorDefinition(
        indicator_id=row[0],
        version="1.0",
        title=row[1],
        unit=row[2],
        unit_policy=_UNIT_POLICIES.get(row[0], "fixed"),
        period_scope=row[3],
        period_type=_PERIOD_TYPES[row[0]],
        formula_version="catalog-v1",
        base_indicator_id=row[4] if len(row) > 4 else None,
    )
    for row in _DEFINITIONS
)


def indicator_definition(indicator_id: str) -> IndicatorDefinition:
    """Return the integrated v1 definition for a canonical indicator ID."""
    for definition in INDICATOR_CATALOG:
        if definition.indicator_id == indicator_id:
            return definition
    raise KeyError(f"Indicador não catalogado: {indicator_id}")


def unavailable_indicator(
    indicator_id: str,
    *,
    reason: NullReason,
    period: str,
    period_type: PeriodType,
    territory: str,
    coverage: IndicatorCoverage,
    producer: str,
    producer_version: str,
    parent_state_hash: str | None = None,
    result_hash: str | None = None,
    limitations: tuple[str, ...] = (),
) -> IndicatorValue:
    """Create an explicit unavailable result without fabricating a value or source."""
    definition = indicator_definition(indicator_id)
    return IndicatorValue(
        indicator_id=definition.indicator_id,
        indicator_version=definition.version,
        value=None,
        null_reason=reason,
        unit=definition.unit,
        period=period,
        period_type=period_type,
        territory=territory,
        coverage=coverage,
        formula_version=definition.formula_version,
        producer=producer,
        producer_version=producer_version,
        parent_state_hash=parent_state_hash,
        result_hash=result_hash,
        limitations=limitations,
    )
