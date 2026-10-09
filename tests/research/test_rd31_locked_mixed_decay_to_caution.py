from __future__ import annotations

import itertools

import pytest

from spotbot.research.rd26_exit_architecture import (
    FAMILY_MOMENTUM_BREAKOUT,
    FAMILY_RELATIVE_STRENGTH_ROTATION,
)
from spotbot.research.rd27_adaptive_lifecycle import (
    RISK_ON,
    TRANSITION,
)
from spotbot.research.rd29_thesis_context import (
    MIXED,
    STRESSED,
    SUPPORTIVE,
    UNAVAILABLE,
    MarketContextDecision,
)
from spotbot.research.rd31_locked_mixed_decay_to_caution import (
    CANDIDATE_TRANSITION_REASON,
    DEFAULT_ENABLED,
    PRODUCTION_ENABLED,
    candidate_hysteresis_governor_admission,
    candidate_transition_governor,
    contract_summary,
)
from spotbot.research.rd31_regime_admission_governor import (
    CAUTION,
    GOVERNOR_STATES,
    LOCKED,
    OPEN,
    hysteresis_governor_admission,
    transition_governor,
)


def context(
    *,
    btc_state: str,
    value: str,
    breadth_ready: bool = True,
    breadth_positive: bool | None = True,
) -> MarketContextDecision:
    return MarketContextDecision(
        btc_state=btc_state,
        breadth_ready=breadth_ready,
        breadth_median_return_72h=(0.05 if breadth_ready else None),
        breadth_positive=(breadth_positive if breadth_ready else None),
        context=value,
        member_count=3,
        observed_member_count=3 if breadth_ready else 2,
    )


def supportive() -> MarketContextDecision:
    return context(btc_state=RISK_ON, value=SUPPORTIVE, breadth_positive=True)


def mixed() -> MarketContextDecision:
    return context(btc_state=TRANSITION, value=MIXED, breadth_positive=True)


def stressed() -> MarketContextDecision:
    return context(btc_state=TRANSITION, value=STRESSED, breadth_positive=False)


def unavailable() -> MarketContextDecision:
    return context(
        btc_state=RISK_ON,
        value=UNAVAILABLE,
        breadth_ready=False,
        breadth_positive=None,
    )


def test_candidate_is_disabled_by_default_and_never_production_enabled():
    assert DEFAULT_ENABLED is False
    assert PRODUCTION_ENABLED is False


@pytest.mark.parametrize("prior", GOVERNOR_STATES)
@pytest.mark.parametrize("market_context", (STRESSED, SUPPORTIVE, MIXED, UNAVAILABLE))
def test_disabled_transition_is_exact_baseline(prior: str, market_context: str):
    assert candidate_transition_governor(
        prior_state=prior,
        market_context=market_context,
        enabled=False,
    ) == transition_governor(
        prior_state=prior,
        market_context=market_context,
    )


def test_enabled_transition_diff_is_only_locked_mixed():
    differences = []
    for prior, market_context in itertools.product(
        GOVERNOR_STATES,
        (STRESSED, SUPPORTIVE, MIXED, UNAVAILABLE),
    ):
        baseline = transition_governor(
            prior_state=prior,
            market_context=market_context,
        )
        candidate = candidate_transition_governor(
            prior_state=prior,
            market_context=market_context,
            enabled=True,
        )
        if candidate != baseline:
            differences.append((prior, market_context, baseline, candidate))

    assert len(differences) == 1
    prior, market_context, baseline, candidate = differences[0]
    assert prior == LOCKED
    assert market_context == MIXED
    assert baseline.next_state == LOCKED
    assert candidate.next_state == CAUTION
    assert candidate.reason == CANDIDATE_TRANSITION_REASON


@pytest.mark.parametrize("prior", GOVERNOR_STATES)
def test_stressed_protection_is_exactly_unchanged(prior: str):
    baseline = transition_governor(prior_state=prior, market_context=STRESSED)
    candidate = candidate_transition_governor(
        prior_state=prior,
        market_context=STRESSED,
        enabled=True,
    )
    assert candidate == baseline
    assert candidate.next_state == LOCKED


@pytest.mark.parametrize("prior", GOVERNOR_STATES)
def test_supportive_semantics_are_exactly_unchanged(prior: str):
    assert candidate_transition_governor(
        prior_state=prior,
        market_context=SUPPORTIVE,
        enabled=True,
    ) == transition_governor(
        prior_state=prior,
        market_context=SUPPORTIVE,
    )


@pytest.mark.parametrize("prior", GOVERNOR_STATES)
def test_unavailable_semantics_are_exactly_unchanged(prior: str):
    assert candidate_transition_governor(
        prior_state=prior,
        market_context=UNAVAILABLE,
        enabled=True,
    ) == transition_governor(
        prior_state=prior,
        market_context=UNAVAILABLE,
    )


