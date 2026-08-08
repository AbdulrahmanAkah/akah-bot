"""RD31 regime-governed portfolio replay.

This module freezes replay semantics only. It contains no raw-data loader and
performs no economic execution at import time.
"""

from __future__ import annotations

import math
from typing import Any, Final

import numpy as np
import pandas as pd

from spotbot.research.rd20_p2_minimal_pullback import MembershipSnapshot
from spotbot.research.rd26_exit_architecture import (
    BASE_ROUND_TRIP_COST,
    COST_MULTIPLIERS,
    DATA_CUTOFF,
    DATA_START,
    INITIAL_EQUITY,
    MAXIMUM_POSITIONS,
    fast_lookup,
    performance_metrics,
)
from spotbot.research.rd27_lifecycle_replay import build_state_lookup
from spotbot.research.rd29_thesis_replay import (
    causal_context_at,
    entry_context_for_event,
)
from spotbot.research.rd30_family_specialist_state import (
    MAX_HOLD_EXIT_REASON,
    TIME_FAIL_EXIT_REASON,
    apply_completed_high,
    evaluate_scheduled_exit,
    new_specialist_position,
)
from spotbot.research.rd30_replacement_replay import (
    ReplayPosition,
    _bar_at,
    _close_position,
    _marked_notionals,
    replay_rd30_policy,
    size_entry_from_marks,
)
from spotbot.research.rd31_regime_admission_governor import (
    FAMILY_QUALITY_CONTROL_EXITS,
    GOVERNOR_STATES,
    LOCKED,
    OPEN,
    POLICIES,
    REGIME_HYSTERESIS_ADMISSION_GOVERNOR,
    GovernedAdmissionDecision,
    admission_decision,
)

SCHEMA_VERSION: Final = "rd31-regime-governed-portfolio-replay-v1"

GOVERNOR_TRANSITION_REASONS: Final = (
    "STRESSED_LOCKS_ADMISSIONS",
    "SUPPORTIVE_OPENS_ADMISSIONS",
    "OPEN_MIXED_TO_CAUTION",
    "CAUTION_MIXED_STAYS_CAUTION",
    "LOCKED_MIXED_STAYS_LOCKED",
    "UNAVAILABLE_PERSISTS_GOVERNOR_STATE",
)


class RD31ReplayError(RuntimeError):
    pass


def _utc(value: Any) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    return timestamp.tz_localize("UTC") if timestamp.tzinfo is None else timestamp.tz_convert("UTC")


def _support_families(value: Any) -> tuple[str, ...]:
    families = tuple(sorted({item for item in str(value).split("|") if item}))
    if not families:
        raise RD31ReplayError("signal has no support family")
    return families


def family_bucket(support_families: tuple[str, ...]) -> str:
    values = set(support_families)
    if values == {"MOMENTUM_BREAKOUT"}:
        return "MB"
    if values == {"RELATIVE_STRENGTH_ROTATION"}:
        return "RS"
    if values == {
        "MOMENTUM_BREAKOUT",
        "RELATIVE_STRENGTH_ROTATION",
    }:
        return "OVERLAP"
    raise RD31ReplayError(f"unknown support-family set: {support_families}")


def apply_entry_policy(
    *,
    policy_id: str,
    support_families: tuple[str, ...] | list[str],
    btc_state: str,
    market_context,
    governor_state: str | None,
) -> tuple[GovernedAdmissionDecision, str | None]:
    if policy_id not in POLICIES:
        raise RD31ReplayError(f"unknown policy: {policy_id}")

    if policy_id == REGIME_HYSTERESIS_ADMISSION_GOVERNOR:
        if governor_state not in GOVERNOR_STATES:
            raise RD31ReplayError("hysteresis policy requires valid governor state")
        governed = admission_decision(
            policy_id=policy_id,
            support_families=support_families,
            btc_state=btc_state,
            market_context=market_context,
            governor_prior_state=str(governor_state),
        )
        if governed.governor_next_state not in GOVERNOR_STATES:
            raise RD31ReplayError("governor admission returned invalid next state")
        return governed, governed.governor_next_state

    governed = admission_decision(
        policy_id=policy_id,
        support_families=support_families,
        btc_state=btc_state,
        market_context=market_context,
    )
    if governed.governor_prior_state is not None or governed.governor_next_state is not None:
        raise RD31ReplayError("static RD31 policy unexpectedly mutated governor state")
    return governed, governor_state


