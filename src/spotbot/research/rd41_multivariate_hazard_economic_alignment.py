from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

PERIODS = ("ROBUSTNESS_2022", "ROBUSTNESS_2023")
UNIVERSES = ("C2", "D2", "E2")
LANDMARKS = (24, 48)
FEATURES = ("ENTRY_MARGIN", "RECENT_12H_RETURN", "PATH_POSITION")
FORWARD = "CALIBRATE_2022_EVALUATE_2023"
REVERSE = "CALIBRATE_2023_EVALUATE_2022"
DIRECTIONS = (FORWARD, REVERSE)
TAIL_THRESHOLD = 0.75
QUALIFIED = "QUALIFIED_EXPECTED_DIRECTION"
REVERSED = "REVERSED_DIRECTION"
NO_EDGE = "NO_DIRECTIONAL_EDGE"
INSUFFICIENT = "INSUFFICIENT_SUPPORT"
UNEVALUABLE = "UNEVALUABLE_CHANNEL"
TAIL_QUALIFIED = "QUALIFIED_NEGATIVE_RCV_TAIL"
TAIL_NOT_NEGATIVE = "TAIL_NOT_ROBUSTLY_NEGATIVE"
SUCCESS_DECISION = "RD41_MULTIVARIATE_HAZARD_SCORE_ECONOMICALLY_ALIGNED_PRE_ACTION_MAPPING"
HAZARD_ONLY_DECISION = (
    "RD41_MULTIVARIATE_HAZARD_TRANSPORTS_BUT_ECONOMIC_ALIGNMENT_FAILS_NO_ACTION_MAPPING"
)
FAILURE_DECISION = "RD41_MULTIVARIATE_HAZARD_INTEGRATION_UNQUALIFIED_NO_ACTION_MAPPING"
SUCCESS_NEXT = "RD41_P7_PREREGISTER_ACTION_MAPPING_WITH_SLOT_ESCROW_AND_NO_CAPITAL_REUSE"
HAZARD_ONLY_NEXT = (
    "RD41_CLOSE_HAZARD_AS_CONTROL_OUTCOME_PREDICTOR_ONLY_REASSESS_EXIT_UTILITY_ARCHITECTURE"
)
FAILURE_NEXT = "RD41_CLOSE_AND_REASSESS_INFORMATION_ARCHITECTURE_BEFORE_RD42"


class RD41P6Error(RuntimeError):
    pass


def validate_constants() -> None:
    if (
        PERIODS != ("ROBUSTNESS_2022", "ROBUSTNESS_2023")
        or UNIVERSES != ("C2", "D2", "E2")
        or LANDMARKS != (24, 48)
        or FEATURES != ("ENTRY_MARGIN", "RECENT_12H_RETURN", "PATH_POSITION")
        or not math.isclose(TAIL_THRESHOLD, 0.75)
    ):
        raise RD41P6Error("frozen registry drifted")


def direction_periods(direction: str) -> tuple[str, str]:
    if direction == FORWARD:
        return "ROBUSTNESS_2022", "ROBUSTNESS_2023"
    if direction == REVERSE:
        return "ROBUSTNESS_2023", "ROBUSTNESS_2022"
    raise RD41P6Error(f"unknown direction {direction}")


def average_rank(values: pd.Series) -> np.ndarray:
    return pd.Series(values, dtype=float).rank(method="average").to_numpy(float)


def auc_binary(labels: pd.Series, scores: pd.Series) -> float:
    y = pd.to_numeric(labels, errors="raise").astype(int).to_numpy()
    s = pd.to_numeric(scores, errors="raise").astype(float).to_numpy()
    if len(y) == 0 or len(y) != len(s):
        return float("nan")
    pos = y == 1
    neg = y == 0
    np_ = int(pos.sum())
    nn = int(neg.sum())
    if np_ == 0 or nn == 0:
        return float("nan")
    ranks = average_rank(pd.Series(s))
    rs = float(ranks[pos].sum())
    return float((rs - np_ * (np_ + 1) / 2) / (np_ * nn))


