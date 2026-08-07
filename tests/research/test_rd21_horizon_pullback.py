from __future__ import annotations

import pandas as pd

from spotbot.research.rd21_horizon_pullback import (
    HORIZON_HOURS,
    replay_fixed_horizon,
    selection_table,
    validate_constants,
)


def synthetic_features() -> dict[str, pd.DataFrame]:
    times = pd.date_range("2019-04-01T00:00:00Z", periods=220, freq="h")
    close = pd.Series([100.0 + 0.05 * i for i in range(len(times))])
    frame = pd.DataFrame(
        {
            "timestamp": times,
            "open": close,
            "high": close + 0.5,
            "low": close - 0.5,
            "close": close + 0.1,
            "volume": 1_000_000.0,
            "trailing_24h_quote_turnover_proxy": 1_000_000_000.0,
        }
    )
    return {"AAA-USDT": frame}


def synthetic_events() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "universe_id": "C2",
                "partition_id": "DISCOVERY_2019_2021",
                "timestamp": pd.Timestamp("2019-04-01T00:00:00Z"),
                "candidate_rank": 1,
                "pair": "AAA-USDT",
                "membership_rank": 1,
                "score": 0.75,
                "initial_stop_reference": 95.0,
            }
        ]
    )


def test_constants_are_frozen() -> None:
    validate_constants()
    assert HORIZON_HOURS == (24, 72, 168)


def test_horizon_exit_occurs_at_scheduled_open() -> None:
    trades, _equity, route = replay_fixed_horizon(
        universe_id="C2",
        cost_multiplier=1.0,
        horizon_hours=24,
        events=synthetic_events(),
        features=synthetic_features(),
    )
    assert route["fixed_horizon_exits"] == 1
    assert len(trades) == 1
    row = trades.iloc[0]
    assert row["exit_reason"] == "FIXED_HORIZON_24H_OPEN"
    assert pd.Timestamp(row["entry_time"]) == pd.Timestamp("2019-04-01T01:00:00Z")
    assert pd.Timestamp(row["exit_time"]) == pd.Timestamp("2019-04-02T01:00:00Z")
    assert float(row["holding_hours"]) == 24.0


def test_static_stop_can_exit_before_horizon() -> None:
    features = synthetic_features()
    frame = features["AAA-USDT"].copy()
    frame.loc[3, "low"] = 94.0
    features["AAA-USDT"] = frame

    trades, _equity, route = replay_fixed_horizon(
        universe_id="C2",
        cost_multiplier=1.0,
        horizon_hours=72,
        events=synthetic_events(),
        features=features,
    )
    assert route["hard_stop_exits"] == 1
    assert route["fixed_horizon_exits"] == 0
    row = trades.iloc[0]
    assert row["exit_reason"] == "HARD_STOP_STATIC"
    assert float(row["exit_price"]) == 95.0
    assert float(row["holding_hours"]) == 2.0


def test_two_x_cost_does_not_change_signal_or_exit_time() -> None:
    one, _equity1, _route1 = replay_fixed_horizon(
        universe_id="C2",
        cost_multiplier=1.0,
        horizon_hours=24,
        events=synthetic_events(),
        features=synthetic_features(),
    )
    two, _equity2, _route2 = replay_fixed_horizon(
        universe_id="C2",
        cost_multiplier=2.0,
        horizon_hours=24,
        events=synthetic_events(),
        features=synthetic_features(),
    )
    assert one.iloc[0]["entry_time"] == two.iloc[0]["entry_time"]
    assert one.iloc[0]["exit_time"] == two.iloc[0]["exit_time"]
    assert one.iloc[0]["exit_reason"] == two.iloc[0]["exit_reason"]
    assert float(two.iloc[0]["net_pnl"]) < float(one.iloc[0]["net_pnl"])


def test_selection_prefers_passing_variant_before_raw_return() -> None:
    rows = []
    for horizon, passed_return in ((24, 0.50), (72, 0.10), (168, 0.20)):
        for universe in ("C2", "D2", "E2"):
            rows.append(
                {
                    "horizon_hours": horizon,
                    "universe_id": universe,
                    "cost_multiplier": 2.0,
                    "net_return": passed_return,
                    "profit_factor": 1.2,
                    "maximum_drawdown": 0.1,
                    "one_way_turnover_initial_equity": 10.0,
                }
            )
    metrics = pd.DataFrame(rows)
    ranking = selection_table(metrics, {24: False, 72: True, 168: True})
    assert int(ranking.iloc[0]["horizon_hours"]) == 168
    assert bool(ranking.iloc[0]["hard_gates_passed"]) is True


def test_selection_uses_lower_drawdown_after_equal_return_and_pf() -> None:
    rows = []
    for horizon, drawdown in ((24, 0.20), (72, 0.12), (168, 0.15)):
        for universe in ("C2", "D2", "E2"):
            rows.append(
                {
                    "horizon_hours": horizon,
                    "universe_id": universe,
                    "cost_multiplier": 2.0,
                    "net_return": 0.20,
                    "profit_factor": 1.3,
                    "maximum_drawdown": drawdown,
                    "one_way_turnover_initial_equity": 10.0,
                }
            )
    metrics = pd.DataFrame(rows)
    ranking = selection_table(metrics, {24: True, 72: True, 168: True})
    assert int(ranking.iloc[0]["horizon_hours"]) == 72
