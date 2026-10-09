from __future__ import annotations

import inspect
from dataclasses import FrozenInstanceError, fields, replace

import pandas as pd
import pytest
from test_rd27_async_memory_shadow_replay import (
    assert_native_equal,
    at,
    identity,
    inputs,
    observation,
)
from test_rd27_observable_later_trigger_predicate import rows_for, run_trigger
from test_rd27_observable_memory_adapter import row

from spotbot.research import rd27_lifecycle_replay as replay
from spotbot.research.rd27_adaptive_lifecycle import (
    AsyncTriggerNotReadyError,
    ExitDecision,
    RD27StateError,
    new_async_memory_state,
    observe_async_memory,
    observe_async_trigger,
)
from spotbot.research.rd27_async_exit_candidate_shadow import (
    CANDIDATE_PARAMETER_COUNT,
    DEFAULT_ASYNC_EXIT_CANDIDATE_SHADOW_ENABLED,
    AsyncExitCandidateShadow,
    ShadowExitCandidate,
    candidate_from_accepted_transition,
)


def run_candidate(*, rows=None, memory=True, fixture=None, observations=(), bindings=None):
    candidate, trigger, shadow = {}, {}, {}
    result = replay.replay_lifecycle_policy(
        **(inputs() if fixture is None else fixture), async_memory_shadow_enabled=True,
        observable_adapter_enabled=True, observable_memory_predicate_enabled=memory,
        observable_later_trigger_predicate_enabled=True, async_exit_candidate_shadow_enabled=True,
        observable_primitive_rows=rows_for() if rows is None else rows,
        observable_symbol_bindings={"AAA-USDT": "AAA"} if bindings is None else bindings,
        async_memory_observations=observations, async_memory_diagnostics=shadow,
        observable_later_trigger_predicate_diagnostics=trigger,
        async_exit_candidate_diagnostics=candidate,
    )
    return result, candidate, trigger, shadow


def accepted(*, position_id="A", memory_hour=4, trigger_hour=8):
    initial = new_async_memory_state(position_id=position_id, enabled=True)
    before = observe_async_memory(initial, observed=True, completed_at=at(memory_hour),
                                  decision_time=at(memory_hour))
    after = observe_async_trigger(before, observed=True, completed_at=at(trigger_hour),
                                 decision_time=at(trigger_hour))
    event = (at(trigger_hour), ("AAA", at(trigger_hour - 4), at(trigger_hour)), 104., 103.)
    return before, after, event


def test_default_disabled_zero_parameters():
    assert DEFAULT_ASYNC_EXIT_CANDIDATE_SHADOW_ENABLED is False
    assert CANDIDATE_PARAMETER_COUNT == 0
    assert inspect.signature(replay.replay_lifecycle_policy).parameters[
        "async_exit_candidate_shadow_enabled"
    ].default is False


def test_disabled_does_not_construct_or_touch_sink(monkeypatch):
    def forbidden():
        raise AssertionError("disabled candidate constructed")

    monkeypatch.setattr(replay, "AsyncExitCandidateShadow", forbidden)
    sink = {"untouched": True}
    native = replay.replay_lifecycle_policy(**inputs())
    disabled = replay.replay_lifecycle_policy(**inputs(), async_exit_candidate_diagnostics=sink)
    assert_native_equal(native, disabled)
    assert sink == {"untouched": True}


def test_memory_then_trigger_emits_exact_evidence_once_and_retains_first_time():
    _, c, t, s = run_candidate()
    assert c["trigger_candidates_observed"] == 2
    assert c["successfully_latched_later_triggers"] == c["shadow_exit_candidates_emitted"] == 1
    assert c["repeated_trigger_observations_after_candidate"] == 1
    event, = c["candidate_events"]
    assert event.position_id == identity() and event.symbol == "AAA"
    assert event.memory_first_seen_time == at(8)
    assert event.memory_latest_seen_time == at(12)
    assert event.memory_episode_count == 1
    assert event.candidate_time == event.latched_trigger_time == at(16)
    assert event.trigger_candidate_time == at(16)
    assert event.memory_snapshot_identity == ("AAA", at(4), at(8))
    assert event.latest_memory_snapshot_identity == ("AAA", at(8), at(12))
    assert event.trigger_snapshot_identity == ("AAA", at(12), at(16))
    assert event.trigger_confirming_close == 103.5 and event.trigger_previous_low == 104
    assert event.memory_to_trigger_delay_hours == 8
    assert c["first_candidate_times"] == ((identity(), at(16)),)
    assert c["memory_to_trigger_delays_hours"] == ((identity(), 8.),)
    assert t["latched_later_triggers"] == 1
    assert s["position_records"][0]["memory_seen"] is True
    assert s["position_records"][0]["later_trigger_time"] == at(16)


