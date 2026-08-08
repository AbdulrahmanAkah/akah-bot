"""RD28 frozen portfolio replay adapter for evidence-gated lifecycle candidates."""

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
    FOCUS_FAMILIES,
    INITIAL_EQUITY,
    LIQUIDITY_CAPACITY_FRACTION_24H,
    MAXIMUM_GROSS_EXPOSURE,
    MAXIMUM_POSITIONS,
    fast_lookup,
    performance_metrics,
)
from spotbot.research.rd27_adaptive_lifecycle import MARKET_STATES, RISK_OFF
from spotbot.research.rd27_lifecycle_replay import (
    STATIC_EXIT_STATE_ROUTER,
    build_state_lookup,
)
from spotbot.research.rd27_lifecycle_replay import (
    replay_lifecycle_policy as rd27_replay_lifecycle_policy,
)
from spotbot.research.rd28_evidence_gated_lifecycle import (
    BACKUP_TIME_FAIL_REASON,
    EARLY_EVIDENCE_REASON,
    FAMILY_MB_EVIDENCE_REASON,
    FAMILY_RS_EVIDENCE_REASON,
    MAX_HOLD_REASON,
    POLICIES,
    PROFIT_GIVEBACK_REASON,
    ROUTER_TIME_FAIL_72_CONTROL,
    EscrowSlot,
    EvidenceExitDecision,
    EvidencePosition,
    active_component_count,
    active_escrow_slots,
    apply_completed_asset_bar,
    escrow_slot_for_exit,
    evaluate_evidence_exit,
    new_evidence_position,
    policy_components,
    router_admission,
    slot_capacity_available,
    uses_evidence_exit,
)

SCHEMA_VERSION: Final = "rd28-lifecycle-portfolio-replay-v1"
FAMILY_OVERLAP_RULE: Final = "ALL_SUPPORTING_FAMILIES_MUST_INVALIDATE"
FAMILY_OVERLAP_EXIT_REASON: Final = "FAMILY_AWARE_ALL_SUPPORTING_FAMILIES_INVALIDATED"


class RD28ReplayError(RuntimeError):
    """Raised when frozen RD28 portfolio replay semantics are violated."""


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
    evidence: EvidencePosition
    entry_market_state: str
    last_mark: float


def validate_replay_constants() -> None:
    if MAXIMUM_POSITIONS != 5:
        raise RD28ReplayError("maximum-position contract drifted")
    if not math.isclose(MAXIMUM_GROSS_EXPOSURE, 0.90):
        raise RD28ReplayError("gross-exposure contract drifted")
    if not math.isclose(LIQUIDITY_CAPACITY_FRACTION_24H, 0.005):
        raise RD28ReplayError("capacity contract drifted")
    if COST_MULTIPLIERS != (1.0, 2.0):
        raise RD28ReplayError("cost matrix drifted")
    if FAMILY_OVERLAP_RULE != "ALL_SUPPORTING_FAMILIES_MUST_INVALIDATE":
        raise RD28ReplayError("family-overlap integration rule drifted")


def _utc_timestamp(value: Any) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    return timestamp.tz_localize("UTC") if timestamp.tzinfo is None else timestamp.tz_convert("UTC")


def _state_at(lookup: dict[int, str], timestamp: pd.Timestamp) -> str:
    value = lookup.get(int(_utc_timestamp(timestamp).value))
    if value is None:
        raise RD28ReplayError(f"market state unavailable at causal cutoff: {timestamp}")
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
    index = lookups.get(pair, {}).get(int(_utc_timestamp(timestamp).value))
    return None if index is None else frame.iloc[index]


def _support_families(value: Any) -> tuple[str, ...]:
    families = tuple(sorted({family for family in str(value).split("|") if family}))
    if not families:
        raise RD28ReplayError("signal has no support family")
    invalid = sorted(set(families).difference(FOCUS_FAMILIES))
    if invalid:
        raise RD28ReplayError(f"unknown support families: {invalid}")
    return families


def _marked_equity(*, cash: float, positions: dict[str, ReplayPosition]) -> tuple[float, float]:
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
    return (
        {
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
            "high_water_at_exit": position.evidence.high_water_prior,
            "entry_market_state": position.entry_market_state,
            "exit_market_state": exit_market_state,
        },
        cash_credit,
    )


