from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Any, cast

import pandas as pd


class AggressiveReaccelerationConfigurationError(
    ValueError
):
    pass


@dataclass(frozen=True, slots=True)
class AggressiveReaccelerationPolicy:
    research_start: datetime
    research_end_exclusive: datetime
    benchmark_symbol: str = "BTC/USDT"
    momentum_days: int = 3
    ema_reclaim_days: int = 10
    relative_strength_days: int = 60
    ranking_maximum: int = 5
    maximum_positions: int = 2
    minimum_momentum: float = 0.02
    minimum_relative_strength: float = 0.0
    maximum_pullback: float = 0.25
    trailing_stop_atr: float = 3.0
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
                raise (
                    AggressiveReaccelerationConfigurationError(
                        f"{name} must be timezone-aware."
                    )
                )

        if (
            self.research_end_exclusive
            <= self.research_start
        ):
            raise (
                AggressiveReaccelerationConfigurationError(
                    "Invalid research range."
                )
            )

        integer_fields = (
            self.momentum_days,
            self.ema_reclaim_days,
            self.relative_strength_days,
            self.ranking_maximum,
            self.maximum_positions,
        )

        if any(
            value <= 0
            for value in integer_fields
        ):
            raise (
                AggressiveReaccelerationConfigurationError(
                    "Integer policy fields must be positive."
                )
            )

        if (
            self.maximum_positions
            > self.ranking_maximum
        ):
            raise (
                AggressiveReaccelerationConfigurationError(
                    "maximum_positions cannot exceed "
                    "ranking_maximum."
                )
            )

        benchmark = (
            self.benchmark_symbol
            .strip()
            .upper()
        )

        if not benchmark:
            raise (
                AggressiveReaccelerationConfigurationError(
                    "benchmark_symbol cannot be empty."
                )
            )

        object.__setattr__(
            self,
            "benchmark_symbol",
            benchmark,
        )

        if self.minimum_momentum < 0.0:
            raise (
                AggressiveReaccelerationConfigurationError(
                    "minimum_momentum cannot be negative."
                )
            )

        if not (
            0.0
            <= self.maximum_pullback
            < 1.0
        ):
            raise (
                AggressiveReaccelerationConfigurationError(
                    "maximum_pullback must be in [0, 1)."
                )
            )

        if self.trailing_stop_atr <= 0.0:
            raise (
                AggressiveReaccelerationConfigurationError(
                    "trailing_stop_atr must exceed zero."
                )
            )

        if (
            self.transaction_cost_fraction
            < 0.0
        ):
            raise (
                AggressiveReaccelerationConfigurationError(
                    "transaction_cost_fraction cannot "
                    "be negative."
                )
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
        raise (
            AggressiveReaccelerationConfigurationError(
                f"{frame_name} is missing columns: "
                f"{missing}."
            )
        )


def _prepare_history(
    history: pd.DataFrame,
) -> pd.DataFrame:
    columns = [
        "symbol",
        "open_time",
        "close_time",
        "open",
        "high",
        "low",
        "close",
    ]

    _require_columns(
        history,
        required=set(columns),
        frame_name="history",
    )

    result = history[columns].copy()

    result["symbol"] = (
        result["symbol"]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    for column in (
        "open_time",
        "close_time",
    ):
        result[column] = pd.to_datetime(
            result[column],
            utc=True,
            errors="raise",
        )

    for column in (
        "open",
        "high",
        "low",
        "close",
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
        raise (
            AggressiveReaccelerationConfigurationError(
                "Duplicate history symbol/close_time rows."
            )
        )

    invalid_prices = (
        (
            result[
                [
                    "open",
                    "high",
                    "low",
                    "close",
                ]
            ]
            <= 0.0
        )
        .any()
        .any()
    )

    if invalid_prices:
        raise (
            AggressiveReaccelerationConfigurationError(
                "History prices must exceed zero."
            )
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
    policy: AggressiveReaccelerationPolicy,
) -> pd.DataFrame:
    columns = [
        "snapshot_time",
        "symbol",
        "composite_score",
        "rank_within_snapshot",
    ]

    _require_columns(
        ranking,
        required=set(columns),
        frame_name="ranking",
    )

    result = ranking[columns].copy()

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

    result["rank_within_snapshot"] = (
        pd.to_numeric(
            result["rank_within_snapshot"],
            errors="raise",
        )
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
        raise (
            AggressiveReaccelerationConfigurationError(
                "Duplicate ranking snapshot/symbol rows."
            )
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


def _compute_features(
    history: pd.DataFrame,
    *,
    policy: AggressiveReaccelerationPolicy,
) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []

    # ATR14 is a fixed implementation convention rather than
    # a tunable H02 parameter.
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

        ema = (
            group["close"]
            .ewm(
                span=policy.ema_reclaim_days,
                adjust=False,
                min_periods=(
                    policy.ema_reclaim_days
                ),
            )
            .mean()
        )

        rolling_high = (
            group["high"]
            .rolling(
                policy.relative_strength_days,
                min_periods=(
                    policy.relative_strength_days
                ),
            )
            .max()
        )

        frames.append(
            pd.DataFrame(
                {
                    "snapshot_time": (
                        group["close_time"]
                    ),
                    "symbol": str(symbol),
                    "signal_close": (
                        group["close"]
                    ),
                    "signal_high": (
                        group["high"]
                    ),
                    "signal_low": (
                        group["low"]
                    ),
                    "previous_close": (
                        previous_close
                    ),
                    "ema_reclaim": ema,
                    "previous_ema_reclaim": (
                        ema.shift(1)
                    ),
                    "momentum_h02": (
                        group["close"]
                        / group["close"].shift(
                            policy.momentum_days
                        )
                        - 1.0
                    ),
                    "return_60d_h02": (
                        group["close"]
                        / group["close"].shift(
                            policy.relative_strength_days
                        )
                        - 1.0
                    ),
                    "pullback_from_60d_high": (
                        group["close"]
                        / rolling_high
                        - 1.0
                    ),
                    "atr_14_h02": (
                        true_range
                        .rolling(
                            atr_days,
                            min_periods=atr_days,
                        )
                        .mean()
                    ),
                }
            )
        )

    if not frames:
        raise (
            AggressiveReaccelerationConfigurationError(
                "No H02 features were constructed."
            )
        )

    features = pd.concat(
        frames,
        ignore_index=True,
    )

    benchmark = (
        features.loc[
            features["symbol"]
            == policy.benchmark_symbol,
            [
                "snapshot_time",
                "return_60d_h02",
            ],
        ]
        .rename(
            columns={
                "return_60d_h02": (
                    "benchmark_return_60d_h02"
                )
            }
        )
        .sort_values("snapshot_time")
    )

    if benchmark.empty:
        raise (
            AggressiveReaccelerationConfigurationError(
                "Benchmark history was not found: "
                f"{policy.benchmark_symbol}."
            )
        )

    features = features.merge(
        benchmark,
        on="snapshot_time",
        how="left",
        validate="many_to_one",
    )

    features[
        "relative_strength_60d_h02"
    ] = (
        features["return_60d_h02"]
        - features[
            "benchmark_return_60d_h02"
        ]
    )

    return features


def build_aggressive_reacceleration_signals(
    history: pd.DataFrame,
    ranking: pd.DataFrame,
    *,
    policy: AggressiveReaccelerationPolicy,
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
        "signal_close",
        "signal_high",
        "signal_low",
        "previous_close",
        "ema_reclaim",
        "previous_ema_reclaim",
        "momentum_h02",
        "return_60d_h02",
        "benchmark_return_60d_h02",
        "relative_strength_60d_h02",
        "pullback_from_60d_high",
        "atr_14_h02",
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

    merged["momentum_pass"] = (
        merged["momentum_h02"]
        >= policy.minimum_momentum
    )

    merged["relative_strength_pass"] = (
        merged[
            "relative_strength_60d_h02"
        ]
        >= policy.minimum_relative_strength
    )

    merged["pullback_pass"] = (
        merged["pullback_from_60d_high"]
        >= -policy.maximum_pullback
    )

    merged["ema_reclaim_pass"] = (
        (
            merged["signal_close"]
            > merged["ema_reclaim"]
        )
        & (
            merged["previous_close"]
            <= merged["previous_ema_reclaim"]
        )
    )

    merged["candidate"] = (
        merged["complete_features"]
        & merged["rank_pass"]
        & merged["momentum_pass"]
        & merged["relative_strength_pass"]
        & merged["pullback_pass"]
        & merged["ema_reclaim_pass"]
    )

    return (
        merged.sort_values(
            [
                "snapshot_time",
                "candidate",
                "rank_within_snapshot",
                "momentum_h02",
                "relative_strength_60d_h02",
                "composite_score",
                "symbol",
            ],
            ascending=[
                True,
                False,
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
        "exit_signal_time": (
            snapshot_time
        ),
        "entry_price": (
            position.entry_price
        ),
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


def build_aggressive_reacceleration_weights(
    history: pd.DataFrame,
    signals: pd.DataFrame,
    *,
    policy: AggressiveReaccelerationPolicy,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    prepared_history = _prepare_history(
        history
    )

    required = {
        "snapshot_time",
        "symbol",
        "rank_within_snapshot",
        "composite_score",
        "signal_close",
        "signal_high",
        "momentum_h02",
        "relative_strength_60d_h02",
        "atr_14_h02",
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
        for value
        in (
            prepared_signals[
                "snapshot_time"
            ]
            .drop_duplicates()
            .sort_values()
        )
    ]

    if not snapshots:
        raise (
            AggressiveReaccelerationConfigurationError(
                "No signal snapshots were supplied."
            )
        )

    symbols = sorted(
        prepared_signals[
            "symbol"
        ]
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

    weights: list[
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
                    row.atr_14_h02,
                )
            )
            for row
            in rows.itertuples(
                index=False
            )
            if pd.notna(
                cast(
                    Any,
                    row.atr_14_h02,
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
                            "DAILY_TRAILING_STOP"
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
                position.stop_price = max(
                    position.stop_price,
                    (
                        position.highest_high
                        - (
                            policy.trailing_stop_atr
                            * atr
                        )
                    ),
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
                        "momentum_h02",
                        (
                            "relative_strength_"
                            "60d_h02"
                        ),
                        "composite_score",
                        "symbol",
                    ],
                    ascending=[
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
                        row.atr_14_h02,
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

                positions[symbol] = (
                    _Position(
                        entry_signal_time=(
                            snapshot
                        ),
                        entry_price=entry_price,
                        highest_high=entry_high,
                        stop_price=max(
                            0.0,
                            (
                                entry_price
                                - (
                                    policy
                                    .trailing_stop_atr
                                    * entry_atr
                                )
                            ),
                        ),
                        last_close=entry_price,
                    )
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

            weights.append(
                {
                    "snapshot_time": (
                        snapshot
                    ),
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

    weight_frame = pd.DataFrame(
        weights
    )

    trade_frame = pd.DataFrame(
        trade_rows,
        columns=_TRADE_COLUMNS,
    )

    exposure = (
        weight_frame.groupby(
            "snapshot_time"
        )["target_weight"]
        .sum()
    )

    selected_counts = (
        weight_frame.groupby(
            "snapshot_time"
        )["selected"]
        .sum()
    )

    if (
        weight_frame["target_weight"]
        < 0.0
    ).any():
        raise (
            AggressiveReaccelerationConfigurationError(
                "Negative Spot weight was generated."
            )
        )

    if (
        exposure
        > 1.0 + 1e-12
    ).any():
        raise (
            AggressiveReaccelerationConfigurationError(
                "Spot exposure exceeded one."
            )
        )

    if (
        selected_counts
        > policy.maximum_positions
    ).any():
        raise (
            AggressiveReaccelerationConfigurationError(
                "Maximum position count was exceeded."
            )
        )

    return (
        weight_frame,
        trade_frame,
    )