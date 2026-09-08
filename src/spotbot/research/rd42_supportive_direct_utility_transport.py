"""RD42-P4 supportive-context direct-utility temporal transport diagnostic.

Frozen research contract:
- Read only frozen RD41 target/feature ledgers + RD42 causal context assignments.
- Primary context SUPPORTIVE only.
- Landmarks 24h and 48h only.
- Three pre-existing continuous channels only.
- No new market data, feature engineering, model fit, threshold search, action mapping,
  portfolio replay, capital reuse, 2024 access, or production authorization.
"""

from __future__ import annotations

import math
from typing import Any, Final

import numpy as np
import pandas as pd

PERIODS: Final = ("ROBUSTNESS_2022", "ROBUSTNESS_2023")
UNIVERSES: Final = ("C2", "D2", "E2")
LANDMARKS: Final = (24, 48)
FEATURES: Final = ("ENTRY_MARGIN", "RECENT_12H_RETURN", "PATH_POSITION")
PRIMARY_CONTEXT: Final = "SUPPORTIVE"

FORWARD: Final = "CALIBRATE_2022_EVALUATE_2023"
REVERSE: Final = "CALIBRATE_2023_EVALUATE_2022"
DIRECTIONS: Final = (FORWARD, REVERSE)

MIN_POSITIONS: Final = 20
MIN_PAIRS: Final = 5
MIN_SIGNAL_DAYS: Final = 10
MIN_NEGATIVE_EVENTS: Final = 10
MIN_NONNEGATIVE_NONEVENTS: Final = 10

TAIL_Q: Final = 0.25
TAIL_MIN_POSITIONS: Final = 10
TAIL_MIN_PAIRS: Final = 3
TAIL_MIN_SIGNAL_DAYS: Final = 5

QUALIFIED: Final = "QUALIFIED_EXPECTED_DIRECTION"
REVERSED: Final = "REVERSED_DIRECTION"
NO_EDGE: Final = "NO_DIRECTIONAL_EDGE"
INSUFFICIENT: Final = "INSUFFICIENT_SUPPORT"
UNEVALUABLE: Final = "UNEVALUABLE_CHANNEL"

SUCCESS_DECISION: Final = (
    "RD42_SUPPORTIVE_CONTEXT_DIRECT_UTILITY_EVIDENCE_QUALIFIED_PRE_ACTION_MAPPING"
)
FAILURE_DECISION: Final = (
    "RD42_SUPPORTIVE_CONTEXT_DIRECT_UTILITY_CHANNELS_UNQUALIFIED_REASSESS_INFORMATION_ARCHITECTURE"
)
SUCCESS_NEXT: Final = (
    "RD42_P5_PREREGISTER_ISOLATED_ACTION_MAPPING_WITH_SLOT_ESCROW_AND_NO_CAPITAL_REUSE"
)
FAILURE_NEXT: Final = (
    "RD42_CLOSE_OR_PREREGISTER_NEW_DIRECT_UTILITY_INFORMATION_SOURCE_"
    "WITHOUT_POST_HOC_THRESHOLD_RESCUE"
)


class RD42P4Error(RuntimeError):
    """Frozen RD42-P4 contract violation."""


def validate_constants() -> None:
    if PERIODS != ("ROBUSTNESS_2022", "ROBUSTNESS_2023"):
        raise RD42P4Error("period registry drifted")
    if UNIVERSES != ("C2", "D2", "E2"):
        raise RD42P4Error("universe registry drifted")
    if LANDMARKS != (24, 48):
        raise RD42P4Error("landmark registry drifted")
    if FEATURES != ("ENTRY_MARGIN", "RECENT_12H_RETURN", "PATH_POSITION"):
        raise RD42P4Error("feature registry drifted")
    if PRIMARY_CONTEXT != "SUPPORTIVE":
        raise RD42P4Error("primary context drifted")
    if not math.isclose(TAIL_Q, 0.25):
        raise RD42P4Error("tail quantile drifted")


def bool_series(values: pd.Series, *, field: str) -> pd.Series:
    """Strictly parse bool-like CSV fields; never rely on astype(bool)."""
    if pd.api.types.is_bool_dtype(values):
        return values.astype(bool)
    normalized = values.astype(str).str.strip().str.lower()
    mapping = {
        "true": True,
        "false": False,
        "1": True,
        "0": False,
    }
    unexpected = sorted(set(normalized.unique()).difference(mapping))
    if unexpected:
        raise RD42P4Error(f"invalid boolean values for {field}: {unexpected}")
    return normalized.map(mapping).astype(bool)


