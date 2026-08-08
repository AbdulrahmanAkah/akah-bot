"""RD32 MB signal-quality portfolio replay.

Pre-economic replay semantics only. No raw-data loader and no execution at import
time. The RD31 Hysteresis control delegates exactly to the frozen RD31 replay.
Candidates preserve the RD31 governor transition and lifecycle, then apply only
the preregistered MB quality veto.
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
    FAMILY_MOMENTUM_BREAKOUT,
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
    size_entry_from_marks,
)
from spotbot.research.rd31_regime_admission_governor import (
    GOVERNOR_STATES,
    LOCKED,
    OPEN,
)
from spotbot.research.rd31_regime_governed_replay import (
    GOVERNOR_TRANSITION_REASONS,
    family_bucket,
    replay_rd31_policy,
)
from spotbot.research.rd32_mb_signal_quality_admission import (
    MB_BREADTH_ACCELERATION_CONFIRMATION,
    MB_CROSS_SECTIONAL_BREAKOUT_LEADER,
    MB_RELATIVE_STRENGTH_LEADER_CONFIRMATION,
    POLICIES,
    RD31_REGIME_HYSTERESIS_CONTROL,
    MBQualityEvidence,
)
from spotbot.research.rd32_mb_signal_quality_admission import (
    admission_decision as rd32_admission_decision,
)

SCHEMA_VERSION: Final = "rd32-mb-signal-quality-portfolio-replay-v1"

CANDIDATE_POLICIES: Final = (
    MB_CROSS_SECTIONAL_BREAKOUT_LEADER,
    MB_BREADTH_ACCELERATION_CONFIRMATION,
    MB_RELATIVE_STRENGTH_LEADER_CONFIRMATION,
)


class RD32ReplayError(RuntimeError):
    pass


def _utc(value: Any) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    return timestamp.tz_localize("UTC") if timestamp.tzinfo is None else timestamp.tz_convert("UTC")


def _support_families(value: Any) -> tuple[str, ...]:
    values = tuple(item for item in str(value).split("|") if item)
    result = tuple(sorted(set(values)))
    if not result:
        raise RD32ReplayError("signal has no support family")
    if len(values) != len(result):
        raise RD32ReplayError("signal contains duplicate support family")
    return result


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
        "mb_quality_evaluated": 0,
        "mb_quality_retained": 0,
        "mb_quality_vetoed": 0,
        "mb_quality_not_applicable": 0,
        "mb_veto_full_suppression": 0,
        "mb_veto_overlap_rs_retained": 0,
    }
    for reason in GOVERNOR_TRANSITION_REASONS:
        counters[f"governor_reason_{reason}"] = 0
    for context in ("SUPPORTIVE", "MIXED", "STRESSED", "UNAVAILABLE"):
        for family in ("MB", "RS", "OVERLAP"):
            counters[f"admission_{context}_{family}_ADMIT"] = 0
            counters[f"admission_{context}_{family}_SUPPRESS"] = 0
    return counters


def _normalize_raw_focus_events(
    raw_focus_events: pd.DataFrame,
    *,
    universe_id: str,
) -> pd.DataFrame:
    required = {
        "universe_id",
        "timestamp",
        "family_id",
        "pair",
        "candidate_rank",
    }
    missing = sorted(required.difference(raw_focus_events.columns))
    if missing:
        raise RD32ReplayError(f"raw focus ledger missing columns: {missing}")
    frame = raw_focus_events.loc[raw_focus_events["universe_id"].astype(str) == universe_id].copy()
    frame["timestamp"] = pd.to_datetime(
        frame["timestamp"],
        utc=True,
        errors="raise",
    )
    frame["candidate_rank"] = pd.to_numeric(
        frame["candidate_rank"],
        errors="raise",
    ).astype(int)
    if bool((frame["candidate_rank"] <= 0).any()):
        raise RD32ReplayError("raw focus candidate rank must be positive")
    duplicate = frame.duplicated(
        ["timestamp", "family_id", "pair"],
        keep=False,
    )
    if bool(duplicate.any()):
        raise RD32ReplayError("raw focus ledger has duplicate pair-time-family")
    return frame


def build_mb_candidate_rank_lookup(
    raw_focus_events: pd.DataFrame,
    *,
    universe_id: str,
) -> dict[tuple[int, str], int]:
    """Freeze RD26 MB candidate_rank as the sole breakout-leader rank source."""
    frame = _normalize_raw_focus_events(
        raw_focus_events,
        universe_id=universe_id,
    )
    frame = frame.loc[frame["family_id"].astype(str) == FAMILY_MOMENTUM_BREAKOUT].copy()
    lookup: dict[tuple[int, str], int] = {}
    for row in frame.itertuples(index=False):
        key = (
            int(pd.Timestamp(row.timestamp).value),
            str(row.pair),
        )
        rank = int(row.candidate_rank)
        if key in lookup:
            raise RD32ReplayError("duplicate MB candidate rank key")
        lookup[key] = rank
    return lookup


def quality_evidence_for_event(
    *,
    policy_id: str,
    universe_id: str,
    pair: str,
    signal_time: pd.Timestamp,
    current_members: tuple[tuple[str, int], ...],
    current_returns: dict[str, float | None],
    membership: list[MembershipSnapshot] | tuple[MembershipSnapshot, ...],
    frames: dict[str, pd.DataFrame],
    lookups: dict[str, dict[int, int]],
    state_lookup: dict[int, str],
    mb_candidate_rank_lookup: dict[tuple[int, str], int],
) -> MBQualityEvidence | None:
    if policy_id == RD31_REGIME_HYSTERESIS_CONTROL:
        return None

    signal_time = _utc(signal_time)

    if policy_id == MB_CROSS_SECTIONAL_BREAKOUT_LEADER:
        key = (int(signal_time.value), pair)
        rank = mb_candidate_rank_lookup.get(key)
        if rank is None:
            raise RD32ReplayError(f"frozen MB candidate rank missing: {pair} {signal_time}")
        return MBQualityEvidence(
            mb_candidate_rank=rank,
        )

    if policy_id == MB_BREADTH_ACCELERATION_CONFIRMATION:
        previous_time = signal_time - pd.Timedelta(hours=1)
        try:
            (
                _previous_members,
                _previous_returns,
                _previous_state,
                previous_context,
            ) = causal_context_at(
                universe_id=universe_id,
                completed_time=previous_time,
                membership=membership,
                frames=frames,
                lookups=lookups,
                state_lookup=state_lookup,
            )
            prior_breadth = previous_context.breadth_median_return_72h
        except Exception:
            prior_breadth = None
        return MBQualityEvidence(
            prior_breadth_median_return_72h=prior_breadth,
        )

    if policy_id == MB_RELATIVE_STRENGTH_LEADER_CONFIRMATION:
        return MBQualityEvidence(
            current_members=current_members,
            current_return_72h_by_pair=current_returns,
        )

    raise RD32ReplayError(f"unknown RD32 policy: {policy_id}")


def replay_rd32_policy(
    *,
    policy_id: str,
    portfolio_id: str,
    universe_id: str,
    cost_multiplier: float,
    events: pd.DataFrame,
    raw_focus_events: pd.DataFrame,
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
    """Replay one frozen RD32 policy without loading any data itself."""
    if policy_id not in POLICIES:
        raise RD32ReplayError(f"unknown policy: {policy_id}")
    if cost_multiplier not in COST_MULTIPLIERS:
        raise RD32ReplayError("unsupported cost multiplier")

    if policy_id == RD31_REGIME_HYSTERESIS_CONTROL:
        return replay_rd31_policy(
            policy_id="REGIME_HYSTERESIS_ADMISSION_GOVERNOR",
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

    replay_start = _utc(replay_start)
    replay_cutoff = _utc(replay_cutoff)
    if replay_start >= replay_cutoff:
        raise RD32ReplayError("invalid replay window")

    lookups = {pair: fast_lookup(frame) for pair, frame in frames.items()}
    state_lookup = build_state_lookup(state_frame)
    mb_rank_lookup = build_mb_candidate_rank_lookup(
        raw_focus_events,
        universe_id=universe_id,
    )
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
    governor_state = OPEN

    for timestamp in pd.date_range(
        replay_start,
        replay_cutoff,
        freq="h",
        inclusive="left",
    ):
        # Exact RD31 scheduled-exit ordering and lifecycle.
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
                raise RD32ReplayError(f"open-position bar missing: {pair} {timestamp}")

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
                    raise RD32ReplayError("scheduled exit missing fill details")
                reason = scheduled_exit.exit_reason
                if reason == TIME_FAIL_EXIT_REASON:
                    counters["time_failure_exits"] += 1
                elif reason == MAX_HOLD_EXIT_REASON:
                    counters["max_hold_exits"] += 1
                else:
                    raise RD32ReplayError(
                        f"RD32 lifecycle emitted prohibited exit reason: {reason}"
                    )

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
                entry_members,
                entry_returns,
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

            evidence = None
            if FAMILY_MOMENTUM_BREAKOUT in support:
                evidence = quality_evidence_for_event(
                    policy_id=policy_id,
                    universe_id=universe_id,
                    pair=pair,
                    signal_time=signal_time,
                    current_members=entry_members,
                    current_returns=entry_returns,
                    membership=membership,
                    frames=frames,
                    lookups=lookups,
                    state_lookup=state_lookup,
                    mb_candidate_rank_lookup=mb_rank_lookup,
                )

            prior_governor_state = governor_state
            governed = rd32_admission_decision(
                policy_id=policy_id,
                pair=pair,
                support_families=support,
                btc_state=entry_state,
                market_context=entry_context,
                governor_prior_state=governor_state,
                evidence=evidence,
            )
            governor_state = governed.rd31_control.governor_next_state
            if governor_state not in GOVERNOR_STATES:
                raise RD32ReplayError("governor state disappeared")
            counters[f"governor_state_{governor_state}"] += 1

            transition_reason = governed.rd31_control.transition_reason
            if transition_reason is None:
                raise RD32ReplayError("governor transition reason missing")
            reason_key = "governor_reason_" + transition_reason
            if reason_key not in counters:
                raise RD32ReplayError(f"unknown governor transition reason: {transition_reason}")
            counters[reason_key] += 1
            if prior_governor_state != governor_state:
                counters["governor_transition_count"] += 1

            quality = governed.quality
            if quality.evaluated:
                counters["mb_quality_evaluated"] += 1
                if quality.retained:
                    counters["mb_quality_retained"] += 1
                else:
                    counters["mb_quality_vetoed"] += 1
            else:
                counters["mb_quality_not_applicable"] += 1

            admission = governed.decision
            outcome = "ADMIT" if admission.admit_position else "SUPPRESS"
            counters[f"admission_{entry_context.context}_{bucket}_{outcome}"] += 1

            if quality.evaluated and quality.retained is False:
                if admission.admit_position and admission.admissible_families == (
                    "RELATIVE_STRENGTH_ROTATION",
                ):
                    counters["mb_veto_overlap_rs_retained"] += 1
                elif not admission.admit_position:
                    counters["mb_veto_full_suppression"] += 1

            if not admission.admit_position:
                counters["suppressed_entries"] += 1
                if governor_state == LOCKED:
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
                raise RD32ReplayError("signal bar missing during admission")
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
                raise RD32ReplayError("invalid entry open price")
            atr = float(item["atr24_at_signal"])
            if not math.isfinite(atr) or atr <= 0.0:
                raise RD32ReplayError("invalid entry ATR")

            notional = float(sizing.notional)
            quantity = notional / entry_price
            entry_cost = notional * side_cost
            cash -= notional + entry_cost
            if cash < -1e-7:
                raise RD32ReplayError("negative cash after entry")
            cash = max(cash, 0.0)

            # Important: a vetoed MB component of an overlap signal is not
            # carried into the live position. RS-only retention is exact.
            admitted_support = tuple(admission.admissible_families)
            specialist = new_specialist_position(
                pair=pair,
                entry_time=timestamp,
                entry_price=entry_price,
                atr24_at_signal=atr,
                support_families=admitted_support,
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
                support_families=admitted_support,
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
                raise RD32ReplayError(f"position mark bar missing: {position.pair} {timestamp}")
            position.specialist = apply_completed_high(
                position.specialist,
                completed_high=float(bar["high"]),
            )
            position.last_mark = float(bar["close"])

        gross_close = sum(position.quantity * position.last_mark for position in positions.values())
        equity_close = cash + gross_close
        if equity_close < -1e-7:
            raise RD32ReplayError("negative equity observed")
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
        raise RD32ReplayError("open positions remained at replay cutoff")

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
        "control_delegate": ("EXACT_RD31_REGIME_HYSTERESIS_ADMISSION_GOVERNOR_REPLAY"),
        "raw_focus_signal_source_required": True,
        "breakout_leader_rank_source": ("EXACT_RD26_RAW_FOCUS_EVENT_CANDIDATE_RANK"),
        "union_event_candidate_rank_reconstruction": False,
        "breadth_current_cutoff": ("SIGNAL_BAR_CLOSE_VIA_EXACT_RD31_ENTRY_CONTEXT"),
        "breadth_prior_cutoff": ("SIGNAL_TIME_MINUS_1H_COMPLETED_CLOSE_VIA_CAUSAL_CONTEXT"),
        "breadth_prior_unavailable_fail_closed": True,
        "rs_leader_current_context_source": ("EXACT_RD31_ENTRY_CONTEXT_MEMBERS_AND_RETURN72"),
        "rd31_governor_runs_once_before_mb_veto": True,
        "governor_transition_recomputed_after_veto": False,
        "veto_mutates_governor_state": False,
        "candidate_mb_admission_subset_of_rd31": True,
        "overlap_vetoed_mb_removed_from_live_position": True,
        "overlap_rs_retained_if_rd31_admissible": True,
        "entry_fill": "NEXT_1H_OPEN_AFTER_SIGNAL",
        "scheduled_exit_state_cutoff": ("PRIOR_COMPLETED_HOUR"),
        "scheduled_exit_fill": "CURRENT_1H_OPEN",
        "lifecycle": ("EXACT_RD31_TIME_FAIL72_MAX168_NO_PROFIT_NO_REPLACEMENT"),
        "current_bar_high_used_for_entry_decision": False,
        "current_bar_low_used_for_entry_decision": False,
        "parameter_grid_search": False,
        "calendar_year_feature": False,
        "pair_blacklist": False,
        "exit_change": False,
        "sizing_change": False,
        "cost_change": False,
        "replacement": False,
        "profit_giveback": False,
        "thesis_failure_exit": False,
        "forced_regime_exit": False,
        "economic_runner_implemented": False,
        "economic_execution_performed": False,
        "real_market_data_loader_present": False,
        "raw_market_data_loaded": False,
        "candidate_results_observed": False,
        "2024_accessed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
    }
