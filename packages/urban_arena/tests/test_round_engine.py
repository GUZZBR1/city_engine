from __future__ import annotations

from urban_arena.city import generate_snapshot, load_city_config
from urban_arena.manifest import build_aurora_synthetic_v1_manifest
from urban_arena.round_engine import AnnualRoundEngine
from urban_arena.state import EffectiveEvent, StateFactory


def test_future_signal_effect_stays_pending_before_effective_round() -> None:
    config = load_city_config()
    snapshot = generate_snapshot(config)
    manifest = build_aurora_synthetic_v1_manifest(
        config,
        snapshot,
        experiment_id="effects-test",
    )
    parent = StateFactory.copies(
        snapshot,
        manifest=manifest,
        instance_ids=["effects-test:instance:01"],
    )[0]
    event = EffectiveEvent(
        event_id="signal:round-2",
        event_type="signal_timing_change",
        effective_round=2,
        payload={"node_id": "node:01:01", "phases": []},
    )
    parent = type(parent).model_validate(
        {
            **parent.model_dump(mode="python"),
            "pending_effects": [event.model_dump(mode="python")],
        }
    )
    engine = AnnualRoundEngine(manifest)

    candidate, observation = engine.prepare_observation(parent)

    assert [item.event_id for item in candidate.pending_effects] == [event.event_id]
    assert not candidate.active_signal_plans
    assert observation.state_view["pending_effects"][0]["event_id"] == event.event_id
    assert observation.city_state_hash == candidate.city_state_hash
    assert parent.pending_effects[0].event_id == event.event_id


def test_due_signal_effect_fails_closed_without_sumo_handler() -> None:
    config = load_city_config()
    snapshot = generate_snapshot(config)
    manifest = build_aurora_synthetic_v1_manifest(
        config,
        snapshot,
        experiment_id="due-effects-test",
    )
    parent = StateFactory.copies(
        snapshot,
        manifest=manifest,
        instance_ids=["due-effects-test:instance:01"],
    )[0]
    event = EffectiveEvent(
        event_id="signal:round-1",
        event_type="signal_timing_change",
        effective_round=1,
        payload={},
    )
    parent = type(parent).model_validate(
        {
            **parent.model_dump(mode="python"),
            "pending_effects": [event.model_dump(mode="python")],
        }
    )
    before = parent.model_dump(mode="json")

    try:
        AnnualRoundEngine(manifest).prepare_observation(parent)
    except ValueError as exc:
        assert "sem handler validado" in str(exc)
    else:
        raise AssertionError("efeito sem adaptador SUMO deve falhar fechado")

    assert parent.model_dump(mode="json") == before
