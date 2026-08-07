"""RD20-P3 frozen minimal core-edge economic evaluator.

This module consumes the already-frozen RD20 P2A-R1 signal ledger. It does not
regenerate or retune signals. It provides causal next-bar execution, static hard
stops, the frozen EMA24 thesis exit, cash-feasible fixed-risk sizing, a causal
liquidity-capacity overlay, diagnostics, and robustness metrics.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Final

import numpy as np
import pandas as pd

from spotbot.research.rd20_p2_minimal_pullback import (
    BASE_ROUND_TRIP_COST,
    DATA_CUTOFF,
    DATA_START,
    FIXED_RISK_FRACTION,
    FROZEN_CONTRACT,
    MAXIMUM_GROSS_EXPOSURE,
    MAXIMUM_SIMULTANEOUS_POSITIONS,
    MAXIMUM_SINGLE_ASSET_NOTIONAL,
    STRESS_2X_ROUND_TRIP_COST,
    fast_lookup,
    fixed_risk_notional,
    prepare_features,
)

SCHEMA_VERSION: Final = "rd20-p3-core-edge-engine-v1"
CANDIDATE_ID: Final = "RD20_MINIMAL_TREND_PULLBACK_V1"
INITIAL_EQUITY: Final = 100_000.0
LIQUIDITY_CAPACITY_FRACTION_24H: Final = 0.005
FORWARD_HORIZONS: Final = (24, 72, 168)
COST_MULTIPLIERS: Final = (1.0, 2.0)
MAXIMUM_DRAWDOWN_HARD: Final = 0.20
MINIMUM_PROFIT_FACTOR_2X: Final = 1.05
MINIMUM_TRADES_2X: Final = 75
MINIMUM_POSITIVE_YEARS_2X: Final = 3
MINIMUM_BREAK_EVEN_COST_MULTIPLIER: Final = 2.0
CROSS_VENUE_TRADE_CONTRIBUTION_TRIGGER: Final = 0.15


class P3Error(RuntimeError):
    """Raised when the frozen P3 economic contract is violated."""


@dataclass
class Position:
    pair: str
    signal_time: pd.Timestamp
    entry_time: pd.Timestamp
    entry_price: float
    stop_price: float
    quantity: float
    entry_notional: float
    entry_cost: float
    score: float
    membership_rank: int
    scheduled_thesis_exit: bool = False
    last_mark: float = 0.0
    max_survived_high: float = 0.0
    min_survived_low: float = math.inf


def _safe_float(value: object, *, name: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise P3Error(f"{name} must be finite")
    return result


def prepare_economic_frame(raw: pd.DataFrame) -> pd.DataFrame:
    """Prepare the frozen signal features plus causal execution-capacity data."""
    if "volume" not in raw.columns:
        raise P3Error("raw 1h source lacks base volume required for capacity control")
    frame = prepare_features(raw)
    frame["volume"] = pd.to_numeric(frame["volume"], errors="raise").astype(float)
    if bool((frame["volume"] < 0.0).any()):
        raise P3Error("volume contains negative values")
    frame["quote_turnover_proxy"] = frame["volume"] * frame["close"]
    frame["trailing_24h_quote_turnover_proxy"] = (
        frame["quote_turnover_proxy"].rolling(24, min_periods=24).sum()
    )
    return frame


def validate_signal_event_parity(
    events: pd.DataFrame,
    features: dict[str, pd.DataFrame],
) -> dict[str, Any]:
    """Verify every frozen signal row against the canonical feature engine."""
    required = {
        "universe_id",
        "partition_id",
        "timestamp",
        "candidate_rank",
        "pair",
        "membership_rank",
        "trend_strength_percentile",
        "recovery_impulse_percentile",
        "score",
        "past_72h_return",
        "recovery_impulse_atr",
        "decision_close",
        "ema24",
        "initial_stop_reference",
    }
    missing = sorted(required.difference(events.columns))
    if missing:
        raise P3Error(f"signal-events columns missing: {missing}")
    frame = events.copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, errors="raise")
    if bool((frame["timestamp"] >= DATA_CUTOFF).any()):
        raise P3Error("2024 or later signal entered P3")
    lookups = {pair: fast_lookup(value) for pair, value in features.items()}
    checked = 0
    for raw in frame.to_dict(orient="records"):
        pair = str(raw["pair"])
        feature = features.get(pair)
        if feature is None:
            raise P3Error(f"signal pair missing feature frame: {pair}")
        index = lookups[pair].get(int(pd.Timestamp(raw["timestamp"]).value))
        if index is None:
            raise P3Error(f"signal timestamp missing from source: {pair} {raw['timestamp']}")
        row = feature.iloc[index]
        comparisons = {
            "past_72h_return": float(row["past_72h_return"]),
            "recovery_impulse_atr": float(row["recovery_impulse_atr"]),
            "decision_close": float(row["close"]),
            "ema24": float(row["ema24"]),
            "initial_stop_reference": float(row["initial_stop_reference"]),
        }
        for column, observed in comparisons.items():
            expected = float(raw[column])
            if not math.isclose(observed, expected, rel_tol=1e-10, abs_tol=1e-12):
                raise P3Error(
                    f"signal parity mismatch {pair} {raw['timestamp']} {column}: "
                    f"{observed} != {expected}"
                )
        checked += 1
    return {
        "signal_rows_checked": checked,
        "signal_rows_total": len(frame),
        "full_signal_event_feature_parity": checked == len(frame),
    }


def _net_return_for_cost(
    entry_price: float,
    exit_price: float,
    round_trip_cost_fraction: float,
) -> float:
    side = round_trip_cost_fraction / 2.0
    ratio = exit_price / entry_price
    return ratio - 1.0 - side * (1.0 + ratio)


def forward_horizon_rows(
    events: pd.DataFrame,
    features: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    """Compute preregistered 24h/72h/168h forward diagnostics after signal freeze."""
    lookups = {pair: fast_lookup(frame) for pair, frame in features.items()}
    rows: list[dict[str, Any]] = []
    for raw in events.to_dict(orient="records"):
        signal_time = pd.Timestamp(raw["timestamp"])
        pair = str(raw["pair"])
        frame = features[pair]
        lookup = lookups[pair]
        entry_time = signal_time + pd.Timedelta(hours=1)
        entry_index = lookup.get(int(entry_time.value))
        if entry_index is None:
            continue
        entry_price = float(frame.iloc[entry_index]["open"])
        if not math.isfinite(entry_price) or entry_price <= 0.0:
            continue
        for horizon in FORWARD_HORIZONS:
            exit_time = signal_time + pd.Timedelta(hours=horizon)
            exit_index = lookup.get(int(exit_time.value))
            if exit_index is None:
                continue
            exit_price = float(frame.iloc[exit_index]["close"])
            if not math.isfinite(exit_price) or exit_price <= 0.0:
                continue
            gross = exit_price / entry_price - 1.0
            for multiplier in COST_MULTIPLIERS:
                round_trip = BASE_ROUND_TRIP_COST * multiplier
                rows.append(
                    {
                        "universe_id": str(raw["universe_id"]),
                        "partition_id": str(raw["partition_id"]),
                        "pair": pair,
                        "signal_time": signal_time,
                        "entry_time": entry_time,
                        "horizon_hours": horizon,
                        "cost_multiplier": multiplier,
                        "score": float(raw["score"]),
                        "gross_forward_return": gross,
                        "net_forward_return": _net_return_for_cost(
                            entry_price,
                            exit_price,
                            round_trip,
                        ),
                    }
                )
    return pd.DataFrame.from_records(rows)


def aggregate_forward_horizons(rows: pd.DataFrame) -> pd.DataFrame:
    output: list[dict[str, Any]] = []
    grouped = rows.groupby(
        ["universe_id", "partition_id", "horizon_hours", "cost_multiplier"],
        sort=True,
    )
    for keys, group in grouped:
        universe_id, partition_id, horizon, cost_multiplier = keys
        returns = pd.to_numeric(group["net_forward_return"], errors="raise").astype(float)
        scores = pd.to_numeric(group["score"], errors="raise").astype(float)
        score_rank = scores.rank(method="average", pct=True)
        return_rank = returns.rank(method="average", pct=True)
        rank_ic = float(score_rank.corr(return_rank)) if len(group) > 1 else math.nan
        quintile = pd.qcut(
            scores.rank(method="first"),
            q=min(5, len(group)),
            labels=False,
            duplicates="drop",
        )
        top_mask = quintile == quintile.max()
        bottom_mask = quintile == quintile.min()
        top_mean = float(returns.loc[top_mask].mean())
        bottom_mean = float(returns.loc[bottom_mask].mean())
        output.append(
            {
                "universe_id": str(universe_id),
                "partition_id": str(partition_id),
                "horizon_hours": int(horizon),
                "cost_multiplier": float(cost_multiplier),
                "event_count": len(group),
                "mean_net_forward_return": float(returns.mean()),
                "median_net_forward_return": float(returns.median()),
                "positive_net_forward_share": float((returns > 0.0).mean()),
                "score_rank_ic": rank_ic,
                "top_score_quintile_mean_net_return": top_mean,
                "bottom_score_quintile_mean_net_return": bottom_mean,
                "top_minus_bottom_net_spread": top_mean - bottom_mean,
            }
        )
    return pd.DataFrame.from_records(output)


def _bar_at(
    pair: str,
    timestamp: pd.Timestamp,
    features: dict[str, pd.DataFrame],
    lookups: dict[str, dict[int, int]],
) -> pd.Series | None:
    frame = features.get(pair)
    index = lookups.get(pair, {}).get(int(timestamp.value))
    if frame is None or index is None:
        return None
    return frame.iloc[index]


def _record_trade(
    *,
    run_id: str,
    universe_id: str,
    cost_multiplier: float,
    position: Position,
    exit_time: pd.Timestamp,
    exit_price: float,
    exit_reason: str,
    side_cost_rate: float,
) -> dict[str, Any]:
    exit_notional = position.quantity * exit_price
    exit_cost = exit_notional * side_cost_rate
    gross_pnl = exit_notional - position.entry_notional
    net_pnl = gross_pnl - position.entry_cost - exit_cost
    gross_return = exit_price / position.entry_price - 1.0
    net_return = net_pnl / position.entry_notional
    mfe = position.max_survived_high / position.entry_price - 1.0
    mae = position.min_survived_low / position.entry_price - 1.0
    capture = gross_return / mfe if mfe > 0.0 else math.nan
    base_cost_dollars_per_multiplier = (
        BASE_ROUND_TRIP_COST / 2.0 * (position.entry_notional + exit_notional)
    )
    return {
        "run_id": run_id,
        "universe_id": universe_id,
        "cost_multiplier": cost_multiplier,
        "pair": position.pair,
        "signal_time": position.signal_time,
        "entry_time": position.entry_time,
        "entry_price": position.entry_price,
        "initial_stop": position.stop_price,
        "quantity": position.quantity,
        "entry_notional": position.entry_notional,
        "entry_cost": position.entry_cost,
        "exit_time": exit_time,
        "exit_price": exit_price,
        "exit_reason": exit_reason,
        "exit_notional": exit_notional,
        "exit_cost": exit_cost,
        "gross_pnl": gross_pnl,
        "net_pnl": net_pnl,
        "gross_return": gross_return,
        "net_return_on_entry_notional": net_return,
        "holding_hours": (exit_time - position.entry_time).total_seconds() / 3600.0,
        "mfe_return": mfe,
        "mae_return": mae,
        "exit_capture_ratio": capture,
        "base_cost_dollars_per_multiplier": base_cost_dollars_per_multiplier,
        "score": position.score,
        "membership_rank": position.membership_rank,
    }


def replay_universe(
    *,
    universe_id: str,
    cost_multiplier: float,
    events: pd.DataFrame,
    features: dict[str, pd.DataFrame],
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Run the frozen minimal portfolio continuously through 2019-2023."""
    round_trip = BASE_ROUND_TRIP_COST * cost_multiplier
    if cost_multiplier == 2.0 and not math.isclose(
        round_trip,
        STRESS_2X_ROUND_TRIP_COST,
    ):
        raise P3Error("2x cost model drifted")
    side_cost = round_trip / 2.0
    run_id = f"{universe_id}_{cost_multiplier:.0f}x"

    selected = events.loc[events["universe_id"].astype(str) == universe_id].copy()
    selected["timestamp"] = pd.to_datetime(selected["timestamp"], utc=True, errors="raise")
    selected["entry_time"] = selected["timestamp"] + pd.Timedelta(hours=1)
    selected = selected.sort_values(
        ["entry_time", "candidate_rank", "pair"],
        kind="stable",
    )
    entries_by_time = {
        pd.Timestamp(timestamp): group.copy()
        for timestamp, group in selected.groupby("entry_time", sort=True)
    }
    if selected.empty:
        raise P3Error(f"no frozen signals for universe {universe_id}")

    lookups = {pair: fast_lookup(frame) for pair, frame in features.items()}
    start = max(DATA_START, selected["entry_time"].min().floor("h"))
    final_hour = DATA_CUTOFF - pd.Timedelta(hours=1)

    cash = INITIAL_EQUITY
    positions: dict[str, Position] = {}
    trades: list[dict[str, Any]] = []
    equity_rows: list[dict[str, Any]] = []
    route = {
        "signal_candidates": 0,
        "admitted_entries": 0,
        "already_open_rejections": 0,
        "position_slot_rejections": 0,
        "missing_entry_bar_rejections": 0,
        "invalid_stop_at_entry_rejections": 0,
        "liquidity_capacity_unavailable_rejections": 0,
        "liquidity_capacity_limited_entries": 0,
        "gross_capacity_limited_entries": 0,
        "cash_capacity_limited_entries": 0,
        "hard_stop_exits": 0,
        "stop_gap_exits": 0,
        "thesis_exits": 0,
        "boundary_exits": 0,
    }
    min_cash = cash
    max_admission_gross_fraction = 0.0
    peak_equity = cash
    max_drawdown = 0.0

    for timestamp in pd.date_range(start, final_hour, freq="h"):
        # Mark currently open positions at the current open and honor any
        # previously scheduled thesis exit before considering new entries.
        for position in positions.values():
            bar = _bar_at(position.pair, timestamp, features, lookups)
            if bar is not None:
                position.last_mark = float(bar["open"])

        for pair in list(positions):
            position = positions[pair]
            if not position.scheduled_thesis_exit:
                continue
            bar = _bar_at(pair, timestamp, features, lookups)
            if bar is None:
                continue
            exit_price = float(bar["open"])
            record = _record_trade(
                run_id=run_id,
                universe_id=universe_id,
                cost_multiplier=cost_multiplier,
                position=position,
                exit_time=timestamp,
                exit_price=exit_price,
                exit_reason="THESIS_INVALIDATION_NEXT_BAR_OPEN",
                side_cost_rate=side_cost,
            )
            cash += record["exit_notional"] - record["exit_cost"]
            trades.append(record)
            del positions[pair]
            route["thesis_exits"] += 1

        candidates = entries_by_time.get(timestamp)
        if candidates is not None:
            for raw in candidates.to_dict(orient="records"):
                route["signal_candidates"] += 1
                pair = str(raw["pair"])
                if pair in positions:
                    route["already_open_rejections"] += 1
                    continue
                if len(positions) >= MAXIMUM_SIMULTANEOUS_POSITIONS:
                    route["position_slot_rejections"] += 1
                    continue
                bar = _bar_at(pair, timestamp, features, lookups)
                if bar is None:
                    route["missing_entry_bar_rejections"] += 1
                    continue
                entry_price = float(bar["open"])
                stop_price = float(raw["initial_stop_reference"])
                if (
                    not math.isfinite(entry_price)
                    or entry_price <= 0.0
                    or not math.isfinite(stop_price)
                    or stop_price <= 0.0
                    or stop_price >= entry_price
                ):
                    route["invalid_stop_at_entry_rejections"] += 1
                    continue

                signal_bar = _bar_at(
                    pair,
                    pd.Timestamp(raw["timestamp"]),
                    features,
                    lookups,
                )
                if signal_bar is None:
                    raise P3Error("frozen signal bar vanished during routing")
                trailing_quote = float(signal_bar["trailing_24h_quote_turnover_proxy"])
                if not math.isfinite(trailing_quote) or trailing_quote <= 0.0:
                    route["liquidity_capacity_unavailable_rejections"] += 1
                    continue
                liquidity_capacity = trailing_quote * LIQUIDITY_CAPACITY_FRACTION_24H

                equity_open = cash + sum(
                    position.quantity * position.last_mark for position in positions.values()
                )
                if equity_open <= 0.0:
                    raise P3Error("portfolio equity became non-positive")
                requested = fixed_risk_notional(
                    equity=equity_open,
                    entry_price=entry_price,
                    stop_price=stop_price,
                )
                existing_gross = sum(
                    position.quantity * position.last_mark for position in positions.values()
                )
                gross_capacity = max(
                    0.0,
                    equity_open * MAXIMUM_GROSS_EXPOSURE - existing_gross,
                )
                cash_capacity = max(0.0, cash / (1.0 + side_cost))
                notional = min(
                    requested,
                    liquidity_capacity,
                    gross_capacity,
                    cash_capacity,
                    equity_open * MAXIMUM_SINGLE_ASSET_NOTIONAL,
                )
                if notional <= 0.0:
                    if gross_capacity <= 0.0:
                        route["gross_capacity_limited_entries"] += 1
                    else:
                        route["cash_capacity_limited_entries"] += 1
                    continue
                if notional < requested - 1e-9:
                    if math.isclose(notional, liquidity_capacity, rel_tol=1e-9, abs_tol=1e-9):
                        route["liquidity_capacity_limited_entries"] += 1
                    if math.isclose(notional, gross_capacity, rel_tol=1e-9, abs_tol=1e-9):
                        route["gross_capacity_limited_entries"] += 1
                    if math.isclose(notional, cash_capacity, rel_tol=1e-9, abs_tol=1e-9):
                        route["cash_capacity_limited_entries"] += 1

                entry_cost = notional * side_cost
                quantity = notional / entry_price
                cash -= notional + entry_cost
                if cash < -1e-7:
                    raise P3Error(f"negative cash after entry: {cash}")
                cash = max(cash, 0.0)
                min_cash = min(min_cash, cash)
                position = Position(
                    pair=pair,
                    signal_time=pd.Timestamp(raw["timestamp"]),
                    entry_time=timestamp,
                    entry_price=entry_price,
                    stop_price=stop_price,
                    quantity=quantity,
                    entry_notional=notional,
                    entry_cost=entry_cost,
                    score=float(raw["score"]),
                    membership_rank=int(raw["membership_rank"]),
                    last_mark=entry_price,
                    max_survived_high=entry_price,
                    min_survived_low=entry_price,
                )
                positions[pair] = position
                route["admitted_entries"] += 1

                gross_after = existing_gross + notional
                gross_fraction = gross_after / equity_open if equity_open > 0.0 else math.inf
                if gross_fraction > MAXIMUM_GROSS_EXPOSURE + 1e-9:
                    raise P3Error("admission gross exposure exceeded frozen cap")
                max_admission_gross_fraction = max(
                    max_admission_gross_fraction,
                    gross_fraction,
                )

        # Static hard stops are checked before any close-based thesis update.
        for pair in list(positions):
            position = positions[pair]
            bar = _bar_at(pair, timestamp, features, lookups)
            if bar is None:
                continue
            bar_open = float(bar["open"])
            bar_low = float(bar["low"])
            if bar_open <= position.stop_price:
                exit_price = bar_open
                reason = "HARD_STOP_GAP_AT_OPEN"
            elif bar_low <= position.stop_price:
                exit_price = position.stop_price
                reason = "HARD_STOP_STATIC"
            else:
                position.max_survived_high = max(
                    position.max_survived_high,
                    float(bar["high"]),
                )
                position.min_survived_low = min(
                    position.min_survived_low,
                    float(bar["low"]),
                )
                position.last_mark = float(bar["close"])
                if float(bar["close"]) < float(bar["ema24"]):
                    position.scheduled_thesis_exit = True
                continue

            position.min_survived_low = min(
                position.min_survived_low,
                exit_price,
            )
            record = _record_trade(
                run_id=run_id,
                universe_id=universe_id,
                cost_multiplier=cost_multiplier,
                position=position,
                exit_time=timestamp,
                exit_price=exit_price,
                exit_reason=reason,
                side_cost_rate=side_cost,
            )
            cash += record["exit_notional"] - record["exit_cost"]
            trades.append(record)
            del positions[pair]
            if reason == "HARD_STOP_GAP_AT_OPEN":
                route["stop_gap_exits"] += 1
            else:
                route["hard_stop_exits"] += 1

        # Research-window liquidation is an accounting boundary, not strategy logic.
        if timestamp == final_hour and positions:
            for pair in list(positions):
                position = positions[pair]
                bar = _bar_at(pair, timestamp, features, lookups)
                exit_price = float(bar["close"]) if bar is not None else float(position.last_mark)
                record = _record_trade(
                    run_id=run_id,
                    universe_id=universe_id,
                    cost_multiplier=cost_multiplier,
                    position=position,
                    exit_time=timestamp,
                    exit_price=exit_price,
                    exit_reason="RESEARCH_BOUNDARY_LIQUIDATION",
                    side_cost_rate=side_cost,
                )
                cash += record["exit_notional"] - record["exit_cost"]
                trades.append(record)
                del positions[pair]
                route["boundary_exits"] += 1

        equity = cash + sum(
            position.quantity * position.last_mark for position in positions.values()
        )
        if equity <= 0.0:
            raise P3Error("portfolio equity became non-positive")
        peak_equity = max(peak_equity, equity)
        drawdown = equity / peak_equity - 1.0
        max_drawdown = min(max_drawdown, drawdown)
        gross_market = sum(
            position.quantity * position.last_mark for position in positions.values()
        )
        equity_rows.append(
            {
                "run_id": run_id,
                "universe_id": universe_id,
                "cost_multiplier": cost_multiplier,
                "timestamp": timestamp,
                "equity": equity,
                "cash": cash,
                "gross_market_value": gross_market,
                "position_count": len(positions),
                "drawdown": drawdown,
                "active": bool(positions),
            }
        )

    trade_frame = pd.DataFrame.from_records(trades)
    equity_frame = pd.DataFrame.from_records(equity_rows)
    if not len(trade_frame):
        raise P3Error(f"economic replay produced zero trades: {run_id}")
    final_equity = float(equity_frame.iloc[-1]["equity"])
    route.update(
        {
            "run_id": run_id,
            "universe_id": universe_id,
            "cost_multiplier": cost_multiplier,
            "min_cash": min_cash,
            "final_cash": cash,
            "final_equity": final_equity,
            "maximum_drawdown": abs(max_drawdown),
            "max_admission_gross_fraction": max_admission_gross_fraction,
            "negative_cash_observed": min_cash < -1e-7,
        }
    )
    return trade_frame, equity_frame, route


