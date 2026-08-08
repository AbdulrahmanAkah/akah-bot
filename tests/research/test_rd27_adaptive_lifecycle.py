from __future__ import annotations

import pandas as pd
import pytest

from spotbot.research.rd26_exit_architecture import (
    DATA_START,
    FAMILY_MOMENTUM_BREAKOUT,
    POLICY_TIME_FAIL,
    replay_policy,
)
from spotbot.research.rd27_adaptive_lifecycle import (
    RISK_OFF,
    RISK_ON,
    TRANSITION,
    apply_completed_bar_update,
    capital_admission_decision,
    classify_market_state,
    entry_market_state,
    evaluate_adaptive_exit,
    evaluate_control_time_fail_exit,
    new_lifecycle_position,
    open_position_market_state,
)


def synthetic_state_frame() -> pd.DataFrame:
    base = pd.Timestamp("2030-01-01T00:00:00Z")
    return pd.DataFrame(
        [
            {"timestamp": base, "market_state": RISK_ON, "state_ready": True},
            {
                "timestamp": base + pd.Timedelta(hours=1),
                "market_state": RISK_OFF,
                "state_ready": True,
            },
            {
                "timestamp": base + pd.Timedelta(hours=2),
                "market_state": TRANSITION,
                "state_ready": True,
            },
        ]
    )


@pytest.mark.parametrize(
    ("inputs", "expected"),
    [
        (
            {
                "close": 110.0,
                "ema720": 100.0,
                "ema720_168h_ago": 99.0,
                "return_72h": 0.05,
                "volatility_shock": False,
            },
            RISK_ON,
        ),
        (
            {
                "close": 90.0,
                "ema720": 100.0,
                "ema720_168h_ago": 101.0,
                "return_72h": -0.05,
                "volatility_shock": False,
            },
            RISK_OFF,
        ),
        (
            {
                "close": 105.0,
                "ema720": 100.0,
                "ema720_168h_ago": 101.0,
                "return_72h": 0.01,
                "volatility_shock": False,
            },
            TRANSITION,
        ),
    ],
)
def test_market_state_classifier_frozen_boundaries(
    inputs: dict[str, float | bool],
    expected: str,
) -> None:
    assert classify_market_state(**inputs) == expected


def test_entry_state_uses_signal_close_not_next_bar() -> None:
    frame = synthetic_state_frame()
    signal_time = pd.Timestamp("2030-01-01T00:00:00Z")
    assert entry_market_state(frame, signal_time=signal_time) == RISK_ON


def test_open_position_state_uses_prior_completed_bar_only() -> None:
    frame = synthetic_state_frame()
    current_open = pd.Timestamp("2030-01-01T02:00:00Z")
    assert open_position_market_state(frame, current_open_time=current_open) == RISK_OFF


def test_risk_off_records_signal_but_suppresses_admission() -> None:
    decision = capital_admission_decision(RISK_OFF)
    assert decision.record_signal is True
    assert decision.admit_position is False
    assert decision.target_slot_fraction == 0.0


def test_router_slot_targets_are_frozen() -> None:
    assert capital_admission_decision(RISK_ON).target_slot_fraction == 0.18
    assert capital_admission_decision(TRANSITION).target_slot_fraction == 0.09
    assert capital_admission_decision(RISK_OFF).target_slot_fraction == 0.0


def test_protection_floor_cannot_loosen_when_state_improves() -> None:
    entry_time = pd.Timestamp("2030-01-01T00:00:00Z")
    position = new_lifecycle_position(
        pair="AAA-USDT",
        entry_time=entry_time,
        entry_price=100.0,
        atr24_at_signal=1.0,
    )
    risk_off = evaluate_adaptive_exit(
        position,
        current_open_time=entry_time + pd.Timedelta(hours=1),
        current_open=100.0,
        current_low=98.0,
        prior_asset_close=100.0,
        market_state=RISK_OFF,
    )
    assert risk_off.should_exit is False
    assert risk_off.effective_floor == 97.0
    position = apply_completed_bar_update(
        position,
        decision=risk_off,
        completed_high=101.0,
    )

    risk_on = evaluate_adaptive_exit(
        position,
        current_open_time=entry_time + pd.Timedelta(hours=2),
        current_open=100.0,
        current_low=98.0,
        prior_asset_close=100.0,
        market_state=RISK_ON,
    )
    assert risk_on.effective_floor == 97.0
    assert risk_on.floor_source == "MONOTONIC_PRIOR_FLOOR"


