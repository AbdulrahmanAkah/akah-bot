"""RD29 frozen portfolio replay adapter for thesis-confidence candidates."""

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
    FAMILY_MOMENTUM_BREAKOUT,
    FOCUS_FAMILIES,
    INITIAL_EQUITY,
    LIQUIDITY_CAPACITY_FRACTION_24H,
    MAXIMUM_GROSS_EXPOSURE,
    MAXIMUM_POSITIONS,
    fast_lookup,
    performance_metrics,
)
from spotbot.research.rd27_lifecycle_replay import build_state_lookup
from spotbot.research.rd28_evidence_gated_lifecycle import (
    ROUTER_TIME_FAIL_72_CONTROL as RD28_CONTROL,
)
from spotbot.research.rd28_lifecycle_replay import (
    replay_rd28_policy as rd28_replay_policy,
)
from spotbot.research.rd29_thesis_context import (
    MAX_HOLD_EXIT_REASON,
    POLICIES,
    PROFIT_GIVEBACK_EXIT_REASON,
    ROUTER_TIME_FAIL_72_CONTROL,
    THESIS_FAILURE_EXIT_REASON,
    PairCooldown,
    ThesisPosition,
    active_pair_cooldowns,
    admission_decision,
    apply_completed_high,
    compute_market_context,
    cooldown_after_exit,
    evaluate_lifecycle_exit,
    new_thesis_position,
    pair_is_cooldown_blocked,
    policy_components,
)

SCHEMA_VERSION: Final = "rd29-thesis-portfolio-replay-v1"


class RD29ReplayError(RuntimeError):
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
    thesis: ThesisPosition
    entry_market_state: str
    entry_market_context: str
    last_mark: float


def validate_replay_constants() -> None:
    if MAXIMUM_POSITIONS != 5:
        raise RD29ReplayError("maximum-position contract drifted")
    if not math.isclose(MAXIMUM_GROSS_EXPOSURE, 0.90):
        raise RD29ReplayError("gross-exposure contract drifted")
    if not math.isclose(LIQUIDITY_CAPACITY_FRACTION_24H, 0.005):
        raise RD29ReplayError("capacity contract drifted")
    if COST_MULTIPLIERS != (1.0, 2.0):
        raise RD29ReplayError("cost matrix drifted")
    if len(POLICIES) != 4:
        raise RD29ReplayError("RD29 policy registry drifted")


def _utc(value: Any) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    return timestamp.tz_localize("UTC") if timestamp.tzinfo is None else timestamp.tz_convert("UTC")


def _support_families(value: Any) -> tuple[str, ...]:
    families = tuple(sorted({item for item in str(value).split("|") if item}))
    if not families:
        raise RD29ReplayError("signal has no support family")
    unknown = sorted(set(families).difference(FOCUS_FAMILIES))
    if unknown:
        raise RD29ReplayError(f"unknown support families: {unknown}")
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


def membership_at(
    snapshots: list[MembershipSnapshot] | tuple[MembershipSnapshot, ...],
    *,
    universe_id: str,
    timestamp: pd.Timestamp,
) -> tuple[tuple[str, int], ...]:
    current = _utc(timestamp)
    matches = [
        snapshot
        for snapshot in snapshots
        if snapshot.universe_id == universe_id
        and _utc(snapshot.decision_time) <= current
        and current < _utc(snapshot.effective_end)
    ]
    if len(matches) != 1:
        raise RD29ReplayError(
            "expected exactly one causal membership snapshot for "
            f"{universe_id} {current}; got {len(matches)}"
        )
    return tuple(matches[0].members)


def return_72h_map_at(
    *,
    members: tuple[tuple[str, int], ...],
    timestamp: pd.Timestamp,
    frames: dict[str, pd.DataFrame],
    lookups: dict[str, dict[int, int]],
) -> dict[str, float | None]:
    result: dict[str, float | None] = {}
    for pair, _rank in members:
        row = _bar_at(pair, timestamp, frames, lookups)
        if row is None or "return_72h" not in row:
            result[pair] = None
            continue
        value = row["return_72h"]
        if pd.isna(value) or not math.isfinite(float(value)):
            result[pair] = None
        else:
            result[pair] = float(value)
    return result


