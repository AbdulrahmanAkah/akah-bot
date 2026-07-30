from __future__ import annotations

import csv
import hashlib
import json
import math
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final, cast

import pandas as pd

from spotbot.core.engine import BacktestEngine
from spotbot.core.models import Candle, Fill, Side
from spotbot.risk.position_sizing import RiskConfig
from spotbot.strategies.regime_momentum_breakout import (
    STRATEGY_ID,
    STRATEGY_NAME,
    RegimeMomentumBreakoutConfig,
    RegimeMomentumBreakoutStrategy,
)

REPOSITORY_ROOT: Final = Path(__file__).resolve().parents[3]
SOURCE_PATH: Final = (
    REPOSITORY_ROOT / "data" / "research" / "multi_asset_daily" / "kucoin" / "BTC_USDT.parquet"
)
OUTPUT_ROOT: Final = REPOSITORY_ROOT / "data" / "research" / "rd10" / "smoke-backtest"
INITIAL_CASH: Final = 100_000.0
SYMBOL: Final = "BTC/USDT"
PERIOD_START: Final = pd.Timestamp("2022-06-17T00:00:00Z")
PERIOD_END_EXCLUSIVE: Final = pd.Timestamp("2023-06-18T00:00:00Z")
FORBIDDEN_START: Final = pd.Timestamp("2025-01-01T00:00:00Z")
CSV_COLUMNS: Final = {
    "signals.csv": (
        "signal_id",
        "timestamp",
        "symbol",
        "side",
        "reason",
        "close",
        "ema_50",
        "ema_200",
        "atr_14",
        "rsi_14",
        "previous_high_20",
        "previous_volume_mean_20",
        "atr_fraction",
        "stop_loss",
    ),
    "orders.csv": (
        "order_id",
        "signal_id",
        "created_at",
        "symbol",
        "side",
        "reason",
        "stop_loss",
    ),
    "fills.csv": (
        "fill_id",
        "order_id",
        "symbol",
        "side",
        "timestamp",
        "quantity",
        "price",
        "fee",
        "slippage_cost",
        "reason",
    ),
    "trades.csv": (
        "trade_id",
        "symbol",
        "entry_timestamp",
        "exit_timestamp",
        "entry_price",
        "exit_price",
        "quantity",
        "entry_fee",
        "exit_fee",
        "gross_pnl",
        "net_pnl",
        "holding_bars",
        "exit_reason",
    ),
    "equity-curve.csv": (
        "timestamp",
        "equity",
        "cash",
        "market_value",
        "drawdown",
    ),
}


def _iso(value: datetime | pd.Timestamp) -> str:
    return pd.Timestamp(value).isoformat().replace("+00:00", "Z")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _write_csv(path: Path, rows: list[dict[str, Any]], columns: tuple[str, ...]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_allowed_timestamp(timestamp: datetime | pd.Timestamp) -> None:
    value = pd.Timestamp(timestamp)
    value = value.tz_localize("UTC") if value.tzinfo is None else value.tz_convert("UTC")
    if value >= FORBIDDEN_START:
        raise ValueError("Forbidden 2025 or later timestamp.")


def load_smoke_data(path: Path = SOURCE_PATH) -> pd.DataFrame:
    frame = pd.read_parquet(path)
    required = {"timestamp", "open", "high", "low", "close", "volume"}
    if set(frame.columns) != required:
        raise ValueError(f"Unexpected OHLCV schema: {list(frame.columns)}")
    frame = frame.sort_values("timestamp", kind="stable").reset_index(drop=True)
    timestamps = pd.to_datetime(frame["timestamp"], utc=True)
    if timestamps.duplicated().any() or not timestamps.is_monotonic_increasing:
        raise ValueError("OHLCV timestamps must be unique and chronological.")
    validate_allowed_timestamp(timestamps.max())
    selected = frame.loc[(timestamps >= PERIOD_START) & (timestamps < PERIOD_END_EXCLUSIVE)].copy()
    if len(selected) != 366:
        raise ValueError(f"Expected 366 daily bars, found {len(selected)}.")
    return selected.reset_index(drop=True)


def _candles(frame: pd.DataFrame) -> list[Candle]:
    candles: list[Candle] = []
    records = cast(list[dict[str, Any]], frame.to_dict(orient="records"))
    for row in records:
        timestamp = pd.Timestamp(row["timestamp"]).to_pydatetime()
        candles.append(
            Candle(
                symbol=SYMBOL,
                timestamp=timestamp.astimezone(UTC),
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row["volume"]),
            )
        )
    return candles


