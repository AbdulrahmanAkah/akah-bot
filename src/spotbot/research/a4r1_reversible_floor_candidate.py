"""A4R1 isolated reversible-protection shadow candidate.

This module is intentionally separate from the frozen RD27 control. It reuses
RD27 constants and position semantics but never mutates the RD27 implementation.
No market-data loading or economic replay is present here.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Final

import pandas as pd

from spotbot.research.rd27_adaptive_lifecycle import (
    ADVERSE_GUARD_ATR_BY_STATE,
    MARKET_STATES,
    MAX_HOLD_HOURS,
    PROFIT_ARM_ATR,
    PROFIT_TRAIL_GAP_ATR_BY_STATE,
    RISK_OFF,
    RISK_ON,
    STAGNATION_HOURS_BY_STATE,
    TRANSITION,
    LifecyclePosition,
    RD27StateError,
    validate_constants,
)

SCHEMA_VERSION: Final = "a4r1-reversible-floor-shadow-candidate-v1"

IMPROVING: Final = "IMPROVING"
UNCHANGED: Final = "UNCHANGED"
DETERIORATING: Final = "DETERIORATING"
UNAVAILABLE_AT_INITIAL_OBSERVATION: Final = "UNAVAILABLE_AT_INITIAL_OBSERVATION"

CONTINUATION_PRESERVATION: Final = "CONTINUATION_PRESERVATION"
ADVERSE_RESCUE: Final = "ADVERSE_RESCUE"

IMPROVING_TRANSITIONS: Final = frozenset(
    {
        (RISK_OFF, TRANSITION),
        (RISK_OFF, RISK_ON),
        (TRANSITION, RISK_ON),
    }
)


@dataclass(frozen=True)
class CandidateExitDecision:
    should_exit: bool
    exit_price: float | None
    exit_reason: str | None
    current_market_state: str
    previous_market_state: str | None
    transition_direction: str
    lifecycle_channel: str
    age_hours: int
    contemporaneous_floor: float
    contemporaneous_floor_source: str
    effective_floor: float
    floor_source: str
    stagnation_threshold_hours: int


def _require_state(state: str) -> None:
    if state not in MARKET_STATES:
        raise RD27StateError(f"unknown market state: {state}")


def transition_direction(
    *,
    previous_market_state: str | None,
    current_market_state: str,
) -> str:
    """Derive direction from completed causal regime labels only."""
    _require_state(current_market_state)
    if previous_market_state is None:
        return UNAVAILABLE_AT_INITIAL_OBSERVATION
    _require_state(previous_market_state)
    if previous_market_state == current_market_state:
        return UNCHANGED
    if (previous_market_state, current_market_state) in IMPROVING_TRANSITIONS:
        return IMPROVING
    return DETERIORATING


def is_continuation_context(
    *,
    previous_market_state: str | None,
    current_market_state: str,
) -> bool:
    direction = transition_direction(
        previous_market_state=previous_market_state,
        current_market_state=current_market_state,
    )
    return direction == IMPROVING or (
        current_market_state == RISK_ON and direction == UNCHANGED
    )


def contemporaneous_floor(
    position: LifecyclePosition,
    *,
    current_market_state: str,
) -> tuple[float, str]:
    """Return C_now using frozen RD27 formulas but excluding historical carry."""
    validate_constants()
    _require_state(current_market_state)
    atr = position.atr24_at_signal
    adverse = (
        position.entry_price
        - ADVERSE_GUARD_ATR_BY_STATE[current_market_state] * atr
    )
    candidates: list[tuple[float, str]] = [(adverse, "ADVERSE_GUARD")]

    arm_level = position.entry_price + PROFIT_ARM_ATR * atr
    if position.high_water_prior >= arm_level:
        trail = (
            position.high_water_prior
            - PROFIT_TRAIL_GAP_ATR_BY_STATE[current_market_state] * atr
        )
        candidates.append((trail, "PROFIT_TRAIL"))

    floor, source = max(candidates, key=lambda item: (item[0], item[1]))
    return float(floor), source


def selected_floor(
    position: LifecyclePosition,
    *,
    previous_market_state: str | None,
    current_market_state: str,
) -> tuple[float, str, float, str, str, str]:
    """Select channel and floor from causal context without future information."""
    c_now, c_source = contemporaneous_floor(
        position,
        current_market_state=current_market_state,
    )
    direction = transition_direction(
        previous_market_state=previous_market_state,
        current_market_state=current_market_state,
    )
    continuation = direction == IMPROVING or (
        current_market_state == RISK_ON and direction == UNCHANGED
    )
    if continuation:
        return (
            c_now,
            f"CONTEMPORANEOUS_{c_source}",
            c_now,
            c_source,
            direction,
            CONTINUATION_PRESERVATION,
        )

    candidates: list[tuple[float, str]] = [(c_now, c_source)]
    if position.protection_floor is not None:
        candidates.append(
            (float(position.protection_floor), "MONOTONIC_PRIOR_FLOOR")
        )
    floor, source = max(candidates, key=lambda item: (item[0], item[1]))
    return (
        float(floor),
        source,
        c_now,
        c_source,
        direction,
        ADVERSE_RESCUE,
    )


def _age_hours(
    position: LifecyclePosition,
    current_open_time: pd.Timestamp,
) -> int:
    timestamp = pd.Timestamp(current_open_time)
    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize("UTC")
    else:
        timestamp = timestamp.tz_convert("UTC")
    seconds = (timestamp - position.entry_time).total_seconds()
    seconds_per_hour = pd.Timedelta(hours=1).total_seconds()
    if seconds < 0 or seconds % seconds_per_hour != 0:
        raise RD27StateError(
            "lifecycle evaluation time must be an hourly point at/after entry"
        )
    return int(seconds // seconds_per_hour)


def evaluate_candidate_exit(
    position: LifecyclePosition,
    *,
    current_open_time: pd.Timestamp,
    current_open: float,
    current_low: float,
    prior_asset_close: float,
    previous_market_state: str | None,
    current_market_state: str,
) -> CandidateExitDecision:
    """Evaluate the repaired candidate without current-bar-high leakage."""
    validate_constants()
    _require_state(current_market_state)
    if previous_market_state is not None:
        _require_state(previous_market_state)
    for name, value in (
        ("current_open", current_open),
        ("current_low", current_low),
        ("prior_asset_close", prior_asset_close),
    ):
        if not math.isfinite(value) or value <= 0:
            raise RD27StateError(f"{name} must be positive and finite")

    age_hours = _age_hours(position, current_open_time)
    (
        floor,
        floor_source,
        c_now,
        c_source,
        direction,
        channel,
    ) = selected_floor(
        position,
        previous_market_state=previous_market_state,
        current_market_state=current_market_state,
    )
    stagnation_hours = STAGNATION_HOURS_BY_STATE[current_market_state]

    decision_fields = {
        "current_market_state": current_market_state,
        "previous_market_state": previous_market_state,
        "transition_direction": direction,
        "lifecycle_channel": channel,
        "age_hours": age_hours,
        "contemporaneous_floor": c_now,
        "contemporaneous_floor_source": c_source,
        "effective_floor": floor,
        "floor_source": floor_source,
        "stagnation_threshold_hours": stagnation_hours,
    }

    if age_hours >= MAX_HOLD_HOURS:
        return CandidateExitDecision(
            should_exit=True,
            exit_price=float(current_open),
            exit_reason=f"MAX_HOLD_{MAX_HOLD_HOURS}H",
            **decision_fields,
        )

    if current_open <= floor:
        return CandidateExitDecision(
            should_exit=True,
            exit_price=float(current_open),
            exit_reason="ADAPTIVE_PROTECTION_GAP",
            **decision_fields,
        )

    if (
        age_hours >= stagnation_hours
        and prior_asset_close <= position.entry_price
    ):
        return CandidateExitDecision(
            should_exit=True,
            exit_price=float(current_open),
            exit_reason=(
                f"ADAPTIVE_STAGNATION_{stagnation_hours}H_"
                "CLOSE_NOT_ABOVE_ENTRY"
            ),
            **decision_fields,
        )

    if current_low <= floor:
        return CandidateExitDecision(
            should_exit=True,
            exit_price=float(floor),
            exit_reason="ADAPTIVE_PROTECTION_TOUCH",
            **decision_fields,
        )

    return CandidateExitDecision(
        should_exit=False,
        exit_price=None,
        exit_reason=None,
        **decision_fields,
    )


def apply_candidate_completed_bar_update(
    position: LifecyclePosition,
    *,
    decision: CandidateExitDecision,
    completed_high: float,
) -> LifecyclePosition:
    """Store the selected floor directly; update high-water for the next bar."""
    if decision.should_exit:
        raise RD27StateError("cannot update a position after an exit decision")
    if not math.isfinite(completed_high) or completed_high <= 0:
        raise RD27StateError("completed high must be positive and finite")
    return replace(
        position,
        high_water_prior=max(
            position.high_water_prior,
            float(completed_high),
        ),
        protection_floor=float(decision.effective_floor),
    )


def contract_summary() -> dict[str, object]:
    validate_constants()
    return {
        "schema_version": SCHEMA_VERSION,
        "candidate_is_shadow_only": True,
        "rd27_control_mutated": False,
        "market_replay_performed": False,
        "current_bar_high_can_tighten_same_bar_floor": False,
        "maximum_hold_hours": MAX_HOLD_HOURS,
        "continuation_context": (
            "IMPROVING_OR_RISK_ON_UNCHANGED"
        ),
        "continuation_floor": "C_now",
        "defensive_floor": "max(P_prev,C_now)_when_prior_exists",
    }
