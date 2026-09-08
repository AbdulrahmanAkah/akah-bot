"""RD45-P2 target-blind market-participation-state reconstruction.

This module is deliberately independent of RCV/target values.  It reconstructs
the frozen RD41 landmark risk set and computes only the two RD45-P1
pre-registered quote-turnover participation axes from completed information.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any, Final

import numpy as np
import pandas as pd

DATA_START: Final = pd.Timestamp("2022-01-01T00:00:00Z")
DATA_CUTOFF: Final = pd.Timestamp("2024-01-01T00:00:00Z")
UNIVERSES: Final = ("C2", "D2", "E2")
PERIODS: Final = ("ROBUSTNESS_2022", "ROBUSTNESS_2023")
LANDMARKS: Final = (24, 48, 72, 96, 120, 144)

RESOLVED: Final = "RESOLVED_CONTROL_OUTCOME"
CENSORED: Final = "RIGHT_CENSORED_AT_CUTOFF"

AXIS_LEVEL: Final = "PAIR_VS_PIT_PEER_MEDIAN_LOG_24H_QUOTE_TURNOVER"
AXIS_CHANGE: Final = "PAIR_VS_PIT_PEER_MEDIAN_12H_LOG_TURNOVER_CHANGE"

MIN_POSITIONS: Final = 20
MIN_PAIRS: Final = 5
MIN_SIGNAL_DAYS: Final = 10


class RD45P2Error(RuntimeError):
    """Frozen RD45-P2 contract violation."""


def utc(value: Any) -> pd.Timestamp:
    stamp = pd.Timestamp(value)
    if stamp.tzinfo is None:
        return stamp.tz_localize("UTC")
    return stamp.tz_convert("UTC")


def period_for(value: Any) -> str:
    stamp = utc(value)
    if pd.Timestamp("2022-01-01T00:00:00Z") <= stamp < pd.Timestamp("2023-01-01T00:00:00Z"):
        return "ROBUSTNESS_2022"
    if pd.Timestamp("2023-01-01T00:00:00Z") <= stamp < DATA_CUTOFF:
        return "ROBUSTNESS_2023"
    raise RD45P2Error(f"timestamp outside frozen RD45 periods: {stamp}")


def terminal_time(row: Mapping[str, Any]) -> pd.Timestamp:
    risk_class = str(row["risk_set_class"])
    if risk_class == RESOLVED:
        value = row.get("exit_time")
        if pd.isna(value):
            raise RD45P2Error("resolved control row lacks exit_time")
        return utc(value)
    if risk_class == CENSORED:
        return DATA_CUTOFF
    raise RD45P2Error(f"unexpected risk_set_class: {risk_class}")


def reconstruct_decision_rows(risk_set: pd.DataFrame) -> pd.DataFrame:
    """Reproduce the RD41 open-at-landmark risk-set semantics exactly."""
    required = {
        "control_position_id",
        "universe_id",
        "period_id",
        "pair",
        "signal_time",
        "entry_time",
        "exit_time",
        "risk_set_class",
    }
    missing = sorted(required.difference(risk_set.columns))
    if missing:
        raise RD45P2Error(f"risk-set ledger missing columns: {missing}")

    records: list[dict[str, Any]] = []
    for row in risk_set.to_dict(orient="records"):
        risk_class = str(row["risk_set_class"])
        if risk_class not in {RESOLVED, CENSORED}:
            continue
        universe = str(row["universe_id"])
        period = str(row["period_id"])
        if universe not in UNIVERSES:
            raise RD45P2Error(f"unexpected universe: {universe}")
        if period not in PERIODS:
            raise RD45P2Error(f"unexpected period: {period}")

        entry = utc(row["entry_time"])
        signal = utc(row["signal_time"])
        terminal = terminal_time(row)
        pair = str(row["pair"])
        position_id = str(row["control_position_id"])

        for age in LANDMARKS:
            decision = entry + pd.Timedelta(hours=age)
            if not (decision < DATA_CUTOFF and decision < terminal):
                continue
            if period_for(signal) != period:
                raise RD45P2Error(f"signal period drift for {position_id}: {signal} vs {period}")
            completed = decision - pd.Timedelta(hours=1)
            records.append(
                {
                    "decision_id": f"{position_id}|{age:03d}h",
                    "control_position_id": position_id,
                    "universe_id": universe,
                    "period_id": period,
                    "pair": pair,
                    "signal_time": signal,
                    "entry_time": entry,
                    "decision_time": decision,
                    "landmark_age_hours": age,
                    "completed_information_time": completed,
                }
            )

    result = pd.DataFrame.from_records(records)
    if result.empty:
        raise RD45P2Error("reconstructed risk-set decision ledger is empty")
    if result["decision_id"].duplicated().any():
        dupes = result.loc[result["decision_id"].duplicated(), "decision_id"].head(10)
        raise RD45P2Error(f"duplicate decision ids: {dupes.tolist()}")
    return result.sort_values(
        ["period_id", "universe_id", "decision_time", "decision_id"],
        kind="stable",
    ).reset_index(drop=True)


def summarize_risk_rows(rows: pd.DataFrame) -> pd.DataFrame:
    records: list[dict[str, Any]] = []
    for period in PERIODS:
        for universe in UNIVERSES:
            for age in LANDMARKS:
                cell = rows.loc[
                    (rows["period_id"].astype(str) == period)
                    & (rows["universe_id"].astype(str) == universe)
                    & (pd.to_numeric(rows["landmark_age_hours"], errors="raise") == age)
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
                            pd.to_datetime(cell["signal_time"], utc=True, errors="raise")
                            .dt.floor("D")
                            .nunique()
                        ),
                    }
                )
    return pd.DataFrame.from_records(records)


def risk_set_parity(
    reconstructed: pd.DataFrame,
    frozen_census: pd.DataFrame,
) -> pd.DataFrame:
    required = {
        "period_id",
        "universe_id",
        "landmark_age_hours",
        "decision_row_count",
        "unique_control_position_count",
        "unique_pair_count",
        "unique_signal_day_count",
    }
    missing = sorted(required.difference(frozen_census.columns))
    if missing:
        raise RD45P2Error(f"frozen age census missing columns: {missing}")

    current = summarize_risk_rows(reconstructed)
    reference = frozen_census.loc[:, sorted(required)].copy()
    reference["landmark_age_hours"] = pd.to_numeric(
        reference["landmark_age_hours"], errors="raise"
    ).astype(int)

    keys = ["period_id", "universe_id", "landmark_age_hours"]
    merged = current.merge(
        reference,
        on=keys,
        how="outer",
        suffixes=("_reconstructed", "_frozen"),
        indicator=True,
        validate="one_to_one",
    )
    count_fields = [
        "decision_row_count",
        "unique_control_position_count",
        "unique_pair_count",
        "unique_signal_day_count",
    ]
    for field in count_fields:
        left = pd.to_numeric(merged[f"{field}_reconstructed"], errors="coerce")
        right = pd.to_numeric(merged[f"{field}_frozen"], errors="coerce")
        merged[f"{field}_match"] = left.eq(right)
    merged["key_match"] = merged["_merge"].eq("both")
    merged["parity_pass"] = merged["key_match"]
    for field in count_fields:
        merged["parity_pass"] &= merged[f"{field}_match"]
    return merged.sort_values(keys, kind="stable").reset_index(drop=True)


def normalize_turnover_bars(raw: pd.DataFrame) -> pd.DataFrame:
    required = {"timestamp", "close", "volume"}
    missing = sorted(required.difference(raw.columns))
    if missing:
        raise RD45P2Error(f"raw turnover source missing columns: {missing}")

    frame = raw.loc[:, ["timestamp", "close", "volume"]].copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, errors="raise")
    frame["close"] = pd.to_numeric(frame["close"], errors="raise").astype(float)
    frame["volume"] = pd.to_numeric(frame["volume"], errors="raise").astype(float)
    frame = (
        frame.sort_values("timestamp", kind="stable")
        .drop_duplicates("timestamp", keep="last")
        .reset_index(drop=True)
    )

    if bool((frame["timestamp"] >= DATA_CUTOFF).any()):
        raise RD45P2Error("2024+ raw bar entered RD45-P2 memory")
    if bool((frame["close"] <= 0.0).any()):
        raise RD45P2Error("non-positive close in raw turnover source")
    if bool((frame["volume"] < 0.0).any()):
        raise RD45P2Error("negative volume in raw turnover source")
    if not np.isfinite(frame[["close", "volume"]].to_numpy(dtype=float)).all():
        raise RD45P2Error("non-finite close/volume in raw turnover source")

    frame["quote_turnover_proxy"] = frame["volume"] * frame["close"]
    if not np.isfinite(frame["quote_turnover_proxy"].to_numpy(dtype=float)).all():
        raise RD45P2Error("non-finite quote-turnover proxy")
    return frame


def build_q24_lookup(raw: pd.DataFrame) -> dict[int, float]:
    """Return Q24 only at timestamps backed by 24 exact contiguous completed hours."""
    frame = normalize_turnover_bars(raw)
    if frame.empty:
        return {}

    turnover = {
        int(pd.Timestamp(ts).value): float(value)
        for ts, value in zip(
            frame["timestamp"],
            frame["quote_turnover_proxy"],
            strict=True,
        )
    }
    one_hour_ns = int(pd.Timedelta(hours=1).value)
    result: dict[int, float] = {}

    for stamp_ns in turnover:
        values: list[float] = []
        ok = True
        for offset in range(23, -1, -1):
            value = turnover.get(stamp_ns - offset * one_hour_ns)
            if value is None:
                ok = False
                break
            values.append(value)
        if not ok:
            continue
        total = float(math.fsum(values))
        if math.isfinite(total) and total > 0.0:
            result[stamp_ns] = total
    return result


def compute_axes(
    *,
    held_pair: str,
    peer_pairs: Sequence[str],
    current_q24: Mapping[str, float | None],
    previous_q24: Mapping[str, float | None],
) -> dict[str, Any]:
    peers = tuple(str(pair) for pair in peer_pairs)
    if len(peers) != 6 or len(set(peers)) != 6:
        return {
            "feature_valid": False,
            "feature_status": "PEER_SET_NOT_EXACTLY_SIX",
            AXIS_LEVEL: math.nan,
            AXIS_CHANGE: math.nan,
        }
    if held_pair not in peers:
        return {
            "feature_valid": False,
            "feature_status": "HELD_PAIR_NOT_IN_PEER_SET",
            AXIS_LEVEL: math.nan,
            AXIS_CHANGE: math.nan,
        }

    current_values: list[float] = []
    previous_values: list[float] = []
    for pair in peers:
        current = current_q24.get(pair)
        previous = previous_q24.get(pair)
        if current is None or previous is None:
            return {
                "feature_valid": False,
                "feature_status": "MISSING_PEER_Q24",
                AXIS_LEVEL: math.nan,
                AXIS_CHANGE: math.nan,
            }
        current = float(current)
        previous = float(previous)
        if (
            not math.isfinite(current)
            or not math.isfinite(previous)
            or current <= 0.0
            or previous <= 0.0
        ):
            return {
                "feature_valid": False,
                "feature_status": "NONPOSITIVE_OR_NONFINITE_PEER_Q24",
                AXIS_LEVEL: math.nan,
                AXIS_CHANGE: math.nan,
            }
        current_values.append(current)
        previous_values.append(previous)

    held_current = float(current_q24[held_pair])
    held_previous = float(previous_q24[held_pair])
    peer_median_current = float(np.median(np.asarray(current_values, dtype=float)))
    peer_log_changes = np.log(
        np.asarray(current_values, dtype=float) / np.asarray(previous_values, dtype=float)
    )
    peer_median_log_change = float(np.median(peer_log_changes))
    held_log_change = math.log(held_current / held_previous)

    return {
        "feature_valid": True,
        "feature_status": "VALID",
        "held_q24_current": held_current,
        "held_q24_previous_12h": held_previous,
        "peer_median_q24_current": peer_median_current,
        "peer_median_12h_log_turnover_change": peer_median_log_change,
        "held_12h_log_turnover_change": held_log_change,
        AXIS_LEVEL: math.log(held_current / peer_median_current),
        AXIS_CHANGE: held_log_change - peer_median_log_change,
    }


def support_census(feature_ledger: pd.DataFrame) -> pd.DataFrame:
    records: list[dict[str, Any]] = []
    for period in PERIODS:
        for universe in UNIVERSES:
            for age in LANDMARKS:
                cell = feature_ledger.loc[
                    (feature_ledger["period_id"].astype(str) == period)
                    & (feature_ledger["universe_id"].astype(str) == universe)
                    & (pd.to_numeric(feature_ledger["landmark_age_hours"], errors="raise") == age)
                ]
                valid = cell.loc[cell["feature_valid"].astype(bool)]
                positions = int(valid["control_position_id"].astype(str).nunique())
                pairs = int(valid["pair"].astype(str).nunique())
                signal_days = int(
                    pd.to_datetime(valid["signal_time"], utc=True, errors="coerce")
                    .dt.floor("D")
                    .nunique()
                )
                records.append(
                    {
                        "period_id": period,
                        "universe_id": universe,
                        "landmark_age_hours": age,
                        "risk_set_row_count": int(len(cell)),
                        "valid_feature_row_count": int(len(valid)),
                        "invalid_feature_row_count": int(len(cell) - len(valid)),
                        "unique_control_position_count": positions,
                        "unique_pair_count": pairs,
                        "unique_signal_day_count": signal_days,
                        "minimum_unique_positions_gate": MIN_POSITIONS,
                        "minimum_unique_pairs_gate": MIN_PAIRS,
                        "minimum_unique_signal_days_gate": MIN_SIGNAL_DAYS,
                        "support_pass": bool(
                            positions >= MIN_POSITIONS
                            and pairs >= MIN_PAIRS
                            and signal_days >= MIN_SIGNAL_DAYS
                        ),
                    }
                )
    return pd.DataFrame.from_records(records)


def qualify_transport_support(census: pd.DataFrame) -> dict[str, Any]:
    matrix: list[dict[str, Any]] = []
    qualified: list[int] = []
    for age in LANDMARKS:
        by_period: dict[str, int] = {}
        for period in PERIODS:
            cell = census.loc[
                (census["period_id"].astype(str) == period)
                & (pd.to_numeric(census["landmark_age_hours"], errors="raise") == age)
            ]
            if len(cell) != 3:
                raise RD45P2Error(f"support census lacks 3 universes: {period} {age}h")
            pass_count = int(cell["support_pass"].astype(bool).sum())
            by_period[period] = pass_count
        qualifies = all(by_period[period] >= 2 for period in PERIODS)
        matrix.append(
            {
                "landmark_age_hours": age,
                "ROBUSTNESS_2022_supporting_universe_count": by_period["ROBUSTNESS_2022"],
                "ROBUSTNESS_2023_supporting_universe_count": by_period["ROBUSTNESS_2023"],
                "transport_support_pass": qualifies,
            }
        )
        if qualifies:
            qualified.append(age)
    return {
        "transport_rule": (
            "LANDMARK_ADVANCES_ONLY_IF_SUPPORTED_IN_AT_LEAST_2_OF_3_UNIVERSES_IN_BOTH_2022_AND_2023"
        ),
        "qualified_landmarks_hours": qualified,
        "qualified_landmark_count": len(qualified),
        "landmark_transport_matrix": matrix,
    }
