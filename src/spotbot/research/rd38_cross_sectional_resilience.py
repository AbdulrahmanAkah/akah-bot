"""Frozen RD38-P2 KuCoin-native cross-sectional resilience diagnostic."""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any, Final

import numpy as np
import pandas as pd

DATA_START: Final = pd.Timestamp("2022-01-01T00:00:00Z")
DATA_CUTOFF: Final = pd.Timestamp("2024-01-01T00:00:00Z")
MAX_LOOKBACK_HOURS: Final = 72
SOURCE_HISTORY_START: Final = DATA_START - pd.Timedelta(hours=MAX_LOOKBACK_HOURS + 1)

UNIVERSES: Final = ("C2", "D2", "E2")
HORIZONS: Final = (6, 24, 72)
PRIMARY_HORIZON: Final = 24
CROSS_SECTION_SIZE: Final = 6

PERSISTENT_WEAKNESS: Final = "PERSISTENT_RELATIVE_WEAKNESS"
LEADERSHIP_BREAKDOWN: Final = "LEADERSHIP_BREAKDOWN"
BREADTH_LAGGARD: Final = "BREADTH_CONFIRMED_LAGGARD"
RECLAIM_CONTROL: Final = "RELATIVE_STRENGTH_RECLAIM_CONTROL"

FAMILY_ORDER: Final = (
    PERSISTENT_WEAKNESS,
    LEADERSHIP_BREAKDOWN,
    BREADTH_LAGGARD,
    RECLAIM_CONTROL,
)
PRIMARY_FAMILIES: Final = (
    PERSISTENT_WEAKNESS,
    LEADERSHIP_BREAKDOWN,
    BREADTH_LAGGARD,
)

LOW_QUARTILE: Final = 0.25
HIGH_QUARTILE: Final = 0.75
NEGATIVE_BREADTH_THRESHOLD: Final = 2.0 / 3.0

MIN_EVENTS: Final = 30
MIN_PAIRS: Final = 10
MIN_SIGNAL_DAYS: Final = 20
MIN_QUALIFIED_UNIVERSES_PER_PERIOD: Final = 2

PERIODS: Final = {
    "ROBUSTNESS_2022": (
        pd.Timestamp("2022-01-01T00:00:00Z"),
        pd.Timestamp("2023-01-01T00:00:00Z"),
    ),
    "ROBUSTNESS_2023": (
        pd.Timestamp("2023-01-01T00:00:00Z"),
        pd.Timestamp("2024-01-01T00:00:00Z"),
    ),
}

SUCCESS_DECISION: Final = (
    "RD38_QUALIFIED_CROSS_SECTIONAL_RESILIENCE_STATES_FREEZE_PRE_EXIT_SHADOW_MAPPING"
)
SUCCESS_NEXT: Final = "RD38_P3_FREEZE_EXIT_BRAIN_MAPPING_FOR_QUALIFIED_RESILIENCE_STATES"
FAILURE_DECISION: Final = "RD38_CROSS_SECTIONAL_RESILIENCE_ALPHA_UNQUALIFIED_NEXT_SOURCE_REQUIRED"
FAILURE_NEXT: Final = "RD39_PREREGISTER_NEXT_SPOT_ONLY_ADAPTIVE_EXIT_INFORMATION_SOURCE"


class RD38P2Error(RuntimeError):
    """Frozen RD38-P2 contract violation."""


def utc(value: Any) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        return timestamp.tz_localize("UTC")
    return timestamp.tz_convert("UTC")


