from __future__ import annotations

import inspect

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
    FULL_FAMILY_QUALITY_THESIS_BRAIN,
    MAX_HOLD_EXIT_REASON,
    MIXED,
    PROFIT_GIVEBACK_EXIT_REASON,
    ROUTER_TIME_FAIL_72_CONTROL,
    STRESSED,
    SUPPORTIVE,
    THESIS_CONFIDENCE_LIFECYCLE,
    THESIS_CONFIDENCE_PAIR_COOLDOWN,
    THESIS_FAILURE_EXIT_REASON,
    UNAVAILABLE,
    active_component_count,
    active_pair_cooldowns,
    admission_decision,
    aggregate_thesis_status,
    apply_completed_high,
    compute_market_context,
    contract_summary,
    cooldown_after_exit,
    evaluate_lifecycle_exit,
    is_thesis_checkpoint,
    momentum_breakout_thesis_status,
    new_thesis_position,
    pair_is_cooldown_blocked,
    policy_components,
    relative_strength_rank,
    relative_strength_thesis_status,
)

ENTRY = pd.Timestamp("2023-01-01T01:00:00Z")
MEMBERS = (
    ("AAA-USDT", 1),
    ("BBB-USDT", 2),
    ("CCC-USDT", 3),
    ("DDD-USDT", 4),
    ("EEE-USDT", 5),
    ("FFF-USDT", 6),
)


def returns(
    aaa: float = 0.30,
    bbb: float = 0.20,
    ccc: float = 0.10,
    ddd: float = 0.05,
    eee: float = 0.01,
    fff: float = -0.02,
):
    return {
        "AAA-USDT": aaa,
        "BBB-USDT": bbb,
        "CCC-USDT": ccc,
        "DDD-USDT": ddd,
        "EEE-USDT": eee,
        "FFF-USDT": fff,
    }


def context(state=RISK_ON, values=None):
    return compute_market_context(
        btc_state=state,
        members=MEMBERS,
        return_72h_by_pair=returns() if values is None else values,
    )


def position(
    *,
    families=(FAMILY_MOMENTUM_BREAKOUT,),
    high_water=None,
):
    item = new_thesis_position(
        pair="AAA-USDT",
        entry_time=ENTRY,
        entry_price=100.0,
        atr24_at_signal=2.0,
        entry_market_context=SUPPORTIVE,
        support_families=families,
        momentum_breakout_reference=(98.0 if FAMILY_MOMENTUM_BREAKOUT in families else None),
    )
    if high_water is None:
        return item
    return item.__class__(
        pair=item.pair,
        entry_time=item.entry_time,
        entry_price=item.entry_price,
        atr24_at_signal=item.atr24_at_signal,
        entry_market_context=item.entry_market_context,
        support_families=item.support_families,
        momentum_breakout_reference=item.momentum_breakout_reference,
        high_water_prior=high_water,
    )


def test_market_context_supportive():
    result = context(RISK_ON)
    assert result.breadth_ready is True
    assert result.breadth_positive is True
    assert result.context == SUPPORTIVE


def test_market_context_mixed():
    assert context(TRANSITION).context == MIXED


def test_market_context_stressed_transition_nonpositive_breadth():
    values = returns(
        aaa=0.04,
        bbb=0.02,
        ccc=0.00,
        ddd=-0.01,
        eee=-0.03,
        fff=-0.05,
    )
    result = context(TRANSITION, values)
    assert result.breadth_positive is False
    assert result.context == STRESSED


def test_risk_off_is_stressed_even_positive_breadth():
    assert context(RISK_OFF).context == STRESSED


def test_missing_breadth_is_unavailable():
    values = returns()
    values["FFF-USDT"] = None
    result = context(RISK_ON, values)
    assert result.breadth_ready is False
    assert result.context == UNAVAILABLE
    assert result.observed_member_count == 5


def test_rs_rank_matches_rd26_tie_break():
    values = returns(aaa=0.20, bbb=0.20)
    ready, current_return, current_rank = relative_strength_rank(
        pair="AAA-USDT",
        members=MEMBERS,
        return_72h_by_pair=values,
    )
    assert ready is True
    assert current_return == pytest.approx(0.20)
    assert current_rank == 1


def test_rs_thesis_retained_only_positive_top_two():
    retained = relative_strength_thesis_status(
        pair="AAA-USDT",
        members=MEMBERS,
        return_72h_by_pair=returns(aaa=0.15, bbb=0.20, ccc=0.10),
    )
    failed_rank = relative_strength_thesis_status(
        pair="AAA-USDT",
        members=MEMBERS,
        return_72h_by_pair=returns(aaa=0.08, bbb=0.20, ccc=0.10),
    )
    assert retained.retained is True
    assert retained.current_rank == 2
    assert failed_rank.failed is True
    assert failed_rank.current_rank == 3


