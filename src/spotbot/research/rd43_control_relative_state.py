"""RD43-P2 control-relative-state reconstruction and support census.

Target blind by construction:
- no RCV, outcome, exit-price, exit-reason, PnL, model, threshold, or action inputs;
- landmark eligibility comes only from the frozen structural risk-set semantics;
- raw bars are causal through t-1 only and are sealed before 2024.
"""

from __future__ import annotations

import math
from typing import Any, Final

import numpy as np
import pandas as pd

DATA_CUTOFF: Final = pd.Timestamp("2024-01-01T00:00:00Z")
PERIODS: Final = ("ROBUSTNESS_2022", "ROBUSTNESS_2023")
UNIVERSES: Final = ("C2", "D2", "E2")
LANDMARKS: Final = (24, 48, 72, 96, 120, 144)

MIN_POSITIONS: Final = 20
MIN_PAIRS: Final = 5
MIN_SIGNAL_DAYS: Final = 10
MIN_UNIVERSES_FOR_TRANSPORT: Final = 2

TRAIL_ARM_ATR: Final = 6.0
TRAIL_GAP_ATR: Final = 4.0

VALID = "RECONSTRUCTED_VALID"
MISSING_REQUIRED_HOURLY_BAR = "MISSING_REQUIRED_HOURLY_BAR"
INVALID_ENTRY_PRICE = "INVALID_ENTRY_PRICE"
INVALID_SIGNAL_ATR = "INVALID_SIGNAL_ATR"
INVALID_RAW_PRICE = "INVALID_RAW_PRICE"
GEOMETRY_VIOLATION = "GEOMETRY_VIOLATION"

SUCCESS_DECISION: Final = (
    "RD43_CONTROL_RELATIVE_STATE_RECONSTRUCTION_AND_SUPPORT_PASS_"
    "READY_FOR_DIRECT_UTILITY_PREREGISTRATION"
)
SUCCESS_NEXT: Final = (
    "RD43_P3_PREREGISTER_CONTROL_RELATIVE_STATE_DIRECT_UTILITY_EVALUATION_PRE_RCV_EXPOSURE"
)
DQ_BLOCK_DECISION: Final = (
    "RD43_CONTROL_RELATIVE_STATE_RECONSTRUCTION_DATA_QUALITY_BLOCK_NO_RCV_EXPOSURE"
)
DQ_BLOCK_NEXT: Final = (
    "RD43_REASSESS_RAW_BAR_COVERAGE_OR_RECONSTRUCTION_SEMANTICS_BEFORE_TARGET_EXPOSURE"
)
UNDERPOWERED_DECISION: Final = "RD43_CONTROL_RELATIVE_STATE_SUPPORT_UNDERPOWERED_NO_RCV_EXPOSURE"
UNDERPOWERED_NEXT: Final = "RD43_REASSESS_CONTROL_RELATIVE_STATE_SUPPORT_BEFORE_TARGET_EXPOSURE"


class RD43P2Error(RuntimeError):
    """Frozen RD43-P2 contract violation."""


def validate_constants() -> None:
    if PERIODS != ("ROBUSTNESS_2022", "ROBUSTNESS_2023"):
        raise RD43P2Error("period registry drifted")
    if UNIVERSES != ("C2", "D2", "E2"):
        raise RD43P2Error("universe registry drifted")
    if LANDMARKS != (24, 48, 72, 96, 120, 144):
        raise RD43P2Error("landmark registry drifted")
    if (
        MIN_POSITIONS != 20
        or MIN_PAIRS != 5
        or MIN_SIGNAL_DAYS != 10
        or MIN_UNIVERSES_FOR_TRANSPORT != 2
    ):
        raise RD43P2Error("support gates drifted")
    if not math.isclose(TRAIL_ARM_ATR, 6.0):
        raise RD43P2Error("trail arm drifted")
    if not math.isclose(TRAIL_GAP_ATR, 4.0):
        raise RD43P2Error("trail gap drifted")


def utc_series(values: pd.Series) -> pd.Series:
    return pd.to_datetime(values, utc=True, errors="raise").dt.as_unit("ns")


