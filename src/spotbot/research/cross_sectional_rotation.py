from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, cast

import pandas as pd


class CrossSectionalRotationConfigurationError(
    ValueError
):
    pass


@dataclass(frozen=True, slots=True)
class CrossSectionalRotationPolicy:
    research_start: datetime
    research_end_exclusive: datetime
    ranking_return_days: int = 14
    ranking_relative_strength_days: int = 30
    ranking_turnover_days: int = 7
    minimum_liquidity_rank_percentile: float = 0.5
    minimum_rank_improvement: int = 3
    maximum_positions: int = 2
    rebalance_frequency: str = "EVERY_3_DAYS"
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
                    CrossSectionalRotationConfigurationError(
                        f"{name} must be timezone-aware."
                    )
                )

        if (
            self.research_end_exclusive
            <= self.research_start
        ):
            raise (
                CrossSectionalRotationConfigurationError(
                    "Invalid research range."
                )
            )

        integer_fields = (
            self.ranking_return_days,
            self.ranking_relative_strength_days,
            self.ranking_turnover_days,
            self.minimum_rank_improvement,
            self.maximum_positions,
        )

        if any(
            value <= 0
            for value in integer_fields
        ):
            raise (
                CrossSectionalRotationConfigurationError(
                    "Integer policy fields must be positive."
                )
            )

        if not (
            0.0
            <= self.minimum_liquidity_rank_percentile
            <= 1.0
        ):
            raise (
                CrossSectionalRotationConfigurationError(
                    "minimum_liquidity_rank_percentile "
                    "must be in [0, 1]."
                )
            )

        frequency = (
            self.rebalance_frequency
            .strip()
            .upper()
        )

        if frequency != "EVERY_3_DAYS":
            raise (
                CrossSectionalRotationConfigurationError(
                    "H04 requires EVERY_3_DAYS "
                    "rebalancing."
                )
            )

        object.__setattr__(
            self,
            "rebalance_frequency",
            frequency,
        )

        if (
            self.transaction_cost_fraction
            < 0.0
        ):
            raise (
                CrossSectionalRotationConfigurationError(
                    "transaction_cost_fraction cannot "
                    "be negative."
                )
            )


@dataclass(slots=True)
class _Position:
    entry_signal_time: pd.Timestamp
    entry_price: float
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
            CrossSectionalRotationConfigurationError(
                f"{frame_name} is missing columns: "
                f"{missing}."
            )
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

            is_quote_activity = (
                "quote" in normalised
                and (
                    "turnover" in normalised
                    or "volume" in normalised
                    or normalised.endswith("vol")
                )
            )

            if is_quote_activity:
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

    raise (
        CrossSectionalRotationConfigurationError(
            "History lacks a supported turnover "
            "or volume column. "
            f"Available columns: {available}."
        )
    )