def causal_context_at(
    *,
    universe_id: str,
    completed_time: pd.Timestamp,
    membership: list[MembershipSnapshot] | tuple[MembershipSnapshot, ...],
    frames: dict[str, pd.DataFrame],
    lookups: dict[str, dict[int, int]],
    state_lookup: dict[int, str],
):
    cutoff = _utc(completed_time)
    members = membership_at(
        membership,
        universe_id=universe_id,
        timestamp=cutoff,
    )
    returns = return_72h_map_at(
        members=members,
        timestamp=cutoff,
        frames=frames,
        lookups=lookups,
    )
    btc_state = state_lookup.get(int(cutoff.value))
    if btc_state is None:
        raise RD29ReplayError(f"BTC state unavailable at causal cutoff: {cutoff}")
    context = compute_market_context(
        btc_state=btc_state,
        members=members,
        return_72h_by_pair=returns,
    )
    return members, returns, btc_state, context


def momentum_breakout_reference_at_signal(
    *,
    support_families: tuple[str, ...],
    pair: str,
    signal_time: pd.Timestamp,
    frames: dict[str, pd.DataFrame],
    lookups: dict[str, dict[int, int]],
) -> float | None:
    if FAMILY_MOMENTUM_BREAKOUT not in support_families:
        return None
    row = _bar_at(pair, signal_time, frames, lookups)
    if row is None:
        raise RD29ReplayError("MB signal bar unavailable")
    if "prior_72h_high" not in row:
        raise RD29ReplayError("MB signal bar lacks prior_72h_high")
    reference = float(row["prior_72h_high"])
    if not math.isfinite(reference) or reference <= 0.0:
        raise RD29ReplayError("MB breakout reference is invalid")
    return reference


def entry_context_for_event(
    *,
    universe_id: str,
    signal_time: pd.Timestamp,
    support_families: tuple[str, ...],
    pair: str,
    membership: list[MembershipSnapshot] | tuple[MembershipSnapshot, ...],
    frames: dict[str, pd.DataFrame],
    lookups: dict[str, dict[int, int]],
    state_lookup: dict[int, str],
):
    members, returns, btc_state, context = causal_context_at(
        universe_id=universe_id,
        completed_time=signal_time,
        membership=membership,
        frames=frames,
        lookups=lookups,
        state_lookup=state_lookup,
    )
    breakout_reference = momentum_breakout_reference_at_signal(
        support_families=support_families,
        pair=pair,
        signal_time=signal_time,
        frames=frames,
        lookups=lookups,
    )
    return members, returns, btc_state, context, breakout_reference


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
            "high_water_at_exit": position.thesis.high_water_prior,
            "entry_market_state": position.entry_market_state,
            "exit_market_state": exit_market_state,
            "entry_market_context": position.entry_market_context,
            "exit_market_context": exit_market_context,
            "mb_breakout_reference": (position.thesis.momentum_breakout_reference),
        },
        cash_credit,
    )


def _normalize_control_label(
    trades: pd.DataFrame,
    daily: pd.DataFrame,
    metrics: dict[str, Any],
):
    trades = trades.copy()
    daily = daily.copy()
    metrics = dict(metrics)
    if len(trades) and "policy_id" in trades:
        trades["policy_id"] = ROUTER_TIME_FAIL_72_CONTROL
    if len(daily) and "policy_id" in daily:
        daily["policy_id"] = ROUTER_TIME_FAIL_72_CONTROL
    metrics["policy_id"] = ROUTER_TIME_FAIL_72_CONTROL
    return trades, daily, metrics


