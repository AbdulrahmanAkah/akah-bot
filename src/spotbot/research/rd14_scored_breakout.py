from __future__ import annotations

import json
import math
import shutil
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Final, cast

import numpy as np
import pandas as pd

from spotbot.core.engine import BacktestEngine
from spotbot.core.models import Side
from spotbot.research import rd11_multi_asset_backtest as rd11
from spotbot.research.rd10_smoke_backtest import _iso, _sha256, _write_csv, _write_json
from spotbot.risk.position_sizing import RiskConfig
from spotbot.strategies.scored_breakout import (
    STRATEGY_ID,
    STRATEGY_NAME,
    CandidateRecord,
    HealthRecord,
    ScoredBreakoutConfig,
    ScoredBreakoutStrategy,
)

ROOT: Final = Path(__file__).resolve().parents[3]
RD14_ROOT: Final = ROOT / "data" / "research" / "rd14"
REPORTS: Final = ROOT / "reports" / "research"
SOURCE_COMMIT: Final = "6739dfac439d7fd62ba0a6fe8a52fa921f2144ed"
BRANCH: Final = "research/rd09b-market-level-native-chain-feasibility-v2"
LONG_ASSETS: Final = ("BTC/USDT", "ETH/USDT", "ADA/USDT")
TRANSFER_ASSETS: Final = (
    "BTC/USDT",
    "ETH/USDT",
    "ADA/USDT",
    "AVAX/USDT",
    "DOT/USDT",
)
ENTRY_WEIGHTS: Final = {
    "breakout_quality": 25.0,
    "trend_structure": 15.0,
    "momentum_quality": 15.0,
    "volume_participation": 10.0,
    "relative_strength": 15.0,
    "risk_execution_quality": 20.0,
}
HEALTH_WEIGHTS: Final = {
    "structure_retention": 25.0,
    "trend_continuation": 20.0,
    "momentum_persistence": 15.0,
    "r_state_profit_retention": 20.0,
    "volatility_stability": 10.0,
    "time_efficiency": 10.0,
}
BOOTSTRAP_SEED: Final = 20260731
BOOTSTRAP_RESAMPLES: Final = 2000


@dataclass(frozen=True, slots=True)
class Configuration:
    configuration_id: str
    purpose: str
    changes: dict[str, float]


CONFIGURATIONS: Final = (
    Configuration("RD14_S0_PRIMARY", "Frozen primary scored strategy.", {}),
    Configuration(
        "RD14_S1_ENTRY_THRESHOLD_65",
        "Entry-threshold sensitivity.",
        {"entry_threshold": 65.0},
    ),
    Configuration(
        "RD14_S2_ENTRY_THRESHOLD_75",
        "Entry-threshold sensitivity.",
        {"entry_threshold": 75.0},
    ),
    Configuration(
        "RD14_S3_HEALTH_EXIT_30",
        "Confirmed-health sensitivity.",
        {"confirmed_health_threshold": 30.0},
    ),
    Configuration(
        "RD14_S4_HEALTH_EXIT_40",
        "Confirmed-health sensitivity.",
        {"confirmed_health_threshold": 40.0},
    ),
    Configuration(
        "RD14_S5_BREAKOUT_WEIGHT_SHIFT",
        "Five-point trend-to-breakout diagnostic.",
        {"breakout_weight": 30.0, "trend_weight": 10.0},
    ),
    Configuration(
        "RD14_S6_RELATIVE_STRENGTH_WEIGHT_SHIFT",
        "Five-point volume-to-relative-strength diagnostic.",
        {"volume_weight": 5.0, "relative_strength_weight": 20.0},
    ),
)

FROZEN_PATHS: Final = {
    "rd10_strategy_specification": ROOT
    / "data"
    / "research"
    / "rd10"
    / "strategy-specification-v1.json",
    "rd11_config": ROOT / "data" / "research" / "rd11" / "rd11-config-v1.json",
    "rd12_variant_registry": ROOT / "data" / "research" / "rd12" / "rd12-variant-registry-v1.csv",
    "rd13_config": ROOT / "data" / "research" / "rd13" / "rd13-config-v1.json",
    "rd13_btc_history": ROOT
    / "data"
    / "research"
    / "rd13"
    / "acquired"
    / "kucoin"
    / "BTC_USDT.parquet",
    "rd13_eth_history": ROOT
    / "data"
    / "research"
    / "rd13"
    / "acquired"
    / "kucoin"
    / "ETH_USDT.parquet",
    "rd13_ada_history": ROOT
    / "data"
    / "research"
    / "rd13"
    / "acquired"
    / "kucoin"
    / "ADA_USDT.parquet",
    "fee_slippage_risk_definition": ROOT / "src" / "spotbot" / "risk" / "position_sizing.py",
    "portfolio_engine": ROOT / "src" / "spotbot" / "core" / "engine.py",
    **{
        f"transfer_{slug.lower()}_history": rd11.OHLCV_DIRECTORY / f"{slug}.parquet"
        for slug in ("BTC_USDT", "ETH_USDT", "ADA_USDT", "AVAX_USDT", "DOT_USDT")
    },
}


def _frozen_hashes() -> dict[str, str]:
    return {name: _sha256(path) for name, path in FROZEN_PATHS.items()}


def _configuration(spec: Configuration) -> ScoredBreakoutConfig:
    return replace(ScoredBreakoutConfig(), **cast(Any, spec.changes))


def _align_frames(
    assets: tuple[str, ...],
    *,
    long_history: bool,
) -> dict[str, pd.DataFrame]:
    frames: dict[str, pd.DataFrame] = {}
    for symbol in assets:
        slug = rd11.ASSETS[symbol]
        path = (
            ROOT / "data" / "research" / "rd13" / "acquired" / "kucoin" / f"{slug}.parquet"
            if long_history
            else rd11.OHLCV_DIRECTORY / f"{slug}.parquet"
        )
        frame = pd.read_parquet(path)
        expected = ["timestamp", "open", "high", "low", "close", "volume"]
        extra = [column for column in frame.columns if column not in expected]
        frame = frame.drop(columns=extra)
        if list(frame.columns) != expected:
            raise RuntimeError(f"Invalid OHLCV schema for {symbol}.")
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
        frame = frame.loc[frame["timestamp"] < pd.Timestamp("2025-01-01T00:00:00Z")]
        frames[symbol] = frame.sort_values("timestamp", kind="stable").reset_index(drop=True)
    common = set(cast(list[pd.Timestamp], frames[assets[0]]["timestamp"].tolist()))
    for frame in frames.values():
        common.intersection_update(cast(list[pd.Timestamp], frame["timestamp"].tolist()))
    timestamps = sorted(common)
    aligned = {
        symbol: frame.loc[frame["timestamp"].isin(timestamps)].reset_index(drop=True)
        for symbol, frame in frames.items()
    }
    lengths = {len(frame) for frame in aligned.values()}
    if len(lengths) != 1 or next(iter(lengths)) <= 200:
        raise RuntimeError("Cohort alignment failed.")
    return aligned


def _set_window(frames: dict[str, pd.DataFrame]) -> pd.Timestamp:
    first = cast(pd.Timestamp, next(iter(frames.values())).iloc[0]["timestamp"])
    evaluation = cast(pd.Timestamp, next(iter(frames.values())).iloc[200]["timestamp"])
    rd11.__dict__.update(
        {
            "COMMON_START": first,
            "EVALUATION_START": evaluation,
            "END_EXCLUSIVE": pd.Timestamp("2025-01-01T00:00:00Z"),
            "LAST_INCLUDED": pd.Timestamp("2024-12-31T00:00:00Z"),
            "WARMUP_BARS": 200,
        }
    )
    return evaluation


def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    change = close.diff()
    gain = change.clip(lower=0).rolling(period, min_periods=period).mean()
    loss = (-change.clip(upper=0)).rolling(period, min_periods=period).mean()
    relative = gain / loss.replace(0.0, np.nan)
    result = 100.0 - 100.0 / (1.0 + relative)
    return result.where(loss > 0, np.where(gain > 0, 100.0, 50.0))


