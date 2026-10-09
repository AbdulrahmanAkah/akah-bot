from __future__ import annotations

import pandas as pd
import pandas.testing as pdt

from spotbot.research import rd27_adaptive_lifecycle as lifecycle
from spotbot.research import rd27_lifecycle_replay as rd27
from spotbot.research.a4r1_reversible_floor_replay import (
    TREATMENT_POLICY_ID,
    replay_reversible_floor_candidate,
)
from spotbot.research.rd26_exit_architecture import (
    DATA_START,
    FAMILY_MOMENTUM_BREAKOUT,
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
            "close": 100.5,
            "volume": 1_000_000.0,
            "trailing_24h_quote_turnover_proxy": 100_000_000.0,
        }
        values.update(overrides.get(hour, {}))
        rows.append(values)
    return pd.DataFrame(rows)


def state_frame(states: list[str], *, hours: int = 200) -> pd.DataFrame:
    filled = states + [states[-1]] * max(0, hours - len(states))
    return pd.DataFrame(
        {
            "timestamp": [DATA_START + pd.Timedelta(hours=hour) for hour in range(hours)],
            "market_state": filled[:hours],
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


def run_control_and_treatment(
    states: list[str],
    *,
    overrides: dict[int, dict[str, float]] | None = None,
):
    frames = {"AAA-USDT": asset_frame(overrides)}
    states_frame = state_frame(states)
    kwargs = dict(
        portfolio_id="TEST",
        universe_id="C2",
        cost_multiplier=1.0,
        events=event(),
        frames=frames,
        state_frame=states_frame,
        replay_start=DATA_START,
        replay_cutoff=DATA_START + pd.Timedelta(hours=180),
    )
    control = rd27.replay_lifecycle_policy(
        policy_id=rd27.FULL_ADAPTIVE_LIFECYCLE_BRAIN,
        **kwargs,
    )
    treatment = replay_reversible_floor_candidate(**kwargs)
    return control, treatment


def test_exact_parity_when_reversible_carry_never_activates() -> None:
    control, treatment = run_control_and_treatment([lifecycle.TRANSITION, lifecycle.TRANSITION])
    control_trades, control_daily, control_metrics, control_counters = control

    t_trades = treatment.trades.copy()
    t_daily = treatment.daily.copy()
    if len(t_trades):
        t_trades["policy_id"] = rd27.FULL_ADAPTIVE_LIFECYCLE_BRAIN
    if len(t_daily):
        t_daily["policy_id"] = rd27.FULL_ADAPTIVE_LIFECYCLE_BRAIN
    t_metrics = dict(treatment.metrics)
    t_metrics["policy_id"] = rd27.FULL_ADAPTIVE_LIFECYCLE_BRAIN

    pdt.assert_frame_equal(
        control_trades.reset_index(drop=True),
        t_trades.reset_index(drop=True),
        check_dtype=False,
    )
    pdt.assert_frame_equal(
        control_daily.reset_index(drop=True),
        t_daily.reset_index(drop=True),
        check_dtype=False,
    )
    assert control_metrics == t_metrics
    assert control_counters == treatment.counters
    assert treatment.diagnostics["floor_relaxation_event_count"] == 0
    assert treatment.diagnostics["patch_restored"] is True


def test_improving_transition_can_preserve_trade_control_exits() -> None:
    overrides = {
        1: {
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.5,
        },
        2: {
            "open": 100.0,
            "high": 101.0,
            "low": 95.5,
            "close": 100.5,
        },
    }
    control, treatment = run_control_and_treatment(
        [lifecycle.TRANSITION, lifecycle.RISK_ON],
        overrides=overrides,
    )
    control_trades = control[0]
    assert len(control_trades) == 1
    assert int(control_trades.iloc[0]["holding_hours"]) == 1
    assert control_trades.iloc[0]["exit_reason"] == "ADAPTIVE_PROTECTION_TOUCH"

    assert treatment.diagnostics["floor_relaxation_event_count"] >= 1
    assert treatment.diagnostics["floor_relaxation_total_magnitude"] > 0.0
    assert treatment.metrics["policy_id"] == TREATMENT_POLICY_ID
    assert treatment.diagnostics["patch_restored"] is True


def test_patch_is_restored_after_replay() -> None:
    original_eval = rd27.evaluate_adaptive_exit
    original_update = rd27.apply_completed_bar_update
    _control, treatment = run_control_and_treatment([lifecycle.TRANSITION, lifecycle.RISK_ON])
    assert rd27.evaluate_adaptive_exit is original_eval
    assert rd27.apply_completed_bar_update is original_update
    assert treatment.diagnostics["patch_restored"] is True
