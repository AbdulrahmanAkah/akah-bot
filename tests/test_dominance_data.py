from __future__ import annotations

import pandas as pd
import pytest

from spotbot.research.dominance_data import (
    DominanceDataError,
    assert_research_boundary,
    decompose_dominance,
    frame_fingerprint,
    reject_non_point_in_time_reconstruction,
    resample_closed_market_cap,
)


def test_dominance_decomposition_identity() -> None:
    component = pd.Series([100.0, 110.0, 121.0])
    total = pd.Series([1_000.0, 1_050.0, 1_100.0])
    result = decompose_dominance(component, total)
    expected = (
        result["delta_log_component_market_cap"]
        - result["delta_log_total_market_cap"]
    )
    pd.testing.assert_series_equal(
        result["delta_log_dominance"], expected, check_names=False
    )


def test_current_supply_backfill_is_rejected() -> None:
    with pytest.raises(DominanceDataError, match="current supply"):
        reject_non_point_in_time_reconstruction(
            historical_prices=True,
            historical_supply=False,
            historical_rankings=True,
        )


def test_current_top_ten_backfill_is_rejected() -> None:
    with pytest.raises(DominanceDataError, match="Top-10"):
        reject_non_point_in_time_reconstruction(
            historical_prices=True,
            historical_supply=True,
            historical_rankings=False,
        )


def test_2025_dominance_observation_is_blocked() -> None:
    with pytest.raises(DominanceDataError, match="locked"):
        assert_research_boundary(
            pd.DataFrame({"timestamp": ["2025-01-01T00:00:00Z"]})
        )


def test_closed_utc_resampling_does_not_emit_locked_bar() -> None:
    frame = pd.DataFrame(
        {
            "timestamp": pd.date_range(
                "2024-12-31T00:00:00Z", periods=6, freq="4h"
            ),
            "btc_market_cap": range(6),
        }
    )
    result = resample_closed_market_cap(frame, frequency="8h")
    assert (result["timestamp"] < pd.Timestamp("2025-01-01T00:00:00Z")).all()


def test_frame_hash_changes_with_data() -> None:
    frame = pd.DataFrame({"timestamp": ["2024-01-01T00:00:00Z"], "value": [1.0]})
    mutated = frame.assign(value=2.0)
    assert frame_fingerprint(frame) != frame_fingerprint(mutated)

