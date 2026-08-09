"""RD36 P3 frozen cross-venue Binance-flow state diagnostic engine.

Filesystem-free primitives only. Binance supplies lagged exogenous flow state.
KuCoin target prices/returns are handled by the frozen diagnostic runner.
No network, portfolio economics, production authorization, or 2024+ access.
"""

from __future__ import annotations

from typing import Final

import numpy as np
import pandas as pd

SCHEMA_VERSION: Final = "rd36-cross-venue-flow-state-engine-v1"

DATA_START: Final = pd.Timestamp("2022-01-01T00:00:00Z")
DATA_CUTOFF: Final = pd.Timestamp("2024-01-01T00:00:00Z")
KNOWN_GAP: Final = pd.Timestamp("2023-03-24T13:00:00Z")

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
HORIZONS: Final = (6, 24, 72)
PRIMARY_HORIZON: Final = 24
MINIMUM_DELAY_HOURS: Final = 1

FAMILY_CONSENSUS_FLOW_RISK_OFF: Final = "CONSENSUS_FLOW_RISK_OFF"
FAMILY_ACCELERATING_FLOW_RISK_OFF: Final = "ACCELERATING_FLOW_RISK_OFF"
FAMILY_BUY_FLOW_EXHAUSTION: Final = "BUY_FLOW_EXHAUSTION"
FAMILY_SELL_FLOW_EXHAUSTION_CONTROL: Final = "SELL_FLOW_EXHAUSTION_CONTROL"

FAMILY_ORDER: Final = (
    FAMILY_CONSENSUS_FLOW_RISK_OFF,
    FAMILY_ACCELERATING_FLOW_RISK_OFF,
    FAMILY_BUY_FLOW_EXHAUSTION,
    FAMILY_SELL_FLOW_EXHAUSTION_CONTROL,
)
NEGATIVE_PRIMARY_FAMILIES: Final = (
    FAMILY_CONSENSUS_FLOW_RISK_OFF,
    FAMILY_ACCELERATING_FLOW_RISK_OFF,
    FAMILY_BUY_FLOW_EXHAUSTION,
)
POSITIVE_CONTROL_FAMILIES: Final = (FAMILY_SELL_FLOW_EXHAUSTION_CONTROL,)

PRESSURE_LOOKBACKS: Final = (6, 24, 72)
ROBUST_HISTORY: Final = 168
RISK_OFF_PRESSURE: Final = -0.10
POSITIVE_PRESSURE: Final = 0.10
ACCELERATION_RISK_OFF: Final = -0.05
PARTICIPATION_ELEVATED: Final = 1.0

MIN_EVENTS: Final = 30
MIN_PAIRS: Final = 10
MIN_SIGNAL_DAYS: Final = 20
MIN_QUALIFIED_UNIVERSES_PER_PERIOD: Final = 2


class RD36P3Error(RuntimeError):
    """Raised when the frozen RD36-P3 engine contract is violated."""


def validate_constants() -> None:
    if SYMBOLS != ("BTCUSDT", "ETHUSDT"):
        raise RD36P3Error("symbol registry drifted")
    if UNIVERSES != ("C2", "D2", "E2"):
        raise RD36P3Error("universe registry drifted")
    if HORIZONS != (6, 24, 72):
        raise RD36P3Error("target horizon registry drifted")
    if PRIMARY_HORIZON != 24 or MINIMUM_DELAY_HOURS != 1:
        raise RD36P3Error("clock contract drifted")
    if FAMILY_ORDER != (
        FAMILY_CONSENSUS_FLOW_RISK_OFF,
        FAMILY_ACCELERATING_FLOW_RISK_OFF,
        FAMILY_BUY_FLOW_EXHAUSTION,
        FAMILY_SELL_FLOW_EXHAUSTION_CONTROL,
    ):
        raise RD36P3Error("family order drifted")
    if PRESSURE_LOOKBACKS != (6, 24, 72) or ROBUST_HISTORY != 168:
        raise RD36P3Error("feature lookback registry drifted")
    if not np.isclose(RISK_OFF_PRESSURE, -0.10):
        raise RD36P3Error("risk-off threshold drifted")
    if not np.isclose(POSITIVE_PRESSURE, 0.10):
        raise RD36P3Error("positive pressure threshold drifted")
    if not np.isclose(ACCELERATION_RISK_OFF, -0.05):
        raise RD36P3Error("acceleration threshold drifted")
    if not np.isclose(PARTICIPATION_ELEVATED, 1.0):
        raise RD36P3Error("participation threshold drifted")
    if (
        MIN_EVENTS != 30
        or MIN_PAIRS != 10
        or MIN_SIGNAL_DAYS != 20
        or MIN_QUALIFIED_UNIVERSES_PER_PERIOD != 2
    ):
        raise RD36P3Error("qualification support thresholds drifted")


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
    raise RD36P3Error(f"reference timestamp outside sealed RD36-P3 periods: {timestamp}")