def spearman(x: pd.Series, y: pd.Series) -> float:
    if len(x) < 2 or len(x) != len(y):
        return float("nan")
    xr = average_rank(x)
    yr = average_rank(y)
    if np.isclose(np.std(xr), 0.0) or np.isclose(np.std(yr), 0.0):
        return float("nan")
    return float(np.corrcoef(xr, yr)[0, 1])


def sig_days(frame: pd.DataFrame) -> int:
    return (
        int(pd.to_datetime(frame["signal_time"], utc=True, errors="raise").dt.floor("D").nunique())
        if len(frame)
        else 0
    )


def support(frame: pd.DataFrame) -> dict[str, Any]:
    p = int(frame["control_position_id"].astype(str).nunique())
    q = int(frame["pair"].astype(str).nunique())
    d = sig_days(frame)
    return {
        "unique_control_position_count": p,
        "unique_pair_count": q,
        "unique_signal_day_count": d,
        "support_pass": bool(p >= 20 and q >= 5 and d >= 10),
    }


def tail_support(frame: pd.DataFrame) -> dict[str, Any]:
    p = int(frame["control_position_id"].astype(str).nunique())
    q = int(frame["pair"].astype(str).nunique())
    d = sig_days(frame)
    return {
        "tail_unique_control_position_count": p,
        "tail_unique_pair_count": q,
        "tail_unique_signal_day_count": d,
        "tail_support_pass": bool(p >= 10 and q >= 3 and d >= 5),
    }


def pivot_features(features: pd.DataFrame) -> pd.DataFrame:
    selected = features.loc[
        features["landmark_age_hours"].isin(LANDMARKS)
        & features["feature_id"].astype(str).isin(FEATURES)
        & features["feature_evaluable"].astype(bool)
    ].copy()
    meta = [
        "decision_id",
        "control_position_id",
        "universe_id",
        "period_id",
        "pair",
        "signal_time",
        "landmark_age_hours",
    ]
    wide = selected.pivot(index=meta, columns="feature_id", values="feature_value").reset_index()
    wide.columns.name = None
    for f in FEATURES:
        if f not in wide.columns:
            raise RD41P6Error(f"missing feature {f}")
        wide[f] = pd.to_numeric(wide[f], errors="raise").astype(float)
    if wide[list(FEATURES)].isna().any(axis=None):
        raise RD41P6Error("missing composite feature")
    return wide


def build_base_rows(targets: pd.DataFrame, features: pd.DataFrame) -> pd.DataFrame:
    target = targets.loc[
        targets["landmark_age_hours"].isin(LANDMARKS)
        & targets["target_evaluable"].astype(bool)
        & targets["hazard_eligible"].astype(bool)
    ].copy()
    if target["right_censored"].astype(bool).any():
        raise RD41P6Error("censored target entered P6")
    wide = pivot_features(features)
    merged = target.merge(
        wide[["decision_id", *FEATURES]], on="decision_id", how="inner", validate="one_to_one"
    )
    if len(merged) != len(target):
        raise RD41P6Error("feature complete rows mismatch")
    merged["rcv_return"] = pd.to_numeric(merged["rcv_return"], errors="raise").astype(float)
    merged["time_failure_event"] = pd.to_numeric(
        merged["time_failure_event"], errors="raise"
    ).astype(int)
    return merged


def adverse_percentile(train: np.ndarray, test: np.ndarray) -> np.ndarray:
    a = np.asarray(train, float)
    b = np.asarray(test, float)
    if len(a) == 0 or not np.isfinite(a).all() or not np.isfinite(b).all():
        raise RD41P6Error("invalid score inputs")
    return np.asarray([(a >= x).mean() for x in b], float)


