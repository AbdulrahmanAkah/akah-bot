"""RD27 frozen portfolio replay adapter for the preregistered lifecycle ablation."""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Any, Final

import numpy as np
import pandas as pd

from spotbot.research.rd26_exit_architecture import (
    BASE_ROUND_TRIP_COST,
    COST_MULTIPLIERS,
    DATA_CUTOFF,
    DATA_START,
    INITIAL_EQUITY,
    LIQUIDITY_CAPACITY_FRACTION_24H,
    MAXIMUM_GROSS_EXPOSURE,
    MAXIMUM_POSITIONS,
    POLICY_TIME_FAIL,
    TARGET_SLOT_NOTIONAL_FRACTION,
    fast_lookup,
    performance_metrics,
)
from spotbot.research.rd26_exit_architecture import (
    replay_policy as rd26_replay_policy,
)
from spotbot.research.rd27_adaptive_lifecycle import (
    MARKET_STATES,
    RISK_OFF,
    LifecyclePosition,
    apply_completed_bar_update,
    capital_admission_decision,
    evaluate_adaptive_exit,
    new_lifecycle_position,
)

SCHEMA_VERSION: Final = "rd27-lifecycle-portfolio-replay-v1"

CONTROL_TIME_FAIL_72_FIXED_CAPITAL: Final = "CONTROL_TIME_FAIL_72_FIXED_CAPITAL"
ADAPTIVE_EXIT_FIXED_CAPITAL: Final = "ADAPTIVE_EXIT_FIXED_CAPITAL"
STATIC_EXIT_STATE_ROUTER: Final = "STATIC_EXIT_STATE_ROUTER"
FULL_ADAPTIVE_LIFECYCLE_BRAIN: Final = "FULL_ADAPTIVE_LIFECYCLE_BRAIN"

POLICIES: Final = (
    CONTROL_TIME_FAIL_72_FIXED_CAPITAL,
    ADAPTIVE_EXIT_FIXED_CAPITAL,
    STATIC_EXIT_STATE_ROUTER,
    FULL_ADAPTIVE_LIFECYCLE_BRAIN,
)


class RD27ReplayError(RuntimeError):
    """Raised when frozen RD27 portfolio replay semantics are violated."""


@dataclass
class ReplayPosition:
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


def validate_policy_constants() -> None:
    if POLICIES != (
        CONTROL_TIME_FAIL_72_FIXED_CAPITAL,
        ADAPTIVE_EXIT_FIXED_CAPITAL,
        STATIC_EXIT_STATE_ROUTER,
        FULL_ADAPTIVE_LIFECYCLE_BRAIN,
    ):
        raise RD27ReplayError("RD27 policy registry drifted")
    if not math.isclose(TARGET_SLOT_NOTIONAL_FRACTION, 0.18):
        raise RD27ReplayError("RD26 fixed-capital slot contract drifted")


def policy_components(policy_id: str) -> tuple[bool, bool]:
    if policy_id == CONTROL_TIME_FAIL_72_FIXED_CAPITAL:
        return False, False
    if policy_id == ADAPTIVE_EXIT_FIXED_CAPITAL:
        return False, True
    if policy_id == STATIC_EXIT_STATE_ROUTER:
        return True, False
    if policy_id == FULL_ADAPTIVE_LIFECYCLE_BRAIN:
        return True, True
    raise RD27ReplayError(f"unknown RD27 policy: {policy_id}")


def active_component_count(policy_id: str) -> int:
    router, adaptive_exit = policy_components(policy_id)
    return int(router) + int(adaptive_exit)


def build_state_lookup(state_frame: pd.DataFrame) -> dict[int, str]:
    required = {"timestamp", "market_state", "state_ready"}
    missing = sorted(required.difference(state_frame.columns))
    if missing:
        raise RD27ReplayError(f"state frame missing columns: {missing}")
    timestamps = pd.to_datetime(state_frame["timestamp"], utc=True, errors="raise")
    lookup: dict[int, str] = {}
    for timestamp, state, ready in zip(
        timestamps,
        state_frame["market_state"],
        state_frame["state_ready"],
        strict=True,
    ):
        if not bool(ready):
            continue
        if pd.isna(state):
            raise RD27ReplayError("ready state row has null market state")
        state_text = str(state)
        if state_text not in MARKET_STATES:
            raise RD27ReplayError(f"unknown market state in state frame: {state_text}")
        lookup[int(pd.Timestamp(timestamp).value)] = state_text
    return lookup


