"""Process-local API jobs for the synthetic Aurora annual arena."""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass
from threading import RLock
from uuid import uuid4

from simulation import load_aurora_input
from urban_arena.actions import (
    DEFAULT_ACTION_CATALOG,
    ActionCatalog,
    ActionReceipt,
    ProposedAction,
    SignalTarget,
)
from urban_arena.arena import ArenaInstance, ArenaRunner, ParticipantFailure
from urban_arena.budget import BudgetAssessment, BudgetCharge
from urban_arena.indicators import IndicatorValue
from urban_arena.manifest import ExperimentManifest, build_aurora_synthetic_v1_manifest
from urban_arena.policies import (
    AgentPolicy,
    DeterministicReferencePolicy,
    FixedSignalTimingPolicy,
)
from urban_arena.repository import RoundRecord
from urban_arena.state import CityState, EffectiveEvent, ServiceDomainState

from .arena_mobility import ArenaSignalSumoEvaluator
from .arena_schemas import (
    ArenaActionReceiptDTO,
    ArenaBudgetAssessmentDTO,
    ArenaBudgetChargeDTO,
    ArenaBudgetStateDTO,
    ArenaCityStateDTO,
    ArenaDecisionDTO,
    ArenaEffectiveEventDTO,
    ArenaEmploymentStateDTO,
    ArenaEnvironmentStateDTO,
    ArenaFailure,
    ArenaHousingStateDTO,
    ArenaIndicatorCoverageDTO,
    ArenaIndicatorDTO,
    ArenaInstanceDTO,
    ArenaJob,
    ArenaManifestDTO,
    ArenaPopulationStateDTO,
    ArenaProposalActionDTO,
    ArenaProposalDTO,
    ArenaRequest,
    ArenaRoundBudgetDTO,
    ArenaRoundDTO,
    ArenaRoundInstanceDTO,
    ArenaServiceDomainStateDTO,
    ArenaServicesStateDTO,
)


class ArenaNotFoundError(LookupError):
    pass


@dataclass
class _ArenaRecord:
    job: ArenaJob
    runner: ArenaRunner
    policies: tuple[AgentPolicy, ...]


_jobs: dict[str, _ArenaRecord] = {}
_jobs_lock = RLock()
_logger = logging.getLogger(__name__)