def _initial_counters(events: pd.DataFrame) -> dict[str, int]:
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
        "suppressed_entries": 0,
        "time_failure_exits": 0,
        "max_hold_exits": 0,
        "governor_transition_count": 0,
        "governor_state_OPEN": 0,
        "governor_state_CAUTION": 0,
        "governor_state_LOCKED": 0,
        "governor_locked_suppressions_MB": 0,
        "governor_locked_suppressions_RS": 0,
        "governor_locked_suppressions_OVERLAP": 0,
    }
    for reason in GOVERNOR_TRANSITION_REASONS:
        counters[f"governor_reason_{reason}"] = 0
    for context in ("SUPPORTIVE", "MIXED", "STRESSED", "UNAVAILABLE"):
        for family in ("MB", "RS", "OVERLAP"):
            counters[f"admission_{context}_{family}_ADMIT"] = 0
            counters[f"admission_{context}_{family}_SUPPRESS"] = 0
    return counters


def _augment_baseline_counters(
    counters: dict[str, int],
    events: pd.DataFrame,
) -> dict[str, int]:
    result = _initial_counters(events)
    for key, value in counters.items():
        if isinstance(value, (int, np.integer)):
            result[key] = int(value)
    result["suppressed_entries"] = int(counters.get("family_quality_suppressed_entries", 0))
    return result


def replay_rd31_policy(
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
    if policy_id not in POLICIES:
        raise RD31ReplayError(f"unknown policy: {policy_id}")
    if cost_multiplier not in COST_MULTIPLIERS:
        raise RD31ReplayError("unsupported cost multiplier")

    if policy_id == FAMILY_QUALITY_CONTROL_EXITS:
        trades, daily, metrics, counters = replay_rd30_policy(
            policy_id=FAMILY_QUALITY_CONTROL_EXITS,
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
        return (
            trades,
            daily,
            metrics,
            _augment_baseline_counters(counters, events),
        )

    replay_start = _utc(replay_start)
    replay_cutoff = _utc(replay_cutoff)
    if replay_start >= replay_cutoff:
        raise RD31ReplayError("invalid replay window")

    lookups = {pair: fast_lookup(frame) for pair, frame in frames.items()}
    state_lookup = build_state_lookup(state_frame)
    side_cost = BASE_ROUND_TRIP_COST * float(cost_multiplier) / 2.0

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
    counters = _initial_counters(events)
    governor_state: str | None = OPEN if policy_id == REGIME_HYSTERESIS_ADMISSION_GOVERNOR else None

    for timestamp in pd.date_range(
        replay_start,
        replay_cutoff,
        freq="h",
        inclusive="left",
    ):
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
                raise RD31ReplayError(f"open-position bar missing: {pair} {timestamp}")

            (
                _current_members,
                _current_returns,
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

            scheduled_exit = evaluate_scheduled_exit(
                position.specialist,
                current_open_time=timestamp,
                current_open=float(bar["open"]),
                prior_completed_close=float(prior_bar["close"]),
                profit_state_enabled=False,
            )
            if scheduled_exit.should_exit:
                if scheduled_exit.exit_price is None or scheduled_exit.exit_reason is None:
                    raise RD31ReplayError("scheduled exit missing fill details")
                reason = scheduled_exit.exit_reason
                if reason == TIME_FAIL_EXIT_REASON:
                    counters["time_failure_exits"] += 1
                elif reason == MAX_HOLD_EXIT_REASON:
                    counters["max_hold_exits"] += 1
                else:
                    raise RD31ReplayError(
                        f"RD31 lifecycle emitted prohibited exit reason: {reason}"
                    )

                record, credit = _close_position(
                    position=position,
                    timestamp=timestamp,
                    exit_price=float(scheduled_exit.exit_price),
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
                del positions[pair]

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
            signal_time = _utc(item["signal_time"])
            support = _support_families(item["support_families"])
            bucket = family_bucket(support)

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

            prior_governor_state = governor_state
            governed, governor_state = apply_entry_policy(
                policy_id=policy_id,
                support_families=support,
                btc_state=entry_state,
                market_context=entry_context,
                governor_state=governor_state,
            )
            admission = governed.decision

            if policy_id == REGIME_HYSTERESIS_ADMISSION_GOVERNOR:
                if governor_state not in GOVERNOR_STATES:
                    raise RD31ReplayError("governor state disappeared")
                counters[f"governor_state_{governor_state}"] += 1
                if governed.transition_reason is None:
                    raise RD31ReplayError("governor transition reason missing")
                reason_key = "governor_reason_" + governed.transition_reason
                if reason_key not in counters:
                    raise RD31ReplayError(
                        f"unknown governor transition reason: {governed.transition_reason}"
                    )
                counters[reason_key] += 1
                if prior_governor_state != governor_state:
                    counters["governor_transition_count"] += 1

            outcome = "ADMIT" if admission.admit_position else "SUPPRESS"
            counters[f"admission_{entry_context.context}_{bucket}_{outcome}"] += 1

            if not admission.admit_position:
                counters["suppressed_entries"] += 1
                if policy_id == REGIME_HYSTERESIS_ADMISSION_GOVERNOR and governor_state == LOCKED:
                    counters[f"governor_locked_suppressions_{bucket}"] += 1
                continue

            if pair in positions:
                counters["same_pair_open"] += 1
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
                raise RD31ReplayError("signal bar missing during admission")
            capacity_source = float(signal_bar["trailing_24h_quote_turnover_proxy"])
            if not math.isfinite(capacity_source) or capacity_source <= 0.0:
                counters["capacity_unavailable"] += 1
                continue

            if len(positions) >= MAXIMUM_POSITIONS:
                counters["position_slots_full"] += 1
                continue

            sizing = size_entry_from_marks(
                cash=cash,
                marked_notionals=_marked_notionals(positions),
                target_slot_fraction=float(admission.target_slot_fraction),
                capacity_source=capacity_source,
                side_cost=side_cost,
            )
            if not sizing.feasible:
                if sizing.reason == "GROSS_LIMIT_NO_ROOM":
                    counters["gross_limit_rejection"] += 1
                elif sizing.reason == "CAPACITY_UNAVAILABLE":
                    counters["capacity_unavailable"] += 1
                continue
            if sizing.capacity_capped:
                counters["capacity_capped_entries"] += 1
            if sizing.cash_capped:
                counters["cash_capped_entries"] += 1

            entry_price = float(entry_bar["open"])
            if not math.isfinite(entry_price) or entry_price <= 0.0:
                raise RD31ReplayError("invalid entry open price")
            atr = float(item["atr24_at_signal"])
            if not math.isfinite(atr) or atr <= 0.0:
                raise RD31ReplayError("invalid entry ATR")

            notional = float(sizing.notional)
            quantity = notional / entry_price
            entry_cost = notional * side_cost
            cash -= notional + entry_cost
            if cash < -1e-7:
                raise RD31ReplayError("negative cash after entry")
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

        for position in positions.values():
            bar = _bar_at(
                position.pair,
                timestamp,
                frames,
                lookups,
            )
            if bar is None:
                raise RD31ReplayError(f"position mark bar missing: {position.pair} {timestamp}")
            position.specialist = apply_completed_high(
                position.specialist,
                completed_high=float(bar["high"]),
            )
            position.last_mark = float(bar["close"])

        gross_close = sum(position.quantity * position.last_mark for position in positions.values())
        equity_close = cash + gross_close
        if equity_close < -1e-7:
            raise RD31ReplayError("negative equity observed")
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
                    "governor_state": governor_state,
                }
            )

    if positions:
        raise RD31ReplayError("open positions remained at replay cutoff")

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
        }
    )
    return (
        trade_frame,
        daily_frame,
        metrics,
        counters,
    )