def _utc_timestamp(value: Any) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    return (
        timestamp.tz_localize("UTC")
        if timestamp.tzinfo is None
        else timestamp.tz_convert("UTC")
    )


def _state_at(lookup: dict[int, str], timestamp: pd.Timestamp) -> str:
    value = lookup.get(int(_utc_timestamp(timestamp).value))
    if value is None:
        raise RD27ReplayError(f"market state unavailable at causal cutoff: {timestamp}")
    return value


def _bar_at(
    pair: str,
    timestamp: pd.Timestamp,
    frames: dict[str, pd.DataFrame],
    lookups: dict[str, dict[int, int]],
) -> pd.Series | None:
    frame = frames.get(pair)
    if frame is None:
        return None
    index = lookups.get(pair, {}).get(int(pd.Timestamp(timestamp).value))
    if index is None:
        return None
    return frame.iloc[index]


def _marked_equity(
    *,
    cash: float,
    positions: dict[str, ReplayPosition],
) -> tuple[float, float]:
    gross = sum(position.quantity * position.last_mark for position in positions.values())
    return cash + gross, gross


def _close_position(
    *,
    position: ReplayPosition,
    timestamp: pd.Timestamp,
    exit_price: float,
    exit_reason: str,
    exit_market_state: str,
    side_cost: float,
    policy_id: str,
    portfolio_id: str,
    universe_id: str,
    cost_multiplier: float,
) -> tuple[dict[str, Any], float]:
    exit_notional = position.quantity * exit_price
    exit_cost = exit_notional * side_cost
    gross_pnl = exit_notional - position.entry_notional
    net_pnl = gross_pnl - position.entry_cost - exit_cost
    cash_credit = exit_notional - exit_cost
    holding_hours = int((timestamp - position.entry_time).total_seconds() / 3600.0)
    record = {
        "policy_id": policy_id,
        "portfolio_id": portfolio_id,
        "universe_id": universe_id,
        "cost_multiplier": cost_multiplier,
        "pair": position.pair,
        "signal_time": position.signal_time,
        "entry_time": position.entry_time,
        "exit_time": timestamp,
        "holding_hours": holding_hours,
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
    }
    return record, cash_credit


