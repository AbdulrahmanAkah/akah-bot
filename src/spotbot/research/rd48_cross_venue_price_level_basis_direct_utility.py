from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

FEATURES = [
    "BTC_ETH_MEAN_SIGNED_CROSS_VENUE_LOG_CLOSE_PRICE_BASIS",
    "BTC_ETH_CROSS_VENUE_LOG_CLOSE_PRICE_BASIS_DISPERSION",
]
LANDMARKS = [24, 48, 72, 96, 120, 144]
UNIVERSES = ["C2", "D2", "E2"]
PERIODS = ["ROBUSTNESS_2022", "ROBUSTNESS_2023"]
ADJACENT_PAIRS = [(24, 48), (48, 72), (72, 96), (96, 120), (120, 144)]

BASE_MIN_ROWS = 20
BASE_MIN_PAIRS = 5
BASE_MIN_DAYS = 10
CLASS_MIN_NEG = 10
CLASS_MIN_NONNEG = 10
SUBSET_MIN_ROWS = 10
SUBSET_MIN_PAIRS = 5
SUBSET_MIN_DAYS = 10
LOPO_MIN_ROWS = 12
LOPO_MIN_PAIRS = 4

DIRECTIONS = {
    "FORWARD": ("ROBUSTNESS_2022", "ROBUSTNESS_2023"),
    "REVERSE": ("ROBUSTNESS_2023", "ROBUSTNESS_2022"),
}


class EvaluationError(RuntimeError):
    pass


@dataclass(frozen=True)
class FitResult:
    beta: np.ndarray
    rank: int
    train_sorted: tuple[np.ndarray, np.ndarray]


def _bool_series(series: pd.Series) -> pd.Series:
    if series.dtype == bool:
        return series
    return (
        series.astype(str).str.strip().str.lower().map({"true": True, "false": False}).fillna(False)
    )


def support_stats(df: pd.DataFrame) -> dict[str, int | bool]:
    signal_day = pd.to_datetime(df["signal_time"], utc=True, errors="raise").dt.date
    rows = int(len(df))
    positions = int(df["control_position_id"].nunique())
    pairs = int(df["pair"].nunique())
    days = int(signal_day.nunique())
    return {
        "row_count": rows,
        "unique_position_count": positions,
        "unique_pair_count": pairs,
        "unique_signal_day_count": days,
        "support_pass": bool(
            positions >= BASE_MIN_ROWS and pairs >= BASE_MIN_PAIRS and days >= BASE_MIN_DAYS
        ),
    }


def ecdf_transform(train: np.ndarray, values: np.ndarray) -> np.ndarray:
    arr = np.asarray(train, dtype=float)
    vals = np.asarray(values, dtype=float)
    if arr.ndim != 1 or len(arr) == 0 or not np.isfinite(arr).all():
        raise EvaluationError("invalid ECDF training vector")
    ordered = np.sort(arr, kind="mergesort")
    return np.searchsorted(ordered, vals, side="right") / float(len(ordered))


def fit_ols(train: pd.DataFrame) -> FitResult:
    if len(train) == 0:
        raise EvaluationError("empty training set")
    transformed = []
    sorted_refs = []
    for feature in FEATURES:
        raw = train[feature].to_numpy(float)
        if not np.isfinite(raw).all():
            raise EvaluationError(f"nonfinite training feature: {feature}")
        ordered = np.sort(raw, kind="mergesort")
        sorted_refs.append(ordered)
        transformed.append(np.searchsorted(ordered, raw, side="right") / len(raw))
    x = np.column_stack([np.ones(len(train)), *transformed])
    y = train["rcv_return"].to_numpy(float)
    rank = int(np.linalg.matrix_rank(x))
    if rank != 3:
        raise EvaluationError(f"design rank {rank} != 3")
    beta, *_ = np.linalg.lstsq(x, y, rcond=None)
    return FitResult(beta=beta, rank=rank, train_sorted=tuple(sorted_refs))


