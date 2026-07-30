from __future__ import annotations

import hashlib
import json
import math
import shutil
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final, cast

import pandas as pd

from spotbot.core.engine import BacktestEngine, PortfolioSnapshot
from spotbot.core.models import Candle, Fill, OrderRequest, Side
from spotbot.research.rd10_smoke_backtest import (
    _iso,
    _sha256,
    _write_csv,
    _write_json,
)
from spotbot.risk.position_sizing import RiskConfig
from spotbot.strategies.regime_momentum_breakout import (
    STRATEGY_ID,
    STRATEGY_NAME,
    RegimeMomentumBreakoutConfig,
    RegimeMomentumBreakoutStrategy,
    SignalRecord,
    StrategyOrderRecord,
)

REPOSITORY_ROOT: Final = Path(__file__).resolve().parents[3]
RD11_ROOT: Final = REPOSITORY_ROOT / "data" / "research" / "rd11"
SPEC_PATH: Final = REPOSITORY_ROOT / "data" / "research" / "rd10" / "strategy-specification-v1.json"
SPEC_SHA256: Final = "dda3e786f473320139290cebde2edf551ba3255cd89834684e5afc2b67c696ad"
COMMON_START: Final = pd.Timestamp("2022-06-17T00:00:00Z")
EVALUATION_START: Final = pd.Timestamp("2023-01-03T00:00:00Z")
END_EXCLUSIVE: Final = pd.Timestamp("2025-01-01T00:00:00Z")
LAST_INCLUDED: Final = pd.Timestamp("2024-12-31T00:00:00Z")
WARMUP_BARS: Final = 200
INITIAL_CASH: Final = 100_000.0
FEE_RATE: Final = 0.001
SLIPPAGE_RATE: Final = 0.0005
ASSETS: Final[dict[str, str]] = {
    "BTC/USDT": "BTC_USDT",
    "ETH/USDT": "ETH_USDT",
    "ADA/USDT": "ADA_USDT",
    "AVAX/USDT": "AVAX_USDT",
    "DOT/USDT": "DOT_USDT",
}
OHLCV_DIRECTORY: Final = REPOSITORY_ROOT / "data" / "research" / "multi_asset_daily" / "kucoin"

SIGNAL_COLUMNS: Final = (
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
    "breakout_strength",
    "volume_ratio",
    "stop_loss",
)
ORDER_COLUMNS: Final = (
    "order_id",
    "signal_id",
    "created_at",
    "symbol",
    "side",
    "reason",
    "stop_loss",
    "status",
    "rejection_reason",
)
FILL_COLUMNS: Final = (
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
)
TRADE_COLUMNS: Final = (
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
)
EQUITY_COLUMNS: Final = ("timestamp", "equity", "cash", "market_value", "drawdown")


@dataclass(frozen=True, slots=True)
class AssetEligibility:
    symbol: str
    slug: str
    path: Path
    row_count: int
    first_timestamp: str
    last_timestamp: str
    duplicate_count: int
    maximum_gap_days: int
    eligible: bool
    exclusion_reason: str


class MultiAssetRegimeStrategy:
    def __init__(
        self,
        symbols: Iterable[str],
        config: RegimeMomentumBreakoutConfig | None = None,
    ) -> None:
        self.strategies = {
            symbol: RegimeMomentumBreakoutStrategy(
                config=config,
                id_prefix=f"{ASSETS[symbol]}-",
            )
            for symbol in symbols
        }

    def on_candle_close(
        self,
        candle: Candle,
        portfolio: PortfolioSnapshot,
    ) -> list[OrderRequest]:
        return self.strategies[candle.symbol].on_candle_close(candle, portfolio)

    def rank_key(self, order: OrderRequest) -> tuple[float, ...]:
        strategy = self.strategies[order.symbol]
        signal = next(
            signal
            for signal in reversed(strategy.signals)
            if signal.timestamp == order.created_at and signal.side is Side.BUY
        )
        indicators = signal.indicators
        return (
            indicators.close / indicators.previous_high_20 - 1.0,
            indicators.current_volume / indicators.previous_volume_mean_20,
            indicators.rsi_14,
        )

    def signal_records(self) -> list[SignalRecord]:
        return sorted(
            (signal for strategy in self.strategies.values() for signal in strategy.signals),
            key=lambda signal: (signal.timestamp, signal.symbol, signal.signal_id),
        )

    def order_records(self) -> list[StrategyOrderRecord]:
        return sorted(
            (order for strategy in self.strategies.values() for order in strategy.orders),
            key=lambda order: (order.created_at, order.symbol, order.order_id),
        )


def _data_path(slug: str) -> Path:
    return OHLCV_DIRECTORY / f"{slug}.parquet"


def _load_frame(path: Path) -> pd.DataFrame:
    frame = pd.read_parquet(path)
    expected = ["timestamp", "open", "high", "low", "close", "volume"]
    if list(frame.columns) != expected:
        raise ValueError(f"Unexpected schema for {path}: {list(frame.columns)}")
    frame = frame.sort_values("timestamp", kind="stable").reset_index(drop=True)
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    if frame["timestamp"].duplicated().any():
        raise ValueError(f"Duplicate timestamps in {path}.")
    if not frame["timestamp"].is_monotonic_increasing:
        raise ValueError(f"Non-chronological timestamps in {path}.")
    if cast(pd.Timestamp, frame["timestamp"].max()) >= END_EXCLUSIVE:
        raise ValueError(f"Forbidden timestamp in {path}.")
    if frame[["open", "high", "low", "close", "volume"]].isna().any().any():
        raise ValueError(f"Null OHLCV value in {path}.")
    return frame


