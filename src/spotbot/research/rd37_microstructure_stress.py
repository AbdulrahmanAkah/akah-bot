"""Frozen RD37-P3 causal 1m-to-hour microstructure stress primitives."""

from __future__ import annotations

from typing import Final

import numpy as np
import pandas as pd

DATA_START: Final = pd.Timestamp("2022-01-01T00:00:00Z")
DATA_CUTOFF: Final = pd.Timestamp("2024-01-01T00:00:00Z")

BLACKOUT_START: Final = pd.Timestamp("2023-03-24T11:38:00Z")
BLACKOUT_END: Final = pd.Timestamp("2023-03-24T14:00:00Z")

SYMBOLS: Final = ("BTCUSDT", "ETHUSDT")
UNIVERSES: Final = ("C2", "D2", "E2")
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
HORIZONS: Final = (1, 6, 24)
PRIMARY_HORIZON: Final = 6
ROBUST_BASELINE_HOURS: Final = 168

FAMILY_DOWNSIDE: Final = "INTRAHOUR_DOWNSIDE_STRESS"
FAMILY_SELL_FLOW: Final = "SELL_FLOW_IMPULSE"
FAMILY_PARTICIPATION: Final = "PARTICIPATION_BURST"
FAMILY_FAILED_RECOVERY: Final = "FAILED_INTRAHOUR_RECOVERY"

FAMILY_ORDER: Final = (
    FAMILY_DOWNSIDE,
    FAMILY_SELL_FLOW,
    FAMILY_PARTICIPATION,
    FAMILY_FAILED_RECOVERY,
)
PRIMARY_FAMILIES: Final = (
    FAMILY_DOWNSIDE,
    FAMILY_SELL_FLOW,
    FAMILY_FAILED_RECOVERY,
)

MIN_EVENTS: Final = 30
MIN_PAIRS: Final = 10
MIN_SIGNAL_DAYS: Final = 20
MIN_QUALIFIED_UNIVERSES_PER_PERIOD: Final = 2


class RD37P3Error(RuntimeError):
    """Frozen RD37-P3 contract violation."""


def utc_timestamp(value: object) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        return timestamp.tz_localize("UTC")
    return timestamp.tz_convert("UTC")


def period_for_reference_time(value: object) -> str:
    timestamp = utc_timestamp(value)
    for period_id, (start, end) in PERIODS.items():
        if start <= timestamp < end:
            return period_id
    raise RD37P3Error(f"reference timestamp outside frozen periods: {timestamp}")


def validate_constants() -> None:
    if SYMBOLS != ("BTCUSDT", "ETHUSDT"):
        raise RD37P3Error("symbol registry drifted")
    if UNIVERSES != ("C2", "D2", "E2"):
        raise RD37P3Error("universe registry drifted")
    if HORIZONS != (1, 6, 24) or PRIMARY_HORIZON != 6:
        raise RD37P3Error("horizon registry drifted")
    if ROBUST_BASELINE_HOURS != 168:
        raise RD37P3Error("robust baseline drifted")
    if FAMILY_ORDER != (
        FAMILY_DOWNSIDE,
        FAMILY_SELL_FLOW,
        FAMILY_PARTICIPATION,
        FAMILY_FAILED_RECOVERY,
    ):
        raise RD37P3Error("family registry drifted")
    if PRIMARY_FAMILIES != (
        FAMILY_DOWNSIDE,
        FAMILY_SELL_FLOW,
        FAMILY_FAILED_RECOVERY,
    ):
        raise RD37P3Error("primary family registry drifted")
    if (
        MIN_EVENTS != 30
        or MIN_PAIRS != 10
        or MIN_SIGNAL_DAYS != 20
        or MIN_QUALIFIED_UNIVERSES_PER_PERIOD != 2
    ):
        raise RD37P3Error("support thresholds drifted")


