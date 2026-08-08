from __future__ import annotations

import inspect

import pandas as pd
import pytest

from spotbot.research.rd26_exit_architecture import (
    FAMILY_MOMENTUM_BREAKOUT,
    FAMILY_RELATIVE_STRENGTH_ROTATION,
)
from spotbot.research.rd27_adaptive_lifecycle import RISK_OFF, RISK_ON, TRANSITION
from spotbot.research.rd28_evidence_gated_lifecycle import (
    BACKUP_TIME_FAIL_REASON,
    EARLY_EVIDENCE_REASON,
    EVIDENCE_GATED_LIFECYCLE_IMMEDIATE_RECYCLE,
    EVIDENCE_GATED_LIFECYCLE_SLOT_ESCROW,
    FAMILY_AWARE_EVIDENCE_LIFECYCLE_SLOT_ESCROW,
    FAMILY_MB_EVIDENCE_REASON,
    FAMILY_RS_EVIDENCE_REASON,
    MAX_HOLD_REASON,
    PROFIT_GIVEBACK_REASON,
    ROUTER_TIME_FAIL_72_CONTROL,
    active_component_count,
    active_escrow_slots,
    apply_completed_asset_bar,
    contract_summary,
    escrow_slot_for_exit,
    evaluate_evidence_exit,
    evaluate_router_time_fail_control_exit,
    new_evidence_position,
    policy_components,
    router_admission,
    slot_capacity_available,
    state_deteriorated,
    state_rank,
    uses_evidence_exit,
)

ENTRY_TIME = pd.Timestamp("2023-01-01T01:00:00Z")


def position(
    *,
    state: str = RISK_ON,
    family: str = FAMILY_RELATIVE_STRENGTH_ROTATION,
    high_water: float | None = None,
):
    item = new_evidence_position(
        pair="TEST-USDT",
        entry_time=ENTRY_TIME,
        entry_price=100.0,
        atr24_at_signal=2.0,
        entry_market_state=state,
        signal_family=family,
    )
    if high_water is None:
        return item
    return item.__class__(
        pair=item.pair,
        entry_time=item.entry_time,
        entry_price=item.entry_price,
        atr24_at_signal=item.atr24_at_signal,
        entry_market_state=item.entry_market_state,
        signal_family=item.signal_family,
        high_water_prior=high_water,
    )


def evaluate(
    item,
    *,
    age: int,
    prior_close: float,
    state: str,
    family_aware: bool = False,
):
    return evaluate_evidence_exit(
        item,
        current_open_time=ENTRY_TIME + pd.Timedelta(hours=age),
        current_open=99.0,
        prior_asset_close=prior_close,
        current_market_state=state,
        family_aware=family_aware,
    )


def test_state_rank_is_exactly_frozen() -> None:
    assert state_rank(RISK_OFF) == 0
    assert state_rank(TRANSITION) == 1
    assert state_rank(RISK_ON) == 2
    assert state_deteriorated(entry_state=RISK_ON, current_state=TRANSITION)
    assert state_deteriorated(entry_state=TRANSITION, current_state=RISK_OFF)
    assert not state_deteriorated(entry_state=TRANSITION, current_state=RISK_ON)


def test_router_reuses_rd27_sensor_contract() -> None:
    on = router_admission(RISK_ON)
    transition = router_admission(TRANSITION)
    off = router_admission(RISK_OFF)
    assert on.admit_position is True
    assert on.target_slot_fraction == pytest.approx(0.18)
    assert transition.admit_position is True
    assert transition.target_slot_fraction == pytest.approx(0.09)
    assert off.record_signal is True
    assert off.admit_position is False
    assert off.target_slot_fraction == 0.0


