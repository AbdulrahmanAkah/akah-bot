from __future__ import annotations

import copy
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import numpy as np
import pandas as pd

from spotbot.research.ams_v2_walk_forward_orchestrator import (
    AmsV2CompletedFoldMetrics,
    AmsV2FoldDefinition,
    validate_ams_v2_experiment_ledger,
)

ADAPTER_CONTRACT_VERSION = (
    "AMS_V2_FAMILY_ADAPTER_CONTRACTS_V1"
)

STRESS_TRANSACTION_COST_FRACTION = 0.004


class AmsV2FamilyAdapterError(RuntimeError):
    pass


class AmsV2FamilyAdapterConfigurationError(
    AmsV2FamilyAdapterError
):
    pass


class AmsV2CanonicalArtifactError(
    AmsV2FamilyAdapterError
):
    pass


class AmsV2FamilyId(StrEnum):
    F01 = "AMS-V2-F01"
    F02 = "AMS-V2-F02"
    F03 = "AMS-V2-F03"
    F04 = "AMS-V2-F04"
    F05 = "AMS-V2-F05"
    F06 = "AMS-V2-F06"


class AdapterImplementationKind(StrEnum):
    COMPOSITE_ENGINE_REQUIRED = (
        "COMPOSITE_ENGINE_REQUIRED"
    )
    DEDICATED_ADAPTER_REQUIRED = (
        "DEDICATED_ADAPTER_REQUIRED"
    )
    NEW_ENGINE_REQUIRED = "NEW_ENGINE_REQUIRED"


class AdapterExecutionStatus(StrEnum):
    CONTRACT_REGISTERED_NOT_EXECUTABLE = (
        "CONTRACT_REGISTERED_NOT_EXECUTABLE"
    )
    EXECUTABLE = "EXECUTABLE"


@dataclass(frozen=True, slots=True)
class FamilyAdapterSpecification:
    family_id: AmsV2FamilyId
    family_name: str
    implementation_kind: AdapterImplementationKind
    execution_status: AdapterExecutionStatus
    required_parameter_keys: tuple[str, ...]
    candidate_modules: tuple[str, ...]
    notes: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "family_id": self.family_id.value,
            "family_name": self.family_name,
            "implementation_kind": (
                self.implementation_kind.value
            ),
            "execution_status": (
                self.execution_status.value
            ),
            "required_parameter_keys": list(
                self.required_parameter_keys
            ),
            "candidate_modules": list(
                self.candidate_modules
            ),
            "notes": list(self.notes),
        }


def _specification(
    family_id: AmsV2FamilyId,
    family_name: str,
    implementation_kind: AdapterImplementationKind,
    required_parameter_keys: Sequence[str],
    candidate_modules: Sequence[str],
    *notes: str,
) -> FamilyAdapterSpecification:
    keys = tuple(required_parameter_keys)

    if not keys or len(keys) != len(set(keys)):
        raise AmsV2FamilyAdapterConfigurationError(
            f"Invalid parameter contract for {family_id}."
        )

    return FamilyAdapterSpecification(
        family_id=family_id,
        family_name=family_name,
        implementation_kind=implementation_kind,
        execution_status=(
            AdapterExecutionStatus
            .CONTRACT_REGISTERED_NOT_EXECUTABLE
        ),
        required_parameter_keys=keys,
        candidate_modules=tuple(candidate_modules),
        notes=tuple(notes),
    )