def normalize_minutes(raw: pd.DataFrame, *, symbol: str) -> pd.DataFrame:
    required = {
        "timestamp",
        "open",
        "high",
        "low",
        "close",
        "quote_volume",
        "number_of_trades",
        "taker_buy_quote_volume",
    }
    missing = sorted(required.difference(raw.columns))
    if missing:
        raise RD37P3Error(f"{symbol} minute source missing: {missing}")
    if symbol not in SYMBOLS:
        raise RD37P3Error(f"unexpected symbol: {symbol}")

    frame = raw.loc[:, sorted(required)].copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, errors="raise").dt.as_unit(
        "ns"
    )
    numeric = [
        "open",
        "high",
        "low",
        "close",
        "quote_volume",
        "number_of_trades",
        "taker_buy_quote_volume",
    ]
    for column in numeric:
        frame[column] = pd.to_numeric(frame[column], errors="raise").astype(float)

    frame = frame.sort_values("timestamp", kind="stable").reset_index(drop=True)
    if frame["timestamp"].duplicated().any():
        raise RD37P3Error(f"duplicate minute timestamp: {symbol}")
    if len(frame) and frame["timestamp"].min() < DATA_START:
        raise RD37P3Error(f"pre-2022 minute entered P3: {symbol}")
    if len(frame) and frame["timestamp"].max() >= DATA_CUTOFF:
        raise RD37P3Error(f"2024+ minute entered P3: {symbol}")

    if bool((frame[["open", "high", "low", "close"]] <= 0.0).any().any()):
        raise RD37P3Error(f"non-positive OHLC: {symbol}")
    if bool(
        (
            frame[
                [
                    "quote_volume",
                    "number_of_trades",
                    "taker_buy_quote_volume",
                ]
            ]
            < 0.0
        )
        .any()
        .any()
    ):
        raise RD37P3Error(f"negative flow field: {symbol}")
    if not np.isfinite(frame[numeric].to_numpy(dtype=float)).all():
        raise RD37P3Error(f"non-finite minute field: {symbol}")

    return frame


def _is_blackout_minute(timestamp: pd.Series) -> pd.Series:
    return (timestamp >= BLACKOUT_START) & (timestamp < BLACKOUT_END)


def aggregate_completed_hours(
    raw: pd.DataFrame,
    *,
    symbol: str,
) -> pd.DataFrame:
    frame = normalize_minutes(raw, symbol=symbol)
    frame = frame.loc[~_is_blackout_minute(frame["timestamp"])].copy()
    frame["hour"] = frame["timestamp"].dt.floor("h")
    frame["minute_offset"] = frame["timestamp"].dt.minute

    records: list[dict[str, object]] = []
    expected_offsets = set(range(60))

    for hour, part in frame.groupby("hour", sort=True):
        if len(part) != 60:
            continue
        offsets = set(part["minute_offset"].astype(int).tolist())
        if offsets != expected_offsets:
            continue

        part = part.sort_values("timestamp", kind="stable")
        open_hour = float(part.iloc[0]["open"])
        close_hour = float(part.iloc[-1]["close"])
        hour_low = float(part["low"].min())

        minute_returns = np.log(
            part["close"].to_numpy(dtype=float) / part["open"].to_numpy(dtype=float)
        )
        squared = minute_returns**2
        rv_sq = float(squared.sum())
        rv = float(np.sqrt(rv_sq))
        downside_sq = float((np.minimum(minute_returns, 0.0) ** 2).sum())
        downside_share = downside_sq / rv_sq if rv_sq > 0.0 else np.nan

        max_drawdown = float(hour_low / open_hour - 1.0)
        if hour_low < open_hour:
            recovery = float(
                np.clip(
                    (close_hour - hour_low) / (open_hour - hour_low),
                    0.0,
                    1.0,
                )
            )
        else:
            recovery = np.nan

        quote_60 = float(part["quote_volume"].sum())
        trades_60 = float(part["number_of_trades"].sum())
        taker_60 = float(part["taker_buy_quote_volume"].sum())
        imbalance_60 = (
            float(np.clip(2.0 * taker_60 / quote_60 - 1.0, -1.0, 1.0)) if quote_60 > 0.0 else np.nan
        )

        last15 = part.iloc[-15:]
        quote_15 = float(last15["quote_volume"].sum())
        taker_15 = float(last15["taker_buy_quote_volume"].sum())
        imbalance_15 = (
            float(np.clip(2.0 * taker_15 / quote_15 - 1.0, -1.0, 1.0)) if quote_15 > 0.0 else np.nan
        )

        records.append(
            {
                "hour": utc_timestamp(hour),
                "hour_return": close_hour / open_hour - 1.0,
                "realized_volatility": rv,
                "downside_share": downside_share,
                "max_drawdown": max_drawdown,
                "recovery_fraction": recovery,
                "imbalance_60": imbalance_60,
                "imbalance_15": imbalance_15,
                "flow_accel": imbalance_15 - imbalance_60,
                "hour_quote_volume": quote_60,
                "hour_trade_count": trades_60,
            }
        )

    result = pd.DataFrame.from_records(records)
    if result.empty:
        raise RD37P3Error(f"no completed source hours: {symbol}")
    result = result.sort_values("hour", kind="stable").reset_index(drop=True)
    if result["hour"].duplicated().any():
        raise RD37P3Error(f"duplicate completed hour: {symbol}")
    return result