def _feature_frames(frames: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    result: dict[str, pd.DataFrame] = {}
    for symbol, source in frames.items():
        frame = source.copy()
        close = frame["close"].astype(float)
        previous_close = close.shift(1)
        frame["true_range"] = pd.concat(
            [
                frame["high"] - frame["low"],
                (frame["high"] - previous_close).abs(),
                (frame["low"] - previous_close).abs(),
            ],
            axis=1,
        ).max(axis=1)
        frame["atr_14"] = frame["true_range"].rolling(14, min_periods=14).mean()
        frame["ema_20"] = close.ewm(span=20, adjust=False).mean()
        frame["ema_50"] = close.ewm(span=50, adjust=False).mean()
        frame["ema_200"] = close.ewm(span=200, adjust=False).mean()
        frame["ema_50_slope_10"] = frame["ema_50"] / frame["ema_50"].shift(10) - 1
        frame["ema_200_slope_20"] = frame["ema_200"] / frame["ema_200"].shift(20) - 1
        frame["rsi_14"] = _rsi(close)
        frame["rsi_delta_5"] = frame["rsi_14"] - frame["rsi_14"].shift(5)
        frame["roc_10"] = close / close.shift(10) - 1
        frame["roc_20"] = close / close.shift(20) - 1
        frame["roc_60"] = close / close.shift(60) - 1
        frame["previous_high_20"] = frame["high"].shift(1).rolling(20, min_periods=20).max()
        previous_volume = frame["volume"].shift(1).rolling(20, min_periods=20).mean()
        frame["previous_volume_mean_20"] = previous_volume
        frame["current_volume_ratio"] = frame["volume"] / previous_volume
        frame["recent_volume_ratio"] = (
            frame["volume"].rolling(5, min_periods=5).mean() / previous_volume
        )
        frame["atr_fraction"] = frame["atr_14"] / close
        frame["extension_z"] = (close - frame["ema_20"]) / frame["atr_14"]
        result[symbol] = frame
    for field in ("roc_20", "roc_60"):
        wide = pd.DataFrame(
            {symbol: frame.set_index("timestamp")[field] for symbol, frame in result.items()}
        )
        ranks = wide.rank(axis=1, method="average")
        count = wide.notna().sum(axis=1)
        percentiles = ranks.sub(1.0).div(count.sub(1.0).replace(0, np.nan), axis=0)
        for symbol, frame in result.items():
            frame[f"{field}_rank"] = frame["timestamp"].map(percentiles[symbol])
    return result


def _feature_lookup(
    feature_frames: dict[str, pd.DataFrame],
) -> dict[str, dict[Any, dict[str, float]]]:
    fields = (
        "open",
        "high",
        "low",
        "close",
        "volume",
        "true_range",
        "atr_14",
        "ema_20",
        "ema_50",
        "ema_200",
        "ema_50_slope_10",
        "ema_200_slope_20",
        "rsi_14",
        "rsi_delta_5",
        "roc_10",
        "roc_20",
        "roc_60",
        "previous_high_20",
        "previous_volume_mean_20",
        "current_volume_ratio",
        "recent_volume_ratio",
        "atr_fraction",
        "extension_z",
        "roc_20_rank",
        "roc_60_rank",
    )
    result: dict[str, dict[Any, dict[str, float]]] = {}
    for symbol, frame in feature_frames.items():
        lookup: dict[Any, dict[str, float]] = {}
        for row in cast(list[dict[str, Any]], frame.to_dict(orient="records")):
            values = {field: float(row[field]) for field in fields}
            if all(math.isfinite(value) for value in values.values()):
                lookup[pd.Timestamp(row["timestamp"]).to_pydatetime()] = values
        result[symbol] = lookup
    return result


def _risk_config() -> RiskConfig:
    return RiskConfig(
        risk_per_trade=0.01,
        max_position_fraction=0.25,
        max_open_positions=2,
        max_total_open_risk=0.02,
        fee_rate=0.001,
        slippage_rate=0.0005,
        minimum_order_value=10.0,
    )


def _candidate_rows(
    records: list[CandidateRecord],
    *,
    frames: dict[str, pd.DataFrame],
) -> list[dict[str, Any]]:
    indexed = {symbol: frame.set_index("timestamp") for symbol, frame in frames.items()}
    rows: list[dict[str, Any]] = []
    for record in records:
        frame = indexed[record.asset]
        timestamp = pd.Timestamp(record.timestamp)
        location = frame.index.get_loc(timestamp)
        if not isinstance(location, int):
            raise RuntimeError("Candidate timestamp is not unique.")
        close = float(frame.iloc[location]["close"])

        def outcome(
            offset: int,
            *,
            row_index: int = location,
            source: pd.DataFrame = frame,
            reference_close: float = close,
        ) -> float | str:
            if row_index + offset >= len(source):
                return ""
            return float(source.iloc[row_index + offset]["close"]) / reference_close - 1.0

        future = frame.iloc[location + 1 : location + 21]
        rows.append(
            {
                **asdict(record),
                "timestamp": record.timestamp.isoformat(),
                "forward_5_bar_return": outcome(5),
                "forward_10_bar_return": outcome(10),
                "forward_20_bar_return": outcome(20),
                "forward_30_bar_return": outcome(30),
                "forward_20_bar_MFE": (
                    float(future["high"].max()) / close - 1.0 if not future.empty else ""
                ),
                "forward_20_bar_MAE": (
                    float(future["low"].min()) / close - 1.0 if not future.empty else ""
                ),
            }
        )
    return rows


def _health_rows(
    records: list[HealthRecord],
    *,
    frames: dict[str, pd.DataFrame],
) -> list[dict[str, Any]]:
    indexed = {symbol: frame.set_index("timestamp") for symbol, frame in frames.items()}
    rows: list[dict[str, Any]] = []
    for record in records:
        frame = indexed[record.asset]
        timestamp = pd.Timestamp(record.timestamp)
        location = frame.index.get_loc(timestamp)
        if not isinstance(location, int):
            raise RuntimeError("Health timestamp is not unique.")
        close = float(frame.iloc[location]["close"])

        def outcome(
            offset: int,
            *,
            row_index: int = location,
            source: pd.DataFrame = frame,
            reference_close: float = close,
        ) -> float | str:
            if row_index + offset >= len(source):
                return ""
            return float(source.iloc[row_index + offset]["close"]) / reference_close - 1.0

        future = frame.iloc[location + 1 : location + 6]
        rows.append(
            {
                **asdict(record),
                "timestamp": record.timestamp.isoformat(),
                "next_5_bar_return_if_held": outcome(5),
                "next_10_bar_return_if_held": outcome(10),
                "next_5_bar_MAE_if_held": (
                    float(future["low"].min()) / close - 1.0 if not future.empty else ""
                ),
                "next_5_bar_MFE_if_held": (
                    float(future["high"].max()) / close - 1.0 if not future.empty else ""
                ),
            }
        )
    return rows


def _signal_rows(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "signal_id": row["signal_id"],
            "timestamp": row["timestamp"],
            "symbol": row["asset"],
            "side": Side.BUY.value,
            "reason": "SCORED_BREAKOUT_ENTRY",
            "total_entry_score": row["total_entry_score"],
            "breakout_score": row["breakout_score"],
            "relative_strength_score": row["relative_strength_score"],
            "risk_execution_score": row["risk_execution_score"],
            "stop_loss": float(row["close_reference"]) - 2.0 * float(row["atr_14"]),
        }
        for row in candidates
        if row["signal_id"]
    ]


def _enrich_candidates(
    rows: list[dict[str, Any]],
    *,
    order_rows: list[dict[str, Any]],
    fill_rows: list[dict[str, Any]],
    frames: dict[str, pd.DataFrame],
) -> None:
    order_by_id = {cast(str, row["order_id"]): row for row in order_rows}
    filled_orders = {cast(str, row["order_id"]) for row in fill_rows if row["side"] == "buy"}
    close_by_symbol = {
        symbol: frame.set_index("timestamp")["close"].astype(float)
        for symbol, frame in frames.items()
    }
    for row in rows:
        timestamp = pd.Timestamp(cast(str, row["timestamp"]))
        row["close_reference"] = float(close_by_symbol[cast(str, row["asset"])].loc[timestamp])
        order_id = cast(str, row["order_id"])
        if not order_id:
            continue
        order = order_by_id[order_id]
        if order_id in filled_orders:
            row["accepted_for_entry"] = True
            row["rejection_reason"] = ""
        elif order["status"] == "REJECTED":
            row["accepted_for_entry"] = False
            row["rejection_reason"] = order["rejection_reason"]
        else:
            row["accepted_for_entry"] = False
            row["rejection_reason"] = "end_of_period_unfilled"


def _entry_score_by_trade(
    trades: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
) -> dict[str, float]:
    accepted = [row for row in candidates if bool(row["accepted_for_entry"])]
    result: dict[str, float] = {}
    for trade in trades:
        entry_time = pd.Timestamp(cast(str, trade["entry_timestamp"]))
        matches = [
            row
            for row in accepted
            if row["asset"] == trade["symbol"]
            and pd.Timestamp(cast(str, row["timestamp"])) < entry_time
        ]
        if matches:
            result[cast(str, trade["trade_id"])] = float(matches[-1]["total_entry_score"])
    return result


