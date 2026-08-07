"""RD23 multi-family raw predictive edge tournament.

Six independent long-only setup families are evaluated on completed 1h bars using
the existing point-in-time effective universe. This module generates signals and
forward-return diagnostics only. It contains no portfolio sizing, stops, capital
routing, or adaptive exits.
"""

from __future__ import annotations

import math
from typing import Any, Final

import numpy as np
import pandas as pd

from spotbot.research.rd20_p2_minimal_pullback import MembershipSnapshot, fast_lookup

SCHEMA_VERSION: Final = "rd23-multifamily-raw-edge-engine-v1"
STAGE: Final = "RD23_P2_MULTIFAMILY_RAW_EDGE_TOURNAMENT"
DATA_START: Final = pd.Timestamp("2019-01-01T00:00:00Z")
REPLICATION_START: Final = pd.Timestamp("2021-01-01T00:00:00Z")
DATA_CUTOFF: Final = pd.Timestamp("2022-01-01T00:00:00Z")
FORWARD_HORIZONS: Final = (24, 72, 168)
COST_MULTIPLIERS: Final = (1.0, 2.0)
BASE_ROUND_TRIP_COST: Final = 0.0025
MINIMUM_EVENTS_PER_CELL: Final = 75
MINIMUM_PAIRS_PER_CELL: Final = 3
MINIMUM_SIGNAL_DAYS_PER_CELL: Final = 30
TRIM_FRACTION: Final = 0.01
MINIMUM_BREAK_EVEN_COST_MULTIPLIER: Final = 2.0

FAMILY_MOMENTUM_BREAKOUT: Final = "MOMENTUM_BREAKOUT"
FAMILY_VOLATILITY_EXPANSION: Final = "VOLATILITY_EXPANSION"
FAMILY_STRUCTURAL_REVERSAL: Final = "STRUCTURAL_REVERSAL"
FAMILY_RELATIVE_STRENGTH_ROTATION: Final = "RELATIVE_STRENGTH_ROTATION"
FAMILY_MOMENTUM_ACCELERATION: Final = "MOMENTUM_ACCELERATION"
FAMILY_BASE_RANGE_BREAKOUT: Final = "BASE_RANGE_BREAKOUT"

FAMILIES: Final = (
    FAMILY_MOMENTUM_BREAKOUT,
    FAMILY_VOLATILITY_EXPANSION,
    FAMILY_STRUCTURAL_REVERSAL,
    FAMILY_RELATIVE_STRENGTH_ROTATION,
    FAMILY_MOMENTUM_ACCELERATION,
    FAMILY_BASE_RANGE_BREAKOUT,
)

PERIODS: Final = {
    "DISCOVERY_2019_2020": (
        pd.Timestamp("2019-01-01T00:00:00Z"),
        pd.Timestamp("2021-01-01T00:00:00Z"),
    ),
    "TEMPORAL_REPLICATION_2021": (
        pd.Timestamp("2021-01-01T00:00:00Z"),
        pd.Timestamp("2022-01-01T00:00:00Z"),
    ),
}


class RD23Error(RuntimeError):
    """Raised when the RD23 frozen raw-edge contract is violated."""


def validate_constants() -> None:
    if FORWARD_HORIZONS != (24, 72, 168):
        raise RD23Error("forward horizon matrix drifted")
    if COST_MULTIPLIERS != (1.0, 2.0):
        raise RD23Error("cost matrix drifted")
    if not math.isclose(BASE_ROUND_TRIP_COST, 0.0025):
        raise RD23Error("base round-trip cost drifted")
    if tuple(FAMILIES) != (
        FAMILY_MOMENTUM_BREAKOUT,
        FAMILY_VOLATILITY_EXPANSION,
        FAMILY_STRUCTURAL_REVERSAL,
        FAMILY_RELATIVE_STRENGTH_ROTATION,
        FAMILY_MOMENTUM_ACCELERATION,
        FAMILY_BASE_RANGE_BREAKOUT,
    ):
        raise RD23Error("family registry drifted")