def normalize_raw_bars(
    raw: pd.DataFrame,
    *,
    cutoff: pd.Timestamp = DATA_CUTOFF,
) -> tuple[pd.DataFrame, int]:
    required = {"timestamp", "high", "close"}
    missing = sorted(required.difference(raw.columns))
    if missing:
        raise RD43P2Error(f"raw bars missing columns: {missing}")

    frame = raw.loc[:, ["timestamp", "high", "close"]].copy()
    frame["timestamp"] = utc_series(frame["timestamp"])
    frame["high"] = pd.to_numeric(frame["high"], errors="raise").astype(float)
    frame["close"] = pd.to_numeric(frame["close"], errors="raise").astype(float)

    duplicate_count = int(frame["timestamp"].duplicated(keep="last").sum())
    frame = (
        frame.sort_values("timestamp", kind="stable")
        .drop_duplicates("timestamp", keep="last")
        .reset_index(drop=True)
    )

    if len(frame) and frame["timestamp"].max() >= cutoff:
        raise RD43P2Error("2024+ raw bar entered memory")
    if bool((frame[["high", "close"]] <= 0.0).any().any()):
        raise RD43P2Error("non-positive raw high/close")
    if bool((frame["high"] + 1e-12 < frame["close"]).any()):
        raise RD43P2Error("raw bar high is below close")
    return frame, duplicate_count


def _empty_reconstruction(
    row: dict[str, Any],
    *,
    quality: str,
    expected_bar_count: int,
    observed_bar_count: int,
) -> dict[str, Any]:
    return {
        **row,
        "data_quality_class": quality,
        "expected_hourly_bar_count": expected_bar_count,
        "observed_hourly_bar_count": observed_bar_count,
        "entry_price": float(row["entry_price"]),
        "atr24_at_signal": float(row["atr24_at_signal"]),
        "completed_mark": np.nan,
        "completed_high_water": np.nan,
        "high_water_gain_atr": np.nan,
        "pullback_from_high_water_atr": np.nan,
        "current_mark_entry_distance_atr": np.nan,
        "profit_trail_arm_distance_atr": np.nan,
        "trail_armed_state": False,
        "profit_trail_floor_distance_atr_when_armed": np.nan,
    }


