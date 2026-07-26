from __future__ import annotations

import pandas as pd
import pytest

from spotbot.research.ams_v5_native_engine import (
    V5NativeError,
    assert_boundary,
    drawdown_multiplier,
    risk_multiplier,
)


def test_research_boundary_allows_last_owned_2024_bar() -> None:
    assert_boundary(
        pd.DataFrame(
            {
                "bar_open_time": [pd.Timestamp("2024-12-31T20:00:00Z")],
                "bar_close_time": [pd.Timestamp("2025-01-01T00:00:00Z")],
            }
        )
    )


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("bar_open_time", "2025-01-01T00:00:00Z"),
        ("bar_close_time", "2025-01-01T04:00:00Z"),
    ],
)
def test_research_boundary_rejects_locked_bars(column: str, value: str) -> None:
    frame = pd.DataFrame(
        {
            "bar_open_time": [pd.Timestamp("2024-12-31T20:00:00Z")],
            "bar_close_time": [pd.Timestamp("2025-01-01T00:00:00Z")],
        }
    )
    frame.loc[0, column] = pd.Timestamp(value)
    with pytest.raises(V5NativeError, match="locked"):
        assert_boundary(frame)


def test_risk_and_drawdown_scaling_contracts() -> None:
    assert risk_multiplier(50) == 0.7
    assert risk_multiplier(60) == 0.9
    assert risk_multiplier(70) == 1.0
    assert risk_multiplier(80) == 1.2
    assert drawdown_multiplier(0.25) == 0
