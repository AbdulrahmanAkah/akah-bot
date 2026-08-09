"""RD41-P2 full control risk-set and censoring reconciliation."""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any, Final

import pandas as pd

DATA_START: Final = pd.Timestamp("2022-01-01T00:00:00Z")
DATA_CUTOFF: Final = pd.Timestamp("2024-01-01T00:00:00Z")

CONTROL_POLICY_LABEL: Final = "RD31_REGIME_HYSTERESIS_CONTROL"
REPLAY_POLICY_ID: Final = "REGIME_HYSTERESIS_ADMISSION_GOVERNOR"
CONTROL_PORTFOLIO: Final = "UNION_FOCUS"
DIAGNOSTIC_COST_MULTIPLIER: Final = 1.0

UNIVERSES: Final = ("C2", "D2", "E2")
GOVERNOR_STATES: Final = ("OPEN", "CAUTION", "LOCKED")
LANDMARK_AGES_HOURS: Final = (24, 48, 72, 96, 120, 144)

RESOLVED: Final = "RESOLVED_CONTROL_OUTCOME"
CENSORED: Final = "RIGHT_CENSORED_AT_CUTOFF"
EXCLUDED_CONTRACT: Final = "EXCLUDED_CONTRACT_VIOLATION"

TIME_FAILURE: Final = "TIME_FAILURE_72H_CLOSE_NOT_ABOVE_ENTRY"
MAX_HOLD: Final = "MAX_HOLD_168H"
CENSORED_REASON: Final = "RIGHT_CENSORED_AT_CUTOFF"

ALLOWED_TERMINAL_REASONS: Final = (
    TIME_FAILURE,
    MAX_HOLD,
    CENSORED_REASON,
)

SUCCESS_DECISION: Final = (
    "RD41_FULL_RISK_SET_CENSORING_RECONCILIATION_PASS_READY_FOR_TARGET_DIAGNOSTIC_FREEZE"
)
SUCCESS_NEXT: Final = (
    "RD41_P3_PREREGISTER_AND_FREEZE_REMAINING_CONTROL_VALUE_TERMINAL_HAZARD_DIAGNOSTIC"
)


class RD41P2Error(RuntimeError):
    """Frozen RD41-P2 contract violation."""


def utc(value: Any) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        return timestamp.tz_localize("UTC")
    return timestamp.tz_convert("UTC")


def period_for_timestamp(value: Any) -> str:
    timestamp = utc(value)
    if pd.Timestamp("2022-01-01T00:00:00Z") <= timestamp < pd.Timestamp("2023-01-01T00:00:00Z"):
        return "ROBUSTNESS_2022"
    if pd.Timestamp("2023-01-01T00:00:00Z") <= timestamp < DATA_CUTOFF:
        return "ROBUSTNESS_2023"
    raise RD41P2Error(f"timestamp outside frozen periods: {timestamp}")


def original_completion_eligible(entry_time: Any) -> bool:
    entry = utc(entry_time)
    return bool(entry + pd.Timedelta(hours=168) < DATA_CUTOFF)


def validate_constants() -> None:
    if UNIVERSES != ("C2", "D2", "E2"):
        raise RD41P2Error("universe registry drifted")
    if GOVERNOR_STATES != ("OPEN", "CAUTION", "LOCKED"):
        raise RD41P2Error("governor-state registry drifted")
    if LANDMARK_AGES_HOURS != (24, 48, 72, 96, 120, 144):
        raise RD41P2Error("landmark grid drifted")
    if ALLOWED_TERMINAL_REASONS != (
        TIME_FAILURE,
        MAX_HOLD,
        CENSORED_REASON,
    ):
        raise RD41P2Error("terminal registry drifted")


def terminal_time(row: Mapping[str, Any]) -> pd.Timestamp:
    risk_class = str(row["risk_set_class"])
    if risk_class == RESOLVED:
        return utc(row["exit_time"])
    if risk_class == CENSORED:
        return DATA_CUTOFF
    raise RD41P2Error(f"non-position risk class in terminal_time: {risk_class}")


def position_open_at_landmark(
    row: Mapping[str, Any],
    *,
    landmark_age_hours: int,
) -> bool:
    if landmark_age_hours not in LANDMARK_AGES_HOURS:
        raise RD41P2Error(f"unexpected landmark: {landmark_age_hours}")
    entry = utc(row["entry_time"])
    landmark = entry + pd.Timedelta(hours=landmark_age_hours)
    return bool(landmark < DATA_CUTOFF and landmark < terminal_time(row))