def reconstruct_decision(
    row: dict[str, Any],
    bars: pd.DataFrame,
) -> dict[str, Any]:
    validate_constants()

    entry_time = pd.Timestamp(row["entry_time"])
    decision_time = pd.Timestamp(row["decision_time"])
    completed_time = pd.Timestamp(row["completed_information_time"])
    if entry_time.tzinfo is None or decision_time.tzinfo is None:
        raise RD43P2Error("landmark timestamps must be timezone-aware")
    if completed_time != decision_time - pd.Timedelta(hours=1):
        raise RD43P2Error("completed-information boundary drifted")
    if decision_time >= DATA_CUTOFF:
        raise RD43P2Error("2024+ landmark decision entered reconstruction")

    landmark = int(row["landmark_age_hours"])
    expected_bar_count = landmark
    entry_price = float(row["entry_price"])
    atr = float(row["atr24_at_signal"])

    if not math.isfinite(entry_price) or entry_price <= 0.0:
        return _empty_reconstruction(
            row,
            quality=INVALID_ENTRY_PRICE,
            expected_bar_count=expected_bar_count,
            observed_bar_count=0,
        )
    if not math.isfinite(atr) or atr <= 0.0:
        return _empty_reconstruction(
            row,
            quality=INVALID_SIGNAL_ATR,
            expected_bar_count=expected_bar_count,
            observed_bar_count=0,
        )

    window = bars.loc[
        (bars["timestamp"] >= entry_time) & (bars["timestamp"] <= completed_time)
    ].copy()

    expected_times = pd.date_range(
        entry_time,
        completed_time,
        freq="h",
        inclusive="both",
    )
    observed_times = pd.DatetimeIndex(window["timestamp"])
    if (
        len(window) != expected_bar_count
        or len(expected_times) != expected_bar_count
        or not observed_times.equals(expected_times)
    ):
        return _empty_reconstruction(
            row,
            quality=MISSING_REQUIRED_HOURLY_BAR,
            expected_bar_count=expected_bar_count,
            observed_bar_count=int(len(window)),
        )

    highs = window["high"].to_numpy(float)
    closes = window["close"].to_numpy(float)
    if (
        not np.isfinite(highs).all()
        or not np.isfinite(closes).all()
        or np.any(highs <= 0.0)
        or np.any(closes <= 0.0)
    ):
        return _empty_reconstruction(
            row,
            quality=INVALID_RAW_PRICE,
            expected_bar_count=expected_bar_count,
            observed_bar_count=int(len(window)),
        )

    completed_mark = float(window.iloc[-1]["close"])
    high_water = float(max(entry_price, float(np.max(highs))))
    if high_water + 1e-12 < entry_price or high_water + 1e-12 < completed_mark:
        return _empty_reconstruction(
            row,
            quality=GEOMETRY_VIOLATION,
            expected_bar_count=expected_bar_count,
            observed_bar_count=int(len(window)),
        )

    high_water_gain = (high_water - entry_price) / atr
    pullback = (high_water - completed_mark) / atr
    mark_entry = (completed_mark - entry_price) / atr
    arm_distance = (entry_price + TRAIL_ARM_ATR * atr - high_water) / atr
    armed_direct = bool(high_water >= entry_price + TRAIL_ARM_ATR * atr)
    floor_distance = (
        (completed_mark - (high_water - TRAIL_GAP_ATR * atr)) / atr if armed_direct else np.nan
    )

    if high_water_gain < -1e-12 or pullback < -1e-12:
        return _empty_reconstruction(
            row,
            quality=GEOMETRY_VIOLATION,
            expected_bar_count=expected_bar_count,
            observed_bar_count=int(len(window)),
        )

    return {
        **row,
        "data_quality_class": VALID,
        "expected_hourly_bar_count": expected_bar_count,
        "observed_hourly_bar_count": int(len(window)),
        "entry_price": entry_price,
        "atr24_at_signal": atr,
        "completed_mark": completed_mark,
        "completed_high_water": high_water,
        "high_water_gain_atr": float(high_water_gain),
        "pullback_from_high_water_atr": float(pullback),
        "current_mark_entry_distance_atr": float(mark_entry),
        "profit_trail_arm_distance_atr": float(arm_distance),
        "trail_armed_state": armed_direct,
        "profit_trail_floor_distance_atr_when_armed": (
            float(floor_distance) if armed_direct else np.nan
        ),
    }


