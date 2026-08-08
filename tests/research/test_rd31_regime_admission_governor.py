from __future__ import annotations

import pytest

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
    MIXED,
    STRESSED,
    SUPPORTIVE,
    UNAVAILABLE,
    MarketContextDecision,
)
from spotbot.research.rd31_regime_admission_governor import (
    CAUTION,
    FAMILY_QUALITY_CONTROL_EXITS,
    GOVERNOR_STATES,
    LOCKED,
    OPEN,
    POLICIES,
    REGIME_HYSTERESIS_ADMISSION_GOVERNOR,
    STRESSED_CONTEXT_MB_EXCLUSION,
    SUPPORTIVE_ONLY_ALL_FAMILIES,
    RD31GovernorError,
    active_component_count,
    admission_decision,
    baseline_family_quality_admission,
    contract_summary,
    hysteresis_governor_admission,
    stressed_context_mb_exclusion_admission,
    supportive_only_all_families_admission,
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
    return context(
        btc_state=RISK_ON,
        value=SUPPORTIVE,
        breadth_positive=True,
    )


def mixed_transition() -> MarketContextDecision:
    return context(
        btc_state=TRANSITION,
        value=MIXED,
        breadth_positive=True,
    )


def stressed_transition() -> MarketContextDecision:
    return context(
        btc_state=TRANSITION,
        value=STRESSED,
        breadth_positive=False,
    )


def stressed_risk_off() -> MarketContextDecision:
    return context(
        btc_state=RISK_OFF,
        value=STRESSED,
        breadth_positive=False,
    )


def unavailable_risk_on() -> MarketContextDecision:
    return context(
        btc_state=RISK_ON,
        value=UNAVAILABLE,
        breadth_ready=False,
        breadth_positive=None,
    )


def test_policy_registry_exact():
    assert POLICIES == (
        FAMILY_QUALITY_CONTROL_EXITS,
        STRESSED_CONTEXT_MB_EXCLUSION,
        SUPPORTIVE_ONLY_ALL_FAMILIES,
        REGIME_HYSTERESIS_ADMISSION_GOVERNOR,
    )


def test_governor_state_registry_exact():
    assert GOVERNOR_STATES == (OPEN, CAUTION, LOCKED)


def test_baseline_mb_risk_on_is_exact_rd30_slot():
    decision = baseline_family_quality_admission(
        support_families=(FAMILY_MOMENTUM_BREAKOUT,),
        btc_state=RISK_ON,
        market_context=supportive(),
    )
    assert decision.admit_position is True
    assert decision.target_slot_fraction == pytest.approx(0.18)


def test_baseline_mb_transition_is_exact_rd30_slot():
    decision = baseline_family_quality_admission(
        support_families=(FAMILY_MOMENTUM_BREAKOUT,),
        btc_state=TRANSITION,
        market_context=mixed_transition(),
    )
    assert decision.admit_position is True
    assert decision.target_slot_fraction == pytest.approx(0.09)


def test_baseline_mb_risk_off_is_suppressed():
    decision = baseline_family_quality_admission(
        support_families=(FAMILY_MOMENTUM_BREAKOUT,),
        btc_state=RISK_OFF,
        market_context=stressed_risk_off(),
    )
    assert decision.admit_position is False


def test_baseline_rs_requires_supportive():
    yes = baseline_family_quality_admission(
        support_families=(FAMILY_RELATIVE_STRENGTH_ROTATION,),
        btc_state=RISK_ON,
        market_context=supportive(),
    )
    no = baseline_family_quality_admission(
        support_families=(FAMILY_RELATIVE_STRENGTH_ROTATION,),
        btc_state=TRANSITION,
        market_context=mixed_transition(),
    )
    assert yes.admit_position is True
    assert yes.target_slot_fraction == pytest.approx(0.18)
    assert no.admit_position is False


def test_stressed_exclusion_preserves_mb_risk_on():
    decision = stressed_context_mb_exclusion_admission(
        support_families=(FAMILY_MOMENTUM_BREAKOUT,),
        btc_state=RISK_ON,
        market_context=supportive(),
    )
    assert decision.admit_position is True
    assert decision.target_slot_fraction == pytest.approx(0.18)


def test_stressed_exclusion_preserves_mb_transition_mixed():
    decision = stressed_context_mb_exclusion_admission(
        support_families=(FAMILY_MOMENTUM_BREAKOUT,),
        btc_state=TRANSITION,
        market_context=mixed_transition(),
    )
    assert decision.admit_position is True
    assert decision.target_slot_fraction == pytest.approx(0.09)


def test_stressed_exclusion_blocks_mb_transition_stressed():
    decision = stressed_context_mb_exclusion_admission(
        support_families=(FAMILY_MOMENTUM_BREAKOUT,),
        btc_state=TRANSITION,
        market_context=stressed_transition(),
    )
    assert decision.admit_position is False


def test_stressed_exclusion_blocks_mb_risk_off():
    decision = stressed_context_mb_exclusion_admission(
        support_families=(FAMILY_MOMENTUM_BREAKOUT,),
        btc_state=RISK_OFF,
        market_context=stressed_risk_off(),
    )
    assert decision.admit_position is False


def test_stressed_exclusion_rs_remains_supportive_only():
    yes = stressed_context_mb_exclusion_admission(
        support_families=(FAMILY_RELATIVE_STRENGTH_ROTATION,),
        btc_state=RISK_ON,
        market_context=supportive(),
    )
    no = stressed_context_mb_exclusion_admission(
        support_families=(FAMILY_RELATIVE_STRENGTH_ROTATION,),
        btc_state=TRANSITION,
        market_context=mixed_transition(),
    )
    assert yes.admit_position is True
    assert no.admit_position is False


def test_stressed_exclusion_overlap_keeps_rs_when_supportive():
    decision = stressed_context_mb_exclusion_admission(
        support_families=(
            FAMILY_MOMENTUM_BREAKOUT,
            FAMILY_RELATIVE_STRENGTH_ROTATION,
        ),
        btc_state=RISK_ON,
        market_context=supportive(),
    )
    assert decision.admit_position is True
    assert decision.target_slot_fraction == pytest.approx(0.18)
    assert set(decision.admissible_families) == {
        FAMILY_MOMENTUM_BREAKOUT,
        FAMILY_RELATIVE_STRENGTH_ROTATION,
    }


def test_supportive_only_all_admits_mb():
    decision = supportive_only_all_families_admission(
        support_families=(FAMILY_MOMENTUM_BREAKOUT,),
        market_context=supportive(),
    )
    assert decision.admit_position is True
    assert decision.target_slot_fraction == pytest.approx(0.18)


def test_supportive_only_all_admits_rs():
    decision = supportive_only_all_families_admission(
        support_families=(FAMILY_RELATIVE_STRENGTH_ROTATION,),
        market_context=supportive(),
    )
    assert decision.admit_position is True


def test_supportive_only_all_blocks_mixed():
    decision = supportive_only_all_families_admission(
        support_families=(FAMILY_MOMENTUM_BREAKOUT,),
        market_context=mixed_transition(),
    )
    assert decision.admit_position is False


def test_supportive_only_all_blocks_stressed():
    decision = supportive_only_all_families_admission(
        support_families=(FAMILY_RELATIVE_STRENGTH_ROTATION,),
        market_context=stressed_transition(),
    )
    assert decision.admit_position is False


def test_supportive_only_all_blocks_unavailable():
    decision = supportive_only_all_families_admission(
        support_families=(FAMILY_MOMENTUM_BREAKOUT,),
        market_context=unavailable_risk_on(),
    )
    assert decision.admit_position is False


@pytest.mark.parametrize("prior", GOVERNOR_STATES)
def test_any_state_stressed_goes_locked(prior: str):
    transition = transition_governor(
        prior_state=prior,
        market_context=STRESSED,
    )
    assert transition.next_state == LOCKED


def test_locked_mixed_stays_locked():
    transition = transition_governor(
        prior_state=LOCKED,
        market_context=MIXED,
    )
    assert transition.next_state == LOCKED


def test_locked_supportive_opens():
    transition = transition_governor(
        prior_state=LOCKED,
        market_context=SUPPORTIVE,
    )
    assert transition.next_state == OPEN


def test_open_mixed_goes_caution():
    transition = transition_governor(
        prior_state=OPEN,
        market_context=MIXED,
    )
    assert transition.next_state == CAUTION


def test_caution_mixed_stays_caution():
    transition = transition_governor(
        prior_state=CAUTION,
        market_context=MIXED,
    )
    assert transition.next_state == CAUTION


def test_caution_supportive_opens():
    transition = transition_governor(
        prior_state=CAUTION,
        market_context=SUPPORTIVE,
    )
    assert transition.next_state == OPEN


@pytest.mark.parametrize("prior", GOVERNOR_STATES)
def test_unavailable_persists_state(prior: str):
    transition = transition_governor(
        prior_state=prior,
        market_context=UNAVAILABLE,
    )
    assert transition.next_state == prior
    assert transition.changed is False


def test_governor_updates_before_admission_stressed_locks():
    governed = hysteresis_governor_admission(
        prior_state=OPEN,
        support_families=(FAMILY_MOMENTUM_BREAKOUT,),
        btc_state=TRANSITION,
        market_context=stressed_transition(),
    )
    assert governed.governor_next_state == LOCKED
    assert governed.decision.admit_position is False


def test_locked_mixed_does_not_reopen_for_mb():
    governed = hysteresis_governor_admission(
        prior_state=LOCKED,
        support_families=(FAMILY_MOMENTUM_BREAKOUT,),
        btc_state=TRANSITION,
        market_context=mixed_transition(),
    )
    assert governed.governor_next_state == LOCKED
    assert governed.decision.admit_position is False


def test_locked_supportive_reopens_and_admits_mb():
    governed = hysteresis_governor_admission(
        prior_state=LOCKED,
        support_families=(FAMILY_MOMENTUM_BREAKOUT,),
        btc_state=RISK_ON,
        market_context=supportive(),
    )
    assert governed.governor_next_state == OPEN
    assert governed.decision.admit_position is True
    assert governed.decision.target_slot_fraction == pytest.approx(0.18)


def test_open_mixed_moves_caution_and_allows_transition_mb():
    governed = hysteresis_governor_admission(
        prior_state=OPEN,
        support_families=(FAMILY_MOMENTUM_BREAKOUT,),
        btc_state=TRANSITION,
        market_context=mixed_transition(),
    )
    assert governed.governor_next_state == CAUTION
    assert governed.decision.admit_position is True
    assert governed.decision.target_slot_fraction == pytest.approx(0.09)


def test_caution_mixed_suppresses_rs():
    governed = hysteresis_governor_admission(
        prior_state=CAUTION,
        support_families=(FAMILY_RELATIVE_STRENGTH_ROTATION,),
        btc_state=TRANSITION,
        market_context=mixed_transition(),
    )
    assert governed.decision.admit_position is False


def test_open_unavailable_persists_and_uses_exact_baseline():
    governed = hysteresis_governor_admission(
        prior_state=OPEN,
        support_families=(FAMILY_MOMENTUM_BREAKOUT,),
        btc_state=RISK_ON,
        market_context=unavailable_risk_on(),
    )
    assert governed.governor_next_state == OPEN
    assert governed.decision.admit_position is True
    assert governed.decision.target_slot_fraction == pytest.approx(0.18)


def test_locked_unavailable_stays_locked_and_suppresses():
    governed = hysteresis_governor_admission(
        prior_state=LOCKED,
        support_families=(FAMILY_MOMENTUM_BREAKOUT,),
        btc_state=RISK_ON,
        market_context=unavailable_risk_on(),
    )
    assert governed.governor_next_state == LOCKED
    assert governed.decision.admit_position is False


def test_public_admission_wrapper_has_no_governor_state_for_static_policy():
    governed = admission_decision(
        policy_id=FAMILY_QUALITY_CONTROL_EXITS,
        support_families=(FAMILY_MOMENTUM_BREAKOUT,),
        btc_state=RISK_ON,
        market_context=supportive(),
    )
    assert governed.governor_prior_state is None
    assert governed.governor_next_state is None
    assert governed.decision.admit_position is True


def test_public_admission_wrapper_exposes_governor_transition():
    governed = admission_decision(
        policy_id=REGIME_HYSTERESIS_ADMISSION_GOVERNOR,
        support_families=(FAMILY_MOMENTUM_BREAKOUT,),
        btc_state=TRANSITION,
        market_context=mixed_transition(),
        governor_prior_state=OPEN,
    )
    assert governed.governor_prior_state == OPEN
    assert governed.governor_next_state == CAUTION


def test_unknown_policy_rejected():
    with pytest.raises(RD31GovernorError):
        admission_decision(
            policy_id="UNKNOWN",
            support_families=(FAMILY_MOMENTUM_BREAKOUT,),
            btc_state=RISK_ON,
            market_context=supportive(),
        )


def test_unknown_family_rejected():
    with pytest.raises(RD31GovernorError):
        admission_decision(
            policy_id=FAMILY_QUALITY_CONTROL_EXITS,
            support_families=("UNKNOWN",),
            btc_state=RISK_ON,
            market_context=supportive(),
        )


def test_unknown_governor_state_rejected():
    with pytest.raises(RD31GovernorError):
        transition_governor(
            prior_state="UNKNOWN",
            market_context=MIXED,
        )


def test_active_component_counts_are_frozen():
    assert active_component_count(FAMILY_QUALITY_CONTROL_EXITS) == 1
    assert active_component_count(STRESSED_CONTEXT_MB_EXCLUSION) == 2
    assert active_component_count(SUPPORTIVE_ONLY_ALL_FAMILIES) == 2
    assert active_component_count(REGIME_HYSTERESIS_ADMISSION_GOVERNOR) == 3


def test_contract_summary_firewalls():
    summary = contract_summary()
    assert summary["baseline_source"] == "EXACT_RD30_FAMILY_QUALITY_CONTROL_EXITS"
    assert summary["rs_supportive_only_preserved"] is True
    assert summary["governor_duration_parameter"] is False
    assert summary["forced_regime_exit"] is False
    assert summary["profit_giveback"] is False
    assert summary["replacement"] is False
    assert summary["thesis_failure_exit"] is False
    assert summary["parameter_grid_search"] is False
    assert summary["calendar_year_feature"] is False
    assert summary["economic_execution_performed"] is False
    assert summary["real_market_data_loader_present"] is False
    assert summary["2024_accessed"] is False
    assert summary["post_2024_accessed"] is False
    assert summary["production_authorized"] is False


def test_btc_state_must_match_market_context():
    with pytest.raises(RD31GovernorError):
        admission_decision(
            policy_id=FAMILY_QUALITY_CONTROL_EXITS,
            support_families=(FAMILY_MOMENTUM_BREAKOUT,),
            btc_state=TRANSITION,
            market_context=supportive(),
        )