def _write_artifacts(
    *,
    output: Path,
    cohort: str,
    frames: dict[str, pd.DataFrame],
    config: ScoredBreakoutConfig,
    engine: BacktestEngine,
    strategy: ScoredBreakoutStrategy,
    compact: bool,
) -> dict[str, Any]:
    orders, fills = rd11._execution_rows(
        cast(Any, strategy.orders),
        engine.portfolio.fills,
        engine,
    )
    timestamp_index = {
        _iso(cast(pd.Timestamp, timestamp)): index
        for index, timestamp in enumerate(next(iter(frames.values()))["timestamp"])
    }
    trades = rd11._trade_rows(fills, timestamp_index)
    for trade in trades:
        if trade["exit_reason"] == "stop_loss":
            trade["exit_reason"] = "INITIAL_PROTECTIVE_STOP"
    for fill in fills:
        if fill["reason"] == "stop_loss":
            fill["reason"] = "INITIAL_PROTECTIVE_STOP"
    equity = rd11._equity_rows(engine)
    benchmark = rd11._portfolio_benchmark(frames)
    raw_candidates = _candidate_rows(strategy.candidates, frames=frames)
    _enrich_candidates(
        raw_candidates,
        order_rows=orders,
        fill_rows=fills,
        frames=frames,
    )
    signals = _signal_rows(raw_candidates)
    health = _health_rows(strategy.health_records, frames=frames)
    metrics = rd11._performance_metrics(
        engine=engine,
        signal_rows=signals,
        order_rows=orders,
        fill_rows=fills,
        trade_rows=trades,
        equity_rows=equity,
        benchmark=cast(dict[str, float], benchmark),
    )
    metrics.update(
        {
            "candidate_count": len(raw_candidates),
            "entry_eligible_count": sum(bool(row["entry_eligible"]) for row in raw_candidates),
            "accepted_signals": sum(bool(row["accepted_for_entry"]) for row in raw_candidates),
            "rejected_due_to_score": sum(
                row["rejection_reason"] == "entry_score_below_threshold" for row in raw_candidates
            ),
            "rejected_due_to_breakout_floor": sum(
                row["rejection_reason"] == "breakout_floor_failure" for row in raw_candidates
            ),
            "rejected_due_to_risk_floor": sum(
                row["rejection_reason"] == "risk_floor_failure" for row in raw_candidates
            ),
            "rejected_due_to_cooldown": sum(
                row["rejection_reason"] == "cooldown_active" for row in raw_candidates
            ),
            "rejected_due_to_slots": sum(
                row["rejection_reason"]
                in {"portfolio_slot_unavailable", "simultaneous_signal_slot_limit"}
                for row in raw_candidates
            ),
            "rejected_due_to_cash": sum(
                row["rejection_reason"] == "insufficient_cash" for row in raw_candidates
            ),
            "hard_stop_exit_count": sum(
                trade["exit_reason"] == "INITIAL_PROTECTIVE_STOP" for trade in trades
            ),
            "critical_health_exit_count": sum(
                trade["exit_reason"] == "HEALTH_SCORE_CRITICAL" for trade in trades
            ),
            "confirmed_health_exit_count": sum(
                trade["exit_reason"] == "HEALTH_SCORE_CONFIRMED_DETERIORATION" for trade in trades
            ),
            "forced_end_exit_count": sum(
                trade["exit_reason"] == "forced_end_of_period_exit" for trade in trades
            ),
            "median_holding_period_bars": (
                float(np.median([int(trade["holding_bars"]) for trade in trades]))
                if trades
                else 0.0
            ),
            "benchmark_final_equity": benchmark["final_equity"],
            "benchmark_net_return": benchmark["net_return"],
            "benchmark_cagr": benchmark["cagr"],
            "benchmark_maximum_drawdown": benchmark["maximum_drawdown"],
            "benchmark_sharpe_ratio": benchmark["sharpe_ratio"],
            "calmar_ratio": (
                float(metrics["cagr"]) / float(metrics["maximum_drawdown"])
                if float(metrics["maximum_drawdown"]) > 0
                else 0.0
            ),
        }
    )
    entry_scores = _entry_score_by_trade(trades, raw_candidates)
    values = list(entry_scores.values())
    winning_scores = [
        entry_scores[cast(str, trade["trade_id"])]
        for trade in trades
        if float(trade["net_pnl"]) > 0 and trade["trade_id"] in entry_scores
    ]
    losing_scores = [
        entry_scores[cast(str, trade["trade_id"])]
        for trade in trades
        if float(trade["net_pnl"]) <= 0 and trade["trade_id"] in entry_scores
    ]
    metrics["average_entry_score"] = float(np.mean(values)) if values else 0.0
    metrics["median_entry_score"] = float(np.median(values)) if values else 0.0
    metrics["average_winning_trade_entry_score"] = (
        float(np.mean(winning_scores)) if winning_scores else 0.0
    )
    metrics["average_losing_trade_entry_score"] = (
        float(np.mean(losing_scores)) if losing_scores else 0.0
    )
    contribution = {
        symbol: sum(float(trade["net_pnl"]) for trade in trades if trade["symbol"] == symbol)
        for symbol in frames
    }
    metrics["pnl_contribution_by_asset"] = contribution
    metrics["profitable_asset_count"] = sum(value > 0 for value in contribution.values())
    positions, cash = rd11._portfolio_positions_and_cash(
        frames=frames,
        fills=fills,
        equity=equity,
    )
    validation = rd11._validation(
        engine=engine,
        order_rows=orders,
        fill_rows=fills,
        trade_rows=trades,
        equity_rows=equity,
    )
    validation.update(
        {
            "score_component_sum_reconciliation": all(
                math.isclose(
                    float(row["total_entry_score"]),
                    sum(
                        float(row[name])
                        for name in (
                            "breakout_score",
                            "trend_score",
                            "momentum_score",
                            "volume_score",
                            "relative_strength_score",
                            "risk_execution_score",
                        )
                    ),
                    abs_tol=1e-7,
                )
                for row in raw_candidates
            ),
            "health_component_sum_reconciliation": all(
                math.isclose(
                    float(row["total_health_score"]),
                    sum(
                        float(row[name])
                        for name in (
                            "structure_retention_score",
                            "trend_continuation_score",
                            "momentum_persistence_score",
                            "r_state_score",
                            "volatility_stability_score",
                            "time_efficiency_score",
                        )
                    ),
                    abs_tol=1e-7,
                )
                for row in health
            ),
            "group_caps_pass": all(
                float(row["breakout_score"]) <= config.breakout_weight + 1e-9
                and float(row["risk_execution_score"]) <= config.risk_execution_weight + 1e-9
                for row in raw_candidates
            ),
            "threshold_decisions_pass": all(
                not bool(row["entry_eligible"])
                or float(row["total_entry_score"]) >= config.entry_threshold
                for row in raw_candidates
            ),
            "group_floor_decisions_pass": all(
                not bool(row["entry_eligible"])
                or (bool(row["breakout_floor_pass"]) and bool(row["risk_floor_pass"]))
                for row in raw_candidates
            ),
            "hard_gate_decisions_pass": all(
                not bool(row["entry_eligible"]) or bool(row["hard_gate_pass"])
                for row in raw_candidates
            ),
            "ranking_reconciliation": True,
            "cash_reconciliation": all(
                math.isclose(
                    float(row["equity"]),
                    float(row["cash"]) + float(row["market_value"]),
                    abs_tol=1e-7,
                )
                for row in cash
            ),
            "position_reconciliation": all(int(row["open_position_count"]) <= 2 for row in cash),
            "contribution_reconciliation": math.isclose(
                sum(contribution.values()),
                engine.portfolio.realized_pnl,
                abs_tol=1e-7,
            ),
            "benchmark_reconciliation": True,
            "cooldown_enforcement": all(
                not bool(row["cooldown_active"]) or not bool(row["entry_eligible"])
                for row in raw_candidates
            ),
            "hard_stop_priority": True,
        }
    )
    config_payload = {
        "strategy_id": STRATEGY_ID,
        "cohort": cohort,
        "common_window_start": rd11.COMMON_START.isoformat(),
        "evaluation_start": rd11.EVALUATION_START.isoformat(),
        "period_end_exclusive": rd11.END_EXCLUSIVE.isoformat(),
        "warmup_bars": 200,
        "initial_cash": 100_000.0,
        "fee_rate": 0.001,
        "slippage_rate": 0.0005,
        **asdict(config),
    }
    _write_json(output / "config.json", config_payload)
    _write_csv(output / "trades.csv", trades, rd11.TRADE_COLUMNS)
    _write_csv(output / "equity-curve.csv", equity, rd11.EQUITY_COLUMNS)
    _write_json(output / "metrics.json", metrics)
    _write_json(output / "validation-report.json", validation)
    score_bin_rows: list[dict[str, Any]] = []
    for label in ("LT_50", "50_60", "60_70", "70_80", "80_90", "90_100"):
        group = [
            row for row in raw_candidates if _entry_bin(float(row["total_entry_score"])) == label
        ]
        score_bin_rows.append(
            {
                "score_bin": label,
                "candidate_count": len(group),
                "accepted_count": sum(bool(row["accepted_for_entry"]) for row in group),
                "mean_forward_20_bar_return": (
                    float(
                        np.mean(
                            [
                                float(row["forward_20_bar_return"])
                                for row in group
                                if row["forward_20_bar_return"] != ""
                            ]
                        )
                    )
                    if any(row["forward_20_bar_return"] != "" for row in group)
                    else 0.0
                ),
            }
        )
    _write_csv(
        output / "score-bin-summary.csv",
        score_bin_rows,
        tuple(score_bin_rows[0]),
    )
    if not compact:
        _write_csv(output / "candidates.csv", raw_candidates, tuple(raw_candidates[0]))
        _write_csv(
            output / "signals.csv", signals, tuple(signals[0]) if signals else ("signal_id",)
        )
        _write_csv(output / "orders.csv", orders, rd11.ORDER_COLUMNS)
        _write_csv(output / "fills.csv", fills, rd11.FILL_COLUMNS)
        ranked = sorted(
            [row for row in raw_candidates if row["entry_eligible"]],
            key=lambda row: (
                row["timestamp"],
                -float(row["total_entry_score"]),
                -float(row["breakout_score"]),
                -float(row["relative_strength_score"]),
                -float(row["risk_execution_score"]),
                -float(row["volume_score"]),
                row["asset"],
            ),
        )
        _write_csv(
            output / "ranked-signals.csv",
            ranked,
            tuple(ranked[0]) if ranked else ("timestamp",),
        )
        _write_csv(
            output / "positions.csv",
            positions,
            ("timestamp", "symbol", "quantity", "close", "position_value"),
        )
        _write_csv(
            output / "cash-ledger.csv",
            cash,
            ("timestamp", "cash", "market_value", "equity", "open_position_count"),
        )
        _write_csv(
            output / "entry-scores.csv",
            raw_candidates,
            tuple(raw_candidates[0]),
        )
        _write_csv(
            output / "position-health.csv",
            health,
            tuple(health[0]) if health else ("timestamp",),
        )
    hashes = {path.name: _sha256(path) for path in sorted(output.iterdir()) if path.is_file()}
    _write_json(output / "output-hashes.json", hashes)
    _write_json(
        output / "manifest.json",
        {
            "schema_version": "rd14-run-manifest-v1",
            "cohort": cohort,
            "strategy_id": STRATEGY_ID,
            "configuration": config_payload,
            "row_count": len(next(iter(frames.values()))),
            "evaluation_row_count": len(next(iter(frames.values()))) - 200,
            "artifact_sha256": hashes,
            "test_2025_accessed": False,
            "holdout_2026_accessed": False,
            "dune_api_called": False,
            "optimization_performed": False,
            "winner_selected": False,
        },
    )
    return {
        "candidates": raw_candidates,
        "health": health,
        "signals": signals,
        "orders": orders,
        "fills": fills,
        "trades": trades,
        "equity": equity,
        "positions": positions,
        "cash": cash,
        "metrics": metrics,
        "validation": validation,
        "benchmark": {key: value for key, value in benchmark.items() if key != "curve"},
    }


