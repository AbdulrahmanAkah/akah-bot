from __future__ import annotations

import pandas as pd
import pytest

import spotbot.research.rd29_thesis_replay as replay_module
from spotbot.research.rd20_p2_minimal_pullback import MembershipSnapshot
from spotbot.research.rd26_exit_architecture import (
    FAMILY_MOMENTUM_BREAKOUT,
    FAMILY_RELATIVE_STRENGTH_ROTATION,
    fast_lookup,
)
from spotbot.research.rd27_adaptive_lifecycle import RISK_ON, TRANSITION
from spotbot.research.rd29_thesis_context import (
    FULL_FAMILY_QUALITY_THESIS_BRAIN,
    ROUTER_TIME_FAIL_72_CONTROL,
    SUPPORTIVE,
    THESIS_CONFIDENCE_LIFECYCLE,
)
from spotbot.research.rd29_thesis_replay import (
    causal_context_at,
    contract_summary,
    entry_context_for_event,
    membership_at,
    replay_rd29_policy,
)

BASE = pd.Timestamp("2023-01-01T00:00:00Z")
PAIRS = (
    "AAA-USDT",
    "BBB-USDT",
    "CCC-USDT",
    "DDD-USDT",
    "EEE-USDT",
    "FFF-USDT",
)


def membership():
    return [
        MembershipSnapshot(
            universe_id="C2",
            decision_time=BASE,
            effective_end=BASE + pd.Timedelta(hours=300),
            members=tuple((pair, index + 1) for index, pair in enumerate(PAIRS)),
        )
    ]


def frame(
    pair: str,
    *,
    hours: int = 240,
    return_value: float = 0.10,
):
    timestamps = pd.date_range(BASE, periods=hours, freq="h")
    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": [100.0] * hours,
            "high": [106.0] * hours,
            "low": [99.0] * hours,
            "close": [105.0] * hours,
            "return_72h": [return_value] * hours,
            "prior_72h_high": [98.0] * hours,
            "trailing_24h_quote_turnover_proxy": [50_000_000.0] * hours,
            "pair": [pair] * hours,
        }
    )


def frames():
    values = {
        "AAA-USDT": 0.30,
        "BBB-USDT": 0.20,
        "CCC-USDT": 0.10,
        "DDD-USDT": 0.05,
        "EEE-USDT": 0.01,
        "FFF-USDT": -0.02,
    }
    return {pair: frame(pair, return_value=values[pair]) for pair in PAIRS}


def state_frame(state=RISK_ON, *, hours: int = 240):
    return pd.DataFrame(
        {
            "timestamp": pd.date_range(BASE, periods=hours, freq="h"),
            "market_state": [state] * hours,
            "state_ready": [True] * hours,
        }
    )


def event(
    *,
    signal_hour: int = 1,
    support: str = FAMILY_MOMENTUM_BREAKOUT,
):
    return pd.DataFrame(
        [
            {
                "timestamp": BASE + pd.Timedelta(hours=signal_hour),
                "pair": "AAA-USDT",
                "membership_rank": 1,
                "period_id": "SYNTHETIC",
                "support_families": support,
                "support_count": len(support.split("|")),
                "atr24_at_signal": 2.0,
            }
        ]
    )


def test_membership_boundary_is_causal():
    snapshots = [
        MembershipSnapshot(
            universe_id="C2",
            decision_time=BASE,
            effective_end=BASE + pd.Timedelta(hours=10),
            members=(("AAA-USDT", 1),),
        ),
        MembershipSnapshot(
            universe_id="C2",
            decision_time=BASE + pd.Timedelta(hours=10),
            effective_end=BASE + pd.Timedelta(hours=20),
            members=(("BBB-USDT", 1),),
        ),
    ]
    before = membership_at(
        snapshots,
        universe_id="C2",
        timestamp=BASE + pd.Timedelta(hours=9),
    )
    boundary = membership_at(
        snapshots,
        universe_id="C2",
        timestamp=BASE + pd.Timedelta(hours=10),
    )
    assert before == (("AAA-USDT", 1),)
    assert boundary == (("BBB-USDT", 1),)


def test_context_uses_named_completed_cutoff():
    current_frames = frames()
    lookups = {pair: fast_lookup(value) for pair, value in current_frames.items()}
    state_lookup = {
        int((BASE + pd.Timedelta(hours=5)).value): RISK_ON,
    }
    members, returns, state, context = causal_context_at(
        universe_id="C2",
        completed_time=BASE + pd.Timedelta(hours=5),
        membership=membership(),
        frames=current_frames,
        lookups=lookups,
        state_lookup=state_lookup,
    )
    assert len(members) == 6
    assert returns["AAA-USDT"] == pytest.approx(0.30)
    assert state == RISK_ON
    assert context.context == SUPPORTIVE


def test_mb_reference_recovered_from_signal_bar():
    current_frames = frames()
    lookups = {pair: fast_lookup(value) for pair, value in current_frames.items()}
    state_lookup = {
        int((BASE + pd.Timedelta(hours=1)).value): RISK_ON,
    }
    result = entry_context_for_event(
        universe_id="C2",
        signal_time=BASE + pd.Timedelta(hours=1),
        support_families=(FAMILY_MOMENTUM_BREAKOUT,),
        pair="AAA-USDT",
        membership=membership(),
        frames=current_frames,
        lookups=lookups,
        state_lookup=state_lookup,
    )
    assert result[4] == pytest.approx(98.0)


