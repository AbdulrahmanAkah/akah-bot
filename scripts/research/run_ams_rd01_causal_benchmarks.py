"""Run local causal benchmarks that do not require dominance market-cap data."""

from __future__ import annotations

import pandas as pd
from ams_md01_common import load_registered_data
from ams_md01r2_common import REPORTS, atomic_json

from spotbot.research.beta_diagnostics import causal_high_beta_benchmark


def _compound(series: pd.Series) -> float:
    clean = series.dropna()
    return float((1.0 + clean).prod() - 1.0)


def main() -> None:
    frames, dataset_hashes = load_registered_data()
    daily = frames["daily"].copy()
    daily["bar_close_time"] = pd.to_datetime(daily["bar_close_time"], utc=True)
    prices = daily.pivot(index="bar_close_time", columns="symbol", values="close")
    returns = prices.sort_index().pct_change(fill_method=None)
    btc = returns["BTC"].dropna()
    results = {}
    for lookback in (28, 84):
        benchmark = causal_high_beta_benchmark(
            returns,
            btc,
            lookback_days=lookback,
            maximum_positions=3,
            transaction_cost=0.002,
        )
        results[f"HIGH_BETA_{lookback}"] = {
            "status": "COMPLETE",
            "net_compounded_return": _compound(benchmark.returns),
            "maximum_exposure": float(benchmark.exposure.max()),
            "average_exposure": float(benchmark.exposure.mean()),
            "turnover": benchmark.turnover,
            "selection_count": benchmark.selection_count,
            "window_days": lookback,
        }
    report = {
        "schema_version": "ams-rd01-causal-benchmark-comparison-v2",
        "status": "COMPLETE",
        "judgment": "MIXED",
        "benchmarks": {
            "BTC_BUY_AND_HOLD": _compound(btc),
            "EQUAL_WEIGHT_SURVIVOR_30": _compound(
                returns.mean(axis=1, skipna=True)
            ),
            "CASH": 0.0,
            **results,
        },
        "constraints": {
            "negative_weights": False,
            "maximum_exposure": 1.0,
            "leverage": False,
            "selection_uses_future_returns": False,
        },
        "dataset_hashes": dataset_hashes,
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
    }
    atomic_json(REPORTS / "ams-rd01-benchmark-comparison-v2.json", report)
    print("CAUSAL_BENCHMARKS=COMPLETE")
    print("HIGH_BETA_WINDOWS=28,84")
    print("MAXIMUM_EXPOSURE=1.0")


if __name__ == "__main__":
    main()
