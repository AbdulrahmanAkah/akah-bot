"""Disabled-by-default research shadow for the frozen causal same-pair policy.

With ``shadow_enabled=False`` this module delegates directly to the frozen
RD27 STATIC_EXIT_STATE_ROUTER path.  The enabled path bypasses only same-pair
uniqueness and allows at most one independent secondary lot globally.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Any, Final

import numpy as np
import pandas as pd

from spotbot.research import rd27_lifecycle_replay as rd27
from spotbot.research.rd26_exit_architecture import (
    BASE_ROUND_TRIP_COST,
    COST_MULTIPLIERS,
    INITIAL_EQUITY,
    LIQUIDITY_CAPACITY_FRACTION_24H,
    MAXIMUM_GROSS_EXPOSURE,
    MAXIMUM_POSITIONS,
    fast_lookup,
    performance_metrics,
)
from spotbot.research.rd27_adaptive_lifecycle import (
    MARKET_STATES,
    RISK_OFF,
    LifecyclePosition,
    capital_admission_decision,
    new_lifecycle_position,
)

IMPLEMENTATION_PROTOCOL_ID: Final = (
    "SHADOW_DISABLED_BY_DEFAULT_CAUSAL_SAME_PAIR_SECONDARY_IMPLEMENTATION_V1"
)
POLICY_PROTOCOL_ID: Final = "CAUSAL_FIRST_ELIGIBLE_SINGLE_ACTIVE_SAME_PAIR_SECONDARY_V1"
DEFAULT_SHADOW_ENABLED: Final = False


class SamePairSecondaryShadowError(RuntimeError):
    """Raised when the bounded research shadow violates its frozen contract."""


@dataclass
class ShadowPosition:
    position_id: str
    pair: str
    signal_time: pd.Timestamp
    entry_time: pd.Timestamp
    max_exit_time: pd.Timestamp
    entry_price: float
    quantity: float
    entry_notional: float
    entry_cost: float
    membership_rank: int
    support_families: tuple[str, ...]
    period_id: str
    atr24_at_signal: float
    lifecycle: LifecyclePosition
    entry_market_state: str
    last_mark: float
    is_secondary: bool


@dataclass
class ShadowReplayResult:
    trades: pd.DataFrame
    daily: pd.DataFrame
    metrics: dict[str, Any]
    counters: dict[str, int]
    diagnostics: dict[str, Any]


def validate_shadow_constants() -> None:
    rd27.validate_policy_constants()
    if MAXIMUM_POSITIONS != 5:
        raise SamePairSecondaryShadowError("maximum-position contract drifted")
    if not math.isclose(MAXIMUM_GROSS_EXPOSURE, 0.9):
        raise SamePairSecondaryShadowError("gross-exposure contract drifted")
    if DEFAULT_SHADOW_ENABLED:
        raise SamePairSecondaryShadowError("shadow must remain disabled by default")


def _utc(value: Any) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    return timestamp.tz_localize("UTC") if timestamp.tzinfo is None else timestamp.tz_convert("UTC")


def _event_key(period_id: str, signal_time: pd.Timestamp, pair: str) -> str:
    return f"{period_id}|{_utc(signal_time).isoformat()}|{pair}"


def _secondary_id(period_id: str, signal_time: pd.Timestamp, pair: str) -> str:
    return f"SECONDARY::{period_id}::{_utc(signal_time).isoformat()}::{pair}"


def secondary_precedence_decision(*, same_pair_open: bool, secondary_open: bool, open_position_count: int) -> str:
    """Return the frozen precedence decision before downstream admission."""
    if not same_pair_open:
        return "NATIVE_FLOW"
    if secondary_open:
        return "BLOCK_GLOBAL_SINGLE_ACTIVE_SECONDARY"
    if open_position_count >= MAXIMUM_POSITIONS:
        return "BLOCK_POSITION_SLOTS"
    return "BYPASS_SAME_PAIR_ONLY_CONTINUE_NATIVE_DOWNSTREAM"


def _marked_equity(cash: float, positions: dict[str, ShadowPosition]) -> tuple[float, float]:
    gross = sum(position.quantity * position.last_mark for position in positions.values())
    return float(cash + gross), float(gross)


def _bar_at(pair: str, timestamp: pd.Timestamp, frames: dict[str, pd.DataFrame], lookups: dict[str, dict[int, int]]) -> pd.Series | None:
    frame = frames.get(pair)
    if frame is None:
        return None
    index = lookups.get(pair, {}).get(int(_utc(timestamp).value))
    return None if index is None else frame.iloc[index]


def _state_at(lookup: dict[int, str], timestamp: pd.Timestamp) -> str:
    value = lookup.get(int(_utc(timestamp).value))
    if value is None:
        raise SamePairSecondaryShadowError(f"market state unavailable at causal cutoff: {timestamp}")
    return value


def _close_position(*, position: ShadowPosition, timestamp: pd.Timestamp, exit_price: float, exit_reason: str, exit_market_state: str, side_cost: float, portfolio_id: str, universe_id: str, cost_multiplier: float) -> tuple[dict[str, Any], float]:
    exit_notional = position.quantity * exit_price
    exit_cost = exit_notional * side_cost
    gross_pnl = exit_notional - position.entry_notional
    net_pnl = gross_pnl - position.entry_cost - exit_cost
    cash_credit = exit_notional - exit_cost
    return {
        "policy_id": rd27.STATIC_EXIT_STATE_ROUTER,
        "portfolio_id": portfolio_id,
        "universe_id": universe_id,
        "cost_multiplier": cost_multiplier,
        "position_id": position.position_id,
        "pair": position.pair,
        "signal_time": position.signal_time,
        "entry_time": position.entry_time,
        "exit_time": timestamp,
        "holding_hours": int((timestamp - position.entry_time).total_seconds() / 3600.0),
        "exit_reason": exit_reason,
        "entry_price": position.entry_price,
        "exit_price": exit_price,
        "quantity": position.quantity,
        "entry_notional": position.entry_notional,
        "exit_notional": exit_notional,
        "entry_cost": position.entry_cost,
        "exit_cost": exit_cost,
        "gross_pnl": gross_pnl,
        "net_pnl": net_pnl,
        "period_id": position.period_id,
        "membership_rank": position.membership_rank,
        "support_families": "|".join(position.support_families),
        "support_count": len(position.support_families),
        "atr24_at_signal": position.atr24_at_signal,
        "high_water_at_exit": position.lifecycle.high_water_prior,
        "entry_market_state": position.entry_market_state,
        "exit_market_state": exit_market_state,
        "protection_floor_at_exit": position.lifecycle.protection_floor,
        "is_secondary": position.is_secondary,
    }, float(cash_credit)


def _empty_diagnostics() -> dict[str, Any]:
    return {
        "policy_enabled": False,
        "admitted_native_entries": 0,
        "secondary_trigger_count": 0,
        "secondary_executed_count": 0,
        "secondary_blocked_global_active_count": 0,
        "secondary_blocked_position_slots_count": 0,
        "secondary_blocked_risk_off_count": 0,
        "secondary_blocked_data_or_capacity_count": 0,
        "secondary_blocked_equity_or_gross_count": 0,
        "secondary_blocked_cash_or_notional_count": 0,
        "secondary_trade_count": 0,
        "secondary_execution_records": [],
        "secondary_trigger_event_keys": [],
        "max_open_positions_hourly_close": 0,
        "max_gross_exposure_hourly_close": 0.0,
        "max_gross_exposure_fraction_mark_to_market_diagnostic": 0.0,
        "minimum_cash_hourly_close": INITIAL_EQUITY,
    }


def replay_same_pair_secondary_shadow(*, portfolio_id: str, universe_id: str, cost_multiplier: float, events: pd.DataFrame, frames: dict[str, pd.DataFrame], state_frame: pd.DataFrame, replay_start: pd.Timestamp, replay_cutoff: pd.Timestamp, shadow_enabled: bool = DEFAULT_SHADOW_ENABLED) -> ShadowReplayResult:
    """Replay the bounded shadow; disabled mode is exact native RD27 delegation."""
    validate_shadow_constants()
    if cost_multiplier not in COST_MULTIPLIERS:
        raise SamePairSecondaryShadowError("unsupported cost multiplier")
    replay_start, replay_cutoff = _utc(replay_start), _utc(replay_cutoff)
    if replay_start >= replay_cutoff:
        raise SamePairSecondaryShadowError("invalid replay window")

    if not shadow_enabled:
        trades, daily, metrics, counters = rd27.replay_lifecycle_policy(
            policy_id=rd27.STATIC_EXIT_STATE_ROUTER,
            portfolio_id=portfolio_id,
            universe_id=universe_id,
            cost_multiplier=cost_multiplier,
            events=events,
            frames=frames,
            state_frame=state_frame,
            replay_start=replay_start,
            replay_cutoff=replay_cutoff,
        )
        return ShadowReplayResult(trades, daily, metrics, counters, _empty_diagnostics())

    lookups = {pair: fast_lookup(frame) for pair, frame in frames.items()}
    state_lookup = rd27.build_state_lookup(state_frame)
    side_cost = BASE_ROUND_TRIP_COST * cost_multiplier / 2.0
    scheduled: dict[int, list[dict[str, Any]]] = {}
    for raw in events.to_dict(orient="records"):
        signal_time = _utc(raw["timestamp"])
        entry_time = signal_time + pd.Timedelta(hours=1)
        max_exit_time = entry_time + pd.Timedelta(hours=168)
        if entry_time < replay_start or max_exit_time >= replay_cutoff:
            continue
        scheduled.setdefault(int(entry_time.value), []).append({**raw, "signal_time": signal_time, "entry_time": entry_time, "max_exit_time": max_exit_time})
    for items in scheduled.values():
        items.sort(key=lambda item: (int(item["membership_rank"]), str(item["pair"])))

    counters = {
        "signal_events": len(events), "missing_entry_bar": 0, "missing_exit_bar_precheck": 0,
        "same_pair_open": 0, "position_slots_full": 0, "gross_limit_rejection": 0,
        "capacity_unavailable": 0, "capacity_capped_entries": 0, "cash_capped_entries": 0,
        "admitted_entries": 0, "risk_off_suppressed_entries": 0, "entry_bar_adaptive_exits": 0,
        "max_hold_exits": 0, "time_failure_exits": 0, "adaptive_stagnation_exits": 0,
        "adaptive_protection_gap_exits": 0, "adaptive_protection_touch_exits": 0,
    }
    for state in MARKET_STATES:
        counters[f"entry_state_{state}"] = 0
    diagnostics = _empty_diagnostics()
    diagnostics["policy_enabled"] = True
    positions: dict[str, ShadowPosition] = {}
    cash = float(INITIAL_EQUITY)
    trades: list[dict[str, Any]] = []
    daily_rows: list[dict[str, Any]] = []
    hourly_equity: list[float] = []

    for timestamp in pd.date_range(replay_start, replay_cutoff, freq="h", inclusive="left"):
        timestamp = _utc(timestamp)
        for position_id in sorted(list(positions)):
            position = positions[position_id]
            bar = _bar_at(position.pair, timestamp, frames, lookups)
            prior_bar = _bar_at(position.pair, timestamp - pd.Timedelta(hours=1), frames, lookups)
            if bar is None or prior_bar is None:
                raise SamePairSecondaryShadowError(f"open-position bar missing: {position_id} {timestamp}")
            current_state = _state_at(state_lookup, timestamp - pd.Timedelta(hours=1))
            reason: str | None = None
            if timestamp == position.max_exit_time:
                reason = "MAX_HOLD_168H"; counters["max_hold_exits"] += 1
            elif timestamp == position.entry_time + pd.Timedelta(hours=72) and float(prior_bar["close"]) <= position.entry_price:
                reason = "TIME_FAILURE_72H_CLOSE_NOT_ABOVE_ENTRY"; counters["time_failure_exits"] += 1
            if reason is not None:
                record, credit = _close_position(position=position, timestamp=timestamp, exit_price=float(bar["open"]), exit_reason=reason, exit_market_state=current_state, side_cost=side_cost, portfolio_id=portfolio_id, universe_id=universe_id, cost_multiplier=cost_multiplier)
                cash += credit; trades.append(record); del positions[position_id]

        for position in positions.values():
            bar = _bar_at(position.pair, timestamp, frames, lookups)
            if bar is not None:
                position.last_mark = float(bar["open"])

        for item in scheduled.get(int(timestamp.value), []):
            pair = str(item["pair"]); signal_time = _utc(item["signal_time"]); period_id = str(item["period_id"])
            event_key = _event_key(period_id, signal_time, pair)
            same_pair_lots = [p for p in positions.values() if p.pair == pair]
            secondary_open = any(p.is_secondary for p in positions.values())
            decision = secondary_precedence_decision(same_pair_open=bool(same_pair_lots), secondary_open=secondary_open, open_position_count=len(positions))
            secondary_attempt = bool(same_pair_lots)
            if secondary_attempt:
                diagnostics["secondary_trigger_count"] += 1; diagnostics["secondary_trigger_event_keys"].append(event_key)
            if decision == "BLOCK_GLOBAL_SINGLE_ACTIVE_SECONDARY":
                counters["same_pair_open"] += 1; diagnostics["secondary_blocked_global_active_count"] += 1; continue
            if decision == "BLOCK_POSITION_SLOTS":
                counters["position_slots_full"] += 1; diagnostics["secondary_blocked_position_slots_count"] += 1; continue
            if decision == "NATIVE_FLOW" and len(positions) >= MAXIMUM_POSITIONS:
                counters["position_slots_full"] += 1; continue

            entry_state = _state_at(state_lookup, signal_time)
            counters[f"entry_state_{entry_state}"] += 1
            admission = capital_admission_decision(entry_state)
            if not admission.admit_position:
                if entry_state != RISK_OFF:
                    raise SamePairSecondaryShadowError("non-RISK_OFF signal unexpectedly suppressed")
                counters["risk_off_suppressed_entries"] += 1
                if secondary_attempt: diagnostics["secondary_blocked_risk_off_count"] += 1
                continue

            entry_bar = _bar_at(pair, timestamp, frames, lookups)
            exit_bar = _bar_at(pair, _utc(item["max_exit_time"]), frames, lookups)
            if entry_bar is None or exit_bar is None:
                counters["missing_entry_bar" if entry_bar is None else "missing_exit_bar_precheck"] += 1
                if secondary_attempt: diagnostics["secondary_blocked_data_or_capacity_count"] += 1
                continue
            signal_bar = _bar_at(pair, signal_time, frames, lookups)
            if signal_bar is None:
                counters["capacity_unavailable"] += 1
                if secondary_attempt: diagnostics["secondary_blocked_data_or_capacity_count"] += 1
                continue
            capacity_source = float(signal_bar["trailing_24h_quote_turnover_proxy"])
            if not math.isfinite(capacity_source) or capacity_source <= 0.0:
                counters["capacity_unavailable"] += 1
                if secondary_attempt: diagnostics["secondary_blocked_data_or_capacity_count"] += 1
                continue

            equity_open, gross_open = _marked_equity(cash, positions)
            if not math.isfinite(equity_open) or equity_open <= 0.0 or not math.isfinite(gross_open):
                if secondary_attempt: diagnostics["secondary_blocked_equity_or_gross_count"] += 1; continue
                raise SamePairSecondaryShadowError("invalid live equity/gross")
            gross_room = max(0.0, (equity_open * MAXIMUM_GROSS_EXPOSURE - gross_open) / (1.0 + MAXIMUM_GROSS_EXPOSURE * side_cost))
            if gross_room <= 0.0:
                counters["gross_limit_rejection"] += 1
                if secondary_attempt: diagnostics["secondary_blocked_equity_or_gross_count"] += 1
                continue
            target_notional = equity_open * float(admission.target_slot_fraction)
            capacity_notional = capacity_source * LIQUIDITY_CAPACITY_FRACTION_24H
            notional = min(target_notional, gross_room, capacity_notional)
            if notional < target_notional - 1e-9 and capacity_notional <= min(target_notional, gross_room):
                counters["capacity_capped_entries"] += 1
            max_cash_notional = cash / (1.0 + side_cost)
            if max_cash_notional <= 0.0:
                if secondary_attempt: diagnostics["secondary_blocked_cash_or_notional_count"] += 1
                continue
            if notional > max_cash_notional:
                counters["cash_capped_entries"] += 1; notional = max_cash_notional
            if not math.isfinite(notional) or notional <= 0.0:
                if secondary_attempt: diagnostics["secondary_blocked_cash_or_notional_count"] += 1
                continue

            entry_price = float(entry_bar["open"])
            if not math.isfinite(entry_price) or entry_price <= 0.0:
                if secondary_attempt: diagnostics["secondary_blocked_data_or_capacity_count"] += 1
                continue
            quantity = notional / entry_price; entry_cost = notional * side_cost; cash_before = cash
            required_cash = notional + entry_cost
            if required_cash > cash + 1e-9 * (1.0 + abs(cash)):
                if secondary_attempt: diagnostics["secondary_blocked_cash_or_notional_count"] += 1; continue
                raise SamePairSecondaryShadowError("negative cash would occur on native entry")
            cash -= required_cash; cash = max(cash, 0.0)
            support = tuple(sorted(f for f in str(item["support_families"]).split("|") if f))
            position_id = _secondary_id(period_id, signal_time, pair) if secondary_attempt else f"NATIVE::{pair}"
            if position_id in positions:
                raise SamePairSecondaryShadowError(f"position identity collision: {position_id}")
            lifecycle = new_lifecycle_position(pair=pair, entry_time=timestamp, entry_price=entry_price, atr24_at_signal=float(item["atr24_at_signal"]))
            positions[position_id] = ShadowPosition(position_id, pair, signal_time, timestamp, _utc(item["max_exit_time"]), entry_price, quantity, notional, entry_cost, int(item["membership_rank"]), support, period_id, float(item["atr24_at_signal"]), lifecycle, entry_state, entry_price, secondary_attempt)
            counters["admitted_entries"] += 1
            if secondary_attempt:
                diagnostics["secondary_executed_count"] += 1
                diagnostics["secondary_execution_records"].append({
                    "cash_before_entry": float(cash_before), "entry_cost": float(entry_cost), "entry_notional": float(notional),
                    "entry_state": entry_state, "entry_time": timestamp.isoformat(), "equity_before_entry": float(equity_open),
                    "event_key": event_key, "gross_before_entry": float(gross_open), "open_positions_before_entry": len(positions) - 1,
                    "pair": pair, "period_id": period_id, "signal_time": signal_time.isoformat(),
                    "target_slot_fraction": float(admission.target_slot_fraction),
                })
            else:
                diagnostics["admitted_native_entries"] += 1

        for position in positions.values():
            bar = _bar_at(position.pair, timestamp, frames, lookups)
            if bar is None:
                raise SamePairSecondaryShadowError(f"position mark bar missing: {position.position_id} {timestamp}")
            position.lifecycle = replace(position.lifecycle, high_water_prior=max(position.lifecycle.high_water_prior, float(bar["high"])))
            position.last_mark = float(bar["close"])

        equity_close, gross_close = _marked_equity(cash, positions)
        if equity_close < -1e-7 or cash < -1e-7 or len(positions) > MAXIMUM_POSITIONS:
            raise SamePairSecondaryShadowError("portfolio safety invariant breached")
        hourly_equity.append(equity_close)
        diagnostics["minimum_cash_hourly_close"] = min(float(diagnostics["minimum_cash_hourly_close"]), cash)
        diagnostics["max_open_positions_hourly_close"] = max(int(diagnostics["max_open_positions_hourly_close"]), len(positions))
        diagnostics["max_gross_exposure_hourly_close"] = max(float(diagnostics["max_gross_exposure_hourly_close"]), gross_close)
        gross_fraction = gross_close / equity_close if equity_close > 0.0 else math.inf
        diagnostics["max_gross_exposure_fraction_mark_to_market_diagnostic"] = max(float(diagnostics["max_gross_exposure_fraction_mark_to_market_diagnostic"]), gross_fraction)
        if timestamp.hour == 23:
            daily_rows.append({"policy_id": rd27.STATIC_EXIT_STATE_ROUTER, "portfolio_id": portfolio_id, "universe_id": universe_id, "cost_multiplier": cost_multiplier, "timestamp": timestamp, "equity": equity_close, "cash": cash, "gross_exposure": gross_close, "gross_exposure_fraction": gross_fraction, "open_positions": len(positions)})

    if positions:
        raise SamePairSecondaryShadowError("open positions remained at replay cutoff")
    trade_frame = pd.DataFrame.from_records(trades); daily_frame = pd.DataFrame.from_records(daily_rows)
    equity_array = np.asarray(hourly_equity, dtype=float); running_peak = np.maximum.accumulate(equity_array)
    drawdowns = np.divide(running_peak - equity_array, running_peak, out=np.zeros_like(equity_array), where=running_peak > 0.0)
    final_equity = float(equity_array[-1]) if len(equity_array) else INITIAL_EQUITY
    metrics = performance_metrics(trade_frame=trade_frame, final_equity=final_equity, maximum_drawdown=float(drawdowns.max()) if len(drawdowns) else 0.0)
    metrics.update({"policy_id": rd27.STATIC_EXIT_STATE_ROUTER, "portfolio_id": portfolio_id, "universe_id": universe_id, "cost_multiplier": cost_multiplier, "minimum_cash": float(daily_frame["cash"].min()) if len(daily_frame) else INITIAL_EQUITY})
    diagnostics["secondary_trade_count"] = int(sum(bool(record["is_secondary"]) for record in trades))
    return ShadowReplayResult(trade_frame, daily_frame, metrics, counters, diagnostics)
