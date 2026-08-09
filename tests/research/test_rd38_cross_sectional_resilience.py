from __future__ import annotations

import math

import pandas as pd

from spotbot.research.rd38_cross_sectional_resilience import (
    BREADTH_LAGGARD,
    CROSS_SECTION_SIZE,
    HORIZONS,
    LEADERSHIP_BREAKDOWN,
    PERSISTENT_WEAKNESS,
    RECLAIM_CONTROL,
    average_percentile,
    events_from_state_rows,
    snapshot_state_rows,
    target_markout,
    validate_constants,
)


def make_lookup(
    *,
    start: str = "2021-12-20T00:00:00Z",
    periods: int = 400,
    slope: float = 1.0,
) -> dict[int, tuple[float, float]]:
    index = pd.date_range(
        start,
        periods=periods,
        freq="h",
        tz="UTC",
    )
    return {
        int(timestamp.as_unit("ns").value): (
            100.0 + slope * i,
            100.5 + slope * i,
        )
        for i, timestamp in enumerate(index)
    }


def test_constants_frozen() -> None:
    validate_constants()
    assert CROSS_SECTION_SIZE == 6
    assert HORIZONS == (6, 24, 72)


def test_six_member_average_percentile_quartiles() -> None:
    values = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]
    assert math.isclose(
        average_percentile(values, 2.0),
        0.25,
    )
    assert math.isclose(
        average_percentile(values, 5.0),
        0.75,
    )


def test_snapshot_requires_all_six_valid_histories() -> None:
    decision = pd.Timestamp("2022-01-02T00:00:00Z")
    members = tuple((f"P{i}", i) for i in range(1, 7))
    lookups = {pair: make_lookup() for pair, _rank in members}
    missing_pair = members[-1][0]
    lookups[missing_pair].pop(
        int((decision - pd.Timedelta(hours=1) - pd.Timedelta(hours=72)).as_unit("ns").value)
    )
    assert (
        snapshot_state_rows(
            universe_id="C2",
            decision_time=decision,
            members=members,
            lookups=lookups,
        )
        is None
    )


def test_false_to_true_event_requires_observed_false() -> None:
    base = {
        "universe_id": "C2",
        "period_id": "ROBUSTNESS_2022",
        "pair": "AAA-USDT",
        "membership_rank": 1,
        "return_6h": -0.01,
        "return_24h": -0.02,
        "return_72h": -0.03,
        "percentile_rank_6h": 0.25,
        "percentile_rank_24h": 0.25,
        "percentile_rank_72h": 0.25,
        "negative_breadth_24h": 0.8,
        "leadership_collapse_score": 0.0,
        LEADERSHIP_BREAKDOWN: False,
        BREADTH_LAGGARD: False,
        RECLAIM_CONTROL: False,
    }
    rows = [
        {
            **base,
            "decision_time": "2022-01-01T00:00:00Z",
            PERSISTENT_WEAKNESS: True,
        },
        {
            **base,
            "decision_time": "2022-01-01T01:00:00Z",
            PERSISTENT_WEAKNESS: True,
        },
        {
            **base,
            "decision_time": "2022-01-01T02:00:00Z",
            PERSISTENT_WEAKNESS: False,
        },
        {
            **base,
            "decision_time": "2022-01-01T03:00:00Z",
            PERSISTENT_WEAKNESS: True,
        },
    ]
    events = events_from_state_rows(rows)
    selected = events.loc[events["family_id"] == PERSISTENT_WEAKNESS]
    assert len(selected) == 1
    assert selected.iloc[0]["decision_time"] == pd.Timestamp("2022-01-01T03:00:00Z")


def test_target_markout_uses_decision_open() -> None:
    lookup = make_lookup(
        start="2022-01-01T00:00:00Z",
        periods=100,
        slope=1.0,
    )
    result = target_markout(
        lookup,
        decision_time="2022-01-01T10:00:00Z",
        horizon_hours=24,
    )
    assert result is not None
    assert math.isclose(
        result["entry_open"],
        110.0,
    )
    assert math.isclose(
        result["exit_open"],
        134.0,
    )
    assert math.isclose(
        result["forward_return"],
        134.0 / 110.0 - 1.0,
    )


def test_unobserved_hour_resets_transition_state() -> None:
    base = {
        "universe_id": "C2",
        "period_id": "ROBUSTNESS_2022",
        "pair": "AAA-USDT",
        "membership_rank": 1,
        "return_6h": -0.01,
        "return_24h": -0.02,
        "return_72h": -0.03,
        "percentile_rank_6h": 0.25,
        "percentile_rank_24h": 0.25,
        "percentile_rank_72h": 0.25,
        "negative_breadth_24h": 0.8,
        "leadership_collapse_score": 0.0,
        LEADERSHIP_BREAKDOWN: False,
        BREADTH_LAGGARD: False,
        RECLAIM_CONTROL: False,
    }
    rows = [
        {
            **base,
            "decision_time": "2022-01-01T00:00:00Z",
            PERSISTENT_WEAKNESS: False,
        },
        {
            **base,
            "decision_time": "2022-01-01T02:00:00Z",
            PERSISTENT_WEAKNESS: True,
        },
    ]
    events = events_from_state_rows(rows)
    selected = events.loc[events["family_id"] == PERSISTENT_WEAKNESS]
    assert selected.empty