def replay_lifecycle_policy(
    *,
    policy_id: str,
    portfolio_id: str,
    universe_id: str,
    cost_multiplier: float,
    events: pd.DataFrame,
    frames: dict[str, pd.DataFrame],
    state_frame: pd.DataFrame,
    replay_start: pd.Timestamp = DATA_START,
    replay_cutoff: pd.Timestamp = DATA_CUTOFF,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any], dict[str, int]]:
    """Replay one frozen RD27 policy; the control delegates exactly to RD26 TIME_FAIL."""
    validate_policy_constants()
    router_enabled, adaptive_exit_enabled = policy_components(policy_id)
    if cost_multiplier not in COST_MULTIPLIERS:
        raise RD27ReplayError("unsupported cost multiplier")

    if policy_id == CONTROL_TIME_FAIL_72_FIXED_CAPITAL:
        if replay_start != DATA_START or replay_cutoff != DATA_CUTOFF:
            raise RD27ReplayError("RD26 control delegation requires the frozen full window")
        trades, daily, metrics, counters = rd26_replay_policy(
            policy_id=POLICY_TIME_FAIL,
            portfolio_id=portfolio_id,
            universe_id=universe_id,
            cost_multiplier=cost_multiplier,
            events=events,
            frames=frames,
        )
        trades = trades.copy()
        daily = daily.copy()
        if len(trades):
            trades["policy_id"] = policy_id
        if len(daily):
            daily["policy_id"] = policy_id
        metrics = {**metrics, "policy_id": policy_id}
        return trades, daily, metrics, counters

    replay_start = _utc_timestamp(replay_start)
    replay_cutoff = _utc_timestamp(replay_cutoff)
    if replay_start >= replay_cutoff:
        raise RD27ReplayError("invalid replay window")

    lookups = {pair: fast_lookup(frame) for pair, frame in frames.items()}
    state_lookup = build_state_lookup(state_frame)
    side_cost = BASE_ROUND_TRIP_COST * cost_multiplier / 2.0

    scheduled: dict[int, list[dict[str, Any]]] = {}
    for raw in events.to_dict(orient="records"):
        signal_time = _utc_timestamp(raw["timestamp"])
        entry_time = signal_time + pd.Timedelta(hours=1)
        max_exit_time = entry_time + pd.Timedelta(hours=168)
        if entry_time < replay_start or max_exit_time >= replay_cutoff:
            continue
        scheduled.setdefault(int(entry_time.value), []).append(
            {
                **raw,
                "signal_time": signal_time,
                "entry_time": entry_time,
                "max_exit_time": max_exit_time,
            }
        )

    cash = INITIAL_EQUITY
    positions: dict[str, ReplayPosition] = {}
    trades: list[dict[str, Any]] = []
    daily_rows: list[dict[str, Any]] = []
    hourly_equity_values: list[float] = []
    pending_updates: dict[str, Any] = {}

    counters = {
        "signal_events": len(events),
        "missing_entry_bar": 0,
        "missing_exit_bar_precheck": 0,
        "same_pair_open": 0,
        "position_slots_full": 0,
        "gross_limit_rejection": 0,
        "capacity_unavailable": 0,
        "capacity_capped_entries": 0,
        "cash_capped_entries": 0,
        "admitted_entries": 0,
        "risk_off_suppressed_entries": 0,
        "entry_bar_adaptive_exits": 0,
        "max_hold_exits": 0,
        "time_failure_exits": 0,
        "adaptive_stagnation_exits": 0,
        "adaptive_protection_gap_exits": 0,
        "adaptive_protection_touch_exits": 0,
    }
    for state in MARKET_STATES:
        counters[f"entry_state_{state}"] = 0

    for timestamp in pd.date_range(replay_start, replay_cutoff, freq="h", inclusive="left"):
        pending_updates.clear()

        for pair in sorted(list(positions)):
            position = positions[pair]
            bar = _bar_at(pair, timestamp, frames, lookups)
            if bar is None:
                raise RD27ReplayError(f"open-position bar missing: {pair} {timestamp}")
            prior_bar = _bar_at(
                pair,
                timestamp - pd.Timedelta(hours=1),
                frames,
                lookups,
            )
            if prior_bar is None:
                raise RD27ReplayError(f"prior asset bar missing: {pair} {timestamp}")

            current_state = _state_at(
                state_lookup,
                timestamp - pd.Timedelta(hours=1),
            )
            exit_price: float | None = None
            exit_reason: str | None = None

            if adaptive_exit_enabled:
                decision = evaluate_adaptive_exit(
                    position.lifecycle,
                    current_open_time=timestamp,
                    current_open=float(bar["open"]),
                    current_low=float(bar["low"]),
                    prior_asset_close=float(prior_bar["close"]),
                    market_state=current_state,
                )
                if decision.should_exit:
                    exit_price = decision.exit_price
                    exit_reason = decision.exit_reason
                    if exit_reason == "MAX_HOLD_168H":
                        counters["max_hold_exits"] += 1
                    elif exit_reason == "ADAPTIVE_PROTECTION_GAP":
                        counters["adaptive_protection_gap_exits"] += 1
                    elif exit_reason == "ADAPTIVE_PROTECTION_TOUCH":
                        counters["adaptive_protection_touch_exits"] += 1
                    elif exit_reason and exit_reason.startswith("ADAPTIVE_STAGNATION_"):
                        counters["adaptive_stagnation_exits"] += 1
                else:
                    pending_updates[pair] = decision
            else:
                if timestamp == position.max_exit_time:
                    exit_price = float(bar["open"])
                    exit_reason = "MAX_HOLD_168H"
                    counters["max_hold_exits"] += 1
                elif timestamp == position.entry_time + pd.Timedelta(hours=72):
                    if float(prior_bar["close"]) <= position.entry_price:
                        exit_price = float(bar["open"])
                        exit_reason = "TIME_FAILURE_72H_CLOSE_NOT_ABOVE_ENTRY"
                        counters["time_failure_exits"] += 1

            if exit_price is not None and exit_reason is not None:
                record, credit = _close_position(
                    position=position,
                    timestamp=timestamp,
                    exit_price=float(exit_price),
                    exit_reason=exit_reason,
                    exit_market_state=current_state,
                    side_cost=side_cost,
                    policy_id=policy_id,
                    portfolio_id=portfolio_id,
                    universe_id=universe_id,
                    cost_multiplier=cost_multiplier,
                )
                cash += credit
                trades.append(record)
                del positions[pair]
                pending_updates.pop(pair, None)

        for pair, position in positions.items():
            bar = _bar_at(pair, timestamp, frames, lookups)
            if bar is not None:
                position.last_mark = float(bar["open"])

        entries = sorted(
            scheduled.get(int(timestamp.value), []),
            key=lambda item: (int(item["membership_rank"]), str(item["pair"])),
        )
        for item in entries:
            pair = str(item["pair"])
            if pair in positions:
                counters["same_pair_open"] += 1
                continue
            if len(positions) >= MAXIMUM_POSITIONS:
                counters["position_slots_full"] += 1
                continue

            signal_time = pd.Timestamp(item["signal_time"])
            entry_state = _state_at(state_lookup, signal_time)
            counters[f"entry_state_{entry_state}"] += 1
            target_slot_fraction = TARGET_SLOT_NOTIONAL_FRACTION
            if router_enabled:
                admission = capital_admission_decision(entry_state)
                if not admission.admit_position:
                    if entry_state != RISK_OFF:
                        raise RD27ReplayError("non-RISK_OFF signal unexpectedly suppressed")
                    counters["risk_off_suppressed_entries"] += 1
                    continue
                target_slot_fraction = admission.target_slot_fraction

            entry_bar = _bar_at(pair, timestamp, frames, lookups)
            if entry_bar is None:
                counters["missing_entry_bar"] += 1
                continue
            exit_bar = _bar_at(
                pair,
                pd.Timestamp(item["max_exit_time"]),
                frames,
                lookups,
            )
            if exit_bar is None:
                counters["missing_exit_bar_precheck"] += 1
                continue
            signal_bar = _bar_at(pair, signal_time, frames, lookups)
            if signal_bar is None:
                raise RD27ReplayError("signal bar missing during admission")
            capacity_source = float(signal_bar["trailing_24h_quote_turnover_proxy"])
            if not math.isfinite(capacity_source) or capacity_source <= 0.0:
                counters["capacity_unavailable"] += 1
                continue

            equity_open, gross_open = _marked_equity(cash=cash, positions=positions)
            if equity_open <= 0.0:
                continue
            gross_numerator = equity_open * MAXIMUM_GROSS_EXPOSURE - gross_open
            gross_room = max(
                0.0,
                gross_numerator / (1.0 + MAXIMUM_GROSS_EXPOSURE * side_cost),
            )
            if gross_room <= 0.0:
                counters["gross_limit_rejection"] += 1
                continue

            target_notional = equity_open * float(target_slot_fraction)
            capacity_notional = capacity_source * LIQUIDITY_CAPACITY_FRACTION_24H
            notional = min(target_notional, gross_room, capacity_notional)
            if notional < target_notional - 1e-9 and capacity_notional <= min(
                target_notional,
                gross_room,
            ):
                counters["capacity_capped_entries"] += 1

            max_cash_notional = cash / (1.0 + side_cost)
            if max_cash_notional <= 0.0:
                continue
            if notional > max_cash_notional:
                counters["cash_capped_entries"] += 1
                notional = max_cash_notional
            if notional <= 0.0:
                continue

            entry_price = float(entry_bar["open"])
            quantity = notional / entry_price
            entry_cost = notional * side_cost
            cash -= notional + entry_cost
            if cash < -1e-7:
                raise RD27ReplayError("negative cash after entry")
            cash = max(cash, 0.0)

            support = tuple(
                sorted(
                    family
                    for family in str(item["support_families"]).split("|")
                    if family
                )
            )
            atr = float(item["atr24_at_signal"])
            lifecycle = new_lifecycle_position(
                pair=pair,
                entry_time=timestamp,
                entry_price=entry_price,
                atr24_at_signal=atr,
            )
            position = ReplayPosition(
                pair=pair,
                signal_time=signal_time,
                entry_time=timestamp,
                max_exit_time=pd.Timestamp(item["max_exit_time"]),
                entry_price=entry_price,
                quantity=quantity,
                entry_notional=notional,
                entry_cost=entry_cost,
                membership_rank=int(item["membership_rank"]),
                support_families=support,
                period_id=str(item["period_id"]),
                atr24_at_signal=atr,
                lifecycle=lifecycle,
                entry_market_state=entry_state,
                last_mark=entry_price,
            )
            positions[pair] = position
            counters["admitted_entries"] += 1

            if adaptive_exit_enabled:
                prior_bar = _bar_at(
                    pair,
                    timestamp - pd.Timedelta(hours=1),
                    frames,
                    lookups,
                )
                if prior_bar is None:
                    raise RD27ReplayError("entry-bar prior asset close missing")
                decision = evaluate_adaptive_exit(
                    lifecycle,
                    current_open_time=timestamp,
                    current_open=entry_price,
                    current_low=float(entry_bar["low"]),
                    prior_asset_close=float(prior_bar["close"]),
                    market_state=entry_state,
                )
                if decision.should_exit:
                    if decision.exit_price is None or decision.exit_reason is None:
                        raise RD27ReplayError("adaptive entry exit missing fill details")
                    reason = decision.exit_reason
                    if reason == "ADAPTIVE_PROTECTION_GAP":
                        counters["adaptive_protection_gap_exits"] += 1
                    elif reason == "ADAPTIVE_PROTECTION_TOUCH":
                        counters["adaptive_protection_touch_exits"] += 1
                    elif reason.startswith("ADAPTIVE_STAGNATION_"):
                        counters["adaptive_stagnation_exits"] += 1
                    elif reason == "MAX_HOLD_168H":
                        counters["max_hold_exits"] += 1
                    counters["entry_bar_adaptive_exits"] += 1
                    record, credit = _close_position(
                        position=position,
                        timestamp=timestamp,
                        exit_price=float(decision.exit_price),
                        exit_reason=reason,
                        exit_market_state=entry_state,
                        side_cost=side_cost,
                        policy_id=policy_id,
                        portfolio_id=portfolio_id,
                        universe_id=universe_id,
                        cost_multiplier=cost_multiplier,
                    )
                    cash += credit
                    trades.append(record)
                    del positions[pair]
                else:
                    pending_updates[pair] = decision

        for pair, position in positions.items():
            bar = _bar_at(pair, timestamp, frames, lookups)
            if bar is None:
                raise RD27ReplayError(f"position mark bar missing: {pair} {timestamp}")
            if adaptive_exit_enabled:
                decision = pending_updates.get(pair)
                if decision is None:
                    raise RD27ReplayError(f"adaptive survivor missing decision: {pair} {timestamp}")
                position.lifecycle = apply_completed_bar_update(
                    position.lifecycle,
                    decision=decision,
                    completed_high=float(bar["high"]),
                )
            else:
                position.lifecycle = replace(
                    position.lifecycle,
                    high_water_prior=max(
                        position.lifecycle.high_water_prior,
                        float(bar["high"]),
                    ),
                )
            position.last_mark = float(bar["close"])

        equity_close, gross_close = _marked_equity(cash=cash, positions=positions)
        if equity_close < -1e-7:
            raise RD27ReplayError("negative equity observed")
        hourly_equity_values.append(equity_close)
        if timestamp.hour == 23:
            daily_rows.append(
                {
                    "policy_id": policy_id,
                    "portfolio_id": portfolio_id,
                    "universe_id": universe_id,
                    "cost_multiplier": cost_multiplier,
                    "timestamp": timestamp,
                    "equity": equity_close,
                    "cash": cash,
                    "gross_exposure": gross_close,
                    "gross_exposure_fraction": (
                        gross_close / equity_close if equity_close > 0.0 else math.nan
                    ),
                    "open_positions": len(positions),
                }
            )

    if positions:
        raise RD27ReplayError("open positions remained at replay cutoff")

    trade_frame = pd.DataFrame.from_records(trades)
    daily_frame = pd.DataFrame.from_records(daily_rows)
    equity = np.asarray(hourly_equity_values, dtype=float)
    running_peak = np.maximum.accumulate(equity)
    drawdowns = np.divide(
        running_peak - equity,
        running_peak,
        out=np.zeros_like(equity),
        where=running_peak > 0.0,
    )
    final_equity = float(equity[-1]) if len(equity) else INITIAL_EQUITY
    metrics = performance_metrics(
        trade_frame=trade_frame,
        final_equity=final_equity,
        maximum_drawdown=float(drawdowns.max()) if len(drawdowns) else 0.0,
    )
    metrics.update(
        {
            "policy_id": policy_id,
            "portfolio_id": portfolio_id,
            "universe_id": universe_id,
            "cost_multiplier": cost_multiplier,
            "minimum_cash": (
                float(daily_frame["cash"].min()) if len(daily_frame) else INITIAL_EQUITY
            ),
        }
    )
    return trade_frame, daily_frame, metrics, counters