def create_arena(request: ArenaRequest) -> ArenaJob:
    """Prepare a queued arena from the one supported synthetic snapshot."""
    config, snapshot = _load_aurora_snapshot()
    experiment_id = str(uuid4())
    manifest = build_aurora_synthetic_v1_manifest(
        config,
        snapshot,
        experiment_id=experiment_id,
        horizon_rounds=request.horizon_rounds,
    )
    runner_options: dict[str, object] = {}
    sumo_available = bool(shutil.which("sumo") and shutil.which("netconvert"))
    if sumo_available:
        mobility_input = load_aurora_input(snapshot.city_id, "weekday_am_peak")
        if mobility_input.snapshot_hash != snapshot.hash:
            raise ValueError("entrada SUMO e snapshot anual devem ter o mesmo hash")
        signal_targets = tuple(
            SignalTarget(
                node_id=signal.node_id,
                phases=tuple(
                    {"movement": phase.movement, "duration_s": phase.duration_seconds}
                    for phase in signal.phases
                ),
            )
            for signal in mobility_input.traffic_signals
        )
        catalog = ActionCatalog(actions=tuple(
            item.model_copy(update={"enabled": True, "unavailable_reason": None})
            if item.action_type == "signal_timing_change"
            else item
            for item in DEFAULT_ACTION_CATALOG.actions
        ))
        runner_options = {
            "catalog": catalog,
            "signal_targets": signal_targets,
            "action_executor": ArenaSignalSumoEvaluator(mobility_input),
        }
    runner = ArenaRunner(snapshot, manifest=manifest, **runner_options)
    if sumo_available:
        ns_priority = (("north_south", 40), ("all_red", 3), ("east_west", 20), ("all_red", 3))
        ew_priority = (("north_south", 30), ("all_red", 3), ("east_west", 30), ("all_red", 3))
        policies: tuple[AgentPolicy, ...] = (
            DeterministicReferencePolicy(
                agent_id="baseline-no-action",
                policy_id="baseline-no-action-v1",
            ),
            FixedSignalTimingPolicy(
                agent_id="signal-ns-node-0200",
                policy_id="heuristic-ns-node-0200-v1",
                signal_changes=(("node:02:00", ns_priority),),
            ),
            FixedSignalTimingPolicy(
                agent_id="signal-ew-node-0200",
                policy_id="heuristic-ew-node-0200-v1",
                signal_changes=(("node:02:00", ew_priority),),
            ),
            FixedSignalTimingPolicy(
                agent_id="signal-ns-node-0204",
                policy_id="heuristic-ns-node-0204-v1",
                signal_changes=(("node:02:04", ns_priority),),
            ),
            FixedSignalTimingPolicy(
                agent_id="signal-coordinated-two-nodes",
                policy_id="heuristic-coordinated-two-nodes-v1",
                signal_changes=(
                    ("node:02:00", ns_priority),
                    ("node:02:04", ew_priority),
                ),
            ),
        )
    else:
        policies = tuple(
            DeterministicReferencePolicy(
                agent_id=f"reference-agent-{index:02d}",
                policy_id=f"deterministic-reference-{index:02d}",
            )
            for index in range(1, 6)
        )
    arena_id = str(uuid4())
    policy_by_instance = {
        instance.instance_id: policy
        for instance, policy in zip(runner.instances, policies, strict=True)
    }
    instances = [
        _instance_dto(
            instance,
            runner.state_copy(instance.instance_id),
            policy_by_instance[instance.instance_id],
        )
        for instance in runner.instances
    ]
    job = ArenaJob(
        arena_id=arena_id,
        status="queued",
        city_id=snapshot.city_id,
        provenance=snapshot.provenance,
        experiment_id=manifest.experiment_id,
        snapshot_id=manifest.snapshot_id,
        snapshot_hash=manifest.snapshot_hash,
        manifest_hash=manifest.manifest_hash,
        manifest=_manifest_dto(manifest),
        horizon_rounds=manifest.horizon_rounds,
        committed_rounds=0,
        completed_rounds=0,
        instances=instances,
    )
    with _jobs_lock:
        _jobs[arena_id] = _ArenaRecord(job=job, runner=runner, policies=policies)
    return job.model_copy(deep=True)


def get_arena(arena_id: str) -> ArenaJob:
    with _jobs_lock:
        record = _jobs.get(arena_id)
        if record is None:
            raise ArenaNotFoundError(arena_id)
        return record.job.model_copy(deep=True)


def run_arena(arena_id: str) -> None:
    """Run annual rounds, publishing only complete committed groups of five."""
    with _jobs_lock:
        record = _jobs.get(arena_id)
        if record is None or record.job.status != "queued":
            return
        record.job = record.job.model_copy(update={"status": "running"})

    for round_index in range(1, record.job.horizon_rounds + 1):
        try:
            committed = record.runner.run_round(round_index, record.policies)
        except ParticipantFailure as exc:
            _logger.exception(
                "Arena participant failed before round %s committed (arena_id=%s)",
                round_index,
                arena_id,
            )
            _fail_arena(
                arena_id,
                ArenaFailure(
                    code="participant_failed",
                    message=f"A rodada {round_index} falhou; nenhum resultado dessa rodada foi publicado.",
                    round_index=round_index,
                    instance_id=exc.instance_id,
                ),
            )
            return
        except Exception:
            _logger.exception("Arena round execution failed (arena_id=%s, round=%s)", arena_id, round_index)
            _fail_arena(
                arena_id,
                ArenaFailure(
                    code="arena_round_failed",
                    message=f"A rodada {round_index} falhou; nenhum resultado dessa rodada foi publicado.",
                    round_index=round_index,
                ),
            )
            return

        # run_round returns only after the domain has committed its five records.
        # Track that fact before attempting API serialization: later mapping errors
        # must not make the GET response look as if the runner stayed on an older state.
        try:
            policies_by_instance = {
                instance.instance_id: policy
                for instance, policy in zip(record.runner.instances, record.policies, strict=True)
            }
            updated_instances = [
                _instance_dto(
                    instance,
                    record.runner.state_copy(instance.instance_id),
                    policies_by_instance[instance.instance_id],
                )
                for instance in record.runner.instances
            ]
        except Exception:
            _logger.exception(
                "Arena committed states could not be serialized (arena_id=%s, round=%s)",
                arena_id,
                round_index,
            )
            _fail_committed_round(
                arena_id,
                round_index=round_index,
                instances=_committed_instance_summaries(record),
                failure=ArenaFailure(
                    code="arena_state_serialization_failed",
                    message=(
                        f"A rodada {round_index} foi confirmada pelo motor, mas os estados não puderam ser serializados. "
                        "Nenhum detalhe dessa rodada foi publicado."
                    ),
                    round_index=round_index,
                ),
            )
            return

        with _jobs_lock:
            current = _jobs.get(arena_id)
            if current is not record:
                return
            record.job = record.job.model_copy(update={
                "committed_rounds": record.job.committed_rounds + 1,
                "instances": updated_instances,
            })

        try:
            if len(committed) != 5 or len({item.instance_id for item in committed}) != 5:
                raise ValueError("committed round must contain exactly five unique instances")
            round_dto = _round_dto(committed)
        except Exception:
            _logger.exception(
                "Arena committed round details could not be serialized (arena_id=%s, round=%s)",
                arena_id,
                round_index,
            )
            _fail_arena(
                arena_id,
                ArenaFailure(
                    code="arena_result_serialization_failed",
                    message=(
                        f"A rodada {round_index} foi confirmada pelo motor, mas seus detalhes não puderam ser serializados. "
                        "Nenhum detalhe dessa rodada foi publicado."
                    ),
                    round_index=round_index,
                ),
            )
            return

        with _jobs_lock:
            current = _jobs.get(arena_id)
            if current is not record:
                return
            rounds = [*record.job.rounds, round_dto]
            record.job = record.job.model_copy(update={
                "completed_rounds": record.job.completed_rounds + 1,
                "rounds": rounds,
            })

    with _jobs_lock:
        current = _jobs.get(arena_id)
        if current is record:
            record.job = record.job.model_copy(update={"status": "succeeded"})


