"""RD48-P2 target-blind cross-venue price-level-basis reconstruction."""

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
LANDMARKS: Final = (24, 48, 72, 96, 120, 144)
RESOLVED: Final = "RESOLVED_CONTROL_OUTCOME"
CENSORED: Final = "RIGHT_CENSORED_AT_CUTOFF"

AXIS_MEAN_BASIS: Final = "BTC_ETH_MEAN_SIGNED_CROSS_VENUE_LOG_CLOSE_PRICE_BASIS"
AXIS_BASIS_DISPERSION: Final = "BTC_ETH_CROSS_VENUE_LOG_CLOSE_PRICE_BASIS_DISPERSION"

MIN_POSITIONS: Final = 20
MIN_PAIRS: Final = 5
MIN_SIGNAL_DAYS: Final = 10

MAINTENANCE_START: Final = pd.Timestamp("2023-03-24T11:38:00Z")
MAINTENANCE_END: Final = pd.Timestamp("2023-03-24T14:00:00Z")


class RD48P2Error(RuntimeError):
    """Frozen RD48-P2 contract violation."""


def utc(value: Any) -> pd.Timestamp:
    stamp = pd.Timestamp(value)
    if stamp.tzinfo is None:
        return stamp.tz_localize("UTC")
    return stamp.tz_convert("UTC")


def timestamp_key(value: Any) -> int:
    """Stable nanosecond UTC key independent of pandas array resolution."""
    return int(utc(value).as_unit("ns").value)


def period_for(value: Any) -> str:
    stamp = utc(value)
    if pd.Timestamp("2022-01-01T00:00:00Z") <= stamp < pd.Timestamp("2023-01-01T00:00:00Z"):
        return "ROBUSTNESS_2022"
    if pd.Timestamp("2023-01-01T00:00:00Z") <= stamp < DATA_CUTOFF:
        return "ROBUSTNESS_2023"
    raise RD48P2Error(f"timestamp outside frozen RD48 periods: {stamp}")


def terminal_time(row: Mapping[str, Any]) -> pd.Timestamp:
    risk_class = str(row["risk_set_class"])
    if risk_class == RESOLVED:
        value = row.get("exit_time")
        if pd.isna(value):
            raise RD48P2Error("resolved control row lacks exit_time")
        return utc(value)
    if risk_class == CENSORED:
        return DATA_CUTOFF
    raise RD48P2Error(f"unexpected risk_set_class: {risk_class}")


def reconstruct_decision_rows(risk_set: pd.DataFrame) -> pd.DataFrame:
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
        raise RD48P2Error(f"risk-set ledger missing columns: {missing}")

    records: list[dict[str, Any]] = []
    for row in risk_set.to_dict(orient="records"):
        risk_class = str(row["risk_set_class"])
        if risk_class not in {RESOLVED, CENSORED}:
            continue

        universe = str(row["universe_id"])
        period = str(row["period_id"])
        if universe not in UNIVERSES:
            raise RD48P2Error(f"unexpected universe: {universe}")
        if period not in PERIODS:
            raise RD48P2Error(f"unexpected period: {period}")

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
                raise RD48P2Error(f"signal period drift for {position_id}: {signal} vs {period}")
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
                    "completed_information_time": decision - pd.Timedelta(hours=1),
                }
            )

    result = pd.DataFrame.from_records(records)
    if result.empty:
        raise RD48P2Error("reconstructed risk-set decision ledger is empty")
    if result["decision_id"].duplicated().any():
        raise RD48P2Error("duplicate decision ids")

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
        raise RD48P2Error(f"frozen age census missing columns: {missing}")

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

    fields = [
        "decision_row_count",
        "unique_control_position_count",
        "unique_pair_count",
        "unique_signal_day_count",
    ]
    merged["key_match"] = merged["_merge"].eq("both")
    merged["parity_pass"] = merged["key_match"]

    for field in fields:
        left = pd.to_numeric(merged[f"{field}_reconstructed"], errors="coerce")
        right = pd.to_numeric(merged[f"{field}_frozen"], errors="coerce")
        merged[f"{field}_match"] = left.eq(right)
        merged["parity_pass"] &= merged[f"{field}_match"]

    return merged.sort_values(keys, kind="stable").reset_index(drop=True)


