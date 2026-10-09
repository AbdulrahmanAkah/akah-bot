from __future__ import annotations

import inspect
from dataclasses import FrozenInstanceError, replace

import pandas as pd
import pytest
from test_rd27_async_memory_shadow_replay import assert_native_equal, at, identity, inputs
from test_rd27_observable_memory_adapter import row, snapshot

from spotbot.research import rd27_lifecycle_replay as replay
from spotbot.research.rd27_adaptive_lifecycle import (
    RD27StateError,
    new_async_memory_state,
    observe_async_memory,
)
from spotbot.research.rd27_observable_memory_adapter import (
    ConflictingSnapshotError,
    ObservableAdapterObservation,
    ObservableMemoryAdapter,
    ObservablePositionContext,
    no_observation_policy,
    normalize_4h_snapshots,
    policy_observation,
)
from spotbot.research.rd27_observable_memory_predicate import (
    DEFAULT_OBSERVABLE_MEMORY_PREDICATE_ENABLED,
    PREDICATE_PARAMETER_COUNT,
    ObservableMemoryPredicatePolicy,
    evaluate_memory_predicate,
    new_memory_predicate_state,
)


def fresh(*, position_id="position-A", symbol="AAA", entry=0, price=100):
    return new_memory_predicate_state(
        position_id=position_id, symbol=symbol, entry_time=at(entry), entry_price=price,
    )


def evaluate(state, bar, *, decision_time=None, **changes):
    position = ObservablePositionContext(
        state.position_id, state.symbol, state.entry_time,
        bar.bar_close_time if decision_time is None else decision_time,
    )
    return evaluate_memory_predicate(state, position=replace(position, **changes), snapshot=bar)


def primitive_rows():
    # Entry is hour 1. Exclude the spanning high=1000 bar entirely. Eligible
    # close observations at hours 8,12,16,20 are True,True,False,True.
    return [row(0, high=1000), row(4), row(8, high=104, close=103),
            row(12, high=106, close=103.5), row(16, high=108, close=106.5)]


def run_predicate(*, fixture=None, rows=None, enabled=True, bindings=None):
    predicate, shadow, adapter = {}, {}, {}
    result = replay.replay_lifecycle_policy(
        **(inputs() if fixture is None else fixture), async_memory_shadow_enabled=True,
        observable_adapter_enabled=True, observable_memory_predicate_enabled=enabled,
        observable_primitive_rows=primitive_rows() if rows is None else rows,
        observable_symbol_bindings={"AAA-USDT": "AAA"} if bindings is None else bindings,
        observable_memory_predicate_diagnostics=predicate, async_memory_diagnostics=shadow,
        observable_adapter_diagnostics=adapter,
    )
    return result, predicate, shadow, adapter


def test_default_disabled_and_adapter_default_still_noop():
    params = inspect.signature(replay.replay_lifecycle_policy).parameters
    assert DEFAULT_OBSERVABLE_MEMORY_PREDICATE_ENABLED is False
    assert params["observable_memory_predicate_enabled"].default is False
    assert params["observable_policy"].default is no_observation_policy
    assert PREDICATE_PARAMETER_COUNT == 0


@pytest.mark.parametrize("close,expected", [(99, False), (100, False), (100.000000001, True),
                                           (101, True)])
def test_first_bar_uses_entry_and_strict_close_only(close, expected):
    state = fresh()
    result = evaluate(state, snapshot(high=106, low=98, close=close))
    assert result.prior_structural_high == 100
    assert result.memory_observed is expected
    assert result.state.structural_high == 106  # Updated AFTER close comparison.
    assert result.state.eligible_snapshot_count == 1
    assert state.structural_high == 100 and state.last_snapshot is None


def test_current_high_not_used_circularly_and_prior_high_affects_later_bars():
    state = evaluate(fresh(), snapshot(high=102, close=101)).state
    b = evaluate(state, snapshot(4, high=104, close=103))
    assert b.memory_observed is True and b.prior_structural_high == 102
    c = evaluate(b.state, snapshot(8, high=106, close=104.5))
    assert c.memory_observed is True and c.prior_structural_high == 104
    assert c.state.structural_high == 106
    wick = evaluate(b.state, snapshot(8, high=106, close=103.5))
    assert wick.memory_observed is False
    assert wick.state.structural_high == 106


