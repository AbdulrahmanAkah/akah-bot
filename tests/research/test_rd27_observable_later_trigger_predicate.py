from __future__ import annotations

import inspect
from dataclasses import FrozenInstanceError, replace

import pandas as pd
import pytest
from test_rd27_async_memory_shadow_replay import (
    assert_native_equal,
    at,
    identity,
    inputs,
    observation,
)
from test_rd27_observable_memory_adapter import row, snapshot

from spotbot.research import rd27_lifecycle_replay as replay
from spotbot.research.rd27_adaptive_lifecycle import (
    AsyncTriggerNotReadyError,
    RD27StateError,
    new_async_memory_state,
    observe_async_memory,
    observe_async_trigger,
)
from spotbot.research.rd27_observable_later_trigger_predicate import (
    DEFAULT_OBSERVABLE_LATER_TRIGGER_PREDICATE_ENABLED,
    TRIGGER_PARAMETER_COUNT,
    ObservableLaterTriggerPredicatePolicy,
    evaluate_later_trigger_predicate,
    new_later_trigger_predicate_state,
)
from spotbot.research.rd27_observable_memory_adapter import (
    ConflictingSnapshotError,
    ObservablePositionContext,
    normalize_4h_snapshots,
)


def bar(hour=0, *, low=104, close=107, high=108, symbol="AAA"):
    return snapshot(hour, symbol=symbol, open=close, high=high, low=low, close=close)


def fresh(*, position_id="A", symbol="AAA", entry=0):
    return new_later_trigger_predicate_state(
        position_id=position_id, symbol=symbol, entry_time=at(entry),
    )


def evaluate(state, value, *, time=None, **changes):
    context = ObservablePositionContext(state.position_id, state.symbol, state.entry_time,
                                        value.bar_close_time if time is None else time)
    return evaluate_later_trigger_predicate(
        state, position=replace(context, **changes), snapshot=value,
    )


def rows_for(case="B"):
    if case == "A":  # candidate at 12, then first memory at 16
        values = [(4, 97, 99, 101), (8, 94, 96, 99), (12, 100, 103, 104)]
    elif case == "C":  # memory, more progress, no deterioration
        values = [(4, 101, 103, 104), (8, 104, 106, 107)]
    else:  # B/D: two memories, two later candidates, one latch at 16
        values = [(4, 101, 103, 104), (8, 104, 106, 107),
                  (12, 102, 103.5, 105), (16, 100, 101, 103)]
    return [row(h, open=c, low=low, close=c, high=high) for h, low, c, high in values]


def run_trigger(
    *, rows=None, memory=True, trigger=True, fixture=None, observations=(), bindings=None,
):
    trigger_diag, memory_diag, shadow_diag = {}, {}, {}
    result = replay.replay_lifecycle_policy(
        **(inputs() if fixture is None else fixture), async_memory_shadow_enabled=True,
        observable_adapter_enabled=True, observable_memory_predicate_enabled=memory,
        observable_later_trigger_predicate_enabled=trigger,
        observable_primitive_rows=rows_for() if rows is None else rows,
        observable_symbol_bindings={"AAA-USDT": "AAA"} if bindings is None else bindings,
        async_memory_observations=observations, async_memory_diagnostics=shadow_diag,
        observable_memory_predicate_diagnostics=memory_diag,
        observable_later_trigger_predicate_diagnostics=trigger_diag,
    )
    return result, trigger_diag, memory_diag, shadow_diag


def test_default_disabled_and_zero_parameters():
    assert DEFAULT_OBSERVABLE_LATER_TRIGGER_PREDICATE_ENABLED is False
    assert inspect.signature(replay.replay_lifecycle_policy).parameters[
        "observable_later_trigger_predicate_enabled"
    ].default is False
    assert TRIGGER_PARAMETER_COUNT == 0


