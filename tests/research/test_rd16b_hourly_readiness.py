from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

from spotbot.data.aggregation import AggregationDataError
from spotbot.research.rd16b_common import (
    load_assets_configuration,
    verify_official_configuration,
)
from spotbot.research.rd16b_hourly_readiness import (
    analyze_hourly_frame,
)


def hourly_frame(
    start: datetime,
    count: int,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for index in range(1, count + 1):
        close_time = start + timedelta(hours=index)
        price = 100.0 + index / 10
        rows.append(
            {
                "timestamp": close_time,
                "open": price,
                "high": price + 1.0,
                "low": price - 1.0,
                "close": price + 0.25,
                "volume": 1_000.0 + index,
            }
        )
    return pd.DataFrame.from_records(rows)


def test_complete_hourly_history_passes_readiness() -> None:
    start = datetime(2024, 1, 1, tzinfo=UTC)
    source = hourly_frame(start, 24 * 14)
    cutoff = datetime(2024, 1, 15, tzinfo=UTC)

    result = analyze_hourly_frame(
        symbol="BTC/USDT",
        source=source,
        cutoff=cutoff,
    )
    readiness = result["readiness"]
    assert isinstance(readiness, dict)
    assert readiness["status"] == "PASS"
    assert readiness["missing_intervals"] == 0
    assert readiness["future_context_violations"] == 0
    assert readiness["stale_context_violations"] == 0
    assert readiness["cutoff_reached"] is True

    aggregation_rows = result["aggregation_rows"]
    assert isinstance(aggregation_rows, list)
    assert {row["target_timeframe"] for row in aggregation_rows} == {"4h", "1d", "1w"}
    assert all(row["dropped_gap_groups"] == 0 for row in aggregation_rows)


def test_missing_hour_blocks_readiness() -> None:
    start = datetime(2024, 1, 1, tzinfo=UTC)
    source = hourly_frame(start, 24 * 14)
    source = source.drop(index=100).reset_index(drop=True)
    cutoff = datetime(2024, 1, 15, tzinfo=UTC)

    result = analyze_hourly_frame(
        symbol="BTC/USDT",
        source=source,
        cutoff=cutoff,
    )
    readiness = result["readiness"]
    assert isinstance(readiness, dict)
    assert readiness["status"] == "FAIL"
    assert readiness["missing_intervals"] == 1

    aggregation_rows = result["aggregation_rows"]
    assert isinstance(aggregation_rows, list)
    assert any(int(row["dropped_gap_groups"]) > 0 for row in aggregation_rows)


def test_post_cutoff_candle_is_rejected() -> None:
    start = datetime(2024, 1, 1, tzinfo=UTC)
    source = hourly_frame(start, 24 * 14 + 1)
    cutoff = datetime(2024, 1, 15, tzinfo=UTC)

    with pytest.raises(
        AggregationDataError,
        match="beyond the cutoff",
    ):
        analyze_hourly_frame(
            symbol="BTC/USDT",
            source=source,
            cutoff=cutoff,
        )


def test_minimum_coverage_gate_blocks_short_history() -> None:
    start = datetime(2024, 1, 1, tzinfo=UTC)
    source = hourly_frame(start, 24 * 14)
    cutoff = datetime(2024, 1, 15, tzinfo=UTC)

    result = analyze_hourly_frame(
        symbol="BTC/USDT",
        source=source,
        cutoff=cutoff,
        minimum_coverage_days=1_000.0,
    )
    readiness = result["readiness"]
    assert isinstance(readiness, dict)
    assert readiness["status"] == "FAIL"
    assert readiness["minimum_coverage_met"] is False


def test_assets_configuration_matches_protocol(
    tmp_path: Path,
) -> None:
    path = tmp_path / "assets.yaml"
    path.write_text(
        """exchange: kucoin
quote_currency: USDT
symbols:
  - BTC/USDT
  - ETH/USDT
  - SOL/USDT
  - LINK/USDT
  - AVAX/USDT
  - NEAR/USDT
timeframes:
  regime: 1d
  structure: 4h
  signal: 1h
""",
        encoding="utf-8",
    )
    exchange, symbols, timeframes = load_assets_configuration(path)
    verify_official_configuration(
        exchange=exchange,
        symbols=symbols,
        timeframes=timeframes,
    )
    assert exchange == "kucoin"
    assert symbols[-1] == "NEAR/USDT"
