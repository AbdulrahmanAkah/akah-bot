"""Auditable ED01 reproduction and Native-execution diagnostic for AMS V4 T12.

This module intentionally *does not import* the V4 strategy module.  The V4
feature equations below are a literal, documented port of the registered T12
source.  All corrected simulations delegate order handling and accounting to
``ams_v5_native_engine.simulate_native_fold`` so the fill ledger remains the
single financial source of truth.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any, cast

import numpy as np
import pandas as pd

from spotbot.research.ams_v5_native_engine import (
    V5FoldResult,
    V5Parameters,
    V5PortfolioProfile,
    assert_boundary,
    simulate_native_fold,
)

ED01_PROTOCOL_ID = "AMS-ED01-V4-T12-NATIVE-EDGE-VERIFICATION"
T12_CONFIGURATION_ID = "AMS-V4-A06"
T12_PROFILE_ID = "AMS-V4-PORTFOLIO-P02"
FOLDS = (
    ("AMS-V4-WF01", "2022-01-01T00:00:00Z", "2023-01-01T00:00:00Z"),
    ("AMS-V4-WF02", "2023-01-01T00:00:00Z", "2024-01-01T00:00:00Z"),
    ("AMS-V4-WF03", "2024-01-01T00:00:00Z", "2025-01-01T00:00:00Z"),
)
T12_PROFILE = V5PortfolioProfile(T12_PROFILE_ID, 0.009, 0.0125, 0.016, 0.06, 6, 2)
T12_PARAMS = V5Parameters(
    "AMS-ED01-A06-NATIVE",
    "HYBRID",
    "V4_T12_STRUCTURE",
    "SOFT_FIBONACCI_SCORE",
    55,
    0.002,
)


class Ed01Error(RuntimeError):
    """Raised for an ED01 extraction, boundary, or diagnostic invariant."""


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def historical_trial(root: Path) -> dict[str, Any]:
    path = root / "reports/research/ams-v4-ams-v4-t12-trial-v1.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("configuration_id") != T12_CONFIGURATION_ID:
        raise Ed01Error("historical T12 configuration mismatch")
    if value.get("portfolio_profile_id") != T12_PROFILE_ID:
        raise Ed01Error("historical T12 portfolio mismatch")
    return cast(dict[str, Any], value)


def load_registered_v4_source(root: Path) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, str]]:
    """Load only the frozen registered AMS data and verify both file hashes."""
    registration = json.loads(
        (root / "reports/research/ams-v3-4h-dataset-registration-v1.json").read_text(
            encoding="utf-8"
        )
    )
    hashes: dict[str, str] = {}
    frames: dict[str, pd.DataFrame] = {}
    for name in ("four_hour", "availability"):
        record = registration["datasets"][name]
        path = root / record["path"]
        actual = file_sha256(path)
        if actual != record["file_sha256"]:
            raise Ed01Error(f"registered dataset hash mismatch: {name}")
        hashes[name] = actual
        frames[name] = pd.read_parquet(path)
    assert_boundary(frames["four_hour"])
    return frames["four_hour"], frames["availability"], hashes


def _atr(frame: pd.DataFrame, period: int = 14) -> pd.Series:
    previous = frame["close"].shift(1)
    return (
        pd.concat(
            [
                frame["high"] - frame["low"],
                (frame["high"] - previous).abs(),
                (frame["low"] - previous).abs(),
            ],
            axis=1,
        )
        .max(axis=1)
        .rolling(period, min_periods=period)
        .mean()
    )


def build_v4_t12_panel(four_hour: pd.DataFrame, availability: pd.DataFrame) -> pd.DataFrame:
    """Port the registered V4 feature equations, without importing V4 runtime code."""
    assert_boundary(four_hour)
    required = {
        "symbol",
        "bar_open_time",
        "bar_close_time",
        "open",
        "high",
        "low",
        "close",
        "volume",
    }
    if missing := required - set(four_hour.columns):
        raise Ed01Error(f"V4 source data missing {sorted(missing)}")
    frame = four_hour.copy()
    for column in ("bar_open_time", "bar_close_time"):
        frame[column] = pd.to_datetime(frame[column], utc=True, errors="raise")
    frame = frame.sort_values(["symbol", "bar_close_time"], kind="mergesort")
    btc_frame = frame.loc[frame["symbol"].eq("BTC"), ["bar_close_time", "close"]]
    if btc_frame.empty:
        raise Ed01Error("BTC is required for the registered V4 score")
    btc = btc_frame.set_index("bar_close_time")["close"].sort_index()
    btc_return = btc.pct_change(20)
    daily_btc = btc.resample("1D").last().to_frame("btc_close")
    daily_btc["btc_fast"] = daily_btc["btc_close"].ewm(span=50, adjust=False).mean()
    daily_btc["btc_slow"] = daily_btc["btc_close"].ewm(span=200, adjust=False).mean()
    daily_btc["btc_drawdown"] = daily_btc["btc_close"] / daily_btc["btc_close"].cummax() - 1.0
    daily_close = frame.set_index("bar_close_time").groupby("symbol")["close"].resample("1D").last()
    daily_ema = daily_close.groupby(level=0).transform(
        lambda value: value.ewm(span=50, adjust=False).mean()
    )
    breadth = (daily_close > daily_ema).groupby(level=1).mean().rename("breadth")
    daily_btc = daily_btc.join(breadth, how="left").ffill()
    d1 = np.select(
        [
            (daily_btc["btc_close"] > daily_btc["btc_fast"])
            & (daily_btc["btc_fast"] > daily_btc["btc_slow"])
            & (daily_btc["breadth"] >= 0.6),
            (daily_btc["btc_close"] > daily_btc["btc_slow"]) & (daily_btc["breadth"] >= 0.45),
            daily_btc["btc_drawdown"] <= -0.18,
            daily_btc["btc_drawdown"] <= -0.10,
        ],
        [15.0, 12.0, 2.0, 5.0],
        default=9.0,
    )
    daily_btc["d1_score"] = d1
    daily_btc["d1_multiplier"] = np.select(
        [d1 == 15.0, d1 == 12.0, d1 == 9.0, d1 == 5.0], [1.15, 1.0, 0.75, 0.45], default=0.2
    )
    output: list[pd.DataFrame] = []
    for _symbol, group in frame.groupby("symbol", sort=True):
        item = group.copy().set_index("bar_close_time", drop=False)
        item["ema_fast"] = item["close"].ewm(span=21, adjust=False).mean()
        item["ema_slow"] = item["close"].ewm(span=55, adjust=False).mean()
        item["atr"] = _atr(item)
        item["donchian_high"] = item["high"].rolling(20, min_periods=20).max().shift(1)
        item["swing_low"] = item["low"].rolling(12, min_periods=8).min().shift(1)
        item["volume_ratio"] = item["volume"] / item["volume"].rolling(30, min_periods=10).median()
        item["trend_slope"] = item["ema_fast"].pct_change(8)
        item["rs"] = item["close"].pct_change(20).sub(btc_return.reindex(item.index).ffill())
        item["ema_distance_atr"] = (item["close"] - item["ema_fast"]) / item["atr"]
        trend = (item["close"] > item["ema_fast"]) & (item["ema_fast"] > item["ema_slow"])
        breakout = (
            (item["close"] > item["donchian_high"])
            & ((item["high"] - item["low"]) > item["atr"] * 0.8)
            & item["ema_distance_atr"].lt(3.5)
        )
        pullback = (
            trend
            & item["low"].le(item["ema_fast"] + item["atr"] * 0.35)
            & item["close"].gt(item["ema_fast"])
            & item["close"].gt(item["open"])
        )
        item["breakout_signal"] = breakout.fillna(False)
        item["pullback_signal"] = pullback.fillna(False)
        item["family"] = np.select(
            [item["breakout_signal"], item["pullback_signal"]],
            ["BREAKOUT", "PULLBACK_CONTINUATION"],
            default="NONE",
        )
        item["eight_hour_score"] = np.where(
            trend, 20.0, np.where(item["close"] > item["ema_slow"], 11.0, 4.0)
        )
        item["relative_strength"] = item["rs"]
        item["rs_score"] = np.clip((item["rs"] * 100.0 + 2.0) * 2.5, 0.0, 10.0)
        item["four_hour_score"] = np.where(breakout, 25.0, np.where(pullback, 22.0, 0.0))
        item["momentum_score"] = np.clip((item["volume_ratio"] - 0.5) * 10.0, 0.0, 10.0)
        item["structure_score"] = np.where(item["trend_slope"] > 0.0, 10.0, 3.0)
        item["liquidity_score"] = np.clip(item["volume_ratio"] * 5.0, 0.0, 10.0)
        high60 = item["high"].rolling(60, min_periods=20).max().shift(1)
        low60 = item["low"].rolling(60, min_periods=20).min().shift(1)
        retracement = (high60 - item["close"]) / (high60 - low60)
        item["fib"] = np.select([retracement.between(0.382, 0.618)], [8.0], default=0.0)
        item.loc[retracement.between(0.236, 0.382) | retracement.between(0.618, 0.786), "fib"] = 4.0
        item.loc[retracement.gt(0.9), "fib"] = -5.0
        raw_stop = np.minimum(
            item["swing_low"] - item["atr"] * 0.25, item["close"] - item["atr"] * 2.8
        )
        distance = item["close"] - raw_stop
        item["stop_invalid"] = distance.gt(item["atr"] * 3.8)
        item["structure_reference"] = item["close"] - distance.clip(
            item["atr"] * 2.2, item["atr"] * 3.8
        )
        item["overextended"] = item["ema_distance_atr"].ge(3.5)
        item["higher_low"] = np.where(
            item["low"] > item["low"].rolling(8, min_periods=4).min().shift(1), item["low"], np.nan
        )
        item["structure_failure"] = (item["close"] < item["ema_fast"]) & (item["trend_slope"] < 0.0)
        item["eight_hour_weak"] = item["trend_slope"] < 0.0
        item["conviction_declined"] = False
        item["new_bullish_structure"] = item["trend_slope"] > 0.0
        item["crisis"] = False
        output.append(item.reset_index(drop=True))
    panel = pd.concat(output, ignore_index=True)
    panel["date"] = panel["bar_close_time"].dt.floor("D")
    environment = daily_btc.reset_index().rename(columns={daily_btc.index.name or "index": "date"})
    environment["date"] = pd.to_datetime(environment["date"], utc=True).dt.floor("D")
    panel = panel.merge(
        environment[
            [
                "date",
                "d1_score",
                "d1_multiplier",
                "btc_close",
                "btc_fast",
                "btc_slow",
                "btc_drawdown",
            ]
        ],
        on="date",
        how="left",
    )
    panel["d1_score"] = panel["d1_score"].fillna(2.0)
    panel["d1_multiplier"] = panel["d1_multiplier"].fillna(0.2)
    panel["score_no_fib"] = (
        panel["d1_score"]
        + panel["eight_hour_score"]
        + panel["rs_score"]
        + panel["four_hour_score"]
        + panel["momentum_score"]
        + panel["structure_score"]
        + panel["liquidity_score"]
    ).clip(0.0, 100.0)
    panel["score_soft_fib"] = (panel["score_no_fib"] + panel["fib"]).clip(0.0, 100.0)
    availability_copy = availability[["symbol", "tradable_from", "tradable_until"]].copy()
    for column in ("tradable_from", "tradable_until"):
        availability_copy[column] = pd.to_datetime(availability_copy[column], utc=True)
    panel = panel.merge(availability_copy, on="symbol", how="left")
    if panel[["tradable_from", "tradable_until"]].isna().any().any():
        raise Ed01Error("missing V4 availability")
    assert_boundary(panel)
    return panel.sort_values(["bar_open_time", "symbol"], kind="mergesort").reset_index(drop=True)


def _native_metrics(result: V5FoldResult) -> dict[str, Any]:
    trades = list(result.trades)
    pnls = np.asarray([trade.realised_pnl for trade in trades], dtype=float)
    returns = np.asarray([trade.return_fraction for trade in trades], dtype=float)
    wins, losses = pnls[pnls > 0], pnls[pnls < 0]
    gross_profit, gross_loss = float(wins.sum()), float(-losses.sum())
    curve = np.asarray([value for _, value in result.equity_curve], dtype=float)
    drawdown = float((1.0 - curve / np.maximum.accumulate(curve)).max()) if curve.size else 0.0
    net = result.final_cash / result.initial_capital - 1.0
    return {
        "initial_capital": result.initial_capital,
        "final_equity": result.final_cash,
        "net_return": net,
        "maximum_drawdown": drawdown,
        "calmar": net / drawdown if drawdown else None,
        "profit_factor": gross_profit / gross_loss
        if gross_loss
        else (99.0 if gross_profit else 0.0),
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
        "trade_count": len(trades),
        "trades_per_year": float(len(trades)),
        "win_rate": float((pnls > 0).mean()) if pnls.size else 0.0,
        "payoff_ratio": float(wins.mean() / -losses.mean()) if wins.size and losses.size else None,
        "expectancy": float(pnls.mean()) if pnls.size else 0.0,
        "expectancy_fraction": float(returns.mean()) if returns.size else 0.0,
        "mae_r": float(np.mean([trade.mae_r for trade in trades])) if trades else 0.0,
        "mfe_r": float(np.mean([trade.mfe_r for trade in trades])) if trades else 0.0,
        "total_fees": float(sum(fill.fee for fill in result.fills)),
        "turnover": float(sum(fill.notional for fill in result.fills)),
        "add_on_count": sum(fill.fill_type == "ADD_ON" for fill in result.fills),
        "reentry_count": sum(trade.reentry_sequence > 0 for trade in trades),
        "exit_counts": {
            name: sum(fill.fill_type == name for fill in result.fills)
            for name in (
                "STOP_EXIT",
                "TRAILING_EXIT",
                "STRUCTURE_EXIT",
                "STAGNATION_EXIT",
                "END_OF_FOLD_EXIT",
                "VENUE_EXIT",
            )
        },
        "candidate_signals": len(result.candidates),
        "accepted_entries": sum(fill.fill_type == "ENTRY" for fill in result.fills),
        "rejection_counts": dict(result.rejections),
        "reconciliation_status": result.reconciliation.status,
    }


def _jsonable(value: Any) -> Any:
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def serialise_fold(result: V5FoldResult) -> dict[str, Any]:
    accepted = [item for item in result.candidates if item.accepted]
    rejected_sample = [
        item
        for item in result.candidates
        if not item.accepted and item.rejection_reason is not None
    ][:100]
    return cast(
        dict[str, Any],
        _jsonable(
            {
                "fold_id": result.fold_id,
                "status": result.status,
                "metrics": _native_metrics(result),
                "candidate_ledger": [asdict(item) for item in accepted + rejected_sample],
                "candidate_ledger_scope": {
                    "stored": "ALL_ACCEPTED_PLUS_FIRST_100_REJECTED_DETERMINISTIC",
                    "total_candidates": len(result.candidates),
                    "accepted_candidates": len(accepted),
                    "sampled_rejected_candidates": len(rejected_sample),
                },
                "scheduled_entries": [asdict(item) for item in result.scheduled_entries],
                "fill_ledger": [asdict(item) for item in result.fills],
                "trade_ledger": [asdict(item) for item in result.trades],
                "reconciliation": asdict(result.reconciliation),
                "open_positions_after_fold": result.open_positions_after_fold,
            }
        ),
    )


def run_native(
    panel: pd.DataFrame,
    *,
    transaction_cost: float,
    allow_reentry: bool = True,
    allow_add_on: bool = True,
) -> dict[str, Any]:
    """Run V4 T12 alpha fields through the one audited Native event engine."""
    results: list[V5FoldResult] = []
    for fold_id, start, end in FOLDS:
        values = panel.loc[
            (panel["bar_open_time"] >= pd.Timestamp(start))
            & (panel["bar_open_time"] < pd.Timestamp(end))
        ].copy()
        results.append(
            simulate_native_fold(
                four_hour_panel=values,
                configuration=replace(T12_PARAMS, cost=transaction_cost),
                portfolio_profile=T12_PROFILE,
                selected_threshold=55,
                transaction_cost=transaction_cost,
                fold_id=fold_id,
                allow_reentry=allow_reentry,
                allow_add_on=allow_add_on,
            )
        )
    folds = [serialise_fold(item) for item in results]
    metrics = [item["metrics"] for item in folds]
    returns = [float(item["net_return"]) for item in metrics]
    return {
        "mode": "NATIVE_CORRECTED",
        "transaction_cost": transaction_cost,
        "switches": {"allow_reentry": allow_reentry, "allow_add_on": allow_add_on},
        "fold_results": folds,
        "aggregate": {
            "aggregate_compounded_return": float(np.prod([1 + item for item in returns]) - 1),
            "mean_maximum_drawdown": float(np.mean([item["maximum_drawdown"] for item in metrics])),
            "mean_profit_factor": float(np.mean([item["profit_factor"] for item in metrics])),
            "mean_win_rate": float(np.mean([item["win_rate"] for item in metrics])),
            "mean_payoff_ratio": float(
                np.mean(
                    [item["payoff_ratio"] for item in metrics if item["payoff_ratio"] is not None]
                )
            )
            if any(item["payoff_ratio"] is not None for item in metrics)
            else None,
            "mean_expectancy": float(np.mean([item["expectancy"] for item in metrics])),
            "mean_trades_per_year": float(np.mean([item["trades_per_year"] for item in metrics])),
            "total_trade_count": int(sum(item["trade_count"] for item in metrics)),
            "total_fees": float(sum(item["total_fees"] for item in metrics)),
            "total_turnover": float(sum(item["turnover"] for item in metrics)),
            "total_reentries": int(sum(item["reentry_count"] for item in metrics)),
            "total_add_ons": int(sum(item["add_on_count"] for item in metrics)),
            "positive_fold_ratio": float(np.mean([value > 0 for value in returns])),
            "worst_fold_return": float(min(returns)),
            "pnl_reconciliation": "PASS"
            if all(item["reconciliation_status"] == "PASS" for item in metrics)
            else "FAIL",
            "open_positions_after_fold": int(
                sum(item["open_positions_after_fold"] for item in folds)
            ),
        },
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
    }


def historical_snapshot(root: Path) -> dict[str, Any]:
    """Return immutable historical T12 ledger summary for transparent parity comparison."""
    trial = historical_trial(root)
    return {
        "mode": "LEGACY_PARITY_ARTIFACT_REPLAY",
        "historical_trial_sha256": file_sha256(
            root / "reports/research/ams-v4-ams-v4-t12-trial-v1.json"
        ),
        "aggregate": trial["aggregate"],
        "fold_results": trial["fold_results"],
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
    }


def trade_episode_attribution(report: Mapping[str, Any]) -> dict[str, Any]:
    trades = [trade for fold in report["fold_results"] for trade in fold["trade_ledger"]]
    episodes: dict[tuple[str, str | None], list[Mapping[str, Any]]] = defaultdict(list)
    for trade in trades:
        episodes[
            (str(trade["symbol"]), trade.get("original_position_id") or trade["position_id"])
        ].append(trade)
    rows = []
    for sequence, ((symbol, origin), values) in enumerate(sorted(episodes.items()), start=1):
        values = sorted(values, key=lambda item: item["entry_time"])
        if not any(int(item.get("reentry_sequence", 0)) > 0 for item in values):
            continue
        initial = values[0]
        reentries = [item for item in values if int(item.get("reentry_sequence", 0)) > 0]
        rows.append(
            {
                "trade_episode_id": f"ED01-E{sequence:05d}",
                "symbol": symbol,
                "original_position_id": origin,
                "initial_entry": initial["entry_time"],
                "initial_exit": initial["exit_time"],
                "reentry_count": len(reentries),
                "combined_net_pnl": float(sum(float(item["realised_pnl"]) for item in values)),
                "initial_pnl": float(initial["realised_pnl"]),
                "reentry_pnl": float(sum(float(item["realised_pnl"]) for item in reentries)),
                "maximum_mfe_r": float(max(float(item["mfe_r"]) for item in values)),
                "maximum_mae_r": float(min(float(item["mae_r"]) for item in values)),
            }
        )
    improved = sum(row["reentry_pnl"] > 0 for row in rows)
    return {
        "episodes": rows,
        "episode_count": len(rows),
        "improved_episodes": improved,
        "worse_episodes": len(rows) - improved,
    }


def fee_overlay(
    fills: Sequence[Mapping[str, Any]], initial_capital: float, fee_rates: Sequence[float]
) -> list[dict[str, float]]:
    """Apply a deterministic fee-only overlay to a fixed native fill sequence."""
    gross = initial_capital
    for fill in fills:
        sign = -1 if fill["fill_type"] in {"ENTRY", "ADD_ON"} else 1
        gross += sign * float(fill["notional"])
    rows = []
    turnover = float(sum(float(fill["notional"]) for fill in fills))
    for rate in fee_rates:
        final = gross - turnover * rate
        rows.append(
            {
                "fee_rate": float(rate),
                "final_equity": final,
                "net_return": final / initial_capital - 1.0,
                "fee_drag": turnover * rate,
            }
        )
    return rows


def regime_label(row: Mapping[str, Any], expanding_volatility: float) -> dict[str, str]:
    d1 = float(row.get("d1_score", 0.0))
    environment = (
        "STRONG_RISK_ON"
        if d1 >= 15
        else "RISK_ON"
        if d1 >= 12
        else "NEUTRAL"
        if d1 >= 9
        else "DEFENSIVE"
        if d1 >= 5
        else "CRISIS"
    )
    btc = (
        "BTC_UPTREND"
        if float(row.get("btc_close", 0))
        > float(row.get("btc_fast", math.inf))
        > float(row.get("btc_slow", -math.inf))
        else "BTC_DOWNTREND"
        if float(row.get("btc_close", 0)) < float(row.get("btc_slow", 0))
        else "BTC_RANGE"
    )
    volatility = (
        "HIGH_VOL"
        if expanding_volatility > 0.04
        else "LOW_VOL"
        if expanding_volatility < 0.015
        else "MEDIUM_VOL"
    )
    return {"daily_environment": environment, "btc_trend": btc, "volatility": volatility}