def predict(fit: FitResult, evaluation: pd.DataFrame) -> np.ndarray:
    columns = []
    for feature, ordered in zip(FEATURES, fit.train_sorted, strict=True):
        raw = evaluation[feature].to_numpy(float)
        if not np.isfinite(raw).all():
            raise EvaluationError(f"nonfinite evaluation feature: {feature}")
        columns.append(np.searchsorted(ordered, raw, side="right") / len(ordered))
    x = np.column_stack([np.ones(len(evaluation)), *columns])
    return x @ fit.beta


def spearman(x: np.ndarray, y: np.ndarray) -> float:
    sx = pd.Series(np.asarray(x, dtype=float)).rank(method="average")
    sy = pd.Series(np.asarray(y, dtype=float)).rank(method="average")
    value = sx.corr(sy, method="pearson")
    return float(value) if pd.notna(value) else float("nan")


def auc_binary(labels: np.ndarray, scores: np.ndarray) -> float:
    labels = np.asarray(labels, dtype=bool)
    scores = np.asarray(scores, dtype=float)
    n_pos = int(labels.sum())
    n_neg = int((~labels).sum())
    if n_pos == 0 or n_neg == 0:
        return float("nan")
    ranks = pd.Series(scores).rank(method="average").to_numpy(float)
    rank_sum_pos = float(ranks[labels].sum())
    return float((rank_sum_pos - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg))