def normalize_source(raw: pd.DataFrame, *, symbol: str) -> pd.DataFrame:
    required = {
        "timestamp",
        "quote_volume",
        "number_of_trades",
        "taker_buy_quote_volume",
    }
    missing = sorted(required.difference(raw.columns))
    if missing:
        raise RD36P3Error(f"{symbol} source missing columns: {missing}")
    if symbol not in SYMBOLS:
        raise RD36P3Error(f"unexpected Binance symbol: {symbol}")

    frame = raw.loc[
        :,
        [
            "timestamp",
            "quote_volume",
            "number_of_trades",
            "taker_buy_quote_volume",
        ],
    ].copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, errors="raise").dt.as_unit(
        "ns"
    )
    for column in (
        "quote_volume",
        "number_of_trades",
        "taker_buy_quote_volume",
    ):
        frame[column] = pd.to_numeric(frame[column], errors="raise").astype(float)

    frame = frame.sort_values("timestamp", kind="stable").reset_index(drop=True)
    if frame["timestamp"].duplicated().any():
        raise RD36P3Error(f"duplicate source timestamp: {symbol}")
    if len(frame) and frame["timestamp"].min() < DATA_START:
        raise RD36P3Error(f"pre-2022 source row entered P3: {symbol}")
    if len(frame) and frame["timestamp"].max() >= DATA_CUTOFF:
        raise RD36P3Error(f"2024 or later source row entered P3: {symbol}")
    if bool(
        (frame[["quote_volume", "number_of_trades", "taker_buy_quote_volume"]] < 0.0).any().any()
    ):
        raise RD36P3Error(f"negative Binance flow field: {symbol}")
    if not np.isfinite(
        frame[["quote_volume", "number_of_trades", "taker_buy_quote_volume"]].to_numpy(dtype=float)
    ).all():
        raise RD36P3Error(f"non-finite Binance flow field: {symbol}")

    diff = frame["timestamp"].diff()
    frame["segment_id"] = diff.ne(pd.Timedelta(hours=1)).cumsum().astype(int)
    return frame


def _rolling_prior_robust_z(values: pd.Series) -> pd.Series:
    shifted = values.shift(1)
    median = shifted.rolling(
        ROBUST_HISTORY,
        min_periods=ROBUST_HISTORY,
    ).median()

    def mad_raw(window: np.ndarray) -> float:
        middle = float(np.median(window))
        return float(np.median(np.abs(window - middle)))

    mad = shifted.rolling(
        ROBUST_HISTORY,
        min_periods=ROBUST_HISTORY,
    ).apply(mad_raw, raw=True)
    scale = 1.4826 * mad
    numerator = values - median
    result = numerator / scale.where(scale > 0.0)
    return result.replace([np.inf, -np.inf], np.nan)


