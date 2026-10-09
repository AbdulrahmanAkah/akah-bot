"""Research-only RD31 lock-semantics candidate.

Single frozen delta:
    baseline:  LOCKED + MIXED -> LOCKED
    candidate: LOCKED + MIXED -> CAUTION

Everything else delegates to the frozen RD31 governor. The candidate is disabled
by default and has no market-data loader, replay runner, or production hook.
"""

from __future__ import annotations

from typing import Final

from spotbot.research.rd29_thesis_context import (
    MIXED,
    MarketContextDecision,
)
from spotbot.research.rd31_regime_admission_governor import (
    CAUTION,
    LOCKED,
    OPEN,
    REGIME_HYSTERESIS_ADMISSION_GOVERNOR,
    GovernedAdmissionDecision,
    GovernorTransition,
    hysteresis_governor_admission,
    transition_governor,
)

SCHEMA_VERSION: Final = "rd31-locked-mixed-decay-to-caution-v1"
STAGE: Final = "RESEARCH_ONLY_PRE_COUNTERFACTUAL_IMPLEMENTATION"
CANDIDATE_ID: Final = "RD31_LOCKED_MIXED_DECAY_TO_CAUTION_V1"
CANDIDATE_TRANSITION_REASON: Final = "LOCKED_MIXED_DECAYS_TO_CAUTION"
DEFAULT_ENABLED: Final = False
PRODUCTION_ENABLED: Final = False


class RD31LockSemanticsCandidateError(RuntimeError):
    """Raised when the frozen candidate contract is violated."""


def candidate_transition_governor(
    *,
    prior_state: str,
    market_context: str,
    enabled: bool = DEFAULT_ENABLED,
) -> GovernorTransition:
    """Return baseline transition unless the single frozen candidate cell applies."""
    baseline = transition_governor(
        prior_state=prior_state,
        market_context=market_context,
    )
    if not enabled:
        return baseline

    if prior_state == LOCKED and market_context == MIXED:
        if baseline.next_state != LOCKED:
            raise RD31LockSemanticsCandidateError(
                "baseline LOCKED+MIXED no longer stays LOCKED"
            )
        if baseline.reason != "LOCKED_MIXED_STAYS_LOCKED":
            raise RD31LockSemanticsCandidateError(
                "baseline LOCKED+MIXED transition reason drifted"
            )
        return GovernorTransition(
            prior_state=LOCKED,
            next_state=CAUTION,
            market_context=MIXED,
            changed=True,
            reason=CANDIDATE_TRANSITION_REASON,
        )

    return baseline


def candidate_hysteresis_governor_admission(
    *,
    prior_state: str,
    support_families: tuple[str, ...] | list[str],
    btc_state: str,
    market_context: MarketContextDecision,
    enabled: bool = DEFAULT_ENABLED,
) -> GovernedAdmissionDecision:
    """Reuse exact baseline admission semantics; change only LOCKED+MIXED transition."""
    baseline = hysteresis_governor_admission(
        prior_state=prior_state,
        support_families=support_families,
        btc_state=btc_state,
        market_context=market_context,
    )
    if not enabled:
        return baseline

    transition = candidate_transition_governor(
        prior_state=prior_state,
        market_context=market_context.context,
        enabled=True,
    )
    if transition.next_state == baseline.governor_next_state:
        return baseline

    if not (
        prior_state == LOCKED
        and market_context.context == MIXED
        and transition.next_state == CAUTION
    ):
        raise RD31LockSemanticsCandidateError(
            "candidate produced an unauthorized transition delta"
        )

    # Reuse the existing RD31 CAUTION admission path exactly. OPEN+MIXED is the
    # frozen baseline path that transitions to CAUTION and then evaluates the
    # existing CAUTION family rules. We consume only its AdmissionDecision.
    caution_proxy = hysteresis_governor_admission(
        prior_state=OPEN,
        support_families=support_families,
        btc_state=btc_state,
        market_context=market_context,
    )
    if caution_proxy.governor_next_state != CAUTION:
        raise RD31LockSemanticsCandidateError(
            "baseline OPEN+MIXED no longer reaches CAUTION"
        )

    return GovernedAdmissionDecision(
        policy_id=REGIME_HYSTERESIS_ADMISSION_GOVERNOR,
        governor_prior_state=LOCKED,
        governor_next_state=CAUTION,
        transition_reason=CANDIDATE_TRANSITION_REASON,
        market_context=MIXED,
        decision=caution_proxy.decision,
    )


def contract_summary() -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "stage": STAGE,
        "candidate_id": CANDIDATE_ID,
        "default_enabled": DEFAULT_ENABLED,
        "production_enabled": PRODUCTION_ENABLED,
        "single_transition_delta": "LOCKED+MIXED->CAUTION",
        "baseline_transition": "LOCKED+MIXED->LOCKED",
        "stressed_semantics_changed": False,
        "supportive_semantics_changed": False,
        "unavailable_semantics_changed": False,
        "admission_logic_reimplemented": False,
        "existing_caution_admission_reused": True,
        "threshold_search": False,
        "family_search": False,
        "economic_execution_performed": False,
        "market_data_loader_present": False,
        "2023_economic_access": False,
        "2024_access": False,
        "2025_access": False,
    }
