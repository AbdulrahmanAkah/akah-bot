from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Any, Final

import pandas as pd

from spotbot.research.rd26_exit_architecture import (
    FAMILY_MOMENTUM_BREAKOUT,
    FAMILY_RELATIVE_STRENGTH_ROTATION,
)
from spotbot.research.rd27_adaptive_lifecycle import (
    MARKET_STATES,
    RISK_OFF,
    RISK_ON,
    TRANSITION,
    AdmissionDecision,
    capital_admission_decision,
)

SCHEMA_VERSION: Final = "rd28-evidence-gated-lifecycle-engine-v1"
STAGE: Final = "RD28_P0B_EVIDENCE_GATED_LIFECYCLE_PRE_ECONOMIC_EXECUTION"

ROUTER_TIME_FAIL_72_CONTROL: Final = "ROUTER_TIME_FAIL_72_CONTROL"
EVIDENCE_GATED_LIFECYCLE_IMMEDIATE_RECYCLE: Final = (
    "EVIDENCE_GATED_LIFECYCLE_IMMEDIATE_RECYCLE"
)
EVIDENCE_GATED_LIFECYCLE_SLOT_ESCROW: Final = "EVIDENCE_GATED_LIFECYCLE_SLOT_ESCROW"
FAMILY_AWARE_EVIDENCE_LIFECYCLE_SLOT_ESCROW: Final = (
    "FAMILY_AWARE_EVIDENCE_LIFECYCLE_SLOT_ESCROW"
)
POLICIES: Final = (
    ROUTER_TIME_FAIL_72_CONTROL,
    EVIDENCE_GATED_LIFECYCLE_IMMEDIATE_RECYCLE,
    EVIDENCE_GATED_LIFECYCLE_SLOT_ESCROW,
    FAMILY_AWARE_EVIDENCE_LIFECYCLE_SLOT_ESCROW,
)

STATE_RANK: Final = {
    RISK_OFF: 0,
    TRANSITION: 1,
    RISK_ON: 2,
}
FOCUS_FAMILIES: Final = (
    FAMILY_MOMENTUM_BREAKOUT,
    FAMILY_RELATIVE_STRENGTH_ROTATION,
)

EARLIEST_EVIDENCE_EXIT_HOURS: Final = 24
BACKUP_TIME_FAILURE_HOURS: Final = 72
MAX_HOLD_HOURS: Final = 168
PROFIT_ARM_ATR: Final = 4.0
PROFIT_GIVEBACK_ATR: Final = 3.0
MAXIMUM_POSITION_SLOTS: Final = 5

EARLY_EVIDENCE_REASON: Final = "EVIDENCE_GATED_REGIME_TRADE_INVALIDATION"
FAMILY_MB_EVIDENCE_REASON: Final = "FAMILY_AWARE_MB_RISK_OFF_TRADE_INVALIDATION"
FAMILY_RS_EVIDENCE_REASON: Final = (
    "FAMILY_AWARE_RS_STATE_DETERIORATION_TRADE_INVALIDATION"
)
PROFIT_GIVEBACK_REASON: Final = "PROFIT_GIVEBACK_LOCK_4ATR_ARM_3ATR_GIVEBACK"
BACKUP_TIME_FAIL_REASON: Final = "TIME_FAILURE_72H_CLOSE_NOT_ABOVE_ENTRY"
MAX_HOLD_REASON: Final = "MAX_HOLD_168H"


class RD28LifecycleError(RuntimeError):
    """Raised when the frozen RD28-P0B lifecycle contract is violated."""


@dataclass(frozen=True)
class EvidencePosition:
    pair: str
    entry_time: pd.Timestamp
    entry_price: float
    atr24_at_signal: float
    entry_market_state: str
    signal_family: str
    high_water_prior: float


@dataclass(frozen=True)
class EvidenceExitDecision:
    should_exit: bool
    exit_price: float | None
    exit_reason: str | None
    age_hours: int
    entry_market_state: str
    current_market_state: str
    trade_weak: bool
    market_state_deteriorated: bool
    profit_lock_armed: bool


@dataclass(frozen=True)
class EscrowSlot:
    pair: str
    release_time: pd.Timestamp


def _utc_timestamp(value: Any) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    return (
        timestamp.tz_localize("UTC")
        if timestamp.tzinfo is None
        else timestamp.tz_convert("UTC")
    )