def prepare_symbol_features(raw: pd.DataFrame, *, symbol: str) -> pd.DataFrame:
    frame = normalize_source(raw, symbol=symbol)

    quote = frame["quote_volume"].to_numpy(dtype=float)
    taker = frame["taker_buy_quote_volume"].to_numpy(dtype=float)
    imbalance = (
        np.divide(
            2.0 * taker,
            quote,
            out=np.full(len(frame), np.nan, dtype=float),
            where=quote > 0.0,
        )
        - 1.0
    )
    finite = np.isfinite(imbalance)
    imbalance[finite] = np.clip(imbalance[finite], -1.0, 1.0)
    frame["imbalance"] = imbalance

    for lookback in PRESSURE_LOOKBACKS:
        column = f"pressure_{lookback}"
        frame[column] = np.nan

    frame["quote_shock"] = np.nan
    frame["trade_shock"] = np.nan

    for _segment, index in frame.groupby("segment_id", sort=False).groups.items():
        idx = list(index)
        part = frame.loc[idx]
        for lookback in PRESSURE_LOOKBACKS:
            frame.loc[idx, f"pressure_{lookback}"] = (
                part["imbalance"].rolling(lookback, min_periods=lookback).mean().to_numpy()
            )

        log_quote = np.log1p(part["quote_volume"])
        log_trades = np.log1p(part["number_of_trades"])
        frame.loc[idx, "quote_shock"] = _rolling_prior_robust_z(log_quote).to_numpy()
        frame.loc[idx, "trade_shock"] = _rolling_prior_robust_z(log_trades).to_numpy()

    frame["acceleration"] = frame["pressure_6"] - frame["pressure_24"]
    frame["participation_shock"] = 0.5 * (frame["quote_shock"] + frame["trade_shock"])

    return frame


def market_state_frame(
    btc_raw: pd.DataFrame,
    eth_raw: pd.DataFrame,
) -> pd.DataFrame:
    btc = prepare_symbol_features(btc_raw, symbol="BTCUSDT")
    eth = prepare_symbol_features(eth_raw, symbol="ETHUSDT")

    keep = [
        "timestamp",
        "pressure_6",
        "pressure_24",
        "pressure_72",
        "acceleration",
        "participation_shock",
    ]
    btc = btc.loc[:, keep].rename(
        columns={column: f"btc_{column}" for column in keep if column != "timestamp"}
    )
    eth = eth.loc[:, keep].rename(
        columns={column: f"eth_{column}" for column in keep if column != "timestamp"}
    )

    frame = btc.merge(
        eth,
        on="timestamp",
        how="inner",
        validate="one_to_one",
    ).sort_values("timestamp", kind="stable")
    frame = frame.reset_index(drop=True)

    frame["market_pressure_6"] = 0.5 * (frame["btc_pressure_6"] + frame["eth_pressure_6"])
    frame["market_pressure_24"] = 0.5 * (frame["btc_pressure_24"] + frame["eth_pressure_24"])
    frame["market_pressure_72"] = 0.5 * (frame["btc_pressure_72"] + frame["eth_pressure_72"])
    frame["market_acceleration"] = 0.5 * (frame["btc_acceleration"] + frame["eth_acceleration"])
    frame["market_participation_shock"] = 0.5 * (
        frame["btc_participation_shock"] + frame["eth_participation_shock"]
    )
    frame["flow_dispersion_24"] = (frame["btc_pressure_24"] - frame["eth_pressure_24"]).abs()

    frame[FAMILY_CONSENSUS_FLOW_RISK_OFF] = (frame["btc_pressure_24"] <= RISK_OFF_PRESSURE) & (
        frame["eth_pressure_24"] <= RISK_OFF_PRESSURE
    )
    frame[FAMILY_ACCELERATING_FLOW_RISK_OFF] = frame[FAMILY_CONSENSUS_FLOW_RISK_OFF] & (
        frame["market_acceleration"] <= ACCELERATION_RISK_OFF
    )
    frame[FAMILY_BUY_FLOW_EXHAUSTION] = (frame["market_pressure_24"] >= POSITIVE_PRESSURE) & (
        frame["market_pressure_6"] <= 0.0
    )
    frame[FAMILY_SELL_FLOW_EXHAUSTION_CONTROL] = (
        frame["market_pressure_24"] <= RISK_OFF_PRESSURE
    ) & (frame["market_pressure_6"] >= 0.0)
    frame["participation_elevated"] = frame["market_participation_shock"] >= PARTICIPATION_ELEVATED
    return frame


