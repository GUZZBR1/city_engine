from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from simulation import (
    RequestedTrip,
    RoadEdge,
    RoadNode,
    SignalTimingIntervention,
    SignalTimingPhase,
    SimulationError,
    SimulationInput,
    SimulationLimits,
    SimulationWindow,
    SumoEngine,
    apply_signal_timing_intervention,
    compile_sumo_inputs,
    load_aurora_input,
    run_simulation,
)
from simulation.compiler import sumo_identifier
from simulation.engine import apply_signal_timing_interventions


def sample_input() -> SimulationInput:
    return SimulationInput(
        city_id="aurora-base-v1",
        snapshot_id="aurora-base-v1:test",
        snapshot_hash="test",
        city_schema_version="1",
        city_generator_version="0.2.0",
        provenance="synthetic",
        window=SimulationWindow(id="test", start="07:00", end="08:00"),
        nodes=(RoadNode(id="a", x_m=0, y_m=0), RoadNode(id="b", x_m=10, y_m=0), RoadNode(id="c", x_m=20, y_m=0)),
        edges=(
            RoadEdge(id="ab", from_node="a", to_node="b", speed_mps=10, lane_count=1),
            RoadEdge(id="bc", from_node="b", to_node="c", speed_mps=10, lane_count=1),
        ),
        trips=(RequestedTrip(id="trip-1", from_edge="ab", to_edge="bc", departure_seconds=5),),
    )


