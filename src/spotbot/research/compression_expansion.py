from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Any, cast

import pandas as pd


class CompressionExpansionConfigurationError(
    ValueError
):
    pass


@dataclass(frozen=True, slots=True)
class CompressionExpansionPolicy:
    research_start: datetime
    research_end_exclusive: datetime
    breakout_lookback_days: int = 20
    compression_lookback_days: int = 60
    compression_percentile_maximum: float = 0.2
    ranking_maximum: int = 10
    maximum_positions: int = 2
    minimum_turnover_expansion: float = 1.5
    initial_stop_atr: float = 2.5
    trailing_stop_atr: float = 4.0
    maximum_holding_days: int = 30
    transaction_cost_fraction: float = 0.002

    def __post_init__(self) -> None:
        for name, value in (
            ("research_start", self.research_start),
            (
                "research_end_exclusive",
                self.research_end_exclusive,
            ),
        ):
            if (
                value.tzinfo is None
                or value.utcoffset() is None
            ):
                raise CompressionExpansionConfigurationError(
                    f"{name} must be timezone-aware."
                )

        if (
            self.research_end_exclusive
            <= self.research_start
        ):
            raise CompressionExpansionConfigurationError(
                "Invalid research range."
            )

        integer_values = (
            self.breakout_lookback_days,
            self.compression_lookback_days,
            self.ranking_maximum,
            self.maximum_positions,
            self.maximum_holding_days,
        )

        if any(value <= 0 for value in integer_values):
            raise CompressionExpansionConfigurationError(
                "Integer policy fields must be positive."
            )

        if (
            self.maximum_positions
            > self.ranking_maximum
        ):
            raise CompressionExpansionConfigurationError(
                "maximum_positions cannot exceed "
                "ranking_maximum."
            )

        if not (
            0.0
            < self.compression_percentile_maximum
            <= 1.0
        ):
            raise CompressionExpansionConfigurationError(
                "compression_percentile_maximum must "
                "be in (0, 1]."
            )

        if (
            self.minimum_turnover_expansion
            <= 0.0
        ):
            raise CompressionExpansionConfigurationError(
                "minimum_turnover_expansion must "
                "exceed zero."
            )

        if self.initial_stop_atr <= 0.0:
            raise CompressionExpansionConfigurationError(
                "initial_stop_atr must exceed zero."
            )

        if self.trailing_stop_atr <= 0.0:
            raise CompressionExpansionConfigurationError(
                "trailing_stop_atr must exceed zero."
            )

        if (
            self.transaction_cost_fraction
            < 0.0
        ):
            raise CompressionExpansionConfigurationError(
                "transaction_cost_fraction cannot "
                "be negative."
            )


@dataclass(slots=True)
class _Position:
    entry_signal_time: pd.Timestamp
    entry_price: float
    highest_high: float
    stop_price: float
    last_close: float


_TRADE_COLUMNS = [
    "symbol",
    "entry_signal_time",
    "exit_signal_time",
    "entry_price",
    "exit_price",
    "net_trade_return_after_round_trip_cost",
    "holding_days",
    "exit_reason",
]


def _require_columns(
    frame: pd.DataFrame,
    *,
    required: set[str],
    frame_name: str,
) -> None:
    missing = sorted(
        required - set(frame.columns)
    )

    if missing:
        raise CompressionExpansionConfigurationError(
            f"{frame_name} is missing columns: "
            f"{missing}."
        )


def _normalise_column_name(
    value: object,
) -> str:
    return "".join(
        character
        for character in str(value).lower()
        if character.isalnum()
    )