def score_rows(cal: pd.DataFrame, ev: pd.DataFrame) -> pd.DataFrame:
    if cal.empty or ev.empty:
        return pd.DataFrame()
    out = ev.copy()
    comps = []
    for f in FEATURES:
        v = adverse_percentile(cal[f].to_numpy(float), ev[f].to_numpy(float))
        out[f"{f}_adverse_percentile"] = v
        comps.append(v)
    out["adverse_score"] = np.mean(np.column_stack(comps), axis=1)
    return out


def transport_cell(
    base: pd.DataFrame,
    direction: str,
    universe: str,
    landmark: int,
    exclude_pair: str | None = None,
) -> pd.DataFrame:
    cp, ep = direction_periods(direction)
    cal = base.loc[
        (base["period_id"].astype(str) == cp)
        & (base["universe_id"].astype(str) == universe)
        & (base["landmark_age_hours"] == landmark)
    ].copy()
    ev = base.loc[
        (base["period_id"].astype(str) == ep)
        & (base["universe_id"].astype(str) == universe)
        & (base["landmark_age_hours"] == landmark)
    ].copy()
    if exclude_pair is not None:
        cal = cal.loc[cal["pair"].astype(str) != exclude_pair].copy()
        ev = ev.loc[ev["pair"].astype(str) != exclude_pair].copy()
    return score_rows(cal, ev)


def lopo_pairs(base: pd.DataFrame, direction: str, universe: str, landmark: int) -> list[str]:
    ep = direction_periods(direction)[1]
    ev = base.loc[
        (base["period_id"].astype(str) == ep)
        & (base["universe_id"].astype(str) == universe)
        & (base["landmark_age_hours"] == landmark)
    ]
    return sorted(ev["pair"].astype(str).unique())


