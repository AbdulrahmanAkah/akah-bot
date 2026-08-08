from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Any, Final

import pandas as pd

from spotbot.research.rd26_exit_architecture import (
    FAMILY_MOMENTUM_BREAKOUT,
    FAMILY_RELATIVE_STRENGTH_ROTATION,
)
from spotbot.research.rd29_thesis_context import (
    MARKET_CONTEXTS,
    MAX_HOLD_HOURS,
    PROFIT_ARM_ATR,
    PROFIT_GIVEBACK_ATR,
    STRESSED,
    THESIS_CHECKPOINT_HOURS,
    AdmissionDecision,
    FamilyThesisStatus,
    MarketContextDecision,
    relative_strength_thesis_status,
)
from spotbot.research.rd29_thesis_context import (
    admission_decision as rd29_admission_decision,
)

SCHEMA_VERSION: Final = "rd30-family-specialist-state-engine-v1"
STAGE: Final = "RD30_P0B_FAMILY_SPECIALIST_STATE_ENGINE_PRE_ECONOMIC_EXECUTION"

ROUTER_TIME_FAIL_72_CONTROL: Final = "ROUTER_TIME_FAIL_72_CONTROL"
FAMILY_QUALITY_CONTROL_EXITS: Final = "FAMILY_QUALITY_CONTROL_EXITS"
FAMILY_QUALITY_REPLACEMENT_AWARE_RS: Final = "FAMILY_QUALITY_REPLACEMENT_AWARE_RS"
FULL_FAMILY_SPECIALIST_REPLACEMENT_BRAIN: Final = "FULL_FAMILY_SPECIALIST_REPLACEMENT_BRAIN"
POLICIES: Final = (
    ROUTER_TIME_FAIL_72_CONTROL,
    FAMILY_QUALITY_CONTROL_EXITS,
    FAMILY_QUALITY_REPLACEMENT_AWARE_RS,
    FULL_FAMILY_SPECIALIST_REPLACEMENT_BRAIN,
)

MB_SUPPORTED: Final = "MB_SUPPORTED"
RS_ONLY: Final = "RS_ONLY"
LIFECYCLE_CLASSES: Final = (MB_SUPPORTED, RS_ONLY)

TIME_FAIL_EXIT_REASON: Final = "TIME_FAILURE_72H_CLOSE_NOT_ABOVE_ENTRY"
PROFIT_GIVEBACK_EXIT_REASON: Final = "PROFIT_GIVEBACK_LOCK_4ATR_ARM_3ATR_GIVEBACK"
MAX_HOLD_EXIT_REASON: Final = "MAX_HOLD_168H"
REPLACEMENT_EXIT_REASON: Final = "RS_DEGRADED_ATOMIC_REPLACEMENT"

FOCUS_FAMILIES: Final = (
    FAMILY_MOMENTUM_BREAKOUT,
    FAMILY_RELATIVE_STRENGTH_ROTATION,
)


class RD30StateError(RuntimeError):
    pass


@dataclass(frozen=True)
class SpecialistPosition:
    pair: str
    entry_time: pd.Timestamp
    entry_price: float
    atr24_at_signal: float
    support_families: tuple[str, ...]
    lifecycle_class: str
    high_water_prior: float
    degraded_since: pd.Timestamp | None = None
    last_checkpoint_time: pd.Timestamp | None = None


@dataclass(frozen=True)
class ScheduledExitDecision:
    should_exit: bool
    exit_price: float | None
    exit_reason: str | None
    age_hours: int
    profit_lock_armed: bool


@dataclass(frozen=True)
class ReplacementStateDecision:
    position: SpecialistPosition
    at_checkpoint: bool
    rs_evaluable: bool
    rs_failed: bool | None
    degraded_before: bool
    degraded_after: bool
    state_changed: bool
    reason: str
    rs_status: FamilyThesisStatus | None


@dataclass(frozen=True)
class ReplacementSelectionDecision:
    should_replace: bool
    incumbent_pair: str | None
    reason: str
    eligible_degraded_pairs: tuple[str, ...]


def _utc(value: Any) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    return timestamp.tz_localize("UTC") if timestamp.tzinfo is None else timestamp.tz_convert("UTC")


def _families(
    support_families: tuple[str, ...] | list[str],
) -> tuple[str, ...]:
    families = tuple(sorted(set(support_families)))
    if not families:
        raise RD30StateError("support family required")
    unknown = set(families).difference(FOCUS_FAMILIES)
    if unknown:
        raise RD30StateError(f"unknown support families: {sorted(unknown)}")
    return families


def validate_constants() -> None:
    if THESIS_CHECKPOINT_HOURS != (24, 48, 72, 96, 120, 144):
        raise RD30StateError("RD29 checkpoint contract drifted")
    if MAX_HOLD_HOURS != 168:
        raise RD30StateError("maximum-hold contract drifted")
    if not math.isclose(PROFIT_ARM_ATR, 4.0):
        raise RD30StateError("profit-arm contract drifted")
    if not math.isclose(PROFIT_GIVEBACK_ATR, 3.0):
        raise RD30StateError("profit-giveback contract drifted")
    if len(POLICIES) != 4:
        raise RD30StateError("RD30 policy registry drifted")


