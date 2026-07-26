"""AMS V4 Active Conviction Swing research protocol.

This module deliberately does not import or mutate AMS V3 strategy state.  It
uses the registered four-hour venue dataset, scores closed-bar opportunities,
and exposes a conservative spot-only portfolio simulation contract.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import numpy as np
import pandas as pd

LOCKED_TEST_START: Final = pd.Timestamp("2025-01-01T00:00:00Z")


class AmsV4Error(RuntimeError):
    """Raised when the frozen AMS V4 research contract is violated."""


@dataclass(frozen=True)
class PortfolioProfile:
    profile_id: str
    name: str
    base_risk_fraction: float
    maximum_initial_risk: float
    maximum_portfolio_heat: float
    maximum_positions: int
    maximum_cluster_positions: int = 2


@dataclass(frozen=True)
class TrialSpecification:
    configuration_id: str
    entry_family: str
    exit_model: str
    fibonacci_mode: str
    score_threshold: int
    portfolio: PortfolioProfile
    transaction_cost: float


@dataclass
class OpenPosition:
    symbol: str
    cluster: str
    quantity: float
    entry_price: float
    initial_stop: float
    stop_price: float
    risk_fraction: float
    entry_time: pd.Timestamp
    entry_notional: float
    entry_fee: float
    partial_taken: bool = False
    add_on_used: bool = False
    highest_price: float = 0.0
    bars_held: int = 0
    mfe_r: float = 0.0
    mae_r: float = 0.0


@dataclass(frozen=True)
class ClosedTrade:
    symbol: str
    entry_time: pd.Timestamp
    exit_time: pd.Timestamp
    entry_price: float
    exit_price: float
    quantity: float
    pnl: float
    return_fraction: float
    initial_risk_per_unit: float
    mae_r: float
    mfe_r: float
    exit_reason: str
    partial_exit_count: int
    add_on_used: bool
    reentry: bool


@dataclass(frozen=True)
class SimulationResult:
    initial_capital: float
    final_equity: float
    equity_curve: pd.DataFrame
    trades: tuple[ClosedTrade, ...]
    rejected_entries: Mapping[str, int]
    candidate_signals: int
    accepted_entries: int
    total_fees: float
    turnover: float
    maximum_heat: float
    add_on_count: int
    reentry_count: int
    partial_exit_count: int


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def assert_research_boundary(frame: pd.DataFrame) -> None:
    for column, inclusive in (("bar_open_time", False), ("bar_close_time", True)):
        if column not in frame.columns:
            continue
        values = pd.to_datetime(frame[column], utc=True, errors="raise")
        invalid = values.gt(LOCKED_TEST_START) if inclusive else values.ge(LOCKED_TEST_START)
        if invalid.any():
            raise AmsV4Error(f"Locked data found in {column}: {values[invalid].max()}")


def portfolio_profiles() -> tuple[PortfolioProfile, ...]:
    return (
        PortfolioProfile("AMS-V4-PORTFOLIO-P01", "ACTIVE_BALANCED", 0.0065, 0.009, 0.04, 5),
        PortfolioProfile("AMS-V4-PORTFOLIO-P02", "CONTROLLED_CONVICTION", 0.009, 0.0125, 0.06, 6),
    )


def build_configuration_grid() -> tuple[dict[str, Any], ...]:
    variants = (
        ("BREAKOUT", "RUNNER_ONLY", "NO_FIBONACCI"),
        ("BREAKOUT", "RUNNER_ONLY", "SOFT_FIBONACCI_SCORE"),
        ("PULLBACK_CONTINUATION", "RUNNER_ONLY", "NO_FIBONACCI"),
        ("PULLBACK_CONTINUATION", "RUNNER_ONLY", "SOFT_FIBONACCI_SCORE"),
        ("HYBRID", "RUNNER_ONLY", "NO_FIBONACCI"),
        ("HYBRID", "RUNNER_ONLY", "SOFT_FIBONACCI_SCORE"),
        ("BREAKOUT", "PARTIAL_AND_RUNNER", "NO_FIBONACCI"),
        ("BREAKOUT", "PARTIAL_AND_RUNNER", "SOFT_FIBONACCI_SCORE"),
        ("PULLBACK_CONTINUATION", "PARTIAL_AND_RUNNER", "NO_FIBONACCI"),
        ("PULLBACK_CONTINUATION", "PARTIAL_AND_RUNNER", "SOFT_FIBONACCI_SCORE"),
        ("HYBRID", "PARTIAL_AND_RUNNER", "NO_FIBONACCI"),
        ("HYBRID", "PARTIAL_AND_RUNNER", "SOFT_FIBONACCI_SCORE"),
    )
    result: list[dict[str, Any]] = []
    for sequence, (entry_family, exit_model, fibonacci_mode) in enumerate(variants, start=1):
        parameters = {
            "entry_family": entry_family,
            "exit_model": exit_model,
            "fibonacci_mode": fibonacci_mode,
            "score_threshold": 55,
            "execution_rule": "SIGNAL_CLOSE_NEXT_BAR_OPEN",
            "spot_long_only": True,
            "leverage_allowed": False,
            "borrowing_allowed": False,
            "base_transaction_cost": 0.002,
            "stress_transaction_cost": 0.004,
            "minimum_stop_atr": 2.2,
            "typical_stop_atr": 2.8,
            "maximum_stop_atr": 3.8,
            "trailing_atr": 3.5,
        }
        encoded = json.dumps(parameters, sort_keys=True, separators=(",", ":")).encode()
        result.append(
            {
                "configuration_id": f"AMS-V4-A{sequence:02d}",
                "family_id": "AMS-V4-ACTIVE-CONVICTION-SWING",
                "parameters": parameters,
                "parameter_hash_sha256": hashlib.sha256(encoded).hexdigest(),
                "trial_status": "REGISTERED_NOT_EXECUTED",
            }
        )
    return tuple(result)


def _atr(frame: pd.DataFrame, period: int = 14) -> pd.Series:
    previous = frame["close"].shift(1)
    ranges = pd.concat(
        [
            frame["high"] - frame["low"],
            (frame["high"] - previous).abs(),
            (frame["low"] - previous).abs(),
        ],
        axis=1,
    )
    return ranges.max(axis=1).rolling(period, min_periods=period).mean()


def _cluster(symbol: str) -> str:
    majors = {"BTC": "MAJORS", "ETH": "MAJORS", "BNB": "MAJORS", "SOL": "L1"}
    return majors.get(symbol, "ALT")


def build_execution_panel(
    four_hour: pd.DataFrame,
    availability: pd.DataFrame,
) -> pd.DataFrame:
    """Build causal scores and setup features from registered four-hour bars."""

    assert_research_boundary(four_hour)
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
    missing = required.difference(four_hour.columns)
    if missing:
        raise AmsV4Error(f"Missing four-hour columns: {sorted(missing)}")
    frame = four_hour.copy()
    for column in ("bar_open_time", "bar_close_time"):
        frame[column] = pd.to_datetime(frame[column], utc=True, errors="raise")
    frame = frame.sort_values(["symbol", "bar_close_time"], kind="mergesort")
    for column in ("open", "high", "low", "close", "volume"):
        frame[column] = pd.to_numeric(frame[column], errors="raise")

    btc_frame = frame.loc[
        frame["symbol"].eq("BTC"),
        ["bar_close_time", "close"],
    ].copy()
    btc: pd.Series = btc_frame.set_index("bar_close_time")["close"].sort_index()
    btc_return = btc.pct_change(20)
    daily_btc = btc.resample("1D").last().to_frame("btc_close")
    daily_btc["btc_fast"] = daily_btc["btc_close"].ewm(span=50, adjust=False).mean()
    daily_btc["btc_slow"] = daily_btc["btc_close"].ewm(span=200, adjust=False).mean()
    daily_btc["btc_vol"] = daily_btc["btc_close"].pct_change().rolling(20).std()
    daily_btc["btc_vol_slow"] = daily_btc["btc_close"].pct_change().rolling(60).std()
    daily_btc["btc_drawdown"] = daily_btc["btc_close"] / daily_btc["btc_close"].cummax() - 1.0

    daily_close: pd.Series = (
        frame.set_index("bar_close_time").groupby("symbol")["close"].resample("1D").last()
    )
    daily_ema = daily_close.groupby(level=0).transform(
        lambda value: value.ewm(span=50, adjust=False).mean()
    )
    breadth = (daily_close > daily_ema).groupby(level=1).mean().rename("breadth")
    daily_btc = daily_btc.join(breadth, how="left").ffill()
    regime_score = np.select(
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
    daily_btc["d1_score"] = regime_score
    daily_btc["d1_multiplier"] = np.select(
        [regime_score == 15.0, regime_score == 12.0, regime_score == 9.0, regime_score == 5.0],
        [1.15, 1.0, 0.75, 0.45],
        default=0.2,
    )

    outputs: list[pd.DataFrame] = []
    for symbol, group in frame.groupby("symbol", sort=True):
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
            & (item["high"] - item["low"] > item["atr"] * 0.8)
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
        item["trend_score"] = np.where(
            trend, 20.0, np.where(item["close"] > item["ema_slow"], 11.0, 4.0)
        )
        item["rs_score"] = np.clip((item["rs"] * 100.0 + 2.0) * 2.5, 0.0, 10.0)
        item["setup_score"] = np.where(breakout, 25.0, np.where(pullback, 22.0, 0.0))
        item["momentum_score"] = np.clip((item["volume_ratio"] - 0.5) * 10.0, 0.0, 10.0)
        item["structure_score"] = np.where(item["trend_slope"] > 0.0, 10.0, 3.0)
        item["liquidity_score"] = np.clip(item["volume_ratio"] * 5.0, 0.0, 10.0)
        rolling_high = item["high"].rolling(60, min_periods=20).max().shift(1)
        rolling_low = item["low"].rolling(60, min_periods=20).min().shift(1)
        retracement = (rolling_high - item["close"]) / (rolling_high - rolling_low)
        item["fib_score"] = np.select(
            [retrace.between(0.382, 0.618) for retrace in [retracement]], [8.0], default=0.0
        )
        item.loc[
            retracement.between(0.236, 0.382) | retracement.between(0.618, 0.786), "fib_score"
        ] = 4.0
        item.loc[retracement.gt(0.9), "fib_score"] = -5.0
        raw_stop = np.minimum(
            item["swing_low"] - item["atr"] * 0.25, item["close"] - item["atr"] * 2.8
        )
        stop_distance = item["close"] - raw_stop
        item["stop_invalid"] = stop_distance.gt(item["atr"] * 3.8)
        item["initial_stop"] = item["close"] - stop_distance.clip(
            item["atr"] * 2.2, item["atr"] * 3.8
        )
        item["cluster"] = _cluster(str(symbol))
        outputs.append(item.reset_index(drop=True))

    panel = pd.concat(outputs, ignore_index=True)
    panel["date"] = panel["bar_close_time"].dt.floor("D")
    environment = daily_btc.reset_index()
    environment = environment.rename(columns={environment.columns[0]: "date"})
    environment["date"] = pd.to_datetime(environment["date"], utc=True).dt.floor("D")
    panel = panel.merge(environment[["date", "d1_score", "d1_multiplier"]], on="date", how="left")
    panel["d1_score"] = panel["d1_score"].fillna(2.0)
    panel["d1_multiplier"] = panel["d1_multiplier"].fillna(0.2)
    panel["conviction_no_fib"] = (
        panel["d1_score"]
        + panel["trend_score"]
        + panel["rs_score"]
        + panel["setup_score"]
        + panel["momentum_score"]
        + panel["structure_score"]
        + panel["liquidity_score"]
    ).clip(0.0, 100.0)
    panel["conviction_soft_fib"] = (panel["conviction_no_fib"] + panel["fib_score"]).clip(
        0.0, 100.0
    )
    panel = panel.merge(
        availability[["symbol", "tradable_from", "tradable_until"]], on="symbol", how="left"
    )
    panel["tradable_from"] = pd.to_datetime(panel["tradable_from"], utc=True)
    panel["tradable_until"] = pd.to_datetime(panel["tradable_until"], utc=True)
    assert_research_boundary(panel)
    return panel.sort_values(["bar_close_time", "symbol"], kind="mergesort").reset_index(drop=True)


def _risk_multiplier(score: float) -> float:
    if score >= 75.0:
        return 1.25
    if score >= 65.0:
        return 1.0
    return 0.75


def _drawdown_multiplier(drawdown: float) -> float:
    if drawdown >= 0.22:
        return 0.0
    if drawdown >= 0.18:
        return 0.30
    if drawdown >= 0.12:
        return 0.55
    if drawdown >= 0.08:
        return 0.80
    return 1.0


def simulate_portfolio(
    panel: pd.DataFrame, specification: TrialSpecification, *, initial_capital: float = 100_000.0
) -> SimulationResult:
    """Conservative next-open spot simulation with runner/partial exits."""

    assert_research_boundary(panel)
    score_column = (
        "conviction_soft_fib"
        if specification.fibonacci_mode == "SOFT_FIBONACCI_SCORE"
        else "conviction_no_fib"
    )
    ordered = panel.sort_values(["bar_close_time", "symbol"], kind="mergesort").copy()
    cash = initial_capital
    peak = initial_capital
    positions: dict[str, OpenPosition] = {}
    pending: dict[str, dict[str, Any]] = {}
    stopped: dict[str, tuple[int, bool]] = {}
    trades: list[ClosedTrade] = []
    rows: list[dict[str, Any]] = []
    rejected = {
        key: 0
        for key in (
            "score",
            "stop",
            "availability",
            "heat",
            "position_limit",
            "cluster",
            "cash",
            "drawdown",
        )
    }
    candidate_signals = 0
    accepted_entries = 0
    total_fees = 0.0
    turnover = 0.0
    maximum_heat = 0.0
    add_on_count = 0
    reentry_count = 0
    partial_exit_count = 0

    def close(
        symbol: str, position: OpenPosition, price: float, timestamp: pd.Timestamp, reason: str
    ) -> None:
        nonlocal cash, total_fees, turnover
        notional = position.quantity * price
        fee = notional * specification.transaction_cost
        cash += notional - fee
        turnover += notional
        total_fees += fee
        pnl = notional - fee - position.entry_notional - position.entry_fee
        risk = max(position.entry_price - position.initial_stop, 1e-12)
        trades.append(
            ClosedTrade(
                symbol,
                position.entry_time,
                timestamp,
                position.entry_price,
                price,
                position.quantity,
                pnl,
                pnl / (position.entry_notional + position.entry_fee),
                risk,
                position.mae_r,
                position.mfe_r,
                reason,
                int(position.partial_taken),
                position.add_on_used,
                symbol in stopped,
            )
        )
        if reason == "STOP":
            stopped[symbol] = (bar_number, True)
        positions.pop(symbol, None)

    bar_number = 0
    for timestamp, group in ordered.groupby("bar_close_time", sort=True):
        bar_number += 1
        current_time = pd.Timestamp(str(timestamp))
        by_symbol = {str(row["symbol"]): row for row in group.to_dict(orient="records")}
        entry_cash = cash
        equity_before = cash + sum(
            position.quantity * position.entry_price for position in positions.values()
        )
        peak = max(peak, equity_before)
        drawdown = 1.0 - equity_before / peak
        throttle = _drawdown_multiplier(drawdown)
        for symbol in list(positions):
            position = positions[symbol]
            row = by_symbol.get(symbol)
            if row is None:
                continue
            open_price, high, low = float(row["open"]), float(row["high"]), float(row["low"])
            position.bars_held += 1
            r = max(position.entry_price - position.initial_stop, 1e-12)
            position.mfe_r = max(position.mfe_r, (high - position.entry_price) / r)
            position.mae_r = min(position.mae_r, (low - position.entry_price) / r)
            if current_time >= pd.Timestamp(row["tradable_until"]):
                close(symbol, position, open_price, current_time, "VENUE_END")
                continue
            target = position.entry_price + 2.5 * r
            hit_stop = low <= position.stop_price
            hit_target = high >= target and not position.partial_taken
            if open_price <= position.stop_price:
                close(symbol, position, open_price, current_time, "STOP")
                continue
            if hit_stop and hit_target:
                close(symbol, position, position.stop_price, current_time, "STOP")
                continue
            if hit_stop:
                close(symbol, position, position.stop_price, current_time, "STOP")
                continue
            if specification.exit_model == "PARTIAL_AND_RUNNER" and hit_target:
                amount = position.quantity * 0.25
                notional = amount * target
                fee = notional * specification.transaction_cost
                cash += notional - fee
                total_fees += fee
                turnover += notional
                position.quantity -= amount
                position.entry_notional -= position.entry_notional * 0.25
                position.partial_taken = True
                partial_exit_count += 1
            if position.mfe_r >= 2.5 or (
                position.bars_held >= 6 and float(row["trend_slope"]) > 0.0
            ):
                position.stop_price = max(position.stop_price, high - float(row["atr"]) * 3.5)
            if (
                position.bars_held >= 18
                and position.mfe_r < 0.75
                and float(row["trend_slope"]) < 0.0
            ):
                close(symbol, position, float(row["close"]), current_time, "TIME")

        heat = sum(position.risk_fraction for position in positions.values())
        cluster_counts = {
            cluster: sum(position.cluster == cluster for position in positions.values())
            for cluster in {position.cluster for position in positions.values()}
        }
        for symbol, signal in sorted(
            pending.items(),
            key=lambda value: (-float(value[1]["score"]), -float(value[1]["rs"]), value[0]),
        ):
            row = by_symbol.get(symbol)
            if row is None or symbol in positions:
                continue
            if throttle <= 0.0:
                rejected["drawdown"] += 1
                continue
            start = pd.Timestamp(row["bar_open_time"])
            if start < pd.Timestamp(row["tradable_from"]) or start >= pd.Timestamp(
                row["tradable_until"]
            ):
                rejected["availability"] += 1
                continue
            if len(positions) >= specification.portfolio.maximum_positions:
                rejected["position_limit"] += 1
                continue
            cluster = str(row["cluster"])
            if cluster_counts.get(cluster, 0) >= specification.portfolio.maximum_cluster_positions:
                rejected["cluster"] += 1
                continue
            remaining_heat = specification.portfolio.maximum_portfolio_heat - heat
            risk_fraction = min(
                specification.portfolio.maximum_initial_risk,
                specification.portfolio.base_risk_fraction
                * _risk_multiplier(float(signal["score"]))
                * float(signal["d1_multiplier"])
                * throttle,
                remaining_heat,
            )
            if risk_fraction <= 0.0:
                rejected["heat"] += 1
                continue
            entry, stop = float(row["open"]), float(signal["stop"])
            if not (entry > stop > 0.0):
                rejected["stop"] += 1
                continue
            risk_quantity = (equity_before * risk_fraction) / (entry - stop)
            cash_quantity = entry_cash / (entry * (1.0 + specification.transaction_cost))
            quantity = min(risk_quantity, cash_quantity)
            if quantity <= 0.0 or not math.isfinite(quantity):
                rejected["cash"] += 1
                continue
            notional = quantity * entry
            fee = notional * specification.transaction_cost
            if notional + fee > cash + 1e-9 or notional + fee > entry_cash + 1e-9:
                rejected["cash"] += 1
                continue
            prior_stop = stopped.get(symbol)
            if prior_stop is not None and bar_number - prior_stop[0] < 2:
                continue
            cash -= notional + fee
            entry_cash -= notional + fee
            total_fees += fee
            turnover += notional
            positions[symbol] = OpenPosition(
                symbol,
                cluster,
                quantity,
                entry,
                stop,
                stop,
                risk_fraction,
                start,
                notional,
                fee,
                highest_price=entry,
            )
            heat += risk_fraction
            cluster_counts[cluster] = cluster_counts.get(cluster, 0) + 1
            accepted_entries += 1
            if prior_stop is not None:
                reentry_count += 1
        pending = {}

        candidates: list[tuple[float, str, dict[str, Any]]] = []
        for symbol, row in by_symbol.items():
            family = specification.entry_family
            setup = (
                bool(row["breakout_signal"])
                if family == "BREAKOUT"
                else bool(row["pullback_signal"])
            )
            if family == "HYBRID":
                setup = bool(row["breakout_signal"]) or bool(row["pullback_signal"])
            if not setup or symbol in positions:
                continue
            candidate_signals += 1
            score = float(row[score_column])
            if score < specification.score_threshold:
                rejected["score"] += 1
                continue
            if bool(row["stop_invalid"]) or not math.isfinite(float(row["initial_stop"])):
                rejected["stop"] += 1
                continue
            candidates.append(
                (
                    score,
                    symbol,
                    {
                        "score": score,
                        "rs": float(row["rs"]),
                        "stop": float(row["initial_stop"]),
                        "d1_multiplier": float(row["d1_multiplier"]),
                    },
                )
            )
        for _, symbol, signal in sorted(
            candidates, key=lambda value: (-value[0], -value[2]["rs"], value[1])
        ):
            pending[symbol] = signal
        equity = cash + sum(
            position.quantity
            * float(by_symbol.get(symbol, {"close": position.entry_price})["close"])
            for symbol, position in positions.items()
        )
        peak = max(peak, equity)
        maximum_heat = max(
            maximum_heat, sum(position.risk_fraction for position in positions.values())
        )
        rows.append(
            {
                "timestamp": current_time,
                "equity": equity,
                "cash": cash,
                "open_positions": len(positions),
                "portfolio_heat": heat,
            }
        )

    if not rows:
        raise AmsV4Error("No simulation rows.")
    final_time = pd.Timestamp(rows[-1]["timestamp"])
    last_group = ordered.loc[ordered["bar_close_time"].eq(final_time)]
    last_prices = dict(
        zip(last_group["symbol"].astype(str), last_group["close"].astype(float), strict=True)
    )
    for symbol in list(positions):
        close(
            symbol,
            positions[symbol],
            float(last_prices.get(symbol, positions[symbol].entry_price)),
            final_time,
            "END_OF_FOLD",
        )
    curve = pd.DataFrame(rows)
    curve.loc[curve.index[-1], "equity"] = cash
    return SimulationResult(
        initial_capital,
        cash,
        curve,
        tuple(trades),
        rejected,
        candidate_signals,
        accepted_entries,
        total_fees,
        turnover,
        maximum_heat,
        add_on_count,
        reentry_count,
        partial_exit_count,
    )


def metrics(result: SimulationResult) -> dict[str, Any]:
    curve = result.equity_curve.copy()
    returns = curve["equity"].pct_change().dropna()
    drawdown = curve["equity"] / curve["equity"].cummax() - 1.0
    trade_returns = [trade.return_fraction for trade in result.trades]
    pnl = [trade.pnl for trade in result.trades]
    wins = [value for value in pnl if value > 0.0]
    losses = [-value for value in pnl if value < 0.0]
    elapsed = max(
        (
            pd.Timestamp(curve.iloc[-1]["timestamp"]) - pd.Timestamp(curve.iloc[0]["timestamp"])
        ).total_seconds()
        / 86_400.0,
        1.0,
    )
    net_return = result.final_equity / result.initial_capital - 1.0
    cagr = (result.final_equity / result.initial_capital) ** (365.25 / elapsed) - 1.0
    maximum_drawdown = abs(float(drawdown.min()))
    sharpe = (
        float(returns.mean() / returns.std() * math.sqrt(6 * 365.25))
        if len(returns) > 1 and returns.std() > 0
        else None
    )
    downside = returns[returns < 0.0].std()
    sortino = (
        float(returns.mean() / downside * math.sqrt(6 * 365.25))
        if len(returns) > 1 and downside > 0
        else None
    )
    per_symbol: dict[str, float] = {}
    for trade in result.trades:
        per_symbol[trade.symbol] = per_symbol.get(trade.symbol, 0.0) + trade.pnl
    gross_profit, gross_loss = sum(wins), sum(losses)
    return {
        "initial_capital": result.initial_capital,
        "final_equity": result.final_equity,
        "net_return": net_return,
        "cagr": cagr,
        "maximum_drawdown": maximum_drawdown,
        "calmar": cagr / maximum_drawdown if maximum_drawdown else None,
        "sharpe": sharpe,
        "sortino": sortino,
        "profit_factor": gross_profit / gross_loss if gross_loss else None,
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
        "trade_count": len(result.trades),
        "trades_per_year": len(result.trades) * 365.25 / elapsed,
        "win_rate": len(wins) / len(pnl) if pnl else 0.0,
        "average_win": sum(wins) / len(wins) if wins else 0.0,
        "average_loss": sum(losses) / len(losses) if losses else 0.0,
        "payoff_ratio": (sum(wins) / len(wins)) / (sum(losses) / len(losses))
        if wins and losses
        else None,
        "expectancy_per_trade": sum(trade_returns) / len(trade_returns) if trade_returns else 0.0,
        "median_trade_return": float(pd.Series(trade_returns).median()) if trade_returns else 0.0,
        "mae_r": float(pd.Series([trade.mae_r for trade in result.trades]).mean()) if pnl else 0.0,
        "mfe_r": float(pd.Series([trade.mfe_r for trade in result.trades]).mean()) if pnl else 0.0,
        "mfe_capture_ratio": float(
            pd.Series(
                [trade.return_fraction / trade.mfe_r for trade in result.trades if trade.mfe_r > 0]
            ).mean()
        )
        if any(trade.mfe_r > 0 for trade in result.trades)
        else None,
        "average_holding_hours": float(
            pd.Series(
                [
                    (trade.exit_time - trade.entry_time).total_seconds() / 3600
                    for trade in result.trades
                ]
            ).mean()
        )
        if pnl
        else 0.0,
        "exposure": float(curve["open_positions"].gt(0).mean()),
        "turnover": result.turnover / result.initial_capital,
        "total_fees": result.total_fees,
        "maximum_simultaneous_positions": int(curve["open_positions"].max()),
        "average_positions": float(curve["open_positions"].mean()),
        "maximum_portfolio_heat": result.maximum_heat,
        "add_on_count": result.add_on_count,
        "reentry_count": result.reentry_count,
        "partial_exit_count": result.partial_exit_count,
        "stop_exit_count": sum(trade.exit_reason == "STOP" for trade in result.trades),
        "trend_exit_count": sum(trade.exit_reason == "TREND" for trade in result.trades),
        "time_exit_count": sum(trade.exit_reason == "TIME" for trade in result.trades),
        "end_of_fold_exits": sum(trade.exit_reason == "END_OF_FOLD" for trade in result.trades),
        "candidate_signals": result.candidate_signals,
        "accepted_entries": result.accepted_entries,
        "rejected_entries": dict(result.rejected_entries),
        "per_symbol_pnl": per_symbol,
        "monthly_returns": {
            str(index): value
            for index, value in curve.set_index("timestamp")["equity"]
            .resample("ME")
            .last()
            .pct_change()
            .dropna()
            .items()
        },
    }


def specification(
    configuration: Mapping[str, Any], profile: PortfolioProfile, *, cost_mode: str
) -> TrialSpecification:
    params = configuration["parameters"]
    cost = float(
        params["stress_transaction_cost"]
        if cost_mode == "STRESS"
        else params["base_transaction_cost"]
    )
    return TrialSpecification(
        str(configuration["configuration_id"]),
        str(params["entry_family"]),
        str(params["exit_model"]),
        str(params["fibonacci_mode"]),
        int(params["score_threshold"]),
        profile,
        cost,
    )
