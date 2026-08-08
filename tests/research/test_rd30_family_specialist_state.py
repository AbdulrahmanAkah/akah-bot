from __future__ import annotations

from dataclasses import replace

import pandas as pd
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
    MarketContextDecision,
)
from spotbot.research.rd30_family_specialist_state import (
    FAMILY_QUALITY_CONTROL_EXITS,
    FAMILY_QUALITY_REPLACEMENT_AWARE_RS,
    FULL_FAMILY_SPECIALIST_REPLACEMENT_BRAIN,
    MAX_HOLD_EXIT_REASON,
    MB_SUPPORTED,
    POLICIES,
    PROFIT_GIVEBACK_EXIT_REASON,
    REPLACEMENT_EXIT_REASON,
    ROUTER_TIME_FAIL_72_CONTROL,
    RS_ONLY,
    TIME_FAIL_EXIT_REASON,
    RD30StateError,
    active_component_count,
    admission_decision,
    apply_completed_high,
    contract_summary,
    evaluate_scheduled_exit,
    lifecycle_class_for_support,
    new_specialist_position,
    policy_components,
    select_replacement_incumbent,
    update_replacement_state,
)


def context(
    *,
    btc_state: str = RISK_ON,
    value: str = SUPPORTIVE,
) -> MarketContextDecision:
    return MarketContextDecision(
        btc_state=btc_state,
        breadth_ready=True,
        breadth_median_return_72h=0.05,
        breadth_positive=True,
        context=value,
        member_count=3,
        observed_member_count=3,
    )


def position(
    *,
    pair: str = "AAA-USDT",
    families: tuple[str, ...] = (FAMILY_RELATIVE_STRENGTH_ROTATION,),
    entry_time: str = "2022-01-01T00:00:00Z",
):
    return new_specialist_position(
        pair=pair,
        entry_time=pd.Timestamp(entry_time),
        entry_price=100.0,
        atr24_at_signal=2.0,
        support_families=families,
    )


def members() -> tuple[tuple[str, int], ...]:
    return (
        ("AAA-USDT", 1),
        ("BBB-USDT", 2),
        ("CCC-USDT", 3),
    )


def test_policy_registry_is_frozen():
    assert POLICIES == (
        ROUTER_TIME_FAIL_72_CONTROL,
        FAMILY_QUALITY_CONTROL_EXITS,
        FAMILY_QUALITY_REPLACEMENT_AWARE_RS,
        FULL_FAMILY_SPECIALIST_REPLACEMENT_BRAIN,
    )


def test_mb_support_classifies_mb_supported():
    assert lifecycle_class_for_support((FAMILY_MOMENTUM_BREAKOUT,)) == MB_SUPPORTED


def test_overlap_classifies_mb_supported():
    assert (
        lifecycle_class_for_support(
            (
                FAMILY_MOMENTUM_BREAKOUT,
                FAMILY_RELATIVE_STRENGTH_ROTATION,
            )
        )
        == MB_SUPPORTED
    )


def test_pure_rs_classifies_rs_only():
    assert lifecycle_class_for_support((FAMILY_RELATIVE_STRENGTH_ROTATION,)) == RS_ONLY


def test_unknown_family_is_rejected():
    with pytest.raises(RD30StateError):
        lifecycle_class_for_support(("UNKNOWN",))


def test_family_quality_rs_requires_supportive_context():
    supportive = admission_decision(
        policy_id=FAMILY_QUALITY_CONTROL_EXITS,
        support_families=(FAMILY_RELATIVE_STRENGTH_ROTATION,),
        btc_state=RISK_ON,
        market_context=context(),
    )
    mixed = admission_decision(
        policy_id=FAMILY_QUALITY_CONTROL_EXITS,
        support_families=(FAMILY_RELATIVE_STRENGTH_ROTATION,),
        btc_state=TRANSITION,
        market_context=context(
            btc_state=TRANSITION,
            value=MIXED,
        ),
    )
    assert supportive.admit_position is True
    assert supportive.target_slot_fraction == pytest.approx(0.18)
    assert mixed.admit_position is False


