from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast

import numpy as np
import pandas as pd


class AmsV2RegimeFeatureError(RuntimeError):
    pass


class AmsV2RegimeFeatureConfigurationError(
    AmsV2RegimeFeatureError
):
    pass


class AmsV2RegimeFeatureDataError(
    AmsV2RegimeFeatureError
):
    pass


REGIME_FEATURE_COLUMNS = (
    "btc_close_vs_ema_200",
    "btc_ema_50_slope",
    "eligible_asset_breadth_above_ema_50",
    "realized_volatility_percentile_20d",
    "average_pairwise_correlation_30d",
    "cross_sectional_return_dispersion_30d",
    "benchmark_drawdown_from_90d_high",
)


@dataclass(frozen=True, slots=True)
class AmsV2RegimeFeaturePolicy:
    research_start: datetime
    research_end_exclusive: datetime
    benchmark_symbol: str = "BTC/USDT"
    fast_ema_days: int = 50
    slow_ema_days: int = 200
    ema_slope_days: int = 20
    realized_volatility_days: int = 20
    volatility_percentile_lookback_days: int = 252
    correlation_days: int = 30
    correlation_minimum_observations: int = 20
    dispersion_return_days: int = 30
    drawdown_lookback_days: int = 90
    minimum_cross_section_assets: int = 3
    all_features_lagged_periods: int = 1

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
                raise AmsV2RegimeFeatureConfigurationError(
                    f"{name} must be timezone-aware."
                )

        if (
            self.research_end_exclusive
            <= self.research_start
        ):
            raise AmsV2RegimeFeatureConfigurationError(
                "Invalid research window."
            )

        integer_values = {
            "fast_ema_days": self.fast_ema_days,
            "slow_ema_days": self.slow_ema_days,
            "ema_slope_days": self.ema_slope_days,
            "realized_volatility_days": (
                self.realized_volatility_days
            ),
            "volatility_percentile_lookback_days": (
                self.volatility_percentile_lookback_days
            ),
            "correlation_days": self.correlation_days,
            "correlation_minimum_observations": (
                self.correlation_minimum_observations
            ),
            "dispersion_return_days": (
                self.dispersion_return_days
            ),
            "drawdown_lookback_days": (
                self.drawdown_lookback_days
            ),
            "minimum_cross_section_assets": (
                self.minimum_cross_section_assets
            ),
            "all_features_lagged_periods": (
                self.all_features_lagged_periods
            ),
        }

        invalid = [
            name
            for name, value in integer_values.items()
            if value <= 0
        ]

        if invalid:
            raise AmsV2RegimeFeatureConfigurationError(
                "Positive integer policy fields required: "
                f"{invalid}."
            )

        if self.fast_ema_days >= self.slow_ema_days:
            raise AmsV2RegimeFeatureConfigurationError(
                "fast_ema_days must be below slow_ema_days."
            )

        if (
            self.correlation_minimum_observations
            > self.correlation_days
        ):
            raise AmsV2RegimeFeatureConfigurationError(
                "Correlation minimum observations "
                "cannot exceed the window."
            )

        if self.all_features_lagged_periods != 1:
            raise AmsV2RegimeFeatureConfigurationError(
                "AMS V2 requires exactly one lagged period."
            )

        benchmark = (
            self.benchmark_symbol
            .strip()
            .upper()
        )

        if not benchmark:
            raise AmsV2RegimeFeatureConfigurationError(
                "benchmark_symbol cannot be empty."
            )

        object.__setattr__(
            self,
            "benchmark_symbol",
            benchmark,
        )


def default_ams_v2_regime_feature_policy(
) -> AmsV2RegimeFeaturePolicy:
    return AmsV2RegimeFeaturePolicy(
        research_start=datetime(
            2021,
            7,
            20,
            tzinfo=UTC,
        ),
        research_end_exclusive=datetime(
            2025,
            1,
            1,
            tzinfo=UTC,
        ),
    )


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
        raise AmsV2RegimeFeatureDataError(
            f"{frame_name} is missing columns: "
            f"{missing}."
        )


