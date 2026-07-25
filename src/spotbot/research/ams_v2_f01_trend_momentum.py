from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import pandas as pd

from spotbot.research.ams_v2_family_adapters import (
    AmsV2FamilyAdapterConfigurationError,
    AmsV2FamilyId,
    validate_registered_family_configuration,
)
from spotbot.research.momentum_reacceleration import (
    MomentumReaccelerationPolicy,
    build_momentum_reacceleration_signals,
    run_daily_portfolio_backtest,
)
from spotbot.research.volatility_breakout import (
    VolatilityBreakoutPolicy,
    build_volatility_breakout_signals,
    build_volatility_breakout_weights,
)

F01_ENGINE_VERSION = (
    "AMS_V2_F01_TREND_MOMENTUM_ENGINE_CORE_V1"
)

F01_ENGINE_EXECUTION_STATUS = (
    "CORE_REGISTERED_NOT_TRIAL_EXECUTABLE"
)

LOCKED_TEST_START = datetime(
    2025,
    1,
    1,
    tzinfo=UTC,
)

SIGNAL_KEY_COLUMNS = (
    "snapshot_time",
    "symbol",
)


class F01TrendMomentumError(RuntimeError):
    pass


class F01TrendMomentumConfigurationError(
    F01TrendMomentumError
):
    pass


class F01TrendMomentumDataError(
    F01TrendMomentumError
):
    pass