def test_family_quality_mb_uses_exact_router():
    risk_on = admission_decision(
        policy_id=FAMILY_QUALITY_CONTROL_EXITS,
        support_families=(FAMILY_MOMENTUM_BREAKOUT,),
        btc_state=RISK_ON,
        market_context=context(),
    )
    transition = admission_decision(
        policy_id=FAMILY_QUALITY_CONTROL_EXITS,
        support_families=(FAMILY_MOMENTUM_BREAKOUT,),
        btc_state=TRANSITION,
        market_context=context(
            btc_state=TRANSITION,
            value=MIXED,
        ),
    )
    risk_off = admission_decision(
        policy_id=FAMILY_QUALITY_CONTROL_EXITS,
        support_families=(FAMILY_MOMENTUM_BREAKOUT,),
        btc_state=RISK_OFF,
        market_context=context(
            btc_state=RISK_OFF,
            value=STRESSED,
        ),
    )
    assert risk_on.target_slot_fraction == pytest.approx(0.18)
    assert transition.target_slot_fraction == pytest.approx(0.09)
    assert risk_off.admit_position is False


def test_overlap_admits_when_mb_is_admissible_even_if_rs_context_not_supportive():
    decision = admission_decision(
        policy_id=FAMILY_QUALITY_CONTROL_EXITS,
        support_families=(
            FAMILY_MOMENTUM_BREAKOUT,
            FAMILY_RELATIVE_STRENGTH_ROTATION,
        ),
        btc_state=TRANSITION,
        market_context=context(
            btc_state=TRANSITION,
            value=MIXED,
        ),
    )
    assert decision.admit_position is True
    assert decision.target_slot_fraction == pytest.approx(0.09)
    assert decision.admissible_families == (FAMILY_MOMENTUM_BREAKOUT,)


def test_control_admission_keeps_rd27_router_ablation():
    decision = admission_decision(
        policy_id=ROUTER_TIME_FAIL_72_CONTROL,
        support_families=(FAMILY_RELATIVE_STRENGTH_ROTATION,),
        btc_state=TRANSITION,
        market_context=context(
            btc_state=TRANSITION,
            value=MIXED,
        ),
    )
    assert decision.admit_position is True
    assert decision.target_slot_fraction == pytest.approx(0.09)


def test_new_mb_position_cannot_carry_degraded_state():
    current = position(families=(FAMILY_MOMENTUM_BREAKOUT,))
    assert current.lifecycle_class == MB_SUPPORTED
    assert current.degraded_since is None


def test_apply_completed_high_is_prior_bar_only_state_update():
    current = position()
    updated = apply_completed_high(current, completed_high=111.0)
    assert updated.high_water_prior == pytest.approx(111.0)
    assert current.high_water_prior == pytest.approx(100.0)


def test_time_fail_occurs_exactly_at_72h():
    current = position()
    at_72 = evaluate_scheduled_exit(
        current,
        current_open_time=pd.Timestamp("2022-01-04T00:00:00Z"),
        current_open=98.0,
        prior_completed_close=99.0,
        profit_state_enabled=False,
    )
    at_73 = evaluate_scheduled_exit(
        current,
        current_open_time=pd.Timestamp("2022-01-04T01:00:00Z"),
        current_open=98.0,
        prior_completed_close=99.0,
        profit_state_enabled=False,
    )
    assert at_72.should_exit is True
    assert at_72.exit_reason == TIME_FAIL_EXIT_REASON
    assert at_73.should_exit is False


def test_time_fail_does_not_exit_if_72h_prior_close_above_entry():
    current = position()
    decision = evaluate_scheduled_exit(
        current,
        current_open_time=pd.Timestamp("2022-01-04T00:00:00Z"),
        current_open=102.0,
        prior_completed_close=101.0,
        profit_state_enabled=False,
    )
    assert decision.should_exit is False