def test_equal_prior_high_is_false_and_structure_never_decreases():
    state = evaluate(fresh(), snapshot(high=104, close=101)).state
    result = evaluate(state, snapshot(4, high=105, close=104))
    assert result.memory_observed is False
    lower = evaluate(result.state, snapshot(8, high=102, close=101))
    assert lower.state.structural_high == 105
    assert lower.memory_observed is False


@pytest.mark.parametrize("open_hour", [-4, 0])
def test_preentry_and_spanning_bars_excluded(open_hour):
    state = fresh(entry=1)
    result = evaluate(state, snapshot(open_hour, high=1000), decision_time=at(4))
    assert result.status == "EXCLUDED_ENTRY_BOUNDARY"
    assert result.memory_observed is None
    assert result.state.structural_high == 100
    assert result.state.eligible_snapshot_count == 0
    eligible = evaluate(result.state, snapshot(4))
    assert eligible.memory_observed is True and eligible.prior_structural_high == 100


def test_bar_closing_exactly_at_entry_excluded_bar_opening_at_entry_eligible():
    excluded = evaluate(fresh(entry=4), snapshot(), decision_time=at(4))
    assert excluded.memory_observed is None
    included = evaluate(excluded.state, snapshot(4))
    assert included.memory_observed is True


@pytest.mark.parametrize("delta", [pd.Timedelta(1, "ns"), pd.Timedelta(seconds=1)])
def test_unfinished_and_future_bar_rejected(delta):
    state = fresh()
    with pytest.raises(RD27StateError, match="future"):
        evaluate(state, snapshot(), decision_time=at(4) - delta)
    assert state.structural_high == 100
    assert evaluate(state, snapshot(), decision_time=at(4)).memory_observed is True


def test_symbol_and_position_and_entry_binding_fail_closed():
    state = fresh()
    for changes in ({"symbol": "BBB"}, {"position_id": "position-B"}, {"entry_time": at(1)}):
        with pytest.raises(RD27StateError, match="binding mismatch"):
            evaluate(state, snapshot(), **changes)
    with pytest.raises(RD27StateError, match="symbol"):
        evaluate(state, snapshot(symbol="BBB"))


def test_same_symbol_different_positions_are_isolated():
    a, b = fresh(position_id="A", price=100), fresh(position_id="B", price=105)
    ra, rb = evaluate(a, snapshot(high=106, close=103)), evaluate(b, snapshot(high=106, close=103))
    assert ra.memory_observed is True and rb.memory_observed is False
    assert a.structural_high == 100 and b.structural_high == 105
    assert ra.state.position_id != rb.state.position_id


def test_out_of_order_snapshot_and_backward_decision_fail():
    state = evaluate(fresh(), snapshot(4)).state
    with pytest.raises(RD27StateError, match="out of order"):
        evaluate(state, snapshot(), decision_time=at(9))
    with pytest.raises(RD27StateError, match="moved backward"):
        evaluate(state, snapshot(), decision_time=at(7))
    with pytest.raises(RD27StateError, match="overlapping"):
        evaluate(state, snapshot(5), decision_time=at(9))


def test_duplicate_snapshot_is_idempotent_without_second_boolean():
    first = evaluate(fresh(), snapshot())
    duplicate = evaluate(first.state, snapshot(), decision_time=at(5))
    assert duplicate.state == first.state
    assert duplicate.status == "DUPLICATE"
    assert duplicate.memory_observed is None
    assert duplicate.state.eligible_snapshot_count == 1


@pytest.mark.parametrize("changes", [{"close": 100}, {"high": 105},
                                     {"source_exchange": "other"}, {"volume": 1001}])
def test_conflicting_duplicate_fails(changes):
    first = evaluate(fresh(), snapshot())
    with pytest.raises(ConflictingSnapshotError):
        evaluate(first.state, snapshot(**changes), decision_time=at(5))


def test_predicate_state_and_result_immutable():
    state = fresh()
    with pytest.raises(FrozenInstanceError):
        state.structural_high = 0
    result = evaluate(state, snapshot())
    with pytest.raises(FrozenInstanceError):
        result.memory_observed = False


@pytest.mark.parametrize("price", [0, -1, float("inf"), float("nan"), True, "100", None])
def test_invalid_entry_price_rejected(price):
    with pytest.raises(RD27StateError, match="price"):
        fresh(price=price)


