"""RD42-P2 causal market-context reconciliation and support census.

This module is structural only. It does not load or compute RCV, PnL, prices,
hazard labels, predictive features, models, thresholds, or actions.
"""

from __future__ import annotations

from typing import Any, Final

import pandas as pd

DATA_START: Final = pd.Timestamp("2022-01-01T00:00:00Z")
DATA_CUTOFF: Final = pd.Timestamp("2024-01-01T00:00:00Z")

PERIODS: Final = ("ROBUSTNESS_2022", "ROBUSTNESS_2023")
UNIVERSES: Final = ("C2", "D2", "E2")
LANDMARKS: Final = (24, 48, 72, 96, 120, 144)
CONTEXTS: Final = ("SUPPORTIVE", "MIXED", "STRESSED", "UNAVAILABLE")

RESOLVED = "RESOLVED_CONTROL_OUTCOME"
RIGHT_CENSORED = "RIGHT_CENSORED_AT_CUTOFF"
RISK_CLASSES: Final = (RESOLVED, RIGHT_CENSORED)

MIN_POSITIONS: Final = 20
MIN_PAIRS: Final = 5
MIN_SIGNAL_DAYS: Final = 10
MIN_UNIVERSES_FOR_TRANSPORT: Final = 2

STRUCTURAL_RISK_COLUMNS: Final = (
    "universe_id",
    "period_id",
    "pair",
    "signal_time",
    "entry_time",
    "exit_time",
    "control_position_id",
    "risk_set_class",
    "censor_time",
)

FORBIDDEN_ANALYTIC_COLUMNS: Final = (
    "rcv_return",
    "rcv_dollars",
    "net_pnl",
    "gross_pnl",
    "entry_price",
    "exit_price",
    "time_failure_event",
    "exit_reason",
)

SUCCESS_DECISION: Final = (
    "RD42_CAUSAL_CONTEXT_SUPPORT_CENSUS_PASS_READY_FOR_SUPPORTED_CONTEXT_FEATURE_PREREGISTRATION"
)
SUCCESS_NEXT: Final = (
    "RD42_P3_PREREGISTER_DIRECT_UTILITY_FEATURE_HYPOTHESES_WITH_SUPPORTED_CAUSAL_CONTEXT_STRATA"
)
UNDERPOWERED_DECISION: Final = (
    "RD42_CAUSAL_CONTEXT_STRATIFICATION_UNDERPOWERED_"
    "NO_TARGET_EXPOSURE_REASSESS_CONTEXT_REPRESENTATION"
)
UNDERPOWERED_NEXT: Final = (
    "RD42_P3_PREREGISTER_DIRECT_UTILITY_FEATURE_HYPOTHESES_"
    "WITH_CONTEXT_AS_DESCRIPTIVE_MODIFIER_ONLY"
)


class RD42P2Error(RuntimeError):
    """Frozen RD42-P2 structural contract violation."""


def validate_constants() -> None:
    if PERIODS != ("ROBUSTNESS_2022", "ROBUSTNESS_2023"):
        raise RD42P2Error("period registry drifted")
    if UNIVERSES != ("C2", "D2", "E2"):
        raise RD42P2Error("universe registry drifted")
    if LANDMARKS != (24, 48, 72, 96, 120, 144):
        raise RD42P2Error("landmark registry drifted")
    if CONTEXTS != ("SUPPORTIVE", "MIXED", "STRESSED", "UNAVAILABLE"):
        raise RD42P2Error("context registry drifted")
    if (
        MIN_POSITIONS != 20
        or MIN_PAIRS != 5
        or MIN_SIGNAL_DAYS != 10
        or MIN_UNIVERSES_FOR_TRANSPORT != 2
    ):
        raise RD42P2Error("support gate registry drifted")
    if set(STRUCTURAL_RISK_COLUMNS).intersection(FORBIDDEN_ANALYTIC_COLUMNS):
        raise RD42P2Error("structural risk column registry leaked analytic fields")


def _utc_series(values: pd.Series) -> pd.Series:
    return pd.to_datetime(values, utc=True, errors="raise").dt.as_unit("ns")