def direction_periods(direction: str) -> tuple[str, str]:
    if direction == FORWARD:
        return "ROBUSTNESS_2022", "ROBUSTNESS_2023"
    if direction == REVERSE:
        return "ROBUSTNESS_2023", "ROBUSTNESS_2022"
    raise RD42P4Error(f"unknown transport direction: {direction}")


def average_rank(values: pd.Series) -> np.ndarray:
    return pd.Series(values, dtype=float).rank(method="average").to_numpy(float)


def auc_binary(labels: pd.Series, scores: pd.Series) -> float:
    y = pd.to_numeric(labels, errors="raise").astype(int).to_numpy()
    s = pd.to_numeric(scores, errors="raise").astype(float).to_numpy()
    if len(y) == 0 or len(y) != len(s):
        return float("nan")
    pos = y == 1
    neg = y == 0
    n_pos = int(pos.sum())
    n_neg = int(neg.sum())
    if n_pos == 0 or n_neg == 0:
        return float("nan")
    ranks = average_rank(pd.Series(s))
    rank_sum_pos = float(ranks[pos].sum())
    return float((rank_sum_pos - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg))


def spearman_rho(x: pd.Series, y: pd.Series) -> float:
    if len(x) < 2 or len(x) != len(y):
        return float("nan")
    xr = average_rank(x)
    yr = average_rank(y)
    if np.isclose(np.std(xr), 0.0) or np.isclose(np.std(yr), 0.0):
        return float("nan")
    return float(np.corrcoef(xr, yr)[0, 1])


def signal_days(frame: pd.DataFrame) -> int:
    if frame.empty:
        return 0
    return int(
        pd.to_datetime(frame["signal_time"], utc=True, errors="raise").dt.floor("D").nunique()
    )


def support(frame: pd.DataFrame) -> dict[str, Any]:
    positions = int(frame["control_position_id"].astype(str).nunique())
    pairs = int(frame["pair"].astype(str).nunique())
    days = signal_days(frame)
    return {
        "unique_control_position_count": positions,
        "unique_pair_count": pairs,
        "unique_signal_day_count": days,
        "support_pass": bool(
            positions >= MIN_POSITIONS and pairs >= MIN_PAIRS and days >= MIN_SIGNAL_DAYS
        ),
    }


def tail_support(frame: pd.DataFrame) -> dict[str, Any]:
    positions = int(frame["control_position_id"].astype(str).nunique())
    pairs = int(frame["pair"].astype(str).nunique())
    days = signal_days(frame)
    return {
        "tail_unique_control_position_count": positions,
        "tail_unique_pair_count": pairs,
        "tail_unique_signal_day_count": days,
        "tail_support_pass": bool(
            positions >= TAIL_MIN_POSITIONS
            and pairs >= TAIL_MIN_PAIRS
            and days >= TAIL_MIN_SIGNAL_DAYS
        ),
    }


def _normalize_time(values: pd.Series) -> pd.Series:
    return pd.to_datetime(values, utc=True, errors="raise").dt.as_unit("ns")


