"""Frozen RD41-P4 continuous RCV and terminal-hazard diagnostic."""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any, Final

import numpy as np
import pandas as pd

DATA_START: Final = pd.Timestamp("2022-01-01T00:00:00Z")
DATA_CUTOFF: Final = pd.Timestamp("2024-01-01T00:00:00Z")

UNIVERSES: Final = ("C2", "D2", "E2")
PERIODS: Final = ("ROBUSTNESS_2022", "ROBUSTNESS_2023")
LANDMARKS_RCV: Final = (24, 48, 72, 96, 120, 144)
LANDMARKS_HAZARD: Final = (24, 48)

ENTRY_MARGIN: Final = "ENTRY_MARGIN"
RECENT_12H_RETURN: Final = "RECENT_12H_RETURN"
PATH_POSITION: Final = "PATH_POSITION"
FEATURES: Final = (ENTRY_MARGIN, RECENT_12H_RETURN, PATH_POSITION)

TIME_FAILURE: Final = "TIME_FAILURE_72H_CLOSE_NOT_ABOVE_ENTRY"
MAX_HOLD: Final = "MAX_HOLD_168H"

CELL_QUALIFIED: Final = "QUALIFIED_EXPECTED_DIRECTION"
CELL_REVERSED: Final = "REVERSED_DIRECTION"
CELL_NO_EDGE: Final = "NO_DIRECTIONAL_EDGE"
CELL_INSUFFICIENT: Final = "INSUFFICIENT_SUPPORT"
CELL_UNEVALUABLE: Final = "UNEVALUABLE_CHANNEL"

MIN_POSITIONS: Final = 20
MIN_PAIRS: Final = 5
MIN_SIGNAL_DAYS: Final = 10
MIN_HAZARD_EVENTS: Final = 10
MIN_HAZARD_NONEVENTS: Final = 10
MIN_UNIVERSES_PER_PERIOD: Final = 2

SUCCESS_DECISION: Final = (
    "RD41_CONTINUOUS_RCV_OR_HAZARD_EVIDENCE_QUALIFIED_PRE_MULTIVARIATE_INTEGRATION"
)
SUCCESS_NEXT: Final = (
    "RD41_P5_PREREGISTER_MULTIVARIATE_CONTINUOUS_EVIDENCE_INTEGRATION_PRE_ACTION_MAPPING"
)
FAILURE_DECISION: Final = (
    "RD41_SIMPLE_CONTINUOUS_TRADE_STATE_CHANNELS_UNQUALIFIED_REASSESS_INFORMATION_ARCHITECTURE"
)
FAILURE_NEXT: Final = "RD41_CLOSE_AND_REASSESS_INFORMATION_ARCHITECTURE_BEFORE_RD42"


class RD41P4Error(RuntimeError):
    """Frozen RD41-P4 contract violation."""


def utc(value: Any) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        return timestamp.tz_localize("UTC")
    return timestamp.tz_convert("UTC")


def validate_constants() -> None:
    if UNIVERSES != ("C2", "D2", "E2"):
        raise RD41P4Error("universe registry drifted")
    if PERIODS != ("ROBUSTNESS_2022", "ROBUSTNESS_2023"):
        raise RD41P4Error("period registry drifted")
    if LANDMARKS_RCV != (24, 48, 72, 96, 120, 144):
        raise RD41P4Error("RCV landmark registry drifted")
    if LANDMARKS_HAZARD != (24, 48):
        raise RD41P4Error("hazard landmark registry drifted")
    if FEATURES != (ENTRY_MARGIN, RECENT_12H_RETURN, PATH_POSITION):
        raise RD41P4Error("feature registry drifted")
    if (
        MIN_POSITIONS != 20
        or MIN_PAIRS != 5
        or MIN_SIGNAL_DAYS != 10
        or MIN_HAZARD_EVENTS != 10
        or MIN_HAZARD_NONEVENTS != 10
        or MIN_UNIVERSES_PER_PERIOD != 2
    ):
        raise RD41P4Error("support gate registry drifted")