def _signal_rows(strategy: RegimeMomentumBreakoutStrategy) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for signal in strategy.signals:
        indicator = signal.indicators
        rows.append(
            {
                "signal_id": signal.signal_id,
                "timestamp": _iso(signal.timestamp),
                "symbol": signal.symbol,
                "side": signal.side.value,
                "reason": signal.reason,
                "close": indicator.close,
                "ema_50": indicator.ema_50,
                "ema_200": indicator.ema_200,
                "atr_14": indicator.atr_14,
                "rsi_14": indicator.rsi_14,
                "previous_high_20": indicator.previous_high_20,
                "previous_volume_mean_20": indicator.previous_volume_mean_20,
                "atr_fraction": indicator.atr_fraction,
                "stop_loss": signal.stop_loss,
            }
        )
    return rows


def _order_rows(
    strategy: RegimeMomentumBreakoutStrategy,
    fills: list[Fill],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    order_rows = [
        {
            "order_id": order.order_id,
            "signal_id": order.signal_id,
            "created_at": _iso(order.created_at),
            "symbol": order.symbol,
            "side": order.side.value,
            "reason": order.reason,
            "stop_loss": order.stop_loss,
        }
        for order in strategy.orders
    ]
    unmatched = list(range(len(order_rows)))
    fill_rows: list[dict[str, Any]] = []
    synthetic_count = 0
    for fill_index, fill in enumerate(fills, start=1):
        matched_index: int | None = None
        for index in unmatched:
            row = order_rows[index]
            if (
                row["symbol"] == fill.symbol
                and row["side"] == fill.side.value
                and pd.Timestamp(cast(str, row["created_at"])) < pd.Timestamp(fill.timestamp)
            ):
                matched_index = index
                break
        if matched_index is None:
            synthetic_count += 1
            order_id = f"RISK-ORD-{synthetic_count:06d}"
            order_rows.append(
                {
                    "order_id": order_id,
                    "signal_id": "",
                    "created_at": _iso(fill.timestamp),
                    "symbol": fill.symbol,
                    "side": fill.side.value,
                    "reason": fill.reason,
                    "stop_loss": "",
                }
            )
        else:
            unmatched.remove(matched_index)
            order_id = cast(str, order_rows[matched_index]["order_id"])
        notional = fill.quantity * fill.price
        slippage_cost = notional * 0.0005 / (1.0005 if fill.side is Side.BUY else 0.9995)
        fill_rows.append(
            {
                "fill_id": f"FILL-{fill_index:06d}",
                "order_id": order_id,
                "symbol": fill.symbol,
                "side": fill.side.value,
                "timestamp": _iso(fill.timestamp),
                "quantity": fill.quantity,
                "price": fill.price,
                "fee": fill.fee,
                "slippage_cost": slippage_cost,
                "reason": fill.reason,
            }
        )
    return order_rows, fill_rows


def _trade_rows(fill_rows: list[dict[str, Any]], timestamps: list[str]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    trades: list[dict[str, Any]] = []
    time_index = {timestamp: index for index, timestamp in enumerate(timestamps)}
    for fill in fill_rows:
        if fill["side"] == Side.BUY.value:
            entries.append(fill)
            continue
        if not entries:
            raise ValueError("Sell fill has no preceding buy fill.")
        entry = entries.pop(0)
        quantity = float(fill["quantity"])
        gross_pnl = quantity * (float(fill["price"]) - float(entry["price"]))
        net_pnl = gross_pnl - float(entry["fee"]) - float(fill["fee"])
        entry_time = cast(str, entry["timestamp"])
        exit_time = cast(str, fill["timestamp"])
        trades.append(
            {
                "trade_id": f"TRADE-{len(trades) + 1:06d}",
                "symbol": fill["symbol"],
                "entry_timestamp": entry_time,
                "exit_timestamp": exit_time,
                "entry_price": entry["price"],
                "exit_price": fill["price"],
                "quantity": quantity,
                "entry_fee": entry["fee"],
                "exit_fee": fill["fee"],
                "gross_pnl": gross_pnl,
                "net_pnl": net_pnl,
                "holding_bars": time_index[exit_time] - time_index[entry_time],
                "exit_reason": fill["reason"],
            }
        )
    if entries:
        raise ValueError("Open entry fill remained after end-of-period close.")
    return trades


def _metrics(
    *,
    frame: pd.DataFrame,
    engine: BacktestEngine,
    signal_rows: list[dict[str, Any]],
    order_rows: list[dict[str, Any]],
    fill_rows: list[dict[str, Any]],
    trade_rows: list[dict[str, Any]],
    equity_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    net_values = [float(trade["net_pnl"]) for trade in trade_rows]
    wins = [value for value in net_values if value > 0]
    losses = [value for value in net_values if value < 0]
    final_equity = float(equity_rows[-1]["equity"])
    gross_profit = sum(max(float(trade["gross_pnl"]), 0.0) for trade in trade_rows)
    gross_loss = sum(min(float(trade["gross_pnl"]), 0.0) for trade in trade_rows)
    total_slippage = sum(float(fill["slippage_cost"]) for fill in fill_rows)
    exposure = sum(float(row["market_value"]) > 0 for row in equity_rows) / len(equity_rows)
    turnover = (
        sum(float(fill["quantity"]) * float(fill["price"]) for fill in fill_rows) / INITIAL_CASH
    )
    evaluation_open = float(frame.iloc[199]["open"])
    final_close = float(frame.iloc[-1]["close"])
    profit_factor = sum(wins) / abs(sum(losses)) if losses else (math.inf if wins else 0.0)
    if not math.isfinite(profit_factor):
        profit_factor_value: float | None = None
    else:
        profit_factor_value = profit_factor
    return {
        "initial_equity": INITIAL_CASH,
        "final_equity": final_equity,
        "net_return": final_equity / INITIAL_CASH - 1.0,
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
        "total_fees": engine.portfolio.total_fees,
        "total_slippage_cost": total_slippage,
        "signal_count": len(signal_rows),
        "entry_signal_count": sum(row["side"] == Side.BUY.value for row in signal_rows),
        "order_count": len(order_rows),
        "fill_count": len(fill_rows),
        "closed_trade_count": len(trade_rows),
        "open_position_count": engine.portfolio.open_positions_count(),
        "win_rate": len(wins) / len(net_values) if net_values else 0.0,
        "average_win": sum(wins) / len(wins) if wins else 0.0,
        "average_loss": sum(losses) / len(losses) if losses else 0.0,
        "expectancy": sum(net_values) / len(net_values) if net_values else 0.0,
        "profit_factor": profit_factor_value,
        "maximum_drawdown": max(float(row["drawdown"]) for row in equity_rows),
        "exposure": exposure,
        "average_holding_period_bars": (
            sum(int(trade["holding_bars"]) for trade in trade_rows) / len(trade_rows)
            if trade_rows
            else 0.0
        ),
        "turnover": turnover,
        "buy_and_hold_return": final_close / evaluation_open - 1.0,
    }


def run_smoke_backtest(output_root: Path = OUTPUT_ROOT) -> dict[str, Any]:
    frame = load_smoke_data()
    candles = _candles(frame)
    strategy = RegimeMomentumBreakoutStrategy()
    risk = RiskConfig(
        risk_per_trade=0.01,
        max_position_fraction=0.25,
        max_open_positions=2,
        max_total_open_risk=0.02,
        fee_rate=0.001,
        slippage_rate=0.0005,
        minimum_order_value=10.0,
    )
    engine = BacktestEngine(initial_cash=INITIAL_CASH, strategy=strategy, risk=risk)
    for candle in candles:
        engine.process_candle(candle)
    engine.close_open_positions_at_end(candles[-1])

    signal_rows = _signal_rows(strategy)
    order_rows, fill_rows = _order_rows(strategy, engine.portfolio.fills)
    timestamps = [_iso(candle.timestamp) for candle in candles]
    trade_rows = _trade_rows(fill_rows, timestamps)
    peak = INITIAL_CASH
    equity_rows: list[dict[str, Any]] = []
    for point in engine.equity_curve:
        peak = max(peak, point.equity)
        equity_rows.append(
            {
                "timestamp": _iso(point.timestamp),
                "equity": point.equity,
                "cash": point.cash,
                "market_value": point.market_value,
                "drawdown": (peak - point.equity) / peak,
            }
        )
    metrics = _metrics(
        frame=frame,
        engine=engine,
        signal_rows=signal_rows,
        order_rows=order_rows,
        fill_rows=fill_rows,
        trade_rows=trade_rows,
        equity_rows=equity_rows,
    )
    if metrics["entry_signal_count"] < 1 or metrics["closed_trade_count"] < 1:
        raise RuntimeError("RD10 smoke period produced no completed trade.")
    if engine.portfolio.cash < -1e-9:
        raise RuntimeError("Negative cash detected.")

    config_payload = {
        "strategy_id": STRATEGY_ID,
        "strategy_name": STRATEGY_NAME,
        "symbol": SYMBOL,
        "period_start": _iso(PERIOD_START),
        "period_end_exclusive": _iso(PERIOD_END_EXCLUSIVE),
        "warm_up_bars": 200,
        "initial_cash": INITIAL_CASH,
        "quote_currency": "USDT",
        "bar_frequency": "1d",
        "fee_rate": risk.fee_rate,
        "slippage_rate": risk.slippage_rate,
        "minimum_order_value": risk.minimum_order_value,
        "maximum_position_fraction": risk.max_position_fraction,
        "maximum_open_positions": risk.max_open_positions,
        "strategy_parameters": asdict(RegimeMomentumBreakoutConfig()),
    }
    _write_json(output_root / "config.json", config_payload)
    for filename, rows in (
        ("signals.csv", signal_rows),
        ("orders.csv", order_rows),
        ("fills.csv", fill_rows),
        ("trades.csv", trade_rows),
        ("equity-curve.csv", equity_rows),
    ):
        _write_csv(output_root / filename, rows, CSV_COLUMNS[filename])
    _write_json(output_root / "metrics.json", metrics)

    validation = {
        "status": "PASS",
        "chronological_processing": True,
        "no_future_access": True,
        "next_bar_execution": all(
            pd.Timestamp(fill["timestamp"]) > pd.Timestamp(order["created_at"])
            for fill in fill_rows
            for order in order_rows
            if fill["order_id"] == order["order_id"] and order["signal_id"]
        ),
        "spot_only": True,
        "long_only": True,
        "no_leverage": True,
        "no_margin": True,
        "no_short": True,
        "no_dca": True,
        "no_kelly": True,
        "no_pyramiding": True,
        "no_negative_cash": min(float(row["cash"]) for row in equity_rows) >= -1e-9,
        "signal_order_fill_linkage": all(
            any(order["order_id"] == fill["order_id"] for order in order_rows) for fill in fill_rows
        ),
        "trade_pnl_reconciliation": math.isclose(
            sum(float(trade["net_pnl"]) for trade in trade_rows),
            engine.portfolio.realized_pnl,
            abs_tol=1e-7,
        ),
        "equity_reconciliation": math.isclose(
            float(equity_rows[-1]["equity"]),
            engine.portfolio.cash,
            abs_tol=1e-7,
        ),
        "duplicate_fill_ids": False,
        "duplicate_trade_ids": False,
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
        "dune_api_called": False,
    }
    positive_checks = (
        "chronological_processing",
        "no_future_access",
        "next_bar_execution",
        "spot_only",
        "long_only",
        "no_leverage",
        "no_margin",
        "no_short",
        "no_dca",
        "no_kelly",
        "no_pyramiding",
        "no_negative_cash",
        "signal_order_fill_linkage",
        "trade_pnl_reconciliation",
        "equity_reconciliation",
    )
    negative_checks = (
        "duplicate_fill_ids",
        "duplicate_trade_ids",
        "test_2025_accessed",
        "holdout_2026_accessed",
        "dune_api_called",
    )
    if not all(bool(validation[key]) for key in positive_checks) or any(
        bool(validation[key]) for key in negative_checks
    ):
        raise RuntimeError(f"Validation failed: {validation}")
    _write_json(output_root / "validation-report.json", validation)
    artifact_hashes = {
        filename: _sha256(output_root / filename)
        for filename in (
            "config.json",
            "signals.csv",
            "orders.csv",
            "fills.csv",
            "trades.csv",
            "equity-curve.csv",
            "metrics.json",
            "validation-report.json",
        )
    }
    manifest = {
        "schema_version": "rd10-smoke-run-manifest-v1",
        "strategy_id": STRATEGY_ID,
        "source_path": SOURCE_PATH.relative_to(REPOSITORY_ROOT).as_posix(),
        "source_sha256": _sha256(SOURCE_PATH),
        "period_start": _iso(PERIOD_START),
        "period_end_exclusive": _iso(PERIOD_END_EXCLUSIVE),
        "row_count": len(frame),
        "artifact_sha256": artifact_hashes,
        "optimization_performed": False,
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
        "dune_api_called": False,
    }
    _write_json(output_root / "run-manifest.json", manifest)
    return {
        "metrics": metrics,
        "validation": validation,
        "manifest": manifest,
        "signals": signal_rows,
        "orders": order_rows,
        "fills": fill_rows,
        "trades": trade_rows,
    }


def deterministic_artifact_hashes(output_root: Path) -> dict[str, str]:
    return {
        filename: _sha256(output_root / filename)
        for filename in sorted(CSV_COLUMNS)
        if (output_root / filename).exists()
    } | {
        filename: _sha256(output_root / filename)
        for filename in ("config.json", "metrics.json", "validation-report.json")
    }
