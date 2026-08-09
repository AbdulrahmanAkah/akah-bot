from __future__ import annotations

import math

import pandas as pd

from spotbot.research.rd40_transition_dynamics_governor import (
    GLOBAL,
    LOCKED,
    LOWER_HIGH,
    RECLAIM_VETO,
    STALE_PEAK,
    TROUGH_FAILURE,
    build_governor_timelines,
    classify_cell,
    events_from_state_rows,
    governor_state_at,
    lifecycle_snapshot,
    normalize_governor_transitions,
    target_markout,
    validate_constants,
)


def make_lookup(
    *,
    start: str = "2022-01-01T00:00:00Z",
    periods: int = 200,
) -> dict[int, tuple[float, float, float, float]]:
    index = pd.date_range(start, periods=periods, freq="h", tz="UTC")
    result: dict[int, tuple[float, float, float, float]] = {}
    for i, timestamp in enumerate(index):
        open_price = 100.0 + i * 0.05
        result[int(timestamp.as_unit("ns").value)] = (
            open_price,
            open_price + 1.0,
            open_price - 1.0,
            open_price + 0.2,
        )
    return result


def make_state_row(
    *,
    decision: str,
    governor_state: str,
    stale_peak: bool,
) -> dict[str, object]:
    return {
        "control_trade_id": 1,
        "universe_id": "C2",
        "period_id": "ROBUSTNESS_2022",
        "pair": "AAA-USDT",
        "entry_time": pd.Timestamp("2022-01-01T00:00:00Z"),
        "control_exit_time": pd.Timestamp("2022-01-06T00:00:00Z"),
        "entry_price": 100.0,
        "decision_time": pd.Timestamp(decision),
        "governor_state": governor_state,
        "holding_age_hours": 48,
        "remaining_control_hours": 72,
        "current_close_return_from_entry": 0.02,
        "peak_price": 110.0,
        "peak_gain_from_entry": 0.10,
        "peak_time": pd.Timestamp("2022-01-01T12:00:00Z"),
        "hours_since_peak": 36,
        "giveback_fraction_of_peak_gain": 0.8,
        "close_return_12h": -0.03,
        "last12_high": 104.0,
        "prior12_high": 108.0,
        "last12_low": 100.0,
        "recovery_from_last12_low_toward_peak": 0.2,
        "last12_positive_close_step_share": 0.3,
        STALE_PEAK: stale_peak,
        LOWER_HIGH: False,
        TROUGH_FAILURE: False,
        RECLAIM_VETO: False,
    }


def test_constants() -> None:
    validate_constants()


def test_governor_state_is_effective_at_action_time_only() -> None:
    raw = pd.DataFrame(
        [
            {
                "policy_id": "REGIME_HYSTERESIS_ADMISSION_GOVERNOR",
                "portfolio_id": "UNION_FOCUS",
                "universe_id": "C2",
                "context_time": "2022-01-01T09:00:00Z",
                "action_time": "2022-01-01T10:00:00Z",
                "prior_state": "OPEN",
                "next_state": "CAUTION",
                "market_context": "MIXED",
                "transition_reason": "TEST",
            },
            {
                "policy_id": "REGIME_HYSTERESIS_ADMISSION_GOVERNOR",
                "portfolio_id": "UNION_FOCUS",
                "universe_id": "C2",
                "context_time": "2022-01-01T10:00:00Z",
                "action_time": "2022-01-01T11:00:00Z",
                "prior_state": "CAUTION",
                "next_state": "LOCKED",
                "market_context": "STRESSED",
                "transition_reason": "TEST",
            },
        ]
    )
    # Add minimal valid chains for D2/E2.
    for universe in ("D2", "E2"):
        raw = pd.concat(
            [
                raw,
                pd.DataFrame(
                    [
                        {
                            "policy_id": "REGIME_HYSTERESIS_ADMISSION_GOVERNOR",
                            "portfolio_id": "UNION_FOCUS",
                            "universe_id": universe,
                            "context_time": "2022-01-01T09:00:00Z",
                            "action_time": "2022-01-01T10:00:00Z",
                            "prior_state": "OPEN",
                            "next_state": "LOCKED",
                            "market_context": "STRESSED",
                            "transition_reason": "TEST",
                        }
                    ]
                ),
            ],
            ignore_index=True,
        )

    transitions = normalize_governor_transitions(raw)
    timelines = build_governor_timelines(transitions)
    assert (
        governor_state_at(
            timelines,
            universe="C2",
            decision_time="2022-01-01T09:00:00Z",
        )
        == "OPEN"
    )
    assert (
        governor_state_at(
            timelines,
            universe="C2",
            decision_time="2022-01-01T10:00:00Z",
        )
        == "CAUTION"
    )
    assert (
        governor_state_at(
            timelines,
            universe="C2",
            decision_time="2022-01-01T11:00:00Z",
        )
        == "LOCKED"
    )


