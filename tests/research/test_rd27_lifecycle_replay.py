from __future__ import annotations

import pandas as pd

from spotbot.research.rd26_exit_architecture import (
    DATA_CUTOFF,
    DATA_START,
    FAMILY_MOMENTUM_BREAKOUT,
    POLICY_TIME_FAIL,
)
from spotbot.research.rd26_exit_architecture import (
    replay_policy as rd26_replay_policy,
)
from spotbot.research.rd27_adaptive_lifecycle import RISK_OFF, RISK_ON, TRANSITION
from spotbot.research.rd27_lifecycle_replay import (
    ADAPTIVE_EXIT_FIXED_CAPITAL,
    CONTROL_TIME_FAIL_72_FIXED_CAPITAL,
    FULL_ADAPTIVE_LIFECYCLE_BRAIN,
    STATIC_EXIT_STATE_ROUTER,
    active_component_count,
    replay_lifecycle_policy,
)


def asset_frame(
    overrides: dict[int, dict[str, float]] | None = None,
    *,
    hours: int = 200,
) -> pd.DataFrame:
    overrides = overrides or {}
    rows = []
    for hour in range(hours):
        values = {
            "timestamp": DATA_START + pd.Timedelta(hours=hour),
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.0,
            "volume": 1_000_000.0,
            "trailing_24h_quote_turnover_proxy": 100_000_000.0,
        }
        values.update(overrides.get(hour, {}))
        rows.append(values)
    return pd.DataFrame(rows)


def state_frame(state: str, *, hours: int = 200) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": [
                DATA_START + pd.Timedelta(hours=hour)
                for hour in range(hours)
            ],
            "market_state": [state] * hours,
            "state_ready": [True] * hours,
        }
    )


def event() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "timestamp": DATA_START,
                "pair": "AAA-USDT",
                "membership_rank": 1,
                "period_id": "ROBUSTNESS_2022",
                "support_families": FAMILY_MOMENTUM_BREAKOUT,
                "atr24_at_signal": 1.0,
            }
        ]
    )


def run_short(
    policy: str,
    state: str,
    *,
    overrides: dict[int, dict[str, float]] | None = None,
):
    return replay_lifecycle_policy(
        policy_id=policy,
        portfolio_id="TEST",
        universe_id="C2",
        cost_multiplier=1.0,
        events=event(),
        frames={"AAA-USDT": asset_frame(overrides)},
        state_frame=state_frame(state),
        replay_start=DATA_START,
        replay_cutoff=DATA_START + pd.Timedelta(hours=180),
    )


def test_component_registry_matches_preregistered_two_by_two() -> None:
    assert active_component_count(CONTROL_TIME_FAIL_72_FIXED_CAPITAL) == 0
    assert active_component_count(ADAPTIVE_EXIT_FIXED_CAPITAL) == 1
    assert active_component_count(STATIC_EXIT_STATE_ROUTER) == 1
    assert active_component_count(FULL_ADAPTIVE_LIFECYCLE_BRAIN) == 2


def test_static_router_risk_off_records_but_suppresses_admission() -> None:
    trades, _daily, metrics, counters = run_short(
        STATIC_EXIT_STATE_ROUTER,
        RISK_OFF,
    )
    assert trades.empty
    assert metrics["trade_count"] == 0
    assert counters["signal_events"] == 1
    assert counters["risk_off_suppressed_entries"] == 1
    assert counters["admitted_entries"] == 0


def test_full_brain_risk_off_suppresses_admission() -> None:
    trades, _daily, _metrics, counters = run_short(
        FULL_ADAPTIVE_LIFECYCLE_BRAIN,
        RISK_OFF,
    )
    assert trades.empty
    assert counters["risk_off_suppressed_entries"] == 1