def test_first_bar_unavailable_and_current_reference_updates_after_comparison():
    state = fresh()
    first = evaluate(state, bar())
    assert first.trigger_candidate is None and first.status == "NO_PRIOR_SNAPSHOT"
    assert first.previous_low is None
    second = evaluate(first.state, bar(4, low=101, close=103.5))
    assert second.trigger_candidate is True
    assert second.previous_low == 104
    assert second.state.previous_eligible_snapshot.low == 101
    assert state.previous_eligible_snapshot is None


@pytest.mark.parametrize("close,expected", [(103.5, True), (104, False), (105, False)])
def test_strict_close_not_wick(close, expected):
    state = evaluate(fresh(), bar()).state
    result = evaluate(state, bar(4, low=101, close=close))
    assert result.trigger_candidate is expected
    assert result.state.previous_eligible_snapshot.low == 101


def test_immediately_previous_low_not_minimum_since_entry():
    state = evaluate(fresh(), bar(low=90, close=105)).state
    state = evaluate(state, bar(4, low=104, close=107)).state
    result = evaluate(state, bar(8, low=102, close=103.5))
    assert result.trigger_candidate is True and result.previous_low == 104


@pytest.mark.parametrize("open_hour", [-4, 0])
def test_preentry_and_entry_spanning_snapshots_never_become_reference(open_hour):
    ignored = evaluate(fresh(entry=1), bar(open_hour), time=at(4))
    assert ignored.status == "EXCLUDED_ENTRY_BOUNDARY"
    assert ignored.state.previous_eligible_snapshot is None
    assert ignored.state.eligible_snapshot_count == 0
    first = evaluate(ignored.state, bar(4, low=101, close=103))
    assert first.trigger_candidate is None


def test_close_at_entry_excluded_open_at_entry_eligible():
    state = evaluate(fresh(entry=4), bar(), time=at(4)).state
    assert state.previous_eligible_snapshot is None
    first = evaluate(state, bar(4))
    assert first.status == "NO_PRIOR_SNAPSHOT" and first.state.eligible_snapshot_count == 1


@pytest.mark.parametrize("delta", [pd.Timedelta(1, "ns"), pd.Timedelta(seconds=1)])
def test_unfinished_bar_is_rejected(delta):
    with pytest.raises(RD27StateError, match="future"):
        evaluate(fresh(), bar(), time=at(4) - delta)


def test_same_symbol_and_different_symbols_are_isolated():
    a = evaluate(fresh(position_id="A"), bar()).state
    b = evaluate(fresh(position_id="B"), bar(low=90)).state
    c = evaluate(fresh(position_id="C", symbol="BBB"), bar(symbol="BBB", low=95)).state
    assert evaluate(a, bar(4, low=100, close=103)).trigger_candidate is True
    assert evaluate(b, bar(4, low=100, close=103)).trigger_candidate is False
    assert evaluate(c, bar(4, symbol="BBB", low=100, close=103)).trigger_candidate is False
    assert a.previous_eligible_snapshot.low == 104


@pytest.mark.parametrize("changes", [{"symbol": "BBB"}, {"position_id": "other"},
                                     {"entry_time": at(1)}])
def test_exact_lifecycle_binding_required(changes):
    with pytest.raises(RD27StateError, match="binding mismatch"):
        evaluate(fresh(), bar(), **changes)


def test_wrong_snapshot_symbol_rejected():
    with pytest.raises(RD27StateError, match="symbol"):
        evaluate(fresh(), bar(symbol="BBB"))


def test_out_of_order_backward_and_overlapping_snapshots_fail():
    state = evaluate(fresh(), bar(4)).state
    with pytest.raises(RD27StateError, match="out of order"):
        evaluate(state, bar(), time=at(9))
    with pytest.raises(RD27StateError, match="moved backward"):
        evaluate(state, bar(), time=at(7))
    with pytest.raises(RD27StateError, match="overlapping"):
        evaluate(state, bar(5))


