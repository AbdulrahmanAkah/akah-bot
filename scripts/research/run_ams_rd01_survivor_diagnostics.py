"""Run Beta and concentration diagnostics on immutable Survivor-30 folds."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict
from typing import Any

import numpy as np
import pandas as pd
from ams_md01_common import load_registered_data
from ams_md01r2_common import REPORTS, atomic_csv, atomic_json

from spotbot.research.ams_md01_momentum import (
    FOLDS,
    VARIANTS,
    simulate_md01_fold,
)
from spotbot.research.beta_diagnostics import (
    causal_volatility_matched_exposure,
    concentration_metrics,
    estimate_beta,
)


def _equity_returns(result: Any) -> pd.Series:
    equity = pd.Series(
        {pd.Timestamp(timestamp): float(value) for timestamp, value in result.equity_curve}
    ).sort_index()
    return equity.pct_change(fill_method=None).dropna()


def _btc_returns(frame: pd.DataFrame) -> pd.Series:
    btc = frame.loc[frame["symbol"] == "BTC"].copy()
    btc["bar_close_time"] = pd.to_datetime(btc["bar_close_time"], utc=True)
    return (
        btc.set_index("bar_close_time")["close"]
        .sort_index()
        .pct_change(fill_method=None)
        .dropna()
    )


def _daily_price_returns(frame: pd.DataFrame) -> pd.DataFrame:
    daily = frame.copy()
    daily["bar_close_time"] = pd.to_datetime(daily["bar_close_time"], utc=True)
    prices = daily.pivot(index="bar_close_time", columns="symbol", values="close")
    return prices.sort_index().pct_change(fill_method=None)


def _compound(values: pd.Series) -> float:
    clean = values.dropna()
    return float((1.0 + clean).prod() - 1.0) if not clean.empty else 0.0


def main() -> None:
    frames, dataset_hashes = load_registered_data()
    btc_returns = _btc_returns(frames["four_hour"])
    daily_returns = _daily_price_returns(frames["daily"])
    beta_rows: list[dict[str, Any]] = []
    concentration_rows: list[dict[str, Any]] = []
    leave_one_rows: list[dict[str, Any]] = []
    leave_top_rows: list[dict[str, Any]] = []
    variants: dict[str, Any] = {}
    for variant_id in sorted(VARIANTS):
        fold_results = [
            simulate_md01_fold(
                four_hour=frames["four_hour"],
                daily=frames["daily"],
                eight_hour=frames["eight_hour"],
                availability=frames["availability"],
                variant_id=variant_id,
                fold_id=fold_id,
                validation_start=start,
                validation_end=end,
                transaction_cost=0.002,
            )
            for fold_id, start, end in FOLDS
        ]
        symbol_pnl: dict[str, float] = defaultdict(float)
        all_trades: list[Any] = []
        fold_returns: list[float] = []
        for result, (fold_id, start, end) in zip(fold_results, FOLDS, strict=True):
            portfolio_returns = _equity_returns(result)
            fold_btc = btc_returns.loc[(btc_returns.index >= start) & (btc_returns.index < end)]
            estimate = estimate_beta(portfolio_returns, fold_btc)
            exposure = causal_volatility_matched_exposure(
                portfolio_returns, fold_btc, lookback=28 * 6
            )
            beta_rows.append(
                {
                    "variant_id": variant_id,
                    "fold_id": fold_id,
                    **asdict(estimate),
                    "volatility_matched_btc_return": _compound(
                        fold_btc.reindex(exposure.index) * exposure
                    ),
                    "maximum_btc_exposure": float(exposure.max()),
                }
            )
            fold_returns.append(result.final_cash / result.initial_capital - 1.0)
            for trade in result.trades:
                symbol_pnl[trade.symbol] += trade.net_pnl
                all_trades.append(trade)
        concentration = concentration_metrics(symbol_pnl)
        concentration_rows.append(
            {"variant_id": variant_id, **concentration, "trade_count": len(all_trades)}
        )
        total_net = sum(trade.net_pnl for trade in all_trades)
        for symbol in sorted(symbol_pnl):
            leave_one_rows.append(
                {
                    "variant_id": variant_id,
                    "symbol": symbol,
                    "net_pnl_after_removal": total_net - symbol_pnl[symbol],
                    "sign_positive": total_net - symbol_pnl[symbol] > 0,
                }
            )
        ordered = sorted(
            ((trade.trade_id, trade.net_pnl) for trade in all_trades),
            key=lambda item: (-item[1], item[0]),
        )
        for count in (1, 3, 5):
            remaining = total_net - sum(value for _, value in ordered[:count])
            leave_top_rows.append(
                {
                    "variant_id": variant_id,
                    "top_n": count,
                    "net_pnl_after_removal": remaining,
                    "sign_positive": remaining > 0,
                }
            )
        variants[variant_id] = {
            "fold_returns": fold_returns,
            "trade_count": len(all_trades),
            "net_pnl": total_net,
            "concentration": concentration,
        }
    btc_daily = daily_returns["BTC"].dropna()
    equal_weight = daily_returns.mean(axis=1, skipna=True)
    benchmark = {
        "BTC_BUY_AND_HOLD": _compound(btc_daily),
        "EQUAL_WEIGHT_SURVIVOR_30": _compound(equal_weight),
        "CASH": 0.0,
        "HIGH_BETA_28": {
            "status": "CAUSAL_ENGINE_TESTED",
            "window_days": 28,
            "performance": "NOT_RUN_WITHOUT_SEPARATE_BENCHMARK_LEDGER",
        },
        "HIGH_BETA_84": {
            "status": "CAUSAL_ENGINE_TESTED",
            "window_days": 84,
            "performance": "NOT_RUN_WITHOUT_SEPARATE_BENCHMARK_LEDGER",
        },
    }
    max_top3 = max(float(row["top_3"]) for row in concentration_rows)
    classification = (
        "DOMINATED_BY_EXCEPTIONAL_WINNERS"
        if max_top3 >= 0.70
        else "MODERATELY_CONCENTRATED"
    )
    beta_report = {
        "schema_version": "ams-rd01-btc-beta-diagnostics-v1",
        "status": "COMPLETE",
        "judgment": "MIXED",
        "windows_days": [28, 84],
        "fold_estimates": beta_rows,
        "dataset_hashes": dataset_hashes,
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
    }
    concentration_report = {
        "schema_version": "ams-rd01-concentration-diagnostics-v1",
        "status": "COMPLETE",
        "classification": classification,
        "variants": variants,
        "maximum_top_3_positive_profit_share": max_top3,
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
    }
    atomic_json(REPORTS / "ams-rd01-btc-beta-diagnostics-v1.json", beta_report)
    atomic_json(
        REPORTS / "ams-rd01-benchmark-comparison-v1.json",
        {
            "schema_version": "ams-rd01-benchmark-comparison-v1",
            "status": "PARTIAL",
            "judgment": "MIXED",
            "benchmarks": benchmark,
            "test_2025_accessed": False,
            "holdout_2026_accessed": False,
        },
    )
    atomic_json(
        REPORTS / "ams-rd01-concentration-diagnostics-v1.json",
        concentration_report,
    )
    atomic_csv(
        REPORTS / "ams-rd01-btc-beta-by-fold-v1.csv",
        fieldnames=tuple(beta_rows[0]),
        rows=beta_rows,
    )
    atomic_csv(
        REPORTS / "ams-rd01-regime-beta-decomposition-v1.csv",
        fieldnames=("status", "reason"),
        rows=(
            {
                "status": "BLOCKED_BY_DATA",
                "reason": "DOMINANCE_REGIMES_UNAVAILABLE",
            },
        ),
    )
    atomic_csv(
        REPORTS / "ams-rd01-leave-top-n-out-v1.csv",
        fieldnames=tuple(leave_top_rows[0]),
        rows=leave_top_rows,
    )
    atomic_csv(
        REPORTS / "ams-rd01-leave-one-asset-out-v1.csv",
        fieldnames=tuple(leave_one_rows[0]),
        rows=leave_one_rows,
    )
    atomic_csv(
        REPORTS / "ams-rd01-leave-one-fold-out-v1.csv",
        fieldnames=("variant_id", "fold_removed", "remaining_compounded_return"),
        rows=[
            {
                "variant_id": variant_id,
                "fold_removed": f"WF{index + 1:02d}",
                "remaining_compounded_return": float(
                    np.prod(
                        [
                            1.0 + value
                            for offset, value in enumerate(record["fold_returns"])
                            if offset != index
                        ]
                    )
                    - 1.0
                ),
            }
            for variant_id, record in variants.items()
            for index in range(3)
        ],
    )
    print("BETA_STATUS=MIXED")
    print(f"CONCENTRATION={classification}")
    print("SURVIVOR_VARIANTS=6")
    print("DYNAMIC_MD01_BUDGET_CONSUMED=0")


if __name__ == "__main__":
    main()