def validate_constants() -> None:
    if UNIVERSES != ("C2", "D2", "E2"):
        raise RD38P2Error("universe registry drifted")
    if HORIZONS != (6, 24, 72) or PRIMARY_HORIZON != 24:
        raise RD38P2Error("horizon registry drifted")
    if CROSS_SECTION_SIZE != 6:
        raise RD38P2Error("cross-section cardinality drifted")
    if FAMILY_ORDER != (
        PERSISTENT_WEAKNESS,
        LEADERSHIP_BREAKDOWN,
        BREADTH_LAGGARD,
        RECLAIM_CONTROL,
    ):
        raise RD38P2Error("family registry drifted")
    if PRIMARY_FAMILIES != (
        PERSISTENT_WEAKNESS,
        LEADERSHIP_BREAKDOWN,
        BREADTH_LAGGARD,
    ):
        raise RD38P2Error("primary family registry drifted")
    if not math.isclose(LOW_QUARTILE, 0.25):
        raise RD38P2Error("low-quartile threshold drifted")
    if not math.isclose(HIGH_QUARTILE, 0.75):
        raise RD38P2Error("high-quartile threshold drifted")
    if not math.isclose(
        NEGATIVE_BREADTH_THRESHOLD,
        0.6666666666666666,
    ):
        raise RD38P2Error("breadth threshold drifted")
    if (
        MIN_EVENTS != 30
        or MIN_PAIRS != 10
        or MIN_SIGNAL_DAYS != 20
        or MIN_QUALIFIED_UNIVERSES_PER_PERIOD != 2
    ):
        raise RD38P2Error("qualification support contract drifted")


def period_for(value: Any) -> str:
    timestamp = utc(value)
    for period_id, (start, end) in PERIODS.items():
        if start <= timestamp < end:
            return period_id
    raise RD38P2Error(f"timestamp outside frozen diagnostic periods: {timestamp}")


def average_percentile(values: list[float], target: float) -> float:
    array = np.asarray(values, dtype=float)
    if len(array) != CROSS_SECTION_SIZE:
        raise RD38P2Error(f"rank denominator must be six, got {len(array)}")
    if not np.isfinite(array).all() or not math.isfinite(target):
        raise RD38P2Error("non-finite percentile input")
    less = float(np.sum(array < target))
    equal = float(np.sum(array == target))
    return (less + 0.5 * equal) / float(len(array))


def normalize_price_frame(
    raw: pd.DataFrame,
    *,
    pair: str,
) -> pd.DataFrame:
    required = {"timestamp", "open", "close"}
    missing = sorted(required.difference(raw.columns))
    if missing:
        raise RD38P2Error(f"{pair} KuCoin frame missing columns: {missing}")

    frame = raw.loc[:, ["timestamp", "open", "close"]].copy()
    frame["timestamp"] = pd.to_datetime(
        frame["timestamp"],
        utc=True,
        errors="raise",
    ).dt.as_unit("ns")
    for column in ("open", "close"):
        frame[column] = pd.to_numeric(
            frame[column],
            errors="raise",
        ).astype(float)

    frame = frame.sort_values(
        "timestamp",
        kind="stable",
    ).reset_index(drop=True)
    if frame["timestamp"].duplicated().any():
        raise RD38P2Error(f"duplicate KuCoin timestamp: {pair}")
    if len(frame) and frame["timestamp"].max() >= DATA_CUTOFF:
        raise RD38P2Error(f"2024+ KuCoin bar entered P2: {pair}")
    if len(frame) and frame["timestamp"].min() < SOURCE_HISTORY_START:
        raise RD38P2Error(f"pre-frozen source history entered P2: {pair}")
    values = frame[["open", "close"]].to_numpy(dtype=float)
    if not np.isfinite(values).all():
        raise RD38P2Error(f"non-finite KuCoin price: {pair}")
    if bool((values <= 0.0).any()):
        raise RD38P2Error(f"non-positive KuCoin price: {pair}")
    return frame


def price_lookup(
    frame: pd.DataFrame,
) -> dict[int, tuple[float, float]]:
    return {
        int(timestamp): (float(open_price), float(close_price))
        for timestamp, open_price, close_price in zip(
            frame["timestamp"].astype("int64").tolist(),
            frame["open"].tolist(),
            frame["close"].tolist(),
            strict=True,
        )
    }


