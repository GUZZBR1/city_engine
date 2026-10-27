"""Deterministic annual transition pipeline for one Aurora instance."""

from __future__ import annotations

import copy
from collections.abc import Sequence

from .actions import (
    DEFAULT_ACTION_CATALOG,
    ActionCatalog,
    ArbitrationContext,
    arbitrate_proposal,
)
from .budget import BudgetEnvelope
from .indicators import (
    INDICATOR_CATALOG,
    IndicatorCoverage,
    IndicatorValue,
    indicator_definition,
    unavailable_indicator,
)
from .manifest import ExperimentManifest
from .observations import Observation, build_observation
from .repository import ProposalRecord, RoundRecord
from .state import (
    CityState,
    CityStateDelta,
    EffectiveEvent,
    StateFactory,
    StateTransitionResult,
)
from .transitions.employment import transition_employment
from .transitions.environment import (
    estimate_annual_co2e,
    transition_environment,
    urban_green_area_per_resident,
)
from .transitions.housing import transition_housing
from .transitions.population import transition_population
from .transitions.services import transition_services

ENGINE_VERSION = "1.0"


class AnnualRoundEngine:
    """Build candidate observations, arbitrate proposals, then run pure domains."""

    def __init__(
        self,
        manifest: ExperimentManifest,
        *,
        catalog: ActionCatalog = DEFAULT_ACTION_CATALOG,
        budget_envelope: BudgetEnvelope | None = None,
    ) -> None:
        self.manifest = manifest
        self.catalog = catalog
        self.budget_envelope = budget_envelope or BudgetEnvelope()

    def prepare_observation(
        self,
        parent: CityState,
        *,
        previous_indicators: Sequence[IndicatorValue] = (),
    ) -> tuple[CityState, Observation]:
        """Apply due effects to a private candidate before freezing its view."""
        round_index = parent.round_index + 1
        if round_index > self.manifest.horizon_rounds:
            raise ValueError("rodada excede o horizonte do manifesto")
        candidate = StateFactory.candidate(parent, round_index=round_index)
        candidate = self._apply_due_effects(candidate, round_index)
        observation = build_observation(
            candidate,
            self.manifest,
            previous_indicators=previous_indicators,
            catalog=self.catalog,
        )
        return candidate, observation

    def execute_round(
        self,
        parent: CityState,
        observed_candidate: CityState,
        observation: Observation,
        proposal_record: ProposalRecord,
        *,
        existing_commitments_cs: dict[int, int] | None = None,
    ) -> RoundRecord:
        """Evaluate one frozen proposal and compute, but do not commit, a round."""
        proposal = proposal_record.proposal
        round_index = parent.round_index + 1
        if (
            observed_candidate.round_index != round_index
            or observed_candidate.parent_city_state_hash != parent.city_state_hash
            or observed_candidate.experiment_id != parent.experiment_id
            or observed_candidate.instance_id != parent.instance_id
        ):
            raise ValueError("candidato observado não corresponde ao estado pai/rodada")
        if observation.city_state_hash != observed_candidate.city_state_hash:
            raise ValueError("observação não corresponde ao candidato congelado")
        if (
            proposal.experiment_id != self.manifest.experiment_id
            or proposal.instance_id != parent.instance_id
            or proposal.round_index != round_index
            or proposal.observed_city_state_hash != observation.city_state_hash
        ):
            raise ValueError("ActionProposal não corresponde à observação congelada")
        if not 1 <= round_index <= self.manifest.horizon_rounds:
            raise ValueError("rodada excede o horizonte do manifesto")

        context = ArbitrationContext(
            experiment_id=self.manifest.experiment_id,
            agent_id=proposal.agent_id,
            instance_id=parent.instance_id,
            round_index=round_index,
            horizon_rounds=self.manifest.horizon_rounds,
            observed_city_state_hash=observation.city_state_hash,
            existing_commitments_cs=existing_commitments_cs or {},
        )
        decision = arbitrate_proposal(
            proposal,
            context,
            catalog=self.catalog,
            envelope=self.budget_envelope,
        )
        if decision.accepted and proposal.actions:
            # No action application adapter is integrated in this version. The
            # default catalog keeps every action disabled, so fail closed if a
            # future catalog enables an action without its state effect handler.
            raise RuntimeError("ação aceita sem adaptador de aplicação integrado")

        transition_delta, candidate = self._run_annual_domains(
            parent,
            observed_candidate,
            round_index,
        )
        indicators = self._calculate_indicators(
            candidate,
            round_index=round_index,
            parent_hash=parent.city_state_hash,
        )
        transition = StateTransitionResult(
            experiment_id=parent.experiment_id,
            instance_id=parent.instance_id,
            round_index=round_index,
            manifest_hash=self.manifest.manifest_hash,
            parent_city_state_hash=parent.city_state_hash,
            city_state_hash=candidate.city_state_hash,
            domain_transition="applied",
            delta=transition_delta,
            candidate_state=candidate,
        )
        return RoundRecord(
            proposal_record=proposal_record,
            decision=decision,
            indicator_results=indicators,
            state_transition=transition,
            observed_city_state_hash=observation.city_state_hash,
        )

    def _apply_due_effects(self, candidate: CityState, round_index: int) -> CityState:
        remaining: list[EffectiveEvent] = []
        for event in candidate.pending_effects:
            if event.effective_round < round_index:
                raise ValueError(f"efeito vencido não aplicado: {event.event_id}")
            if event.effective_round > round_index:
                remaining.append(event.model_copy(deep=True))
                continue
            raise ValueError(
                "sem handler validado para aplicar efeito vencido: "
                f"{event.event_type}; ações semafóricas permanecem desabilitadas sem SUMO"
            )

        values = candidate.model_dump(mode="python")
        values["pending_effects"] = remaining
        return CityState.model_validate(values)

    def _run_annual_domains(
        self,
        parent: CityState,
        candidate: CityState,
        round_index: int,
    ) -> tuple[CityStateDelta, CityState]:
        population = transition_population(parent, self.manifest)
        housing = transition_housing(parent, self.manifest, population)
        employment = transition_employment(parent, self.manifest)

        candidate = _apply_domain_delta(candidate, parent, population)
        candidate = _apply_domain_delta(candidate, parent, housing)
        candidate = _apply_domain_delta(candidate, parent, employment)

        services = transition_services(parent, candidate, self.manifest)
        environment = transition_environment(parent, candidate, self.manifest)
        candidate = _apply_domain_delta(
            candidate,
            parent,
            CityStateDelta(parent_city_state_hash=parent.city_state_hash, domains=(services,)),
        )
        candidate = _apply_domain_delta(
            candidate,
            parent,
            CityStateDelta(parent_city_state_hash=parent.city_state_hash, domains=(environment,)),
        )
        if candidate.round_index != round_index:
            raise ValueError("transições anuais alteraram a identidade da rodada")

        combined = CityStateDelta(
            parent_city_state_hash=parent.city_state_hash,
            domains=(
                population.domains[0],
                housing.domains[0],
                employment.domains[0],
                services,
                environment,
            ),
            effective_events=(
                *population.effective_events,
                *housing.effective_events,
                *employment.effective_events,
            ),
        )
        return combined, candidate

    def _calculate_indicators(
        self,
        state: CityState,
        *,
        round_index: int,
        parent_hash: str,
    ) -> tuple[IndicatorValue, ...]:
        period = f"synthetic_year:{round_index}"
        territory = "cinco distritos urbanos de Aurora"
        coverage = IndicatorCoverage(
            status="complete",
            spatial=territory,
            temporal=period,
        )
        school_unmet = sum(
            max(0.0, demand - state.services.school.capacity_by_district[district_id])
            for district_id, demand in state.services.school.demand_by_district.items()
        )
        health_unmet = sum(
            max(0.0, demand - state.services.primary_health.capacity_by_district[district_id])
            for district_id, demand in state.services.primary_health.demand_by_district.items()
        )
        co2e, co2e_reason = estimate_annual_co2e(state, self.manifest)
        green_per_resident, green_reason = urban_green_area_per_resident(state, self.manifest)
        computed: dict[str, tuple[int | float | None, str | None, str, tuple[str, ...]]] = {
            "SER-02a": (
                school_unmet,
                None,
                "derived",
                ("Hiato sintético entre demanda modelada e capacidade nominal; não é atendimento observado.",),
            ),
            "SER-02b": (
                health_unmet,
                None,
                "derived",
                ("Hiato sintético entre demanda modelada e capacidade nominal; não é atendimento observado.",),
            ),
            "AMB-01a": (
                co2e,
                co2e_reason,
                "estimated",
                ("Atividade veículo-km exógena; não mede efeito de tráfego, SUMO ou concentração atmosférica.",),
            ),
            "AMB-03a": (
                green_per_resident,
                green_reason,
                "derived",
                ("Agregado sintético dos cinco distritos urbanos; não mede acesso, qualidade ou segurança.",),
            ),
        }

        results: list[IndicatorValue] = []
        for definition in INDICATOR_CATALOG:
            value_data = computed.get(definition.indicator_id)
            if value_data is None:
                reason = _unavailable_indicator_reason(definition.indicator_id)
                results.append(
                    unavailable_indicator(
                        definition.indicator_id,
                        reason=reason,
                        period=period,
                        period_type=definition.period_type,
                        territory=territory,
                        coverage=IndicatorCoverage(
                            status="unknown",
                            spatial=territory,
                            temporal=period,
                        ),
                        producer="aurora_annual_round_engine",
                        producer_version=ENGINE_VERSION,
                        parent_state_hash=parent_hash,
                        result_hash=state.city_state_hash,
                        limitations=("A integração v1 não possui os insumos tipados necessários para este indicador.",),
                    )
                )
                continue

            value, null_reason, method, limitations = value_data
            definition = indicator_definition(definition.indicator_id)
            results.append(
                IndicatorValue(
                    indicator_id=definition.indicator_id,
                    indicator_version=definition.version,
                    value=value,
                    null_reason=null_reason,
                    unit=definition.unit,
                    period=period,
                    period_type=definition.period_type,
                    territory=territory,
                    coverage=coverage,
                    formula_version=definition.formula_version,
                    source_kind="synthetic_config" if value is not None else None,
                    production_method=method if value is not None else None,
                    producer="aurora_annual_round_engine",
                    producer_version=ENGINE_VERSION,
                    parent_state_hash=parent_hash,
                    result_hash=state.city_state_hash,
                    limitations=limitations,
                )
            )
        return tuple(results)


def _unavailable_indicator_reason(indicator_id: str) -> str:
    if indicator_id.startswith("MOB-") or indicator_id in {"AMB-01", "FIN-01", "FIN-02", "FIN-03"}:
        return "not_applicable"
    if indicator_id in {"SER-01", "AMB-03", "EQU-01", "EQU-02", "EQU-03"}:
        return "unknown_coverage"
    return "missing_input"


def _apply_domain_delta(
    candidate: CityState,
    parent: CityState,
    delta: CityStateDelta,
) -> CityState:
    if delta.parent_city_state_hash != parent.city_state_hash:
        raise ValueError("delta referencia um estado pai diferente do candidato")
    values = candidate.model_dump(mode="python")
    for domain in delta.domains:
        values[domain.domain] = copy.deepcopy(domain.values)
    return CityState.model_validate(values)
