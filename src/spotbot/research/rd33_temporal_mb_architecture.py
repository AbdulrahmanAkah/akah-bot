"""RD33 causal temporal Momentum-Breakout architecture engine.

Pre-economic, filesystem-free engine. It never computes or mutates the RD31
governor. A pending MB origin may only be created from an already-computed
RD31 admission decision that independently admits Momentum Breakout.

Confirmation bars are completed bars only. Confirmation never reserves cash,
gross exposure, or a position slot. Actual entry is always the next 1h open
after the completed confirmation bar; portfolio replay is implemented later.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Final

import pandas as pd

from spotbot.research.rd26_exit_architecture import (
    FAMILY_MOMENTUM_BREAKOUT,
    FAMILY_RELATIVE_STRENGTH_ROTATION,
)
from spotbot.research.rd29_thesis_context import AdmissionDecision

SCHEMA_VERSION: Final = "rd33-temporal-mb-architecture-engine-v1"
STAGE: Final = "RD33_P0B_TEMPORAL_MB_ARCHITECTURE_ENGINE_PRE_ECONOMIC_EXECUTION"

RD31_REGIME_HYSTERESIS_CONTROL: Final = "RD31_REGIME_HYSTERESIS_CONTROL"
MB_ONE_BAR_BREAKOUT_LEVEL_HOLD: Final = "MB_ONE_BAR_BREAKOUT_LEVEL_HOLD"
MB_ONE_BAR_POST_BREAKOUT_CONTINUATION: Final = "MB_ONE_BAR_POST_BREAKOUT_CONTINUATION"
MB_FIRST_RETEST_RECLAIM_WITHIN_FROZEN_72H: Final = "MB_FIRST_RETEST_RECLAIM_WITHIN_FROZEN_72H"

CANDIDATE_POLICIES: Final = (
    MB_ONE_BAR_BREAKOUT_LEVEL_HOLD,
    MB_ONE_BAR_POST_BREAKOUT_CONTINUATION,
    MB_FIRST_RETEST_RECLAIM_WITHIN_FROZEN_72H,
)
POLICIES: Final = (RD31_REGIME_HYSTERESIS_CONTROL, *CANDIDATE_POLICIES)

PENDING: Final = "PENDING"
CONFIRMED: Final = "CONFIRMED"
REJECTED: Final = "REJECTED"
EXPIRED: Final = "EXPIRED"
CANCELLED: Final = "CANCELLED"
TERMINAL_STATUSES: Final = (CONFIRMED, REJECTED, EXPIRED, CANCELLED)

ONE_BAR_CONFIRMATION_HOURS: Final = 1
RETEST_WINDOW_HOURS: Final = 72


class RD33TemporalMBError(RuntimeError):
    """Raised when the preregistered temporal MB contract is violated."""


@dataclass(frozen=True)
class PendingMBOrigin:
    policy_id: str
    universe_id: str
    pair: str
    signal_time: pd.Timestamp
    normal_entry_time: pd.Timestamp
    breakout_reference: float
    signal_close: float
    membership_rank: int
    period_id: str
    target_slot_fraction: float
    origin_support_families: tuple[str, ...]
    origin_admissible_families: tuple[str, ...]
    origin_key: str


@dataclass(frozen=True)
class TemporalMBDecision:
    policy_id: str
    pair: str
    origin_key: str
    status: str
    reason: str
    completed_time: pd.Timestamp | None
    actual_entry_time: pd.Timestamp | None
    observed_low: float | None = None
    observed_close: float | None = None


@dataclass(frozen=True)
class PendingRegistrationDecision:
    accepted: bool
    reason: str
    pair: str
    owner_origin_key: str | None
    owner_signal_time: pd.Timestamp | None


def _utc(value: Any) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    return timestamp.tz_localize("UTC") if timestamp.tzinfo is None else timestamp.tz_convert("UTC")


def _finite_positive(value: Any, *, label: str) -> float:
    numeric = float(value)
    if not math.isfinite(numeric) or numeric <= 0.0:
        raise RD33TemporalMBError(f"{label} must be finite and positive")
    return numeric


def _rank(value: Any) -> int:
    if isinstance(value, bool):
        raise RD33TemporalMBError("membership_rank must be a positive integer")
    rank = int(value)
    if float(value) != float(rank) or rank <= 0:
        raise RD33TemporalMBError("membership_rank must be a positive integer")
    return rank


def _families(value: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    raw = tuple(value)
    result = tuple(sorted(set(raw)))
    if not result:
        raise RD33TemporalMBError("support family required")
    if len(raw) != len(result):
        raise RD33TemporalMBError("duplicate support family")
    unknown = sorted(
        set(result).difference(
            {
                FAMILY_MOMENTUM_BREAKOUT,
                FAMILY_RELATIVE_STRENGTH_ROTATION,
            }
        )
    )
    if unknown:
        raise RD33TemporalMBError(f"unknown support families: {unknown}")
    return result


def _origin_key(
    *,
    universe_id: str,
    pair: str,
    signal_time: pd.Timestamp,
) -> str:
    return f"{universe_id}|{pair}|{_utc(signal_time).isoformat()}"


def create_pending_origin(
    *,
    policy_id: str,
    universe_id: str,
    pair: str,
    signal_time: pd.Timestamp,
    breakout_reference: float,
    signal_close: float,
    membership_rank: int,
    period_id: str,
    support_families: tuple[str, ...] | list[str],
    rd31_decision: AdmissionDecision,
) -> PendingMBOrigin:
    """Create a pending MB origin after, and only after, frozen RD31 admission.

    This function receives the already-computed RD31 decision. It contains no
    governor transition function and cannot mutate governor state.
    """
    if policy_id not in CANDIDATE_POLICIES:
        raise RD33TemporalMBError(f"pending MB origin requires candidate policy: {policy_id}")
    if not universe_id or not pair or not period_id:
        raise RD33TemporalMBError("universe_id, pair, and period_id are required")

    support = _families(support_families)

    if FAMILY_MOMENTUM_BREAKOUT not in support:
        raise RD33TemporalMBError("raw origin is not an MB-supporting event")
    if not rd31_decision.admit_position:
        raise RD33TemporalMBError("RD31-suppressed MB cannot become pending")

    admissible = _families(list(rd31_decision.admissible_families))
    if FAMILY_MOMENTUM_BREAKOUT not in admissible:
        raise RD33TemporalMBError(
            "MB is not independently admissible under the frozen RD31 decision"
        )
    slot = float(rd31_decision.target_slot_fraction)
    if not math.isfinite(slot) or slot <= 0.0:
        raise RD33TemporalMBError("RD31-admitted MB requires positive slot")

    signal = _utc(signal_time)
    return PendingMBOrigin(
        policy_id=policy_id,
        universe_id=str(universe_id),
        pair=str(pair),
        signal_time=signal,
        normal_entry_time=signal + pd.Timedelta(hours=1),
        breakout_reference=_finite_positive(
            breakout_reference,
            label="breakout_reference",
        ),
        signal_close=_finite_positive(signal_close, label="signal_close"),
        membership_rank=_rank(membership_rank),
        period_id=str(period_id),
        target_slot_fraction=slot,
        origin_support_families=support,
        origin_admissible_families=admissible,
        origin_key=_origin_key(
            universe_id=str(universe_id),
            pair=str(pair),
            signal_time=signal,
        ),
    )


def pending_decision(origin: PendingMBOrigin) -> TemporalMBDecision:
    return TemporalMBDecision(
        policy_id=origin.policy_id,
        pair=origin.pair,
        origin_key=origin.origin_key,
        status=PENDING,
        reason="RD33_MB_PENDING_CONFIRMATION",
        completed_time=None,
        actual_entry_time=None,
    )


def register_pending(
    pending_by_pair: dict[str, PendingMBOrigin],
    origin: PendingMBOrigin,
) -> tuple[dict[str, PendingMBOrigin], PendingRegistrationDecision]:
    """Earliest pending origin owns the pair until resolved/cancelled."""
    result = dict(pending_by_pair)
    existing = result.get(origin.pair)
    if existing is None:
        result[origin.pair] = origin
        return result, PendingRegistrationDecision(
            accepted=True,
            reason="RD33_MB_PENDING_REGISTERED",
            pair=origin.pair,
            owner_origin_key=origin.origin_key,
            owner_signal_time=origin.signal_time,
        )

    if existing.signal_time > origin.signal_time:
        raise RD33TemporalMBError(
            "pending registry encountered a later owner before an earlier origin"
        )
    return result, PendingRegistrationDecision(
        accepted=False,
        reason="RD33_MB_PENDING_DUPLICATE_EARLIEST_OWNER_RETAINED",
        pair=origin.pair,
        owner_origin_key=existing.origin_key,
        owner_signal_time=existing.signal_time,
    )


def cancel_pending_for_rs_open(
    pending_by_pair: dict[str, PendingMBOrigin],
    *,
    pair: str,
) -> tuple[dict[str, PendingMBOrigin], TemporalMBDecision | None]:
    """An actual RS open cancels the same-pair pending MB without replacement."""
    result = dict(pending_by_pair)
    origin = result.pop(pair, None)
    if origin is None:
        return result, None
    return result, TemporalMBDecision(
        policy_id=origin.policy_id,
        pair=origin.pair,
        origin_key=origin.origin_key,
        status=CANCELLED,
        reason="RD33_MB_PENDING_CANCELLED_BY_RS_OPEN",
        completed_time=None,
        actual_entry_time=None,
    )


def remove_resolved_pending(
    pending_by_pair: dict[str, PendingMBOrigin],
    *,
    origin: PendingMBOrigin,
) -> dict[str, PendingMBOrigin]:
    result = dict(pending_by_pair)
    current = result.get(origin.pair)
    if current is None:
        raise RD33TemporalMBError("resolved pending origin is not registered")
    if current.origin_key != origin.origin_key:
        raise RD33TemporalMBError("resolved origin is not the current pair owner")
    del result[origin.pair]
    return result


def _bar_values(
    *,
    completed_time: pd.Timestamp,
    low: Any,
    close: Any,
) -> tuple[pd.Timestamp, float, float]:
    timestamp = _utc(completed_time)
    low_value = _finite_positive(low, label="completed bar low")
    close_value = _finite_positive(close, label="completed bar close")
    return timestamp, low_value, close_value


def _confirmed(
    origin: PendingMBOrigin,
    *,
    completed_time: pd.Timestamp,
    low: float,
    close: float,
    reason: str,
) -> TemporalMBDecision:
    return TemporalMBDecision(
        policy_id=origin.policy_id,
        pair=origin.pair,
        origin_key=origin.origin_key,
        status=CONFIRMED,
        reason=reason,
        completed_time=completed_time,
        actual_entry_time=completed_time + pd.Timedelta(hours=1),
        observed_low=low,
        observed_close=close,
    )


def _rejected(
    origin: PendingMBOrigin,
    *,
    completed_time: pd.Timestamp,
    low: float,
    close: float,
    reason: str,
) -> TemporalMBDecision:
    return TemporalMBDecision(
        policy_id=origin.policy_id,
        pair=origin.pair,
        origin_key=origin.origin_key,
        status=REJECTED,
        reason=reason,
        completed_time=completed_time,
        actual_entry_time=None,
        observed_low=low,
        observed_close=close,
    )


def evaluate_completed_bar(
    origin: PendingMBOrigin,
    *,
    completed_time: pd.Timestamp,
    low: Any,
    close: Any,
) -> TemporalMBDecision:
    """Evaluate one completed confirmation bar under the frozen architecture."""
    timestamp, low_value, close_value = _bar_values(
        completed_time=completed_time,
        low=low,
        close=close,
    )
    age_hours_float = (timestamp - origin.signal_time) / pd.Timedelta(hours=1)
    if not float(age_hours_float).is_integer():
        raise RD33TemporalMBError("confirmation bar must lie on the 1h clock")
    age_hours = int(age_hours_float)
    if age_hours < 1:
        raise RD33TemporalMBError(
            "confirmation cannot use signal bar or future-uncompleted evidence"
        )

    if origin.policy_id == MB_ONE_BAR_BREAKOUT_LEVEL_HOLD:
        if age_hours != ONE_BAR_CONFIRMATION_HOURS:
            raise RD33TemporalMBError("one-bar level-hold evaluates exactly signal_time + 1h")
        if close_value > origin.breakout_reference:
            return _confirmed(
                origin,
                completed_time=timestamp,
                low=low_value,
                close=close_value,
                reason="RD33_MB_LEVEL_HOLD_CONFIRMED",
            )
        return _rejected(
            origin,
            completed_time=timestamp,
            low=low_value,
            close=close_value,
            reason="RD33_MB_LEVEL_HOLD_FAILED",
        )

    if origin.policy_id == MB_ONE_BAR_POST_BREAKOUT_CONTINUATION:
        if age_hours != ONE_BAR_CONFIRMATION_HOURS:
            raise RD33TemporalMBError("one-bar continuation evaluates exactly signal_time + 1h")
        if close_value > origin.signal_close:
            return _confirmed(
                origin,
                completed_time=timestamp,
                low=low_value,
                close=close_value,
                reason="RD33_MB_POST_BREAKOUT_CONTINUATION_CONFIRMED",
            )
        return _rejected(
            origin,
            completed_time=timestamp,
            low=low_value,
            close=close_value,
            reason="RD33_MB_POST_BREAKOUT_CONTINUATION_FAILED",
        )

    if origin.policy_id == MB_FIRST_RETEST_RECLAIM_WITHIN_FROZEN_72H:
        if age_hours > RETEST_WINDOW_HOURS:
            raise RD33TemporalMBError("retest evaluation exceeded frozen 72h window")
        reclaimed = (
            low_value <= origin.breakout_reference and close_value > origin.breakout_reference
        )
        if reclaimed:
            return _confirmed(
                origin,
                completed_time=timestamp,
                low=low_value,
                close=close_value,
                reason="RD33_MB_FIRST_RETEST_RECLAIM_CONFIRMED",
            )
        if age_hours == RETEST_WINDOW_HOURS:
            return TemporalMBDecision(
                policy_id=origin.policy_id,
                pair=origin.pair,
                origin_key=origin.origin_key,
                status=EXPIRED,
                reason="RD33_MB_RETEST_WINDOW_72H_EXPIRED",
                completed_time=timestamp,
                actual_entry_time=None,
                observed_low=low_value,
                observed_close=close_value,
            )
        return TemporalMBDecision(
            policy_id=origin.policy_id,
            pair=origin.pair,
            origin_key=origin.origin_key,
            status=PENDING,
            reason="RD33_MB_RETEST_RECLAIM_STILL_PENDING",
            completed_time=timestamp,
            actual_entry_time=None,
            observed_low=low_value,
            observed_close=close_value,
        )

    raise RD33TemporalMBError(f"unknown temporal MB policy: {origin.policy_id}")


def missing_confirmation_bar_decision(
    origin: PendingMBOrigin,
    *,
    expected_completed_time: pd.Timestamp,
) -> TemporalMBDecision:
    """Fail closed when a required completed bar is unavailable."""
    timestamp = _utc(expected_completed_time)
    age_hours = int((timestamp - origin.signal_time) / pd.Timedelta(hours=1))
    if origin.policy_id in (
        MB_ONE_BAR_BREAKOUT_LEVEL_HOLD,
        MB_ONE_BAR_POST_BREAKOUT_CONTINUATION,
    ):
        if age_hours != 1:
            raise RD33TemporalMBError("one-bar missing-confirmation timestamp must be +1h")
        return TemporalMBDecision(
            policy_id=origin.policy_id,
            pair=origin.pair,
            origin_key=origin.origin_key,
            status=REJECTED,
            reason="RD33_MB_REQUIRED_ONE_BAR_CONFIRMATION_UNAVAILABLE",
            completed_time=timestamp,
            actual_entry_time=None,
        )
    if origin.policy_id == MB_FIRST_RETEST_RECLAIM_WITHIN_FROZEN_72H:
        if age_hours < 1 or age_hours > RETEST_WINDOW_HOURS:
            raise RD33TemporalMBError("retest missing-bar timestamp outside frozen 72h window")
        if age_hours == RETEST_WINDOW_HOURS:
            return TemporalMBDecision(
                policy_id=origin.policy_id,
                pair=origin.pair,
                origin_key=origin.origin_key,
                status=EXPIRED,
                reason="RD33_MB_RETEST_WINDOW_ENDED_WITH_UNAVAILABLE_FINAL_BAR",
                completed_time=timestamp,
                actual_entry_time=None,
            )
        return TemporalMBDecision(
            policy_id=origin.policy_id,
            pair=origin.pair,
            origin_key=origin.origin_key,
            status=PENDING,
            reason="RD33_MB_RETEST_MISSING_BAR_STILL_PENDING",
            completed_time=timestamp,
            actual_entry_time=None,
        )
    raise RD33TemporalMBError(f"unknown temporal MB policy: {origin.policy_id}")


def active_component_count(policy_id: str) -> int:
    if policy_id == RD31_REGIME_HYSTERESIS_CONTROL:
        return 3
    if policy_id in CANDIDATE_POLICIES:
        return 4
    raise RD33TemporalMBError(f"unknown RD33 policy: {policy_id}")


def contract_summary() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "stage": STAGE,
        "policies": list(POLICIES),
        "candidate_policies": list(CANDIDATE_POLICIES),
        "governor_transition_function_present": False,
        "confirmation_engine_can_mutate_governor": False,
        "pending_requires_precomputed_rd31_mb_admission": True,
        "rd31_suppressed_mb_can_become_pending": False,
        "pending_consumes_position_slot": False,
        "pending_reserves_cash": False,
        "pending_reserves_gross_exposure": False,
        "same_pair_earliest_pending_owner": True,
        "rs_open_cancels_same_pair_pending_mb": True,
        "one_bar_confirmation_completed_hours_after_signal": 1,
        "retest_window_hours": 72,
        "actual_entry_is_next_1h_open_after_confirmation": True,
        "confirmation_uses_completed_bar_only": True,
        "numeric_confirmation_margin": None,
        "pair_blacklist": False,
        "calendar_year_rule": False,
        "parameter_grid_search": False,
        "exit_change": False,
        "sizing_change": False,
        "cost_change": False,
        "economic_execution_performed": False,
        "real_market_data_loader_present": False,
        "raw_market_data_loaded": False,
        "2024_accessed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
    }