def trailing_return(
    lookup: Mapping[int, tuple[float, float]],
    *,
    decision_time: Any,
    horizon_hours: int,
) -> float | None:
    if horizon_hours not in HORIZONS:
        raise RD38P2Error(f"unexpected feature horizon: {horizon_hours}")
    decision = utc(decision_time)
    latest_close_bar = decision - pd.Timedelta(hours=1)
    baseline_close_bar = latest_close_bar - pd.Timedelta(hours=horizon_hours)
    latest = lookup.get(int(latest_close_bar.as_unit("ns").value))
    baseline = lookup.get(int(baseline_close_bar.as_unit("ns").value))
    if latest is None or baseline is None:
        return None
    latest_close = float(latest[1])
    baseline_close = float(baseline[1])
    if latest_close <= 0.0 or baseline_close <= 0.0:
        raise RD38P2Error("invalid close in trailing return")
    return float(latest_close / baseline_close - 1.0)


def snapshot_state_rows(
    *,
    universe_id: str,
    decision_time: Any,
    members: tuple[tuple[str, int], ...],
    lookups: Mapping[str, Mapping[int, tuple[float, float]]],
) -> list[dict[str, Any]] | None:
    if universe_id not in UNIVERSES:
        raise RD38P2Error(f"unexpected universe: {universe_id}")
    if len(members) != CROSS_SECTION_SIZE:
        raise RD38P2Error(f"{universe_id} snapshot does not have six members")
    if len({pair for pair, _rank in members}) != CROSS_SECTION_SIZE:
        raise RD38P2Error(f"{universe_id} snapshot has duplicate pairs")

    decision = utc(decision_time)
    if not DATA_START <= decision < DATA_CUTOFF:
        raise RD38P2Error(f"decision outside frozen periods: {decision}")

    return_maps: dict[str, dict[int, float]] = {}
    for pair, _membership_rank in members:
        lookup = lookups.get(pair)
        if lookup is None:
            return None
        values: dict[int, float] = {}
        for horizon in HORIZONS:
            value = trailing_return(
                lookup,
                decision_time=decision,
                horizon_hours=horizon,
            )
            if value is None or not math.isfinite(value):
                return None
            values[horizon] = float(value)
        return_maps[pair] = values

    ranks: dict[int, dict[str, float]] = {}
    for horizon in HORIZONS:
        values = [return_maps[pair][horizon] for pair, _rank in members]
        ranks[horizon] = {
            pair: average_percentile(
                values,
                return_maps[pair][horizon],
            )
            for pair, _rank in members
        }

    negative_breadth_24h = float(
        sum(return_maps[pair][24] < 0.0 for pair, _rank in members) / CROSS_SECTION_SIZE
    )

    rows: list[dict[str, Any]] = []
    for pair, membership_rank in members:
        r6 = return_maps[pair][6]
        r24 = return_maps[pair][24]
        r72 = return_maps[pair][72]
        rank6 = ranks[6][pair]
        rank24 = ranks[24][pair]
        rank72 = ranks[72][pair]

        persistent = r24 < 0.0 and rank24 <= LOW_QUARTILE and rank72 <= LOW_QUARTILE
        breakdown = rank72 >= HIGH_QUARTILE and rank6 <= LOW_QUARTILE and r6 < 0.0
        laggard = (
            negative_breadth_24h >= NEGATIVE_BREADTH_THRESHOLD
            and r24 < 0.0
            and rank24 <= LOW_QUARTILE
        )
        reclaim = rank24 <= LOW_QUARTILE and rank6 >= HIGH_QUARTILE and r6 > 0.0

        rows.append(
            {
                "universe_id": universe_id,
                "decision_time": decision,
                "period_id": period_for(decision),
                "pair": pair,
                "membership_rank": int(membership_rank),
                "return_6h": r6,
                "return_24h": r24,
                "return_72h": r72,
                "percentile_rank_6h": rank6,
                "percentile_rank_24h": rank24,
                "percentile_rank_72h": rank72,
                "negative_breadth_24h": negative_breadth_24h,
                "leadership_collapse_score": rank6 - rank72,
                PERSISTENT_WEAKNESS: bool(persistent),
                LEADERSHIP_BREAKDOWN: bool(breakdown),
                BREADTH_LAGGARD: bool(laggard),
                RECLAIM_CONTROL: bool(reclaim),
            }
        )
    return rows