def build_landmark_rows(
    risk_set: pd.DataFrame,
    governor_timelines: Mapping[str, Mapping[int, str]],
) -> pd.DataFrame:
    records: list[dict[str, Any]] = []
    for row in risk_set.to_dict(orient="records"):
        if str(row["risk_set_class"]) not in {RESOLVED, CENSORED}:
            continue
        universe = str(row["universe_id"])
        timeline = governor_timelines.get(universe)
        if timeline is None:
            raise RD41P2Error(f"missing governor timeline: {universe}")

        entry = utc(row["entry_time"])
        signal_time = utc(row["signal_time"])
        for age in LANDMARK_AGES_HOURS:
            if not position_open_at_landmark(
                row,
                landmark_age_hours=age,
            ):
                continue
            landmark = entry + pd.Timedelta(hours=age)
            state = timeline.get(int(landmark.value))
            if state not in GOVERNOR_STATES:
                raise RD41P2Error(f"missing governor state at landmark: {universe} {landmark}")
            records.append(
                {
                    "control_position_id": str(row["control_position_id"]),
                    "universe_id": universe,
                    "period_id": str(row["period_id"]),
                    "pair": str(row["pair"]),
                    "signal_time": signal_time,
                    "entry_time": entry,
                    "landmark_time": landmark,
                    "landmark_age_hours": age,
                    "governor_state": state,
                    "terminal_class": str(row["risk_set_class"]),
                    "resolved_target_available": (str(row["risk_set_class"]) == RESOLVED),
                    "right_censored_target": (str(row["risk_set_class"]) == CENSORED),
                }
            )
    return pd.DataFrame.from_records(records)


def summarize_landmarks_by_age(
    landmark_rows: pd.DataFrame,
) -> pd.DataFrame:
    records: list[dict[str, Any]] = []
    for period in ("ROBUSTNESS_2022", "ROBUSTNESS_2023"):
        for universe in UNIVERSES:
            for age in LANDMARK_AGES_HOURS:
                cell = landmark_rows.loc[
                    (landmark_rows["period_id"] == period)
                    & (landmark_rows["universe_id"] == universe)
                    & (landmark_rows["landmark_age_hours"] == age)
                ]
                records.append(
                    {
                        "period_id": period,
                        "universe_id": universe,
                        "landmark_age_hours": age,
                        "decision_row_count": int(len(cell)),
                        "unique_control_position_count": int(
                            cell["control_position_id"].astype(str).nunique()
                        ),
                        "unique_pair_count": int(cell["pair"].astype(str).nunique()),
                        "unique_signal_day_count": int(
                            pd.to_datetime(
                                cell["signal_time"],
                                utc=True,
                                errors="coerce",
                            )
                            .dt.floor("D")
                            .nunique()
                        ),
                        "resolved_target_count": int(
                            cell["resolved_target_available"].astype(bool).sum()
                        ),
                        "right_censored_target_count": int(
                            cell["right_censored_target"].astype(bool).sum()
                        ),
                        "minimum_unique_positions_gate": 20,
                        "minimum_unique_pairs_gate": 5,
                        "minimum_unique_signal_days_gate": 10,
                        "support_pass": bool(
                            cell["control_position_id"].astype(str).nunique() >= 20
                            and cell["pair"].astype(str).nunique() >= 5
                            and pd.to_datetime(
                                cell["signal_time"],
                                utc=True,
                                errors="coerce",
                            )
                            .dt.floor("D")
                            .nunique()
                            >= 10
                        ),
                    }
                )
    return pd.DataFrame.from_records(records)


def summarize_landmarks_by_governor(
    landmark_rows: pd.DataFrame,
) -> pd.DataFrame:
    records: list[dict[str, Any]] = []
    for period in ("ROBUSTNESS_2022", "ROBUSTNESS_2023"):
        for universe in UNIVERSES:
            for age in LANDMARK_AGES_HOURS:
                for state in GOVERNOR_STATES:
                    cell = landmark_rows.loc[
                        (landmark_rows["period_id"] == period)
                        & (landmark_rows["universe_id"] == universe)
                        & (landmark_rows["landmark_age_hours"] == age)
                        & (landmark_rows["governor_state"] == state)
                    ]
                    records.append(
                        {
                            "period_id": period,
                            "universe_id": universe,
                            "landmark_age_hours": age,
                            "governor_state": state,
                            "decision_row_count": int(len(cell)),
                            "unique_control_position_count": int(
                                cell["control_position_id"].astype(str).nunique()
                            ),
                            "unique_pair_count": int(cell["pair"].astype(str).nunique()),
                            "unique_signal_day_count": int(
                                pd.to_datetime(
                                    cell["signal_time"],
                                    utc=True,
                                    errors="coerce",
                                )
                                .dt.floor("D")
                                .nunique()
                            ),
                            "resolved_target_count": int(
                                cell["resolved_target_available"].astype(bool).sum()
                            ),
                            "right_censored_target_count": int(
                                cell["right_censored_target"].astype(bool).sum()
                            ),
                            "diagnostic_only": True,
                            "governor_is_binary_exit_permission": False,
                        }
                    )
    return pd.DataFrame.from_records(records)


