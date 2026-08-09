"""Frozen RD39-P2 trade-conditioned lifecycle path diagnostic."""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any, Final

import numpy as np
import pandas as pd

DATA_START: Final = pd.Timestamp("2022-01-01T00:00:00Z")
DATA_CUTOFF: Final = pd.Timestamp("2024-01-01T00:00:00Z")

CONTROL_POLICY: Final = "RD31_REGIME_HYSTERESIS_CONTROL"
CONTROL_PORTFOLIO: Final = "UNION_FOCUS"
DIAGNOSTIC_COST_MULTIPLIER: Final = 1.0

UNIVERSES: Final = ("C2", "D2", "E2")
PERIODS: Final = ("ROBUSTNESS_2022", "ROBUSTNESS_2023")
TARGET_HORIZONS: Final = (6, 24, 48)
PRIMARY_HORIZON: Final = 24

MIN_HOLDING_AGE_HOURS: Final = 24
RECOVERY_WINDOW_HOURS: Final = 12
LOW_PATH_QUARTILE: Final = 0.25
HIGH_PATH_QUARTILE: Final = 0.75
MID_PATH_POSITION: Final = 0.50
MAX_RETAINED_MFE_FRACTION: Final = 0.25

UNRECOVERED: Final = "UNRECOVERED_ENTRY_FAILURE"
ADVERSE: Final = "ADVERSE_PATH_DOMINANCE"
GIVEBACK: Final = "PROFIT_GIVEBACK_FROM_PATH_PEAK"
RECLAIM_CONTROL: Final = "ENTRY_RECLAIM_WITH_HIGH_PATH_POSITION_CONTROL"

FAMILY_ORDER: Final = (
    UNRECOVERED,
    ADVERSE,
    GIVEBACK,
    RECLAIM_CONTROL,
)
PRIMARY_FAMILIES: Final = (
    UNRECOVERED,
    ADVERSE,
    GIVEBACK,
)

MIN_EVENTS: Final = 20
MIN_PAIRS: Final = 5
MIN_SIGNAL_DAYS: Final = 10
MIN_QUALIFIED_UNIVERSES_PER_PERIOD: Final = 2

SUCCESS_DECISION: Final = (
    "RD39_QUALIFIED_TRADE_CONDITIONED_LIFECYCLE_STATES_FREEZE_PRE_EXIT_SHADOW_MAPPING"
)
SUCCESS_NEXT: Final = "RD39_P3_FREEZE_EXIT_BRAIN_MAPPING_FOR_QUALIFIED_LIFECYCLE_STATES"
FAILURE_DECISION: Final = "RD39_TRADE_CONDITIONED_LIFECYCLE_PATH_UNQUALIFIED_NEXT_SOURCE_REQUIRED"
FAILURE_NEXT: Final = "RD40_PREREGISTER_NEXT_SPOT_ONLY_ADAPTIVE_EXIT_INFORMATION_SOURCE"


class RD39P2Error(RuntimeError):
    """Frozen RD39-P2 contract violation."""


def utc(value: Any) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        return timestamp.tz_localize("UTC")
    return timestamp.tz_convert("UTC")


def period_for(value: Any) -> str:
    timestamp = utc(value)
    if pd.Timestamp("2022-01-01T00:00:00Z") <= timestamp < pd.Timestamp("2023-01-01T00:00:00Z"):
        return "ROBUSTNESS_2022"
    if pd.Timestamp("2023-01-01T00:00:00Z") <= timestamp < DATA_CUTOFF:
        return "ROBUSTNESS_2023"
    raise RD39P2Error(f"timestamp outside frozen periods: {timestamp}")


def validate_constants() -> None:
    if UNIVERSES != ("C2", "D2", "E2"):
        raise RD39P2Error("universe registry drifted")
    if TARGET_HORIZONS != (6, 24, 48) or PRIMARY_HORIZON != 24:
        raise RD39P2Error("target horizon registry drifted")
    if FAMILY_ORDER != (
        UNRECOVERED,
        ADVERSE,
        GIVEBACK,
        RECLAIM_CONTROL,
    ):
        raise RD39P2Error("family registry drifted")
    if PRIMARY_FAMILIES != (UNRECOVERED, ADVERSE, GIVEBACK):
        raise RD39P2Error("primary family registry drifted")
    if MIN_HOLDING_AGE_HOURS != 24 or RECOVERY_WINDOW_HOURS != 12:
        raise RD39P2Error("lifecycle window drifted")
    if not math.isclose(LOW_PATH_QUARTILE, 0.25):
        raise RD39P2Error("low path quartile drifted")
    if not math.isclose(HIGH_PATH_QUARTILE, 0.75):
        raise RD39P2Error("high path quartile drifted")
    if not math.isclose(MID_PATH_POSITION, 0.50):
        raise RD39P2Error("path midpoint drifted")
    if not math.isclose(MAX_RETAINED_MFE_FRACTION, 0.25):
        raise RD39P2Error("retained-MFE threshold drifted")
    if (
        MIN_EVENTS != 20
        or MIN_PAIRS != 5
        or MIN_SIGNAL_DAYS != 10
        or MIN_QUALIFIED_UNIVERSES_PER_PERIOD != 2
    ):
        raise RD39P2Error("support/qualification contract drifted")