def test_adaptive_exit_fixed_capital_still_admits_in_risk_off() -> None:
    trades, _daily, _metrics, counters = run_short(
        ADAPTIVE_EXIT_FIXED_CAPITAL,
        RISK_OFF,
    )
    assert len(trades) == 1
    assert counters["admitted_entries"] == 1
    assert counters["risk_off_suppressed_entries"] == 0
    assert trades.iloc[0]["exit_reason"] == (
        "ADAPTIVE_STAGNATION_24H_CLOSE_NOT_ABOVE_ENTRY"
    )


def test_transition_router_uses_half_slot_notional() -> None:
    trades, _daily, _metrics, counters = run_short(
        STATIC_EXIT_STATE_ROUTER,
        TRANSITION,
    )
    assert len(trades) == 1
    assert counters["admitted_entries"] == 1
    assert abs(float(trades.iloc[0]["entry_notional"]) - 9_000.0) < 1e-9


def test_adaptive_adverse_guard_is_active_on_entry_bar() -> None:
    trades, _daily, _metrics, counters = run_short(
        ADAPTIVE_EXIT_FIXED_CAPITAL,
        RISK_ON,
        overrides={1: {"low": 94.0}},
    )
    assert len(trades) == 1
    row = trades.iloc[0]
    assert row["holding_hours"] == 0
    assert row["exit_reason"] == "ADAPTIVE_PROTECTION_TOUCH"
    assert abs(float(row["exit_price"]) - 95.0) < 1e-12
    assert counters["entry_bar_adaptive_exits"] == 1


def test_adaptive_trail_uses_completed_prior_bar_high() -> None:
    overrides = {
        1: {"open": 100.0, "high": 110.0, "low": 99.0, "close": 109.0},
        2: {"open": 109.0, "high": 109.0, "low": 105.0, "close": 105.5},
    }
    trades, _daily, _metrics, _counters = run_short(
        ADAPTIVE_EXIT_FIXED_CAPITAL,
        RISK_ON,
        overrides=overrides,
    )
    row = trades.iloc[0]
    assert row["holding_hours"] == 1
    assert row["exit_reason"] == "ADAPTIVE_PROTECTION_TOUCH"
    assert abs(float(row["exit_price"]) - 106.0) < 1e-12


def test_static_router_preserves_time_fail_72_exit() -> None:
    trades, _daily, _metrics, counters = run_short(
        STATIC_EXIT_STATE_ROUTER,
        RISK_ON,
    )
    row = trades.iloc[0]
    assert row["holding_hours"] == 72
    assert row["exit_reason"] == "TIME_FAILURE_72H_CLOSE_NOT_ABOVE_ENTRY"
    assert counters["time_failure_exits"] == 1


def test_control_delegates_exactly_to_rd26_time_fail() -> None:
    frames = {"AAA-USDT": asset_frame()}
    direct_trades, _direct_daily, direct_metrics, _direct_counters = rd26_replay_policy(
        policy_id=POLICY_TIME_FAIL,
        portfolio_id="TEST",
        universe_id="C2",
        cost_multiplier=1.0,
        events=event(),
        frames=frames,
    )
    trades, _daily, metrics, _counters = replay_lifecycle_policy(
        policy_id=CONTROL_TIME_FAIL_72_FIXED_CAPITAL,
        portfolio_id="TEST",
        universe_id="C2",
        cost_multiplier=1.0,
        events=event(),
        frames=frames,
        state_frame=state_frame(RISK_ON),
        replay_start=DATA_START,
        replay_cutoff=DATA_CUTOFF,
    )
    assert len(trades) == len(direct_trades) == 1
    assert trades.iloc[0]["exit_time"] == direct_trades.iloc[0]["exit_time"]
    assert trades.iloc[0]["exit_price"] == direct_trades.iloc[0]["exit_price"]
    assert trades.iloc[0]["net_pnl"] == direct_trades.iloc[0]["net_pnl"]
    assert metrics["net_return"] == direct_metrics["net_return"]
    assert metrics["maximum_drawdown"] == direct_metrics["maximum_drawdown"]