def normalize_price_frame(raw: pd.DataFrame, *, pair: str) -> pd.DataFrame:
    required = {"timestamp", "open", "high", "low", "close"}
    missing = sorted(required.difference(raw.columns))
    if missing:
        raise RD41P4Error(f"{pair} price frame missing columns: {missing}")

    frame = raw.loc[:, ["timestamp", "open", "high", "low", "close"]].copy()
    frame["timestamp"] = pd.to_datetime(
        frame["timestamp"],
        utc=True,
        errors="raise",
    ).dt.as_unit("ns")
    for column in ("open", "high", "low", "close"):
        frame[column] = pd.to_numeric(
            frame[column],
            errors="raise",
        ).astype(float)

    frame = frame.sort_values("timestamp", kind="stable").reset_index(drop=True)
    if frame["timestamp"].duplicated().any():
        raise RD41P4Error(f"duplicate timestamp in {pair}")
    if len(frame) and frame["timestamp"].min() < DATA_START:
        raise RD41P4Error(f"pre-2022 bar entered RD41-P4: {pair}")
    if len(frame) and frame["timestamp"].max() >= DATA_CUTOFF:
        raise RD41P4Error(f"2024+ bar entered RD41-P4: {pair}")

    values = frame[["open", "high", "low", "close"]].to_numpy(dtype=float)
    if not np.isfinite(values).all():
        raise RD41P4Error(f"non-finite OHLC in {pair}")
    if bool((values <= 0.0).any()):
        raise RD41P4Error(f"non-positive OHLC in {pair}")
    if bool((frame["high"] < frame["low"]).any()):
        raise RD41P4Error(f"high below low in {pair}")
    if bool((frame["high"] < frame[["open", "close"]].max(axis=1)).any()):
        raise RD41P4Error(f"high below open/close in {pair}")
    if bool((frame["low"] > frame[["open", "close"]].min(axis=1)).any()):
        raise RD41P4Error(f"low above open/close in {pair}")
    return frame


def price_lookup(
    frame: pd.DataFrame,
) -> dict[int, tuple[float, float, float, float]]:
    return {
        int(timestamp): (
            float(open_price),
            float(high_price),
            float(low_price),
            float(close_price),
        )
        for timestamp, open_price, high_price, low_price, close_price in zip(
            frame["timestamp"].astype("int64").tolist(),
            frame["open"].tolist(),
            frame["high"].tolist(),
            frame["low"].tolist(),
            frame["close"].tolist(),
            strict=True,
        )
    }


def feature_snapshot(
    lookup: Mapping[int, tuple[float, float, float, float]],
    *,
    entry_time: Any,
    entry_price: float,
    decision_time: Any,
) -> dict[str, Any]:
    entry = utc(entry_time)
    decision = utc(decision_time)
    entry_price = float(entry_price)

    if entry != entry.floor("h") or decision != decision.floor("h"):
        raise RD41P4Error("entry/decision time is not hourly")
    if decision <= entry:
        raise RD41P4Error("decision must occur after entry")
    if not math.isfinite(entry_price) or entry_price <= 0.0:
        raise RD41P4Error("invalid frozen entry price")

    decision_row = lookup.get(int(decision.as_unit("ns").value))
    if decision_row is None:
        return {
            "target_open_available": False,
            "path_contiguous": False,
            "decision_open": np.nan,
            ENTRY_MARGIN: np.nan,
            RECENT_12H_RETURN: np.nan,
            PATH_POSITION: np.nan,
            "path_position_evaluable": False,
            "unevaluable_reason": "MISSING_DECISION_OPEN",
        }

    expected = list(
        pd.date_range(
            entry,
            decision - pd.Timedelta(hours=1),
            freq="h",
            tz="UTC",
        )
    )
    rows: list[tuple[pd.Timestamp, tuple[float, float, float, float]]] = []
    for timestamp in expected:
        row = lookup.get(int(timestamp.as_unit("ns").value))
        if row is None:
            return {
                "target_open_available": True,
                "path_contiguous": False,
                "decision_open": float(decision_row[0]),
                ENTRY_MARGIN: np.nan,
                RECENT_12H_RETURN: np.nan,
                PATH_POSITION: np.nan,
                "path_position_evaluable": False,
                "unevaluable_reason": "MISSING_REQUIRED_PATH_HOUR",
            }
        rows.append((timestamp, row))

    if len(rows) < 13:
        raise RD41P4Error("frozen landmarks require at least 13 path bars")

    close_t_minus_1 = float(rows[-1][1][3])
    close_t_minus_13 = float(rows[-13][1][3])
    path_high = max(float(item[1][1]) for item in rows)
    path_low = min(float(item[1][2]) for item in rows)

    entry_margin = close_t_minus_1 / entry_price - 1.0
    recent_return = close_t_minus_1 / close_t_minus_13 - 1.0

    path_position = np.nan
    path_position_evaluable = path_high > path_low
    if path_position_evaluable:
        path_position = (close_t_minus_1 - path_low) / (path_high - path_low)

    return {
        "target_open_available": True,
        "path_contiguous": True,
        "decision_open": float(decision_row[0]),
        ENTRY_MARGIN: float(entry_margin),
        RECENT_12H_RETURN: float(recent_return),
        PATH_POSITION: (float(path_position) if np.isfinite(path_position) else np.nan),
        "path_position_evaluable": bool(path_position_evaluable),
        "unevaluable_reason": ("" if path_position_evaluable else "ZERO_PATH_RANGE"),
    }


