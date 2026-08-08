from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Any, Final

import numpy as np
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
    capital_admission_decision,
)

SCHEMA_VERSION: Final = "rd29-thesis-context-engine-v1"
STAGE: Final = "RD29_P0B_THESIS_CONTEXT_ENGINE_PRE_ECONOMIC_EXECUTION"

SUPPORTIVE: Final = "SUPPORTIVE"
MIXED: Final = "MIXED"
STRESSED: Final = "STRESSED"
UNAVAILABLE: Final = "UNAVAILABLE"
MARKET_CONTEXTS: Final = (SUPPORTIVE, MIXED, STRESSED, UNAVAILABLE)

ROUTER_TIME_FAIL_72_CONTROL: Final = "ROUTER_TIME_FAIL_72_CONTROL"
THESIS_CONFIDENCE_LIFECYCLE: Final = "THESIS_CONFIDENCE_LIFECYCLE"
THESIS_CONFIDENCE_PAIR_COOLDOWN: Final = "THESIS_CONFIDENCE_PAIR_COOLDOWN"
FULL_FAMILY_QUALITY_THESIS_BRAIN: Final = "FULL_FAMILY_QUALITY_THESIS_BRAIN"
POLICIES: Final = (
    ROUTER_TIME_FAIL_72_CONTROL,
    THESIS_CONFIDENCE_LIFECYCLE,
    THESIS_CONFIDENCE_PAIR_COOLDOWN,
    FULL_FAMILY_QUALITY_THESIS_BRAIN,
)

FOCUS_FAMILIES: Final = (
    FAMILY_MOMENTUM_BREAKOUT,
    FAMILY_RELATIVE_STRENGTH_ROTATION,
)
THESIS_CHECKPOINT_HOURS: Final = (24, 48, 72, 96, 120, 144)
MAX_HOLD_HOURS: Final = 168
PROFIT_ARM_ATR: Final = 4.0
PROFIT_GIVEBACK_ATR: Final = 3.0
PAIR_COOLDOWN_RELEASE_HOURS: Final = 72

THESIS_FAILURE_EXIT_REASON: Final = "THESIS_FAILURE_IN_STRESSED_CONTEXT"
PROFIT_GIVEBACK_EXIT_REASON: Final = "PROFIT_GIVEBACK_LOCK_4ATR_ARM_3ATR_GIVEBACK"
MAX_HOLD_EXIT_REASON: Final = "MAX_HOLD_168H"


class RD29ContextError(RuntimeError):
    pass


@dataclass(frozen=True)
class MarketContextDecision:
    btc_state: str
    breadth_ready: bool
    breadth_median_return_72h: float | None
    breadth_positive: bool | None
    context: str
    member_count: int
    observed_member_count: int


@dataclass(frozen=True)
class FamilyThesisStatus:
    family_id: str
    evaluable: bool
    retained: bool | None
    failed: bool | None
    reason: str
    current_return_72h: float | None = None
    current_rank: int | None = None


@dataclass(frozen=True)
class ThesisAggregateStatus:
    evaluable: bool
    failed: bool | None
    retained: bool | None
    reason: str
    family_statuses: tuple[FamilyThesisStatus, ...]


@dataclass(frozen=True)
class AdmissionDecision:
    record_signal: bool
    admit_position: bool
    target_slot_fraction: float
    reason: str
    admissible_families: tuple[str, ...]


@dataclass(frozen=True)
class ThesisPosition:
    pair: str
    entry_time: pd.Timestamp
    entry_price: float
    atr24_at_signal: float
    entry_market_context: str
    support_families: tuple[str, ...]
    momentum_breakout_reference: float | None
    high_water_prior: float


@dataclass(frozen=True)
class LifecycleExitDecision:
    should_exit: bool
    exit_price: float | None
    exit_reason: str | None
    age_hours: int
    at_thesis_checkpoint: bool
    market_context: str
    thesis_evaluable: bool
    thesis_failed: bool | None
    profit_lock_armed: bool


@dataclass(frozen=True)
class PairCooldown:
    pair: str
    release_time: pd.Timestamp


def _utc(value: Any) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    return timestamp.tz_localize("UTC") if timestamp.tzinfo is None else timestamp.tz_convert("UTC")


