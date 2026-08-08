from __future__ import annotations

from dataclasses import replace

import pandas as pd
import pytest

import spotbot.research.rd30_replacement_replay as replay_module
from spotbot.research.rd26_exit_architecture import (
    FAMILY_MOMENTUM_BREAKOUT,
    FAMILY_RELATIVE_STRENGTH_ROTATION,
)
from spotbot.research.rd30_family_specialist_state import (
    FAMILY_QUALITY_CONTROL_EXITS,
    FAMILY_QUALITY_REPLACEMENT_AWARE_RS,
    FULL_FAMILY_SPECIALIST_REPLACEMENT_BRAIN,
    MB_SUPPORTED,
    ROUTER_TIME_FAIL_72_CONTROL,
    RS_ONLY,
    new_specialist_position,
)
from spotbot.research.rd30_replacement_replay import (
    AtomicReplacementPlan,
    EntrySizingDecision,
    RD30ReplayError,
    ReplayPosition,
    contract_summary,
    plan_atomic_replacement,
    replay_rd30_policy,
    size_entry_from_marks,
)


def replay_position(
    *,
    pair: str,
    family: str = FAMILY_RELATIVE_STRENGTH_ROTATION,
    entry_time: str = "2022-01-01T00:00:00Z",
    degraded_since: str | None = None,
    quantity: float = 10.0,
    last_mark: float = 100.0,
) -> ReplayPosition:
    specialist = new_specialist_position(
        pair=pair,
        entry_time=pd.Timestamp(entry_time),
        entry_price=100.0,
        atr24_at_signal=2.0,
        support_families=(family,),
    )
    if degraded_since is not None:
        specialist = replace(
            specialist,
            degraded_since=pd.Timestamp(degraded_since),
        )
    return ReplayPosition(
        pair=pair,
        signal_time=pd.Timestamp("2021-12-31T23:00:00Z"),
        entry_time=pd.Timestamp(entry_time),
        max_exit_time=pd.Timestamp(entry_time) + pd.Timedelta(hours=168),
        entry_price=100.0,
        quantity=quantity,
        entry_notional=quantity * 100.0,
        entry_cost=2.5,
        membership_rank=1,
        support_families=(family,),
        period_id="ROBUSTNESS_2022",
        atr24_at_signal=2.0,
        specialist=specialist,
        entry_market_state="RISK_ON",
        entry_market_context="SUPPORTIVE",
        last_mark=last_mark,
    )


def test_size_entry_normal_free_slot():
    decision = size_entry_from_marks(
        cash=50000.0,
        marked_notionals=[10000.0, 10000.0],
        target_slot_fraction=0.18,
        capacity_source=10_000_000.0,
        side_cost=0.00125,
    )
    assert decision.feasible is True
    assert decision.notional > 0.0
    assert decision.reason == "ENTRY_FEASIBLE"


def test_size_entry_capacity_cap_is_detected():
    decision = size_entry_from_marks(
        cash=100000.0,
        marked_notionals=[],
        target_slot_fraction=0.18,
        capacity_source=100_000.0,
        side_cost=0.00125,
    )
    assert decision.feasible is True
    assert decision.capacity_capped is True
    assert decision.notional == pytest.approx(500.0)


def test_gross_limit_precedes_cash_limit_under_90pct_contract():
    decision = size_entry_from_marks(
        cash=100.0,
        marked_notionals=[700.0],
        target_slot_fraction=0.18,
        capacity_source=10_000_000.0,
        side_cost=0.00125,
    )
    assert decision.feasible is True
    assert decision.cash_capped is False
    assert decision.gross_room < decision.max_cash_notional
    assert decision.notional == pytest.approx(decision.gross_room)


def test_size_entry_capacity_unavailable_is_infeasible():
    decision = size_entry_from_marks(
        cash=100000.0,
        marked_notionals=[],
        target_slot_fraction=0.18,
        capacity_source=0.0,
        side_cost=0.00125,
    )
    assert decision.feasible is False
    assert decision.reason == "CAPACITY_UNAVAILABLE"


def test_replacement_requires_prevalidated_incoming():
    positions = {
        "AAA-USDT": replay_position(
            pair="AAA-USDT",
            degraded_since="2022-01-02T00:00:00Z",
        )
    }
    plan = plan_atomic_replacement(
        positions,
        cash=50000.0,
        incoming_prevalidated=False,
        free_slot_exists=False,
        target_slot_fraction=0.18,
        capacity_source=10_000_000.0,
        side_cost=0.00125,
        current_open_by_pair={"AAA-USDT": 95.0},
    )
    assert plan.should_replace is False
    assert plan.reason == "INCOMING_ENTRY_NOT_PREVALIDATED"


