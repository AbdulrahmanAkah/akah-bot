from __future__ import annotations

import math

import pandas as pd

from spotbot.research.rd24_minimal_portfolio import (
    DATA_CUTOFF,
    QUALIFIED_FAMILIES,
    concentration_diagnostics,
    fast_lookup,
    fixed_path_pf1_break_even_multiplier,
    normalize_economic_bars,
    prepare_frozen_events,
    replay_portfolio,
    union_events,
)


def synthetic_bars(
    *,
    start: str = "2019-01-01T00:00:00Z",
    hours: int = 500,
    base: float = 100.0,
) -> pd.DataFrame:
    timestamps = pd.date_range(start, periods=hours, freq="h")
    close = pd.Series(
        [base * (1.0002**index) for index in range(hours)],
        dtype=float,
    )
    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": close,
            "high": close * 1.01,
            "low": close * 0.99,
            "close": close,
            "volume": 1_000_000.0,
        }
    )


def event_frame(
    family: str = "MOMENTUM_BREAKOUT",
    pair: str = "AAA-USDT",
    timestamp: str = "2019-01-10T00:00:00Z",
) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "universe_id": "C2",
                "period_id": "DISCOVERY_2019_2020",
                "timestamp": timestamp,
                "family_id": family,
                "pair": pair,
                "membership_rank": 1,
            }
        ]
    )


def test_normalize_builds_causal_capacity_proxy() -> None:
    frame = normalize_economic_bars(synthetic_bars())
    assert "trailing_24h_quote_turnover_proxy" in frame.columns
    assert math.isnan(float(frame.iloc[22]["trailing_24h_quote_turnover_proxy"]))
    assert float(frame.iloc[23]["trailing_24h_quote_turnover_proxy"]) > 0.0
    assert frame["timestamp"].max() < DATA_CUTOFF


def test_fast_lookup_normalizes_timestamp_unit() -> None:
    raw = synthetic_bars()
    raw["timestamp"] = raw["timestamp"].dt.as_unit("us")
    frame = normalize_economic_bars(raw)
    lookup = fast_lookup(frame)
    target = pd.Timestamp(frame.iloc[100]["timestamp"])
    assert target.value in lookup


def test_prepare_events_rejects_nonqualified_family() -> None:
    raw = pd.concat(
        [
            event_frame("MOMENTUM_BREAKOUT"),
            event_frame("STRUCTURAL_REVERSAL", pair="BBB-USDT"),
        ],
        ignore_index=True,
    )
    frame = prepare_frozen_events(raw)
    assert set(frame["family_id"]) == {"MOMENTUM_BREAKOUT"}


def test_union_deduplicates_same_pair_timestamp_and_records_support() -> None:
    raw = pd.concat(
        [
            event_frame("MOMENTUM_BREAKOUT"),
            event_frame("VOLATILITY_EXPANSION"),
        ],
        ignore_index=True,
    )
    prepared = prepare_frozen_events(raw)
    union = union_events(
        prepared,
        universe_id="C2",
        families=QUALIFIED_FAMILIES,
    )
    assert len(union) == 1
    assert int(union.iloc[0]["support_count"]) == 2
    assert union.iloc[0]["support_families"] == ("MOMENTUM_BREAKOUT|VOLATILITY_EXPANSION")


def test_replay_uses_exact_168_hour_entry_to_exit_hold() -> None:
    raw = synthetic_bars(hours=600)
    frames = {"AAA-USDT": normalize_economic_bars(raw)}
    events = event_frame(timestamp="2019-01-10T00:00:00Z")
    prepared = prepare_frozen_events(events)
    prepared["support_families"] = "MOMENTUM_BREAKOUT"
    trades, _daily, metrics, counters = replay_portfolio(
        portfolio_id="MOMENTUM_BREAKOUT",
        universe_id="C2",
        cost_multiplier=1.0,
        events=prepared,
        frames=frames,
    )
    assert len(trades) == 1
    trade = trades.iloc[0]
    entry = pd.Timestamp(trade["entry_time"])
    exit_ = pd.Timestamp(trade["exit_time"])
    assert exit_ - entry == pd.Timedelta(hours=168)
    assert int(trade["holding_hours"]) == 168
    assert metrics["trade_count"] == 1
    assert counters["admitted_entries"] == 1


def test_replay_never_uses_negative_cash_or_more_than_five_slots() -> None:
    pairs = [f"P{index}-USDT" for index in range(8)]
    frames = {
        pair: normalize_economic_bars(synthetic_bars(hours=600, base=100.0 + index))
        for index, pair in enumerate(pairs)
    }
    rows = []
    for rank, pair in enumerate(pairs, start=1):
        rows.append(
            {
                "universe_id": "C2",
                "period_id": "DISCOVERY_2019_2020",
                "timestamp": "2019-01-10T00:00:00Z",
                "family_id": "MOMENTUM_BREAKOUT",
                "pair": pair,
                "membership_rank": rank,
                "support_families": "MOMENTUM_BREAKOUT",
            }
        )
    events = prepare_frozen_events(pd.DataFrame(rows))
    events["support_families"] = "MOMENTUM_BREAKOUT"
    trades, daily, _metrics, counters = replay_portfolio(
        portfolio_id="MOMENTUM_BREAKOUT",
        universe_id="C2",
        cost_multiplier=2.0,
        events=events,
        frames=frames,
    )
    assert len(trades) == 5
    assert counters["position_slots_full"] == 3
    assert float(daily["cash"].min()) >= 0.0
    assert int(daily["open_positions"].max()) <= 5


def test_concentration_and_break_even_are_finite() -> None:
    trades = pd.DataFrame(
        [
            {
                "pair": "AAA-USDT",
                "entry_time": "2019-01-01T00:00:00Z",
                "net_pnl": 100.0,
                "gross_pnl": 130.0,
                "entry_notional": 1000.0,
                "exit_notional": 1130.0,
            },
            {
                "pair": "BBB-USDT",
                "entry_time": "2020-01-01T00:00:00Z",
                "net_pnl": -20.0,
                "gross_pnl": -5.0,
                "entry_notional": 1000.0,
                "exit_notional": 995.0,
            },
        ]
    )
    diagnostics = concentration_diagnostics(trades)
    assert diagnostics["total_net_pnl"] == 80.0
    assert diagnostics["net_pnl_without_largest_winner"] == -20.0
    value = fixed_path_pf1_break_even_multiplier(trades)
    assert math.isfinite(value)
    assert value > 0.0