def test_conditioned_event_can_be_created_by_governor_transition() -> None:
    rows = [
        make_state_row(
            decision="2022-01-03T00:00:00Z",
            governor_state="OPEN",
            stale_peak=True,
        ),
        make_state_row(
            decision="2022-01-03T01:00:00Z",
            governor_state="LOCKED",
            stale_peak=True,
        ),
    ]
    events = events_from_state_rows(rows)
    locked = events.loc[(events["family_id"] == STALE_PEAK) & (events["lane_id"] == LOCKED)]
    assert len(locked) == 1
    # Global starts true without prior observed false, so it is not an event.
    global_events = events.loc[(events["family_id"] == STALE_PEAK) & (events["lane_id"] == GLOBAL)]
    assert global_events.empty


def test_unobserved_gap_resets_event_state() -> None:
    rows = [
        make_state_row(
            decision="2022-01-03T00:00:00Z",
            governor_state="LOCKED",
            stale_peak=False,
        ),
        make_state_row(
            decision="2022-01-03T02:00:00Z",
            governor_state="LOCKED",
            stale_peak=True,
        ),
    ]
    events = events_from_state_rows(rows)
    selected = events.loc[(events["family_id"] == STALE_PEAK) & (events["lane_id"] == LOCKED)]
    assert selected.empty


def test_lifecycle_snapshot_uses_t_minus_1_and_requires_open_t() -> None:
    lookup = make_lookup(periods=100)
    result = lifecycle_snapshot(
        lookup,
        entry_time="2022-01-01T00:00:00Z",
        entry_price=100.0,
        control_exit_time="2022-01-05T00:00:00Z",
        decision_time="2022-01-03T00:00:00Z",
    )
    assert result is not None
    # Latest completed close at t-1 = hour 47.
    assert math.isclose(
        result["current_close_return_from_entry"],
        (100.0 + 47 * 0.05 + 0.2) / 100.0 - 1.0,
    )

    lookup.pop(int(pd.Timestamp("2022-01-03T00:00:00Z").as_unit("ns").value))
    assert (
        lifecycle_snapshot(
            lookup,
            entry_time="2022-01-01T00:00:00Z",
            entry_price=100.0,
            control_exit_time="2022-01-05T00:00:00Z",
            decision_time="2022-01-03T00:00:00Z",
        )
        is None
    )


def test_target_markout_respects_control_exit_boundary() -> None:
    lookup = make_lookup(periods=150)
    assert (
        target_markout(
            lookup,
            decision_time="2022-01-03T00:00:00Z",
            control_exit_time="2022-01-04T00:00:00Z",
            horizon_hours=24,
        )
        is not None
    )
    assert (
        target_markout(
            lookup,
            decision_time="2022-01-03T00:00:00Z",
            control_exit_time="2022-01-04T00:00:00Z",
            horizon_hours=48,
        )
        is None
    )


def test_cell_taxonomy_distinguishes_reversed_direction() -> None:
    negative_reversed = {
        "event_count": 40,
        "pair_count": 8,
        "signal_day_count": 20,
        "mean_forward_return": 0.02,
        "median_forward_return": 0.01,
        "lopo_worst_directional_mean": 0.005,
    }
    assert (
        classify_cell(
            negative_reversed,
            direction="NEGATIVE",
        )
        == "REVERSED_DIRECTION"
    )

    positive_pass = {
        **negative_reversed,
        "mean_forward_return": 0.02,
        "median_forward_return": 0.01,
        "lopo_worst_directional_mean": 0.005,
    }
    assert (
        classify_cell(
            positive_pass,
            direction="POSITIVE",
        )
        == "QUALIFIED_EXPECTED_DIRECTION"
    )