@dataclass(frozen=True, slots=True)
class F01TrendMomentumPolicy:
    research_start: datetime
    research_end_exclusive: datetime
    breakout_lookback_days: int
    initial_stop_atr: float
    maximum_holding_days: int
    maximum_positions: int
    momentum_lookback_days: int
    ranking_maximum: int
    trailing_stop_atr: float
    transaction_cost_fraction: float
    turnover_expansion_minimum: float
    benchmark_symbol: str = "BTC/USDT"
    atr_expansion_minimum: float = 1.2
    atr_days: int = 14

    def __post_init__(self) -> None:
        timestamps = {
            "research_start": self.research_start,
            "research_end_exclusive": (
                self.research_end_exclusive
            ),
        }

        for name, timestamp_value in timestamps.items():
            if (
                timestamp_value.tzinfo is None
                or timestamp_value.utcoffset() is None
            ):
                raise F01TrendMomentumConfigurationError(
                    f"{name} must be timezone-aware."
                )

        if not (
            self.research_start
            < self.research_end_exclusive
            <= LOCKED_TEST_START
        ):
            raise F01TrendMomentumConfigurationError(
                "F01 research boundaries are invalid or "
                "reach the locked 2025 test."
            )

        positive_integer_fields: dict[str, int] = {
            "breakout_lookback_days": (
                self.breakout_lookback_days
            ),
            "maximum_holding_days": (
                self.maximum_holding_days
            ),
            "maximum_positions": (
                self.maximum_positions
            ),
            "momentum_lookback_days": (
                self.momentum_lookback_days
            ),
            "ranking_maximum": (
                self.ranking_maximum
            ),
            "atr_days": self.atr_days,
        }

        for (
            name,
            integer_value,
        ) in positive_integer_fields.items():
            if integer_value <= 0:
                raise F01TrendMomentumConfigurationError(
                    f"{name} must be positive."
                )

        positive_float_fields: dict[str, float] = {
            "initial_stop_atr": (
                self.initial_stop_atr
            ),
            "trailing_stop_atr": (
                self.trailing_stop_atr
            ),
            "turnover_expansion_minimum": (
                self.turnover_expansion_minimum
            ),
            "atr_expansion_minimum": (
                self.atr_expansion_minimum
            ),
        }

        for (
            name,
            float_value,
        ) in positive_float_fields.items():
            if (
                not math.isfinite(float_value)
                or float_value <= 0.0
            ):
                raise F01TrendMomentumConfigurationError(
                    f"{name} must be finite and positive."
                )

        if (
            not math.isfinite(
                self.transaction_cost_fraction
            )
            or not (
                0.0
                <= self.transaction_cost_fraction
                <= 0.01
            )
        ):
            raise F01TrendMomentumConfigurationError(
                "transaction_cost_fraction must be "
                "inside [0, 0.01]."
            )

        if not self.benchmark_symbol.strip():
            raise F01TrendMomentumConfigurationError(
                "benchmark_symbol cannot be empty."
            )

    @classmethod
    def from_registered_configuration(
        cls,
        configuration: Mapping[str, Any],
        *,
        research_start: datetime,
        research_end_exclusive: datetime,
    ) -> F01TrendMomentumPolicy:
        specification = (
            validate_registered_family_configuration(
                configuration
            )
        )

        if (
            specification.family_id
            != AmsV2FamilyId.F01
        ):
            raise F01TrendMomentumConfigurationError(
                "Configuration is not registered as "
                "AMS-V2-F01."
            )

        raw_parameters = configuration.get(
            "parameters"
        )

        if not isinstance(
            raw_parameters,
            Mapping,
        ):
            raise F01TrendMomentumConfigurationError(
                "F01 parameters must be a mapping."
            )

        parameters = {
            str(key): value
            for key, value
            in raw_parameters.items()
        }

        return cls(
            research_start=research_start,
            research_end_exclusive=(
                research_end_exclusive
            ),
            breakout_lookback_days=(
                _required_integer(
                    parameters,
                    "breakout_lookback_days",
                )
            ),
            initial_stop_atr=(
                _required_float(
                    parameters,
                    "initial_stop_atr",
                )
            ),
            maximum_holding_days=(
                _required_integer(
                    parameters,
                    "maximum_holding_days",
                )
            ),
            maximum_positions=(
                _required_integer(
                    parameters,
                    "maximum_positions",
                )
            ),
            momentum_lookback_days=(
                _required_integer(
                    parameters,
                    "momentum_lookback_days",
                )
            ),
            ranking_maximum=(
                _required_integer(
                    parameters,
                    "ranking_maximum",
                )
            ),
            trailing_stop_atr=(
                _required_float(
                    parameters,
                    "trailing_stop_atr",
                )
            ),
            transaction_cost_fraction=(
                _required_float(
                    parameters,
                    "transaction_cost_fraction",
                )
            ),
            turnover_expansion_minimum=(
                _required_float(
                    parameters,
                    "turnover_expansion_minimum",
                )
            ),
        )

    def to_momentum_policy(
        self,
    ) -> MomentumReaccelerationPolicy:
        return MomentumReaccelerationPolicy(
            research_start=self.research_start,
            research_end_exclusive=(
                self.research_end_exclusive
            ),
            benchmark_symbol=self.benchmark_symbol,
            maximum_rank=self.ranking_maximum,
            maximum_positions=self.maximum_positions,
            momentum_days=(
                self.momentum_lookback_days
            ),
            rolling_high_days=(
                self.breakout_lookback_days
            ),
            transaction_cost_fraction=(
                self.transaction_cost_fraction
            ),
        )

    def to_breakout_policy(
        self,
    ) -> VolatilityBreakoutPolicy:
        return VolatilityBreakoutPolicy(
            research_start=self.research_start,
            research_end_exclusive=(
                self.research_end_exclusive
            ),
            ranking_maximum=self.ranking_maximum,
            maximum_positions=self.maximum_positions,
            breakout_lookback_days=(
                self.breakout_lookback_days
            ),
            turnover_expansion_minimum=(
                self.turnover_expansion_minimum
            ),
            atr_expansion_minimum=(
                self.atr_expansion_minimum
            ),
            atr_days=self.atr_days,
            initial_stop_atr=self.initial_stop_atr,
            trailing_stop_atr=(
                self.trailing_stop_atr
            ),
            maximum_holding_days=(
                self.maximum_holding_days
            ),
            transaction_cost_fraction=(
                self.transaction_cost_fraction
            ),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "research_start": (
                self.research_start.isoformat()
            ),
            "research_end_exclusive": (
                self.research_end_exclusive.isoformat()
            ),
            "breakout_lookback_days": (
                self.breakout_lookback_days
            ),
            "initial_stop_atr": (
                self.initial_stop_atr
            ),
            "maximum_holding_days": (
                self.maximum_holding_days
            ),
            "maximum_positions": (
                self.maximum_positions
            ),
            "momentum_lookback_days": (
                self.momentum_lookback_days
            ),
            "ranking_maximum": (
                self.ranking_maximum
            ),
            "trailing_stop_atr": (
                self.trailing_stop_atr
            ),
            "transaction_cost_fraction": (
                self.transaction_cost_fraction
            ),
            "turnover_expansion_minimum": (
                self.turnover_expansion_minimum
            ),
            "benchmark_symbol": (
                self.benchmark_symbol
            ),
            "atr_expansion_minimum": (
                self.atr_expansion_minimum
            ),
            "atr_days": self.atr_days,
        }