def _prepare_history(
    history: pd.DataFrame,
    *,
    policy: AmsV2RegimeFeaturePolicy,
) -> pd.DataFrame:
    _require_columns(
        history,
        required={
            "symbol",
            "close_time",
            "close",
        },
        frame_name="history",
    )

    result = history[
        [
            "symbol",
            "close_time",
            "close",
        ]
    ].copy()

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

    if (
        result["symbol"]
        == ""
    ).any():
        raise AmsV2RegimeFeatureDataError(
            "History contains an empty symbol."
        )

    if (
        result["close"]
        <= 0.0
    ).any():
        raise AmsV2RegimeFeatureDataError(
            "History close prices must exceed zero."
        )

    if result.duplicated(
        [
            "symbol",
            "close_time",
        ]
    ).any():
        raise AmsV2RegimeFeatureDataError(
            "Duplicate history symbol/close_time rows."
        )

    locked_start = pd.Timestamp(
        policy.research_end_exclusive
    )

    if (
        result["close_time"]
        >= locked_start
    ).any():
        raise AmsV2RegimeFeatureDataError(
            "History contains locked 2025+ observations."
        )

    return (
        result.sort_values(
            [
                "close_time",
                "symbol",
            ]
        )
        .reset_index(drop=True)
    )


def _eligible_values(
    values: pd.Series,
) -> pd.Series:
    if pd.api.types.is_bool_dtype(
        values.dtype
    ):
        return values.astype(bool)

    numeric = pd.to_numeric(
        values,
        errors="raise",
    )

    if not numeric.isin(
        [
            0,
            1,
        ]
    ).all():
        raise AmsV2RegimeFeatureDataError(
            "Universe eligible values must be boolean or 0/1."
        )

    return numeric.astype(bool)


