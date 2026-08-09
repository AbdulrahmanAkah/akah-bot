from __future__ import annotations

from dataclasses import replace

import pandas as pd
import pytest

from spotbot.research.rd26_exit_architecture import (
    FAMILY_MOMENTUM_BREAKOUT,
    FAMILY_RELATIVE_STRENGTH_ROTATION,
)
from spotbot.research.rd29_thesis_context import AdmissionDecision
from spotbot.research.rd33_temporal_mb_architecture import (
    CANCELLED,
    CONFIRMED,
    EXPIRED,
    MB_FIRST_RETEST_RECLAIM_WITHIN_FROZEN_72H,
    MB_ONE_BAR_BREAKOUT_LEVEL_HOLD,
    MB_ONE_BAR_POST_BREAKOUT_CONTINUATION,
    PENDING,
    RD31_REGIME_HYSTERESIS_CONTROL,
    REJECTED,
    RD33TemporalMBError,
    active_component_count,
    cancel_pending_for_rs_open,
    contract_summary,
    create_pending_origin,
    evaluate_completed_bar,
    missing_confirmation_bar_decision,
    pending_decision,
    register_pending,
    remove_resolved_pending,
)

T0 = pd.Timestamp("2023-05-01T12:00:00Z")


def admission(*families: str, admit: bool = True) -> AdmissionDecision:
    return AdmissionDecision(
        record_signal=True,
        admit_position=admit,
        target_slot_fraction=0.18 if admit else 0.0,
        reason="SYNTHETIC_RD31",
        admissible_families=tuple(families) if admit else (),
    )


def origin(
    policy: str,
    *,
    pair: str = "AAA-USDT",
    signal_time: pd.Timestamp = T0,
    support: tuple[str, ...] = (FAMILY_MOMENTUM_BREAKOUT,),
    admissible: tuple[str, ...] = (FAMILY_MOMENTUM_BREAKOUT,),
):
    return create_pending_origin(
        policy_id=policy,
        universe_id="C2",
        pair=pair,
        signal_time=signal_time,
        breakout_reference=100.0,
        signal_close=102.0,
        membership_rank=1,
        period_id="ROBUSTNESS_2023",
        support_families=support,
        rd31_decision=admission(*admissible),
    )


@pytest.mark.parametrize(
    "policy",
    [
        MB_ONE_BAR_BREAKOUT_LEVEL_HOLD,
        MB_ONE_BAR_POST_BREAKOUT_CONTINUATION,
        MB_FIRST_RETEST_RECLAIM_WITHIN_FROZEN_72H,
    ],
)
def test_candidate_creates_pending_only_from_rd31_admitted_mb(policy: str) -> None:
    value = origin(policy)
    assert value.normal_entry_time == T0 + pd.Timedelta(hours=1)
    assert FAMILY_MOMENTUM_BREAKOUT in value.origin_admissible_families
    assert pending_decision(value).status == PENDING


def test_rd31_suppressed_mb_cannot_become_pending() -> None:
    with pytest.raises(
        RD33TemporalMBError,
        match="RD31-suppressed MB cannot become pending",
    ):
        create_pending_origin(
            policy_id=MB_ONE_BAR_BREAKOUT_LEVEL_HOLD,
            universe_id="C2",
            pair="AAA-USDT",
            signal_time=T0,
            breakout_reference=100.0,
            signal_close=102.0,
            membership_rank=1,
            period_id="ROBUSTNESS_2023",
            support_families=(FAMILY_MOMENTUM_BREAKOUT,),
            rd31_decision=admission(FAMILY_MOMENTUM_BREAKOUT, admit=False),
        )