def test_rs_only_entry_has_no_mb_reference():
    current_frames = frames()
    lookups = {pair: fast_lookup(value) for pair, value in current_frames.items()}
    state_lookup = {
        int((BASE + pd.Timedelta(hours=1)).value): RISK_ON,
    }
    result = entry_context_for_event(
        universe_id="C2",
        signal_time=BASE + pd.Timedelta(hours=1),
        support_families=(FAMILY_RELATIVE_STRENGTH_ROTATION,),
        pair="AAA-USDT",
        membership=membership(),
        frames=current_frames,
        lookups=lookups,
        state_lookup=state_lookup,
    )
    assert result[4] is None


def test_control_delegates_and_only_normalizes_label(monkeypatch):
    def fake(**kwargs):
        assert kwargs["policy_id"] == replay_module.RD28_CONTROL
        return (
            pd.DataFrame(
                [
                    {
                        "policy_id": "STATIC_EXIT_STATE_ROUTER",
                        "net_pnl": 7.0,
                    }
                ]
            ),
            pd.DataFrame(
                [
                    {
                        "policy_id": "STATIC_EXIT_STATE_ROUTER",
                        "equity": 101.0,
                    }
                ]
            ),
            {
                "policy_id": "STATIC_EXIT_STATE_ROUTER",
                "net_return": 0.01,
            },
            {"admitted_entries": 1},
        )

    monkeypatch.setattr(replay_module, "rd28_replay_policy", fake)
    trades, daily, metrics, counters = replay_rd29_policy(
        policy_id=ROUTER_TIME_FAIL_72_CONTROL,
        portfolio_id="UNION_FOCUS",
        universe_id="C2",
        cost_multiplier=1.0,
        events=pd.DataFrame(),
        frames={},
        state_frame=pd.DataFrame(),
        membership=[],
        replay_start=BASE,
        replay_cutoff=BASE + pd.Timedelta(hours=200),
    )
    assert trades.iloc[0]["net_pnl"] == 7.0
    assert daily.iloc[0]["equity"] == 101.0
    assert metrics["net_return"] == 0.01
    assert counters == {"admitted_entries": 1}
    assert set(trades["policy_id"]) == {ROUTER_TIME_FAIL_72_CONTROL}
    assert metrics["policy_id"] == ROUTER_TIME_FAIL_72_CONTROL


def test_candidate_replay_runs_to_max_hold():
    trades, _daily, metrics, counters = replay_rd29_policy(
        policy_id=THESIS_CONFIDENCE_LIFECYCLE,
        portfolio_id="UNION_FOCUS",
        universe_id="C2",
        cost_multiplier=1.0,
        events=event(),
        frames=frames(),
        state_frame=state_frame(),
        membership=membership(),
        replay_start=BASE,
        replay_cutoff=BASE + pd.Timedelta(hours=220),
    )
    assert counters["admitted_entries"] == 1
    assert len(trades) == 1
    assert trades.iloc[0]["holding_hours"] == 168
    assert trades.iloc[0]["exit_reason"] == "MAX_HOLD_168H"
    assert trades.iloc[0]["mb_breakout_reference"] == pytest.approx(98.0)
    assert metrics["trade_count"] == 1


def test_full_family_quality_suppresses_rs_in_transition():
    trades, _daily, metrics, counters = replay_rd29_policy(
        policy_id=FULL_FAMILY_QUALITY_THESIS_BRAIN,
        portfolio_id=FAMILY_RELATIVE_STRENGTH_ROTATION,
        universe_id="C2",
        cost_multiplier=1.0,
        events=event(support=FAMILY_RELATIVE_STRENGTH_ROTATION),
        frames=frames(),
        state_frame=state_frame(TRANSITION),
        membership=membership(),
        replay_start=BASE,
        replay_cutoff=BASE + pd.Timedelta(hours=220),
    )
    assert counters["admitted_entries"] == 0
    assert counters["family_quality_suppressed_entries"] == 1
    assert len(trades) == 0
    assert metrics["trade_count"] == 0


def test_overlap_preserves_support_and_recovers_mb_reference():
    support = f"{FAMILY_MOMENTUM_BREAKOUT}|{FAMILY_RELATIVE_STRENGTH_ROTATION}"
    trades, _daily, _metrics, counters = replay_rd29_policy(
        policy_id=THESIS_CONFIDENCE_LIFECYCLE,
        portfolio_id="UNION_FOCUS",
        universe_id="C2",
        cost_multiplier=1.0,
        events=event(support=support),
        frames=frames(),
        state_frame=state_frame(),
        membership=membership(),
        replay_start=BASE,
        replay_cutoff=BASE + pd.Timedelta(hours=220),
    )
    assert counters["admitted_entries"] == 1
    assert trades.iloc[0]["support_count"] == 2
    assert trades.iloc[0]["mb_breakout_reference"] == pytest.approx(98.0)


def test_contract_is_pre_economic_and_no_global_escrow():
    summary = contract_summary()
    assert summary["control_delegate"] == "RD28_ROUTER_TIME_FAIL_72_CONTROL"
    assert summary["control_economics_changed"] is False
    assert summary["entry_context_cutoff"] == "SIGNAL_BAR_CLOSE"
    assert summary["open_position_context_cutoff"] == "PRIOR_COMPLETED_HOUR"
    assert summary["mb_reference_source"] == "SIGNAL_BAR_PRIOR_72H_HIGH"
    assert summary["global_slot_escrow"] is False
    assert summary["same_pair_cooldown_only"] is True
    assert summary["economic_execution_performed"] is False
    assert summary["real_market_data_loader_present"] is False
