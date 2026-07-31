from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd

from spotbot.data.aggregation import aggregate_completed_ohlcv


def hourly_frame(
    closes: list[datetime],
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for index, timestamp in enumerate(closes):
        open_price = 100.0 + index
        rows.append(
            {
                "timestamp": timestamp,
                "open": open_price,
                "high": open_price + 3.0,
                "low": open_price - 2.0,
                "close": open_price + 1.0,
                "volume": 10.0 + index,
            }
        )
    return pd.DataFrame.from_records(rows)


def consecutive_closes(
    start: datetime,
    count: int,
) -> list[datetime]:
    return [start + timedelta(hours=index) for index in range(1, count + 1)]


def test_four_hour_aggregation_uses_exact_children() -> None:
    start = datetime(2024, 1, 1, tzinfo=UTC)
    source = hourly_frame(consecutive_closes(start, 8))
    result = aggregate_completed_ohlcv(
        source,
        symbol="BTC/USDT",
        source_timeframe="1h",
        target_timeframe="4h",
        cutoff=pd.Timestamp("2024-01-01T08:00:00Z"),
    )

    assert len(result.frame) == 2
    first = result.frame.iloc[0]
    assert first["timestamp"] == pd.Timestamp("2024-01-01T04:00:00Z")
    assert first["open"] == 100.0
    assert first["high"] == 106.0
    assert first["low"] == 98.0
    assert first["close"] == 104.0
    assert first["volume"] == 46.0
    assert result.audit.required_children == 4
    assert result.audit.dropped_gap_groups == 0


def test_missing_child_is_rejected_not_filled() -> None:
    start = datetime(2024, 1, 1, tzinfo=UTC)
    closes = consecutive_closes(start, 12)
    del closes[5]
    source = hourly_frame(closes)
    result = aggregate_completed_ohlcv(
        source,
        symbol="BTC/USDT",
        source_timeframe="1h",
        target_timeframe="4h",
        cutoff=pd.Timestamp("2024-01-01T12:00:00Z"),
    )

    assert list(result.frame["timestamp"]) == [
        pd.Timestamp("2024-01-01T04:00:00Z"),
        pd.Timestamp("2024-01-01T12:00:00Z"),
    ]
    assert result.audit.source_missing_intervals == 1
    assert result.audit.dropped_gap_groups == 1
    assert result.audit.accepted_groups == 2


def test_partial_edge_group_is_rejected() -> None:
    start = datetime(
        2024,
        1,
        1,
        1,
        tzinfo=UTC,
    )
    source = hourly_frame(consecutive_closes(start, 7))
    result = aggregate_completed_ohlcv(
        source,
        symbol="BTC/USDT",
        source_timeframe="1h",
        target_timeframe="4h",
        cutoff=pd.Timestamp("2024-01-01T08:00:00Z"),
    )

    assert len(result.frame) == 1
    assert result.frame.iloc[0]["timestamp"] == (pd.Timestamp("2024-01-01T08:00:00Z"))
    assert result.audit.dropped_edge_groups == 1


def test_daily_and_weekly_boundaries_are_utc() -> None:
    monday = datetime(2024, 1, 1, tzinfo=UTC)
    source = hourly_frame(consecutive_closes(monday, 168))
    daily = aggregate_completed_ohlcv(
        source,
        symbol="BTC/USDT",
        source_timeframe="1h",
        target_timeframe="1d",
        cutoff=pd.Timestamp("2024-01-08T00:00:00Z"),
    )
    weekly = aggregate_completed_ohlcv(
        source,
        symbol="BTC/USDT",
        source_timeframe="1h",
        target_timeframe="1w",
        cutoff=pd.Timestamp("2024-01-08T00:00:00Z"),
    )

    assert len(daily.frame) == 7
    assert daily.frame.iloc[0]["timestamp"] == (pd.Timestamp("2024-01-02T00:00:00Z"))
    assert len(weekly.frame) == 1
    assert weekly.frame.iloc[0]["timestamp"] == (pd.Timestamp("2024-01-08T00:00:00Z"))
    assert weekly.audit.required_children == 168