def _prepare_history(
    history: pd.DataFrame,
) -> pd.DataFrame:
    required = {
        "symbol",
        "close_time",
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

    result["close"] = pd.to_numeric(
        result["close"],
        errors="raise",
    )

    result["turnover"] = pd.to_numeric(
        result["turnover"],
        errors="raise",
    )

    if result.duplicated(
        [
            "symbol",
            "close_time",
        ]
    ).any():
        raise (
            CrossSectionalRotationConfigurationError(
                "Duplicate history symbol/close_time rows."
            )
        )

    if (
        result["close"]
        <= 0.0
    ).any():
        raise (
            CrossSectionalRotationConfigurationError(
                "History closes must exceed zero."
            )
        )

    if (
        result["turnover"]
        < 0.0
    ).any():
        raise (
            CrossSectionalRotationConfigurationError(
                "History turnover cannot be negative."
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
    policy: CrossSectionalRotationPolicy,
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
        raise (
            CrossSectionalRotationConfigurationError(
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
    policy: CrossSectionalRotationPolicy,
) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []

    for symbol, raw_group in history.groupby(
        "symbol",
        sort=True,
    ):
        group = (
            raw_group
            .sort_values("close_time")
            .reset_index(drop=True)
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
                    "return_14_h04": (
                        group["close"]
                        / group["close"].shift(
                            policy.ranking_return_days
                        )
                        - 1.0
                    ),
                    "return_30_h04": (
                        group["close"]
                        / group["close"].shift(
                            policy
                            .ranking_relative_strength_days
                        )
                        - 1.0
                    ),
                    "turnover_7_h04": (
                        group["turnover"]
                        .rolling(
                            policy.ranking_turnover_days,
                            min_periods=(
                                policy.ranking_turnover_days
                            ),
                        )
                        .mean()
                    ),
                }
            )
        )

    if not frames:
        raise (
            CrossSectionalRotationConfigurationError(
                "No H04 features were constructed."
            )
        )

    return pd.concat(
        frames,
        ignore_index=True,
    )


def _add_cross_sectional_ranks(
    frame: pd.DataFrame,
) -> pd.DataFrame:
    result = frame.copy()

    result["complete_features"] = (
        result[
            [
                "signal_close",
                "return_14_h04",
                "return_30_h04",
                "turnover_7_h04",
            ]
        ]
        .notna()
        .all(axis=1)
    )

    result[
        "return_rank_percentile_h04"
    ] = float("nan")

    result[
        "relative_strength_rank_percentile_h04"
    ] = float("nan")

    result[
        "liquidity_rank_percentile_h04"
    ] = float("nan")

    result["leadership_score_h04"] = float(
        "nan"
    )

    result["leadership_rank_h04"] = float(
        "nan"
    )

    for _, group in result.groupby(
        "snapshot_time",
        sort=True,
    ):
        valid = group.loc[
            group["complete_features"]
        ]

        if valid.empty:
            continue

        short_percentile = (
            valid["return_14_h04"]
            .rank(
                ascending=True,
                method="average",
                pct=True,
            )
        )

        relative_percentile = (
            valid["return_30_h04"]
            .rank(
                ascending=True,
                method="average",
                pct=True,
            )
        )

        liquidity_percentile = (
            valid["turnover_7_h04"]
            .rank(
                ascending=True,
                method="average",
                pct=True,
            )
        )

        result.loc[
            valid.index,
            "return_rank_percentile_h04",
        ] = short_percentile

        result.loc[
            valid.index,
            (
                "relative_strength_"
                "rank_percentile_h04"
            ),
        ] = relative_percentile

        result.loc[
            valid.index,
            "liquidity_rank_percentile_h04",
        ] = liquidity_percentile

        score = (
            short_percentile
            + relative_percentile
            + liquidity_percentile
        ) / 3.0

        result.loc[
            valid.index,
            "leadership_score_h04",
        ] = score

        ordered = (
            result.loc[
                valid.index
            ]
            .assign(
                _leadership_score=score
            )
            .sort_values(
                [
                    "_leadership_score",
                    "composite_score",
                    "symbol",
                ],
                ascending=[
                    False,
                    False,
                    True,
                ],
            )
        )

        result.loc[
            ordered.index,
            "leadership_rank_h04",
        ] = range(
            1,
            len(ordered) + 1,
        )

    return result


def _add_rebalance_state(
    frame: pd.DataFrame,
) -> pd.DataFrame:
    result = frame.copy()

    snapshots = [
        pd.Timestamp(
            cast(
                Any,
                value,
            )
        )
        for value in (
            result["snapshot_time"]
            .drop_duplicates()
            .sort_values()
        )
    ]

    rebalance_map = {
        snapshot: (
            index % 3 == 0
        )
        for index, snapshot
        in enumerate(snapshots)
    }

    result["rebalance_day"] = (
        result["snapshot_time"]
        .map(rebalance_map)
        .astype(bool)
    )

    previous = result[
        [
            "snapshot_time",
            "symbol",
            "leadership_rank_h04",
        ]
    ].copy()

    previous["snapshot_time"] = (
        previous["snapshot_time"]
        + pd.Timedelta(days=3)
    )

    previous = previous.rename(
        columns={
            "leadership_rank_h04": (
                "previous_rebalance_"
                "leadership_rank_h04"
            )
        }
    )

    result = result.merge(
        previous,
        on=[
            "snapshot_time",
            "symbol",
        ],
        how="left",
        validate="one_to_one",
    )

    result["rank_improvement_h04"] = (
        result[
            (
                "previous_rebalance_"
                "leadership_rank_h04"
            )
        ]
        - result["leadership_rank_h04"]
    )

    return result


def build_cross_sectional_rotation_signals(
    history: pd.DataFrame,
    ranking: pd.DataFrame,
    *,
    policy: CrossSectionalRotationPolicy,
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

    merged = _add_cross_sectional_ranks(
        merged
    )

    merged = _add_rebalance_state(
        merged
    )

    merged["liquidity_pass"] = (
        merged[
            "liquidity_rank_percentile_h04"
        ]
        >= (
            policy
            .minimum_liquidity_rank_percentile
        )
    )

    merged["rank_improvement_pass"] = (
        merged["rank_improvement_h04"]
        >= policy.minimum_rank_improvement
    )

    merged["candidate"] = (
        merged["complete_features"]
        & merged["rebalance_day"]
        & merged["liquidity_pass"]
        & merged["rank_improvement_pass"]
    )

    return (
        merged.sort_values(
            [
                "snapshot_time",
                "candidate",
                "leadership_rank_h04",
                "rank_improvement_h04",
                "leadership_score_h04",
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


def build_cross_sectional_rotation_weights(
    signals: pd.DataFrame,
    *,
    policy: CrossSectionalRotationPolicy,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    required = {
        "snapshot_time",
        "symbol",
        "signal_close",
        "composite_score",
        "leadership_score_h04",
        "leadership_rank_h04",
        "rank_improvement_h04",
        "candidate",
        "rebalance_day",
    }

    _require_columns(
        signals,
        required=required,
        frame_name="signals",
    )

    prepared = signals.copy()

    prepared["snapshot_time"] = pd.to_datetime(
        prepared["snapshot_time"],
        utc=True,
        errors="raise",
    )

    prepared["symbol"] = (
        prepared["symbol"]
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
            prepared["snapshot_time"]
            .drop_duplicates()
            .sort_values()
        )
    ]

    if not snapshots:
        raise (
            CrossSectionalRotationConfigurationError(
                "No H04 signal snapshots were supplied."
            )
        )

    symbols = sorted(
        prepared["symbol"]
        .drop_duplicates()
        .tolist()
    )

    groups = {
        pd.Timestamp(
            cast(
                Any,
                snapshot,
            )
        ): group
        for snapshot, group
        in prepared.groupby(
            "snapshot_time",
            sort=True,
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
        rows = groups[snapshot]

        current_closes = {
            str(
                cast(
                    Any,
                    row.symbol,
                )
            ): float(
                cast(
                    Any,
                    row.signal_close,
                )
            )
            for row
            in rows.itertuples(
                index=False
            )
            if pd.notna(
                cast(
                    Any,
                    row.signal_close,
                )
            )
        }

        for symbol in list(
            positions
        ):
            position = positions[symbol]

            close = current_closes.get(
                symbol
            )

            if close is None:
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

            position.last_close = close

        is_rebalance = bool(
            rows["rebalance_day"].iloc[0]
        )

        if snapshot == final_snapshot:
            for symbol in list(
                positions
            ):
                position = positions[symbol]

                trade_rows.append(
                    _trade_record(
                        symbol=symbol,
                        position=position,
                        snapshot_time=snapshot,
                        exit_price=(
                            position.last_close
                        ),
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

        elif is_rebalance:
            candidates = (
                rows.loc[
                    rows["candidate"]
                    .astype(bool)
                ]
                .sort_values(
                    [
                        "leadership_rank_h04",
                        "rank_improvement_h04",
                        "leadership_score_h04",
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
                .head(
                    policy.maximum_positions
                )
            )

            desired = set(
                candidates[
                    "symbol"
                ].astype(str)
            )

            for symbol in list(
                positions
            ):
                if symbol in desired:
                    continue

                position = positions[symbol]

                trade_rows.append(
                    _trade_record(
                        symbol=symbol,
                        position=position,
                        snapshot_time=snapshot,
                        exit_price=(
                            position.last_close
                        ),
                        exit_reason=(
                            "ROTATION_EXIT"
                        ),
                        transaction_cost_fraction=(
                            policy
                            .transaction_cost_fraction
                        ),
                    )
                )

                del positions[symbol]

            for row in candidates.itertuples(
                index=False
            ):
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

                if entry_price <= 0.0:
                    continue

                positions[symbol] = _Position(
                    entry_signal_time=snapshot,
                    entry_price=entry_price,
                    last_close=entry_price,
                )

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
                    "rebalance_day": (
                        is_rebalance
                    ),
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
        raise (
            CrossSectionalRotationConfigurationError(
                "Negative Spot weight was generated."
            )
        )

    if (
        exposure
        > 1.0 + 1e-12
    ).any():
        raise (
            CrossSectionalRotationConfigurationError(
                "Spot exposure exceeded one."
            )
        )

    if (
        position_counts
        > policy.maximum_positions
    ).any():
        raise (
            CrossSectionalRotationConfigurationError(
                "Maximum position count was exceeded."
            )
        )

    return (
        weights,
        trades,
    )