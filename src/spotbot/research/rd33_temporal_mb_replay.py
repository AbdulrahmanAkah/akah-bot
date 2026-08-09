"""RD33 temporal-MB portfolio replay.

Pre-economic replay semantics only. This module contains no raw-data loader and
does not execute 2022-2023 economics at import time.

The key invariant is structural: every candidate consumes one precomputed
RD31-control governor ledger built on the original signal clock. Temporal MB
confirmation never calls or mutates the governor and never creates a second
transition. RS-only portfolios delegate exactly to the frozen RD31 replay with
policy-label normalization only.
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
    FAMILY_MOMENTUM_BREAKOUT,
    FAMILY_RELATIVE_STRENGTH_ROTATION,
    INITIAL_EQUITY,
    MAXIMUM_POSITIONS,
    fast_lookup,
    performance_metrics,
)
from spotbot.research.rd27_lifecycle_replay import build_state_lookup
from spotbot.research.rd29_thesis_context import AdmissionDecision
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
    size_entry_from_marks,
)
from spotbot.research.rd31_regime_admission_governor import (
    GOVERNOR_STATES,
    LOCKED,
    OPEN,
    REGIME_HYSTERESIS_ADMISSION_GOVERNOR,
)
from spotbot.research.rd31_regime_admission_governor import (
    admission_decision as rd31_admission_decision,
)
from spotbot.research.rd31_regime_governed_replay import (
    GOVERNOR_TRANSITION_REASONS,
    family_bucket,
    replay_rd31_policy,
)
from spotbot.research.rd33_temporal_mb_architecture import (
    CANCELLED,
    CANDIDATE_POLICIES,
    CONFIRMED,
    EXPIRED,
    MB_FIRST_RETEST_RECLAIM_WITHIN_FROZEN_72H,
    MB_ONE_BAR_BREAKOUT_LEVEL_HOLD,
    MB_ONE_BAR_POST_BREAKOUT_CONTINUATION,
    PENDING,
    POLICIES,
    RD31_REGIME_HYSTERESIS_CONTROL,
    REJECTED,
    PendingMBOrigin,
    TemporalMBDecision,
    cancel_pending_for_rs_open,
    create_pending_origin,
    evaluate_completed_bar,
    missing_confirmation_bar_decision,
    register_pending,
    remove_resolved_pending,
)

SCHEMA_VERSION: Final = "rd33-temporal-mb-portfolio-replay-v1"
STAGE: Final = "RD33_P0C_TEMPORAL_MB_PORTFOLIO_REPLAY_PRE_ECONOMIC_EXECUTION"

ENTRY_KIND_RS: Final = "RS_IMMEDIATE"
ENTRY_KIND_MB: Final = "MB_CONFIRMED"
ENTRY_KINDS: Final = (ENTRY_KIND_RS, ENTRY_KIND_MB)

TERMINAL_PENDING_STATUSES: Final = (CONFIRMED, REJECTED, EXPIRED, CANCELLED)


class RD33ReplayError(RuntimeError):
    """Raised when frozen RD33 portfolio-replay semantics are violated."""


@dataclass(frozen=True)
class EntryIntent:
    entry_kind: str
    pair: str
    signal_time: pd.Timestamp
    actual_entry_time: pd.Timestamp
    membership_rank: int
    period_id: str
    support_families: tuple[str, ...]
    target_slot_fraction: float
    atr24_at_signal: float
    capacity_source: float
    entry_market_state: str
    entry_market_context: str
    origin_key: str | None


@dataclass(frozen=True)
class RD33ReplayDiagnostics:
    governor_transition_ledger: pd.DataFrame
    pending_lifecycle_ledger: pd.DataFrame


def _utc(value: Any) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    return timestamp.tz_localize("UTC") if timestamp.tzinfo is None else timestamp.tz_convert("UTC")


def _support_families(value: Any) -> tuple[str, ...]:
    raw = tuple(item for item in str(value).split("|") if item)
    result = tuple(sorted(set(raw)))
    if not result:
        raise RD33ReplayError("signal has no support family")
    if len(raw) != len(result):
        raise RD33ReplayError("signal contains duplicate support family")
    unknown = set(result).difference(
        {
            FAMILY_MOMENTUM_BREAKOUT,
            FAMILY_RELATIVE_STRENGTH_ROTATION,
        }
    )
    if unknown:
        raise RD33ReplayError(f"unknown support families: {sorted(unknown)}")
    return result


def _portfolio_has_mb(events: pd.DataFrame) -> bool:
    if events.empty:
        return False
    if "support_families" not in events.columns:
        raise RD33ReplayError("events missing support_families")
    return any(
        FAMILY_MOMENTUM_BREAKOUT in _support_families(value)
        for value in events["support_families"].tolist()
    )


def _eligible_original_events(
    events: pd.DataFrame,
    *,
    replay_start: pd.Timestamp,
    replay_cutoff: pd.Timestamp,
) -> list[dict[str, Any]]:
    """Use the exact RD31 control eligibility window and original event clock."""
    replay_start = _utc(replay_start)
    replay_cutoff = _utc(replay_cutoff)
    rows: list[dict[str, Any]] = []
    for raw in events.to_dict(orient="records"):
        signal_time = _utc(raw["timestamp"])
        normal_entry_time = signal_time + pd.Timedelta(hours=1)
        control_max_exit_time = normal_entry_time + pd.Timedelta(hours=168)
        if normal_entry_time < replay_start or control_max_exit_time >= replay_cutoff:
            continue
        rows.append(
            {
                **raw,
                "signal_time": signal_time,
                "normal_entry_time": normal_entry_time,
                "control_max_exit_time": control_max_exit_time,
            }
        )
    rows.sort(
        key=lambda item: (
            _utc(item["normal_entry_time"]),
            int(item["membership_rank"]),
            str(item["pair"]),
        )
    )
    duplicate_keys: set[tuple[int, int, str]] = set()
    for item in rows:
        key = (
            int(_utc(item["normal_entry_time"]).value),
            int(item["membership_rank"]),
            str(item["pair"]),
        )
        if key in duplicate_keys:
            raise RD33ReplayError(
                "ambiguous duplicate original event ordering at one control clock"
            )
        duplicate_keys.add(key)
    for event_seq, item in enumerate(rows):
        item["event_seq"] = event_seq
    return rows


def build_control_governor_transition_ledger(
    *,
    universe_id: str,
    events: pd.DataFrame,
    frames: dict[str, pd.DataFrame],
    state_frame: pd.DataFrame,
    membership: list[MembershipSnapshot] | tuple[MembershipSnapshot, ...],
    replay_start: pd.Timestamp = DATA_START,
    replay_cutoff: pd.Timestamp = DATA_CUTOFF,
) -> tuple[list[dict[str, Any]], pd.DataFrame]:
    """Precompute the sole RD31 governor path on original signal clocks.

    Candidate confirmation code never calls the governor. All later MB pending
    decisions consume the admission decision frozen in this ledger.
    """
    replay_start = _utc(replay_start)
    replay_cutoff = _utc(replay_cutoff)
    if replay_start >= replay_cutoff:
        raise RD33ReplayError("invalid replay window")

    scheduled = _eligible_original_events(
        events,
        replay_start=replay_start,
        replay_cutoff=replay_cutoff,
    )
    lookups = {pair: fast_lookup(frame) for pair, frame in frames.items()}
    state_lookup = build_state_lookup(state_frame)

    governor_state = OPEN
    rows: list[dict[str, Any]] = []
    for item in scheduled:
        signal_time = _utc(item["signal_time"])
        pair = str(item["pair"])
        support = _support_families(item["support_families"])

        (
            _members,
            _returns,
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

        prior_state = governor_state
        governed = rd31_admission_decision(
            policy_id=REGIME_HYSTERESIS_ADMISSION_GOVERNOR,
            support_families=support,
            btc_state=entry_state,
            market_context=entry_context,
            governor_prior_state=prior_state,
        )
        next_state = governed.governor_next_state
        if next_state not in GOVERNOR_STATES:
            raise RD33ReplayError("control governor returned invalid next state")
        if governed.transition_reason not in GOVERNOR_TRANSITION_REASONS:
            raise RD33ReplayError("control governor returned unknown transition reason")
        if governed.governor_prior_state != prior_state:
            raise RD33ReplayError("control governor prior-state mismatch")

        admission = governed.decision
        rows.append(
            {
                "event_seq": int(item["event_seq"]),
                "universe_id": universe_id,
                "pair": pair,
                "signal_time": signal_time,
                "normal_entry_time": _utc(item["normal_entry_time"]),
                "membership_rank": int(item["membership_rank"]),
                "support_families": "|".join(support),
                "entry_market_state": entry_state,
                "entry_market_context": entry_context.context,
                "breakout_reference": (
                    float(breakout_reference) if breakout_reference is not None else math.nan
                ),
                "governor_prior_state": prior_state,
                "governor_next_state": next_state,
                "governor_changed": prior_state != next_state,
                "transition_reason": governed.transition_reason,
                "admit_position": bool(admission.admit_position),
                "target_slot_fraction": float(admission.target_slot_fraction),
                "admission_reason": admission.reason,
                "admissible_families": "|".join(admission.admissible_families),
            }
        )
        governor_state = next_state

    ledger = pd.DataFrame.from_records(rows)
    if len(ledger) != len(scheduled):
        raise RD33ReplayError("control governor ledger cardinality drifted")
    return scheduled, ledger


def _temporal_counter_defaults(events: pd.DataFrame) -> dict[str, int]:
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
        "mb_pending_registered": 0,
        "mb_pending_duplicate_suppressed": 0,
        "mb_pending_cancelled_by_rs_open": 0,
        "mb_confirmation_checks": 0,
        "mb_confirmed": 0,
        "mb_rejected": 0,
        "mb_expired": 0,
        "mb_confirmed_entry_attempts": 0,
        "mb_confirmed_entries": 0,
        "mb_confirmed_entry_failures": 0,
        "delayed_entry_cutoff_rejection": 0,
        "rs_immediate_entry_attempts": 0,
        "rs_immediate_entries": 0,
    }
    for reason in GOVERNOR_TRANSITION_REASONS:
        counters[f"governor_reason_{reason}"] = 0
    for context in ("SUPPORTIVE", "MIXED", "STRESSED", "UNAVAILABLE"):
        for family in ("MB", "RS", "OVERLAP"):
            counters[f"admission_{context}_{family}_ADMIT"] = 0
            counters[f"admission_{context}_{family}_SUPPRESS"] = 0
    return counters


def _augment_temporal_counters(
    baseline: dict[str, int],
    events: pd.DataFrame,
) -> dict[str, int]:
    result = _temporal_counter_defaults(events)
    for key, value in baseline.items():
        if isinstance(value, (int, np.integer)):
            result[key] = int(value)
    return result


def _relabel_outputs(
    *,
    requested_policy_id: str,
    trades: pd.DataFrame,
    daily: pd.DataFrame,
    metrics: dict[str, Any],
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    output_metrics = dict(metrics)
    output_metrics["policy_id"] = requested_policy_id

    def relabel(frame: pd.DataFrame) -> pd.DataFrame:
        result = frame.copy()
        if len(result) and "policy_id" not in result.columns:
            raise RD33ReplayError("delegated replay output missing policy_id")
        if len(result):
            result["policy_id"] = requested_policy_id
        return result

    return relabel(trades), relabel(daily), output_metrics


def _admission_from_ledger(row: pd.Series) -> AdmissionDecision:
    families = tuple(item for item in str(row["admissible_families"]).split("|") if item)
    return AdmissionDecision(
        record_signal=True,
        admit_position=bool(row["admit_position"]),
        target_slot_fraction=float(row["target_slot_fraction"]),
        reason=str(row["admission_reason"]),
        admissible_families=families,
    )


def _pending_row(
    *,
    policy_id: str,
    universe_id: str,
    portfolio_id: str,
    origin: PendingMBOrigin,
    status: str,
    reason: str,
    event_time: pd.Timestamp,
    actual_entry_time: pd.Timestamp | None = None,
    observed_low: float | None = None,
    observed_close: float | None = None,
) -> dict[str, Any]:
    return {
        "policy_id": policy_id,
        "portfolio_id": portfolio_id,
        "universe_id": universe_id,
        "pair": origin.pair,
        "origin_key": origin.origin_key,
        "signal_time": origin.signal_time,
        "event_time": _utc(event_time),
        "status": status,
        "reason": reason,
        "actual_entry_time": actual_entry_time,
        "observed_low": observed_low,
        "observed_close": observed_close,
    }


def _intent_from_rs(
    *,
    item: dict[str, Any],
    ledger_row: pd.Series,
    capacity_source: float,
) -> EntryIntent:
    return EntryIntent(
        entry_kind=ENTRY_KIND_RS,
        pair=str(item["pair"]),
        signal_time=_utc(item["signal_time"]),
        actual_entry_time=_utc(item["normal_entry_time"]),
        membership_rank=int(item["membership_rank"]),
        period_id=str(item["period_id"]),
        support_families=(FAMILY_RELATIVE_STRENGTH_ROTATION,),
        target_slot_fraction=float(ledger_row["target_slot_fraction"]),
        atr24_at_signal=float(item["atr24_at_signal"]),
        capacity_source=float(capacity_source),
        entry_market_state=str(ledger_row["entry_market_state"]),
        entry_market_context=str(ledger_row["entry_market_context"]),
        origin_key=None,
    )


def _intent_from_confirmed_mb(
    *,
    origin: PendingMBOrigin,
    confirmation: TemporalMBDecision,
    atr24_at_signal: float,
    capacity_source: float,
    entry_market_state: str,
    entry_market_context: str,
) -> EntryIntent:
    if confirmation.status != CONFIRMED or confirmation.actual_entry_time is None:
        raise RD33ReplayError("MB entry intent requires confirmed temporal decision")
    return EntryIntent(
        entry_kind=ENTRY_KIND_MB,
        pair=origin.pair,
        signal_time=origin.signal_time,
        actual_entry_time=_utc(confirmation.actual_entry_time),
        membership_rank=origin.membership_rank,
        period_id=origin.period_id,
        support_families=(FAMILY_MOMENTUM_BREAKOUT,),
        target_slot_fraction=origin.target_slot_fraction,
        atr24_at_signal=float(atr24_at_signal),
        capacity_source=float(capacity_source),
        entry_market_state=entry_market_state,
        entry_market_context=entry_market_context,
        origin_key=origin.origin_key,
    )


def _execute_entry_intent(
    *,
    intent: EntryIntent,
    timestamp: pd.Timestamp,
    policy_id: str,
    portfolio_id: str,
    universe_id: str,
    cost_multiplier: float,
    replay_cutoff: pd.Timestamp,
    side_cost: float,
    frames: dict[str, pd.DataFrame],
    lookups: dict[str, dict[int, int]],
    positions: dict[str, ReplayPosition],
    cash: float,
    counters: dict[str, int],
) -> tuple[float, bool, str]:
    timestamp = _utc(timestamp)
    if intent.entry_kind not in ENTRY_KINDS:
        raise RD33ReplayError(f"unknown entry intent kind: {intent.entry_kind}")
    if intent.actual_entry_time != timestamp:
        raise RD33ReplayError("entry intent executed off its frozen next-open clock")

    if intent.entry_kind == ENTRY_KIND_RS:
        counters["rs_immediate_entry_attempts"] += 1
    else:
        counters["mb_confirmed_entry_attempts"] += 1

    if intent.pair in positions:
        counters["same_pair_open"] += 1
        if intent.entry_kind == ENTRY_KIND_MB:
            counters["mb_confirmed_entry_failures"] += 1
        return cash, False, "SAME_PAIR_OPEN"

    entry_bar = _bar_at(intent.pair, timestamp, frames, lookups)
    max_exit_time = timestamp + pd.Timedelta(hours=168)
    if max_exit_time >= replay_cutoff:
        counters["delayed_entry_cutoff_rejection"] += 1
        counters["missing_exit_bar_precheck"] += 1
        if intent.entry_kind == ENTRY_KIND_MB:
            counters["mb_confirmed_entry_failures"] += 1
        return cash, False, "MAX_EXIT_OUTSIDE_REPLAY_CUTOFF"

    exit_bar = _bar_at(intent.pair, max_exit_time, frames, lookups)
    if entry_bar is None:
        counters["missing_entry_bar"] += 1
        if intent.entry_kind == ENTRY_KIND_MB:
            counters["mb_confirmed_entry_failures"] += 1
        return cash, False, "MISSING_ENTRY_BAR"
    if exit_bar is None:
        counters["missing_exit_bar_precheck"] += 1
        if intent.entry_kind == ENTRY_KIND_MB:
            counters["mb_confirmed_entry_failures"] += 1
        return cash, False, "MISSING_EXIT_BAR_PRECHECK"

    capacity_source = float(intent.capacity_source)
    if not math.isfinite(capacity_source) or capacity_source <= 0.0:
        counters["capacity_unavailable"] += 1
        if intent.entry_kind == ENTRY_KIND_MB:
            counters["mb_confirmed_entry_failures"] += 1
        return cash, False, "CAPACITY_UNAVAILABLE"

    if len(positions) >= MAXIMUM_POSITIONS:
        counters["position_slots_full"] += 1
        if intent.entry_kind == ENTRY_KIND_MB:
            counters["mb_confirmed_entry_failures"] += 1
        return cash, False, "POSITION_SLOTS_FULL"

    sizing = size_entry_from_marks(
        cash=cash,
        marked_notionals=_marked_notionals(positions),
        target_slot_fraction=float(intent.target_slot_fraction),
        capacity_source=capacity_source,
        side_cost=side_cost,
    )
    if not sizing.feasible:
        if sizing.reason == "GROSS_LIMIT_NO_ROOM":
            counters["gross_limit_rejection"] += 1
        elif sizing.reason == "CAPACITY_UNAVAILABLE":
            counters["capacity_unavailable"] += 1
        if intent.entry_kind == ENTRY_KIND_MB:
            counters["mb_confirmed_entry_failures"] += 1
        return cash, False, sizing.reason
    if sizing.capacity_capped:
        counters["capacity_capped_entries"] += 1
    if sizing.cash_capped:
        counters["cash_capped_entries"] += 1

    entry_price = float(entry_bar["open"])
    if not math.isfinite(entry_price) or entry_price <= 0.0:
        raise RD33ReplayError("invalid entry open price")
    atr = float(intent.atr24_at_signal)
    if not math.isfinite(atr) or atr <= 0.0:
        raise RD33ReplayError("invalid entry ATR")

    notional = float(sizing.notional)
    quantity = notional / entry_price
    entry_cost = notional * side_cost
    new_cash = cash - notional - entry_cost
    if new_cash < -1e-7:
        raise RD33ReplayError("negative cash after entry")
    new_cash = max(new_cash, 0.0)

    specialist = new_specialist_position(
        pair=intent.pair,
        entry_time=timestamp,
        entry_price=entry_price,
        atr24_at_signal=atr,
        support_families=intent.support_families,
    )
    positions[intent.pair] = ReplayPosition(
        pair=intent.pair,
        signal_time=intent.signal_time,
        entry_time=timestamp,
        max_exit_time=max_exit_time,
        entry_price=entry_price,
        quantity=quantity,
        entry_notional=notional,
        entry_cost=entry_cost,
        membership_rank=intent.membership_rank,
        support_families=intent.support_families,
        period_id=intent.period_id,
        atr24_at_signal=atr,
        specialist=specialist,
        entry_market_state=intent.entry_market_state,
        entry_market_context=intent.entry_market_context,
        last_mark=entry_price,
    )
    counters["admitted_entries"] += 1
    if intent.entry_kind == ENTRY_KIND_RS:
        counters["rs_immediate_entries"] += 1
    else:
        counters["mb_confirmed_entries"] += 1
    return new_cash, True, "ENTRY_OPENED"


def replay_rd33_policy(
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
    RD33ReplayDiagnostics,
]:
    """Replay one frozen RD33 policy without loading any market data itself."""
    if policy_id not in POLICIES:
        raise RD33ReplayError(f"unknown policy: {policy_id}")
    if cost_multiplier not in COST_MULTIPLIERS:
        raise RD33ReplayError("unsupported cost multiplier")

    replay_start = _utc(replay_start)
    replay_cutoff = _utc(replay_cutoff)
    if replay_start >= replay_cutoff:
        raise RD33ReplayError("invalid replay window")

    scheduled, governor_ledger = build_control_governor_transition_ledger(
        universe_id=universe_id,
        events=events,
        frames=frames,
        state_frame=state_frame,
        membership=membership,
        replay_start=replay_start,
        replay_cutoff=replay_cutoff,
    )
    diagnostics_empty = RD33ReplayDiagnostics(
        governor_transition_ledger=governor_ledger.copy(),
        pending_lifecycle_ledger=pd.DataFrame(),
    )

    if policy_id == RD31_REGIME_HYSTERESIS_CONTROL:
        trades, daily, metrics, counters = replay_rd31_policy(
            policy_id=REGIME_HYSTERESIS_ADMISSION_GOVERNOR,
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
        trades, daily, metrics = _relabel_outputs(
            requested_policy_id=policy_id,
            trades=trades,
            daily=daily,
            metrics=metrics,
        )
        return (
            trades,
            daily,
            metrics,
            _augment_temporal_counters(counters, events),
            diagnostics_empty,
        )

    if policy_id not in CANDIDATE_POLICIES:
        raise RD33ReplayError(f"unknown candidate policy: {policy_id}")

    # Strong RS invariant: when the portfolio contains no MB component, use
    # the exact frozen RD31 replay. Only the policy namespace is relabelled.
    if not _portfolio_has_mb(events):
        trades, daily, metrics, counters = replay_rd31_policy(
            policy_id=REGIME_HYSTERESIS_ADMISSION_GOVERNOR,
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
        trades, daily, metrics = _relabel_outputs(
            requested_policy_id=policy_id,
            trades=trades,
            daily=daily,
            metrics=metrics,
        )
        return (
            trades,
            daily,
            metrics,
            _augment_temporal_counters(counters, events),
            diagnostics_empty,
        )

    lookups = {pair: fast_lookup(frame) for pair, frame in frames.items()}
    state_lookup = build_state_lookup(state_frame)
    side_cost = BASE_ROUND_TRIP_COST * float(cost_multiplier) / 2.0

    event_schedule: dict[int, list[dict[str, Any]]] = {}
    for item in scheduled:
        event_schedule.setdefault(
            int(_utc(item["normal_entry_time"]).value),
            [],
        ).append(item)

    ledger_by_seq = {int(row.event_seq): row for row in governor_ledger.itertuples(index=False)}
    if len(ledger_by_seq) != len(governor_ledger):
        raise RD33ReplayError("duplicate event_seq in governor ledger")

    cash = INITIAL_EQUITY
    positions: dict[str, ReplayPosition] = {}
    pending_by_pair: dict[str, PendingMBOrigin] = {}
    pending_origin_meta: dict[str, dict[str, Any]] = {}
    pending_rows: list[dict[str, Any]] = []
    trades: list[dict[str, Any]] = []
    daily_rows: list[dict[str, Any]] = []
    hourly_equity_values: list[float] = []
    counters = _temporal_counter_defaults(events)
    governor_state = OPEN

    for timestamp in pd.date_range(
        replay_start,
        replay_cutoff,
        freq="h",
        inclusive="left",
    ):
        timestamp = _utc(timestamp)

        # Exact frozen RD31 exit ordering and lifecycle, anchored to actual
        # entry time for delayed MB positions.
        for pair in sorted(list(positions)):
            position = positions[pair]
            bar = _bar_at(pair, timestamp, frames, lookups)
            prior_time = timestamp - pd.Timedelta(hours=1)
            prior_bar = _bar_at(pair, prior_time, frames, lookups)
            if bar is None or prior_bar is None:
                raise RD33ReplayError(f"open-position bar missing: {pair} {timestamp}")

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
                    raise RD33ReplayError("scheduled exit missing fill details")
                reason = scheduled_exit.exit_reason
                if reason == TIME_FAIL_EXIT_REASON:
                    counters["time_failure_exits"] += 1
                elif reason == MAX_HOLD_EXIT_REASON:
                    counters["max_hold_exits"] += 1
                else:
                    raise RD33ReplayError(
                        f"RD33 lifecycle emitted prohibited exit reason: {reason}"
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
            bar = _bar_at(position.pair, timestamp, frames, lookups)
            if bar is not None:
                position.last_mark = float(bar["open"])

        rs_intents: list[EntryIntent] = []

        # Consume the immutable precomputed control ledger. No candidate
        # confirmation or portfolio state can change this sequence.
        current_events = event_schedule.get(int(timestamp.value), [])
        for item in current_events:
            event_seq = int(item["event_seq"])
            raw_row = ledger_by_seq.get(event_seq)
            if raw_row is None:
                raise RD33ReplayError("missing control governor ledger row")
            row = pd.Series(raw_row._asdict())

            if str(row["governor_prior_state"]) != governor_state:
                raise RD33ReplayError(
                    "candidate governor state diverged from precomputed control ledger"
                )
            governor_state = str(row["governor_next_state"])
            if governor_state not in GOVERNOR_STATES:
                raise RD33ReplayError("candidate consumed invalid governor state")
            counters[f"governor_state_{governor_state}"] += 1
            transition_reason = str(row["transition_reason"])
            reason_key = "governor_reason_" + transition_reason
            if reason_key not in counters:
                raise RD33ReplayError("candidate consumed unknown transition reason")
            counters[reason_key] += 1
            if bool(row["governor_changed"]):
                counters["governor_transition_count"] += 1

            support = _support_families(item["support_families"])
            bucket = family_bucket(support)
            admission = _admission_from_ledger(row)
            outcome = "ADMIT" if admission.admit_position else "SUPPRESS"
            context = str(row["entry_market_context"])
            counters[f"admission_{context}_{bucket}_{outcome}"] += 1

            if not admission.admit_position:
                counters["suppressed_entries"] += 1
                if governor_state == LOCKED:
                    counters[f"governor_locked_suppressions_{bucket}"] += 1
                continue

            admissible = set(admission.admissible_families)

            if FAMILY_MOMENTUM_BREAKOUT in admissible:
                signal_bar = _bar_at(
                    str(item["pair"]),
                    _utc(item["signal_time"]),
                    frames,
                    lookups,
                )
                if signal_bar is None:
                    raise RD33ReplayError("signal bar missing while creating MB pending origin")
                breakout_reference = float(row["breakout_reference"])
                if not math.isfinite(breakout_reference) or breakout_reference <= 0.0:
                    raise RD33ReplayError("control ledger missing finite MB breakout reference")
                origin = create_pending_origin(
                    policy_id=policy_id,
                    universe_id=universe_id,
                    pair=str(item["pair"]),
                    signal_time=_utc(item["signal_time"]),
                    breakout_reference=breakout_reference,
                    signal_close=float(signal_bar["close"]),
                    membership_rank=int(item["membership_rank"]),
                    period_id=str(item["period_id"]),
                    support_families=support,
                    rd31_decision=admission,
                )
                pending_by_pair, registration = register_pending(
                    pending_by_pair,
                    origin,
                )
                if registration.accepted:
                    counters["mb_pending_registered"] += 1
                    pending_origin_meta[origin.origin_key] = {
                        "atr24_at_signal": float(item["atr24_at_signal"]),
                        "entry_market_state": str(row["entry_market_state"]),
                        "entry_market_context": str(row["entry_market_context"]),
                    }
                    pending_rows.append(
                        _pending_row(
                            policy_id=policy_id,
                            universe_id=universe_id,
                            portfolio_id=portfolio_id,
                            origin=origin,
                            status=PENDING,
                            reason=registration.reason,
                            event_time=timestamp,
                        )
                    )
                else:
                    counters["mb_pending_duplicate_suppressed"] += 1

            if FAMILY_RELATIVE_STRENGTH_ROTATION in admissible:
                signal_bar = _bar_at(
                    str(item["pair"]),
                    _utc(item["signal_time"]),
                    frames,
                    lookups,
                )
                if signal_bar is None:
                    raise RD33ReplayError("signal bar missing while creating immediate RS intent")
                rs_intents.append(
                    _intent_from_rs(
                        item=item,
                        ledger_row=row,
                        capacity_source=float(signal_bar["trailing_24h_quote_turnover_proxy"]),
                    )
                )

        # RS has deterministic priority at the same open. This preserves the
        # frozen RS path; an actual RS open cancels same-pair pending MB.
        rs_intents.sort(
            key=lambda intent: (
                intent.membership_rank,
                intent.pair,
            )
        )
        for intent in rs_intents:
            cash, opened, _reason = _execute_entry_intent(
                intent=intent,
                timestamp=timestamp,
                policy_id=policy_id,
                portfolio_id=portfolio_id,
                universe_id=universe_id,
                cost_multiplier=cost_multiplier,
                replay_cutoff=replay_cutoff,
                side_cost=side_cost,
                frames=frames,
                lookups=lookups,
                positions=positions,
                cash=cash,
                counters=counters,
            )
            if opened:
                prior_origin = pending_by_pair.get(intent.pair)
                pending_by_pair, cancelled = cancel_pending_for_rs_open(
                    pending_by_pair,
                    pair=intent.pair,
                )
                if cancelled is not None:
                    counters["mb_pending_cancelled_by_rs_open"] += 1
                    if prior_origin is None:
                        raise RD33ReplayError("RS cancellation lost pending origin")
                    pending_rows.append(
                        _pending_row(
                            policy_id=policy_id,
                            universe_id=universe_id,
                            portfolio_id=portfolio_id,
                            origin=prior_origin,
                            status=CANCELLED,
                            reason=cancelled.reason,
                            event_time=timestamp,
                        )
                    )
                    pending_origin_meta.pop(prior_origin.origin_key, None)

        mb_intents: list[EntryIntent] = []
        prior_time = timestamp - pd.Timedelta(hours=1)

        # Evaluate only bars that are completed before this open. Pending MB
        # never calls the governor and cannot create another transition.
        for pair in sorted(list(pending_by_pair)):
            origin = pending_by_pair[pair]
            age_float = (prior_time - origin.signal_time) / pd.Timedelta(hours=1)
            if not float(age_float).is_integer():
                raise RD33ReplayError("pending MB age left the 1h clock")
            age_hours = int(age_float)
            if age_hours < 1:
                continue
            if (
                origin.policy_id
                in (
                    MB_ONE_BAR_BREAKOUT_LEVEL_HOLD,
                    MB_ONE_BAR_POST_BREAKOUT_CONTINUATION,
                )
                and age_hours > 1
            ):
                raise RD33ReplayError("one-bar pending survived beyond its frozen confirmation bar")
            if origin.policy_id == MB_FIRST_RETEST_RECLAIM_WITHIN_FROZEN_72H and age_hours > 72:
                raise RD33ReplayError("retest pending survived beyond 72h")

            confirmation_bar = _bar_at(
                pair,
                prior_time,
                frames,
                lookups,
            )
            counters["mb_confirmation_checks"] += 1
            if confirmation_bar is None:
                decision = missing_confirmation_bar_decision(
                    origin,
                    expected_completed_time=prior_time,
                )
            else:
                decision = evaluate_completed_bar(
                    origin,
                    completed_time=prior_time,
                    low=float(confirmation_bar["low"]),
                    close=float(confirmation_bar["close"]),
                )

            pending_rows.append(
                _pending_row(
                    policy_id=policy_id,
                    universe_id=universe_id,
                    portfolio_id=portfolio_id,
                    origin=origin,
                    status=decision.status,
                    reason=decision.reason,
                    event_time=prior_time,
                    actual_entry_time=decision.actual_entry_time,
                    observed_low=decision.observed_low,
                    observed_close=decision.observed_close,
                )
            )

            if decision.status == PENDING:
                continue

            if decision.status == CONFIRMED:
                counters["mb_confirmed"] += 1
                if decision.actual_entry_time != timestamp:
                    raise RD33ReplayError("confirmed MB did not map to current next-open timestamp")
                if confirmation_bar is None:
                    raise RD33ReplayError("confirmed MB cannot originate from missing bar")
                meta = pending_origin_meta.get(origin.origin_key)
                if meta is None:
                    raise RD33ReplayError("pending origin metadata disappeared")
                mb_intents.append(
                    _intent_from_confirmed_mb(
                        origin=origin,
                        confirmation=decision,
                        atr24_at_signal=float(meta["atr24_at_signal"]),
                        capacity_source=float(
                            confirmation_bar["trailing_24h_quote_turnover_proxy"]
                        ),
                        entry_market_state=str(meta["entry_market_state"]),
                        entry_market_context=str(meta["entry_market_context"]),
                    )
                )
            elif decision.status == REJECTED:
                counters["mb_rejected"] += 1
            elif decision.status == EXPIRED:
                counters["mb_expired"] += 1
            else:
                raise RD33ReplayError(f"unexpected terminal pending status: {decision.status}")

            pending_by_pair = remove_resolved_pending(
                pending_by_pair,
                origin=origin,
            )
            pending_origin_meta.pop(origin.origin_key, None)

        mb_intents.sort(
            key=lambda intent: (
                intent.membership_rank,
                intent.pair,
            )
        )
        for intent in mb_intents:
            cash, _opened, _reason = _execute_entry_intent(
                intent=intent,
                timestamp=timestamp,
                policy_id=policy_id,
                portfolio_id=portfolio_id,
                universe_id=universe_id,
                cost_multiplier=cost_multiplier,
                replay_cutoff=replay_cutoff,
                side_cost=side_cost,
                frames=frames,
                lookups=lookups,
                positions=positions,
                cash=cash,
                counters=counters,
            )

        for position in positions.values():
            bar = _bar_at(
                position.pair,
                timestamp,
                frames,
                lookups,
            )
            if bar is None:
                raise RD33ReplayError(f"position mark bar missing: {position.pair} {timestamp}")
            position.specialist = apply_completed_high(
                position.specialist,
                completed_high=float(bar["high"]),
            )
            position.last_mark = float(bar["close"])

        gross_close = sum(position.quantity * position.last_mark for position in positions.values())
        equity_close = cash + gross_close
        if equity_close < -1e-7:
            raise RD33ReplayError("negative equity observed")
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
                    "pending_mb_count": len(pending_by_pair),
                }
            )

    if positions:
        raise RD33ReplayError("open positions remained at replay cutoff")
    if pending_by_pair:
        raise RD33ReplayError("pending MB origins remained at replay cutoff")
    if pending_origin_meta:
        raise RD33ReplayError("pending MB metadata remained at replay cutoff")

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
        }
    )
    diagnostics = RD33ReplayDiagnostics(
        governor_transition_ledger=governor_ledger.copy(),
        pending_lifecycle_ledger=pd.DataFrame.from_records(pending_rows),
    )
    return trade_frame, daily_frame, metrics, counters, diagnostics


def governor_ledger_parity(
    left: pd.DataFrame,
    right: pd.DataFrame,
) -> dict[str, Any]:
    """Exact parity check for candidate/control governor event clocks."""
    keys = (
        "event_seq",
        "universe_id",
        "pair",
        "signal_time",
        "normal_entry_time",
        "membership_rank",
        "support_families",
        "entry_market_state",
        "entry_market_context",
        "governor_prior_state",
        "governor_next_state",
        "governor_changed",
        "transition_reason",
        "admit_position",
        "admission_reason",
        "admissible_families",
    )
    numeric = ("breakout_reference", "target_slot_fraction")

    a = left.sort_values("event_seq", kind="stable").reset_index(drop=True)
    b = right.sort_values("event_seq", kind="stable").reset_index(drop=True)
    if len(a) != len(b):
        raise RD33ReplayError(f"governor ledger cardinality mismatch: {len(a)} != {len(b)}")
    for column in keys:
        if column not in a.columns or column not in b.columns:
            raise RD33ReplayError(f"governor ledger missing parity column: {column}")
        if a[column].astype(str).tolist() != b[column].astype(str).tolist():
            raise RD33ReplayError(f"governor ledger exact-key mismatch: {column}")

    maximum_error = 0.0
    for column in numeric:
        left_values = pd.to_numeric(a[column], errors="coerce").astype(float)
        right_values = pd.to_numeric(b[column], errors="coerce").astype(float)
        both_nan = left_values.isna() & right_values.isna()
        error = (left_values - right_values).abs()
        error = error.mask(both_nan, 0.0)
        if bool(error.isna().any()):
            raise RD33ReplayError(f"governor ledger one-sided NaN mismatch: {column}")
        maximum = float(error.max()) if len(error) else 0.0
        maximum_error = max(maximum_error, maximum)
        tolerance = 1e-12 * (1.0 + left_values.abs().fillna(0.0))
        if bool((error > tolerance).any()):
            raise RD33ReplayError(f"governor ledger numeric mismatch: {column}")
    return {
        "passed": True,
        "row_count": len(a),
        "maximum_numeric_absolute_error": maximum_error,
    }


def contract_summary() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "stage": STAGE,
        "policies": list(POLICIES),
        "candidate_policies": list(CANDIDATE_POLICIES),
        "control_delegate": "EXACT_RD31_HYSTERESIS_REPLAY",
        "rs_only_candidate_delegate": ("EXACT_RD31_HYSTERESIS_REPLAY_POLICY_LABEL_ONLY"),
        "candidate_governor_source": (
            "PRECOMPUTED_EXACT_RD31_CONTROL_LEDGER_ON_ORIGINAL_SIGNAL_CLOCK"
        ),
        "candidate_confirmation_calls_governor": False,
        "candidate_confirmation_can_mutate_governor": False,
        "second_governor_transition_on_confirmation": False,
        "governor_transition_ledger_emitted": True,
        "original_event_governor_transition_before_portfolio_constraints": True,
        "rs_same_open_priority_over_confirmed_mb": True,
        "actual_rs_open_cancels_same_pair_pending_mb": True,
        "pending_consumes_position_slot": False,
        "pending_reserves_cash": False,
        "pending_reserves_gross_exposure": False,
        "confirmed_mb_capacity_source": (
            "TRAILING_24H_QUOTE_TURNOVER_PROXY_FROM_COMPLETED_CONFIRMATION_BAR"
        ),
        "confirmed_mb_entry_fill": "NEXT_1H_OPEN_AFTER_CONFIRMATION",
        "delayed_mb_exit_lifecycle_anchor": "ACTUAL_DELAYED_ENTRY",
        "time_failure_hours": 72,
        "maximum_hold_hours": 168,
        "profit_giveback": False,
        "replacement": False,
        "forced_regime_exit": False,
        "parameter_grid_search": False,
        "pair_blacklist": False,
        "calendar_year_feature": False,
        "economic_execution_performed": False,
        "real_market_data_loader_present": False,
        "raw_market_data_loaded": False,
        "candidate_results_observed": False,
        "2024_accessed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
    }