def test_utc_normalization_uses_existing_context_contract():
    state = new_memory_predicate_state(position_id="A", symbol="AAA",
                                       entry_time="2030-01-01T03:00:00+03:00", entry_price=100)
    assert state.entry_time == at(0)


def test_bridge_uses_existing_async_api_memory_persists_and_new_episode_starts():
    policy = ObservableMemoryPredicatePolicy(symbol_bindings={"pair": "AAA"})
    policy.open_position(position_id="A", replay_pair="pair", entry_time=at(0), entry_price=100)
    memory = new_async_memory_state(position_id="A", enabled=True)
    values = []
    for bar in [snapshot(), snapshot(4, high=104, close=101), snapshot(8, high=106, close=105)]:
        context = ObservablePositionContext("A", "AAA", at(0), bar.bar_close_time)
        event = policy_observation(ObservableAdapterObservation(context, bar),
                                   prior_state=memory, policy=policy)
        assert event.observation_type == "memory"
        values.append(event.observed)
        memory = observe_async_memory(
            memory, observed=event.observed, completed_at=event.completed_at,
            decision_time=context.decision_time,
        )
        assert memory.memory_seen is True
        assert memory.first_seen_time == at(4)
        assert memory.trigger_latched is False and memory.trigger_time is None
    assert values == [True, False, True]
    assert memory.latest_seen_time == at(12) and memory.episode_count == 2
    policy.close_position("A")
    assert policy.diagnostics()["active_position_count"] == 0


def test_policy_rejects_unknown_closed_and_reused_position():
    policy = ObservableMemoryPredicatePolicy(symbol_bindings={"pair": "AAA"})
    context = ObservablePositionContext("A", "AAA", at(0), at(4))
    state = new_async_memory_state(position_id="A", enabled=True)
    with pytest.raises(RD27StateError, match="unknown/closed"):
        policy(position=context, snapshot=snapshot(), prior_state=state)
    policy.open_position(position_id="A", replay_pair="pair", entry_time=at(0), entry_price=100)
    policy.close_position("A")
    with pytest.raises(RD27StateError, match="unknown/closed"):
        policy(position=context, snapshot=snapshot(), prior_state=state)
    with pytest.raises(RD27StateError, match="reused"):
        policy.open_position(position_id="A", replay_pair="pair", entry_time=at(8), entry_price=100)


def test_flag_requires_both_existing_switches_and_rejects_custom_policy():
    for flags in ({}, {"async_memory_shadow_enabled": True}):
        with pytest.raises(replay.RD27ReplayError, match="explicitly enabled"):
            replay.replay_lifecycle_policy(
                **inputs(), **flags, observable_memory_predicate_enabled=True,
            )
    with pytest.raises(replay.RD27ReplayError, match="custom adapter policy"):
        replay.replay_lifecycle_policy(
            **inputs(), async_memory_shadow_enabled=True, observable_adapter_enabled=True,
            observable_memory_predicate_enabled=True, observable_policy=lambda **_: None,
        )
    with pytest.raises(replay.RD27ReplayError, match="switch must be boolean"):
        replay.replay_lifecycle_policy(**inputs(), observable_memory_predicate_enabled=1)


def test_disabled_predicate_does_not_construct_or_touch_sink(monkeypatch):
    def forbidden(**kwargs):
        raise AssertionError("disabled predicate instantiated")

    monkeypatch.setattr(replay, "ObservableMemoryPredicatePolicy", forbidden)
    sink = {"untouched": True}
    baseline = replay.replay_lifecycle_policy(**inputs())
    result = replay.replay_lifecycle_policy(
        **inputs(), async_memory_shadow_enabled=True, observable_adapter_enabled=True,
        observable_primitive_rows=primitive_rows(), observable_symbol_bindings={"AAA-USDT": "AAA"},
        observable_memory_predicate_diagnostics=sink,
    )
    assert_native_equal(baseline, result)
    assert sink == {"untouched": True}


@pytest.mark.parametrize("policy", [replay.STATIC_EXIT_STATE_ROUTER,
                                   replay.ADAPTIVE_EXIT_FIXED_CAPITAL,
                                   replay.FULL_ADAPTIVE_LIFECYCLE_BRAIN])