def normalize_structural_risk_set(frame: pd.DataFrame) -> pd.DataFrame:
    validate_constants()
    missing = sorted(set(STRUCTURAL_RISK_COLUMNS).difference(frame.columns))
    if missing:
        raise RD42P2Error(f"structural risk set missing columns: {missing}")
    leaked = sorted(set(FORBIDDEN_ANALYTIC_COLUMNS).intersection(frame.columns))
    if leaked:
        raise RD42P2Error(f"analytic columns entered structural risk memory: {leaked}")

    result = frame.loc[:, list(STRUCTURAL_RISK_COLUMNS)].copy()
    for column in ("signal_time", "entry_time"):
        result[column] = _utc_series(result[column])

    result["exit_time"] = pd.to_datetime(
        result["exit_time"],
        utc=True,
        errors="coerce",
    ).dt.as_unit("ns")
    result["censor_time"] = pd.to_datetime(
        result["censor_time"],
        utc=True,
        errors="coerce",
    ).dt.as_unit("ns")

    if result["control_position_id"].astype(str).duplicated().any():
        raise RD42P2Error("duplicate control_position_id in risk set")
    if not set(result["universe_id"].astype(str)).issubset(UNIVERSES):
        raise RD42P2Error("unexpected universe in risk set")
    if not set(result["period_id"].astype(str)).issubset(PERIODS):
        raise RD42P2Error("unexpected period in risk set")
    if not set(result["risk_set_class"].astype(str)).issubset(RISK_CLASSES):
        raise RD42P2Error("unexpected risk-set class")

    resolved = result["risk_set_class"].astype(str) == RESOLVED
    censored = result["risk_set_class"].astype(str) == RIGHT_CENSORED
    if result.loc[resolved, "exit_time"].isna().any():
        raise RD42P2Error("resolved control position missing exit_time")
    if result.loc[censored, "censor_time"].isna().any():
        raise RD42P2Error("censored control position missing censor_time")
    if result.loc[censored, "exit_time"].notna().any():
        raise RD42P2Error("censored control position unexpectedly has exit_time")

    if bool((result["entry_time"] < DATA_START).any()):
        raise RD42P2Error("pre-2022 control entry entered RD42-P2")
    if bool((result["entry_time"] >= DATA_CUTOFF).any()):
        raise RD42P2Error("2024+ control entry entered RD42-P2")
    return result