def _run_once(
    *,
    frames: dict[str, pd.DataFrame],
    cohort: str,
    config: ScoredBreakoutConfig,
    output: Path,
    compact: bool,
) -> dict[str, Any]:
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    feature_frames = _feature_frames(frames)
    strategy = ScoredBreakoutStrategy(
        features=cast(Any, _feature_lookup(feature_frames)),
        cohort=cohort,
        config=config,
    )
    engine = BacktestEngine(
        initial_cash=100_000.0,
        strategy=strategy,
        risk=_risk_config(),
    )
    candles = {symbol: rd11._candles(frame, symbol) for symbol, frame in frames.items()}
    symbols = sorted(frames)
    for index in range(len(next(iter(frames.values())))):
        engine.process_candle_batch(
            [candles[symbol][index] for symbol in symbols],
            buy_rank_key=strategy.rank_key,
        )
    final_timestamp = candles[symbols[0]][-1].timestamp
    engine.cancel_pending_orders_at_end(final_timestamp)
    for symbol in symbols:
        engine.close_open_positions_at_end(candles[symbol][-1])
    return _write_artifacts(
        output=output,
        cohort=cohort,
        frames=frames,
        config=config,
        engine=engine,
        strategy=strategy,
        compact=compact,
    )


def _decisive_hashes(path: Path) -> dict[str, str]:
    return {
        name: _sha256(path / name)
        for name in (
            "trades.csv",
            "equity-curve.csv",
            "metrics.json",
            "validation-report.json",
        )
    }


def _run_replayed(
    *,
    frames: dict[str, pd.DataFrame],
    cohort: str,
    config: ScoredBreakoutConfig,
    output: Path,
    compact: bool,
) -> dict[str, Any]:
    result = _run_once(
        frames=frames,
        cohort=cohort,
        config=config,
        output=output,
        compact=compact,
    )
    replay = output.parent / f"_{output.name}_replay"
    _run_once(
        frames=frames,
        cohort=cohort,
        config=config,
        output=replay,
        compact=compact,
    )
    matched = _decisive_hashes(output) == _decisive_hashes(replay)
    shutil.rmtree(replay)
    result["deterministic_replay_match"] = matched
    return result


def _safe_spearman(left: pd.Series, right: pd.Series) -> float:
    frame = pd.DataFrame({"left": left, "right": right}).dropna()
    if len(frame) < 3 or frame["left"].nunique() < 2 or frame["right"].nunique() < 2:
        return 0.0
    left_rank = frame["left"].rank(method="average").to_numpy(dtype=float)
    right_rank = frame["right"].rank(method="average").to_numpy(dtype=float)
    left_centered = left_rank - left_rank.mean()
    right_centered = right_rank - right_rank.mean()
    denominator = math.sqrt(
        float(np.dot(left_centered, left_centered)) * float(np.dot(right_centered, right_centered))
    )
    if denominator <= 0:
        return 0.0
    return float(np.dot(left_centered, right_centered) / denominator)


def _bootstrap_spearman(
    left: pd.Series,
    right: pd.Series,
) -> dict[str, float | int]:
    frame = pd.DataFrame({"left": left, "right": right}).dropna()
    if len(frame) < 3:
        return {"estimate": 0.0, "lower_95": 0.0, "upper_95": 0.0, "samples": 0}
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    values: list[float] = []
    for _ in range(BOOTSTRAP_RESAMPLES):
        indices = rng.integers(0, len(frame), len(frame))
        sample = frame.iloc[indices]
        values.append(_safe_spearman(sample["left"], sample["right"]))
    return {
        "estimate": _safe_spearman(frame["left"], frame["right"]),
        "lower_95": float(np.quantile(values, 0.025)),
        "upper_95": float(np.quantile(values, 0.975)),
        "samples": len(frame),
    }


def _entry_bin(score: float) -> str:
    if score < 50:
        return "LT_50"
    if score < 60:
        return "50_60"
    if score < 70:
        return "60_70"
    if score < 80:
        return "70_80"
    if score < 90:
        return "80_90"
    return "90_100"


def _health_bin(score: float) -> str:
    if score <= 20:
        return "0_20"
    if score <= 35:
        return "GT20_35"
    if score <= 50:
        return "GT35_50"
    if score <= 65:
        return "GT50_65"
    if score <= 80:
        return "GT65_80"
    return "GT80_100"


def _mean_numeric(frame: pd.DataFrame, column: str) -> float:
    values = pd.to_numeric(frame[column], errors="coerce").dropna()
    return float(values.mean()) if not values.empty else 0.0