def test_enabled_and_disabled_full_native_parity_and_exact_diagnostics(policy):
    fixture = inputs() | {"policy_id": policy}
    baseline = replay.replay_lifecycle_policy(**fixture)
    disabled, dp, ds, da = run_predicate(fixture=fixture, enabled=False)
    enabled, p, s, a = run_predicate(fixture=fixture)
    assert len(enabled[0]) == 1
    assert_native_equal(baseline, disabled)
    assert_native_equal(baseline, enabled)
    assert dp == {} and da["emitted_memory_observations"] == 0
    assert ds["memory_observations_processed"] == 0
    assert p["predicate_evaluations"] == p["eligible_snapshots_processed"] == 4
    assert p["true_predicate_observations"] == 3
    assert p["false_predicate_observations"] == 1
    assert p["positions_that_established_predicate_memory"] == 1
    assert p["excluded_entry_snapshots"] == 1
    assert p["duplicate_noop_count"] > 0
    assert p["active_position_count"] == 0 and p["positions_closed"] == 1
    record = p["position_records"][0]
    assert record["first_predicate_true_time"] == at(8)
    assert record["current_structural_high"] == 108
    assert [e[2:] for e in record["true_events"]] == [(100, 101, 102), (102, 103, 104),
                                                    (106, 106.5, 108)]
    assert s["memory_observations_processed"] == a["emitted_memory_observations"] == 4
    assert s["memory_episodes_started"] == 2
    assert s["trigger_observations_processed"] == a["emitted_trigger_observations"] == 0
    memory = s["position_records"][0]
    assert memory["first_seen_time"] == at(8) and memory["latest_seen_time"] == at(20)
    assert memory["later_trigger_seen"] is False
    assert memory["memory_seen"] is True and memory["memory_seen_after_reset"] is False


def test_false_after_true_does_not_clear_generic_memory():
    _, p, s, _ = run_predicate(rows=primitive_rows()[:-1])
    assert p["true_predicate_observations"] == 2 and p["false_predicate_observations"] == 1
    memory = s["position_records"][0]
    assert memory["memory_seen"] is True
    assert memory["previous_memory_observation"] is False
    assert memory["latest_seen_time"] == at(12)


def test_identical_runs_shuffled_rows_and_duplicates_same_events():
    rows = primitive_rows()
    a, pa, sa, _ = run_predicate(rows=rows)
    b, pb, sb, ab = run_predicate(rows=rows[::-1] + [rows[1]])
    assert_native_equal(a, b)
    assert pa == pb and sa == sb
    assert ab["duplicates_deduplicated"] == 1
    _, pc, sc, _ = run_predicate(rows=rows)
    assert pa == pc and sa == sc


def test_conflicting_source_duplicate_rejected_before_replay():
    rows = primitive_rows()
    with pytest.raises(ConflictingSnapshotError):
        run_predicate(rows=rows + [row(4, close=100)])


def test_future_source_bar_cannot_affect_current_structure_or_memory():
    a, pa, sa, _ = run_predicate()
    b, pb, sb, _ = run_predicate(rows=primitive_rows() + [row(204, high=9999, close=9998)])
    assert_native_equal(a, b)
    assert pa == pb and sa == sb


def test_two_positions_isolated_and_fresh_later_same_pair():
    fixture = inputs(pairs=("AAA-USDT", "BBB-USDT"), signals=(0, 170), hours=345)
    rows = primitive_rows() + [row(4, "BBB", high=101, close=100), row(172, high=102, close=101)]
    _, p, s, _ = run_predicate(fixture=fixture, rows=rows,
                             bindings={"AAA-USDT": "AAA", "BBB-USDT": "BBB"})
    records = {r["position_id"]: r for r in p["position_records"]}
    assert records[identity()]["current_structural_high"] == 108
    assert records[identity("BBB-USDT")]["first_predicate_true_time"] is None
    later = records[identity(entry=171, sequence=2)]
    assert later["first_predicate_true_time"] == at(176)
    assert later["true_events"][0][2] == 100  # New lifecycle starts at entry, not old 108.
    assert s["resets"] == 4 and p["active_position_count"] == 0