def _turnover_values(
    history: pd.DataFrame,
) -> pd.Series:
    normalised_columns = {
        _normalise_column_name(column): str(column)
        for column in history.columns
    }

    direct_priorities = (
        "turnover",
        "quoteturnover",
        "quotevolume",
        "quoteassetvolume",
        "quotevol",
        "funds",
    )

    direct_column = next(
        (
            normalised_columns[name]
            for name in direct_priorities
            if name in normalised_columns
        ),
        None,
    )

    if direct_column is None:
        for column in history.columns:
            normalised = _normalise_column_name(
                column
            )

            quote_activity = (
                "quote" in normalised
                and (
                    "turnover" in normalised
                    or "volume" in normalised
                    or normalised.endswith("vol")
                )
            )

            if quote_activity:
                direct_column = str(column)
                break

    if direct_column is not None:
        return pd.to_numeric(
            history[direct_column],
            errors="raise",
        )

    base_priorities = (
        "basevolume",
        "baseassetvolume",
        "basevol",
        "volume",
        "amount",
        "quantity",
        "size",
    )

    base_column = next(
        (
            normalised_columns[name]
            for name in base_priorities
            if name in normalised_columns
        ),
        None,
    )

    if base_column is None:
        for column in history.columns:
            normalised = _normalise_column_name(
                column
            )

            probable_base_volume = (
                (
                    "volume" in normalised
                    or normalised.endswith("vol")
                )
                and "quote" not in normalised
            )

            if probable_base_volume:
                base_column = str(column)
                break

    if base_column is not None:
        base_volume = pd.to_numeric(
            history[base_column],
            errors="raise",
        )

        close = pd.to_numeric(
            history["close"],
            errors="raise",
        )

        return base_volume * close

    available = sorted(
        str(column)
        for column in history.columns
    )

    raise CompressionExpansionConfigurationError(
        "History lacks a supported turnover "
        "or volume column. "
        f"Available columns: {available}."
    )