def test_identical_duplicate_idempotent_without_new_candidate():
    first = evaluate(fresh(), bar())
    second = evaluate(first.state, bar(4, low=100, close=103))
    duplicate = evaluate(second.state, bar(4, low=100, close=103), time=at(9))
    assert duplicate.state == second.state
    assert duplicate.trigger_candidate is None and duplicate.status == "DUPLICATE"
    assert duplicate.state.eligible_snapshot_count == 2


@pytest.mark.parametrize("changes", [{"close": 106}, {"low": 103},
                                     {"volume": 1001}, {"source_exchange": "other"}])
def test_conflicting_duplicate_fails(changes):
    value = bar()
    state = evaluate(fresh(), value).state
    with pytest.raises(ConflictingSnapshotError):
        evaluate(state, replace(value, **changes), time=at(5))


def test_state_and_result_are_immutable():
    state = fresh()
    with pytest.raises(FrozenInstanceError):
        state.previous_eligible_snapshot = bar()
    result = evaluate(state, bar())
    with pytest.raises(FrozenInstanceError):
        result.trigger_candidate = True


def test_predicate_does_not_inspect_async_state_or_memory_formula():
    class PoisonMemory:
        def __getattribute__(self, name):
            raise AssertionError("trigger formula read memory")

    policy = ObservableLaterTriggerPredicatePolicy(symbol_bindings={"pair": "AAA"})
    policy.open_position(position_id="A", replay_pair="pair", entry_time=at(0))
    for value in [bar(), bar(4, low=100, close=103)]:
        result = policy(position=ObservablePositionContext("A", "AAA", at(0), value.bar_close_time),
                        snapshot=value, prior_state=PoisonMemory())
    assert result.observation_type == "trigger" and result.observed is True
    assert set(inspect.signature(evaluate_later_trigger_predicate).parameters) == {
        "state", "position", "snapshot",
    }


def test_case_a_candidate_before_memory_never_backfills():
    _, t, m, s = run_trigger(rows=rows_for("A"))
    assert t["true_trigger_candidates"] == 1
    assert t["trigger_candidates_before_memory"] == 1
    assert t["trigger_candidates_rejected_by_temporal_contract"] == 1
    assert t["latched_later_triggers"] == 0
    assert t["position_records"][0]["first_trigger_candidate_time"] == at(12)
    assert t["position_records"][0]["first_latched_trigger_time"] is None
    assert m["position_records"][0]["first_predicate_true_time"] == at(16)
    assert s["position_records"][0]["memory_seen"] is True
    assert s["position_records"][0]["later_trigger_seen"] is False


def test_same_rejected_bar_not_retroactively_replayed_when_memory_arrives():
    _, t, _, s = run_trigger(rows=rows_for("A")[:2], memory=False,
                             observations=[observation(13)])
    assert t["true_trigger_candidates"] == 1 and t["latched_later_triggers"] == 0
    assert t["duplicate_noop_count"] > 0
    assert s["position_records"][0]["first_seen_time"] == at(13)
    assert s["position_records"][0]["later_trigger_time"] is None


def test_cases_b_d_two_memories_two_later_candidates_one_earliest_latch():
    _, t, m, s = run_trigger()
    assert t["eligible_trigger_evaluations"] == 4 and t["no_prior_snapshot_count"] == 1
    assert t["true_trigger_candidates"] == 2 and t["false_trigger_candidates"] == 1
    assert t["trigger_candidates_after_memory"] == 2
    assert t["trigger_candidates_before_memory"] == 0
    assert t["latched_later_triggers"] == 1
    assert m["true_predicate_observations"] == 2
    record = t["position_records"][0]
    assert record["first_trigger_candidate_time"] == record["first_latched_trigger_time"] == at(16)
    assert [e[2:] for e in record["candidate_events"]] == [(104, 103.5), (102, 101)]
    assert record["candidate_routing"] == ((at(16), "LATCHED"), (at(20), "ALREADY_LATCHED"))
    memory = s["position_records"][0]
    assert memory["first_seen_time"] == at(8) and memory["latest_seen_time"] == at(12)
    assert memory["later_trigger_time"] == at(16) > memory["first_seen_time"]
    assert memory["memory_seen"] is True and memory["later_trigger_seen"] is True
    assert s["valid_later_triggers_latched"] == 1