def profit_factor(net_pnl: pd.Series) -> float:
    values = pd.to_numeric(net_pnl, errors="raise").astype(float)
    gains = float(values.loc[values > 0.0].sum())
    losses = float(-values.loc[values < 0.0].sum())
    if losses == 0.0:
        return math.inf if gains > 0.0 else 0.0
    return gains / losses


def fixed_path_pf1_break_even_multiplier(trades: pd.DataFrame) -> float:
    """PF=1 cost multiplier on the frozen BASE-routed trade path."""
    gross = pd.to_numeric(trades["gross_pnl"], errors="raise").astype(float).to_numpy()
    base_cost = (
        pd.to_numeric(
            trades["base_cost_dollars_per_multiplier"],
            errors="raise",
        )
        .astype(float)
        .to_numpy()
    )

    def pf(multiplier: float) -> float:
        pnl = pd.Series(gross - multiplier * base_cost)
        return profit_factor(pnl)

    if pf(0.0) <= 1.0:
        return 0.0
    upper = 1.0
    while upper < 1024.0 and pf(upper) > 1.0:
        upper *= 2.0
    if upper >= 1024.0 and pf(upper) > 1.0:
        return math.inf
    lower = 0.0
    for _ in range(80):
        middle = (lower + upper) / 2.0
        if pf(middle) > 1.0:
            lower = middle
        else:
            upper = middle
    return (lower + upper) / 2.0


