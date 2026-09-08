from __future__ import annotations

import math

import pandas as pd

from spotbot.research.rd43_control_relative_state import (
    MISSING_REQUIRED_HOURLY_BAR,
    VALID,
    identity_parity,
    normalize_raw_bars,
    reconstruct_decision,
    validate_constants,
)


def _row(landmark: int = 24) -> dict[str, object]:
    entry = pd.Timestamp("2023-01-01T00:00:00Z")
    decision = entry + pd.Timedelta(hours=landmark)
    return {
        "decision_id": f"X|{landmark}",
        "control_position_id": "X",
        "universe_id": "C2",
        "period_id": "ROBUSTNESS_2023",
        "pair": "BTC-USDT",
        "signal_time": entry - pd.Timedelta(hours=1),
        "entry_time": entry,
        "decision_time": decision,
        "completed_information_time": decision - pd.Timedelta(hours=1),
        "landmark_age_hours": landmark,
        "risk_set_class": "RESOLVED_CONTROL_OUTCOME",
        "resolved_target": True,
        "right_censored_target": False,
        "entry_price": 100.0,
        "atr24_at_signal": 2.0,
    }


def _bars(count: int = 24) -> pd.DataFrame:
    timestamps = pd.date_range(
        "2023-01-01T00:00:00Z",
        periods=count,
        freq="h",
    )
    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "high": [101.0 + i for i in range(count)],
            "close": [100.5 + i for i in range(count)],
        }
    )


def test_constants() -> None:
    validate_constants()


def test_high_water_uses_completed_highs_through_t_minus_1() -> None:
    bars, _duplicates = normalize_raw_bars(_bars())
    result = reconstruct_decision(_row(), bars)
    assert result["data_quality_class"] == VALID
    assert math.isclose(result["completed_high_water"], 124.0)
    assert math.isclose(result["completed_mark"], 123.5)
    assert math.isclose(result["high_water_gain_atr"], 12.0)
    assert math.isclose(
        result["pullback_from_high_water_atr"],
        0.25,
    )


def test_decision_bar_is_not_required_or_used() -> None:
    bars = _bars(25)
    bars.loc[24, "high"] = 1000.0
    bars.loc[24, "close"] = 999.0
    bars, _duplicates = normalize_raw_bars(bars)
    result = reconstruct_decision(_row(), bars)
    assert math.isclose(result["completed_high_water"], 124.0)
    assert math.isclose(result["completed_mark"], 123.5)


def test_missing_required_hour_blocks_row() -> None:
    bars = _bars().drop(index=10).reset_index(drop=True)
    bars, _duplicates = normalize_raw_bars(bars)
    result = reconstruct_decision(_row(), bars)
    assert result["data_quality_class"] == MISSING_REQUIRED_HOURLY_BAR


def test_derived_identity_parity() -> None:
    bars, _duplicates = normalize_raw_bars(_bars())
    result = reconstruct_decision(_row(), bars)
    parity = identity_parity(pd.DataFrame([result]))
    assert parity["all_identity_checks_pass"] is True
    assert parity["trail_armed_mismatch_count"] == 0


def test_duplicate_timestamp_matches_frozen_keep_last_semantics() -> None:
    bars = pd.concat(
        [
            _bars(),
            pd.DataFrame(
                {
                    "timestamp": [pd.Timestamp("2023-01-01T23:00:00Z")],
                    "high": [130.0],
                    "close": [129.0],
                }
            ),
        ],
        ignore_index=True,
    )
    normalized, duplicates = normalize_raw_bars(bars)
    assert duplicates == 1
    row = normalized.loc[normalized["timestamp"] == pd.Timestamp("2023-01-01T23:00:00Z")].iloc[0]
    assert math.isclose(float(row["high"]), 130.0)


def test_2024_bar_is_rejected() -> None:
    raw = pd.DataFrame(
        {
            "timestamp": [pd.Timestamp("2024-01-01T00:00:00Z")],
            "high": [101.0],
            "close": [100.0],
        }
    )
    try:
        normalize_raw_bars(raw)
    except Exception as exc:
        assert "2024+" in str(exc)
    else:
        raise AssertionError("2024 bar should be rejected")