def test_case_c_memory_without_deterioration():
    _, t, m, s = run_trigger(rows=rows_for("C"))
    assert m["true_predicate_observations"] == 2
    assert t["true_trigger_candidates"] == t["latched_later_triggers"] == 0
    assert s["position_records"][0]["memory_seen"] is True
    assert s["position_records"][0]["later_trigger_seen"] is False


def test_same_time_first_memory_candidate_rejected_then_new_later_candidate_latches():
    _, t, _, s = run_trigger(memory=False, observations=[observation(16)])
    assert t["true_trigger_candidates"] == 2
    assert t["same_time_candidates_rejected"] == 1
    assert t["trigger_candidates_rejected_by_temporal_contract"] == 1
    assert t["trigger_candidates_after_memory"] == 1
    assert t["position_records"][0]["first_latched_trigger_time"] == at(20)
    assert s["position_records"][0]["later_trigger_time"] == at(20)


def test_generic_api_typed_readiness_errors_preserve_base_exception_and_messages():
    state = new_async_memory_state(position_id="A", enabled=True)
    with pytest.raises(AsyncTriggerNotReadyError, match="established memory") as exc:
        observe_async_trigger(state, observed=True, completed_at=at(4), decision_time=at(4))
    assert isinstance(exc.value, RD27StateError) and exc.value.reason == "MEMORY_NOT_ESTABLISHED"
    state = observe_async_memory(state, observed=True, completed_at=at(4), decision_time=at(4))
    with pytest.raises(AsyncTriggerNotReadyError, match="strictly later") as exc:
        observe_async_trigger(state, observed=True, completed_at=at(4), decision_time=at(4))
    assert exc.value.reason == "NOT_STRICTLY_LATER"


def test_generic_duplicate_conflict_not_swallowed_as_not_ready():
    with pytest.raises(RD27StateError, match="conflicting duplicate trigger"):
        run_trigger(observations=[observation(16, "trigger", False)])


def test_disabled_constructor_and_sink_untouched(monkeypatch):
    def forbidden(**kwargs):
        raise AssertionError("disabled trigger constructed")

    monkeypatch.setattr(replay, "ObservableLaterTriggerPredicatePolicy", forbidden)
    sink = {"untouched": True}
    result = replay.replay_lifecycle_policy(**inputs(),
        observable_later_trigger_predicate_diagnostics=sink)
    assert_native_equal(replay.replay_lifecycle_policy(**inputs()), result)
    assert sink == {"untouched": True}


@pytest.mark.parametrize("policy", [replay.STATIC_EXIT_STATE_ROUTER,
                                   replay.ADAPTIVE_EXIT_FIXED_CAPITAL,
                                   replay.FULL_ADAPTIVE_LIFECYCLE_BRAIN])
def test_native_parity_all_disabled_memory_only_and_both_enabled(policy):
    fixture = inputs() | {"policy_id": policy}
    original = replay.replay_lifecycle_policy(**fixture)
    a, ta, ma, _ = run_trigger(fixture=fixture, memory=False, trigger=False)
    b, tb, mb, _ = run_trigger(fixture=fixture, trigger=False)
    c, tc, mc, _ = run_trigger(fixture=fixture)
    for result in (a, b, c):
        assert_native_equal(original, result)
        assert len(result[0]) == 1
    assert ta == tb == ma == {}
    assert mb == mc  # Trigger integration does not change memory semantics/diagnostics.
    assert tc["true_trigger_candidates"] == 2 and tc["latched_later_triggers"] == 1


