from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime

import pandas as pd

__all__ = [
    "AssetRankingConfigurationError",
    "AssetRankingPolicy",
    "build_asset_ranking",
]


class AssetRankingConfigurationError(
    ValueError
):
    pass


def _require_aware_datetime(
    value: datetime,
    *,
    field_name: str,
) -> None:
    if (
        value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise AssetRankingConfigurationError(
            f"{field_name} must be "
            "timezone-aware."
        )


@dataclass(frozen=True, slots=True)
class AssetRankingPolicy:
    research_start: datetime
    research_end_exclusive: datetime
    benchmark_symbol: str = "BTC/USDT"
    momentum_short_days: int = 30
    momentum_long_days: int = 90
    volatility_days: int = 30
    turnover_short_days: int = 7
    turnover_long_days: int = 30
    drawdown_days: int = 90
    minimum_volatility_observations: int = 20
    minimum_turnover_short_observations: int = 5
    minimum_turnover_long_observations: int = 20
    minimum_drawdown_observations: int = 60
    minimum_cross_section_size: int = 5

    def __post_init__(self) -> None:
        _require_aware_datetime(
            self.research_start,
            field_name="research_start",
        )

        _require_aware_datetime(
            self.research_end_exclusive,
            field_name="research_end_exclusive",
        )

        if (
            self.research_end_exclusive
            <= self.research_start
        ):
            raise AssetRankingConfigurationError(
                "research_end_exclusive must "
                "be later than research_start."
            )

        normalized_benchmark = (
            self.benchmark_symbol
            .strip()
            .upper()
        )

        if not normalized_benchmark:
            raise AssetRankingConfigurationError(
                "benchmark_symbol cannot "
                "be empty."
            )

        object.__setattr__(
            self,
            "benchmark_symbol",
            normalized_benchmark,
        )

        positive_integer_fields = {
            "momentum_short_days": (
                self.momentum_short_days
            ),
            "momentum_long_days": (
                self.momentum_long_days
            ),
            "volatility_days": (
                self.volatility_days
            ),
            "turnover_short_days": (
                self.turnover_short_days
            ),
            "turnover_long_days": (
                self.turnover_long_days
            ),
            "drawdown_days": (
                self.drawdown_days
            ),
            "minimum_volatility_observations": (
                self.minimum_volatility_observations
            ),
            "minimum_turnover_short_observations": (
                self.minimum_turnover_short_observations
            ),
            "minimum_turnover_long_observations": (
                self.minimum_turnover_long_observations
            ),
            "minimum_drawdown_observations": (
                self.minimum_drawdown_observations
            ),
            "minimum_cross_section_size": (
                self.minimum_cross_section_size
            ),
        }

        for name, value in (
            positive_integer_fields.items()
        ):
            if value <= 0:
                raise AssetRankingConfigurationError(
                    f"{name} must be positive."
                )

        if (
            self.momentum_short_days
            >= self.momentum_long_days
        ):
            raise AssetRankingConfigurationError(
                "momentum_short_days must be "
                "smaller than momentum_long_days."
            )

        if (
            self.turnover_short_days
            >= self.turnover_long_days
        ):
            raise AssetRankingConfigurationError(
                "turnover_short_days must be "
                "smaller than turnover_long_days."
            )

        if (
            self.minimum_volatility_observations
            > self.volatility_days
        ):
            raise AssetRankingConfigurationError(
                "minimum_volatility_observations "
                "cannot exceed volatility_days."
            )

        if (
            self.minimum_turnover_short_observations
            > self.turnover_short_days
        ):
            raise AssetRankingConfigurationError(
                "minimum_turnover_short_observations "
                "cannot exceed turnover_short_days."
            )

        if (
            self.minimum_turnover_long_observations
            > self.turnover_long_days
        ):
            raise AssetRankingConfigurationError(
                "minimum_turnover_long_observations "
                "cannot exceed turnover_long_days."
            )

        if (
            self.minimum_drawdown_observations
            > self.drawdown_days
        ):
            raise AssetRankingConfigurationError(
                "minimum_drawdown_observations "
                "cannot exceed drawdown_days."
            )


def _require_columns(
    frame: pd.DataFrame,
    *,
    required: set[str],
    frame_name: str,
) -> None:
    missing = sorted(
        required
        - set(frame.columns)
    )

    if missing:
        raise AssetRankingConfigurationError(
            f"{frame_name} is missing "
            f"required columns: {missing}."
        )


def _prepare_history(
    history: pd.DataFrame,
) -> pd.DataFrame:
    _require_columns(
        history,
        required={
            "symbol",
            "close_time",
            "close",
            "quote_turnover",
        },
        frame_name="history",
    )

    prepared = history[
        [
            "symbol",
            "close_time",
            "close",
            "quote_turnover",
        ]
    ].copy()

    prepared["symbol"] = (
        prepared["symbol"]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    prepared["close_time"] = pd.to_datetime(
        prepared["close_time"],
        utc=True,
        errors="raise",
    )

    prepared["close"] = pd.to_numeric(
        prepared["close"],
        errors="raise",
    )

    prepared["quote_turnover"] = (
        pd.to_numeric(
            prepared["quote_turnover"],
            errors="raise",
        )
    )

    if prepared["symbol"].eq("").any():
        raise AssetRankingConfigurationError(
            "History contains an empty symbol."
        )

    if prepared[
        [
            "close",
            "quote_turnover",
        ]
    ].isna().any().any():
        raise AssetRankingConfigurationError(
            "History contains missing "
            "numeric values."
        )

    if (
        prepared["close"]
        <= 0
    ).any():
        raise AssetRankingConfigurationError(
            "History contains non-positive "
            "close prices."
        )

    if (
        prepared["quote_turnover"]
        < 0
    ).any():
        raise AssetRankingConfigurationError(
            "History contains negative "
            "quote turnover."
        )

    if prepared.duplicated(
        subset=[
            "symbol",
            "close_time",
        ]
    ).any():
        raise AssetRankingConfigurationError(
            "History contains duplicate "
            "symbol/close_time rows."
        )

    return (
        prepared.sort_values(
            [
                "symbol",
                "close_time",
            ]
        )
        .reset_index(drop=True)
    )


def _prepare_universe(
    universe: pd.DataFrame,
    *,
    policy: AssetRankingPolicy,
) -> pd.DataFrame:
    _require_columns(
        universe,
        required={
            "snapshot_time",
            "symbol",
            "eligible",
        },
        frame_name="universe",
    )

    prepared = universe[
        [
            "snapshot_time",
            "symbol",
            "eligible",
        ]
    ].copy()

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
        .str.strip()
        .str.upper()
    )

    prepared["eligible"] = (
        prepared["eligible"].astype(bool)
    )

    research_start = pd.Timestamp(
        policy.research_start
    )

    research_end = pd.Timestamp(
        policy.research_end_exclusive
    )

    prepared = prepared.loc[
        (
            prepared["snapshot_time"]
            >= research_start
        )
        & (
            prepared["snapshot_time"]
            < research_end
        )
    ]

    if prepared.duplicated(
        subset=[
            "snapshot_time",
            "symbol",
        ]
    ).any():
        raise AssetRankingConfigurationError(
            "Universe contains duplicate "
            "snapshot_time/symbol rows."
        )

    return (
        prepared.sort_values(
            [
                "snapshot_time",
                "symbol",
            ]
        )
        .reset_index(drop=True)
    )


def _compute_feature_history(
    history: pd.DataFrame,
    *,
    policy: AssetRankingPolicy,
) -> pd.DataFrame:
    feature_frames: list[
        pd.DataFrame
    ] = []

    for symbol, raw_group in history.groupby(
        "symbol",
        sort=True,
    ):
        group = (
            raw_group.sort_values(
                "close_time"
            )
            .reset_index(drop=True)
            .copy()
        )

        daily_return = (
            group["close"]
            .pct_change(
                fill_method=None
            )
        )

        group["return_30d"] = (
            group["close"]
            / group["close"].shift(
                policy.momentum_short_days
            )
            - 1.0
        )

        group["return_90d"] = (
            group["close"]
            / group["close"].shift(
                policy.momentum_long_days
            )
            - 1.0
        )

        group["volatility_30d"] = (
            daily_return.rolling(
                window=policy.volatility_days,
                min_periods=(
                    policy
                    .minimum_volatility_observations
                ),
            )
            .std(ddof=0)
            * math.sqrt(365.0)
        )

        short_turnover = (
            group["quote_turnover"]
            .rolling(
                window=(
                    policy.turnover_short_days
                ),
                min_periods=(
                    policy
                    .minimum_turnover_short_observations
                ),
            )
            .median()
        )

        long_turnover = (
            group["quote_turnover"]
            .rolling(
                window=(
                    policy.turnover_long_days
                ),
                min_periods=(
                    policy
                    .minimum_turnover_long_observations
                ),
            )
            .median()
        )

        group["turnover_expansion"] = (
            short_turnover
            / long_turnover.replace(
                0.0,
                float("nan"),
            )
        )

        rolling_high = (
            group["close"]
            .rolling(
                window=policy.drawdown_days,
                min_periods=(
                    policy
                    .minimum_drawdown_observations
                ),
            )
            .max()
        )

        group["drawdown_90d"] = (
            group["close"]
            / rolling_high
            - 1.0
        )

        group["symbol"] = str(symbol)

        feature_frames.append(
            group[
                [
                    "symbol",
                    "close_time",
                    "close",
                    "return_30d",
                    "return_90d",
                    "volatility_30d",
                    "turnover_expansion",
                    "drawdown_90d",
                ]
            ].rename(
                columns={
                    "close_time": (
                        "feature_time"
                    ),
                    "close": (
                        "feature_close"
                    ),
                }
            )
        )

    if not feature_frames:
        raise AssetRankingConfigurationError(
            "No feature history could be "
            "constructed."
        )

    return (
        pd.concat(
            feature_frames,
            ignore_index=True,
        )
        .sort_values(
            [
                "symbol",
                "feature_time",
            ]
        )
        .reset_index(drop=True)
    )


def _merge_features(
    eligible_universe: pd.DataFrame,
    feature_history: pd.DataFrame,
) -> pd.DataFrame:
    merged_frames: list[
        pd.DataFrame
    ] = []

    for symbol, raw_universe in (
        eligible_universe.groupby(
            "symbol",
            sort=True,
        )
    ):
        symbol_features = (
            feature_history.loc[
                feature_history["symbol"]
                == symbol
            ]
            .drop(
                columns=["symbol"]
            )
            .sort_values(
                "feature_time"
            )
        )

        if symbol_features.empty:
            continue

        symbol_universe = (
            raw_universe[
                [
                    "snapshot_time",
                    "symbol",
                ]
            ]
            .sort_values(
                "snapshot_time"
            )
        )

        merged = pd.merge_asof(
            symbol_universe,
            symbol_features,
            left_on="snapshot_time",
            right_on="feature_time",
            direction="backward",
            allow_exact_matches=True,
        )

        merged_frames.append(merged)

    if not merged_frames:
        raise AssetRankingConfigurationError(
            "No eligible universe rows could "
            "be matched to feature history."
        )

    return (
        pd.concat(
            merged_frames,
            ignore_index=True,
        )
        .sort_values(
            [
                "snapshot_time",
                "symbol",
            ]
        )
        .reset_index(drop=True)
    )


def _attach_benchmark(
    rows: pd.DataFrame,
    feature_history: pd.DataFrame,
    *,
    benchmark_symbol: str,
) -> pd.DataFrame:
    benchmark = (
        feature_history.loc[
            feature_history["symbol"]
            == benchmark_symbol,
            [
                "feature_time",
                "return_90d",
            ],
        ]
        .rename(
            columns={
                "feature_time": (
                    "benchmark_feature_time"
                ),
                "return_90d": (
                    "benchmark_return_90d"
                ),
            }
        )
        .sort_values(
            "benchmark_feature_time"
        )
    )

    if benchmark.empty:
        raise AssetRankingConfigurationError(
            "Benchmark history was not found: "
            f"{benchmark_symbol}."
        )

    left = rows.sort_values(
        [
            "snapshot_time",
            "symbol",
        ]
    )

    attached = pd.merge_asof(
        left,
        benchmark,
        left_on="snapshot_time",
        right_on="benchmark_feature_time",
        direction="backward",
        allow_exact_matches=True,
    )

    return attached


def build_asset_ranking(
    history: pd.DataFrame,
    universe: pd.DataFrame,
    *,
    policy: AssetRankingPolicy,
) -> pd.DataFrame:
    prepared_history = _prepare_history(
        history
    )

    prepared_universe = _prepare_universe(
        universe,
        policy=policy,
    )

    eligible_universe = (
        prepared_universe.loc[
            prepared_universe["eligible"]
        ]
        .drop(columns=["eligible"])
        .copy()
    )

    if eligible_universe.empty:
        raise AssetRankingConfigurationError(
            "The universe contains no "
            "eligible rows."
        )

    feature_history = (
        _compute_feature_history(
            prepared_history,
            policy=policy,
        )
    )

    merged = _merge_features(
        eligible_universe,
        feature_history,
    )

    merged = _attach_benchmark(
        merged,
        feature_history,
        benchmark_symbol=(
            policy.benchmark_symbol
        ),
    )

    merged["relative_strength_90d"] = (
        merged["return_90d"]
        - merged["benchmark_return_90d"]
    )

    required_features = [
        "feature_time",
        "benchmark_feature_time",
        "feature_close",
        "return_30d",
        "return_90d",
        "benchmark_return_90d",
        "relative_strength_90d",
        "volatility_30d",
        "turnover_expansion",
        "drawdown_90d",
    ]

    complete = (
        merged[
            required_features
        ]
        .notna()
        .all(axis=1)
    )

    causal = (
        merged["feature_time"]
        <= merged["snapshot_time"]
    ) & (
        merged["benchmark_feature_time"]
        <= merged["snapshot_time"]
    )

    rankable = (
        merged.loc[
            complete & causal
        ]
        .copy()
        .sort_values(
            [
                "snapshot_time",
                "symbol",
            ]
        )
        .reset_index(drop=True)
    )

    if rankable.empty:
        raise AssetRankingConfigurationError(
            "No complete causal feature rows "
            "were available for ranking."
        )

    rankable[
        "cross_section_size"
    ] = (
        rankable.groupby(
            "snapshot_time"
        )["symbol"]
        .transform("size")
        .astype("int64")
    )

    rankable = rankable.loc[
        rankable["cross_section_size"]
        >= policy.minimum_cross_section_size
    ].copy()

    if rankable.empty:
        raise AssetRankingConfigurationError(
            "No snapshot met the minimum "
            "cross-section size."
        )

    score_inputs = {
        "momentum_30_score": (
            "return_30d"
        ),
        "momentum_90_score": (
            "return_90d"
        ),
        "relative_strength_score": (
            "relative_strength_90d"
        ),
        "turnover_expansion_score": (
            "turnover_expansion"
        ),
        "drawdown_recovery_score": (
            "drawdown_90d"
        ),
    }

    for score_column, value_column in (
        score_inputs.items()
    ):
        rankable[score_column] = (
            rankable.groupby(
                "snapshot_time"
            )[value_column]
            .rank(
                method="average",
                ascending=True,
                pct=True,
            )
        )

    rankable["composite_score"] = (
        0.25
        * rankable[
            "momentum_30_score"
        ]
        + 0.30
        * rankable[
            "momentum_90_score"
        ]
        + 0.20
        * rankable[
            "relative_strength_score"
        ]
        + 0.15
        * rankable[
            "turnover_expansion_score"
        ]
        + 0.10
        * rankable[
            "drawdown_recovery_score"
        ]
    )

    rankable = rankable.sort_values(
        [
            "snapshot_time",
            "composite_score",
            "symbol",
        ],
        ascending=[
            True,
            False,
            True,
        ],
    ).reset_index(drop=True)

    rankable["rank_within_snapshot"] = (
        rankable.groupby(
            "snapshot_time"
        )["composite_score"]
        .rank(
            method="first",
            ascending=False,
        )
        .astype("int64")
    )

    rankable["top_5"] = (
        rankable[
            "rank_within_snapshot"
        ]
        <= 5
    )

    rankable["top_10"] = (
        rankable[
            "rank_within_snapshot"
        ]
        <= 10
    )

    columns = [
        "snapshot_time",
        "symbol",
        "feature_time",
        "benchmark_feature_time",
        "feature_close",
        "return_30d",
        "return_90d",
        "benchmark_return_90d",
        "relative_strength_90d",
        "volatility_30d",
        "turnover_expansion",
        "drawdown_90d",
        "momentum_30_score",
        "momentum_90_score",
        "relative_strength_score",
        "turnover_expansion_score",
        "drawdown_recovery_score",
        "composite_score",
        "cross_section_size",
        "rank_within_snapshot",
        "top_5",
        "top_10",
    ]

    return (
        rankable[columns]
        .sort_values(
            [
                "snapshot_time",
                "rank_within_snapshot",
                "symbol",
            ]
        )
        .reset_index(drop=True)
    )