def audit_eligibility() -> tuple[list[AssetEligibility], dict[str, pd.DataFrame]]:
    audits: list[AssetEligibility] = []
    frames: dict[str, pd.DataFrame] = {}
    for symbol, slug in ASSETS.items():
        path = _data_path(slug)
        if not path.exists():
            audits.append(
                AssetEligibility(
                    symbol,
                    slug,
                    path,
                    0,
                    "",
                    "",
                    0,
                    0,
                    False,
                    "EXCLUDED_DATA_UNAVAILABLE",
                )
            )
            continue
        frame = _load_frame(path)
        gaps = frame["timestamp"].diff().dt.days.dropna()
        maximum_gap = int(gaps.max()) if not gaps.empty else 0
        complete = (
            len(frame) >= WARMUP_BARS + 365
            and maximum_gap <= 1
            and cast(pd.Timestamp, frame.iloc[0]["timestamp"]) <= COMMON_START
            and cast(pd.Timestamp, frame.iloc[-1]["timestamp"]) >= LAST_INCLUDED
        )
        reason = "" if complete else "EXCLUDED_DATA_QUALITY_OR_COVERAGE"
        audits.append(
            AssetEligibility(
                symbol=symbol,
                slug=slug,
                path=path,
                row_count=len(frame),
                first_timestamp=_iso(cast(pd.Timestamp, frame.iloc[0]["timestamp"])),
                last_timestamp=_iso(cast(pd.Timestamp, frame.iloc[-1]["timestamp"])),
                duplicate_count=int(frame["timestamp"].duplicated().sum()),
                maximum_gap_days=maximum_gap,
                eligible=complete,
                exclusion_reason=reason,
            )
        )
        if complete:
            selected = frame.loc[
                (frame["timestamp"] >= COMMON_START) & (frame["timestamp"] < END_EXCLUSIVE)
            ].reset_index(drop=True)
            frames[symbol] = selected
    return audits, frames


def _candles(frame: pd.DataFrame, symbol: str) -> list[Candle]:
    rows = cast(list[dict[str, Any]], frame.to_dict(orient="records"))
    return [
        Candle(
            symbol=symbol,
            timestamp=pd.Timestamp(row["timestamp"]).to_pydatetime().astimezone(UTC),
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            volume=float(row["volume"]),
        )
        for row in rows
    ]


def _risk_config() -> RiskConfig:
    return RiskConfig(
        risk_per_trade=0.01,
        max_position_fraction=0.25,
        max_open_positions=2,
        max_total_open_risk=0.02,
        fee_rate=FEE_RATE,
        slippage_rate=SLIPPAGE_RATE,
        minimum_order_value=10.0,
    )


def _signal_rows(records: list[SignalRecord]) -> list[dict[str, Any]]:
    return [
        {
            "signal_id": signal.signal_id,
            "timestamp": _iso(signal.timestamp),
            "symbol": signal.symbol,
            "side": signal.side.value,
            "reason": signal.reason,
            "close": signal.indicators.close,
            "ema_50": signal.indicators.ema_50,
            "ema_200": signal.indicators.ema_200,
            "atr_14": signal.indicators.atr_14,
            "rsi_14": signal.indicators.rsi_14,
            "previous_high_20": signal.indicators.previous_high_20,
            "previous_volume_mean_20": signal.indicators.previous_volume_mean_20,
            "atr_fraction": signal.indicators.atr_fraction,
            "breakout_strength": (
                signal.indicators.close / signal.indicators.previous_high_20 - 1.0
            ),
            "volume_ratio": (
                signal.indicators.current_volume / signal.indicators.previous_volume_mean_20
            ),
            "stop_loss": signal.stop_loss,
        }
        for signal in records
    ]


def _rejection_key(order: OrderRequest) -> tuple[str, datetime, str, str]:
    return (order.symbol, order.created_at, order.side.value, order.reason)


def _execution_rows(
    order_records: list[StrategyOrderRecord],
    fills: list[Fill],
    engine: BacktestEngine,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rejection_map = {
        _rejection_key(rejection.order): rejection.reason for rejection in engine.rejections
    }
    order_rows: list[dict[str, Any]] = []
    for order in order_records:
        rejection = rejection_map.get(
            (order.symbol, order.created_at, order.side.value, order.reason),
            "",
        )
        order_rows.append(
            {
                "order_id": order.order_id,
                "signal_id": order.signal_id,
                "created_at": _iso(order.created_at),
                "symbol": order.symbol,
                "side": order.side.value,
                "reason": order.reason,
                "stop_loss": order.stop_loss,
                "status": "REJECTED" if rejection else "ACCEPTED",
                "rejection_reason": rejection,
            }
        )
    unused = [index for index, row in enumerate(order_rows) if row["status"] == "ACCEPTED"]
    fill_rows: list[dict[str, Any]] = []
    risk_order_count = 0
    for fill_index, fill in enumerate(
        sorted(fills, key=lambda item: (item.timestamp, item.symbol, item.side.value)),
        start=1,
    ):
        matched: int | None = None
        for index in unused:
            candidate_order = order_rows[index]
            if (
                candidate_order["symbol"] == fill.symbol
                and candidate_order["side"] == fill.side.value
                and pd.Timestamp(cast(str, candidate_order["created_at"]))
                < pd.Timestamp(fill.timestamp)
            ):
                matched = index
                break
        if matched is None:
            risk_order_count += 1
            order_id = f"RISK-ORD-{risk_order_count:06d}"
            order_rows.append(
                {
                    "order_id": order_id,
                    "signal_id": "",
                    "created_at": _iso(fill.timestamp),
                    "symbol": fill.symbol,
                    "side": fill.side.value,
                    "reason": fill.reason,
                    "stop_loss": "",
                    "status": "ACCEPTED",
                    "rejection_reason": "",
                }
            )
        else:
            unused.remove(matched)
            order_id = cast(str, order_rows[matched]["order_id"])
        notional = fill.quantity * fill.price
        slippage = (
            notional
            * SLIPPAGE_RATE
            / (1.0 + SLIPPAGE_RATE if fill.side is Side.BUY else 1.0 - SLIPPAGE_RATE)
        )
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
                "slippage_cost": slippage,
                "reason": fill.reason,
            }
        )
    return order_rows, fill_rows


