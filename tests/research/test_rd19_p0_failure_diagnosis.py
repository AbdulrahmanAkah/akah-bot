"""Tests for RD19-P0 failure diagnosis."""

from __future__ import annotations

import pandas as pd
import pytest

from spotbot.research.rd19_p0_failure_diagnosis import (
    grouped_attribution,
    holding_attribution,
    prepare_trades,
    profit_factor,
    tail_concentration,
)


def sample_trades() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "pair": ["AAA-USDT", "BBB-USDT", "AAA-USDT"],
            "signal_close": [
                "2024-01-01T00:00:00Z",
                "2024-01-02T00:00:00Z",
                "2024-01-03T00:00:00Z",
            ],
            "net_pnl": [100.0, -50.0, 25.0],
            "gross_pnl": [110.0, -40.0, 30.0],
            "risk_budget": [100.0, 100.0, 100.0],
            "bars_held": [4, 10, 80],
            "engine_id": ["TREND", "COMPRESSION", "TREND"],
            "market_regime": ["BULL", "SIDEWAYS", "BULL"],
            "volatility_regime": ["NORMAL", "LOW", "NORMAL"],
            "exit_reason": ["TIME", "STOP", "TRAIL"],
        }
    )


def test_profit_factor() -> None:
    values = pd.Series([100.0, -50.0, 25.0])
    assert profit_factor(values) == pytest.approx(2.5)


def test_prepare_and_grouped_attribution() -> None:
    trades = prepare_trades(
        sample_trades(),
        universe_id="C2",
        cost_multiplier=1.0,
    )
    rows = grouped_attribution(
        trades,
        universe_id="C2",
        cost_multiplier=1.0,
        group_column="engine_id",
        output_column="engine_id",
    )
    assert len(rows) == 2
    trend = next(row for row in rows if row["engine_id"] == "TREND")
    assert trend["trade_count"] == 2
    assert trend["net_pnl"] == pytest.approx(125.0)


def test_holding_buckets_cover_all_trades() -> None:
    trades = prepare_trades(
        sample_trades(),
        universe_id="C2",
        cost_multiplier=1.0,
    )
    rows = holding_attribution(
        trades,
        universe_id="C2",
        cost_multiplier=1.0,
    )
    assert sum(int(row["trade_count"]) for row in rows) == 3


def test_tail_concentration_is_reported() -> None:
    trades = prepare_trades(
        sample_trades(),
        universe_id="C2",
        cost_multiplier=1.0,
    )
    rows = tail_concentration(
        trades,
        universe_id="C2",
        cost_multiplier=1.0,
    )
    scopes = {str(row["tail_scope"]) for row in rows}
    assert {"TOP_1_TRADES", "TOP_ASSET", "TOP_YEAR"}.issubset(scopes)


def test_post_2024_is_rejected() -> None:
    raw = sample_trades()
    raw.loc[0, "signal_close"] = "2025-01-01T00:00:00Z"
    with pytest.raises(Exception, match="post-2024"):
        prepare_trades(
            raw,
            universe_id="C2",
            cost_multiplier=1.0,
        )