def default_family_adapter_registry(
) -> dict[AmsV2FamilyId, FamilyAdapterSpecification]:
    return {
        AmsV2FamilyId.F01: _specification(
            AmsV2FamilyId.F01,
            "TREND_MOMENTUM",
            (
                AdapterImplementationKind
                .COMPOSITE_ENGINE_REQUIRED
            ),
            (
                "breakout_lookback_days",
                "initial_stop_atr",
                "maximum_holding_days",
                "maximum_positions",
                "momentum_lookback_days",
                "ranking_maximum",
                "trailing_stop_atr",
                "transaction_cost_fraction",
                "turnover_expansion_minimum",
            ),
            (
                "momentum_reacceleration",
                "volatility_breakout",
            ),
            (
                "Requires one composite trend, momentum "
                "and breakout engine."
            ),
        ),
        AmsV2FamilyId.F02: _specification(
            AmsV2FamilyId.F02,
            "PULLBACK_REACCELERATION",
            (
                AdapterImplementationKind
                .DEDICATED_ADAPTER_REQUIRED
            ),
            (
                "ema_reclaim_days",
                "maximum_holding_days",
                "maximum_positions",
                "maximum_pullback",
                "momentum_days",
                "ranking_maximum",
                "relative_strength_days",
                "trailing_stop_atr",
                "transaction_cost_fraction",
            ),
            ("momentum_reacceleration",),
            "Requires V2-specific pullback logic.",
        ),
        AmsV2FamilyId.F03: _specification(
            AmsV2FamilyId.F03,
            "VOLATILITY_COMPRESSION_EXPANSION",
            (
                AdapterImplementationKind
                .COMPOSITE_ENGINE_REQUIRED
            ),
            (
                "breakout_lookback_days",
                "compression_lookback_days",
                "compression_percentile_maximum",
                "initial_stop_atr",
                "maximum_holding_days",
                "maximum_positions",
                "minimum_turnover_expansion",
                "ranking_maximum",
                "trailing_stop_atr",
                "transaction_cost_fraction",
            ),
            (
                "compression_expansion",
                "volatility_breakout",
            ),
            "Requires explicit compression-breakout sequencing.",
        ),
        AmsV2FamilyId.F04: _specification(
            AmsV2FamilyId.F04,
            "LIQUIDITY_SWEEP_RECOVERY",
            (
                AdapterImplementationKind
                .DEDICATED_ADAPTER_REQUIRED
            ),
            (
                "initial_stop_atr",
                "maximum_holding_days",
                "maximum_positions",
                "minimum_turnover_expansion",
                "profit_trail_atr",
                "ranking_maximum",
                "recovery_close_fraction",
                "sweep_lookback_days",
                "transaction_cost_fraction",
            ),
            ("liquidity_sweep_reversal",),
            "Requires canonical V2 parameter translation.",
        ),
        AmsV2FamilyId.F05: _specification(
            AmsV2FamilyId.F05,
            "CAPITULATION_RECOVERY",
            AdapterImplementationKind.NEW_ENGINE_REQUIRED,
            (
                "drawdown_lookback_days",
                "drawdown_threshold",
                "initial_stop_atr",
                "maximum_holding_days",
                "maximum_positions",
                "minimum_turnover_expansion",
                "ranking_maximum",
                "rebound_lookback_days",
                "trailing_stop_atr",
                "transaction_cost_fraction",
            ),
            ("liquidity_sweep_reversal",),
            "A new capitulation-recovery engine is mandatory.",
        ),
        AmsV2FamilyId.F06: _specification(
            AmsV2FamilyId.F06,
            "CROSS_SECTIONAL_LEADERSHIP",
            (
                AdapterImplementationKind
                .DEDICATED_ADAPTER_REQUIRED
            ),
            (
                "maximum_positions",
                "minimum_liquidity_rank_percentile",
                "ranking_relative_strength_days",
                "ranking_return_days",
                "rebalance_days",
                "transaction_cost_fraction",
            ),
            ("cross_sectional_rotation",),
            "Requires V2 regime and leadership constraints.",
        ),
    }


