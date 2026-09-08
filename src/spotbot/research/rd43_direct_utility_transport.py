"""RD43-P4 preregistered direct-utility temporal transport.

This module implements only the frozen RD43-P3 model and gates:
- two CONTROL_RELATIVE_STATE axes;
- training-only empirical CDF transform;
- fixed four-column OLS basis;
- forward 2022->2023 primary transport;
- reverse 2023->2022 regime diagnostic;
- leave-one-pair-out robustness;
- economic subset threshold predicted RCV < 0 only.

No threshold, model-family, feature, landmark, context, or hyperparameter search.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Final

import numpy as np
import pandas as pd

LANDMARKS: Final = (24, 48, 72, 96, 120, 144)
UNIVERSES: Final = ("C2", "D2", "E2")
DIRECTIONS: Final = (
    "CALIBRATE_2022_EVALUATE_2023",
    "CALIBRATE_2023_EVALUATE_2022",
)
PRIMARY_DIRECTION: Final = "CALIBRATE_2022_EVALUATE_2023"
REVERSE_DIRECTION: Final = "CALIBRATE_2023_EVALUATE_2022"

TRAIN_PERIOD: Final = {
    PRIMARY_DIRECTION: "ROBUSTNESS_2022",
    REVERSE_DIRECTION: "ROBUSTNESS_2023",
}
EVAL_PERIOD: Final = {
    PRIMARY_DIRECTION: "ROBUSTNESS_2023",
    REVERSE_DIRECTION: "ROBUSTNESS_2022",
}

MIN_POSITIONS: Final = 20
MIN_PAIRS: Final = 5
MIN_SIGNAL_DAYS: Final = 10
MIN_CLASS_NEGATIVE: Final = 10
MIN_CLASS_NONNEGATIVE: Final = 10
MIN_NEGATIVE_SUBSET_ROWS: Final = 10
MIN_NEGATIVE_SUBSET_PAIRS: Final = 5
MIN_NEGATIVE_SUBSET_SIGNAL_DAYS: Final = 10
LOPO_MIN_TRAIN_ROWS: Final = 12
LOPO_MIN_TRAIN_PAIRS: Final = 4
LOPO_MIN_EVAL_ROWS: Final = 12
LOPO_MIN_EVAL_PAIRS: Final = 4

MODEL_BASIS: Final = (
    "INTERCEPT",
    "CDF_HIGH_WATER_GAIN_ATR",
    "CDF_PULLBACK_FROM_HIGH_WATER_ATR",
    "CDF_HIGH_WATER_GAIN_ATR_X_CDF_PULLBACK_FROM_HIGH_WATER_ATR",
)

ADJACENT_LANDMARK_PAIRS: Final = (
    (24, 48),
    (48, 72),
    (72, 96),
    (96, 120),
    (120, 144),
)

DECISION_UNQUALIFIED: Final = (
    "RD43_CONTROL_RELATIVE_STATE_DIRECT_UTILITY_UNQUALIFIED_REASSESS_INFORMATION_ARCHITECTURE"
)
NEXT_UNQUALIFIED: Final = (
    "RD43_CLOSE_OR_PREREGISTER_DISTINCT_DIRECT_UTILITY_INFORMATION_SOURCE_WITHOUT_THRESHOLD_RESCUE"
)
DECISION_REGIME_DEPENDENT: Final = (
    "RD43_FORWARD_DIRECT_UTILITY_EXISTS_WITH_REGIME_DEPENDENCE_REQUIRE_CAUSAL_CONTEXT_CONDITIONING"
)
NEXT_REGIME_DEPENDENT: Final = (
    "RD43_P5_PREREGISTER_CAUSAL_CONTEXT_CONDITIONING_OF_"
    "CONTROL_RELATIVE_STATE_BEFORE_ACTION_MAPPING"
)
DECISION_BIDIRECTIONAL: Final = (
    "RD43_CONTROL_RELATIVE_STATE_DIRECT_UTILITY_BIDIRECTIONALLY_PERSISTENT"
)
NEXT_BIDIRECTIONAL: Final = (
    "RD43_P5_PREREGISTER_ISOLATED_ACTION_MAPPING_WITH_SLOT_ESCROW_AND_NO_EARLY_CAPITAL_REUSE"
)

VALID_STATE_CLASS: Final = "RECONSTRUCTED_VALID"


class RD43P4Error(RuntimeError):
    """Frozen P4 contract violation."""


@dataclass(frozen=True)
class FittedModel:
    coefficients: np.ndarray
    high_water_sorted: np.ndarray
    pullback_sorted: np.ndarray
    train_row_count: int
    design_rank: int


def validate_constants() -> None:
    if LANDMARKS != (24, 48, 72, 96, 120, 144):
        raise RD43P4Error("landmark registry drifted")
    if UNIVERSES != ("C2", "D2", "E2"):
        raise RD43P4Error("universe registry drifted")
    if DIRECTIONS != (
        "CALIBRATE_2022_EVALUATE_2023",
        "CALIBRATE_2023_EVALUATE_2022",
    ):
        raise RD43P4Error("direction registry drifted")
    if len(MODEL_BASIS) != 4:
        raise RD43P4Error("model basis dimension drifted")
    if ADJACENT_LANDMARK_PAIRS != (
        (24, 48),
        (48, 72),
        (72, 96),
        (96, 120),
        (120, 144),
    ):
        raise RD43P4Error("persistence registry drifted")


def parse_bool_series(series: pd.Series, *, name: str) -> pd.Series:
    if pd.api.types.is_bool_dtype(series):
        return series.astype(bool)
    mapping = {
        "true": True,
        "false": False,
        "1": True,
        "0": False,
    }
    values = series.astype(str).str.strip().str.lower()
    unknown = sorted(set(values.unique()).difference(mapping))
    if unknown:
        raise RD43P4Error(f"{name} has unknown booleans: {unknown}")
    return values.map(mapping).astype(bool)


def normalize_joined_ledger(
    state: pd.DataFrame,
    target: pd.DataFrame,
) -> pd.DataFrame:
    validate_constants()

    state_required = {
        "decision_id",
        "control_position_id",
        "universe_id",
        "period_id",
        "pair",
        "signal_time",
        "decision_time",
        "landmark_age_hours",
        "data_quality_class",
        "high_water_gain_atr",
        "pullback_from_high_water_atr",
    }
    target_required = {
        "decision_id",
        "control_position_id",
        "universe_id",
        "period_id",
        "pair",
        "decision_time",
        "landmark_age_hours",
        "target_evaluable",
        "rcv_return",
        "right_censored",
    }
    missing_state = sorted(state_required.difference(state.columns))
    missing_target = sorted(target_required.difference(target.columns))
    if missing_state:
        raise RD43P4Error(f"state missing columns: {missing_state}")
    if missing_target:
        raise RD43P4Error(f"target missing columns: {missing_target}")

    if state["decision_id"].astype(str).duplicated().any():
        raise RD43P4Error("duplicate state decision_id")
    if target["decision_id"].astype(str).duplicated().any():
        raise RD43P4Error("duplicate target decision_id")

    state_ids = set(state["decision_id"].astype(str))
    target_ids = set(target["decision_id"].astype(str))
    if state_ids != target_ids:
        missing_in_target = len(state_ids - target_ids)
        missing_in_state = len(target_ids - state_ids)
        raise RD43P4Error(
            "decision registry mismatch: "
            f"missing_in_target={missing_in_target}, "
            f"missing_in_state={missing_in_state}"
        )

    state_frame = state.copy()
    target_frame = target.copy()
    state_frame["decision_id"] = state_frame["decision_id"].astype(str)
    target_frame["decision_id"] = target_frame["decision_id"].astype(str)

    for frame in (state_frame, target_frame):
        frame["control_position_id"] = frame["control_position_id"].astype(str)
        frame["universe_id"] = frame["universe_id"].astype(str)
        frame["period_id"] = frame["period_id"].astype(str)
        frame["pair"] = frame["pair"].astype(str)
        frame["decision_time"] = pd.to_datetime(
            frame["decision_time"],
            utc=True,
            errors="raise",
        )
        frame["landmark_age_hours"] = pd.to_numeric(
            frame["landmark_age_hours"],
            errors="raise",
        ).astype(int)

    state_frame["signal_time"] = pd.to_datetime(
        state_frame["signal_time"],
        utc=True,
        errors="raise",
    )
    state_frame["high_water_gain_atr"] = pd.to_numeric(
        state_frame["high_water_gain_atr"],
        errors="raise",
    ).astype(float)
    state_frame["pullback_from_high_water_atr"] = pd.to_numeric(
        state_frame["pullback_from_high_water_atr"],
        errors="raise",
    ).astype(float)

    if not (state_frame["data_quality_class"].astype(str) == VALID_STATE_CLASS).all():
        raise RD43P4Error("state ledger contains non-valid reconstruction rows")

    for axis in ("high_water_gain_atr", "pullback_from_high_water_atr"):
        values = state_frame[axis].to_numpy(float)
        if not np.isfinite(values).all():
            raise RD43P4Error(f"state axis is non-finite: {axis}")

    target_frame["target_evaluable"] = parse_bool_series(
        target_frame["target_evaluable"],
        name="target_evaluable",
    )
    target_frame["right_censored"] = parse_bool_series(
        target_frame["right_censored"],
        name="right_censored",
    )
    target_frame["rcv_return"] = pd.to_numeric(
        target_frame["rcv_return"],
        errors="coerce",
    )

    if bool((target_frame["target_evaluable"] & target_frame["right_censored"]).any()):
        raise RD43P4Error("target row is both evaluable and right-censored")
    if bool((target_frame["target_evaluable"] & target_frame["rcv_return"].isna()).any()):
        raise RD43P4Error("evaluable target row is missing rcv_return")
    if bool((~target_frame["target_evaluable"] & target_frame["rcv_return"].notna()).any()):
        raise RD43P4Error("non-evaluable target row has rcv_return")
    if not np.isfinite(
        target_frame.loc[
            target_frame["target_evaluable"],
            "rcv_return",
        ].to_numpy(float)
    ).all():
        raise RD43P4Error("evaluable rcv_return contains non-finite value")

    parity_columns = (
        "control_position_id",
        "universe_id",
        "period_id",
        "pair",
        "decision_time",
        "landmark_age_hours",
    )
    parity = state_frame[["decision_id", *parity_columns]].merge(
        target_frame[["decision_id", *parity_columns]],
        on="decision_id",
        how="inner",
        validate="one_to_one",
        suffixes=("_state", "_target"),
    )
    for column in parity_columns:
        left = parity[f"{column}_state"]
        right = parity[f"{column}_target"]
        if pd.api.types.is_datetime64_any_dtype(left):
            equal = left.eq(right)
        else:
            equal = left.astype(str).eq(right.astype(str))
        if not bool(equal.all()):
            raise RD43P4Error(f"join parity mismatch: {column}")

    joined = state_frame.merge(
        target_frame[
            [
                "decision_id",
                "target_evaluable",
                "rcv_return",
                "right_censored",
            ]
        ],
        on="decision_id",
        how="inner",
        validate="one_to_one",
    )

    expected_periods = {"ROBUSTNESS_2022", "ROBUSTNESS_2023"}
    if set(joined["period_id"].unique()) != expected_periods:
        raise RD43P4Error("joined period registry drifted")
    if not set(joined["universe_id"].unique()).issubset(set(UNIVERSES)):
        raise RD43P4Error("joined universe registry drifted")
    if not set(joined["landmark_age_hours"].unique()).issubset(set(LANDMARKS)):
        raise RD43P4Error("joined landmark registry drifted")

    joined["rcv_negative"] = joined["target_evaluable"] & (joined["rcv_return"] < 0.0)
    return joined.sort_values(
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


def support_summary(frame: pd.DataFrame) -> dict[str, int]:
    return {
        "rows": int(len(frame)),
        "positions": int(frame["control_position_id"].astype(str).nunique()),
        "pairs": int(frame["pair"].astype(str).nunique()),
        "signal_days": signal_day_count(frame),
    }


def base_support_pass(frame: pd.DataFrame) -> bool:
    support = support_summary(frame)
    return bool(
        support["positions"] >= MIN_POSITIONS
        and support["pairs"] >= MIN_PAIRS
        and support["signal_days"] >= MIN_SIGNAL_DAYS
    )


def lopo_support_pass(
    train: pd.DataFrame,
    evaluation: pd.DataFrame,
) -> bool:
    return bool(
        len(train) >= LOPO_MIN_TRAIN_ROWS
        and train["pair"].astype(str).nunique() >= LOPO_MIN_TRAIN_PAIRS
        and len(evaluation) >= LOPO_MIN_EVAL_ROWS
        and evaluation["pair"].astype(str).nunique() >= LOPO_MIN_EVAL_PAIRS
    )


def empirical_cdf_reference(values: np.ndarray) -> np.ndarray:
    raw = np.asarray(values, dtype=float)
    if raw.ndim != 1 or len(raw) == 0:
        raise RD43P4Error("empirical CDF needs non-empty 1D training values")
    if not np.isfinite(raw).all():
        raise RD43P4Error("empirical CDF training values non-finite")
    return np.sort(raw, kind="mergesort")


def apply_empirical_cdf(
    sorted_training: np.ndarray,
    values: np.ndarray,
) -> np.ndarray:
    raw = np.asarray(values, dtype=float)
    if raw.ndim != 1:
        raise RD43P4Error("CDF values must be 1D")
    if not np.isfinite(raw).all():
        raise RD43P4Error("CDF evaluation values non-finite")
    if len(sorted_training) == 0:
        raise RD43P4Error("CDF reference empty")
    return np.searchsorted(
        sorted_training,
        raw,
        side="right",
    ).astype(float) / float(len(sorted_training))


def design_matrix(
    high_water_cdf: np.ndarray,
    pullback_cdf: np.ndarray,
) -> np.ndarray:
    h = np.asarray(high_water_cdf, dtype=float)
    p = np.asarray(pullback_cdf, dtype=float)
    if h.shape != p.shape or h.ndim != 1:
        raise RD43P4Error("design axes shape mismatch")
    return np.column_stack(
        [
            np.ones(len(h), dtype=float),
            h,
            p,
            h * p,
        ]
    )


def fit_model(train: pd.DataFrame) -> FittedModel:
    if train.empty:
        raise RD43P4Error("cannot fit empty training cell")

    h_ref = empirical_cdf_reference(train["high_water_gain_atr"].to_numpy(float))
    p_ref = empirical_cdf_reference(train["pullback_from_high_water_atr"].to_numpy(float))
    h = apply_empirical_cdf(
        h_ref,
        train["high_water_gain_atr"].to_numpy(float),
    )
    p = apply_empirical_cdf(
        p_ref,
        train["pullback_from_high_water_atr"].to_numpy(float),
    )
    x = design_matrix(h, p)
    y = train["rcv_return"].to_numpy(float)

    coefficients, _residuals, rank, _singular = np.linalg.lstsq(
        x,
        y,
        rcond=None,
    )
    if int(rank) != len(MODEL_BASIS):
        raise RD43P4Error(f"full design rank required, got {rank}/{len(MODEL_BASIS)}")
    if not np.isfinite(coefficients).all():
        raise RD43P4Error("OLS coefficients non-finite")
    return FittedModel(
        coefficients=coefficients,
        high_water_sorted=h_ref,
        pullback_sorted=p_ref,
        train_row_count=int(len(train)),
        design_rank=int(rank),
    )


def predict(model: FittedModel, frame: pd.DataFrame) -> np.ndarray:
    h = apply_empirical_cdf(
        model.high_water_sorted,
        frame["high_water_gain_atr"].to_numpy(float),
    )
    p = apply_empirical_cdf(
        model.pullback_sorted,
        frame["pullback_from_high_water_atr"].to_numpy(float),
    )
    values = design_matrix(h, p) @ model.coefficients
    if not np.isfinite(values).all():
        raise RD43P4Error("prediction contains non-finite value")
    return values


def spearman(x: np.ndarray, y: np.ndarray) -> float:
    left = pd.Series(np.asarray(x, dtype=float)).rank(
        method="average",
    )
    right = pd.Series(np.asarray(y, dtype=float)).rank(
        method="average",
    )
    value = left.corr(right, method="pearson")
    if pd.isna(value):
        return float("nan")
    return float(value)


def auc_binary(
    event: np.ndarray,
    score: np.ndarray,
) -> float:
    labels = np.asarray(event, dtype=bool)
    values = np.asarray(score, dtype=float)
    if labels.shape != values.shape or labels.ndim != 1:
        raise RD43P4Error("AUC arrays shape mismatch")
    positives = int(labels.sum())
    negatives = int((~labels).sum())
    if positives == 0 or negatives == 0:
        return float("nan")
    ranks = pd.Series(values).rank(method="average").to_numpy(float)
    positive_rank_sum = float(ranks[labels].sum())
    auc = (positive_rank_sum - positives * (positives + 1) / 2.0) / float(positives * negatives)
    return float(auc)


def stable_prediction_halves(
    evaluation: pd.DataFrame,
    predictions: np.ndarray,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    temp = evaluation[["decision_id", "rcv_return"]].copy()
    temp["prediction"] = np.asarray(predictions, dtype=float)
    temp = temp.sort_values(
        ["prediction", "decision_id"],
        kind="stable",
    ).reset_index(drop=True)
    bottom_n = len(temp) // 2
    if bottom_n == 0 or bottom_n == len(temp):
        raise RD43P4Error("cannot split prediction halves")
    return temp.iloc[:bottom_n], temp.iloc[bottom_n:]


def subset_support_pass(frame: pd.DataFrame) -> bool:
    return bool(
        len(frame) >= MIN_NEGATIVE_SUBSET_ROWS
        and frame["pair"].astype(str).nunique() >= MIN_NEGATIVE_SUBSET_PAIRS
        and signal_day_count(frame) >= MIN_NEGATIVE_SUBSET_SIGNAL_DAYS
    )


def evaluate_metrics(
    evaluation: pd.DataFrame,
    predictions: np.ndarray,
) -> dict[str, Any]:
    if len(evaluation) != len(predictions):
        raise RD43P4Error("evaluation/prediction length mismatch")
    actual = evaluation["rcv_return"].to_numpy(float)
    pred = np.asarray(predictions, dtype=float)
    event = actual < 0.0

    rho = spearman(pred, actual)
    bottom, top = stable_prediction_halves(evaluation, pred)
    bottom_mean = float(bottom["rcv_return"].mean())
    top_mean = float(top["rcv_return"].mean())

    event_count = int(event.sum())
    non_event_count = int((~event).sum())
    classification_support = bool(
        event_count >= MIN_CLASS_NEGATIVE and non_event_count >= MIN_CLASS_NONNEGATIVE
    )
    auc = auc_binary(event, -pred) if classification_support else float("nan")
    event_median_prediction = float(np.median(pred[event])) if event_count else float("nan")
    non_event_median_prediction = (
        float(np.median(pred[~event])) if non_event_count else float("nan")
    )

    subset_mask = pred < 0.0
    subset = evaluation.loc[subset_mask].copy()
    complement = evaluation.loc[~subset_mask].copy()
    subset_support = subset_support_pass(subset) and not complement.empty

    if subset.empty:
        subset_mean = float("nan")
        subset_median = float("nan")
        subset_negative_fraction = float("nan")
    else:
        subset_mean = float(subset["rcv_return"].mean())
        subset_median = float(subset["rcv_return"].median())
        subset_negative_fraction = float((subset["rcv_return"] < 0.0).mean())
    complement_mean = (
        float(complement["rcv_return"].mean()) if not complement.empty else float("nan")
    )

    continuous_point_pass = bool(math.isfinite(rho) and rho > 0.0 and bottom_mean < top_mean)
    classification_point_pass = bool(
        classification_support
        and math.isfinite(auc)
        and auc > 0.5
        and event_median_prediction < non_event_median_prediction
    )
    subset_point_pass = bool(
        subset_support
        and subset_mean < 0.0
        and subset_median < 0.0
        and subset_negative_fraction > 0.5
        and subset_mean < complement_mean
    )

    return {
        "evaluation_row_count": int(len(evaluation)),
        "spearman_predicted_vs_actual": rho,
        "predicted_bottom_half_actual_mean_rcv": bottom_mean,
        "predicted_top_half_actual_mean_rcv": top_mean,
        "continuous_point_pass": continuous_point_pass,
        "actual_negative_row_count": event_count,
        "actual_nonnegative_row_count": non_event_count,
        "classification_support_pass": classification_support,
        "negative_rcv_auc": auc,
        "actual_negative_event_median_prediction": event_median_prediction,
        "actual_nonnegative_event_median_prediction": (non_event_median_prediction),
        "classification_point_pass": classification_point_pass,
        "predicted_negative_subset_row_count": int(len(subset)),
        "predicted_negative_subset_unique_pairs": int(subset["pair"].astype(str).nunique()),
        "predicted_negative_subset_signal_days": signal_day_count(subset),
        "predicted_negative_subset_support_pass": subset_support,
        "predicted_negative_subset_actual_mean_rcv": subset_mean,
        "predicted_negative_subset_actual_median_rcv": subset_median,
        "predicted_negative_subset_actual_negative_fraction": (subset_negative_fraction),
        "predicted_nonnegative_complement_actual_mean_rcv": complement_mean,
        "negative_subset_point_pass": subset_point_pass,
    }


def empty_full_evaluation(
    *,
    direction: str,
    universe: str,
    landmark: int,
    train: pd.DataFrame,
    evaluation: pd.DataFrame,
    outcome: str,
) -> dict[str, Any]:
    train_support = support_summary(train)
    eval_support = support_summary(evaluation)
    return {
        "transport_direction": direction,
        "universe_id": universe,
        "landmark_age_hours": landmark,
        "train_period_id": TRAIN_PERIOD[direction],
        "evaluation_period_id": EVAL_PERIOD[direction],
        "train_row_count": train_support["rows"],
        "train_unique_positions": train_support["positions"],
        "train_unique_pairs": train_support["pairs"],
        "train_unique_signal_days": train_support["signal_days"],
        "evaluation_row_count": eval_support["rows"],
        "evaluation_unique_positions": eval_support["positions"],
        "evaluation_unique_pairs": eval_support["pairs"],
        "evaluation_unique_signal_days": eval_support["signal_days"],
        "base_support_pass": False,
        "design_rank": 0,
        "fit_status": outcome,
    }


def evaluate_cell(
    joined: pd.DataFrame,
    *,
    direction: str,
    universe: str,
    landmark: int,
) -> tuple[
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    list[dict[str, Any]],
]:
    train_period = TRAIN_PERIOD[direction]
    eval_period = EVAL_PERIOD[direction]
    base = joined.loc[
        (joined["universe_id"].astype(str) == universe)
        & (joined["landmark_age_hours"].astype(int) == landmark)
    ]
    train = base.loc[
        (base["period_id"].astype(str) == train_period) & base["target_evaluable"].astype(bool)
    ].copy()
    evaluation = base.loc[
        (base["period_id"].astype(str) == eval_period) & base["target_evaluable"].astype(bool)
    ].copy()

    train_support = support_summary(train)
    eval_support = support_summary(evaluation)
    base_support = base_support_pass(train) and base_support_pass(evaluation)
    base_row = {
        "transport_direction": direction,
        "universe_id": universe,
        "landmark_age_hours": landmark,
        "train_period_id": train_period,
        "evaluation_period_id": eval_period,
        "train_row_count": train_support["rows"],
        "train_unique_positions": train_support["positions"],
        "train_unique_pairs": train_support["pairs"],
        "train_unique_signal_days": train_support["signal_days"],
        "evaluation_row_count": eval_support["rows"],
        "evaluation_unique_positions": eval_support["positions"],
        "evaluation_unique_pairs": eval_support["pairs"],
        "evaluation_unique_signal_days": eval_support["signal_days"],
        "base_support_pass": base_support,
    }

    if not base_support:
        common = {
            **base_row,
            "design_rank": 0,
            "fit_status": "INSUFFICIENT_SUPPORT",
        }
        continuous = {
            **common,
            "spearman_predicted_vs_actual": np.nan,
            "predicted_bottom_half_actual_mean_rcv": np.nan,
            "predicted_top_half_actual_mean_rcv": np.nan,
            "continuous_point_pass": False,
            "all_lopo_continuous_pass": False,
            "continuous_gate_pass": False,
        }
        classification = {
            **common,
            "actual_negative_row_count": int((evaluation["rcv_return"] < 0.0).sum()),
            "actual_nonnegative_row_count": int((evaluation["rcv_return"] >= 0.0).sum()),
            "classification_support_pass": False,
            "negative_rcv_auc": np.nan,
            "actual_negative_event_median_prediction": np.nan,
            "actual_nonnegative_event_median_prediction": np.nan,
            "classification_point_pass": False,
            "all_lopo_classification_pass": False,
            "classification_gate_pass": False,
        }
        subset = {
            **common,
            "predicted_negative_subset_row_count": 0,
            "predicted_negative_subset_unique_pairs": 0,
            "predicted_negative_subset_signal_days": 0,
            "predicted_negative_subset_support_pass": False,
            "predicted_negative_subset_actual_mean_rcv": np.nan,
            "predicted_negative_subset_actual_median_rcv": np.nan,
            "predicted_negative_subset_actual_negative_fraction": np.nan,
            "predicted_nonnegative_complement_actual_mean_rcv": np.nan,
            "negative_subset_point_pass": False,
            "all_lopo_negative_subset_pass": False,
            "negative_subset_gate_pass": False,
        }
        qualification = {
            **common,
            "continuous_gate_pass": False,
            "classification_gate_pass": False,
            "negative_subset_gate_pass": False,
            "joint_cell_qualified": False,
        }
        return continuous, classification, subset, qualification, []

    try:
        model = fit_model(train)
    except RD43P4Error:
        common = {
            **base_row,
            "design_rank": 0,
            "fit_status": "RANK_OR_FIT_FAILURE",
        }
        continuous = {
            **common,
            "spearman_predicted_vs_actual": np.nan,
            "predicted_bottom_half_actual_mean_rcv": np.nan,
            "predicted_top_half_actual_mean_rcv": np.nan,
            "continuous_point_pass": False,
            "all_lopo_continuous_pass": False,
            "continuous_gate_pass": False,
        }
        classification = {
            **common,
            "actual_negative_row_count": int((evaluation["rcv_return"] < 0.0).sum()),
            "actual_nonnegative_row_count": int((evaluation["rcv_return"] >= 0.0).sum()),
            "classification_support_pass": False,
            "negative_rcv_auc": np.nan,
            "actual_negative_event_median_prediction": np.nan,
            "actual_nonnegative_event_median_prediction": np.nan,
            "classification_point_pass": False,
            "all_lopo_classification_pass": False,
            "classification_gate_pass": False,
        }
        subset = {
            **common,
            "predicted_negative_subset_row_count": 0,
            "predicted_negative_subset_unique_pairs": 0,
            "predicted_negative_subset_signal_days": 0,
            "predicted_negative_subset_support_pass": False,
            "predicted_negative_subset_actual_mean_rcv": np.nan,
            "predicted_negative_subset_actual_median_rcv": np.nan,
            "predicted_negative_subset_actual_negative_fraction": np.nan,
            "predicted_nonnegative_complement_actual_mean_rcv": np.nan,
            "negative_subset_point_pass": False,
            "all_lopo_negative_subset_pass": False,
            "negative_subset_gate_pass": False,
        }
        qualification = {
            **common,
            "continuous_gate_pass": False,
            "classification_gate_pass": False,
            "negative_subset_gate_pass": False,
            "joint_cell_qualified": False,
        }
        return continuous, classification, subset, qualification, []

    predictions = predict(model, evaluation)
    metrics = evaluate_metrics(evaluation, predictions)

    lopo_rows: list[dict[str, Any]] = []
    all_pairs = sorted(set(train["pair"].astype(str)) | set(evaluation["pair"].astype(str)))
    for removed_pair in all_pairs:
        train_lopo = train.loc[train["pair"].astype(str) != removed_pair].copy()
        eval_lopo = evaluation.loc[evaluation["pair"].astype(str) != removed_pair].copy()
        lopo_support = lopo_support_pass(train_lopo, eval_lopo)
        row: dict[str, Any] = {
            "transport_direction": direction,
            "universe_id": universe,
            "landmark_age_hours": landmark,
            "removed_pair": removed_pair,
            "train_row_count": int(len(train_lopo)),
            "train_unique_pairs": int(train_lopo["pair"].astype(str).nunique()),
            "evaluation_row_count": int(len(eval_lopo)),
            "evaluation_unique_pairs": int(eval_lopo["pair"].astype(str).nunique()),
            "lopo_support_pass": lopo_support,
            "lopo_fit_status": "NOT_RUN",
            "spearman_predicted_vs_actual": np.nan,
            "bottom_minus_top_actual_mean_rcv": np.nan,
            "continuous_pass": False,
            "negative_rcv_auc": np.nan,
            "classification_pass": False,
            "predicted_negative_subset_row_count": 0,
            "predicted_negative_subset_unique_pairs": 0,
            "predicted_negative_subset_signal_days": 0,
            "predicted_negative_subset_mean_rcv": np.nan,
            "predicted_negative_subset_negative_fraction": np.nan,
            "negative_subset_pass": False,
        }
        if not lopo_support:
            row["lopo_fit_status"] = "INSUFFICIENT_SUPPORT"
            lopo_rows.append(row)
            continue

        try:
            lopo_model = fit_model(train_lopo)
        except RD43P4Error:
            row["lopo_fit_status"] = "RANK_OR_FIT_FAILURE"
            lopo_rows.append(row)
            continue

        lopo_pred = predict(lopo_model, eval_lopo)
        lopo_metrics = evaluate_metrics(eval_lopo, lopo_pred)
        row.update(
            {
                "lopo_fit_status": "PASS",
                "spearman_predicted_vs_actual": (lopo_metrics["spearman_predicted_vs_actual"]),
                "bottom_minus_top_actual_mean_rcv": (
                    lopo_metrics["predicted_bottom_half_actual_mean_rcv"]
                    - lopo_metrics["predicted_top_half_actual_mean_rcv"]
                ),
                "continuous_pass": bool(
                    math.isfinite(lopo_metrics["spearman_predicted_vs_actual"])
                    and lopo_metrics["spearman_predicted_vs_actual"] > 0.0
                    and (
                        lopo_metrics["predicted_bottom_half_actual_mean_rcv"]
                        - lopo_metrics["predicted_top_half_actual_mean_rcv"]
                    )
                    < 0.0
                ),
                "negative_rcv_auc": lopo_metrics["negative_rcv_auc"],
                "classification_pass": bool(
                    lopo_metrics["classification_support_pass"]
                    and math.isfinite(lopo_metrics["negative_rcv_auc"])
                    and lopo_metrics["negative_rcv_auc"] > 0.5
                ),
                "predicted_negative_subset_row_count": (
                    lopo_metrics["predicted_negative_subset_row_count"]
                ),
                "predicted_negative_subset_unique_pairs": (
                    lopo_metrics["predicted_negative_subset_unique_pairs"]
                ),
                "predicted_negative_subset_signal_days": (
                    lopo_metrics["predicted_negative_subset_signal_days"]
                ),
                "predicted_negative_subset_mean_rcv": (
                    lopo_metrics["predicted_negative_subset_actual_mean_rcv"]
                ),
                "predicted_negative_subset_negative_fraction": (
                    lopo_metrics["predicted_negative_subset_actual_negative_fraction"]
                ),
                "negative_subset_pass": bool(
                    lopo_metrics["predicted_negative_subset_support_pass"]
                    and lopo_metrics["predicted_negative_subset_actual_mean_rcv"] < 0.0
                    and lopo_metrics["predicted_negative_subset_actual_negative_fraction"] > 0.5
                ),
            }
        )
        lopo_rows.append(row)

    all_lopo_continuous = bool(lopo_rows and all(bool(row["continuous_pass"]) for row in lopo_rows))
    all_lopo_classification = bool(
        lopo_rows and all(bool(row["classification_pass"]) for row in lopo_rows)
    )
    all_lopo_subset = bool(
        lopo_rows and all(bool(row["negative_subset_pass"]) for row in lopo_rows)
    )

    common = {
        **base_row,
        "design_rank": model.design_rank,
        "fit_status": "PASS",
    }
    continuous_gate = bool(metrics["continuous_point_pass"] and all_lopo_continuous)
    classification_gate = bool(metrics["classification_point_pass"] and all_lopo_classification)
    subset_gate = bool(metrics["negative_subset_point_pass"] and all_lopo_subset)

    continuous = {
        **common,
        "spearman_predicted_vs_actual": (metrics["spearman_predicted_vs_actual"]),
        "predicted_bottom_half_actual_mean_rcv": (metrics["predicted_bottom_half_actual_mean_rcv"]),
        "predicted_top_half_actual_mean_rcv": (metrics["predicted_top_half_actual_mean_rcv"]),
        "continuous_point_pass": metrics["continuous_point_pass"],
        "all_lopo_continuous_pass": all_lopo_continuous,
        "continuous_gate_pass": continuous_gate,
    }
    classification = {
        **common,
        "actual_negative_row_count": metrics["actual_negative_row_count"],
        "actual_nonnegative_row_count": (metrics["actual_nonnegative_row_count"]),
        "classification_support_pass": (metrics["classification_support_pass"]),
        "negative_rcv_auc": metrics["negative_rcv_auc"],
        "actual_negative_event_median_prediction": (
            metrics["actual_negative_event_median_prediction"]
        ),
        "actual_nonnegative_event_median_prediction": (
            metrics["actual_nonnegative_event_median_prediction"]
        ),
        "classification_point_pass": metrics["classification_point_pass"],
        "all_lopo_classification_pass": all_lopo_classification,
        "classification_gate_pass": classification_gate,
    }
    subset = {
        **common,
        "predicted_negative_subset_row_count": (metrics["predicted_negative_subset_row_count"]),
        "predicted_negative_subset_unique_pairs": (
            metrics["predicted_negative_subset_unique_pairs"]
        ),
        "predicted_negative_subset_signal_days": (metrics["predicted_negative_subset_signal_days"]),
        "predicted_negative_subset_support_pass": (
            metrics["predicted_negative_subset_support_pass"]
        ),
        "predicted_negative_subset_actual_mean_rcv": (
            metrics["predicted_negative_subset_actual_mean_rcv"]
        ),
        "predicted_negative_subset_actual_median_rcv": (
            metrics["predicted_negative_subset_actual_median_rcv"]
        ),
        "predicted_negative_subset_actual_negative_fraction": (
            metrics["predicted_negative_subset_actual_negative_fraction"]
        ),
        "predicted_nonnegative_complement_actual_mean_rcv": (
            metrics["predicted_nonnegative_complement_actual_mean_rcv"]
        ),
        "negative_subset_point_pass": metrics["negative_subset_point_pass"],
        "all_lopo_negative_subset_pass": all_lopo_subset,
        "negative_subset_gate_pass": subset_gate,
    }
    qualification = {
        **common,
        "continuous_gate_pass": continuous_gate,
        "classification_gate_pass": classification_gate,
        "negative_subset_gate_pass": subset_gate,
        "joint_cell_qualified": bool(continuous_gate and classification_gate and subset_gate),
    }
    coefficients = {
        "transport_direction": direction,
        "universe_id": universe,
        "landmark_age_hours": landmark,
        "train_period_id": train_period,
        "evaluation_period_id": eval_period,
        "train_row_count": int(len(train)),
        "design_rank": model.design_rank,
        "beta_intercept": float(model.coefficients[0]),
        "beta_cdf_high_water_gain_atr": float(model.coefficients[1]),
        "beta_cdf_pullback_from_high_water_atr": float(model.coefficients[2]),
        "beta_interaction": float(model.coefficients[3]),
    }
    return (
        continuous,
        classification,
        subset,
        qualification,
        [
            coefficients,
            *lopo_rows,
        ],
    )


def run_all_cells(
    joined: pd.DataFrame,
) -> dict[str, pd.DataFrame]:
    continuous_rows: list[dict[str, Any]] = []
    classification_rows: list[dict[str, Any]] = []
    subset_rows: list[dict[str, Any]] = []
    qualification_rows: list[dict[str, Any]] = []
    coefficient_rows: list[dict[str, Any]] = []
    lopo_rows: list[dict[str, Any]] = []

    total = len(DIRECTIONS) * len(UNIVERSES) * len(LANDMARKS)
    index = 0
    for direction in DIRECTIONS:
        for universe in UNIVERSES:
            for landmark in LANDMARKS:
                index += 1
                (
                    continuous,
                    classification,
                    subset,
                    qualification,
                    artifacts,
                ) = evaluate_cell(
                    joined,
                    direction=direction,
                    universe=universe,
                    landmark=landmark,
                )
                continuous_rows.append(continuous)
                classification_rows.append(classification)
                subset_rows.append(subset)
                qualification_rows.append(qualification)
                for artifact in artifacts:
                    if "removed_pair" in artifact:
                        lopo_rows.append(artifact)
                    else:
                        coefficient_rows.append(artifact)
                print(
                    f"RD43_P4_CELL_PROGRESS={index}/{total}:{direction}:{universe}:{landmark}",
                    flush=True,
                )

    expected_cells = total
    for rows, label in (
        (continuous_rows, "continuous"),
        (classification_rows, "classification"),
        (subset_rows, "subset"),
        (qualification_rows, "qualification"),
    ):
        if len(rows) != expected_cells:
            raise RD43P4Error(f"{label} cell cardinality drifted")

    return {
        "continuous": pd.DataFrame.from_records(continuous_rows),
        "classification": pd.DataFrame.from_records(classification_rows),
        "subset": pd.DataFrame.from_records(subset_rows),
        "qualification": pd.DataFrame.from_records(qualification_rows),
        "coefficients": pd.DataFrame.from_records(coefficient_rows),
        "lopo": pd.DataFrame.from_records(lopo_rows),
    }


def landmark_qualification(
    cell_qualification: pd.DataFrame,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for landmark in LANDMARKS:
        record: dict[str, Any] = {
            "landmark_age_hours": landmark,
        }
        for direction, prefix in (
            (PRIMARY_DIRECTION, "forward"),
            (REVERSE_DIRECTION, "reverse"),
        ):
            cell = cell_qualification.loc[
                (cell_qualification["transport_direction"].astype(str) == direction)
                & (cell_qualification["landmark_age_hours"].astype(int) == landmark)
            ]
            qualified_universes = sorted(
                cell.loc[
                    cell["joint_cell_qualified"].astype(bool),
                    "universe_id",
                ]
                .astype(str)
                .tolist()
            )
            record[f"{prefix}_qualified_universe_count"] = int(len(qualified_universes))
            record[f"{prefix}_qualified_universes"] = "|".join(qualified_universes)
            record[f"{prefix}_landmark_qualified"] = bool(len(qualified_universes) >= 2)
        rows.append(record)
    return pd.DataFrame.from_records(rows)


def temporal_persistence(
    landmarks: pd.DataFrame,
) -> dict[str, Any]:
    by_age = landmarks.set_index("landmark_age_hours")
    forward_pairs: list[list[int]] = []
    reverse_pairs: list[list[int]] = []
    for left, right in ADJACENT_LANDMARK_PAIRS:
        if bool(by_age.loc[left, "forward_landmark_qualified"]) and bool(
            by_age.loc[right, "forward_landmark_qualified"]
        ):
            forward_pairs.append([left, right])
        if bool(by_age.loc[left, "reverse_landmark_qualified"]) and bool(
            by_age.loc[right, "reverse_landmark_qualified"]
        ):
            reverse_pairs.append([left, right])

    reverse_set = {tuple(pair) for pair in reverse_pairs}
    matching = [pair for pair in forward_pairs if tuple(pair) in reverse_set]

    if not forward_pairs:
        decision = DECISION_UNQUALIFIED
        next_stage = NEXT_UNQUALIFIED
    elif not matching:
        decision = DECISION_REGIME_DEPENDENT
        next_stage = NEXT_REGIME_DEPENDENT
    else:
        decision = DECISION_BIDIRECTIONAL
        next_stage = NEXT_BIDIRECTIONAL

    return {
        "schema_version": "rd43-p4-temporal-persistence-qualification-v1",
        "status": "PASS",
        "adjacent_landmark_pairs": [list(pair) for pair in ADJACENT_LANDMARK_PAIRS],
        "forward_persistent_pairs": forward_pairs,
        "reverse_persistent_pairs": reverse_pairs,
        "matching_forward_reverse_persistent_pairs": matching,
        "forward_persistent_pair_count": len(forward_pairs),
        "reverse_persistent_pair_count": len(reverse_pairs),
        "matching_persistent_pair_count": len(matching),
        "isolated_single_landmark_success_insufficient": True,
        "best_persistent_pair_selection_used": False,
        "decision": decision,
        "next_stage": next_stage,
        "action_mapping_authorized": False,
    }