def _prior_robust_z(values: pd.Series, segment: pd.Series) -> pd.Series:
    result = pd.Series(np.nan, index=values.index, dtype=float)

    def mad_raw(window: np.ndarray) -> float:
        median = float(np.median(window))
        return float(np.median(np.abs(window - median)))

    for _, idx in segment.groupby(segment, sort=False).groups.items():
        indexes = list(idx)
        part = values.loc[indexes].astype(float)
        shifted = part.shift(1)
        median = shifted.rolling(
            ROBUST_BASELINE_HOURS,
            min_periods=ROBUST_BASELINE_HOURS,
        ).median()
        mad = shifted.rolling(
            ROBUST_BASELINE_HOURS,
            min_periods=ROBUST_BASELINE_HOURS,
        ).apply(mad_raw, raw=True)
        scale = 1.4826 * mad
        z = (part - median) / scale.where(scale > 0.0)
        result.loc[indexes] = z.replace([np.inf, -np.inf], np.nan).to_numpy()
    return result


def market_state_frame(
    btc_minutes: pd.DataFrame,
    eth_minutes: pd.DataFrame,
) -> pd.DataFrame:
    btc = aggregate_completed_hours(btc_minutes, symbol="BTCUSDT")
    eth = aggregate_completed_hours(eth_minutes, symbol="ETHUSDT")

    btc = btc.rename(
        columns={column: f"btc_{column}" for column in btc.columns if column != "hour"}
    )
    eth = eth.rename(
        columns={column: f"eth_{column}" for column in eth.columns if column != "hour"}
    )
    frame = btc.merge(
        eth,
        on="hour",
        how="inner",
        validate="one_to_one",
    ).sort_values("hour", kind="stable")
    frame = frame.reset_index(drop=True)

    diff = frame["hour"].diff()
    frame["segment_id"] = diff.ne(pd.Timedelta(hours=1)).cumsum().astype(int)

    for prefix in ("btc", "eth"):
        frame[f"{prefix}_realized_volatility_z"] = _prior_robust_z(
            np.log1p(frame[f"{prefix}_realized_volatility"]),
            frame["segment_id"],
        )
        frame[f"{prefix}_quote_volume_z"] = _prior_robust_z(
            np.log1p(frame[f"{prefix}_hour_quote_volume"]),
            frame["segment_id"],
        )
        frame[f"{prefix}_trade_count_z"] = _prior_robust_z(
            np.log1p(frame[f"{prefix}_hour_trade_count"]),
            frame["segment_id"],
        )
        frame[f"{prefix}_participation_z"] = 0.5 * (
            frame[f"{prefix}_quote_volume_z"] + frame[f"{prefix}_trade_count_z"]
        )

    def mean2(left: str, right: str) -> pd.Series:
        return 0.5 * (frame[left] + frame[right])

    frame["market_hour_return"] = mean2("btc_hour_return", "eth_hour_return")
    frame["market_realized_volatility_z"] = mean2(
        "btc_realized_volatility_z",
        "eth_realized_volatility_z",
    )
    frame["market_downside_share"] = mean2("btc_downside_share", "eth_downside_share")
    frame["market_max_drawdown"] = mean2("btc_max_drawdown", "eth_max_drawdown")
    frame["market_recovery_fraction"] = mean2(
        "btc_recovery_fraction",
        "eth_recovery_fraction",
    )
    frame["market_imbalance_60"] = mean2("btc_imbalance_60", "eth_imbalance_60")
    frame["market_imbalance_15"] = mean2("btc_imbalance_15", "eth_imbalance_15")
    frame["market_flow_acceleration"] = mean2("btc_flow_accel", "eth_flow_accel")
    frame["market_participation_z"] = mean2("btc_participation_z", "eth_participation_z")

    frame[f"{FAMILY_DOWNSIDE}_evaluable"] = (
        frame[
            [
                "market_hour_return",
                "market_downside_share",
                "market_realized_volatility_z",
            ]
        ]
        .notna()
        .all(axis=1)
    )
    frame[FAMILY_DOWNSIDE] = (
        frame[f"{FAMILY_DOWNSIDE}_evaluable"]
        & (frame["market_hour_return"] <= -0.003)
        & (frame["market_downside_share"] >= 0.60)
        & (frame["market_realized_volatility_z"] >= 1.00)
    )

    frame[f"{FAMILY_SELL_FLOW}_evaluable"] = (
        frame[["market_imbalance_15", "market_flow_acceleration"]].notna().all(axis=1)
    )
    frame[FAMILY_SELL_FLOW] = (
        frame[f"{FAMILY_SELL_FLOW}_evaluable"]
        & (frame["market_imbalance_15"] <= -0.08)
        & (frame["market_flow_acceleration"] <= -0.04)
    )

    frame[f"{FAMILY_PARTICIPATION}_evaluable"] = (
        frame[["market_participation_z"]].notna().all(axis=1)
    )
    frame[FAMILY_PARTICIPATION] = frame[f"{FAMILY_PARTICIPATION}_evaluable"] & (
        frame["market_participation_z"] >= 1.50
    )

    frame[f"{FAMILY_FAILED_RECOVERY}_evaluable"] = (
        frame[
            [
                "market_max_drawdown",
                "market_recovery_fraction",
                "market_imbalance_15",
            ]
        ]
        .notna()
        .all(axis=1)
    )
    frame[FAMILY_FAILED_RECOVERY] = (
        frame[f"{FAMILY_FAILED_RECOVERY}_evaluable"]
        & (frame["market_max_drawdown"] <= -0.004)
        & (frame["market_recovery_fraction"] <= 0.35)
        & (frame["market_imbalance_15"] <= -0.04)
    )

    return frame