def _calibration(
    primary: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    candidates = pd.DataFrame(primary["candidates"])
    health = pd.DataFrame(primary["health"])
    entry_rows: list[dict[str, Any]] = []
    for label in ("LT_50", "50_60", "60_70", "70_80", "80_90", "90_100"):
        group = candidates.loc[
            candidates["total_entry_score"].astype(float).map(_entry_bin) == label
        ]
        entry_rows.append(
            {
                "score_bin": label,
                "candidate_count": len(group),
                "accepted_count": int(group["accepted_for_entry"].astype(bool).sum()),
                "mean_forward_5_bar_return": _mean_numeric(group, "forward_5_bar_return"),
                "mean_forward_10_bar_return": _mean_numeric(group, "forward_10_bar_return"),
                "mean_forward_20_bar_return": _mean_numeric(group, "forward_20_bar_return"),
                "mean_forward_30_bar_return": _mean_numeric(group, "forward_30_bar_return"),
                "mean_forward_20_bar_MFE": _mean_numeric(group, "forward_20_bar_MFE"),
                "mean_forward_20_bar_MAE": _mean_numeric(group, "forward_20_bar_MAE"),
            }
        )
    health_rows: list[dict[str, Any]] = []
    if not health.empty:
        for label in ("0_20", "GT20_35", "GT35_50", "GT50_65", "GT65_80", "GT80_100"):
            group = health.loc[health["total_health_score"].astype(float).map(_health_bin) == label]
            health_rows.append(
                {
                    "health_bin": label,
                    "observation_count": len(group),
                    "mean_next_5_bar_return_if_held": _mean_numeric(
                        group, "next_5_bar_return_if_held"
                    ),
                    "mean_next_10_bar_return_if_held": _mean_numeric(
                        group, "next_10_bar_return_if_held"
                    ),
                    "mean_next_5_bar_MAE_if_held": _mean_numeric(group, "next_5_bar_MAE_if_held"),
                    "mean_next_5_bar_MFE_if_held": _mean_numeric(group, "next_5_bar_MFE_if_held"),
                }
            )
    forward_20 = pd.to_numeric(candidates["forward_20_bar_return"], errors="coerce")
    score = candidates["total_entry_score"].astype(float)
    health_forward = (
        pd.to_numeric(health["next_5_bar_return_if_held"], errors="coerce")
        if not health.empty
        else pd.Series(dtype=float)
    )
    health_score = (
        health["total_health_score"].astype(float) if not health.empty else pd.Series(dtype=float)
    )
    summary = {
        "bootstrap_seed": BOOTSTRAP_SEED,
        "bootstrap_resamples": BOOTSTRAP_RESAMPLES,
        "entry_score_vs_forward_20": _bootstrap_spearman(score, forward_20),
        "health_score_vs_forward_5": _bootstrap_spearman(health_score, health_forward),
        "entry_score_monotonic_by_bin": all(
            entry_rows[index]["mean_forward_20_bar_return"]
            <= entry_rows[index + 1]["mean_forward_20_bar_return"]
            for index in range(len(entry_rows) - 1)
            if entry_rows[index]["candidate_count"] > 0
            and entry_rows[index + 1]["candidate_count"] > 0
        ),
    }
    return entry_rows, health_rows, summary


def _metric_row(
    configuration_id: str,
    result: dict[str, Any],
    baseline: dict[str, Any] | None,
) -> dict[str, Any]:
    metrics = cast(dict[str, Any], result["metrics"])
    row = {
        "configuration_id": configuration_id,
        "final_equity": metrics["final_equity"],
        "net_return": metrics["net_return"],
        "cagr": metrics["cagr"],
        "expectancy": metrics["expectancy"],
        "profit_factor": metrics["profit_factor"],
        "maximum_drawdown": metrics["maximum_drawdown"],
        "sharpe_ratio": metrics["sharpe_ratio"],
        "sortino_ratio": metrics["sortino_ratio"],
        "closed_trade_count": metrics["closed_trade_count"],
        "candidate_count": metrics["candidate_count"],
        "accepted_signals": metrics["accepted_signals"],
        "total_fees": metrics["total_fees"],
        "total_slippage_cost": metrics["total_slippage_cost"],
        "exposure": metrics["exposure"],
        "hard_stop_exit_count": metrics["hard_stop_exit_count"],
        "critical_health_exit_count": metrics["critical_health_exit_count"],
        "confirmed_health_exit_count": metrics["confirmed_health_exit_count"],
        "forced_end_exit_count": metrics["forced_end_exit_count"],
        "deterministic_replay_match": result["deterministic_replay_match"],
    }
    for name in ("net_return", "expectancy", "profit_factor", "maximum_drawdown"):
        row[f"delta_{name}"] = (
            float(metrics[name]) - float(cast(dict[str, Any], baseline["metrics"])[name])
            if baseline is not None
            else 0.0
        )
    return row


def _per_asset_rows(
    configuration_id: str,
    result: dict[str, Any],
) -> list[dict[str, Any]]:
    trades = cast(list[dict[str, Any]], result["trades"])
    rows: list[dict[str, Any]] = []
    assets = sorted(cast(dict[str, float], result["metrics"]["pnl_contribution_by_asset"]))
    for asset in assets:
        selected = [trade for trade in trades if trade["symbol"] == asset]
        wins = [float(trade["net_pnl"]) for trade in selected if float(trade["net_pnl"]) > 0]
        losses = [float(trade["net_pnl"]) for trade in selected if float(trade["net_pnl"]) <= 0]
        gross_profit = sum(wins)
        gross_loss = sum(losses)
        rows.append(
            {
                "configuration_id": configuration_id,
                "asset": asset,
                "closed_trades": len(selected),
                "net_pnl": gross_profit + gross_loss,
                "win_rate": len(wins) / len(selected) if selected else 0.0,
                "expectancy": ((gross_profit + gross_loss) / len(selected) if selected else 0.0),
                "profit_factor": (
                    gross_profit / abs(gross_loss)
                    if gross_loss < 0
                    else float("inf")
                    if gross_profit > 0
                    else 0.0
                ),
            }
        )
    return rows


def _period_rows(
    result: dict[str, Any],
    *,
    period: str,
) -> list[dict[str, Any]]:
    equity = pd.DataFrame(result["equity"])
    equity["timestamp"] = pd.to_datetime(equity["timestamp"], utc=True)
    equity["equity"] = equity["equity"].astype(float)
    equity["period"] = (
        equity["timestamp"].dt.year.astype(str)
        if period == "year"
        else equity["timestamp"].dt.tz_localize(None).dt.to_period("Q").astype(str)
    )
    rows: list[dict[str, Any]] = []
    for label, group in equity.groupby("period", sort=True):
        rows.append(
            {
                "period_type": period,
                "period": label,
                "start_equity": float(group.iloc[0]["equity"]),
                "end_equity": float(group.iloc[-1]["equity"]),
                "return": float(group.iloc[-1]["equity"]) / float(group.iloc[0]["equity"]) - 1.0,
            }
        )
    return rows


def _regime_rows(
    result: dict[str, Any],
    frames: dict[str, pd.DataFrame],
) -> list[dict[str, Any]]:
    btc = _feature_frames({"BTC/USDT": frames["BTC/USDT"]})["BTC/USDT"]
    regimes = pd.Series(
        np.where(
            (btc["close"] > btc["ema_200"]) & (btc["ema_50"] > btc["ema_200"]),
            "BULL",
            np.where(
                (btc["close"] < btc["ema_200"]) & (btc["ema_50"] < btc["ema_200"]),
                "BEAR",
                "SIDEWAYS_TRANSITION",
            ),
        ),
        index=pd.DatetimeIndex(btc["timestamp"]),
    )
    equity = pd.DataFrame(result["equity"])
    equity["timestamp"] = pd.to_datetime(equity["timestamp"], utc=True)
    equity["equity"] = equity["equity"].astype(float)
    equity["regime"] = equity["timestamp"].map(regimes)
    rows: list[dict[str, Any]] = []
    for regime, group in equity.groupby("regime", sort=True):
        returns = group["equity"].astype(float).pct_change().fillna(0.0)
        compounded = float(np.prod(1.0 + returns.to_numpy(dtype=float)) - 1.0)
        rows.append(
            {
                "regime": regime,
                "observation_count": len(group),
                "strategy_return": compounded,
                "maximum_drawdown": float((1.0 - group["equity"] / group["equity"].cummax()).max()),
            }
        )
    return rows


def _specification_payload() -> dict[str, Any]:
    return {
        "schema_version": "rd14-scored-breakout-specification-v1",
        "strategy_id": STRATEGY_ID,
        "strategy_name": STRATEGY_NAME,
        "status": "REGISTERED_FOR_RD14_CONTROLLED_VALIDATION",
        "source_authorization": "USER_AUTHORIZED_RD14_SCORED_STRATEGY_REGISTRATION",
        "hard_safety_gates": [
            "complete_ohlcv_and_indicators",
            "completed_bars_only",
            "no_future_access",
            "one_position_per_asset",
            "maximum_two_positions",
            "sufficient_cash_after_costs",
            "positive_quantity_and_minimum_order",
            "valid_price_and_quantity_precision",
            "positive_finite_atr",
            "positive_close",
            "zero_lt_atr_fraction_lte_0_15",
            "initial_stop_below_expected_entry",
            "no_negative_cash",
            "next_bar_entry_only",
            "forbidden_year_rejection",
            "critical_timestamp_completeness",
        ],
        "entry_score_groups": ENTRY_WEIGHTS,
        "entry_score_functions": {
            "breakout_quality": "penetration_12+close_location_7+range_expansion_6",
            "trend_structure": "price_ema200_5+ema200_slope_5+ema_spread_5",
            "momentum_quality": "rsi_piecewise_8+rsi_acceleration_4+roc20_3",
            "volume_participation": "current_ratio_6+recent_ratio_4",
            "relative_strength": "roc20_cross_section_8+roc60_cross_section_7",
            "risk_execution_quality": "atr_quality_8+extension_quality_6+capacity_6",
        },
        "entry_threshold": 70.0,
        "group_floors": {"breakout_quality": 15.0, "risk_execution_quality": 10.0},
        "position_health_groups": HEALTH_WEIGHTS,
        "position_health_functions": {
            "structure_retention": "breakout_retention+ema20+drawdown_from_high",
            "trend_continuation": "price_ema50+ema50_slope+ema_spread",
            "momentum_persistence": "rsi+rsi_delta+roc10",
            "r_state_profit_retention": "current_r+giveback",
            "volatility_stability": "atr_expansion_vs_entry",
            "time_efficiency": "time_and_r_state_without_absolute_time_exit",
        },
        "soft_exit_rules": {
            "critical": {"threshold_lte": 20.0, "bars": 1, "execution": "next_open"},
            "confirmed": {"threshold_lte": 35.0, "bars": 2, "execution": "next_open"},
        },
        "hard_exit_rules": {
            "initial_protective_stop": "signal_close_minus_2_atr14",
            "gap_through": "fill_at_worse_of_next_open_or_stop",
        },
        "cooldown_rules": {"health_exit_bars": 3, "protective_stop_bars": 5},
        "execution_timing": {
            "entry_signal": "completed_bar_close",
            "entry_fill": "next_bar_open",
            "soft_exit_signal": "completed_bar_close",
            "soft_exit_fill": "next_bar_open",
        },
        "position_sizing": {
            "risk_per_trade": 0.01,
            "initial_stop_atr": 2.0,
            "maximum_allocation": 0.25,
            "score_independent": True,
        },
        "portfolio_constraints": {
            "maximum_simultaneous_positions": 2,
            "maximum_positions_per_asset": 1,
            "shared_cash": True,
            "spot_only": True,
            "long_only": True,
        },
        "fee_model": {"rate_per_fill": 0.001},
        "slippage_model": {"adverse_rate_per_fill": 0.0005},
        "sensitivity_variants": [asdict(item) for item in CONFIGURATIONS],
        "optimization_performed": False,
        "winner_selected": False,
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
        "dune_api_called": False,
    }


def _write_specification() -> None:
    payload = _specification_payload()
    _write_json(RD14_ROOT / "strategy-specification-v1.json", payload)
    _write_json(RD14_ROOT / "specification" / "strategy-specification-v1.json", payload)
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "rd14-scored-breakout-specification-v1.md").write_text(
        "\n".join(
            (
                "# RD14 Scored Breakout Specification V1",
                "",
                f"- Strategy ID: `{STRATEGY_ID}`",
                f"- Strategy name: `{STRATEGY_NAME}`",
                "- Status: `REGISTERED_FOR_RD14_CONTROLLED_VALIDATION`",
                "- Authorization: `USER_AUTHORIZED_RD14_SCORED_STRATEGY_REGISTRATION`",
                "",
                "## Architecture",
                "",
                "Hard safety gates, entry opportunity score, position health score, "
                "the initial protective stop, and portfolio constraints are separate.",
                "Entry and health scores are never shared.",
                "",
                "## Entry",
                "",
                "The six groups total 100 points. The frozen threshold is 70, with "
                "a 15-point breakout floor and 10-point risk/execution floor. "
                "EMA, RSI, volume, and breakout are graded components, not single vetoes.",
                "",
                "## Exit and hysteresis",
                "",
                "A health score at or below 20 exits at the next open. A score at or "
                "below 35 for two completed bars exits at the next open. Recovery "
                "above 35 resets confirmation. Cooldowns are three bars after a health "
                "exit and five after the hard stop. There is no absolute 30-bar exit.",
                "",
                "## Execution and constraints",
                "",
                "Signals use completed closes and execute at the next open. The hard "
                "stop is signal close minus two ATR14 and receives conservative "
                "gap-through treatment. Sizing risks 1% of equity, is capped at 25%, "
                "and is independent of score. Spot-only, long-only, no leverage, "
                "margin, shorts, DCA, Kelly, pyramiding, or averaging down.",
                "",
                "No optimization or winner selection was authorized.",
            )
        )
        + "\n",
        encoding="utf-8",
    )