def reconstruct_ledger(
    landmark_rows: pd.DataFrame,
    position_state: pd.DataFrame,
    bar_frames: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    required_state = {
        "control_position_id",
        "entry_price",
        "atr24_at_signal",
    }
    missing = sorted(required_state.difference(position_state.columns))
    if missing:
        raise RD43P2Error(f"position state missing columns: {missing}")
    if position_state["control_position_id"].astype(str).duplicated().any():
        raise RD43P2Error("duplicate position state id")

    rows = landmark_rows.merge(
        position_state.loc[:, list(required_state)],
        on="control_position_id",
        how="left",
        validate="many_to_one",
    )
    if rows[["entry_price", "atr24_at_signal"]].isna().any().any():
        raise RD43P2Error("landmark row missing entry price or signal ATR")

    records: list[dict[str, Any]] = []
    total = len(rows)
    for index, raw in enumerate(rows.to_dict(orient="records"), start=1):
        pair = str(raw["pair"])
        bars = bar_frames.get(pair)
        if bars is None:
            raise RD43P2Error(f"raw frame missing for pair: {pair}")
        records.append(reconstruct_decision(raw, bars))
        if index % 250 == 0 or index == total:
            print(
                f"RD43_P2_RECONSTRUCTION_PROGRESS={index}/{total}",
                flush=True,
            )

    result = pd.DataFrame.from_records(records)
    if len(result) != len(landmark_rows):
        raise RD43P2Error("reconstruction ledger cardinality drifted")
    if result["decision_id"].astype(str).duplicated().any():
        raise RD43P2Error("duplicate reconstructed decision_id")
    return result.sort_values(
        [
            "decision_time",
            "universe_id",
            "control_position_id",
            "landmark_age_hours",
        ],
        kind="stable",
    ).reset_index(drop=True)


def signal_day_count(frame: pd.DataFrame) -> int:
    if frame.empty:
        return 0
    return int(
        pd.to_datetime(
            frame["signal_time"],
            utc=True,
            errors="raise",
        )
        .dt.floor("D")
        .nunique()
    )


def support_counts(frame: pd.DataFrame) -> dict[str, Any]:
    positions = int(frame["control_position_id"].astype(str).nunique())
    pairs = int(frame["pair"].astype(str).nunique())
    days = signal_day_count(frame)
    return {
        "decision_row_count": int(len(frame)),
        "unique_control_position_count": positions,
        "unique_pair_count": pairs,
        "unique_signal_day_count": days,
        "numeric_support_pass": bool(
            positions >= MIN_POSITIONS and pairs >= MIN_PAIRS and days >= MIN_SIGNAL_DAYS
        ),
    }


def support_census(ledger: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for period in PERIODS:
        for universe in UNIVERSES:
            for landmark in LANDMARKS:
                all_rows = ledger.loc[
                    (ledger["period_id"].astype(str) == period)
                    & (ledger["universe_id"].astype(str) == universe)
                    & (ledger["landmark_age_hours"] == landmark)
                ]
                valid_rows = all_rows.loc[all_rows["data_quality_class"].astype(str) == VALID]
                counts = support_counts(valid_rows)
                reconstruction_complete = bool(len(valid_rows) == len(all_rows))
                rows.append(
                    {
                        "period_id": period,
                        "universe_id": universe,
                        "landmark_age_hours": landmark,
                        "structural_decision_row_count": int(len(all_rows)),
                        **counts,
                        "minimum_unique_positions_gate": MIN_POSITIONS,
                        "minimum_unique_pairs_gate": MIN_PAIRS,
                        "minimum_unique_signal_days_gate": MIN_SIGNAL_DAYS,
                        "reconstruction_complete": reconstruction_complete,
                        "support_pass": bool(
                            reconstruction_complete and counts["numeric_support_pass"]
                        ),
                    }
                )
    result = pd.DataFrame.from_records(rows)
    expected = len(PERIODS) * len(UNIVERSES) * len(LANDMARKS)
    if len(result) != expected:
        raise RD43P2Error("support census cardinality drifted")
    return result


def data_quality_summary(ledger: pd.DataFrame) -> pd.DataFrame:
    classes = sorted(
        set(ledger["data_quality_class"].astype(str).unique())
        | {
            VALID,
            MISSING_REQUIRED_HOURLY_BAR,
            INVALID_ENTRY_PRICE,
            INVALID_SIGNAL_ATR,
            INVALID_RAW_PRICE,
            GEOMETRY_VIOLATION,
        }
    )
    rows: list[dict[str, Any]] = []
    for period in PERIODS:
        for universe in UNIVERSES:
            for landmark in LANDMARKS:
                base = ledger.loc[
                    (ledger["period_id"].astype(str) == period)
                    & (ledger["universe_id"].astype(str) == universe)
                    & (ledger["landmark_age_hours"] == landmark)
                ]
                total = len(base)
                for quality in classes:
                    cell = base.loc[base["data_quality_class"].astype(str) == quality]
                    rows.append(
                        {
                            "period_id": period,
                            "universe_id": universe,
                            "landmark_age_hours": landmark,
                            "data_quality_class": quality,
                            "decision_row_count": int(len(cell)),
                            "decision_row_fraction": (float(len(cell) / total) if total else 0.0),
                            "unique_control_position_count": int(
                                cell["control_position_id"].astype(str).nunique()
                            ),
                        }
                    )
    return pd.DataFrame.from_records(rows)


def transport_supported_landmarks(
    census: pd.DataFrame,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for landmark in LANDMARKS:
        counts: dict[str, int] = {}
        for period in PERIODS:
            cell = census.loc[
                (census["period_id"].astype(str) == period)
                & (census["landmark_age_hours"] == landmark)
            ]
            counts[period] = int(cell["support_pass"].astype(bool).sum())
        eligible = bool(
            counts["ROBUSTNESS_2022"] >= MIN_UNIVERSES_FOR_TRANSPORT
            and counts["ROBUSTNESS_2023"] >= MIN_UNIVERSES_FOR_TRANSPORT
        )
        rows.append(
            {
                "landmark_age_hours": int(landmark),
                "supported_universes_2022": counts["ROBUSTNESS_2022"],
                "supported_universes_2023": counts["ROBUSTNESS_2023"],
                "transport_support_eligible": eligible,
            }
        )
    return rows


def identity_parity(ledger: pd.DataFrame) -> dict[str, Any]:
    valid = ledger.loc[ledger["data_quality_class"].astype(str) == VALID].copy()
    if valid.empty:
        return {
            "status": "NO_VALID_ROWS",
            "valid_row_count": 0,
            "current_mark_entry_max_abs_error": None,
            "profit_trail_arm_distance_max_abs_error": None,
            "trail_armed_mismatch_count": None,
            "profit_trail_floor_distance_max_abs_error_when_armed": None,
            "all_identity_checks_pass": False,
        }

    current_identity = valid["high_water_gain_atr"] - valid["pullback_from_high_water_atr"]
    current_error = np.abs(
        current_identity.to_numpy(float) - valid["current_mark_entry_distance_atr"].to_numpy(float)
    )

    arm_identity = TRAIL_ARM_ATR - valid["high_water_gain_atr"]
    arm_error = np.abs(
        arm_identity.to_numpy(float) - valid["profit_trail_arm_distance_atr"].to_numpy(float)
    )

    armed_identity = valid["high_water_gain_atr"] >= TRAIL_ARM_ATR
    armed_direct = valid["trail_armed_state"].astype(bool)
    armed_mismatch = int((armed_identity != armed_direct).sum())

    armed_rows = valid.loc[armed_direct].copy()
    if len(armed_rows):
        floor_identity = TRAIL_GAP_ATR - armed_rows["pullback_from_high_water_atr"]
        floor_error = np.abs(
            floor_identity.to_numpy(float)
            - armed_rows["profit_trail_floor_distance_atr_when_armed"].to_numpy(float)
        )
        floor_max = float(np.max(floor_error))
    else:
        floor_max = 0.0

    current_max = float(np.max(current_error))
    arm_max = float(np.max(arm_error))
    tolerance = 1e-10
    all_pass = bool(
        current_max <= tolerance
        and arm_max <= tolerance
        and armed_mismatch == 0
        and floor_max <= tolerance
    )
    return {
        "status": "PASS" if all_pass else "FAIL",
        "valid_row_count": int(len(valid)),
        "armed_row_count": int(len(armed_rows)),
        "tolerance": tolerance,
        "current_mark_entry_max_abs_error": current_max,
        "profit_trail_arm_distance_max_abs_error": arm_max,
        "trail_armed_mismatch_count": armed_mismatch,
        "profit_trail_floor_distance_max_abs_error_when_armed": (floor_max),
        "all_identity_checks_pass": all_pass,
    }


def decide(
    ledger: pd.DataFrame,
    census: pd.DataFrame,
    identities: dict[str, Any],
) -> tuple[str, str]:
    invalid_count = int((ledger["data_quality_class"].astype(str) != VALID).sum())
    if invalid_count > 0 or not bool(identities["all_identity_checks_pass"]):
        return DQ_BLOCK_DECISION, DQ_BLOCK_NEXT

    transport = transport_supported_landmarks(census)
    if any(bool(item["transport_support_eligible"]) for item in transport):
        return SUCCESS_DECISION, SUCCESS_NEXT
    return UNDERPOWERED_DECISION, UNDERPOWERED_NEXT