def test_rs_only_admission_cannot_create_mb_pending() -> None:
    with pytest.raises(
        RD33TemporalMBError,
        match="MB is not independently admissible",
    ):
        create_pending_origin(
            policy_id=MB_ONE_BAR_BREAKOUT_LEVEL_HOLD,
            universe_id="C2",
            pair="AAA-USDT",
            signal_time=T0,
            breakout_reference=100.0,
            signal_close=102.0,
            membership_rank=1,
            period_id="ROBUSTNESS_2023",
            support_families=(
                FAMILY_MOMENTUM_BREAKOUT,
                FAMILY_RELATIVE_STRENGTH_ROTATION,
            ),
            rd31_decision=admission(FAMILY_RELATIVE_STRENGTH_ROTATION),
        )


def test_overlap_can_create_pending_when_rd31_admits_mb_and_rs() -> None:
    value = origin(
        MB_ONE_BAR_BREAKOUT_LEVEL_HOLD,
        support=(
            FAMILY_MOMENTUM_BREAKOUT,
            FAMILY_RELATIVE_STRENGTH_ROTATION,
        ),
        admissible=(
            FAMILY_MOMENTUM_BREAKOUT,
            FAMILY_RELATIVE_STRENGTH_ROTATION,
        ),
    )
    assert value.origin_admissible_families == (
        FAMILY_MOMENTUM_BREAKOUT,
        FAMILY_RELATIVE_STRENGTH_ROTATION,
    )


def test_level_hold_confirms_strictly_above_breakout_reference() -> None:
    value = origin(MB_ONE_BAR_BREAKOUT_LEVEL_HOLD)
    decision = evaluate_completed_bar(
        value,
        completed_time=T0 + pd.Timedelta(hours=1),
        low=99.0,
        close=100.01,
    )
    assert decision.status == CONFIRMED
    assert decision.actual_entry_time == T0 + pd.Timedelta(hours=2)


@pytest.mark.parametrize("close", [100.0, 99.0])
def test_level_hold_rejects_equal_or_below_reference(close: float) -> None:
    value = origin(MB_ONE_BAR_BREAKOUT_LEVEL_HOLD)
    decision = evaluate_completed_bar(
        value,
        completed_time=T0 + pd.Timedelta(hours=1),
        low=98.0,
        close=close,
    )
    assert decision.status == REJECTED
    assert decision.actual_entry_time is None


def test_continuation_confirms_strictly_above_signal_close() -> None:
    value = origin(MB_ONE_BAR_POST_BREAKOUT_CONTINUATION)
    decision = evaluate_completed_bar(
        value,
        completed_time=T0 + pd.Timedelta(hours=1),
        low=100.0,
        close=102.01,
    )
    assert decision.status == CONFIRMED
    assert decision.actual_entry_time == T0 + pd.Timedelta(hours=2)


@pytest.mark.parametrize("close", [102.0, 101.99])
def test_continuation_rejects_equal_or_below_signal_close(close: float) -> None:
    value = origin(MB_ONE_BAR_POST_BREAKOUT_CONTINUATION)
    decision = evaluate_completed_bar(
        value,
        completed_time=T0 + pd.Timedelta(hours=1),
        low=100.0,
        close=close,
    )
    assert decision.status == REJECTED


def test_one_bar_architecture_rejects_wrong_confirmation_hour() -> None:
    value = origin(MB_ONE_BAR_BREAKOUT_LEVEL_HOLD)
    with pytest.raises(RD33TemporalMBError, match="exactly signal_time"):
        evaluate_completed_bar(
            value,
            completed_time=T0 + pd.Timedelta(hours=2),
            low=99.0,
            close=101.0,
        )


def test_no_confirmation_can_use_signal_bar() -> None:
    value = origin(MB_FIRST_RETEST_RECLAIM_WITHIN_FROZEN_72H)
    with pytest.raises(RD33TemporalMBError, match="cannot use signal bar"):
        evaluate_completed_bar(
            value,
            completed_time=T0,
            low=99.0,
            close=101.0,
        )