def test_max_hold_has_priority_at_168h():
    current = position()
    decision = evaluate_scheduled_exit(
        current,
        current_open_time=pd.Timestamp("2022-01-08T00:00:00Z"),
        current_open=90.0,
        prior_completed_close=90.0,
        profit_state_enabled=True,
    )
    assert decision.should_exit is True
    assert decision.exit_reason == MAX_HOLD_EXIT_REASON


def test_profit_giveback_is_inert_when_policy_component_disabled():
    current = apply_completed_high(position(), completed_high=110.0)
    decision = evaluate_scheduled_exit(
        current,
        current_open_time=pd.Timestamp("2022-01-02T12:00:00Z"),
        current_open=103.0,
        prior_completed_close=103.0,
        profit_state_enabled=False,
    )
    assert decision.should_exit is False
    assert decision.profit_lock_armed is True


def test_profit_giveback_uses_exact_4atr_arm_3atr_gap():
    current = apply_completed_high(position(), completed_high=108.0)
    decision = evaluate_scheduled_exit(
        current,
        current_open_time=pd.Timestamp("2022-01-02T12:00:00Z"),
        current_open=101.0,
        prior_completed_close=102.0,
        profit_state_enabled=True,
    )
    assert decision.should_exit is True
    assert decision.exit_reason == PROFIT_GIVEBACK_EXIT_REASON


def test_rs_degraded_sets_only_at_checkpoint_stressed_and_failed():
    current = position()
    decision = update_replacement_state(
        current,
        current_open_time=pd.Timestamp("2022-01-02T00:00:00Z"),
        current_members=members(),
        return_72h_by_pair={
            "AAA-USDT": -0.01,
            "BBB-USDT": 0.03,
            "CCC-USDT": 0.02,
        },
        market_context=context(
            btc_state=RISK_OFF,
            value=STRESSED,
        ),
    )
    assert decision.at_checkpoint is True
    assert decision.degraded_after is True
    assert decision.reason == "RS_DEGRADED_SET"
    assert decision.position.degraded_since == pd.Timestamp("2022-01-02T00:00:00Z")


def test_rs_failure_in_supportive_context_does_not_degrade():
    current = position()
    decision = update_replacement_state(
        current,
        current_open_time=pd.Timestamp("2022-01-02T00:00:00Z"),
        current_members=members(),
        return_72h_by_pair={
            "AAA-USDT": -0.01,
            "BBB-USDT": 0.03,
            "CCC-USDT": 0.02,
        },
        market_context=context(),
    )
    assert decision.rs_failed is True
    assert decision.degraded_after is False


def test_rs_noncheckpoint_never_changes_degraded_state():
    current = replace(
        position(),
        degraded_since=pd.Timestamp("2022-01-02T00:00:00Z"),
    )
    decision = update_replacement_state(
        current,
        current_open_time=pd.Timestamp("2022-01-02T01:00:00Z"),
        current_members=members(),
        return_72h_by_pair={
            "AAA-USDT": 0.20,
            "BBB-USDT": 0.03,
            "CCC-USDT": 0.02,
        },
        market_context=context(),
    )
    assert decision.at_checkpoint is False
    assert decision.degraded_after is True
    assert decision.state_changed is False


def test_rs_retained_at_next_checkpoint_clears_degraded_state():
    current = replace(
        position(),
        degraded_since=pd.Timestamp("2022-01-02T00:00:00Z"),
    )
    decision = update_replacement_state(
        current,
        current_open_time=pd.Timestamp("2022-01-03T00:00:00Z"),
        current_members=members(),
        return_72h_by_pair={
            "AAA-USDT": 0.20,
            "BBB-USDT": 0.03,
            "CCC-USDT": 0.02,
        },
        market_context=context(
            btc_state=RISK_OFF,
            value=STRESSED,
        ),
    )
    assert decision.degraded_after is False
    assert decision.reason == "RS_DEGRADED_CLEARED"