def test_deterministic_runs_and_shuffled_duplicate_source_rows():
    rows = rows_for()
    a = run_trigger(rows=rows)
    b = run_trigger(rows=rows[::-1] + [rows[2]])
    c = run_trigger(rows=rows)
    assert_native_equal(a[0], b[0])
    assert a[1:] == b[1:] == c[1:]


def test_future_snapshot_has_no_effect_on_candidates_or_latches():
    a = run_trigger()
    b = run_trigger(rows=rows_for() + [row(204, open=1, low=0.5, close=1, high=2)])
    assert_native_equal(a[0], b[0])
    assert a[1:] == b[1:]


def test_per_position_lifecycle_cleanup_and_new_same_pair_has_no_old_reference():
    fixture = inputs(pairs=("AAA-USDT", "BBB-USDT"), signals=(0, 170), hours=345)
    rows = rows_for() + [row(4, "BBB"), row(8, "BBB"), row(172, low=90, close=95)]
    result, t, _, s = run_trigger(fixture=fixture, rows=rows,
                                  bindings={"AAA-USDT": "AAA", "BBB-USDT": "BBB"})
    assert len(result[0]) == 4
    records = {r["position_id"]: r for r in t["position_records"]}
    assert records[identity()]["first_latched_trigger_time"] == at(16)
    assert records[identity("BBB-USDT")]["first_trigger_candidate_time"] is None
    later = records[identity(entry=171, sequence=2)]
    assert later["eligible_snapshots_processed"] == 1
    assert later["first_trigger_candidate_time"] is None
    assert t["positions_created"] == t["positions_closed"] == s["resets"] == 4
    assert t["active_position_count"] == 0


def test_trigger_only_is_independent_of_memory_enable_flag():
    _, t, m, s = run_trigger(memory=False)
    assert m == {}
    assert t["true_trigger_candidates"] == t["trigger_candidates_before_memory"] == 2
    assert t["latched_later_triggers"] == 0
    assert s["positions_ever_established_memory"] == 0


@pytest.mark.parametrize("flags", [{}, {"async_memory_shadow_enabled": True}])
def test_explicit_parent_switches_required(flags):
    with pytest.raises(replay.RD27ReplayError, match="explicitly enabled"):
        replay.replay_lifecycle_policy(**inputs(), **flags,
                                       observable_later_trigger_predicate_enabled=True)


def test_invalid_switch_and_custom_policy_fail_closed():
    with pytest.raises(replay.RD27ReplayError, match="switch must be boolean"):
        replay.replay_lifecycle_policy(**inputs(), observable_later_trigger_predicate_enabled=1)
    with pytest.raises(replay.RD27ReplayError, match="custom adapter policy"):
        replay.replay_lifecycle_policy(
            **inputs(), async_memory_shadow_enabled=True, observable_adapter_enabled=True,
            observable_later_trigger_predicate_enabled=True, observable_policy=lambda **_: None,
        )


def test_no_snapshot_registers_and_cleans_up_without_candidate():
    _, t, _, s = run_trigger(rows=[])
    assert t["eligible_trigger_evaluations"] == t["true_trigger_candidates"] == 0
    assert t["positions_created"] == t["positions_closed"] == s["resets"] == 1


def test_unknown_closed_and_reused_trigger_identity_rejected():
    policy = ObservableLaterTriggerPredicatePolicy(symbol_bindings={"pair": "AAA"})
    kwargs = dict(position=ObservablePositionContext("A", "AAA", at(0), at(4)),
                  snapshot=bar(), prior_state=None)
    with pytest.raises(RD27StateError, match="unknown/closed"):
        policy(**kwargs)
    policy.open_position(position_id="A", replay_pair="pair", entry_time=at(0))
    policy.close_position("A")
    with pytest.raises(RD27StateError, match="unknown/closed"):
        policy(**kwargs)
    with pytest.raises(RD27StateError, match="reused"):
        policy.open_position(position_id="A", replay_pair="pair", entry_time=at(8))