def _fail_arena(arena_id: str, failure: ArenaFailure) -> None:
    with _jobs_lock:
        record = _jobs.get(arena_id)
        if record is not None:
            record.job = record.job.model_copy(update={"status": "failed", "error": failure})


def _committed_instance_summaries(record: _ArenaRecord) -> list[ArenaInstanceDTO]:
    """Expose confirmed state identity/hash while marking full state unavailable."""
    existing_by_id = {instance.instance_id: instance for instance in record.job.instances}
    summaries: list[ArenaInstanceDTO] = []
    for instance in record.runner.instances:
        state = record.runner.state_copy(instance.instance_id)
        existing = existing_by_id[instance.instance_id]
        summaries.append(existing.model_copy(update={
            "current_city_state_hash": state.city_state_hash,
            "current_round_index": state.round_index,
            "current_state": None,
        }))
    return summaries


def _fail_committed_round(
    arena_id: str,
    *,
    round_index: int,
    instances: list[ArenaInstanceDTO],
    failure: ArenaFailure,
) -> None:
    """Record a runner commit even when the current-state DTO mapping also fails."""
    with _jobs_lock:
        record = _jobs.get(arena_id)
        if record is not None:
            record.job = record.job.model_copy(update={
                "status": "failed",
                "committed_rounds": record.job.committed_rounds + 1,
                "instances": instances,
                "error": failure,
            })


def _load_aurora_snapshot():
    # Import the package-level loader only; the API never accepts arbitrary city data.
    from urban_arena import load_aurora_snapshot

    config, snapshot = load_aurora_snapshot()
    if snapshot.city_id != "aurora-base-v1" or snapshot.provenance != "synthetic":
        raise ValueError("a API de arena aceita apenas o snapshot sintético Aurora existente")
    return config, snapshot


def _manifest_dto(manifest: ExperimentManifest) -> ArenaManifestDTO:
    return ArenaManifestDTO(
        schema_version=manifest.schema_version,
        profile_id=manifest.profile_id,
        profile_version=manifest.profile_version,
        parameter_version=manifest.parameter_version,
        horizon_rounds=manifest.horizon_rounds,
        snapshot_id=manifest.snapshot_id,
        snapshot_hash=manifest.snapshot_hash,
        generator_version=manifest.generator_version,
        transition_version=manifest.transition_version,
        parameters=manifest.parameters.model_dump(mode="json"),
        seeds=dict(manifest.seeds),
        catalog_version=manifest.catalog_version,
        rules_version=manifest.rules_version,
        provenance=manifest.provenance,
        manifest_hash=manifest.manifest_hash,
    )