def validate_registered_family_configuration(
    configuration: Mapping[str, Any],
) -> FamilyAdapterSpecification:
    raw_family_id = configuration.get(
        "family_id"
    )

    if not isinstance(raw_family_id, str):
        raise AmsV2FamilyAdapterConfigurationError(
            "family_id must be a string."
        )

    try:
        family_id = AmsV2FamilyId(
            raw_family_id
        )
    except ValueError as error:
        raise AmsV2FamilyAdapterConfigurationError(
            f"Unknown family ID: {raw_family_id!r}."
        ) from error

    specification = (
        default_family_adapter_registry()[
            family_id
        ]
    )

    raw_parameters = configuration.get(
        "parameters"
    )

    if not isinstance(
        raw_parameters,
        Mapping,
    ):
        raise AmsV2FamilyAdapterConfigurationError(
            f"{family_id} parameters must be a mapping."
        )

    parameters = {
        str(key): value
        for key, value in raw_parameters.items()
    }

    observed_keys = set(parameters)
    expected_keys = set(
        specification.required_parameter_keys
    )

    missing = sorted(
        expected_keys - observed_keys
    )

    unexpected = sorted(
        observed_keys - expected_keys
    )

    if missing or unexpected:
        raise AmsV2FamilyAdapterConfigurationError(
            f"{family_id} parameter contract mismatch; "
            f"missing={missing}, unexpected={unexpected}."
        )

    raw_cost = parameters.get(
        "transaction_cost_fraction"
    )

    if raw_cost is None:
        raise AmsV2FamilyAdapterConfigurationError(
            f"{family_id} transaction cost is missing."
        )

    try:
        transaction_cost = float(
            raw_cost
        )
    except (
        TypeError,
        ValueError,
    ) as error:
        raise AmsV2FamilyAdapterConfigurationError(
            f"{family_id} transaction cost is not numeric."
        ) from error

    if (
        not math.isfinite(transaction_cost)
        or not 0.0 <= transaction_cost <= 0.01
    ):
        raise AmsV2FamilyAdapterConfigurationError(
            f"{family_id} transaction cost is outside "
            "[0, 0.01]."
        )

    return specification


def build_family_adapter_plan(
    experiment_ledger: Mapping[str, Any],
) -> tuple[dict[str, object], ...]:
    validate_ams_v2_experiment_ledger(
        experiment_ledger
    )

    raw_configurations = experiment_ledger.get(
        "alpha_configurations"
    )

    if not isinstance(
        raw_configurations,
        list,
    ):
        raise AmsV2FamilyAdapterConfigurationError(
            "alpha_configurations must be a list."
        )

    plan: list[dict[str, object]] = []

    for raw_configuration in raw_configurations:
        if not isinstance(
            raw_configuration,
            Mapping,
        ):
            raise AmsV2FamilyAdapterConfigurationError(
                "Alpha configuration must be a mapping."
            )

        configuration = {
            str(key): value
            for key, value
            in raw_configuration.items()
        }

        specification = (
            validate_registered_family_configuration(
                configuration
            )
        )

        plan.append(
            {
                "configuration_id": str(
                    configuration[
                        "configuration_id"
                    ]
                ),
                "family_id": (
                    specification.family_id.value
                ),
                "execution_status": (
                    specification.execution_status.value
                ),
                "implementation_kind": (
                    specification.implementation_kind.value
                ),
                "candidate_modules": list(
                    specification.candidate_modules
                ),
                "parameters": copy.deepcopy(
                    configuration["parameters"]
                ),
            }
        )

    return tuple(
        sorted(
            plan,
            key=lambda item: str(
                item["configuration_id"]
            ),
        )
    )


def assert_no_family_adapter_is_executable() -> None:
    executable = [
        specification.family_id.value
        for specification
        in default_family_adapter_registry().values()
        if specification.execution_status
        == AdapterExecutionStatus.EXECUTABLE
    ]

    if executable:
        raise AmsV2FamilyAdapterConfigurationError(
            f"Executable adapters are not authorized: {executable}."
        )


TRADE_COLUMNS = (
    "trade_id",
    "configuration_id",
    "family_id",
    "fold_name",
    "symbol",
    "entry_time",
    "exit_time",
    "base_price_gross_pnl",
    "net_pnl",
    "r_multiple",
    "transaction_cost",
)


PORTFOLIO_COLUMNS = (
    "snapshot_time",
    "equity",
    "transaction_cost_fraction",
)