def test_compiler_emits_deterministic_sumo_inputs(tmp_path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    compile_sumo_inputs(sample_input(), first, SimulationLimits())
    compile_sumo_inputs(sample_input(), second, SimulationLimits())
    assert {p.name: p.read_bytes() for p in first.iterdir()} == {p.name: p.read_bytes() for p in second.iterdir()}
    routes = ET.parse(first / "aurora.rou.xml").getroot()
    vehicle = routes.find("vehicle")
    assert vehicle is not None
    assert vehicle.attrib["depart"] == "5"
    assert vehicle.find("route").attrib["edges"] == "id_ab id_bc"


def test_current_aurora_contract_adapts_network_and_od_flows():
    inputs = load_aurora_input("aurora-base-v1", "weekday_am_peak")
    assert len(inputs.nodes) == 25
    assert len(inputs.edges) == 74
    assert len(inputs.trips) == 930
    assert len(inputs.traffic_signals) == 2
    assert inputs.trips[0].departure_seconds > 0
    assert inputs.warnings == ()


def test_run_simulation_rejects_explicit_input_for_different_window():
    with pytest.raises(SimulationError) as error:
        run_simulation(window_id="weekday_off_peak", inputs=sample_input())

    assert error.value.code == "invalid_input"
    assert str(error.value) == "A janela do contrato não corresponde à janela solicitada."


def test_compiler_marks_only_configured_signal_nodes_as_traffic_lights(tmp_path):
    inputs = load_aurora_input("aurora-base-v1", "weekday_am_peak")
    compile_sumo_inputs(inputs, tmp_path, SimulationLimits())
    nodes = ET.parse(tmp_path / "aurora.nod.xml").getroot()
    tls_nodes = {node.attrib["id"] for node in nodes.findall("node") if node.get("type") == "traffic_light"}
    assert tls_nodes == {sumo_identifier(signal.node_id) for signal in inputs.traffic_signals}


def test_missing_sumo_binary_has_stable_failure(tmp_path):
    with pytest.raises(SimulationError) as error:
        SumoEngine(sumo_binary="does-not-exist-sumo", netconvert_binary="does-not-exist-netconvert").run(
            sample_input(), seed=42, limits=SimulationLimits(output_directory=str(tmp_path))
        )
    assert error.value.code == "sumo_unavailable"


def test_drain_extends_sumo_horizon_and_accounts_for_unfinished_trips(tmp_path, monkeypatch):
    monkeypatch.setattr("simulation.sumo.shutil.which", lambda binary: f"/fake/{binary}")
    sumo_end = None

    def fake_execute(command, *, timeout, stage):
        nonlocal sumo_end
        if stage == "sumo_version":
            return "Eclipse SUMO sumo 1.20.0"
        if stage == "netconvert":
            output = Path(command[command.index("--output-file") + 1])
            output.write_text("<net/>")
            return ""
        if stage == "sumo":
            sumo_end = command[command.index("--end") + 1]
            tripinfo = Path(command[command.index("--tripinfo-output") + 1])
            tripinfo.write_text('<tripinfos><tripinfo id="trip-1" duration="20" routeLength="100"/></tripinfos>')
            queue = Path(command[command.index("--queue-output") + 1])
            queue.write_text('<queue><data timestep="3599"><lanes><lane queueing_length="3"/></lanes></data><data timestep="3600"><lanes><lane queueing_length="99"/></lanes></data></queue>')
            return ""
        raise AssertionError(stage)

    monkeypatch.setattr(SumoEngine, "_execute", staticmethod(fake_execute))
    result = SumoEngine().run(sample_input(), seed=42, limits=SimulationLimits(
        output_directory=str(tmp_path), drain_limit_seconds=120,
    ))
    assert sumo_end == "3720"
    assert result.metrics.trips_requested == 1
    assert result.metrics.trips_completed == 1
    assert result.metrics.trips_not_completed == 0
    assert result.metrics.mean_travel_time_seconds == 20
    assert result.metrics.mean_queue_length_meters == 3


def test_drain_limit_reports_remaining_trip_as_not_completed(tmp_path, monkeypatch):
    monkeypatch.setattr("simulation.sumo.shutil.which", lambda binary: f"/fake/{binary}")
    def fake_execute(command, *, timeout, stage):
        if stage == "sumo_version":
            return "Eclipse SUMO sumo 1.20.0"
        if stage == "netconvert":
            Path(command[command.index("--output-file") + 1]).write_text("<net/>")
            return ""
        if stage == "sumo":
            Path(command[command.index("--tripinfo-output") + 1]).write_text("<tripinfos/>")
            Path(command[command.index("--queue-output") + 1]).write_text("<data/>")
            return ""
        raise AssertionError(stage)

    monkeypatch.setattr(SumoEngine, "_execute", staticmethod(fake_execute))
    result = SumoEngine().run(sample_input(), seed=42, limits=SimulationLimits(output_directory=str(tmp_path)))
    assert (result.metrics.trips_requested, result.metrics.trips_completed, result.metrics.trips_not_completed) == (1, 0, 1)
    assert result.metrics.mean_travel_time_seconds is None
    assert any("limite de escoamento" in warning for warning in result.warnings)


def aurora_intervention(durations=(40, 3, 20, 3), movements=("north_south", "all_red", "east_west", "all_red")):
    return SignalTimingIntervention(
        node_id="node:02:00",
        phases=tuple(SignalTimingPhase(movement=movement, duration_seconds=duration)
                     for movement, duration in zip(movements, durations)),
    )


def test_timing_intervention_changes_only_declared_signal_durations():
    base = load_aurora_input("aurora-base-v1", "weekday_am_peak")
    changed = apply_signal_timing_intervention(base, aurora_intervention())
    base_signals = {signal.node_id: signal for signal in base.traffic_signals}
    changed_signals = {signal.node_id: signal for signal in changed.traffic_signals}
    assert base.snapshot_hash == changed.snapshot_hash
    assert base.trips == changed.trips
    assert base.edges == changed.edges
    assert [phase.duration_seconds for phase in changed_signals["node:02:00"].phases] == [40, 3, 20, 3]
    assert changed_signals["node:02:00"].program_id == base_signals["node:02:00"].program_id
    assert changed_signals["node:02:00"].offset_seconds == base_signals["node:02:00"].offset_seconds
    assert changed_signals["node:02:00"].initial_phase_index == base_signals["node:02:00"].initial_phase_index
    assert changed_signals["node:02:04"] == base_signals["node:02:04"]


def test_timing_intervention_package_changes_two_signals_and_preserves_other_inputs():
    base = load_aurora_input("aurora-base-v1", "weekday_am_peak")
    interventions = (
        aurora_intervention(),
        SignalTimingIntervention(
            node_id="node:02:04",
            phases=tuple(
                SignalTimingPhase(movement=movement, duration_seconds=duration)
                for movement, duration in zip(
                    ("north_south", "all_red", "east_west", "all_red"),
                    (35, 3, 25, 3),
                )
            ),
        ),
    )

    changed = apply_signal_timing_interventions(base, interventions)
    base_signals = {signal.node_id: signal for signal in base.traffic_signals}
    changed_signals = {signal.node_id: signal for signal in changed.traffic_signals}

    assert [phase.duration_seconds for phase in changed_signals["node:02:00"].phases] == [40, 3, 20, 3]
    assert [phase.duration_seconds for phase in changed_signals["node:02:04"].phases] == [35, 3, 25, 3]
    assert changed_signals["node:02:00"].offset_seconds == base_signals["node:02:00"].offset_seconds
    assert changed_signals["node:02:04"].program_id == base_signals["node:02:04"].program_id
    assert changed.city_id == base.city_id
    assert changed.window == base.window
    assert changed.nodes == base.nodes
    assert changed.edges == base.edges
    assert changed.trips == base.trips
    assert changed.warnings == base.warnings
    assert base.traffic_signals == tuple(base_signals.values())


def test_timing_intervention_package_rejects_duplicate_targets():
    intervention = aurora_intervention()
    with pytest.raises(SimulationError, match="mesmo nó"):
        apply_signal_timing_interventions(
            load_aurora_input("aurora-base-v1", "weekday_am_peak"),
            (intervention, intervention),
        )


def test_timing_intervention_package_rejects_more_than_two_changes():
    intervention = aurora_intervention()
    with pytest.raises(SimulationError, match="no máximo duas"):
        apply_signal_timing_interventions(
            load_aurora_input("aurora-base-v1", "weekday_am_peak"),
            (intervention, intervention.model_copy(update={"node_id": "node:02:04"}),
             intervention.model_copy(update={"node_id": "node:99:99"})),
        )


def test_timing_intervention_package_rejects_node_without_signal():
    intervention = SignalTimingIntervention(
        node_id="b",
        phases=aurora_intervention().phases,
    )
    with pytest.raises(SimulationError, match="não possui controlador"):
        apply_signal_timing_interventions(sample_input(), (intervention,))


def test_timing_intervention_package_validates_every_change_before_applying():
    base = load_aurora_input("aurora-base-v1", "weekday_am_peak")
    valid = aurora_intervention()
    invalid = SignalTimingIntervention(
        node_id="node:02:04",
        phases=aurora_intervention(durations=(41, 3, 20, 3)).phases,
    )

    with pytest.raises(SimulationError, match="ciclo total"):
        apply_signal_timing_interventions(base, (valid, invalid))
    assert [phase.duration_seconds for phase in base.traffic_signals[0].phases] == [35, 3, 25, 3]


def test_run_simulation_keeps_singular_argument_and_accepts_package():
    class CapturingEngine:
        def __init__(self):
            self.inputs = None

        def run(self, inputs, *, seed, limits):
            self.inputs = inputs
            return inputs

    base = load_aurora_input("aurora-base-v1", "weekday_am_peak")
    intervention = aurora_intervention()
    singular_engine = CapturingEngine()
    singular_result = run_simulation(
        inputs=base,
        engine=singular_engine,
        signal_timing_intervention=intervention,
    )
    assert singular_result is singular_engine.inputs
    assert [phase.duration_seconds for phase in singular_result.traffic_signals[0].phases] == [40, 3, 20, 3]

    package_engine = CapturingEngine()
    package_result = run_simulation(
        inputs=base,
        engine=package_engine,
        signal_timing_interventions=(intervention,),
    )
    assert package_result is package_engine.inputs
    assert [phase.duration_seconds for phase in package_result.traffic_signals[0].phases] == [40, 3, 20, 3]


@pytest.mark.parametrize("intervention, message", [
    (SignalTimingIntervention(node_id="node:99:99", phases=aurora_intervention().phases), "não existe"),
    (aurora_intervention(durations=(40, 3, 20)), "ordem"),
    (aurora_intervention(movements=("east_west", "all_red", "north_south", "all_red")), "ordem"),
    (aurora_intervention(durations=(41, 3, 20, 3)), "ciclo total"),
])
def test_invalid_timing_interventions_are_rejected(intervention, message):
    base = load_aurora_input("aurora-base-v1", "weekday_am_peak")
    with pytest.raises(SimulationError, match=message):
        apply_signal_timing_intervention(base, intervention)


def test_nonpositive_timing_duration_is_rejected_by_contract():
    with pytest.raises(ValueError):
        SignalTimingPhase(movement="north_south", duration_seconds=0)