def test_current_bar_high_cannot_tighten_same_bar_trail() -> None:
    entry_time = pd.Timestamp("2030-01-01T00:00:00Z")
    position = new_lifecycle_position(
        pair="AAA-USDT",
        entry_time=entry_time,
        entry_price=100.0,
        atr24_at_signal=1.0,
    )
    first = evaluate_adaptive_exit(
        position,
        current_open_time=entry_time + pd.Timedelta(hours=1),
        current_open=100.0,
        current_low=99.0,
        prior_asset_close=100.0,
        market_state=RISK_ON,
    )
    assert first.should_exit is False
    assert first.effective_floor == 95.0

    position = apply_completed_bar_update(
        position,
        decision=first,
        completed_high=110.0,
    )
    second = evaluate_adaptive_exit(
        position,
        current_open_time=entry_time + pd.Timedelta(hours=2),
        current_open=109.0,
        current_low=105.0,
        prior_asset_close=109.0,
        market_state=RISK_ON,
    )
    assert second.should_exit is True
    assert second.exit_reason == "ADAPTIVE_PROTECTION_TOUCH"
    assert second.exit_price == 106.0


@pytest.mark.parametrize(
    ("state", "age_hours"),
    [(RISK_ON, 72), (TRANSITION, 48), (RISK_OFF, 24)],
)
def test_stagnation_horizon_adapts_to_current_state(state: str, age_hours: int) -> None:
    entry_time = pd.Timestamp("2030-01-01T00:00:00Z")
    position = new_lifecycle_position(
        pair="AAA-USDT",
        entry_time=entry_time,
        entry_price=100.0,
        atr24_at_signal=1.0,
    )
    decision = evaluate_adaptive_exit(
        position,
        current_open_time=entry_time + pd.Timedelta(hours=age_hours),
        current_open=100.0,
        current_low=98.0,
        prior_asset_close=99.0,
        market_state=state,
    )
    assert decision.should_exit is True
    assert decision.exit_reason == f"ADAPTIVE_STAGNATION_{age_hours}H_CLOSE_NOT_ABOVE_ENTRY"
    assert decision.exit_price == 100.0


def rd26_frame(overrides: dict[int, dict[str, float]] | None = None) -> pd.DataFrame:
    overrides = overrides or {}
    rows = []
    for hour in range(200):
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


def rd26_event() -> pd.DataFrame:
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


@pytest.mark.parametrize(
    ("overrides", "expected_reason", "expected_holding"),
    [
        ({72: {"close": 99.0}, 73: {"open": 98.0}}, "TIME_FAILURE_72H_CLOSE_NOT_ABOVE_ENTRY", 72),
        ({72: {"close": 101.0}}, "MAX_HOLD_168H", 168),
    ],
)
def test_control_decision_matches_rd26_time_fail_synthetic_path(
    overrides: dict[int, dict[str, float]],
    expected_reason: str,
    expected_holding: int,
) -> None:
    trades, _daily, _metrics, _counters = replay_policy(
        policy_id=POLICY_TIME_FAIL,
        portfolio_id="RD27_P0B_SYNTHETIC_PARITY",
        universe_id="C2",
        cost_multiplier=1.0,
        events=rd26_event(),
        frames={"AAA-USDT": rd26_frame(overrides)},
    )
    rd26_trade = trades.iloc[0]
    assert rd26_trade["exit_reason"] == expected_reason
    assert rd26_trade["holding_hours"] == expected_holding

    position = new_lifecycle_position(
        pair="AAA-USDT",
        entry_time=DATA_START + pd.Timedelta(hours=1),
        entry_price=100.0,
        atr24_at_signal=1.0,
    )
    current_time = position.entry_time + pd.Timedelta(hours=expected_holding)
    frame = rd26_frame(overrides)
    current = frame.loc[frame["timestamp"] == current_time].iloc[0]
    prior = frame.loc[frame["timestamp"] == current_time - pd.Timedelta(hours=1)].iloc[0]

    should_exit, exit_price, reason = evaluate_control_time_fail_exit(
        position,
        current_open_time=current_time,
        current_open=float(current["open"]),
        prior_asset_close=float(prior["close"]),
    )
    assert should_exit is True
    assert reason == expected_reason
    assert exit_price == float(rd26_trade["exit_price"])