def build_analysis_base(
    targets: pd.DataFrame,
    features: pd.DataFrame,
    contexts: pd.DataFrame,
) -> pd.DataFrame:
    """Join frozen ledgers without rebuilding targets, features, or context."""
    target_required = {
        "decision_id",
        "control_position_id",
        "universe_id",
        "period_id",
        "pair",
        "signal_time",
        "landmark_age_hours",
        "rcv_return",
        "target_evaluable",
        "right_censored",
    }
    feature_required = {
        "decision_id",
        "control_position_id",
        "universe_id",
        "period_id",
        "pair",
        "signal_time",
        "landmark_age_hours",
        "feature_id",
        "feature_value",
        "feature_evaluable",
    }
    context_required = {
        "decision_id",
        "control_position_id",
        "universe_id",
        "period_id",
        "pair",
        "signal_time",
        "landmark_age_hours",
        "resolved_target",
        "right_censored_target",
        "market_context",
        "data_completeness_class",
    }
    for label, frame, required in (
        ("target", targets, target_required),
        ("feature", features, feature_required),
        ("context", contexts, context_required),
    ):
        missing = sorted(required.difference(frame.columns))
        if missing:
            raise RD42P4Error(f"{label} ledger missing fields: {missing}")

    target = targets.loc[targets["landmark_age_hours"].isin(LANDMARKS)].copy()
    target_eval = bool_series(target["target_evaluable"], field="target_evaluable")
    target_censored = bool_series(target["right_censored"], field="right_censored")
    target = target.loc[target_eval & ~target_censored].copy()

    target["signal_time"] = _normalize_time(target["signal_time"])
    target["rcv_return"] = pd.to_numeric(target["rcv_return"], errors="raise").astype(float)
    if not np.isfinite(target["rcv_return"].to_numpy()).all():
        raise RD42P4Error("non-finite RCV entered P4")
    if target["decision_id"].astype(str).duplicated().any():
        raise RD42P4Error("duplicate target decision_id")

    context = contexts.loc[
        contexts["landmark_age_hours"].isin(LANDMARKS)
        & (contexts["market_context"].astype(str) == PRIMARY_CONTEXT)
    ].copy()
    context_resolved = bool_series(context["resolved_target"], field="resolved_target")
    context_censored = bool_series(context["right_censored_target"], field="right_censored_target")
    context = context.loc[context_resolved & ~context_censored].copy()
    if (context["data_completeness_class"].astype(str) != "OBSERVED_VALID").any():
        raise RD42P4Error("non-observed-valid context entered P4")
    context["signal_time"] = _normalize_time(context["signal_time"])

    structural_key = [
        "control_position_id",
        "universe_id",
        "period_id",
        "landmark_age_hours",
    ]
    if context.duplicated(structural_key).any():
        raise RD42P4Error("duplicate context structural key")

    context_keep = context[
        structural_key + ["pair", "signal_time", "decision_id", "market_context"]
    ].rename(
        columns={
            "pair": "context_pair",
            "signal_time": "context_signal_time",
            "decision_id": "context_decision_id",
        }
    )

    merged = target.merge(
        context_keep,
        on=structural_key,
        how="inner",
        validate="one_to_one",
    )
    if merged.empty:
        raise RD42P4Error("no target rows matched SUPPORTIVE context")
    if not (merged["pair"].astype(str) == merged["context_pair"].astype(str)).all():
        raise RD42P4Error("target/context pair mismatch")
    if not (merged["signal_time"] == merged["context_signal_time"]).all():
        raise RD42P4Error("target/context signal_time mismatch")

    supportive_target_ids = set(merged["decision_id"].astype(str))
    feature = features.loc[
        features["landmark_age_hours"].isin(LANDMARKS)
        & features["feature_id"].astype(str).isin(FEATURES)
        & features["decision_id"].astype(str).isin(supportive_target_ids)
    ].copy()
    feature_eval = bool_series(feature["feature_evaluable"], field="feature_evaluable")
    feature = feature.loc[feature_eval].copy()
    feature["signal_time"] = _normalize_time(feature["signal_time"])
    feature["feature_value"] = pd.to_numeric(feature["feature_value"], errors="raise").astype(float)
    if not np.isfinite(feature["feature_value"].to_numpy()).all():
        raise RD42P4Error("non-finite feature value entered P4")

    if feature.duplicated(["decision_id", "feature_id"]).any():
        raise RD42P4Error("duplicate feature decision/channel row")

    target_base = merged[
        [
            "decision_id",
            "control_position_id",
            "universe_id",
            "period_id",
            "pair",
            "signal_time",
            "landmark_age_hours",
            "rcv_return",
            "market_context",
        ]
    ].copy()

    result = feature.merge(
        target_base,
        on="decision_id",
        how="inner",
        suffixes=("_feature", ""),
        validate="many_to_one",
    )
    metadata_checks = (
        ("control_position_id_feature", "control_position_id"),
        ("universe_id_feature", "universe_id"),
        ("period_id_feature", "period_id"),
        ("pair_feature", "pair"),
        ("signal_time_feature", "signal_time"),
        ("landmark_age_hours_feature", "landmark_age_hours"),
    )
    for left, right in metadata_checks:
        if not (result[left].astype(str) == result[right].astype(str)).all():
            if "time" in left:
                if not (
                    pd.to_datetime(result[left], utc=True)
                    == pd.to_datetime(result[right], utc=True)
                ).all():
                    raise RD42P4Error(f"feature/target metadata mismatch: {left}")
            else:
                raise RD42P4Error(f"feature/target metadata mismatch: {left}")

    keep = result[
        [
            "decision_id",
            "control_position_id",
            "universe_id",
            "period_id",
            "pair",
            "signal_time",
            "landmark_age_hours",
            "rcv_return",
            "market_context",
            "feature_id",
            "feature_value",
        ]
    ].copy()
    keep["rcv_negative"] = keep["rcv_return"] < 0.0

    if not set(keep["period_id"].astype(str)).issubset(PERIODS):
        raise RD42P4Error("unexpected period in analysis base")
    if not set(keep["universe_id"].astype(str)).issubset(UNIVERSES):
        raise RD42P4Error("unexpected universe in analysis base")
    if not set(keep["feature_id"].astype(str)).issubset(FEATURES):
        raise RD42P4Error("unexpected feature in analysis base")
    if (keep["market_context"].astype(str) != PRIMARY_CONTEXT).any():
        raise RD42P4Error("non-SUPPORTIVE row entered analysis base")
    return keep.sort_values(
        [
            "period_id",
            "universe_id",
            "landmark_age_hours",
            "feature_id",
            "decision_id",
        ],
        kind="stable",
    ).reset_index(drop=True)