def normalize_price_frame(raw: pd.DataFrame, *, pair: str) -> pd.DataFrame:
    required = {"timestamp", "open", "high", "low", "close"}
    missing = sorted(required.difference(raw.columns))
    if missing:
        raise RD39P2Error(f"{pair} KuCoin frame missing columns: {missing}")

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
        raise RD39P2Error(f"duplicate KuCoin timestamp: {pair}")
    if len(frame) and frame["timestamp"].min() < DATA_START:
        raise RD39P2Error(f"pre-2022 KuCoin bar entered P2: {pair}")
    if len(frame) and frame["timestamp"].max() >= DATA_CUTOFF:
        raise RD39P2Error(f"2024+ KuCoin bar entered P2: {pair}")

    values = frame[["open", "high", "low", "close"]].to_numpy(dtype=float)
    if not np.isfinite(values).all():
        raise RD39P2Error(f"non-finite KuCoin OHLC: {pair}")
    if bool((values <= 0.0).any()):
        raise RD39P2Error(f"non-positive KuCoin OHLC: {pair}")
    if bool((frame["high"] < frame["low"]).any()):
        raise RD39P2Error(f"high below low: {pair}")
    if bool((frame["high"] < frame[["open", "close"]].max(axis=1)).any()):
        raise RD39P2Error(f"high below open/close: {pair}")
    if bool((frame["low"] > frame[["open", "close"]].min(axis=1)).any()):
        raise RD39P2Error(f"low above open/close: {pair}")
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


