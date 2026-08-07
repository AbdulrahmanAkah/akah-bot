from __future__ import annotations

import pandas as pd

from spotbot.research.rd26_exit_architecture import (
    DATA_START,
    FAMILY_MOMENTUM_BREAKOUT,
    POLICY_BASELINE,
    POLICY_COMBINED,
    POLICY_PROFIT_TRAIL,
    POLICY_TIME_FAIL,
    replay_policy,
    union_events,
)


def frame_with(overrides: dict[int, dict[str, float]] | None = None) -> pd.DataFrame:
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


def run(policy: str, overrides=None):
    trades, _daily, metrics, _counters = replay_policy(
        policy_id=policy,
        portfolio_id="TEST",
        universe_id="C2",
        cost_multiplier=1.0,
        events=event(),
        frames={"AAA-USDT": frame_with(overrides)},
    )
    return trades, metrics


def test_baseline_exits_at_168_hours() -> None:
    trades, _metrics = run(POLICY_BASELINE)
    assert len(trades) == 1
    row = trades.iloc[0]
    assert row["holding_hours"] == 168
    assert row["exit_reason"] == "MAX_HOLD_168H"


def test_time_failure_exits_at_72_hours() -> None:
    overrides = {72: {"close": 99.0}}
    trades, _metrics = run(POLICY_TIME_FAIL, overrides)
    row = trades.iloc[0]
    assert row["holding_hours"] == 72
    assert row["exit_reason"] == "TIME_FAILURE_72H_CLOSE_NOT_ABOVE_ENTRY"


def test_time_failure_allows_positive_prior_close() -> None:
    overrides = {72: {"close": 101.0}}
    trades, _metrics = run(POLICY_TIME_FAIL, overrides)
    row = trades.iloc[0]
    assert row["holding_hours"] == 168
    assert row["exit_reason"] == "MAX_HOLD_168H"


def test_profit_trail_uses_prior_completed_high_water() -> None:
    overrides = {
        10: {"high": 107.0, "low": 100.0, "close": 106.0},
        11: {"open": 106.0, "high": 108.0, "low": 102.0, "close": 103.0},
    }
    trades, _metrics = run(POLICY_PROFIT_TRAIL, overrides)
    row = trades.iloc[0]
    assert row["holding_hours"] == 10
    assert row["exit_reason"] == "PROFIT_TRAIL_TOUCH"
    assert abs(row["exit_price"] - 103.0) < 1e-12


def test_profit_trail_does_not_same_bar_ratchet() -> None:
    overrides = {
        10: {"open": 100.0, "high": 110.0, "low": 99.0, "close": 109.0},
        11: {"open": 109.0, "high": 109.0, "low": 105.0, "close": 105.5},
    }
    trades, _metrics = run(POLICY_PROFIT_TRAIL, overrides)
    row = trades.iloc[0]
    assert row["holding_hours"] == 10
    assert row["exit_reason"] == "PROFIT_TRAIL_TOUCH"
    assert abs(row["exit_price"] - 106.0) < 1e-12


def test_combined_time_failure_has_open_priority() -> None:
    overrides = {
        60: {"high": 108.0, "close": 106.0},
        72: {"close": 99.0},
        73: {"open": 98.0, "high": 99.0, "low": 95.0, "close": 96.0},
    }
    trades, _metrics = run(POLICY_COMBINED, overrides)
    row = trades.iloc[0]
    assert row["holding_hours"] <= 72
    assert row["exit_reason"] in {
        "PROFIT_TRAIL_GAP",
        "PROFIT_TRAIL_TOUCH",
        "TIME_FAILURE_72H_CLOSE_NOT_ABOVE_ENTRY",
    }


def test_union_deduplicates_same_pair_time() -> None:
    events = pd.DataFrame(
        [
            {
                "universe_id": "C2",
                "timestamp": DATA_START,
                "pair": "AAA-USDT",
                "membership_rank": 2,
                "period_id": "ROBUSTNESS_2022",
                "family_id": "MOMENTUM_BREAKOUT",
                "atr24_at_signal": 1.0,
            },
            {
                "universe_id": "C2",
                "timestamp": DATA_START,
                "pair": "AAA-USDT",
                "membership_rank": 1,
                "period_id": "ROBUSTNESS_2022",
                "family_id": "RELATIVE_STRENGTH_ROTATION",
                "atr24_at_signal": 1.0,
            },
        ]
    )
    union = union_events(events, universe_id="C2")
    assert len(union) == 1
    assert union.iloc[0]["membership_rank"] == 1
    assert union.iloc[0]["support_count"] == 2


def test_replay_never_uses_negative_cash() -> None:
    trades, metrics = run(POLICY_BASELINE)
    assert len(trades) == 1
    assert metrics["minimum_cash"] >= -1e-7
