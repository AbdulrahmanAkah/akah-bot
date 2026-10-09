from __future__ import annotations

from dataclasses import FrozenInstanceError, replace

import pandas as pd
import pytest

from spotbot.research.rd27_adaptive_lifecycle import (
    ASYNC_MEMORY_PROTOCOL_ID,
    DEFAULT_ASYNC_MEMORY_ENABLED,
    AsyncMemoryState,
    RD27StateError,
    contract_summary,
    new_async_memory_state,
    observe_async_memory,
    observe_async_trigger,
    reset_async_memory_state,
)

BASE = pd.Timestamp("2030-01-01T00:00:00Z")


def at(hours: float) -> pd.Timestamp:
    return BASE + pd.Timedelta(hours=hours)


def fresh(position_id: str = "position-A") -> AsyncMemoryState:
    return new_async_memory_state(position_id=position_id, enabled=True)


def memory(state: AsyncMemoryState, hour: float, value: bool = True) -> AsyncMemoryState:
    return observe_async_memory(
        state, observed=value, completed_at=at(hour), decision_time=at(hour),
    )


def trigger(state: AsyncMemoryState, hour: float, value: bool = True) -> AsyncMemoryState:
    return observe_async_trigger(
        state, observed=value, completed_at=at(hour), decision_time=at(hour),
    )


def test_default_disabled_is_no_op() -> None:
    state = new_async_memory_state(position_id="position-A")
    assert DEFAULT_ASYNC_MEMORY_ENABLED is False
    assert state.enabled is False
    assert memory(state, 0) == state
    assert trigger(state, 0) == state
    assert memory(state, 0) is not state
    assert state.current_age_hours is None


def test_first_memory_establishes_without_mutating_input() -> None:
    state = fresh()
    armed = memory(state, 1)
    assert armed.memory_seen is True
    assert armed.first_seen_time == armed.latest_seen_time == at(1)
    assert armed.episode_count == 1
    assert armed.previous_memory_observation is True
    assert armed.current_age_hours == 0
    assert state.memory_seen is False
    assert armed is not state


def test_strictly_later_trigger_after_false_interval() -> None:
    state = memory(memory(fresh(), 1), 2, False)
    result = trigger(state, 3)
    assert result.trigger_latched is True
    assert result.trigger_time == at(3)
    assert result.previous_memory_observation is False
    assert state.trigger_latched is False


def test_same_time_first_memory_and_trigger_fails() -> None:
    with pytest.raises(RD27StateError, match="strictly later"):
        trigger(memory(fresh(), 1), 1)


def test_trigger_before_memory_fails() -> None:
    with pytest.raises(RD27StateError, match="established memory"):
        trigger(fresh(), 0)


def test_false_trigger_without_memory_is_recorded_but_not_latched() -> None:
    state = trigger(fresh(), 1, False)
    assert state.trigger_latched is False
    assert state.last_trigger_observation_value is False
    assert state.current_age_hours is None


def test_first_and_latest_seen_times() -> None:
    state = memory(memory(fresh(), 1), 4)
    assert state.first_seen_time == at(1)
    assert state.latest_seen_time == at(4)
    assert state.last_memory_observation_time == at(4)
    assert state.last_memory_observation_value is True


def test_age_progresses_in_whole_hours_since_latest_true() -> None:
    state = memory(fresh(), 1)
    state = memory(state, 3.75, False)
    assert state.current_age_hours == 2
    state = trigger(state, 5, False)
    assert state.current_age_hours == 4
    assert memory(state, 6).current_age_hours == 0


def test_continuous_true_observations_are_one_episode() -> None:
    state = fresh()
    for hour in range(5):
        state = memory(state, hour)
    assert state.episode_count == 1


def test_false_to_true_starts_new_episode() -> None:
    state = memory(memory(memory(fresh(), 0), 1, False), 2)
    assert state.episode_count == 2
    assert state.first_seen_time == at(0)
    assert state.latest_seen_time == at(2)


@pytest.mark.parametrize("value", [False, True])
def test_identical_memory_duplicate_is_idempotent(value: bool) -> None:
    state = memory(fresh(), 0, value)
    duplicate = memory(state, 0, value)
    assert duplicate == state
    assert duplicate is not state


@pytest.mark.parametrize("value", [False, True])
def test_conflicting_memory_duplicate_fails(value: bool) -> None:
    with pytest.raises(RD27StateError, match="conflicting duplicate memory"):
        memory(memory(fresh(), 0, value), 0, not value)


def test_backward_memory_fails() -> None:
    with pytest.raises(RD27StateError, match="backward"):
        memory(memory(fresh(), 2), 1)


def test_cross_stream_clock_rejects_stale_memory_retry() -> None:
    state = trigger(memory(fresh(), 1), 2)
    with pytest.raises(RD27StateError, match="backward"):
        memory(state, 1)


def test_backward_trigger_fails() -> None:
    with pytest.raises(RD27StateError, match="backward"):
        trigger(memory(fresh(), 2), 1)


def test_trigger_duplicate_is_idempotent() -> None:
    state = trigger(memory(fresh(), 0), 1)
    duplicate = trigger(state, 1)
    assert duplicate == state
    assert duplicate is not state


def test_conflicting_trigger_duplicate_fails() -> None:
    state = trigger(memory(fresh(), 0), 1, False)
    with pytest.raises(RD27StateError, match="conflicting duplicate trigger"):
        trigger(state, 1)


