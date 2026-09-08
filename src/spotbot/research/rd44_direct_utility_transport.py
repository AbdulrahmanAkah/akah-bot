"""RD44-P4 frozen control-relative-dynamics direct-utility transport.

Implements only the RD44-P3 preregistered design:
- three CONTROL_RELATIVE_DYNAMICS axes;
- training-only empirical CDF transforms;
- fixed four-coefficient OLS with no interactions;
- 2022->2023 primary transport and 2023->2022 regime diagnostic;
- leave-one-pair-out robustness;
- economic subset threshold predicted RCV < 0 only;
- adjacent-landmark persistence.

No feature, model, threshold, context, landmark, or universe search.
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

AXES: Final = (
    "time_since_completed_high_water_hours",
    "recent_12h_high_water_increment_atr",
    "recent_12h_pullback_change_atr",
)
MODEL_BASIS: Final = (
    "INTERCEPT",
    "CDF_TIME_SINCE_COMPLETED_HIGH_WATER_HOURS",
    "CDF_RECENT_12H_HIGH_WATER_INCREMENT_ATR",
    "CDF_RECENT_12H_PULLBACK_CHANGE_ATR",
)

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

ADJACENT_LANDMARK_PAIRS: Final = (
    (24, 48),
    (48, 72),
    (72, 96),
    (96, 120),
    (120, 144),
)

VALID_STATE_CLASS: Final = "RECONSTRUCTED_VALID"

DECISION_UNQUALIFIED: Final = (
    "RD44_CONTROL_RELATIVE_DYNAMICS_DIRECT_UTILITY_UNQUALIFIED_REASSESS_INFORMATION_ARCHITECTURE"
)
NEXT_UNQUALIFIED: Final = (
    "RD44_CLOSE_OR_PREREGISTER_DISTINCT_DIRECT_UTILITY_INFORMATION_SOURCE_WITHOUT_THRESHOLD_RESCUE"
)
DECISION_REGIME_DEPENDENT: Final = (
    "RD44_FORWARD_DIRECT_UTILITY_EXISTS_WITH_REGIME_DEPENDENCE_REQUIRE_CAUSAL_CONTEXT_CONDITIONING"
)
NEXT_REGIME_DEPENDENT: Final = (
    "RD44_P5_PREREGISTER_CAUSAL_CONTEXT_CONDITIONING_OF_"
    "CONTROL_RELATIVE_DYNAMICS_BEFORE_ACTION_MAPPING"
)
DECISION_BIDIRECTIONAL: Final = (
    "RD44_CONTROL_RELATIVE_DYNAMICS_DIRECT_UTILITY_BIDIRECTIONALLY_PERSISTENT"
)
NEXT_BIDIRECTIONAL: Final = (
    "RD44_P5_PREREGISTER_ISOLATED_ACTION_MAPPING_WITH_SLOT_ESCROW_AND_NO_EARLY_CAPITAL_REUSE"
)


class RD44P4Error(RuntimeError):
    """Frozen RD44-P4 contract violation."""


@dataclass(frozen=True)
class FittedModel:
    coefficients: np.ndarray
    sorted_references: tuple[np.ndarray, np.ndarray, np.ndarray]
    train_row_count: int
    design_rank: int


def validate_constants() -> None:
    if LANDMARKS != (24, 48, 72, 96, 120, 144):
        raise RD44P4Error("landmark registry drifted")
    if UNIVERSES != ("C2", "D2", "E2"):
        raise RD44P4Error("universe registry drifted")
    if DIRECTIONS != (
        "CALIBRATE_2022_EVALUATE_2023",
        "CALIBRATE_2023_EVALUATE_2022",
    ):
        raise RD44P4Error("direction registry drifted")
    if AXES != (
        "time_since_completed_high_water_hours",
        "recent_12h_high_water_increment_atr",
        "recent_12h_pullback_change_atr",
    ):
        raise RD44P4Error("dynamic axis registry drifted")
    if len(MODEL_BASIS) != 4:
        raise RD44P4Error("model basis dimension drifted")
    if ADJACENT_LANDMARK_PAIRS != (
        (24, 48),
        (48, 72),
        (72, 96),
        (96, 120),
        (120, 144),
    ):
        raise RD44P4Error("persistence registry drifted")


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
        raise RD44P4Error(f"{name} has unknown booleans: {unknown}")
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
        *AXES,
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
        raise RD44P4Error(f"state missing columns: {missing_state}")
    if missing_target:
        raise RD44P4Error(f"target missing columns: {missing_target}")

    if state["decision_id"].astype(str).duplicated().any():
        raise RD44P4Error("duplicate state decision_id")
    if target["decision_id"].astype(str).duplicated().any():
        raise RD44P4Error("duplicate target decision_id")

    state_ids = set(state["decision_id"].astype(str))
    target_ids = set(target["decision_id"].astype(str))
    if state_ids != target_ids:
        raise RD44P4Error(
            "decision registry mismatch: "
            f"missing_in_target={len(state_ids - target_ids)}, "
            f"missing_in_state={len(target_ids - state_ids)}"
        )
    if len(state_ids) != 1996:
        raise RD44P4Error(f"expected 1996 decision ids, got {len(state_ids)}")

    state_frame = state.copy()
    target_frame = target.copy()
    for frame in (state_frame, target_frame):
        frame["decision_id"] = frame["decision_id"].astype(str)
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
    if not (state_frame["data_quality_class"].astype(str) == VALID_STATE_CLASS).all():
        raise RD44P4Error("state ledger contains non-valid reconstruction rows")

    for axis in AXES:
        state_frame[axis] = pd.to_numeric(
            state_frame[axis],
            errors="raise",
        ).astype(float)
        values = state_frame[axis].to_numpy(float)
        if not np.isfinite(values).all():
            raise RD44P4Error(f"state axis is non-finite: {axis}")

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
        raise RD44P4Error("target row is both evaluable and right-censored")
    if bool((target_frame["target_evaluable"] & target_frame["rcv_return"].isna()).any()):
        raise RD44P4Error("evaluable target row is missing rcv_return")
    if bool((~target_frame["target_evaluable"] & target_frame["rcv_return"].notna()).any()):
        raise RD44P4Error("non-evaluable target row has rcv_return")
    evaluable_values = target_frame.loc[
        target_frame["target_evaluable"],
        "rcv_return",
    ].to_numpy(float)
    if not np.isfinite(evaluable_values).all():
        raise RD44P4Error("evaluable rcv_return contains non-finite value")

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
            raise RD44P4Error(f"join parity mismatch: {column}")

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
    if len(joined) != 1996:
        raise RD44P4Error(f"joined row count drifted: {len(joined)}")

    if set(joined["period_id"].unique()) != {
        "ROBUSTNESS_2022",
        "ROBUSTNESS_2023",
    }:
        raise RD44P4Error("joined period registry drifted")
    if set(joined["universe_id"].unique()) != set(UNIVERSES):
        raise RD44P4Error("joined universe registry drifted")
    if set(joined["landmark_age_hours"].unique()) != set(LANDMARKS):
        raise RD44P4Error("joined landmark registry drifted")

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
        raise RD44P4Error("empirical CDF needs non-empty 1D training values")
    if not np.isfinite(raw).all():
        raise RD44P4Error("empirical CDF training values non-finite")
    return np.sort(raw, kind="mergesort")


def apply_empirical_cdf(
    sorted_training: np.ndarray,
    values: np.ndarray,
) -> np.ndarray:
    raw = np.asarray(values, dtype=float)
    if raw.ndim != 1:
        raise RD44P4Error("CDF values must be 1D")
    if not np.isfinite(raw).all():
        raise RD44P4Error("CDF evaluation values non-finite")
    if len(sorted_training) == 0:
        raise RD44P4Error("CDF reference empty")
    return np.searchsorted(
        sorted_training,
        raw,
        side="right",
    ).astype(float) / float(len(sorted_training))


def design_matrix(
    axis_1: np.ndarray,
    axis_2: np.ndarray,
    axis_3: np.ndarray,
) -> np.ndarray:
    a = np.asarray(axis_1, dtype=float)
    b = np.asarray(axis_2, dtype=float)
    c = np.asarray(axis_3, dtype=float)
    if a.ndim != 1 or a.shape != b.shape or a.shape != c.shape:
        raise RD44P4Error("design axes shape mismatch")
    return np.column_stack(
        [
            np.ones(len(a), dtype=float),
            a,
            b,
            c,
        ]
    )


def fit_model(train: pd.DataFrame) -> FittedModel:
    if train.empty:
        raise RD44P4Error("cannot fit empty training cell")

    references = tuple(empirical_cdf_reference(train[axis].to_numpy(float)) for axis in AXES)
    transformed = tuple(
        apply_empirical_cdf(
            reference,
            train[axis].to_numpy(float),
        )
        for axis, reference in zip(
            AXES,
            references,
            strict=True,
        )
    )
    x = design_matrix(*transformed)
    y = train["rcv_return"].to_numpy(float)
    coefficients, _residuals, rank, _singular = np.linalg.lstsq(
        x,
        y,
        rcond=None,
    )
    if int(rank) != len(MODEL_BASIS):
        raise RD44P4Error(f"full design rank required, got {rank}/{len(MODEL_BASIS)}")
    if not np.isfinite(coefficients).all():
        raise RD44P4Error("OLS coefficients non-finite")

    return FittedModel(
        coefficients=coefficients,
        sorted_references=(
            references[0],
            references[1],
            references[2],
        ),
        train_row_count=int(len(train)),
        design_rank=int(rank),
    )


def predict(
    model: FittedModel,
    frame: pd.DataFrame,
) -> np.ndarray:
    transformed = tuple(
        apply_empirical_cdf(
            reference,
            frame[axis].to_numpy(float),
        )
        for axis, reference in zip(
            AXES,
            model.sorted_references,
            strict=True,
        )
    )
    values = design_matrix(*transformed) @ model.coefficients
    if not np.isfinite(values).all():
        raise RD44P4Error("prediction contains non-finite value")
    return values


def spearman(
    left: np.ndarray,
    right: np.ndarray,
) -> float:
    x = pd.Series(np.asarray(left, dtype=float)).rank(
        method="average",
    )
    y = pd.Series(np.asarray(right, dtype=float)).rank(
        method="average",
    )
    value = x.corr(y, method="pearson")
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
        raise RD44P4Error("AUC arrays shape mismatch")
    positives = int(labels.sum())
    negatives = int((~labels).sum())
    if positives == 0 or negatives == 0:
        return float("nan")
    ranks = pd.Series(values).rank(method="average").to_numpy(float)
    positive_rank_sum = float(ranks[labels].sum())
    return float(
        (positive_rank_sum - positives * (positives + 1) / 2.0) / float(positives * negatives)
    )


def stable_prediction_halves(
    evaluation: pd.DataFrame,
    predictions: np.ndarray,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    temp = evaluation[["decision_id", "rcv_return"]].copy()
    temp["prediction"] = np.asarray(
        predictions,
        dtype=float,
    )
    temp = temp.sort_values(
        ["prediction", "decision_id"],
        kind="stable",
    ).reset_index(drop=True)
    bottom_n = len(temp) // 2
    if bottom_n == 0 or bottom_n == len(temp):
        raise RD44P4Error("cannot split prediction halves")
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
        raise RD44P4Error("evaluation/prediction length mismatch")

    actual = evaluation["rcv_return"].to_numpy(float)
    pred = np.asarray(predictions, dtype=float)
    event = actual < 0.0

    rho = spearman(pred, actual)
    bottom, top = stable_prediction_halves(
        evaluation,
        pred,
    )
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
        "classification_support_pass": (classification_support),
        "negative_rcv_auc": auc,
        "actual_negative_event_median_prediction": (event_median_prediction),
        "actual_nonnegative_event_median_prediction": (non_event_median_prediction),
        "classification_point_pass": (classification_point_pass),
        "predicted_negative_subset_row_count": int(len(subset)),
        "predicted_negative_subset_unique_pairs": int(subset["pair"].astype(str).nunique()),
        "predicted_negative_subset_signal_days": (signal_day_count(subset)),
        "predicted_negative_subset_support_pass": (subset_support),
        "predicted_negative_subset_actual_mean_rcv": (subset_mean),
        "predicted_negative_subset_actual_median_rcv": (subset_median),
        "predicted_negative_subset_actual_negative_fraction": (subset_negative_fraction),
        "predicted_nonnegative_complement_actual_mean_rcv": (complement_mean),
        "negative_subset_point_pass": subset_point_pass,
    }


def _nan_metrics() -> dict[str, Any]:
    return {
        "evaluation_row_count": 0,
        "spearman_predicted_vs_actual": float("nan"),
        "predicted_bottom_half_actual_mean_rcv": float("nan"),
        "predicted_top_half_actual_mean_rcv": float("nan"),
        "continuous_point_pass": False,
        "actual_negative_row_count": 0,
        "actual_nonnegative_row_count": 0,
        "classification_support_pass": False,
        "negative_rcv_auc": float("nan"),
        "actual_negative_event_median_prediction": float("nan"),
        "actual_nonnegative_event_median_prediction": float("nan"),
        "classification_point_pass": False,
        "predicted_negative_subset_row_count": 0,
        "predicted_negative_subset_unique_pairs": 0,
        "predicted_negative_subset_signal_days": 0,
        "predicted_negative_subset_support_pass": False,
        "predicted_negative_subset_actual_mean_rcv": float("nan"),
        "predicted_negative_subset_actual_median_rcv": float("nan"),
        "predicted_negative_subset_actual_negative_fraction": float("nan"),
        "predicted_nonnegative_complement_actual_mean_rcv": float("nan"),
        "negative_subset_point_pass": False,
    }


def _cell_prefix(
    *,
    direction: str,
    universe: str,
    landmark: int,
    train: pd.DataFrame,
    evaluation: pd.DataFrame,
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
    if direction not in DIRECTIONS:
        raise RD44P4Error(f"unknown direction: {direction}")
    if universe not in UNIVERSES:
        raise RD44P4Error(f"unknown universe: {universe}")
    if landmark not in LANDMARKS:
        raise RD44P4Error(f"unknown landmark: {landmark}")

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

    prefix = _cell_prefix(
        direction=direction,
        universe=universe,
        landmark=landmark,
        train=train,
        evaluation=evaluation,
    )
    support_pass = bool(base_support_pass(train) and base_support_pass(evaluation))

    metrics = _nan_metrics()
    model: FittedModel | None = None
    fit_status = "NOT_FIT"
    if not support_pass:
        fit_status = "INSUFFICIENT_BASE_SUPPORT"
    else:
        try:
            model = fit_model(train)
        except RD44P4Error as exc:
            if "full design rank required" not in str(exc):
                raise
            fit_status = "DESIGN_RANK_FAIL"
        else:
            fit_status = "FIT_PASS"
            metrics = evaluate_metrics(
                evaluation,
                predict(model, evaluation),
            )

    lopo_rows: list[dict[str, Any]] = []
    pair_registry = sorted(set(train["pair"].astype(str)) | set(evaluation["pair"].astype(str)))
    for held_pair in pair_registry:
        train_lopo = train.loc[train["pair"].astype(str) != held_pair].copy()
        eval_lopo = evaluation.loc[evaluation["pair"].astype(str) != held_pair].copy()

        lopo_prefix = {
            "transport_direction": direction,
            "universe_id": universe,
            "landmark_age_hours": landmark,
            "held_out_pair": held_pair,
            "train_row_count": int(len(train_lopo)),
            "train_unique_pairs": int(train_lopo["pair"].astype(str).nunique()),
            "evaluation_row_count": int(len(eval_lopo)),
            "evaluation_unique_pairs": int(eval_lopo["pair"].astype(str).nunique()),
        }
        if not lopo_support_pass(
            train_lopo,
            eval_lopo,
        ):
            lopo_rows.append(
                {
                    **lopo_prefix,
                    "lopo_support_pass": False,
                    "design_rank": 0,
                    "fit_status": ("INSUFFICIENT_LOPO_SUPPORT"),
                    "continuous_lopo_pass": False,
                    "classification_lopo_auc_pass": False,
                    "negative_subset_lopo_pass": False,
                    **_nan_metrics(),
                }
            )
            continue

        try:
            lopo_model = fit_model(train_lopo)
        except RD44P4Error as exc:
            if "full design rank required" not in str(exc):
                raise
            lopo_rows.append(
                {
                    **lopo_prefix,
                    "lopo_support_pass": True,
                    "design_rank": 0,
                    "fit_status": "DESIGN_RANK_FAIL",
                    "continuous_lopo_pass": False,
                    "classification_lopo_auc_pass": False,
                    "negative_subset_lopo_pass": False,
                    **_nan_metrics(),
                }
            )
            continue

        lopo_metrics = evaluate_metrics(
            eval_lopo,
            predict(lopo_model, eval_lopo),
        )
        classification_lopo_auc_pass = bool(
            lopo_metrics["classification_support_pass"]
            and math.isfinite(lopo_metrics["negative_rcv_auc"])
            and lopo_metrics["negative_rcv_auc"] > 0.5
        )
        negative_subset_lopo_pass = bool(
            lopo_metrics["predicted_negative_subset_support_pass"]
            and lopo_metrics["predicted_negative_subset_actual_mean_rcv"] < 0.0
            and lopo_metrics["predicted_negative_subset_actual_negative_fraction"] > 0.5
        )
        lopo_rows.append(
            {
                **lopo_prefix,
                "lopo_support_pass": True,
                "design_rank": lopo_model.design_rank,
                "fit_status": "FIT_PASS",
                "continuous_lopo_pass": bool(lopo_metrics["continuous_point_pass"]),
                "classification_lopo_auc_pass": (classification_lopo_auc_pass),
                "negative_subset_lopo_pass": (negative_subset_lopo_pass),
                **lopo_metrics,
            }
        )

    all_lopo_continuous_pass = bool(
        lopo_rows and all(bool(row["continuous_lopo_pass"]) for row in lopo_rows)
    )
    all_lopo_classification_pass = bool(
        lopo_rows and all(bool(row["classification_lopo_auc_pass"]) for row in lopo_rows)
    )
    all_lopo_negative_subset_pass = bool(
        lopo_rows and all(bool(row["negative_subset_lopo_pass"]) for row in lopo_rows)
    )

    continuous_gate_pass = bool(
        support_pass
        and fit_status == "FIT_PASS"
        and metrics["continuous_point_pass"]
        and all_lopo_continuous_pass
    )
    classification_gate_pass = bool(
        support_pass
        and fit_status == "FIT_PASS"
        and metrics["classification_point_pass"]
        and all_lopo_classification_pass
    )
    negative_subset_gate_pass = bool(
        support_pass
        and fit_status == "FIT_PASS"
        and metrics["negative_subset_point_pass"]
        and all_lopo_negative_subset_pass
    )
    joint_qualified = bool(
        continuous_gate_pass and classification_gate_pass and negative_subset_gate_pass
    )

    common = {
        **prefix,
        "base_support_pass": support_pass,
        "design_rank": (model.design_rank if model is not None else 0),
        "fit_status": fit_status,
    }
    continuous_row = {
        **common,
        "spearman_predicted_vs_actual": metrics["spearman_predicted_vs_actual"],
        "predicted_bottom_half_actual_mean_rcv": metrics["predicted_bottom_half_actual_mean_rcv"],
        "predicted_top_half_actual_mean_rcv": metrics["predicted_top_half_actual_mean_rcv"],
        "continuous_point_pass": metrics["continuous_point_pass"],
        "lopo_run_count": len(lopo_rows),
        "all_lopo_continuous_pass": (all_lopo_continuous_pass),
        "continuous_gate_pass": continuous_gate_pass,
        "joint_cell_qualified": joint_qualified,
    }
    classification_row = {
        **common,
        "actual_negative_row_count": metrics["actual_negative_row_count"],
        "actual_nonnegative_row_count": metrics["actual_nonnegative_row_count"],
        "classification_support_pass": metrics["classification_support_pass"],
        "negative_rcv_auc": metrics["negative_rcv_auc"],
        "actual_negative_event_median_prediction": metrics[
            "actual_negative_event_median_prediction"
        ],
        "actual_nonnegative_event_median_prediction": metrics[
            "actual_nonnegative_event_median_prediction"
        ],
        "classification_point_pass": metrics["classification_point_pass"],
        "lopo_run_count": len(lopo_rows),
        "all_lopo_classification_auc_pass": (all_lopo_classification_pass),
        "classification_gate_pass": (classification_gate_pass),
        "joint_cell_qualified": joint_qualified,
    }
    subset_row = {
        **common,
        "predicted_negative_subset_row_count": metrics["predicted_negative_subset_row_count"],
        "predicted_negative_subset_unique_pairs": metrics["predicted_negative_subset_unique_pairs"],
        "predicted_negative_subset_signal_days": metrics["predicted_negative_subset_signal_days"],
        "predicted_negative_subset_support_pass": metrics["predicted_negative_subset_support_pass"],
        "predicted_negative_subset_actual_mean_rcv": metrics[
            "predicted_negative_subset_actual_mean_rcv"
        ],
        "predicted_negative_subset_actual_median_rcv": metrics[
            "predicted_negative_subset_actual_median_rcv"
        ],
        "predicted_negative_subset_actual_negative_fraction": metrics[
            "predicted_negative_subset_actual_negative_fraction"
        ],
        "predicted_nonnegative_complement_actual_mean_rcv": metrics[
            "predicted_nonnegative_complement_actual_mean_rcv"
        ],
        "negative_subset_point_pass": metrics["negative_subset_point_pass"],
        "lopo_run_count": len(lopo_rows),
        "all_lopo_negative_subset_pass": (all_lopo_negative_subset_pass),
        "negative_subset_gate_pass": (negative_subset_gate_pass),
        "joint_cell_qualified": joint_qualified,
    }
    coefficient_row = {
        **prefix,
        "base_support_pass": support_pass,
        "fit_status": fit_status,
        "design_rank": (model.design_rank if model is not None else 0),
        "beta_intercept": (float(model.coefficients[0]) if model is not None else float("nan")),
        "beta_cdf_time_since_completed_high_water_hours": (
            float(model.coefficients[1]) if model is not None else float("nan")
        ),
        "beta_cdf_recent_12h_high_water_increment_atr": (
            float(model.coefficients[2]) if model is not None else float("nan")
        ),
        "beta_cdf_recent_12h_pullback_change_atr": (
            float(model.coefficients[3]) if model is not None else float("nan")
        ),
        "joint_cell_qualified": joint_qualified,
    }

    return (
        continuous_row,
        classification_row,
        subset_row,
        coefficient_row,
        lopo_rows,
    )


def run_all_cells(
    joined: pd.DataFrame,
) -> dict[str, pd.DataFrame]:
    continuous_rows: list[dict[str, Any]] = []
    classification_rows: list[dict[str, Any]] = []
    subset_rows: list[dict[str, Any]] = []
    coefficient_rows: list[dict[str, Any]] = []
    lopo_rows: list[dict[str, Any]] = []

    total = len(DIRECTIONS) * len(UNIVERSES) * len(LANDMARKS)
    current = 0
    for direction in DIRECTIONS:
        for universe in UNIVERSES:
            for landmark in LANDMARKS:
                current += 1
                print(
                    f"RD44_P4_CELL_PROGRESS={current}/{total}:{direction}:{universe}:{landmark}",
                    flush=True,
                )
                (
                    continuous,
                    classification,
                    subset,
                    coefficients,
                    cell_lopo,
                ) = evaluate_cell(
                    joined,
                    direction=direction,
                    universe=universe,
                    landmark=landmark,
                )
                continuous_rows.append(continuous)
                classification_rows.append(classification)
                subset_rows.append(subset)
                coefficient_rows.append(coefficients)
                lopo_rows.extend(cell_lopo)

    return {
        "continuous": pd.DataFrame.from_records(continuous_rows),
        "classification": pd.DataFrame.from_records(classification_rows),
        "subset": pd.DataFrame.from_records(subset_rows),
        "coefficients": pd.DataFrame.from_records(coefficient_rows),
        "lopo": pd.DataFrame.from_records(lopo_rows),
    }


def landmark_qualification(
    continuous: pd.DataFrame,
    classification: pd.DataFrame,
    subset: pd.DataFrame,
) -> pd.DataFrame:
    keys = [
        "transport_direction",
        "universe_id",
        "landmark_age_hours",
    ]
    merged = (
        continuous[[*keys, "continuous_gate_pass"]]
        .merge(
            classification[[*keys, "classification_gate_pass"]],
            on=keys,
            validate="one_to_one",
        )
        .merge(
            subset[[*keys, "negative_subset_gate_pass"]],
            on=keys,
            validate="one_to_one",
        )
    )
    merged["joint_cell_qualified"] = (
        merged["continuous_gate_pass"].astype(bool)
        & merged["classification_gate_pass"].astype(bool)
        & merged["negative_subset_gate_pass"].astype(bool)
    )

    rows: list[dict[str, Any]] = []
    for direction in DIRECTIONS:
        for landmark in LANDMARKS:
            cell = merged.loc[
                (merged["transport_direction"].astype(str) == direction)
                & (merged["landmark_age_hours"].astype(int) == landmark)
            ]
            joint_count = int(cell["joint_cell_qualified"].astype(bool).sum())
            rows.append(
                {
                    "transport_direction": direction,
                    "landmark_age_hours": landmark,
                    "joint_qualified_universe_count": (joint_count),
                    "universe_count": len(UNIVERSES),
                    "landmark_qualified": bool(joint_count >= 2),
                    "qualified_universes": "|".join(
                        sorted(
                            cell.loc[
                                cell["joint_cell_qualified"].astype(bool),
                                "universe_id",
                            ].astype(str)
                        )
                    ),
                }
            )
    return pd.DataFrame.from_records(rows)


def persistent_pairs(
    qualification: pd.DataFrame,
    *,
    direction: str,
) -> list[list[int]]:
    qualified = set(
        qualification.loc[
            (qualification["transport_direction"].astype(str) == direction)
            & qualification["landmark_qualified"].astype(bool),
            "landmark_age_hours",
        ].astype(int)
    )
    return [
        [left, right]
        for left, right in ADJACENT_LANDMARK_PAIRS
        if left in qualified and right in qualified
    ]


def decision_from_persistence(
    forward_pairs: list[list[int]],
    reverse_pairs: list[list[int]],
) -> tuple[
    str,
    str,
    list[list[int]],
]:
    forward = {tuple(pair) for pair in forward_pairs}
    reverse = {tuple(pair) for pair in reverse_pairs}
    matching = sorted([list(pair) for pair in forward & reverse])
    if not forward_pairs:
        return (
            DECISION_UNQUALIFIED,
            NEXT_UNQUALIFIED,
            matching,
        )
    if not matching:
        return (
            DECISION_REGIME_DEPENDENT,
            NEXT_REGIME_DEPENDENT,
            matching,
        )
    return (
        DECISION_BIDIRECTIONAL,
        NEXT_BIDIRECTIONAL,
        matching,
    )
