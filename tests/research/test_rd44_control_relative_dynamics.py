from __future__ import annotations

import numpy as np
import pandas as pd

from spotbot.research.rd44_control_relative_dynamics import (
    MISSING_REQUIRED_HOURLY_BAR,
    VALID,
    dynamic_identity_parity,
    normalize_raw_bars,
    reconstruct_decision,
    support_counts,
    transport_supported_landmarks,
    validate_constants,
)


def _row() -> dict[str, object]:
    entry = pd.Timestamp("2022-01-01T00:00:00Z")
    decision = entry + pd.Timedelta(hours=24)
    return {
        "decision_id": "P1|024h",
        "control_position_id": "P1",
        "universe_id": "C2",
        "period_id": "ROBUSTNESS_2022",
        "pair": "TEST-USDT",
        "signal_time": entry - pd.Timedelta(hours=1),
        "entry_time": entry,
        "decision_time": decision,
        "completed_information_time": decision - pd.Timedelta(hours=1),
        "landmark_age_hours": 24,
        "risk_set_class": "RESOLVED_CONTROL_OUTCOME",
        "resolved_target": True,
        "right_censored_target": False,
        "entry_price": 100.0,
        "atr24_at_signal": 10.0,
    }


def _bars() -> pd.DataFrame:
    start = pd.Timestamp("2022-01-01T00:00:00Z")
    rows = []
    for hour in range(24):
        timestamp = start + pd.Timedelta(hours=hour)
        high = 101.0 + 0.5 * hour
        close = high - 1.0
        rows.append(
            {
                "timestamp": timestamp,
                "high": high,
                "close": close,
            }
        )

    # Reference time is hour 11. Force reference high water to 110.
    for hour in range(0, 12):
        rows[hour]["high"] = min(rows[hour]["high"], 110.0)
        rows[hour]["close"] = min(rows[hour]["close"], rows[hour]["high"])
    rows[10]["high"] = 110.0
    rows[10]["close"] = 109.0
    rows[11]["high"] = 110.0
    rows[11]["close"] = 108.0

    # Final high water first appears at hour 20, repeats at 21.
    for hour in range(12, 20):
        rows[hour]["high"] = 111.0 + (hour - 12)
        rows[hour]["close"] = rows[hour]["high"] - 1.0
    rows[20]["high"] = 120.0
    rows[20]["close"] = 117.0
    rows[21]["high"] = 120.0
    rows[21]["close"] = 116.0
    rows[22]["high"] = 119.0
    rows[22]["close"] = 116.0
    rows[23]["high"] = 118.0
    rows[23]["close"] = 115.0
    return pd.DataFrame(rows)


def test_constants() -> None:
    validate_constants()


def test_normalize_raw_bars_deduplicates_last() -> None:
    raw = _bars()
    duplicate = raw.iloc[[0]].copy()
    duplicate["close"] = 100.5
    merged = pd.concat([raw, duplicate], ignore_index=True)
    normalized, duplicate_count = normalize_raw_bars(merged)
    assert duplicate_count == 1
    assert len(normalized) == 24
    first = normalized.loc[normalized["timestamp"] == pd.Timestamp("2022-01-01T00:00:00Z")].iloc[0]
    assert float(first["close"]) == 100.5


def test_reconstruction_frozen_dynamic_axes() -> None:
    result = reconstruct_decision(_row(), _bars())
    assert result["data_quality_class"] == VALID
    assert result["reference_time_12h"] == pd.Timestamp("2022-01-01T11:00:00Z")
    assert result["audit_completed_high_water_time"] == pd.Timestamp("2022-01-01T20:00:00Z")
    assert result["time_since_completed_high_water_hours"] == 3.0
    assert np.isclose(
        result["recent_12h_high_water_increment_atr"],
        1.0,
    )
    # Reference pullback=(110-108)/10=.2
    # Completed pullback=(120-115)/10=.5
    assert np.isclose(
        result["recent_12h_pullback_change_atr"],
        0.3,
    )
    # Mark change=(115-108)/10=.7 = 1.0 - .3
    assert np.isclose(
        result["audit_recent_12h_mark_change_atr"],
        0.7,
    )
    assert abs(result["audit_recent_mark_change_identity_residual"]) < 1e-12


def test_equal_high_does_not_reset_high_water_time() -> None:
    result = reconstruct_decision(_row(), _bars())
    assert result["audit_strict_high_water_time_match"] is True
    assert result["audit_completed_high_water_time"] == pd.Timestamp("2022-01-01T20:00:00Z")


def test_missing_hour_fails_closed() -> None:
    bars = _bars().drop(index=5).reset_index(drop=True)
    result = reconstruct_decision(_row(), bars)
    assert result["data_quality_class"] == MISSING_REQUIRED_HOURLY_BAR


def test_dynamic_identity_parity_passes_valid_row() -> None:
    result = reconstruct_decision(_row(), _bars())
    ledger = pd.DataFrame([result])
    parity = dynamic_identity_parity(ledger)
    assert parity["identity_parity_pass"] is True
    assert parity["strict_high_water_time_mismatch_row_count"] == 0
    assert parity["recent_mark_change_is_candidate_feature"] is False


def test_support_counts_gate() -> None:
    rows = []
    base = pd.Timestamp("2022-01-01T00:00:00Z")
    for index in range(20):
        rows.append(
            {
                "control_position_id": f"P{index}",
                "pair": f"PAIR-{index % 5}",
                "signal_time": base + pd.Timedelta(days=index % 10),
            }
        )
    support = support_counts(pd.DataFrame(rows))
    assert support["numeric_support_pass"] is True
    assert support["unique_control_position_count"] == 20
    assert support["unique_pair_count"] == 5
    assert support["unique_signal_day_count"] == 10


def test_transport_support_needs_two_universes_each_year() -> None:
    rows = []
    for period in ("ROBUSTNESS_2022", "ROBUSTNESS_2023"):
        for universe in ("C2", "D2", "E2"):
            for landmark in (24, 48, 72, 96, 120, 144):
                rows.append(
                    {
                        "period_id": period,
                        "universe_id": universe,
                        "landmark_age_hours": landmark,
                        "support_pass": bool(landmark == 24 and universe in {"C2", "D2"}),
                    }
                )
    result = transport_supported_landmarks(pd.DataFrame(rows))
    row24 = next(row for row in result if row["landmark_age_hours"] == 24)
    row48 = next(row for row in result if row["landmark_age_hours"] == 48)
    assert row24["transport_support_eligible"] is True
    assert row48["transport_support_eligible"] is False
