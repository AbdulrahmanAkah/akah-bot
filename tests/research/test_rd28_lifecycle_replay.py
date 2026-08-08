from __future__ import annotations

import numpy as np
import pandas as pd

import spotbot.research.rd28_lifecycle_replay as replay_module
from spotbot.research.rd26_exit_architecture import (
    FAMILY_MOMENTUM_BREAKOUT,
    FAMILY_RELATIVE_STRENGTH_ROTATION,
)
from spotbot.research.rd27_adaptive_lifecycle import RISK_OFF, RISK_ON, TRANSITION
from spotbot.research.rd28_evidence_gated_lifecycle import (
    EVIDENCE_GATED_LIFECYCLE_IMMEDIATE_RECYCLE,
    EVIDENCE_GATED_LIFECYCLE_SLOT_ESCROW,
    FAMILY_AWARE_EVIDENCE_LIFECYCLE_SLOT_ESCROW,
    ROUTER_TIME_FAIL_72_CONTROL,
    new_evidence_position,
)
from spotbot.research.rd28_lifecycle_replay import (
    FAMILY_OVERLAP_EXIT_REASON,
    FAMILY_OVERLAP_RULE,
    ReplayPosition,
    contract_summary,
    family_aware_exit_decision,
    replay_rd28_policy,
)

BASE = pd.Timestamp("2023-01-01T00:00:00Z")


def _frame(pair: str, *, hours: int = 240, weak_at_hour: int | None = None) -> pd.DataFrame:
    timestamps = pd.date_range(BASE, periods=hours, freq="h")
    close = np.full(hours, 105.0)
    if weak_at_hour is not None:
        close[weak_at_hour] = 99.0
    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": np.full(hours, 100.0),
            "high": np.full(hours, 106.0),
            "low": np.full(hours, 99.0),
            "close": close,
            "trailing_24h_quote_turnover_proxy": np.full(hours, 50_000_000.0),
            "pair": pair,
        }
    )


def _states(hours: int = 240) -> pd.DataFrame:
    timestamps = pd.date_range(BASE, periods=hours, freq="h")
    states = [RISK_ON if index <= 24 else TRANSITION for index in range(hours)]
    return pd.DataFrame(
        {"timestamp": timestamps, "market_state": states, "state_ready": [True] * hours}
    )


def _event(
    *, pair: str, signal_hour: int, rank: int, support: str = FAMILY_MOMENTUM_BREAKOUT
) -> dict[str, object]:
    return {
        "timestamp": BASE + pd.Timedelta(hours=signal_hour),
        "pair": pair,
        "membership_rank": rank,
        "support_families": support,
        "support_count": len(support.split("|")),
        "period_id": "SYNTHETIC",
        "atr24_at_signal": 2.0,
    }


def _position(*, support: tuple[str, ...]) -> ReplayPosition:
    evidence = new_evidence_position(
        pair="TEST-USDT",
        entry_time=BASE + pd.Timedelta(hours=2),
        entry_price=100.0,
        atr24_at_signal=2.0,
        entry_market_state=RISK_ON,
        signal_family=support[0],
    )
    return ReplayPosition(
        pair="TEST-USDT",
        signal_time=BASE + pd.Timedelta(hours=1),
        entry_time=BASE + pd.Timedelta(hours=2),
        max_exit_time=BASE + pd.Timedelta(hours=170),
        entry_price=100.0,
        quantity=1.0,
        entry_notional=100.0,
        entry_cost=0.0,
        membership_rank=1,
        support_families=support,
        period_id="SYNTHETIC",
        atr24_at_signal=2.0,
        evidence=evidence,
        entry_market_state=RISK_ON,
        last_mark=100.0,
    )


def test_overlap_rule_is_frozen() -> None:
    assert FAMILY_OVERLAP_RULE == "ALL_SUPPORTING_FAMILIES_MUST_INVALIDATE"


def test_overlap_survives_when_only_rs_invalidates() -> None:
    position = _position(support=(FAMILY_MOMENTUM_BREAKOUT, FAMILY_RELATIVE_STRENGTH_ROTATION))
    decision = family_aware_exit_decision(
        position,
        current_open_time=BASE + pd.Timedelta(hours=26),
        current_open=99.0,
        prior_asset_close=99.0,
        current_market_state=TRANSITION,
    )
    assert decision.should_exit is False


def test_overlap_exits_when_all_supporting_families_invalidate() -> None:
    position = _position(support=(FAMILY_MOMENTUM_BREAKOUT, FAMILY_RELATIVE_STRENGTH_ROTATION))
    decision = family_aware_exit_decision(
        position,
        current_open_time=BASE + pd.Timedelta(hours=26),
        current_open=98.0,
        prior_asset_close=99.0,
        current_market_state=RISK_OFF,
    )
    assert decision.should_exit is True
    assert decision.exit_reason == FAMILY_OVERLAP_EXIT_REASON


