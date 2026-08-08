from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

from spotbot.research.rd26_exit_architecture import (
    FAMILY_MOMENTUM_BREAKOUT,
    FAMILY_RELATIVE_STRENGTH_ROTATION,
)
from spotbot.research.rd27_adaptive_lifecycle import (
    RISK_OFF,
    RISK_ON,
    TRANSITION,
)
from spotbot.research.rd29_thesis_context import (
    MARKET_CONTEXTS,
    MIXED,
    STRESSED,
    SUPPORTIVE,
    AdmissionDecision,
    MarketContextDecision,
)
from spotbot.research.rd30_family_specialist_state import (
    FAMILY_QUALITY_CONTROL_EXITS as RD30_FAMILY_QUALITY_CONTROL_EXITS,
)
from spotbot.research.rd30_family_specialist_state import (
    admission_decision as rd30_admission_decision,
)

SCHEMA_VERSION: Final = "rd31-regime-admission-governor-v1"
STAGE: Final = "RD31_P0B_CAUSAL_REGIME_ADMISSION_GOVERNOR_PRE_ECONOMIC_EXECUTION"

FAMILY_QUALITY_CONTROL_EXITS: Final = "FAMILY_QUALITY_CONTROL_EXITS"
STRESSED_CONTEXT_MB_EXCLUSION: Final = "STRESSED_CONTEXT_MB_EXCLUSION"
SUPPORTIVE_ONLY_ALL_FAMILIES: Final = "SUPPORTIVE_ONLY_ALL_FAMILIES"
REGIME_HYSTERESIS_ADMISSION_GOVERNOR: Final = "REGIME_HYSTERESIS_ADMISSION_GOVERNOR"
POLICIES: Final = (
    FAMILY_QUALITY_CONTROL_EXITS,
    STRESSED_CONTEXT_MB_EXCLUSION,
    SUPPORTIVE_ONLY_ALL_FAMILIES,
    REGIME_HYSTERESIS_ADMISSION_GOVERNOR,
)

OPEN: Final = "OPEN"
CAUTION: Final = "CAUTION"
LOCKED: Final = "LOCKED"
GOVERNOR_STATES: Final = (OPEN, CAUTION, LOCKED)

FOCUS_FAMILIES: Final = (
    FAMILY_MOMENTUM_BREAKOUT,
    FAMILY_RELATIVE_STRENGTH_ROTATION,
)


class RD31GovernorError(RuntimeError):
    pass


@dataclass(frozen=True)
class GovernorTransition:
    prior_state: str
    next_state: str
    market_context: str
    changed: bool
    reason: str


@dataclass(frozen=True)
class GovernedAdmissionDecision:
    policy_id: str
    governor_prior_state: str | None
    governor_next_state: str | None
    transition_reason: str | None
    market_context: str
    decision: AdmissionDecision


def _families(
    support_families: tuple[str, ...] | list[str],
) -> tuple[str, ...]:
    result = tuple(sorted(set(support_families)))
    if not result:
        raise RD31GovernorError("support family required")
    unknown = set(result).difference(FOCUS_FAMILIES)
    if unknown:
        raise RD31GovernorError(f"unknown support families: {sorted(unknown)}")
    return result


def _validate_context(market_context: MarketContextDecision) -> None:
    if market_context.context not in MARKET_CONTEXTS:
        raise RD31GovernorError(f"unknown market context: {market_context.context}")
    if market_context.btc_state not in (RISK_ON, TRANSITION, RISK_OFF):
        raise RD31GovernorError(f"unknown BTC state: {market_context.btc_state}")


def _validate_btc_alignment(
    btc_state: str,
    market_context: MarketContextDecision,
) -> None:
    _validate_context(market_context)
    if btc_state != market_context.btc_state:
        raise RD31GovernorError("btc_state must match market_context.btc_state")


def _decision(
    *,
    admit: bool,
    slot: float,
    reason: str,
    admissible_families: tuple[str, ...],
) -> AdmissionDecision:
    return AdmissionDecision(
        record_signal=True,
        admit_position=admit,
        target_slot_fraction=float(slot),
        reason=reason,
        admissible_families=admissible_families,
    )


def baseline_family_quality_admission(
    *,
    support_families: tuple[str, ...] | list[str],
    btc_state: str,
    market_context: MarketContextDecision,
) -> AdmissionDecision:
    return rd30_admission_decision(
        policy_id=RD30_FAMILY_QUALITY_CONTROL_EXITS,
        support_families=support_families,
        btc_state=btc_state,
        market_context=market_context,
    )