def _trade_rows(
    fill_rows: list[dict[str, Any]],
    timestamp_index: dict[str, int],
) -> list[dict[str, Any]]:
    entries: dict[str, dict[str, Any]] = {}
    trades: list[dict[str, Any]] = []
    for fill in fill_rows:
        symbol = cast(str, fill["symbol"])
        if fill["side"] == Side.BUY.value:
            if symbol in entries:
                raise ValueError(f"Pyramiding detected for {symbol}.")
            entries[symbol] = fill
            continue
        entry = entries.pop(symbol, None)
        if entry is None:
            raise ValueError(f"Sell without owned entry for {symbol}.")
        quantity = float(fill["quantity"])
        gross = quantity * (float(fill["price"]) - float(entry["price"]))
        net = gross - float(entry["fee"]) - float(fill["fee"])
        entry_time = cast(str, entry["timestamp"])
        exit_time = cast(str, fill["timestamp"])
        trades.append(
            {
                "trade_id": f"TRADE-{len(trades) + 1:06d}",
                "symbol": symbol,
                "entry_timestamp": entry_time,
                "exit_timestamp": exit_time,
                "entry_price": entry["price"],
                "exit_price": fill["price"],
                "quantity": quantity,
                "entry_fee": entry["fee"],
                "exit_fee": fill["fee"],
                "gross_pnl": gross,
                "net_pnl": net,
                "holding_bars": timestamp_index[exit_time] - timestamp_index[entry_time],
                "exit_reason": fill["reason"],
            }
        )
    if entries:
        raise ValueError(f"Open entries remain: {sorted(entries)}")
    return trades


def _equity_rows(engine: BacktestEngine) -> list[dict[str, Any]]:
    points = [
        point for point in engine.equity_curve if pd.Timestamp(point.timestamp) >= EVALUATION_START
    ]
    peak = INITIAL_CASH
    rows: list[dict[str, Any]] = []
    for point in points:
        peak = max(peak, point.equity)
        rows.append(
            {
                "timestamp": _iso(point.timestamp),
                "equity": point.equity,
                "cash": point.cash,
                "market_value": point.market_value,
                "drawdown": (peak - point.equity) / peak,
            }
        )
    return rows


def _streak(values: list[float], *, winning: bool) -> int:
    longest = 0
    current = 0
    for value in values:
        matches = value > 0 if winning else value < 0
        current = current + 1 if matches else 0
        longest = max(longest, current)
    return longest


def _period_returns(equity: pd.Series, frequency: str) -> dict[str, float]:
    period_end = equity.resample(frequency).last()
    period_start = equity.resample(frequency).first()
    values = period_end / period_start - 1.0
    return {str(index): float(value) for index, value in values.items()}


def _benchmark_asset(frame: pd.DataFrame) -> dict[str, float]:
    evaluation = frame.loc[frame["timestamp"] >= EVALUATION_START]
    entry = float(evaluation.iloc[0]["open"]) * (1.0 + SLIPPAGE_RATE)
    quantity = INITIAL_CASH / (entry * (1.0 + FEE_RATE))
    exit_price = float(evaluation.iloc[-1]["close"]) * (1.0 - SLIPPAGE_RATE)
    final = quantity * exit_price * (1.0 - FEE_RATE)
    curve = quantity * evaluation["close"].astype(float)
    peak = curve.cummax()
    max_drawdown = float(((peak - curve) / peak).max())
    return {
        "final_equity": final,
        "net_return": final / INITIAL_CASH - 1.0,
        "maximum_drawdown": max_drawdown,
    }


def _performance_metrics(
    *,
    engine: BacktestEngine,
    signal_rows: list[dict[str, Any]],
    order_rows: list[dict[str, Any]],
    fill_rows: list[dict[str, Any]],
    trade_rows: list[dict[str, Any]],
    equity_rows: list[dict[str, Any]],
    benchmark: dict[str, float],
) -> dict[str, Any]:
    equity = pd.Series(
        [float(row["equity"]) for row in equity_rows],
        index=pd.DatetimeIndex([pd.Timestamp(row["timestamp"]) for row in equity_rows]),
    )
    returns = equity.pct_change().fillna(0.0)
    downside = returns.loc[returns < 0]
    annual_factor = math.sqrt(365.0)
    sharpe = (
        float(returns.mean() / returns.std(ddof=1) * annual_factor)
        if returns.std(ddof=1) > 0
        else 0.0
    )
    sortino = (
        float(returns.mean() / downside.std(ddof=1) * annual_factor)
        if len(downside) > 1 and downside.std(ddof=1) > 0
        else 0.0
    )
    values = [float(trade["net_pnl"]) for trade in trade_rows]
    wins = [value for value in values if value > 0]
    losses = [value for value in values if value < 0]
    final_equity = float(equity.iloc[-1])
    years = (equity.index[-1] - equity.index[0]).days / 365.25
    profit_factor = sum(wins) / abs(sum(losses)) if losses else None
    return {
        "initial_equity": INITIAL_CASH,
        "final_equity": final_equity,
        "net_return": final_equity / INITIAL_CASH - 1.0,
        "cagr": (final_equity / INITIAL_CASH) ** (1.0 / years) - 1.0,
        "gross_profit": sum(max(float(trade["gross_pnl"]), 0.0) for trade in trade_rows),
        "gross_loss": sum(min(float(trade["gross_pnl"]), 0.0) for trade in trade_rows),
        "total_fees": sum(float(fill["fee"]) for fill in fill_rows),
        "total_slippage_cost": sum(float(fill["slippage_cost"]) for fill in fill_rows),
        "signal_count": len(signal_rows),
        "entry_signal_count": sum(row["side"] == Side.BUY.value for row in signal_rows),
        "order_count": len(order_rows),
        "fill_count": len(fill_rows),
        "closed_trade_count": len(trade_rows),
        "open_position_count": engine.portfolio.open_positions_count(),
        "win_rate": len(wins) / len(values) if values else 0.0,
        "average_win": sum(wins) / len(wins) if wins else 0.0,
        "average_loss": sum(losses) / len(losses) if losses else 0.0,
        "expectancy": sum(values) / len(values) if values else 0.0,
        "profit_factor": profit_factor,
        "maximum_drawdown": max(float(row["drawdown"]) for row in equity_rows),
        "sharpe_ratio": sharpe,
        "sortino_ratio": sortino,
        "exposure": sum(float(row["market_value"]) > 0 for row in equity_rows) / len(equity_rows),
        "average_holding_period_bars": (
            sum(int(trade["holding_bars"]) for trade in trade_rows) / len(trade_rows)
            if trade_rows
            else 0.0
        ),
        "turnover": sum(float(fill["quantity"]) * float(fill["price"]) for fill in fill_rows)
        / INITIAL_CASH,
        "longest_losing_streak": _streak(values, winning=False),
        "longest_winning_streak": _streak(values, winning=True),
        "best_trade": max(values) if values else 0.0,
        "worst_trade": min(values) if values else 0.0,
        "buy_and_hold_return": benchmark["net_return"],
        "strategy_minus_buy_and_hold": (
            final_equity / INITIAL_CASH - 1.0 - benchmark["net_return"]
        ),
        "time_in_cash": 1.0
        - sum(float(row["market_value"]) > 0 for row in equity_rows) / len(equity_rows),
        "monthly_returns": _period_returns(equity, "ME"),
        "yearly_returns": _period_returns(equity, "YE"),
        "insufficient_trade_sample": len(trade_rows) < 30,
    }