@dataclass(frozen=True, slots=True)
class F01EngineCoreArtifacts:
    composite_signals: pd.DataFrame
    target_weights: pd.DataFrame
    trade_records: pd.DataFrame
    daily_portfolio: pd.DataFrame

    def to_summary(self) -> dict[str, int]:
        return {
            "signal_rows": len(
                self.composite_signals
            ),
            "weight_rows": len(
                self.target_weights
            ),
            "trade_rows": len(
                self.trade_records
            ),
            "daily_rows": len(
                self.daily_portfolio
            ),
        }


def _required_float(
    parameters: Mapping[str, Any],
    key: str,
) -> float:
    raw_value = parameters.get(key)

    if (
        raw_value is None
        or isinstance(raw_value, bool)
    ):
        raise F01TrendMomentumConfigurationError(
            f"{key} is missing or invalid."
        )

    try:
        numeric_value = float(
            raw_value
        )
    except (
        TypeError,
        ValueError,
    ) as error:
        raise F01TrendMomentumConfigurationError(
            f"{key} must be numeric."
        ) from error

    if not math.isfinite(numeric_value):
        raise F01TrendMomentumConfigurationError(
            f"{key} must be finite."
        )

    return numeric_value


def _required_integer(
    parameters: Mapping[str, Any],
    key: str,
) -> int:
    numeric_value = _required_float(
        parameters,
        key,
    )

    if not numeric_value.is_integer():
        raise F01TrendMomentumConfigurationError(
            f"{key} must be an integer."
        )

    return int(numeric_value)


def _require_columns(
    frame: pd.DataFrame,
    *,
    required: tuple[str, ...],
    frame_name: str,
) -> None:
    missing = sorted(
        set(required)
        - set(frame.columns)
    )

    if missing:
        raise F01TrendMomentumDataError(
            f"{frame_name} is missing columns: "
            f"{missing}."
        )


def _normalize_signal_keys(
    frame: pd.DataFrame,
    *,
    frame_name: str,
) -> pd.DataFrame:
    result = frame.copy()

    result["snapshot_time"] = pd.to_datetime(
        result["snapshot_time"],
        utc=True,
        errors="raise",
    )

    result["symbol"] = (
        result["symbol"]
        .astype(str)
        .str.strip()
    )

    if result["symbol"].eq("").any():
        raise F01TrendMomentumDataError(
            f"{frame_name} contains an empty symbol."
        )

    if result.duplicated(
        subset=list(
            SIGNAL_KEY_COLUMNS
        )
    ).any():
        raise F01TrendMomentumDataError(
            f"{frame_name} contains duplicate "
            "snapshot/symbol rows."
        )

    return result


def _numeric_column(
    frame: pd.DataFrame,
    column: str,
    *,
    fill_value: float,
) -> pd.Series:
    converted = pd.to_numeric(
        frame[column],
        errors="coerce",
    )

    return pd.Series(
        converted,
        index=frame.index,
        dtype="float64",
    ).fillna(
        fill_value
    )


