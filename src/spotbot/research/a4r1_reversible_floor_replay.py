"""A4R1 paired shadow replay adapter.

This module delegates portfolio mechanics to the frozen RD27 replay engine and
temporarily replaces only the adaptive lifecycle decision/update hooks with the
A4R1 repaired reversible-floor semantics. The patch is restored in ``finally``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

import pandas as pd

from spotbot.research import a4r1_reversible_floor_candidate as candidate
from spotbot.research import rd27_lifecycle_replay as rd27

SCHEMA_VERSION: Final = "a4r1-reversible-floor-paired-replay-v1"
TREATMENT_POLICY_ID: Final = "A4R1_REPAIRED_REVERSIBLE_FLOOR_SHADOW"


@dataclass(frozen=True)
class TreatmentReplayResult:
    trades: pd.DataFrame
    daily: pd.DataFrame
    metrics: dict[str, Any]
    counters: dict[str, int]
    diagnostics: dict[str, Any]


def _utc(value: Any) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    return timestamp.tz_localize("UTC") if timestamp.tzinfo is None else timestamp.tz_convert("UTC")


def replay_reversible_floor_candidate(
    *,
    portfolio_id: str,
    universe_id: str,
    cost_multiplier: float,
    events: pd.DataFrame,
    frames: dict[str, pd.DataFrame],
    state_frame: pd.DataFrame,
    replay_start: pd.Timestamp,
    replay_cutoff: pd.Timestamp,
) -> TreatmentReplayResult:
    """Run the treatment on the exact frozen RD27 portfolio mechanics."""
    rd27.validate_policy_constants()
    candidate.contract_summary()

    state_lookup = rd27.build_state_lookup(state_frame)
    diagnostics: dict[str, Any] = {
        "evaluation_count": 0,
        "continuation_evaluation_count": 0,
        "adverse_evaluation_count": 0,
        "floor_relaxation_event_count": 0,
        "floor_relaxation_total_magnitude": 0.0,
        "floor_relaxation_max_magnitude": 0.0,
        "transition_direction_counts": {},
        "market_state_evaluation_counts": {},
        "patch_restored": False,
    }

    original_evaluate = rd27.evaluate_adaptive_exit
    original_update = rd27.apply_completed_bar_update

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
        previous_state = state_lookup.get(int((timestamp - pd.Timedelta(hours=2)).value))
        decision = candidate.evaluate_candidate_exit(
            position,
            current_open_time=timestamp,
            current_open=float(current_open),
            current_low=float(current_low),
            prior_asset_close=float(prior_asset_close),
            previous_market_state=previous_state,
            current_market_state=str(market_state),
        )

        diagnostics["evaluation_count"] += 1
        channel_key = (
            "continuation_evaluation_count"
            if decision.lifecycle_channel == candidate.CONTINUATION_PRESERVATION
            else "adverse_evaluation_count"
        )
        diagnostics[channel_key] += 1

        direction_counts = diagnostics["transition_direction_counts"]
        direction_counts[decision.transition_direction] = (
            int(direction_counts.get(decision.transition_direction, 0)) + 1
        )
        state_counts = diagnostics["market_state_evaluation_counts"]
        state_counts[str(market_state)] = int(state_counts.get(str(market_state), 0)) + 1

        if position.protection_floor is not None:
            magnitude = float(position.protection_floor) - float(decision.effective_floor)
            if (
                decision.lifecycle_channel == candidate.CONTINUATION_PRESERVATION
                and magnitude > 1e-12
            ):
                diagnostics["floor_relaxation_event_count"] += 1
                diagnostics["floor_relaxation_total_magnitude"] += magnitude
                diagnostics["floor_relaxation_max_magnitude"] = max(
                    float(diagnostics["floor_relaxation_max_magnitude"]),
                    magnitude,
                )
        return decision

    def treatment_update(
        position,
        *,
        decision,
        completed_high,
    ):
        return candidate.apply_candidate_completed_bar_update(
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
        trades["policy_id"] = TREATMENT_POLICY_ID
    if len(daily):
        daily["policy_id"] = TREATMENT_POLICY_ID
    metrics["policy_id"] = TREATMENT_POLICY_ID

    return TreatmentReplayResult(
        trades=trades,
        daily=daily,
        metrics=metrics,
        counters=dict(counters),
        diagnostics=diagnostics,
    )