def _decision_for_family(
    position: ReplayPosition,
    *,
    signal_family: str,
    current_open_time: pd.Timestamp,
    current_open: float,
    prior_asset_close: float,
    current_market_state: str,
) -> EvidenceExitDecision:
    evidence = replace(position.evidence, signal_family=signal_family)
    return evaluate_evidence_exit(
        evidence,
        current_open_time=current_open_time,
        current_open=current_open,
        prior_asset_close=prior_asset_close,
        current_market_state=current_market_state,
        family_aware=True,
    )


def family_aware_exit_decision(
    position: ReplayPosition,
    *,
    current_open_time: pd.Timestamp,
    current_open: float,
    prior_asset_close: float,
    current_market_state: str,
) -> EvidenceExitDecision:
    """For multi-family UNION support, every supporting entry thesis must invalidate."""
    decisions = [
        _decision_for_family(
            position,
            signal_family=family,
            current_open_time=current_open_time,
            current_open=current_open,
            prior_asset_close=prior_asset_close,
            current_market_state=current_market_state,
        )
        for family in position.support_families
    ]
    if not decisions:
        raise RD28ReplayError("family-aware position has no support family")
    common = (MAX_HOLD_REASON, PROFIT_GIVEBACK_REASON, BACKUP_TIME_FAIL_REASON)
    for reason in common:
        hits = [decision for decision in decisions if decision.exit_reason == reason]
        if hits:
            if len(hits) != len(decisions):
                raise RD28ReplayError(f"common exit reason diverged across families: {reason}")
            return hits[0]
    early = {FAMILY_MB_EVIDENCE_REASON, FAMILY_RS_EVIDENCE_REASON}
    if all(decision.should_exit and decision.exit_reason in early for decision in decisions):
        return replace(decisions[0], exit_reason=FAMILY_OVERLAP_EXIT_REASON)
    return replace(decisions[0], should_exit=False, exit_price=None, exit_reason=None)


def _generic_exit_decision(
    position: ReplayPosition,
    *,
    current_open_time: pd.Timestamp,
    current_open: float,
    prior_asset_close: float,
    current_market_state: str,
) -> EvidenceExitDecision:
    evidence = replace(position.evidence, signal_family=position.support_families[0])
    return evaluate_evidence_exit(
        evidence,
        current_open_time=current_open_time,
        current_open=current_open,
        prior_asset_close=prior_asset_close,
        current_market_state=current_market_state,
        family_aware=False,
    )


