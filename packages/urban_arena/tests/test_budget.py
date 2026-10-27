import pytest
from urban_arena.budget import BudgetCharge, BudgetEnvelope, assess_budget


def charge(round_index: int, amount: int, kind: str = "one_time") -> BudgetCharge:
    return BudgetCharge(
        round_index=round_index,
        amount_cs=amount,
        kind=kind,
        source_action_id="action-1",
    )


def test_aurora_envelope_is_100_split_60_10_30() -> None:
    envelope = BudgetEnvelope()

    assert envelope.total_cs == 100
    assert envelope.fixed_operations_cs == 60
    assert envelope.reserve_cs == 10
    assert envelope.discretionary_cs == 30
    assert assess_budget([charge(1, 30)]).accepted


def test_envelope_rejects_inconsistent_splits() -> None:
    with pytest.raises(ValueError, match="aurora_synthetic_v1"):
        BudgetEnvelope(fixed_operations_cs=70, reserve_cs=10, discretionary_cs=20)

    with pytest.raises(ValueError, match="aurora_synthetic_v1"):
        BudgetEnvelope(discretionary_cs=31)


def test_discretionary_limit_is_per_round_without_carry_over() -> None:
    assert assess_budget([charge(1, 30)], horizon_rounds=10).accepted
    assert not assess_budget([charge(1, 31)], horizon_rounds=10).accepted

    # An unused balance from round 1 does not increase round 2's limit.
    round_two = assess_budget([charge(2, 30)], horizon_rounds=10)
    assert round_two.accepted
    assert round_two.rounds[0].limit_cs == 30


def test_existing_future_commitments_reduce_that_rounds_discretionary_limit() -> None:
    assessment = assess_budget(
        [charge(2, 29)],
        horizon_rounds=10,
        existing_commitments={2: 2},
    )

    assert not assessment.accepted
    assert assessment.code == "budget_exceeded"
    assert assessment.rounds[0].available_cs == -1


def test_commitment_after_horizon_is_rejected() -> None:
    assessment = assess_budget(
        [charge(10, 2, "recurring")],
        horizon_rounds=9,
    )

    assert not assessment.accepted
    assert assessment.code == "commitment_outside_horizon"