def _require_state(state: str) -> None:
    if state not in MARKET_STATES:
        raise RD28LifecycleError(f"unknown market state: {state}")


def _require_family(signal_family: str) -> None:
    if signal_family not in FOCUS_FAMILIES:
        raise RD28LifecycleError(f"unknown focus family: {signal_family}")


def validate_constants() -> None:
    if STATE_RANK != {RISK_OFF: 0, TRANSITION: 1, RISK_ON: 2}:
        raise RD28LifecycleError("state-rank contract drifted")
    if (
        EARLIEST_EVIDENCE_EXIT_HOURS,
        BACKUP_TIME_FAILURE_HOURS,
        MAX_HOLD_HOURS,
    ) != (24, 72, 168):
        raise RD28LifecycleError("lifecycle timing contract drifted")
    if not math.isclose(PROFIT_ARM_ATR, 4.0):
        raise RD28LifecycleError("profit arm contract drifted")
    if not math.isclose(PROFIT_GIVEBACK_ATR, 3.0):
        raise RD28LifecycleError("profit giveback contract drifted")
    if MAXIMUM_POSITION_SLOTS != 5:
        raise RD28LifecycleError("position-slot contract drifted")
    if POLICIES != (
        ROUTER_TIME_FAIL_72_CONTROL,
        EVIDENCE_GATED_LIFECYCLE_IMMEDIATE_RECYCLE,
        EVIDENCE_GATED_LIFECYCLE_SLOT_ESCROW,
        FAMILY_AWARE_EVIDENCE_LIFECYCLE_SLOT_ESCROW,
    ):
        raise RD28LifecycleError("policy registry drifted")


def policy_components(policy_id: str) -> tuple[bool, bool]:
    """Return family-aware and slot-escrow flags for one frozen RD28 policy."""
    validate_constants()
    if policy_id == ROUTER_TIME_FAIL_72_CONTROL:
        return False, False
    if policy_id == EVIDENCE_GATED_LIFECYCLE_IMMEDIATE_RECYCLE:
        return False, False
    if policy_id == EVIDENCE_GATED_LIFECYCLE_SLOT_ESCROW:
        return False, True
    if policy_id == FAMILY_AWARE_EVIDENCE_LIFECYCLE_SLOT_ESCROW:
        return True, True
    raise RD28LifecycleError(f"unknown RD28 policy: {policy_id}")


def uses_evidence_exit(policy_id: str) -> bool:
    validate_constants()
    if policy_id == ROUTER_TIME_FAIL_72_CONTROL:
        return False
    if policy_id in (
        EVIDENCE_GATED_LIFECYCLE_IMMEDIATE_RECYCLE,
        EVIDENCE_GATED_LIFECYCLE_SLOT_ESCROW,
        FAMILY_AWARE_EVIDENCE_LIFECYCLE_SLOT_ESCROW,
    ):
        return True
    raise RD28LifecycleError(f"unknown RD28 policy: {policy_id}")


def active_component_count(policy_id: str) -> int:
    family_aware, slot_escrow = policy_components(policy_id)
    evidence_exit = uses_evidence_exit(policy_id)
    return 1 + int(evidence_exit) + int(slot_escrow) + int(family_aware)


def router_admission(market_state: str) -> AdmissionDecision:
    """Reuse the exact frozen RD27 state-router sensor."""
    return capital_admission_decision(market_state)


def state_rank(market_state: str) -> int:
    _require_state(market_state)
    return int(STATE_RANK[market_state])


def state_deteriorated(*, entry_state: str, current_state: str) -> bool:
    return state_rank(current_state) < state_rank(entry_state)


def new_evidence_position(
    *,
    pair: str,
    entry_time: pd.Timestamp,
    entry_price: float,
    atr24_at_signal: float,
    entry_market_state: str,
    signal_family: str,
) -> EvidencePosition:
    validate_constants()
    if not pair:
        raise RD28LifecycleError("pair is required")
    if not math.isfinite(entry_price) or entry_price <= 0.0:
        raise RD28LifecycleError("entry price must be positive and finite")
    if not math.isfinite(atr24_at_signal) or atr24_at_signal <= 0.0:
        raise RD28LifecycleError("signal ATR must be positive and finite")
    _require_state(entry_market_state)
    _require_family(signal_family)
    return EvidencePosition(
        pair=pair,
        entry_time=_utc_timestamp(entry_time),
        entry_price=float(entry_price),
        atr24_at_signal=float(atr24_at_signal),
        entry_market_state=entry_market_state,
        signal_family=signal_family,
        high_water_prior=float(entry_price),
    )