def _families(values: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    result = tuple(sorted(set(values)))
    if not result:
        raise RD29ContextError("support family required")
    unknown = set(result).difference(FOCUS_FAMILIES)
    if unknown:
        raise RD29ContextError(f"unknown support families: {sorted(unknown)}")
    return result


def validate_constants() -> None:
    if THESIS_CHECKPOINT_HOURS != (24, 48, 72, 96, 120, 144):
        raise RD29ContextError("checkpoint contract drifted")
    if MAX_HOLD_HOURS != 168 or PAIR_COOLDOWN_RELEASE_HOURS != 72:
        raise RD29ContextError("time contract drifted")
    if not math.isclose(PROFIT_ARM_ATR, 4.0):
        raise RD29ContextError("profit-arm contract drifted")
    if not math.isclose(PROFIT_GIVEBACK_ATR, 3.0):
        raise RD29ContextError("profit-giveback contract drifted")


def compute_market_context(
    *,
    btc_state: str,
    members: tuple[tuple[str, int], ...],
    return_72h_by_pair: dict[str, float | None],
) -> MarketContextDecision:
    validate_constants()
    if btc_state not in MARKET_STATES:
        raise RD29ContextError(f"unknown BTC state: {btc_state}")
    if not members:
        raise RD29ContextError("PIT membership cannot be empty")
    pairs = [pair for pair, _rank in members]
    if len(set(pairs)) != len(pairs):
        raise RD29ContextError("duplicate PIT pair")

    observed: list[float] = []
    for pair, _rank in members:
        value = return_72h_by_pair.get(pair)
        if value is None or not math.isfinite(float(value)):
            continue
        observed.append(float(value))

    if len(observed) != len(members):
        return MarketContextDecision(
            btc_state,
            False,
            None,
            None,
            UNAVAILABLE,
            len(members),
            len(observed),
        )

    median = float(np.median(np.asarray(observed, dtype=float)))
    positive = median > 0.0
    if btc_state == RISK_ON and positive:
        context = SUPPORTIVE
    elif btc_state == RISK_OFF or (btc_state == TRANSITION and not positive):
        context = STRESSED
    else:
        context = MIXED
    return MarketContextDecision(
        btc_state,
        True,
        median,
        positive,
        context,
        len(members),
        len(observed),
    )


def relative_strength_rank(
    *,
    pair: str,
    members: tuple[tuple[str, int], ...],
    return_72h_by_pair: dict[str, float | None],
) -> tuple[bool, float | None, int | None]:
    if not members:
        raise RD29ContextError("PIT membership cannot be empty")
    member_pairs = {member_pair for member_pair, _rank in members}
    if len(member_pairs) != len(members):
        raise RD29ContextError("duplicate PIT pair")
    if pair not in member_pairs:
        return True, None, None

    rows: list[tuple[float, int, str]] = []
    for member_pair, membership_rank in members:
        value = return_72h_by_pair.get(member_pair)
        if value is None or not math.isfinite(float(value)):
            return False, None, None
        rows.append((float(value), int(membership_rank), str(member_pair)))
    rows.sort(key=lambda item: (-item[0], item[1], item[2]))
    for rank, (value, _membership_rank, current_pair) in enumerate(rows, 1):
        if current_pair == pair:
            return True, value, rank
    raise RD29ContextError("RS pair disappeared during ranking")


def momentum_breakout_thesis_status(
    *,
    pair_in_current_membership: bool,
    prior_completed_close: float,
    breakout_reference: float | None,
) -> FamilyThesisStatus:
    if not pair_in_current_membership:
        return FamilyThesisStatus(
            FAMILY_MOMENTUM_BREAKOUT,
            True,
            False,
            True,
            "MEMBERSHIP_LOSS",
        )
    if breakout_reference is None:
        return FamilyThesisStatus(
            FAMILY_MOMENTUM_BREAKOUT,
            False,
            None,
            None,
            "BREAKOUT_REFERENCE_UNAVAILABLE",
        )
    close = float(prior_completed_close)
    reference = float(breakout_reference)
    if not math.isfinite(close) or close <= 0.0:
        raise RD29ContextError("invalid prior close")
    if not math.isfinite(reference) or reference <= 0.0:
        raise RD29ContextError("invalid breakout reference")
    retained = close > reference
    return FamilyThesisStatus(
        FAMILY_MOMENTUM_BREAKOUT,
        True,
        retained,
        not retained,
        (
            "PRIOR_CLOSE_ABOVE_ENTRY_BREAKOUT_REFERENCE"
            if retained
            else "PRIOR_CLOSE_AT_OR_BELOW_ENTRY_BREAKOUT_REFERENCE"
        ),
    )


def relative_strength_thesis_status(
    *,
    pair: str,
    members: tuple[tuple[str, int], ...],
    return_72h_by_pair: dict[str, float | None],
) -> FamilyThesisStatus:
    if pair not in {member_pair for member_pair, _rank in members}:
        return FamilyThesisStatus(
            FAMILY_RELATIVE_STRENGTH_ROTATION,
            True,
            False,
            True,
            "MEMBERSHIP_LOSS",
        )
    ready, current_return, current_rank = relative_strength_rank(
        pair=pair,
        members=members,
        return_72h_by_pair=return_72h_by_pair,
    )
    if not ready:
        return FamilyThesisStatus(
            FAMILY_RELATIVE_STRENGTH_ROTATION,
            False,
            None,
            None,
            "CURRENT_CROSS_SECTIONAL_RETURN_72H_UNAVAILABLE",
        )
    if current_return is None or current_rank is None:
        raise RD29ContextError("unexpected null RS observation")
    retained = current_return > 0.0 and current_rank <= 2
    return FamilyThesisStatus(
        FAMILY_RELATIVE_STRENGTH_ROTATION,
        True,
        retained,
        not retained,
        (
            "POSITIVE_RETURN_AND_CURRENT_RANK_LE_2"
            if retained
            else "RETURN_NONPOSITIVE_OR_CURRENT_RANK_GT_2"
        ),
        current_return,
        current_rank,
    )


def aggregate_thesis_status(
    *,
    pair: str,
    support_families: tuple[str, ...] | list[str],
    members: tuple[tuple[str, int], ...],
    prior_completed_close: float,
    return_72h_by_pair: dict[str, float | None],
    momentum_breakout_reference: float | None,
) -> ThesisAggregateStatus:
    families = _families(support_families)
    current_pairs = {member_pair for member_pair, _rank in members}
    statuses: list[FamilyThesisStatus] = []
    for family in families:
        if family == FAMILY_MOMENTUM_BREAKOUT:
            statuses.append(
                momentum_breakout_thesis_status(
                    pair_in_current_membership=pair in current_pairs,
                    prior_completed_close=prior_completed_close,
                    breakout_reference=momentum_breakout_reference,
                )
            )
        else:
            statuses.append(
                relative_strength_thesis_status(
                    pair=pair,
                    members=members,
                    return_72h_by_pair=return_72h_by_pair,
                )
            )
    if any(not status.evaluable for status in statuses):
        return ThesisAggregateStatus(
            False,
            None,
            None,
            "ONE_OR_MORE_SUPPORTING_THESES_UNAVAILABLE",
            tuple(statuses),
        )
    failed = all(status.failed is True for status in statuses)
    return ThesisAggregateStatus(
        True,
        failed,
        not failed,
        (
            "ALL_SUPPORTING_ENTRY_THESES_FAILED"
            if failed
            else "AT_LEAST_ONE_SUPPORTING_ENTRY_THESIS_RETAINED"
        ),
        tuple(statuses),
    )


def admission_decision(
    *,
    support_families: tuple[str, ...] | list[str],
    btc_state: str,
    market_context: MarketContextDecision,
    family_quality_enabled: bool,
) -> AdmissionDecision:
    families = _families(support_families)
    if not family_quality_enabled:
        router = capital_admission_decision(btc_state)
        return AdmissionDecision(
            True,
            router.admit_position,
            float(router.target_slot_fraction),
            "EXACT_RD27_ROUTER_ABLATION",
            families if router.admit_position else (),
        )

    admissible: list[tuple[str, float]] = []
    for family in families:
        if family == FAMILY_MOMENTUM_BREAKOUT:
            router = capital_admission_decision(btc_state)
            if router.admit_position:
                admissible.append((family, float(router.target_slot_fraction)))
        else:
            if market_context.breadth_ready and market_context.context == SUPPORTIVE:
                admissible.append((family, 0.18))
    if not admissible:
        return AdmissionDecision(
            True,
            False,
            0.0,
            "NO_SUPPORTING_FAMILY_ADMISSIBLE",
            (),
        )
    return AdmissionDecision(
        True,
        True,
        max(slot for _family, slot in admissible),
        "AT_LEAST_ONE_SUPPORTING_FAMILY_ADMISSIBLE",
        tuple(family for family, _slot in admissible),
    )


def new_thesis_position(
    *,
    pair: str,
    entry_time: pd.Timestamp,
    entry_price: float,
    atr24_at_signal: float,
    entry_market_context: str,
    support_families: tuple[str, ...] | list[str],
    momentum_breakout_reference: float | None,
) -> ThesisPosition:
    families = _families(support_families)
    if not pair:
        raise RD29ContextError("pair required")
    if not math.isfinite(entry_price) or entry_price <= 0.0:
        raise RD29ContextError("invalid entry price")
    if not math.isfinite(atr24_at_signal) or atr24_at_signal <= 0.0:
        raise RD29ContextError("invalid ATR")
    if entry_market_context not in MARKET_CONTEXTS:
        raise RD29ContextError("invalid entry market context")
    if FAMILY_MOMENTUM_BREAKOUT in families:
        if breakout := momentum_breakout_reference:
            if not math.isfinite(float(breakout)) or float(breakout) <= 0.0:
                raise RD29ContextError("invalid MB breakout reference")
        else:
            raise RD29ContextError("MB position requires breakout reference")
    return ThesisPosition(
        pair,
        _utc(entry_time),
        float(entry_price),
        float(atr24_at_signal),
        entry_market_context,
        families,
        (float(momentum_breakout_reference) if momentum_breakout_reference is not None else None),
        float(entry_price),
    )


def age_hours(position: ThesisPosition, current_open_time: pd.Timestamp) -> int:
    seconds = (_utc(current_open_time) - position.entry_time).total_seconds()
    if seconds < 0.0 or seconds % 3600.0 != 0.0:
        raise RD29ContextError("evaluation time must be hourly at/after entry")
    return int(seconds // 3600.0)


def is_thesis_checkpoint(age: int) -> bool:
    if age < 0:
        raise RD29ContextError("negative age")
    return age in THESIS_CHECKPOINT_HOURS


def evaluate_lifecycle_exit(
    position: ThesisPosition,
    *,
    current_open_time: pd.Timestamp,
    current_open: float,
    prior_completed_close: float,
    current_members: tuple[tuple[str, int], ...],
    return_72h_by_pair: dict[str, float | None],
    market_context: MarketContextDecision,
) -> LifecycleExitDecision:
    open_price = float(current_open)
    prior_close = float(prior_completed_close)
    if not math.isfinite(open_price) or open_price <= 0.0:
        raise RD29ContextError("invalid current open")
    if not math.isfinite(prior_close) or prior_close <= 0.0:
        raise RD29ContextError("invalid prior close")
    age = age_hours(position, current_open_time)
    checkpoint = is_thesis_checkpoint(age)
    arm = position.entry_price + PROFIT_ARM_ATR * position.atr24_at_signal
    armed = position.high_water_prior >= arm
    giveback = position.high_water_prior - PROFIT_GIVEBACK_ATR * position.atr24_at_signal
    if age >= MAX_HOLD_HOURS:
        return LifecycleExitDecision(
            True,
            open_price,
            MAX_HOLD_EXIT_REASON,
            age,
            checkpoint,
            market_context.context,
            False,
            None,
            armed,
        )
    if armed and prior_close <= giveback:
        return LifecycleExitDecision(
            True,
            open_price,
            PROFIT_GIVEBACK_EXIT_REASON,
            age,
            checkpoint,
            market_context.context,
            False,
            None,
            True,
        )
    if not checkpoint:
        return LifecycleExitDecision(
            False,
            None,
            None,
            age,
            False,
            market_context.context,
            False,
            None,
            armed,
        )
    thesis = aggregate_thesis_status(
        pair=position.pair,
        support_families=position.support_families,
        members=current_members,
        prior_completed_close=prior_close,
        return_72h_by_pair=return_72h_by_pair,
        momentum_breakout_reference=position.momentum_breakout_reference,
    )
    should_exit = thesis.evaluable and thesis.failed is True and market_context.context == STRESSED
    return LifecycleExitDecision(
        should_exit,
        open_price if should_exit else None,
        THESIS_FAILURE_EXIT_REASON if should_exit else None,
        age,
        True,
        market_context.context,
        thesis.evaluable,
        thesis.failed,
        armed,
    )


def apply_completed_high(
    position: ThesisPosition,
    *,
    completed_high: float,
) -> ThesisPosition:
    high = float(completed_high)
    if not math.isfinite(high) or high <= 0.0:
        raise RD29ContextError("invalid completed high")
    return replace(position, high_water_prior=max(position.high_water_prior, high))


def cooldown_after_exit(
    position: ThesisPosition,
    *,
    exit_time: pd.Timestamp,
    exit_reason: str,
    same_pair_cooldown_enabled: bool,
) -> PairCooldown | None:
    if not same_pair_cooldown_enabled:
        return None
    if exit_reason != THESIS_FAILURE_EXIT_REASON:
        return None
    release = position.entry_time + pd.Timedelta(hours=PAIR_COOLDOWN_RELEASE_HOURS)
    if _utc(exit_time) >= release:
        return None
    return PairCooldown(position.pair, release)


def pair_is_cooldown_blocked(
    cooldowns: tuple[PairCooldown, ...] | list[PairCooldown],
    *,
    pair: str,
    current_time: pd.Timestamp,
) -> bool:
    timestamp = _utc(current_time)
    return any(
        cooldown.pair == pair and timestamp < cooldown.release_time for cooldown in cooldowns
    )


def active_pair_cooldowns(
    cooldowns: tuple[PairCooldown, ...] | list[PairCooldown],
    *,
    current_time: pd.Timestamp,
) -> tuple[PairCooldown, ...]:
    timestamp = _utc(current_time)
    return tuple(cooldown for cooldown in cooldowns if timestamp < cooldown.release_time)


def policy_components(policy_id: str) -> dict[str, bool]:
    if policy_id == ROUTER_TIME_FAIL_72_CONTROL:
        return {
            "family_quality_admission": False,
            "thesis_confidence_exit": False,
            "profit_state": False,
            "same_pair_cooldown": False,
        }
    if policy_id == THESIS_CONFIDENCE_LIFECYCLE:
        return {
            "family_quality_admission": False,
            "thesis_confidence_exit": True,
            "profit_state": True,
            "same_pair_cooldown": False,
        }
    if policy_id == THESIS_CONFIDENCE_PAIR_COOLDOWN:
        return {
            "family_quality_admission": False,
            "thesis_confidence_exit": True,
            "profit_state": True,
            "same_pair_cooldown": True,
        }
    if policy_id == FULL_FAMILY_QUALITY_THESIS_BRAIN:
        return {
            "family_quality_admission": True,
            "thesis_confidence_exit": True,
            "profit_state": True,
            "same_pair_cooldown": True,
        }
    raise RD29ContextError(f"unknown policy: {policy_id}")


def active_component_count(policy_id: str) -> int:
    return 1 + sum(int(value) for value in policy_components(policy_id).values())


def contract_summary() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "stage": STAGE,
        "policies": list(POLICIES),
        "market_contexts": list(MARKET_CONTEXTS),
        "thesis_checkpoint_hours": list(THESIS_CHECKPOINT_HOURS),
        "maximum_hold_hours": MAX_HOLD_HOURS,
        "profit_arm_atr": PROFIT_ARM_ATR,
        "profit_giveback_atr": PROFIT_GIVEBACK_ATR,
        "pair_cooldown_release_hours": PAIR_COOLDOWN_RELEASE_HOURS,
        "breadth_missing_data_admission_behavior": "FAIL_CLOSED",
        "thesis_missing_data_exit_behavior": "FAIL_OPEN_HOLD",
        "global_slot_escrow": False,
        "current_bar_high_used_for_exit": False,
        "current_bar_low_used_for_exit": False,
        "partial_selling": False,
        "economic_execution_performed": False,
        "real_market_data_loader_present": False,
    }