def build_ledgers(
    *,
    risk_set: pd.DataFrame,
    lookups: Mapping[
        str,
        Mapping[int, tuple[float, float, float, float]],
    ],
    governor_state_getter: Any,
    exit_side_cost: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    targets: list[dict[str, Any]] = []
    features: list[dict[str, Any]] = []

    for row in risk_set.to_dict(orient="records"):
        if str(row["risk_set_class"]) != "RESOLVED_CONTROL_OUTCOME":
            continue

        universe = str(row["universe_id"])
        pair = str(row["pair"])
        period = str(row["period_id"])
        position_id = str(row["control_position_id"])
        entry_time = utc(row["entry_time"])
        exit_time = utc(row["exit_time"])
        signal_time = utc(row["signal_time"])
        entry_price = float(row["entry_price"])
        exit_price = float(row["exit_price"])
        quantity = float(row["quantity"])
        exit_reason = str(row["exit_reason"])

        if pair not in lookups:
            raise RD41P4Error(f"missing price lookup: {pair}")
        if exit_reason not in {TIME_FAILURE, MAX_HOLD}:
            raise RD41P4Error(f"unexpected terminal reason: {exit_reason}")

        for age in LANDMARKS_RCV:
            decision_time = entry_time + pd.Timedelta(hours=age)
            if not decision_time < exit_time:
                continue

            snapshot = feature_snapshot(
                lookups[pair],
                entry_time=entry_time,
                entry_price=entry_price,
                decision_time=decision_time,
            )
            target_available = bool(snapshot["target_open_available"])
            decision_open = float(snapshot["decision_open"])

            rcv_return = np.nan
            rcv_dollars = np.nan
            immediate_value = np.nan
            control_value = np.nan
            if target_available:
                immediate_value = quantity * decision_open * (1.0 - exit_side_cost)
                control_value = quantity * exit_price * (1.0 - exit_side_cost)
                if immediate_value <= 0.0:
                    raise RD41P4Error("non-positive immediate liquidation value")
                rcv_return = control_value / immediate_value - 1.0
                rcv_dollars = control_value - immediate_value

            governor_state = governor_state_getter(
                universe=universe,
                decision_time=decision_time,
            )
            decision_id = f"{position_id}|{age:03d}h"

            hazard_eligible = age in LANDMARKS_HAZARD
            hazard_label = int(exit_reason == TIME_FAILURE) if hazard_eligible else np.nan

            targets.append(
                {
                    "decision_id": decision_id,
                    "control_position_id": position_id,
                    "universe_id": universe,
                    "period_id": period,
                    "pair": pair,
                    "signal_time": signal_time,
                    "entry_time": entry_time,
                    "decision_time": decision_time,
                    "landmark_age_hours": age,
                    "governor_state": governor_state,
                    "control_exit_time": exit_time,
                    "control_exit_reason": exit_reason,
                    "decision_open": decision_open,
                    "control_exit_price": exit_price,
                    "quantity": quantity,
                    "exit_side_cost": exit_side_cost,
                    "immediate_net_liquidation_value": immediate_value,
                    "control_exit_net_liquidation_value": control_value,
                    "target_evaluable": target_available,
                    "rcv_return": rcv_return,
                    "rcv_dollars": rcv_dollars,
                    "hazard_eligible": hazard_eligible,
                    "time_failure_event": hazard_label,
                    "right_censored": False,
                }
            )

            for feature_id in FEATURES:
                value = float(snapshot[feature_id])
                feature_evaluable = bool(snapshot["path_contiguous"] and np.isfinite(value))
                reason = ""
                if not snapshot["path_contiguous"]:
                    reason = str(snapshot["unevaluable_reason"])
                elif feature_id == PATH_POSITION and not snapshot["path_position_evaluable"]:
                    feature_evaluable = False
                    reason = "ZERO_PATH_RANGE"

                features.append(
                    {
                        "decision_id": decision_id,
                        "control_position_id": position_id,
                        "universe_id": universe,
                        "period_id": period,
                        "pair": pair,
                        "signal_time": signal_time,
                        "decision_time": decision_time,
                        "landmark_age_hours": age,
                        "governor_state": governor_state,
                        "feature_id": feature_id,
                        "feature_value": (value if feature_evaluable else np.nan),
                        "feature_evaluable": feature_evaluable,
                        "feature_unevaluable_reason": reason,
                        "feature_clock": "COMPLETED_BAR_t_minus_1",
                    }
                )

    target_frame = pd.DataFrame.from_records(targets)
    feature_frame = pd.DataFrame.from_records(features)

    if target_frame.empty or feature_frame.empty:
        raise RD41P4Error("RD41-P4 ledgers are empty")
    if target_frame["decision_id"].duplicated().any():
        raise RD41P4Error("duplicate target decision_id")
    if feature_frame.duplicated(["decision_id", "feature_id"]).any():
        raise RD41P4Error("duplicate feature decision/channel")

    target_frame = target_frame.sort_values(
        [
            "decision_time",
            "universe_id",
            "control_position_id",
            "landmark_age_hours",
        ],
        kind="stable",
    ).reset_index(drop=True)
    feature_frame = feature_frame.sort_values(
        [
            "decision_time",
            "universe_id",
            "control_position_id",
            "landmark_age_hours",
            "feature_id",
        ],
        kind="stable",
    ).reset_index(drop=True)
    return target_frame, feature_frame


def support_counts(frame: pd.DataFrame) -> dict[str, int]:
    return {
        "unique_control_position_count": int(frame["control_position_id"].astype(str).nunique()),
        "unique_pair_count": int(frame["pair"].astype(str).nunique()),
        "unique_signal_day_count": int(
            pd.to_datetime(
                frame["signal_time"],
                utc=True,
                errors="raise",
            )
            .dt.floor("D")
            .nunique()
        ),
    }


def base_support_pass(frame: pd.DataFrame) -> bool:
    counts = support_counts(frame)
    return bool(
        counts["unique_control_position_count"] >= MIN_POSITIONS
        and counts["unique_pair_count"] >= MIN_PAIRS
        and counts["unique_signal_day_count"] >= MIN_SIGNAL_DAYS
    )


def average_rank(values: pd.Series) -> np.ndarray:
    return pd.Series(values, dtype=float).rank(method="average").to_numpy(dtype=float)


def spearman_rho(x: pd.Series, y: pd.Series) -> float:
    if len(x) != len(y) or len(x) < 2:
        return float("nan")
    xr = average_rank(x)
    yr = average_rank(y)
    if np.isclose(np.std(xr), 0.0) or np.isclose(np.std(yr), 0.0):
        return float("nan")
    return float(np.corrcoef(xr, yr)[0, 1])


def median_split_rcv(frame: pd.DataFrame) -> dict[str, float | int | bool]:
    if frame.empty:
        return {
            "evaluable": False,
            "feature_median": np.nan,
            "lower_count": 0,
            "upper_count": 0,
            "lower_mean_rcv": np.nan,
            "upper_mean_rcv": np.nan,
            "spread": np.nan,
        }

    median = float(frame["feature_value"].median())
    lower = frame.loc[frame["feature_value"] <= median]
    upper = frame.loc[frame["feature_value"] > median]
    if lower.empty or upper.empty:
        return {
            "evaluable": False,
            "feature_median": median,
            "lower_count": int(len(lower)),
            "upper_count": int(len(upper)),
            "lower_mean_rcv": np.nan,
            "upper_mean_rcv": np.nan,
            "spread": np.nan,
        }

    lower_mean = float(lower["rcv_return"].mean())
    upper_mean = float(upper["rcv_return"].mean())
    return {
        "evaluable": True,
        "feature_median": median,
        "lower_count": int(len(lower)),
        "upper_count": int(len(upper)),
        "lower_mean_rcv": lower_mean,
        "upper_mean_rcv": upper_mean,
        "spread": float(upper_mean - lower_mean),
    }


def lopo_rcv(frame: pd.DataFrame) -> dict[str, Any]:
    pairs = sorted(frame["pair"].astype(str).unique())
    spreads: list[float] = []
    for pair in pairs:
        remaining = frame.loc[frame["pair"].astype(str) != pair]
        split = median_split_rcv(remaining)
        if not bool(split["evaluable"]):
            return {
                "complete": False,
                "pair_count": len(pairs),
                "evaluated_count": len(spreads),
                "minimum_spread": np.nan,
                "maximum_spread": np.nan,
            }
        spreads.append(float(split["spread"]))
    if not spreads:
        return {
            "complete": False,
            "pair_count": len(pairs),
            "evaluated_count": 0,
            "minimum_spread": np.nan,
            "maximum_spread": np.nan,
        }
    return {
        "complete": True,
        "pair_count": len(pairs),
        "evaluated_count": len(spreads),
        "minimum_spread": float(min(spreads)),
        "maximum_spread": float(max(spreads)),
    }


def auc_binary(labels: pd.Series, scores: pd.Series) -> float:
    y = pd.to_numeric(labels, errors="raise").astype(int).to_numpy()
    s = pd.to_numeric(scores, errors="raise").astype(float)
    if len(y) != len(s) or len(y) == 0:
        return float("nan")
    positives = y == 1
    negatives = y == 0
    n_pos = int(positives.sum())
    n_neg = int(negatives.sum())
    if n_pos == 0 or n_neg == 0:
        return float("nan")
    ranks = average_rank(pd.Series(s))
    rank_sum_pos = float(ranks[positives].sum())
    return float((rank_sum_pos - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg))


def lopo_auc(frame: pd.DataFrame) -> dict[str, Any]:
    pairs = sorted(frame["pair"].astype(str).unique())
    values: list[float] = []
    for pair in pairs:
        remaining = frame.loc[frame["pair"].astype(str) != pair]
        auc = auc_binary(
            remaining["time_failure_event"],
            -remaining["feature_value"],
        )
        if not np.isfinite(auc):
            return {
                "complete": False,
                "pair_count": len(pairs),
                "evaluated_count": len(values),
                "minimum_auc": np.nan,
                "maximum_auc": np.nan,
            }
        values.append(float(auc))
    if not values:
        return {
            "complete": False,
            "pair_count": len(pairs),
            "evaluated_count": 0,
            "minimum_auc": np.nan,
            "maximum_auc": np.nan,
        }
    return {
        "complete": True,
        "pair_count": len(pairs),
        "evaluated_count": len(values),
        "minimum_auc": float(min(values)),
        "maximum_auc": float(max(values)),
    }


def merged_evaluable(
    targets: pd.DataFrame,
    features: pd.DataFrame,
    *,
    feature_id: str,
    landmark: int,
    universe: str,
    period: str,
) -> pd.DataFrame:
    left = targets.loc[
        (targets["landmark_age_hours"] == landmark)
        & (targets["universe_id"].astype(str) == universe)
        & (targets["period_id"].astype(str) == period)
        & targets["target_evaluable"].astype(bool)
    ].copy()
    right = features.loc[
        (features["feature_id"].astype(str) == feature_id)
        & (features["landmark_age_hours"] == landmark)
        & (features["universe_id"].astype(str) == universe)
        & (features["period_id"].astype(str) == period)
        & features["feature_evaluable"].astype(bool)
    ].copy()

    merged = left.merge(
        right[["decision_id", "feature_value"]],
        on="decision_id",
        how="inner",
        validate="one_to_one",
    )
    return merged


def rcv_cell_evaluation(
    targets: pd.DataFrame,
    features: pd.DataFrame,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []

    for feature_id in FEATURES:
        for landmark in LANDMARKS_RCV:
            for period in PERIODS:
                for universe in UNIVERSES:
                    frame = merged_evaluable(
                        targets,
                        features,
                        feature_id=feature_id,
                        landmark=landmark,
                        universe=universe,
                        period=period,
                    )
                    counts = support_counts(frame)
                    support_pass = base_support_pass(frame)

                    rho = spearman_rho(
                        frame["feature_value"],
                        frame["rcv_return"],
                    )
                    split = median_split_rcv(frame)
                    lopo = lopo_rcv(frame)

                    metrics_evaluable = bool(
                        np.isfinite(rho) and bool(split["evaluable"]) and bool(lopo["complete"])
                    )

                    if not support_pass:
                        outcome = CELL_INSUFFICIENT
                    elif not metrics_evaluable:
                        outcome = CELL_UNEVALUABLE
                    elif (
                        rho > 0.0
                        and float(split["spread"]) > 0.0
                        and float(lopo["minimum_spread"]) > 0.0
                    ):
                        outcome = CELL_QUALIFIED
                    elif (
                        rho < 0.0
                        and float(split["spread"]) < 0.0
                        and float(lopo["maximum_spread"]) < 0.0
                    ):
                        outcome = CELL_REVERSED
                    else:
                        outcome = CELL_NO_EDGE

                    rows.append(
                        {
                            "feature_id": feature_id,
                            "landmark_age_hours": landmark,
                            "period_id": period,
                            "universe_id": universe,
                            "decision_row_count": int(len(frame)),
                            **counts,
                            "support_pass": support_pass,
                            "mean_rcv_return": (
                                float(frame["rcv_return"].mean()) if len(frame) else np.nan
                            ),
                            "median_rcv_return": (
                                float(frame["rcv_return"].median()) if len(frame) else np.nan
                            ),
                            "spearman_rho": rho,
                            "feature_median": split["feature_median"],
                            "lower_feature_half_count": split["lower_count"],
                            "upper_feature_half_count": split["upper_count"],
                            "lower_feature_half_mean_rcv": split["lower_mean_rcv"],
                            "upper_feature_half_mean_rcv": split["upper_mean_rcv"],
                            "feature_median_split_mean_rcv_spread": split["spread"],
                            "lopo_complete": bool(lopo["complete"]),
                            "lopo_evaluated_pair_count": int(lopo["evaluated_count"]),
                            "lopo_minimum_mean_rcv_spread": lopo["minimum_spread"],
                            "lopo_maximum_mean_rcv_spread": lopo["maximum_spread"],
                            "cell_outcome": outcome,
                        }
                    )
    return pd.DataFrame.from_records(rows)


def hazard_cell_evaluation(
    targets: pd.DataFrame,
    features: pd.DataFrame,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []

    for feature_id in FEATURES:
        for landmark in LANDMARKS_HAZARD:
            for period in PERIODS:
                for universe in UNIVERSES:
                    frame = merged_evaluable(
                        targets,
                        features,
                        feature_id=feature_id,
                        landmark=landmark,
                        universe=universe,
                        period=period,
                    )
                    frame = frame.loc[frame["hazard_eligible"].astype(bool)].copy()
                    counts = support_counts(frame)
                    event_count = int(
                        (
                            pd.to_numeric(
                                frame["time_failure_event"],
                                errors="raise",
                            )
                            == 1
                        ).sum()
                    )
                    nonevent_count = int(
                        (
                            pd.to_numeric(
                                frame["time_failure_event"],
                                errors="raise",
                            )
                            == 0
                        ).sum()
                    )
                    support_pass = bool(
                        base_support_pass(frame)
                        and event_count >= MIN_HAZARD_EVENTS
                        and nonevent_count >= MIN_HAZARD_NONEVENTS
                    )

                    auc = auc_binary(
                        frame["time_failure_event"],
                        -frame["feature_value"],
                    )
                    event_values = frame.loc[
                        frame["time_failure_event"] == 1,
                        "feature_value",
                    ]
                    nonevent_values = frame.loc[
                        frame["time_failure_event"] == 0,
                        "feature_value",
                    ]
                    median_spread = (
                        float(nonevent_values.median()) - float(event_values.median())
                        if len(event_values) and len(nonevent_values)
                        else np.nan
                    )
                    lopo = lopo_auc(frame)
                    metrics_evaluable = bool(
                        np.isfinite(auc) and np.isfinite(median_spread) and bool(lopo["complete"])
                    )

                    if not support_pass:
                        outcome = CELL_INSUFFICIENT
                    elif not metrics_evaluable:
                        outcome = CELL_UNEVALUABLE
                    elif auc > 0.5 and median_spread > 0.0 and float(lopo["minimum_auc"]) > 0.5:
                        outcome = CELL_QUALIFIED
                    elif auc < 0.5 and median_spread < 0.0 and float(lopo["maximum_auc"]) < 0.5:
                        outcome = CELL_REVERSED
                    else:
                        outcome = CELL_NO_EDGE

                    rows.append(
                        {
                            "feature_id": feature_id,
                            "landmark_age_hours": landmark,
                            "period_id": period,
                            "universe_id": universe,
                            "decision_row_count": int(len(frame)),
                            **counts,
                            "time_failure_event_count": event_count,
                            "max_hold_non_event_count": nonevent_count,
                            "support_pass": support_pass,
                            "auc_of_negative_channel": auc,
                            "time_failure_median_channel": (
                                float(event_values.median()) if len(event_values) else np.nan
                            ),
                            "max_hold_median_channel": (
                                float(nonevent_values.median()) if len(nonevent_values) else np.nan
                            ),
                            "non_event_minus_event_median_channel_spread": (median_spread),
                            "lopo_complete": bool(lopo["complete"]),
                            "lopo_evaluated_pair_count": int(lopo["evaluated_count"]),
                            "lopo_minimum_auc": lopo["minimum_auc"],
                            "lopo_maximum_auc": lopo["maximum_auc"],
                            "cell_outcome": outcome,
                        }
                    )
    return pd.DataFrame.from_records(rows)


def qualify_feature_landmarks(
    cells: pd.DataFrame,
    *,
    landmarks: tuple[int, ...],
    target_id: str,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for feature_id in FEATURES:
        for landmark in landmarks:
            subset = cells.loc[
                (cells["feature_id"].astype(str) == feature_id)
                & (cells["landmark_age_hours"] == landmark)
            ]
            qualified_counts = {}
            reversed_counts = {}
            insufficient_counts = {}
            for period in PERIODS:
                period_rows = subset.loc[subset["period_id"].astype(str) == period]
                qualified_counts[period] = int(
                    (period_rows["cell_outcome"] == CELL_QUALIFIED).sum()
                )
                reversed_counts[period] = int((period_rows["cell_outcome"] == CELL_REVERSED).sum())
                insufficient_counts[period] = int(
                    (period_rows["cell_outcome"] == CELL_INSUFFICIENT).sum()
                )

            qualified = bool(
                qualified_counts["ROBUSTNESS_2022"] >= MIN_UNIVERSES_PER_PERIOD
                and qualified_counts["ROBUSTNESS_2023"] >= MIN_UNIVERSES_PER_PERIOD
            )
            reversed_across_both = bool(
                reversed_counts["ROBUSTNESS_2022"] >= MIN_UNIVERSES_PER_PERIOD
                and reversed_counts["ROBUSTNESS_2023"] >= MIN_UNIVERSES_PER_PERIOD
            )
            regime_direction_reversal = bool(
                (
                    qualified_counts["ROBUSTNESS_2022"] >= MIN_UNIVERSES_PER_PERIOD
                    and reversed_counts["ROBUSTNESS_2023"] >= MIN_UNIVERSES_PER_PERIOD
                )
                or (
                    reversed_counts["ROBUSTNESS_2022"] >= MIN_UNIVERSES_PER_PERIOD
                    and qualified_counts["ROBUSTNESS_2023"] >= MIN_UNIVERSES_PER_PERIOD
                )
            )

            rows.append(
                {
                    "target_id": target_id,
                    "feature_id": feature_id,
                    "landmark_age_hours": landmark,
                    "qualified_universes_2022": qualified_counts["ROBUSTNESS_2022"],
                    "qualified_universes_2023": qualified_counts["ROBUSTNESS_2023"],
                    "reversed_universes_2022": reversed_counts["ROBUSTNESS_2022"],
                    "reversed_universes_2023": reversed_counts["ROBUSTNESS_2023"],
                    "insufficient_support_universes_2022": insufficient_counts["ROBUSTNESS_2022"],
                    "insufficient_support_universes_2023": insufficient_counts["ROBUSTNESS_2023"],
                    "qualified": qualified,
                    "reversed_across_both_periods": reversed_across_both,
                    "regime_direction_reversal": regime_direction_reversal,
                    "advances": qualified,
                    "best_feature_selection_used": False,
                    "best_landmark_selection_used": False,
                    "failed_channel_rescue_used": False,
                }
            )
    return pd.DataFrame.from_records(rows)


def governor_descriptive_attribution(
    targets: pd.DataFrame,
    features: pd.DataFrame,
) -> pd.DataFrame:
    merged = features.merge(
        targets[
            [
                "decision_id",
                "rcv_return",
                "hazard_eligible",
                "time_failure_event",
                "target_evaluable",
            ]
        ],
        on="decision_id",
        how="left",
        validate="many_to_one",
    )
    rows: list[dict[str, Any]] = []
    for feature_id in FEATURES:
        for landmark in LANDMARKS_RCV:
            for period in PERIODS:
                for universe in UNIVERSES:
                    for state in ("OPEN", "CAUTION", "LOCKED"):
                        cell = merged.loc[
                            (merged["feature_id"] == feature_id)
                            & (merged["landmark_age_hours"] == landmark)
                            & (merged["period_id"] == period)
                            & (merged["universe_id"] == universe)
                            & (merged["governor_state"] == state)
                            & merged["feature_evaluable"].astype(bool)
                            & merged["target_evaluable"].astype(bool)
                        ].copy()
                        hazard = cell.loc[cell["hazard_eligible"].astype(bool)]
                        rows.append(
                            {
                                "feature_id": feature_id,
                                "landmark_age_hours": landmark,
                                "period_id": period,
                                "universe_id": universe,
                                "governor_state": state,
                                "evaluable_position_count": int(len(cell)),
                                "mean_feature_value": (
                                    float(cell["feature_value"].mean()) if len(cell) else np.nan
                                ),
                                "median_feature_value": (
                                    float(cell["feature_value"].median()) if len(cell) else np.nan
                                ),
                                "mean_rcv_return": (
                                    float(cell["rcv_return"].mean()) if len(cell) else np.nan
                                ),
                                "median_rcv_return": (
                                    float(cell["rcv_return"].median()) if len(cell) else np.nan
                                ),
                                "hazard_evaluable_position_count": int(len(hazard)),
                                "time_failure_rate": (
                                    float(hazard["time_failure_event"].mean())
                                    if len(hazard)
                                    else np.nan
                                ),
                                "selection_eligible": False,
                                "causal_effect_claim": False,
                            }
                        )
    return pd.DataFrame.from_records(rows)