def _prepare_history(
    history: pd.DataFrame,
) -> pd.DataFrame:
    required = {
        "symbol",
        "close_time",
        "high",
        "low",
        "close",
    }

    _require_columns(
        history,
        required=required,
        frame_name="history",
    )

    result = history[
        [
            "symbol",
            "close_time",
            "high",
            "low",
            "close",
        ]
    ].copy()

    result["turnover"] = _turnover_values(
        history
    )

    result["symbol"] = (
        result["symbol"]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    result["close_time"] = pd.to_datetime(
        result["close_time"],
        utc=True,
        errors="raise",
    )

    for column in (
        "high",
        "low",
        "close",
        "turnover",
    ):
        result[column] = pd.to_numeric(
            result[column],
            errors="raise",
        )

    if result.duplicated(
        [
            "symbol",
            "close_time",
        ]
    ).any():
        raise CompressionExpansionConfigurationError(
            "Duplicate history symbol/close_time rows."
        )

    if (
        result[
            [
                "high",
                "low",
                "close",
            ]
        ]
        <= 0.0
    ).any().any():
        raise CompressionExpansionConfigurationError(
            "History prices must exceed zero."
        )

    if (
        result["high"]
        < result[
            [
                "low",
                "close",
            ]
        ].max(axis=1)
    ).any():
        raise CompressionExpansionConfigurationError(
            "Invalid OHLC high values."
        )

    if (
        result["low"]
        > result[
            [
                "high",
                "close",
            ]
        ].min(axis=1)
    ).any():
        raise CompressionExpansionConfigurationError(
            "Invalid OHLC low values."
        )

    if (
        result["turnover"]
        < 0.0
    ).any():
        raise CompressionExpansionConfigurationError(
            "History turnover cannot be negative."
        )

    return (
        result.sort_values(
            [
                "symbol",
                "close_time",
            ]
        )
        .reset_index(drop=True)
    )


def _prepare_ranking(
    ranking: pd.DataFrame,
    *,
    policy: CompressionExpansionPolicy,
) -> pd.DataFrame:
    required = {
        "snapshot_time",
        "symbol",
        "composite_score",
        "rank_within_snapshot",
    }

    _require_columns(
        ranking,
        required=required,
        frame_name="ranking",
    )

    result = ranking[
        [
            "snapshot_time",
            "symbol",
            "composite_score",
            "rank_within_snapshot",
        ]
    ].copy()

    result["snapshot_time"] = pd.to_datetime(
        result["snapshot_time"],
        utc=True,
        errors="raise",
    )

    result["symbol"] = (
        result["symbol"]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    result["composite_score"] = pd.to_numeric(
        result["composite_score"],
        errors="raise",
    )

    result["rank_within_snapshot"] = pd.to_numeric(
        result["rank_within_snapshot"],
        errors="raise",
    )

    start = pd.Timestamp(
        policy.research_start
    )

    end = pd.Timestamp(
        policy.research_end_exclusive
    )

    result = result.loc[
        (
            result["snapshot_time"]
            >= start
        )
        & (
            result["snapshot_time"]
            < end
        )
    ]

    if result.duplicated(
        [
            "snapshot_time",
            "symbol",
        ]
    ).any():
        raise CompressionExpansionConfigurationError(
            "Duplicate ranking snapshot/symbol rows."
        )

    return (
        result.sort_values(
            [
                "snapshot_time",
                "symbol",
            ]
        )
        .reset_index(drop=True)
    )


def _last_percentile(
    values: pd.Series,
) -> float:
    ranks = values.rank(
        method="average",
        pct=True,
    )

    return float(
        ranks.iloc[-1]
    )


def _compute_features(
    history: pd.DataFrame,
    *,
    policy: CompressionExpansionPolicy,
) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []

    # ATR14 and the turnover baseline based on the
    # breakout lookback are implementation conventions,
    # not additional tunable H05 parameters.
    atr_days = 14

    for symbol, raw_group in history.groupby(
        "symbol",
        sort=True,
    ):
        group = (
            raw_group
            .sort_values("close_time")
            .reset_index(drop=True)
        )

        previous_close = (
            group["close"].shift(1)
        )

        true_range = pd.concat(
            [
                (
                    group["high"]
                    - group["low"]
                ),
                (
                    group["high"]
                    - previous_close
                ).abs(),
                (
                    group["low"]
                    - previous_close
                ).abs(),
            ],
            axis=1,
        ).max(axis=1)

        atr = (
            true_range
            .rolling(
                atr_days,
                min_periods=atr_days,
            )
            .mean()
        )

        normalised_atr = (
            atr
            / group["close"]
        )

        prior_normalised_atr = (
            normalised_atr.shift(1)
        )

        compression_percentile = (
            prior_normalised_atr
            .rolling(
                policy.compression_lookback_days,
                min_periods=(
                    policy.compression_lookback_days
                ),
            )
            .apply(
                _last_percentile,
                raw=False,
            )
        )

        prior_breakout_high = (
            group["high"]
            .rolling(
                policy.breakout_lookback_days,
                min_periods=(
                    policy.breakout_lookback_days
                ),
            )
            .max()
            .shift(1)
        )

        prior_turnover_median = (
            group["turnover"]
            .rolling(
                policy.breakout_lookback_days,
                min_periods=(
                    policy.breakout_lookback_days
                ),
            )
            .median()
            .shift(1)
        )

        turnover_expansion = (
            group["turnover"]
            / prior_turnover_median.where(
                prior_turnover_median > 0.0
            )
        )

        breakout_distance = (
            group["close"]
            / prior_breakout_high.where(
                prior_breakout_high > 0.0
            )
            - 1.0
        )

        frames.append(
            pd.DataFrame(
                {
                    "snapshot_time": (
                        group["close_time"]
                    ),
                    "symbol": str(symbol),
                    "signal_high": (
                        group["high"]
                    ),
                    "signal_low": (
                        group["low"]
                    ),
                    "signal_close": (
                        group["close"]
                    ),
                    "signal_turnover": (
                        group["turnover"]
                    ),
                    "previous_close": (
                        previous_close
                    ),
                    "atr_14_h05": atr,
                    "normalised_atr_h05": (
                        normalised_atr
                    ),
                    "prior_normalised_atr_h05": (
                        prior_normalised_atr
                    ),
                    (
                        "compression_percentile_"
                        "h05"
                    ): compression_percentile,
                    "prior_breakout_high_h05": (
                        prior_breakout_high
                    ),
                    (
                        "prior_turnover_median_"
                        "h05"
                    ): prior_turnover_median,
                    "turnover_expansion_h05": (
                        turnover_expansion
                    ),
                    "breakout_distance_h05": (
                        breakout_distance
                    ),
                }
            )
        )

    if not frames:
        raise CompressionExpansionConfigurationError(
            "No H05 features were constructed."
        )

    return pd.concat(
        frames,
        ignore_index=True,
    )


def build_compression_expansion_signals(
    history: pd.DataFrame,
    ranking: pd.DataFrame,
    *,
    policy: CompressionExpansionPolicy,
) -> pd.DataFrame:
    prepared_history = _prepare_history(
        history
    )

    prepared_ranking = _prepare_ranking(
        ranking,
        policy=policy,
    )

    features = _compute_features(
        prepared_history,
        policy=policy,
    )

    merged = prepared_ranking.merge(
        features,
        on=[
            "snapshot_time",
            "symbol",
        ],
        how="left",
        validate="one_to_one",
    )

    feature_columns = [
        "signal_high",
        "signal_low",
        "signal_close",
        "signal_turnover",
        "previous_close",
        "atr_14_h05",
        "normalised_atr_h05",
        "prior_normalised_atr_h05",
        "compression_percentile_h05",
        "prior_breakout_high_h05",
        "prior_turnover_median_h05",
        "turnover_expansion_h05",
        "breakout_distance_h05",
    ]

    merged["complete_features"] = (
        merged[
            feature_columns
        ].notna().all(axis=1)
    )

    merged["rank_pass"] = (
        merged["rank_within_snapshot"]
        <= policy.ranking_maximum
    )

    merged["compression_pass"] = (
        merged[
            "compression_percentile_h05"
        ]
        <= (
            policy
            .compression_percentile_maximum
        )
    )

    merged["breakout_pass"] = (
        merged["signal_close"]
        > merged[
            "prior_breakout_high_h05"
        ]
    )

    merged["turnover_pass"] = (
        merged["turnover_expansion_h05"]
        >= policy.minimum_turnover_expansion
    )

    merged["candidate"] = (
        merged["complete_features"]
        & merged["rank_pass"]
        & merged["compression_pass"]
        & merged["breakout_pass"]
        & merged["turnover_pass"]
    )

    return (
        merged.sort_values(
            [
                "snapshot_time",
                "candidate",
                "rank_within_snapshot",
                "compression_percentile_h05",
                "breakout_distance_h05",
                "turnover_expansion_h05",
                "composite_score",
                "symbol",
            ],
            ascending=[
                True,
                False,
                True,
                True,
                False,
                False,
                False,
                True,
            ],
        )
        .reset_index(drop=True)
    )


def _trade_record(
    *,
    symbol: str,
    position: _Position,
    snapshot_time: pd.Timestamp,
    exit_price: float,
    exit_reason: str,
    transaction_cost_fraction: float,
) -> dict[str, object]:
    net_return = (
        (
            exit_price
            * (
                1.0
                - transaction_cost_fraction
            )
        )
        / (
            position.entry_price
            * (
                1.0
                + transaction_cost_fraction
            )
        )
        - 1.0
    )

    return {
        "symbol": symbol,
        "entry_signal_time": (
            position.entry_signal_time
        ),
        "exit_signal_time": snapshot_time,
        "entry_price": position.entry_price,
        "exit_price": exit_price,
        (
            "net_trade_return_after_"
            "round_trip_cost"
        ): net_return,
        "holding_days": int(
            (
                snapshot_time
                - position.entry_signal_time
            ).days
        ),
        "exit_reason": exit_reason,
    }


def build_compression_expansion_weights(
    history: pd.DataFrame,
    signals: pd.DataFrame,
    *,
    policy: CompressionExpansionPolicy,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    prepared_history = _prepare_history(
        history
    )

    required = {
        "snapshot_time",
        "symbol",
        "rank_within_snapshot",
        "composite_score",
        "signal_high",
        "signal_close",
        "atr_14_h05",
        "compression_percentile_h05",
        "breakout_distance_h05",
        "turnover_expansion_h05",
        "candidate",
    }

    _require_columns(
        signals,
        required=required,
        frame_name="signals",
    )

    prepared_signals = signals.copy()

    prepared_signals["snapshot_time"] = (
        pd.to_datetime(
            prepared_signals[
                "snapshot_time"
            ],
            utc=True,
            errors="raise",
        )
    )

    prepared_signals["symbol"] = (
        prepared_signals["symbol"]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    snapshots = [
        pd.Timestamp(
            cast(
                Any,
                value,
            )
        )
        for value in (
            prepared_signals[
                "snapshot_time"
            ]
            .drop_duplicates()
            .sort_values()
        )
    ]

    if not snapshots:
        raise CompressionExpansionConfigurationError(
            "No H05 signal snapshots were supplied."
        )

    symbols = sorted(
        prepared_signals["symbol"]
        .drop_duplicates()
        .tolist()
    )

    signal_groups = {
        pd.Timestamp(
            cast(
                Any,
                snapshot,
            )
        ): group
        for snapshot, group
        in prepared_signals.groupby(
            "snapshot_time",
            sort=True,
        )
    }

    bars = {
        (
            pd.Timestamp(
                cast(
                    Any,
                    row.close_time,
                )
            ),
            str(
                cast(
                    Any,
                    row.symbol,
                )
            ),
        ): (
            float(
                cast(
                    Any,
                    row.high,
                )
            ),
            float(
                cast(
                    Any,
                    row.low,
                )
            ),
            float(
                cast(
                    Any,
                    row.close,
                )
            ),
        )
        for row
        in prepared_history.itertuples(
            index=False
        )
    }

    positions: dict[
        str,
        _Position,
    ] = {}

    weight_rows: list[
        dict[str, object]
    ] = []

    trade_rows: list[
        dict[str, object]
    ] = []

    final_snapshot = snapshots[-1]

    for snapshot in snapshots:
        rows = signal_groups[
            snapshot
        ]

        current_symbols = set(
            rows["symbol"].tolist()
        )

        atr_by_symbol = {
            str(
                cast(
                    Any,
                    row.symbol,
                )
            ): float(
                cast(
                    Any,
                    row.atr_14_h05,
                )
            )
            for row
            in rows.itertuples(
                index=False
            )
            if pd.notna(
                cast(
                    Any,
                    row.atr_14_h05,
                )
            )
        }

        for symbol in list(
            positions
        ):
            position = positions[
                symbol
            ]

            bar = bars.get(
                (
                    snapshot,
                    symbol,
                )
            )

            if (
                symbol
                not in current_symbols
                or bar is None
            ):
                trade_rows.append(
                    _trade_record(
                        symbol=symbol,
                        position=position,
                        snapshot_time=snapshot,
                        exit_price=(
                            position.last_close
                        ),
                        exit_reason=(
                            "UNIVERSE_OR_DATA_EXIT"
                        ),
                        transaction_cost_fraction=(
                            policy
                            .transaction_cost_fraction
                        ),
                    )
                )

                del positions[symbol]
                continue

            high, low, close = bar

            if low <= position.stop_price:
                trade_rows.append(
                    _trade_record(
                        symbol=symbol,
                        position=position,
                        snapshot_time=snapshot,
                        exit_price=close,
                        exit_reason=(
                            "DAILY_STOP_TRIGGER"
                        ),
                        transaction_cost_fraction=(
                            policy
                            .transaction_cost_fraction
                        ),
                    )
                )

                del positions[symbol]
                continue

            holding_days = int(
                (
                    snapshot
                    - position.entry_signal_time
                ).days
            )

            if (
                holding_days
                >= policy.maximum_holding_days
            ):
                trade_rows.append(
                    _trade_record(
                        symbol=symbol,
                        position=position,
                        snapshot_time=snapshot,
                        exit_price=close,
                        exit_reason=(
                            "MAXIMUM_HOLDING_DAYS"
                        ),
                        transaction_cost_fraction=(
                            policy
                            .transaction_cost_fraction
                        ),
                    )
                )

                del positions[symbol]
                continue

            position.highest_high = max(
                position.highest_high,
                high,
            )

            position.last_close = close

            atr = atr_by_symbol.get(
                symbol,
                float("nan"),
            )

            if (
                math.isfinite(atr)
                and atr > 0.0
            ):
                trailing_stop = (
                    position.highest_high
                    - (
                        policy.trailing_stop_atr
                        * atr
                    )
                )

                position.stop_price = max(
                    position.stop_price,
                    trailing_stop,
                    0.0,
                )

        if snapshot == final_snapshot:
            for symbol in list(
                positions
            ):
                position = positions[
                    symbol
                ]

                bar = bars.get(
                    (
                        snapshot,
                        symbol,
                    )
                )

                exit_price = (
                    bar[2]
                    if bar is not None
                    else position.last_close
                )

                trade_rows.append(
                    _trade_record(
                        symbol=symbol,
                        position=position,
                        snapshot_time=snapshot,
                        exit_price=exit_price,
                        exit_reason=(
                            "END_OF_RESEARCH"
                        ),
                        transaction_cost_fraction=(
                            policy
                            .transaction_cost_fraction
                        ),
                    )
                )

                del positions[symbol]

        if snapshot != final_snapshot:
            available_slots = (
                policy.maximum_positions
                - len(positions)
            )

            candidates = (
                rows.loc[
                    rows["candidate"]
                    .astype(bool)
                ]
                .sort_values(
                    [
                        "rank_within_snapshot",
                        "compression_percentile_h05",
                        "breakout_distance_h05",
                        "turnover_expansion_h05",
                        "composite_score",
                        "symbol",
                    ],
                    ascending=[
                        True,
                        True,
                        False,
                        False,
                        False,
                        True,
                    ],
                )
            )

            for row in candidates.itertuples(
                index=False
            ):
                if available_slots <= 0:
                    break

                symbol = str(
                    cast(
                        Any,
                        row.symbol,
                    )
                )

                if symbol in positions:
                    continue

                entry_price = float(
                    cast(
                        Any,
                        row.signal_close,
                    )
                )

                entry_high = float(
                    cast(
                        Any,
                        row.signal_high,
                    )
                )

                entry_atr = float(
                    cast(
                        Any,
                        row.atr_14_h05,
                    )
                )

                if (
                    entry_price <= 0.0
                    or entry_atr <= 0.0
                    or not math.isfinite(
                        entry_atr
                    )
                ):
                    continue

                positions[symbol] = _Position(
                    entry_signal_time=snapshot,
                    entry_price=entry_price,
                    highest_high=entry_high,
                    stop_price=max(
                        0.0,
                        (
                            entry_price
                            - (
                                policy.initial_stop_atr
                                * entry_atr
                            )
                        ),
                    ),
                    last_close=entry_price,
                )

                available_slots -= 1

        active_count = len(
            positions
        )

        target_weight = (
            1.0 / active_count
            if active_count > 0
            else 0.0
        )

        for symbol in symbols:
            selected = (
                symbol in positions
            )

            weight_rows.append(
                {
                    "snapshot_time": snapshot,
                    "symbol": symbol,
                    "target_weight": (
                        target_weight
                        if selected
                        else 0.0
                    ),
                    "selected": selected,
                    "rebalance_day": True,
                }
            )

    weights = pd.DataFrame(
        weight_rows
    )

    trades = pd.DataFrame(
        trade_rows,
        columns=_TRADE_COLUMNS,
    )

    exposure = (
        weights.groupby(
            "snapshot_time"
        )["target_weight"]
        .sum()
    )

    position_counts = (
        weights.groupby(
            "snapshot_time"
        )["selected"]
        .sum()
    )

    if (
        weights["target_weight"]
        < 0.0
    ).any():
        raise CompressionExpansionConfigurationError(
            "Negative Spot weight was generated."
        )

    if (
        exposure
        > 1.0 + 1e-12
    ).any():
        raise CompressionExpansionConfigurationError(
            "Spot exposure exceeded one."
        )

    if (
        position_counts
        > policy.maximum_positions
    ).any():
        raise CompressionExpansionConfigurationError(
            "Maximum position count was exceeded."
        )

    return (
        weights,
        trades,
    )