def _instance_dto(
    instance: ArenaInstance,
    state: CityState,
    policy: DeterministicReferencePolicy,
) -> ArenaInstanceDTO:
    return ArenaInstanceDTO(
        experiment_id=instance.experiment_id,
        instance_id=instance.instance_id,
        agent_id=policy.agent_id,
        policy_id=policy.policy_id,
        policy_version=policy.policy_version,
        initial_city_state_hash=instance.initial_city_state_hash,
        current_city_state_hash=state.city_state_hash,
        current_round_index=state.round_index,
        current_state=_city_state(state),
    )


def _city_state(state: CityState) -> ArenaCityStateDTO:
    return ArenaCityStateDTO(
        experiment_id=state.experiment_id,
        instance_id=state.instance_id,
        round_index=state.round_index,
        schema_version=state.schema_version,
        transition_version=state.transition_version,
        parent_city_state_hash=state.parent_city_state_hash,
        snapshot_hash=state.snapshot_hash,
        city_state_hash=state.city_state_hash,
        population=ArenaPopulationStateDTO(
            residents_by_district=dict(state.population.residents_by_district),
            total_residents=state.population.total_residents,
            urban_residents=state.population.urban_residents,
            rural_catchment_residents=state.population.rural_catchment_residents,
        ),
        housing=ArenaHousingStateDTO(
            initialization_method=state.housing.initialization_method,
            occupied_households_reference_total=state.housing.occupied_households_reference_total,
            occupied_households_urban=state.housing.occupied_households_urban,
            vacancy_rate_target=state.housing.vacancy_rate_target,
            units_by_district=dict(state.housing.units_by_district),
            total_units=state.housing.total_units,
        ),
        employment=ArenaEmploymentStateDTO(
            jobs_by_district=dict(state.employment.jobs_by_district),
            total_jobs=state.employment.total_jobs,
        ),
        services=ArenaServicesStateDTO(
            school=_service_state(state.services.school),
            primary_health=_service_state(state.services.primary_health),
        ),
        environment=ArenaEnvironmentStateDTO(
            public_green_area_m2_by_district=dict(state.environment.public_green_area_m2_by_district),
        ),
        budget=ArenaBudgetStateDTO(
            currency=state.budget.currency,
            credits_per_round=state.budget.credits_per_round,
            fixed_operations=state.budget.fixed_operations,
            reserve=state.budget.reserve,
            discretionary_budget=state.budget.discretionary_budget,
        ),
        pending_effects=[_effective_event(event) for event in state.pending_effects],
        active_signal_plans=[_effective_event(event) for event in state.active_signal_plans],
    )


def _service_state(service: ServiceDomainState) -> ArenaServiceDomainStateDTO:
    return ArenaServiceDomainStateDTO(
        demand_by_district=dict(service.demand_by_district),
        capacity_by_district=dict(service.capacity_by_district),
    )


def _effective_event(event: EffectiveEvent) -> ArenaEffectiveEventDTO:
    return ArenaEffectiveEventDTO(
        event_id=event.event_id,
        event_type=event.event_type,
        effective_round=event.effective_round,
        payload=dict(event.payload),
        source_action_id=event.source_action_id,
    )


def _round_dto(records: tuple[RoundRecord, ...]) -> ArenaRoundDTO:
    ordered = sorted(records, key=lambda item: item.instance_id)
    return ArenaRoundDTO(
        round_index=ordered[0].round_index,
        instances=[_round_instance_dto(record) for record in ordered],
    )