def _require_columns(
    frame: pd.DataFrame,
    required: Sequence[str],
    artifact_name: str,
) -> None:
    missing = sorted(
        set(required) - set(frame.columns)
    )

    if missing:
        raise AmsV2CanonicalArtifactError(
            f"{artifact_name} is missing columns: {missing}."
        )


def _numeric_series(
    frame: pd.DataFrame,
    column: str,
) -> pd.Series:
    try:
        series = pd.Series(
            pd.to_numeric(
                frame.loc[:, column],
                errors="raise",
            ),
            index=frame.index,
            dtype="float64",
        )
    except (
        TypeError,
        ValueError,
    ) as error:
        raise AmsV2CanonicalArtifactError(
            f"{column} is not numeric."
        ) from error

    values = series.to_numpy(
        dtype=float
    )

    if not bool(
        np.isfinite(values).all()
    ):
        raise AmsV2CanonicalArtifactError(
            f"{column} contains non-finite values."
        )

    return series


def validate_canonical_trade_frame(
    frame: pd.DataFrame,
    *,
    configuration_id: str,
    family_id: AmsV2FamilyId,
    fold: AmsV2FoldDefinition,
) -> pd.DataFrame:
    _require_columns(
        frame,
        TRADE_COLUMNS,
        "Canonical trade frame",
    )

    result = frame.copy()

    if result["trade_id"].duplicated().any():
        raise AmsV2CanonicalArtifactError(
            "Canonical trade IDs are not unique."
        )

    expected_values = {
        "configuration_id": configuration_id,
        "family_id": family_id.value,
        "fold_name": fold.name,
    }

    for column, expected in expected_values.items():
        observed = set(
            result[column].astype(str)
        )

        if observed and observed != {
            expected
        }:
            raise AmsV2CanonicalArtifactError(
                f"{column} does not match {expected!r}."
            )

    result["entry_time"] = pd.to_datetime(
        result["entry_time"],
        utc=True,
        errors="raise",
    )

    result["exit_time"] = pd.to_datetime(
        result["exit_time"],
        utc=True,
        errors="raise",
    )

    if (
        result["exit_time"]
        < result["entry_time"]
    ).any():
        raise AmsV2CanonicalArtifactError(
            "A trade exits before entry."
        )

    start = pd.Timestamp(
        fold.evaluation_start
    )

    end = pd.Timestamp(
        fold.evaluation_end_exclusive
    )

    for column in (
        "entry_time",
        "exit_time",
    ):
        if (
            (result[column] < start).any()
            or (result[column] >= end).any()
        ):
            raise AmsV2CanonicalArtifactError(
                f"{column} falls outside {fold.name}."
            )

    for column in (
        "base_price_gross_pnl",
        "net_pnl",
        "r_multiple",
        "transaction_cost",
    ):
        result[column] = _numeric_series(
            result,
            column,
        )

    if (
        result["transaction_cost"] < 0.0
    ).any():
        raise AmsV2CanonicalArtifactError(
            "Transaction cost cannot be negative."
        )

    return (
        result.sort_values(
            [
                "exit_time",
                "trade_id",
            ]
        )
        .reset_index(drop=True)
    )


def validate_canonical_portfolio_frame(
    frame: pd.DataFrame,
    *,
    fold: AmsV2FoldDefinition,
    expected_cost: float,
    artifact_name: str,
) -> pd.DataFrame:
    _require_columns(
        frame,
        PORTFOLIO_COLUMNS,
        artifact_name,
    )

    if len(frame) < 2:
        raise AmsV2CanonicalArtifactError(
            f"{artifact_name} requires at least two rows."
        )

    result = frame.copy()

    result["snapshot_time"] = pd.to_datetime(
        result["snapshot_time"],
        utc=True,
        errors="raise",
    )

    if result["snapshot_time"].duplicated().any():
        raise AmsV2CanonicalArtifactError(
            f"{artifact_name} has duplicate snapshots."
        )

    result = (
        result.sort_values(
            "snapshot_time"
        )
        .reset_index(drop=True)
    )

    start = pd.Timestamp(
        fold.evaluation_start
    )

    end = pd.Timestamp(
        fold.evaluation_end_exclusive
    )

    if (
        (result["snapshot_time"] < start).any()
        or (result["snapshot_time"] >= end).any()
    ):
        raise AmsV2CanonicalArtifactError(
            f"{artifact_name} reaches outside {fold.name}."
        )

    equity = _numeric_series(
        result,
        "equity",
    )

    if (equity <= 0.0).any():
        raise AmsV2CanonicalArtifactError(
            f"{artifact_name} equity must stay positive."
        )

    costs = _numeric_series(
        result,
        "transaction_cost_fraction",
    )

    if not bool(
        np.isclose(
            costs.to_numpy(dtype=float),
            expected_cost,
            rtol=0.0,
            atol=1e-12,
        ).all()
    ):
        raise AmsV2CanonicalArtifactError(
            f"{artifact_name} transaction cost does not "
            f"equal {expected_cost}."
        )

    result["equity"] = equity
    result["transaction_cost_fraction"] = costs

    return result