def age_hours(position: EvidencePosition, current_open_time: pd.Timestamp) -> int:
    timestamp = _utc_timestamp(current_open_time)
    seconds = (timestamp - position.entry_time).total_seconds()
    if seconds < 0.0 or seconds % 3600.0 != 0.0:
        raise RD28LifecycleError("evaluation time must be an hourly point at/after entry")
    return int(seconds // 3600.0)


def _family_early_condition(
    position: EvidencePosition,
    *,
    current_market_state: str,
    family_aware: bool,
) -> tuple[bool, str]:
    deteriorated = state_deteriorated(
        entry_state=position.entry_market_state,
        current_state=current_market_state,
    )
    if not family_aware:
        return deteriorated, EARLY_EVIDENCE_REASON
    if position.signal_family == FAMILY_MOMENTUM_BREAKOUT:
        return (
            current_market_state == RISK_OFF,
            FAMILY_MB_EVIDENCE_REASON,
        )
    if position.signal_family == FAMILY_RELATIVE_STRENGTH_ROTATION:
        return deteriorated, FAMILY_RS_EVIDENCE_REASON
    raise RD28LifecycleError(f"unsupported family: {position.signal_family}")


def evaluate_evidence_exit(
    position: EvidencePosition,
    *,
    current_open_time: pd.Timestamp,
    current_open: float,
    prior_asset_close: float,
    current_market_state: str,
    family_aware: bool,
) -> EvidenceExitDecision:
    """
    Evaluate at the current 1h open using only prior completed asset/BTC evidence.

    The function intentionally accepts neither current-bar high nor current-bar low.
    Every RD28-P0B exit fills at the current 1h open.
    """
    validate_constants()
    _require_state(current_market_state)
    for name, value in (
        ("current_open", current_open),
        ("prior_asset_close", prior_asset_close),
    ):
        if not math.isfinite(value) or value <= 0.0:
            raise RD28LifecycleError(f"{name} must be positive and finite")

    age = age_hours(position, current_open_time)
    trade_weak = float(prior_asset_close) <= position.entry_price
    deteriorated = state_deteriorated(
        entry_state=position.entry_market_state,
        current_state=current_market_state,
    )
    arm_level = position.entry_price + PROFIT_ARM_ATR * position.atr24_at_signal
    profit_lock_armed = position.high_water_prior >= arm_level
    giveback_floor = (
        position.high_water_prior - PROFIT_GIVEBACK_ATR * position.atr24_at_signal
    )

    def decision(reason: str) -> EvidenceExitDecision:
        return EvidenceExitDecision(
            should_exit=True,
            exit_price=float(current_open),
            exit_reason=reason,
            age_hours=age,
            entry_market_state=position.entry_market_state,
            current_market_state=current_market_state,
            trade_weak=trade_weak,
            market_state_deteriorated=deteriorated,
            profit_lock_armed=profit_lock_armed,
        )

    if age >= MAX_HOLD_HOURS:
        return decision(MAX_HOLD_REASON)

    if profit_lock_armed and float(prior_asset_close) <= giveback_floor:
        return decision(PROFIT_GIVEBACK_REASON)

    if age == BACKUP_TIME_FAILURE_HOURS and trade_weak:
        return decision(BACKUP_TIME_FAIL_REASON)

    early_condition, early_reason = _family_early_condition(
        position,
        current_market_state=current_market_state,
        family_aware=family_aware,
    )
    if age >= EARLIEST_EVIDENCE_EXIT_HOURS and trade_weak and early_condition:
        return decision(early_reason)

    return EvidenceExitDecision(
        should_exit=False,
        exit_price=None,
        exit_reason=None,
        age_hours=age,
        entry_market_state=position.entry_market_state,
        current_market_state=current_market_state,
        trade_weak=trade_weak,
        market_state_deteriorated=deteriorated,
        profit_lock_armed=profit_lock_armed,
    )


def evaluate_router_time_fail_control_exit(
    position: EvidencePosition,
    *,
    current_open_time: pd.Timestamp,
    current_open: float,
    prior_asset_close: float,
) -> EvidenceExitDecision:
    """Frozen RD27 static-router + TIME_FAIL_72 control exit semantics."""
    if not math.isfinite(current_open) or current_open <= 0.0:
        raise RD28LifecycleError("current open must be positive and finite")
    if not math.isfinite(prior_asset_close) or prior_asset_close <= 0.0:
        raise RD28LifecycleError("prior close must be positive and finite")
    age = age_hours(position, current_open_time)
    if age >= MAX_HOLD_HOURS:
        reason = MAX_HOLD_REASON
    elif age == BACKUP_TIME_FAILURE_HOURS and prior_asset_close <= position.entry_price:
        reason = BACKUP_TIME_FAIL_REASON
    else:
        reason = None
    return EvidenceExitDecision(
        should_exit=reason is not None,
        exit_price=float(current_open) if reason is not None else None,
        exit_reason=reason,
        age_hours=age,
        entry_market_state=position.entry_market_state,
        current_market_state=position.entry_market_state,
        trade_weak=float(prior_asset_close) <= position.entry_price,
        market_state_deteriorated=False,
        profit_lock_armed=False,
    )


def apply_completed_asset_bar(
    position: EvidencePosition,
    *,
    completed_high: float,
) -> EvidencePosition:
    """Ratchet high-water only after a survived completed asset bar."""
    if not math.isfinite(completed_high) or completed_high <= 0.0:
        raise RD28LifecycleError("completed high must be positive and finite")
    return replace(
        position,
        high_water_prior=max(position.high_water_prior, float(completed_high)),
    )


def escrow_slot_for_exit(
    position: EvidencePosition,
    *,
    exit_time: pd.Timestamp,
    exit_reason: str,
    slot_escrow_enabled: bool,
) -> EscrowSlot | None:
    """
    Reserve only a virtual position slot for evidence/profit exits before 72h.

    Cash and notional are never reserved. At exactly entry+72h the slot is free.
    """
    if not slot_escrow_enabled:
        return None
    exit_timestamp = _utc_timestamp(exit_time)
    release_time = position.entry_time + pd.Timedelta(hours=BACKUP_TIME_FAILURE_HOURS)
    eligible_reason = exit_reason in {
        EARLY_EVIDENCE_REASON,
        FAMILY_MB_EVIDENCE_REASON,
        FAMILY_RS_EVIDENCE_REASON,
        PROFIT_GIVEBACK_REASON,
    }
    if eligible_reason and exit_timestamp < release_time:
        return EscrowSlot(pair=position.pair, release_time=release_time)
    return None


def active_escrow_slots(
    escrows: tuple[EscrowSlot, ...] | list[EscrowSlot],
    *,
    current_time: pd.Timestamp,
) -> tuple[EscrowSlot, ...]:
    timestamp = _utc_timestamp(current_time)
    return tuple(slot for slot in escrows if timestamp < slot.release_time)


def slot_capacity_available(
    *,
    open_position_count: int,
    active_escrow_count: int,
) -> bool:
    if open_position_count < 0 or active_escrow_count < 0:
        raise RD28LifecycleError("slot counts cannot be negative")
    return open_position_count + active_escrow_count < MAXIMUM_POSITION_SLOTS


def contract_summary() -> dict[str, Any]:
    validate_constants()
    return {
        "schema_version": SCHEMA_VERSION,
        "stage": STAGE,
        "policies": list(POLICIES),
        "state_rank": dict(STATE_RANK),
        "earliest_evidence_exit_hours": EARLIEST_EVIDENCE_EXIT_HOURS,
        "backup_time_failure_hours": BACKUP_TIME_FAILURE_HOURS,
        "maximum_hold_hours": MAX_HOLD_HOURS,
        "profit_arm_atr": PROFIT_ARM_ATR,
        "profit_giveback_atr": PROFIT_GIVEBACK_ATR,
        "router_source": "EXACT_RD27_P0B_CAPITAL_ADMISSION_DECISION",
        "current_bar_high_used_for_exit": False,
        "current_bar_low_used_for_exit": False,
        "partial_selling": False,
        "slot_escrow_reserves_cash": False,
        "slot_escrow_reserves_notional": False,
        "economic_execution_performed": False,
        "real_market_data_loader_present": False,
    }