def replay_rd28_policy(
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
    validate_replay_constants()
    if policy_id not in POLICIES:
        raise RD28ReplayError(f"unknown policy: {policy_id}")
    if cost_multiplier not in COST_MULTIPLIERS:
        raise RD28ReplayError("unsupported cost multiplier")
    if policy_id == ROUTER_TIME_FAIL_72_CONTROL:
        return rd27_replay_lifecycle_policy(
            policy_id=STATIC_EXIT_STATE_ROUTER,
            portfolio_id=portfolio_id,
            universe_id=universe_id,
            cost_multiplier=cost_multiplier,
            events=events,
            frames=frames,
            state_frame=state_frame,
            replay_start=replay_start,
            replay_cutoff=replay_cutoff,
        )

    family_aware, slot_escrow_enabled = policy_components(policy_id)
    if not uses_evidence_exit(policy_id):
        raise RD28ReplayError("non-control policy must use evidence exit")
    replay_start = _utc_timestamp(replay_start)
    replay_cutoff = _utc_timestamp(replay_cutoff)
    if replay_start >= replay_cutoff:
        raise RD28ReplayError("invalid replay window")

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
    escrows: list[EscrowSlot] = []
    trades: list[dict[str, Any]] = []
    daily_rows: list[dict[str, Any]] = []
    hourly_equity_values: list[float] = []
    counters: dict[str, int] = {
        "signal_events": len(events),
        "missing_entry_bar": 0,
        "missing_exit_bar_precheck": 0,
        "same_pair_open": 0,
        "position_slots_full": 0,
        "escrow_slot_rejections": 0,
        "gross_limit_rejection": 0,
        "capacity_unavailable": 0,
        "capacity_capped_entries": 0,
        "cash_capped_entries": 0,
        "admitted_entries": 0,
        "risk_off_suppressed_entries": 0,
        "evidence_regime_trade_exits": 0,
        "family_mb_evidence_exits": 0,
        "family_rs_evidence_exits": 0,
        "family_overlap_all_invalidated_exits": 0,
        "profit_giveback_exits": 0,
        "time_failure_exits": 0,
        "max_hold_exits": 0,
        "escrow_slots_created": 0,
        "escrow_slots_released": 0,
        "max_active_escrow_slots": 0,
    }
    for state in MARKET_STATES:
        counters[f"entry_state_{state}"] = 0

    for timestamp in pd.date_range(replay_start, replay_cutoff, freq="h", inclusive="left"):
        before = len(escrows)
        escrows = list(active_escrow_slots(escrows, current_time=timestamp))
        counters["escrow_slots_released"] += before - len(escrows)

        for pair in sorted(list(positions)):
            position = positions[pair]
            bar = _bar_at(pair, timestamp, frames, lookups)
            prior_bar = _bar_at(pair, timestamp - pd.Timedelta(hours=1), frames, lookups)
            if bar is None or prior_bar is None:
                raise RD28ReplayError(f"open-position bar missing: {pair} {timestamp}")
            current_state = _state_at(state_lookup, timestamp - pd.Timedelta(hours=1))
            if family_aware:
                decision = family_aware_exit_decision(
                    position,
                    current_open_time=timestamp,
                    current_open=float(bar["open"]),
                    prior_asset_close=float(prior_bar["close"]),
                    current_market_state=current_state,
                )
            else:
                decision = _generic_exit_decision(
                    position,
                    current_open_time=timestamp,
                    current_open=float(bar["open"]),
                    prior_asset_close=float(prior_bar["close"]),
                    current_market_state=current_state,
                )
            if decision.should_exit:
                if decision.exit_price is None or decision.exit_reason is None:
                    raise RD28ReplayError("exit missing fill details")
                reason = decision.exit_reason
                counter_by_reason = {
                    EARLY_EVIDENCE_REASON: "evidence_regime_trade_exits",
                    FAMILY_MB_EVIDENCE_REASON: "family_mb_evidence_exits",
                    FAMILY_RS_EVIDENCE_REASON: "family_rs_evidence_exits",
                    FAMILY_OVERLAP_EXIT_REASON: "family_overlap_all_invalidated_exits",
                    PROFIT_GIVEBACK_REASON: "profit_giveback_exits",
                    BACKUP_TIME_FAIL_REASON: "time_failure_exits",
                    MAX_HOLD_REASON: "max_hold_exits",
                }
                if reason not in counter_by_reason:
                    raise RD28ReplayError(f"unknown RD28 exit reason: {reason}")
                counters[counter_by_reason[reason]] += 1
                record, credit = _close_position(
                    position=position,
                    timestamp=timestamp,
                    exit_price=float(decision.exit_price),
                    exit_reason=reason,
                    exit_market_state=current_state,
                    side_cost=side_cost,
                    policy_id=policy_id,
                    portfolio_id=portfolio_id,
                    universe_id=universe_id,
                    cost_multiplier=cost_multiplier,
                )
                cash += credit
                trades.append(record)
                escrow_reason = (
                    EARLY_EVIDENCE_REASON if reason == FAMILY_OVERLAP_EXIT_REASON else reason
                )
                slot = escrow_slot_for_exit(
                    position.evidence,
                    exit_time=timestamp,
                    exit_reason=escrow_reason,
                    slot_escrow_enabled=slot_escrow_enabled,
                )
                if slot is not None:
                    escrows.append(slot)
                    counters["escrow_slots_created"] += 1
                    counters["max_active_escrow_slots"] = max(
                        counters["max_active_escrow_slots"], len(escrows)
                    )
                del positions[pair]

        for position in positions.values():
            bar = _bar_at(position.pair, timestamp, frames, lookups)
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
            if not slot_capacity_available(
                open_position_count=len(positions), active_escrow_count=len(escrows)
            ):
                counters["position_slots_full"] += 1
                if len(positions) < MAXIMUM_POSITIONS and escrows:
                    counters["escrow_slot_rejections"] += 1
                continue

            signal_time = _utc_timestamp(item["signal_time"])
            entry_state = _state_at(state_lookup, signal_time)
            counters[f"entry_state_{entry_state}"] += 1
            admission = router_admission(entry_state)
            if not admission.admit_position:
                if entry_state != RISK_OFF:
                    raise RD28ReplayError("non-RISK_OFF signal unexpectedly suppressed")
                counters["risk_off_suppressed_entries"] += 1
                continue

            entry_bar = _bar_at(pair, timestamp, frames, lookups)
            exit_bar = _bar_at(pair, _utc_timestamp(item["max_exit_time"]), frames, lookups)
            if entry_bar is None:
                counters["missing_entry_bar"] += 1
                continue
            if exit_bar is None:
                counters["missing_exit_bar_precheck"] += 1
                continue
            signal_bar = _bar_at(pair, signal_time, frames, lookups)
            if signal_bar is None:
                raise RD28ReplayError("signal bar missing during admission")
            capacity_source = float(signal_bar["trailing_24h_quote_turnover_proxy"])
            if not math.isfinite(capacity_source) or capacity_source <= 0.0:
                counters["capacity_unavailable"] += 1
                continue

            equity_open, gross_open = _marked_equity(cash=cash, positions=positions)
            if equity_open <= 0.0:
                continue
            gross_room = max(
                0.0,
                (equity_open * MAXIMUM_GROSS_EXPOSURE - gross_open)
                / (1.0 + MAXIMUM_GROSS_EXPOSURE * side_cost),
            )
            if gross_room <= 0.0:
                counters["gross_limit_rejection"] += 1
                continue
            target_notional = equity_open * float(admission.target_slot_fraction)
            capacity_notional = capacity_source * LIQUIDITY_CAPACITY_FRACTION_24H
            notional = min(target_notional, gross_room, capacity_notional)
            if notional < target_notional - 1e-9 and capacity_notional <= min(
                target_notional, gross_room
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
                raise RD28ReplayError("negative cash after entry")
            cash = max(cash, 0.0)
            support = _support_families(item["support_families"])
            atr = float(item["atr24_at_signal"])
            evidence = new_evidence_position(
                pair=pair,
                entry_time=timestamp,
                entry_price=entry_price,
                atr24_at_signal=atr,
                entry_market_state=entry_state,
                signal_family=support[0],
            )
            positions[pair] = ReplayPosition(
                pair=pair,
                signal_time=signal_time,
                entry_time=timestamp,
                max_exit_time=_utc_timestamp(item["max_exit_time"]),
                entry_price=entry_price,
                quantity=quantity,
                entry_notional=notional,
                entry_cost=entry_cost,
                membership_rank=int(item["membership_rank"]),
                support_families=support,
                period_id=str(item["period_id"]),
                atr24_at_signal=atr,
                evidence=evidence,
                entry_market_state=entry_state,
                last_mark=entry_price,
            )
            counters["admitted_entries"] += 1

        for position in positions.values():
            bar = _bar_at(position.pair, timestamp, frames, lookups)
            if bar is None:
                raise RD28ReplayError(f"position mark bar missing: {position.pair} {timestamp}")
            position.evidence = apply_completed_asset_bar(
                position.evidence, completed_high=float(bar["high"])
            )
            position.last_mark = float(bar["close"])

        equity_close, gross_close = _marked_equity(cash=cash, positions=positions)
        if equity_close < -1e-7:
            raise RD28ReplayError("negative equity observed")
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
                    "gross_exposure_fraction": gross_close / equity_close
                    if equity_close > 0.0
                    else math.nan,
                    "open_positions": len(positions),
                    "active_escrow_slots": len(escrows),
                }
            )

    escrows = list(active_escrow_slots(escrows, current_time=replay_cutoff))
    if positions:
        raise RD28ReplayError("open positions remained at replay cutoff")
    if escrows:
        raise RD28ReplayError("active escrow slots remained at replay cutoff")

    trade_frame = pd.DataFrame.from_records(trades)
    daily_frame = pd.DataFrame.from_records(daily_rows)
    equity = np.asarray(hourly_equity_values, dtype=float)
    running_peak = np.maximum.accumulate(equity)
    drawdowns = np.divide(
        running_peak - equity, running_peak, out=np.zeros_like(equity), where=running_peak > 0.0
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
            "minimum_cash": float(daily_frame["cash"].min())
            if len(daily_frame)
            else INITIAL_EQUITY,
            "maximum_active_escrow_slots": counters["max_active_escrow_slots"],
        }
    )
    return trade_frame, daily_frame, metrics, counters


def contract_summary() -> dict[str, Any]:
    validate_replay_constants()
    return {
        "schema_version": SCHEMA_VERSION,
        "policies": list(POLICIES),
        "control_delegate": "RD27_STATIC_EXIT_STATE_ROUTER",
        "router": "EXACT_RD27_P0B_STATE_ROUTER",
        "family_overlap_rule": FAMILY_OVERLAP_RULE,
        "slot_escrow_counts_toward_maximum_positions": True,
        "slot_escrow_reserves_cash": False,
        "slot_escrow_reserves_notional": False,
        "signal_generation_changed": False,
        "cost_contract_changed": False,
        "capacity_contract_changed": False,
        "economic_execution_performed": False,
        "real_market_data_loader_present": False,
        "active_component_counts": {policy: active_component_count(policy) for policy in POLICIES},
    }