def test_policy_registry_and_components_are_frozen() -> None:
    assert uses_evidence_exit(ROUTER_TIME_FAIL_72_CONTROL) is False
    assert policy_components(EVIDENCE_GATED_LIFECYCLE_IMMEDIATE_RECYCLE) == (False, False)
    assert policy_components(EVIDENCE_GATED_LIFECYCLE_SLOT_ESCROW) == (False, True)
    assert policy_components(FAMILY_AWARE_EVIDENCE_LIFECYCLE_SLOT_ESCROW) == (True, True)
    assert active_component_count(ROUTER_TIME_FAIL_72_CONTROL) == 1
    assert active_component_count(EVIDENCE_GATED_LIFECYCLE_IMMEDIATE_RECYCLE) == 2
    assert active_component_count(EVIDENCE_GATED_LIFECYCLE_SLOT_ESCROW) == 3
    assert active_component_count(FAMILY_AWARE_EVIDENCE_LIFECYCLE_SLOT_ESCROW) == 4


def test_evidence_exit_signature_has_no_current_high_or_low() -> None:
    parameters = inspect.signature(evaluate_evidence_exit).parameters
    assert "current_high" not in parameters
    assert "current_low" not in parameters


def test_early_exit_requires_age_24_or_more() -> None:
    item = position()
    before = evaluate(item, age=23, prior_close=99.0, state=TRANSITION)
    at = evaluate(item, age=24, prior_close=99.0, state=TRANSITION)
    assert before.should_exit is False
    assert at.should_exit is True
    assert at.exit_reason == EARLY_EVIDENCE_REASON
    assert at.exit_price == pytest.approx(99.0)


def test_early_exit_requires_trade_weakness() -> None:
    item = position()
    result = evaluate(item, age=24, prior_close=100.01, state=TRANSITION)
    assert result.should_exit is False
    assert result.market_state_deteriorated is True
    assert result.trade_weak is False


def test_early_exit_requires_state_deterioration() -> None:
    item = position(state=TRANSITION)
    result = evaluate(item, age=30, prior_close=99.0, state=TRANSITION)
    assert result.should_exit is False
    assert result.trade_weak is True
    assert result.market_state_deteriorated is False


def test_family_aware_momentum_waits_for_risk_off() -> None:
    item = position(
        state=RISK_ON,
        family=FAMILY_MOMENTUM_BREAKOUT,
    )
    transition = evaluate(
        item,
        age=24,
        prior_close=99.0,
        state=TRANSITION,
        family_aware=True,
    )
    risk_off = evaluate(
        item,
        age=24,
        prior_close=99.0,
        state=RISK_OFF,
        family_aware=True,
    )
    assert transition.should_exit is False
    assert risk_off.should_exit is True
    assert risk_off.exit_reason == FAMILY_MB_EVIDENCE_REASON


def test_family_aware_relative_strength_uses_any_state_deterioration() -> None:
    item = position(
        state=RISK_ON,
        family=FAMILY_RELATIVE_STRENGTH_ROTATION,
    )
    result = evaluate(
        item,
        age=24,
        prior_close=99.0,
        state=TRANSITION,
        family_aware=True,
    )
    assert result.should_exit is True
    assert result.exit_reason == FAMILY_RS_EVIDENCE_REASON


def test_backup_time_failure_is_exact_72h_and_needs_weakness() -> None:
    item = position(state=RISK_ON)
    before = evaluate(item, age=71, prior_close=99.0, state=RISK_ON)
    at = evaluate(item, age=72, prior_close=100.0, state=RISK_ON)
    after = evaluate(item, age=73, prior_close=99.0, state=RISK_ON)
    assert before.should_exit is False
    assert at.should_exit is True
    assert at.exit_reason == BACKUP_TIME_FAIL_REASON
    assert after.should_exit is False


def test_profit_giveback_lock_uses_prior_high_water_and_prior_close() -> None:
    item = position(high_water=108.0)
    result = evaluate(item, age=10, prior_close=102.0, state=RISK_ON)
    assert result.should_exit is True
    assert result.exit_reason == PROFIT_GIVEBACK_REASON
    assert result.profit_lock_armed is True


def test_profit_giveback_does_not_arm_below_four_atr() -> None:
    item = position(high_water=107.99)
    result = evaluate(item, age=10, prior_close=101.0, state=RISK_ON)
    assert result.should_exit is False
    assert result.profit_lock_armed is False