def _round_instance_dto(record: RoundRecord) -> ArenaRoundInstanceDTO:
    proposal_record = record.proposal_record
    proposal = proposal_record.proposal
    decision = record.decision
    transition = record.state_transition
    return ArenaRoundInstanceDTO(
        instance_id=record.instance_id,
        proposal=ArenaProposalDTO(
            schema_version=proposal.schema_version,
            experiment_id=proposal.experiment_id,
            proposal_id=proposal.proposal_id,
            idempotency_key=proposal.idempotency_key,
            agent_id=proposal.agent_id,
            instance_id=proposal.instance_id,
            round_index=proposal.round_index,
            observed_city_state_hash=proposal.observed_city_state_hash,
            actions=[_action(action) for action in proposal.actions],
            budget_request=proposal.budget_request,
            policy_id=proposal_record.policy_id,
            policy_version=proposal_record.policy_version,
            proposal_record_hash=proposal_record.content_hash,
        ),
        decision=ArenaDecisionDTO(
            proposal_id=decision.proposal_id,
            idempotency_key=decision.idempotency_key,
            proposal_hash=decision.proposal_hash,
            accepted=decision.accepted,
            decision=decision.decision,
            code=decision.code,
            actions=[_action_receipt(receipt) for receipt in decision.actions],
            budget=_budget_assessment(decision.budget) if decision.budget is not None else None,
        ),
        action_execution_evidence=(
            record.action_execution_evidence.model_dump(mode="json")
            if record.action_execution_evidence is not None
            else None
        ),
        indicators=[_indicator(indicator) for indicator in record.indicator_results],
        observed_city_state_hash=record.observed_city_state_hash,
        parent_city_state_hash=transition.parent_city_state_hash,
        city_state_hash=transition.city_state_hash,
        manifest_hash=transition.manifest_hash,
        round_record_hash=record.round_record_hash,
    )


def _action(action: ProposedAction) -> ArenaProposalActionDTO:
    parameters = action.parameters
    if action.action_type == "signal_timing_change":
        mapped_parameters = {"phases": [
            {"movement": phase.movement, "duration_s": phase.duration_s}
            for phase in parameters.phases
        ]}
    elif action.action_type == "housing_add_units":
        mapped_parameters = {"units": parameters.units}
    else:
        mapped_parameters = {
            "service_type": parameters.service_type,
            "unit": parameters.unit,
            "capacity_units": parameters.capacity_units,
        }
    return ArenaProposalActionDTO(
        action_id=action.action_id,
        action_type=action.action_type,
        target_id=action.target_id,
        parameters=mapped_parameters,
        rationale=action.rationale,
    )


def _action_receipt(receipt: ActionReceipt) -> ArenaActionReceiptDTO:
    return ArenaActionReceiptDTO(
        action_id=receipt.action_id,
        action_type=receipt.action_type,
        accepted=receipt.accepted,
        code=receipt.code,
        message=receipt.message,
        charges=[_charge(charge) for charge in receipt.charges],
        effective_round=receipt.effective_round,
        conflict_key=receipt.conflict_key,
    )


def _charge(charge: BudgetCharge) -> ArenaBudgetChargeDTO:
    return ArenaBudgetChargeDTO(
        round_index=charge.round_index,
        amount_cs=charge.amount_cs,
        kind=charge.kind,
        source_action_id=charge.source_action_id,
    )


def _budget_assessment(budget: BudgetAssessment) -> ArenaBudgetAssessmentDTO:
    return ArenaBudgetAssessmentDTO(
        accepted=budget.accepted,
        code=budget.code,
        rounds=[
            ArenaRoundBudgetDTO(
                round_index=item.round_index,
                limit_cs=item.limit_cs,
                already_committed_cs=item.already_committed_cs,
                proposed_cs=item.proposed_cs,
                available_cs=item.available_cs,
            )
            for item in budget.rounds
        ],
        charges=[_charge(item) for item in budget.charges],
    )


def _indicator(indicator: IndicatorValue) -> ArenaIndicatorDTO:
    coverage = indicator.coverage
    return ArenaIndicatorDTO(
        indicator_id=indicator.indicator_id,
        indicator_version=indicator.indicator_version,
        value=indicator.value,
        null_reason=indicator.null_reason,
        unit=indicator.unit,
        unit_basis=indicator.unit_basis,
        period=indicator.period,
        period_type=indicator.period_type,
        territory=indicator.territory,
        coverage=ArenaIndicatorCoverageDTO(
            status=coverage.status,
            spatial=coverage.spatial,
            temporal=coverage.temporal,
            numerator=coverage.numerator,
            denominator=coverage.denominator,
            filters=list(coverage.filters),
        ),
        formula_version=indicator.formula_version,
        source_kind=indicator.source_kind,
        production_method=indicator.production_method,
        source_id=indicator.source_id,
        source_license=indicator.source_license,
        producer=indicator.producer,
        producer_version=indicator.producer_version,
        parent_state_hash=indicator.parent_state_hash,
        result_hash=indicator.result_hash,
        seed=indicator.seed,
        limitations=list(indicator.limitations),
    )