def test_retest_requires_touch_and_reclaim_on_same_completed_bar() -> None:
    value = origin(MB_FIRST_RETEST_RECLAIM_WITHIN_FROZEN_72H)
    no_touch = evaluate_completed_bar(
        value,
        completed_time=T0 + pd.Timedelta(hours=1),
        low=100.01,
        close=103.0,
    )
    assert no_touch.status == PENDING

    no_reclaim = evaluate_completed_bar(
        value,
        completed_time=T0 + pd.Timedelta(hours=2),
        low=99.0,
        close=100.0,
    )
    assert no_reclaim.status == PENDING

    confirmed = evaluate_completed_bar(
        value,
        completed_time=T0 + pd.Timedelta(hours=3),
        low=100.0,
        close=100.01,
    )
    assert confirmed.status == CONFIRMED
    assert confirmed.actual_entry_time == T0 + pd.Timedelta(hours=4)


def test_retest_expires_exactly_at_frozen_72h() -> None:
    value = origin(MB_FIRST_RETEST_RECLAIM_WITHIN_FROZEN_72H)
    decision = evaluate_completed_bar(
        value,
        completed_time=T0 + pd.Timedelta(hours=72),
        low=101.0,
        close=102.0,
    )
    assert decision.status == EXPIRED
    assert decision.actual_entry_time is None


def test_retest_can_confirm_at_hour_72_before_expiry() -> None:
    value = origin(MB_FIRST_RETEST_RECLAIM_WITHIN_FROZEN_72H)
    decision = evaluate_completed_bar(
        value,
        completed_time=T0 + pd.Timedelta(hours=72),
        low=99.0,
        close=101.0,
    )
    assert decision.status == CONFIRMED
    assert decision.actual_entry_time == T0 + pd.Timedelta(hours=73)


def test_retest_rejects_evaluation_after_72h() -> None:
    value = origin(MB_FIRST_RETEST_RECLAIM_WITHIN_FROZEN_72H)
    with pytest.raises(RD33TemporalMBError, match="exceeded frozen 72h"):
        evaluate_completed_bar(
            value,
            completed_time=T0 + pd.Timedelta(hours=73),
            low=99.0,
            close=101.0,
        )


def test_earliest_pending_owner_is_retained() -> None:
    first = origin(
        MB_FIRST_RETEST_RECLAIM_WITHIN_FROZEN_72H,
        signal_time=T0,
    )
    later = origin(
        MB_FIRST_RETEST_RECLAIM_WITHIN_FROZEN_72H,
        signal_time=T0 + pd.Timedelta(hours=2),
    )
    book, first_reg = register_pending({}, first)
    assert first_reg.accepted is True
    book2, later_reg = register_pending(book, later)
    assert later_reg.accepted is False
    assert book2["AAA-USDT"].origin_key == first.origin_key


def test_registry_fails_if_later_owner_preexists_before_earlier_origin() -> None:
    later = origin(
        MB_FIRST_RETEST_RECLAIM_WITHIN_FROZEN_72H,
        signal_time=T0 + pd.Timedelta(hours=2),
    )
    earlier = origin(
        MB_FIRST_RETEST_RECLAIM_WITHIN_FROZEN_72H,
        signal_time=T0,
    )
    with pytest.raises(RD33TemporalMBError, match="later owner"):
        register_pending({"AAA-USDT": later}, earlier)


def test_rs_open_cancels_same_pair_pending() -> None:
    value = origin(MB_ONE_BAR_BREAKOUT_LEVEL_HOLD)
    book, _ = register_pending({}, value)
    book, decision = cancel_pending_for_rs_open(
        book,
        pair="AAA-USDT",
    )
    assert book == {}
    assert decision is not None
    assert decision.status == CANCELLED
    assert decision.reason == "RD33_MB_PENDING_CANCELLED_BY_RS_OPEN"


def test_rs_open_without_pending_is_noop() -> None:
    book, decision = cancel_pending_for_rs_open({}, pair="AAA-USDT")
    assert book == {}
    assert decision is None


