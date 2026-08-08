"""RD30 replacement-aware portfolio replay adapter.

This module freezes replay semantics only. It contains no raw-data loader and
performs no economic execution at import time.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Final

import numpy as np
import pandas as pd

from spotbot.research.rd20_p2_minimal_pullback import MembershipSnapshot
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
from spotbot.research.rd27_lifecycle_replay import build_state_lookup
from spotbot.research.rd29_thesis_replay import (
    ROUTER_TIME_FAIL_72_CONTROL as RD29_CONTROL,
)
from spotbot.research.rd29_thesis_replay import (
    causal_context_at,
    entry_context_for_event,
    replay_rd29_policy,
)
from spotbot.research.rd30_family_specialist_state import (
    MAX_HOLD_EXIT_REASON,
    POLICIES,
    PROFIT_GIVEBACK_EXIT_REASON,
    REPLACEMENT_EXIT_REASON,
    ROUTER_TIME_FAIL_72_CONTROL,
    TIME_FAIL_EXIT_REASON,
    SpecialistPosition,
    admission_decision,
    apply_completed_high,
    evaluate_scheduled_exit,
    new_specialist_position,
    policy_components,
    select_replacement_incumbent,
    update_replacement_state,
)

SCHEMA_VERSION: Final = "rd30-replacement-aware-portfolio-replay-v1"


class RD30ReplayError(RuntimeError):
    pass


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
    specialist: SpecialistPosition
    entry_market_state: str
    entry_market_context: str
    last_mark: float


@dataclass(frozen=True)
class EntrySizingDecision:
    feasible: bool
    notional: float
    target_notional: float
    capacity_notional: float
    gross_room: float
    max_cash_notional: float
    capacity_capped: bool
    cash_capped: bool
    reason: str


@dataclass(frozen=True)
class AtomicReplacementPlan:
    should_replace: bool
    incumbent_pair: str | None
    incumbent_exit_price: float | None
    incumbent_cash_credit: float
    sizing: EntrySizingDecision | None
    reason: str
    eligible_degraded_pairs: tuple[str, ...]


def validate_replay_constants() -> None:
    if MAXIMUM_POSITIONS != 5:
        raise RD30ReplayError("maximum-position contract drifted")
    if not math.isclose(MAXIMUM_GROSS_EXPOSURE, 0.90):
        raise RD30ReplayError("gross-exposure contract drifted")
    if not math.isclose(LIQUIDITY_CAPACITY_FRACTION_24H, 0.005):
        raise RD30ReplayError("capacity contract drifted")
    if COST_MULTIPLIERS != (1.0, 2.0):
        raise RD30ReplayError("cost matrix drifted")
    if len(POLICIES) != 4:
        raise RD30ReplayError("RD30 policy registry drifted")


def _utc(value: Any) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    return timestamp.tz_localize("UTC") if timestamp.tzinfo is None else timestamp.tz_convert("UTC")


def _support_families(value: Any) -> tuple[str, ...]:
    families = tuple(sorted({item for item in str(value).split("|") if item}))
    if not families:
        raise RD30ReplayError("signal has no support family")
    unknown = sorted(set(families).difference(FOCUS_FAMILIES))
    if unknown:
        raise RD30ReplayError(f"unknown support families: {unknown}")
    return families


def _bar_at(
    pair: str,
    timestamp: pd.Timestamp,
    frames: dict[str, pd.DataFrame],
    lookups: dict[str, dict[int, int]],
) -> pd.Series | None:
    frame = frames.get(pair)
    if frame is None:
        return None
    index = lookups.get(pair, {}).get(int(_utc(timestamp).value))
    return None if index is None else frame.iloc[index]


def _marked_notionals(
    positions: dict[str, ReplayPosition],
    *,
    excluded_pair: str | None = None,
) -> tuple[float, ...]:
    return tuple(
        position.quantity * position.last_mark
        for pair, position in positions.items()
        if pair != excluded_pair
    )


def size_entry_from_marks(
    *,
    cash: float,
    marked_notionals: tuple[float, ...] | list[float],
    target_slot_fraction: float,
    capacity_source: float,
    side_cost: float,
) -> EntrySizingDecision:
    if cash < -1e-9 or not math.isfinite(float(cash)):
        raise RD30ReplayError("invalid cash for entry sizing")
    if not math.isfinite(float(target_slot_fraction)) or target_slot_fraction <= 0.0:
        raise RD30ReplayError("invalid target slot fraction")
    if not math.isfinite(float(capacity_source)) or capacity_source <= 0.0:
        return EntrySizingDecision(
            False,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            False,
            False,
            "CAPACITY_UNAVAILABLE",
        )
    if side_cost < 0.0 or not math.isfinite(float(side_cost)):
        raise RD30ReplayError("invalid side cost")

    marks = [float(value) for value in marked_notionals]
    if any(not math.isfinite(value) or value < 0.0 for value in marks):
        raise RD30ReplayError("invalid marked notional")

    gross_open = float(sum(marks))
    equity_open = float(cash) + gross_open
    if equity_open <= 0.0:
        return EntrySizingDecision(
            False,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            False,
            False,
            "NONPOSITIVE_EQUITY",
        )

    gross_room = max(
        0.0,
        (equity_open * MAXIMUM_GROSS_EXPOSURE - gross_open)
        / (1.0 + MAXIMUM_GROSS_EXPOSURE * side_cost),
    )
    target_notional = equity_open * float(target_slot_fraction)
    capacity_notional = float(capacity_source) * LIQUIDITY_CAPACITY_FRACTION_24H
    if gross_room <= 0.0:
        return EntrySizingDecision(
            False,
            0.0,
            target_notional,
            capacity_notional,
            gross_room,
            0.0,
            False,
            False,
            "GROSS_LIMIT_NO_ROOM",
        )

    notional = min(
        target_notional,
        gross_room,
        capacity_notional,
    )
    capacity_capped = notional < target_notional - 1e-9 and capacity_notional <= min(
        target_notional, gross_room
    )

    max_cash_notional = float(cash) / (1.0 + side_cost)
    if max_cash_notional <= 0.0:
        return EntrySizingDecision(
            False,
            0.0,
            target_notional,
            capacity_notional,
            gross_room,
            max_cash_notional,
            capacity_capped,
            False,
            "CASH_UNAVAILABLE",
        )

    cash_capped = notional > max_cash_notional
    if cash_capped:
        notional = max_cash_notional
    if notional <= 0.0:
        return EntrySizingDecision(
            False,
            0.0,
            target_notional,
            capacity_notional,
            gross_room,
            max_cash_notional,
            capacity_capped,
            cash_capped,
            "NONPOSITIVE_NOTIONAL",
        )

    return EntrySizingDecision(
        True,
        float(notional),
        float(target_notional),
        float(capacity_notional),
        float(gross_room),
        float(max_cash_notional),
        bool(capacity_capped),
        bool(cash_capped),
        "ENTRY_FEASIBLE",
    )


def _incumbent_cash_credit(
    position: ReplayPosition,
    *,
    exit_price: float,
    side_cost: float,
) -> float:
    exit_notional = position.quantity * float(exit_price)
    return exit_notional * (1.0 - side_cost)


def plan_atomic_replacement(
    positions: dict[str, ReplayPosition],
    *,
    cash: float,
    incoming_prevalidated: bool,
    free_slot_exists: bool,
    target_slot_fraction: float,
    capacity_source: float,
    side_cost: float,
    current_open_by_pair: dict[str, float],
) -> AtomicReplacementPlan:
    selection = select_replacement_incumbent(
        [position.specialist for position in positions.values()],
        incoming_prevalidated=incoming_prevalidated,
        free_slot_exists=free_slot_exists,
    )
    if not selection.should_replace:
        return AtomicReplacementPlan(
            False,
            None,
            None,
            0.0,
            None,
            selection.reason,
            selection.eligible_degraded_pairs,
        )
    if selection.incumbent_pair is None:
        raise RD30ReplayError("replacement selection missing incumbent")

    incumbent = positions.get(selection.incumbent_pair)
    if incumbent is None:
        raise RD30ReplayError("selected replacement incumbent disappeared")
    raw_exit_price = current_open_by_pair.get(incumbent.pair)
    if raw_exit_price is None:
        return AtomicReplacementPlan(
            False,
            incumbent.pair,
            None,
            0.0,
            None,
            "INCUMBENT_CURRENT_OPEN_UNAVAILABLE",
            selection.eligible_degraded_pairs,
        )
    exit_price = float(raw_exit_price)
    if not math.isfinite(exit_price) or exit_price <= 0.0:
        return AtomicReplacementPlan(
            False,
            incumbent.pair,
            None,
            0.0,
            None,
            "INCUMBENT_CURRENT_OPEN_INVALID",
            selection.eligible_degraded_pairs,
        )

    credit = _incumbent_cash_credit(
        incumbent,
        exit_price=exit_price,
        side_cost=side_cost,
    )
    sizing = size_entry_from_marks(
        cash=float(cash) + credit,
        marked_notionals=_marked_notionals(
            positions,
            excluded_pair=incumbent.pair,
        ),
        target_slot_fraction=target_slot_fraction,
        capacity_source=capacity_source,
        side_cost=side_cost,
    )
    if not sizing.feasible:
        return AtomicReplacementPlan(
            False,
            incumbent.pair,
            exit_price,
            credit,
            sizing,
            f"REPLACEMENT_ENTRY_INFEASIBLE_{sizing.reason}",
            selection.eligible_degraded_pairs,
        )
    return AtomicReplacementPlan(
        True,
        incumbent.pair,
        exit_price,
        credit,
        sizing,
        "ATOMIC_REPLACEMENT_FEASIBLE",
        selection.eligible_degraded_pairs,
    )


def _close_position(
    *,
    position: ReplayPosition,
    timestamp: pd.Timestamp,
    exit_price: float,
    exit_reason: str,
    exit_market_state: str,
    exit_market_context: str,
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
    degraded_since = position.specialist.degraded_since
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
            "high_water_at_exit": (position.specialist.high_water_prior),
            "entry_market_state": (position.entry_market_state),
            "exit_market_state": exit_market_state,
            "entry_market_context": (position.entry_market_context),
            "exit_market_context": exit_market_context,
            "lifecycle_class": (position.specialist.lifecycle_class),
            "degraded_since_at_exit": degraded_since,
        },
        cash_credit,
    )


def replay_rd30_policy(
    *,
    policy_id: str,
    portfolio_id: str,
    universe_id: str,
    cost_multiplier: float,
    events: pd.DataFrame,
    frames: dict[str, pd.DataFrame],
    state_frame: pd.DataFrame,
    membership: list[MembershipSnapshot] | tuple[MembershipSnapshot, ...],
    replay_start: pd.Timestamp = DATA_START,
    replay_cutoff: pd.Timestamp = DATA_CUTOFF,
) -> tuple[
    pd.DataFrame,
    pd.DataFrame,
    dict[str, Any],
    dict[str, int],
]:
    validate_replay_constants()
    if policy_id not in POLICIES:
        raise RD30ReplayError(f"unknown policy: {policy_id}")
    if cost_multiplier not in COST_MULTIPLIERS:
        raise RD30ReplayError("unsupported cost multiplier")

    if policy_id == ROUTER_TIME_FAIL_72_CONTROL:
        return replay_rd29_policy(
            policy_id=RD29_CONTROL,
            portfolio_id=portfolio_id,
            universe_id=universe_id,
            cost_multiplier=cost_multiplier,
            events=events,
            frames=frames,
            state_frame=state_frame,
            membership=membership,
            replay_start=replay_start,
            replay_cutoff=replay_cutoff,
        )

    components = policy_components(policy_id)
    replay_start = _utc(replay_start)
    replay_cutoff = _utc(replay_cutoff)
    if replay_start >= replay_cutoff:
        raise RD30ReplayError("invalid replay window")

    lookups = {pair: fast_lookup(frame) for pair, frame in frames.items()}
    state_lookup = build_state_lookup(state_frame)
    side_cost = BASE_ROUND_TRIP_COST * cost_multiplier / 2.0

    scheduled: dict[int, list[dict[str, Any]]] = {}
    for raw in events.to_dict(orient="records"):
        signal_time = _utc(raw["timestamp"])
        entry_time = signal_time + pd.Timedelta(hours=1)
        max_exit_time = entry_time + pd.Timedelta(hours=168)
        if entry_time < replay_start or max_exit_time >= replay_cutoff:
            continue
        scheduled.setdefault(
            int(entry_time.value),
            [],
        ).append(
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
    counters: dict[str, int] = {
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
        "family_quality_suppressed_entries": 0,
        "risk_off_or_router_suppressed_entries": 0,
        "time_failure_exits": 0,
        "profit_giveback_exits": 0,
        "max_hold_exits": 0,
        "rs_degraded_set_count": 0,
        "rs_degraded_clear_count": 0,
        "rs_degraded_persist_count": 0,
        "rs_unevaluable_checkpoint_count": 0,
        "atomic_replacement_count": 0,
        "atomic_replacement_incoming_mb_supported": 0,
        "atomic_replacement_incoming_rs_only": 0,
        "replacement_no_candidate": 0,
        "replacement_entry_infeasible": 0,
        "degraded_positions_held_without_replacement": 0,
        "entry_context_SUPPORTIVE": 0,
        "entry_context_MIXED": 0,
        "entry_context_STRESSED": 0,
        "entry_context_UNAVAILABLE": 0,
    }

    for timestamp in pd.date_range(
        replay_start,
        replay_cutoff,
        freq="h",
        inclusive="left",
    ):
        context_cache: dict[
            str,
            tuple[str, str],
        ] = {}

        for pair in sorted(list(positions)):
            position = positions[pair]
            bar = _bar_at(
                pair,
                timestamp,
                frames,
                lookups,
            )
            prior_time = timestamp - pd.Timedelta(hours=1)
            prior_bar = _bar_at(
                pair,
                prior_time,
                frames,
                lookups,
            )
            if bar is None or prior_bar is None:
                raise RD30ReplayError(f"open-position bar missing: {pair} {timestamp}")

            (
                current_members,
                current_returns,
                current_state,
                current_context,
            ) = causal_context_at(
                universe_id=universe_id,
                completed_time=prior_time,
                membership=membership,
                frames=frames,
                lookups=lookups,
                state_lookup=state_lookup,
            )
            context_cache[pair] = (
                current_state,
                current_context.context,
            )

            scheduled_exit = evaluate_scheduled_exit(
                position.specialist,
                current_open_time=timestamp,
                current_open=float(bar["open"]),
                prior_completed_close=float(prior_bar["close"]),
                profit_state_enabled=components["profit_state"],
            )
            if scheduled_exit.should_exit:
                if scheduled_exit.exit_price is None or scheduled_exit.exit_reason is None:
                    raise RD30ReplayError("scheduled exit missing fill details")
                reason = scheduled_exit.exit_reason
                if reason == TIME_FAIL_EXIT_REASON:
                    counters["time_failure_exits"] += 1
                elif reason == PROFIT_GIVEBACK_EXIT_REASON:
                    counters["profit_giveback_exits"] += 1
                elif reason == MAX_HOLD_EXIT_REASON:
                    counters["max_hold_exits"] += 1
                else:
                    raise RD30ReplayError(f"unknown RD30 exit reason: {reason}")
                record, credit = _close_position(
                    position=position,
                    timestamp=timestamp,
                    exit_price=float(scheduled_exit.exit_price),
                    exit_reason=reason,
                    exit_market_state=current_state,
                    exit_market_context=(current_context.context),
                    side_cost=side_cost,
                    policy_id=policy_id,
                    portfolio_id=portfolio_id,
                    universe_id=universe_id,
                    cost_multiplier=cost_multiplier,
                )
                cash += credit
                trades.append(record)
                del positions[pair]
                continue

            if components["replacement_state"]:
                state = update_replacement_state(
                    position.specialist,
                    current_open_time=timestamp,
                    current_members=current_members,
                    return_72h_by_pair=current_returns,
                    market_context=current_context,
                )
                position.specialist = state.position
                if state.reason == "RS_DEGRADED_SET":
                    counters["rs_degraded_set_count"] += 1
                elif state.reason == "RS_DEGRADED_CLEARED":
                    counters["rs_degraded_clear_count"] += 1
                elif state.reason == "RS_DEGRADED_PERSIST":
                    counters["rs_degraded_persist_count"] += 1
                elif state.reason == ("RS_UNEVALUABLE_PERSIST_PRIOR_DEGRADED_STATE"):
                    counters["rs_unevaluable_checkpoint_count"] += 1

        for position in positions.values():
            bar = _bar_at(
                position.pair,
                timestamp,
                frames,
                lookups,
            )
            if bar is not None:
                position.last_mark = float(bar["open"])

        entries = sorted(
            scheduled.get(int(timestamp.value), []),
            key=lambda item: (
                int(item["membership_rank"]),
                str(item["pair"]),
            ),
        )
        for item in entries:
            pair = str(item["pair"])
            if pair in positions:
                counters["same_pair_open"] += 1
                continue

            signal_time = _utc(item["signal_time"])
            support = _support_families(item["support_families"])
            (
                _entry_members,
                _entry_returns,
                entry_state,
                entry_context,
                _breakout_reference,
            ) = entry_context_for_event(
                universe_id=universe_id,
                signal_time=signal_time,
                support_families=support,
                pair=pair,
                membership=membership,
                frames=frames,
                lookups=lookups,
                state_lookup=state_lookup,
            )
            counters[f"entry_context_{entry_context.context}"] += 1

            admission = admission_decision(
                policy_id=policy_id,
                support_families=support,
                btc_state=entry_state,
                market_context=entry_context,
            )
            if not admission.admit_position:
                if components["family_quality_admission"]:
                    counters["family_quality_suppressed_entries"] += 1
                else:
                    counters["risk_off_or_router_suppressed_entries"] += 1
                continue

            entry_bar = _bar_at(
                pair,
                timestamp,
                frames,
                lookups,
            )
            exit_bar = _bar_at(
                pair,
                _utc(item["max_exit_time"]),
                frames,
                lookups,
            )
            if entry_bar is None:
                counters["missing_entry_bar"] += 1
                continue
            if exit_bar is None:
                counters["missing_exit_bar_precheck"] += 1
                continue

            signal_bar = _bar_at(
                pair,
                signal_time,
                frames,
                lookups,
            )
            if signal_bar is None:
                raise RD30ReplayError("signal bar missing during admission")
            capacity_source = float(signal_bar["trailing_24h_quote_turnover_proxy"])
            if not math.isfinite(capacity_source) or capacity_source <= 0.0:
                counters["capacity_unavailable"] += 1
                continue

            target_slot = float(admission.target_slot_fraction)
            sizing: EntrySizingDecision | None = None
            replacement_plan: AtomicReplacementPlan | None = None

            if len(positions) < MAXIMUM_POSITIONS:
                sizing = size_entry_from_marks(
                    cash=cash,
                    marked_notionals=_marked_notionals(positions),
                    target_slot_fraction=target_slot,
                    capacity_source=capacity_source,
                    side_cost=side_cost,
                )
            elif components["replacement_state"]:
                current_open_by_pair: dict[str, float] = {}
                for incumbent_pair in positions:
                    incumbent_bar = _bar_at(
                        incumbent_pair,
                        timestamp,
                        frames,
                        lookups,
                    )
                    if incumbent_bar is not None:
                        current_open_by_pair[incumbent_pair] = float(incumbent_bar["open"])
                replacement_plan = plan_atomic_replacement(
                    positions,
                    cash=cash,
                    incoming_prevalidated=True,
                    free_slot_exists=False,
                    target_slot_fraction=target_slot,
                    capacity_source=capacity_source,
                    side_cost=side_cost,
                    current_open_by_pair=(current_open_by_pair),
                )
                if not replacement_plan.should_replace:
                    counters["position_slots_full"] += 1
                    if replacement_plan.reason == ("NO_DEGRADED_RS_ONLY_INCUMBENT"):
                        counters["replacement_no_candidate"] += 1
                    elif replacement_plan.reason.startswith("REPLACEMENT_ENTRY_INFEASIBLE_"):
                        counters["replacement_entry_infeasible"] += 1
                    continue
                sizing = replacement_plan.sizing
            else:
                counters["position_slots_full"] += 1
                continue

            if sizing is None or not sizing.feasible:
                if sizing is not None:
                    if sizing.reason == "GROSS_LIMIT_NO_ROOM":
                        counters["gross_limit_rejection"] += 1
                    elif sizing.reason == "CAPACITY_UNAVAILABLE":
                        counters["capacity_unavailable"] += 1
                continue

            if sizing.capacity_capped:
                counters["capacity_capped_entries"] += 1
            if sizing.cash_capped:
                counters["cash_capped_entries"] += 1

            if replacement_plan is not None and replacement_plan.should_replace:
                incumbent_pair = replacement_plan.incumbent_pair
                exit_price = replacement_plan.incumbent_exit_price
                if incumbent_pair is None or exit_price is None:
                    raise RD30ReplayError("feasible replacement missing incumbent")
                incumbent = positions[incumbent_pair]
                state_context = context_cache.get(incumbent_pair)
                if state_context is None:
                    prior_time = timestamp - pd.Timedelta(hours=1)
                    (
                        _members,
                        _returns,
                        incumbent_state,
                        incumbent_context,
                    ) = causal_context_at(
                        universe_id=universe_id,
                        completed_time=prior_time,
                        membership=membership,
                        frames=frames,
                        lookups=lookups,
                        state_lookup=state_lookup,
                    )
                    state_context = (
                        incumbent_state,
                        incumbent_context.context,
                    )
                record, credit = _close_position(
                    position=incumbent,
                    timestamp=timestamp,
                    exit_price=float(exit_price),
                    exit_reason=REPLACEMENT_EXIT_REASON,
                    exit_market_state=state_context[0],
                    exit_market_context=state_context[1],
                    side_cost=side_cost,
                    policy_id=policy_id,
                    portfolio_id=portfolio_id,
                    universe_id=universe_id,
                    cost_multiplier=cost_multiplier,
                )
                if not math.isclose(
                    credit,
                    replacement_plan.incumbent_cash_credit,
                    rel_tol=1e-12,
                    abs_tol=1e-9,
                ):
                    raise RD30ReplayError("replacement credit changed after plan")
                cash += credit
                trades.append(record)
                del positions[incumbent_pair]
                counters["atomic_replacement_count"] += 1

            entry_price = float(entry_bar["open"])
            if not math.isfinite(entry_price) or entry_price <= 0.0:
                raise RD30ReplayError("invalid entry open price")
            atr = float(item["atr24_at_signal"])
            if not math.isfinite(atr) or atr <= 0.0:
                raise RD30ReplayError("invalid entry ATR")

            notional = float(sizing.notional)
            quantity = notional / entry_price
            entry_cost = notional * side_cost
            cash -= notional + entry_cost
            if cash < -1e-7:
                raise RD30ReplayError("negative cash after entry")
            cash = max(cash, 0.0)

            specialist = new_specialist_position(
                pair=pair,
                entry_time=timestamp,
                entry_price=entry_price,
                atr24_at_signal=atr,
                support_families=support,
            )
            positions[pair] = ReplayPosition(
                pair=pair,
                signal_time=signal_time,
                entry_time=timestamp,
                max_exit_time=_utc(item["max_exit_time"]),
                entry_price=entry_price,
                quantity=quantity,
                entry_notional=notional,
                entry_cost=entry_cost,
                membership_rank=int(item["membership_rank"]),
                support_families=support,
                period_id=str(item["period_id"]),
                atr24_at_signal=atr,
                specialist=specialist,
                entry_market_state=entry_state,
                entry_market_context=(entry_context.context),
                last_mark=entry_price,
            )
            counters["admitted_entries"] += 1

            if replacement_plan is not None:
                if specialist.lifecycle_class == "MB_SUPPORTED":
                    counters["atomic_replacement_incoming_mb_supported"] += 1
                else:
                    counters["atomic_replacement_incoming_rs_only"] += 1

        if components["replacement_state"]:
            counters["degraded_positions_held_without_replacement"] += sum(
                int(position.specialist.degraded_since is not None)
                for position in positions.values()
            )

        for position in positions.values():
            bar = _bar_at(
                position.pair,
                timestamp,
                frames,
                lookups,
            )
            if bar is None:
                raise RD30ReplayError(f"position mark bar missing: {position.pair} {timestamp}")
            position.specialist = apply_completed_high(
                position.specialist,
                completed_high=float(bar["high"]),
            )
            position.last_mark = float(bar["close"])

        gross_close = sum(position.quantity * position.last_mark for position in positions.values())
        equity_close = cash + gross_close
        if equity_close < -1e-7:
            raise RD30ReplayError("negative equity observed")
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
                    "active_degraded_rs_positions": sum(
                        int(position.specialist.degraded_since is not None)
                        for position in positions.values()
                    ),
                }
            )

    if positions:
        raise RD30ReplayError("open positions remained at replay cutoff")

    trade_frame = pd.DataFrame.from_records(trades)
    daily_frame = pd.DataFrame.from_records(daily_rows)
    equity = np.asarray(
        hourly_equity_values,
        dtype=float,
    )
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
        maximum_drawdown=(float(drawdowns.max()) if len(drawdowns) else 0.0),
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
            "atomic_replacement_count": counters["atomic_replacement_count"],
        }
    )
    return (
        trade_frame,
        daily_frame,
        metrics,
        counters,
    )


def contract_summary() -> dict[str, Any]:
    validate_replay_constants()
    return {
        "schema_version": SCHEMA_VERSION,
        "policies": list(POLICIES),
        "control_delegate": ("EXACT_RD29_ROUTER_TIME_FAIL_72_CONTROL"),
        "family_quality_source": ("EXACT_RD30_P0B_USING_RD29_ADMISSION"),
        "open_position_context_cutoff": ("PRIOR_COMPLETED_HOUR"),
        "entry_context_cutoff": "SIGNAL_BAR_CLOSE",
        "scheduled_exit_fill": "CURRENT_1H_OPEN",
        "replacement_exit_fill": "CURRENT_1H_OPEN",
        "replacement_entry_fill": ("SAME_CURRENT_1H_OPEN_AFTER_ATOMIC_EXIT"),
        "replacement_requires_prevalidated_incoming": True,
        "replacement_forbidden_when_free_slot_exists": True,
        "replacement_planned_before_mutation": True,
        "replacement_entry_sizing_uses_hypothetical_exit_credit": True,
        "failed_replacement_plan_keeps_incumbent": True,
        "mb_thesis_failure_exit": False,
        "mb_replacement_degradation": False,
        "global_slot_escrow": False,
        "same_pair_cooldown": False,
        "current_bar_high_used_for_exit": False,
        "current_bar_low_used_for_exit": False,
        "signal_generation_changed": False,
        "cost_contract_changed": False,
        "capacity_contract_changed": False,
        "economic_execution_performed": False,
        "real_market_data_loader_present": False,
        "2024_accessed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
    }