def test_control_delegates_exactly_to_rd27_static_router(monkeypatch) -> None:
    captured = {}

    def fake_delegate(**kwargs):
        captured.update(kwargs)
        return pd.DataFrame(), pd.DataFrame(), {"net_return": 0.0}, {"admitted_entries": 1}

    monkeypatch.setattr(replay_module, "rd27_replay_lifecycle_policy", fake_delegate)
    result = replay_rd28_policy(
        policy_id=ROUTER_TIME_FAIL_72_CONTROL,
        portfolio_id="UNION_FOCUS",
        universe_id="C2",
        cost_multiplier=1.0,
        events=pd.DataFrame(),
        frames={},
        state_frame=pd.DataFrame(),
        replay_start=BASE,
        replay_cutoff=BASE + pd.Timedelta(hours=200),
    )
    assert captured["policy_id"] == replay_module.STATIC_EXIT_STATE_ROUTER
    assert captured["replay_start"] == BASE
    assert captured["replay_cutoff"] == BASE + pd.Timedelta(hours=200)
    assert result[2]["net_return"] == 0.0


def test_slot_escrow_blocks_same_hour_recycle_at_full_slot_budget() -> None:
    pairs = [f"P{index}-USDT" for index in range(6)]
    frames = {
        pair: _frame(pair, weak_at_hour=25 if index == 0 else None)
        for index, pair in enumerate(pairs)
    }
    events = pd.DataFrame(
        [
            *[
                _event(pair=pair, signal_hour=1, rank=index + 1)
                for index, pair in enumerate(pairs[:5])
            ],
            _event(
                pair=pairs[5], signal_hour=25, rank=1, support=FAMILY_RELATIVE_STRENGTH_ROTATION
            ),
        ]
    )
    kwargs = dict(
        portfolio_id="UNION_FOCUS",
        universe_id="C2",
        cost_multiplier=1.0,
        events=events,
        frames=frames,
        state_frame=_states(),
        replay_start=BASE,
        replay_cutoff=BASE + pd.Timedelta(hours=230),
    )
    immediate = replay_rd28_policy(policy_id=EVIDENCE_GATED_LIFECYCLE_IMMEDIATE_RECYCLE, **kwargs)
    escrow = replay_rd28_policy(policy_id=EVIDENCE_GATED_LIFECYCLE_SLOT_ESCROW, **kwargs)
    assert immediate[3]["admitted_entries"] == 6
    assert escrow[3]["admitted_entries"] == 5
    assert escrow[3]["escrow_slot_rejections"] >= 1
    assert escrow[3]["escrow_slots_created"] >= 1


def test_generic_evidence_exit_occurs_no_earlier_than_24h() -> None:
    pair = "ONE-USDT"
    trades, _, _, counters = replay_rd28_policy(
        policy_id=EVIDENCE_GATED_LIFECYCLE_IMMEDIATE_RECYCLE,
        portfolio_id="UNION_FOCUS",
        universe_id="C2",
        cost_multiplier=1.0,
        events=pd.DataFrame([_event(pair=pair, signal_hour=1, rank=1)]),
        frames={pair: _frame(pair, weak_at_hour=25)},
        state_frame=_states(),
        replay_start=BASE,
        replay_cutoff=BASE + pd.Timedelta(hours=220),
    )
    assert counters["admitted_entries"] == 1
    assert len(trades) == 1
    assert int(trades.iloc[0]["holding_hours"]) >= 24
    assert trades.iloc[0]["exit_reason"] == "EVIDENCE_GATED_REGIME_TRADE_INVALIDATION"


def test_family_aware_mb_does_not_exit_on_transition() -> None:
    position = _position(support=(FAMILY_MOMENTUM_BREAKOUT,))
    decision = family_aware_exit_decision(
        position,
        current_open_time=BASE + pd.Timedelta(hours=26),
        current_open=99.0,
        prior_asset_close=99.0,
        current_market_state=TRANSITION,
    )
    assert decision.should_exit is False


def test_contract_summary_is_pre_economic() -> None:
    summary = contract_summary()
    assert summary["control_delegate"] == "RD27_STATIC_EXIT_STATE_ROUTER"
    assert summary["router"] == "EXACT_RD27_P0B_STATE_ROUTER"
    assert summary["family_overlap_rule"] == FAMILY_OVERLAP_RULE
    assert summary["slot_escrow_counts_toward_maximum_positions"] is True
    assert summary["slot_escrow_reserves_cash"] is False
    assert summary["slot_escrow_reserves_notional"] is False
    assert summary["signal_generation_changed"] is False
    assert summary["economic_execution_performed"] is False
    assert summary["real_market_data_loader_present"] is False
    assert FAMILY_AWARE_EVIDENCE_LIFECYCLE_SLOT_ESCROW in summary["policies"]