def test_remove_resolved_pending_requires_exact_origin_owner() -> None:
    value = origin(MB_ONE_BAR_BREAKOUT_LEVEL_HOLD)
    book, _ = register_pending({}, value)
    wrong = replace(value, origin_key="wrong")
    with pytest.raises(RD33TemporalMBError, match="not the current pair owner"):
        remove_resolved_pending(book, origin=wrong)
    assert remove_resolved_pending(book, origin=value) == {}


@pytest.mark.parametrize(
    "policy",
    [
        MB_ONE_BAR_BREAKOUT_LEVEL_HOLD,
        MB_ONE_BAR_POST_BREAKOUT_CONTINUATION,
    ],
)
def test_missing_required_one_bar_confirmation_fails_closed(policy: str) -> None:
    value = origin(policy)
    decision = missing_confirmation_bar_decision(
        value,
        expected_completed_time=T0 + pd.Timedelta(hours=1),
    )
    assert decision.status == REJECTED
    assert decision.actual_entry_time is None


def test_missing_retest_bar_stays_pending_before_72h_and_expires_at_72h() -> None:
    value = origin(MB_FIRST_RETEST_RECLAIM_WITHIN_FROZEN_72H)
    pending = missing_confirmation_bar_decision(
        value,
        expected_completed_time=T0 + pd.Timedelta(hours=10),
    )
    assert pending.status == PENDING
    expired = missing_confirmation_bar_decision(
        value,
        expected_completed_time=T0 + pd.Timedelta(hours=72),
    )
    assert expired.status == EXPIRED


def test_origin_is_frozen_and_deterministic() -> None:
    left = origin(MB_ONE_BAR_BREAKOUT_LEVEL_HOLD)
    right = origin(MB_ONE_BAR_BREAKOUT_LEVEL_HOLD)
    assert left == right
    assert left.origin_key == "C2|AAA-USDT|2023-05-01T12:00:00+00:00"


def test_invalid_numeric_inputs_fail_closed() -> None:
    with pytest.raises(RD33TemporalMBError, match="breakout_reference"):
        create_pending_origin(
            policy_id=MB_ONE_BAR_BREAKOUT_LEVEL_HOLD,
            universe_id="C2",
            pair="AAA-USDT",
            signal_time=T0,
            breakout_reference=float("nan"),
            signal_close=102.0,
            membership_rank=1,
            period_id="ROBUSTNESS_2023",
            support_families=(FAMILY_MOMENTUM_BREAKOUT,),
            rd31_decision=admission(FAMILY_MOMENTUM_BREAKOUT),
        )


def test_control_policy_cannot_create_pending_origin() -> None:
    with pytest.raises(RD33TemporalMBError, match="requires candidate policy"):
        origin(RD31_REGIME_HYSTERESIS_CONTROL)


def test_active_component_count_frozen() -> None:
    assert active_component_count(RD31_REGIME_HYSTERESIS_CONTROL) == 3
    assert active_component_count(MB_ONE_BAR_BREAKOUT_LEVEL_HOLD) == 4
    assert active_component_count(MB_ONE_BAR_POST_BREAKOUT_CONTINUATION) == 4
    assert active_component_count(MB_FIRST_RETEST_RECLAIM_WITHIN_FROZEN_72H) == 4


def test_contract_summary_has_no_economic_or_governor_execution() -> None:
    summary = contract_summary()
    assert summary["governor_transition_function_present"] is False
    assert summary["confirmation_engine_can_mutate_governor"] is False
    assert summary["pending_consumes_position_slot"] is False
    assert summary["pending_reserves_cash"] is False
    assert summary["pending_reserves_gross_exposure"] is False
    assert summary["retest_window_hours"] == 72
    assert summary["numeric_confirmation_margin"] is None
    assert summary["economic_execution_performed"] is False
    assert summary["real_market_data_loader_present"] is False
    assert summary["raw_market_data_loaded"] is False
    assert summary["2024_accessed"] is False
    assert summary["post_2024_accessed"] is False
    assert summary["production_authorized"] is False