def test_replacement_forbidden_when_free_slot_exists():
    positions = {
        "AAA-USDT": replay_position(
            pair="AAA-USDT",
            degraded_since="2022-01-02T00:00:00Z",
        )
    }
    plan = plan_atomic_replacement(
        positions,
        cash=50000.0,
        incoming_prevalidated=True,
        free_slot_exists=True,
        target_slot_fraction=0.18,
        capacity_source=10_000_000.0,
        side_cost=0.00125,
        current_open_by_pair={"AAA-USDT": 95.0},
    )
    assert plan.should_replace is False
    assert plan.reason == "FREE_SLOT_EXISTS_NO_REPLACEMENT"


def test_mb_supported_is_never_selected_as_incumbent():
    positions = {
        "MB-USDT": replay_position(
            pair="MB-USDT",
            family=FAMILY_MOMENTUM_BREAKOUT,
        )
    }
    plan = plan_atomic_replacement(
        positions,
        cash=50000.0,
        incoming_prevalidated=True,
        free_slot_exists=False,
        target_slot_fraction=0.18,
        capacity_source=10_000_000.0,
        side_cost=0.00125,
        current_open_by_pair={"MB-USDT": 95.0},
    )
    assert positions["MB-USDT"].specialist.lifecycle_class == MB_SUPPORTED
    assert plan.should_replace is False
    assert plan.reason == "NO_DEGRADED_RS_ONLY_INCUMBENT"


def test_oldest_degraded_rs_is_selected():
    positions = {
        "NEW-USDT": replay_position(
            pair="NEW-USDT",
            degraded_since="2022-01-03T00:00:00Z",
        ),
        "OLD-USDT": replay_position(
            pair="OLD-USDT",
            degraded_since="2022-01-02T00:00:00Z",
        ),
    }
    plan = plan_atomic_replacement(
        positions,
        cash=50000.0,
        incoming_prevalidated=True,
        free_slot_exists=False,
        target_slot_fraction=0.18,
        capacity_source=10_000_000.0,
        side_cost=0.00125,
        current_open_by_pair={
            "NEW-USDT": 100.0,
            "OLD-USDT": 90.0,
        },
    )
    assert plan.should_replace is True
    assert plan.incumbent_pair == "OLD-USDT"


def test_replacement_plan_uses_hypothetical_exit_credit():
    positions = {
        "AAA-USDT": replay_position(
            pair="AAA-USDT",
            degraded_since="2022-01-02T00:00:00Z",
            quantity=10.0,
        )
    }
    plan = plan_atomic_replacement(
        positions,
        cash=1.0,
        incoming_prevalidated=True,
        free_slot_exists=False,
        target_slot_fraction=0.18,
        capacity_source=10_000_000.0,
        side_cost=0.00125,
        current_open_by_pair={"AAA-USDT": 100.0},
    )
    assert plan.should_replace is True
    assert plan.incumbent_cash_credit == pytest.approx(998.75)
    assert plan.sizing is not None
    assert plan.sizing.feasible is True
    assert plan.sizing.notional > 1.0


def test_failed_replacement_sizing_does_not_mutate_positions():
    incumbent = replay_position(
        pair="AAA-USDT",
        degraded_since="2022-01-02T00:00:00Z",
    )
    positions = {"AAA-USDT": incumbent}
    before = dict(positions)
    plan = plan_atomic_replacement(
        positions,
        cash=50000.0,
        incoming_prevalidated=True,
        free_slot_exists=False,
        target_slot_fraction=0.18,
        capacity_source=0.0,
        side_cost=0.00125,
        current_open_by_pair={"AAA-USDT": 90.0},
    )
    assert plan.should_replace is False
    assert plan.reason == ("REPLACEMENT_ENTRY_INFEASIBLE_CAPACITY_UNAVAILABLE")
    assert positions == before
    assert positions["AAA-USDT"] is incumbent


def test_missing_incumbent_current_open_keeps_incumbent():
    incumbent = replay_position(
        pair="AAA-USDT",
        degraded_since="2022-01-02T00:00:00Z",
    )
    positions = {"AAA-USDT": incumbent}
    plan = plan_atomic_replacement(
        positions,
        cash=50000.0,
        incoming_prevalidated=True,
        free_slot_exists=False,
        target_slot_fraction=0.18,
        capacity_source=10_000_000.0,
        side_cost=0.00125,
        current_open_by_pair={},
    )
    assert plan.should_replace is False
    assert plan.reason == "INCUMBENT_CURRENT_OPEN_UNAVAILABLE"
    assert "AAA-USDT" in positions