def empirical_positive_score(
    training_values: np.ndarray,
    evaluation_values: np.ndarray,
) -> np.ndarray:
    train = np.asarray(training_values, dtype=float)
    test = np.asarray(evaluation_values, dtype=float)
    if len(train) == 0:
        raise RD42P4Error("empty calibration distribution")
    if not np.isfinite(train).all() or not np.isfinite(test).all():
        raise RD42P4Error("non-finite feature in empirical score")
    return np.asarray(
        [(train <= value).mean() for value in test],
        dtype=float,
    )


def training_q25(training_values: np.ndarray) -> float:
    values = np.asarray(training_values, dtype=float)
    if len(values) == 0 or not np.isfinite(values).all():
        return float("nan")
    return float(np.quantile(values, TAIL_Q, method="linear"))


def score_evaluation_rows(
    calibration: pd.DataFrame,
    evaluation: pd.DataFrame,
) -> pd.DataFrame:
    if calibration.empty or evaluation.empty:
        return pd.DataFrame()
    scored = evaluation.copy()
    scored["positive_score"] = empirical_positive_score(
        calibration["feature_value"].to_numpy(float),
        evaluation["feature_value"].to_numpy(float),
    )
    scored["adverse_score"] = 1.0 - scored["positive_score"]
    q25 = training_q25(calibration["feature_value"].to_numpy(float))
    scored["training_feature_q25"] = q25
    scored["negative_utility_tail"] = scored["feature_value"] <= q25
    if bool((scored["positive_score"] < 0.0).any() or (scored["positive_score"] > 1.0).any()):
        raise RD42P4Error("positive score outside [0,1]")
    return scored


def transport_cell(
    base: pd.DataFrame,
    *,
    direction: str,
    universe: str,
    landmark: int,
    feature: str,
    exclude_pair: str | None = None,
) -> pd.DataFrame:
    calibration_period, evaluation_period = direction_periods(direction)
    common = (
        (base["universe_id"].astype(str) == universe)
        & (base["landmark_age_hours"] == landmark)
        & (base["feature_id"].astype(str) == feature)
    )
    calibration = base.loc[common & (base["period_id"].astype(str) == calibration_period)].copy()
    evaluation = base.loc[common & (base["period_id"].astype(str) == evaluation_period)].copy()
    if exclude_pair is not None:
        calibration = calibration.loc[calibration["pair"].astype(str) != exclude_pair].copy()
        evaluation = evaluation.loc[evaluation["pair"].astype(str) != exclude_pair].copy()
    return score_evaluation_rows(calibration, evaluation)


def lopo_pairs(
    base: pd.DataFrame,
    *,
    direction: str,
    universe: str,
    landmark: int,
    feature: str,
) -> list[str]:
    _calibration_period, evaluation_period = direction_periods(direction)
    rows = base.loc[
        (base["period_id"].astype(str) == evaluation_period)
        & (base["universe_id"].astype(str) == universe)
        & (base["landmark_age_hours"] == landmark)
        & (base["feature_id"].astype(str) == feature)
    ]
    return sorted(rows["pair"].astype(str).unique())