def stressed_context_mb_exclusion_admission(
    *,
    support_families: tuple[str, ...] | list[str],
    btc_state: str,
    market_context: MarketContextDecision,
) -> AdmissionDecision:
    families = _families(support_families)
    _validate_btc_alignment(btc_state, market_context)

    admissible: list[tuple[str, float]] = []
    for family in families:
        if family == FAMILY_MOMENTUM_BREAKOUT:
            baseline = baseline_family_quality_admission(
                support_families=(FAMILY_MOMENTUM_BREAKOUT,),
                btc_state=btc_state,
                market_context=market_context,
            )
            if market_context.context != STRESSED and baseline.admit_position:
                admissible.append(
                    (
                        FAMILY_MOMENTUM_BREAKOUT,
                        float(baseline.target_slot_fraction),
                    )
                )
        elif market_context.breadth_ready and market_context.context == SUPPORTIVE:
            admissible.append((FAMILY_RELATIVE_STRENGTH_ROTATION, 0.18))

    if not admissible:
        return _decision(
            admit=False,
            slot=0.0,
            reason="RD31_STRESSED_CONTEXT_MB_EXCLUSION_NO_FAMILY_ADMISSIBLE",
            admissible_families=(),
        )
    return _decision(
        admit=True,
        slot=max(slot for _family, slot in admissible),
        reason="RD31_STRESSED_CONTEXT_MB_EXCLUSION_ADMITTED",
        admissible_families=tuple(family for family, _slot in admissible),
    )


def supportive_only_all_families_admission(
    *,
    support_families: tuple[str, ...] | list[str],
    market_context: MarketContextDecision,
) -> AdmissionDecision:
    families = _families(support_families)
    _validate_context(market_context)
    if market_context.breadth_ready and market_context.context == SUPPORTIVE:
        return _decision(
            admit=True,
            slot=0.18,
            reason="RD31_SUPPORTIVE_ONLY_ALL_FAMILIES_ADMITTED",
            admissible_families=families,
        )
    return _decision(
        admit=False,
        slot=0.0,
        reason="RD31_SUPPORTIVE_ONLY_ALL_FAMILIES_SUPPRESSED",
        admissible_families=(),
    )


def transition_governor(
    *,
    prior_state: str,
    market_context: str,
) -> GovernorTransition:
    if prior_state not in GOVERNOR_STATES:
        raise RD31GovernorError(f"unknown governor state: {prior_state}")
    if market_context not in MARKET_CONTEXTS:
        raise RD31GovernorError(f"unknown market context: {market_context}")

    if market_context == STRESSED:
        next_state = LOCKED
        reason = "STRESSED_LOCKS_ADMISSIONS"
    elif market_context == SUPPORTIVE:
        next_state = OPEN
        reason = "SUPPORTIVE_OPENS_ADMISSIONS"
    elif market_context == MIXED:
        if prior_state == OPEN:
            next_state = CAUTION
            reason = "OPEN_MIXED_TO_CAUTION"
        elif prior_state == CAUTION:
            next_state = CAUTION
            reason = "CAUTION_MIXED_STAYS_CAUTION"
        else:
            next_state = LOCKED
            reason = "LOCKED_MIXED_STAYS_LOCKED"
    else:
        next_state = prior_state
        reason = "UNAVAILABLE_PERSISTS_GOVERNOR_STATE"

    return GovernorTransition(
        prior_state=prior_state,
        next_state=next_state,
        market_context=market_context,
        changed=next_state != prior_state,
        reason=reason,
    )


