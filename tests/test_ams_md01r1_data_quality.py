from __future__ import annotations

import pandas as pd
import pytest

from spotbot.research.ams_md01r1_universe import (
    MD01R1Error,
    assert_research_boundary,
)


def _frame(open_time: str, close_time: str) -> pd.DataFrame:
    return pd.DataFrame(
        {"bar_open_time": [open_time], "bar_close_time": [close_time]}
    )


def test_last_2024_four_hour_candle_is_allowed() -> None:
    assert_research_boundary(
        _frame("2024-12-31T20:00:00Z", "2025-01-01T00:00:00Z")
    )


@pytest.mark.parametrize(
    ("open_time", "close_time"),
    [
        ("2025-01-01T00:00:00Z", "2025-01-01T04:00:00Z"),
        ("2024-12-31T20:00:00Z", "2025-01-01T00:00:01Z"),
    ],
)
def test_locked_candles_are_rejected(open_time: str, close_time: str) -> None:
    with pytest.raises(MD01R1Error):
        assert_research_boundary(_frame(open_time, close_time))