def continuous_metrics(frame: pd.DataFrame) -> dict[str, Any]:
    if frame.empty:
        return {
            "spearman_rho": np.nan,
            "lower_score_count": 0,
            "upper_score_count": 0,
            "lower_score_mean_rcv": np.nan,
            "upper_score_mean_rcv": np.nan,
            "upper_minus_lower_mean_rcv_spread": np.nan,
        }
    lower = frame.loc[frame["positive_score"] < 0.50]
    upper = frame.loc[frame["positive_score"] >= 0.50]
    rho = spearman_rho(frame["positive_score"], frame["rcv_return"])
    lower_mean = float(lower["rcv_return"].mean()) if len(lower) else np.nan
    upper_mean = float(upper["rcv_return"].mean()) if len(upper) else np.nan
    spread = (
        float(upper_mean - lower_mean)
        if np.isfinite(lower_mean) and np.isfinite(upper_mean)
        else np.nan
    )
    return {
        "spearman_rho": rho,
        "lower_score_count": int(len(lower)),
        "upper_score_count": int(len(upper)),
        "lower_score_mean_rcv": lower_mean,
        "upper_score_mean_rcv": upper_mean,
        "upper_minus_lower_mean_rcv_spread": spread,
    }


def negative_classification_metrics(frame: pd.DataFrame) -> dict[str, Any]:
    if frame.empty:
        return {
            "negative_event_count": 0,
            "nonnegative_nonevent_count": 0,
            "auc": np.nan,
            "event_median_adverse_score": np.nan,
            "nonevent_median_adverse_score": np.nan,
            "event_minus_nonevent_median_adverse_score_spread": np.nan,
        }
    labels = frame["rcv_negative"].astype(bool).astype(int)
    event = frame.loc[labels == 1]
    nonevent = frame.loc[labels == 0]
    auc = auc_binary(labels, frame["adverse_score"])
    event_median = float(event["adverse_score"].median()) if len(event) else np.nan
    nonevent_median = float(nonevent["adverse_score"].median()) if len(nonevent) else np.nan
    spread = (
        float(event_median - nonevent_median)
        if np.isfinite(event_median) and np.isfinite(nonevent_median)
        else np.nan
    )
    return {
        "negative_event_count": int(len(event)),
        "nonnegative_nonevent_count": int(len(nonevent)),
        "auc": auc,
        "event_median_adverse_score": event_median,
        "nonevent_median_adverse_score": nonevent_median,
        "event_minus_nonevent_median_adverse_score_spread": spread,
    }


def tail_metrics(frame: pd.DataFrame) -> dict[str, Any]:
    tail = frame.loc[frame["negative_utility_tail"].astype(bool)].copy()
    ts = tail_support(tail)
    return {
        **ts,
        "tail_row_count": int(len(tail)),
        "tail_mean_rcv": (float(tail["rcv_return"].mean()) if len(tail) else np.nan),
        "tail_median_rcv": (float(tail["rcv_return"].median()) if len(tail) else np.nan),
        "training_feature_q25": (
            float(frame["training_feature_q25"].iloc[0]) if len(frame) else np.nan
        ),
    }


def _classify_signed(
    *,
    support_pass: bool,
    expected_values: list[float],
    reversed_values: list[float],
    finite_required: list[float],
) -> str:
    if not support_pass:
        return INSUFFICIENT
    if not all(np.isfinite(value) for value in finite_required):
        return UNEVALUABLE
    if all(value > 0.0 for value in expected_values):
        return QUALIFIED
    if all(value > 0.0 for value in reversed_values):
        return REVERSED
    return NO_EDGE


