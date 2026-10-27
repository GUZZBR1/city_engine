import pytest
from pydantic import ValidationError
from urban_arena.indicators import (
    INDICATOR_CATALOG,
    IndicatorCoverage,
    IndicatorValue,
    indicator_definition,
    unavailable_indicator,
)


def _available(**overrides: object) -> IndicatorValue:
    values: dict[str, object] = {
        "indicator_id": "MOB-02",
        "indicator_version": "1.0",
        "value": 0,
        "unit": "veículos/viagens por execução e janela",
        "period": "weekday_am_peak; partidas 07:00–09:00, escoamento até 10:00",
        "period_type": "simulation_window",
        "territory": "rede sintética aurora-base-v1",
        "coverage": IndicatorCoverage(
            status="complete",
            spatial="rede simulada completa",
            temporal="todas as partidas da janela e período de escoamento",
            numerator=100,
            denominator=100,
        ),
        "formula_version": "catalog-v1",
        "source_kind": "synthetic_generated",
        "production_method": "simulated",
        "producer": "sumo-adapter",
        "producer_version": "1.0",
        "seed": 42,
    }
    values.update(overrides)
    return IndicatorValue.model_validate(values)


def test_integrated_catalog_uses_versioned_ids_and_parent_links() -> None:
    definitions = {item.indicator_id: item for item in INDICATOR_CATALOG}

    assert definitions["MOB-01"].version == "1.0"
    assert definitions["MOB-01"].period_scope == "janela de demanda"
    assert definitions["SER-02a"].base_indicator_id == "SER-02"
    assert definitions["SER-02b"].base_indicator_id == "SER-02"
    assert definitions["AMB-01a"].base_indicator_id == "AMB-01"
    assert definitions["AMB-03a"].base_indicator_id == "AMB-03"
    assert "SER-02" not in definitions


def test_catalog_units_and_periods_are_specific_to_each_indicator() -> None:
    assert indicator_definition("MOB-01").period_scope == "janela de demanda"
    assert indicator_definition("MOB-01").period_type == "simulation_window"
    assert indicator_definition("MOB-07").unit == "m"
    assert indicator_definition("HAB-03").unit == "domicílios e % da coorte elegível"
    assert indicator_definition("SER-02a").unit == "vagas/ano letivo"
    assert indicator_definition("SER-02b").unit == "consultas/ano"
    assert indicator_definition("AMB-01a").unit == "kg CO₂e/ano sintético"
    assert indicator_definition("AMB-02").unit_policy == "source_declared"


def test_unavailable_indicator_is_null_with_reason_and_catalog_metadata() -> None:
    result = unavailable_indicator(
        "SER-01",
        reason="unknown_coverage",
        period="rodada anual 1",
        period_type="observation_period",
        territory="cinco distritos urbanos",
        coverage=IndicatorCoverage(status="unknown", spatial="rede de serviços ausente", temporal="ano 1"),
        producer="annual-engine",
        producer_version="1.0",
        parent_state_hash="parent-hash",
        result_hash="result-hash",
    )

    assert result.value is None
    assert result.null_reason == "unknown_coverage"
    assert result.unit == indicator_definition("SER-01").unit
    assert result.period == "rodada anual 1"
    assert result.coverage.status == "unknown"
    assert result.source_kind is None
    assert result.production_method is None


@pytest.mark.parametrize(
    ("value", "reason"),
    [(None, None), (1, "missing_input")],
)
def test_value_and_null_reason_must_be_consistent(value: int | None, reason: str | None) -> None:
    with pytest.raises(ValidationError, match="null_reason"):
        _available(value=value, null_reason=reason)


def test_zero_is_a_valid_value_and_synthetic_provenance_stays_separate() -> None:
    result = _available(value=0, source_kind="synthetic_config", production_method="derived")

    assert result.value == 0
    assert result.source_kind == "synthetic_config"
    assert result.production_method == "derived"
    assert result.source_kind != "observed"


def test_provenance_axes_are_required_together_but_not_collapsed() -> None:
    with pytest.raises(ValidationError, match="source_kind e production_method"):
        _available(source_kind="synthetic_generated", production_method=None)
    with pytest.raises(ValidationError, match="valor disponível exige source_kind"):
        _available(source_kind=None, production_method=None)


def test_result_identity_version_unit_and_formula_are_bound_to_catalog() -> None:
    with pytest.raises(ValidationError, match="indicator_version"):
        _available(indicator_version="2.0")
    with pytest.raises(ValidationError, match="unidade fixa"):
        _available(unit="passageiros/ano")
    with pytest.raises(ValidationError, match="não catalogado"):
        _available(indicator_id="CUSTOM-01")


def test_mobility_results_cannot_be_annualized() -> None:
    with pytest.raises(ValidationError, match="period_type"):
        _available(period_type="annual_round", period="ano 2025")


def test_observed_result_requires_auditable_source_license_and_coverage() -> None:
    with pytest.raises(ValidationError, match="fonte e licença"):
        _available(source_kind="observed", production_method="measured")
    with pytest.raises(ValidationError, match="cobertura auditável"):
        _available(
            source_kind="observed",
            production_method="measured",
            source_id="monitoring-station-1",
            source_license="open-data-license",
            coverage=IndicatorCoverage(status="unknown", spatial="unknown", temporal="unknown"),
        )


def test_amb02_accepts_source_declared_unit_only_with_auditable_source() -> None:
    result = _available(
        indicator_id="AMB-02",
        unit="mg/m³",
        unit_basis="source_declared",
        period_type="observation_period",
        source_kind="observed",
        production_method="measured",
        source_id="monitoring-station-1",
        source_license="open-data-license",
    )

    assert result.unit == "mg/m³"
    assert result.unit_basis == "source_declared"
    with pytest.raises(ValidationError, match="unidade declarada exige origem"):
        _available(
            indicator_id="AMB-02",
            unit="mg/m³",
            unit_basis="source_declared",
            period_type="observation_period",
            source_kind="synthetic_generated",
            production_method="simulated",
        )


def test_coverage_requires_valid_paired_counts() -> None:
    with pytest.raises(ValidationError, match="em conjunto"):
        IndicatorCoverage(status="partial", spatial="distrito", temporal="ano", numerator=3)
    with pytest.raises(ValidationError, match="0 <= numerador"):
        IndicatorCoverage(status="partial", spatial="distrito", temporal="ano", numerator=4, denominator=3)
    with pytest.raises(ValidationError, match="0 <= numerador"):
        IndicatorCoverage(status="partial", spatial="distrito", temporal="ano", numerator=float("nan"), denominator=4)


def test_unknown_catalog_indicator_is_not_silently_registered() -> None:
    with pytest.raises(KeyError, match="não catalogado"):
        indicator_definition("CUSTOM-01")