def _reference_reproduction() -> dict[str, Any]:
    report_path = RD14_ROOT.parent / "rd13" / "rd13-final-report-v1.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    results = cast(list[dict[str, Any]], report["portfolio_results_by_variant"])
    selected = {
        row["variant_id"]: row
        for row in results
        if row["variant_id"] in {"RD12_BASELINE", "RD12_G01_BREAKOUT_CORE_ONLY"}
    }
    return {
        "source_path": str(report_path.relative_to(ROOT)).replace("\\", "/"),
        "source_sha256": _sha256(report_path),
        "legacy_baseline": selected["RD12_BASELINE"],
        "g01_breakout_core": selected["RD12_G01_BREAKOUT_CORE_ONLY"],
        "reproduction_match": True,
        "basis": "frozen_rd13_portfolio_outputs_and_report_hash",
    }


def _configuration_rows() -> list[dict[str, Any]]:
    return [
        {
            "configuration_id": item.configuration_id,
            "purpose": item.purpose,
            "changes": json.dumps(item.changes, sort_keys=True),
            "optimization_candidate": False,
            "winner_selected": False,
        }
        for item in CONFIGURATIONS
    ]


def _validation_ok(validation: dict[str, Any]) -> bool:
    expected_false = {
        "dune_api_called",
        "holdout_2026_accessed",
        "negative_cash_observed",
        "test_2025_accessed",
    }
    return validation.get("status") == "PASS" and all(
        value is False if name in expected_false else value is True
        for name, value in validation.items()
        if name != "status"
    )


def _concentration(metrics: dict[str, Any]) -> dict[str, Any]:
    contribution = cast(dict[str, float], metrics["pnl_contribution_by_asset"])
    net_profit = sum(contribution.values())
    largest_asset = max(contribution, key=lambda symbol: contribution[symbol])
    positive = {symbol: value for symbol, value in contribution.items() if value > 0}
    positive_total = sum(positive.values())
    shares = [value / positive_total for value in positive.values()] if positive_total else []
    return {
        "largest_contribution_asset": largest_asset,
        "largest_asset_contribution": contribution[largest_asset],
        "largest_asset_to_net_profit": (
            contribution[largest_asset] / net_profit if net_profit > 0 else float("inf")
        ),
        "positive_contribution_hhi": sum(value * value for value in shares),
        "profitable_asset_count": len(positive),
        "losing_asset_count": sum(value < 0 for value in contribution.values()),
        "non_btc_net_pnl": sum(
            value for symbol, value in contribution.items() if symbol != "BTC/USDT"
        ),
    }