def episode_ledger(market: pd.DataFrame) -> pd.DataFrame:
    records: list[dict[str, object]] = []

    context_columns = (
        "market_hour_return",
        "market_realized_volatility_z",
        "market_downside_share",
        "market_max_drawdown",
        "market_recovery_fraction",
        "market_imbalance_60",
        "market_imbalance_15",
        "market_flow_acceleration",
        "market_participation_z",
    )

    for family in PRIMARY_FAMILIES:
        active = market[family].fillna(False).astype(bool)
        evaluable = market[f"{family}_evaluable"].fillna(False).astype(bool)
        previous_active = active.shift(1, fill_value=False)
        previous_evaluable = evaluable.shift(1, fill_value=False)
        previous_segment = market["segment_id"].shift(1)
        same_segment = previous_segment.eq(market["segment_id"])
        entry = active & (~previous_active | ~previous_evaluable | ~same_segment)

        for index in market.index[entry]:
            source_hour = utc_timestamp(market.at[index, "hour"])
            reference_time = source_hour + pd.Timedelta(hours=1)
            if reference_time >= DATA_CUTOFF:
                continue
            record: dict[str, object] = {
                "family_id": family,
                "source_hour": source_hour,
                "reference_time": reference_time,
                "period_id": period_for_reference_time(reference_time),
                "participation_burst_active": bool(market.at[index, FAMILY_PARTICIPATION]),
            }
            for column in context_columns:
                value = market.at[index, column]
                record[column] = float(value) if pd.notna(value) else np.nan
            records.append(record)

    columns = [
        "family_id",
        "source_hour",
        "reference_time",
        "period_id",
        "participation_burst_active",
        *context_columns,
    ]
    result = pd.DataFrame.from_records(records, columns=columns)
    if not result.empty:
        order = {family: i for i, family in enumerate(PRIMARY_FAMILIES)}
        result["_order"] = result["family_id"].map(order)
        result = (
            result.sort_values(
                ["reference_time", "_order"],
                kind="stable",
            )
            .drop(columns="_order")
            .reset_index(drop=True)
        )
    return result