def state_entry_ledger(market: pd.DataFrame) -> pd.DataFrame:
    required = {"timestamp", *FAMILY_ORDER}
    missing = sorted(required.difference(market.columns))
    if missing:
        raise RD36P3Error(f"market state frame missing columns: {missing}")

    records: list[dict[str, object]] = []
    context_columns = (
        "btc_pressure_24",
        "eth_pressure_24",
        "market_pressure_6",
        "market_pressure_24",
        "market_pressure_72",
        "market_acceleration",
        "market_participation_shock",
        "flow_dispersion_24",
        "participation_elevated",
    )
    for family in FAMILY_ORDER:
        state = market[family].fillna(False).astype(bool)
        previous = state.shift(1, fill_value=False)
        entered = state & ~previous
        for index in market.index[entered]:
            source_time = utc_timestamp(market.at[index, "timestamp"])
            reference_time = source_time + pd.Timedelta(hours=MINIMUM_DELAY_HOURS)
            if reference_time >= DATA_CUTOFF:
                continue
            record: dict[str, object] = {
                "family_id": family,
                "source_time": source_time,
                "reference_time": reference_time,
                "period_id": period_for_reference_time(reference_time),
            }
            for column in context_columns:
                value = market.at[index, column]
                if isinstance(value, (np.bool_, bool)):
                    record[column] = bool(value)
                elif pd.isna(value):
                    record[column] = np.nan
                else:
                    record[column] = float(value)
            records.append(record)

    columns = [
        "family_id",
        "source_time",
        "reference_time",
        "period_id",
        *context_columns,
    ]
    result = pd.DataFrame.from_records(records, columns=columns)
    if not result.empty:
        order = {family: i for i, family in enumerate(FAMILY_ORDER)}
        result["_family_order"] = result["family_id"].map(order)
        result = (
            result.sort_values(
                ["reference_time", "_family_order"],
                kind="stable",
            )
            .drop(columns="_family_order")
            .reset_index(drop=True)
        )
    return result


def normalize_target_bars(raw: pd.DataFrame, *, pair: str) -> pd.DataFrame:
    required = {"timestamp", "open"}
    missing = sorted(required.difference(raw.columns))
    if missing:
        raise RD36P3Error(f"KuCoin target source missing columns {pair}: {missing}")
    frame = raw.loc[:, ["timestamp", "open"]].copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, errors="raise").dt.as_unit(
        "ns"
    )
    frame["open"] = pd.to_numeric(frame["open"], errors="raise").astype(float)
    frame = frame.sort_values("timestamp", kind="stable").reset_index(drop=True)
    if frame["timestamp"].duplicated().any():
        raise RD36P3Error(f"duplicate KuCoin target timestamp: {pair}")
    if len(frame) and frame["timestamp"].max() >= DATA_CUTOFF:
        raise RD36P3Error(f"2024 or later target row entered P3: {pair}")
    if bool((frame["open"] <= 0.0).any()):
        raise RD36P3Error(f"non-positive KuCoin open: {pair}")
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
    pair: str,
    reference_time: object,
    horizon_hours: int,
    lookup: dict[int, float],
) -> dict[str, object] | None:
    if horizon_hours not in HORIZONS:
        raise RD36P3Error(f"unexpected horizon: {horizon_hours}")
    entry_time = utc_timestamp(reference_time)
    exit_time = entry_time + pd.Timedelta(hours=horizon_hours)
    if entry_time >= DATA_CUTOFF or exit_time >= DATA_CUTOFF:
        return None

    entry_key = int(entry_time.as_unit("ns").value)
    exit_key = int(exit_time.as_unit("ns").value)
    entry = lookup.get(entry_key)
    exit_price = lookup.get(exit_key)
    if entry is None or exit_price is None:
        return None
    if entry <= 0.0 or exit_price <= 0.0:
        raise RD36P3Error(f"invalid target price for {pair}")
    return {
        "entry_time": entry_time,
        "exit_time": exit_time,
        "entry_price": entry,
        "exit_price": exit_price,
        "forward_return": exit_price / entry - 1.0,
    }