def normalize_kucoin_hours(raw: pd.DataFrame) -> pd.DataFrame:
    required = {"timestamp", "close"}
    missing = sorted(required.difference(raw.columns))
    if missing:
        raise RD48P2Error(f"KuCoin source missing columns: {missing}")

    frame = raw.loc[:, ["timestamp", "close"]].copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, errors="raise")
    frame["close"] = pd.to_numeric(frame["close"], errors="raise").astype(float)

    frame = (
        frame.sort_values("timestamp", kind="stable")
        .drop_duplicates("timestamp", keep="last")
        .reset_index(drop=True)
    )

    if bool((frame["timestamp"] >= DATA_CUTOFF).any()):
        raise RD48P2Error("2024+ KuCoin row entered memory")

    values = frame["close"].to_numpy(dtype=float)
    if not np.isfinite(values).all():
        raise RD48P2Error("non-finite KuCoin close")
    if bool((frame["close"] <= 0.0).any()):
        raise RD48P2Error("non-positive KuCoin close")

    return frame


def kucoin_hour_lookup(raw: pd.DataFrame) -> dict[int, float]:
    frame = normalize_kucoin_hours(raw)
    return {timestamp_key(row.timestamp): float(row.close) for row in frame.itertuples(index=False)}


def normalize_binance_minutes(raw: pd.DataFrame) -> pd.DataFrame:
    required = {"open_time", "close"}
    missing = sorted(required.difference(raw.columns))
    if missing:
        raise RD48P2Error(f"Binance source missing columns: {missing}")

    frame = raw.loc[:, ["open_time", "close"]].copy()
    numeric_time = pd.to_numeric(frame["open_time"], errors="raise")
    frame["open_time"] = pd.to_datetime(
        numeric_time,
        unit="ms",
        utc=True,
        errors="raise",
    )
    frame["close"] = pd.to_numeric(frame["close"], errors="raise").astype(float)

    if bool((frame["open_time"] >= DATA_CUTOFF).any()):
        raise RD48P2Error("2024+ Binance minute entered memory")

    values = frame["close"].to_numpy(dtype=float)
    if not np.isfinite(values).all():
        raise RD48P2Error("non-finite Binance close")
    if bool((frame["close"] <= 0.0).any()):
        raise RD48P2Error("non-positive Binance close")

    return frame.sort_values("open_time", kind="stable").reset_index(drop=True)


def hour_overlaps_maintenance(hour_open: pd.Timestamp) -> bool:
    h = utc(hour_open)
    return bool(h < MAINTENANCE_END and h + pd.Timedelta(hours=1) > MAINTENANCE_START)


def aggregate_binance_hours(
    raw: pd.DataFrame,
) -> tuple[dict[int, float], dict[str, int]]:
    frame = normalize_binance_minutes(raw)
    if frame.empty:
        return {}, {
            "minute_rows": 0,
            "candidate_hours": 0,
            "valid_hours": 0,
            "invalid_grid_hours": 0,
            "maintenance_invalidated_hours": 0,
        }

    frame["hour_open"] = frame["open_time"].dt.floor("h")

    lookup: dict[int, float] = {}
    candidate = 0
    invalid_grid = 0
    maintenance = 0

    for hour, raw_group in frame.groupby("hour_open", sort=True):
        candidate += 1
        h = utc(hour)

        if hour_overlaps_maintenance(h):
            maintenance += 1
            continue

        group = raw_group.sort_values("open_time", kind="stable").reset_index(drop=True)
        times = pd.DatetimeIndex(group["open_time"])
        expected = pd.date_range(start=h, periods=60, freq="min")

        exact_grid = len(group) == 60 and times.nunique() == 60 and times.equals(expected)
        if not exact_grid:
            invalid_grid += 1
            continue

        hour_close = float(group.iloc[-1]["close"])
        if not (math.isfinite(hour_close) and hour_close > 0.0):
            raise RD48P2Error("invalid aggregated Binance close")

        lookup[timestamp_key(h)] = hour_close

    return lookup, {
        "minute_rows": int(len(frame)),
        "candidate_hours": int(candidate),
        "valid_hours": int(len(lookup)),
        "invalid_grid_hours": int(invalid_grid),
        "maintenance_invalidated_hours": int(maintenance),
    }


def price_basis(binance_close: float, kucoin_close: float) -> float | None:
    if not (
        math.isfinite(binance_close)
        and math.isfinite(kucoin_close)
        and binance_close > 0.0
        and kucoin_close > 0.0
    ):
        return None
    value = math.log(binance_close / kucoin_close)
    return value if math.isfinite(value) else None