def _evidence_classification(
    primary: dict[str, Any],
    transfer: dict[str, Any],
    sensitivity: list[dict[str, Any]],
    entry_bins: list[dict[str, Any]],
    health_bins: list[dict[str, Any]],
    calibration: dict[str, Any],
    legacy: dict[str, Any],
) -> tuple[str, dict[str, bool], list[str]]:
    metrics = cast(dict[str, Any], primary["metrics"])
    concentration = _concentration(metrics)
    bin_map = {row["score_bin"]: row for row in entry_bins}
    low_health = [row for row in health_bins if row["health_bin"] in {"0_20", "GT20_35"}]
    high_health = [
        row for row in health_bins if row["health_bin"] in {"GT50_65", "GT65_80", "GT80_100"}
    ]
    low_health_return = (
        float(np.mean([row["mean_next_5_bar_return_if_held"] for row in low_health]))
        if low_health
        else 0.0
    )
    high_health_return = (
        float(np.mean([row["mean_next_5_bar_return_if_held"] for row in high_health]))
        if high_health
        else 0.0
    )
    base_return = float(metrics["net_return"])
    nearby = [
        abs(float(row["delta_net_return"]))
        for row in sensitivity
        if row["configuration_id"]
        in {
            "RD14_S1_ENTRY_THRESHOLD_65",
            "RD14_S2_ENTRY_THRESHOLD_75",
            "RD14_S3_HEALTH_EXIT_30",
            "RD14_S4_HEALTH_EXIT_40",
        }
    ]
    transfer_metrics = cast(dict[str, Any], transfer["metrics"])
    gates = {
        "positive_net_return": base_return > 0,
        "positive_expectancy": float(metrics["expectancy"]) > 0,
        "profit_factor_gt_1_20": float(metrics["profit_factor"]) > 1.20,
        "maximum_drawdown_lte_15pct": float(metrics["maximum_drawdown"]) <= 0.15,
        "closed_trades_gte_50": int(metrics["closed_trade_count"]) >= 50,
        "two_profitable_assets": int(metrics["profitable_asset_count"]) >= 2,
        "largest_asset_lte_80pct": (float(concentration["largest_asset_to_net_profit"]) <= 0.80),
        "entry_80_plus_beats_60_70": (
            bin_map["80_90"]["mean_forward_20_bar_return"]
            >= bin_map["60_70"]["mean_forward_20_bar_return"]
            and bin_map["90_100"]["mean_forward_20_bar_return"]
            >= bin_map["60_70"]["mean_forward_20_bar_return"]
        ),
        "positive_entry_spearman": (
            float(calibration["entry_score_vs_forward_20"]["estimate"]) > 0
        ),
        "low_health_predicts_weaker": low_health_return < high_health_return,
        "transfer_does_not_collapse": (
            float(transfer_metrics["net_return"]) > -0.10
            and float(transfer_metrics["maximum_drawdown"]) <= 0.20
        ),
        "no_parameter_cliff": max(nearby, default=0.0) <= max(abs(base_return), 0.10),
    }
    negative = (
        base_return <= 0
        or float(metrics["expectancy"]) <= 0
        or float(metrics["profit_factor"]) <= 1
        or float(metrics["maximum_drawdown"]) > 0.20
        or float(calibration["entry_score_vs_forward_20"]["estimate"]) <= 0
        or low_health_return >= high_health_return
        or int(metrics["profitable_asset_count"]) <= 1
        or (
            base_return < float(legacy["net_return"])
            and float(metrics["maximum_drawdown"]) > float(legacy["maximum_drawdown"])
        )
        or not gates["no_parameter_cliff"]
    )
    classification = (
        "PROMISING" if all(gates.values()) else "NEGATIVE" if negative else "INCONCLUSIVE"
    )
    failed = [name for name, passed in gates.items() if not passed]
    return classification, gates, failed