def hysteresis_governor_admission(
    *,
    prior_state: str,
    support_families: tuple[str, ...] | list[str],
    btc_state: str,
    market_context: MarketContextDecision,
) -> GovernedAdmissionDecision:
    families = _families(support_families)
    _validate_btc_alignment(btc_state, market_context)
    transition = transition_governor(
        prior_state=prior_state,
        market_context=market_context.context,
    )
    state = transition.next_state

    if state == LOCKED:
        decision = _decision(
            admit=False,
            slot=0.0,
            reason="RD31_GOVERNOR_LOCKED_SUPPRESS_ALL",
            admissible_families=(),
        )
    elif state == OPEN:
        decision = baseline_family_quality_admission(
            support_families=families,
            btc_state=btc_state,
            market_context=market_context,
        )
    elif state == CAUTION:
        admissible: list[tuple[str, float]] = []
        if (
            FAMILY_MOMENTUM_BREAKOUT in families
            and btc_state == TRANSITION
            and market_context.context == MIXED
        ):
            admissible.append((FAMILY_MOMENTUM_BREAKOUT, 0.09))
        if (
            FAMILY_RELATIVE_STRENGTH_ROTATION in families
            and market_context.breadth_ready
            and market_context.context == SUPPORTIVE
        ):
            admissible.append((FAMILY_RELATIVE_STRENGTH_ROTATION, 0.18))
        if admissible:
            decision = _decision(
                admit=True,
                slot=max(slot for _family, slot in admissible),
                reason="RD31_GOVERNOR_CAUTION_ADMITTED",
                admissible_families=tuple(family for family, _slot in admissible),
            )
        else:
            decision = _decision(
                admit=False,
                slot=0.0,
                reason="RD31_GOVERNOR_CAUTION_SUPPRESSED",
                admissible_families=(),
            )
    else:
        raise RD31GovernorError("unreachable governor state")

    return GovernedAdmissionDecision(
        policy_id=REGIME_HYSTERESIS_ADMISSION_GOVERNOR,
        governor_prior_state=prior_state,
        governor_next_state=state,
        transition_reason=transition.reason,
        market_context=market_context.context,
        decision=decision,
    )


def admission_decision(
    *,
    policy_id: str,
    support_families: tuple[str, ...] | list[str],
    btc_state: str,
    market_context: MarketContextDecision,
    governor_prior_state: str = OPEN,
) -> GovernedAdmissionDecision:
    _families(support_families)
    _validate_btc_alignment(btc_state, market_context)

    if policy_id == FAMILY_QUALITY_CONTROL_EXITS:
        decision = baseline_family_quality_admission(
            support_families=support_families,
            btc_state=btc_state,
            market_context=market_context,
        )
        return GovernedAdmissionDecision(
            policy_id,
            None,
            None,
            None,
            market_context.context,
            decision,
        )

    if policy_id == STRESSED_CONTEXT_MB_EXCLUSION:
        decision = stressed_context_mb_exclusion_admission(
            support_families=support_families,
            btc_state=btc_state,
            market_context=market_context,
        )
        return GovernedAdmissionDecision(
            policy_id,
            None,
            None,
            None,
            market_context.context,
            decision,
        )

    if policy_id == SUPPORTIVE_ONLY_ALL_FAMILIES:
        decision = supportive_only_all_families_admission(
            support_families=support_families,
            market_context=market_context,
        )
        return GovernedAdmissionDecision(
            policy_id,
            None,
            None,
            None,
            market_context.context,
            decision,
        )

    if policy_id == REGIME_HYSTERESIS_ADMISSION_GOVERNOR:
        return hysteresis_governor_admission(
            prior_state=governor_prior_state,
            support_families=support_families,
            btc_state=btc_state,
            market_context=market_context,
        )

    raise RD31GovernorError(f"unknown policy: {policy_id}")


def active_component_count(policy_id: str) -> int:
    if policy_id == FAMILY_QUALITY_CONTROL_EXITS:
        return 1
    if policy_id in (
        STRESSED_CONTEXT_MB_EXCLUSION,
        SUPPORTIVE_ONLY_ALL_FAMILIES,
    ):
        return 2
    if policy_id == REGIME_HYSTERESIS_ADMISSION_GOVERNOR:
        return 3
    raise RD31GovernorError(f"unknown policy: {policy_id}")


def contract_summary() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "stage": STAGE,
        "policies": list(POLICIES),
        "governor_states": list(GOVERNOR_STATES),
        "initial_governor_state": OPEN,
        "baseline_source": "EXACT_RD30_FAMILY_QUALITY_CONTROL_EXITS",
        "rs_supportive_only_preserved": True,
        "governor_duration_parameter": False,
        "unavailable_context_transition": "PERSIST_PRIOR_STATE",
        "forced_regime_exit": False,
        "profit_giveback": False,
        "replacement": False,
        "thesis_failure_exit": False,
        "parameter_grid_search": False,
        "calendar_year_feature": False,
        "economic_execution_performed": False,
        "real_market_data_loader_present": False,
        "2024_accessed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
    }
