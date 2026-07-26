"""Run the eight immutable causal AMS-MD01 benchmark specifications."""

from __future__ import annotations

import json
import math
from typing import Any

import numpy as np
import pandas as pd
from ams_md01_common import (
    LEDGER,
    REPORTS,
    atomic_json,
    atomic_text,
    copy_external,
    load_registered_data,
    sha256,
)

from spotbot.research.ams_md01_momentum import (
    FOLDS,
    build_trend_features,
    causal_cluster_snapshot,
    select_assets,
    variant_spec,
)

BENCHMARKS = {
    "B00": "CASH",
    "B01": "BTC_BUY_AND_HOLD",
    "B02": "EQUAL_WEIGHT_ELIGIBLE_UNIVERSE",
    "B03": "BTC_DAILY_TREND_FILTERED",
    "B04": "EQUAL_WEIGHT_DAILY_TREND_FILTERED",
    "B05": "SIMPLE_TSM_12W_WITHOUT_4H",
    "B06": "SIMPLE_XSM_12W_TOP3_WITHOUT_4H",
    "B07": "SIMPLE_DUAL_12W_TOP3_WITHOUT_4H",
}


def _metrics(equity: pd.Series, turnover: float, fees: float) -> dict[str, Any]:
    returns = equity.pct_change().dropna()
    net_return = float(equity.iloc[-1] / equity.iloc[0] - 1.0)
    peak = equity.cummax()
    drawdown = 1.0 - equity / peak
    maximum_drawdown = float(drawdown.max())
    downside = returns[returns < 0]
    monthly = equity.resample("ME").last().pct_change().dropna()
    yearly = equity.resample("YE").last().pct_change().dropna()
    recovery = 0
    current = 0
    for value in drawdown:
        if value > 1e-12:
            current += 1
            recovery = max(recovery, current)
        else:
            current = 0
    return {
        "initial_capital": float(equity.iloc[0]),
        "final_equity": float(equity.iloc[-1]),
        "net_return": net_return,
        "cagr": net_return,
        "maximum_drawdown": maximum_drawdown,
        "calmar": net_return / maximum_drawdown if maximum_drawdown > 0 else None,
        "sharpe": (
            float(returns.mean() / returns.std(ddof=1) * math.sqrt(365))
            if len(returns) > 1 and returns.std(ddof=1) > 0
            else None
        ),
        "sortino": (
            float(returns.mean() / downside.std(ddof=1) * math.sqrt(365))
            if len(downside) > 1 and downside.std(ddof=1) > 0
            else None
        ),
        "turnover": turnover,
        "fees": fees,
        "exposure": None,
        "worst_year": float(yearly.min()) if len(yearly) else net_return,
        "worst_month": float(monthly.min()) if len(monthly) else net_return,
        "recovery_time_days": recovery,
    }