def test_trigger_latch_retains_earliest_time() -> None:
    state = trigger(memory(fresh(), 0), 1)
    state = trigger(state, 2, False)
    state = trigger(state, 3)
    assert state.trigger_latched is True
    assert state.trigger_time == at(1)
    assert state.latest_event_time == at(3)


def test_refresh_on_trigger_bar_does_not_erase_earlier_memory() -> None:
    state = memory(memory(fresh(), 0), 1)
    assert trigger(state, 1).trigger_latched is True


def test_reset_clears_memory_trigger_and_duplicate_state() -> None:
    state = trigger(memory(fresh(), 0), 1)
    cleared = reset_async_memory_state(
        state, reset_at=at(2), reason="POSITION_CLOSED", decision_time=at(2),
    )
    assert cleared == replace(fresh(), latest_event_time=at(2), reset_time=at(2),
                              reset_reason="POSITION_CLOSED")
    assert cleared.memory_seen is cleared.trigger_latched is False
    assert cleared.current_age_hours is None
    assert state.trigger_latched is True
    with pytest.raises(RD27StateError, match="established memory"):
        trigger(cleared, 3)


def test_reset_reason_is_retained_when_new_memory_establishes() -> None:
    state = reset_async_memory_state(fresh(), reset_at=at(1), reason="REENTRY", decision_time=at(1))
    state = memory(state, 2)
    assert state.reset_reason == "REENTRY"
    assert state.first_seen_time == at(2)
    assert state.episode_count == 1


@pytest.mark.parametrize("reason", ["", "   ", None])
def test_reset_requires_nonempty_reason(reason: str) -> None:
    with pytest.raises(RD27StateError, match="non-empty reason"):
        reset_async_memory_state(fresh(), reset_at=at(0), reason=reason, decision_time=at(0))


def test_backward_reset_fails() -> None:
    with pytest.raises(RD27StateError, match="backward"):
        reset_async_memory_state(memory(fresh(), 2), reset_at=at(1),
                                 reason="CLOSED", decision_time=at(2))


def test_same_frontier_reset_is_allowed_but_stale_observation_is_not() -> None:
    state = reset_async_memory_state(memory(fresh(), 1), reset_at=at(1),
                                     reason="CLOSED", decision_time=at(1))
    with pytest.raises(RD27StateError, match="after reset"):
        memory(state, 1)
    assert memory(state, 2).episode_count == 1


def test_position_sidecars_are_isolated() -> None:
    a, b = fresh("A"), fresh("B")
    updated = trigger(memory(a, 0), 1)
    assert updated.position_id == "A"
    assert a == fresh("A")
    assert b == fresh("B")
    assert new_async_memory_state(position_id="A", enabled=True).memory_seen is False


def test_state_is_frozen() -> None:
    state = fresh()
    with pytest.raises(FrozenInstanceError):
        state.memory_seen = True


def test_utc_normalization_preserves_duplicate_identity() -> None:
    state = observe_async_memory(fresh(), observed=True,
                                 completed_at=pd.Timestamp("2030-01-01T03:00:00+03:00"),
                                 decision_time=BASE.tz_localize(None))
    assert state.first_seen_time == BASE
    assert str(state.first_seen_time.tz) == "UTC"
    assert memory(state, 0) == state


@pytest.mark.parametrize("observe", [observe_async_memory, observe_async_trigger])
def test_future_observation_fails(observe) -> None:
    with pytest.raises(RD27StateError, match="not yet available"):
        observe(fresh(), observed=False, completed_at=at(2), decision_time=at(1))


def test_future_reset_fails() -> None:
    with pytest.raises(RD27StateError, match="not yet available"):
        reset_async_memory_state(fresh(), reset_at=at(2), reason="CLOSED", decision_time=at(1))


@pytest.mark.parametrize("value", [None, pd.NaT, "now", "today", "bad-time"])
def test_invalid_or_wall_clock_timestamp_fails(value) -> None:
    with pytest.raises(RD27StateError, match="timestamp"):
        observe_async_memory(fresh(), observed=True, completed_at=value, decision_time=at(1))


@pytest.mark.parametrize("value", [None, 0, 1, "true"])
def test_missing_or_coerced_boolean_fails(value) -> None:
    with pytest.raises(RD27StateError, match="boolean"):
        memory(fresh(), 0, value)


@pytest.mark.parametrize("position_id", ["", "  ", None])
def test_nonempty_position_identity_required(position_id: str) -> None:
    with pytest.raises(RD27StateError, match="position_id"):
        new_async_memory_state(position_id=position_id)


def test_enabled_flag_is_explicit_boolean() -> None:
    with pytest.raises(RD27StateError, match="boolean"):
        new_async_memory_state(position_id="A", enabled=1)


def test_deterministic_state_sequence_from_equal_snapshots() -> None:
    def sequence(state: AsyncMemoryState) -> AsyncMemoryState:
        return trigger(memory(memory(memory(state, 0), 1, False), 2), 3)

    original = fresh()
    assert sequence(original) == sequence(replace(original))
    assert original == fresh()


def test_contract_exposes_only_shadow_protocol() -> None:
    summary = contract_summary()
    assert summary["async_memory_protocol_id"] == ASYNC_MEMORY_PROTOCOL_ID
    assert ASYNC_MEMORY_PROTOCOL_ID == "CAUSAL_EXIT_BRAIN_ASYNC_MEMORY_STATE_MACHINE_V1"
    assert summary["async_memory_default_enabled"] is False
    assert summary["async_memory_changes_exit_decisions"] is False
