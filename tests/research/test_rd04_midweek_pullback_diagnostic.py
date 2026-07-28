"""Behavioural tests for the frozen RD04-D5E0 weekly path diagnostic."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest

from spotbot.research.rd04_midweek_pullback_diagnostic import (
    ORIGINAL_TRADE_FIELDS,
    MidweekPullbackError,
    build_weekly_path,
    entry_diagnostics,
    expected_week_opens,
    fold_metrics,
    parse_utc,
    pattern_gate,
    projection_fingerprint,
    validate_four_hour,
    validate_input_trades,
    validate_projection,
    week_start,
    weekday_metrics,
    weekly_low_distribution,
)


def utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def trade(
    *,
    trade_id: str = "T1",
    fold_id: str = "WF01",
    symbol: str = "BTC-USDT",
    entry_time: str = "2022-01-04T04:00:00Z",
    exit_time: str = "2022-01-05T04:00:00Z",
    exit_reason: str = "STOP_EXIT",
) -> dict[str, str]:
    values = {
        "universe_mode": "PIT_UNIVERSE",
        "portfolio_mode": "CONTROL",
        "fold_id": fold_id,
        "trade_id": trade_id,
        "position_id": f"P-{trade_id}",
        "candidate_id": f"C-{trade_id}",
        "symbol": symbol,
        "entry_time": entry_time,
        "exit_time": exit_time,
        "entry_price": "100",
        "exit_price": "101",
        "quantity": "1",
        "gross_pnl": "1",
        "net_pnl": "0.8",
        "return_fraction": "0.008",
        "exit_reason": exit_reason,
        "alignment_tier": "A",
        "holding_hours": "24",
        "mfe": "0.03",
        "mae": "-0.01",
        "natural_reselection_sequence": "0",
        "previous_position_id": "",
    }
    assert tuple(values) == ORIGINAL_TRADE_FIELDS
    return values


def bars(*, symbol: str = "BTC-USDT", start: datetime | None = None) -> pd.DataFrame:
    monday = start or utc("2022-01-03T00:00:00Z")
    rows = []
    for index, opened in enumerate(expected_week_opens(monday)):
        rows.append(
            {
                "symbol": symbol,
                "bar_open_time": opened,
                "bar_close_time": opened + timedelta(hours=4),
                "low": 100.0 + index,
                "close": 200.0 + index,
            }
        )
    return pd.DataFrame(rows)


def test_week_start_and_utc_parsing_are_causal() -> None:
    timestamp = parse_utc("2022-01-09T23:59:59Z")
    assert week_start(timestamp) == utc("2022-01-03T00:00:00Z")
    assert parse_utc("2022-01-03T00:00:00+00:00").tzinfo == UTC


def test_complete_weekly_path_uses_earliest_low_tie_and_friday_close() -> None:
    frame = bars()
    frame.loc[6, "low"] = 1.0
    frame.loc[7, "low"] = 1.0
    path = build_weekly_path(
        validate_four_hour(frame),
        fold_id="WF01",
        symbol="BTC-USDT",
        monday_start=utc("2022-01-03T00:00:00Z"),
    )
    assert path.complete is True
    assert path.observed_bar_count == 42
    assert path.weekly_low_time == utc("2022-01-04T00:00:00Z")
    assert path.weekly_low_weekday == "TUESDAY"
    assert path.friday_close == pytest.approx(229.0)


def test_missing_bar_is_not_a_complete_weekly_path() -> None:
    frame = bars().drop(index=10)
    path = build_weekly_path(
        validate_four_hour(frame),
        fold_id="WF01",
        symbol="BTC-USDT",
        monday_start=utc("2022-01-03T00:00:00Z"),
    )
    assert path.complete is False
    assert path.missing_bar_count == 1
    assert path.weekly_low_time is None


def test_four_hour_boundary_rejects_2025_open_and_post_lock_close() -> None:
    frame = bars()
    frame.loc[0, "bar_open_time"] = "2025-01-01T00:00:00Z"
    with pytest.raises(MidweekPullbackError, match="2025 bar open"):
        validate_four_hour(frame)
    frame = bars()
    frame.loc[0, "bar_close_time"] = "2025-01-01T00:00:01Z"
    with pytest.raises(MidweekPullbackError, match="post-lock close"):
        validate_four_hour(frame)


def test_input_contract_accepts_exact_boundary_end_of_fold_exit() -> None:
    rows = [
        trade(trade_id="A", fold_id="WF01"),
        trade(trade_id="B", fold_id="WF02"),
        trade(
            trade_id="C",
            fold_id="WF03",
            exit_time="2025-01-01T00:00:00Z",
            exit_reason="END_OF_FOLD_EXIT",
        ),
    ]
    validate_input_trades(rows, expected_count=3, expected_boundary_exit_count=1)
    rows[2]["entry_time"] = "2025-01-01T00:00:00Z"
    with pytest.raises(MidweekPullbackError, match="locked boundary"):
        validate_input_trades(rows, expected_count=3, expected_boundary_exit_count=1)


def test_trade_projection_is_immutable_and_tuesday_return_uses_friday_close() -> None:
    source = trade()
    path = build_weekly_path(
        validate_four_hour(bars()),
        fold_id="WF01",
        symbol="BTC-USDT",
        monday_start=utc("2022-01-03T00:00:00Z"),
    )
    rows = entry_diagnostics(
        [source],
        {("WF01", "BTC-USDT", utc("2022-01-03T00:00:00Z")): path},
    )
    validate_projection([source], rows)
    assert projection_fingerprint([source]) == projection_fingerprint(rows)
    assert float(rows[0]["tuesday_to_friday_return"]) == pytest.approx(1.29)
    rows[0]["net_pnl"] = "changed"
    with pytest.raises(MidweekPullbackError, match="changed original field"):
        validate_projection([source], rows)


def test_weekday_metrics_include_all_days() -> None:
    metrics = weekday_metrics(
        [
            {
                **trade(),
                "entry_weekday": "TUESDAY",
            }
        ]
    )
    assert len(metrics) == 7
    assert next(row for row in metrics if row["entry_weekday"] == "MONDAY")["trade_count"] == 0
    assert next(row for row in metrics if row["entry_weekday"] == "TUESDAY")["net_pnl"] == 0.8


def test_pattern_gate_is_strict_and_counts_all_tuesday_signals() -> None:
    distribution = [
        {"weekly_low_weekday": day, "share": 0.0}
        for day in ("MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY")
    ]
    distribution[1]["share"] = 0.5
    distribution[0]["share"] = 0.2
    folds = [
        {
            "tuesday_to_friday_observation_count": 1,
            "tuesday_mean_return_positive": True,
        },
        {
            "tuesday_to_friday_observation_count": 1,
            "tuesday_mean_return_positive": True,
        },
        {
            "tuesday_to_friday_observation_count": 0,
            "tuesday_mean_return_positive": False,
        },
    ]
    entries = [
        {"entry_weekday": "TUESDAY", "tuesday_to_friday_return": "0.1"},
        {"entry_weekday": "TUESDAY", "tuesday_to_friday_return": ""},
        {"entry_weekday": "TUESDAY", "tuesday_to_friday_return": "0.2"},
    ]
    result = pattern_gate(distribution, folds, entries)
    assert result["pattern_supported"] is True
    assert result["tuesday_signal_count"] == 3
    assert result["tuesday_to_friday_observation_count"] == 2


def test_pattern_gate_fails_when_tuesday_does_not_exceed_other_weekday() -> None:
    distribution = [
        {"weekly_low_weekday": day, "share": 0.1}
        for day in ("MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY")
    ]
    distribution[1]["share"] = 0.2
    distribution[2]["share"] = 0.2
    folds = [
        {
            "tuesday_to_friday_observation_count": 1,
            "tuesday_mean_return_positive": True,
        }
        for _ in range(3)
    ]
    entries = [{"entry_weekday": "TUESDAY", "tuesday_to_friday_return": "0.1"}]
    assert pattern_gate(distribution, folds, entries)["pattern_supported"] is False


def test_fold_metrics_reports_each_registered_fold() -> None:
    rows = [
        {"fold_id": "WF01", "entry_weekday": "TUESDAY", "tuesday_to_friday_return": "0.1"},
        {"fold_id": "WF02", "entry_weekday": "TUESDAY", "tuesday_to_friday_return": "-0.1"},
    ]
    metrics = fold_metrics(rows)
    assert [row["fold_id"] for row in metrics] == ["WF01", "WF02", "WF03"]
    assert metrics[0]["tuesday_mean_return_positive"] is True
    assert metrics[1]["tuesday_mean_return_positive"] is False


def test_weekly_low_distribution_ignores_incomplete_paths() -> None:
    complete = build_weekly_path(
        validate_four_hour(bars()),
        fold_id="WF01",
        symbol="BTC-USDT",
        monday_start=utc("2022-01-03T00:00:00Z"),
    )
    incomplete = build_weekly_path(
        validate_four_hour(bars().drop(index=0)),
        fold_id="WF01",
        symbol="BTC-USDT",
        monday_start=utc("2022-01-03T00:00:00Z"),
    )
    distribution = weekly_low_distribution([complete, incomplete])
    assert sum(float(row["share"]) for row in distribution) == pytest.approx(1.0)
