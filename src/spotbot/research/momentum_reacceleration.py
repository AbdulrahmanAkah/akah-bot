from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import pandas as pd

__all__ = [
    "MomentumReaccelerationConfigurationError",
    "MomentumReaccelerationPolicy",
    "build_momentum_reacceleration_signals",
    "build_target_weights",
    "run_daily_portfolio_backtest",
]


class MomentumReaccelerationConfigurationError(
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
        raise (
            MomentumReaccelerationConfigurationError(
                f"{field_name} must be "
                "timezone-aware."
            )
        )


@dataclass(frozen=True, slots=True)
class MomentumReaccelerationPolicy:
    research_start: datetime
    research_end_exclusive: datetime
    benchmark_symbol: str = "BTC/USDT"
    maximum_rank: int = 10
    maximum_positions: int = 5
    rebalance_weekday: int = 0
    momentum_days: int = 5
    ema_days: int = 20
    trend_days: int = 200
    regime_fast_days: int = 50
    regime_slow_days: int = 200
    rolling_high_days: int = 60
    atr_days: int = 14
    minimum_momentum_5d: float = 0.01
    minimum_return_90d: float = 0.0
    minimum_relative_strength_90d: float = -0.05
    maximum_pullback_from_high: float = 0.20
    minimum_atr_fraction: float = 0.005
    maximum_atr_fraction: float = 0.20
    transaction_cost_fraction: float = 0.002

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
            raise (
                MomentumReaccelerationConfigurationError(
                    "research_end_exclusive must "
                    "be later than research_start."
                )
            )

        benchmark = (
            self.benchmark_symbol
            .strip()
            .upper()
        )

        if not benchmark:
            raise (
                MomentumReaccelerationConfigurationError(
                    "benchmark_symbol cannot "
                    "be empty."
                )
            )

        object.__setattr__(
            self,
            "benchmark_symbol",
            benchmark,
        )

        positive_integer_fields = {
            "maximum_rank": self.maximum_rank,
            "maximum_positions": (
                self.maximum_positions
            ),
            "momentum_days": self.momentum_days,
            "ema_days": self.ema_days,
            "trend_days": self.trend_days,
            "regime_fast_days": (
                self.regime_fast_days
            ),
            "regime_slow_days": (
                self.regime_slow_days
            ),
            "rolling_high_days": (
                self.rolling_high_days
            ),
            "atr_days": self.atr_days,
        }

        for name, value in (
            positive_integer_fields.items()
        ):
            if value <= 0:
                raise (
                    MomentumReaccelerationConfigurationError(
                        f"{name} must be positive."
                    )
                )

        if not 0 <= self.rebalance_weekday <= 6:
            raise (
                MomentumReaccelerationConfigurationError(
                    "rebalance_weekday must be "
                    "between 0 and 6."
                )
            )

        if (
            self.maximum_positions
            > self.maximum_rank
        ):
            raise (
                MomentumReaccelerationConfigurationError(
                    "maximum_positions cannot "
                    "exceed maximum_rank."
                )
            )

        if (
            self.regime_fast_days
            >= self.regime_slow_days
        ):
            raise (
                MomentumReaccelerationConfigurationError(
                    "regime_fast_days must be "
                    "smaller than "
                    "regime_slow_days."
                )
            )

        if not (
            0.0
            < self.maximum_pullback_from_high
            < 1.0
        ):
            raise (
                MomentumReaccelerationConfigurationError(
                    "maximum_pullback_from_high "
                    "must be between zero and one."
                )
            )

        if not (
            0.0
            <= self.minimum_atr_fraction
            < self.maximum_atr_fraction
        ):
            raise (
                MomentumReaccelerationConfigurationError(
                    "ATR fraction boundaries "
                    "are invalid."
                )
            )

        if (
            self.transaction_cost_fraction
            < 0.0
        ):
            raise (
                MomentumReaccelerationConfigurationError(
                    "transaction_cost_fraction "
                    "cannot be negative."
                )
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
        raise (
            MomentumReaccelerationConfigurationError(
                f"{frame_name} is missing "
                f"required columns: {missing}."
            )
        )


def _prepare_history(
    history: pd.DataFrame,
) -> pd.DataFrame:
    _require_columns(
        history,
        required={
            "symbol",
            "close_time",
            "high",
            "low",
            "close",
        },
        frame_name="history",
    )

    prepared = history[
        [
            "symbol",
            "close_time",
            "high",
            "low",
            "close",
        ]
    ].copy()

    prepared["symbol"] = (
        prepared["symbol"]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    prepared["close_time"] = (
        pd.to_datetime(
            prepared["close_time"],
            utc=True,
            errors="raise",
        )
    )

    for column in (
        "high",
        "low",
        "close",
    ):
        prepared[column] = pd.to_numeric(
            prepared[column],
            errors="raise",
        )

    if prepared["symbol"].eq("").any():
        raise (
            MomentumReaccelerationConfigurationError(
                "History contains an empty "
                "symbol."
            )
        )

    if prepared[
        [
            "high",
            "low",
            "close",
        ]
    ].isna().any().any():
        raise (
            MomentumReaccelerationConfigurationError(
                "History contains missing "
                "price values."
            )
        )

    if (
        prepared[
            [
                "high",
                "low",
                "close",
            ]
        ]
        <= 0.0
    ).any().any():
        raise (
            MomentumReaccelerationConfigurationError(
                "History contains non-positive "
                "price values."
            )
        )

    if prepared.duplicated(
        subset=[
            "symbol",
            "close_time",
        ]
    ).any():
        raise (
            MomentumReaccelerationConfigurationError(
                "History contains duplicate "
                "symbol/close_time rows."
            )
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


def _prepare_ranking(
    ranking: pd.DataFrame,
    *,
    policy: MomentumReaccelerationPolicy,
) -> pd.DataFrame:
    _require_columns(
        ranking,
        required={
            "snapshot_time",
            "symbol",
            "return_90d",
            "relative_strength_90d",
            "composite_score",
            "rank_within_snapshot",
        },
        frame_name="ranking",
    )

    prepared = ranking[
        [
            "snapshot_time",
            "symbol",
            "return_90d",
            "relative_strength_90d",
            "composite_score",
            "rank_within_snapshot",
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

    numeric_columns = [
        "return_90d",
        "relative_strength_90d",
        "composite_score",
        "rank_within_snapshot",
    ]

    for column in numeric_columns:
        prepared[column] = pd.to_numeric(
            prepared[column],
            errors="raise",
        )

    start = pd.Timestamp(
        policy.research_start
    )

    end = pd.Timestamp(
        policy.research_end_exclusive
    )

    prepared = prepared.loc[
        (
            prepared["snapshot_time"]
            >= start
        )
        & (
            prepared["snapshot_time"]
            < end
        )
    ]

    if prepared.duplicated(
        subset=[
            "snapshot_time",
            "symbol",
        ]
    ).any():
        raise (
            MomentumReaccelerationConfigurationError(
                "Ranking contains duplicate "
                "snapshot_time/symbol rows."
            )
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


def _compute_features(
    history: pd.DataFrame,
    *,
    policy: MomentumReaccelerationPolicy,
) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []

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

        group["momentum_5d"] = (
            group["close"]
            / group["close"].shift(
                policy.momentum_days
            )
            - 1.0
        )

        group["ema_20"] = (
            group["close"].ewm(
                span=policy.ema_days,
                adjust=False,
                min_periods=policy.ema_days,
            ).mean()
        )

        group["sma_200"] = (
            group["close"].rolling(
                window=policy.trend_days,
                min_periods=policy.trend_days,
            ).mean()
        )

        group["regime_sma_fast"] = (
            group["close"].rolling(
                window=policy.regime_fast_days,
                min_periods=(
                    policy.regime_fast_days
                ),
            ).mean()
        )

        group["regime_sma_slow"] = (
            group["close"].rolling(
                window=policy.regime_slow_days,
                min_periods=(
                    policy.regime_slow_days
                ),
            ).mean()
        )

        rolling_high = (
            group["high"].rolling(
                window=policy.rolling_high_days,
                min_periods=(
                    policy.rolling_high_days
                ),
            ).max()
        )

        group["pullback_from_60d_high"] = (
            group["close"]
            / rolling_high
            - 1.0
        )

        group["atr_fraction"] = (
            true_range.rolling(
                window=policy.atr_days,
                min_periods=policy.atr_days,
            ).mean()
            / group["close"]
        )

        group["symbol"] = str(symbol)

        frames.append(
            group[
                [
                    "symbol",
                    "close_time",
                    "close",
                    "momentum_5d",
                    "ema_20",
                    "sma_200",
                    "regime_sma_fast",
                    "regime_sma_slow",
                    "pullback_from_60d_high",
                    "atr_fraction",
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

    if not frames:
        raise (
            MomentumReaccelerationConfigurationError(
                "No feature history could "
                "be constructed."
            )
        )

    return (
        pd.concat(
            frames,
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


def _merge_symbol_features(
    ranking: pd.DataFrame,
    features: pd.DataFrame,
) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []

    for symbol, symbol_ranking in (
        ranking.groupby(
            "symbol",
            sort=True,
        )
    ):
        symbol_features = (
            features.loc[
                features["symbol"]
                == symbol
            ]
            .drop(columns=["symbol"])
            .sort_values(
                "feature_time"
            )
        )

        if symbol_features.empty:
            continue

        merged = pd.merge_asof(
            symbol_ranking.sort_values(
                "snapshot_time"
            ),
            symbol_features,
            left_on="snapshot_time",
            right_on="feature_time",
            direction="backward",
            allow_exact_matches=True,
        )

        frames.append(merged)

    if not frames:
        raise (
            MomentumReaccelerationConfigurationError(
                "No ranking rows could be "
                "matched to price features."
            )
        )

    return (
        pd.concat(
            frames,
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


def _attach_market_regime(
    rows: pd.DataFrame,
    features: pd.DataFrame,
    *,
    benchmark_symbol: str,
) -> pd.DataFrame:
    benchmark = (
        features.loc[
            features["symbol"]
            == benchmark_symbol,
            [
                "feature_time",
                "feature_close",
                "regime_sma_fast",
                "regime_sma_slow",
            ],
        ]
        .rename(
            columns={
                "feature_time": (
                    "benchmark_feature_time"
                ),
                "feature_close": (
                    "benchmark_close"
                ),
                "regime_sma_fast": (
                    "benchmark_sma_fast"
                ),
                "regime_sma_slow": (
                    "benchmark_sma_slow"
                ),
            }
        )
        .sort_values(
            "benchmark_feature_time"
        )
    )

    if benchmark.empty:
        raise (
            MomentumReaccelerationConfigurationError(
                "Benchmark history was not "
                f"found: {benchmark_symbol}."
            )
        )

    return pd.merge_asof(
        rows.sort_values(
            [
                "snapshot_time",
                "symbol",
            ]
        ),
        benchmark,
        left_on="snapshot_time",
        right_on="benchmark_feature_time",
        direction="backward",
        allow_exact_matches=True,
    )


def build_momentum_reacceleration_signals(
    history: pd.DataFrame,
    ranking: pd.DataFrame,
    *,
    policy: MomentumReaccelerationPolicy,
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

    merged = _merge_symbol_features(
        prepared_ranking,
        features,
    )

    merged = _attach_market_regime(
        merged,
        features,
        benchmark_symbol=(
            policy.benchmark_symbol
        ),
    )

    required_feature_columns = [
        "feature_time",
        "feature_close",
        "momentum_5d",
        "ema_20",
        "sma_200",
        "pullback_from_60d_high",
        "atr_fraction",
        "benchmark_feature_time",
        "benchmark_close",
        "benchmark_sma_fast",
        "benchmark_sma_slow",
    ]

    merged["complete_features"] = (
        merged[
            required_feature_columns
        ]
        .notna()
        .all(axis=1)
    )

    merged["causal_features"] = (
        merged["feature_time"]
        <= merged["snapshot_time"]
    ) & (
        merged["benchmark_feature_time"]
        <= merged["snapshot_time"]
    )

    merged["rank_pass"] = (
        merged["rank_within_snapshot"]
        <= policy.maximum_rank
    )

    merged["long_term_momentum_pass"] = (
        merged["return_90d"]
        >= policy.minimum_return_90d
    )

    merged["relative_strength_pass"] = (
        merged["relative_strength_90d"]
        >= (
            policy
            .minimum_relative_strength_90d
        )
    )

    merged["trend_pass"] = (
        merged["feature_close"]
        > merged["sma_200"]
    )

    merged["reacceleration_pass"] = (
        (
            merged["momentum_5d"]
            >= policy.minimum_momentum_5d
        )
        & (
            merged["feature_close"]
            > merged["ema_20"]
        )
    )

    merged["pullback_pass"] = (
        merged["pullback_from_60d_high"]
        >= (
            -policy
            .maximum_pullback_from_high
        )
    ) & (
        merged["pullback_from_60d_high"]
        <= 0.0
    )

    merged["volatility_pass"] = (
        merged["atr_fraction"]
        >= policy.minimum_atr_fraction
    ) & (
        merged["atr_fraction"]
        <= policy.maximum_atr_fraction
    )

    merged["market_regime_pass"] = (
        merged["benchmark_close"]
        > merged["benchmark_sma_slow"]
    ) & (
        merged["benchmark_sma_fast"]
        > merged["benchmark_sma_slow"]
    )

    merged["candidate"] = (
        merged["complete_features"]
        & merged["causal_features"]
        & merged["rank_pass"]
        & merged["long_term_momentum_pass"]
        & merged["relative_strength_pass"]
        & merged["trend_pass"]
        & merged["reacceleration_pass"]
        & merged["pullback_pass"]
        & merged["volatility_pass"]
        & merged["market_regime_pass"]
    )

    merged["signal_score"] = (
        merged["composite_score"]
        + 0.10
        * merged["momentum_5d"].clip(
            lower=-0.50,
            upper=0.50,
        )
        + 0.05
        * merged[
            "relative_strength_90d"
        ].clip(
            lower=-1.0,
            upper=1.0,
        )
    )

    columns = [
        "snapshot_time",
        "symbol",
        "feature_time",
        "benchmark_feature_time",
        "feature_close",
        "return_90d",
        "relative_strength_90d",
        "composite_score",
        "rank_within_snapshot",
        "momentum_5d",
        "ema_20",
        "sma_200",
        "pullback_from_60d_high",
        "atr_fraction",
        "benchmark_close",
        "benchmark_sma_fast",
        "benchmark_sma_slow",
        "complete_features",
        "causal_features",
        "rank_pass",
        "long_term_momentum_pass",
        "relative_strength_pass",
        "trend_pass",
        "reacceleration_pass",
        "pullback_pass",
        "volatility_pass",
        "market_regime_pass",
        "signal_score",
        "candidate",
    ]

    return (
        merged[columns]
        .sort_values(
            [
                "snapshot_time",
                "candidate",
                "signal_score",
                "symbol",
            ],
            ascending=[
                True,
                False,
                False,
                True,
            ],
        )
        .reset_index(drop=True)
    )


def build_target_weights(
    signals: pd.DataFrame,
    *,
    policy: MomentumReaccelerationPolicy,
) -> pd.DataFrame:
    _require_columns(
        signals,
        required={
            "snapshot_time",
            "symbol",
            "candidate",
            "signal_score",
            "rank_within_snapshot",
        },
        frame_name="signals",
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
        .str.strip()
        .str.upper()
    )

    snapshots = sorted(
        prepared[
            "snapshot_time"
        ].unique().tolist()
    )

    symbols = sorted(
        prepared[
            "symbol"
        ].unique().tolist()
    )

    current_weights = {
        symbol: 0.0
        for symbol in symbols
    }

    records: list[
        dict[str, object]
    ] = []

    for raw_snapshot in snapshots:
        snapshot = pd.Timestamp(
            raw_snapshot
        )

        rows = prepared.loc[
            prepared["snapshot_time"]
            == snapshot
        ]

        available_symbols = set(
            rows["symbol"].tolist()
        )

        for symbol in symbols:
            if symbol not in available_symbols:
                current_weights[symbol] = 0.0

        rebalance = (
            snapshot.dayofweek
            == policy.rebalance_weekday
        )

        if rebalance:
            candidates = (
                rows.loc[
                    rows["candidate"]
                ]
                .sort_values(
                    [
                        "signal_score",
                        "rank_within_snapshot",
                        "symbol",
                    ],
                    ascending=[
                        False,
                        True,
                        True,
                    ],
                )
                .head(
                    policy.maximum_positions
                )
            )

            selected_symbols = (
                candidates[
                    "symbol"
                ].astype(str).tolist()
            )

            current_weights = {
                symbol: 0.0
                for symbol in symbols
            }

            if selected_symbols:
                equal_weight = (
                    1.0
                    / len(selected_symbols)
                )

                for symbol in selected_symbols:
                    current_weights[
                        symbol
                    ] = equal_weight

        for symbol in symbols:
            weight = float(
                current_weights[symbol]
            )

            records.append(
                {
                    "snapshot_time": snapshot,
                    "symbol": symbol,
                    "target_weight": weight,
                    "selected": weight > 0.0,
                    "rebalance_day": rebalance,
                }
            )

    result = pd.DataFrame.from_records(
        records
    )

    weight_sums = (
        result.groupby(
            "snapshot_time"
        )["target_weight"]
        .sum()
    )

    if (
        weight_sums
        > 1.0 + 1e-12
    ).any():
        raise (
            MomentumReaccelerationConfigurationError(
                "Target portfolio weight "
                "exceeds one."
            )
        )

    selected_counts = (
        result.groupby(
            "snapshot_time"
        )["selected"]
        .sum()
    )

    if (
        selected_counts
        > policy.maximum_positions
    ).any():
        raise (
            MomentumReaccelerationConfigurationError(
                "Target portfolio exceeds "
                "maximum_positions."
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


def run_daily_portfolio_backtest(
    history: pd.DataFrame,
    target_weights: pd.DataFrame,
    *,
    policy: MomentumReaccelerationPolicy,
) -> pd.DataFrame:
    prepared_history = _prepare_history(
        history
    )

    _require_columns(
        target_weights,
        required={
            "snapshot_time",
            "symbol",
            "target_weight",
        },
        frame_name="target_weights",
    )

    weights = target_weights.copy()

    weights["snapshot_time"] = (
        pd.to_datetime(
            weights["snapshot_time"],
            utc=True,
            errors="raise",
        )
    )

    weights["symbol"] = (
        weights["symbol"]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    weights["target_weight"] = (
        pd.to_numeric(
            weights["target_weight"],
            errors="raise",
        )
    )

    if (
        weights["target_weight"]
        < 0.0
    ).any():
        raise (
            MomentumReaccelerationConfigurationError(
                "Negative target weight "
                "detected."
            )
        )

    close_frame = (
        prepared_history[
            [
                "symbol",
                "close_time",
                "close",
            ]
        ]
        .sort_values(
            [
                "symbol",
                "close_time",
            ]
        )
        .copy()
    )

    close_frame["asset_return"] = (
        close_frame.groupby(
            "symbol",
            sort=False,
        )["close"]
        .pct_change(
            fill_method=None
        )
    )

    returns = (
        close_frame.pivot(
            index="close_time",
            columns="symbol",
            values="asset_return",
        )
        .sort_index()
    )

    target_matrix = (
        weights.pivot(
            index="snapshot_time",
            columns="symbol",
            values="target_weight",
        )
        .sort_index()
        .fillna(0.0)
    )

    index = target_matrix.index

    returns = (
        returns.reindex(
            index=index,
            columns=target_matrix.columns,
        )
        .fillna(0.0)
    )

    effective_weights = (
        target_matrix.shift(1)
        .fillna(0.0)
    )

    gross_return = (
        effective_weights
        * returns
    ).sum(axis=1)

    previous_weights = (
        effective_weights.shift(1)
        .fillna(0.0)
    )

    turnover = (
        effective_weights
        - previous_weights
    ).abs().sum(axis=1)

    transaction_cost = (
        turnover
        * policy.transaction_cost_fraction
    )

    net_return = (
        gross_return
        - transaction_cost
    )

    if (
        net_return
        <= -1.0
    ).any():
        raise (
            MomentumReaccelerationConfigurationError(
                "Portfolio return reached "
                "or crossed -100%."
            )
        )

    benchmark_returns = (
        returns[
            policy.benchmark_symbol
        ]
        if (
            policy.benchmark_symbol
            in returns.columns
        )
        else pd.Series(
            0.0,
            index=index,
            dtype="float64",
        )
    )

    equity = (
        1.0
        + net_return
    ).cumprod()

    benchmark_equity = (
        1.0
        + benchmark_returns
    ).cumprod()

    exposure = effective_weights.sum(
        axis=1
    )

    active_positions = (
        effective_weights
        > 0.0
    ).sum(axis=1)

    result = pd.DataFrame(
        {
            "snapshot_time": index,
            "gross_return": (
                gross_return.to_numpy()
            ),
            "turnover": (
                turnover.to_numpy()
            ),
            "transaction_cost": (
                transaction_cost.to_numpy()
            ),
            "net_return": (
                net_return.to_numpy()
            ),
            "equity": equity.to_numpy(),
            "benchmark_return": (
                benchmark_returns.to_numpy()
            ),
            "benchmark_equity": (
                benchmark_equity.to_numpy()
            ),
            "exposure": exposure.to_numpy(),
            "active_positions": (
                active_positions.to_numpy()
            ),
        }
    )

    result["drawdown"] = (
        result["equity"]
        / result["equity"].cummax()
        - 1.0
    )

    return result.reset_index(drop=True)