def build_landmark_risk_rows(risk_set: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for raw in risk_set.to_dict(orient="records"):
        risk_class = str(raw["risk_set_class"])
        terminal_time = (
            pd.Timestamp(raw["exit_time"])
            if risk_class == RESOLVED
            else pd.Timestamp(raw["censor_time"])
        )
        entry_time = pd.Timestamp(raw["entry_time"])
        for landmark in LANDMARKS:
            decision_time = entry_time + pd.Timedelta(hours=landmark)
            if not decision_time < terminal_time:
                continue
            rows.append(
                {
                    "decision_id": (f"{raw['control_position_id']}|{landmark:03d}h"),
                    "control_position_id": str(raw["control_position_id"]),
                    "universe_id": str(raw["universe_id"]),
                    "period_id": str(raw["period_id"]),
                    "pair": str(raw["pair"]),
                    "signal_time": pd.Timestamp(raw["signal_time"]),
                    "entry_time": entry_time,
                    "decision_time": decision_time,
                    "completed_information_time": (decision_time - pd.Timedelta(hours=1)),
                    "landmark_age_hours": int(landmark),
                    "risk_set_class": risk_class,
                    "resolved_target": risk_class == RESOLVED,
                    "right_censored_target": risk_class == RIGHT_CENSORED,
                }
            )
    frame = pd.DataFrame.from_records(rows)
    if frame.empty:
        raise RD42P2Error("landmark risk set is empty")
    if frame["decision_id"].astype(str).duplicated().any():
        raise RD42P2Error("duplicate landmark decision_id")
    if bool((frame["decision_time"] >= DATA_CUTOFF).any()):
        raise RD42P2Error("2024+ decision row entered RD42-P2")
    return frame.sort_values(
        [
            "decision_time",
            "universe_id",
            "control_position_id",
            "landmark_age_hours",
        ],
        kind="stable",
    ).reset_index(drop=True)


def _signal_day_count(frame: pd.DataFrame) -> int:
    if frame.empty:
        return 0
    return int(
        pd.to_datetime(frame["signal_time"], utc=True, errors="raise").dt.floor("D").nunique()
    )


def structural_counts(frame: pd.DataFrame) -> dict[str, int]:
    return {
        "decision_row_count": int(len(frame)),
        "unique_control_position_count": int(frame["control_position_id"].astype(str).nunique()),
        "unique_pair_count": int(frame["pair"].astype(str).nunique()),
        "unique_signal_day_count": _signal_day_count(frame),
        "resolved_target_count": int(frame["resolved_target"].astype(bool).sum()),
        "right_censored_target_count": int(frame["right_censored_target"].astype(bool).sum()),
    }


def landmark_parity(
    landmark_rows: pd.DataFrame,
    frozen_age_census: pd.DataFrame,
) -> pd.DataFrame:
    required = {
        "period_id",
        "universe_id",
        "landmark_age_hours",
        "decision_row_count",
        "unique_control_position_count",
        "unique_pair_count",
        "unique_signal_day_count",
        "resolved_target_count",
        "right_censored_target_count",
    }
    missing = sorted(required.difference(frozen_age_census.columns))
    if missing:
        raise RD42P2Error(f"frozen age census missing columns: {missing}")

    rows: list[dict[str, Any]] = []
    for frozen in frozen_age_census.to_dict(orient="records"):
        period = str(frozen["period_id"])
        universe = str(frozen["universe_id"])
        landmark = int(frozen["landmark_age_hours"])
        cell = landmark_rows.loc[
            (landmark_rows["period_id"].astype(str) == period)
            & (landmark_rows["universe_id"].astype(str) == universe)
            & (landmark_rows["landmark_age_hours"] == landmark)
        ]
        observed = structural_counts(cell)
        record: dict[str, Any] = {
            "period_id": period,
            "universe_id": universe,
            "landmark_age_hours": landmark,
        }
        parity = True
        for field in (
            "decision_row_count",
            "unique_control_position_count",
            "unique_pair_count",
            "unique_signal_day_count",
            "resolved_target_count",
            "right_censored_target_count",
        ):
            expected = int(frozen[field])
            actual = int(observed[field])
            record[f"frozen_{field}"] = expected
            record[f"observed_{field}"] = actual
            record[f"{field}_delta"] = actual - expected
            parity = parity and actual == expected
        record["parity_pass"] = parity
        rows.append(record)

    result = pd.DataFrame.from_records(rows)
    if len(result) != len(PERIODS) * len(UNIVERSES) * len(LANDMARKS):
        raise RD42P2Error("landmark parity cardinality drifted")
    if not bool(result["parity_pass"].all()):
        sample = result.loc[~result["parity_pass"]].head(5).to_dict(orient="records")
        raise RD42P2Error(f"frozen landmark parity failed: {sample}")
    return result


def attach_context(
    landmark_rows: pd.DataFrame,
    context_records: list[dict[str, Any]],
) -> pd.DataFrame:
    context = pd.DataFrame.from_records(context_records)
    if len(context) != len(landmark_rows):
        raise RD42P2Error(
            f"context assignment count {len(context)} != landmark rows {len(landmark_rows)}"
        )
    required = {
        "decision_id",
        "market_context",
        "btc_state",
        "breadth_ready",
        "breadth_median_return_72h",
        "breadth_positive",
        "member_count",
        "observed_member_count",
        "data_completeness_class",
    }
    missing = sorted(required.difference(context.columns))
    if missing:
        raise RD42P2Error(f"context records missing columns: {missing}")

    if context["decision_id"].astype(str).duplicated().any():
        raise RD42P2Error("duplicate context decision_id")
    if not set(context["market_context"].astype(str)).issubset(CONTEXTS):
        raise RD42P2Error("unexpected market context")

    merged = landmark_rows.merge(
        context,
        on="decision_id",
        how="left",
        validate="one_to_one",
    )
    if merged["market_context"].isna().any():
        raise RD42P2Error("one or more landmark rows lack context assignment")
    return merged


def support_census(assignments: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for period in PERIODS:
        for universe in UNIVERSES:
            for landmark in LANDMARKS:
                for context in CONTEXTS:
                    cell = assignments.loc[
                        (assignments["period_id"].astype(str) == period)
                        & (assignments["universe_id"].astype(str) == universe)
                        & (assignments["landmark_age_hours"] == landmark)
                        & (assignments["market_context"].astype(str) == context)
                    ]
                    counts = structural_counts(cell)
                    numeric_support = bool(
                        counts["unique_control_position_count"] >= MIN_POSITIONS
                        and counts["unique_pair_count"] >= MIN_PAIRS
                        and counts["unique_signal_day_count"] >= MIN_SIGNAL_DAYS
                    )
                    primary_eligible = context != "UNAVAILABLE"
                    rows.append(
                        {
                            "period_id": period,
                            "universe_id": universe,
                            "landmark_age_hours": landmark,
                            "market_context": context,
                            **counts,
                            "minimum_unique_positions_gate": MIN_POSITIONS,
                            "minimum_unique_pairs_gate": MIN_PAIRS,
                            "minimum_unique_signal_days_gate": (MIN_SIGNAL_DAYS),
                            "numeric_support_pass": numeric_support,
                            "primary_context_eligible": primary_eligible,
                            "primary_support_pass": bool(numeric_support and primary_eligible),
                        }
                    )
    result = pd.DataFrame.from_records(rows)
    expected = len(PERIODS) * len(UNIVERSES) * len(LANDMARKS) * len(CONTEXTS)
    if len(result) != expected:
        raise RD42P2Error("support census cardinality drifted")
    return result


def data_quality_summary(assignments: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    classes = sorted(assignments["data_completeness_class"].astype(str).unique())
    for period in PERIODS:
        for universe in UNIVERSES:
            for landmark in LANDMARKS:
                base = assignments.loc[
                    (assignments["period_id"].astype(str) == period)
                    & (assignments["universe_id"].astype(str) == universe)
                    & (assignments["landmark_age_hours"] == landmark)
                ]
                total = len(base)
                for completeness in classes:
                    cell = base.loc[base["data_completeness_class"].astype(str) == completeness]
                    rows.append(
                        {
                            "period_id": period,
                            "universe_id": universe,
                            "landmark_age_hours": landmark,
                            "data_completeness_class": completeness,
                            "decision_row_count": int(len(cell)),
                            "decision_row_fraction": (float(len(cell) / total) if total else 0.0),
                            "unique_control_position_count": int(
                                cell["control_position_id"].astype(str).nunique()
                            ),
                            "unavailable_context_count": int(
                                (cell["market_context"].astype(str) == "UNAVAILABLE").sum()
                            ),
                        }
                    )
    return pd.DataFrame.from_records(rows)


def right_censoring_summary(assignments: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for period in PERIODS:
        for universe in UNIVERSES:
            for context in CONTEXTS:
                cell = assignments.loc[
                    (assignments["period_id"].astype(str) == period)
                    & (assignments["universe_id"].astype(str) == universe)
                    & (assignments["market_context"].astype(str) == context)
                ]
                censored = cell.loc[cell["right_censored_target"].astype(bool)]
                rows.append(
                    {
                        "period_id": period,
                        "universe_id": universe,
                        "market_context": context,
                        "decision_row_count": int(len(cell)),
                        "right_censored_decision_row_count": int(len(censored)),
                        "right_censored_unique_position_count": int(
                            censored["control_position_id"].astype(str).nunique()
                        ),
                        "force_close_used": False,
                        "censor_imputation_used": False,
                    }
                )
    return pd.DataFrame.from_records(rows)


def transport_eligible_context_landmarks(
    census: pd.DataFrame,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for context in ("SUPPORTIVE", "MIXED", "STRESSED"):
        for landmark in LANDMARKS:
            counts: dict[str, int] = {}
            for period in PERIODS:
                cell = census.loc[
                    (census["period_id"].astype(str) == period)
                    & (census["landmark_age_hours"] == landmark)
                    & (census["market_context"].astype(str) == context)
                ]
                counts[period] = int(cell["primary_support_pass"].astype(bool).sum())
            eligible = bool(
                counts["ROBUSTNESS_2022"] >= MIN_UNIVERSES_FOR_TRANSPORT
                and counts["ROBUSTNESS_2023"] >= MIN_UNIVERSES_FOR_TRANSPORT
            )
            rows.append(
                {
                    "market_context": context,
                    "landmark_age_hours": int(landmark),
                    "supported_universes_2022": counts["ROBUSTNESS_2022"],
                    "supported_universes_2023": counts["ROBUSTNESS_2023"],
                    "transport_support_eligible": eligible,
                }
            )
    return rows


def decision_from_support(
    transport_rows: list[dict[str, Any]],
) -> tuple[str, str]:
    if any(bool(row["transport_support_eligible"]) for row in transport_rows):
        return SUCCESS_DECISION, SUCCESS_NEXT
    return UNDERPOWERED_DECISION, UNDERPOWERED_NEXT
