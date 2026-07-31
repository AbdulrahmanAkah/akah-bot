from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest

from spotbot.research.rd16d_metrics import (
    build_equity_curve,
    classify_family,
    concentration_row,
    market_regime_from_row,
    performance_metrics,
    replay_admission_rows,
)

START = datetime(2024, 1, 1, tzinfo=UTC)


def hourly_frame(symbol_offset: float = 0.0) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": [START + timedelta(hours=index) for index in range(6)],
            "close": [100.0 + symbol_offset + index for index in range(6)],
        }
    )


def trade_frame() -> pd.DataFrame:
    return pd.DataFrame.from_records(
        [
            {
                "trade_id": "T1",
                "family_id": "FAMILY",
                "symbol": "BTC/USDT",
                "signal_close": START,
                "entry_open_time": START,
                "entry_bar_close": START + timedelta(hours=1),
                "entry_price": 100.0,
                "exit_bar_close": START + timedelta(hours=3),
                "exit_price": 103.0,
                "risk_per_unit": 5.0,
                "risk_budget": 500.0,
                "quantity": 10.0,
                "notional": 1_000.0,
                "gross_pnl": 30.0,
                "fees": 2.03,
                "net_pnl": 27.97,
                "bars_held": 3,
                "exit_reason": "TIME_EXIT",
            }
        ]
    )


def test_market_regime_classification() -> None:
    assert (
        market_regime_from_row(
            {
                "1d_close": 120.0,
                "1d_ema50": 110.0,
                "1d_ema200": 100.0,
                "1w_close": 120.0,
                "1w_ema40": 105.0,
            }
        )
        == "STRONG_BULL"
    )
    assert (
        market_regime_from_row(
            {
                "1d_close": 80.0,
                "1d_ema50": 90.0,
                "1d_ema200": 100.0,
                "1w_close": 85.0,
                "1w_ema40": 95.0,
            }
        )
        == "BEAR"
    )


def test_equity_curve_reconciles_trade_and_costs() -> None:
    timeline = pd.DatetimeIndex([START + timedelta(hours=index) for index in range(6)])
    curve = build_equity_curve(
        trade_frame(),
        hourly_frames={"BTC/USDT": hourly_frame()},
        timeline=timeline,
        cost_multiplier=1.0,
    )
    assert len(curve) == 6
    assert curve.iloc[-1]["equity"] == pytest.approx(100_027.97)
    assert int(curve["open_positions"].max()) == 1
    assert float(curve.iloc[-1]["cumulative_fees"]) == pytest.approx(2.03)


def test_performance_metrics_reports_positive_baseline() -> None:
    timeline = pd.DatetimeIndex([START + timedelta(hours=index) for index in range(6)])
    trades = trade_frame()
    curve = build_equity_curve(
        trades,
        hourly_frames={"BTC/USDT": hourly_frame()},
        timeline=timeline,
    )
    metrics = performance_metrics(curve, trades, cost_multiplier=1.0)
    assert float(metrics["net_return"]) > 0.0
    assert int(metrics["trade_count"]) == 1
    assert metrics["capital_feasible"] is True
    assert metrics["profit_factor"] is None


def test_concentration_detects_top_trade_dependency() -> None:
    trades = pd.DataFrame(
        {
            "net_pnl": [100.0, 10.0, -20.0],
            "symbol": ["BTC/USDT", "ETH/USDT", "BTC/USDT"],
            "entry_year": [2024, 2024, 2024],
        }
    )
    row = concentration_row(trades, family_id="FAMILY")
    assert float(row["top_1_trade_profit_share"]) == pytest.approx(100.0 / 110.0)
    assert row["top_asset"] == "BTC/USDT"
    assert float(row["net_return_without_top_1"]) == pytest.approx(-0.0001)


def test_admission_replay_identifies_same_asset_rejection() -> None:
    base = trade_frame().iloc[0].to_dict()
    second = dict(base)
    second["trade_id"] = ""
    second["signal_close"] = START + timedelta(hours=1)
    second["entry_open_time"] = START + timedelta(hours=1)
    second["entry_bar_close"] = START + timedelta(hours=2)
    second["exit_bar_close"] = START + timedelta(hours=4)
    evaluated = pd.DataFrame.from_records([base, second]).drop(columns=["trade_id"])
    admitted = pd.DataFrame.from_records([base])
    rows = replay_admission_rows(
        evaluated,
        admitted,
        family_id="FAMILY",
    )
    by_reason = {row["admission_reason"]: row for row in rows}
    assert int(by_reason["ADMITTED"]["candidate_count"]) == 1
    assert int(by_reason["REJECTED_SAME_ASSET"]["candidate_count"]) == 1


def test_fixed_classification_does_not_select_winner() -> None:
    metrics: dict[str, object] = {
        "capital_feasible": True,
        "net_return": 0.5,
        "profit_factor": 1.4,
        "maximum_drawdown": 0.2,
        "trade_count": 200,
        "monthly_geometric_return": 0.01,
    }
    cost_2x: dict[str, object] = {
        "net_return": 0.2,
        "profit_factor": 1.1,
    }
    concentration: dict[str, object] = {
        "top_3_trade_profit_share": 0.2,
        "top_asset_profit_share": 0.4,
    }
    yearly = [
        {"return": 0.1, "trade_count": 20},
        {"return": 0.2, "trade_count": 20},
    ]
    result = classify_family(
        metrics,
        cost_2x=cost_2x,
        concentration=concentration,
        yearly_rows=yearly,
        bull_rows=[],
    )
    assert result.classification == "ROBUST_POSITIVE_BASELINE"
    assert result.strategic_objective_met is False
    assert result.gates["monthly_target_24pct_met"] is False
