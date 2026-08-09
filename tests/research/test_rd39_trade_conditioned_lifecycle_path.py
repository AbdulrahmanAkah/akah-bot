from __future__ import annotations

import math

import pandas as pd

from spotbot.research.rd39_trade_conditioned_lifecycle_path import (
    ADVERSE,
    GIVEBACK,
    RECLAIM_CONTROL,
    UNRECOVERED,
    events_from_trade_states,
    lifecycle_snapshot,
    target_markout,
    validate_constants,
)


def make_lookup(
    *,
    start: str = "2022-01-01T00:00:00Z",
    periods: int = 200,
    base: float = 100.0,
) -> dict[int, tuple[float, float, float, float]]:
    index = pd.date_range(start, periods=periods, freq="h", tz="UTC")
    result: dict[int, tuple[float, float, float, float]] = {}
    for i, timestamp in enumerate(index):
        open_price = base + 0.1 * i
        result[int(timestamp.as_unit("ns").value)] = (
            open_price,
            open_price + 1.0,
            open_price - 1.0,
            open_price + 0.2,
        )
    return result


def test_constants() -> None:
    validate_constants()


def test_lifecycle_snapshot_is_strictly_completed_bar_causal() -> None:
    lookup = make_lookup(periods=80)
    result = lifecycle_snapshot(
        lookup,
        entry_time="2022-01-01T00:00:00Z",
        entry_price=100.0,
        control_exit_time="2022-01-04T00:00:00Z",
        decision_time="2022-01-02T00:00:00Z",
    )
    assert result is not None
    assert result["holding_age_hours"] == 24
    # At t=24 the latest used close is t-1 = hour 23.
    assert math.isclose(
        result["entry_relative_close_return"],
        102.5 / 100.0 - 1.0,
    )


def test_missing_path_hour_is_unevaluable() -> None:
    lookup = make_lookup(periods=80)
    lookup.pop(int(pd.Timestamp("2022-01-01T10:00:00Z").as_unit("ns").value))
    result = lifecycle_snapshot(
        lookup,
        entry_time="2022-01-01T00:00:00Z",
        entry_price=100.0,
        control_exit_time="2022-01-04T00:00:00Z",
        decision_time="2022-01-02T00:00:00Z",
    )
    assert result is None


def test_unrecovered_family_logic() -> None:
    index = pd.date_range(
        "2022-01-01T00:00:00Z",
        periods=80,
        freq="h",
        tz="UTC",
    )
    lookup = {}
    for timestamp in index:
        lookup[int(timestamp.as_unit("ns").value)] = (
            98.0,
            99.0,
            96.0,
            98.0,
        )
    result = lifecycle_snapshot(
        lookup,
        entry_time="2022-01-01T00:00:00Z",
        entry_price=100.0,
        control_exit_time="2022-01-04T00:00:00Z",
        decision_time="2022-01-02T00:00:00Z",
    )
    assert result is not None
    assert result[UNRECOVERED] is True
    assert result["last_12_completed_closes_above_entry_count"] == 0


def test_event_requires_consecutive_observed_false() -> None:
    base = {
        "control_trade_id": 1,
        "universe_id": "C2",
        "period_id": "ROBUSTNESS_2022",
        "pair": "AAA-USDT",
        "entry_time": pd.Timestamp("2022-01-01T00:00:00Z"),
        "control_exit_time": pd.Timestamp("2022-01-05T00:00:00Z"),
        "entry_price": 100.0,
        "holding_age_hours": 24,
        "remaining_control_hours": 72,
        "entry_relative_close_return": -0.01,
        "mfe_return": 0.02,
        "mae_return": -0.03,
        "path_position": 0.4,
        "retained_mfe_fraction": -0.5,
        "last_12_completed_closes_above_entry_count": 0,
        "last_12_completed_closes_below_entry_count": 12,
        ADVERSE: False,
        GIVEBACK: False,
        RECLAIM_CONTROL: False,
    }
    rows = [
        {
            **base,
            "decision_time": "2022-01-02T00:00:00Z",
            UNRECOVERED: False,
        },
        {
            **base,
            "decision_time": "2022-01-02T02:00:00Z",
            UNRECOVERED: True,
        },
        {
            **base,
            "decision_time": "2022-01-02T03:00:00Z",
            UNRECOVERED: False,
        },
        {
            **base,
            "decision_time": "2022-01-02T04:00:00Z",
            UNRECOVERED: True,
        },
    ]
    events = events_from_trade_states(rows)
    selected = events.loc[events["family_id"] == UNRECOVERED]
    assert len(selected) == 1
    assert selected.iloc[0]["decision_time"] == pd.Timestamp("2022-01-02T04:00:00Z")


def test_target_markout_respects_control_exit_boundary() -> None:
    lookup = make_lookup(periods=120)
    valid = target_markout(
        lookup,
        decision_time="2022-01-02T00:00:00Z",
        control_exit_time="2022-01-03T00:00:00Z",
        horizon_hours=24,
    )
    assert valid is not None

    invalid = target_markout(
        lookup,
        decision_time="2022-01-02T00:00:00Z",
        control_exit_time="2022-01-03T00:00:00Z",
        horizon_hours=48,
    )
    assert invalid is None
