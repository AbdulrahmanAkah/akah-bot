"""Tests for RD19-P2C-R1 conformance corrections."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from spotbot.research import rd19_p2c_discovery as p2c
from spotbot.research.rd19_p2a_engine import resolve_variants
from spotbot.research.rd19_p2c_r1_engine import (
    FastPairFrame,
    build_feature_store,
    entry_filter_reason,
    execute_run_fast,
    feature_signature,
    prepare_feature_frame_corrected,
)


def protocol() -> dict[str, object]:
    path = (
        Path(__file__).resolve().parents[2] / "data/research/rd19_p2_runtime/"
        "rd19-p2-discovery-protocol-v1.json"
    )
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def pullback_variant() -> dict[str, object]:
    return next(
        row for row in resolve_variants(protocol()) if row["entry_family"] == "CONFIRMED_PULLBACK"
    )


def breakout_variant() -> dict[str, object]:
    return next(
        row
        for row in resolve_variants(protocol())
        if row["entry_family"] == "VOLATILITY_CONTRACTION_BREAKOUT"
    )


def synthetic_bars(periods: int = 900) -> pd.DataFrame:
    timestamps = pd.date_range(
        "2020-01-01T00:00:00Z",
        periods=periods,
        freq="h",
    )
    close = pd.Series(
        100.0 + 0.03 * pd.RangeIndex(periods),
        dtype=float,
    )
    open_ = close.shift(1).fillna(close.iloc[0])
    high = pd.concat([open_, close], axis=1).max(axis=1) + 1.0
    low = pd.concat([open_, close], axis=1).min(axis=1) - 1.0
    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": open_.to_numpy(),
            "high": high.to_numpy(),
            "low": low.to_numpy(),
            "close": close.to_numpy(),
            "volume": 1_000_000.0,
        }
    )


def test_pullback_lookback_uses_prior_twelve_bar_window() -> None:
    config = pullback_variant()
    raw = synthetic_bars()
    featured = prepare_feature_frame_corrected(raw, config)

    index = 800
    # Force a touch five bars before the recovery bar while the immediately
    # preceding bar remains above its EMA.
    featured.loc[index - 5, "low"] = featured.loc[index - 5, "entry_ema"] - 0.5
    touch = (
        (featured["low"] <= featured["entry_ema"])
        .shift(1)
        .rolling(
            int(config["pullback_lookback_bars"]),
            min_periods=int(config["pullback_lookback_bars"]),
        )
        .max()
        .fillna(False)
        .astype(bool)
    )
    featured["pullback_touch_prior_window"] = touch
    featured.loc[index, "close"] = max(
        featured.loc[index, "entry_ema"] + 1.0,
        featured.loc[index, "prior_close"] + 1.0,
    )
    featured.loc[index, "trend_fast_ema"] = featured.loc[index, "close"] - 0.5
    featured.loc[index, "atr"] = 2.0

    frame = FastPairFrame.from_frame(featured)
    assert frame.flag(index, "pullback_touch_prior_window")
    assert entry_filter_reason(frame, index, config) == "PASS"


def test_breakout_contraction_is_measured_before_breakout_bar() -> None:
    config = breakout_variant()
    raw = synthetic_bars()
    featured = prepare_feature_frame_corrected(raw, config)
    index = 800

    featured.loc[index, "close"] = featured.loc[index, "breakout_high"] + 1.0
    featured.loc[index, "trend_fast_ema"] = featured.loc[index, "close"] - 0.5
    featured.loc[index, "atr"] = 2.0
    featured.loc[index, "prior_atr"] = 0.5
    featured.loc[index, "prior_atr_reference"] = 1.0
    # Current-bar ATR may expand; the prior contraction remains valid.
    featured.loc[index, "atr_reference"] = 1.0

    frame = FastPairFrame.from_frame(featured)
    assert entry_filter_reason(frame, index, config) == "PASS"


def test_feature_matrix_collapses_to_two_cached_signatures() -> None:
    variants = resolve_variants(protocol())
    assert len(variants) == 12
    assert len({feature_signature(row) for row in variants}) == 2


def test_corrected_feature_store_never_reads_2024() -> None:
    config = pullback_variant()
    raw = synthetic_bars()
    store = build_feature_store({"BTC-USDT": raw}, config)
    pair = store.pair("BTC-USDT")
    assert pair is not None
    maximum = int(pair.timestamps_ns.max())
    assert maximum < pd.Timestamp("2024-01-01T00:00:00Z").value


def test_frozen_parameters_remain_unchanged_by_resolution() -> None:
    value = protocol()
    variants = resolve_variants(value)
    assert value["matrix_frozen"] is True
    assert value["parameters_frozen_for_p2"] is True
    assert len(variants) == 12
    assert {float(row["risk_per_position_fraction_of_equity"]) for row in variants} == {0.005}
    assert {int(row["maximum_holding_bars"]) for row in variants} == {720}


def test_thesis_invalidation_executes_at_next_bar_open() -> None:
    config = next(row for row in resolve_variants(protocol()) if row["variant_id"] == "RD19_P2_V12")
    periods = 2200
    timestamps = pd.date_range(
        "2020-01-01T00:00:00Z",
        periods=periods,
        freq="h",
    )
    pairs = (
        "BTC-USDT",
        "ETH-USDT",
        "SOL-USDT",
        "LINK-USDT",
        "ADA-USDT",
        "AVAX-USDT",
    )
    raw_frames: dict[str, pd.DataFrame] = {}
    x = pd.Series(range(periods), dtype=float)
    for offset, pair in enumerate(pairs):
        close = 100.0 + offset * 5.0 + 0.02 * x
        open_ = close.shift(1).fillna(close.iloc[0])
        high = pd.concat([open_, close], axis=1).max(axis=1) + 1.0
        low = pd.concat([open_, close], axis=1).min(axis=1) - 1.0
        raw_frames[pair] = pd.DataFrame(
            {
                "timestamp": timestamps,
                "open": open_.to_numpy(),
                "high": high.to_numpy(),
                "low": low.to_numpy(),
                "close": close.to_numpy(),
                "volume": 1_000_000.0,
            }
        )

    store = build_feature_store(raw_frames, config)
    start = timestamps[1900]
    end = timestamps[1910]
    frame = store.pair("ETH-USDT")
    assert frame is not None
    signal_index = frame.index_at_ns(start.value)
    entry_time = start + pd.Timedelta(hours=1)
    invalidation_index = frame.index_at_ns(entry_time.value)
    next_time = start + pd.Timedelta(hours=2)
    next_index = frame.index_at_ns(next_time.value)

    frame.columns["trend_fast_ema"][invalidation_index] = (
        frame.columns["close"][invalidation_index] + 10.0
    )
    membership_frame = pd.DataFrame(
        [
            {
                "universe_id": "C2",
                "decision_time": start - pd.Timedelta(days=1),
                "effective_end": end + pd.Timedelta(days=1),
                "effective_pair": pair,
                "effective_rank": rank,
            }
            for rank, pair in enumerate(pairs, start=1)
        ]
    )
    membership = p2c.MembershipIndex(membership_frame)
    plan = {
        start.value: (
            {
                "signal_time": start,
                "execution_time": entry_time,
                "pair": "ETH-USDT",
                "rank": 1,
                "score": 1.0,
                "atr": frame.value(signal_index, "atr"),
                "atr_percent": frame.value(signal_index, "atr_percent"),
                "cost_hurdle_ratio": 99.0,
                "entry_family": str(config["entry_family"]),
            },
        )
    }
    result = execute_run_fast(
        run_row={
            "execution_order": 1,
            "variant_id": "RD19_P2_V12",
            "partition_id": "TEST",
            "universe_id": "C2",
            "cost_multiplier": 1.0,
        },
        config=config,
        store=store,
        membership=membership,
        candidate_plan=plan,
        partition_start=start,
        partition_end=end,
    )
    trades = result["trades"]
    assert len(trades) == 1
    trade = trades.iloc[0]
    assert pd.Timestamp(trade["entry_time"]) == entry_time
    assert pd.Timestamp(trade["exit_time"]) == next_time
    assert trade["exit_reason"] == "THESIS_INVALIDATION"
    assert float(trade["exit_price"]) == frame.value(next_index, "open")