def lifecycle_class_for_support(
    support_families: tuple[str, ...] | list[str],
) -> str:
    families = _families(support_families)
    if FAMILY_MOMENTUM_BREAKOUT in families:
        return MB_SUPPORTED
    if families == (FAMILY_RELATIVE_STRENGTH_ROTATION,):
        return RS_ONLY
    raise RD30StateError("unclassifiable support-family set")


def policy_components(policy_id: str) -> dict[str, bool]:
    if policy_id == ROUTER_TIME_FAIL_72_CONTROL:
        return {
            "family_quality_admission": False,
            "replacement_state": False,
            "profit_state": False,
        }
    if policy_id == FAMILY_QUALITY_CONTROL_EXITS:
        return {
            "family_quality_admission": True,
            "replacement_state": False,
            "profit_state": False,
        }
    if policy_id == FAMILY_QUALITY_REPLACEMENT_AWARE_RS:
        return {
            "family_quality_admission": True,
            "replacement_state": True,
            "profit_state": False,
        }
    if policy_id == FULL_FAMILY_SPECIALIST_REPLACEMENT_BRAIN:
        return {
            "family_quality_admission": True,
            "replacement_state": True,
            "profit_state": True,
        }
    raise RD30StateError(f"unknown policy: {policy_id}")


def active_component_count(policy_id: str) -> int:
    return 1 + sum(int(value) for value in policy_components(policy_id).values())


def admission_decision(
    *,
    policy_id: str,
    support_families: tuple[str, ...] | list[str],
    btc_state: str,
    market_context: MarketContextDecision,
) -> AdmissionDecision:
    components = policy_components(policy_id)
    return rd29_admission_decision(
        support_families=support_families,
        btc_state=btc_state,
        market_context=market_context,
        family_quality_enabled=components["family_quality_admission"],
    )


def new_specialist_position(
    *,
    pair: str,
    entry_time: pd.Timestamp,
    entry_price: float,
    atr24_at_signal: float,
    support_families: tuple[str, ...] | list[str],
) -> SpecialistPosition:
    validate_constants()
    families = _families(support_families)
    if not pair:
        raise RD30StateError("pair required")
    if not math.isfinite(float(entry_price)) or float(entry_price) <= 0.0:
        raise RD30StateError("invalid entry price")
    if not math.isfinite(float(atr24_at_signal)) or float(atr24_at_signal) <= 0.0:
        raise RD30StateError("invalid ATR")
    return SpecialistPosition(
        pair=str(pair),
        entry_time=_utc(entry_time),
        entry_price=float(entry_price),
        atr24_at_signal=float(atr24_at_signal),
        support_families=families,
        lifecycle_class=lifecycle_class_for_support(families),
        high_water_prior=float(entry_price),
    )