def hazard_eval(base: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for direction in DIRECTIONS:
        for landmark in LANDMARKS:
            for universe in UNIVERSES:
                cell = transport_cell(base, direction, universe, landmark)
                sup = support(cell)
                events = cell.loc[cell["time_failure_event"] == 1]
                none = cell.loc[cell["time_failure_event"] == 0]
                event_support = len(events) >= 10 and len(none) >= 10
                auc = auc_binary(cell["time_failure_event"], cell["adverse_score"])
                em = float(events["adverse_score"].median()) if len(events) else np.nan
                nm = float(none["adverse_score"].median()) if len(none) else np.nan
                spread = em - nm if np.isfinite(em) and np.isfinite(nm) else np.nan
                lopo_auc_values = []
                complete = True
                for pair in lopo_pairs(base, direction, universe, landmark):
                    x = transport_cell(base, direction, universe, landmark, pair)
                    a = auc_binary(x["time_failure_event"], x["adverse_score"])
                    if not np.isfinite(a):
                        complete = False
                        break
                    lopo_auc_values.append(float(a))
                lmin = min(lopo_auc_values) if lopo_auc_values else np.nan
                lmax = max(lopo_auc_values) if lopo_auc_values else np.nan
                sp = bool(sup["support_pass"] and event_support)
                if not sp:
                    outcome = INSUFFICIENT
                elif not np.isfinite(auc) or not np.isfinite(spread) or not complete:
                    outcome = UNEVALUABLE
                elif auc > 0.5 and spread > 0 and lmin > 0.5:
                    outcome = QUALIFIED
                elif auc < 0.5 and spread < 0 and lmax < 0.5:
                    outcome = REVERSED
                else:
                    outcome = NO_EDGE
                rows.append(
                    {
                        "transport_direction": direction,
                        "landmark_age_hours": landmark,
                        "universe_id": universe,
                        "evaluation_period": direction_periods(direction)[1],
                        "decision_row_count": len(cell),
                        **sup,
                        "time_failure_event_count": len(events),
                        "max_hold_non_event_count": len(none),
                        "hazard_support_pass": sp,
                        "auc": auc,
                        "event_median_adverse_score": em,
                        "nonevent_median_adverse_score": nm,
                        "event_minus_nonevent_median_adverse_score_spread": spread,
                        "lopo_complete": complete,
                        "lopo_pair_count": len(lopo_auc_values),
                        "lopo_minimum_auc": lmin,
                        "lopo_maximum_auc": lmax,
                        "cell_outcome": outcome,
                    }
                )
    return pd.DataFrame(rows)


def rcv_eval(base: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for direction in DIRECTIONS:
        for landmark in LANDMARKS:
            for universe in UNIVERSES:
                cell = transport_cell(base, direction, universe, landmark)
                sup = support(cell)
                low = cell.loc[cell["adverse_score"] < 0.5]
                high = cell.loc[cell["adverse_score"] >= 0.5]
                rho = spearman(cell["adverse_score"], cell["rcv_return"])
                lm = float(low["rcv_return"].mean()) if len(low) else np.nan
                hm = float(high["rcv_return"].mean()) if len(high) else np.nan
                spread = hm - lm if np.isfinite(hm) and np.isfinite(lm) else np.nan
                lopo_rcv_spreads = []
                complete = True
                for pair in lopo_pairs(base, direction, universe, landmark):
                    x = transport_cell(base, direction, universe, landmark, pair)
                    xl = x.loc[x["adverse_score"] < 0.5]
                    xh = x.loc[x["adverse_score"] >= 0.5]
                    if xl.empty or xh.empty:
                        complete = False
                        break
                    s = float(xh["rcv_return"].mean() - xl["rcv_return"].mean())
                    if not np.isfinite(s):
                        complete = False
                        break
                    lopo_rcv_spreads.append(s)
                lmin = min(lopo_rcv_spreads) if lopo_rcv_spreads else np.nan
                lmax = max(lopo_rcv_spreads) if lopo_rcv_spreads else np.nan
                if not sup["support_pass"]:
                    outcome = INSUFFICIENT
                elif not np.isfinite(rho) or not np.isfinite(spread) or not complete:
                    outcome = UNEVALUABLE
                elif rho < 0 and spread < 0 and lmax < 0:
                    outcome = QUALIFIED
                elif rho > 0 and spread > 0 and lmin > 0:
                    outcome = REVERSED
                else:
                    outcome = NO_EDGE
                rows.append(
                    {
                        "transport_direction": direction,
                        "landmark_age_hours": landmark,
                        "universe_id": universe,
                        "evaluation_period": direction_periods(direction)[1],
                        "decision_row_count": len(cell),
                        **sup,
                        "spearman_rho_adverse_score_vs_rcv": rho,
                        "low_score_count": len(low),
                        "high_score_count": len(high),
                        "low_score_mean_rcv": lm,
                        "high_score_mean_rcv": hm,
                        "high_minus_low_mean_rcv_spread": spread,
                        "lopo_complete": complete,
                        "lopo_pair_count": len(lopo_rcv_spreads),
                        "lopo_minimum_rcv_spread": lmin,
                        "lopo_maximum_rcv_spread": lmax,
                        "cell_outcome": outcome,
                    }
                )
    return pd.DataFrame(rows)


def tail_eval(base: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for direction in DIRECTIONS:
        for landmark in LANDMARKS:
            for universe in UNIVERSES:
                cell = transport_cell(base, direction, universe, landmark)
                tail = cell.loc[cell["adverse_score"] >= TAIL_THRESHOLD].copy()
                sup = tail_support(tail)
                mean = float(tail["rcv_return"].mean()) if len(tail) else np.nan
                median = float(tail["rcv_return"].median()) if len(tail) else np.nan
                lopo_tail_means = []
                complete = True
                for pair in lopo_pairs(base, direction, universe, landmark):
                    x = transport_cell(base, direction, universe, landmark, pair)
                    xt = x.loc[x["adverse_score"] >= TAIL_THRESHOLD]
                    if xt.empty:
                        complete = False
                        break
                    v = float(xt["rcv_return"].mean())
                    if not np.isfinite(v):
                        complete = False
                        break
                    lopo_tail_means.append(v)
                lmin = min(lopo_tail_means) if lopo_tail_means else np.nan
                lmax = max(lopo_tail_means) if lopo_tail_means else np.nan
                if not sup["tail_support_pass"]:
                    outcome = INSUFFICIENT
                elif not np.isfinite(mean) or not np.isfinite(median) or not complete:
                    outcome = UNEVALUABLE
                elif mean < 0 and median < 0 and lmax < 0:
                    outcome = TAIL_QUALIFIED
                else:
                    outcome = TAIL_NOT_NEGATIVE
                rows.append(
                    {
                        "transport_direction": direction,
                        "landmark_age_hours": landmark,
                        "universe_id": universe,
                        "evaluation_period": direction_periods(direction)[1],
                        **sup,
                        "tail_row_count": len(tail),
                        "tail_mean_rcv": mean,
                        "tail_median_rcv": median,
                        "lopo_complete": complete,
                        "lopo_pair_count": len(lopo_tail_means),
                        "lopo_minimum_tail_mean_rcv": lmin,
                        "lopo_maximum_tail_mean_rcv": lmax,
                        "cell_outcome": outcome,
                    }
                )
    return pd.DataFrame(rows)


def score_ledger(base: pd.DataFrame) -> pd.DataFrame:
    parts = []
    for direction in DIRECTIONS:
        for landmark in LANDMARKS:
            for universe in UNIVERSES:
                cell = transport_cell(base, direction, universe, landmark)
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
                        "time_failure_event",
                        "rcv_return",
                        *FEATURES,
                        *[f"{f}_adverse_percentile" for f in FEATURES],
                        "adverse_score",
                    ]
                ].copy()
                keep.insert(0, "transport_direction", direction)
                keep.insert(1, "calibration_period", direction_periods(direction)[0])
                keep.insert(2, "evaluation_period", direction_periods(direction)[1])
                parts.append(keep)
    return pd.concat(parts, ignore_index=True)


def qcount(frame: pd.DataFrame, direction: str, landmark: int, value: str) -> int:
    x = frame.loc[
        (frame["transport_direction"] == direction)
        & (frame["landmark_age_hours"] == landmark)
        & (frame["cell_outcome"] == value)
    ]
    return int(x["universe_id"].astype(str).nunique())


def qualify(hazard: pd.DataFrame, rcv: pd.DataFrame, tail: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for landmark in LANDMARKS:
        r = {"landmark_age_hours": landmark}
        hp = []
        fp = []
        for direction, prefix in ((FORWARD, "forward"), (REVERSE, "reverse")):
            h = qcount(hazard, direction, landmark, QUALIFIED)
            v = qcount(rcv, direction, landmark, QUALIFIED)
            t = qcount(tail, direction, landmark, TAIL_QUALIFIED)
            hpass = h >= 2
            full = hpass and v >= 2 and t >= 2
            r[f"{prefix}_hazard_qualified_universes"] = h
            r[f"{prefix}_rcv_qualified_universes"] = v
            r[f"{prefix}_negative_tail_qualified_universes"] = t
            r[f"{prefix}_hazard_transport_pass"] = hpass
            r[f"{prefix}_economic_alignment_pass"] = v >= 2 and t >= 2
            r[f"{prefix}_all_three_gates_pass"] = full
            hp.append(hpass)
            fp.append(full)
        r["hazard_transports_both_directions"] = all(hp)
        r["economically_aligned_both_directions"] = all(fp)
        r["advances_to_action_mapping_preregistration"] = all(fp)
        rows.append(r)
    return pd.DataFrame(rows)


def decide(q: pd.DataFrame) -> tuple[str, str]:
    if q["advances_to_action_mapping_preregistration"].astype(bool).any():
        return SUCCESS_DECISION, SUCCESS_NEXT
    if q["hazard_transports_both_directions"].astype(bool).any():
        return HAZARD_ONLY_DECISION, HAZARD_ONLY_NEXT
    return FAILURE_DECISION, FAILURE_NEXT