def test_early_trigger_then_memory_cannot_backfill():
    _, c, _, s = run_candidate(rows=rows_for("A"))
    assert c["candidate_suppressed_before_memory"] == 1
    assert c["shadow_exit_candidates_emitted"] == 0
    assert c["candidate_events"] == ()
    assert c["memory_established_lifecycles"] == 1
    assert s["position_records"][0]["first_seen_time"] == at(16)


def test_early_trigger_not_retried_when_memory_arrives_between_bars():
    _, c, _, _ = run_candidate(rows=rows_for("A"), memory=False,
                               observations=[observation(13)])
    assert c["trigger_candidates_observed"] == 1
    assert c["shadow_exit_candidates_emitted"] == 0


def test_same_time_rejection_then_later_new_event_only():
    _, c, _, _ = run_candidate(memory=False, observations=[observation(16)])
    assert c["candidate_suppressed_temporal_invalid"] == 1
    assert c["shadow_exit_candidates_emitted"] == 1
    event, = c["candidate_events"]
    assert event.memory_first_seen_time == at(16) and event.candidate_time == at(20)
    assert event.memory_snapshot_identity is None


def test_same_time_without_another_trigger_never_emits():
    _, c, _, _ = run_candidate(rows=rows_for()[:3], memory=False,
                               observations=[observation(16)])
    assert c["candidate_suppressed_temporal_invalid"] == 1
    assert c["shadow_exit_candidates_emitted"] == 0


def test_generic_same_time_still_fails_closed():
    with pytest.raises(AsyncTriggerNotReadyError, match="strictly later"):
        accepted(memory_hour=8, trigger_hour=8)


@pytest.mark.parametrize("memory,case", [(True, "C"), (False, "B")])
def test_memory_without_deterioration_or_trigger_without_memory(memory, case):
    _, c, _, _ = run_candidate(rows=rows_for(case), memory=memory)
    assert c["shadow_exit_candidates_emitted"] == 0
    assert c["memory_established_lifecycles"] == int(memory)
    assert c["candidate_suppressed_before_memory"] == (0 if memory else 2)


def test_multiple_memory_episodes_captured_at_first_latch():
    values = [(4, 101, 103, 104), (8, 102, 103, 105),
              (12, 105, 106, 107), (16, 102, 104, 106)]
    rows = [row(h, open=c, low=low, close=c, high=high) for h, low, c, high in values]
    _, c, _, _ = run_candidate(rows=rows)
    event, = c["candidate_events"]
    assert event.memory_episode_count == 2
    assert event.memory_first_seen_time == at(8) and event.memory_latest_seen_time == at(16)
    assert event.candidate_time == at(20)


def test_three_true_triggers_still_one_event():
    rows = rows_for() + [row(20, open=99, low=98, close=99, high=100)]
    _, c, _, _ = run_candidate(rows=rows)
    assert c["trigger_candidates_observed"] == 3
    assert c["repeated_trigger_observations_after_candidate"] == 2
    assert c["shadow_exit_candidates_emitted"] == 1
    assert c["candidate_events"][0].candidate_time == at(16)


@pytest.mark.parametrize("policy", [replay.STATIC_EXIT_STATE_ROUTER,
                                   replay.ADAPTIVE_EXIT_FIXED_CAPITAL,
                                   replay.FULL_ADAPTIVE_LIFECYCLE_BRAIN])
def test_all_four_modes_complete_native_parity_and_generic_state_unchanged(policy):
    fixture = inputs() | {"policy_id": policy}
    native = replay.replay_lifecycle_policy(**fixture)
    memory_only = run_trigger(fixture=fixture, trigger=False)
    both = run_trigger(fixture=fixture)
    conjunction = run_candidate(fixture=fixture)
    for output in (memory_only[0], both[0], conjunction[0]):
        assert_native_equal(native, output)
        assert len(output[0]) == 1
    assert both[1] == conjunction[2]  # Existing trigger diagnostics untouched.
    assert both[3] == conjunction[3]  # No generic memory/trigger/reset mutation.
    assert conjunction[1]["shadow_exit_candidates_emitted"] == 1


