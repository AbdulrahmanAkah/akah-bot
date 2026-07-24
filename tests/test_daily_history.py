from datetime import UTC, datetime

import pandas as pd
import pytest

from spotbot.research.daily_history import (
    DailyHistoryDataError,
    DailyHistoryPolicy,
    normalize_ccxt_daily_ohlcv,
    safe_symbol_filename,
    summarize_daily_history,
    validate_daily_history_frame,
)

UTC = UTC


def policy() -> DailyHistoryPolicy:
    return DailyHistoryPolicy(
        history_start_open=datetime(
            2021,
            1,
            1,
            tzinfo=UTC,
        ),
        research_start_close=datetime(
            2021,
            7,
            20,
            tzinfo=UTC,
        ),
        research_end_close_exclusive=(
            datetime(
                2025,
                1,
                1,
                tzinfo=UTC,
            )
        ),
    )


def test_ccxt_open_timestamp_becomes_close_timestamp() -> None:
    rows = [
        [
            int(
                pd.Timestamp(
                    "2021-01-01T00:00:00Z"
                ).timestamp()
                * 1000
            ),
            10.0,
            12.0,
            9.0,
            11.0,
            100.0,
        ]
    ]

    frame = normalize_ccxt_daily_ohlcv(
        rows,
        policy=policy(),
    )

    assert frame.iloc[0][
        "timestamp"
    ] == pd.Timestamp(
        "2021-01-02T00:00:00Z"
    )


def test_invalid_ohlc_is_rejected() -> None:
    rows = [
        [
            int(
                pd.Timestamp(
                    "2021-01-01T00:00:00Z"
                ).timestamp()
                * 1000
            ),
            10.0,
            9.0,
            8.0,
            11.0,
            100.0,
        ]
    ]

    with pytest.raises(
        DailyHistoryDataError,
        match="High price",
    ):
        normalize_ccxt_daily_ohlcv(
            rows,
            policy=policy(),
        )


def test_locked_timestamp_is_rejected() -> None:
    frame = pd.DataFrame(
        {
            "timestamp": [
                pd.Timestamp(
                    "2025-01-01T00:00:00Z"
                )
            ],
            "open": [10.0],
            "high": [11.0],
            "low": [9.0],
            "close": [10.5],
            "volume": [100.0],
        }
    )

    with pytest.raises(
        DailyHistoryDataError,
        match="locked test",
    ):
        validate_daily_history_frame(
            frame,
            policy=policy(),
        )


def test_duplicate_daily_timestamp_is_rejected() -> None:
    frame = pd.DataFrame(
        {
            "timestamp": [
                pd.Timestamp(
                    "2022-01-01T00:00:00Z"
                ),
                pd.Timestamp(
                    "2022-01-01T00:00:00Z"
                ),
            ],
            "open": [10.0, 10.0],
            "high": [11.0, 11.0],
            "low": [9.0, 9.0],
            "close": [10.5, 10.5],
            "volume": [100.0, 100.0],
        }
    )

    with pytest.raises(
        DailyHistoryDataError,
        match="duplicate",
    ):
        validate_daily_history_frame(
            frame,
            policy=policy(),
        )


def test_summary_detects_gap_and_listing_age() -> None:
    frame = pd.DataFrame(
        {
            "timestamp": [
                pd.Timestamp(
                    "2021-01-01T00:00:00Z"
                ),
                pd.Timestamp(
                    "2021-01-03T00:00:00Z"
                ),
            ],
            "open": [10.0, 11.0],
            "high": [12.0, 13.0],
            "low": [9.0, 10.0],
            "close": [11.0, 12.0],
            "volume": [100.0, 110.0],
        }
    )

    summary = summarize_daily_history(
        symbol="BTC/USDT",
        frame=frame,
        policy=policy(),
    )

    assert summary[
        "missing_daily_candle_count"
    ] == 1

    assert summary[
        "eligible_at_research_start_proxy"
    ] is True

    assert summary[
        "coverage_status"
    ] == "RESEARCH_COVERAGE_WITH_GAPS"


def test_empty_history_is_reported() -> None:
    frame = pd.DataFrame(
        columns=[
            "timestamp",
            "open",
            "high",
            "low",
            "close",
            "volume",
        ]
    )

    summary = summarize_daily_history(
        symbol="NEW/USDT",
        frame=frame,
        policy=policy(),
    )

    assert summary[
        "history_present_in_research"
    ] is False

    assert summary[
        "coverage_status"
    ] == "NO_PRE_2025_HISTORY"


def test_symbol_filename_is_deterministic() -> None:
    assert safe_symbol_filename(
        "btc/usdt"
    ) == "BTC_USDT"