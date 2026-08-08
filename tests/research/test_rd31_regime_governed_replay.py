from __future__ import annotations

import pandas as pd
import pytest

import spotbot.research.rd31_regime_governed_replay as replay_module
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
    MarketContextDecision,
)
from spotbot.research.rd31_regime_admission_governor import (
    CAUTION,
    FAMILY_QUALITY_CONTROL_EXITS,
    LOCKED,
    OPEN,
    REGIME_HYSTERESIS_ADMISSION_GOVERNOR,
    STRESSED_CONTEXT_MB_EXCLUSION,
    SUPPORTIVE_ONLY_ALL_FAMILIES,
)
from spotbot.research.rd31_regime_governed_replay import (
    RD31ReplayError,
    apply_entry_policy,
    contract_summary,
    family_bucket,
    replay_rd31_policy,
)


def context(
    btc_state: str,
    value: str,
    *,
    breadth_positive: bool,
) -> MarketContextDecision:
    return MarketContextDecision(
        btc_state=btc_state,
        breadth_ready=True,
        breadth_median_return_72h=(0.05 if breadth_positive else -0.05),
        breadth_positive=breadth_positive,
        context=value,
        member_count=3,
        observed_member_count=3,
    )


def supportive() -> MarketContextDecision:
    return context(
        RISK_ON,
        SUPPORTIVE,
        breadth_positive=True,
    )


def mixed() -> MarketContextDecision:
    return context(
        TRANSITION,
        MIXED,
        breadth_positive=True,
    )


def stressed() -> MarketContextDecision:
    return context(
        TRANSITION,
        STRESSED,
        breadth_positive=False,
    )


def test_family_bucket_mb():
    assert family_bucket((FAMILY_MOMENTUM_BREAKOUT,)) == "MB"


def test_family_bucket_rs():
    assert family_bucket((FAMILY_RELATIVE_STRENGTH_ROTATION,)) == "RS"


def test_family_bucket_overlap():
    assert (
        family_bucket(
            (
                FAMILY_MOMENTUM_BREAKOUT,
                FAMILY_RELATIVE_STRENGTH_ROTATION,
            )
        )
        == "OVERLAP"
    )


def test_family_bucket_rejects_unknown():
    with pytest.raises(RD31ReplayError):
        family_bucket(("UNKNOWN",))


def test_static_baseline_does_not_mutate_governor_state():
    governed, next_state = apply_entry_policy(
        policy_id=FAMILY_QUALITY_CONTROL_EXITS,
        support_families=(FAMILY_MOMENTUM_BREAKOUT,),
        btc_state=RISK_ON,
        market_context=supportive(),
        governor_state=None,
    )
    assert governed.decision.admit_position is True
    assert next_state is None


def test_stressed_mb_exclusion_static_policy_has_no_governor():
    governed, next_state = apply_entry_policy(
        policy_id=STRESSED_CONTEXT_MB_EXCLUSION,
        support_families=(FAMILY_MOMENTUM_BREAKOUT,),
        btc_state=TRANSITION,
        market_context=stressed(),
        governor_state=None,
    )
    assert governed.decision.admit_position is False
    assert next_state is None


def test_supportive_only_static_policy_has_no_governor():
    governed, next_state = apply_entry_policy(
        policy_id=SUPPORTIVE_ONLY_ALL_FAMILIES,
        support_families=(FAMILY_RELATIVE_STRENGTH_ROTATION,),
        btc_state=RISK_ON,
        market_context=supportive(),
        governor_state=None,
    )
    assert governed.decision.admit_position is True
    assert next_state is None


def test_hysteresis_requires_valid_state():
    with pytest.raises(RD31ReplayError):
        apply_entry_policy(
            policy_id=REGIME_HYSTERESIS_ADMISSION_GOVERNOR,
            support_families=(FAMILY_MOMENTUM_BREAKOUT,),
            btc_state=RISK_ON,
            market_context=supportive(),
            governor_state=None,
        )


def test_hysteresis_stressed_locks_before_admission():
    governed, next_state = apply_entry_policy(
        policy_id=REGIME_HYSTERESIS_ADMISSION_GOVERNOR,
        support_families=(FAMILY_MOMENTUM_BREAKOUT,),
        btc_state=TRANSITION,
        market_context=stressed(),
        governor_state=OPEN,
    )
    assert next_state == LOCKED
    assert governed.decision.admit_position is False


def test_hysteresis_locked_mixed_stays_locked():
    governed, next_state = apply_entry_policy(
        policy_id=REGIME_HYSTERESIS_ADMISSION_GOVERNOR,
        support_families=(FAMILY_MOMENTUM_BREAKOUT,),
        btc_state=TRANSITION,
        market_context=mixed(),
        governor_state=LOCKED,
    )
    assert next_state == LOCKED
    assert governed.decision.admit_position is False


