from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Any, cast

import pandas as pd


class VolatilityBreakoutConfigurationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class VolatilityBreakoutPolicy:
    research_start: datetime
    research_end_exclusive: datetime
    ranking_maximum: int = 8
    maximum_positions: int = 2
    breakout_lookback_days: int = 20
    turnover_expansion_minimum: float = 1.5
    atr_expansion_minimum: float = 1.2
    atr_days: int = 14
    initial_stop_atr: float = 2.5
    trailing_stop_atr: float = 3.5
    maximum_holding_days: int = 45
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
                raise VolatilityBreakoutConfigurationError(
                    f"{name} must be timezone-aware."
                )

        if (
            self.research_end_exclusive
            <= self.research_start
        ):
            raise VolatilityBreakoutConfigurationError(
                "Invalid research range."
            )

        integers = (
            self.ranking_maximum,
            self.maximum_positions,
            self.breakout_lookback_days,
            self.atr_days,
            self.maximum_holding_days,
        )

        if any(
            value <= 0
            for value in integers
        ):
            raise VolatilityBreakoutConfigurationError(
                "Integer policy fields must be positive."
            )

        if (
            self.maximum_positions
            > self.ranking_maximum
        ):
            raise VolatilityBreakoutConfigurationError(
                "maximum_positions cannot exceed "
                "ranking_maximum."
            )

        positives = (
            self.turnover_expansion_minimum,
            self.atr_expansion_minimum,
            self.initial_stop_atr,
            self.trailing_stop_atr,
        )

        if any(
            value <= 0.0
            for value in positives
        ):
            raise VolatilityBreakoutConfigurationError(
                "Positive policy fields must exceed zero."
            )

        if (
            self.transaction_cost_fraction
            < 0.0
        ):
            raise VolatilityBreakoutConfigurationError(
                "transaction_cost_fraction cannot "
                "be negative."
            )


@dataclass(slots=True)
class _Position:
    entry_time: pd.Timestamp
    entry_price: float
    highest_high: float
    stop_price: float
    last_close: float


def _require(
    frame: pd.DataFrame,
    required: set[str],
    name: str,
) -> None:
    missing = sorted(
        required - set(frame.columns)
    )

    if missing:
        raise VolatilityBreakoutConfigurationError(
            f"{name} is missing columns: {missing}."
        )