def test_rs_membership_loss_is_failure():
    reduced = tuple(member for member in MEMBERS if member[0] != "AAA-USDT")
    status = relative_strength_thesis_status(
        pair="AAA-USDT",
        members=reduced,
        return_72h_by_pair=returns(),
    )
    assert status.evaluable is True
    assert status.failed is True
    assert status.reason == "MEMBERSHIP_LOSS"


def test_rs_missing_cross_section_is_unevaluable():
    values = returns()
    values["CCC-USDT"] = None
    status = relative_strength_thesis_status(
        pair="AAA-USDT",
        members=MEMBERS,
        return_72h_by_pair=values,
    )
    assert status.evaluable is False
    assert status.failed is None


def test_mb_uses_entry_breakout_reference_not_entry_price():
    retained = momentum_breakout_thesis_status(
        pair_in_current_membership=True,
        prior_completed_close=99.0,
        breakout_reference=98.0,
    )
    failed = momentum_breakout_thesis_status(
        pair_in_current_membership=True,
        prior_completed_close=98.0,
        breakout_reference=98.0,
    )
    assert retained.retained is True
    assert failed.failed is True


def test_mb_membership_loss_is_failure():
    status = momentum_breakout_thesis_status(
        pair_in_current_membership=False,
        prior_completed_close=120.0,
        breakout_reference=98.0,
    )
    assert status.failed is True
    assert status.reason == "MEMBERSHIP_LOSS"


def test_overlap_requires_all_supporting_theses_to_fail():
    status = aggregate_thesis_status(
        pair="AAA-USDT",
        support_families=(
            FAMILY_MOMENTUM_BREAKOUT,
            FAMILY_RELATIVE_STRENGTH_ROTATION,
        ),
        members=MEMBERS,
        prior_completed_close=97.0,
        return_72h_by_pair=returns(aaa=0.15, bbb=0.20, ccc=0.10),
        momentum_breakout_reference=98.0,
    )
    assert status.evaluable is True
    assert status.failed is False
    assert status.retained is True


def test_overlap_fails_when_all_supporting_theories_fail():
    status = aggregate_thesis_status(
        pair="AAA-USDT",
        support_families=(
            FAMILY_MOMENTUM_BREAKOUT,
            FAMILY_RELATIVE_STRENGTH_ROTATION,
        ),
        members=MEMBERS,
        prior_completed_close=97.0,
        return_72h_by_pair=returns(aaa=0.08, bbb=0.20, ccc=0.10),
        momentum_breakout_reference=98.0,
    )
    assert status.failed is True


def test_checkpoints_are_exact():
    assert is_thesis_checkpoint(24)
    assert is_thesis_checkpoint(72)
    assert is_thesis_checkpoint(144)
    assert not is_thesis_checkpoint(25)
    assert not is_thesis_checkpoint(73)


def test_failed_thesis_does_not_exit_off_checkpoint():
    item = position()
    stressed = context(
        TRANSITION,
        returns(
            aaa=0.04,
            bbb=0.02,
            ccc=0.00,
            ddd=-0.01,
            eee=-0.03,
            fff=-0.05,
        ),
    )
    decision = evaluate_lifecycle_exit(
        item,
        current_open_time=ENTRY + pd.Timedelta(hours=25),
        current_open=97.0,
        prior_completed_close=97.0,
        current_members=MEMBERS,
        return_72h_by_pair=returns(),
        market_context=stressed,
    )
    assert decision.should_exit is False
    assert decision.at_thesis_checkpoint is False


def test_exit_requires_failed_thesis_and_stressed_context():
    item = position()
    stressed = context(
        TRANSITION,
        returns(
            aaa=0.04,
            bbb=0.02,
            ccc=0.00,
            ddd=-0.01,
            eee=-0.03,
            fff=-0.05,
        ),
    )
    failed_stressed = evaluate_lifecycle_exit(
        item,
        current_open_time=ENTRY + pd.Timedelta(hours=24),
        current_open=97.0,
        prior_completed_close=97.0,
        current_members=MEMBERS,
        return_72h_by_pair=returns(),
        market_context=stressed,
    )
    failed_supportive = evaluate_lifecycle_exit(
        item,
        current_open_time=ENTRY + pd.Timedelta(hours=24),
        current_open=97.0,
        prior_completed_close=97.0,
        current_members=MEMBERS,
        return_72h_by_pair=returns(),
        market_context=context(RISK_ON),
    )
    assert failed_stressed.should_exit is True
    assert failed_stressed.exit_reason == THESIS_FAILURE_EXIT_REASON
    assert failed_supportive.should_exit is False


