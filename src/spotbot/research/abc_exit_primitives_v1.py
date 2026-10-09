"""Frozen A/B/C exit primitive execution adapter V1.

This module overlays preregistered exit candidates on the existing
FULL_ADAPTIVE_LIFECYCLE_BRAIN without changing native entry, sizing,
router, cost, same-pair, or native exit precedence semantics.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from spotbot.research.rd26_exit_architecture import (
    BASE_ROUND_TRIP_COST,
    INITIAL_EQUITY,
    LIQUIDITY_CAPACITY_FRACTION_24H,
    MAXIMUM_GROSS_EXPOSURE,
    MAXIMUM_POSITIONS,
    TARGET_SLOT_NOTIONAL_FRACTION,
    fast_lookup,
    performance_metrics,
)
from spotbot.research.rd27_adaptive_lifecycle import (
    RISK_OFF,
    apply_completed_bar_update,
    capital_admission_decision,
    evaluate_adaptive_exit,
    new_lifecycle_position,
)
from spotbot.research.rd27_lifecycle_replay import (
    FULL_ADAPTIVE_LIFECYCLE_BRAIN,
    ReplayPosition,
    build_state_lookup,
)

CANDIDATE_C = "C"
CANDIDATE_A = "A"
CANDIDATE_B = "B"
CANDIDATES = (CANDIDATE_C, CANDIDATE_A, CANDIDATE_B)

C_ID = "NO_STRUCTURAL_PROGRESS_AFTER_12_BARS_V1"
A_ID = "DONCHIAN_CLOSE_BREAK_10_V1"
B_ID = "POST_MEMORY_ATR_RATCHET_22_3_V1"

MAX_HOLD_HOURS = 168
ATR_PERIOD = 22
ATR_MULTIPLIER = 3.0
DONCHIAN_LOOKBACK = 10
C_BAR_LIMIT = 12


class ABCExecutionError(RuntimeError):
    pass


@dataclass
class CandidateState:
    entry_time: pd.Timestamp
    entry_price: float
    structural_high: float
    memory_seen: bool = False
    eligible_bar_count: int = 0
    b_active: bool = False
    b_hpeak: float | None = None
    b_stop: float | None = None
    b_memory_before_atr_ready: bool = False
    eligible_bars_seen: int = 0
    indicator_ready_bars_seen: int = 0


def _utc(v: Any) -> pd.Timestamp:
    x = pd.Timestamp(v)
    return x.tz_localize("UTC") if x.tzinfo is None else x.tz_convert("UTC")


def validate_candidate_id(candidate_id: str) -> None:
    if candidate_id not in CANDIDATES:
        raise ABCExecutionError(f"unknown candidate: {candidate_id}")


def normalize_hourly(raw: pd.DataFrame, *, cutoff: pd.Timestamp) -> pd.DataFrame:
    required = {"timestamp", "open", "high", "low", "close", "volume"}
    missing = sorted(required - set(raw.columns))
    if missing:
        raise ABCExecutionError(f"raw 1h missing columns: {missing}")
    f = raw.loc[:, ["timestamp", "open", "high", "low", "close", "volume"]].copy()
    f["timestamp"] = pd.to_datetime(f["timestamp"], utc=True, errors="raise")
    for col in ("open", "high", "low", "close", "volume"):
        f[col] = pd.to_numeric(f[col], errors="raise").astype(float)
    f = f.sort_values("timestamp", kind="stable").drop_duplicates("timestamp", keep="last").reset_index(drop=True)
    cutoff = _utc(cutoff)
    if len(f) and f["timestamp"].max() >= cutoff:
        raise ABCExecutionError(f"row at/beyond cutoff materialized: {f['timestamp'].max()} >= {cutoff}")
    if bool((f[["open", "high", "low", "close"]] <= 0).any().any()):
        raise ABCExecutionError("non-positive OHLC")
    return f


def build_four_hour_bars(raw: pd.DataFrame, *, cutoff: pd.Timestamp) -> pd.DataFrame:
    """Build exact completed UTC 4H bars and causal ATR22 / prior Donchian10."""
    f = normalize_hourly(raw, cutoff=cutoff).set_index("timestamp").sort_index()
    rows: list[dict[str, Any]] = []
    for start, g in f.groupby(f.index.floor("4h")):
        expected = pd.date_range(start, start + pd.Timedelta(hours=3), freq="h", tz="UTC")
        idx = pd.DatetimeIndex(g.index.unique()).sort_values()
        if len(idx) != 4 or not idx.equals(expected):
            continue
        rows.append(
            {
                "bar_open_time": pd.Timestamp(start),
                "bar_close_time": pd.Timestamp(start) + pd.Timedelta(hours=4),
                "open": float(g.iloc[0]["open"]),
                "high": float(g["high"].max()),
                "low": float(g["low"].min()),
                "close": float(g.iloc[-1]["close"]),
            }
        )
    if not rows:
        return pd.DataFrame(
            columns=[
                "bar_open_time", "bar_close_time", "open", "high", "low", "close",
                "atr22_wilder", "donchian10_prior_low",
            ]
        )
    b = pd.DataFrame.from_records(rows).sort_values("bar_open_time", kind="stable").reset_index(drop=True)
    b["atr22_wilder"] = np.nan
    b["donchian10_prior_low"] = np.nan

    # Contiguous segments only. A gap invalidates continuity; readiness is rebuilt causally.
    segment_start = 0
    n = len(b)
    while segment_start < n:
        segment_end = segment_start + 1
        while (
            segment_end < n
            and b.loc[segment_end, "bar_open_time"] - b.loc[segment_end - 1, "bar_open_time"]
            == pd.Timedelta(hours=4)
        ):
            segment_end += 1

        seg = b.iloc[segment_start:segment_end].copy()
        high = seg["high"].to_numpy(float)
        low = seg["low"].to_numpy(float)
        close = seg["close"].to_numpy(float)
        tr = np.empty(len(seg), dtype=float)
        for i in range(len(seg)):
            if i == 0:
                tr[i] = high[i] - low[i]
            else:
                tr[i] = max(
                    high[i] - low[i],
                    abs(high[i] - close[i - 1]),
                    abs(low[i] - close[i - 1]),
                )
        atr = np.full(len(seg), np.nan, dtype=float)
        if len(seg) >= ATR_PERIOD:
            atr[ATR_PERIOD - 1] = float(np.mean(tr[:ATR_PERIOD]))
            for i in range(ATR_PERIOD, len(seg)):
                atr[i] = ((ATR_PERIOD - 1) * atr[i - 1] + tr[i]) / ATR_PERIOD
        don = np.full(len(seg), np.nan, dtype=float)
        for i in range(DONCHIAN_LOOKBACK, len(seg)):
            don[i] = float(np.min(low[i - DONCHIAN_LOOKBACK:i]))

        b.loc[segment_start:segment_end - 1, "atr22_wilder"] = atr
        b.loc[segment_start:segment_end - 1, "donchian10_prior_low"] = don
        segment_start = segment_end

    return b


def four_hour_close_lookup(bars: pd.DataFrame) -> dict[int, pd.Series]:
    out: dict[int, pd.Series] = {}
    for _, row in bars.iterrows():
        out[int(_utc(row["bar_close_time"]).value)] = row
    return out


def new_candidate_state(entry_time: pd.Timestamp, entry_price: float) -> CandidateState:
    if not math.isfinite(entry_price) or entry_price <= 0:
        raise ABCExecutionError("invalid candidate entry price")
    return CandidateState(
        entry_time=_utc(entry_time),
        entry_price=float(entry_price),
        structural_high=float(entry_price),
    )


def evaluate_completed_4h(
    *,
    candidate_id: str,
    state: CandidateState,
    row: pd.Series,
) -> tuple[bool, str | None, str]:
    """Return (signal, reason, readiness_status). Mutates trade-specific candidate state."""
    validate_candidate_id(candidate_id)
    bar_open = _utc(row["bar_open_time"])
    if bar_open < state.entry_time:
        return False, None, "INELIGIBLE_PRE_ENTRY_OR_PARTIAL_ENTRY_BAR"

    state.eligible_bars_seen += 1
    previous_high = float(state.structural_high)
    close = float(row["close"])
    high = float(row["high"])
    memory_now = close > previous_high

    # Frozen ordering: memory first, then structural-high update, then C counter.
    state.memory_seen = bool(state.memory_seen or memory_now)
    state.structural_high = max(previous_high, high)
    state.eligible_bar_count += 1

    if candidate_id == CANDIDATE_C:
        state.indicator_ready_bars_seen += 1
        signal = state.eligible_bar_count == C_BAR_LIMIT and not state.memory_seen
        return signal, (C_ID if signal else None), "READY"

    if candidate_id == CANDIDATE_A:
        don = row.get("donchian10_prior_low")
        if pd.isna(don):
            return False, None, "NOT_READY_DONCHIAN10"
        state.indicator_ready_bars_seen += 1
        signal = close < float(don)
        return signal, (A_ID if signal else None), "READY"

    atr = row.get("atr22_wilder")
    if pd.isna(atr):
        if memory_now and not state.b_active:
            state.b_memory_before_atr_ready = True
        return False, None, "NOT_READY_ATR22"
    state.indicator_ready_bars_seen += 1
    atr = float(atr)

    if not state.b_active:
        if state.b_memory_before_atr_ready:
            return False, None, "UNEVALUABLE_MEMORY_OCCURRED_BEFORE_ATR_READY"
        if memory_now:
            state.b_active = True
            state.b_hpeak = max(state.entry_price, state.structural_high)
            state.b_stop = float(state.b_hpeak - ATR_MULTIPLIER * atr)
            return False, None, "READY_ACTIVATED_NO_EXIT"
        return False, None, "READY_PRE_MEMORY"

    if state.b_stop is None or state.b_hpeak is None:
        raise ABCExecutionError("B active without hpeak/stop")
    if close < state.b_stop:
        return True, B_ID, "READY"

    state.b_hpeak = max(float(state.b_hpeak), high)
    state.b_stop = max(float(state.b_stop), float(state.b_hpeak - ATR_MULTIPLIER * atr))
    return False, None, "READY"


def _state_at(lookup: dict[int, str], t: pd.Timestamp) -> str:
    v = lookup.get(int(_utc(t).value))
    if v is None:
        raise ABCExecutionError(f"market state unavailable at causal cutoff {t}")
    return v


def _bar_at(
    pair: str,
    timestamp: pd.Timestamp,
    frames: dict[str, pd.DataFrame],
    lookups: dict[str, dict[int, int]],
) -> pd.Series | None:
    frame = frames.get(pair)
    if frame is None:
        return None
    idx = lookups.get(pair, {}).get(int(_utc(timestamp).value))
    return None if idx is None else frame.iloc[idx]


def _marked_equity(cash: float, positions: dict[str, ReplayPosition]) -> tuple[float, float]:
    gross = sum(p.quantity * p.last_mark for p in positions.values())
    return cash + gross, gross


def _close_record(
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
    holding_hours = int((_utc(timestamp) - position.entry_time).total_seconds() / 3600.0)
    return {
        "policy_id": policy_id,
        "portfolio_id": portfolio_id,
        "universe_id": universe_id,
        "cost_multiplier": cost_multiplier,
        "pair": position.pair,
        "signal_time": position.signal_time,
        "entry_time": position.entry_time,
        "exit_time": _utc(timestamp),
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
    }, cash_credit


def replay_overlay(
    *,
    candidate_id: str | None,
    events: pd.DataFrame,
    frames: dict[str, pd.DataFrame],
    state_frame: pd.DataFrame,
    four_hour: dict[str, pd.DataFrame],
    replay_start: pd.Timestamp,
    replay_cutoff: pd.Timestamp,
    portfolio_id: str = "UNION_FOCUS",
    universe_id: str = "C2",
    cost_multiplier: float = 1.0,
    external_signal_schedule: dict[str, set[tuple[int, int]]] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any], dict[str, int], pd.DataFrame]:
    """Full portfolio replay. candidate_id=None must parity-match native FULL_ADAPTIVE_LIFECYCLE_BRAIN."""
    if candidate_id is not None:
        if external_signal_schedule is None:
            validate_candidate_id(candidate_id)
        elif candidate_id not in {
            "H1_WATCH_STALLED",
            "H2_WATCH_DAMAGE_ACTIVE",
            "H3_PROTECT_DAMAGE_ONSET",
            "H4_PROTECT_DAMAGE_CONTINUATION",
            "H5_EXIT_CONFLUENT_DAMAGE",
            "H6_DEESCALATE_DAMAGE_CLEAR",
            "R1_CONFIRMED_STRUCTURAL_BREAK_ONLY",
            "R2_CONFIRMED_VOLATILITY_DAMAGE_ONLY",
            "R3_CONFIRMED_CONFLUENT_DAMAGE",
            "R4_EARLY_PROGRESS_STRUCTURAL_BREAK",
            "R5_UNCONFIRMED_STALLED_STRUCTURAL_BREAK",
            "R6_UNCONFIRMED_STRUCTURAL_BREAK_NO_STALL",
            "R7_CONFIRMED_ONSET_STRUCTURAL_BREAK_ONLY",
            "R8_CONFIRMED_ONSET_WITH_VOLATILITY_DAMAGE",
            "R9_CONFIRMED_CONTINUATION_STRUCTURAL_BREAK_ONLY",
            "R10_CONFIRMED_CONTINUATION_WITH_VOLATILITY_DAMAGE",
            "EB1_CAUSAL_TECH_LINEAR_EDGE",
        }:
            raise ABCExecutionError(f"unsupported external hypothesis id: {candidate_id}")
    elif external_signal_schedule is not None:
        raise ABCExecutionError("external_signal_schedule requires candidate_id")

    if external_signal_schedule is not None:
        for _pair, _keys in external_signal_schedule.items():
            if not isinstance(_pair, str) or not isinstance(_keys, (set, frozenset)):
                raise ABCExecutionError("external_signal_schedule malformed")
            for _key in _keys:
                if (
                    not isinstance(_key, tuple)
                    or len(_key) != 2
                    or not all(isinstance(_v, int) for _v in _key)
                ):
                    raise ABCExecutionError("external_signal_schedule key malformed")
    replay_start, replay_cutoff = _utc(replay_start), _utc(replay_cutoff)
    lookups = {p: fast_lookup(f) for p, f in frames.items()}
    state_lookup = build_state_lookup(state_frame)
    h4_lookup = {p: four_hour_close_lookup(b) for p, b in four_hour.items()}
    side_cost = BASE_ROUND_TRIP_COST * cost_multiplier / 2.0

    scheduled: dict[int, list[dict[str, Any]]] = {}
    for raw in events.to_dict(orient="records"):
        signal_time = _utc(raw["timestamp"])
        entry_time = signal_time + pd.Timedelta(hours=1)
        max_exit_time = entry_time + pd.Timedelta(hours=MAX_HOLD_HOURS)
        if entry_time < replay_start or not (max_exit_time < replay_cutoff):
            continue
        scheduled.setdefault(int(entry_time.value), []).append(
            {**raw, "signal_time": signal_time, "entry_time": entry_time, "max_exit_time": max_exit_time}
        )

    policy_id = FULL_ADAPTIVE_LIFECYCLE_BRAIN if candidate_id is None else f"{FULL_ADAPTIVE_LIFECYCLE_BRAIN}__ABC_{candidate_id}"
    cash = INITIAL_EQUITY
    positions: dict[str, ReplayPosition] = {}
    cstates: dict[str, CandidateState] = {}
    pending: dict[str, dict[str, Any]] = {}
    trades: list[dict[str, Any]] = []
    daily_rows: list[dict[str, Any]] = []
    intervention_rows: list[dict[str, Any]] = []
    hourly_equity: list[float] = []
    pending_native_updates: dict[str, Any] = {}
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
        "adaptive_stagnation_exits": 0,
        "adaptive_protection_gap_exits": 0,
        "adaptive_protection_touch_exits": 0,
        "candidate_signals": 0,
        "candidate_executed": 0,
        "candidate_native_preempted": 0,
        "candidate_native_tie_priority": 0,
        "candidate_not_ready_observations": 0,
        "candidate_unevaluable_memory_before_atr": 0,
    }

    for timestamp in pd.date_range(replay_start, replay_cutoff, freq="h", inclusive="left"):
        timestamp = _utc(timestamp)
        pending_native_updates.clear()

        # Native exits always get first priority.
        for pair in sorted(list(positions)):
            position = positions[pair]
            bar = _bar_at(pair, timestamp, frames, lookups)
            prior = _bar_at(pair, timestamp - pd.Timedelta(hours=1), frames, lookups)
            if bar is None or prior is None:
                raise ABCExecutionError(f"open-position hourly data missing: {pair} {timestamp}")
            current_state = _state_at(state_lookup, timestamp - pd.Timedelta(hours=1))
            decision = evaluate_adaptive_exit(
                position.lifecycle,
                current_open_time=timestamp,
                current_open=float(bar["open"]),
                current_low=float(bar["low"]),
                prior_asset_close=float(prior["close"]),
                market_state=current_state,
            )
            if decision.should_exit:
                if decision.exit_price is None or decision.exit_reason is None:
                    raise ABCExecutionError("native exit missing fill")
                if pair in pending:
                    sched = _utc(pending[pair]["execution_time"])
                    if timestamp < sched:
                        counters["candidate_native_preempted"] += 1
                        why = "NATIVE_PREEMPTED"
                    elif timestamp == sched:
                        counters["candidate_native_tie_priority"] += 1
                        why = "NATIVE_TIE_PRIORITY"
                    else:
                        why = "NATIVE_AFTER_CANDIDATE_SCHEDULE_BUG"
                    intervention_rows.append(
                        {
                            "candidate_id": candidate_id,
                            "pair": pair,
                            "entry_time": position.entry_time,
                            "candidate_signal_time": pending[pair]["signal_time"],
                            "candidate_scheduled_execution_time": sched,
                            "candidate_executable": False,
                            "candidate_executed": False,
                            "native_preempted": True,
                            "preemption_reason": why,
                            "native_exit_time": timestamp,
                        }
                    )
                    pending.pop(pair, None)
                reason = str(decision.exit_reason)
                if reason == "MAX_HOLD_168H": counters["max_hold_exits"] += 1
                elif reason == "ADAPTIVE_PROTECTION_GAP": counters["adaptive_protection_gap_exits"] += 1
                elif reason == "ADAPTIVE_PROTECTION_TOUCH": counters["adaptive_protection_touch_exits"] += 1
                elif reason.startswith("ADAPTIVE_STAGNATION_"): counters["adaptive_stagnation_exits"] += 1
                record, credit = _close_record(
                    position=position, timestamp=timestamp, exit_price=float(decision.exit_price),
                    exit_reason=reason, exit_market_state=current_state, side_cost=side_cost,
                    policy_id=policy_id, portfolio_id=portfolio_id, universe_id=universe_id,
                    cost_multiplier=cost_multiplier,
                )
                cash += credit
                trades.append(record)
                positions.pop(pair, None)
                cstates.pop(pair, None)
                pending_native_updates.pop(pair, None)
                continue
            pending_native_updates[pair] = decision

        # Candidate fills occur after native precedence at the same hourly open.
        if candidate_id is not None:
            for pair in sorted(list(positions)):
                pnd = pending.get(pair)
                if pnd is None or _utc(pnd["execution_time"]) != timestamp:
                    continue
                position = positions[pair]
                bar = _bar_at(pair, timestamp, frames, lookups)
                if bar is None:
                    intervention_rows.append(
                        {
                            "candidate_id": candidate_id, "pair": pair, "entry_time": position.entry_time,
                            "candidate_signal_time": pnd["signal_time"],
                            "candidate_scheduled_execution_time": timestamp,
                            "candidate_executable": False, "candidate_executed": False,
                            "native_preempted": False, "preemption_reason": "NO_VALID_EXECUTION_PRICE",
                            "native_exit_time": None,
                        }
                    )
                    pending.pop(pair, None)
                    continue
                current_state = _state_at(state_lookup, timestamp - pd.Timedelta(hours=1))
                record, credit = _close_record(
                    position=position, timestamp=timestamp, exit_price=float(bar["open"]),
                    exit_reason=f"ABC_{candidate_id}_CANDIDATE_EXIT", exit_market_state=current_state,
                    side_cost=side_cost, policy_id=policy_id, portfolio_id=portfolio_id,
                    universe_id=universe_id, cost_multiplier=cost_multiplier,
                )
                cash += credit
                trades.append(record)
                counters["candidate_executed"] += 1
                intervention_rows.append(
                    {
                        "candidate_id": candidate_id, "pair": pair, "entry_time": position.entry_time,
                        "candidate_signal_time": pnd["signal_time"],
                        "candidate_scheduled_execution_time": timestamp,
                        "candidate_executable": True, "candidate_executed": True,
                        "native_preempted": False, "preemption_reason": None,
                        "native_exit_time": None,
                    }
                )
                positions.pop(pair, None)
                cstates.pop(pair, None)
                pending.pop(pair, None)
                pending_native_updates.pop(pair, None)

        for pair, position in positions.items():
            bar = _bar_at(pair, timestamp, frames, lookups)
            if bar is not None:
                position.last_mark = float(bar["open"])

        # Native entries, unchanged.
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
            signal_time = _utc(item["signal_time"])
            entry_state = _state_at(state_lookup, signal_time)
            admission = capital_admission_decision(entry_state)
            if not admission.admit_position:
                if entry_state != RISK_OFF:
                    raise ABCExecutionError("unexpected non-RISK_OFF suppression")
                counters["risk_off_suppressed_entries"] += 1
                continue

            entry_bar = _bar_at(pair, timestamp, frames, lookups)
            exit_bar = _bar_at(pair, _utc(item["max_exit_time"]), frames, lookups)
            signal_bar = _bar_at(pair, signal_time, frames, lookups)
            if entry_bar is None:
                counters["missing_entry_bar"] += 1
                continue
            if exit_bar is None:
                counters["missing_exit_bar_precheck"] += 1
                continue
            if signal_bar is None:
                raise ABCExecutionError("signal bar missing during admission")
            capacity_source = float(signal_bar["trailing_24h_quote_turnover_proxy"])
            if not math.isfinite(capacity_source) or capacity_source <= 0:
                counters["capacity_unavailable"] += 1
                continue

            equity_open, gross_open = _marked_equity(cash, positions)
            gross_room = max(
                0.0,
                (equity_open * MAXIMUM_GROSS_EXPOSURE - gross_open)
                / (1.0 + MAXIMUM_GROSS_EXPOSURE * side_cost),
            )
            if gross_room <= 0:
                counters["gross_limit_rejection"] += 1
                continue
            target_notional = equity_open * float(admission.target_slot_fraction)
            capacity_notional = capacity_source * LIQUIDITY_CAPACITY_FRACTION_24H
            notional = min(target_notional, gross_room, capacity_notional)
            if notional < target_notional - 1e-9 and capacity_notional <= min(target_notional, gross_room):
                counters["capacity_capped_entries"] += 1
            max_cash_notional = cash / (1.0 + side_cost)
            if max_cash_notional <= 0:
                continue
            if notional > max_cash_notional:
                counters["cash_capped_entries"] += 1
                notional = max_cash_notional
            if notional <= 0:
                continue

            entry_price = float(entry_bar["open"])
            quantity = notional / entry_price
            entry_cost = notional * side_cost
            cash -= notional + entry_cost
            if cash < -1e-7:
                raise ABCExecutionError("negative cash after entry")
            cash = max(cash, 0.0)
            support = tuple(sorted(x for x in str(item["support_families"]).split("|") if x))
            atr_signal = float(item["atr24_at_signal"])
            lifecycle = new_lifecycle_position(
                pair=pair, entry_time=timestamp, entry_price=entry_price, atr24_at_signal=atr_signal
            )
            position = ReplayPosition(
                pair=pair, signal_time=signal_time, entry_time=timestamp,
                max_exit_time=_utc(item["max_exit_time"]), entry_price=entry_price,
                quantity=quantity, entry_notional=notional, entry_cost=entry_cost,
                membership_rank=int(item["membership_rank"]), support_families=support,
                period_id=str(item["period_id"]), atr24_at_signal=atr_signal,
                lifecycle=lifecycle, entry_market_state=entry_state, last_mark=entry_price,
            )
            positions[pair] = position
            if candidate_id is not None:
                cstates[pair] = new_candidate_state(timestamp, entry_price)
            counters["admitted_entries"] += 1

            prior = _bar_at(pair, timestamp - pd.Timedelta(hours=1), frames, lookups)
            if prior is None:
                raise ABCExecutionError("entry-bar prior close missing")
            decision = evaluate_adaptive_exit(
                lifecycle, current_open_time=timestamp, current_open=entry_price,
                current_low=float(entry_bar["low"]), prior_asset_close=float(prior["close"]),
                market_state=entry_state,
            )
            if decision.should_exit:
                if decision.exit_price is None or decision.exit_reason is None:
                    raise ABCExecutionError("native entry-bar exit missing fill")
                counters["entry_bar_adaptive_exits"] += 1
                reason = str(decision.exit_reason)
                if reason == "MAX_HOLD_168H": counters["max_hold_exits"] += 1
                elif reason == "ADAPTIVE_PROTECTION_GAP": counters["adaptive_protection_gap_exits"] += 1
                elif reason == "ADAPTIVE_PROTECTION_TOUCH": counters["adaptive_protection_touch_exits"] += 1
                elif reason.startswith("ADAPTIVE_STAGNATION_"): counters["adaptive_stagnation_exits"] += 1
                record, credit = _close_record(
                    position=position, timestamp=timestamp, exit_price=float(decision.exit_price),
                    exit_reason=reason, exit_market_state=entry_state, side_cost=side_cost,
                    policy_id=policy_id, portfolio_id=portfolio_id, universe_id=universe_id,
                    cost_multiplier=cost_multiplier,
                )
                cash += credit
                trades.append(record)
                positions.pop(pair, None)
                cstates.pop(pair, None)
            else:
                pending_native_updates[pair] = decision

        # Native completed-hour update.
        for pair, position in positions.items():
            bar = _bar_at(pair, timestamp, frames, lookups)
            if bar is None:
                raise ABCExecutionError(f"position mark missing {pair} {timestamp}")
            decision = pending_native_updates.get(pair)
            if decision is None:
                raise ABCExecutionError(f"native survivor missing decision {pair} {timestamp}")
            position.lifecycle = apply_completed_bar_update(
                position.lifecycle, decision=decision, completed_high=float(bar["high"])
            )
            position.last_mark = float(bar["close"])

        # Candidate observes completed 4H bar at its close. Fill is first 1H open strictly after close.
        if candidate_id is not None:
            decision_time = timestamp + pd.Timedelta(hours=1)
            if decision_time.hour % 4 == 0:
                for pair in sorted(list(positions)):
                    if pair in pending:
                        continue
                    row = h4_lookup.get(pair, {}).get(int(decision_time.value))
                    if row is None:
                        continue
                    st = cstates[pair]
                    if external_signal_schedule is None:
                        signal, reason, readiness = evaluate_completed_4h(
                            candidate_id=candidate_id, state=st, row=row
                        )
                        if readiness.startswith("NOT_READY"):
                            counters["candidate_not_ready_observations"] += 1
                        if readiness == "UNEVALUABLE_MEMORY_OCCURRED_BEFORE_ATR_READY":
                            counters["candidate_unevaluable_memory_before_atr"] += 1
                    else:
                        lifecycle_key = (
                            int(_utc(positions[pair].entry_time).value),
                            int(decision_time.value),
                        )
                        signal = lifecycle_key in external_signal_schedule.get(pair, set())
                        reason = (
                            "EXTERNAL_STATE_CONDITIONED_HYPOTHESIS_SIGNAL"
                            if signal else None
                        )
                        readiness = "EXTERNAL_SCHEDULE"
                    if signal:
                        counters["candidate_signals"] += 1
                        pending[pair] = {
                            "signal_time": decision_time,
                            "execution_time": decision_time + pd.Timedelta(hours=1),
                            "reason": reason,
                        }

        equity_close, gross_close = _marked_equity(cash, positions)
        if equity_close < -1e-7:
            raise ABCExecutionError("negative equity")
        hourly_equity.append(equity_close)
        if timestamp.hour == 23:
            daily_rows.append(
                {
                    "policy_id": policy_id, "portfolio_id": portfolio_id,
                    "universe_id": universe_id, "cost_multiplier": cost_multiplier,
                    "timestamp": timestamp, "equity": equity_close, "cash": cash,
                    "gross_exposure": gross_close,
                    "gross_exposure_fraction": gross_close / equity_close if equity_close > 0 else math.nan,
                    "open_positions": len(positions),
                }
            )

    if positions:
        raise ABCExecutionError("open positions remained at annual cutoff")

    trade_frame = pd.DataFrame.from_records(trades)
    daily_frame = pd.DataFrame.from_records(daily_rows)
    intervention_frame = pd.DataFrame.from_records(intervention_rows)
    eq = np.asarray(hourly_equity, dtype=float)
    peaks = np.maximum.accumulate(eq)
    dd = np.divide(peaks - eq, peaks, out=np.zeros_like(eq), where=peaks > 0)
    final_equity = float(eq[-1]) if len(eq) else INITIAL_EQUITY
    metrics = performance_metrics(
        trade_frame=trade_frame, final_equity=final_equity,
        maximum_drawdown=float(dd.max()) if len(dd) else 0.0,
    )
    metrics.update(
        {
            "policy_id": policy_id, "portfolio_id": portfolio_id,
            "universe_id": universe_id, "cost_multiplier": cost_multiplier,
            "minimum_cash": float(daily_frame["cash"].min()) if len(daily_frame) else INITIAL_EQUITY,
        }
    )
    return trade_frame, daily_frame, metrics, counters, intervention_frame


def _candidate_direct_for_trade(
    *,
    candidate_id: str,
    trade: pd.Series,
    hourly: pd.DataFrame,
    h4: pd.DataFrame,
    side_cost: float,
) -> dict[str, Any]:
    validate_candidate_id(candidate_id)
    entry_time = _utc(trade["entry_time"])
    native_exit = _utc(trade["exit_time"])
    entry_price = float(trade["entry_price"])
    state = new_candidate_state(entry_time, entry_price)
    rows = h4.loc[
        (pd.to_datetime(h4["bar_open_time"], utc=True) >= entry_time)
        & (pd.to_datetime(h4["bar_close_time"], utc=True) <= native_exit)
    ]
    candidate_signal_time = None
    scheduled = None
    readiness_seen = 0
    unavailable_seen = 0
    for _, row in rows.iterrows():
        signal, _reason, readiness = evaluate_completed_4h(candidate_id=candidate_id, state=state, row=row)
        if readiness.startswith("READY"):
            readiness_seen += 1
        elif readiness.startswith("NOT_READY"):
            unavailable_seen += 1
        if signal:
            candidate_signal_time = _utc(row["bar_close_time"])
            scheduled = candidate_signal_time + pd.Timedelta(hours=1)
            break

    executable = False
    executed = False
    preempted = False
    preemption_reason = None
    modified_exit_time = native_exit
    modified_exit_price = float(trade["exit_price"])

    if scheduled is not None:
        if native_exit < scheduled:
            preempted = True
            preemption_reason = "NATIVE_PREEMPTED"
        elif native_exit == scheduled:
            preempted = True
            preemption_reason = "NATIVE_TIE_PRIORITY"
        else:
            hour = hourly.loc[pd.to_datetime(hourly["timestamp"], utc=True) == scheduled]
            if len(hour) != 1:
                preemption_reason = "NO_VALID_EXECUTION_PRICE"
            else:
                executable = True
                executed = True
                modified_exit_time = scheduled
                modified_exit_price = float(hour.iloc[0]["open"])

    quantity = float(trade["quantity"])
    entry_notional = float(trade["entry_notional"])
    entry_cost = float(trade["entry_cost"])
    modified_exit_notional = quantity * modified_exit_price
    modified_exit_cost = modified_exit_notional * side_cost
    modified_net_pnl = modified_exit_notional - entry_notional - entry_cost - modified_exit_cost
    control_net_pnl = float(trade["net_pnl"])
    delta = modified_net_pnl - control_net_pnl

    return {
        "candidate_id": candidate_id,
        "pair": str(trade["pair"]),
        "entry_time": entry_time,
        "control_exit_time": native_exit,
        "control_exit_reason": str(trade["exit_reason"]),
        "candidate_signal_time": candidate_signal_time,
        "candidate_scheduled_execution_time": scheduled,
        "candidate_executable": executable,
        "candidate_executed": executed,
        "native_preempted": preempted,
        "preemption_reason": preemption_reason,
        "modified_exit_time": modified_exit_time,
        "modified_exit_price": modified_exit_price,
        "control_net_pnl": control_net_pnl,
        "modified_net_pnl": modified_net_pnl,
        "direct_effect_delta_pnl": delta,
        "lead_hours_vs_native": (
            (native_exit - modified_exit_time).total_seconds() / 3600.0 if executed else 0.0
        ),
        "eligible_4h_bars_seen": state.eligible_bars_seen,
        "indicator_ready_bars_seen": state.indicator_ready_bars_seen,
        "not_ready_observations": unavailable_seen,
        "evaluable_lifecycle": bool(state.eligible_bars_seen > 0 and (candidate_id == CANDIDATE_C or readiness_seen > 0)),
        "b_memory_before_atr_ready": bool(state.b_memory_before_atr_ready),
    }


def direct_effect(
    *,
    candidate_id: str,
    control_trades: pd.DataFrame,
    hourly_by_pair: dict[str, pd.DataFrame],
    four_hour_by_pair: dict[str, pd.DataFrame],
    cost_multiplier: float = 1.0,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    side_cost = BASE_ROUND_TRIP_COST * cost_multiplier / 2.0
    rows = []
    for _, trade in control_trades.iterrows():
        pair = str(trade["pair"])
        if pair not in hourly_by_pair or pair not in four_hour_by_pair:
            raise ABCExecutionError(f"direct-effect market source missing for {pair}")
        rows.append(
            _candidate_direct_for_trade(
                candidate_id=candidate_id, trade=trade,
                hourly=hourly_by_pair[pair], h4=four_hour_by_pair[pair], side_cost=side_cost,
            )
        )
    frame = pd.DataFrame.from_records(rows)
    summary = {
        "direct_effect": float(frame["direct_effect_delta_pnl"].sum()) if len(frame) else 0.0,
        "control_lifecycle_count": len(frame),
        "evaluable_lifecycle_count": int(frame["evaluable_lifecycle"].sum()) if len(frame) else 0,
        "candidate_signal_count": int(frame["candidate_signal_time"].notna().sum()) if len(frame) else 0,
        "executed_intervention_count": int(frame["candidate_executed"].sum()) if len(frame) else 0,
        "native_preempted_count": int(frame["native_preempted"].sum()) if len(frame) else 0,
        "mean_lead_hours_executed": (
            float(frame.loc[frame["candidate_executed"], "lead_hours_vs_native"].mean())
            if len(frame) and bool(frame["candidate_executed"].any()) else 0.0
        ),
    }
    return frame, summary


def parity_compare(
    native_trades: pd.DataFrame,
    native_metrics: dict[str, Any],
    overlay_trades: pd.DataFrame,
    overlay_metrics: dict[str, Any],
) -> dict[str, Any]:
    metric_fields = [
        "trade_count", "final_equity", "net_return", "net_pnl", "profit_factor",
        "win_rate", "maximum_drawdown", "turnover", "mean_holding_hours", "minimum_cash",
    ]
    diffs = []
    for k in metric_fields:
        a, b = native_metrics.get(k), overlay_metrics.get(k)
        if isinstance(a, (int, np.integer)) and isinstance(b, (int, np.integer)):
            ok = int(a) == int(b)
        else:
            ok = bool(np.isclose(float(a), float(b), rtol=1e-11, atol=1e-8, equal_nan=True))
        if not ok:
            diffs.append({"field": k, "native": a, "overlay": b})

    core = [
        "pair", "entry_time", "exit_time", "exit_reason", "entry_price", "exit_price",
        "quantity", "entry_notional", "entry_cost", "exit_cost", "net_pnl",
        "entry_market_state", "exit_market_state",
    ]
    if len(native_trades) != len(overlay_trades):
        diffs.append({"field": "trade_row_count", "native": len(native_trades), "overlay": len(overlay_trades)})
    else:
        n = native_trades.reset_index(drop=True)
        o = overlay_trades.reset_index(drop=True)
        for col in core:
            if col not in n.columns or col not in o.columns:
                diffs.append({"field": f"missing_column:{col}"})
                continue
            if col in {"entry_price","exit_price","quantity","entry_notional","entry_cost","exit_cost","net_pnl"}:
                if not np.allclose(
                    pd.to_numeric(n[col], errors="raise"),
                    pd.to_numeric(o[col], errors="raise"),
                    rtol=1e-11, atol=1e-8, equal_nan=True,
                ):
                    diffs.append({"field": f"trade_numeric:{col}"})
            else:
                if not np.array_equal(n[col].astype(str).to_numpy(), o[col].astype(str).to_numpy()):
                    diffs.append({"field": f"trade_exact:{col}"})
    return {"pass": not diffs, "difference_count": len(diffs), "differences": diffs[:100]}


def concentration_review(direct_rows: pd.DataFrame) -> dict[str, Any]:
    if direct_rows.empty:
        return {}
    executed = direct_rows.loc[direct_rows["candidate_executed"]].copy()
    if executed.empty:
        return {"executed_count": 0}
    pnl = pd.to_numeric(executed["direct_effect_delta_pnl"], errors="raise").astype(float)
    by_pair = executed.assign(_delta=pnl).groupby("pair", sort=True)["_delta"].sum().sort_values(ascending=False)
    months = pd.to_datetime(executed["modified_exit_time"], utc=True).dt.to_period("M").astype(str)
    by_month = executed.assign(_delta=pnl, _month=months).groupby("_month", sort=True)["_delta"].sum()
    return {
        "executed_count": len(executed),
        "top_pair_delta_pnl": by_pair.head(5).to_dict(),
        "bottom_pair_delta_pnl": by_pair.tail(5).to_dict(),
        "monthly_delta_pnl": by_month.to_dict(),
    }