def _year_returns(daily: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    previous = INITIAL_EQUITY
    for year, group in daily.groupby(daily["timestamp"].dt.year, sort=True):
        end_equity = float(group.iloc[-1]["equity"])
        rows.append(
            {
                "year": int(year),
                "start_equity": previous,
                "end_equity": end_equity,
                "return": end_equity / previous - 1.0,
            }
        )
        previous = end_equity
    return pd.DataFrame.from_records(rows)


def _daily_metrics(equity: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    frame = equity.copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, errors="raise")
    frame["date"] = frame["timestamp"].dt.floor("D")
    daily = (
        frame.groupby("date", as_index=False)
        .agg(
            equity=("equity", "last"),
            active=("active", "max"),
        )
        .rename(columns={"date": "timestamp"})
    )
    daily["daily_return"] = daily["equity"].pct_change()
    if len(daily):
        daily.loc[daily.index[0], "daily_return"] = (
            float(daily.iloc[0]["equity"]) / INITIAL_EQUITY - 1.0
        )
    returns = daily["daily_return"].astype(float)
    q05 = float(returns.quantile(0.05)) if len(returns) else math.nan
    cvar = float(returns.loc[returns <= q05].mean()) if len(returns) else math.nan
    rolling: dict[str, Any] = {}
    for window in (30, 60, 90):
        values = daily["equity"] / daily["equity"].shift(window) - 1.0
        finite = values.dropna()
        rolling[f"rolling_{window}d_median_return"] = (
            float(finite.median()) if len(finite) else math.nan
        )
        rolling[f"rolling_{window}d_worst_return"] = (
            float(finite.min()) if len(finite) else math.nan
        )
        rolling[f"rolling_{window}d_best_return"] = float(finite.max()) if len(finite) else math.nan
    metrics = {
        "positive_calendar_day_share": float((returns > 0.0).mean()),
        "median_daily_return": float(returns.median()),
        "worst_daily_return": float(returns.min()),
        "daily_cvar_5pct": cvar,
        "active_day_share": float(daily["active"].astype(bool).mean()),
        **rolling,
    }
    return daily, metrics


def contribution_diagnostics(
    trades: pd.DataFrame,
) -> tuple[dict[str, Any], pd.DataFrame, pd.DataFrame]:
    pnl = pd.to_numeric(trades["net_pnl"], errors="raise").astype(float)
    total = float(pnl.sum())
    positive_total = float(pnl.loc[pnl > 0.0].sum())
    largest_winner = float(pnl.max())
    largest_winner_share = largest_winner / positive_total if positive_total > 0.0 else math.nan

    work = trades.copy()
    work["entry_time"] = pd.to_datetime(work["entry_time"], utc=True, errors="raise")
    work["entry_month"] = work["entry_time"].dt.strftime("%Y-%m")
    work["entry_year"] = work["entry_time"].dt.year.astype(int)

    def concentration(column: str) -> tuple[float, str]:
        grouped = work.groupby(column)["net_pnl"].sum().sort_values(ascending=False)
        if grouped.empty:
            return math.nan, ""
        positive = grouped.clip(lower=0.0)
        share = (
            float(positive.iloc[0] / positive.sum()) if float(positive.sum()) > 0.0 else math.nan
        )
        return share, str(grouped.index[0])

    asset_share, top_asset = concentration("pair")
    month_share, top_month = concentration("entry_month")
    year_share, top_year = concentration("entry_year")

    loao_rows = []
    for asset, group in work.groupby("pair", sort=True):
        removed = float(group["net_pnl"].sum())
        loao_rows.append(
            {
                "removed_asset": str(asset),
                "removed_net_pnl": removed,
                "remaining_net_pnl": total - removed,
            }
        )
    loyo_rows = []
    for year, group in work.groupby("entry_year", sort=True):
        removed = float(group["net_pnl"].sum())
        loyo_rows.append(
            {
                "removed_year": int(year),
                "removed_net_pnl": removed,
                "remaining_net_pnl": total - removed,
            }
        )
    loao = pd.DataFrame.from_records(loao_rows)
    loyo = pd.DataFrame.from_records(loyo_rows)
    diagnostics = {
        "total_net_pnl": total,
        "positive_net_pnl_pool": positive_total,
        "largest_winner_net_pnl": largest_winner,
        "largest_winner_positive_pnl_share": largest_winner_share,
        "net_pnl_without_largest_winner": total - largest_winner,
        "top_asset": top_asset,
        "top_asset_positive_contribution_share": asset_share,
        "top_month": top_month,
        "top_month_positive_contribution_share": month_share,
        "top_year": top_year,
        "top_year_positive_contribution_share": year_share,
        "minimum_loao_remaining_net_pnl": (
            float(loao["remaining_net_pnl"].min()) if len(loao) else total
        ),
        "minimum_loyo_remaining_net_pnl": (
            float(loyo["remaining_net_pnl"].min()) if len(loyo) else total
        ),
        "cross_venue_trade_review_triggered": (
            math.isfinite(largest_winner_share)
            and largest_winner_share > CROSS_VENUE_TRADE_CONTRIBUTION_TRIGGER
        ),
    }
    return diagnostics, loao, loyo


def performance_metrics(
    trades: pd.DataFrame,
    equity: pd.DataFrame,
    route: dict[str, Any],
) -> tuple[dict[str, Any], pd.DataFrame]:
    net = pd.to_numeric(trades["net_pnl"], errors="raise").astype(float)
    final_equity = float(equity.iloc[-1]["equity"])
    daily, daily_metrics = _daily_metrics(equity)
    years = _year_returns(daily)
    contribution, _, _ = contribution_diagnostics(trades)
    metrics = {
        "run_id": str(route["run_id"]),
        "universe_id": str(route["universe_id"]),
        "cost_multiplier": float(route["cost_multiplier"]),
        "initial_equity": INITIAL_EQUITY,
        "final_equity": final_equity,
        "net_return": final_equity / INITIAL_EQUITY - 1.0,
        "trade_count": len(trades),
        "winning_trade_count": int((net > 0.0).sum()),
        "losing_trade_count": int((net < 0.0).sum()),
        "profit_factor": profit_factor(net),
        "maximum_drawdown": float(route["maximum_drawdown"]),
        "min_cash": float(route["min_cash"]),
        "negative_cash_observed": bool(route["negative_cash_observed"]),
        "one_way_turnover_initial_equity": float(
            pd.to_numeric(trades["entry_notional"], errors="raise").sum() / INITIAL_EQUITY
        ),
        "positive_year_count": int((years["return"] > 0.0).sum()),
        "year_count": len(years),
        "largest_winner_positive_pnl_share": contribution["largest_winner_positive_pnl_share"],
        "net_pnl_without_largest_winner": contribution["net_pnl_without_largest_winner"],
        "minimum_loao_remaining_net_pnl": contribution["minimum_loao_remaining_net_pnl"],
        "minimum_loyo_remaining_net_pnl": contribution["minimum_loyo_remaining_net_pnl"],
        "top_asset_positive_contribution_share": contribution[
            "top_asset_positive_contribution_share"
        ],
        "top_month_positive_contribution_share": contribution[
            "top_month_positive_contribution_share"
        ],
        "top_year_positive_contribution_share": contribution[
            "top_year_positive_contribution_share"
        ],
        "cross_venue_trade_review_triggered": contribution["cross_venue_trade_review_triggered"],
        "mean_mfe_return": float(pd.to_numeric(trades["mfe_return"]).mean()),
        "mean_mae_return": float(pd.to_numeric(trades["mae_return"]).mean()),
        "median_exit_capture_ratio": float(
            pd.to_numeric(trades["exit_capture_ratio"], errors="coerce")
            .replace([np.inf, -np.inf], np.nan)
            .median()
        ),
        **daily_metrics,
    }
    return metrics, years


def hard_gate_evaluation(
    metrics: pd.DataFrame,
    break_even: pd.DataFrame,
    concentration: pd.DataFrame,
) -> tuple[pd.DataFrame, bool]:
    rows: list[dict[str, Any]] = []
    for universe in ("C2", "D2", "E2"):
        base = metrics.loc[
            (metrics["universe_id"] == universe) & (metrics["cost_multiplier"] == 1.0)
        ].iloc[0]
        stress = metrics.loc[
            (metrics["universe_id"] == universe) & (metrics["cost_multiplier"] == 2.0)
        ].iloc[0]
        be = float(
            break_even.loc[
                break_even["universe_id"] == universe,
                "pf1_break_even_cost_multiplier_fixed_base_path",
            ].iloc[0]
        )
        conc = concentration.loc[
            (concentration["universe_id"] == universe) & (concentration["cost_multiplier"] == 2.0)
        ].iloc[0]
        checks = {
            "BASE_NET_RETURN_POSITIVE": float(base["net_return"]) > 0.0,
            "STRESS_2X_NET_RETURN_POSITIVE": float(stress["net_return"]) > 0.0,
            "STRESS_2X_PF_AT_LEAST_1_05": float(stress["profit_factor"])
            >= MINIMUM_PROFIT_FACTOR_2X,
            "STRESS_2X_DRAWDOWN_AT_MOST_20PCT": float(stress["maximum_drawdown"])
            <= MAXIMUM_DRAWDOWN_HARD,
            "STRESS_2X_TRADES_AT_LEAST_75": int(stress["trade_count"]) >= MINIMUM_TRADES_2X,
            "STRESS_2X_POSITIVE_YEARS_AT_LEAST_3": int(stress["positive_year_count"])
            >= MINIMUM_POSITIVE_YEARS_2X,
            "CASH_FEASIBLE_BASE_AND_2X": (
                not bool(base["negative_cash_observed"])
                and not bool(stress["negative_cash_observed"])
            ),
            "PF1_BREAK_EVEN_COST_MULTIPLIER_AT_LEAST_2X": (
                math.isinf(be) or be >= MINIMUM_BREAK_EVEN_COST_MULTIPLIER
            ),
            "LARGEST_WINNER_REMOVAL_REMAINS_POSITIVE_2X": float(
                conc["net_pnl_without_largest_winner"]
            )
            > 0.0,
            "LEAVE_ONE_ASSET_OUT_REMAINS_POSITIVE_2X": float(conc["minimum_loao_remaining_net_pnl"])
            > 0.0,
            "LEAVE_ONE_YEAR_OUT_REMAINS_POSITIVE_2X": float(conc["minimum_loyo_remaining_net_pnl"])
            > 0.0,
        }
        for gate_id, passed in checks.items():
            rows.append(
                {
                    "universe_id": universe,
                    "gate_id": gate_id,
                    "passed": bool(passed),
                }
            )
    frame = pd.DataFrame.from_records(rows)
    return frame, bool(frame["passed"].all())


def validate_protocol_constants() -> None:
    if FROZEN_CONTRACT["candidate_id"] != CANDIDATE_ID:
        raise P3Error("candidate id drift")
    if not math.isclose(BASE_ROUND_TRIP_COST, 0.0025):
        raise P3Error("base round-trip cost drift")
    if not math.isclose(STRESS_2X_ROUND_TRIP_COST, 0.005):
        raise P3Error("2x round-trip cost drift")
    if not math.isclose(FIXED_RISK_FRACTION, 0.005):
        raise P3Error("fixed risk fraction drift")
    if MAXIMUM_SIMULTANEOUS_POSITIONS != 5:
        raise P3Error("position count drift")
    if not math.isclose(MAXIMUM_GROSS_EXPOSURE, 0.90):
        raise P3Error("gross exposure drift")
    if FROZEN_CONTRACT["take_profit"] is not None:
        raise P3Error("take-profit entered frozen candidate")
    if FROZEN_CONTRACT["adaptive_trailing"] is not False:
        raise P3Error("adaptive trailing entered frozen candidate")
    if FROZEN_CONTRACT["capital_replacement"] is not False:
        raise P3Error("capital replacement entered frozen candidate")