def test_unavailable_thesis_is_fail_open_hold():
    item = position(families=(FAMILY_RELATIVE_STRENGTH_ROTATION,))
    values = returns()
    values["CCC-USDT"] = None
    decision = evaluate_lifecycle_exit(
        item,
        current_open_time=ENTRY + pd.Timedelta(hours=24),
        current_open=95.0,
        prior_completed_close=95.0,
        current_members=MEMBERS,
        return_72h_by_pair=values,
        market_context=context(RISK_OFF),
    )
    assert decision.should_exit is False
    assert decision.thesis_evaluable is False


def test_no_unconditional_72h_time_fail():
    item = position()
    decision = evaluate_lifecycle_exit(
        item,
        current_open_time=ENTRY + pd.Timedelta(hours=72),
        current_open=90.0,
        prior_completed_close=97.0,
        current_members=MEMBERS,
        return_72h_by_pair=returns(),
        market_context=context(RISK_ON),
    )
    assert decision.should_exit is False


def test_profit_giveback_is_separate_and_off_checkpoint():
    item = position(high_water=108.0)
    decision = evaluate_lifecycle_exit(
        item,
        current_open_time=ENTRY + pd.Timedelta(hours=11),
        current_open=101.0,
        prior_completed_close=102.0,
        current_members=MEMBERS,
        return_72h_by_pair=returns(),
        market_context=context(RISK_ON),
    )
    assert decision.should_exit is True
    assert decision.exit_reason == PROFIT_GIVEBACK_EXIT_REASON


def test_completed_high_only_changes_next_decision():
    item = position()
    first = evaluate_lifecycle_exit(
        item,
        current_open_time=ENTRY + pd.Timedelta(hours=11),
        current_open=101.0,
        prior_completed_close=102.0,
        current_members=MEMBERS,
        return_72h_by_pair=returns(),
        market_context=context(RISK_ON),
    )
    assert first.should_exit is False
    updated = apply_completed_high(item, completed_high=108.0)
    second = evaluate_lifecycle_exit(
        updated,
        current_open_time=ENTRY + pd.Timedelta(hours=12),
        current_open=101.0,
        prior_completed_close=102.0,
        current_members=MEMBERS,
        return_72h_by_pair=returns(),
        market_context=context(RISK_ON),
    )
    assert second.should_exit is True
    assert second.exit_reason == PROFIT_GIVEBACK_EXIT_REASON


def test_exit_signature_has_no_current_high_or_low():
    params = inspect.signature(evaluate_lifecycle_exit).parameters
    assert "current_high" not in params
    assert "current_low" not in params


def test_max_hold_priority_at_168():
    item = position(high_water=108.0)
    decision = evaluate_lifecycle_exit(
        item,
        current_open_time=ENTRY + pd.Timedelta(hours=168),
        current_open=101.0,
        prior_completed_close=102.0,
        current_members=MEMBERS,
        return_72h_by_pair=returns(),
        market_context=context(RISK_ON),
    )
    assert decision.exit_reason == MAX_HOLD_EXIT_REASON


def test_family_quality_disabled_exact_rd27_router():
    decision = admission_decision(
        support_families=(FAMILY_RELATIVE_STRENGTH_ROTATION,),
        btc_state=TRANSITION,
        market_context=context(TRANSITION),
        family_quality_enabled=False,
    )
    assert decision.admit_position is True
    assert decision.target_slot_fraction == pytest.approx(0.09)


def test_full_family_quality_rs_supportive_only():
    family = (FAMILY_RELATIVE_STRENGTH_ROTATION,)
    supportive = admission_decision(
        support_families=family,
        btc_state=RISK_ON,
        market_context=context(RISK_ON),
        family_quality_enabled=True,
    )
    mixed = admission_decision(
        support_families=family,
        btc_state=TRANSITION,
        market_context=context(TRANSITION),
        family_quality_enabled=True,
    )
    values = returns()
    values["FFF-USDT"] = None
    unavailable = admission_decision(
        support_families=family,
        btc_state=RISK_ON,
        market_context=context(RISK_ON, values),
        family_quality_enabled=True,
    )
    assert supportive.target_slot_fraction == pytest.approx(0.18)
    assert mixed.admit_position is False
    assert unavailable.admit_position is False