def test_nonstressed_context_at_checkpoint_clears_degraded_state():
    current = replace(
        position(),
        degraded_since=pd.Timestamp("2022-01-02T00:00:00Z"),
    )
    decision = update_replacement_state(
        current,
        current_open_time=pd.Timestamp("2022-01-03T00:00:00Z"),
        current_members=members(),
        return_72h_by_pair={
            "AAA-USDT": -0.01,
            "BBB-USDT": 0.03,
            "CCC-USDT": 0.02,
        },
        market_context=context(),
    )
    assert decision.rs_failed is True
    assert decision.degraded_after is False
    assert decision.reason == "RS_DEGRADED_CLEARED"


def test_rs_unevaluable_checkpoint_persists_prior_degraded_state():
    current = replace(
        position(),
        degraded_since=pd.Timestamp("2022-01-02T00:00:00Z"),
    )
    decision = update_replacement_state(
        current,
        current_open_time=pd.Timestamp("2022-01-03T00:00:00Z"),
        current_members=members(),
        return_72h_by_pair={
            "AAA-USDT": None,
            "BBB-USDT": 0.03,
            "CCC-USDT": 0.02,
        },
        market_context=context(
            btc_state=RISK_OFF,
            value=STRESSED,
        ),
    )
    assert decision.rs_evaluable is False
    assert decision.degraded_after is True
    assert decision.state_changed is False


def test_membership_loss_is_rs_failure_and_can_degrade():
    current = position(pair="AAA-USDT")
    decision = update_replacement_state(
        current,
        current_open_time=pd.Timestamp("2022-01-02T00:00:00Z"),
        current_members=(
            ("BBB-USDT", 1),
            ("CCC-USDT", 2),
        ),
        return_72h_by_pair={
            "BBB-USDT": 0.03,
            "CCC-USDT": 0.02,
        },
        market_context=context(
            btc_state=RISK_OFF,
            value=STRESSED,
        ),
    )
    assert decision.rs_failed is True
    assert decision.degraded_after is True


def test_mb_supported_never_degrades_even_in_stressed_context():
    current = position(families=(FAMILY_MOMENTUM_BREAKOUT,))
    decision = update_replacement_state(
        current,
        current_open_time=pd.Timestamp("2022-01-02T00:00:00Z"),
        current_members=members(),
        return_72h_by_pair={
            "AAA-USDT": -0.20,
            "BBB-USDT": 0.03,
            "CCC-USDT": 0.02,
        },
        market_context=context(
            btc_state=RISK_OFF,
            value=STRESSED,
        ),
    )
    assert decision.degraded_after is False
    assert decision.reason == "MB_SUPPORTED_NEVER_THESIS_DEGRADED"


def test_replacement_requires_prevalidated_incoming():
    degraded = replace(
        position(),
        degraded_since=pd.Timestamp("2022-01-02T00:00:00Z"),
    )
    decision = select_replacement_incumbent(
        [degraded],
        incoming_prevalidated=False,
        free_slot_exists=False,
    )
    assert decision.should_replace is False
    assert decision.reason == "INCOMING_ENTRY_NOT_PREVALIDATED"


def test_replacement_forbidden_when_free_slot_exists():
    degraded = replace(
        position(),
        degraded_since=pd.Timestamp("2022-01-02T00:00:00Z"),
    )
    decision = select_replacement_incumbent(
        [degraded],
        incoming_prevalidated=True,
        free_slot_exists=True,
    )
    assert decision.should_replace is False
    assert decision.reason == "FREE_SLOT_EXISTS_NO_REPLACEMENT"