def _daily_matrix(daily: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    relevant = daily.loc[
        (daily["bar_close_time"] >= start) & (daily["bar_close_time"] <= end)
    ].copy()
    prices = relevant.pivot(index="bar_close_time", columns="symbol", values="close")
    return prices.sort_index()


def _ranked_fast(
    timestamp: pd.Timestamp,
    *,
    daily_features: pd.DataFrame,
    availability: pd.DataFrame,
) -> pd.DataFrame:
    """Fast causal 84-day rank using the already completed daily panel."""
    eligible = daily_features.loc[daily_features["bar_close_time"] <= timestamp]
    latest = eligible.groupby("symbol", sort=False).tail(1).copy()
    available = availability.copy()
    available["tradable_from"] = pd.to_datetime(available["tradable_from"], utc=True)
    available["tradable_until"] = pd.to_datetime(available["tradable_until"], utc=True)
    latest = latest.merge(
        available[["symbol", "tradable_from", "tradable_until"]],
        on="symbol",
        how="left",
        validate="one_to_one",
    )
    latest = latest.loc[
        (latest["tradable_from"] <= timestamp)
        & (timestamp < latest["tradable_until"])
        & latest["momentum_84"].notna()
    ].copy()
    latest = latest.sort_values(
        ["momentum_84", "symbol"], ascending=[False, True], kind="stable"
    )
    latest = latest.rename(columns={"momentum_84": "momentum_return"})
    latest["percentile_rank"] = (
        1.0
        if len(latest) <= 1
        else 1.0 - np.arange(len(latest)) / (len(latest) - 1)
    )
    return latest


def _weight_schedules(
    daily_features: pd.DataFrame,
    availability: pd.DataFrame,
) -> dict[str, dict[pd.Timestamp, dict[str, float]]]:
    schedules: dict[str, dict[pd.Timestamp, dict[str, float]]] = {
        identity: {} for identity in BENCHMARKS
    }
    closes = sorted(
        pd.Timestamp(value)
        for value in daily_features.loc[
            daily_features["bar_close_time"] >= pd.Timestamp("2021-12-31T00:00:00Z"),
            "bar_close_time",
        ].unique()
    )
    for timestamp in closes:
        latest_btc = daily_features.loc[
            daily_features["symbol"].eq("BTC")
            & (daily_features["bar_close_time"] <= timestamp)
        ].iloc[-1]
        schedules["B00"][timestamp] = {}
        schedules["B01"][timestamp] = {"BTC": 1.0}
        schedules["B03"][timestamp] = (
            {"BTC": 1.0} if bool(latest_btc["trend_positive"]) else {}
        )
        ranked = _ranked_fast(
            timestamp,
            daily_features=daily_features,
            availability=availability,
        )
        positive_symbols = ranked.loc[
            ranked["trend_positive"], "symbol"
        ].astype(str).tolist()
        schedules["B04"][timestamp] = (
            {symbol: 1.0 / len(positive_symbols) for symbol in positive_symbols}
            if positive_symbols
            else {}
        )
        if timestamp.weekday() != 6:
            continue
        symbols = ranked["symbol"].astype(str).tolist()
        schedules["B02"][timestamp] = (
            {symbol: 1.0 / len(symbols) for symbol in symbols} if symbols else {}
        )
        clusters, _, _, _ = causal_cluster_snapshot(
            daily_features,
            timestamp=timestamp,
            symbols=symbols,
        )
        for benchmark_id, variant_id in (
            ("B05", "MD01-M02"),
            ("B06", "MD01-M04"),
            ("B07", "MD01-M06"),
        ):
            selected, _ = select_assets(
                ranked[["symbol", "momentum_return", "percentile_rank"]],
                variant=variant_spec(variant_id),
                clusters=clusters,
            )
            weight = 0.20 if benchmark_id == "B05" else 0.25
            schedules[benchmark_id][timestamp] = {
                symbol: weight for symbol in selected
            }
    return schedules


def _fold(
    benchmark_id: str,
    *,
    start: pd.Timestamp,
    end: pd.Timestamp,
    daily: pd.DataFrame,
    weight_schedule: dict[pd.Timestamp, dict[str, float]],
    cost: float,
) -> dict[str, Any]:
    prices = _daily_matrix(daily, start, end)
    if prices.empty:
        raise RuntimeError("empty benchmark fold")
    asset_returns = prices.pct_change(fill_method=None).fillna(0.0)
    initial_decision = pd.Timestamp(prices.index[0]) - pd.Timedelta(days=1)
    weights: dict[str, float] = dict(weight_schedule.get(initial_decision, {}))
    prior_weights: dict[str, float] = {}
    equity_values = [100_000.0]
    equity_index = [prices.index[0]]
    turnover = 0.0
    fees = 0.0
    exposures: list[float] = []
    for timestamp in prices.index[1:]:
        decision_time = pd.Timestamp(timestamp) - pd.Timedelta(days=1)
        if pd.Timestamp(timestamp).weekday() == 0 or benchmark_id in {"B03", "B04"}:
            weights = weight_schedule.get(decision_time, weights)
            change = sum(
                abs(weights.get(symbol, 0.0) - prior_weights.get(symbol, 0.0))
                for symbol in set(weights) | set(prior_weights)
            )
            notional = equity_values[-1] * change
            turnover += notional
            fee = notional * cost
            fees += fee
            equity_values[-1] -= fee
            prior_weights = dict(weights)
        row = asset_returns.loc[timestamp]
        portfolio_return = sum(
            weight * float(row.get(symbol, 0.0)) for symbol, weight in weights.items()
        )
        equity_values.append(equity_values[-1] * (1.0 + portfolio_return))
        equity_index.append(timestamp)
        exposures.append(sum(weights.values()))
    # Exit fee at fold end.
    exit_turnover = equity_values[-1] * sum(weights.values())
    exit_fee = exit_turnover * cost
    turnover += exit_turnover
    fees += exit_fee
    equity_values[-1] -= exit_fee
    equity = pd.Series(equity_values, index=pd.DatetimeIndex(equity_index))
    result = _metrics(equity, turnover, fees)
    result["exposure"] = float(np.mean(exposures)) if exposures else 0.0
    return result


def main() -> None:
    frames, hashes = load_registered_data()
    daily_features = build_trend_features(frames["daily"])
    daily_features["momentum_84"] = daily_features.groupby("symbol", sort=False)[
        "close"
    ].transform(lambda values: values / values.shift(84) - 1.0)
    schedules = _weight_schedules(daily_features, frames["availability"])
    records: dict[str, Any] = {}
    for benchmark_id, name in BENCHMARKS.items():
        modes: dict[str, Any] = {}
        for mode, cost in (("ZERO_COST", 0.0), ("BASE_COST", 0.002)):
            folds = [
                _fold(
                    benchmark_id,
                    start=start,
                    end=end,
                    daily=frames["daily"],
                    weight_schedule=schedules[benchmark_id],
                    cost=cost,
                )
                for _, start, end in FOLDS
            ]
            calmar_values = [
                float(item["calmar"]) for item in folds if item["calmar"] is not None
            ]
            modes[mode] = {
                "folds": folds,
                "compounded_return": math.prod(1.0 + item["net_return"] for item in folds)
                - 1.0,
                "mean_maximum_drawdown": float(
                    np.mean([item["maximum_drawdown"] for item in folds])
                ),
                "mean_calmar": float(np.mean(calmar_values)) if calmar_values else None,
                "turnover": sum(item["turnover"] for item in folds),
                "fees": sum(item["fees"] for item in folds),
                "worst_year": min(item["worst_year"] for item in folds),
                "worst_month": min(item["worst_month"] for item in folds),
                "recovery_time_days": max(item["recovery_time_days"] for item in folds),
            }
        records[benchmark_id] = {"name": name, **modes}
    report: dict[str, Any] = {
        "schema_version": "ams-md01-benchmark-comparison-v1",
        "status": "PASS",
        "benchmarks": records,
        "methodology": (
            "Causal prior-daily-close signals, next daily return, independent folds; "
            "B05-B07 intentionally omit 4H alignment."
        ),
        "dataset_hashes": hashes,
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
    }
    names = [
        "ams-md01-benchmark-comparison-v1.json",
        "ams-md01-benchmark-comparison-v1.md",
    ]
    atomic_json(REPORTS / names[0], report)
    atomic_text(
        REPORTS / names[1],
        "\n".join(
            [
                "# AMS-MD01 Benchmark Comparison",
                "",
                "| ID | Benchmark | Zero-cost compounded return | Base-cost compounded return |",
                "|---|---|---:|---:|",
                *[
                    (
                        f"| {identity} | {record['name']} | "
                        f"{record['ZERO_COST']['compounded_return']:.2%} | "
                        f"{record['BASE_COST']['compounded_return']:.2%} |"
                    )
                    for identity, record in records.items()
                ],
                "",
            ]
        ),
    )
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    ledger["report_hashes"].update(
        {name: sha256(REPORTS / name) for name in names}
    )
    atomic_json(LEDGER, ledger)
    copy_external(names)
    print("BENCHMARKS_EXECUTED=8")


if __name__ == "__main__":
    main()