def test_deterministic_replay_shuffling_and_exact_duplicates():
    a = run_candidate()
    b = run_candidate(rows=list(reversed(rows_for())) + [rows_for()[2]])
    c = run_candidate()
    assert_native_equal(a[0], b[0])
    assert a[1:] == b[1:] == c[1:]


def test_future_bar_does_not_change_diagnostics():
    a = run_candidate()
    b = run_candidate(rows=rows_for() + [row(204, open=1, low=.5, close=1, high=2)])
    assert a[1:] == b[1:]


def test_off_grid_close_uses_actual_latch_boundary_not_bar_label():
    rows = [{**r, "bar_open_time": r["bar_open_time"] + pd.Timedelta(minutes=30),
             "bar_close_time": r["bar_close_time"] + pd.Timedelta(minutes=30)} for r in rows_for()]
    _, c, _, _ = run_candidate(rows=rows)
    event, = c["candidate_events"]
    assert event.memory_first_seen_time == at(9)
    assert event.candidate_time == at(17) and event.trigger_snapshot_identity[2] == at(16.5)
    assert event.memory_to_trigger_delay_hours == 8


def test_positions_and_later_lifecycles_isolated_and_archived():
    fixture = inputs(pairs=("AAA-USDT", "BBB-USDT"), signals=(0, 170), hours=345)
    rows = rows_for() + [row(4, "BBB"), row(8, "BBB"), row(172, low=90, close=95)]
    result, c, _, s = run_candidate(fixture=fixture, rows=rows,
                                    bindings={"AAA-USDT": "AAA", "BBB-USDT": "BBB"})
    assert_native_equal(replay.replay_lifecycle_policy(**fixture), result)
    assert c["lifecycles_observed"] == c["archived_candidate_states"] == s["resets"] == 4
    assert c["active_candidate_states"] == 0 and c["lifecycles_with_candidate"] == 1
    records = {r.position_id: r for r in c["position_records"]}
    assert records[identity()].candidate.candidate_time == at(16)
    assert records[identity("BBB-USDT")].candidate is None
    assert records[identity(entry=171, sequence=2)].candidate is None
    assert records[identity(entry=171, sequence=2)].memory_established is False


@pytest.mark.parametrize("policy,weak,overrides", [
    (replay.STATIC_EXIT_STATE_ROUTER, True, None),
    (replay.ADAPTIVE_EXIT_FIXED_CAPITAL, True, None),
    (replay.ADAPTIVE_EXIT_FIXED_CAPITAL, False, {10: {"low": 90}}),
    (replay.ADAPTIVE_EXIT_FIXED_CAPITAL, False, {1: {"low": 90}}),
])
def test_native_exit_cleanup_paths(policy, weak, overrides):
    fixture = inputs(weak=weak, overrides=overrides) | {"policy_id": policy}
    result, c, _, s = run_candidate(fixture=fixture)
    assert_native_equal(replay.replay_lifecycle_policy(**fixture), result)
    assert c["archived_candidate_states"] == s["resets"] == 1
    assert c["active_candidate_states"] == 0


def test_immutable_records_are_not_exit_decisions_or_outcome_containers():
    _, c, _, _ = run_candidate()
    event, = c["candidate_events"]
    assert isinstance(event, ShadowExitCandidate) and not isinstance(event, ExitDecision)
    with pytest.raises(FrozenInstanceError):
        event.candidate_time = at(100)
    with pytest.raises(FrozenInstanceError):
        c["position_records"][0].candidate = None
    names = {f.name for f in fields(event)}
    assert not names & {"pnl", "mfe", "mae", "exit_reason", "exit_price", "regime"}
    assert c["actual_exit_authority"] is False


@pytest.mark.parametrize("trigger_hour", [5, 8, 1000])
def test_no_delay_threshold_and_pure_projection_does_not_mutate(trigger_hour):
    before, after, evidence = accepted(trigger_hour=trigger_hour)
    saved = (before, after)
    event = candidate_from_accepted_transition(before, after, symbol="AAA", trigger_event=evidence)
    assert event.candidate_time == at(trigger_hour)
    assert event.memory_to_trigger_delay_hours == trigger_hour - 4
    assert saved == (before, after)
    assert candidate_from_accepted_transition(after, after, symbol="AAA",
                                              trigger_event=evidence) is None