def test_replacement_ignores_mb_supported_and_healthy_rs():
    mb = position(
        pair="MB-USDT",
        families=(FAMILY_MOMENTUM_BREAKOUT,),
    )
    healthy = position(pair="HEALTHY-USDT")
    decision = select_replacement_incumbent(
        [mb, healthy],
        incoming_prevalidated=True,
        free_slot_exists=False,
    )
    assert decision.should_replace is False
    assert decision.reason == "NO_DEGRADED_RS_ONLY_INCUMBENT"


def test_replacement_selects_oldest_degraded_since_first():
    newer = replace(
        position(
            pair="NEW-USDT",
            entry_time="2022-01-01T00:00:00Z",
        ),
        degraded_since=pd.Timestamp("2022-01-03T00:00:00Z"),
    )
    older = replace(
        position(
            pair="OLD-USDT",
            entry_time="2022-01-02T00:00:00Z",
        ),
        degraded_since=pd.Timestamp("2022-01-02T00:00:00Z"),
    )
    decision = select_replacement_incumbent(
        [newer, older],
        incoming_prevalidated=True,
        free_slot_exists=False,
    )
    assert decision.should_replace is True
    assert decision.incumbent_pair == "OLD-USDT"
    assert decision.eligible_degraded_pairs == (
        "OLD-USDT",
        "NEW-USDT",
    )


def test_replacement_tie_breaks_by_entry_then_pair():
    b = replace(
        position(
            pair="BBB-USDT",
            entry_time="2022-01-01T00:00:00Z",
        ),
        degraded_since=pd.Timestamp("2022-01-02T00:00:00Z"),
    )
    a = replace(
        position(
            pair="AAA-USDT",
            entry_time="2022-01-01T00:00:00Z",
        ),
        degraded_since=pd.Timestamp("2022-01-02T00:00:00Z"),
    )
    decision = select_replacement_incumbent(
        [b, a],
        incoming_prevalidated=True,
        free_slot_exists=False,
    )
    assert decision.incumbent_pair == "AAA-USDT"


def test_replacement_reason_constant_is_frozen_for_replay_stage():
    assert REPLACEMENT_EXIT_REASON == "RS_DEGRADED_ATOMIC_REPLACEMENT"


def test_policy_component_ablation_is_structural():
    assert policy_components(ROUTER_TIME_FAIL_72_CONTROL) == {
        "family_quality_admission": False,
        "replacement_state": False,
        "profit_state": False,
    }
    assert policy_components(FAMILY_QUALITY_CONTROL_EXITS) == {
        "family_quality_admission": True,
        "replacement_state": False,
        "profit_state": False,
    }
    assert policy_components(FAMILY_QUALITY_REPLACEMENT_AWARE_RS) == {
        "family_quality_admission": True,
        "replacement_state": True,
        "profit_state": False,
    }
    assert policy_components(FULL_FAMILY_SPECIALIST_REPLACEMENT_BRAIN) == {
        "family_quality_admission": True,
        "replacement_state": True,
        "profit_state": True,
    }


def test_active_component_count_increases_by_ablation():
    assert active_component_count(ROUTER_TIME_FAIL_72_CONTROL) == 1
    assert active_component_count(FAMILY_QUALITY_CONTROL_EXITS) == 2
    assert active_component_count(FAMILY_QUALITY_REPLACEMENT_AWARE_RS) == 3
    assert active_component_count(FULL_FAMILY_SPECIALIST_REPLACEMENT_BRAIN) == 4


def test_contract_summary_has_firewalls_and_no_loader():
    summary = contract_summary()
    assert summary["economic_execution_performed"] is False
    assert summary["real_market_data_loader_present"] is False
    assert summary["2024_accessed"] is False
    assert summary["post_2024_accessed"] is False
    assert summary["production_authorized"] is False
    assert summary["mb_thesis_failure_exit"] is False
    assert summary["mb_replacement_degradation"] is False
    assert summary["rs_degradation_immediate_cash_exit"] is False
    assert summary["global_slot_escrow"] is False
    assert summary["same_pair_cooldown"] is False
