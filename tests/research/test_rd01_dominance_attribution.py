from __future__ import annotations

import pandas as pd
import pytest

from spotbot.research.rd01_dominance_attribution import (
    daily_attribution_rows,
    return_statistics,
    stability_rows,
    tag_daily_series,
    trade_attribution_rows,
)


def dominance_frame() -> pd.DataFrame:
    days = pd.date_range(
        "2021-01-01T00:00:00Z",
        periods=160,
        freq="1D",
    )
    frame = pd.DataFrame(
        {
            "day": days,
            "available_at": days + pd.Timedelta(days=1),
            "btc_dominance_pct": 50.0,
            "eth_dominance_pct": 20.0,
            "stablecoin_dominance_pct": 10.0,
            "altcoin_share_pct": 50.0,
        }
    )

    for window in (7, 28, 84):
        btc = pd.Series(
            [-1.0] * 80 + [1.0] * 80,
            dtype=float,
        )
        stable = pd.Series(
            [-1.0] * 80 + [1.0] * 80,
            dtype=float,
        )
        frame[f"btc_dominance_change_{window}d_pp"] = btc
        frame[f"stablecoin_dominance_change_{window}d_pp"] = stable

    return frame


def daily_frame() -> pd.DataFrame:
    timestamps = pd.date_range(
        "2021-02-01T00:00:00Z",
        periods=100,
        freq="1D",
    )
    fold_ids = ["WF01"] * 50 + ["WF02"] * 50
    values = pd.Series(
        [0.01, -0.005] * 50,
        dtype=float,
    )
    return pd.DataFrame(
        {
            "fold_id": fold_ids,
            "timestamp": timestamps,
            "m05_daily_return": values,
            "btc_daily_return": values * 0.8,
            "equal_weight_daily_return": values * 0.7,
            "exposure_matched_equal_weight_return": values * 0.6,
            "volatility_matched_equal_weight_return": values * 0.5,
            "volatility_matched_btc_return": values * 0.4,
        }
    )


def tagged_trades() -> pd.DataFrame:
    rows = []

    for fold_id in ("WF01", "WF02", "WF03"):
        for index in range(4):
            rows.append(
                {
                    "rd01_fold_id": fold_id,
                    "entry_dominance_quadrant": ("BTC_DOWN_STABLE_DOWN"),
                    "net_pnl": 10.0 - index,
                    "return_fraction": 0.10 - index * 0.01,
                    "mfe": 0.15,
                    "mae": -0.04,
                    "holding_hours": 168.0,
                }
            )

    return pd.DataFrame(rows)


def test_return_statistics_are_deterministic() -> None:
    metrics = return_statistics(pd.Series([0.10, -0.05, 0.02]))

    assert metrics["observations"] == 3
    assert metrics["compounded_return"] > 0.0
    assert metrics["maximum_drawdown"] >= 0.0
    assert metrics["annualized_volatility"] is not None


def test_daily_attribution_includes_fold_and_aggregate_beta() -> None:
    tagged = tag_daily_series(
        daily_frame(),
        dominance_frame(),
    )
    rows = daily_attribution_rows(
        tagged,
        minimum_observations=5,
    )

    assert rows
    assert {row["fold_id"] for row in rows}.issuperset({"AGGREGATE", "WF01", "WF02"})
    assert all("beta_vs_btc" in row for row in rows)
    assert all("metrics" in row for row in rows)


def test_trade_attribution_reports_expectancy_and_mfe_mae() -> None:
    rows = trade_attribution_rows(
        tagged_trades(),
        minimum_trades=3,
    )

    aggregate = next(row for row in rows if row["fold_id"] == "AGGREGATE")
    assert aggregate["trade_count"] == 12
    assert aggregate["mean_net_pnl"] > 0.0
    assert aggregate["mean_mfe"] == pytest.approx(0.15)
    assert aggregate["mean_mae"] == pytest.approx(-0.04)


def test_stability_requires_multiple_valid_folds() -> None:
    daily_rows = [
        {
            "fold_id": fold,
            "dominance_quadrant": "Q",
            "status": "VALID",
            "m05_minus_exposure_matched_return": -0.1,
        }
        for fold in ("WF01", "WF02", "WF03")
    ]
    trade_rows = [
        {
            "fold_id": fold,
            "dominance_quadrant": "Q",
            "status": "VALID",
            "mean_net_pnl": -5.0,
        }
        for fold in ("WF01", "WF02", "WF03")
    ]

    rows = stability_rows(daily_rows, trade_rows)

    assert rows[0]["daily_excess_sign_consistent"]
    assert rows[0]["trade_expectancy_sign_consistent"]
    assert rows[0]["daily_excess_negative_folds"] == 3
    assert rows[0]["trade_expectancy_negative_folds"] == 3