def stable_prediction_halves(
    evaluation: pd.DataFrame,
    predicted: np.ndarray,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    work = evaluation.copy()
    work["_predicted_rcv"] = np.asarray(predicted, dtype=float)
    work = work.sort_values(
        ["_predicted_rcv", "decision_id"],
        kind="mergesort",
    ).reset_index(drop=True)
    n_bottom = len(work) // 2
    return work.iloc[:n_bottom].copy(), work.iloc[n_bottom:].copy()


def continuous_metrics(
    evaluation: pd.DataFrame,
    predicted: np.ndarray,
) -> dict[str, Any]:
    actual = evaluation["rcv_return"].to_numpy(float)
    rho = spearman(predicted, actual)
    bottom, top = stable_prediction_halves(evaluation, predicted)
    bottom_mean = float(bottom["rcv_return"].mean()) if len(bottom) else float("nan")
    top_mean = float(top["rcv_return"].mean()) if len(top) else float("nan")
    return {
        "spearman_predicted_vs_actual": rho,
        "predicted_bottom_half_actual_mean_rcv": bottom_mean,
        "predicted_top_half_actual_mean_rcv": top_mean,
        "spearman_gt_zero": bool(math.isfinite(rho) and rho > 0.0),
        "top_half_mean_gt_bottom_half_mean": bool(
            math.isfinite(top_mean) and math.isfinite(bottom_mean) and top_mean > bottom_mean
        ),
    }


def classification_metrics(
    evaluation: pd.DataFrame,
    predicted: np.ndarray,
) -> dict[str, Any]:
    actual = evaluation["rcv_return"].to_numpy(float)
    event = actual < 0.0
    n_neg = int(event.sum())
    n_nonneg = int((~event).sum())
    adverse_score = -np.asarray(predicted, dtype=float)
    auc = auc_binary(event, adverse_score)
    med_neg = float(np.median(np.asarray(predicted)[event])) if n_neg else float("nan")
    med_nonneg = float(np.median(np.asarray(predicted)[~event])) if n_nonneg else float("nan")
    return {
        "negative_event_count": n_neg,
        "nonnegative_event_count": n_nonneg,
        "auc_adverse_score": auc,
        "median_predicted_rcv_negative_events": med_neg,
        "median_predicted_rcv_nonnegative_events": med_nonneg,
        "class_support_pass": bool(n_neg >= CLASS_MIN_NEG and n_nonneg >= CLASS_MIN_NONNEG),
        "auc_gt_0_5": bool(math.isfinite(auc) and auc > 0.5),
        "negative_event_median_pred_lt_nonnegative": bool(
            math.isfinite(med_neg) and math.isfinite(med_nonneg) and med_neg < med_nonneg
        ),
    }


def subset_metrics(
    evaluation: pd.DataFrame,
    predicted: np.ndarray,
) -> dict[str, Any]:
    work = evaluation.copy()
    work["_predicted_rcv"] = np.asarray(predicted, dtype=float)
    subset = work.loc[work["_predicted_rcv"] < 0.0].copy()
    complement = work.loc[work["_predicted_rcv"] >= 0.0].copy()

    if len(subset):
        signal_days = int(
            pd.to_datetime(
                subset["signal_time"],
                utc=True,
                errors="raise",
            ).dt.date.nunique()
        )
        pair_count = int(subset["pair"].nunique())
        mean_actual = float(subset["rcv_return"].mean())
        median_actual = float(subset["rcv_return"].median())
        negative_fraction = float((subset["rcv_return"] < 0.0).mean())
    else:
        signal_days = 0
        pair_count = 0
        mean_actual = median_actual = negative_fraction = float("nan")

    complement_mean = float(complement["rcv_return"].mean()) if len(complement) else float("nan")
    support = bool(
        len(subset) >= SUBSET_MIN_ROWS
        and pair_count >= SUBSET_MIN_PAIRS
        and signal_days >= SUBSET_MIN_DAYS
    )

    return {
        "subset_row_count": int(len(subset)),
        "subset_unique_pair_count": pair_count,
        "subset_unique_signal_day_count": signal_days,
        "subset_actual_mean_rcv": mean_actual,
        "subset_actual_median_rcv": median_actual,
        "subset_actual_negative_fraction": negative_fraction,
        "complement_actual_mean_rcv": complement_mean,
        "subset_support_pass": support,
        "subset_mean_lt_zero": bool(math.isfinite(mean_actual) and mean_actual < 0.0),
        "subset_median_lt_zero": bool(math.isfinite(median_actual) and median_actual < 0.0),
        "subset_negative_fraction_gt_0_5": bool(
            math.isfinite(negative_fraction) and negative_fraction > 0.5
        ),
        "subset_mean_lt_complement_mean": bool(
            math.isfinite(mean_actual)
            and math.isfinite(complement_mean)
            and mean_actual < complement_mean
        ),
    }


def _full_gate_flags(
    train: pd.DataFrame,
    evaluation: pd.DataFrame,
    predicted: np.ndarray,
) -> dict[str, Any]:
    train_support = support_stats(train)
    eval_support = support_stats(evaluation)
    continuous = continuous_metrics(evaluation, predicted)
    classification = classification_metrics(evaluation, predicted)
    subset = subset_metrics(evaluation, predicted)

    continuous_full = bool(
        train_support["support_pass"]
        and eval_support["support_pass"]
        and continuous["spearman_gt_zero"]
        and continuous["top_half_mean_gt_bottom_half_mean"]
    )
    classification_full = bool(
        train_support["support_pass"]
        and eval_support["support_pass"]
        and classification["class_support_pass"]
        and classification["auc_gt_0_5"]
        and classification["negative_event_median_pred_lt_nonnegative"]
    )
    subset_full = bool(
        train_support["support_pass"]
        and eval_support["support_pass"]
        and subset["subset_support_pass"]
        and subset["subset_mean_lt_zero"]
        and subset["subset_median_lt_zero"]
        and subset["subset_negative_fraction_gt_0_5"]
        and subset["subset_mean_lt_complement_mean"]
    )
    return {
        "train_support": train_support,
        "evaluation_support": eval_support,
        "continuous": continuous,
        "classification": classification,
        "subset": subset,
        "continuous_full_without_lopo": continuous_full,
        "classification_full_without_lopo": classification_full,
        "subset_full_without_lopo": subset_full,
    }


def evaluate_cell(
    train: pd.DataFrame,
    evaluation: pd.DataFrame,
    universe: str,
    landmark: int,
    direction: str,
) -> dict[str, Any]:
    base = {
        "universe_id": universe,
        "landmark_age_hours": int(landmark),
        "direction": direction,
        "training_period": DIRECTIONS[direction][0],
        "evaluation_period": DIRECTIONS[direction][1],
    }
    try:
        fit = fit_ols(train)
        predicted = predict(fit, evaluation)
        full = _full_gate_flags(train, evaluation, predicted)
        rank = fit.rank
    except EvaluationError as exc:
        return {
            **base,
            "model_fit_pass": False,
            "model_failure_reason": str(exc),
            "rank": 0,
            "coefficients": [],
            "full": None,
            "lopo": [],
            "continuous_gate_pass": False,
            "classification_gate_pass": False,
            "negative_subset_gate_pass": False,
            "joint_gate_pass": False,
        }

    pairs = sorted(set(train["pair"].astype(str)) | set(evaluation["pair"].astype(str)))
    lopo: list[dict[str, Any]] = []
    all_cont = True
    all_class_auc = True
    all_subset_required = True

    for removed in pairs:
        tr = train.loc[train["pair"].astype(str) != removed].copy()
        ev = evaluation.loc[evaluation["pair"].astype(str) != removed].copy()
        row: dict[str, Any] = {
            **base,
            "removed_pair": removed,
            "training_row_count": int(len(tr)),
            "evaluation_row_count": int(len(ev)),
            "training_pair_count": int(tr["pair"].nunique()),
            "evaluation_pair_count": int(ev["pair"].nunique()),
        }
        structural = bool(
            len(tr) >= LOPO_MIN_ROWS
            and len(ev) >= LOPO_MIN_ROWS
            and tr["pair"].nunique() >= LOPO_MIN_PAIRS
            and ev["pair"].nunique() >= LOPO_MIN_PAIRS
        )
        row["structural_support_pass"] = structural

        if not structural:
            row.update(
                {
                    "model_fit_pass": False,
                    "continuous_lopo_pass": False,
                    "classification_auc_lopo_pass": False,
                    "subset_required_lopo_pass": False,
                    "failure_reason": "LOPO_STRUCTURAL_SUPPORT_FAIL",
                }
            )
            all_cont = all_class_auc = all_subset_required = False
            lopo.append(row)
            continue

        try:
            lf = fit_ols(tr)
            lp = predict(lf, ev)
            lm = _full_gate_flags(tr, ev, lp)
            cont_pass = bool(
                lm["continuous"]["spearman_gt_zero"]
                and lm["continuous"]["top_half_mean_gt_bottom_half_mean"]
            )
            class_auc_pass = bool(
                lm["classification"]["class_support_pass"] and lm["classification"]["auc_gt_0_5"]
            )
            subset_required = bool(
                lm["subset"]["subset_support_pass"]
                and lm["subset"]["subset_mean_lt_zero"]
                and lm["subset"]["subset_negative_fraction_gt_0_5"]
            )
            row.update(
                {
                    "model_fit_pass": True,
                    "continuous_lopo_pass": cont_pass,
                    "classification_auc_lopo_pass": class_auc_pass,
                    "subset_required_lopo_pass": subset_required,
                    "spearman_predicted_vs_actual": lm["continuous"][
                        "spearman_predicted_vs_actual"
                    ],
                    "auc_adverse_score": lm["classification"]["auc_adverse_score"],
                    "subset_row_count": lm["subset"]["subset_row_count"],
                    "subset_actual_mean_rcv": lm["subset"]["subset_actual_mean_rcv"],
                    "subset_actual_negative_fraction": lm["subset"][
                        "subset_actual_negative_fraction"
                    ],
                }
            )
        except EvaluationError as exc:
            cont_pass = class_auc_pass = subset_required = False
            row.update(
                {
                    "model_fit_pass": False,
                    "continuous_lopo_pass": False,
                    "classification_auc_lopo_pass": False,
                    "subset_required_lopo_pass": False,
                    "failure_reason": str(exc),
                }
            )

        all_cont = all_cont and cont_pass
        all_class_auc = all_class_auc and class_auc_pass
        all_subset_required = all_subset_required and subset_required
        lopo.append(row)

    continuous_gate = bool(full["continuous_full_without_lopo"] and all_cont)
    classification_gate = bool(full["classification_full_without_lopo"] and all_class_auc)
    negative_subset_gate = bool(full["subset_full_without_lopo"] and all_subset_required)
    return {
        **base,
        "model_fit_pass": True,
        "model_failure_reason": "",
        "rank": rank,
        "coefficients": [float(v) for v in fit.beta],
        "full": full,
        "lopo": lopo,
        "continuous_gate_pass": continuous_gate,
        "classification_gate_pass": classification_gate,
        "negative_subset_gate_pass": negative_subset_gate,
        "joint_gate_pass": bool(continuous_gate and classification_gate and negative_subset_gate),
    }


def qualify_landmarks(
    cell_results: list[dict[str, Any]],
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for direction in DIRECTIONS:
        for landmark in LANDMARKS:
            matched = [
                row
                for row in cell_results
                if row["direction"] == direction and row["landmark_age_hours"] == landmark
            ]
            passing = sorted(row["universe_id"] for row in matched if row["joint_gate_pass"])
            rows.append(
                {
                    "direction": direction,
                    "landmark_age_hours": landmark,
                    "joint_passing_universe_count": len(passing),
                    "joint_passing_universes": "|".join(passing),
                    "landmark_qualified": len(passing) >= 2,
                }
            )
    return pd.DataFrame(rows)


def persistent_pairs(
    landmark_df: pd.DataFrame,
    direction: str,
) -> list[list[int]]:
    qualified = set(
        landmark_df.loc[
            (landmark_df["direction"] == direction)
            & landmark_df["landmark_qualified"].astype(bool),
            "landmark_age_hours",
        ].astype(int)
    )
    return [[a, b] for a, b in ADJACENT_PAIRS if a in qualified and b in qualified]


def decision_from_persistence(
    forward: list[list[int]],
    reverse: list[list[int]],
) -> tuple[str, str, list[list[int]]]:
    reverse_set = {tuple(v) for v in reverse}
    matching = [v for v in forward if tuple(v) in reverse_set]
    if matching:
        return (
            "RD48_CROSS_VENUE_PRICE_LEVEL_BASIS_DIRECT_UTILITY_BIDIRECTIONALLY_PERSISTENT",
            "RD48_P5_PREREGISTER_ISOLATED_ACTION_MAPPING_WITH_"
            "SLOT_ESCROW_AND_NO_EARLY_CAPITAL_REUSE",
            matching,
        )
    if forward:
        return (
            "RD48_CROSS_VENUE_PRICE_LEVEL_BASIS_DIRECT_UTILITY_"
            "FORWARD_ONLY_REGIME_DEPENDENT_NO_CONTEXT_RESCUE",
            "RD48_CLOSE_DIRECT_ACTION_MAPPING_FOR_THIS_SOURCE_AND_"
            "RETAIN_FORWARD_ONLY_EVIDENCE_AS_DIAGNOSTIC",
            [],
        )
    return (
        "RD48_CROSS_VENUE_PRICE_LEVEL_BASIS_DIRECT_UTILITY_UNQUALIFIED_NO_RESCUE",
        "RD48_CLOSE_OR_PREREGISTER_DISTINCT_DIRECT_UTILITY_INFORMATION_SOURCE_PRE_TARGET_EXPOSURE",
        [],
    )


def strict_join(
    state: pd.DataFrame,
    target: pd.DataFrame,
) -> pd.DataFrame:
    required_state = {
        "decision_id",
        "control_position_id",
        "universe_id",
        "period_id",
        "pair",
        "signal_time",
        "decision_time",
        "landmark_age_hours",
        "feature_valid",
        *FEATURES,
    }
    required_target = {
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
    missing_state = required_state - set(state.columns)
    missing_target = required_target - set(target.columns)
    if missing_state:
        raise EvaluationError(f"state missing columns: {sorted(missing_state)}")
    if missing_target:
        raise EvaluationError(f"target missing columns: {sorted(missing_target)}")
    if state["decision_id"].duplicated().any() or target["decision_id"].duplicated().any():
        raise EvaluationError("duplicate decision_id")
    if len(state) != 1996 or len(target) != 1996:
        raise EvaluationError(f"registry size drift state={len(state)} target={len(target)}")
    if set(state["decision_id"]) != set(target["decision_id"]):
        raise EvaluationError("decision_id registry mismatch")

    parity = [
        "control_position_id",
        "universe_id",
        "period_id",
        "pair",
        "decision_time",
        "landmark_age_hours",
    ]
    target_keep = [
        "decision_id",
        *parity,
        "target_evaluable",
        "rcv_return",
        "right_censored",
    ]
    joined = state.merge(
        target[target_keep],
        on="decision_id",
        how="left",
        validate="one_to_one",
        suffixes=("", "_target"),
    )
    for field in parity:
        left = joined[field].astype(str)
        right = joined[f"{field}_target"].astype(str)
        if not left.equals(right):
            raise EvaluationError(f"target parity mismatch: {field}")
        joined.drop(columns=[f"{field}_target"], inplace=True)

    joined["feature_valid"] = _bool_series(joined["feature_valid"])
    joined["target_evaluable"] = _bool_series(joined["target_evaluable"])
    joined["right_censored"] = _bool_series(joined["right_censored"])
    if not joined["target_evaluable"].all():
        raise EvaluationError("non-evaluable target rows present; no imputation allowed")
    if joined["right_censored"].any():
        raise EvaluationError("right-censored target rows present; no imputation allowed")
    if joined["rcv_return"].isna().any():
        raise EvaluationError("missing RCV values")
    return joined


def evaluate(joined: pd.DataFrame) -> dict[str, Any]:
    valid = joined.loc[joined["feature_valid"]].copy()
    if len(valid) != 1993:
        raise EvaluationError(f"valid feature count drift: {len(valid)}")
    if len(joined) - len(valid) != 3:
        raise EvaluationError("invalid feature count drift")

    cells: list[dict[str, Any]] = []
    for direction, (
        training_period,
        evaluation_period,
    ) in DIRECTIONS.items():
        for universe in UNIVERSES:
            for landmark in LANDMARKS:
                train = valid.loc[
                    (valid["period_id"] == training_period)
                    & (valid["universe_id"] == universe)
                    & (valid["landmark_age_hours"].astype(int) == landmark)
                ].copy()
                ev = valid.loc[
                    (valid["period_id"] == evaluation_period)
                    & (valid["universe_id"] == universe)
                    & (valid["landmark_age_hours"].astype(int) == landmark)
                ].copy()
                cells.append(
                    evaluate_cell(
                        train,
                        ev,
                        universe,
                        landmark,
                        direction,
                    )
                )

    landmarks = qualify_landmarks(cells)
    forward = persistent_pairs(landmarks, "FORWARD")
    reverse = persistent_pairs(landmarks, "REVERSE")
    decision, next_stage, matching = decision_from_persistence(
        forward,
        reverse,
    )
    return {
        "cells": cells,
        "landmarks": landmarks,
        "forward_persistent_pairs": forward,
        "reverse_persistent_pairs": reverse,
        "matching_persistent_pairs": matching,
        "decision": decision,
        "next_stage": next_stage,
    }


def write_outputs(
    joined: pd.DataFrame,
    result: dict[str, Any],
    output_dir: Path,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=False)

    joined.to_csv(
        output_dir / "joined-cross-venue-price-level-basis-rcv-ledger.csv",
        index=False,
        lineterminator="\n",
    )

    coeff_rows: list[dict[str, Any]] = []
    cont_rows: list[dict[str, Any]] = []
    class_rows: list[dict[str, Any]] = []
    subset_rows: list[dict[str, Any]] = []
    lopo_rows: list[dict[str, Any]] = []

    for cell in result["cells"]:
        base = {
            "direction": cell["direction"],
            "training_period": cell["training_period"],
            "evaluation_period": cell["evaluation_period"],
            "universe_id": cell["universe_id"],
            "landmark_age_hours": cell["landmark_age_hours"],
            "model_fit_pass": cell["model_fit_pass"],
            "rank": cell["rank"],
        }
        if cell["model_fit_pass"]:
            names = ["INTERCEPT", FEATURES[0], FEATURES[1]]
            for name, value in zip(
                names,
                cell["coefficients"],
                strict=True,
            ):
                coeff_rows.append(
                    {
                        **base,
                        "coefficient_name": name,
                        "coefficient_value": value,
                    }
                )
            full = cell["full"]
            cont_rows.append(
                {
                    **base,
                    **full["train_support"],
                    **{f"evaluation_{k}": v for k, v in full["evaluation_support"].items()},
                    **full["continuous"],
                    "all_lopo_continuous_pass": all(
                        bool(v["continuous_lopo_pass"]) for v in cell["lopo"]
                    ),
                    "continuous_gate_pass": cell["continuous_gate_pass"],
                }
            )
            class_rows.append(
                {
                    **base,
                    **full["classification"],
                    "all_lopo_auc_pass": all(
                        bool(v["classification_auc_lopo_pass"]) for v in cell["lopo"]
                    ),
                    "classification_gate_pass": cell["classification_gate_pass"],
                }
            )
            subset_rows.append(
                {
                    **base,
                    **full["subset"],
                    "all_lopo_subset_required_pass": all(
                        bool(v["subset_required_lopo_pass"]) for v in cell["lopo"]
                    ),
                    "negative_subset_gate_pass": cell["negative_subset_gate_pass"],
                }
            )
        else:
            cont_rows.append(
                {
                    **base,
                    "failure_reason": cell["model_failure_reason"],
                    "continuous_gate_pass": False,
                }
            )
            class_rows.append(
                {
                    **base,
                    "failure_reason": cell["model_failure_reason"],
                    "classification_gate_pass": False,
                }
            )
            subset_rows.append(
                {
                    **base,
                    "failure_reason": cell["model_failure_reason"],
                    "negative_subset_gate_pass": False,
                }
            )
        lopo_rows.extend(cell["lopo"])

    pd.DataFrame(coeff_rows).to_csv(
        output_dir / "cross-venue-price-level-basis-model-coefficients.csv",
        index=False,
        lineterminator="\n",
    )
    pd.DataFrame(cont_rows).to_csv(
        output_dir / "continuous-rcv-cell-evaluation.csv",
        index=False,
        lineterminator="\n",
    )
    pd.DataFrame(class_rows).to_csv(
        output_dir / "negative-rcv-classification-cell-evaluation.csv",
        index=False,
        lineterminator="\n",
    )
    pd.DataFrame(subset_rows).to_csv(
        output_dir / "negative-utility-subset-cell-evaluation.csv",
        index=False,
        lineterminator="\n",
    )
    pd.DataFrame(lopo_rows).to_csv(
        output_dir / "leave-one-pair-out-evaluation.csv",
        index=False,
        lineterminator="\n",
    )
    result["landmarks"].to_csv(
        output_dir / "landmark-qualification.csv",
        index=False,
        lineterminator="\n",
    )

    temporal = {
        "schema_version": "rd48-p4-temporal-persistence-qualification-v1",
        "forward_persistent_pairs": result["forward_persistent_pairs"],
        "reverse_persistent_pairs": result["reverse_persistent_pairs"],
        "matching_forward_reverse_persistent_pairs": result["matching_persistent_pairs"],
        "isolated_single_landmark_success_insufficient": True,
        "best_persistent_pair_selection_used": False,
    }
    (output_dir / "temporal-persistence-qualification.json").write_text(
        json.dumps(temporal, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    forward_cells = [row for row in result["cells"] if row["direction"] == "FORWARD"]
    reverse_cells = [row for row in result["cells"] if row["direction"] == "REVERSE"]
    evidence = {
        "schema_version": "rd48-p4-qualified-direct-utility-evidence-freeze-v1",
        "status": "PASS",
        "decision": result["decision"],
        "next_stage": result["next_stage"],
        "forward_continuous_gate_pass_cell_count": sum(
            row["continuous_gate_pass"] for row in forward_cells
        ),
        "forward_classification_gate_pass_cell_count": sum(
            row["classification_gate_pass"] for row in forward_cells
        ),
        "forward_negative_subset_gate_pass_cell_count": sum(
            row["negative_subset_gate_pass"] for row in forward_cells
        ),
        "forward_joint_qualified_cell_count": sum(row["joint_gate_pass"] for row in forward_cells),
        "reverse_continuous_gate_pass_cell_count": sum(
            row["continuous_gate_pass"] for row in reverse_cells
        ),
        "reverse_classification_gate_pass_cell_count": sum(
            row["classification_gate_pass"] for row in reverse_cells
        ),
        "reverse_negative_subset_gate_pass_cell_count": sum(
            row["negative_subset_gate_pass"] for row in reverse_cells
        ),
        "reverse_joint_qualified_cell_count": sum(row["joint_gate_pass"] for row in reverse_cells),
        "forward_persistent_pairs": result["forward_persistent_pairs"],
        "reverse_persistent_pairs": result["reverse_persistent_pairs"],
        "matching_forward_reverse_persistent_pairs": result["matching_persistent_pairs"],
        "threshold_optimization_used": False,
        "winner_selection_used": False,
        "context_selection_used": False,
        "action_mapping_executed": False,
        "economic_action_executed": False,
        "production_authorized": False,
        "2024_accessed": False,
    }
    (output_dir / "qualified-direct-utility-evidence-freeze.json").write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    report = {
        **evidence,
        "schema_version": "rd48-p4-direct-utility-report-v1",
        "joined_row_count": int(len(joined)),
        "target_evaluable_row_count": int(joined["target_evaluable"].sum()),
        "right_censored_row_count": int(joined["right_censored"].sum()),
        "valid_feature_row_count": int(joined["feature_valid"].sum()),
        "invalid_feature_row_count": int((~joined["feature_valid"]).sum()),
        "model_family": "LOW_CAPACITY_OLS",
        "model_basis_dimension": 3,
        "model_fit_performed": True,
        "rcv_values_loaded": True,
        "rcv_associations_computed": True,
        "raw_market_data_loaded": False,
        "post_2024_accessed": False,
        "portfolio_replay_performed": False,
        "slot_escrow_executed": False,
        "parameter_search_used": False,
        "landmark_selection_used": False,
        "p4_action_mapping_executed": False,
        "p4_capital_reuse_before_control_exit": False,
        "p4_confirmation_window_created": False,
        "p4_economic_action_executed": False,
        "p4_exit_rule_created": False,
        "p4_full_liquidation_rule_created": False,
        "p4_partial_derisk_rule_created": False,
        "p4_portfolio_replay_executed": False,
        "p4_slot_escrow_executed": False,
    }
    (output_dir / "rd48-p4-direct-utility-report-v1.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return report