def family_evaluable_hours(
    market: pd.DataFrame,
    *,
    family: str,
) -> pd.DataFrame:
    if family not in PRIMARY_FAMILIES:
        raise RD37P3Error(f"not a primary family: {family}")
    subset = market.loc[
        market[f"{family}_evaluable"].fillna(False).astype(bool),
        ["hour"],
    ].copy()
    subset["reference_time"] = subset["hour"] + pd.Timedelta(hours=1)
    subset = subset.loc[subset["reference_time"] < DATA_CUTOFF].copy()
    subset["period_id"] = subset["reference_time"].map(period_for_reference_time)
    return subset.reset_index(drop=True)


def normalize_target_bars(
    raw: pd.DataFrame,
    *,
    pair: str,
) -> pd.DataFrame:
    required = {"timestamp", "open"}
    missing = sorted(required.difference(raw.columns))
    if missing:
        raise RD37P3Error(f"target source missing {pair}: {missing}")

    frame = raw.loc[:, ["timestamp", "open"]].copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, errors="raise").dt.as_unit(
        "ns"
    )
    frame["open"] = pd.to_numeric(frame["open"], errors="raise").astype(float)
    frame = frame.sort_values("timestamp", kind="stable").reset_index(drop=True)
    if frame["timestamp"].duplicated().any():
        raise RD37P3Error(f"duplicate KuCoin timestamp: {pair}")
    if len(frame) and frame["timestamp"].max() >= DATA_CUTOFF:
        raise RD37P3Error(f"2024+ target bar entered P3: {pair}")
    if bool((frame["open"] <= 0.0).any()):
        raise RD37P3Error(f"non-positive target open: {pair}")
    return frame


def target_open_lookup(frame: pd.DataFrame) -> dict[int, float]:
    timestamps = pd.to_datetime(frame["timestamp"], utc=True, errors="raise").dt.as_unit("ns")
    return {
        int(timestamp): float(price)
        for timestamp, price in zip(
            timestamps.astype("int64").to_numpy(),
            frame["open"].to_numpy(dtype=float),
            strict=True,
        )
    }


