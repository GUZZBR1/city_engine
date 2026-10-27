from urban_arena import (
    RoundConflictError,
    RoundStore,
    generate_snapshot,
    load_city_config,
    prepare_no_action_round,
)


def test_no_action_cycle_is_deterministic_and_preserves_city_state() -> None:
    config = load_city_config()
    snapshot = generate_snapshot(config)
    candidate_a = prepare_no_action_round(
        config, snapshot, experiment_id="exp-1", instance_id="ref-1", round_index=1
    )
    candidate_b = prepare_no_action_round(
        config, snapshot, experiment_id="exp-1", instance_id="ref-1", round_index=1
    )
    store_a, store_b = RoundStore(snapshot), RoundStore(snapshot)

    record_a = store_a.commit(candidate_a)
    record_b = store_b.commit(candidate_b)

    assert record_a == record_b
    assert record_a.record_hash == record_b.record_hash
    assert record_a.actions == ()
    assert record_a.policy_id == "no_action"
    assert record_a.domain_transition == "not_run"
    assert record_a.metrics == ()
    assert record_a.budget.total_cs == 100
    assert record_a.budget.discretionary_limit_cs == 30
    assert record_a.budget.discretionary_spent_cs == 0
    assert store_a.city_state_hash == snapshot.hash
    assert store_a.city_state.model_dump(mode="json") == snapshot.model_dump(mode="json")
    assert store_a.records == (record_a,)


def test_candidate_and_committed_state_are_isolated_from_input_and_sibling_copies() -> None:
    config = load_city_config()
    snapshot = generate_snapshot(config)
    sibling = snapshot.model_copy(deep=True)
    candidate = prepare_no_action_round(
        config, snapshot, experiment_id="exp-1", instance_id="ref-1", round_index=1
    )
    store = RoundStore(snapshot)
    store.commit(candidate)

    returned = store.city_state
    returned.layers["districts"].features[0].properties["residents"] = -1
    assert sibling.layers["districts"].features[0].properties["residents"] >= 0
    assert snapshot.layers["districts"].features[0].properties["residents"] >= 0
    assert store.city_state.layers["districts"].features[0].properties["residents"] >= 0


def test_candidate_rejects_mutated_snapshot_with_stale_hash() -> None:
    config = load_city_config()
    snapshot = generate_snapshot(config)
    snapshot.layers["districts"].features[0].properties["residents"] = -1

    try:
        prepare_no_action_round(
            config, snapshot, experiment_id="exp-1", instance_id="ref-1", round_index=1
        )
    except ValueError as exc:
        assert "conteúdo do snapshot diverge" in str(exc)
    else:
        raise AssertionError("snapshot alterado com hash antigo deveria falhar")


def test_round_retry_is_idempotent_and_conflicting_reuse_is_rejected() -> None:
    config = load_city_config()
    snapshot = generate_snapshot(config)
    store = RoundStore(snapshot)
    candidate = prepare_no_action_round(
        config, snapshot, experiment_id="exp-1", instance_id="ref-1", round_index=1
    )

    first = store.commit(candidate)
    assert store.commit(candidate) == first
    assert len(store.records) == 1

    changed_identity = prepare_no_action_round(
        config, snapshot, experiment_id="exp-other", instance_id="ref-1", round_index=1
    )
    try:
        store.commit(changed_identity)
    except RoundConflictError as exc:
        assert "conteúdo diferente" in str(exc)
    else:
        raise AssertionError("reutilizar a rodada com conteúdo diferente deveria falhar")
    assert store.records == (first,)
    assert store.city_state_hash == snapshot.hash


def test_stale_round_parent_does_not_partially_commit() -> None:
    config = load_city_config()
    snapshot = generate_snapshot(config)
    store = RoundStore(snapshot)
    candidate = prepare_no_action_round(
        config,
        snapshot,
        experiment_id="exp-1",
        instance_id="ref-1",
        round_index=1,
        parent_round_hash="stale-parent",
    )

    try:
        store.commit(candidate)
    except RoundConflictError as exc:
        assert "hash do registro" in str(exc)
    else:
        raise AssertionError("hash pai obsoleto deveria ser rejeitado")
    assert store.records == ()
    assert store.city_state_hash == snapshot.hash


def test_round_chain_requires_same_instance_and_parent_record() -> None:
    config = load_city_config()
    snapshot = generate_snapshot(config)
    store = RoundStore(snapshot)
    first_candidate = prepare_no_action_round(
        config, snapshot, experiment_id="exp-1", instance_id="ref-1", round_index=1
    )
    first_record = store.commit(first_candidate)
    second_candidate = prepare_no_action_round(
        config,
        snapshot,
        experiment_id="exp-1",
        instance_id="ref-1",
        round_index=2,
        parent_round_hash=first_record.record_hash,
    )
    second_record = store.commit(second_candidate)
    assert second_record.parent_round_hash == first_record.record_hash

    other_instance = prepare_no_action_round(
        config,
        snapshot,
        experiment_id="exp-1",
        instance_id="ref-2",
        round_index=3,
        parent_round_hash=second_record.record_hash,
    )
    try:
        store.commit(other_instance)
    except RoundConflictError as exc:
        assert "misturar experimentos ou instâncias" in str(exc)
    else:
        raise AssertionError("uma store não pode misturar instâncias")
    assert store.records == (first_record, second_record)
