"""Tests for the RD19-P2A frozen engine implementation."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from spotbot.research.rd19_p2a_engine import (
    P2AEngineError,
    dry_run_variant,
    normalize_bars,
    resolve_variants,
    synthetic_frames,
)


def _protocol() -> dict[str, object]:
    path = (
        Path(__file__).resolve().parents[2] / "data/research/rd19_p2_runtime/"
        "rd19-p2-discovery-protocol-v1.json"
    )
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_resolves_exactly_twelve_frozen_variants() -> None:
    variants = resolve_variants(_protocol())
    assert len(variants) == 12
    assert len({str(row["variant_id"]) for row in variants}) == 12
    assert {str(row["entry_family"]) for row in variants} == {
        "CONFIRMED_PULLBACK",
        "VOLATILITY_CONTRACTION_BREAKOUT",
    }
    assert {int(row["top_k"]) for row in variants} == {2, 3}
    assert {float(row["trail_atr"]) for row in variants} == {3.0, 4.0}


@pytest.mark.parametrize(
    "entry_family",
    [
        "CONFIRMED_PULLBACK",
        "VOLATILITY_CONTRACTION_BREAKOUT",
    ],
)
def test_both_entry_families_complete_fixture_dry_run(
    entry_family: str,
) -> None:
    variant = next(
        row for row in resolve_variants(_protocol()) if row["entry_family"] == entry_family
    )
    candidates, trades = dry_run_variant(
        variant,
        cost_multiplier=2.0,
    )
    assert not candidates.empty
    assert not trades.empty
    assert (trades["minimum_cash"] >= 0.0).all()
    assert set(trades["instrument_type"]) == {"SPOT"}
    assert set(trades["side"]) == {"LONG"}
    signal = pd.to_datetime(trades["signal_time"], utc=True)
    entry = pd.to_datetime(trades["entry_time"], utc=True)
    assert ((entry - signal) == pd.Timedelta(hours=1)).all()


def test_fixture_remains_before_sealed_cutoff() -> None:
    variant = resolve_variants(_protocol())[0]
    frames = synthetic_frames(variant)
    maximum = max(pd.to_datetime(frame["timestamp"], utc=True).max() for frame in frames.values())
    assert maximum < pd.Timestamp("2025-01-01T00:00:00Z")


def test_normalize_rejects_post_2024_bar() -> None:
    variant = resolve_variants(_protocol())[0]
    frame = synthetic_frames(variant)["BTC-USDT"].tail(10).copy()
    frame.loc[frame.index[-1], "timestamp"] = "2025-01-01T00:00:00Z"
    with pytest.raises(P2AEngineError, match="sealed 2025 cutoff"):
        normalize_bars(frame)


def test_normalize_rejects_duplicate_timestamp() -> None:
    variant = resolve_variants(_protocol())[0]
    frame = synthetic_frames(variant)["BTC-USDT"].tail(10).copy()
    frame.loc[frame.index[-1], "timestamp"] = frame.iloc[-2]["timestamp"]
    with pytest.raises(P2AEngineError, match="duplicate timestamps"):
        normalize_bars(frame)