def target_markout(
    *,
    reference_time: object,
    horizon_hours: int,
    lookup: dict[int, float],
) -> dict[str, object] | None:
    if horizon_hours not in HORIZONS:
        raise RD37P3Error(f"unexpected horizon: {horizon_hours}")
    entry_time = utc_timestamp(reference_time)
    exit_time = entry_time + pd.Timedelta(hours=horizon_hours)
    if entry_time >= DATA_CUTOFF or exit_time >= DATA_CUTOFF:
        return None

    entry = lookup.get(int(entry_time.as_unit("ns").value))
    exit_price = lookup.get(int(exit_time.as_unit("ns").value))
    if entry is None or exit_price is None:
        return None
    if entry <= 0.0 or exit_price <= 0.0:
        raise RD37P3Error("invalid target price")
    return {
        "entry_time": entry_time,
        "exit_time": exit_time,
        "entry_price": float(entry),
        "exit_price": float(exit_price),
        "forward_return": float(exit_price / entry - 1.0),
    }


def lopo_worst_mean(frame: pd.DataFrame) -> float:
    if frame.empty:
        return float("nan")
    pairs = sorted(frame["pair"].astype(str).unique())
    if len(pairs) < 2:
        return float("nan")
    means: list[float] = []
    for pair in pairs:
        remaining = frame.loc[frame["pair"].astype(str) != pair]
        if not remaining.empty:
            means.append(float(remaining["forward_return"].mean()))
    return max(means) if means else float("nan")


