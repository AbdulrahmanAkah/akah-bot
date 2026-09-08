"""RD44-P2 target-blind control-relative-dynamics reconstruction.

Research-data scope:
- frozen structural control risk set / age census;
- causal hourly high/close bars strictly before 2024;
- no RCV, outcome utility, predictive model, threshold, context selection,
  action mapping, or portfolio replay.

The three frozen RD44-P1 dynamic axes are reconstructed exactly:
1) time since completed high water;
2) recent 12h high-water increment / frozen signal ATR;
3) recent 12h pullback change / frozen signal ATR.
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
DYNAMIC_WINDOW_HOURS: Final = 12

MIN_POSITIONS: Final = 20
MIN_PAIRS: Final = 5
MIN_SIGNAL_DAYS: Final = 10
MIN_UNIVERSES_FOR_TRANSPORT: Final = 2

VALID: Final = "RECONSTRUCTED_VALID"
MISSING_REQUIRED_HOURLY_BAR: Final = "MISSING_REQUIRED_HOURLY_BAR"
INVALID_ENTRY_PRICE: Final = "INVALID_ENTRY_PRICE"
INVALID_SIGNAL_ATR: Final = "INVALID_SIGNAL_ATR"
INVALID_RAW_PRICE: Final = "INVALID_RAW_PRICE"
GEOMETRY_VIOLATION: Final = "GEOMETRY_VIOLATION"
REFERENCE_BOUNDARY_VIOLATION: Final = "REFERENCE_BOUNDARY_VIOLATION"
TIME_IDENTITY_VIOLATION: Final = "TIME_IDENTITY_VIOLATION"

QUALITY_CLASSES: Final = (
    VALID,
    MISSING_REQUIRED_HOURLY_BAR,
    INVALID_ENTRY_PRICE,
    INVALID_SIGNAL_ATR,
    INVALID_RAW_PRICE,
    GEOMETRY_VIOLATION,
    REFERENCE_BOUNDARY_VIOLATION,
    TIME_IDENTITY_VIOLATION,
)

SUCCESS_DECISION: Final = (
    "RD44_CONTROL_RELATIVE_DYNAMICS_RECONSTRUCTION_AND_SUPPORT_PASS_"
    "READY_FOR_DIRECT_UTILITY_PREREGISTRATION"
)
SUCCESS_NEXT: Final = (
    "RD44_P3_PREREGISTER_CONTROL_RELATIVE_DYNAMICS_DIRECT_UTILITY_EVALUATION_PRE_RCV_EXPOSURE"
)
DQ_BLOCK_DECISION: Final = (
    "RD44_CONTROL_RELATIVE_DYNAMICS_RECONSTRUCTION_DATA_QUALITY_BLOCK_NO_RCV_EXPOSURE"
)
DQ_BLOCK_NEXT: Final = (
    "RD44_REASSESS_DYNAMIC_RECONSTRUCTION_OR_RAW_BAR_COVERAGE_BEFORE_TARGET_EXPOSURE"
)
UNDERPOWERED_DECISION: Final = "RD44_CONTROL_RELATIVE_DYNAMICS_SUPPORT_UNDERPOWERED_NO_RCV_EXPOSURE"
UNDERPOWERED_NEXT: Final = "RD44_REASSESS_DYNAMIC_INFORMATION_SOURCE_SUPPORT_BEFORE_TARGET_EXPOSURE"


class RD44P2Error(RuntimeError):
    """Frozen RD44-P2 contract violation."""


def validate_constants() -> None:
    if PERIODS != ("ROBUSTNESS_2022", "ROBUSTNESS_2023"):
        raise RD44P2Error("period registry drifted")
    if UNIVERSES != ("C2", "D2", "E2"):
        raise RD44P2Error("universe registry drifted")
    if LANDMARKS != (24, 48, 72, 96, 120, 144):
        raise RD44P2Error("landmark registry drifted")
    if DYNAMIC_WINDOW_HOURS != 12:
        raise RD44P2Error("dynamic window drifted")
    if (
        MIN_POSITIONS != 20
        or MIN_PAIRS != 5
        or MIN_SIGNAL_DAYS != 10
        or MIN_UNIVERSES_FOR_TRANSPORT != 2
    ):
        raise RD44P2Error("support gates drifted")


def utc_series(values: pd.Series) -> pd.Series:
    return pd.to_datetime(values, utc=True, errors="raise").dt.as_unit("ns")


def normalize_raw_bars(
    raw: pd.DataFrame,
    *,
    cutoff: pd.Timestamp = DATA_CUTOFF,
) -> tuple[pd.DataFrame, int]:
    validate_constants()
    required = {"timestamp", "high", "close"}
    missing = sorted(required.difference(raw.columns))
    if missing:
        raise RD44P2Error(f"raw bars missing columns: {missing}")

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
        raise RD44P2Error("2024+ raw bar entered memory")
    if bool((frame[["high", "close"]] <= 0.0).any().any()):
        raise RD44P2Error("non-positive raw high/close")
    if bool((frame["high"] + 1e-12 < frame["close"]).any()):
        raise RD44P2Error("raw bar high is below close")
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
        "reference_time_12h": pd.NaT,
        "audit_reference_mark_12h": np.nan,
        "audit_completed_mark": np.nan,
        "audit_reference_high_water_12h": np.nan,
        "audit_completed_high_water": np.nan,
        "audit_completed_high_water_time": pd.NaT,
        "time_since_completed_high_water_hours": np.nan,
        "recent_12h_high_water_increment_atr": np.nan,
        "audit_reference_pullback_atr": np.nan,
        "audit_completed_pullback_atr": np.nan,
        "recent_12h_pullback_change_atr": np.nan,
        "audit_recent_12h_mark_change_atr": np.nan,
        "audit_recent_mark_change_identity_residual": np.nan,
        "audit_completed_high_water_time_expected": pd.NaT,
        "audit_strict_high_water_time_match": False,
    }


def _first_time_of_final_high_water(
    *,
    entry_time: pd.Timestamp,
    entry_price: float,
    window: pd.DataFrame,
    final_high_water: float,
) -> pd.Timestamp:
    if final_high_water <= entry_price:
        return entry_time
    matches = window.loc[window["high"].astype(float) == final_high_water]
    if matches.empty:
        raise RD44P2Error("final high-water value has no source bar")
    return pd.Timestamp(matches.iloc[0]["timestamp"])


def reconstruct_decision(
    row: dict[str, Any],
    bars: pd.DataFrame,
) -> dict[str, Any]:
    validate_constants()

    entry_time = pd.Timestamp(row["entry_time"])
    decision_time = pd.Timestamp(row["decision_time"])
    completed_time = pd.Timestamp(row["completed_information_time"])
    if entry_time.tzinfo is None or decision_time.tzinfo is None or completed_time.tzinfo is None:
        raise RD44P2Error("landmark timestamps must be timezone-aware")

    if completed_time != decision_time - pd.Timedelta(hours=1):
        raise RD44P2Error("completed-information boundary drifted")
    if decision_time >= DATA_CUTOFF:
        raise RD44P2Error("2024+ decision entered reconstruction")

    landmark = int(row["landmark_age_hours"])
    if landmark not in LANDMARKS:
        raise RD44P2Error(f"unsupported landmark: {landmark}")
    expected_bar_count = landmark

    expected_decision = entry_time + pd.Timedelta(hours=landmark)
    if decision_time != expected_decision:
        raise RD44P2Error("decision-time landmark identity drifted")

    reference_time = completed_time - pd.Timedelta(hours=DYNAMIC_WINDOW_HOURS)
    expected_reference = decision_time - pd.Timedelta(hours=DYNAMIC_WINDOW_HOURS + 1)
    if reference_time != expected_reference or not reference_time >= entry_time:
        return _empty_reconstruction(
            row,
            quality=REFERENCE_BOUNDARY_VIOLATION,
            expected_bar_count=expected_bar_count,
            observed_bar_count=0,
        )

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
        or np.any(highs + 1e-12 < closes)
    ):
        return _empty_reconstruction(
            row,
            quality=INVALID_RAW_PRICE,
            expected_bar_count=expected_bar_count,
            observed_bar_count=int(len(window)),
        )

    reference_rows = window.loc[window["timestamp"] == reference_time]
    completed_rows = window.loc[window["timestamp"] == completed_time]
    if len(reference_rows) != 1 or len(completed_rows) != 1:
        return _empty_reconstruction(
            row,
            quality=REFERENCE_BOUNDARY_VIOLATION,
            expected_bar_count=expected_bar_count,
            observed_bar_count=int(len(window)),
        )

    high_water = entry_price
    high_water_time = entry_time
    reference_high_water: float | None = None
    reference_mark: float | None = None

    for raw in window.to_dict(orient="records"):
        timestamp = pd.Timestamp(raw["timestamp"])
        high = float(raw["high"])
        if high > high_water:
            high_water = high
            high_water_time = timestamp
        if timestamp == reference_time:
            reference_high_water = high_water
            reference_mark = float(raw["close"])

    if reference_high_water is None or reference_mark is None:
        return _empty_reconstruction(
            row,
            quality=REFERENCE_BOUNDARY_VIOLATION,
            expected_bar_count=expected_bar_count,
            observed_bar_count=int(len(window)),
        )

    completed_mark = float(completed_rows.iloc[0]["close"])
    completed_high_water = float(high_water)
    completed_high_water_time = pd.Timestamp(high_water_time)

    if (
        reference_high_water + 1e-12 < entry_price
        or completed_high_water + 1e-12 < reference_high_water
        or reference_high_water + 1e-12 < reference_mark
        or completed_high_water + 1e-12 < completed_mark
    ):
        return _empty_reconstruction(
            row,
            quality=GEOMETRY_VIOLATION,
            expected_bar_count=expected_bar_count,
            observed_bar_count=int(len(window)),
        )

    expected_final_high_water = float(max(entry_price, float(np.max(highs))))
    expected_high_water_time = _first_time_of_final_high_water(
        entry_time=entry_time,
        entry_price=entry_price,
        window=window,
        final_high_water=expected_final_high_water,
    )
    strict_time_match = bool(completed_high_water_time == expected_high_water_time)
    if (
        not math.isclose(
            completed_high_water,
            expected_final_high_water,
            rel_tol=0.0,
            abs_tol=1e-12,
        )
        or not strict_time_match
    ):
        return _empty_reconstruction(
            row,
            quality=TIME_IDENTITY_VIOLATION,
            expected_bar_count=expected_bar_count,
            observed_bar_count=int(len(window)),
        )

    age_float = (completed_time - completed_high_water_time).total_seconds() / 3600.0
    age_round = round(age_float)
    if age_float < -1e-12 or not math.isclose(
        age_float,
        float(age_round),
        rel_tol=0.0,
        abs_tol=1e-12,
    ):
        return _empty_reconstruction(
            row,
            quality=TIME_IDENTITY_VIOLATION,
            expected_bar_count=expected_bar_count,
            observed_bar_count=int(len(window)),
        )

    recent_high_water_increment = (completed_high_water - reference_high_water) / atr
    reference_pullback = (reference_high_water - reference_mark) / atr
    completed_pullback = (completed_high_water - completed_mark) / atr
    pullback_change = completed_pullback - reference_pullback
    recent_mark_change = (completed_mark - reference_mark) / atr
    identity_residual = recent_high_water_increment - pullback_change - recent_mark_change

    if recent_high_water_increment < -1e-12:
        return _empty_reconstruction(
            row,
            quality=GEOMETRY_VIOLATION,
            expected_bar_count=expected_bar_count,
            observed_bar_count=int(len(window)),
        )
    if reference_pullback < -1e-12 or completed_pullback < -1e-12:
        return _empty_reconstruction(
            row,
            quality=GEOMETRY_VIOLATION,
            expected_bar_count=expected_bar_count,
            observed_bar_count=int(len(window)),
        )
    if abs(identity_residual) > 1e-10:
        return _empty_reconstruction(
            row,
            quality=TIME_IDENTITY_VIOLATION,
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
        "reference_time_12h": reference_time,
        "audit_reference_mark_12h": float(reference_mark),
        "audit_completed_mark": completed_mark,
        "audit_reference_high_water_12h": float(reference_high_water),
        "audit_completed_high_water": completed_high_water,
        "audit_completed_high_water_time": completed_high_water_time,
        "time_since_completed_high_water_hours": float(age_round),
        "recent_12h_high_water_increment_atr": float(recent_high_water_increment),
        "audit_reference_pullback_atr": float(reference_pullback),
        "audit_completed_pullback_atr": float(completed_pullback),
        "recent_12h_pullback_change_atr": float(pullback_change),
        "audit_recent_12h_mark_change_atr": float(recent_mark_change),
        "audit_recent_mark_change_identity_residual": float(identity_residual),
        "audit_completed_high_water_time_expected": expected_high_water_time,
        "audit_strict_high_water_time_match": strict_time_match,
    }


def reconstruct_ledger(
    landmark_rows: pd.DataFrame,
    position_state: pd.DataFrame,
    bar_frames: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    validate_constants()
    required_state = {
        "control_position_id",
        "entry_price",
        "atr24_at_signal",
    }
    missing = sorted(required_state.difference(position_state.columns))
    if missing:
        raise RD44P2Error(f"position state missing columns: {missing}")
    if position_state["control_position_id"].astype(str).duplicated().any():
        raise RD44P2Error("duplicate position state id")

    rows = landmark_rows.merge(
        position_state.loc[:, list(required_state)],
        on="control_position_id",
        how="left",
        validate="many_to_one",
    )
    if rows[["entry_price", "atr24_at_signal"]].isna().any().any():
        raise RD44P2Error("landmark row missing entry price or frozen signal ATR")

    records: list[dict[str, Any]] = []
    total = len(rows)
    for index, raw in enumerate(rows.to_dict(orient="records"), start=1):
        pair = str(raw["pair"])
        bars = bar_frames.get(pair)
        if bars is None:
            raise RD44P2Error(f"raw frame missing for pair: {pair}")
        records.append(reconstruct_decision(raw, bars))
        if index % 250 == 0 or index == total:
            print(
                f"RD44_P2_RECONSTRUCTION_PROGRESS={index}/{total}",
                flush=True,
            )

    result = pd.DataFrame.from_records(records)
    if len(result) != len(landmark_rows):
        raise RD44P2Error("reconstruction ledger cardinality drifted")
    if result["decision_id"].astype(str).duplicated().any():
        raise RD44P2Error("duplicate reconstructed decision_id")
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
                    & (ledger["landmark_age_hours"].astype(int) == landmark)
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
                        "reconstruction_complete": (reconstruction_complete),
                        "support_pass": bool(
                            reconstruction_complete and counts["numeric_support_pass"]
                        ),
                    }
                )
    result = pd.DataFrame.from_records(rows)
    expected = len(PERIODS) * len(UNIVERSES) * len(LANDMARKS)
    if len(result) != expected:
        raise RD44P2Error("support census cardinality drifted")
    return result


def data_quality_summary(ledger: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for quality in QUALITY_CLASSES:
        frame = ledger.loc[ledger["data_quality_class"].astype(str) == quality]
        rows.append(
            {
                "data_quality_class": quality,
                "row_count": int(len(frame)),
                "unique_position_count": int(frame["control_position_id"].astype(str).nunique()),
            }
        )
    return pd.DataFrame.from_records(rows)


def dynamic_identity_parity(
    ledger: pd.DataFrame,
    *,
    tolerance: float = 1e-10,
) -> dict[str, Any]:
    valid = ledger.loc[ledger["data_quality_class"].astype(str) == VALID].copy()
    if valid.empty:
        return {
            "schema_version": "rd44-p2-dynamic-identity-parity-v1",
            "status": "FAIL",
            "identity_parity_pass": False,
            "valid_row_count": 0,
        }

    numeric_columns = (
        "time_since_completed_high_water_hours",
        "recent_12h_high_water_increment_atr",
        "audit_reference_pullback_atr",
        "audit_completed_pullback_atr",
        "recent_12h_pullback_change_atr",
        "audit_recent_12h_mark_change_atr",
        "audit_recent_mark_change_identity_residual",
    )
    for column in numeric_columns:
        values = pd.to_numeric(valid[column], errors="raise").to_numpy(float)
        if not np.isfinite(values).all():
            raise RD44P2Error(f"identity column non-finite: {column}")

    age = pd.to_numeric(
        valid["time_since_completed_high_water_hours"],
        errors="raise",
    ).to_numpy(float)
    increment = pd.to_numeric(
        valid["recent_12h_high_water_increment_atr"],
        errors="raise",
    ).to_numpy(float)
    residual = pd.to_numeric(
        valid["audit_recent_mark_change_identity_residual"],
        errors="raise",
    ).to_numpy(float)
    strict_match = valid["audit_strict_high_water_time_match"].astype(bool)

    reference_hw = pd.to_numeric(
        valid["audit_reference_high_water_12h"],
        errors="raise",
    ).to_numpy(float)
    completed_hw = pd.to_numeric(
        valid["audit_completed_high_water"],
        errors="raise",
    ).to_numpy(float)

    age_integer_error = np.abs(age - np.round(age))
    max_age_integer_error = float(age_integer_error.max())
    max_mark_identity_error = float(np.abs(residual).max())
    minimum_increment = float(increment.min())
    minimum_hw_difference = float((completed_hw - reference_hw).min())

    completed_times = pd.to_datetime(
        valid["completed_information_time"],
        utc=True,
        errors="raise",
    )
    high_water_times = pd.to_datetime(
        valid["audit_completed_high_water_time"],
        utc=True,
        errors="raise",
    )
    recomputed_age = (completed_times - high_water_times).dt.total_seconds().to_numpy(
        float
    ) / 3600.0
    max_age_reconstruction_error = float(np.abs(recomputed_age - age).max())

    parity = bool(
        strict_match.all()
        and max_age_integer_error <= tolerance
        and max_age_reconstruction_error <= tolerance
        and max_mark_identity_error <= tolerance
        and minimum_increment >= -tolerance
        and minimum_hw_difference >= -tolerance
    )

    return {
        "schema_version": "rd44-p2-dynamic-identity-parity-v1",
        "status": "PASS" if parity else "FAIL",
        "identity_parity_pass": parity,
        "valid_row_count": int(len(valid)),
        "strict_high_water_time_match_row_count": int(strict_match.sum()),
        "strict_high_water_time_mismatch_row_count": int((~strict_match).sum()),
        "maximum_time_since_high_water_integer_error": (max_age_integer_error),
        "maximum_time_since_high_water_reconstruction_error": (max_age_reconstruction_error),
        "maximum_recent_mark_change_identity_error": (max_mark_identity_error),
        "minimum_recent_12h_high_water_increment_atr": (minimum_increment),
        "minimum_completed_minus_reference_high_water": (minimum_hw_difference),
        "numeric_tolerance": tolerance,
        "recent_mark_change_checked_as_identity_only": True,
        "recent_mark_change_is_candidate_feature": False,
        "equal_high_resets_recency": False,
    }


def transport_supported_landmarks(
    census: pd.DataFrame,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for landmark in LANDMARKS:
        item: dict[str, Any] = {
            "landmark_age_hours": landmark,
        }
        transport = True
        for period, suffix in (
            ("ROBUSTNESS_2022", "2022"),
            ("ROBUSTNESS_2023", "2023"),
        ):
            cell = census.loc[
                (census["period_id"].astype(str) == period)
                & (census["landmark_age_hours"].astype(int) == landmark)
            ]
            supported = int(cell["support_pass"].astype(bool).sum())
            item[f"supported_universes_{suffix}"] = supported
            if supported < MIN_UNIVERSES_FOR_TRANSPORT:
                transport = False
        item["transport_support_eligible"] = transport
        rows.append(item)
    return rows


def decide(
    *,
    ledger: pd.DataFrame,
    census: pd.DataFrame,
    parity: dict[str, Any],
) -> tuple[str, str, list[int]]:
    invalid = int((ledger["data_quality_class"].astype(str) != VALID).sum())
    if invalid:
        return DQ_BLOCK_DECISION, DQ_BLOCK_NEXT, []
    if parity.get("identity_parity_pass") is not True:
        return DQ_BLOCK_DECISION, DQ_BLOCK_NEXT, []

    transport = transport_supported_landmarks(census)
    qualified = [
        int(row["landmark_age_hours"])
        for row in transport
        if bool(row["transport_support_eligible"])
    ]
    if not qualified:
        return UNDERPOWERED_DECISION, UNDERPOWERED_NEXT, []
    return SUCCESS_DECISION, SUCCESS_NEXT, qualified