def _history(
    frame: pd.DataFrame,
) -> pd.DataFrame:
    columns = [
        "symbol",
        "open_time",
        "close_time",
        "open",
        "high",
        "low",
        "close",
        "quote_turnover",
    ]

    _require(
        frame,
        set(columns),
        "history",
    )

    result = frame[columns].copy()

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
        "quote_turnover",
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
        raise VolatilityBreakoutConfigurationError(
            "Duplicate history symbol/close_time rows."
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


def _ranking(
    frame: pd.DataFrame,
    policy: VolatilityBreakoutPolicy,
) -> pd.DataFrame:
    columns = [
        "snapshot_time",
        "symbol",
        "composite_score",
        "rank_within_snapshot",
    ]

    _require(
        frame,
        set(columns),
        "ranking",
    )

    result = frame[columns].copy()

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
        raise VolatilityBreakoutConfigurationError(
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


def _features(
    history: pd.DataFrame,
    policy: VolatilityBreakoutPolicy,
) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []

    for symbol, raw in history.groupby(
        "symbol",
        sort=True,
    ):
        group = (
            raw.sort_values("close_time")
            .reset_index(drop=True)
        )

        previous_close = (
            group["close"].shift(1)
        )

        true_range = pd.concat(
            [
                group["high"]
                - group["low"],
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

        prior_high = (
            group["high"]
            .shift(1)
            .rolling(
                policy.breakout_lookback_days
            )
            .max()
        )

        prior_turnover = (
            group["quote_turnover"]
            .shift(1)
            .rolling(
                policy.breakout_lookback_days
            )
            .median()
        )

        prior_atr = (
            true_range
            .shift(1)
            .rolling(policy.atr_days)
            .mean()
        )

        current_atr = (
            true_range
            .rolling(policy.atr_days)
            .mean()
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
                    "prior_breakout_high": (
                        prior_high
                    ),
                    "turnover_expansion_h01": (
                        group["quote_turnover"]
                        / prior_turnover.replace(
                            0.0,
                            float("nan"),
                        )
                    ),
                    "atr_expansion_h01": (
                        true_range
                        / prior_atr.replace(
                            0.0,
                            float("nan"),
                        )
                    ),
                    "atr_h01": current_atr,
                    "breakout_strength": (
                        group["close"]
                        / prior_high
                        - 1.0
                    ),
                }
            )
        )

    if not frames:
        raise VolatilityBreakoutConfigurationError(
            "No features constructed."
        )

    return pd.concat(
        frames,
        ignore_index=True,
    )


def build_volatility_breakout_signals(
    history: pd.DataFrame,
    ranking: pd.DataFrame,
    *,
    policy: VolatilityBreakoutPolicy,
) -> pd.DataFrame:
    merged = _ranking(
        ranking,
        policy,
    ).merge(
        _features(
            _history(history),
            policy,
        ),
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
        "prior_breakout_high",
        "turnover_expansion_h01",
        "atr_expansion_h01",
        "atr_h01",
        "breakout_strength",
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

    merged["price_breakout_pass"] = (
        merged["signal_close"]
        > merged["prior_breakout_high"]
    )

    merged["turnover_expansion_pass"] = (
        merged["turnover_expansion_h01"]
        >= policy.turnover_expansion_minimum
    )

    merged["atr_expansion_pass"] = (
        merged["atr_expansion_h01"]
        >= policy.atr_expansion_minimum
    )

    merged["candidate"] = (
        merged["complete_features"]
        & merged["rank_pass"]
        & merged["price_breakout_pass"]
        & merged["turnover_expansion_pass"]
        & merged["atr_expansion_pass"]
    )

    return (
        merged.sort_values(
            [
                "snapshot_time",
                "candidate",
                "rank_within_snapshot",
                "breakout_strength",
                "turnover_expansion_h01",
                "symbol",
            ],
            ascending=[
                True,
                False,
                True,
                False,
                False,
                True,
            ],
        )
        .reset_index(drop=True)
    )


def _trade(
    symbol: str,
    position: _Position,
    snapshot: pd.Timestamp,
    exit_price: float,
    reason: str,
    cost: float,
) -> dict[str, object]:
    net_return = (
        exit_price
        * (
            1.0
            - cost
        )
        / (
            position.entry_price
            * (
                1.0
                + cost
            )
        )
        - 1.0
    )

    return {
        "symbol": symbol,
        "entry_signal_time": (
            position.entry_time
        ),
        "exit_signal_time": snapshot,
        "entry_price": (
            position.entry_price
        ),
        "exit_price": exit_price,
        "net_trade_return_after_round_trip_cost": (
            net_return
        ),
        "holding_days": int(
            (
                snapshot
                - position.entry_time
            ).days
        ),
        "exit_reason": reason,
    }


def build_volatility_breakout_weights(
    history: pd.DataFrame,
    signals: pd.DataFrame,
    *,
    policy: VolatilityBreakoutPolicy,
) -> tuple[
    pd.DataFrame,
    pd.DataFrame,
]:
    prepared_history = _history(
        history
    )

    required = {
        "snapshot_time",
        "symbol",
        "rank_within_snapshot",
        "signal_close",
        "signal_high",
        "signal_low",
        "breakout_strength",
        "turnover_expansion_h01",
        "atr_expansion_h01",
        "atr_h01",
        "candidate",
    }

    _require(
        signals,
        required,
        "signals",
    )

    prepared = signals.copy()

    prepared["snapshot_time"] = (
        pd.to_datetime(
            prepared["snapshot_time"],
            utc=True,
            errors="raise",
        )
    )

    prepared["symbol"] = (
        prepared["symbol"]
        .astype(str)
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
            prepared[
                "snapshot_time"
            ]
            .drop_duplicates()
            .sort_values()
        )
    ]

    symbols = sorted(
        prepared["symbol"]
        .unique()
        .tolist()
    )

    groups = {
        pd.Timestamp(
            cast(
                Any,
                key,
            )
        ): rows
        for key, rows
        in prepared.groupby(
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

    trades: list[
        dict[str, object]
    ] = []

    final_snapshot = snapshots[-1]

    for snapshot in snapshots:
        rows = groups[snapshot]

        current_symbols = set(
            rows["symbol"].tolist()
        )

        atrs = {
            str(
                cast(
                    Any,
                    row.symbol,
                )
            ): float(
                cast(
                    Any,
                    row.atr_h01,
                )
            )
            for row
            in rows.itertuples(
                index=False
            )
            if pd.notna(
                cast(
                    Any,
                    row.atr_h01,
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
                trades.append(
                    _trade(
                        symbol,
                        position,
                        snapshot,
                        position.last_close,
                        "UNIVERSE_OR_DATA_EXIT",
                        (
                            policy
                            .transaction_cost_fraction
                        ),
                    )
                )

                del positions[symbol]
                continue

            high, low, close = bar

            holding_days = int(
                (
                    snapshot
                    - position.entry_time
                ).days
            )

            if (
                low
                <= position.stop_price
            ):
                trades.append(
                    _trade(
                        symbol,
                        position,
                        snapshot,
                        close,
                        "DAILY_STOP_TRIGGER",
                        (
                            policy
                            .transaction_cost_fraction
                        ),
                    )
                )

                del positions[symbol]
                continue

            if (
                holding_days
                >= policy.maximum_holding_days
            ):
                trades.append(
                    _trade(
                        symbol,
                        position,
                        snapshot,
                        close,
                        "MAXIMUM_HOLDING_DAYS",
                        (
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

            atr = atrs.get(
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
                            policy
                            .trailing_stop_atr
                            * atr
                        )
                    ),
                    0.0,
                )

        if (
            snapshot
            == final_snapshot
        ):
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

                trades.append(
                    _trade(
                        symbol,
                        position,
                        snapshot,
                        exit_price,
                        "END_OF_RESEARCH",
                        (
                            policy
                            .transaction_cost_fraction
                        ),
                    )
                )

                del positions[symbol]

        else:
            slots = (
                policy.maximum_positions
                - len(positions)
            )

            candidates = (
                rows.loc[
                    rows[
                        "candidate"
                    ].astype(bool)
                ]
                .sort_values(
                    [
                        "rank_within_snapshot",
                        "breakout_strength",
                        "turnover_expansion_h01",
                        "atr_expansion_h01",
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
                if slots <= 0:
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
                        row.atr_h01,
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
                        entry_time=snapshot,
                        entry_price=(
                            entry_price
                        ),
                        highest_high=(
                            entry_high
                        ),
                        stop_price=max(
                            0.0,
                            (
                                entry_price
                                - (
                                    policy
                                    .initial_stop_atr
                                    * entry_atr
                                )
                            ),
                        ),
                        last_close=(
                            entry_price
                        ),
                    )
                )

                slots -= 1

        count = len(positions)

        equal_weight = (
            1.0 / count
            if count
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
                        equal_weight
                        if selected
                        else 0.0
                    ),
                    "selected": selected,
                    "rebalance_day": True,
                }
            )

    weight_frame = (
        pd.DataFrame(weights)
    )

    exposure = (
        weight_frame.groupby(
            "snapshot_time"
        )["target_weight"]
        .sum()
    )

    counts = (
        weight_frame.groupby(
            "snapshot_time"
        )["selected"]
        .sum()
    )

    if (
        weight_frame[
            "target_weight"
        ]
        < 0.0
    ).any():
        raise VolatilityBreakoutConfigurationError(
            "Negative Spot weight."
        )

    if (
        exposure
        > 1.0 + 1e-12
    ).any():
        raise VolatilityBreakoutConfigurationError(
            "Exposure exceeded one."
        )

    if (
        counts
        > policy.maximum_positions
    ).any():
        raise VolatilityBreakoutConfigurationError(
            "Maximum position count exceeded."
        )

    return (
        weight_frame,
        pd.DataFrame(trades),
    )