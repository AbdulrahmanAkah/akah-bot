"""Run causal momentum-factor and multi-timeframe-alignment diagnostics."""

from __future__ import annotations

import argparse
import json
from collections.abc import Iterable
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
    classify_alignment,
    eligible_universe_at,
    rank_buckets,
    weekly_rebalance_times,
)


def _fold_id(timestamp: pd.Timestamp) -> str:
    for fold_id, start, end in FOLDS:
        if start <= timestamp < end:
            return fold_id
    return "TRAIN"


def _forward(
    daily_symbol: pd.DataFrame,
    timestamp: pd.Timestamp,
    days: int,
) -> float | None:
    values = daily_symbol
    current = values.loc[values["bar_close_time"] <= timestamp]
    future = values.loc[values["bar_close_time"] <= timestamp + pd.Timedelta(days=days)]
    if current.empty or future.empty:
        return None
    if pd.Timestamp(future.iloc[-1]["bar_close_time"]) <= timestamp:
        return None
    return float(future.iloc[-1]["close"] / current.iloc[-1]["close"] - 1.0)


def _spearman(left: pd.Series, right: pd.Series) -> float | None:
    valid = pd.DataFrame({"left": left, "right": right}).dropna()
    if len(valid) < 3 or valid["left"].nunique() < 2 or valid["right"].nunique() < 2:
        return None
    return float(valid["left"].rank().corr(valid["right"].rank()))


def _bootstrap(values: Iterable[float], seed: int) -> list[float] | str:
    array = np.asarray(list(values), dtype=float)
    if len(array) < 30:
        return "INSUFFICIENT_SAMPLE"
    generator = np.random.default_rng(seed)
    means = [
        float(generator.choice(array, size=len(array), replace=True).mean())
        for _ in range(1_000)
    ]
    return [float(np.quantile(means, 0.025)), float(np.quantile(means, 0.975))]


def _factor_status(
    *,
    mean_ic: float | None,
    fold_ic: dict[str, float | None],
    fold_spread: dict[str, float | None],
    sample: int,
) -> str:
    if sample < 100:
        return "INSUFFICIENT_SAMPLE"
    positive_ic_folds = sum(value is not None and value > 0 for value in fold_ic.values())
    positive_spread_folds = sum(
        value is not None and value > 0 for value in fold_spread.values()
    )
    if (
        mean_ic is not None
        and mean_ic > 0
        and positive_ic_folds >= 2
        and positive_spread_folds >= 2
    ):
        return "RAW_FACTOR_PASS"
    if mean_ic is not None and mean_ic > 0 and (
        positive_ic_folds >= 2 or positive_spread_folds >= 2
    ):
        return "RAW_FACTOR_WEAK"
    return "RAW_FACTOR_FAIL"