def period_for(timestamp: pd.Timestamp) -> str:
    for name, (start, end) in PERIODS.items():
        if start <= timestamp < end:
            return name
    raise RD23Error(f"timestamp outside RD23 periods: {timestamp}")


def normalize_bars(raw: pd.DataFrame) -> pd.DataFrame:
    required = {"timestamp", "open", "high", "low", "close", "volume"}
    missing = sorted(required.difference(raw.columns))
    if missing:
        raise RD23Error(f"raw bars missing columns: {missing}")
    frame = raw.loc[:, sorted(required)].copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, errors="raise")
    for column in ("open", "high", "low", "close", "volume"):
        frame[column] = pd.to_numeric(frame[column], errors="raise").astype(float)
    frame = (
        frame.sort_values("timestamp", kind="stable")
        .drop_duplicates("timestamp", keep="last")
        .reset_index(drop=True)
    )
    if len(frame) and frame["timestamp"].max() >= DATA_CUTOFF:
        raise RD23Error("2022 or later bar entered RD23 memory")
    if bool((frame[["open", "high", "low", "close"]] <= 0.0).any().any()):
        raise RD23Error("non-positive OHLC value entered RD23")
    if bool((frame["volume"] < 0.0).any()):
        raise RD23Error("negative volume entered RD23")
    return frame