def contract_summary() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "policies": list(POLICIES),
        "baseline_delegate": ("EXACT_RD30_FAMILY_QUALITY_CONTROL_EXITS"),
        "candidate_lifecycle": ("EXACT_RD30_TIME_FAIL72_MAX168_NO_PROFIT_NO_REPLACEMENT"),
        "entry_context_cutoff": "SIGNAL_BAR_CLOSE",
        "governor_update": ("AT_SIGNAL_TIME_BEFORE_ADMISSION"),
        "governor_initial_state": OPEN,
        "governor_states": list(GOVERNOR_STATES),
        "same_timestamp_repeated_context_is_idempotent": True,
        "scheduled_exit_state_cutoff": "PRIOR_COMPLETED_HOUR",
        "scheduled_exit_fill": "CURRENT_1H_OPEN",
        "entry_fill": "NEXT_1H_OPEN_AFTER_SIGNAL",
        "profit_giveback": False,
        "replacement": False,
        "thesis_failure_exit": False,
        "forced_regime_exit": False,
        "current_bar_high_used_for_exit": False,
        "current_bar_low_used_for_exit": False,
        "parameter_grid_search": False,
        "calendar_year_feature": False,
        "economic_execution_performed": False,
        "real_market_data_loader_present": False,
        "2024_accessed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
    }