def factor_diagnostics(
    daily: pd.DataFrame,
    eight: pd.DataFrame,
    four: pd.DataFrame,
    availability: pd.DataFrame,
) -> dict[str, Any]:
    timestamps = weekly_rebalance_times(
        pd.Timestamp("2022-01-01T00:00:00Z"),
        pd.Timestamp("2025-01-01T00:00:00Z"),
    )
    daily_groups = {
        str(symbol): values.sort_values("bar_close_time")
        for symbol, values in daily.groupby("symbol", sort=False)
    }
    factors: dict[str, Any] = {}
    for horizon in (28, 84):
        period_rows: list[dict[str, Any]] = []
        prior_top: set[str] = set()
        turnover: list[float] = []
        for timestamp in timestamps:
            ranked, _ = eligible_universe_at(
                timestamp=timestamp,
                horizon_days=horizon,
                daily=daily,
                eight_hour=eight,
                four_hour=four,
                availability=availability,
            )
            if ranked.empty:
                continue
            ranked = ranked.copy()
            ranked["bucket"] = rank_buckets(ranked)
            top = set(ranked.nsmallest(max(1, len(ranked) // 5), "bucket")["symbol"])
            if prior_top:
                turnover.append(1.0 - len(top & prior_top) / max(len(top | prior_top), 1))
            prior_top = top
            for row in ranked.itertuples(index=False):
                record: dict[str, Any] = {
                    "timestamp": timestamp,
                    "fold_id": _fold_id(timestamp),
                    "year": timestamp.year,
                    "symbol": str(row.symbol),
                    "momentum_return": float(row.momentum_return),
                    "percentile_rank": float(row.percentile_rank),
                    "bucket": int(row.bucket),
                }
                for days in (7, 14, 28):
                    record[f"forward_{days}d"] = _forward(
                        daily_groups[str(row.symbol)], timestamp, days
                    )
                period_rows.append(record)
        observations = pd.DataFrame(period_rows)
        if observations.empty:
            factors[f"MOMENTUM_{horizon}D"] = {"status": "INSUFFICIENT_SAMPLE"}
            continue
        forward_reports: dict[str, Any] = {}
        for days in (7, 14, 28):
            column = f"forward_{days}d"
            per_time: list[dict[str, Any]] = []
            for timestamp, values in observations.groupby("timestamp", sort=True):
                valid = values.dropna(subset=[column])
                if len(valid) < 3:
                    continue
                top_bucket = valid.loc[valid["bucket"].eq(valid["bucket"].min()), column]
                bottom_bucket = valid.loc[valid["bucket"].eq(valid["bucket"].max()), column]
                per_time.append(
                    {
                        "timestamp": timestamp,
                        "fold_id": str(valid.iloc[0]["fold_id"]),
                        "rank_ic": _spearman(valid["momentum_return"], valid[column]),
                        "top_minus_bottom": float(top_bucket.mean() - bottom_bucket.mean()),
                        "top_minus_universe": float(top_bucket.mean() - valid[column].mean()),
                    }
                )
            time_frame = pd.DataFrame(per_time)
            valid_ic = time_frame["rank_ic"].dropna() if not time_frame.empty else pd.Series()
            fold_ic: dict[str, float | None] = {}
            fold_spread: dict[str, float | None] = {}
            for fold_id, _, _ in FOLDS:
                fold_values = (
                    time_frame.loc[time_frame["fold_id"].eq(fold_id)]
                    if not time_frame.empty
                    else pd.DataFrame()
                )
                fold_ic[fold_id] = (
                    float(fold_values["rank_ic"].dropna().mean())
                    if not fold_values.empty and fold_values["rank_ic"].notna().any()
                    else None
                )
                fold_spread[fold_id] = (
                    float(fold_values["top_minus_bottom"].mean())
                    if not fold_values.empty
                    else None
                )
            bucket_means = (
                observations.groupby("bucket", observed=True)[column].mean().to_dict()
            )
            monotonic = all(
                bucket_means[left] >= bucket_means[right]
                for left, right in zip(
                    sorted(bucket_means)[:-1], sorted(bucket_means)[1:], strict=False
                )
            )
            forward_reports[f"{days}d"] = {
                "sample_count": int(observations[column].notna().sum()),
                "mean_rank_ic": float(valid_ic.mean()) if len(valid_ic) else None,
                "median_rank_ic": float(valid_ic.median()) if len(valid_ic) else None,
                "positive_ic_frequency": float((valid_ic > 0).mean())
                if len(valid_ic)
                else None,
                "top_minus_bottom": float(time_frame["top_minus_bottom"].mean())
                if not time_frame.empty
                else None,
                "top_minus_universe": float(time_frame["top_minus_universe"].mean())
                if not time_frame.empty
                else None,
                "fold_rank_ic": fold_ic,
                "fold_top_minus_bottom": fold_spread,
                "bucket_mean_forward_returns": {
                    str(key): float(value) for key, value in bucket_means.items()
                },
                "forward_return_monotonic": monotonic,
                "rank_ic_bootstrap_ci_95": _bootstrap(valid_ic.tolist(), 10_000 + horizon + days),
            }
        report_28 = forward_reports["28d"]
        status = _factor_status(
            mean_ic=report_28["mean_rank_ic"],
            fold_ic=report_28["fold_rank_ic"],
            fold_spread=report_28["fold_top_minus_bottom"],
            sample=int(report_28["sample_count"]),
        )
        positive = observations.loc[observations["momentum_return"] > 0, "forward_28d"].dropna()
        positive_fold = {
            fold_id: float(
                observations.loc[
                    observations["fold_id"].eq(fold_id)
                    & (observations["momentum_return"] > 0),
                    "forward_28d",
                ].mean()
            )
            for fold_id, _, _ in FOLDS
        }
        dual = observations.loc[
            observations["bucket"].eq(0) & (observations["momentum_return"] > 0)
        ]
        dual_forward = dual["forward_28d"].dropna()
        dual_fold = {
            fold_id: float(
                dual.loc[dual["fold_id"].eq(fold_id), "forward_28d"].mean()
            )
            for fold_id, _, _ in FOLDS
        }
        factors[f"MOMENTUM_{horizon}D"] = {
            "status": status,
            "forward_returns": forward_reports,
            "time_series_positive_signal": {
                "sample_count": int(len(positive)),
                "mean_forward_28d": float(positive.mean()) if len(positive) else None,
                "median_forward_28d": float(positive.median()) if len(positive) else None,
                "positive_frequency": float((positive > 0).mean()) if len(positive) else None,
                "fold_mean_forward_28d": positive_fold,
            },
            "dual_top_positive_signal": {
                "sample_count": int(len(dual_forward)),
                "mean_forward_28d": float(dual_forward.mean())
                if len(dual_forward)
                else None,
                "median_forward_28d": float(dual_forward.median())
                if len(dual_forward)
                else None,
                "positive_frequency": float((dual_forward > 0).mean())
                if len(dual_forward)
                else None,
                "fold_mean_forward_28d": dual_fold,
            },
            "top_bucket_turnover": float(np.mean(turnover)) if turnover else None,
            "rank_dispersion": float(observations["momentum_return"].std(ddof=0)),
            "results_by_year": {
                str(year): {
                    "mean_forward_28d": float(values["forward_28d"].mean()),
                    "sample_count": int(values["forward_28d"].notna().sum()),
                }
                for year, values in observations.groupby("year")
            },
            "results_by_symbol": {
                str(symbol): {
                    "mean_forward_28d": float(values["forward_28d"].mean()),
                    "sample_count": int(values["forward_28d"].notna().sum()),
                }
                for symbol, values in observations.groupby("symbol")
            },
        }
    factor_values = list(factors.values())
    tsm_pass = any(
        record["time_series_positive_signal"]["mean_forward_28d"] > 0
        and sum(
            value > 0
            for value in record["time_series_positive_signal"][
                "fold_mean_forward_28d"
            ].values()
        )
        >= 2
        for record in factor_values
    )
    dual_positive = any(
        record["dual_top_positive_signal"]["mean_forward_28d"] > 0
        and sum(
            value > 0
            for value in record["dual_top_positive_signal"][
                "fold_mean_forward_28d"
            ].values()
        )
        >= 2
        for record in factor_values
    )
    xsm_status = max(
        (record["status"] for record in factor_values),
        key=lambda value: {
            "RAW_FACTOR_FAIL": 0,
            "RAW_FACTOR_WEAK": 1,
            "RAW_FACTOR_PASS": 2,
            "INSUFFICIENT_SAMPLE": -1,
        }[value],
    )
    return {
        "schema_version": "ams-md01-factor-diagnostics-v1",
        "status": "PASS",
        "factors": factors,
        "school_statuses": {
            "TSM": (
                "RAW_FACTOR_PASS" if tsm_pass else "RAW_FACTOR_FAIL"
            ),
            "XSM": xsm_status,
            "DUAL": (
                "RAW_FACTOR_PASS"
                if dual_positive and xsm_status == "RAW_FACTOR_PASS"
                else "RAW_FACTOR_WEAK"
                if dual_positive
                else "RAW_FACTOR_FAIL"
            ),
        },
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
    }


def alignment_diagnostics(
    daily: pd.DataFrame,
    eight: pd.DataFrame,
    four: pd.DataFrame,
) -> dict[str, Any]:
    signals = four.loc[
        four["four_hour_positive"]
        & (four["bar_close_time"] >= pd.Timestamp("2022-01-01T00:00:00Z"))
    ].copy()
    daily_support = daily[
        ["symbol", "bar_close_time", "trend_positive", "trend_state"]
    ].rename(
        columns={
            "trend_positive": "daily_positive",
            "trend_state": "daily_state",
        }
    )
    eight_support = eight[
        ["symbol", "bar_close_time", "trend_positive", "trend_state"]
    ].rename(
        columns={
            "trend_positive": "eight_positive",
            "trend_state": "eight_state",
        }
    )
    signals = pd.merge_asof(
        signals.sort_values(["bar_close_time", "symbol"]),
        daily_support.sort_values(["bar_close_time", "symbol"]),
        on="bar_close_time",
        by="symbol",
        direction="backward",
    )
    signals = pd.merge_asof(
        signals.sort_values(["bar_close_time", "symbol"]),
        eight_support.sort_values(["bar_close_time", "symbol"]),
        on="bar_close_time",
        by="symbol",
        direction="backward",
    )
    tiers: list[str] = []
    for row in signals.itertuples(index=False):
        tier, _ = classify_alignment(
            daily_positive=bool(row.daily_positive),
            eight_hour_positive=bool(row.eight_positive),
            four_hour_positive=True,
        )
        tiers.append(tier)
    signals["alignment_tier"] = tiers
    daily_groups = {
        str(symbol): values.sort_values("bar_close_time")
        for symbol, values in daily.groupby("symbol", sort=False)
    }
    rows: list[dict[str, Any]] = []
    for row in signals.itertuples(index=False):
        symbol = str(row.symbol)
        timestamp = pd.Timestamp(row.bar_close_time)
        values = daily_groups[symbol]
        current = values.loc[values["bar_close_time"] <= timestamp]
        if current.empty:
            continue
        current_price = float(current.iloc[-1]["close"])
        record: dict[str, Any] = {
            "symbol": symbol,
            "timestamp": timestamp,
            "tier": str(row.alignment_tier),
            "fold_id": _fold_id(timestamp),
        }
        for days in (1, 3, 7, 14, 28):
            future = values.loc[
                (values["bar_close_time"] > timestamp)
                & (values["bar_close_time"] <= timestamp + pd.Timedelta(days=days))
            ]
            if future.empty:
                record[f"forward_{days}d"] = None
                record[f"mae_{days}d"] = None
                record[f"mfe_{days}d"] = None
            else:
                record[f"forward_{days}d"] = float(
                    future.iloc[-1]["close"] / current_price - 1.0
                )
                record[f"mae_{days}d"] = float(future["low"].min() / current_price - 1.0)
                record[f"mfe_{days}d"] = float(future["high"].max() / current_price - 1.0)
        rows.append(record)
    observations = pd.DataFrame(rows)
    tiers_report: dict[str, Any] = {}
    for tier, values in observations.groupby("tier", sort=True):
        horizons: dict[str, Any] = {}
        for days in (1, 3, 7, 14, 28):
            forward = values[f"forward_{days}d"].dropna()
            horizons[f"{days}d"] = {
                "sample_count": int(len(forward)),
                "mean_forward_return": float(forward.mean()) if len(forward) else None,
                "median_forward_return": float(forward.median()) if len(forward) else None,
                "positive_return_frequency": float((forward > 0).mean())
                if len(forward)
                else None,
                "downside_deviation": float(forward[forward < 0].std(ddof=0))
                if bool((forward < 0).any())
                else 0.0,
                "maximum_adverse_move": float(values[f"mae_{days}d"].min()),
                "maximum_favourable_move": float(values[f"mfe_{days}d"].max()),
                "bootstrap_mean_ci_95": _bootstrap(
                    forward.tolist(), 20_000 + days + len(tier)
                ),
            }
        tiers_report[str(tier)] = {"signal_count": int(len(values)), "horizons": horizons}
    means_28 = {
        tier: report["horizons"]["28d"]["mean_forward_return"]
        for tier, report in tiers_report.items()
    }
    available = all(
        tier in means_28 and means_28[tier] is not None
        for tier in ("FULL", "MEDIUM", "FOUR_HOUR_ONLY")
    )
    if not available:
        status = "INSUFFICIENT_SAMPLE"
    elif means_28["FULL"] > means_28["MEDIUM"] > means_28["FOUR_HOUR_ONLY"]:
        status = "ALIGNMENT_MONOTONIC"
    elif means_28["FULL"] > means_28["FOUR_HOUR_ONLY"]:
        status = "ALIGNMENT_PARTIALLY_MONOTONIC"
    else:
        status = "ALIGNMENT_NOT_PREDICTIVE"
    return {
        "schema_version": "ams-md01-alignment-analysis-v1",
        "status": "PASS",
        "alignment_status": status,
        "tiers": tiers_report,
        "hypothesis": "FULL > MEDIUM > FOUR_HOUR_ONLY",
        "effect_size": {
            "full_minus_four_hour_only_28d": (
                means_28.get("FULL", 0.0) - means_28.get("FOUR_HOUR_ONLY", 0.0)
                if available
                else None
            )
        },
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
    }


def _write_report(name: str, report: dict[str, Any], title: str) -> tuple[str, str]:
    json_name = f"{name}.json"
    markdown_name = f"{name}.md"
    atomic_json(REPORTS / json_name, report)
    atomic_text(
        REPORTS / markdown_name,
        "\n".join(
            [
                f"# {title}",
                "",
                f"- Status: **{report['status']}**",
                f"- Test 2025 accessed: `{str(report['test_2025_accessed']).lower()}`",
                f"- Holdout 2026 accessed: `{str(report['holdout_2026_accessed']).lower()}`",
                "",
                "The JSON report is the canonical numeric record.",
                "",
            ]
        ),
    )
    return json_name, markdown_name


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reuse-verified-alignment", action="store_true")
    arguments = parser.parse_args()
    frames, _ = load_registered_data()
    daily = build_trend_features(frames["daily"])
    eight = build_trend_features(frames["eight_hour"])
    four = build_trend_features(frames["four_hour"], four_hour=True)
    factor = factor_diagnostics(daily, eight, four, frames["availability"])
    alignment_path = REPORTS / "ams-md01-alignment-analysis-v1.json"
    if arguments.reuse_verified_alignment:
        alignment = json.loads(alignment_path.read_text(encoding="utf-8"))
        if (
            alignment["status"] != "PASS"
            or alignment["test_2025_accessed"]
            or alignment["holdout_2026_accessed"]
        ):
            raise RuntimeError("existing alignment report is not reusable")
    else:
        alignment = alignment_diagnostics(daily, eight, four)
    names = [
        *_write_report(
            "ams-md01-factor-diagnostics-v1",
            factor,
            "AMS-MD01 Momentum Factor Diagnostics",
        ),
        *_write_report(
            "ams-md01-alignment-analysis-v1",
            alignment,
            "AMS-MD01 Multi-Timeframe Alignment Analysis",
        ),
    ]
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    ledger["report_hashes"].update(
        {name: sha256(REPORTS / name) for name in names}
    )
    atomic_json(LEDGER, ledger)
    copy_external(names)
    print(f"ALIGNMENT_STATUS={alignment['alignment_status']}")
    print(f"TSM_FACTOR_STATUS={factor['school_statuses']['TSM']}")
    print(f"XSM_FACTOR_STATUS={factor['school_statuses']['XSM']}")


if __name__ == "__main__":
    main()
