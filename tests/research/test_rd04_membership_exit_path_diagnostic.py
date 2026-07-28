"""Behavioural tests for the frozen RD04-D5F membership-exit diagnostic."""

from __future__ import annotations

import pandas as pd
import pytest

from spotbot.research.rd04_membership_exit_path_diagnostic import (
    STATE_ENTRANT,
    STATE_REMOVED,
    STATE_RETAINED,
    MembershipExitPathError,
    build_pit_map,
    contiguous_path,
    displacement_label,
    fold_id_for_time,
    normalized_bars,
    transition_rows,
)


def schedule() -> pd.DataFrame:
    rows = []
    for timestamp, symbols in (
        ("2022-01-03T00:00:00Z", ("AAA",) * 30),
        ("2022-01-10T00:00:00Z", ("BBB",) * 30),
    ):
        rows.extend(
            {
                "rebalance_time": timestamp,
                "canonical_symbol": f"{symbols[0]}{index:02d}",
                "venue_data_eligible": True,
            }
            for index in range(30)
        )
    return pd.DataFrame(rows)


def four_hour_bars() -> pd.DataFrame:
    opened = pd.date_range("2022-01-10T00:00:00Z", periods=42, freq="4h")
    return pd.DataFrame(
        {
            "symbol": ["AAA00"] * len(opened),
            "bar_open_time": opened,
            "bar_close_time": opened + pd.Timedelta(hours=4),
            "open": [100.0] * len(opened),
            "high": [110.0] * len(opened),
            "low": [90.0] * len(opened),
            "close": [105.0] * len(opened),
        }
    )


def test_pit_map_requires_thirty_eligible_monday_members() -> None:
    pit_map = build_pit_map(schedule(), expected_snapshots=2)
    assert len(pit_map) == 2
    broken = schedule().iloc[:-1]
    with pytest.raises(MembershipExitPathError, match="exactly 30"):
        build_pit_map(broken, expected_snapshots=2)


def test_transition_rows_define_exit_without_future_return_information() -> None:
    pit_map = {
        pd.Timestamp("2022-01-03T00:00:00Z"): frozenset({"AAA", "BBB"}),
        pd.Timestamp("2022-01-10T00:00:00Z"): frozenset({"BBB", "CCC"}),
    }
    transitions = transition_rows(pit_map, fixed_symbols=frozenset({"AAA"}))
    assert {(row.state, row.symbol) for row in transitions} == {
        (STATE_REMOVED, "AAA"),
        (STATE_RETAINED, "BBB"),
        (STATE_ENTRANT, "CCC"),
    }
    removal = next(row for row in transitions if row.state == STATE_REMOVED)
    assert removal.fixed_survivor is True
    assert removal.decision_time == pd.Timestamp("2022-01-10T00:00:00Z")


def test_normalized_bars_reject_2025_and_duplicate_rows() -> None:
    frame = four_hour_bars()
    normalized = normalized_bars(frame)
    assert len(normalized) == 42
    duplicate = pd.concat([frame, frame.iloc[[0]]], ignore_index=True)
    with pytest.raises(MembershipExitPathError, match="duplicate"):
        normalized_bars(duplicate)
    future = frame.copy()
    future.loc[0, "bar_open_time"] = "2025-01-01T00:00:00Z"
    with pytest.raises(MembershipExitPathError, match="2025"):
        normalized_bars(future)


def test_contiguous_path_never_imputes_missing_bars() -> None:
    frame = normalized_bars(four_hour_bars())
    start = pd.Timestamp("2022-01-10T00:00:00Z")
    assert (
        contiguous_path(frame, symbol="AAA00", start=start, end=start + pd.Timedelta(weeks=1))
        is not None
    )
    missing = frame.drop(index=4)
    assert (
        contiguous_path(missing, symbol="AAA00", start=start, end=start + pd.Timedelta(weeks=1))
        is None
    )


def test_fold_mapping_is_research_bound_and_deterministic() -> None:
    assert fold_id_for_time(pd.Timestamp("2022-12-26T00:00:00Z")) == "WF01"
    assert fold_id_for_time(pd.Timestamp("2023-01-02T00:00:00Z")) == "WF02"
    assert fold_id_for_time(pd.Timestamp("2024-01-01T00:00:00Z")) == "WF03"
    with pytest.raises(MembershipExitPathError, match="outside"):
        fold_id_for_time(pd.Timestamp("2025-01-01T00:00:00Z"))


def test_predeclared_descriptive_classification_does_not_authorize_treatment() -> None:
    assert (
        displacement_label(
            fixed_post_exit_pnl=100.0,
            gap_share=0.12,
            positive_share_4w=0.5,
        )
        == "REMOVED_SURVIVOR_DISPLACEMENT_MATERIAL"
    )
    assert (
        displacement_label(
            fixed_post_exit_pnl=100.0,
            gap_share=0.09,
            positive_share_4w=1.0,
        )
        == "REMOVED_SURVIVOR_DISPLACEMENT_NOT_EVIDENT"
    )