def numeric_tolerance(left: pd.Series) -> pd.Series:
    values = pd.to_numeric(left, errors="raise").astype(float)
    return 1e-9 * (1.0 + values.abs())


def compare_resolved_overlap(
    *,
    current_risk_set: pd.DataFrame,
    frozen_reference: pd.DataFrame,
) -> pd.DataFrame:
    current = current_risk_set.loc[
        (current_risk_set["risk_set_class"] == RESOLVED)
        & current_risk_set["original_completion_eligible"].astype(bool)
    ].copy()
    reference = frozen_reference.copy()

    keys = [
        "universe_id",
        "pair",
        "entry_time",
        "exit_time",
    ]
    for frame in (current, reference):
        frame["entry_time"] = pd.to_datetime(
            frame["entry_time"],
            utc=True,
            errors="raise",
        )
        frame["exit_time"] = pd.to_datetime(
            frame["exit_time"],
            utc=True,
            errors="raise",
        )

    records: list[dict[str, Any]] = []
    for universe in (*UNIVERSES, "ALL"):
        left = (
            (
                current
                if universe == "ALL"
                else current.loc[current["universe_id"].astype(str) == universe]
            )
            .sort_values(keys, kind="stable")
            .reset_index(drop=True)
        )
        right = (
            (
                reference
                if universe == "ALL"
                else reference.loc[reference["universe_id"].astype(str) == universe]
            )
            .sort_values(keys, kind="stable")
            .reset_index(drop=True)
        )

        row_count_match = len(left) == len(right)
        key_match = bool(row_count_match)
        if row_count_match:
            for key in keys:
                if key in {"entry_time", "exit_time"}:
                    key_match = key_match and bool(
                        left[key].astype("int64").tolist() == right[key].astype("int64").tolist()
                    )
                else:
                    key_match = key_match and bool(
                        left[key].astype(str).tolist() == right[key].astype(str).tolist()
                    )

        exit_reason_match = bool(
            row_count_match
            and left["exit_reason"].astype(str).tolist()
            == right["exit_reason"].astype(str).tolist()
        )

        max_entry_error = math.nan
        max_exit_error = math.nan
        price_match = False
        if row_count_match:
            entry_error = (
                pd.to_numeric(left["entry_price"], errors="raise").astype(float)
                - pd.to_numeric(right["entry_price"], errors="raise").astype(float)
            ).abs()
            exit_error = (
                pd.to_numeric(left["exit_price"], errors="raise").astype(float)
                - pd.to_numeric(right["exit_price"], errors="raise").astype(float)
            ).abs()
            max_entry_error = float(entry_error.max()) if len(entry_error) else 0.0
            max_exit_error = float(exit_error.max()) if len(exit_error) else 0.0
            entry_ok = bool(
                (
                    entry_error
                    <= numeric_tolerance(
                        pd.to_numeric(
                            right["entry_price"],
                            errors="raise",
                        )
                    )
                ).all()
            )
            exit_ok = bool(
                (
                    exit_error
                    <= numeric_tolerance(
                        pd.to_numeric(
                            right["exit_price"],
                            errors="raise",
                        )
                    )
                ).all()
            )
            price_match = entry_ok and exit_ok

        parity_pass = bool(row_count_match and key_match and exit_reason_match and price_match)
        records.append(
            {
                "universe_id": universe,
                "frozen_reference_count": int(len(right)),
                "reconstructed_overlap_count": int(len(left)),
                "row_count_match": row_count_match,
                "key_match": key_match,
                "exit_reason_match": exit_reason_match,
                "price_match": price_match,
                "maximum_entry_price_absolute_error": max_entry_error,
                "maximum_exit_price_absolute_error": max_exit_error,
                "parity_pass": parity_pass,
            }
        )

    return pd.DataFrame.from_records(records)
