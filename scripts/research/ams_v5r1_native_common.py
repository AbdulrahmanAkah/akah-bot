"""Neutral I/O and metrics helpers for AMS V5R1 research scripts."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from spotbot.research.ams_v5_native_engine import (
    V5FoldResult,
    V5Parameters,
    V5PortfolioProfile,
    build_features,
)

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "reports" / "research"
REGISTRATION = REPORTS / "ams-v3-4h-dataset-registration-v1.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"
    descriptor, temporary = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(text)
        os.replace(temporary, path)
    except BaseException:
        if os.path.exists(temporary):
            os.unlink(temporary)
        raise


def atomic_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(value)
        os.replace(temporary, path)
    except BaseException:
        if os.path.exists(temporary):
            os.unlink(temporary)
        raise


def load_registered_panel(
    symbols: Sequence[str] | None = None,
) -> tuple[pd.DataFrame, dict[str, str]]:
    registration = json.loads(REGISTRATION.read_text(encoding="utf-8"))
    datasets = registration["datasets"]
    hashes: dict[str, str] = {}
    frames: dict[str, pd.DataFrame] = {}
    for name in ("four_hour", "availability"):
        record = datasets[name]
        path = ROOT / record["path"]
        actual = sha256(path)
        if actual != record["file_sha256"]:
            raise RuntimeError(f"dataset hash mismatch: {name}")
        hashes[name] = actual
        frames[name] = pd.read_parquet(path)
    if symbols is not None:
        allowed = set(symbols)
        frames["four_hour"] = frames["four_hour"].loc[
            frames["four_hour"]["symbol"].isin(allowed)
        ]
        frames["availability"] = frames["availability"].loc[
            frames["availability"]["symbol"].isin(allowed)
        ]
    return build_features(frames["four_hour"], frames["availability"]), hashes


def metrics(result: V5FoldResult) -> dict[str, Any]:
    trades = list(result.trades)
    pnl = np.asarray([trade.realised_pnl for trade in trades], dtype=float)
    returns = np.asarray([trade.return_fraction for trade in trades], dtype=float)
    wins = pnl[pnl > 0]
    losses = pnl[pnl < 0]
    gross_profit = float(wins.sum()) if wins.size else 0.0
    gross_loss = float(-losses.sum()) if losses.size else 0.0
    profit_factor = (
        gross_profit / gross_loss if gross_loss > 0 else (99.0 if gross_profit > 0 else 0.0)
    )
    equity = np.asarray([value for _, value in result.equity_curve], dtype=float)
    if equity.size:
        peak = np.maximum.accumulate(equity)
        drawdowns = 1.0 - equity / peak
        maximum_drawdown = float(drawdowns.max())
        equity_returns = pd.Series(equity).pct_change().dropna()
    else:
        maximum_drawdown = 0.0
        equity_returns = pd.Series(dtype=float)
    net_return = result.final_cash / result.initial_capital - 1.0
    years = (
        max(
            (
                result.equity_curve[-1][0] - result.equity_curve[0][0]
            ).total_seconds()
            / (365.25 * 86400),
            1 / 365.25,
        )
        if len(result.equity_curve) > 1
        else 1.0
    )
    cagr = (1.0 + net_return) ** (1.0 / years) - 1.0 if net_return > -1 else -1.0
    downside = equity_returns[equity_returns < 0]
    sharpe = (
        float(equity_returns.mean() / equity_returns.std(ddof=1) * np.sqrt(365 * 6))
        if len(equity_returns) > 1 and equity_returns.std(ddof=1) > 0
        else None
    )
    sortino = (
        float(equity_returns.mean() / downside.std(ddof=1) * np.sqrt(365 * 6))
        if len(downside) > 1 and downside.std(ddof=1) > 0
        else None
    )
    average_win = float(wins.mean()) if wins.size else 0.0
    average_loss = float(-losses.mean()) if losses.size else 0.0
    fees = sum(fill.fee for fill in result.fills)
    turnover = sum(fill.notional for fill in result.fills)
    fill_counts = Counter(fill.fill_type for fill in result.fills)
    symbol_pnl: dict[str, float] = {}
    symbol_trades: dict[str, int] = {}
    for trade in trades:
        symbol_pnl[trade.symbol] = symbol_pnl.get(trade.symbol, 0.0) + trade.realised_pnl
        symbol_trades[trade.symbol] = symbol_trades.get(trade.symbol, 0) + 1
    positive_pnl = sum(max(value, 0.0) for value in symbol_pnl.values())
    concentration = (
        max((max(value, 0.0) for value in symbol_pnl.values()), default=0.0) / positive_pnl
        if positive_pnl > 0
        else 0.0
    )
    return {
        "initial_capital": result.initial_capital,
        "final_equity": result.final_cash,
        "net_return": net_return,
        "cagr": cagr,
        "maximum_drawdown": maximum_drawdown,
        "calmar": cagr / maximum_drawdown if maximum_drawdown > 0 else None,
        "sharpe": sharpe,
        "sortino": sortino,
        "profit_factor": profit_factor,
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
        "trade_count": len(trades),
        "trades_per_year": len(trades) / years,
        "win_rate": float((pnl > 0).mean()) if pnl.size else 0.0,
        "average_win": average_win,
        "average_loss": average_loss,
        "payoff_ratio": average_win / average_loss if average_loss > 0 else None,
        "expectancy": float(pnl.mean()) if pnl.size else 0.0,
        "expectancy_fraction": float(returns.mean()) if returns.size else 0.0,
        "median_trade": float(np.median(returns)) if returns.size else 0.0,
        "mae_r": float(np.mean([trade.mae_r for trade in trades])) if trades else 0.0,
        "mfe_r": float(np.mean([trade.mfe_r for trade in trades])) if trades else 0.0,
        "mfe_capture_ratio": float(
            np.mean(
                [
                    max(trade.realised_pnl, 0.0)
                    / max(
                        trade.mfe_r
                        * (trade.average_entry - result.candidates[0].structural_stop_reference)
                        * trade.quantity,
                        1e-12,
                    )
                    for trade in trades
                    if trade.mfe_r > 0 and result.candidates
                ]
            )
        )
        if trades
        else 0.0,
        "average_holding_bars": float(np.mean([trade.bars_held for trade in trades]))
        if trades
        else 0.0,
        "median_holding_bars": float(np.median([trade.bars_held for trade in trades]))
        if trades
        else 0.0,
        "turnover": turnover,
        "total_fees": fees,
        "add_on_count": fill_counts["ADD_ON"],
        "reentry_count": sum(trade.reentry_sequence > 0 for trade in trades),
        "stop_exits": fill_counts["STOP_EXIT"],
        "trailing_exits": fill_counts["TRAILING_EXIT"],
        "structure_exits": fill_counts["STRUCTURE_EXIT"],
        "stagnation_exits": fill_counts["STAGNATION_EXIT"],
        "venue_exits": fill_counts["VENUE_EXIT"],
        "end_of_fold_exits": fill_counts["END_OF_FOLD_EXIT"],
        "candidate_signals": len(result.candidates),
        "accepted_entries": fill_counts["ENTRY"],
        "rejection_counts": dict(result.rejections),
        "per_symbol_pnl": symbol_pnl,
        "per_symbol_trades": symbol_trades,
        "pnl_concentration_by_symbol": concentration,
        "reconciliation_status": result.reconciliation.status,
    }


def serialize_threshold(selection: Any) -> dict[str, Any]:
    return {
        "selected_threshold": selection.selected_threshold,
        "train_hash_sha256": selection.train_hash_sha256,
        "validation_inspected": selection.validation_inspected,
        "metrics_by_threshold": selection.metrics_by_threshold,
        "normalized_components": selection.normalized_components,
        "quality_scores": selection.quality_scores,
        "exclusions": selection.exclusions,
    }


def parameters_from_record(record: Mapping[str, Any]) -> V5Parameters:
    values = record["parameters"]
    return V5Parameters(
        str(record["configuration_id"]),
        str(values["entry_family"]),
        str(values["stop_model"]),
        str(values["fibonacci_mode"]),
    )


def profile_from_record(record: Mapping[str, Any]) -> V5PortfolioProfile:
    return V5PortfolioProfile(
        str(record["profile_id"]),
        float(record["base_risk"]),
        float(record["max_initial_risk"]),
        float(record["max_position_risk"]),
        float(record["max_heat"]),
        int(record["max_positions"]),
        int(record["max_cluster"]),
    )