def test_atomic_plan_is_immutable_description_only():
    positions = {
        "AAA-USDT": replay_position(
            pair="AAA-USDT",
            degraded_since="2022-01-02T00:00:00Z",
        )
    }
    plan = plan_atomic_replacement(
        positions,
        cash=50000.0,
        incoming_prevalidated=True,
        free_slot_exists=False,
        target_slot_fraction=0.18,
        capacity_source=10_000_000.0,
        side_cost=0.00125,
        current_open_by_pair={"AAA-USDT": 95.0},
    )
    assert isinstance(plan, AtomicReplacementPlan)
    assert isinstance(plan.sizing, EntrySizingDecision)
    assert "AAA-USDT" in positions


def test_control_delegates_exact_rd29_control(monkeypatch):
    sentinel = (
        pd.DataFrame({"x": [1]}),
        pd.DataFrame({"y": [2]}),
        {"policy_id": ROUTER_TIME_FAIL_72_CONTROL},
        {"sentinel": 1},
    )

    def fake_rd29(**kwargs):
        assert kwargs["policy_id"] == replay_module.RD29_CONTROL
        return sentinel

    monkeypatch.setattr(
        replay_module,
        "replay_rd29_policy",
        fake_rd29,
    )
    result = replay_rd30_policy(
        policy_id=ROUTER_TIME_FAIL_72_CONTROL,
        portfolio_id="UNION_FOCUS",
        universe_id="C2",
        cost_multiplier=1.0,
        events=pd.DataFrame(),
        frames={},
        state_frame=pd.DataFrame(),
        membership=[],
    )
    assert result is sentinel


def test_invalid_policy_rejected_before_replay():
    with pytest.raises(RD30ReplayError):
        replay_rd30_policy(
            policy_id="UNKNOWN",
            portfolio_id="UNION_FOCUS",
            universe_id="C2",
            cost_multiplier=1.0,
            events=pd.DataFrame(),
            frames={},
            state_frame=pd.DataFrame(),
            membership=[],
        )


def test_invalid_cost_rejected_before_replay():
    with pytest.raises(RD30ReplayError):
        replay_rd30_policy(
            policy_id=FAMILY_QUALITY_CONTROL_EXITS,
            portfolio_id="UNION_FOCUS",
            universe_id="C2",
            cost_multiplier=3.0,
            events=pd.DataFrame(),
            frames={},
            state_frame=pd.DataFrame(),
            membership=[],
        )


def test_contract_summary_freezes_atomic_semantics():
    summary = contract_summary()
    assert summary["replacement_requires_prevalidated_incoming"] is True
    assert summary["replacement_forbidden_when_free_slot_exists"] is True
    assert summary["replacement_planned_before_mutation"] is True
    assert summary["replacement_entry_sizing_uses_hypothetical_exit_credit"] is True
    assert summary["failed_replacement_plan_keeps_incumbent"] is True
    assert summary["mb_thesis_failure_exit"] is False
    assert summary["mb_replacement_degradation"] is False


def test_contract_summary_has_no_loader_or_economic_execution():
    summary = contract_summary()
    assert summary["economic_execution_performed"] is False
    assert summary["real_market_data_loader_present"] is False
    assert summary["2024_accessed"] is False
    assert summary["post_2024_accessed"] is False
    assert summary["production_authorized"] is False


def test_candidate_policy_ids_are_available():
    assert FAMILY_QUALITY_CONTROL_EXITS in replay_module.POLICIES
    assert FAMILY_QUALITY_REPLACEMENT_AWARE_RS in replay_module.POLICIES
    assert FULL_FAMILY_SPECIALIST_REPLACEMENT_BRAIN in replay_module.POLICIES


def test_specialist_classes_available_for_replay_diagnostics():
    mb = new_specialist_position(
        pair="MB-USDT",
        entry_time=pd.Timestamp("2022-01-01T00:00:00Z"),
        entry_price=100.0,
        atr24_at_signal=2.0,
        support_families=(FAMILY_MOMENTUM_BREAKOUT,),
    )
    rs = new_specialist_position(
        pair="RS-USDT",
        entry_time=pd.Timestamp("2022-01-01T00:00:00Z"),
        entry_price=100.0,
        atr24_at_signal=2.0,
        support_families=(FAMILY_RELATIVE_STRENGTH_ROTATION,),
    )
    assert mb.lifecycle_class == MB_SUPPORTED
    assert rs.lifecycle_class == RS_ONLY
