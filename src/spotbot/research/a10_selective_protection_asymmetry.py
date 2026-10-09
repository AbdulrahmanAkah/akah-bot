"""Selective protection asymmetry shadow adapters for A10R1.

This module preserves the frozen RD27 control and reuses the exact A4R1
continuation candidate only inside mutually exclusive causal price/floor
channels. All non-eligible decisions and updates delegate to frozen RD27.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final, Literal

import pandas as pd

from spotbot.research import a4r1_reversible_floor_candidate as candidate
from spotbot.research import rd27_lifecycle_replay as rd27

SCHEMA_VERSION: Final = "a10-selective-protection-asymmetry-v1"

PRIMARY_POLICY_ID: Final = "A10_WINNER_RETENTION_SELECTIVE_PROTECTION_V1"
DIAGNOSTIC_POLICY_ID: Final = "A10_LOSER_RESCUE_DIAGNOSTIC_V1"

WINNER_RETENTION: Final = "WINNER_RETENTION"
LOSER_RESCUE_DIAGNOSTIC: Final = "LOSER_RESCUE_DIAGNOSTIC"
DIAGNOSTIC_CAN_RESCUE_PRIMARY: Final = False

Arm = Literal["WINNER_RETENTION", "LOSER_RESCUE_DIAGNOSTIC"]


@dataclass(frozen=True)
class SelectiveReplayResult:
    trades: pd.DataFrame
    daily: pd.DataFrame
    metrics: dict[str, Any]
    counters: dict[str, int]
    diagnostics: dict[str, Any]


def _utc(value: Any) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    return (
        timestamp.tz_localize("UTC")
        if timestamp.tzinfo is None
        else timestamp.tz_convert("UTC")
    )


def _selective_channel_eligible(
    *,
    position: Any,
    prior_asset_close: float,
    decision: Any,
    arm: Arm,
) -> bool:
    """Return whether exact A4R1 relaxation may replace the frozen RD27 control.

    Only prior-completed information is used. The entry price is the structural
    zero-PnL boundary frozen by A10; no fitted numeric threshold is introduced.

    Winner-retention:
      * prior completed close > entry
      * previous floor > entry
      * proposed A4R1 floor > entry
      * exact A4R1 continuation channel
      * exact A4R1 proposal actually relaxes historical carry

    Loser-rescue diagnostic:
      * prior completed close <= entry
      * previous floor <= entry
      * proposed A4R1 floor <= entry
      * exact A4R1 continuation channel
      * exact A4R1 proposal actually relaxes historical carry
    """

    if decision.lifecycle_channel != candidate.CONTINUATION_PRESERVATION:
        return False

    previous_floor = position.protection_floor
    if previous_floor is None:
        return False

    entry = float(position.entry_price)
    previous = float(previous_floor)
    proposed = float(decision.effective_floor)
    prior_close = float(prior_asset_close)

    if not proposed < previous:
        return False

    if arm == WINNER_RETENTION:
        return (
            prior_close > entry
            and previous > entry
            and proposed > entry
        )

    if arm == LOSER_RESCUE_DIAGNOSTIC:
        return (
            prior_close <= entry
            and previous <= entry
            and proposed <= entry
        )

    raise ValueError(f"UNKNOWN_SELECTIVE_ARM:{arm}")


def _replay_selective(
    *,
    arm: Arm,
    policy_id: str,
    portfolio_id: str,
    universe_id: str,
    cost_multiplier: float,
    events: pd.DataFrame,
    frames: dict[str, pd.DataFrame],
    state_frame: pd.DataFrame,
    replay_start: pd.Timestamp,
    replay_cutoff: pd.Timestamp,
) -> SelectiveReplayResult:
    """Replay one selective arm on exact frozen RD27 portfolio mechanics."""

    rd27.validate_policy_constants()
    candidate.contract_summary()

    state_lookup = rd27.build_state_lookup(state_frame)

    diagnostics: dict[str, Any] = {
        "arm": arm,
        "evaluation_count": 0,
        "candidate_evaluation_count": 0,
        "control_fallback_evaluation_count": 0,
        "selective_relaxation_event_count": 0,
        "selective_relaxation_total_magnitude": 0.0,
        "selective_relaxation_max_magnitude": 0.0,
        "winner_prior_close_count": 0,
        "loser_or_flat_prior_close_count": 0,
        "profit_floor_previous_count": 0,
        "adverse_floor_previous_count": 0,
        "candidate_update_count": 0,
        "control_update_count": 0,
        "patch_restored": False,
    }

    original_evaluate = rd27.evaluate_adaptive_exit
    original_update = rd27.apply_completed_bar_update
    selected_source_by_decision_id: dict[int, str] = {}

    def treatment_evaluate(
        position,
        *,
        current_open_time,
        current_open,
        current_low,
        prior_asset_close,
        market_state,
    ):
        timestamp = _utc(current_open_time)
        prior_close = float(prior_asset_close)
        entry = float(position.entry_price)

        if prior_close > entry:
            diagnostics["winner_prior_close_count"] += 1
        else:
            diagnostics["loser_or_flat_prior_close_count"] += 1

        if position.protection_floor is not None:
            if float(position.protection_floor) > entry:
                diagnostics["profit_floor_previous_count"] += 1
            else:
                diagnostics["adverse_floor_previous_count"] += 1

        previous_state = state_lookup.get(
            int((timestamp - pd.Timedelta(hours=2)).value)
        )
        candidate_decision = candidate.evaluate_candidate_exit(
            position,
            current_open_time=timestamp,
            current_open=float(current_open),
            current_low=float(current_low),
            prior_asset_close=prior_close,
            previous_market_state=previous_state,
            current_market_state=str(market_state),
        )

        use_candidate = _selective_channel_eligible(
            position=position,
            prior_asset_close=prior_close,
            decision=candidate_decision,
            arm=arm,
        )

        diagnostics["evaluation_count"] += 1

        if use_candidate:
            selected = candidate_decision
            selected_source_by_decision_id[id(selected)] = "candidate"
            diagnostics["candidate_evaluation_count"] += 1

            previous_floor = float(position.protection_floor)
            proposed_floor = float(candidate_decision.effective_floor)
            magnitude = previous_floor - proposed_floor
            diagnostics["selective_relaxation_event_count"] += 1
            diagnostics["selective_relaxation_total_magnitude"] += magnitude
            diagnostics["selective_relaxation_max_magnitude"] = max(
                float(diagnostics["selective_relaxation_max_magnitude"]),
                magnitude,
            )
            return selected

        selected = original_evaluate(
            position,
            current_open_time=timestamp,
            current_open=float(current_open),
            current_low=float(current_low),
            prior_asset_close=prior_close,
            market_state=str(market_state),
        )
        selected_source_by_decision_id[id(selected)] = "control"
        diagnostics["control_fallback_evaluation_count"] += 1
        return selected

    def treatment_update(
        position,
        *,
        decision,
        completed_high,
    ):
        source = selected_source_by_decision_id.pop(id(decision), "control")
        if source == "candidate":
            diagnostics["candidate_update_count"] += 1
            return candidate.apply_candidate_completed_bar_update(
                position,
                decision=decision,
                completed_high=float(completed_high),
            )

        diagnostics["control_update_count"] += 1
        return original_update(
            position,
            decision=decision,
            completed_high=float(completed_high),
        )

    try:
        rd27.evaluate_adaptive_exit = treatment_evaluate
        rd27.apply_completed_bar_update = treatment_update

        trades, daily, metrics, counters = rd27.replay_lifecycle_policy(
            policy_id=rd27.FULL_ADAPTIVE_LIFECYCLE_BRAIN,
            portfolio_id=portfolio_id,
            universe_id=universe_id,
            cost_multiplier=cost_multiplier,
            events=events,
            frames=frames,
            state_frame=state_frame,
            replay_start=replay_start,
            replay_cutoff=replay_cutoff,
        )
    finally:
        rd27.evaluate_adaptive_exit = original_evaluate
        rd27.apply_completed_bar_update = original_update
        diagnostics["patch_restored"] = (
            rd27.evaluate_adaptive_exit is original_evaluate
            and rd27.apply_completed_bar_update is original_update
        )

    if not diagnostics["patch_restored"]:
        raise RuntimeError("RD27_PATCH_RESTORE_FAILED")

    trades = trades.copy()
    daily = daily.copy()
    metrics = dict(metrics)

    if len(trades):
        trades["policy_id"] = policy_id
    if len(daily):
        daily["policy_id"] = policy_id
    metrics["policy_id"] = policy_id

    return SelectiveReplayResult(
        trades=trades,
        daily=daily,
        metrics=metrics,
        counters=dict(counters),
        diagnostics=diagnostics,
    )


def replay_winner_retention_candidate(
    *,
    portfolio_id: str,
    universe_id: str,
    cost_multiplier: float,
    events: pd.DataFrame,
    frames: dict[str, pd.DataFrame],
    state_frame: pd.DataFrame,
    replay_start: pd.Timestamp,
    replay_cutoff: pd.Timestamp,
) -> SelectiveReplayResult:
    """Replay the sole A10 primary candidate."""

    return _replay_selective(
        arm=WINNER_RETENTION,
        policy_id=PRIMARY_POLICY_ID,
        portfolio_id=portfolio_id,
        universe_id=universe_id,
        cost_multiplier=cost_multiplier,
        events=events,
        frames=frames,
        state_frame=state_frame,
        replay_start=replay_start,
        replay_cutoff=replay_cutoff,
    )


def replay_loser_rescue_diagnostic(
    *,
    portfolio_id: str,
    universe_id: str,
    cost_multiplier: float,
    events: pd.DataFrame,
    frames: dict[str, pd.DataFrame],
    state_frame: pd.DataFrame,
    replay_start: pd.Timestamp,
    replay_cutoff: pd.Timestamp,
) -> SelectiveReplayResult:
    """Replay the report-only A10 loser-rescue falsification arm."""

    return _replay_selective(
        arm=LOSER_RESCUE_DIAGNOSTIC,
        policy_id=DIAGNOSTIC_POLICY_ID,
        portfolio_id=portfolio_id,
        universe_id=universe_id,
        cost_multiplier=cost_multiplier,
        events=events,
        frames=frames,
        state_frame=state_frame,
        replay_start=replay_start,
        replay_cutoff=replay_cutoff,
    )