def test_hysteresis_locked_supportive_reopens():
    governed, next_state = apply_entry_policy(
        policy_id=REGIME_HYSTERESIS_ADMISSION_GOVERNOR,
        support_families=(FAMILY_MOMENTUM_BREAKOUT,),
        btc_state=RISK_ON,
        market_context=supportive(),
        governor_state=LOCKED,
    )
    assert next_state == OPEN
    assert governed.decision.admit_position is True


def test_hysteresis_same_timestamp_mixed_is_idempotent_after_first_transition():
    first, state = apply_entry_policy(
        policy_id=REGIME_HYSTERESIS_ADMISSION_GOVERNOR,
        support_families=(FAMILY_MOMENTUM_BREAKOUT,),
        btc_state=TRANSITION,
        market_context=mixed(),
        governor_state=OPEN,
    )
    second, state2 = apply_entry_policy(
        policy_id=REGIME_HYSTERESIS_ADMISSION_GOVERNOR,
        support_families=(FAMILY_MOMENTUM_BREAKOUT,),
        btc_state=TRANSITION,
        market_context=mixed(),
        governor_state=state,
    )
    assert first.governor_next_state == CAUTION
    assert state == CAUTION
    assert second.governor_next_state == CAUTION
    assert state2 == CAUTION


def test_hysteresis_same_timestamp_supportive_stays_open():
    _, state = apply_entry_policy(
        policy_id=REGIME_HYSTERESIS_ADMISSION_GOVERNOR,
        support_families=(FAMILY_MOMENTUM_BREAKOUT,),
        btc_state=RISK_ON,
        market_context=supportive(),
        governor_state=OPEN,
    )
    _, state2 = apply_entry_policy(
        policy_id=REGIME_HYSTERESIS_ADMISSION_GOVERNOR,
        support_families=(FAMILY_RELATIVE_STRENGTH_ROTATION,),
        btc_state=RISK_ON,
        market_context=supportive(),
        governor_state=state,
    )
    assert state == OPEN
    assert state2 == OPEN


def test_baseline_replay_delegates_exact_rd30(monkeypatch):
    sentinel = (
        pd.DataFrame({"trade": [1]}),
        pd.DataFrame({"equity": [1]}),
        {"policy_id": FAMILY_QUALITY_CONTROL_EXITS},
        {"family_quality_suppressed_entries": 7},
    )

    def fake_rd30(**kwargs):
        assert kwargs["policy_id"] == FAMILY_QUALITY_CONTROL_EXITS
        return sentinel

    monkeypatch.setattr(
        replay_module,
        "replay_rd30_policy",
        fake_rd30,
    )
    trades, daily, metrics, counters = replay_rd31_policy(
        policy_id=FAMILY_QUALITY_CONTROL_EXITS,
        portfolio_id="UNION_FOCUS",
        universe_id="C2",
        cost_multiplier=1.0,
        events=pd.DataFrame(),
        frames={},
        state_frame=pd.DataFrame(),
        membership=[],
    )
    assert trades is sentinel[0]
    assert daily is sentinel[1]
    assert metrics is sentinel[2]
    assert counters["suppressed_entries"] == 7


def test_invalid_policy_rejected_before_replay():
    with pytest.raises(RD31ReplayError):
        replay_rd31_policy(
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
    with pytest.raises(RD31ReplayError):
        replay_rd31_policy(
            policy_id=STRESSED_CONTEXT_MB_EXCLUSION,
            portfolio_id="UNION_FOCUS",
            universe_id="C2",
            cost_multiplier=3.0,
            events=pd.DataFrame(),
            frames={},
            state_frame=pd.DataFrame(),
            membership=[],
        )


def test_contract_freezes_baseline_delegate_and_lifecycle():
    summary = contract_summary()
    assert summary["baseline_delegate"] == ("EXACT_RD30_FAMILY_QUALITY_CONTROL_EXITS")
    assert summary["candidate_lifecycle"] == (
        "EXACT_RD30_TIME_FAIL72_MAX168_NO_PROFIT_NO_REPLACEMENT"
    )
    assert summary["governor_update"] == ("AT_SIGNAL_TIME_BEFORE_ADMISSION")
    assert summary["governor_initial_state"] == OPEN


def test_contract_forbids_rejected_rd30_components():
    summary = contract_summary()
    assert summary["profit_giveback"] is False
    assert summary["replacement"] is False
    assert summary["thesis_failure_exit"] is False
    assert summary["forced_regime_exit"] is False


def test_contract_firewalls():
    summary = contract_summary()
    assert summary["parameter_grid_search"] is False
    assert summary["calendar_year_feature"] is False
    assert summary["economic_execution_performed"] is False
    assert summary["real_market_data_loader_present"] is False
    assert summary["2024_accessed"] is False
    assert summary["post_2024_accessed"] is False
    assert summary["production_authorized"] is False