@pytest.mark.parametrize("policy,weak,overrides", [
    (replay.STATIC_EXIT_STATE_ROUTER, True, None),
    (replay.ADAPTIVE_EXIT_FIXED_CAPITAL, True, None),
    (replay.ADAPTIVE_EXIT_FIXED_CAPITAL, False, {10: {"low": 90}}),
    (replay.ADAPTIVE_EXIT_FIXED_CAPITAL, False, {1: {"low": 90}}),
])
def test_trigger_cleanup_and_parity_for_existing_exit_paths(policy, weak, overrides):
    fixture = inputs(weak=weak, overrides=overrides) | {"policy_id": policy}
    result, t, _, s = run_trigger(fixture=fixture)
    assert_native_equal(replay.replay_lifecycle_policy(**fixture), result)
    assert t["positions_closed"] == t["positions_created"] == s["resets"] == 1
    assert t["active_position_count"] == 0


def test_gaps_use_previous_available_eligible_snapshot_without_lookback_parameter():
    state = evaluate(fresh(), bar()).state
    result = evaluate(state, bar(12, low=101, close=103))
    assert result.trigger_candidate is True and result.previous_low == 104


def test_normalization_and_ordered_fold_are_deterministic():
    source = rows_for()
    final = []
    for rows in (source, source[::-1]):
        state = fresh(entry=1)
        for value in normalize_4h_snapshots(rows).snapshots:
            state = evaluate(state, value).state
        final.append(state)
    assert final[0] == final[1]


def test_off_grid_close_uses_actual_causal_boundary_without_backdating():
    rows = [r | {"bar_open_time": r["bar_open_time"] + pd.Timedelta(minutes=30),
                 "bar_close_time": r["bar_close_time"] + pd.Timedelta(minutes=30)}
            for r in rows_for()]
    _, t, m, s = run_trigger(rows=rows)
    assert t["true_trigger_candidates"] == 2 and t["latched_later_triggers"] == 1
    record = t["position_records"][0]
    assert record["first_trigger_candidate_time"] == record["first_latched_trigger_time"] == at(17)
    assert record["candidate_events"][0][1][2] == at(16.5)
    assert m["position_records"][0]["first_predicate_true_time"] == at(9)
    assert s["position_records"][0]["later_trigger_time"] == at(17)


def test_conflicting_source_does_not_publish_partial_diagnostics():
    sink = {"untouched": True}
    with pytest.raises(ConflictingSnapshotError):
        replay.replay_lifecycle_policy(
            **inputs(), async_memory_shadow_enabled=True, observable_adapter_enabled=True,
            observable_later_trigger_predicate_enabled=True,
            observable_primitive_rows=[row(4), row(4, close=100)],
            observable_symbol_bindings={"AAA-USDT": "AAA"},
            observable_later_trigger_predicate_diagnostics=sink,
        )
    assert sink == {"untouched": True}


def test_same_symbol_two_candidate_policy_lifecycles_are_isolated():
    policy = ObservableLaterTriggerPredicatePolicy(symbol_bindings={"pair": "AAA"})
    for pid, low in [("A", 104), ("B", 90)]:
        policy.open_position(position_id=pid, replay_pair="pair", entry_time=at(0))
        policy(position=ObservablePositionContext(pid, "AAA", at(0), at(4)),
               snapshot=bar(low=low), prior_state=None)
    outcomes = [policy(position=ObservablePositionContext(pid, "AAA", at(0), at(8)),
                       snapshot=bar(4, low=100, close=103), prior_state=None) for pid in ("A", "B")]
    assert [value.observed for value in outcomes] == [True, False]
    policy.close_position("A")
    policy.close_position("B")
    assert policy.diagnostics()["active_position_count"] == 0
