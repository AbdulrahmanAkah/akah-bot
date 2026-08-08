"""RD32 MB signal-quality admission engine.

This module is pre-economic and filesystem-free. It delegates the market-regime
transition and baseline family admission to the exact frozen RD31 governor, then
applies at most one monotonic veto to Momentum Breakout support.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Final

from spotbot.research.rd26_exit_architecture import (
    FAMILY_MOMENTUM_BREAKOUT,
    FAMILY_RELATIVE_STRENGTH_ROTATION,
)
from spotbot.research.rd29_thesis_context import (
    SUPPORTIVE,
    AdmissionDecision,
    MarketContextDecision,
    relative_strength_rank,
)
from spotbot.research.rd31_regime_admission_governor import (
    REGIME_HYSTERESIS_ADMISSION_GOVERNOR,
    GovernedAdmissionDecision,
)
from spotbot.research.rd31_regime_admission_governor import (
    admission_decision as rd31_admission_decision,
)

SCHEMA_VERSION: Final = "rd32-mb-signal-quality-admission-engine-v1"
STAGE: Final = "RD32_P2B_MB_SIGNAL_QUALITY_ADMISSION_ENGINE_PRE_ECONOMIC_EXECUTION"

RD31_REGIME_HYSTERESIS_CONTROL: Final = "RD31_REGIME_HYSTERESIS_CONTROL"
MB_CROSS_SECTIONAL_BREAKOUT_LEADER: Final = "MB_CROSS_SECTIONAL_BREAKOUT_LEADER"
MB_BREADTH_ACCELERATION_CONFIRMATION: Final = "MB_BREADTH_ACCELERATION_CONFIRMATION"
MB_RELATIVE_STRENGTH_LEADER_CONFIRMATION: Final = "MB_RELATIVE_STRENGTH_LEADER_CONFIRMATION"
POLICIES: Final = (
    RD31_REGIME_HYSTERESIS_CONTROL,
    MB_CROSS_SECTIONAL_BREAKOUT_LEADER,
    MB_BREADTH_ACCELERATION_CONFIRMATION,
    MB_RELATIVE_STRENGTH_LEADER_CONFIRMATION,
)

FOCUS_FAMILIES: Final = (
    FAMILY_MOMENTUM_BREAKOUT,
    FAMILY_RELATIVE_STRENGTH_ROTATION,
)


class RD32AdmissionError(RuntimeError):
    """Raised when the frozen RD32 admission-quality contract is violated."""


@dataclass(frozen=True)
class MBQualityEvidence:
    """Causal evidence available at the already-completed signal bar."""

    mb_candidate_rank: int | None = None
    prior_breadth_median_return_72h: float | None = None
    current_members: tuple[tuple[str, int], ...] | None = None
    current_return_72h_by_pair: dict[str, float | None] | None = None


@dataclass(frozen=True)
class MBQualityDecision:
    policy_id: str
    evaluated: bool
    retained: bool | None
    reason: str
    mb_candidate_rank: int | None = None
    current_breadth_median_return_72h: float | None = None
    prior_breadth_median_return_72h: float | None = None
    rs_rank_evaluable: bool | None = None
    pair_return_72h: float | None = None
    pair_relative_strength_rank: int | None = None


@dataclass(frozen=True)
class RD32GovernedAdmissionDecision:
    policy_id: str
    rd31_control: GovernedAdmissionDecision
    quality: MBQualityDecision
    decision: AdmissionDecision


def _families(
    support_families: tuple[str, ...] | list[str],
) -> tuple[str, ...]:
    values = tuple(support_families)
    result = tuple(sorted(set(values)))
    if not result:
        raise RD32AdmissionError("support family required")
    if len(values) != len(result):
        raise RD32AdmissionError("duplicate support family")
    unknown = sorted(set(result).difference(FOCUS_FAMILIES))
    if unknown:
        raise RD32AdmissionError(f"unknown support families: {unknown}")
    return result


def _finite_or_none(value: float | None, *, label: str) -> float | None:
    if value is None:
        return None
    numeric = float(value)
    if not math.isfinite(numeric):
        raise RD32AdmissionError(f"{label} must be finite when available")
    return numeric


def _candidate_rank(value: int | None) -> int:
    if value is None:
        raise RD32AdmissionError("MB candidate rank required")
    if isinstance(value, bool):
        raise RD32AdmissionError("MB candidate rank must be an integer")
    rank = int(value)
    if float(value) != float(rank) or rank <= 0:
        raise RD32AdmissionError("MB candidate rank must be a positive integer")
    return rank


def _control_quality() -> MBQualityDecision:
    return MBQualityDecision(
        policy_id=RD31_REGIME_HYSTERESIS_CONTROL,
        evaluated=False,
        retained=None,
        reason="RD32_CONTROL_NO_MB_QUALITY_VETO",
    )


def _not_applicable_quality(policy_id: str) -> MBQualityDecision:
    return MBQualityDecision(
        policy_id=policy_id,
        evaluated=False,
        retained=None,
        reason="RD32_MB_NOT_ADMISSIBLE_UNDER_EXACT_RD31",
    )


def _breakout_leader_quality(
    evidence: MBQualityEvidence,
) -> MBQualityDecision:
    rank = _candidate_rank(evidence.mb_candidate_rank)
    retained = rank == 1
    return MBQualityDecision(
        policy_id=MB_CROSS_SECTIONAL_BREAKOUT_LEADER,
        evaluated=True,
        retained=retained,
        reason=(
            "RD32_MB_BREAKOUT_LEADER_RETAINED" if retained else "RD32_MB_BREAKOUT_NONLEADER_VETOED"
        ),
        mb_candidate_rank=rank,
    )


def _breadth_acceleration_quality(
    *,
    market_context: MarketContextDecision,
    evidence: MBQualityEvidence,
) -> MBQualityDecision:
    current = _finite_or_none(
        market_context.breadth_median_return_72h,
        label="current breadth median return 72h",
    )
    prior = _finite_or_none(
        evidence.prior_breadth_median_return_72h,
        label="prior breadth median return 72h",
    )
    ready = (
        market_context.context == SUPPORTIVE
        and market_context.breadth_ready
        and current is not None
        and prior is not None
    )
    retained = bool(ready and current > prior)
    if not ready:
        reason = "RD32_MB_BREADTH_ACCELERATION_UNAVAILABLE_OR_NOT_SUPPORTIVE_VETOED"
    elif retained:
        reason = "RD32_MB_BREADTH_ACCELERATION_RETAINED"
    else:
        reason = "RD32_MB_BREADTH_NOT_ACCELERATING_VETOED"
    return MBQualityDecision(
        policy_id=MB_BREADTH_ACCELERATION_CONFIRMATION,
        evaluated=True,
        retained=retained,
        reason=reason,
        current_breadth_median_return_72h=current,
        prior_breadth_median_return_72h=prior,
    )


def _relative_strength_leader_quality(
    *,
    pair: str,
    evidence: MBQualityEvidence,
) -> MBQualityDecision:
    members = evidence.current_members
    returns = evidence.current_return_72h_by_pair
    if members is None or returns is None:
        raise RD32AdmissionError(
            "current PIT members and return72 map required for RS-leader confirmation"
        )
    try:
        evaluable, pair_return, rank = relative_strength_rank(
            pair=pair,
            members=members,
            return_72h_by_pair=returns,
        )
    except Exception as exc:
        raise RD32AdmissionError("exact RD29 relative-strength ranking failed") from exc
    pair_return = _finite_or_none(
        pair_return,
        label="pair return 72h",
    )
    retained = bool(evaluable and pair_return is not None and rank == 1 and pair_return > 0.0)
    if not evaluable:
        reason = "RD32_MB_RS_LEADER_RANK_UNAVAILABLE_VETOED"
    elif pair_return is None or rank is None:
        reason = "RD32_MB_RS_LEADER_PAIR_NOT_RANKED_VETOED"
    elif pair_return <= 0.0:
        reason = "RD32_MB_RS_LEADER_NONPOSITIVE_RETURN_VETOED"
    elif rank != 1:
        reason = "RD32_MB_RS_LEADER_NOT_RANK1_VETOED"
    else:
        reason = "RD32_MB_RS_LEADER_RETAINED"
    return MBQualityDecision(
        policy_id=MB_RELATIVE_STRENGTH_LEADER_CONFIRMATION,
        evaluated=True,
        retained=retained,
        reason=reason,
        rs_rank_evaluable=bool(evaluable),
        pair_return_72h=pair_return,
        pair_relative_strength_rank=rank,
    )


def evaluate_mb_quality(
    *,
    policy_id: str,
    pair: str,
    market_context: MarketContextDecision,
    evidence: MBQualityEvidence,
) -> MBQualityDecision:
    """Evaluate exactly one preregistered MB-quality veto."""
    if policy_id == RD31_REGIME_HYSTERESIS_CONTROL:
        return _control_quality()
    if policy_id == MB_CROSS_SECTIONAL_BREAKOUT_LEADER:
        return _breakout_leader_quality(evidence)
    if policy_id == MB_BREADTH_ACCELERATION_CONFIRMATION:
        return _breadth_acceleration_quality(
            market_context=market_context,
            evidence=evidence,
        )
    if policy_id == MB_RELATIVE_STRENGTH_LEADER_CONFIRMATION:
        return _relative_strength_leader_quality(
            pair=pair,
            evidence=evidence,
        )
    raise RD32AdmissionError(f"unknown RD32 policy: {policy_id}")


def _candidate_decision_after_veto(
    *,
    policy_id: str,
    control: AdmissionDecision,
    quality: MBQualityDecision,
) -> AdmissionDecision:
    if quality.retained is not False:
        return control

    remaining = tuple(
        family for family in control.admissible_families if family != FAMILY_MOMENTUM_BREAKOUT
    )
    if remaining:
        return AdmissionDecision(
            record_signal=control.record_signal,
            admit_position=control.admit_position,
            target_slot_fraction=control.target_slot_fraction,
            reason=f"RD32_{policy_id}_MB_VETO_RS_RETAINED",
            admissible_families=remaining,
        )
    return AdmissionDecision(
        record_signal=control.record_signal,
        admit_position=False,
        target_slot_fraction=0.0,
        reason=f"RD32_{policy_id}_MB_VETO_SUPPRESSED",
        admissible_families=(),
    )


def _assert_monotonic(
    *,
    control: GovernedAdmissionDecision,
    candidate: AdmissionDecision,
) -> None:
    original = control.decision
    if candidate.admit_position and not original.admit_position:
        raise RD32AdmissionError("candidate created admission suppressed by RD31")
    if candidate.target_slot_fraction > original.target_slot_fraction + 1e-12:
        raise RD32AdmissionError("candidate increased target slot fraction")
    if not set(candidate.admissible_families).issubset(set(original.admissible_families)):
        raise RD32AdmissionError("candidate created new admissible family")
    if candidate.record_signal != original.record_signal:
        raise RD32AdmissionError("candidate changed record_signal semantics")
    if candidate.admit_position and not candidate.admissible_families:
        raise RD32AdmissionError("admitted candidate lacks admissible family")
    if not candidate.admit_position and candidate.target_slot_fraction != 0.0:
        raise RD32AdmissionError("suppressed candidate has nonzero slot")


def admission_decision(
    *,
    policy_id: str,
    pair: str,
    support_families: tuple[str, ...] | list[str],
    btc_state: str,
    market_context: MarketContextDecision,
    governor_prior_state: str,
    evidence: MBQualityEvidence | None = None,
) -> RD32GovernedAdmissionDecision:
    """Run exact RD31 Hysteresis once, then apply a monotonic MB-only veto."""
    families = _families(support_families)
    if policy_id not in POLICIES:
        raise RD32AdmissionError(f"unknown RD32 policy: {policy_id}")
    if not pair:
        raise RD32AdmissionError("pair required")

    control = rd31_admission_decision(
        policy_id=REGIME_HYSTERESIS_ADMISSION_GOVERNOR,
        support_families=families,
        btc_state=btc_state,
        market_context=market_context,
        governor_prior_state=governor_prior_state,
    )

    if policy_id == RD31_REGIME_HYSTERESIS_CONTROL:
        return RD32GovernedAdmissionDecision(
            policy_id=policy_id,
            rd31_control=control,
            quality=_control_quality(),
            decision=control.decision,
        )

    if FAMILY_MOMENTUM_BREAKOUT not in control.decision.admissible_families:
        candidate = control.decision
        quality = _not_applicable_quality(policy_id)
        _assert_monotonic(control=control, candidate=candidate)
        return RD32GovernedAdmissionDecision(
            policy_id=policy_id,
            rd31_control=control,
            quality=quality,
            decision=candidate,
        )

    if evidence is None:
        raise RD32AdmissionError("MB quality evidence required when MB is RD31-admissible")
    quality = evaluate_mb_quality(
        policy_id=policy_id,
        pair=pair,
        market_context=market_context,
        evidence=evidence,
    )
    candidate = _candidate_decision_after_veto(
        policy_id=policy_id,
        control=control.decision,
        quality=quality,
    )
    _assert_monotonic(control=control, candidate=candidate)

    return RD32GovernedAdmissionDecision(
        policy_id=policy_id,
        rd31_control=control,
        quality=quality,
        decision=candidate,
    )


def active_component_count(policy_id: str) -> int:
    """RD31 Hysteresis has three components; each candidate adds one veto."""
    if policy_id == RD31_REGIME_HYSTERESIS_CONTROL:
        return 3
    if policy_id in (
        MB_CROSS_SECTIONAL_BREAKOUT_LEADER,
        MB_BREADTH_ACCELERATION_CONFIRMATION,
        MB_RELATIVE_STRENGTH_LEADER_CONFIRMATION,
    ):
        return 4
    raise RD32AdmissionError(f"unknown RD32 policy: {policy_id}")


def contract_summary() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "stage": STAGE,
        "policies": list(POLICIES),
        "exact_rd31_policy": REGIME_HYSTERESIS_ADMISSION_GOVERNOR,
        "rd31_runs_before_mb_veto": True,
        "governor_transition_recomputed_after_veto": False,
        "mb_filter_is_monotonic_veto_only": True,
        "candidate_can_create_new_admission": False,
        "candidate_can_increase_slot": False,
        "candidate_can_create_new_family": False,
        "rs_only_path_unchanged": True,
        "overlap_rs_survives_failed_mb_if_rd31_admitted_rs": True,
        "cross_sectional_breakout_rank_threshold": 1,
        "breadth_acceleration_numeric_delta_threshold": None,
        "breadth_acceleration_comparator": "CURRENT_STRICTLY_GREATER_THAN_PRIOR",
        "breadth_unavailable_fail_closed": True,
        "rs_leader_rank_threshold": 1,
        "rs_leader_positive_return_required": True,
        "rs_leader_uses_exact_rd29_relative_strength_rank": True,
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
        "economic_execution_performed": False,
        "real_market_data_loader_present": False,
        "raw_market_data_loaded": False,
        "2024_accessed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
    }