def compute_axes(
    hour_open: pd.Timestamp,
    kucoin: Mapping[str, Mapping[int, float]],
    binance: Mapping[str, Mapping[int, float]],
) -> dict[str, Any]:
    key = timestamp_key(hour_open)
    mapping = (
        ("BTC", "BTC-USDT", "BTCUSDT"),
        ("ETH", "ETH-USDT", "ETHUSDT"),
    )

    components: dict[str, float] = {}
    bases: dict[str, float] = {}

    for label, ksymbol, bsymbol in mapping:
        kclose = kucoin.get(ksymbol, {}).get(key)
        bclose = binance.get(bsymbol, {}).get(key)

        if kclose is None or bclose is None:
            return {
                "feature_valid": False,
                "feature_status": f"MISSING_SOURCE_HOUR_{label}",
                AXIS_MEAN_BASIS: math.nan,
                AXIS_BASIS_DISPERSION: math.nan,
            }

        basis = price_basis(float(bclose), float(kclose))
        if basis is None:
            return {
                "feature_valid": False,
                "feature_status": f"INVALID_CLOSE_PRICE_{label}",
                AXIS_MEAN_BASIS: math.nan,
                AXIS_BASIS_DISPERSION: math.nan,
            }

        components[f"{label.lower()}_kucoin_close"] = float(kclose)
        components[f"{label.lower()}_binance_close"] = float(bclose)
        components[f"{label.lower()}_cross_venue_log_close_price_basis"] = basis
        bases[label] = basis

    axis_mean = 0.5 * (bases["BTC"] + bases["ETH"])
    axis_dispersion = abs(bases["BTC"] - bases["ETH"])

    if not (math.isfinite(axis_mean) and math.isfinite(axis_dispersion)):
        raise RD48P2Error("non-finite RD48 axes")

    return {
        "feature_valid": True,
        "feature_status": "VALID_ALL_FOUR_CLOSE_COMPONENTS",
        **components,
        AXIS_MEAN_BASIS: axis_mean,
        AXIS_BASIS_DISPERSION: axis_dispersion,
    }


def attach_features(
    decisions: pd.DataFrame,
    kucoin: Mapping[str, Mapping[int, float]],
    binance: Mapping[str, Mapping[int, float]],
) -> pd.DataFrame:
    records: list[dict[str, Any]] = []

    for row in decisions.to_dict(orient="records"):
        decision = utc(row["decision_time"])
        hour_open = decision - pd.Timedelta(hours=1)
        records.append(
            {
                **row,
                "source_hour_open": hour_open,
                **compute_axes(hour_open, kucoin, binance),
            }
        )

    return pd.DataFrame.from_records(records)


def support_census(feature_ledger: pd.DataFrame) -> pd.DataFrame:
    records: list[dict[str, Any]] = []

    for period in PERIODS:
        for universe in UNIVERSES:
            for age in LANDMARKS:
                cell = feature_ledger.loc[
                    (feature_ledger["period_id"].astype(str) == period)
                    & (feature_ledger["universe_id"].astype(str) == universe)
                    & (
                        pd.to_numeric(
                            feature_ledger["landmark_age_hours"],
                            errors="raise",
                        )
                        == age
                    )
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
                raise RD48P2Error(f"support census lacks 3 universes: {period} {age}h")
            by_period[period] = int(cell["support_pass"].astype(bool).sum())

        passed = all(by_period[p] >= 2 for p in PERIODS)
        matrix.append(
            {
                "landmark_age_hours": age,
                "ROBUSTNESS_2022_supporting_universe_count": by_period["ROBUSTNESS_2022"],
                "ROBUSTNESS_2023_supporting_universe_count": by_period["ROBUSTNESS_2023"],
                "transport_support_pass": passed,
            }
        )

        if passed:
            qualified.append(age)

    return {
        "transport_rule": "LANDMARK_ADVANCES_ONLY_IF_SUPPORT_PASS_IN_AT_LEAST_2_OF_3_"
        "UNIVERSES_IN_BOTH_2022_AND_2023",
        "qualified_landmarks_hours": qualified,
        "qualified_landmark_count": len(qualified),
        "landmark_transport_matrix": matrix,
    }