def summarize_signal_markouts(
    markouts: pd.DataFrame,
    baseline_summary: pd.DataFrame,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []

    for family in PRIMARY_FAMILIES:
        for universe in UNIVERSES:
            for period_id in PERIODS:
                for horizon in HORIZONS:
                    cell = markouts.loc[
                        (markouts["family_id"] == family)
                        & (markouts["universe_id"] == universe)
                        & (markouts["period_id"] == period_id)
                        & (markouts["horizon_hours"] == horizon)
                    ]
                    returns = pd.to_numeric(cell["forward_return"], errors="coerce").dropna()

                    baseline_match = baseline_summary.loc[
                        (baseline_summary["family_id"] == family)
                        & (baseline_summary["universe_id"] == universe)
                        & (baseline_summary["period_id"] == period_id)
                        & (baseline_summary["horizon_hours"] == horizon)
                    ]
                    if len(baseline_match) != 1:
                        raise RD37P3Error(
                            "expected one baseline summary cell for "
                            f"{family}/{universe}/{period_id}/{horizon}"
                        )
                    baseline_mean = float(baseline_match.iloc[0]["baseline_mean_forward_return"])

                    signal_mean = float(returns.mean()) if len(returns) else np.nan
                    rows.append(
                        {
                            "family_id": family,
                            "universe_id": universe,
                            "period_id": period_id,
                            "horizon_hours": horizon,
                            "episode_event_count": int(
                                pd.to_datetime(
                                    cell["reference_time"],
                                    utc=True,
                                    errors="coerce",
                                ).nunique()
                            ),
                            "pair_count": int(cell["pair"].astype(str).nunique()),
                            "signal_day_count": int(
                                pd.to_datetime(
                                    cell["reference_time"],
                                    utc=True,
                                    errors="coerce",
                                )
                                .dt.floor("D")
                                .nunique()
                            ),
                            "markout_count": int(len(cell)),
                            "mean_forward_return": signal_mean,
                            "median_forward_return": (
                                float(returns.median()) if len(returns) else np.nan
                            ),
                            "positive_share": (
                                float((returns > 0.0).mean()) if len(returns) else np.nan
                            ),
                            "lopo_worst_mean_forward_return": (lopo_worst_mean(cell)),
                            "baseline_mean_forward_return": baseline_mean,
                            "signal_excess_return": (
                                signal_mean - baseline_mean
                                if np.isfinite(signal_mean) and np.isfinite(baseline_mean)
                                else np.nan
                            ),
                        }
                    )
    return pd.DataFrame.from_records(rows)


def participation_interaction_summary(
    markouts: pd.DataFrame,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    subset = markouts.loc[markouts["participation_burst_active"].fillna(False).astype(bool)]
    for family in PRIMARY_FAMILIES:
        for universe in UNIVERSES:
            for period_id in PERIODS:
                for horizon in HORIZONS:
                    cell = subset.loc[
                        (subset["family_id"] == family)
                        & (subset["universe_id"] == universe)
                        & (subset["period_id"] == period_id)
                        & (subset["horizon_hours"] == horizon)
                    ]
                    returns = pd.to_numeric(cell["forward_return"], errors="coerce").dropna()
                    rows.append(
                        {
                            "family_id": family,
                            "universe_id": universe,
                            "period_id": period_id,
                            "horizon_hours": horizon,
                            "episode_event_count": int(
                                pd.to_datetime(
                                    cell["reference_time"],
                                    utc=True,
                                    errors="coerce",
                                ).nunique()
                            ),
                            "pair_count": int(cell["pair"].astype(str).nunique()),
                            "markout_count": int(len(cell)),
                            "mean_forward_return": (
                                float(returns.mean()) if len(returns) else np.nan
                            ),
                            "median_forward_return": (
                                float(returns.median()) if len(returns) else np.nan
                            ),
                            "qualification_use": "DESCRIPTIVE_ONLY",
                            "may_rescue_primary_failure": False,
                        }
                    )
    return pd.DataFrame.from_records(rows)


def qualification_tables(
    summary: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    cells: list[dict[str, object]] = []

    for family in PRIMARY_FAMILIES:
        for universe in UNIVERSES:
            for period_id in PERIODS:
                match = summary.loc[
                    (summary["family_id"] == family)
                    & (summary["universe_id"] == universe)
                    & (summary["period_id"] == period_id)
                    & (summary["horizon_hours"] == PRIMARY_HORIZON)
                ]
                if len(match) != 1:
                    raise RD37P3Error(
                        f"expected one primary-horizon cell for {family}/{universe}/{period_id}"
                    )
                row = match.iloc[0]
                event_count = int(row["episode_event_count"])
                pair_count = int(row["pair_count"])
                signal_days = int(row["signal_day_count"])
                mean_value = float(row["mean_forward_return"])
                median_value = float(row["median_forward_return"])
                excess_value = float(row["signal_excess_return"])
                lopo_value = float(row["lopo_worst_mean_forward_return"])

                support = (
                    event_count >= MIN_EVENTS
                    and pair_count >= MIN_PAIRS
                    and signal_days >= MIN_SIGNAL_DAYS
                )
                directional = (
                    np.isfinite(mean_value)
                    and np.isfinite(median_value)
                    and np.isfinite(excess_value)
                    and np.isfinite(lopo_value)
                    and mean_value < 0.0
                    and median_value < 0.0
                    and excess_value < 0.0
                    and lopo_value < 0.0
                )
                cells.append(
                    {
                        "family_id": family,
                        "universe_id": universe,
                        "period_id": period_id,
                        "episode_event_count_6h": event_count,
                        "pair_count_6h": pair_count,
                        "signal_day_count_6h": signal_days,
                        "mean_6h": mean_value,
                        "median_6h": median_value,
                        "baseline_mean_6h": float(row["baseline_mean_forward_return"]),
                        "signal_excess_6h": excess_value,
                        "lopo_worst_mean_6h": lopo_value,
                        "support_pass": bool(support),
                        "direction_pass": bool(directional),
                        "cell_qualified": bool(support and directional),
                    }
                )

    cell_frame = pd.DataFrame.from_records(cells)
    family_rows: list[dict[str, object]] = []
    for family in PRIMARY_FAMILIES:
        subset = cell_frame.loc[cell_frame["family_id"] == family]
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
                "advances_to_shadow_ablation": bool(qualified),
                "parameter_search_used": False,
                "threshold_optimization_used": False,
                "winner_selection_used": False,
                "participation_context_used_for_qualification": False,
            }
        )

    return cell_frame, pd.DataFrame.from_records(family_rows)