def lifecycle_snapshot(
    lookup: Mapping[int, tuple[float, float, float, float]],
    *,
    entry_time: Any,
    entry_price: float,
    control_exit_time: Any,
    decision_time: Any,
) -> dict[str, Any] | None:
    entry = utc(entry_time)
    exit_time = utc(control_exit_time)
    decision = utc(decision_time)
    entry_price = float(entry_price)

    if not math.isfinite(entry_price) or entry_price <= 0.0:
        raise RD39P2Error("invalid frozen entry price")
    if entry != entry.floor("h") or exit_time != exit_time.floor("h"):
        raise RD39P2Error("control trade boundary is not hourly")
    if decision != decision.floor("h"):
        raise RD39P2Error("decision timestamp is not hourly")
    if not entry < exit_time:
        raise RD39P2Error("control trade has non-positive holding interval")

    age_hours = int((decision - entry).total_seconds() // 3600)
    remaining_hours = int((exit_time - decision).total_seconds() // 3600)
    if age_hours < MIN_HOLDING_AGE_HOURS:
        return None
    if remaining_hours < PRIMARY_HORIZON:
        return None

    expected = list(
        pd.date_range(
            entry,
            decision - pd.Timedelta(hours=1),
            freq="h",
            tz="UTC",
        )
    )
    if len(expected) != age_hours:
        raise RD39P2Error("path-hour cardinality drifted")

    rows: list[tuple[float, float, float, float]] = []
    for timestamp in expected:
        row = lookup.get(int(timestamp.as_unit("ns").value))
        if row is None:
            return None
        rows.append(row)

    if len(rows) < MIN_HOLDING_AGE_HOURS:
        return None

    current_close = float(rows[-1][3])
    max_high = max(float(row[1]) for row in rows)
    min_low = min(float(row[2]) for row in rows)
    current_return = current_close / entry_price - 1.0
    mfe_return = max_high / entry_price - 1.0
    mae_return = min_low / entry_price - 1.0

    path_range = mfe_return - mae_return
    path_position: float | None = (
        float((current_return - mae_return) / path_range) if path_range > 0.0 else None
    )

    retained_mfe_fraction: float | None = (
        float(current_return / mfe_return) if mfe_return > 0.0 else None
    )

    recent = rows[-RECOVERY_WINDOW_HOURS:]
    above = int(sum(float(row[3]) > entry_price for row in recent))
    below = int(sum(float(row[3]) < entry_price for row in recent))

    states = {
        UNRECOVERED: bool(current_return < 0.0 and above == 0),
        ADVERSE: bool(
            current_return < 0.0
            and path_position is not None
            and path_position <= LOW_PATH_QUARTILE
            and abs(mae_return) >= max(mfe_return, 0.0)
        ),
        GIVEBACK: bool(
            mfe_return > 0.0
            and current_return > 0.0
            and retained_mfe_fraction is not None
            and retained_mfe_fraction <= MAX_RETAINED_MFE_FRACTION
            and path_position is not None
            and path_position <= MID_PATH_POSITION
        ),
        RECLAIM_CONTROL: bool(
            current_return > 0.0
            and below >= 1
            and path_position is not None
            and path_position >= HIGH_PATH_QUARTILE
        ),
    }

    return {
        "decision_time": decision,
        "holding_age_hours": age_hours,
        "remaining_control_hours": remaining_hours,
        "entry_relative_close_return": float(current_return),
        "mfe_return": float(mfe_return),
        "mae_return": float(mae_return),
        "path_position": path_position,
        "retained_mfe_fraction": retained_mfe_fraction,
        "last_12_completed_closes_above_entry_count": above,
        "last_12_completed_closes_below_entry_count": below,
        **states,
    }


def events_from_trade_states(
    state_rows: list[dict[str, Any]],
) -> pd.DataFrame:
    previous: dict[
        tuple[int, str],
        tuple[pd.Timestamp, bool],
    ] = {}
    records: list[dict[str, Any]] = []

    sorted_rows = sorted(
        state_rows,
        key=lambda row: (
            int(row["control_trade_id"]),
            utc(row["decision_time"]),
        ),
    )
    context_fields = (
        "universe_id",
        "period_id",
        "pair",
        "entry_time",
        "control_exit_time",
        "entry_price",
        "holding_age_hours",
        "remaining_control_hours",
        "entry_relative_close_return",
        "mfe_return",
        "mae_return",
        "path_position",
        "retained_mfe_fraction",
        "last_12_completed_closes_above_entry_count",
        "last_12_completed_closes_below_entry_count",
    )

    for row in sorted_rows:
        trade_id = int(row["control_trade_id"])
        decision = utc(row["decision_time"])
        expected_previous = decision - pd.Timedelta(hours=1)

        for family in FAMILY_ORDER:
            key = (trade_id, family)
            current = bool(row[family])
            prior = previous.get(key)
            prior_is_consecutive_false = (
                prior is not None and prior[0] == expected_previous and prior[1] is False
            )
            if prior_is_consecutive_false and current:
                record: dict[str, Any] = {
                    "family_id": family,
                    "control_trade_id": trade_id,
                    "decision_time": decision,
                }
                for field in context_fields:
                    record[field] = row[field]
                records.append(record)
            previous[key] = (decision, current)

    columns = [
        "family_id",
        "control_trade_id",
        "decision_time",
        *context_fields,
    ]
    result = pd.DataFrame.from_records(records, columns=columns)
    if result.empty:
        result["event_id"] = pd.Series(dtype="int64")
        return result

    family_order = {family: index for index, family in enumerate(FAMILY_ORDER)}
    result["_family_order"] = result["family_id"].map(family_order)
    result = (
        result.sort_values(
            [
                "decision_time",
                "universe_id",
                "control_trade_id",
                "_family_order",
            ],
            kind="stable",
        )
        .drop(columns="_family_order")
        .reset_index(drop=True)
    )
    result["event_id"] = np.arange(len(result), dtype=np.int64)
    return result


def target_markout(
    lookup: Mapping[int, tuple[float, float, float, float]],
    *,
    decision_time: Any,
    control_exit_time: Any,
    horizon_hours: int,
) -> dict[str, Any] | None:
    if horizon_hours not in TARGET_HORIZONS:
        raise RD39P2Error(f"unexpected target horizon: {horizon_hours}")

    decision = utc(decision_time)
    control_exit = utc(control_exit_time)
    exit_time = decision + pd.Timedelta(hours=horizon_hours)

    if exit_time > control_exit:
        return None
    if exit_time >= DATA_CUTOFF:
        return None

    entry_row = lookup.get(int(decision.as_unit("ns").value))
    exit_row = lookup.get(int(exit_time.as_unit("ns").value))
    if entry_row is None or exit_row is None:
        return None

    entry_open = float(entry_row[0])
    exit_open = float(exit_row[0])
    if entry_open <= 0.0 or exit_open <= 0.0:
        raise RD39P2Error("invalid markout open")
    return {
        "entry_time": decision,
        "exit_time": exit_time,
        "entry_open": entry_open,
        "exit_open": exit_open,
        "forward_return": float(exit_open / entry_open - 1.0),
    }


def build_markout_ledger(
    events: pd.DataFrame,
    lookups: Mapping[str, Mapping[int, tuple[float, float, float, float]]],
) -> pd.DataFrame:
    records: list[dict[str, Any]] = []
    for event in events.to_dict(orient="records"):
        pair = str(event["pair"])
        lookup = lookups.get(pair)
        if lookup is None:
            raise RD39P2Error(f"missing price lookup for {pair}")

        for horizon in TARGET_HORIZONS:
            markout = target_markout(
                lookup,
                decision_time=event["decision_time"],
                control_exit_time=event["control_exit_time"],
                horizon_hours=horizon,
            )
            if markout is None:
                continue
            records.append(
                {
                    "event_id": int(event["event_id"]),
                    "family_id": str(event["family_id"]),
                    "control_trade_id": int(event["control_trade_id"]),
                    "universe_id": str(event["universe_id"]),
                    "period_id": str(event["period_id"]),
                    "pair": pair,
                    "decision_time": utc(event["decision_time"]),
                    "horizon_hours": horizon,
                    "exit_time": markout["exit_time"],
                    "entry_open": markout["entry_open"],
                    "exit_open": markout["exit_open"],
                    "forward_return": markout["forward_return"],
                }
            )

    columns = [
        "event_id",
        "family_id",
        "control_trade_id",
        "universe_id",
        "period_id",
        "pair",
        "decision_time",
        "horizon_hours",
        "exit_time",
        "entry_open",
        "exit_open",
        "forward_return",
    ]
    result = pd.DataFrame.from_records(records, columns=columns)
    if not result.empty:
        result = result.sort_values(
            [
                "decision_time",
                "family_id",
                "universe_id",
                "control_trade_id",
                "horizon_hours",
            ],
            kind="stable",
        ).reset_index(drop=True)
    return result


def lopo_worst_mean(frame: pd.DataFrame, *, direction: str) -> float:
    if frame.empty:
        return float("nan")
    pairs = sorted(frame["pair"].astype(str).unique())
    if len(pairs) < 2:
        return float("nan")

    means: list[float] = []
    for pair in pairs:
        remaining = frame.loc[frame["pair"].astype(str) != pair]
        if remaining.empty:
            continue
        means.append(float(remaining["forward_return"].mean()))

    if not means:
        return float("nan")
    if direction == "NEGATIVE":
        return max(means)
    if direction == "POSITIVE":
        return min(means)
    raise RD39P2Error(f"unexpected LOPO direction: {direction}")


def summarize_markouts(markouts: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for family in FAMILY_ORDER:
        direction = "NEGATIVE" if family in PRIMARY_FAMILIES else "POSITIVE"
        for universe in UNIVERSES:
            for period in PERIODS:
                for horizon in TARGET_HORIZONS:
                    cell = markouts.loc[
                        (markouts["family_id"] == family)
                        & (markouts["universe_id"] == universe)
                        & (markouts["period_id"] == period)
                        & (markouts["horizon_hours"] == horizon)
                    ]
                    returns = pd.to_numeric(
                        cell["forward_return"],
                        errors="coerce",
                    ).dropna()
                    rows.append(
                        {
                            "family_id": family,
                            "expected_direction": direction,
                            "universe_id": universe,
                            "period_id": period,
                            "horizon_hours": horizon,
                            "event_count": int(cell["event_id"].nunique()),
                            "trade_count": int(cell["control_trade_id"].nunique()),
                            "pair_count": int(cell["pair"].astype(str).nunique()),
                            "signal_day_count": int(
                                pd.to_datetime(
                                    cell["decision_time"],
                                    utc=True,
                                    errors="coerce",
                                )
                                .dt.floor("D")
                                .nunique()
                            ),
                            "markout_count": int(len(cell)),
                            "mean_forward_return": (
                                float(returns.mean()) if len(returns) else np.nan
                            ),
                            "median_forward_return": (
                                float(returns.median()) if len(returns) else np.nan
                            ),
                            "positive_share": (
                                float((returns > 0.0).mean()) if len(returns) else np.nan
                            ),
                            "lopo_worst_directional_mean": lopo_worst_mean(
                                cell,
                                direction=direction,
                            ),
                        }
                    )
    return pd.DataFrame.from_records(rows)


def qualification_tables(
    summary: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    negative_rows: list[dict[str, Any]] = []

    for family in PRIMARY_FAMILIES:
        for universe in UNIVERSES:
            for period in PERIODS:
                cell = summary.loc[
                    (summary["family_id"] == family)
                    & (summary["universe_id"] == universe)
                    & (summary["period_id"] == period)
                    & (summary["horizon_hours"] == PRIMARY_HORIZON)
                ]
                if len(cell) != 1:
                    raise RD39P2Error("expected one primary qualification cell")
                row = cell.iloc[0]

                event_count = int(row["event_count"])
                pair_count = int(row["pair_count"])
                signal_days = int(row["signal_day_count"])
                mean_value = float(row["mean_forward_return"])
                median_value = float(row["median_forward_return"])
                lopo_value = float(row["lopo_worst_directional_mean"])

                support = (
                    event_count >= MIN_EVENTS
                    and pair_count >= MIN_PAIRS
                    and signal_days >= MIN_SIGNAL_DAYS
                )
                direction = (
                    np.isfinite(mean_value)
                    and np.isfinite(median_value)
                    and np.isfinite(lopo_value)
                    and mean_value < 0.0
                    and median_value < 0.0
                    and lopo_value < 0.0
                )
                negative_rows.append(
                    {
                        "family_id": family,
                        "universe_id": universe,
                        "period_id": period,
                        "event_count_24h": event_count,
                        "trade_count_24h": int(row["trade_count"]),
                        "pair_count_24h": pair_count,
                        "signal_day_count_24h": signal_days,
                        "mean_24h": mean_value,
                        "median_24h": median_value,
                        "lopo_worst_mean_24h": lopo_value,
                        "support_pass": bool(support),
                        "direction_pass": bool(direction),
                        "cell_qualified": bool(support and direction),
                    }
                )

    negative = pd.DataFrame.from_records(negative_rows)
    family_rows: list[dict[str, Any]] = []

    for family in PRIMARY_FAMILIES:
        subset = negative.loc[negative["family_id"] == family]
        counts = {
            period: int(
                subset.loc[
                    subset["period_id"] == period,
                    "cell_qualified",
                ].sum()
            )
            for period in PERIODS
        }
        qualified = all(count >= MIN_QUALIFIED_UNIVERSES_PER_PERIOD for count in counts.values())
        family_rows.append(
            {
                "family_id": family,
                "qualified_universes_2022": counts["ROBUSTNESS_2022"],
                "qualified_universes_2023": counts["ROBUSTNESS_2023"],
                "qualified": bool(qualified),
                "advances_to_mapping_freeze": bool(qualified),
                "winner_selection_used": False,
                "threshold_optimization_used": False,
                "parameter_search_used": False,
            }
        )
    families = pd.DataFrame.from_records(family_rows)

    control_rows: list[dict[str, Any]] = []
    for universe in UNIVERSES:
        for period in PERIODS:
            cell = summary.loc[
                (summary["family_id"] == RECLAIM_CONTROL)
                & (summary["universe_id"] == universe)
                & (summary["period_id"] == period)
                & (summary["horizon_hours"] == PRIMARY_HORIZON)
            ]
            if len(cell) != 1:
                raise RD39P2Error("expected one positive-control cell")
            row = cell.iloc[0]
            event_count = int(row["event_count"])
            pair_count = int(row["pair_count"])
            signal_days = int(row["signal_day_count"])
            mean_value = float(row["mean_forward_return"])
            median_value = float(row["median_forward_return"])
            support = (
                event_count >= MIN_EVENTS
                and pair_count >= MIN_PAIRS
                and signal_days >= MIN_SIGNAL_DAYS
            )
            direction = (
                np.isfinite(mean_value)
                and np.isfinite(median_value)
                and mean_value > 0.0
                and median_value > 0.0
            )
            control_rows.append(
                {
                    "family_id": RECLAIM_CONTROL,
                    "universe_id": universe,
                    "period_id": period,
                    "event_count_24h": event_count,
                    "trade_count_24h": int(row["trade_count"]),
                    "pair_count_24h": pair_count,
                    "signal_day_count_24h": signal_days,
                    "mean_24h": mean_value,
                    "median_24h": median_value,
                    "support_pass": bool(support),
                    "direction_pass": bool(direction),
                    "control_cell_pass": bool(support and direction),
                    "selection_eligible": False,
                }
            )
    control = pd.DataFrame.from_records(control_rows)
    return negative, families, control