def build_f01_trend_momentum_signals(
    history: pd.DataFrame,
    ranking: pd.DataFrame,
    *,
    policy: F01TrendMomentumPolicy,
) -> pd.DataFrame:
    momentum_signals = (
        build_momentum_reacceleration_signals(
            history,
            ranking,
            policy=policy.to_momentum_policy(),
        )
    )

    breakout_signals = (
        build_volatility_breakout_signals(
            history,
            ranking,
            policy=policy.to_breakout_policy(),
        )
    )

    _require_columns(
        momentum_signals,
        required=(
            "snapshot_time",
            "symbol",
            "candidate",
            "signal_score",
        ),
        frame_name="Momentum signals",
    )

    _require_columns(
        breakout_signals,
        required=(
            "snapshot_time",
            "symbol",
            "candidate",
            "rank_within_snapshot",
            "turnover_expansion_h01",
        ),
        frame_name="Breakout signals",
    )

    momentum = _normalize_signal_keys(
        momentum_signals,
        frame_name="Momentum signals",
    )

    breakout = _normalize_signal_keys(
        breakout_signals,
        frame_name="Breakout signals",
    )

    momentum_subset = (
        momentum.loc[
            :,
            [
                "snapshot_time",
                "symbol",
                "candidate",
                "signal_score",
            ],
        ]
        .rename(
            columns={
                "candidate": (
                    "f01_momentum_candidate"
                ),
                "signal_score": (
                    "f01_momentum_signal_score"
                ),
            }
        )
    )

    merged = breakout.merge(
        momentum_subset,
        on=list(
            SIGNAL_KEY_COLUMNS
        ),
        how="left",
        sort=False,
        validate="one_to_one",
    )

    breakout_candidate = (
        merged["candidate"]
        .fillna(False)
        .astype(bool)
    )

    momentum_candidate = (
        merged[
            "f01_momentum_candidate"
        ]
        .fillna(False)
        .astype(bool)
    )

    momentum_score = _numeric_column(
        merged,
        "f01_momentum_signal_score",
        fill_value=-1_000_000.0,
    )

    turnover_expansion = _numeric_column(
        merged,
        "turnover_expansion_h01",
        fill_value=0.0,
    )

    merged["f01_breakout_candidate"] = (
        breakout_candidate
    )

    merged["f01_momentum_candidate"] = (
        momentum_candidate
    )

    merged["candidate"] = (
        breakout_candidate
        & momentum_candidate
    )

    merged[
        "f01_composite_signal_score"
    ] = (
        momentum_score
        + turnover_expansion
    )

    return (
        merged.sort_values(
            [
                "snapshot_time",
                "candidate",
                "f01_composite_signal_score",
                "rank_within_snapshot",
                "symbol",
            ],
            ascending=[
                True,
                False,
                False,
                True,
                True,
            ],
        )
        .reset_index(drop=True)
    )


def _validate_engine_output_times(
    frame: pd.DataFrame,
    *,
    policy: F01TrendMomentumPolicy,
    frame_name: str,
) -> pd.DataFrame:
    result = frame.copy()

    result["snapshot_time"] = pd.to_datetime(
        result["snapshot_time"],
        utc=True,
        errors="raise",
    )

    start = pd.Timestamp(
        policy.research_start
    )

    end = pd.Timestamp(
        policy.research_end_exclusive
    )

    if (
        (
            result["snapshot_time"]
            < start
        ).any()
        or (
            result["snapshot_time"]
            >= end
        ).any()
    ):
        raise F01TrendMomentumDataError(
            f"{frame_name} reaches outside "
            "the F01 research window."
        )

    return result


def run_f01_trend_momentum_engine_core(
    history: pd.DataFrame,
    ranking: pd.DataFrame,
    *,
    policy: F01TrendMomentumPolicy,
) -> F01EngineCoreArtifacts:
    signals = build_f01_trend_momentum_signals(
        history,
        ranking,
        policy=policy,
    )

    weights, trades = (
        build_volatility_breakout_weights(
            history,
            signals,
            policy=policy.to_breakout_policy(),
        )
    )

    daily = run_daily_portfolio_backtest(
        history,
        weights,
        policy=policy.to_momentum_policy(),
    )

    _require_columns(
        weights,
        required=(
            "snapshot_time",
            "symbol",
            "target_weight",
        ),
        frame_name="F01 target weights",
    )

    _require_columns(
        daily,
        required=(
            "snapshot_time",
            "equity",
        ),
        frame_name="F01 daily portfolio",
    )

    validated_weights = (
        _validate_engine_output_times(
            weights,
            policy=policy,
            frame_name="F01 target weights",
        )
    )

    validated_daily = (
        _validate_engine_output_times(
            daily,
            policy=policy,
            frame_name="F01 daily portfolio",
        )
    )

    return F01EngineCoreArtifacts(
        composite_signals=signals.copy(),
        target_weights=validated_weights,
        trade_records=trades.copy(),
        daily_portfolio=validated_daily,
    )


def assert_f01_core_not_trial_executable() -> None:
    if (
        F01_ENGINE_EXECUTION_STATUS
        != (
            "CORE_REGISTERED_NOT_TRIAL_EXECUTABLE"
        )
    ):
        raise AmsV2FamilyAdapterConfigurationError(
            "F01 trial execution was enabled without "
            "canonical artifact authorization."
        )