def prepare_features(raw: pd.DataFrame) -> pd.DataFrame:
    """Build causal 1h features shared by the six setup families."""
    frame = normalize_bars(raw)
    close = frame["close"]
    high = frame["high"]
    low = frame["low"]
    open_ = frame["open"]
    prior_close = close.shift(1)

    true_range = pd.concat(
        [
            high - low,
            (high - prior_close).abs(),
            (low - prior_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr24_prior = true_range.shift(1).rolling(24, min_periods=24).mean()

    frame["prior_close"] = prior_close
    frame["atr24_prior"] = atr24_prior
    frame["return_6h"] = close / close.shift(6) - 1.0
    frame["previous_6h_return"] = close.shift(6) / close.shift(12) - 1.0
    frame["return_24h"] = close / close.shift(24) - 1.0
    frame["return_72h"] = close / close.shift(72) - 1.0

    frame["prior_24h_low"] = low.shift(1).rolling(24, min_periods=24).min()
    frame["prior_24h_high"] = high.shift(1).rolling(24, min_periods=24).max()
    frame["prior_48h_low"] = low.shift(1).rolling(48, min_periods=48).min()
    frame["prior_48h_high"] = high.shift(1).rolling(48, min_periods=48).max()
    frame["previous_prior_48h_high"] = frame["prior_48h_high"].shift(1)
    frame["prior_72h_high"] = high.shift(1).rolling(72, min_periods=72).max()
    frame["previous_prior_72h_high"] = frame["prior_72h_high"].shift(1)

    frame["true_range"] = true_range
    frame["volatility_expansion_ratio"] = true_range / atr24_prior
    bar_range = high - low
    frame["close_location"] = np.where(
        bar_range > 0.0,
        (close - low) / bar_range,
        0.5,
    )
    frame["base_width_atr"] = (frame["prior_48h_high"] - frame["prior_48h_low"]) / atr24_prior

    frame["momentum_breakout"] = (close > frame["prior_72h_high"]) & (
        prior_close <= frame["previous_prior_72h_high"]
    )

    vol_condition = (
        (frame["volatility_expansion_ratio"] >= 2.0)
        & (close > open_)
        & (frame["close_location"] >= 0.75)
    )
    frame["volatility_expansion"] = vol_condition & ~vol_condition.shift(1, fill_value=False)

    frame["structural_reversal"] = (
        (frame["return_72h"] < 0.0)
        & (low < frame["prior_24h_low"])
        & (close > frame["prior_24h_low"])
        & (close > open_)
    )

    acceleration_condition = (
        (frame["return_24h"] > 0.0)
        & (frame["previous_6h_return"] > 0.0)
        & (frame["return_6h"] >= 1.5 * frame["previous_6h_return"])
    )
    frame["momentum_acceleration"] = acceleration_condition & ~acceleration_condition.shift(
        1, fill_value=False
    )

    frame["base_range_breakout"] = (
        (frame["base_width_atr"] <= 5.0)
        & (close > frame["prior_48h_high"])
        & (prior_close <= frame["previous_prior_48h_high"])
    )

    required_features = [
        "prior_close",
        "atr24_prior",
        "return_6h",
        "previous_6h_return",
        "return_24h",
        "return_72h",
        "prior_24h_low",
        "prior_48h_low",
        "prior_48h_high",
        "previous_prior_48h_high",
        "prior_72h_high",
        "previous_prior_72h_high",
        "volatility_expansion_ratio",
        "close_location",
        "base_width_atr",
    ]
    frame["feature_ready"] = frame[required_features].notna().all(axis=1) & (
        frame["atr24_prior"] > 0.0
    )
    return frame


def _row_at(
    pair: str,
    timestamp: pd.Timestamp,
    features: dict[str, pd.DataFrame],
    lookups: dict[str, dict[int, int]],
) -> pd.Series | None:
    frame = features.get(pair)
    index = lookups.get(pair, {}).get(int(timestamp.value))
    if frame is None or index is None:
        return None
    return frame.iloc[index]


def _relative_strength_event(
    *,
    timestamp: pd.Timestamp,
    members: tuple[tuple[str, int], ...],
    features: dict[str, pd.DataFrame],
    lookups: dict[str, dict[int, int]],
) -> dict[str, Any] | None:
    now: list[tuple[float, int, str]] = []
    previous: list[tuple[float, int, str]] = []
    previous_time = timestamp - pd.Timedelta(hours=1)

    for pair, membership_rank in members:
        current_row = _row_at(pair, timestamp, features, lookups)
        previous_row = _row_at(pair, previous_time, features, lookups)
        if current_row is not None and bool(current_row["feature_ready"]):
            now.append((float(current_row["return_72h"]), membership_rank, pair))
        if previous_row is not None and bool(previous_row["feature_ready"]):
            previous.append((float(previous_row["return_72h"]), membership_rank, pair))

    if len(now) < 2 or len(previous) < 2:
        return None
    now.sort(key=lambda item: (-item[0], item[1], item[2]))
    previous.sort(key=lambda item: (-item[0], item[1], item[2]))
    current_return, membership_rank, current_pair = now[0]
    previous_pair = previous[0][2]
    if current_return <= 0.0 or current_pair == previous_pair:
        return None
    second_return = now[1][0]
    row = _row_at(current_pair, timestamp, features, lookups)
    if row is None:
        return None
    return {
        "family_id": FAMILY_RELATIVE_STRENGTH_ROTATION,
        "pair": current_pair,
        "membership_rank": int(membership_rank),
        "signal_strength": float(current_return - second_return),
        "decision_close": float(row["close"]),
        "return_72h": float(current_return),
        "aux_value": float(second_return),
    }


def evaluate_hour(
    *,
    timestamp: pd.Timestamp,
    members: tuple[tuple[str, int], ...],
    features: dict[str, pd.DataFrame],
    lookups: dict[str, dict[int, int]],
    allow_relative_strength: bool,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    events: list[dict[str, Any]] = []
    counters = {
        "asset_checks": len(members),
        "feature_ready_pass": 0,
        **{f"events_{family}": 0 for family in FAMILIES},
    }

    for pair, membership_rank in members:
        row = _row_at(pair, timestamp, features, lookups)
        if row is None or not bool(row["feature_ready"]):
            continue
        counters["feature_ready_pass"] += 1
        common = {
            "pair": pair,
            "membership_rank": int(membership_rank),
            "decision_close": float(row["close"]),
            "return_72h": float(row["return_72h"]),
        }

        family_rows: list[dict[str, Any]] = []
        if bool(row["momentum_breakout"]):
            family_rows.append(
                {
                    **common,
                    "family_id": FAMILY_MOMENTUM_BREAKOUT,
                    "signal_strength": float(
                        (row["close"] - row["prior_72h_high"]) / row["atr24_prior"]
                    ),
                    "aux_value": float(row["prior_72h_high"]),
                }
            )
        if bool(row["volatility_expansion"]):
            family_rows.append(
                {
                    **common,
                    "family_id": FAMILY_VOLATILITY_EXPANSION,
                    "signal_strength": float(row["volatility_expansion_ratio"]),
                    "aux_value": float(row["close_location"]),
                }
            )
        if bool(row["structural_reversal"]):
            family_rows.append(
                {
                    **common,
                    "family_id": FAMILY_STRUCTURAL_REVERSAL,
                    "signal_strength": float(
                        (row["close"] - row["prior_24h_low"]) / row["atr24_prior"]
                    ),
                    "aux_value": float(row["prior_24h_low"]),
                }
            )
        if bool(row["momentum_acceleration"]):
            family_rows.append(
                {
                    **common,
                    "family_id": FAMILY_MOMENTUM_ACCELERATION,
                    "signal_strength": float(row["return_6h"] - 1.5 * row["previous_6h_return"]),
                    "aux_value": float(row["previous_6h_return"]),
                }
            )
        if bool(row["base_range_breakout"]):
            family_rows.append(
                {
                    **common,
                    "family_id": FAMILY_BASE_RANGE_BREAKOUT,
                    "signal_strength": float(
                        (row["close"] - row["prior_48h_high"]) / row["atr24_prior"]
                    ),
                    "aux_value": float(row["base_width_atr"]),
                }
            )

        for family_row in family_rows:
            family = str(family_row["family_id"])
            counters[f"events_{family}"] += 1
            events.append(family_row)

    relative = None
    if allow_relative_strength:
        relative = _relative_strength_event(
            timestamp=timestamp,
            members=members,
            features=features,
            lookups=lookups,
        )
    if relative is not None:
        counters[f"events_{FAMILY_RELATIVE_STRENGTH_ROTATION}"] += 1
        events.append(relative)

    events.sort(
        key=lambda row: (
            str(row["family_id"]),
            -float(row["signal_strength"]),
            int(row["membership_rank"]),
            str(row["pair"]),
        )
    )
    return events, counters


def scan_signals(
    *,
    membership: list[MembershipSnapshot],
    features: dict[str, pd.DataFrame],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    validate_constants()
    lookups = {pair: fast_lookup(frame) for pair, frame in features.items()}
    event_rows: list[dict[str, Any]] = []
    funnel: dict[tuple[str, str], dict[str, int]] = {}

    for snapshot in membership:
        start = max(snapshot.decision_time, DATA_START).ceil("h")
        end = min(snapshot.effective_end, DATA_CUTOFF)
        if start >= end:
            continue
        for timestamp in pd.date_range(start, end, freq="h", inclusive="left"):
            period = period_for(timestamp)
            period_end = PERIODS[period][1]
            key = (snapshot.universe_id, period)
            counter = funnel.setdefault(
                key,
                {
                    "snapshot_hours": 0,
                    "asset_checks": 0,
                    "feature_ready_pass": 0,
                    **{f"events_{family}": 0 for family in FAMILIES},
                },
            )
            counter["snapshot_hours"] += 1
            if timestamp + pd.Timedelta(hours=max(FORWARD_HORIZONS)) >= period_end:
                continue
            hour_events, hour_counts = evaluate_hour(
                timestamp=timestamp,
                members=snapshot.members,
                features=features,
                lookups=lookups,
                allow_relative_strength=timestamp > start,
            )
            for name, value in hour_counts.items():
                counter[name] += int(value)
            ranks: dict[str, int] = {}
            for row in hour_events:
                family = str(row["family_id"])
                ranks[family] = ranks.get(family, 0) + 1
                event_rows.append(
                    {
                        "universe_id": snapshot.universe_id,
                        "period_id": period,
                        "timestamp": timestamp,
                        "candidate_rank": ranks[family],
                        **row,
                    }
                )

    funnel_rows: list[dict[str, Any]] = []
    for universe in ("C2", "D2", "E2"):
        for period in PERIODS:
            counts = funnel.get(
                (universe, period),
                {
                    "snapshot_hours": 0,
                    "asset_checks": 0,
                    "feature_ready_pass": 0,
                    **{f"events_{family}": 0 for family in FAMILIES},
                },
            )
            for family in FAMILIES:
                ready = int(counts["feature_ready_pass"])
                events = int(counts[f"events_{family}"])
                funnel_rows.append(
                    {
                        "universe_id": universe,
                        "period_id": period,
                        "family_id": family,
                        "snapshot_hours": int(counts["snapshot_hours"]),
                        "asset_checks": int(counts["asset_checks"]),
                        "feature_ready_pass": ready,
                        "candidate_events": events,
                        "candidate_survival_fraction_of_feature_ready": (
                            events / ready if ready else 0.0
                        ),
                    }
                )
    return pd.DataFrame.from_records(event_rows), pd.DataFrame.from_records(funnel_rows)


def _net_return_for_cost(
    *,
    entry_price: float,
    exit_price: float,
    cost_multiplier: float,
) -> tuple[float, float, float]:
    ratio = exit_price / entry_price
    gross = ratio - 1.0
    cost_drag = BASE_ROUND_TRIP_COST * cost_multiplier * (1.0 + ratio) / 2.0
    return gross, gross - cost_drag, cost_drag / cost_multiplier


def forward_event_rows(
    *,
    events: pd.DataFrame,
    features: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    lookups = {pair: fast_lookup(frame) for pair, frame in features.items()}
    rows: list[dict[str, Any]] = []
    for raw in events.to_dict(orient="records"):
        pair = str(raw["pair"])
        signal_time = pd.Timestamp(raw["timestamp"])
        frame = features[pair]
        lookup = lookups[pair]
        entry_time = signal_time + pd.Timedelta(hours=1)
        entry_index = lookup.get(int(entry_time.value))
        if entry_index is None:
            continue
        entry_price = float(frame.iloc[entry_index]["open"])
        if not math.isfinite(entry_price) or entry_price <= 0.0:
            continue
        for horizon in FORWARD_HORIZONS:
            exit_time = signal_time + pd.Timedelta(hours=horizon)
            if exit_time >= DATA_CUTOFF:
                continue
            exit_index = lookup.get(int(exit_time.value))
            if exit_index is None:
                continue
            exit_price = float(frame.iloc[exit_index]["close"])
            if not math.isfinite(exit_price) or exit_price <= 0.0:
                continue
            for multiplier in COST_MULTIPLIERS:
                gross, net, base_cost_weight = _net_return_for_cost(
                    entry_price=entry_price,
                    exit_price=exit_price,
                    cost_multiplier=multiplier,
                )
                rows.append(
                    {
                        "family_id": str(raw["family_id"]),
                        "universe_id": str(raw["universe_id"]),
                        "period_id": str(raw["period_id"]),
                        "pair": pair,
                        "signal_time": signal_time,
                        "entry_time": entry_time,
                        "exit_time": exit_time,
                        "horizon_hours": int(horizon),
                        "cost_multiplier": float(multiplier),
                        "gross_forward_return": gross,
                        "net_forward_return": net,
                        "base_cost_weight": base_cost_weight,
                    }
                )
    return pd.DataFrame.from_records(rows)


def _trimmed_mean(values: pd.Series) -> float:
    array = np.sort(pd.to_numeric(values, errors="raise").astype(float).to_numpy())
    if not len(array):
        return math.nan
    trim = int(math.floor(len(array) * TRIM_FRACTION))
    if trim > 0 and len(array) > 2 * trim:
        array = array[trim:-trim]
    return float(np.mean(array))


def _leave_one_pair_out_min_mean(group: pd.DataFrame) -> float:
    pairs = sorted(group["pair"].astype(str).unique())
    if len(pairs) < 2:
        return -math.inf
    values: list[float] = []
    for pair in pairs:
        remaining = group.loc[group["pair"].astype(str) != pair, "net_forward_return"]
        if remaining.empty:
            return -math.inf
        values.append(float(pd.to_numeric(remaining, errors="raise").mean()))
    return min(values)


def _break_even_cost_multiplier(group: pd.DataFrame) -> float:
    gross = float(pd.to_numeric(group["gross_forward_return"], errors="raise").mean())
    weight = float(pd.to_numeric(group["base_cost_weight"], errors="raise").mean())
    if not math.isfinite(gross) or not math.isfinite(weight) or weight <= 0.0:
        return 0.0
    return max(0.0, gross / weight)


def aggregate_raw_edge(rows: pd.DataFrame) -> pd.DataFrame:
    output: list[dict[str, Any]] = []
    grouped = rows.groupby(
        [
            "family_id",
            "universe_id",
            "period_id",
            "horizon_hours",
            "cost_multiplier",
        ],
        sort=True,
    )
    for keys, group in grouped:
        family, universe, period, horizon, multiplier = keys
        returns = pd.to_numeric(group["net_forward_return"], errors="raise").astype(float)
        pair_counts = group.groupby("pair", sort=True).size()
        largest_pair_share = float(pair_counts.max() / len(group)) if len(group) else math.nan
        output.append(
            {
                "family_id": str(family),
                "universe_id": str(universe),
                "period_id": str(period),
                "horizon_hours": int(horizon),
                "cost_multiplier": float(multiplier),
                "event_count": int(len(group)),
                "pair_count": int(group["pair"].astype(str).nunique()),
                "signal_day_count": int(
                    pd.to_datetime(group["signal_time"], utc=True).dt.floor("D").nunique()
                ),
                "mean_net_forward_return": float(returns.mean()),
                "median_net_forward_return": float(returns.median()),
                "trimmed_1pct_mean_net_forward_return": _trimmed_mean(returns),
                "positive_net_forward_share": float((returns > 0.0).mean()),
                "leave_one_pair_out_min_mean_net_return": _leave_one_pair_out_min_mean(group),
                "largest_pair_event_share": largest_pair_share,
                "pf1_break_even_cost_multiplier_raw_mean": _break_even_cost_multiplier(group),
            }
        )
    return pd.DataFrame.from_records(output)


def evaluate_family_horizons(
    metrics: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    gate_rows: list[dict[str, Any]] = []
    selection_rows: list[dict[str, Any]] = []
    metric_2x = metrics.loc[metrics["cost_multiplier"] == 2.0].copy()

    for family in FAMILIES:
        family_metrics = metric_2x.loc[metric_2x["family_id"] == family].copy()
        horizon_pass: dict[int, bool] = {}
        horizon_worst_trimmed: dict[int, float] = {}
        horizon_worst_break_even: dict[int, float] = {}
        for horizon in FORWARD_HORIZONS:
            selected = family_metrics.loc[family_metrics["horizon_hours"] == horizon]
            expected_cells = len(PERIODS) * 3
            if len(selected) != expected_cells:
                passed = False
                worst_trimmed = -math.inf
                worst_break_even = 0.0
            else:
                cell_pass = (
                    (selected["event_count"] >= MINIMUM_EVENTS_PER_CELL)
                    & (selected["pair_count"] >= MINIMUM_PAIRS_PER_CELL)
                    & (selected["signal_day_count"] >= MINIMUM_SIGNAL_DAYS_PER_CELL)
                    & (selected["mean_net_forward_return"] > 0.0)
                    & (selected["trimmed_1pct_mean_net_forward_return"] > 0.0)
                    & (selected["leave_one_pair_out_min_mean_net_return"] > 0.0)
                    & (
                        selected["pf1_break_even_cost_multiplier_raw_mean"]
                        >= MINIMUM_BREAK_EVEN_COST_MULTIPLIER
                    )
                )
                passed = bool(cell_pass.all())
                worst_trimmed = float(selected["trimmed_1pct_mean_net_forward_return"].min())
                worst_break_even = float(selected["pf1_break_even_cost_multiplier_raw_mean"].min())
                for row, row_pass in zip(
                    selected.to_dict(orient="records"),
                    cell_pass.tolist(),
                    strict=True,
                ):
                    gate_rows.append(
                        {
                            "family_id": family,
                            "horizon_hours": horizon,
                            "universe_id": str(row["universe_id"]),
                            "period_id": str(row["period_id"]),
                            "passed": bool(row_pass),
                            "event_count": int(row["event_count"]),
                            "pair_count": int(row["pair_count"]),
                            "signal_day_count": int(row["signal_day_count"]),
                            "mean_2x": float(row["mean_net_forward_return"]),
                            "trimmed_mean_2x": float(row["trimmed_1pct_mean_net_forward_return"]),
                            "lopo_min_mean_2x": float(
                                row["leave_one_pair_out_min_mean_net_return"]
                            ),
                            "break_even_cost_multiplier": float(
                                row["pf1_break_even_cost_multiplier_raw_mean"]
                            ),
                        }
                    )
            horizon_pass[horizon] = passed
            horizon_worst_trimmed[horizon] = worst_trimmed
            horizon_worst_break_even[horizon] = worst_break_even

        eligible = [horizon for horizon, passed in horizon_pass.items() if passed]
        if eligible:
            eligible.sort(
                key=lambda horizon: (
                    -horizon_worst_trimmed[horizon],
                    -horizon_worst_break_even[horizon],
                    horizon,
                )
            )
            selected_horizon: int | None = eligible[0]
        else:
            selected_horizon = None
        selection_rows.append(
            {
                "family_id": family,
                "raw_edge_confirmed": selected_horizon is not None,
                "selected_horizon_hours": selected_horizon,
                "h24_passed": bool(horizon_pass[24]),
                "h72_passed": bool(horizon_pass[72]),
                "h168_passed": bool(horizon_pass[168]),
                "best_worst_trimmed_2x": (
                    horizon_worst_trimmed[selected_horizon]
                    if selected_horizon is not None
                    else max(horizon_worst_trimmed.values())
                ),
                "best_worst_break_even_cost_multiplier": (
                    horizon_worst_break_even[selected_horizon]
                    if selected_horizon is not None
                    else max(horizon_worst_break_even.values())
                ),
            }
        )
    return pd.DataFrame.from_records(gate_rows), pd.DataFrame.from_records(selection_rows)


def family_overlap(events: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    if events.empty:
        return pd.DataFrame(), {
            "unique_event_keys": 0,
            "multi_family_event_keys": 0,
            "multi_family_event_key_share": 0.0,
        }
    frame = events.loc[:, ["family_id", "universe_id", "timestamp", "pair"]].copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, errors="raise")
    key_columns = ["universe_id", "timestamp", "pair"]
    family_keys = {
        family: set(
            map(
                tuple,
                frame.loc[frame["family_id"] == family, key_columns].itertuples(
                    index=False,
                    name=None,
                ),
            )
        )
        for family in FAMILIES
    }
    rows: list[dict[str, Any]] = []
    for family_a in FAMILIES:
        for family_b in FAMILIES:
            keys_a = family_keys[family_a]
            keys_b = family_keys[family_b]
            union = keys_a | keys_b
            intersection = keys_a & keys_b
            rows.append(
                {
                    "family_a": family_a,
                    "family_b": family_b,
                    "events_a": len(keys_a),
                    "events_b": len(keys_b),
                    "intersection": len(intersection),
                    "union": len(union),
                    "jaccard": len(intersection) / len(union) if union else 0.0,
                }
            )
    grouped = frame.groupby(key_columns, sort=False)["family_id"].nunique()
    multi = int((grouped > 1).sum())
    total = int(len(grouped))
    summary = {
        "unique_event_keys": total,
        "multi_family_event_keys": multi,
        "multi_family_event_key_share": multi / total if total else 0.0,
        "maximum_families_on_one_event_key": int(grouped.max()) if total else 0,
    }
    return pd.DataFrame.from_records(rows), summary