@pytest.mark.parametrize(
    "prior,ctx,families",
    [
        (OPEN, supportive(), (FAMILY_MOMENTUM_BREAKOUT,)),
        (CAUTION, mixed(), (FAMILY_MOMENTUM_BREAKOUT,)),
        (OPEN, unavailable(), (FAMILY_MOMENTUM_BREAKOUT,)),
        (LOCKED, stressed(), (FAMILY_MOMENTUM_BREAKOUT,)),
        (LOCKED, supportive(), (FAMILY_RELATIVE_STRENGTH_ROTATION,)),
        (
            OPEN,
            supportive(),
            (
                FAMILY_MOMENTUM_BREAKOUT,
                FAMILY_RELATIVE_STRENGTH_ROTATION,
            ),
        ),
    ],
)
def test_disabled_admission_is_exact_baseline(prior, ctx, families):
    assert candidate_hysteresis_governor_admission(
        prior_state=prior,
        support_families=families,
        btc_state=ctx.btc_state,
        market_context=ctx,
        enabled=False,
    ) == hysteresis_governor_admission(
        prior_state=prior,
        support_families=families,
        btc_state=ctx.btc_state,
        market_context=ctx,
    )


def test_locked_mixed_mb_reuses_exact_existing_caution_admission():
    ctx = mixed()
    candidate = candidate_hysteresis_governor_admission(
        prior_state=LOCKED,
        support_families=(FAMILY_MOMENTUM_BREAKOUT,),
        btc_state=ctx.btc_state,
        market_context=ctx,
        enabled=True,
    )
    caution_reference = hysteresis_governor_admission(
        prior_state=OPEN,
        support_families=(FAMILY_MOMENTUM_BREAKOUT,),
        btc_state=ctx.btc_state,
        market_context=ctx,
    )

    assert candidate.governor_prior_state == LOCKED
    assert candidate.governor_next_state == CAUTION
    assert candidate.transition_reason == CANDIDATE_TRANSITION_REASON
    assert candidate.decision == caution_reference.decision
    assert candidate.decision.admit_position is True
    assert candidate.decision.target_slot_fraction == pytest.approx(0.09)


def test_locked_mixed_rs_reuses_caution_and_remains_suppressed():
    ctx = mixed()
    candidate = candidate_hysteresis_governor_admission(
        prior_state=LOCKED,
        support_families=(FAMILY_RELATIVE_STRENGTH_ROTATION,),
        btc_state=ctx.btc_state,
        market_context=ctx,
        enabled=True,
    )
    caution_reference = hysteresis_governor_admission(
        prior_state=OPEN,
        support_families=(FAMILY_RELATIVE_STRENGTH_ROTATION,),
        btc_state=ctx.btc_state,
        market_context=ctx,
    )
    assert candidate.decision == caution_reference.decision
    assert candidate.decision.admit_position is False


def test_locked_mixed_overlap_reuses_caution_without_rs_relaxation():
    ctx = mixed()
    families = (
        FAMILY_MOMENTUM_BREAKOUT,
        FAMILY_RELATIVE_STRENGTH_ROTATION,
    )
    candidate = candidate_hysteresis_governor_admission(
        prior_state=LOCKED,
        support_families=families,
        btc_state=ctx.btc_state,
        market_context=ctx,
        enabled=True,
    )
    caution_reference = hysteresis_governor_admission(
        prior_state=OPEN,
        support_families=families,
        btc_state=ctx.btc_state,
        market_context=ctx,
    )
    assert candidate.decision == caution_reference.decision
    assert candidate.decision.admit_position is True
    assert candidate.decision.target_slot_fraction == pytest.approx(0.09)
    assert candidate.decision.admissible_families == (FAMILY_MOMENTUM_BREAKOUT,)


def test_enabled_non_target_admission_paths_remain_exact_baseline():
    cases = (
        (OPEN, supportive(), (FAMILY_MOMENTUM_BREAKOUT,)),
        (LOCKED, supportive(), (FAMILY_MOMENTUM_BREAKOUT,)),
        (OPEN, mixed(), (FAMILY_MOMENTUM_BREAKOUT,)),
        (CAUTION, mixed(), (FAMILY_MOMENTUM_BREAKOUT,)),
        (LOCKED, stressed(), (FAMILY_MOMENTUM_BREAKOUT,)),
        (LOCKED, unavailable(), (FAMILY_MOMENTUM_BREAKOUT,)),
    )
    for prior, ctx, families in cases:
        candidate = candidate_hysteresis_governor_admission(
            prior_state=prior,
            support_families=families,
            btc_state=ctx.btc_state,
            market_context=ctx,
            enabled=True,
        )
        baseline = hysteresis_governor_admission(
            prior_state=prior,
            support_families=families,
            btc_state=ctx.btc_state,
            market_context=ctx,
        )
        assert candidate == baseline


def test_contract_firewalls():
    summary = contract_summary()
    assert summary["candidate_id"] == "RD31_LOCKED_MIXED_DECAY_TO_CAUTION_V1"
    assert summary["default_enabled"] is False
    assert summary["production_enabled"] is False
    assert summary["single_transition_delta"] == "LOCKED+MIXED->CAUTION"
    assert summary["stressed_semantics_changed"] is False
    assert summary["supportive_semantics_changed"] is False
    assert summary["unavailable_semantics_changed"] is False
    assert summary["admission_logic_reimplemented"] is False
    assert summary["existing_caution_admission_reused"] is True
    assert summary["threshold_search"] is False
    assert summary["family_search"] is False
    assert summary["economic_execution_performed"] is False
    assert summary["market_data_loader_present"] is False
    assert summary["2023_economic_access"] is False
    assert summary["2024_access"] is False
    assert summary["2025_access"] is False