def replay_rd29_policy(
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
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any], dict[str, int]]:
    validate_replay_constants()
    if policy_id not in POLICIES:
        raise RD29ReplayError(f"unknown policy: {policy_id}")
    if cost_multiplier not in COST_MULTIPLIERS:
        raise RD29ReplayError("unsupported cost multiplier")

    if policy_id == ROUTER_TIME_FAIL_72_CONTROL:
        trades, daily, metrics, counters = rd28_replay_policy(
            policy_id=RD28_CONTROL,
            portfolio_id=portfolio_id,
            universe_id=universe_id,
            cost_multiplier=cost_multiplier,
            events=events,
            frames=frames,
            state_frame=state_frame,
            replay_start=replay_start,
            replay_cutoff=replay_cutoff,
        )
        trades, daily, metrics = _normalize_control_label(
            trades,
            daily,
            metrics,
        )
        return trades, daily, metrics, counters

    components = policy_components(policy_id)
    if not components["thesis_confidence_exit"]:
        raise RD29ReplayError("candidate policy must use thesis-confidence exit")

    replay_start = _utc(replay_start)
    replay_cutoff = _utc(replay_cutoff)
    if replay_start >= replay_cutoff:
        raise RD29ReplayError("invalid replay window")

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
    cooldowns: list[PairCooldown] = []
    trades: list[dict[str, Any]] = []
    daily_rows: list[dict[str, Any]] = []
    hourly_equity_values: list[float] = []
    counters: dict[str, int] = {
        "signal_events": len(events),
        "missing_entry_bar": 0,
        "missing_exit_bar_precheck": 0,
        "same_pair_open": 0,
        "position_slots_full": 0,
        "same_pair_cooldown_rejections": 0,
        "gross_limit_rejection": 0,
        "capacity_unavailable": 0,
        "capacity_capped_entries": 0,
        "cash_capped_entries": 0,
        "admitted_entries": 0,
        "family_quality_suppressed_entries": 0,
        "risk_off_or_router_suppressed_entries": 0,
        "thesis_failure_exits": 0,
        "profit_giveback_exits": 0,
        "max_hold_exits": 0,
        "pair_cooldowns_created": 0,
        "pair_cooldowns_released": 0,
        "max_active_pair_cooldowns": 0,
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
        before = len(cooldowns)
        cooldowns = list(active_pair_cooldowns(cooldowns, current_time=timestamp))
        counters["pair_cooldowns_released"] += before - len(cooldowns)

        for pair in sorted(list(positions)):
            position = positions[pair]
            bar = _bar_at(pair, timestamp, frames, lookups)
            prior_time = timestamp - pd.Timedelta(hours=1)
            prior_bar = _bar_at(pair, prior_time, frames, lookups)
            if bar is None or prior_bar is None:
                raise RD29ReplayError(f"open-position bar missing: {pair} {timestamp}")

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
            decision = evaluate_lifecycle_exit(
                position.thesis,
                current_open_time=timestamp,
                current_open=float(bar["open"]),
                prior_completed_close=float(prior_bar["close"]),
                current_members=current_members,
                return_72h_by_pair=current_returns,
                market_context=current_context,
            )
            if decision.should_exit:
                if decision.exit_price is None or decision.exit_reason is None:
                    raise RD29ReplayError("exit missing fill details")
                reason = decision.exit_reason
                if reason == THESIS_FAILURE_EXIT_REASON:
                    counters["thesis_failure_exits"] += 1
                elif reason == PROFIT_GIVEBACK_EXIT_REASON:
                    counters["profit_giveback_exits"] += 1
                elif reason == MAX_HOLD_EXIT_REASON:
                    counters["max_hold_exits"] += 1
                else:
                    raise RD29ReplayError(f"unknown RD29 exit reason: {reason}")

                record, credit = _close_position(
                    position=position,
                    timestamp=timestamp,
                    exit_price=float(decision.exit_price),
                    exit_reason=reason,
                    exit_market_state=current_state,
                    exit_market_context=current_context.context,
                    side_cost=side_cost,
                    policy_id=policy_id,
                    portfolio_id=portfolio_id,
                    universe_id=universe_id,
                    cost_multiplier=cost_multiplier,
                )
                cash += credit
                trades.append(record)
                cooldown = cooldown_after_exit(
                    position.thesis,
                    exit_time=timestamp,
                    exit_reason=reason,
                    same_pair_cooldown_enabled=components["same_pair_cooldown"],
                )
                if cooldown is not None:
                    cooldowns.append(cooldown)
                    counters["pair_cooldowns_created"] += 1
                    counters["max_active_pair_cooldowns"] = max(
                        counters["max_active_pair_cooldowns"],
                        len(cooldowns),
                    )
                del positions[pair]

        for position in positions.values():
            bar = _bar_at(position.pair, timestamp, frames, lookups)
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
            if pair_is_cooldown_blocked(
                cooldowns,
                pair=pair,
                current_time=timestamp,
            ):
                counters["same_pair_cooldown_rejections"] += 1
                continue
            if len(positions) >= MAXIMUM_POSITIONS:
                counters["position_slots_full"] += 1
                continue

            signal_time = _utc(item["signal_time"])
            support = _support_families(item["support_families"])
            (
                _entry_members,
                _entry_returns,
                entry_state,
                entry_context,
                breakout_reference,
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
                support_families=support,
                btc_state=entry_state,
                market_context=entry_context,
                family_quality_enabled=components["family_quality_admission"],
            )
            if not admission.admit_position:
                if components["family_quality_admission"]:
                    counters["family_quality_suppressed_entries"] += 1
                else:
                    counters["risk_off_or_router_suppressed_entries"] += 1
                continue

            entry_bar = _bar_at(pair, timestamp, frames, lookups)
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
            signal_bar = _bar_at(pair, signal_time, frames, lookups)
            if signal_bar is None:
                raise RD29ReplayError("signal bar missing during admission")

            capacity_source = float(signal_bar["trailing_24h_quote_turnover_proxy"])
            if not math.isfinite(capacity_source) or capacity_source <= 0.0:
                counters["capacity_unavailable"] += 1
                continue

            equity_open, gross_open = _marked_equity(
                cash=cash,
                positions=positions,
            )
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
            atr = float(item["atr24_at_signal"])
            quantity = notional / entry_price
            entry_cost = notional * side_cost
            cash -= notional + entry_cost
            if cash < -1e-7:
                raise RD29ReplayError("negative cash after entry")
            cash = max(cash, 0.0)

            thesis = new_thesis_position(
                pair=pair,
                entry_time=timestamp,
                entry_price=entry_price,
                atr24_at_signal=atr,
                entry_market_context=entry_context.context,
                support_families=support,
                momentum_breakout_reference=breakout_reference,
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
                thesis=thesis,
                entry_market_state=entry_state,
                entry_market_context=entry_context.context,
                last_mark=entry_price,
            )
            counters["admitted_entries"] += 1

        for position in positions.values():
            bar = _bar_at(position.pair, timestamp, frames, lookups)
            if bar is None:
                raise RD29ReplayError(f"position mark bar missing: {position.pair} {timestamp}")
            position.thesis = apply_completed_high(
                position.thesis,
                completed_high=float(bar["high"]),
            )
            position.last_mark = float(bar["close"])

        equity_close, gross_close = _marked_equity(
            cash=cash,
            positions=positions,
        )
        if equity_close < -1e-7:
            raise RD29ReplayError("negative equity observed")
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
                    "active_pair_cooldowns": len(cooldowns),
                }
            )

    if positions:
        raise RD29ReplayError("open positions remained at replay cutoff")

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
            "maximum_active_pair_cooldowns": counters["max_active_pair_cooldowns"],
        }
    )
    return trade_frame, daily_frame, metrics, counters


def contract_summary() -> dict[str, Any]:
    validate_replay_constants()
    return {
        "schema_version": SCHEMA_VERSION,
        "policies": list(POLICIES),
        "control_delegate": "RD28_ROUTER_TIME_FAIL_72_CONTROL",
        "control_economics_changed": False,
        "control_label_normalized_only": True,
        "membership_source": "CAUSALLY_EFFECTIVE_PIT_SNAPSHOT",
        "entry_context_cutoff": "SIGNAL_BAR_CLOSE",
        "open_position_context_cutoff": "PRIOR_COMPLETED_HOUR",
        "mb_reference_source": "SIGNAL_BAR_PRIOR_72H_HIGH",
        "rs_rank_source": "CURRENT_PIT_MEMBER_RETURN_72H",
        "global_slot_escrow": False,
        "same_pair_cooldown_only": True,
        "signal_generation_changed": False,
        "cost_contract_changed": False,
        "capacity_contract_changed": False,
        "economic_execution_performed": False,
        "real_market_data_loader_present": False,
    }