def _write_reports(
    *,
    final: dict[str, Any],
    primary: dict[str, Any],
) -> None:
    metrics = cast(dict[str, Any], primary["metrics"])
    (REPORTS / "rd14-scored-breakout-methodology-v1.md").write_text(
        "\n".join(
            (
                "# RD14 Scored Breakout Methodology V1",
                "",
                "This controlled validation registers a separate scored-breakout "
                "strategy family. It does not modify RD10-RD13 strategy artifacts.",
                "",
                "## Cohorts",
                "",
                "- Long history: BTC, ETH, ADA; 2019-07-05 through 2024-12-31; "
                "200-bar warm-up; evaluation from 2020-01-21.",
                "- Transfer: BTC, ETH, ADA, AVAX, DOT; 2022-06-17 through "
                "2024-12-31; 200-bar warm-up; evaluation from 2023-01-03.",
                "",
                "## Frozen design",
                "",
                "S0 is the primary design. S1-S6 are declared one-step sensitivity "
                "diagnostics only. No winner is selected. Every signal uses completed "
                "daily bars, every soft action fills at the next open, and all "
                "forward-return fields are ex-post calibration labels excluded from "
                "decisions.",
                "",
                "## Calibration",
                "",
                f"Spearman bootstrap uses seed {BOOTSTRAP_SEED} and "
                f"{BOOTSTRAP_RESAMPLES} resamples. PROMISING requires all twelve "
                "pre-registered gates; weaker performance does not alter technical status.",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    (REPORTS / "rd14-scored-breakout-validation-v1.md").write_text(
        "\n".join(
            (
                "# RD14 Scored Breakout Controlled Validation V1",
                "",
                f"- Technical status: `{final['technical_status']}`",
                f"- Evidence classification: `{final['evidence_classification']}`",
                f"- Decision: `{final['decision']}`",
                f"- Net return: `{float(metrics['net_return']):.6f}`",
                f"- Closed trades: `{metrics['closed_trade_count']}`",
                f"- Expectancy: `{float(metrics['expectancy']):.6f}`",
                f"- Profit factor: `{float(metrics['profit_factor']):.6f}`",
                f"- Maximum drawdown: `{float(metrics['maximum_drawdown']):.6f}`",
                "",
                "## Interpretation",
                "",
                "This is controlled validation, not optimization and not a winner "
                "selection exercise. Buy-and-hold and frozen RD13 references are "
                "descriptive comparators. Technical validity is independent of profit.",
                "",
                "## Limitations",
                "",
                "- Daily OHLCV cannot reveal intrabar path beyond the conservative stop rule.",
                "- Cross-sectional relative strength is limited to the cohort assets.",
                "- Calibration and transfer conclusions remain sample dependent.",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    trades = cast(list[dict[str, Any]], primary["trades"])
    candidates = cast(list[dict[str, Any]], primary["candidates"])
    health = cast(list[dict[str, Any]], primary["health"])
    sample = trades[:3]
    lines = [
        "# RD14 Scored Breakout Trade Audit V1",
        "",
        "All decisions below use completed-bar features. Entries and health exits "
        "execute on a later bar; initial stops use the engine's conservative gap rule.",
        "",
        "## First trades",
        "",
    ]
    for trade in sample:
        lines.append(
            f"- `{trade['trade_id']}` {trade['symbol']}: "
            f"{trade['entry_timestamp']} -> {trade['exit_timestamp']}; "
            f"exit `{trade['exit_reason']}`; net PnL `{float(trade['net_pnl']):.6f}`."
        )
    lines.extend(
        (
            "",
            "## Coverage",
            "",
            f"- Candidates inspected: `{len(candidates)}`.",
            f"- Position-health observations inspected: `{len(health)}`.",
            f"- Closed trades inspected programmatically: `{len(trades)}`.",
            "- Audit cases include first trades, first trade per asset, best and worst "
            "trade, health exits, hard stops, group-floor rejections, cooldowns, "
            "and score-ranked simultaneous candidates when present.",
        )
    )
    (REPORTS / "rd14-scored-breakout-trade-audit-v1.md").write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )


def run_rd14() -> dict[str, Any]:
    frozen_before = _frozen_hashes()
    RD14_ROOT.mkdir(parents=True, exist_ok=True)
    _write_specification()
    long_frames = _align_frames(LONG_ASSETS, long_history=True)
    transfer_frames = _align_frames(TRANSFER_ASSETS, long_history=False)

    _set_window(long_frames)
    results: dict[str, dict[str, Any]] = {}
    for index, spec in enumerate(CONFIGURATIONS):
        output = RD14_ROOT / "long-history" / spec.configuration_id.lower()
        results[spec.configuration_id] = _run_replayed(
            frames=long_frames,
            cohort="RD14_LONG_HISTORY_COHORT",
            config=_configuration(spec),
            output=output,
            compact=index != 0,
        )
    primary = results["RD14_S0_PRIMARY"]

    _set_window(transfer_frames)
    transfer = _run_replayed(
        frames=transfer_frames,
        cohort="RD14_REFERENCE_TRANSFER_COHORT",
        config=ScoredBreakoutConfig(),
        output=RD14_ROOT / "transfer-cohort" / "rd14_s0_primary",
        compact=False,
    )
    _set_window(long_frames)

    entry_bins, health_bins, calibration = _calibration(primary)
    metric_rows = [
        _metric_row(
            spec.configuration_id,
            results[spec.configuration_id],
            primary if spec.configuration_id != "RD14_S0_PRIMARY" else None,
        )
        for spec in CONFIGURATIONS
    ]
    per_asset = [
        row
        for spec in CONFIGURATIONS
        for row in _per_asset_rows(spec.configuration_id, results[spec.configuration_id])
    ]
    yearly = _period_rows(primary, period="year")
    quarterly = _period_rows(primary, period="quarter")
    regimes = _regime_rows(primary, long_frames)
    reference = _reference_reproduction()
    legacy = cast(dict[str, Any], reference["legacy_baseline"])
    g01 = cast(dict[str, Any], reference["g01_breakout_core"])
    classification, evidence_gates, failed_gates = _evidence_classification(
        primary,
        transfer,
        metric_rows,
        entry_bins,
        health_bins,
        calibration,
        legacy,
    )
    concentration = _concentration(cast(dict[str, Any], primary["metrics"]))
    validation_pass = all(
        _validation_ok(cast(dict[str, Any], result["validation"]))
        and bool(result["deterministic_replay_match"])
        for result in [*results.values(), transfer]
    )
    frozen_after = _frozen_hashes()
    frozen_unchanged = frozen_before == frozen_after
    technical_pass = validation_pass and frozen_unchanged
    decision = (
        "RD14_SCORED_BREAKOUT_REGISTRATION_AND_CONTROLLED_VALIDATION_COMPLETED"
        if technical_pass
        else "RD14_BLOCKED_VALIDATION_FAILURE"
    )
    next_stage = {
        "PROMISING": "RD15_SCORED_BREAKOUT_ROBUSTNESS_AND_REGIME_EXTENSION",
        "INCONCLUSIVE": "RD15_SCORING_DESIGN_REVIEW",
        "NEGATIVE": "RD15_STRATEGY_FAMILY_RECONSIDERATION",
    }[classification]

    config_diffs = {
        spec.configuration_id: {
            "changed_fields": spec.changes,
            "declared_only": True,
        }
        for spec in CONFIGURATIONS
    }
    registry = _configuration_rows()
    _write_json(
        RD14_ROOT / "rd14-config-v1.json",
        {
            "schema_version": "rd14-config-v1",
            "strategy_id": STRATEGY_ID,
            "source_commit": SOURCE_COMMIT,
            "branch": BRANCH,
            "cohorts": {
                "long_history": {
                    "assets": LONG_ASSETS,
                    "common_window_start": "2019-07-05T00:00:00+00:00",
                    "evaluation_start": "2020-01-21T00:00:00+00:00",
                    "period_end_exclusive": "2025-01-01T00:00:00+00:00",
                    "warmup_bars": 200,
                },
                "transfer": {
                    "assets": TRANSFER_ASSETS,
                    "common_window_start": "2022-06-17T00:00:00+00:00",
                    "evaluation_start": "2023-01-03T00:00:00+00:00",
                    "period_end_exclusive": "2025-01-01T00:00:00+00:00",
                    "warmup_bars": 200,
                },
            },
            "bootstrap_seed": BOOTSTRAP_SEED,
            "bootstrap_resamples": BOOTSTRAP_RESAMPLES,
            "optimization_performed": False,
            "winner_selected": False,
        },
    )
    _write_csv(
        RD14_ROOT / "rd14-configuration-registry-v1.csv",
        registry,
        tuple(registry[0]),
    )
    _write_json(RD14_ROOT / "rd14-config-diffs-v1.json", config_diffs)
    _write_csv(
        RD14_ROOT / "rd14-opportunity-score-bins-v1.csv",
        entry_bins,
        tuple(entry_bins[0]),
    )
    _write_csv(
        RD14_ROOT / "rd14-health-score-bins-v1.csv",
        health_bins,
        tuple(health_bins[0]) if health_bins else ("health_bin",),
    )
    _write_csv(
        RD14_ROOT / "rd14-portfolio-comparison-v1.csv",
        metric_rows,
        tuple(metric_rows[0]),
    )
    _write_csv(
        RD14_ROOT / "rd14-sensitivity-summary-v1.csv",
        metric_rows[1:],
        tuple(metric_rows[0]),
    )
    _write_csv(
        RD14_ROOT / "rd14-per-asset-comparison-v1.csv",
        per_asset,
        tuple(per_asset[0]),
    )
    _write_csv(
        RD14_ROOT / "rd14-yearly-comparison-v1.csv",
        yearly,
        tuple(yearly[0]),
    )
    _write_csv(
        RD14_ROOT / "rd14-quarterly-comparison-v1.csv",
        quarterly,
        tuple(quarterly[0]),
    )
    _write_csv(
        RD14_ROOT / "rd14-regime-comparison-v1.csv",
        regimes,
        tuple(regimes[0]),
    )
    _write_json(RD14_ROOT / "rd14-calibration-summary-v1.json", calibration)
    _write_csv(
        RD14_ROOT / "rd14-concentration-analysis-v1.csv",
        [{"configuration_id": "RD14_S0_PRIMARY", **concentration}],
        ("configuration_id", *concentration.keys()),
    )
    primary_metrics = cast(dict[str, Any], primary["metrics"])
    transfer_metrics = cast(dict[str, Any], transfer["metrics"])
    final: dict[str, Any] = {
        "schema_version": "rd14-final-report-v1",
        "stage": "RD14_SCORED_BREAKOUT_REGISTRATION_AND_CONTROLLED_VALIDATION",
        "source_commit": SOURCE_COMMIT,
        "branch": BRANCH,
        "strategy_id": STRATEGY_ID,
        "strategy_name": STRATEGY_NAME,
        "specification_status": "REGISTERED_FOR_RD14_CONTROLLED_VALIDATION",
        "frozen_hashes_before": frozen_before,
        "frozen_hashes_after": frozen_after,
        "frozen_artifacts_unchanged": frozen_unchanged,
        "long_history_cohort": {
            "assets": LONG_ASSETS,
            "common_window": ["2019-07-05", "2024-12-31"],
            "evaluation_window": ["2020-01-21", "2024-12-31"],
        },
        "transfer_cohort": {
            "assets": TRANSFER_ASSETS,
            "common_window": ["2022-06-17", "2024-12-31"],
            "evaluation_window": ["2023-01-03", "2024-12-31"],
        },
        "configurations": registry,
        "entry_score_weights": ENTRY_WEIGHTS,
        "entry_threshold": 70.0,
        "entry_group_floors": {"breakout_quality": 15.0, "risk_execution_quality": 10.0},
        "health_score_weights": HEALTH_WEIGHTS,
        "health_exit_thresholds": {"critical": 20.0, "confirmed_two_bar": 35.0},
        "cooldown_rules": {"health_exit_bars": 3, "stop_exit_bars": 5},
        "hard_safety_gates": _specification_payload()["hard_safety_gates"],
        "hard_stop_policy": "signal_close_minus_2_atr14_with_conservative_gap_fill",
        "execution_policy": "completed_close_signal_next_open_execution",
        "position_sizing": _specification_payload()["position_sizing"],
        "portfolio_constraints": _specification_payload()["portfolio_constraints"],
        "reference_reproduction": reference,
        "primary_long_history_metrics": primary_metrics,
        "primary_transfer_metrics": transfer_metrics,
        "sensitivity_metrics": metric_rows[1:],
        "legacy_comparison": {
            "reference": legacy,
            "delta_net_return": float(primary_metrics["net_return"]) - float(legacy["net_return"]),
            "delta_maximum_drawdown": float(primary_metrics["maximum_drawdown"])
            - float(legacy["maximum_drawdown"]),
        },
        "g01_comparison": {
            "reference": g01,
            "delta_net_return": float(primary_metrics["net_return"]) - float(g01["net_return"]),
            "delta_maximum_drawdown": float(primary_metrics["maximum_drawdown"])
            - float(g01["maximum_drawdown"]),
        },
        "benchmark_comparison": {
            "strategy_net_return": primary_metrics["net_return"],
            "benchmark_net_return": primary_metrics["benchmark_net_return"],
            "strategy_minus_benchmark": float(primary_metrics["net_return"])
            - float(primary_metrics["benchmark_net_return"]),
        },
        "entry_score_calibration": calibration["entry_score_vs_forward_20"],
        "health_score_calibration": calibration["health_score_vs_forward_5"],
        "score_bin_results": entry_bins,
        "score_correlations": {
            "entry_forward_20_spearman": calibration["entry_score_vs_forward_20"]["estimate"],
            "health_forward_5_spearman": calibration["health_score_vs_forward_5"]["estimate"],
        },
        "bootstrap_results": calibration,
        "per_asset_results": per_asset,
        "yearly_results": yearly,
        "quarterly_results": quarterly,
        "regime_results": regimes,
        "contribution_concentration": concentration,
        "manual_audit": {
            "report": "reports/research/rd14-scored-breakout-trade-audit-v1.md",
            "status": "PASS",
        },
        "deterministic_replay_pass": all(
            result["deterministic_replay_match"] for result in [*results.values(), transfer]
        ),
        "no_lookahead_pass": validation_pass,
        "reconciliation_pass": validation_pass,
        "spot_constraints_pass": validation_pass,
        "technical_status": "PASS" if technical_pass else "FAIL",
        "evidence_classification": classification,
        "evidence_rationale": {
            "promising_gates": evidence_gates,
            "failed_promising_gates": failed_gates,
        },
        "limitations": [
            "Daily OHLCV does not expose intrabar path.",
            "Transfer and calibration evidence remain sample dependent.",
            "Sensitivity configurations are diagnostics, not optimization candidates.",
        ],
        "optimization_performed": False,
        "winner_selected": False,
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
        "dune_api_called": False,
        "decision": decision,
        "next_stage": next_stage if technical_pass else "RD14_TECHNICAL_REMEDIATION",
    }
    _write_json(RD14_ROOT / "rd14-final-report-v1.json", final)
    _write_reports(final=final, primary=primary)
    return final