def lopo_worst_mean(
    frame: pd.DataFrame,
    *,
    expected_direction: str,
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
    if expected_direction == "NEGATIVE":
        return max(means)
    if expected_direction == "POSITIVE":
        return min(means)
    raise RD36P3Error(f"unexpected direction: {expected_direction}")


def summarize_markouts(markouts: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for family in FAMILY_ORDER:
        direction = "NEGATIVE" if family in NEGATIVE_PRIMARY_FAMILIES else "POSITIVE"
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
                    rows.append(
                        {
                            "family_id": family,
                            "universe_id": universe,
                            "period_id": period_id,
                            "horizon_hours": horizon,
                            "expected_direction": direction,
                            "event_count": int(len(cell)),
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
                            "source_state_count": int(
                                pd.to_datetime(
                                    cell["source_time"],
                                    utc=True,
                                    errors="coerce",
                                ).nunique()
                            ),
                            "mean_forward_return": (
                                float(returns.mean()) if len(returns) else np.nan
                            ),
                            "median_forward_return": (
                                float(returns.median()) if len(returns) else np.nan
                            ),
                            "positive_share": (
                                float((returns > 0.0).mean()) if len(returns) else np.nan
                            ),
                            "lopo_worst_mean_forward_return": lopo_worst_mean(
                                cell,
                                expected_direction=direction,
                            ),
                        }
                    )
    return pd.DataFrame.from_records(rows)


def qualification_tables(
    summary: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    cells: list[dict[str, object]] = []

    for family in FAMILY_ORDER:
        direction = "NEGATIVE" if family in NEGATIVE_PRIMARY_FAMILIES else "POSITIVE"
        for universe in UNIVERSES:
            for period_id in PERIODS:
                matches = summary.loc[
                    (summary["family_id"] == family)
                    & (summary["universe_id"] == universe)
                    & (summary["period_id"] == period_id)
                    & (summary["horizon_hours"] == PRIMARY_HORIZON)
                ]
                if len(matches) != 1:
                    raise RD36P3Error(
                        "expected one primary-horizon summary cell for "
                        f"{family}/{universe}/{period_id}"
                    )
                row = matches.iloc[0]
                event_count = int(row["event_count"])
                pair_count = int(row["pair_count"])
                signal_days = int(row["signal_day_count"])
                mean_value = float(row["mean_forward_return"])
                median_value = float(row["median_forward_return"])
                lopo_value = float(row["lopo_worst_mean_forward_return"])

                support = (
                    event_count >= MIN_EVENTS
                    and pair_count >= MIN_PAIRS
                    and signal_days >= MIN_SIGNAL_DAYS
                )
                if direction == "NEGATIVE":
                    directional = (
                        np.isfinite(mean_value)
                        and np.isfinite(median_value)
                        and np.isfinite(lopo_value)
                        and mean_value < 0.0
                        and median_value < 0.0
                        and lopo_value < 0.0
                    )
                else:
                    directional = np.isfinite(mean_value) and mean_value > 0.0

                cells.append(
                    {
                        "family_id": family,
                        "universe_id": universe,
                        "period_id": period_id,
                        "expected_direction": direction,
                        "event_count_24h": event_count,
                        "pair_count_24h": pair_count,
                        "signal_day_count_24h": signal_days,
                        "mean_24h": mean_value,
                        "median_24h": median_value,
                        "lopo_worst_mean_24h": lopo_value,
                        "support_pass": bool(support),
                        "direction_pass": bool(directional),
                        "cell_qualified": bool(support and directional),
                    }
                )

    cell_frame = pd.DataFrame.from_records(cells)
    family_rows: list[dict[str, object]] = []
    for family in FAMILY_ORDER:
        subset = cell_frame.loc[cell_frame["family_id"] == family]
        counts: dict[str, int] = {}
        for period_id in PERIODS:
            counts[period_id] = int(
                subset.loc[
                    subset["period_id"] == period_id,
                    "cell_qualified",
                ].sum()
            )
        qualified = all(count >= MIN_QUALIFIED_UNIVERSES_PER_PERIOD for count in counts.values())
        primary = family in NEGATIVE_PRIMARY_FAMILIES
        family_rows.append(
            {
                "family_id": family,
                "expected_direction": ("NEGATIVE" if primary else "POSITIVE"),
                "primary_exit_candidate": primary,
                "qualified_universes_2022": counts["ROBUSTNESS_2022"],
                "qualified_universes_2023": counts["ROBUSTNESS_2023"],
                "qualified": bool(qualified),
                "advances_to_shadow_ablation": bool(qualified and primary),
                "return_ranking_used": False,
                "winner_selection_used": False,
                "parameter_search_used": False,
            }
        )
    return cell_frame, pd.DataFrame.from_records(family_rows)
