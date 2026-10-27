from __future__ import annotations

from urban_arena.actions import (
    ActionProposal,
    ArbitrationContext,
    ProposedAction,
    SignalTarget,
)
from urban_arena.observations import Observation

from app.arena_mobility import ArenaSignalSumoEvaluator
from simulation import load_aurora_input
from simulation.models import (
    ArtifactReferences,
    SimulationMetrics,
    SimulationResult,
)


def _action_proposal(observation: Observation) -> ActionProposal:
    action = ProposedAction(
        action_id="signal-action-1",
        action_type="signal_timing_change",
        target_id="node:02:00",
        parameters={"phases": [
            {"movement": "north_south", "duration_s": 40},
            {"movement": "all_red", "duration_s": 3},
            {"movement": "east_west", "duration_s": 20},
            {"movement": "all_red", "duration_s": 3},
        ]},
    )
    return ActionProposal(
        experiment_id="experiment-1",
        proposal_id="proposal-1",
        idempotency_key="key-1",
        agent_id="agent-1",
        instance_id="instance-1",
        round_index=1,
        observed_city_state_hash=observation.city_state_hash,
        actions=(action,),
    )


def _context(observation: Observation) -> ArbitrationContext:
    return ArbitrationContext(
        experiment_id="experiment-1",
        agent_id="agent-1",
        instance_id="instance-1",
        round_index=1,
        observed_city_state_hash=observation.city_state_hash,
        signal_targets=(SignalTarget(
            node_id="node:02:00",
            phases=(
                {"movement": "north_south", "duration_s": 35},
                {"movement": "all_red", "duration_s": 3},
                {"movement": "east_west", "duration_s": 25},
                {"movement": "all_red", "duration_s": 3},
            ),
        ),),
    )


def test_evaluator_runs_paired_same_input_and_records_window_scoped_evidence():
    inputs = load_aurora_input("aurora-base-v1", "weekday_am_peak")
    observation = Observation(
        instance_id="instance-1",
        round_index=1,
        city_state_hash="state-hash",
        state_view={"snapshot_hash": inputs.snapshot_hash},
        available_actions=(),
        budget_view={},
        indicator_values={},
    )

    class FakeEngine:
        engine_name = "fake-sumo"

        def __init__(self):
            self.calls = []

        def run(self, simulation_input, *, seed, limits=None):
            self.calls.append((simulation_input, seed, limits))
            changed = [signal for signal in simulation_input.traffic_signals if signal.node_id == "node:02:00"]
            intervention_run = [phase.duration_seconds for phase in changed[0].phases] == [40, 3, 20, 3]
            return SimulationResult(
                simulation_id=f"simulation-{len(self.calls)}",
                city_id=simulation_input.city_id,
                snapshot_id=simulation_input.snapshot_id,
                snapshot_hash=simulation_input.snapshot_hash,
                city_schema_version=simulation_input.city_schema_version,
                city_generator_version=simulation_input.city_generator_version,
                window_id=simulation_input.window.id,
                seed=seed,
                engine="fake-sumo",
                engine_version="test",
                metrics=SimulationMetrics(
                    trips_requested=930,
                    trips_completed=930,
                    trips_not_completed=0,
                    mean_travel_time_seconds=580.0 if intervention_run else 590.0,
                    mean_speed_kmh=37.0 if intervention_run else 36.0,
                    mean_queue_length_meters=0.5 if intervention_run else 0.8,
                ),
                metric_methods={"scope": "test"},
                artifacts=ArtifactReferences(network_file="network", routes_file="routes"),
            )

    engine = FakeEngine()
    evaluator = ArenaSignalSumoEvaluator(inputs, seed=42, engine=engine)
    proposal = _action_proposal(observation)
    evidence = evaluator(proposal, observation, _context(observation))

    assert len(engine.calls) == 2
    base_input, base_seed, _ = engine.calls[0]
    changed_input, changed_seed, _ = engine.calls[1]
    assert base_seed == changed_seed == 42
    assert base_input.snapshot_hash == changed_input.snapshot_hash == inputs.snapshot_hash
    assert base_input.window == changed_input.window == inputs.window
    assert base_input.trips == changed_input.trips == inputs.trips
    assert base_input.edges == changed_input.edges == inputs.edges
    assert [phase.duration_seconds for phase in changed_input.traffic_signals[0].phases] == [40, 3, 20, 3]
    assert evidence.action_ids == ("signal-action-1",)
    assert evidence.details["scope"] == "simulation_window"
    assert evidence.details["deltas"]["mean_travel_time_seconds"] == -10.0
    assert "não são anualizadas" in evidence.details["limitations"][1]


def test_evaluator_rejects_observation_from_another_snapshot():
    inputs = load_aurora_input("aurora-base-v1", "weekday_am_peak")
    observation = Observation(
        instance_id="instance-1",
        round_index=1,
        city_state_hash="state-hash",
        state_view={"snapshot_hash": "different-snapshot"},
        available_actions=(),
        budget_view={},
        indicator_values={},
    )

    class UnusedEngine:
        engine_name = "unused"

        def run(self, *args, **kwargs):
            raise AssertionError("engine must not run for a mismatched snapshot")

    evaluator = ArenaSignalSumoEvaluator(inputs, engine=UnusedEngine())
    try:
        evaluator(_action_proposal(observation), observation, _context(observation))
    except ValueError as exc:
        assert "snapshot" in str(exc)
    else:
        raise AssertionError("expected mismatched snapshot rejection")