def _total_return(
    equity: pd.Series,
) -> float:
    return (
        float(equity.iloc[-1])
        / float(equity.iloc[0])
    ) - 1.0


def _drawdown_magnitude(
    equity: pd.Series,
) -> float:
    drawdown = (
        equity / equity.cummax()
    ) - 1.0

    return abs(
        float(drawdown.min())
    )


def extract_completed_fold_metrics(
    *,
    configuration_id: str,
    family_id: AmsV2FamilyId,
    fold: AmsV2FoldDefinition,
    baseline_portfolio_frame: pd.DataFrame,
    stress_portfolio_frame: pd.DataFrame,
    canonical_trade_frame: pd.DataFrame,
    baseline_transaction_cost_fraction: float,
) -> AmsV2CompletedFoldMetrics:
    baseline = validate_canonical_portfolio_frame(
        baseline_portfolio_frame,
        fold=fold,
        expected_cost=(
            baseline_transaction_cost_fraction
        ),
        artifact_name="Baseline portfolio frame",
    )

    stress = validate_canonical_portfolio_frame(
        stress_portfolio_frame,
        fold=fold,
        expected_cost=(
            STRESS_TRANSACTION_COST_FRACTION
        ),
        artifact_name="Stress portfolio frame",
    )

    trades = validate_canonical_trade_frame(
        canonical_trade_frame,
        configuration_id=configuration_id,
        family_id=family_id,
        fold=fold,
    )

    if not baseline[
        "snapshot_time"
    ].equals(
        stress["snapshot_time"]
    ):
        raise AmsV2CanonicalArtifactError(
            "Baseline and stress snapshots differ."
        )

    baseline_equity = pd.Series(
        baseline["equity"],
        dtype="float64",
    )

    stress_equity = pd.Series(
        stress["equity"],
        dtype="float64",
    )

    net_pnl = pd.Series(
        trades["net_pnl"],
        dtype="float64",
    )

    positive = net_pnl[
        net_pnl > 0.0
    ]

    negative = net_pnl[
        net_pnl < 0.0
    ]

    return AmsV2CompletedFoldMetrics(
        fold_name=fold.name,
        evaluation_start=fold.evaluation_start,
        evaluation_end_exclusive=(
            fold.evaluation_end_exclusive
        ),
        executed_trade_count=len(trades),
        base_price_gross_pnl=float(
            pd.Series(
                trades[
                    "base_price_gross_pnl"
                ],
                dtype="float64",
            ).sum()
        ),
        net_pnl=float(net_pnl.sum()),
        total_return=_total_return(
            baseline_equity
        ),
        maximum_drawdown=(
            _drawdown_magnitude(
                baseline_equity
            )
        ),
        gross_profit=float(
            positive.sum()
        ),
        gross_loss_abs=abs(
            float(negative.sum())
        ),
        total_r_multiple=float(
            pd.Series(
                trades["r_multiple"],
                dtype="float64",
            ).sum()
        ),
        stress_cost_total_return_0_004=(
            _total_return(
                stress_equity
            )
        ),
    )