def test_completed_bar_high_only_affects_next_evaluation() -> None:
    item = position()
    first = evaluate(item, age=10, prior_close=101.0, state=RISK_ON)
    assert first.should_exit is False
    updated = apply_completed_asset_bar(item, completed_high=108.0)
    second = evaluate(updated, age=11, prior_close=102.0, state=RISK_ON)
    assert second.should_exit is True
    assert second.exit_reason == PROFIT_GIVEBACK_REASON


def test_max_hold_exits_at_168h_current_open() -> None:
    item = position()
    result = evaluate(item, age=168, prior_close=110.0, state=RISK_ON)
    assert result.should_exit is True
    assert result.exit_reason == MAX_HOLD_REASON
    assert result.exit_price == pytest.approx(99.0)


def test_control_time_fail_matches_frozen_checkpoint_semantics() -> None:
    item = position()
    no_exit = evaluate_router_time_fail_control_exit(
        item,
        current_open_time=ENTRY_TIME + pd.Timedelta(hours=71),
        current_open=99.0,
        prior_asset_close=90.0,
    )
    time_fail = evaluate_router_time_fail_control_exit(
        item,
        current_open_time=ENTRY_TIME + pd.Timedelta(hours=72),
        current_open=98.0,
        prior_asset_close=100.0,
    )
    assert no_exit.should_exit is False
    assert time_fail.should_exit is True
    assert time_fail.exit_reason == BACKUP_TIME_FAIL_REASON
    assert time_fail.exit_price == pytest.approx(98.0)


def test_slot_escrow_reserves_only_early_exit_slot_until_72h() -> None:
    item = position()
    escrow = escrow_slot_for_exit(
        item,
        exit_time=ENTRY_TIME + pd.Timedelta(hours=24),
        exit_reason=EARLY_EVIDENCE_REASON,
        slot_escrow_enabled=True,
    )
    assert escrow is not None
    assert escrow.release_time == ENTRY_TIME + pd.Timedelta(hours=72)
    active_before = active_escrow_slots(
        [escrow],
        current_time=ENTRY_TIME + pd.Timedelta(hours=71),
    )
    active_at = active_escrow_slots(
        [escrow],
        current_time=ENTRY_TIME + pd.Timedelta(hours=72),
    )
    assert len(active_before) == 1
    assert len(active_at) == 0


def test_slot_escrow_does_not_apply_to_backup_or_disabled_policy() -> None:
    item = position()
    backup = escrow_slot_for_exit(
        item,
        exit_time=ENTRY_TIME + pd.Timedelta(hours=72),
        exit_reason=BACKUP_TIME_FAIL_REASON,
        slot_escrow_enabled=True,
    )
    disabled = escrow_slot_for_exit(
        item,
        exit_time=ENTRY_TIME + pd.Timedelta(hours=24),
        exit_reason=EARLY_EVIDENCE_REASON,
        slot_escrow_enabled=False,
    )
    assert backup is None
    assert disabled is None


def test_slot_capacity_counts_open_plus_active_escrow_only() -> None:
    assert slot_capacity_available(open_position_count=4, active_escrow_count=0)
    assert slot_capacity_available(open_position_count=3, active_escrow_count=1)
    assert not slot_capacity_available(open_position_count=4, active_escrow_count=1)
    assert not slot_capacity_available(open_position_count=2, active_escrow_count=3)


def test_contract_summary_forbids_rd27_intrabar_exit_inputs() -> None:
    summary = contract_summary()
    assert summary["current_bar_high_used_for_exit"] is False
    assert summary["current_bar_low_used_for_exit"] is False
    assert summary["partial_selling"] is False
    assert summary["slot_escrow_reserves_cash"] is False
    assert summary["slot_escrow_reserves_notional"] is False
    assert summary["economic_execution_performed"] is False
    assert summary["real_market_data_loader_present"] is False