def test_full_family_quality_mb_keeps_rd27_router():
    family = (FAMILY_MOMENTUM_BREAKOUT,)
    on = admission_decision(
        support_families=family,
        btc_state=RISK_ON,
        market_context=context(RISK_ON),
        family_quality_enabled=True,
    )
    transition = admission_decision(
        support_families=family,
        btc_state=TRANSITION,
        market_context=context(TRANSITION),
        family_quality_enabled=True,
    )
    off = admission_decision(
        support_families=family,
        btc_state=RISK_OFF,
        market_context=context(RISK_OFF),
        family_quality_enabled=True,
    )
    assert on.target_slot_fraction == pytest.approx(0.18)
    assert transition.target_slot_fraction == pytest.approx(0.09)
    assert off.admit_position is False


def test_overlap_admission_any_family_max_slot():
    decision = admission_decision(
        support_families=(
            FAMILY_MOMENTUM_BREAKOUT,
            FAMILY_RELATIVE_STRENGTH_ROTATION,
        ),
        btc_state=TRANSITION,
        market_context=context(TRANSITION),
        family_quality_enabled=True,
    )
    assert decision.admit_position is True
    assert decision.target_slot_fraction == pytest.approx(0.09)
    assert decision.admissible_families == (FAMILY_MOMENTUM_BREAKOUT,)


def test_same_pair_cooldown_only_until_entry_plus_72h():
    item = position()
    cooldown = cooldown_after_exit(
        item,
        exit_time=ENTRY + pd.Timedelta(hours=24),
        exit_reason=THESIS_FAILURE_EXIT_REASON,
        same_pair_cooldown_enabled=True,
    )
    assert cooldown is not None
    assert pair_is_cooldown_blocked(
        [cooldown],
        pair="AAA-USDT",
        current_time=ENTRY + pd.Timedelta(hours=71),
    )
    assert not pair_is_cooldown_blocked(
        [cooldown],
        pair="BBB-USDT",
        current_time=ENTRY + pd.Timedelta(hours=71),
    )
    assert not pair_is_cooldown_blocked(
        [cooldown],
        pair="AAA-USDT",
        current_time=ENTRY + pd.Timedelta(hours=72),
    )


def test_profit_exit_does_not_create_cooldown():
    item = position()
    assert (
        cooldown_after_exit(
            item,
            exit_time=ENTRY + pd.Timedelta(hours=24),
            exit_reason=PROFIT_GIVEBACK_EXIT_REASON,
            same_pair_cooldown_enabled=True,
        )
        is None
    )


def test_active_cooldown_releases_at_72h():
    item = position()
    cooldown = cooldown_after_exit(
        item,
        exit_time=ENTRY + pd.Timedelta(hours=24),
        exit_reason=THESIS_FAILURE_EXIT_REASON,
        same_pair_cooldown_enabled=True,
    )
    assert cooldown is not None
    assert (
        len(
            active_pair_cooldowns(
                [cooldown],
                current_time=ENTRY + pd.Timedelta(hours=71),
            )
        )
        == 1
    )
    assert (
        len(
            active_pair_cooldowns(
                [cooldown],
                current_time=ENTRY + pd.Timedelta(hours=72),
            )
        )
        == 0
    )


def test_policy_registry_and_component_counts():
    assert policy_components(ROUTER_TIME_FAIL_72_CONTROL) == {
        "family_quality_admission": False,
        "thesis_confidence_exit": False,
        "profit_state": False,
        "same_pair_cooldown": False,
    }
    assert policy_components(THESIS_CONFIDENCE_LIFECYCLE)["thesis_confidence_exit"]
    assert policy_components(THESIS_CONFIDENCE_PAIR_COOLDOWN)["same_pair_cooldown"]
    assert policy_components(FULL_FAMILY_QUALITY_THESIS_BRAIN)["family_quality_admission"]
    assert active_component_count(ROUTER_TIME_FAIL_72_CONTROL) == 1


def test_contract_is_pre_economic_and_no_global_escrow():
    summary = contract_summary()
    assert summary["breadth_missing_data_admission_behavior"] == "FAIL_CLOSED"
    assert summary["thesis_missing_data_exit_behavior"] == "FAIL_OPEN_HOLD"
    assert summary["global_slot_escrow"] is False
    assert summary["current_bar_high_used_for_exit"] is False
    assert summary["current_bar_low_used_for_exit"] is False
    assert summary["economic_execution_performed"] is False
    assert summary["real_market_data_loader_present"] is False