def age_hours(
    position: SpecialistPosition,
    current_open_time: pd.Timestamp,
) -> int:
    seconds = (_utc(current_open_time) - position.entry_time).total_seconds()
    if seconds < 0.0 or seconds % 3600.0 != 0.0:
        raise RD30StateError("evaluation time must be hourly at/after entry")
    return int(seconds // 3600.0)


def apply_completed_high(
    position: SpecialistPosition,
    *,
    completed_high: float,
) -> SpecialistPosition:
    high = float(completed_high)
    if not math.isfinite(high) or high <= 0.0:
        raise RD30StateError("invalid completed high")
    return replace(
        position,
        high_water_prior=max(position.high_water_prior, high),
    )


def evaluate_scheduled_exit(
    position: SpecialistPosition,
    *,
    current_open_time: pd.Timestamp,
    current_open: float,
    prior_completed_close: float,
    profit_state_enabled: bool,
) -> ScheduledExitDecision:
    validate_constants()
    open_price = float(current_open)
    prior_close = float(prior_completed_close)
    if not math.isfinite(open_price) or open_price <= 0.0:
        raise RD30StateError("invalid current open")
    if not math.isfinite(prior_close) or prior_close <= 0.0:
        raise RD30StateError("invalid prior close")

    age = age_hours(position, current_open_time)
    arm = position.entry_price + PROFIT_ARM_ATR * position.atr24_at_signal
    armed = position.high_water_prior >= arm
    giveback = position.high_water_prior - PROFIT_GIVEBACK_ATR * position.atr24_at_signal

    if age >= MAX_HOLD_HOURS:
        return ScheduledExitDecision(
            True,
            open_price,
            MAX_HOLD_EXIT_REASON,
            age,
            armed,
        )
    if profit_state_enabled and armed and prior_close <= giveback:
        return ScheduledExitDecision(
            True,
            open_price,
            PROFIT_GIVEBACK_EXIT_REASON,
            age,
            True,
        )
    if age == 72 and prior_close <= position.entry_price:
        return ScheduledExitDecision(
            True,
            open_price,
            TIME_FAIL_EXIT_REASON,
            age,
            armed,
        )
    return ScheduledExitDecision(
        False,
        None,
        None,
        age,
        armed,
    )


def update_replacement_state(
    position: SpecialistPosition,
    *,
    current_open_time: pd.Timestamp,
    current_members: tuple[tuple[str, int], ...],
    return_72h_by_pair: dict[str, float | None],
    market_context: MarketContextDecision,
) -> ReplacementStateDecision:
    validate_constants()
    if market_context.context not in MARKET_CONTEXTS:
        raise RD30StateError("unknown market context")

    age = age_hours(position, current_open_time)
    at_checkpoint = age in THESIS_CHECKPOINT_HOURS
    degraded_before = position.degraded_since is not None

    if position.lifecycle_class == MB_SUPPORTED:
        if degraded_before:
            raise RD30StateError("MB-supported position cannot carry degraded state")
        return ReplacementStateDecision(
            position,
            at_checkpoint,
            False,
            None,
            False,
            False,
            False,
            "MB_SUPPORTED_NEVER_THESIS_DEGRADED",
            None,
        )

    if position.lifecycle_class != RS_ONLY:
        raise RD30StateError(f"unknown lifecycle class: {position.lifecycle_class}")

    if not at_checkpoint:
        return ReplacementStateDecision(
            position,
            False,
            False,
            None,
            degraded_before,
            degraded_before,
            False,
            "NOT_A_REPLACEMENT_CHECKPOINT",
            None,
        )

    status = relative_strength_thesis_status(
        pair=position.pair,
        members=current_members,
        return_72h_by_pair=return_72h_by_pair,
    )
    checkpoint_time = _utc(current_open_time)

    if not status.evaluable:
        updated = replace(
            position,
            last_checkpoint_time=checkpoint_time,
        )
        return ReplacementStateDecision(
            updated,
            True,
            False,
            None,
            degraded_before,
            degraded_before,
            False,
            "RS_UNEVALUABLE_PERSIST_PRIOR_DEGRADED_STATE",
            status,
        )

    should_degrade = status.failed is True and market_context.context == STRESSED
    if should_degrade:
        degraded_since = (
            position.degraded_since if position.degraded_since is not None else checkpoint_time
        )
        updated = replace(
            position,
            degraded_since=degraded_since,
            last_checkpoint_time=checkpoint_time,
        )
        return ReplacementStateDecision(
            updated,
            True,
            True,
            True,
            degraded_before,
            True,
            not degraded_before,
            ("RS_DEGRADED_SET" if not degraded_before else "RS_DEGRADED_PERSIST"),
            status,
        )

    updated = replace(
        position,
        degraded_since=None,
        last_checkpoint_time=checkpoint_time,
    )
    return ReplacementStateDecision(
        updated,
        True,
        True,
        status.failed,
        degraded_before,
        False,
        degraded_before,
        ("RS_DEGRADED_CLEARED" if degraded_before else "RS_NOT_DEGRADED"),
        status,
    )


def select_replacement_incumbent(
    positions: tuple[SpecialistPosition, ...] | list[SpecialistPosition],
    *,
    incoming_prevalidated: bool,
    free_slot_exists: bool,
) -> ReplacementSelectionDecision:
    if not incoming_prevalidated:
        return ReplacementSelectionDecision(
            False,
            None,
            "INCOMING_ENTRY_NOT_PREVALIDATED",
            (),
        )
    if free_slot_exists:
        return ReplacementSelectionDecision(
            False,
            None,
            "FREE_SLOT_EXISTS_NO_REPLACEMENT",
            (),
        )

    candidates = [
        position
        for position in positions
        if position.lifecycle_class == RS_ONLY and position.degraded_since is not None
    ]
    candidates.sort(
        key=lambda position: (
            _utc(position.degraded_since),
            position.entry_time,
            position.pair,
        )
    )
    eligible = tuple(position.pair for position in candidates)
    if not candidates:
        return ReplacementSelectionDecision(
            False,
            None,
            "NO_DEGRADED_RS_ONLY_INCUMBENT",
            (),
        )
    return ReplacementSelectionDecision(
        True,
        candidates[0].pair,
        "OLDEST_DEGRADED_RS_ONLY_SELECTED",
        eligible,
    )


def contract_summary() -> dict[str, Any]:
    validate_constants()
    return {
        "schema_version": SCHEMA_VERSION,
        "stage": STAGE,
        "policies": list(POLICIES),
        "lifecycle_classes": list(LIFECYCLE_CLASSES),
        "thesis_checkpoint_hours": list(THESIS_CHECKPOINT_HOURS),
        "maximum_hold_hours": MAX_HOLD_HOURS,
        "profit_arm_atr": PROFIT_ARM_ATR,
        "profit_giveback_atr": PROFIT_GIVEBACK_ATR,
        "mb_thesis_failure_exit": False,
        "mb_replacement_degradation": False,
        "rs_degradation_immediate_cash_exit": False,
        "replacement_requires_prevalidated_incoming": True,
        "replacement_forbidden_when_free_slot_exists": True,
        "global_slot_escrow": False,
        "same_pair_cooldown": False,
        "economic_execution_performed": False,
        "real_market_data_loader_present": False,
        "2024_accessed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
    }