def test_same_symbol_registry_isolation_and_reused_closed_identity_fail():
    observer = AsyncExitCandidateShadow()
    observer.open_position("A", "AAA")
    observer.open_position("B", "AAA")
    before, after, event = accepted()
    observer.observe_memory(before)
    observer.accepted_trigger(before, after, trigger_event=event)
    first = observer.diagnostics()
    observer.accepted_trigger(after, after)
    assert observer.diagnostics()["candidate_events"] == first["candidate_events"]
    assert observer.diagnostics()["position_records"][1].candidate is None
    observer.close_position("A")
    with pytest.raises(RD27StateError, match="reused"):
        observer.open_position("A", "AAA")
    with pytest.raises(RD27StateError, match="unknown or closed"):
        observer.observe_memory(after)
    observer.open_position("A2", "AAA")
    assert observer.diagnostics()["position_records"][1].candidate is None
    assert first["position_records"][0].archived is False


@pytest.mark.parametrize("mutation", ["identity", "symbol", "time"])
def test_projection_evidence_binding_fails_closed(mutation):
    before, after, event = accepted()
    if mutation == "identity":
        before = replace(before, position_id="wrong")
    elif mutation == "symbol":
        event = (event[0], ("BBB", at(4), at(8)), event[2], event[3])
    else:
        event = (at(9), *event[1:])
    with pytest.raises(RD27StateError):
        candidate_from_accepted_transition(before, after, symbol="AAA", trigger_event=event)


def test_external_true_trigger_without_snapshot_evidence_rejected():
    with pytest.raises(RD27StateError, match="snapshot-bound"):
        run_candidate(observations=[observation(10, "trigger")])


def test_generic_conflicts_not_swallowed_by_candidate_layer():
    with pytest.raises(RD27StateError, match="conflicting duplicate trigger"):
        run_candidate(observations=[observation(16, "trigger", False)])


@pytest.mark.parametrize("flags", [{"async_exit_candidate_shadow_enabled": 1},
                                     {"async_exit_candidate_shadow_enabled": True}])
def test_invalid_configuration_fails_closed(flags):
    with pytest.raises(replay.RD27ReplayError):
        replay.replay_lifecycle_policy(**inputs(), **flags)


def test_no_snapshot_no_event_but_complete_lifecycle_accounting():
    _, c, _, _ = run_candidate(rows=[])
    assert c["shadow_exit_candidates_emitted"] == c["memory_established_lifecycles"] == 0
    assert c["lifecycles_observed"] == c["archived_candidate_states"] == 1


def test_later_same_symbol_lifecycle_can_emit_its_own_fresh_event():
    fixture = inputs(signals=(0, 170), hours=345)
    shift = pd.Timedelta(hours=168)
    later_rows = [{**r, "bar_open_time": r["bar_open_time"] + shift,
                   "bar_close_time": r["bar_close_time"] + shift} for r in rows_for()]
    result, c, _, _ = run_candidate(fixture=fixture, rows=rows_for() + later_rows)
    assert_native_equal(replay.replay_lifecycle_policy(**fixture), result)
    assert c["shadow_exit_candidates_emitted"] == 2
    first, second = c["candidate_events"]
    assert first.position_id == identity() and first.candidate_time == at(16)
    assert second.position_id == identity(entry=171, sequence=2)
    assert second.memory_first_seen_time == at(176) and second.candidate_time == at(184)
    assert second.memory_episode_count == 1


def test_failed_replay_does_not_publish_partial_candidate_sink():
    sink = {"untouched": True}
    with pytest.raises(RD27StateError, match="conflicting duplicate trigger"):
        replay.replay_lifecycle_policy(
            **inputs(), async_memory_shadow_enabled=True, observable_adapter_enabled=True,
            observable_memory_predicate_enabled=True,
            observable_later_trigger_predicate_enabled=True,
            async_exit_candidate_shadow_enabled=True, observable_primitive_rows=rows_for(),
            observable_symbol_bindings={"AAA-USDT": "AAA"},
            async_memory_observations=[observation(16, "trigger", False)],
            async_exit_candidate_diagnostics=sink,
        )
    assert sink == {"untouched": True}
