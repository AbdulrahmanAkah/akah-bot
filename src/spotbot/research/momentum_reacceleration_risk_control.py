from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime

import pandas as pd

__all__ = [
    "RiskControlConfigurationError",
    "RiskControlPolicy",
    "run_risk_controlled_backtest",
]


class RiskControlConfigurationError(
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
        raise RiskControlConfigurationError(
            f"{field_name} must be "
            "timezone-aware."
        )


@dataclass(frozen=True, slots=True)
class RiskControlPolicy:
    research_start: datetime
    research_end_exclusive: datetime
    benchmark_symbol: str = "BTC/USDT"
    target_annualized_volatility: float = 0.35
    volatility_lookback_days: int = 30
    minimum_volatility_observations: int = 20
    initial_exposure_fraction: float = 0.50
    maximum_exposure_fraction: float = 1.00
    transaction_cost_fraction: float = 0.002
    drawdown_level_1: float = -0.10
    drawdown_level_2: float = -0.20
    drawdown_level_3: float = -0.30
    drawdown_level_4: float = -0.40
    exposure_level_1: float = 0.75
    exposure_level_2: float = 0.50
    exposure_level_3: float = 0.25
    exposure_level_4: float = 0.00

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
            raise RiskControlConfigurationError(
                "research_end_exclusive must "
                "be later than research_start."
            )

        normalized_benchmark = (
            self.benchmark_symbol
            .strip()
            .upper()
        )

        if not normalized_benchmark:
            raise RiskControlConfigurationError(
                "benchmark_symbol cannot "
                "be empty."
            )

        object.__setattr__(
            self,
            "benchmark_symbol",
            normalized_benchmark,
        )

        if (
            self.target_annualized_volatility
            <= 0.0
        ):
            raise RiskControlConfigurationError(
                "target_annualized_volatility "
                "must be positive."
            )

        if (
            self.volatility_lookback_days
            <= 1
        ):
            raise RiskControlConfigurationError(
                "volatility_lookback_days must "
                "be greater than one."
            )

        if not (
            1
            <= self.minimum_volatility_observations
            <= self.volatility_lookback_days
        ):
            raise RiskControlConfigurationError(
                "minimum_volatility_observations "
                "is invalid."
            )

        fractions = {
            "initial_exposure_fraction": (
                self.initial_exposure_fraction
            ),
            "maximum_exposure_fraction": (
                self.maximum_exposure_fraction
            ),
            "exposure_level_1": (
                self.exposure_level_1
            ),
            "exposure_level_2": (
                self.exposure_level_2
            ),
            "exposure_level_3": (
                self.exposure_level_3
            ),
            "exposure_level_4": (
                self.exposure_level_4
            ),
        }

        for name, value in fractions.items():
            if not 0.0 <= value <= 1.0:
                raise RiskControlConfigurationError(
                    f"{name} must be between "
                    "zero and one."
                )

        if (
            self.initial_exposure_fraction
            > self.maximum_exposure_fraction
        ):
            raise RiskControlConfigurationError(
                "initial exposure cannot exceed "
                "maximum exposure."
            )

        if (
            self.transaction_cost_fraction
            < 0.0
        ):
            raise RiskControlConfigurationError(
                "transaction_cost_fraction "
                "cannot be negative."
            )

        drawdown_levels = [
            self.drawdown_level_1,
            self.drawdown_level_2,
            self.drawdown_level_3,
            self.drawdown_level_4,
        ]

        if not (
            0.0
            > drawdown_levels[0]
            > drawdown_levels[1]
            > drawdown_levels[2]
            > drawdown_levels[3]
            > -1.0
        ):
            raise RiskControlConfigurationError(
                "Drawdown thresholds must be "
                "strictly decreasing."
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
        raise RiskControlConfigurationError(
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
        },
        frame_name="history",
    )

    prepared = history[
        [
            "symbol",
            "close_time",
            "close",
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

    if prepared["symbol"].eq("").any():
        raise RiskControlConfigurationError(
            "History contains an empty symbol."
        )

    if (
        prepared["close"].isna().any()
        or (
            prepared["close"]
            <= 0.0
        ).any()
    ):
        raise RiskControlConfigurationError(
            "History contains invalid "
            "close prices."
        )

    if prepared.duplicated(
        subset=[
            "symbol",
            "close_time",
        ]
    ).any():
        raise RiskControlConfigurationError(
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


def _prepare_weights(
    target_weights: pd.DataFrame,
    *,
    policy: RiskControlPolicy,
) -> pd.DataFrame:
    _require_columns(
        target_weights,
        required={
            "snapshot_time",
            "symbol",
            "target_weight",
        },
        frame_name="target_weights",
    )

    prepared = target_weights[
        [
            "snapshot_time",
            "symbol",
            "target_weight",
        ]
    ].copy()

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

    prepared["target_weight"] = pd.to_numeric(
        prepared["target_weight"],
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
        raise RiskControlConfigurationError(
            "Target weights contain duplicate "
            "snapshot/symbol rows."
        )

    if (
        prepared["target_weight"]
        < 0.0
    ).any():
        raise RiskControlConfigurationError(
            "Negative target weight detected."
        )

    weight_sums = (
        prepared.groupby(
            "snapshot_time"
        )["target_weight"]
        .sum()
    )

    if (
        weight_sums
        > 1.0 + 1e-12
    ).any():
        raise RiskControlConfigurationError(
            "Base target exposure exceeds one."
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


def _drawdown_exposure_scale(
    drawdown: float,
    *,
    policy: RiskControlPolicy,
) -> float:
    if drawdown <= policy.drawdown_level_4:
        return policy.exposure_level_4

    if drawdown <= policy.drawdown_level_3:
        return policy.exposure_level_3

    if drawdown <= policy.drawdown_level_2:
        return policy.exposure_level_2

    if drawdown <= policy.drawdown_level_1:
        return policy.exposure_level_1

    return policy.maximum_exposure_fraction


def run_risk_controlled_backtest(
    history: pd.DataFrame,
    base_target_weights: pd.DataFrame,
    *,
    policy: RiskControlPolicy,
) -> pd.DataFrame:
    prepared_history = _prepare_history(
        history
    )

    prepared_weights = _prepare_weights(
        base_target_weights,
        policy=policy,
    )

    history_returns = prepared_history.copy()

    history_returns["asset_return"] = (
        history_returns.groupby(
            "symbol",
            sort=False,
        )["close"]
        .pct_change(
            fill_method=None
        )
    )

    returns = (
        history_returns.pivot(
            index="close_time",
            columns="symbol",
            values="asset_return",
        )
        .sort_index()
    )

    base_targets = (
        prepared_weights.pivot(
            index="snapshot_time",
            columns="symbol",
            values="target_weight",
        )
        .sort_index()
        .fillna(0.0)
    )

    returns = (
        returns.reindex(
            index=base_targets.index,
            columns=base_targets.columns,
        )
        .fillna(0.0)
    )

    base_effective_weights = (
        base_targets.shift(1)
        .fillna(0.0)
    )

    base_gross_returns = (
        base_effective_weights
        * returns
    ).sum(axis=1)

    annualized_base_volatility = (
        base_gross_returns.rolling(
            window=(
                policy.volatility_lookback_days
            ),
            min_periods=(
                policy
                .minimum_volatility_observations
            ),
        )
        .std(ddof=0)
        * math.sqrt(365.0)
    )

    raw_volatility_scale = (
        policy.target_annualized_volatility
        / annualized_base_volatility.replace(
            0.0,
            float("nan"),
        )
    )

    volatility_scale = (
        raw_volatility_scale.clip(
            lower=0.0,
            upper=(
                policy.maximum_exposure_fraction
            ),
        )
        .fillna(
            policy.initial_exposure_fraction
        )
    )

    symbols = list(
        base_targets.columns
    )

    previous_target = pd.Series(
        0.0,
        index=symbols,
        dtype="float64",
    )

    previous_effective = pd.Series(
        0.0,
        index=symbols,
        dtype="float64",
    )

    equity = 1.0
    equity_peak = 1.0

    records: list[
        dict[str, object]
    ] = []

    for timestamp in base_targets.index:
        asset_returns = returns.loc[
            timestamp
        ]

        effective_weights = (
            previous_target.copy()
        )

        gross_return = float(
            (
                effective_weights
                * asset_returns
            ).sum()
        )

        turnover = float(
            (
                effective_weights
                - previous_effective
            )
            .abs()
            .sum()
        )

        transaction_cost = (
            turnover
            * policy.transaction_cost_fraction
        )

        net_return = (
            gross_return
            - transaction_cost
        )

        if net_return <= -1.0:
            raise RiskControlConfigurationError(
                "Portfolio return reached or "
                "crossed -100%."
            )

        equity *= 1.0 + net_return

        equity_peak = max(
            equity_peak,
            equity,
        )

        drawdown = (
            equity
            / equity_peak
            - 1.0
        )

        drawdown_scale = (
            _drawdown_exposure_scale(
                drawdown,
                policy=policy,
            )
        )

        current_volatility_scale = float(
            volatility_scale.loc[timestamp]
        )

        risk_scale = min(
            current_volatility_scale,
            drawdown_scale,
            policy.maximum_exposure_fraction,
        )

        next_target = (
            base_targets.loc[timestamp]
            * risk_scale
        )

        benchmark_return = (
            float(
                asset_returns[
                    policy.benchmark_symbol
                ]
            )
            if (
                policy.benchmark_symbol
                in asset_returns.index
            )
            else 0.0
        )

        records.append(
            {
                "snapshot_time": timestamp,
                "base_gross_return": float(
                    base_gross_returns.loc[
                        timestamp
                    ]
                ),
                "trailing_annualized_volatility": (
                    float(
                        annualized_base_volatility.loc[
                            timestamp
                        ]
                    )
                    if pd.notna(
                        annualized_base_volatility.loc[
                            timestamp
                        ]
                    )
                    else None
                ),
                "volatility_scale": (
                    current_volatility_scale
                ),
                "drawdown_scale": (
                    drawdown_scale
                ),
                "risk_scale": risk_scale,
                "gross_return": gross_return,
                "turnover": turnover,
                "transaction_cost": (
                    transaction_cost
                ),
                "net_return": net_return,
                "equity": equity,
                "drawdown": drawdown,
                "benchmark_return": (
                    benchmark_return
                ),
                "effective_exposure": float(
                    effective_weights.sum()
                ),
                "next_target_exposure": float(
                    next_target.sum()
                ),
                "active_positions": int(
                    (
                        effective_weights
                        > 0.0
                    ).sum()
                ),
            }
        )

        previous_effective = (
            effective_weights
        )

        previous_target = next_target

    result = pd.DataFrame.from_records(
        records
    )

    result["benchmark_equity"] = (
        1.0
        + result["benchmark_return"]
    ).cumprod()

    if (
        result["effective_exposure"]
        > policy.maximum_exposure_fraction
        + 1e-12
    ).any():
        raise RiskControlConfigurationError(
            "Risk-controlled exposure "
            "exceeds the configured maximum."
        )

    if (
        result["risk_scale"]
        < 0.0
    ).any():
        raise RiskControlConfigurationError(
            "Negative risk scale detected."
        )

    return result.reset_index(drop=True)
