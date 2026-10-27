"""Synthetic, per-round discretionary budget contracts for Aurora v1."""

from __future__ import annotations

from collections import defaultdict
from typing import Literal

from pydantic import Field, StrictInt, model_validator

from .models import StrictModel


class BudgetEnvelope(StrictModel):
    """The fixed 100 CS envelope; only the discretionary share funds actions."""

    total_cs: StrictInt = Field(default=100, ge=0)
    fixed_operations_cs: StrictInt = Field(default=60, ge=0)
    reserve_cs: StrictInt = Field(default=10, ge=0)
    discretionary_cs: StrictInt = Field(default=30, ge=0)

    @model_validator(mode="after")
    def validate_envelope(self) -> BudgetEnvelope:
        if (
            self.total_cs,
            self.fixed_operations_cs,
            self.reserve_cs,
            self.discretionary_cs,
        ) != (100, 60, 10, 30):
            raise ValueError("o envelope aurora_synthetic_v1 deve ser 100 CS = 60 + 10 + 30")
        return self


class BudgetCharge(StrictModel):
    """One server-calculated charge in the round where it is due."""

    round_index: StrictInt = Field(ge=1)
    amount_cs: StrictInt = Field(gt=0)
    kind: Literal["one_time", "recurring"]
    source_action_id: str = Field(min_length=1)


class RoundBudget(StrictModel):
    round_index: StrictInt = Field(ge=1)
    limit_cs: StrictInt = Field(ge=0)
    already_committed_cs: StrictInt = Field(ge=0)
    proposed_cs: StrictInt = Field(ge=0)
    available_cs: StrictInt


class BudgetAssessment(StrictModel):
    accepted: bool
    code: Literal["within_budget", "budget_exceeded", "commitment_outside_horizon"]
    rounds: tuple[RoundBudget, ...]
    charges: tuple[BudgetCharge, ...]


def assess_budget(
    charges: tuple[BudgetCharge, ...] | list[BudgetCharge],
    *,
    horizon_rounds: int = 10,
    existing_commitments: dict[int, int] | None = None,
    envelope: BudgetEnvelope | None = None,
) -> BudgetAssessment:
    """Check current and future commitments without mutating any ledger.

    Unused CS never carry forward. Existing commitments are reserved against the
    discretionary limit of their due round, and fixed operations/reserve are
    never included in the amount available to actions.
    """
    if horizon_rounds < 1:
        raise ValueError("horizon_rounds deve ser positivo")
    envelope = envelope or BudgetEnvelope()
    commitments = existing_commitments or {}
    proposed_by_round: dict[int, int] = defaultdict(int)
    for charge in charges:
        if charge.round_index > horizon_rounds:
            rounds = tuple(
                RoundBudget(
                    round_index=round_index,
                    limit_cs=envelope.discretionary_cs,
                    already_committed_cs=commitments.get(round_index, 0),
                    proposed_cs=proposed_by_round.get(round_index, 0),
                    available_cs=envelope.discretionary_cs
                    - commitments.get(round_index, 0)
                    - proposed_by_round.get(round_index, 0),
                )
                for round_index in sorted(set(commitments) | set(proposed_by_round))
            )
            return BudgetAssessment(
                accepted=False,
                code="commitment_outside_horizon",
                rounds=rounds,
                charges=tuple(charges),
            )
        proposed_by_round[charge.round_index] += charge.amount_cs

    invalid_commitment_round = any(
        round_index < 1 or round_index > horizon_rounds
        for round_index in commitments
    )
    if invalid_commitment_round:
        return BudgetAssessment(
            accepted=False,
            code="commitment_outside_horizon",
            rounds=(),
            charges=tuple(charges),
        )
    if any(amount < 0 or amount > envelope.discretionary_cs for amount in commitments.values()):
        raise ValueError("compromissos existentes devem caber no teto discricionário de cada rodada")

    affected_rounds = sorted(set(commitments) | set(proposed_by_round))
    round_results = tuple(
        RoundBudget(
            round_index=round_index,
            limit_cs=envelope.discretionary_cs,
            already_committed_cs=commitments.get(round_index, 0),
            proposed_cs=proposed_by_round.get(round_index, 0),
            available_cs=(
                envelope.discretionary_cs
                - commitments.get(round_index, 0)
                - proposed_by_round.get(round_index, 0)
            ),
        )
        for round_index in affected_rounds
    )
    accepted = all(item.available_cs >= 0 for item in round_results)
    return BudgetAssessment(
        accepted=accepted,
        code="within_budget" if accepted else "budget_exceeded",
        rounds=round_results,
        charges=tuple(charges),
    )