@pytest.mark.parametrize("policy,weak,overrides", [
    (replay.STATIC_EXIT_STATE_ROUTER, True, None),
    (replay.ADAPTIVE_EXIT_FIXED_CAPITAL, True, None),
    (replay.ADAPTIVE_EXIT_FIXED_CAPITAL, False, {10: {"low": 90}}),
    (replay.ADAPTIVE_EXIT_FIXED_CAPITAL, False, {1: {"low": 90}}),
])
def test_cleanup_and_parity_on_existing_exit_paths(policy, weak, overrides):
    fixture = inputs(weak=weak, overrides=overrides) | {"policy_id": policy}
    baseline = replay.replay_lifecycle_policy(**fixture)
    actual, p, s, _ = run_predicate(fixture=fixture)
    assert_native_equal(baseline, actual)
    assert p["positions_created"] == p["positions_closed"] == 1
    assert p["active_position_count"] == 0 and s["resets"] == 1


def test_off_grid_four_hour_closes_all_observed_at_first_available_hour():
    rows = [row(1.5), row(5.5, high=104, close=103), row(9.5, high=106, close=103.5)]
    _, p, s, _ = run_predicate(rows=rows)
    assert p["predicate_evaluations"] == 3
    assert p["true_predicate_observations"] == 2 and p["false_predicate_observations"] == 1
    record = p["position_records"][0]
    assert record["first_predicate_true_time"] == at(6)
    assert record["true_events"][0][1][2] == at(5.5)
    assert s["position_records"][0]["first_seen_time"] == at(6)


def test_no_snapshots_still_registers_and_cleans_predicate_position():
    _, p, s, _ = run_predicate(rows=[])
    assert p["predicate_evaluations"] == 0
    assert p["positions_created"] == p["positions_closed"] == 1
    assert s["memory_observations_processed"] == 0


def test_same_symbol_policy_registry_keeps_two_position_ids_isolated():
    policy = ObservableMemoryPredicatePolicy(symbol_bindings={"pair": "AAA"})
    for position_id, price in [("A", 100), ("B", 105)]:
        policy.open_position(position_id=position_id, replay_pair="pair",
                             entry_time=at(0), entry_price=price)
    adapter = ObservableMemoryAdapter([row(high=106, close=103)],
                                     symbol_bindings={"pair": "AAA"}, policy=policy)
    events = [adapter.observe(position_id=pid, replay_pair="pair", entry_time=at(0),
                              decision_time=at(4),
                              prior_state=new_async_memory_state(position_id=pid, enabled=True))
              for pid in ("A", "B")]
    assert [e.observed for e in events] == [True, False]
    assert [e.position_id for e in events] == ["A", "B"]


def test_source_normalization_and_pure_fold_shuffled_stream_match():
    rows = primitive_rows()[1:]
    states = []
    for source in (rows, rows[::-1]):
        state = fresh(entry=1)
        for bar in normalize_4h_snapshots(source).snapshots:
            state = evaluate(state, bar).state
        states.append(state)
    assert states[0] == states[1]


def test_native_actual_entry_price_is_structural_initial_reference():
    fixture = inputs(overrides={hour: {"open": 105, "high": 107, "low": 104, "close": 106}
                                for hour in range(200)})
    baseline = replay.replay_lifecycle_policy(**fixture)
    result, p, s, _ = run_predicate(fixture=fixture)
    assert_native_equal(baseline, result)
    record = p["position_records"][0]
    assert record["entry_price"] == 105
    assert p["true_predicate_observations"] == 1 and p["false_predicate_observations"] == 3
    assert record["first_predicate_true_time"] == at(20)
    assert record["true_events"][0][2:] == (106, 106.5, 108)
    assert s["position_records"][0]["first_seen_time"] == at(20)


def test_failed_predicate_replay_does_not_publish_diagnostic_sinks():
    predicate, shadow, adapter = {"untouched": True}, {"untouched": True}, {"untouched": True}
    with pytest.raises(ConflictingSnapshotError):
        replay.replay_lifecycle_policy(
            **inputs(), async_memory_shadow_enabled=True, observable_adapter_enabled=True,
            observable_memory_predicate_enabled=True,
            observable_primitive_rows=[row(4), row(4, close=100)],
            observable_symbol_bindings={"AAA-USDT": "AAA"},
            observable_memory_predicate_diagnostics=predicate,
            async_memory_diagnostics=shadow, observable_adapter_diagnostics=adapter,
        )
    assert predicate == shadow == adapter == {"untouched": True}