def events_from_state_rows(
    state_rows: list[dict[str, Any]],
) -> pd.DataFrame:
    previous: dict[
        tuple[str, str, str],
        tuple[pd.Timestamp, bool],
    ] = {}
    records: list[dict[str, Any]] = []

    sorted_rows = sorted(
        state_rows,
        key=lambda row: (
            utc(row["decision_time"]),
            str(row["universe_id"]),
            str(row["pair"]),
        ),
    )
    context_fields = (
        "membership_rank",
        "return_6h",
        "return_24h",
        "return_72h",
        "percentile_rank_6h",
        "percentile_rank_24h",
        "percentile_rank_72h",
        "negative_breadth_24h",
        "leadership_collapse_score",
    )

    for row in sorted_rows:
        universe = str(row["universe_id"])
        pair = str(row["pair"])
        decision_time = utc(row["decision_time"])
        expected_previous_time = decision_time - pd.Timedelta(hours=1)

        for family in FAMILY_ORDER:
            key = (universe, pair, family)
            current = bool(row[family])
            prior_observation = previous.get(key)

            prior_is_consecutive_false = (
                prior_observation is not None
                and prior_observation[0] == expected_previous_time
                and prior_observation[1] is False
            )
            if prior_is_consecutive_false and current:
                record: dict[str, Any] = {
                    "family_id": family,
                    "universe_id": universe,
                    "period_id": str(row["period_id"]),
                    "pair": pair,
                    "decision_time": decision_time,
                }
                for field in context_fields:
                    record[field] = row[field]
                records.append(record)

            previous[key] = (decision_time, current)

    columns = [
        "family_id",
        "universe_id",
        "period_id",
        "pair",
        "decision_time",
        *context_fields,
    ]
    result = pd.DataFrame.from_records(
        records,
        columns=columns,
    )
    if not result.empty:
        order = {family: index for index, family in enumerate(FAMILY_ORDER)}
        result["_family_order"] = result["family_id"].map(order)
        result = (
            result.sort_values(
                [
                    "decision_time",
                    "universe_id",
                    "pair",
                    "_family_order",
                ],
                kind="stable",
            )
            .drop(columns="_family_order")
            .reset_index(drop=True)
        )
        result["event_id"] = np.arange(
            len(result),
            dtype=np.int64,
        )
    else:
        result["event_id"] = pd.Series(dtype="int64")
    return result


def target_markout(
    lookup: Mapping[int, tuple[float, float]],
    *,
    decision_time: Any,
    horizon_hours: int,
) -> dict[str, Any] | None:
    if horizon_hours not in HORIZONS:
        raise RD38P2Error(f"unexpected target horizon: {horizon_hours}")
    decision = utc(decision_time)
    exit_time = decision + pd.Timedelta(hours=horizon_hours)
    if exit_time >= DATA_CUTOFF:
        return None

    entry = lookup.get(int(decision.as_unit("ns").value))
    exit_row = lookup.get(int(exit_time.as_unit("ns").value))
    if entry is None or exit_row is None:
        return None

    entry_open = float(entry[0])
    exit_open = float(exit_row[0])
    if entry_open <= 0.0 or exit_open <= 0.0:
        raise RD38P2Error("invalid target open")
    return {
        "entry_time": decision,
        "exit_time": exit_time,
        "entry_open": entry_open,
        "exit_open": exit_open,
        "forward_return": float(exit_open / entry_open - 1.0),
    }


