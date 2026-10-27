"""Versioned action proposal, catalog, and pure atomic arbitration contracts."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, StrictInt, model_validator

from .budget import BudgetAssessment, BudgetCharge, BudgetEnvelope, assess_budget
from .models import StrictModel

ActionType = Literal[
    "signal_timing_change",
    "housing_add_units",
    "service_capacity_contract",
]

# No annual orchestrator or action adapter exists in this package yet.
_SIGNAL_RUNTIME_INTEGRATED = False


class SignalPhaseProposal(StrictModel):
    movement: Literal["north_south", "all_red", "east_west"]
    duration_s: StrictInt = Field(gt=0)


class SignalTimingParameters(StrictModel):
    phases: tuple[SignalPhaseProposal, ...] = Field(min_length=2)


class HousingParameters(StrictModel):
    units: StrictInt = Field(gt=0, multiple_of=10)


class ServiceParameters(StrictModel):
    service_type: str = Field(min_length=1)
    unit: str = Field(min_length=1)
    capacity_units: StrictInt = Field(default=10, gt=0)


ActionParameters = Annotated[
    SignalTimingParameters | HousingParameters | ServiceParameters,
    Field(discriminator=None),
]


class ProposedAction(StrictModel):
    action_id: str = Field(min_length=1)
    action_type: ActionType
    target_id: str = Field(min_length=1)
    parameters: ActionParameters
    rationale: str | None = None

    @model_validator(mode="after")
    def parameters_match_action(self) -> ProposedAction:
        expected = {
            "signal_timing_change": SignalTimingParameters,
            "housing_add_units": HousingParameters,
            "service_capacity_contract": ServiceParameters,
        }[self.action_type]
        if not isinstance(self.parameters, expected):
            raise ValueError(f"parameters incompatíveis com {self.action_type}")  # noqa: TRY004 - Pydantic validators require ValueError.
        return self


class ActionProposal(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    experiment_id: str = Field(min_length=1)
    proposal_id: str = Field(min_length=1)
    idempotency_key: str = Field(min_length=1)
    agent_id: str = Field(min_length=1)
    instance_id: str = Field(min_length=1)
    round_index: StrictInt = Field(ge=1)
    observed_city_state_hash: str = Field(min_length=1)
    actions: tuple[ProposedAction, ...] = ()
    # Annotation only. It never affects server-calculated costs or authorization.
    budget_request: StrictInt | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_action_ids(self) -> ActionProposal:
        action_ids = [action.action_id for action in self.actions]
        if len(action_ids) != len(set(action_ids)):
            raise ValueError("action_id deve ser único dentro da proposta")
        return self


class ActionDefinition(StrictModel):
    action_type: ActionType
    enabled: bool = False
    unavailable_reason: str | None = None
    setup_cost_cs: StrictInt = Field(ge=0)
    operation_cost_cs: StrictInt = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_availability(self) -> ActionDefinition:
        if not self.enabled and not self.unavailable_reason:
            raise ValueError("ação desabilitada deve informar unavailable_reason")
        if self.enabled and self.unavailable_reason:
            raise ValueError("ação habilitada não pode ter unavailable_reason")
        if self.setup_cost_cs + self.operation_cost_cs == 0:
            raise ValueError("ação sem tarifa configurada deve permanecer indisponível")
        return self


class ActionCatalog(StrictModel):
    version: str = "aurora_actions_v1"
    actions: tuple[ActionDefinition, ...]

    @model_validator(mode="after")
    def validate_unique_actions(self) -> ActionCatalog:
        kinds = [item.action_type for item in self.actions]
        if len(kinds) != len(set(kinds)):
            raise ValueError("catálogo contém action_type duplicado")
        if set(kinds) != {
            "signal_timing_change",
            "housing_add_units",
            "service_capacity_contract",
        }:
            raise ValueError("catálogo v1 deve definir as três ações do contrato integrado")
        return self

    def get(self, action_type: ActionType) -> ActionDefinition:
        return next(item for item in self.actions if item.action_type == action_type)


DEFAULT_ACTION_CATALOG = ActionCatalog(
    actions=(
        ActionDefinition(
            action_type="signal_timing_change",
            unavailable_reason="annual_runtime_integration_incomplete",
            setup_cost_cs=2,
            operation_cost_cs=1,
        ),
        ActionDefinition(
            action_type="housing_add_units",
            unavailable_reason="housing_inventory_unavailable",
            setup_cost_cs=8,
        ),
        ActionDefinition(
            action_type="service_capacity_contract",
            unavailable_reason="service_inventory_unavailable",
            setup_cost_cs=6,
            operation_cost_cs=2,
        ),
    )
)


class SignalTarget(StrictModel):
    node_id: str = Field(min_length=1)
    phases: tuple[SignalPhaseProposal, ...] = Field(min_length=2)


class ArbitrationContext(StrictModel):
    experiment_id: str = Field(min_length=1)
    agent_id: str = Field(min_length=1)
    instance_id: str = Field(min_length=1)
    round_index: StrictInt = Field(ge=1)
    horizon_rounds: StrictInt = Field(default=10, ge=1, le=10)
    observed_city_state_hash: str = Field(min_length=1)
    signal_targets: tuple[SignalTarget, ...] = ()
    existing_commitments_cs: dict[StrictInt, StrictInt] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_context(self) -> ArbitrationContext:
        if self.round_index > self.horizon_rounds:
            raise ValueError("round_index excede o horizonte congelado")
        if len({target.node_id for target in self.signal_targets}) != len(self.signal_targets):
            raise ValueError("signal_targets contém node_id duplicado")
        if any(round_index < 1 for round_index in self.existing_commitments_cs):
            raise ValueError("rodadas de compromissos devem ser positivas")
        return self


class ActionReceipt(StrictModel):
    action_id: str
    action_type: ActionType
    accepted: bool
    code: str
    message: str
    charges: tuple[BudgetCharge, ...] = ()
    effective_round: StrictInt | None = None
    conflict_key: str | None = None


class ArbitrationDecision(StrictModel):
    proposal_id: str
    idempotency_key: str
    proposal_hash: str
    accepted: bool
    decision: Literal["accepted", "rejected", "no_action"]
    code: str
    actions: tuple[ActionReceipt, ...]
    budget: BudgetAssessment | None = None


def _validate_signal_action(
    action: ProposedAction,
    context: ArbitrationContext,
) -> tuple[str, str, int | None]:
    target = next((item for item in context.signal_targets if item.node_id == action.target_id), None)
    if target is None:
        return "target_unavailable", "nó semafórico não existe no estado observado", None
    parameters = action.parameters
    assert isinstance(parameters, SignalTimingParameters)
    expected_order = tuple(phase.movement for phase in target.phases)
    actual_order = tuple(phase.movement for phase in parameters.phases)
    if actual_order != expected_order:
        return "invalid_phase_order", "a proposta deve preservar a ordem de fases do plano existente", None
    if sum(phase.duration_s for phase in parameters.phases) != sum(phase.duration_s for phase in target.phases):
        return "invalid_cycle_duration", "a proposta deve preservar a duração total do ciclo existente", None
    if len(parameters.phases) != 4 or actual_order != ("north_south", "all_red", "east_west", "all_red"):
        return "invalid_phase_plan", "o plano deve usar NS, todos-vermelhos, EW, todos-vermelhos", None
    return "valid", "plano válido para a próxima janela de mobilidade desta rodada", context.round_index


def arbitrate_proposal(
    proposal: ActionProposal,
    context: ArbitrationContext,
    *,
    catalog: ActionCatalog = DEFAULT_ACTION_CATALOG,
    envelope: BudgetEnvelope | None = None,
) -> ArbitrationDecision:
    """Validate a proposal statelessly and calculate all charges server-side.

    Durable retry deduplication belongs at the round repository/commit
    boundary, which is not part of the current package interface.
    """
    import hashlib
    import json

    payload = proposal.model_dump(mode="json")
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    proposal_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    identity_error = (
        proposal.experiment_id != context.experiment_id
        or proposal.agent_id != context.agent_id
        or proposal.instance_id != context.instance_id
        or proposal.round_index != context.round_index
        or proposal.observed_city_state_hash != context.observed_city_state_hash
    )
    if identity_error:
        return ArbitrationDecision(
            proposal_id=proposal.proposal_id,
            idempotency_key=proposal.idempotency_key,
            proposal_hash=proposal_hash,
            accepted=False,
            decision="rejected",
            code="observation_mismatch",
            actions=tuple(
                ActionReceipt(
                    action_id=action.action_id,
                    action_type=action.action_type,
                    accepted=False,
                    code="observation_mismatch",
                    message="identidade, rodada ou hash observado não corresponde ao contexto",
                )
                for action in proposal.actions
            ),
        )
    if not proposal.actions:
        return ArbitrationDecision(
            proposal_id=proposal.proposal_id,
            idempotency_key=proposal.idempotency_key,
            proposal_hash=proposal_hash,
            accepted=True,
            decision="no_action",
            code="empty_proposal",
            actions=(),
            budget=assess_budget(
                (),
                horizon_rounds=context.horizon_rounds,
                existing_commitments=context.existing_commitments_cs,
                envelope=envelope,
            ),
        )

    receipts: list[ActionReceipt] = []
    charge_lines: list[BudgetCharge] = []
    for action in proposal.actions:
        definition = catalog.get(action.action_type)
        if action.action_type == "signal_timing_change" and not _SIGNAL_RUNTIME_INTEGRATED:
            receipts.append(ActionReceipt(
                action_id=action.action_id,
                action_type=action.action_type,
                accepted=False,
                code="annual_runtime_integration_incomplete",
                message="a ação semafórica não está conectada ao runtime anual",
            ))
            continue
        if not definition.enabled:
            receipts.append(ActionReceipt(
                action_id=action.action_id,
                action_type=action.action_type,
                accepted=False,
                code=definition.unavailable_reason or "action_disabled",
                message="ação indisponível nesta integração do runtime",
            ))
            continue
        if action.action_type == "signal_timing_change":
            code, message, effective_round = _validate_signal_action(action, context)
            if code != "valid":
                receipts.append(ActionReceipt(
                    action_id=action.action_id,
                    action_type=action.action_type,
                    accepted=False,
                    code=code,
                    message=message,
                ))
                continue
            same_node = sum(
                other.action_type == "signal_timing_change" and other.target_id == action.target_id
                for other in proposal.actions
            )
            signal_count = sum(other.action_type == "signal_timing_change" for other in proposal.actions)
            if same_node > 1 or signal_count > 2:
                receipts.append(ActionReceipt(
                    action_id=action.action_id,
                    action_type=action.action_type,
                    accepted=False,
                    code="internal_conflict",
                    message="máximo de uma alteração por nó e duas alterações semafóricas por proposta",
                    conflict_key=f"signal:{action.target_id}:{context.round_index}",
                ))
                continue
        elif action.action_type == "housing_add_units":
            # No housing inventory or capacity validator exists in the current
            # annual-state interface, so this action must remain unavailable.
            receipts.append(ActionReceipt(
                action_id=action.action_id,
                action_type=action.action_type,
                accepted=False,
                code="housing_inventory_unavailable",
                message="não há capacidade edificável tipada para validar o alvo",
            ))
            continue
        elif action.action_type == "service_capacity_contract":
            # Service type, unit, facility and baseline are absent from state.
            receipts.append(ActionReceipt(
                action_id=action.action_id,
                action_type=action.action_type,
                accepted=False,
                code="service_inventory_unavailable",
                message="não há inventário tipado para validar tipo, unidade e capacidade-base",
            ))
            continue
        else:
            effective_round = context.round_index + 1

        action_charges: list[BudgetCharge] = []
        if action.action_type == "signal_timing_change":
            action_charges = [
                BudgetCharge(round_index=context.round_index, amount_cs=definition.setup_cost_cs, kind="one_time", source_action_id=action.action_id),
                BudgetCharge(round_index=context.round_index, amount_cs=definition.operation_cost_cs, kind="recurring", source_action_id=action.action_id),
            ]
        elif action.action_type == "housing_add_units":
            parameters = action.parameters
            assert isinstance(parameters, HousingParameters)
            action_charges = [BudgetCharge(
                round_index=context.round_index,
                amount_cs=definition.setup_cost_cs * (parameters.units // 10),
                kind="one_time",
                source_action_id=action.action_id,
            )]
        else:
            action_charges = [
                BudgetCharge(round_index=context.round_index, amount_cs=definition.setup_cost_cs, kind="one_time", source_action_id=action.action_id),
                BudgetCharge(round_index=context.round_index + 1, amount_cs=definition.operation_cost_cs, kind="recurring", source_action_id=action.action_id),
            ]
        charge_lines.extend(action_charges)
        receipts.append(ActionReceipt(
            action_id=action.action_id,
            action_type=action.action_type,
            accepted=True,
            code="validated",
            message="ação validada pelo catálogo",
            charges=tuple(action_charges),
            effective_round=effective_round,
            conflict_key=f"{action.action_type}:{action.target_id}:{effective_round}",
        ))

    if any(not item.accepted for item in receipts):
        return ArbitrationDecision(
            proposal_id=proposal.proposal_id,
            idempotency_key=proposal.idempotency_key,
            proposal_hash=proposal_hash,
            accepted=False,
            decision="rejected",
            code="atomic_validation_failed",
            actions=tuple(
                item.model_copy(update={"accepted": False, "code": "proposal_rejected_atomically"})
                if item.accepted else item
                for item in receipts
            ),
        )

    budget = assess_budget(
        charge_lines,
        horizon_rounds=context.horizon_rounds,
        existing_commitments=context.existing_commitments_cs,
        envelope=envelope,
    )
    if not budget.accepted:
        return ArbitrationDecision(
            proposal_id=proposal.proposal_id,
            idempotency_key=proposal.idempotency_key,
            proposal_hash=proposal_hash,
            accepted=False,
            decision="rejected",
            code=budget.code,
            actions=tuple(item.model_copy(update={"accepted": False, "code": "proposal_rejected_atomically"}) for item in receipts),
            budget=budget,
        )
    return ArbitrationDecision(
        proposal_id=proposal.proposal_id,
        idempotency_key=proposal.idempotency_key,
        proposal_hash=proposal_hash,
        accepted=True,
        decision="accepted",
        code="accepted",
        actions=tuple(receipts),
        budget=budget,
    )
