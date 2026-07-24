from datetime import UTC, datetime

import pytest

from spotbot.research.daily_history import (
    DailyHistoryDataError,
    backward_page_end_at_seconds,
    deduplicate_ccxt_ohlcv_rows,
)

UTC = UTC


def test_backward_end_at_stays_before_locked_boundary() -> None:
    result = backward_page_end_at_seconds(
        datetime(
            2025,
            1,
            1,
            tzinfo=UTC,
        )
    )

    expected = int(
        datetime(
            2024,
            12,
            31,
            23,
            59,
            59,
            tzinfo=UTC,
        ).timestamp()
    )

    assert result == expected


def test_identical_rows_are_deduplicated() -> None:
    row = [
        1_700_000_000_000,
        10.0,
        12.0,
        9.0,
        11.0,
        100.0,
    ]

    result = deduplicate_ccxt_ohlcv_rows(
        [
            row,
            list(row),
        ]
    )

    assert result == [row]


def test_conflicting_duplicate_rows_are_rejected() -> None:
    first = [
        1_700_000_000_000,
        10.0,
        12.0,
        9.0,
        11.0,
        100.0,
    ]

    second = [
        1_700_000_000_000,
        10.0,
        13.0,
        9.0,
        11.0,
        100.0,
    ]

    with pytest.raises(
        DailyHistoryDataError,
        match="Conflicting",
    ):
        deduplicate_ccxt_ohlcv_rows(
            [
                first,
                second,
            ]
        )
