"""Tests for RD19-P2C frozen discovery execution helpers."""

from __future__ import annotations

import pandas as pd
import pytest

from spotbot.research.rd19_p2c_discovery import (
    MembershipIndex,
    P2CExecutionError,
    maximum_drawdown,
    profit_factor,
    top_trade_share,
)


def test_profit_factor_and_drawdown() -> None:
    assert profit_factor(pd.Series([10.0, -5.0, 5.0])) == pytest.approx(3.0)
    assert maximum_drawdown(pd.Series([100.0, 120.0, 90.0, 110.0])) == pytest.approx(0.25)


def test_top_trade_share() -> None:
    trades = pd.DataFrame({"net_pnl": [10.0, 5.0, -3.0, 2.0]})
    assert top_trade_share(trades, count=2) == pytest.approx(15.0 / 17.0)


def test_membership_index_is_point_in_time() -> None:
    frame = pd.DataFrame(
        {
            "universe_id": ["C2"] * 12,
            "decision_time": (["2020-01-01T00:00:00Z"] * 6 + ["2020-02-01T00:00:00Z"] * 6),
            "effective_end": (["2020-02-01T00:00:00Z"] * 6 + ["2020-03-01T00:00:00Z"] * 6),
            "effective_pair": [
                "A",
                "B",
                "C",
                "D",
                "E",
                "F",
                "G",
                "H",
                "I",
                "J",
                "K",
                "L",
            ],
            "effective_rank": [1, 2, 3, 4, 5, 6] * 2,
        }
    )
    index = MembershipIndex(frame)
    assert index.members_at(
        "C2",
        pd.Timestamp("2020-01-15T00:00:00Z"),
    ) == ("A", "B", "C", "D", "E", "F")
    assert index.members_at(
        "C2",
        pd.Timestamp("2020-02-15T00:00:00Z"),
    ) == ("G", "H", "I", "J", "K", "L")


def test_membership_width_drift_rejected() -> None:
    frame = pd.DataFrame(
        {
            "universe_id": ["C2"] * 5,
            "decision_time": ["2020-01-01T00:00:00Z"] * 5,
            "effective_end": ["2020-02-01T00:00:00Z"] * 5,
            "effective_pair": ["A", "B", "C", "D", "E"],
            "effective_rank": [1, 2, 3, 4, 5],
        }
    )
    with pytest.raises(P2CExecutionError, match="membership width"):
        MembershipIndex(frame)
