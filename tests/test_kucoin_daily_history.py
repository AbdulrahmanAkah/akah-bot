from datetime import UTC, datetime
from itertools import pairwise

import pandas as pd
import pytest

from spotbot.research.daily_history import (
    DailyHistoryDataError,
    DailyHistoryPolicy,
)
from spotbot.research.kucoin_daily_history import (
    build_kucoin_daily_windows,
    merge_kucoin_daily_pages,
    parse_kucoin_spot_daily_rows,
    summarize_direct_kucoin_history,
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
            1,
            7,
            tzinfo=UTC,
        ),
        research_end_close_exclusive=(
            datetime(
                2021,
                1,
                12,
                tzinfo=UTC,
            )
        ),
        minimum_listing_age_days=2,
    )


def raw_row(
    timestamp: str,
    *,
    open_price: str = "10",
    close_price: str = "11",
    high_price: str = "12",
    low_price: str = "9",
    base_volume: str = "100",
    quote_volume: str = "1050",
) -> list[object]:
    return [
        str(
            int(
                pd.Timestamp(
                    timestamp
                ).timestamp()
            )
        ),
        open_price,
        close_price,
        high_price,
        low_price,
        base_volume,
        quote_volume,
    ]


def test_windows_are_contiguous_and_locked_safe() -> None:
    windows = build_kucoin_daily_windows(
        policy=policy(),
        maximum_calendar_days=3,
    )

    assert windows[0].start_open == datetime(
        2021,
        1,
        1,
        tzinfo=UTC,
    )

    assert (
        windows[-1].end_open_exclusive
        == datetime(
            2021,
            1,
            11,
            tzinfo=UTC,
        )
    )

    for previous, current in pairwise(windows):
        assert (
            previous.end_open_exclusive
            == current.start_open
        )


def test_raw_kucoin_field_order_is_normalized() -> None:
    frame = parse_kucoin_spot_daily_rows(
        [
            raw_row(
                "2021-01-01T00:00:00Z"
            )
        ],
        policy=policy(),
    )

    row = frame.iloc[0]

    assert row["timestamp"] == pd.Timestamp(
        "2021-01-02T00:00:00Z"
    )

    assert row["open"] == 10.0
    assert row["close"] == 11.0
    assert row["high"] == 12.0
    assert row["low"] == 9.0
    assert row["volume"] == 100.0
    assert row["quote_volume"] == 1050.0


def test_locked_raw_candle_is_rejected() -> None:
    with pytest.raises(
        DailyHistoryDataError,
        match="outside",
    ):
        parse_kucoin_spot_daily_rows(
            [
                raw_row(
                    "2021-01-11T00:00:00Z"
                )
            ],
            policy=policy(),
        )


def test_conflicting_raw_duplicate_is_rejected() -> None:
    with pytest.raises(
        DailyHistoryDataError,
        match="Conflicting",
    ):
        parse_kucoin_spot_daily_rows(
            [
                raw_row(
                    "2021-01-01T00:00:00Z"
                ),
                raw_row(
                    "2021-01-01T00:00:00Z",
                    close_price="11.5",
                ),
            ],
            policy=policy(),
        )


def test_pages_are_sorted_and_merged() -> None:
    first = parse_kucoin_spot_daily_rows(
        [
            raw_row(
                "2021-01-02T00:00:00Z"
            )
        ],
        policy=policy(),
    )

    second = parse_kucoin_spot_daily_rows(
        [
            raw_row(
                "2021-01-01T00:00:00Z"
            )
        ],
        policy=policy(),
    )

    result = merge_kucoin_daily_pages(
        [
            first,
            second,
        ],
        policy=policy(),
    )

    assert result[
        "timestamp"
    ].tolist() == [
        pd.Timestamp(
            "2021-01-02T00:00:00Z"
        ),
        pd.Timestamp(
            "2021-01-03T00:00:00Z"
        ),
    ]


def test_summary_detects_start_eligibility() -> None:
    frame = parse_kucoin_spot_daily_rows(
        [
            raw_row(
                "2021-01-01T00:00:00Z"
            ),
            raw_row(
                "2021-01-02T00:00:00Z"
            ),
            raw_row(
                "2021-01-10T00:00:00Z"
            ),
        ],
        policy=policy(),
    )

    summary = (
        summarize_direct_kucoin_history(
            symbol="BTC/USDT",
            frame=frame,
            policy=policy(),
        )
    )

    assert summary[
        "eligible_at_research_start_proxy"
    ] is True

    assert summary[
        "reaches_research_end"
    ] is True

    assert summary[
        "quote_volume_source"
    ] == "KUCOIN_REPORTED_TURNOVER"