from __future__ import annotations

import pandas as pd

from spotbot.research.rd18_p3e_performance import (
    base_classification,
    concentration_metrics,
    holding_attribution_rows,
    prepare_reporting_trades,
)


def test_prepare_reporting_trades_applies_cost_and_path() -> None:
    bars = pd.DataFrame(
        {
            "timestamp": pd.date_range(
                "2020-01-01T01:00:00Z",
                periods=3,
                freq="1h",
            ),
            "open": [100.0, 105.0, 110.0],
            "high": [110.0, 120.0, 115.0],
            "low": [95.0, 100.0, 108.0],
            "close": [105.0, 110.0, 112.0],
            "volume": [1.0, 1.0, 1.0],
        }
    )
    trades = pd.DataFrame(
        [
            {
                "trade_id": "T1",
                "symbol": "BTC/USDT",
                "pair": "BTC-USDT",
                "signal_close": pd.Timestamp("2020-01-01T00:00:00Z"),
                "entry_open_time": pd.Timestamp("2020-01-01T00:00:00Z"),
                "entry_bar_close": pd.Timestamp("2020-01-01T01:00:00Z"),
                "exit_bar_close": pd.Timestamp("2020-01-01T03:00:00Z"),
                "entry_price": 100.0,
                "exit_price": 112.0,
                "risk_per_unit": 10.0,
                "risk_budget": 500.0,
                "quantity": 5.0,
                "gross_pnl": 60.0,
                "fees": 1.06,
                "net_pnl": 58.94,
                "bars_held": 3,
                "market_regime": "STRONG_BULL",
                "volatility_regime": "NORMAL_VOLATILITY",
            }
        ]
    )
    result = prepare_reporting_trades(
        trades,
        hourly_frames={"BTC/USDT": bars},
        cost_multiplier=2.0,
    )
    assert result.iloc[0]["mfe_r"] == 2.0
    assert result.iloc[0]["mae_r"] == -0.5
    assert result.iloc[0]["fees"] == 2.12
    assert result.iloc[0]["net_pnl"] == 57.88
    assert result.iloc[0]["entry_year"] == 2020


def test_holding_buckets_cover_96_hours() -> None:
    trades = pd.DataFrame(
        {
            "bars_held": [1, 48, 49, 72, 73, 96],
            "net_pnl": [1.0] * 6,
            "risk_budget": [1.0] * 6,
        }
    )
    rows = holding_attribution_rows(
        trades,
        universe_id="C2",
        cost_multiplier=1.0,
    )
    assert sum(row["trade_count"] for row in rows) == 6
    assert rows[-1]["holding_bucket"] == "73_96_BARS"


def test_concentration_without_top_trade() -> None:
    trades = pd.DataFrame(
        {
            "net_pnl": [100.0, 50.0, -20.0],
            "symbol": ["A", "B", "C"],
            "entry_year": [2020, 2021, 2022],
        }
    )
    result = concentration_metrics(
        trades,
        universe_id="C2",
        cost_multiplier=1.0,
    )
    assert result["top_1_trade_profit_share"] == 2.0 / 3.0
    assert result["net_return_without_top_1"] == 0.0003


def test_base_classification_defers_sensitivity() -> None:
    class Run:
        def __init__(self, monthly: float) -> None:
            self.metrics = {"monthly_geometric_return": monthly}

    runs = {(universe, cost): Run(0.25) for universe in ("C2", "D2", "E2") for cost in (1.0, 2.0)}
    result = base_classification(
        universe_gates=[
            {"passed": True},
            {"passed": True},
            {"passed": True},
        ],
        cross_universe={"passed": True},
        runs=runs,
        registry={"strategic_objective": {"worst_universe_geometric_monthly_return_minimum": 0.24}},
    )
    assert result["classification"] == ("BASE_ROBUSTNESS_PASS_SENSITIVITY_PENDING")
    assert result["strategic_objective_met"] is True
    assert result["final_advancement_decision_deferred"] is True