def evaluate_continuous_rcv(base: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for direction in DIRECTIONS:
        for landmark in LANDMARKS:
            for universe in UNIVERSES:
                for feature in FEATURES:
                    cell = transport_cell(
                        base,
                        direction=direction,
                        universe=universe,
                        landmark=landmark,
                        feature=feature,
                    )
                    supp = support(cell)
                    metrics = continuous_metrics(cell)

                    lopo_spreads: list[float] = []
                    lopo_complete = True
                    for pair in lopo_pairs(
                        base,
                        direction=direction,
                        universe=universe,
                        landmark=landmark,
                        feature=feature,
                    ):
                        lopo = transport_cell(
                            base,
                            direction=direction,
                            universe=universe,
                            landmark=landmark,
                            feature=feature,
                            exclude_pair=pair,
                        )
                        spread = continuous_metrics(lopo)["upper_minus_lower_mean_rcv_spread"]
                        if not np.isfinite(spread):
                            lopo_complete = False
                            break
                        lopo_spreads.append(float(spread))

                    lopo_min = min(lopo_spreads) if lopo_spreads else np.nan
                    lopo_max = max(lopo_spreads) if lopo_spreads else np.nan
                    finite = [
                        float(metrics["spearman_rho"]),
                        float(metrics["upper_minus_lower_mean_rcv_spread"]),
                        float(lopo_min),
                        float(lopo_max),
                    ]
                    if not lopo_complete:
                        finite.append(np.nan)
                    outcome = _classify_signed(
                        support_pass=bool(supp["support_pass"]),
                        expected_values=[
                            float(metrics["spearman_rho"]),
                            float(metrics["upper_minus_lower_mean_rcv_spread"]),
                            float(lopo_min),
                        ],
                        reversed_values=[
                            -float(metrics["spearman_rho"]),
                            -float(metrics["upper_minus_lower_mean_rcv_spread"]),
                            -float(lopo_max),
                        ],
                        finite_required=finite,
                    )
                    rows.append(
                        {
                            "transport_direction": direction,
                            "evaluation_period": direction_periods(direction)[1],
                            "market_context": PRIMARY_CONTEXT,
                            "landmark_age_hours": landmark,
                            "universe_id": universe,
                            "feature_id": feature,
                            "decision_row_count": int(len(cell)),
                            **supp,
                            **metrics,
                            "lopo_complete": lopo_complete,
                            "lopo_pair_count": len(lopo_spreads),
                            "lopo_minimum_rcv_spread": lopo_min,
                            "lopo_maximum_rcv_spread": lopo_max,
                            "cell_outcome": outcome,
                        }
                    )
    return pd.DataFrame.from_records(rows)


def evaluate_negative_rcv(base: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for direction in DIRECTIONS:
        for landmark in LANDMARKS:
            for universe in UNIVERSES:
                for feature in FEATURES:
                    cell = transport_cell(
                        base,
                        direction=direction,
                        universe=universe,
                        landmark=landmark,
                        feature=feature,
                    )
                    supp = support(cell)
                    metrics = negative_classification_metrics(cell)
                    event_support = (
                        int(metrics["negative_event_count"]) >= MIN_NEGATIVE_EVENTS
                        and int(metrics["nonnegative_nonevent_count"]) >= MIN_NONNEGATIVE_NONEVENTS
                    )
                    classification_support = bool(supp["support_pass"] and event_support)

                    lopo_aucs: list[float] = []
                    lopo_complete = True
                    for pair in lopo_pairs(
                        base,
                        direction=direction,
                        universe=universe,
                        landmark=landmark,
                        feature=feature,
                    ):
                        lopo = transport_cell(
                            base,
                            direction=direction,
                            universe=universe,
                            landmark=landmark,
                            feature=feature,
                            exclude_pair=pair,
                        )
                        auc = negative_classification_metrics(lopo)["auc"]
                        if not np.isfinite(auc):
                            lopo_complete = False
                            break
                        lopo_aucs.append(float(auc))

                    lopo_min = min(lopo_aucs) if lopo_aucs else np.nan
                    lopo_max = max(lopo_aucs) if lopo_aucs else np.nan
                    finite = [
                        float(metrics["auc"]),
                        float(metrics["event_minus_nonevent_median_adverse_score_spread"]),
                        float(lopo_min),
                        float(lopo_max),
                    ]
                    if not lopo_complete:
                        finite.append(np.nan)
                    outcome = _classify_signed(
                        support_pass=classification_support,
                        expected_values=[
                            float(metrics["auc"]) - 0.5,
                            float(metrics["event_minus_nonevent_median_adverse_score_spread"]),
                            float(lopo_min) - 0.5,
                        ],
                        reversed_values=[
                            0.5 - float(metrics["auc"]),
                            -float(metrics["event_minus_nonevent_median_adverse_score_spread"]),
                            0.5 - float(lopo_max),
                        ],
                        finite_required=finite,
                    )
                    rows.append(
                        {
                            "transport_direction": direction,
                            "evaluation_period": direction_periods(direction)[1],
                            "market_context": PRIMARY_CONTEXT,
                            "landmark_age_hours": landmark,
                            "universe_id": universe,
                            "feature_id": feature,
                            "decision_row_count": int(len(cell)),
                            **supp,
                            **metrics,
                            "event_support_pass": event_support,
                            "classification_support_pass": classification_support,
                            "lopo_complete": lopo_complete,
                            "lopo_pair_count": len(lopo_aucs),
                            "lopo_minimum_auc": lopo_min,
                            "lopo_maximum_auc": lopo_max,
                            "cell_outcome": outcome,
                        }
                    )
    return pd.DataFrame.from_records(rows)


def evaluate_negative_tail(base: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for direction in DIRECTIONS:
        for landmark in LANDMARKS:
            for universe in UNIVERSES:
                for feature in FEATURES:
                    cell = transport_cell(
                        base,
                        direction=direction,
                        universe=universe,
                        landmark=landmark,
                        feature=feature,
                    )
                    metrics = tail_metrics(cell)

                    lopo_means: list[float] = []
                    lopo_complete = True
                    for pair in lopo_pairs(
                        base,
                        direction=direction,
                        universe=universe,
                        landmark=landmark,
                        feature=feature,
                    ):
                        lopo = transport_cell(
                            base,
                            direction=direction,
                            universe=universe,
                            landmark=landmark,
                            feature=feature,
                            exclude_pair=pair,
                        )
                        lopo_tail = lopo.loc[lopo["negative_utility_tail"].astype(bool)]
                        if lopo_tail.empty:
                            lopo_complete = False
                            break
                        mean = float(lopo_tail["rcv_return"].mean())
                        if not np.isfinite(mean):
                            lopo_complete = False
                            break
                        lopo_means.append(mean)

                    lopo_min = min(lopo_means) if lopo_means else np.nan
                    lopo_max = max(lopo_means) if lopo_means else np.nan
                    support_pass = bool(metrics["tail_support_pass"])
                    finite_required = [
                        float(metrics["tail_mean_rcv"]),
                        float(metrics["tail_median_rcv"]),
                        float(lopo_min),
                        float(lopo_max),
                    ]
                    if not lopo_complete:
                        finite_required.append(np.nan)

                    if not support_pass:
                        outcome = INSUFFICIENT
                    elif not all(np.isfinite(v) for v in finite_required):
                        outcome = UNEVALUABLE
                    elif (
                        float(metrics["tail_mean_rcv"]) < 0.0
                        and float(metrics["tail_median_rcv"]) < 0.0
                        and float(lopo_max) < 0.0
                    ):
                        outcome = QUALIFIED
                    elif (
                        float(metrics["tail_mean_rcv"]) > 0.0
                        and float(metrics["tail_median_rcv"]) > 0.0
                        and float(lopo_min) > 0.0
                    ):
                        outcome = REVERSED
                    else:
                        outcome = NO_EDGE

                    rows.append(
                        {
                            "transport_direction": direction,
                            "evaluation_period": direction_periods(direction)[1],
                            "market_context": PRIMARY_CONTEXT,
                            "landmark_age_hours": landmark,
                            "universe_id": universe,
                            "feature_id": feature,
                            **metrics,
                            "lopo_complete": lopo_complete,
                            "lopo_pair_count": len(lopo_means),
                            "lopo_minimum_tail_mean_rcv": lopo_min,
                            "lopo_maximum_tail_mean_rcv": lopo_max,
                            "cell_outcome": outcome,
                        }
                    )
    return pd.DataFrame.from_records(rows)


def build_score_ledger(base: pd.DataFrame) -> pd.DataFrame:
    rows: list[pd.DataFrame] = []
    for direction in DIRECTIONS:
        for landmark in LANDMARKS:
            for universe in UNIVERSES:
                for feature in FEATURES:
                    cell = transport_cell(
                        base,
                        direction=direction,
                        universe=universe,
                        landmark=landmark,
                        feature=feature,
                    )
                    if cell.empty:
                        continue
                    keep = cell[
                        [
                            "decision_id",
                            "control_position_id",
                            "universe_id",
                            "period_id",
                            "pair",
                            "signal_time",
                            "landmark_age_hours",
                            "market_context",
                            "feature_id",
                            "feature_value",
                            "rcv_return",
                            "rcv_negative",
                            "training_feature_q25",
                            "positive_score",
                            "adverse_score",
                            "negative_utility_tail",
                        ]
                    ].copy()
                    keep.insert(0, "transport_direction", direction)
                    keep.insert(
                        1,
                        "calibration_period",
                        direction_periods(direction)[0],
                    )
                    keep.insert(
                        2,
                        "evaluation_period",
                        direction_periods(direction)[1],
                    )
                    rows.append(keep)
    if not rows:
        raise RD42P4Error("empty score ledger")
    return (
        pd.concat(rows, ignore_index=True)
        .sort_values(
            [
                "transport_direction",
                "landmark_age_hours",
                "universe_id",
                "feature_id",
                "decision_id",
            ],
            kind="stable",
        )
        .reset_index(drop=True)
    )


def _outcome_for(
    frame: pd.DataFrame,
    *,
    direction: str,
    landmark: int,
    feature: str,
    universe: str,
) -> str:
    cell = frame.loc[
        (frame["transport_direction"].astype(str) == direction)
        & (frame["landmark_age_hours"] == landmark)
        & (frame["feature_id"].astype(str) == feature)
        & (frame["universe_id"].astype(str) == universe)
    ]
    if len(cell) != 1:
        raise RD42P4Error(
            f"evaluation cell cardinality !=1: {direction}/{landmark}/{feature}/{universe}"
        )
    return str(cell.iloc[0]["cell_outcome"])


def qualify_feature_landmarks(
    continuous: pd.DataFrame,
    negative: pd.DataFrame,
    tail: pd.DataFrame,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for landmark in LANDMARKS:
        for feature in FEATURES:
            record: dict[str, Any] = {
                "market_context": PRIMARY_CONTEXT,
                "landmark_age_hours": landmark,
                "feature_id": feature,
            }
            both_direction_passes: list[bool] = []
            for direction in DIRECTIONS:
                prefix = "forward" if direction == FORWARD else "reverse"
                continuous_pass_universes = []
                negative_pass_universes = []
                tail_pass_universes = []
                joint_pass_universes = []
                for universe in UNIVERSES:
                    cont_pass = (
                        _outcome_for(
                            continuous,
                            direction=direction,
                            landmark=landmark,
                            feature=feature,
                            universe=universe,
                        )
                        == QUALIFIED
                    )
                    neg_pass = (
                        _outcome_for(
                            negative,
                            direction=direction,
                            landmark=landmark,
                            feature=feature,
                            universe=universe,
                        )
                        == QUALIFIED
                    )
                    tail_pass = (
                        _outcome_for(
                            tail,
                            direction=direction,
                            landmark=landmark,
                            feature=feature,
                            universe=universe,
                        )
                        == QUALIFIED
                    )
                    if cont_pass:
                        continuous_pass_universes.append(universe)
                    if neg_pass:
                        negative_pass_universes.append(universe)
                    if tail_pass:
                        tail_pass_universes.append(universe)
                    if cont_pass and neg_pass and tail_pass:
                        joint_pass_universes.append(universe)

                record[f"{prefix}_continuous_rcv_qualified_universes"] = len(
                    continuous_pass_universes
                )
                record[f"{prefix}_negative_rcv_qualified_universes"] = len(negative_pass_universes)
                record[f"{prefix}_negative_tail_qualified_universes"] = len(tail_pass_universes)
                record[f"{prefix}_joint_qualified_universes"] = len(joint_pass_universes)
                record[f"{prefix}_joint_qualified_universe_ids"] = "|".join(joint_pass_universes)
                direction_pass = len(joint_pass_universes) >= 2
                record[f"{prefix}_all_three_gates_pass"] = direction_pass
                both_direction_passes.append(direction_pass)

            record["both_transport_directions_pass"] = all(both_direction_passes)
            record["advances_to_action_mapping_preregistration"] = all(both_direction_passes)
            rows.append(record)
    return pd.DataFrame.from_records(rows)


def qualified_pairs(qualification: pd.DataFrame) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    selected = qualification.loc[
        qualification["advances_to_action_mapping_preregistration"].astype(bool)
    ]
    for row in selected.to_dict(orient="records"):
        result.append(
            {
                "market_context": PRIMARY_CONTEXT,
                "feature_id": str(row["feature_id"]),
                "landmark_age_hours": int(row["landmark_age_hours"]),
            }
        )
    return result


def decide(
    qualification: pd.DataFrame,
) -> tuple[str, str]:
    if bool(qualification["advances_to_action_mapping_preregistration"].astype(bool).any()):
        return SUCCESS_DECISION, SUCCESS_NEXT
    return FAILURE_DECISION, FAILURE_NEXT