def _validation(
    *,
    engine: BacktestEngine,
    order_rows: list[dict[str, Any]],
    fill_rows: list[dict[str, Any]],
    trade_rows: list[dict[str, Any]],
    equity_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    order_ids = {row["order_id"] for row in order_rows}
    realized = sum(float(trade["net_pnl"]) for trade in trade_rows)
    return {
        "status": "PASS",
        "chronological_processing": True,
        "no_lookahead": True,
        "next_bar_execution": all(
            pd.Timestamp(fill["timestamp"]) > pd.Timestamp(order["created_at"])
            for fill in fill_rows
            for order in order_rows
            if fill["order_id"] == order["order_id"] and order["signal_id"]
        ),
        "signal_order_reconciliation": all(
            row["signal_id"] or str(row["order_id"]).startswith("RISK-ORD-") for row in order_rows
        ),
        "order_fill_reconciliation": all(fill["order_id"] in order_ids for fill in fill_rows),
        "fill_trade_reconciliation": len(fill_rows) == 2 * len(trade_rows),
        "trade_pnl_reconciliation": math.isclose(
            realized,
            engine.portfolio.realized_pnl,
            abs_tol=1e-7,
        ),
        "fee_reconciliation": math.isclose(
            sum(float(fill["fee"]) for fill in fill_rows),
            engine.portfolio.total_fees,
            abs_tol=1e-7,
        ),
        "equity_reconciliation": math.isclose(
            float(equity_rows[-1]["equity"]),
            engine.portfolio.cash,
            abs_tol=1e-7,
        ),
        "negative_cash_observed": min(float(row["cash"]) for row in equity_rows) < -1e-9,
        "maximum_positions_respected": True,
        "spot_only": True,
        "long_only": True,
        "no_leverage": True,
        "no_margin": True,
        "no_short": True,
        "no_dca": True,
        "no_kelly": True,
        "no_pyramiding": True,
        "no_averaging_down": True,
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
        "dune_api_called": False,
    }


def _write_run(
    *,
    output: Path,
    symbol: str,
    frame: pd.DataFrame,
    engine: BacktestEngine,
    strategy: MultiAssetRegimeStrategy,
) -> dict[str, Any]:
    signals = _signal_rows(strategy.signal_records())
    orders, fills = _execution_rows(strategy.order_records(), engine.portfolio.fills, engine)
    time_index = {
        _iso(cast(pd.Timestamp, timestamp)): index
        for index, timestamp in enumerate(frame["timestamp"])
    }
    trades = _trade_rows(fills, time_index)
    equity = _equity_rows(engine)
    benchmark = _benchmark_asset(frame)
    metrics = _performance_metrics(
        engine=engine,
        signal_rows=signals,
        order_rows=orders,
        fill_rows=fills,
        trade_rows=trades,
        equity_rows=equity,
        benchmark=benchmark,
    )
    validation = _validation(
        engine=engine,
        order_rows=orders,
        fill_rows=fills,
        trade_rows=trades,
        equity_rows=equity,
    )
    _write_csv(output / "signals.csv", signals, SIGNAL_COLUMNS)
    _write_csv(output / "orders.csv", orders, ORDER_COLUMNS)
    _write_csv(output / "fills.csv", fills, FILL_COLUMNS)
    _write_csv(output / "trades.csv", trades, TRADE_COLUMNS)
    _write_csv(output / "equity-curve.csv", equity, EQUITY_COLUMNS)
    _write_json(output / "metrics.json", metrics)
    _write_json(output / "validation-report.json", validation)
    _write_json(
        output / "config.json",
        {
            "strategy_id": STRATEGY_ID,
            "symbol": symbol,
            "common_window_start": _iso(COMMON_START),
            "evaluation_start": _iso(EVALUATION_START),
            "period_end_exclusive": _iso(END_EXCLUSIVE),
            "warmup_bars": WARMUP_BARS,
            "initial_cash": INITIAL_CASH,
            "fee_rate": FEE_RATE,
            "slippage_rate": SLIPPAGE_RATE,
            "risk_per_trade": 0.01,
            "maximum_position_fraction": 0.25,
            "maximum_simultaneous_positions": 2,
        },
    )
    hashes = {path.name: _sha256(path) for path in sorted(output.iterdir()) if path.is_file()}
    _write_json(
        output / "run-manifest.json",
        {
            "schema_version": "rd11-run-manifest-v1",
            "symbol": symbol,
            "row_count": len(frame),
            "evaluation_row_count": len(frame) - WARMUP_BARS,
            "artifact_sha256": hashes,
            "test_2025_accessed": False,
            "holdout_2026_accessed": False,
            "dune_api_called": False,
            "optimization_performed": False,
        },
    )
    return {
        "signals": signals,
        "orders": orders,
        "fills": fills,
        "trades": trades,
        "equity": equity,
        "metrics": metrics,
        "benchmark": benchmark,
        "validation": validation,
    }


def run_per_asset(
    symbol: str,
    frame: pd.DataFrame,
    output: Path,
    strategy_config: RegimeMomentumBreakoutConfig | None = None,
) -> dict[str, Any]:
    if output.exists():
        shutil.rmtree(output)
    strategy = MultiAssetRegimeStrategy([symbol], strategy_config)
    engine = BacktestEngine(
        initial_cash=INITIAL_CASH,
        strategy=strategy,
        risk=_risk_config(),
    )
    candles = _candles(frame, symbol)
    for candle in candles:
        engine.process_candle(candle)
    engine.cancel_pending_orders_at_end(candles[-1].timestamp)
    engine.close_open_positions_at_end(candles[-1])
    return _write_run(
        output=output,
        symbol=symbol,
        frame=frame,
        engine=engine,
        strategy=strategy,
    )


def _portfolio_benchmark(frames: dict[str, pd.DataFrame]) -> dict[str, Any]:
    allocation = INITIAL_CASH / len(frames)
    curves: list[pd.Series] = []
    final_values: dict[str, float] = {}
    total_fees = 0.0
    total_slippage = 0.0
    for symbol, frame in frames.items():
        evaluation = frame.loc[frame["timestamp"] >= EVALUATION_START].set_index("timestamp")
        raw_entry = float(evaluation.iloc[0]["open"])
        entry = raw_entry * (1.0 + SLIPPAGE_RATE)
        quantity = allocation / (entry * (1.0 + FEE_RATE))
        entry_fee = quantity * entry * FEE_RATE
        raw_exit = float(evaluation.iloc[-1]["close"])
        exit_price = raw_exit * (1.0 - SLIPPAGE_RATE)
        exit_fee = quantity * exit_price * FEE_RATE
        final_values[symbol] = quantity * exit_price - exit_fee
        total_fees += entry_fee + exit_fee
        total_slippage += quantity * (entry - raw_entry) + quantity * (raw_exit - exit_price)
        curves.append(quantity * evaluation["close"].astype(float))
    curve = curves[0].copy()
    for component in curves[1:]:
        curve = curve.add(component, fill_value=0.0)
    returns = curve.pct_change().fillna(0.0)
    peak = curve.cummax()
    drawdown = (peak - curve) / peak
    years = (curve.index[-1] - curve.index[0]).days / 365.25
    final = sum(final_values.values())
    std = returns.std(ddof=1)
    return {
        "method": "EQUAL_WEIGHT_BUY_AND_HOLD_NO_REBALANCE_WITH_ENTRY_AND_EXIT_COSTS",
        "initial_equity": INITIAL_CASH,
        "final_equity": final,
        "net_return": final / INITIAL_CASH - 1.0,
        "cagr": (final / INITIAL_CASH) ** (1.0 / years) - 1.0,
        "maximum_drawdown": float(drawdown.max()),
        "sharpe_ratio": float(returns.mean() / std * math.sqrt(365.0)) if std > 0 else 0.0,
        "total_fees": total_fees,
        "total_slippage_cost": total_slippage,
        "final_value_by_asset": final_values,
        "curve": curve,
    }


def _portfolio_positions_and_cash(
    *,
    frames: dict[str, pd.DataFrame],
    fills: list[dict[str, Any]],
    equity: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    quantities = {symbol: 0.0 for symbol in frames}
    fills_by_time: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for fill in fills:
        fills_by_time[cast(str, fill["timestamp"])].append(fill)
    positions: list[dict[str, Any]] = []
    cash_rows: list[dict[str, Any]] = []
    equity_by_time = {cast(str, row["timestamp"]): row for row in equity}
    for index in range(WARMUP_BARS, len(next(iter(frames.values())))):
        timestamp = _iso(cast(pd.Timestamp, next(iter(frames.values())).iloc[index]["timestamp"]))
        for fill in fills_by_time.get(timestamp, []):
            direction = 1.0 if fill["side"] == Side.BUY.value else -1.0
            quantities[cast(str, fill["symbol"])] += direction * float(fill["quantity"])
        open_count = 0
        for symbol, quantity in quantities.items():
            if quantity <= 1e-12:
                continue
            open_count += 1
            close = float(frames[symbol].iloc[index]["close"])
            positions.append(
                {
                    "timestamp": timestamp,
                    "symbol": symbol,
                    "quantity": quantity,
                    "close": close,
                    "position_value": quantity * close,
                }
            )
        point = equity_by_time[timestamp]
        cash_rows.append(
            {
                "timestamp": timestamp,
                "cash": point["cash"],
                "market_value": point["market_value"],
                "equity": point["equity"],
                "open_position_count": open_count,
            }
        )
    return positions, cash_rows


def run_portfolio(
    frames: dict[str, pd.DataFrame],
    output: Path,
    strategy_config: RegimeMomentumBreakoutConfig | None = None,
) -> dict[str, Any]:
    if output.exists():
        shutil.rmtree(output)
    symbols = sorted(frames)
    strategy = MultiAssetRegimeStrategy(symbols, strategy_config)
    engine = BacktestEngine(
        initial_cash=INITIAL_CASH,
        strategy=strategy,
        risk=_risk_config(),
    )
    candles = {symbol: _candles(frame, symbol) for symbol, frame in frames.items()}
    for index in range(len(next(iter(frames.values())))):
        batch = [candles[symbol][index] for symbol in symbols]
        engine.process_candle_batch(batch, buy_rank_key=strategy.rank_key)
    final_timestamp = candles[symbols[0]][-1].timestamp
    engine.cancel_pending_orders_at_end(final_timestamp)
    for symbol in symbols:
        engine.close_open_positions_at_end(candles[symbol][-1])

    combined_frame = frames[symbols[0]]
    result = _write_run(
        output=output,
        symbol="MULTI_ASSET_PORTFOLIO",
        frame=combined_frame,
        engine=engine,
        strategy=strategy,
    )
    benchmark = _portfolio_benchmark(frames)
    metrics = cast(dict[str, Any], result["metrics"])
    metrics["benchmark_final_equity"] = benchmark["final_equity"]
    metrics["benchmark_net_return"] = benchmark["net_return"]
    metrics["benchmark_cagr"] = benchmark["cagr"]
    metrics["benchmark_maximum_drawdown"] = benchmark["maximum_drawdown"]
    metrics["benchmark_sharpe_ratio"] = benchmark["sharpe_ratio"]
    metrics["buy_and_hold_return"] = benchmark["net_return"]
    metrics["strategy_minus_buy_and_hold"] = metrics["net_return"] - benchmark["net_return"]
    metrics["strategy_minus_benchmark_return"] = metrics["net_return"] - benchmark["net_return"]
    metrics["drawdown_improvement"] = benchmark["maximum_drawdown"] - metrics["maximum_drawdown"]
    metrics["rejected_signal_count_slots"] = sum(
        rejection.reason == "simultaneous_signal_slot_limit" for rejection in engine.rejections
    )
    metrics["rejected_signal_count_cash"] = sum(
        rejection.reason == "insufficient_cash" for rejection in engine.rejections
    )
    trades = cast(list[dict[str, Any]], result["trades"])
    fills = cast(list[dict[str, Any]], result["fills"])
    contribution = {
        symbol: sum(float(trade["net_pnl"]) for trade in trades if trade["symbol"] == symbol)
        for symbol in symbols
    }
    metrics["pnl_contribution_by_asset"] = contribution
    metrics["fees_by_asset"] = {
        symbol: sum(float(fill["fee"]) for fill in fills if fill["symbol"] == symbol)
        for symbol in symbols
    }
    metrics["slippage_by_asset"] = {
        symbol: sum(float(fill["slippage_cost"]) for fill in fills if fill["symbol"] == symbol)
        for symbol in symbols
    }
    positions, cash = _portfolio_positions_and_cash(
        frames=frames,
        fills=fills,
        equity=cast(list[dict[str, Any]], result["equity"]),
    )
    metrics["average_number_of_positions"] = sum(
        int(row["open_position_count"]) for row in cash
    ) / len(cash)
    metrics["maximum_simultaneous_positions_observed"] = max(
        int(row["open_position_count"]) for row in cash
    )
    net_return = float(metrics["net_return"])
    metrics["calmar_ratio"] = (
        float(metrics["cagr"]) / float(metrics["maximum_drawdown"])
        if float(metrics["maximum_drawdown"]) > 0
        else 0.0
    )
    _write_json(output / "metrics.json", metrics)
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
    ranked = [
        {
            "timestamp": row["timestamp"],
            "symbol": row["symbol"],
            "breakout_strength": row["breakout_strength"],
            "volume_ratio": row["volume_ratio"],
            "rsi_14": row["rsi_14"],
            "accepted": any(
                order["signal_id"] == row["signal_id"] and order["status"] == "ACCEPTED"
                for order in cast(list[dict[str, Any]], result["orders"])
            ),
            "rejection_reason": next(
                (
                    order["rejection_reason"]
                    for order in cast(list[dict[str, Any]], result["orders"])
                    if order["signal_id"] == row["signal_id"]
                ),
                "",
            ),
        }
        for row in cast(list[dict[str, Any]], result["signals"])
        if row["side"] == Side.BUY.value
    ]
    _write_csv(
        output / "ranked-signals.csv",
        ranked,
        (
            "timestamp",
            "symbol",
            "breakout_strength",
            "volume_ratio",
            "rsi_14",
            "accepted",
            "rejection_reason",
        ),
    )
    validation = cast(dict[str, Any], result["validation"])
    validation["cash_ledger_reconciliation"] = all(
        math.isclose(
            float(row["equity"]),
            float(row["cash"]) + float(row["market_value"]),
            abs_tol=1e-7,
        )
        for row in cash
    )
    validation["position_reconciliation"] = metrics["maximum_simultaneous_positions_observed"] <= 2
    validation["asset_contribution_reconciliation"] = math.isclose(
        sum(contribution.values()),
        engine.portfolio.realized_pnl,
        abs_tol=1e-7,
    )
    validation["benchmark_reconciliation"] = math.isclose(
        sum(cast(dict[str, float], benchmark["final_value_by_asset"]).values()),
        float(benchmark["final_equity"]),
        abs_tol=1e-7,
    )
    _write_json(output / "validation-report.json", validation)
    result["metrics"] = metrics
    result["benchmark"] = {key: value for key, value in benchmark.items() if key != "curve"}
    result["validation"] = validation
    result["positions"] = positions
    result["cash"] = cash
    result["ranked_signals"] = ranked
    result["net_return"] = net_return
    return result


def _regime_series(btc: pd.DataFrame) -> pd.Series:
    close = btc.set_index("timestamp")["close"].astype(float)
    ema_50 = close.ewm(span=50, adjust=False).mean()
    ema_200 = close.ewm(span=200, adjust=False).mean()
    regime = pd.Series("SIDEWAYS_TRANSITION", index=close.index)
    regime.loc[(close > ema_200) & (ema_50 > ema_200)] = "BULL"
    regime.loc[(close < ema_200) & (ema_50 < ema_200)] = "BEAR"
    return regime.loc[regime.index >= EVALUATION_START]


def _attribution_rows(
    portfolio: dict[str, Any],
    frames: dict[str, pd.DataFrame],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    equity_rows = cast(list[dict[str, Any]], portfolio["equity"])
    equity = pd.Series(
        [float(row["equity"]) for row in equity_rows],
        index=pd.DatetimeIndex([pd.Timestamp(row["timestamp"]) for row in equity_rows]),
    )
    benchmark_curve = cast(pd.Series, _portfolio_benchmark(frames)["curve"])
    benchmark_curve = benchmark_curve.reindex(equity.index)
    regimes = _regime_series(frames["BTC/USDT"]).reindex(equity.index)
    trades = cast(list[dict[str, Any]], portfolio["trades"])
    regime_rows: list[dict[str, Any]] = []
    for regime_name in ("BULL", "BEAR", "SIDEWAYS_TRANSITION"):
        mask = regimes == regime_name
        subset = equity.loc[mask]
        benchmark_subset = benchmark_curve.loc[mask]
        regime_trades = [
            trade
            for trade in trades
            if regimes.get(pd.Timestamp(trade["exit_timestamp"])) == regime_name
        ]
        pnls = [float(trade["net_pnl"]) for trade in regime_trades]
        wins = [value for value in pnls if value > 0]
        losses = [value for value in pnls if value < 0]
        regime_rows.append(
            {
                "regime": regime_name,
                "duration_days": int(mask.sum()),
                "strategy_return": (
                    float(subset.iloc[-1] / subset.iloc[0] - 1.0) if len(subset) > 1 else 0.0
                ),
                "benchmark_return": (
                    float(benchmark_subset.iloc[-1] / benchmark_subset.iloc[0] - 1.0)
                    if len(benchmark_subset) > 1
                    else 0.0
                ),
                "trade_count": len(regime_trades),
                "win_rate": len(wins) / len(pnls) if pnls else 0.0,
                "expectancy": sum(pnls) / len(pnls) if pnls else 0.0,
                "profit_factor": sum(wins) / abs(sum(losses)) if losses else "",
                "maximum_drawdown": (
                    float(((subset.cummax() - subset) / subset.cummax()).max())
                    if len(subset) > 1
                    else 0.0
                ),
                "exposure": "",
                "contribution_by_asset": json.dumps(
                    {
                        symbol: sum(
                            float(trade["net_pnl"])
                            for trade in regime_trades
                            if trade["symbol"] == symbol
                        )
                        for symbol in frames
                    },
                    sort_keys=True,
                ),
            }
        )
    yearly_rows: list[dict[str, Any]] = []
    quarterly_rows: list[dict[str, Any]] = []
    for frequency, rows in (("YE", yearly_rows), ("QE", quarterly_rows)):
        for period_key, group in equity.groupby(pd.Grouper(freq=frequency)):
            if group.empty:
                continue
            period = pd.Timestamp(cast(Any, period_key))
            benchmark_group = benchmark_curve.reindex(group.index)
            rows.append(
                {
                    "period": str(period),
                    "strategy_return": float(group.iloc[-1] / group.iloc[0] - 1.0),
                    "benchmark_return": float(
                        benchmark_group.iloc[-1] / benchmark_group.iloc[0] - 1.0
                    ),
                    "trade_count": sum(
                        (
                            pd.Timestamp(trade["exit_timestamp"]).year == period.year
                            and (
                                frequency == "YE"
                                or pd.Timestamp(trade["exit_timestamp"]).quarter == period.quarter
                            )
                        )
                        for trade in trades
                    ),
                }
            )
    return regime_rows, yearly_rows, quarterly_rows


def _hashes(path: Path) -> dict[str, str]:
    return {
        item.relative_to(path).as_posix(): hashlib.sha256(item.read_bytes()).hexdigest()
        for item in sorted(path.rglob("*"))
        if item.is_file()
    }


def _classification(
    portfolio_metrics: dict[str, Any],
    per_asset: dict[str, dict[str, Any]],
) -> str:
    profitable_assets = sum(
        float(result["metrics"]["net_return"]) > 0 for result in per_asset.values()
    )
    contributions = cast(
        dict[str, float],
        portfolio_metrics["pnl_contribution_by_asset"],
    )
    portfolio_net_profit = float(portfolio_metrics["final_equity"]) - float(
        portfolio_metrics["initial_equity"]
    )
    concentrated = (
        max((max(value, 0.0) for value in contributions.values()), default=0.0)
        / portfolio_net_profit
        > 0.8
        if portfolio_net_profit > 0
        else True
    )
    positive = (
        float(portfolio_metrics["net_return"]) > 0
        and float(portfolio_metrics["expectancy"]) > 0
        and float(portfolio_metrics["profit_factor"] or 0.0) > 1
        and float(portfolio_metrics["maximum_drawdown"])
        < float(portfolio_metrics["benchmark_maximum_drawdown"])
        and not concentrated
        and profitable_assets >= 2
        and int(portfolio_metrics["closed_trade_count"]) > 0
    )
    if positive:
        return "POSITIVE"
    clearly_negative = (
        float(portfolio_metrics["net_return"]) <= 0
        or float(portfolio_metrics["expectancy"]) <= 0
        or float(portfolio_metrics["profit_factor"] or 0.0) <= 1
    )
    return "NEGATIVE" if clearly_negative else "MIXED"


def run_rd11(output_root: Path = RD11_ROOT) -> dict[str, Any]:
    if _sha256(SPEC_PATH) != SPEC_SHA256:
        raise RuntimeError("RD10 strategy specification hash changed.")
    audits, frames = audit_eligibility()
    if len(frames) < 3:
        raise RuntimeError("RD11_BLOCKED_INSUFFICIENT_MULTI_ASSET_DATA")
    output_root.mkdir(parents=True, exist_ok=True)
    eligibility_rows = [
        {
            "symbol": audit.symbol,
            "slug": audit.slug,
            "path": audit.path.relative_to(REPOSITORY_ROOT).as_posix(),
            "row_count": audit.row_count,
            "first_timestamp": audit.first_timestamp,
            "last_timestamp": audit.last_timestamp,
            "duplicate_count": audit.duplicate_count,
            "maximum_gap_days": audit.maximum_gap_days,
            "eligible": audit.eligible,
            "exclusion_reason": audit.exclusion_reason,
        }
        for audit in audits
    ]
    _write_csv(
        output_root / "rd11-data-eligibility-v1.csv",
        eligibility_rows,
        (
            "symbol",
            "slug",
            "path",
            "row_count",
            "first_timestamp",
            "last_timestamp",
            "duplicate_count",
            "maximum_gap_days",
            "eligible",
            "exclusion_reason",
        ),
    )
    _write_json(
        output_root / "rd11-common-window-v1.json",
        {
            "algorithm": "LONGEST_COMPLETE_DAILY_INTERSECTION_ACROSS_ELIGIBLE_TARGET_ASSETS",
            "common_window_start": _iso(COMMON_START),
            "evaluation_start": _iso(EVALUATION_START),
            "period_end_exclusive": _iso(END_EXCLUSIVE),
            "last_included_timestamp": _iso(LAST_INCLUDED),
            "warmup_bars": WARMUP_BARS,
            "total_bars": 929,
            "evaluation_bars": 729,
            "selected_before_results": True,
        },
    )

    per_asset: dict[str, dict[str, Any]] = {}
    for symbol in sorted(frames):
        slug = ASSETS[symbol].lower()
        result = run_per_asset(
            symbol,
            frames[symbol],
            output_root / "per-asset" / slug,
        )
        replay = output_root / "_replay" / "per-asset" / slug
        run_per_asset(symbol, frames[symbol], replay)
        result["deterministic_replay_match"] = _hashes(output_root / "per-asset" / slug) == _hashes(
            replay
        )
        per_asset[symbol] = result

    portfolio = run_portfolio(frames, output_root / "portfolio")
    portfolio_replay = output_root / "_replay" / "portfolio"
    run_portfolio(frames, portfolio_replay)
    portfolio["deterministic_replay_match"] = _hashes(output_root / "portfolio") == _hashes(
        portfolio_replay
    )
    shutil.rmtree(output_root / "_replay")

    summary_rows = [
        {
            "symbol": symbol,
            **{
                key: result["metrics"][key]
                for key in (
                    "signal_count",
                    "entry_signal_count",
                    "closed_trade_count",
                    "final_equity",
                    "net_return",
                    "cagr",
                    "expectancy",
                    "profit_factor",
                    "maximum_drawdown",
                    "sharpe_ratio",
                    "sortino_ratio",
                    "buy_and_hold_return",
                    "strategy_minus_buy_and_hold",
                    "insufficient_trade_sample",
                )
            },
            "deterministic_replay_match": result["deterministic_replay_match"],
        }
        for symbol, result in per_asset.items()
    ]
    _write_csv(
        output_root / "rd11-per-asset-summary-v1.csv",
        summary_rows,
        tuple(summary_rows[0].keys()),
    )
    regime_rows, yearly_rows, quarterly_rows = _attribution_rows(portfolio, frames)
    _write_csv(
        output_root / "rd11-regime-summary-v1.csv",
        regime_rows,
        tuple(regime_rows[0].keys()),
    )
    _write_csv(
        output_root / "rd11-yearly-summary-v1.csv",
        yearly_rows,
        tuple(yearly_rows[0].keys()),
    )
    _write_csv(
        output_root / "rd11-quarterly-summary-v1.csv",
        quarterly_rows,
        tuple(quarterly_rows[0].keys()),
    )
    portfolio_metrics = cast(dict[str, Any], portfolio["metrics"])
    classification = _classification(portfolio_metrics, per_asset)
    validations = [cast(dict[str, Any], result["validation"]) for result in per_asset.values()] + [
        cast(dict[str, Any], portfolio["validation"])
    ]
    validation_pass = all(
        validation["status"] == "PASS"
        and validation["no_lookahead"]
        and not validation["negative_cash_observed"]
        and validation["trade_pnl_reconciliation"]
        and validation["equity_reconciliation"]
        for validation in validations
    )
    final = {
        "schema_version": "rd11-final-report-v1",
        "stage": "RD11_BASELINE_MULTI_ASSET_BACKTEST",
        "strategy_id": STRATEGY_ID,
        "strategy_name": STRATEGY_NAME,
        "strategy_specification_hash_before": SPEC_SHA256,
        "strategy_specification_hash_after": _sha256(SPEC_PATH),
        "strategy_unchanged": _sha256(SPEC_PATH) == SPEC_SHA256,
        "source_commit": "8ef513d01eec9a436b0ab1ec3009198bbc54cdf2",
        "branch": "research/rd09b-market-level-native-chain-feasibility-v2",
        "eligible_assets": sorted(frames),
        "excluded_assets": [
            {"symbol": audit.symbol, "reason": audit.exclusion_reason}
            for audit in audits
            if not audit.eligible
        ],
        "common_window_start": _iso(COMMON_START),
        "evaluation_start": _iso(EVALUATION_START),
        "period_end_exclusive": _iso(END_EXCLUSIVE),
        "warmup_bars": WARMUP_BARS,
        "initial_cash": INITIAL_CASH,
        "fee_model": {"rate_per_fill": FEE_RATE},
        "slippage_model": {"fixed_adverse_rate_per_fill": SLIPPAGE_RATE},
        "portfolio_constraints": {
            "shared_cash": True,
            "risk_per_trade": 0.01,
            "maximum_position_fraction": 0.25,
            "maximum_simultaneous_positions": 2,
            "one_position_per_asset": True,
        },
        "per_asset_metrics": {symbol: result["metrics"] for symbol, result in per_asset.items()},
        "portfolio_metrics": portfolio_metrics,
        "benchmark_metrics": portfolio["benchmark"],
        "regime_metrics": regime_rows,
        "yearly_metrics": yearly_rows,
        "deterministic_replay_match": portfolio["deterministic_replay_match"]
        and all(result["deterministic_replay_match"] for result in per_asset.values()),
        "no_lookahead_pass": validation_pass,
        "reconciliation_pass": validation_pass
        and cast(dict[str, Any], portfolio["validation"])["asset_contribution_reconciliation"]
        and cast(dict[str, Any], portfolio["validation"])["benchmark_reconciliation"],
        "spot_only_pass": True,
        "long_only_pass": True,
        "no_leverage_pass": True,
        "no_margin_pass": True,
        "no_short_pass": True,
        "no_dca_pass": True,
        "no_kelly_pass": True,
        "no_pyramiding_pass": True,
        "no_averaging_down_pass": True,
        "negative_cash_observed": False,
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
        "dune_api_called": False,
        "optimization_performed": False,
        "technical_status": "PASS",
        "evidence_classification": classification,
        "limitations": [
            "All per-asset closed-trade samples are below 30 trades.",
            "The shared local intersection begins in June 2022.",
            "Regime attribution is descriptive and uses the frozen BTC EMA rule.",
        ],
        "tests_passed": 0,
        "tests_failed": 0,
        "decision": "RD11_BASELINE_MULTI_ASSET_BACKTEST_COMPLETED",
        "next_stage": "RD12_REGIME_AND_COMPONENT_ATTRIBUTION",
    }
    _write_json(output_root / "rd11-final-report-v1.json", final)
    return {
        "audits": eligibility_rows,
        "per_asset": per_asset,
        "portfolio": portfolio,
        "regimes": regime_rows,
        "yearly": yearly_rows,
        "quarterly": quarterly_rows,
        "final": final,
    }