def _prepare_universe(
    universe_snapshots: pd.DataFrame,
    *,
    policy: AmsV2RegimeFeaturePolicy,
) -> pd.DataFrame:
    _require_columns(
        universe_snapshots,
        required={
            "snapshot_time",
            "symbol",
            "eligible",
        },
        frame_name="universe_snapshots",
    )

    result = universe_snapshots[
        [
            "snapshot_time",
            "symbol",
            "eligible",
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

    result["eligible"] = _eligible_values(
        result["eligible"]
    )

    if result.duplicated(
        [
            "snapshot_time",
            "symbol",
        ]
    ).any():
        raise AmsV2RegimeFeatureDataError(
            "Duplicate universe snapshot/symbol rows."
        )

    locked_start = pd.Timestamp(
        policy.research_end_exclusive
    )

    if (
        result["snapshot_time"]
        >= locked_start
    ).any():
        raise AmsV2RegimeFeatureDataError(
            "Universe contains locked 2025+ snapshots."
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


def _ema_frame(
    close_matrix: pd.DataFrame,
    *,
    period: int,
) -> pd.DataFrame:
    result = pd.DataFrame(
        index=close_matrix.index
    )

    for symbol in close_matrix.columns:
        source_series = close_matrix.loc[:, symbol]

        result[str(symbol)] = (
            source_series
            .ewm(
                span=period,
                adjust=False,
                min_periods=period,
            )
            .mean()
        )

    return result


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


def _row_boolean_mask(
    frame: pd.DataFrame,
    *,
    timestamp: pd.Timestamp,
) -> pd.Series:
    row = cast(
        pd.Series,
        frame.loc[
            timestamp
        ],
    )

    aligned = row.reindex(
        frame.columns
    )

    return pd.Series(
        aligned
        .fillna(False)
        .astype(bool)
        .to_numpy(
            dtype=bool
        ),
        index=frame.columns,
        dtype=bool,
    )


def _breadth_values(
    *,
    calendar: pd.DatetimeIndex,
    eligible_lagged: pd.DataFrame,
    close_lagged: pd.DataFrame,
    ema_lagged: pd.DataFrame,
) -> tuple[
    pd.Series,
    pd.Series,
]:
    breadth: list[float] = []
    observation_counts: list[int] = []

    for timestamp in calendar:
        eligible = _row_boolean_mask(
            eligible_lagged,
            timestamp=timestamp,
        )

        close_row = cast(
            pd.Series,
            close_lagged.loc[
                timestamp
            ],
        ).reindex(
            eligible.index
        )

        ema_row = cast(
            pd.Series,
            ema_lagged.loc[
                timestamp
            ],
        ).reindex(
            eligible.index
        )

        valid_values = (
            eligible.to_numpy(
                dtype=bool
            )
            & close_row.notna().to_numpy(
                dtype=bool
            )
            & ema_row.notna().to_numpy(
                dtype=bool
            )
        )

        count = int(
            valid_values.sum()
        )

        observation_counts.append(
            count
        )

        if count == 0:
            breadth.append(
                float("nan")
            )
            continue

        close_values = close_row.to_numpy(
            dtype=float
        )[valid_values]

        ema_values = ema_row.to_numpy(
            dtype=float
        )[valid_values]

        above_values = (
            close_values
            > ema_values
        )

        breadth.append(
            float(
                above_values.mean()
            )
        )

    return (
        pd.Series(
            breadth,
            index=calendar,
            dtype=float,
        ),
        pd.Series(
            observation_counts,
            index=calendar,
            dtype=int,
        ),
    )


def _dispersion_values(
    *,
    calendar: pd.DatetimeIndex,
    eligible_lagged: pd.DataFrame,
    lagged_period_returns: pd.DataFrame,
) -> tuple[
    pd.Series,
    pd.Series,
]:
    dispersion: list[float] = []
    counts: list[int] = []

    for timestamp in calendar:
        eligible = _row_boolean_mask(
            eligible_lagged,
            timestamp=timestamp,
        )

        return_row = cast(
            pd.Series,
            lagged_period_returns.loc[
                timestamp
            ],
        ).reindex(
            eligible.index
        )

        selected_values = (
            return_row.to_numpy(
                dtype=float,
                na_value=float("nan"),
            )[
                eligible.to_numpy(
                    dtype=bool
                )
            ]
        )

        finite_values = selected_values[
            np.isfinite(
                selected_values
            )
        ]

        count = int(
            finite_values.size
        )

        counts.append(
            count
        )

        if count < 2:
            dispersion.append(
                float("nan")
            )
            continue

        dispersion.append(
            float(
                finite_values.std(
                    ddof=1
                )
            )
        )

    return (
        pd.Series(
            dispersion,
            index=calendar,
            dtype=float,
        ),
        pd.Series(
            counts,
            index=calendar,
            dtype=int,
        ),
    )


def _average_pairwise_correlation(
    returns: pd.DataFrame,
    *,
    timestamp: pd.Timestamp,
    eligible: pd.Series,
    policy: AmsV2RegimeFeaturePolicy,
) -> tuple[
    float,
    int,
]:
    end_position = int(
        returns.index.searchsorted(
            timestamp,
            side="left",
        )
    )

    start_position = max(
        0,
        end_position
        - policy.correlation_days,
    )

    window = returns.iloc[
        start_position:end_position
    ]

    selected_symbols = [
        str(symbol)
        for symbol, selected
        in eligible.items()
        if bool(selected)
        and symbol in window.columns
    ]

    if not selected_symbols:
        return (
            float("nan"),
            0,
        )

    selected = window.reindex(
        columns=selected_symbols
    )

    valid_symbols: list[str] = []

    for symbol in selected_symbols:
        symbol_returns = selected.loc[:, symbol]

        observation_count = int(
            symbol_returns
            .notna()
            .to_numpy(
                dtype=bool
            )
            .sum()
        )

        if (
            observation_count
            >= (
                policy
                .correlation_minimum_observations
            )
        ):
            valid_symbols.append(
                symbol
            )

    asset_count = len(
        valid_symbols
    )

    if (
        asset_count
        < policy.minimum_cross_section_assets
    ):
        return (
            float("nan"),
            asset_count,
        )

    correlation = (
        selected
        .reindex(
            columns=valid_symbols
        )
        .corr(
            min_periods=(
                policy
                .correlation_minimum_observations
            )
        )
    )

    values = correlation.to_numpy(
        dtype=float
    )

    upper = values[
        np.triu_indices(
            asset_count,
            k=1,
        )
    ]

    finite = upper[
        np.isfinite(
            upper
        )
    ]

    if finite.size == 0:
        return (
            float("nan"),
            asset_count,
        )

    return (
        float(
            finite.mean()
        ),
        asset_count,
    )


def _correlation_values(
    *,
    calendar: pd.DatetimeIndex,
    eligible_lagged: pd.DataFrame,
    returns: pd.DataFrame,
    policy: AmsV2RegimeFeaturePolicy,
) -> tuple[
    pd.Series,
    pd.Series,
]:
    values: list[float] = []
    counts: list[int] = []

    for timestamp in calendar:
        eligible = _row_boolean_mask(
            eligible_lagged,
            timestamp=timestamp,
        )

        value, count = (
            _average_pairwise_correlation(
                returns,
                timestamp=timestamp,
                eligible=eligible,
                policy=policy,
            )
        )

        values.append(
            value
        )

        counts.append(
            count
        )

    return (
        pd.Series(
            values,
            index=calendar,
            dtype=float,
        ),
        pd.Series(
            counts,
            index=calendar,
            dtype=int,
        ),
    )


def build_ams_v2_regime_feature_frame(
    history: pd.DataFrame,
    universe_snapshots: pd.DataFrame,
    *,
    policy: AmsV2RegimeFeaturePolicy | None = None,
) -> pd.DataFrame:
    active_policy = (
        policy
        if policy is not None
        else default_ams_v2_regime_feature_policy()
    )

    prepared_history = _prepare_history(
        history,
        policy=active_policy,
    )

    prepared_universe = _prepare_universe(
        universe_snapshots,
        policy=active_policy,
    )

    start = pd.Timestamp(
        active_policy.research_start
    )

    end = pd.Timestamp(
        active_policy.research_end_exclusive
    )

    calendar_values = (
        prepared_universe.loc[
            (
                prepared_universe[
                    "snapshot_time"
                ]
                >= start
            )
            & (
                prepared_universe[
                    "snapshot_time"
                ]
                < end
            ),
            "snapshot_time",
        ]
        .drop_duplicates()
        .sort_values()
        .tolist()
    )

    calendar = pd.DatetimeIndex(
        calendar_values
    )

    if calendar.empty:
        raise AmsV2RegimeFeatureDataError(
            "No universe snapshots exist "
            "inside the research window."
        )

    close_matrix = (
        prepared_history.pivot(
            index="close_time",
            columns="symbol",
            values="close",
        )
        .sort_index()
        .sort_index(axis=1)
    )

    benchmark_symbol = (
        active_policy.benchmark_symbol
    )

    if benchmark_symbol not in close_matrix.columns:
        raise AmsV2RegimeFeatureDataError(
            "Benchmark symbol is absent from history: "
            f"{benchmark_symbol}."
        )

    eligibility = (
        prepared_universe.pivot(
            index="snapshot_time",
            columns="symbol",
            values="eligible",
        )
        .sort_index()
        .sort_index(axis=1)
    )

    all_symbols = sorted(
        set(
            str(symbol)
            for symbol in close_matrix.columns
        )
        | set(
            str(symbol)
            for symbol in eligibility.columns
        )
    )

    close_matrix = close_matrix.reindex(
        columns=all_symbols
    )

    eligibility = eligibility.reindex(
        columns=all_symbols
    )

    eligibility_on_calendar = (
        eligibility.reindex(
            calendar
        )
    )

    eligible_lagged = (
        eligibility_on_calendar
        .shift(
            active_policy
            .all_features_lagged_periods
        )
        .fillna(False)
        .astype(bool)
    )

    ema_50 = _ema_frame(
        close_matrix,
        period=active_policy.fast_ema_days,
    )

    ema_200 = _ema_frame(
        close_matrix,
        period=active_policy.slow_ema_days,
    )

    close_lagged = (
        close_matrix
        .shift(
            active_policy
            .all_features_lagged_periods
        )
        .reindex(calendar)
    )

    ema_50_lagged = (
        ema_50
        .shift(
            active_policy
            .all_features_lagged_periods
        )
        .reindex(calendar)
    )

    breadth, breadth_count = _breadth_values(
        calendar=calendar,
        eligible_lagged=eligible_lagged,
        close_lagged=close_lagged,
        ema_lagged=ema_50_lagged,
    )

    period_returns = (
        close_matrix
        / close_matrix.shift(
            active_policy.dispersion_return_days
        )
        - 1.0
    )

    lagged_period_returns = (
        period_returns
        .shift(
            active_policy
            .all_features_lagged_periods
        )
        .reindex(calendar)
    )

    dispersion, dispersion_count = (
        _dispersion_values(
            calendar=calendar,
            eligible_lagged=eligible_lagged,
            lagged_period_returns=(
                lagged_period_returns
            ),
        )
    )

    daily_returns = close_matrix.pct_change(
        fill_method=None
    )

    correlation, correlation_count = (
        _correlation_values(
            calendar=calendar,
            eligible_lagged=eligible_lagged,
            returns=daily_returns,
            policy=active_policy,
        )
    )

    benchmark_close = close_matrix.loc[:, benchmark_symbol]

    benchmark_ema_50 = ema_50.loc[:, benchmark_symbol]

    benchmark_ema_200 = ema_200.loc[:, benchmark_symbol]


    lagged_benchmark_close = (
        benchmark_close.shift(
            active_policy
            .all_features_lagged_periods
        )
    )

    lagged_benchmark_ema_200 = (
        benchmark_ema_200.shift(
            active_policy
            .all_features_lagged_periods
        )
    )

    close_vs_ema_200 = (
        lagged_benchmark_close
        / lagged_benchmark_ema_200
        - 1.0
    )

    ema_50_slope = (
        benchmark_ema_50.shift(
            active_policy
            .all_features_lagged_periods
        )
        / benchmark_ema_50.shift(
            active_policy
            .all_features_lagged_periods
            + active_policy.ema_slope_days
        )
        - 1.0
    )

    benchmark_ratio = (
        benchmark_close
        / benchmark_close.shift(1)
    )

    benchmark_log_returns = pd.Series(
        np.log(
            benchmark_ratio.to_numpy(
                dtype=float
            )
        ),
        index=benchmark_ratio.index,
        dtype=float,
        name="benchmark_log_return",
    )


    realized_volatility = (
        benchmark_log_returns
        .rolling(
            active_policy
            .realized_volatility_days,
            min_periods=(
                active_policy
                .realized_volatility_days
            ),
        )
        .std(
            ddof=1
        )
        * math.sqrt(365.0)
    )

    lagged_realized_volatility = (
        realized_volatility.shift(
            active_policy
            .all_features_lagged_periods
        )
    )

    volatility_percentile = (
        lagged_realized_volatility
        .rolling(
            (
                active_policy
                .volatility_percentile_lookback_days
            ),
            min_periods=(
                active_policy
                .volatility_percentile_lookback_days
            ),
        )
        .apply(
            _last_percentile,
            raw=False,
        )
    )

    prior_90d_high = (
        benchmark_close
        .rolling(
            active_policy.drawdown_lookback_days,
            min_periods=(
                active_policy.drawdown_lookback_days
            ),
        )
        .max()
        .shift(
            active_policy
            .all_features_lagged_periods
        )
    )

    benchmark_drawdown = (
        1.0
        - (
            lagged_benchmark_close
            / prior_90d_high
        )
    )

    frame = pd.DataFrame(
        {
            "snapshot_time": calendar,
            "feature_information_cutoff": (
                calendar
                - pd.Timedelta(days=1)
            ),
            "lagged_periods": (
                active_policy
                .all_features_lagged_periods
            ),
            "benchmark_symbol": (
                benchmark_symbol
            ),
            "eligible_asset_count": (
                eligible_lagged.sum(
                    axis=1
                ).astype(int)
            ),
            "breadth_observation_count": (
                breadth_count
            ),
            "correlation_asset_count": (
                correlation_count
            ),
            "dispersion_asset_count": (
                dispersion_count
            ),
            "btc_close_vs_ema_200": (
                close_vs_ema_200.reindex(
                    calendar
                )
            ),
            "btc_ema_50_slope": (
                ema_50_slope.reindex(
                    calendar
                )
            ),
            (
                "eligible_asset_breadth_"
                "above_ema_50"
            ): breadth,
            (
                "realized_volatility_"
                "percentile_20d"
            ): volatility_percentile.reindex(
                calendar
            ),
            (
                "average_pairwise_"
                "correlation_30d"
            ): correlation,
            (
                "cross_sectional_return_"
                "dispersion_30d"
            ): dispersion,
            (
                "benchmark_drawdown_"
                "from_90d_high"
            ): benchmark_drawdown.reindex(
                calendar
            ),
        }
    )

    frame["complete_features"] = (
        frame[
            list(
                REGIME_FEATURE_COLUMNS
            )
        ]
        .notna()
        .all(axis=1)
    )

    return validate_ams_v2_regime_feature_frame(
        frame,
        policy=active_policy,
    )


def validate_ams_v2_regime_feature_frame(
    frame: pd.DataFrame,
    *,
    policy: AmsV2RegimeFeaturePolicy | None = None,
) -> pd.DataFrame:
    active_policy = (
        policy
        if policy is not None
        else default_ams_v2_regime_feature_policy()
    )

    required = {
        "snapshot_time",
        "feature_information_cutoff",
        "lagged_periods",
        "benchmark_symbol",
        "eligible_asset_count",
        "breadth_observation_count",
        "correlation_asset_count",
        "dispersion_asset_count",
        "complete_features",
        *REGIME_FEATURE_COLUMNS,
    }

    _require_columns(
        frame,
        required=required,
        frame_name="regime_feature_frame",
    )

    result = frame.copy()

    result["snapshot_time"] = pd.to_datetime(
        result["snapshot_time"],
        utc=True,
        errors="raise",
    )

    result["feature_information_cutoff"] = (
        pd.to_datetime(
            result[
                "feature_information_cutoff"
            ],
            utc=True,
            errors="raise",
        )
    )

    if result.empty:
        raise AmsV2RegimeFeatureDataError(
            "Regime feature frame is empty."
        )

    if result["snapshot_time"].duplicated().any():
        raise AmsV2RegimeFeatureDataError(
            "Duplicate regime feature snapshots."
        )

    if not result[
        "snapshot_time"
    ].is_monotonic_increasing:
        raise AmsV2RegimeFeatureDataError(
            "Regime feature snapshots are not sorted."
        )

    start = pd.Timestamp(
        active_policy.research_start
    )

    end = pd.Timestamp(
        active_policy.research_end_exclusive
    )

    if (
        result["snapshot_time"]
        < start
    ).any():
        raise AmsV2RegimeFeatureDataError(
            "Regime frame begins before the research window."
        )

    if (
        result["snapshot_time"]
        >= end
    ).any():
        raise AmsV2RegimeFeatureDataError(
            "Regime frame contains locked dates."
        )

    expected_cutoff = (
        result["snapshot_time"]
        - pd.Timedelta(days=1)
    )

    if not result[
        "feature_information_cutoff"
    ].equals(expected_cutoff):
        raise AmsV2RegimeFeatureDataError(
            "Feature cutoff is not lagged by one day."
        )

    if not (
        result["lagged_periods"]
        == 1
    ).all():
        raise AmsV2RegimeFeatureDataError(
            "All regime features must be lagged once."
        )

    if not (
        result["benchmark_symbol"]
        == active_policy.benchmark_symbol
    ).all():
        raise AmsV2RegimeFeatureDataError(
            "Unexpected benchmark symbol."
        )

    count_columns = (
        "eligible_asset_count",
        "breadth_observation_count",
        "correlation_asset_count",
        "dispersion_asset_count",
    )

    for column in count_columns:
        numeric = pd.to_numeric(
            result[column],
            errors="raise",
        )

        if (
            numeric < 0
        ).any():
            raise AmsV2RegimeFeatureDataError(
                f"{column} cannot be negative."
            )

    bounded_columns = {
        (
            "eligible_asset_breadth_"
            "above_ema_50"
        ): (
            0.0,
            1.0,
        ),
        (
            "realized_volatility_"
            "percentile_20d"
        ): (
            0.0,
            1.0,
        ),
        (
            "average_pairwise_"
            "correlation_30d"
        ): (
            -1.0,
            1.0,
        ),
    }

    for column, bounds in bounded_columns.items():
        values = pd.to_numeric(
            result[column],
            errors="raise",
        ).dropna()

        if (
            values < bounds[0] - 1e-12
        ).any() or (
            values > bounds[1] + 1e-12
        ).any():
            raise AmsV2RegimeFeatureDataError(
                f"{column} is outside {bounds}."
            )

    nonnegative_columns = (
        "cross_sectional_return_dispersion_30d",
        "benchmark_drawdown_from_90d_high",
    )

    for column in nonnegative_columns:
        values = pd.to_numeric(
            result[column],
            errors="raise",
        ).dropna()

        if (
            values < -1e-12
        ).any():
            raise AmsV2RegimeFeatureDataError(
                f"{column} cannot be negative."
            )

    complete = result.loc[
        result["complete_features"]
    ]

    if complete.empty:
        raise AmsV2RegimeFeatureDataError(
            "No complete regime feature snapshots exist."
        )

    complete_values = complete[
        list(
            REGIME_FEATURE_COLUMNS
        )
    ]

    finite = complete_values.apply(
        lambda column: column.map(
            math.isfinite
        )
    )

    if not finite.all().all():
        raise AmsV2RegimeFeatureDataError(
            "Complete feature rows contain non-finite values."
        )

    return (
        result.sort_values(
            "snapshot_time"
        )
        .reset_index(drop=True)
    )