def build_markout_ledger(
    events: pd.DataFrame,
    lookups: Mapping[str, Mapping[int, tuple[float, float]]],
) -> pd.DataFrame:
    records: list[dict[str, Any]] = []

    for event in events.to_dict(orient="records"):
        pair = str(event["pair"])
        lookup = lookups.get(pair)
        if lookup is None:
            raise RD38P2Error(f"target lookup missing for event pair: {pair}")
        for horizon in HORIZONS:
            markout = target_markout(
                lookup,
                decision_time=event["decision_time"],
                horizon_hours=horizon,
            )
            if markout is None:
                continue
            records.append(
                {
                    "event_id": int(event["event_id"]),
                    "family_id": str(event["family_id"]),
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
    result = pd.DataFrame.from_records(
        records,
        columns=columns,
    )
    if not result.empty:
        result = result.sort_values(
            [
                "decision_time",
                "family_id",
                "universe_id",
                "pair",
                "horizon_hours",
            ],
            kind="stable",
        ).reset_index(drop=True)
    return result


def lopo_worst_mean(
    frame: pd.DataFrame,
    *,
    direction: str,
) -> float:
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
    raise RD38P2Error(f"unexpected LOPO direction: {direction}")


def summarize_markouts(
    markouts: pd.DataFrame,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []

    for family in FAMILY_ORDER:
        direction = "NEGATIVE" if family in PRIMARY_FAMILIES else "POSITIVE"
        for universe in UNIVERSES:
            for period_id in PERIODS:
                for horizon in HORIZONS:
                    cell = markouts.loc[
                        (markouts["family_id"] == family)
                        & (markouts["universe_id"] == universe)
                        & (markouts["period_id"] == period_id)
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
                            "period_id": period_id,
                            "horizon_hours": horizon,
                            "event_count": int(cell["event_id"].nunique()),
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
                            "lopo_worst_directional_mean": (
                                lopo_worst_mean(
                                    cell,
                                    direction=direction,
                                )
                            ),
                        }
                    )
    return pd.DataFrame.from_records(rows)


def qualification_tables(
    summary: pd.DataFrame,
) -> tuple[
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
]:
    negative_rows: list[dict[str, Any]] = []

    for family in PRIMARY_FAMILIES:
        for universe in UNIVERSES:
            for period_id in PERIODS:
                cell = summary.loc[
                    (summary["family_id"] == family)
                    & (summary["universe_id"] == universe)
                    & (summary["period_id"] == period_id)
                    & (summary["horizon_hours"] == PRIMARY_HORIZON)
                ]
                if len(cell) != 1:
                    raise RD38P2Error("expected one primary summary cell")
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
                directional = (
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
                        "period_id": period_id,
                        "event_count_24h": event_count,
                        "pair_count_24h": pair_count,
                        "signal_day_count_24h": (signal_days),
                        "mean_24h": mean_value,
                        "median_24h": median_value,
                        "lopo_worst_mean_24h": lopo_value,
                        "support_pass": bool(support),
                        "direction_pass": bool(directional),
                        "cell_qualified": bool(support and directional),
                    }
                )

    negative = pd.DataFrame.from_records(negative_rows)
    family_rows: list[dict[str, Any]] = []
    for family in PRIMARY_FAMILIES:
        subset = negative.loc[negative["family_id"] == family]
        counts = {
            period_id: int(
                subset.loc[
                    subset["period_id"] == period_id,
                    "cell_qualified",
                ].sum()
            )
            for period_id in PERIODS
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
        for period_id in PERIODS:
            cell = summary.loc[
                (summary["family_id"] == RECLAIM_CONTROL)
                & (summary["universe_id"] == universe)
                & (summary["period_id"] == period_id)
                & (summary["horizon_hours"] == PRIMARY_HORIZON)
            ]
            if len(cell) != 1:
                raise RD38P2Error("expected one positive-control cell")
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
                    "period_id": period_id,
                    "event_count_24h": event_count,
                    "pair_count_24h": pair_count,
                    "signal_day_count_24h": (signal_days),
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
