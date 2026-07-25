from __future__ import annotations

import copy
import math
from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any, Final, Protocol

import pandas as pd

from spotbot.research.ams_v2_f01_canonical_artifacts import (
    F01CanonicalArtifacts,
    build_f01_canonical_artifacts,
)
from spotbot.research.ams_v2_f01_trend_momentum import (
    F01EngineCoreArtifacts,
    F01TrendMomentumPolicy,
    run_f01_trend_momentum_engine_core,
)
from spotbot.research.ams_v2_family_adapters import (
    AmsV2FamilyId,
    extract_completed_fold_metrics,
)
from spotbot.research.ams_v2_walk_forward_orchestrator import (
    AmsV2CompletedFoldMetrics,
    AmsV2FoldDefinition,
)

F01_FOLD_HARNESS_VERSION: Final[str] = (
    "AMS_V2_F01_FOLD_EXECUTION_HARNESS_V1"
)

F01_FOLD_HARNESS_STATUS: Final[str] = (
    "HARNESS_REGISTERED_NOT_TRIAL_EXECUTABLE"
)

STRESS_TRANSACTION_COST_FRACTION: Final[float] = 0.004


class F01FoldHarnessError(RuntimeError):
    pass


class F01FoldHarnessConfigurationError(
    F01FoldHarnessError
):
    pass


class F01FoldHarnessArtifactError(
    F01FoldHarnessError
):
    pass


class F01EngineRunner(Protocol):
    def __call__(
        self,
        history: pd.DataFrame,
        ranking: pd.DataFrame,
        *,
        policy: F01TrendMomentumPolicy,
    ) -> F01EngineCoreArtifacts:
        ...


@dataclass(frozen=True, slots=True)
class F01FoldHarnessArtifacts:
    configuration_id: str
    fold: AmsV2FoldDefinition
    baseline_policy: F01TrendMomentumPolicy
    stress_policy: F01TrendMomentumPolicy
    baseline_engine_summary: dict[str, int]
    stress_engine_summary: dict[str, int]
    baseline_canonical: F01CanonicalArtifacts
    stress_canonical: F01CanonicalArtifacts
    completed_fold_metrics: AmsV2CompletedFoldMetrics

    def to_summary(self) -> dict[str, object]:
        return {
            "configuration_id": self.configuration_id,
            "family_id": AmsV2FamilyId.F01.value,
            "fold_name": self.fold.name,
            "baseline_transaction_cost_fraction": (
                self.baseline_policy
                .transaction_cost_fraction
            ),
            "stress_transaction_cost_fraction": (
                self.stress_policy
                .transaction_cost_fraction
            ),
            "baseline_engine": dict(
                self.baseline_engine_summary
            ),
            "stress_engine": dict(
                self.stress_engine_summary
            ),
            "baseline_canonical": (
                self.baseline_canonical.to_summary()
            ),
            "stress_canonical": (
                self.stress_canonical.to_summary()
            ),
            "completed_fold_metrics": (
                self.completed_fold_metrics.to_dict()
            ),
        }


def _configuration_id(
    configuration: Mapping[str, Any],
) -> str:
    raw_value = configuration.get(
        "configuration_id"
    )

    if not isinstance(raw_value, str):
        raise F01FoldHarnessConfigurationError(
            "configuration_id must be a string."
        )

    configuration_id = raw_value.strip()

    if not configuration_id:
        raise F01FoldHarnessConfigurationError(
            "configuration_id cannot be empty."
        )

    return configuration_id


def _trade_identity(
    artifacts: F01CanonicalArtifacts,
) -> pd.DataFrame:
    return (
        artifacts.canonical_trades.loc[
            :,
            [
                "symbol",
                "entry_time",
                "exit_time",
            ],
        ]
        .sort_values(
            [
                "exit_time",
                "entry_time",
                "symbol",
            ]
        )
        .reset_index(drop=True)
    )


def _validate_baseline_stress_identity(
    baseline: F01CanonicalArtifacts,
    stress: F01CanonicalArtifacts,
) -> None:
    if not _trade_identity(
        baseline
    ).equals(
        _trade_identity(
            stress
        )
    ):
        raise F01FoldHarnessArtifactError(
            "Baseline and stress executions generated "
            "different trade identities."
        )

    baseline_times = (
        baseline.canonical_portfolio[
            "snapshot_time"
        ].reset_index(drop=True)
    )

    stress_times = (
        stress.canonical_portfolio[
            "snapshot_time"
        ].reset_index(drop=True)
    )

    if not baseline_times.equals(
        stress_times
    ):
        raise F01FoldHarnessArtifactError(
            "Baseline and stress portfolio snapshots differ."
        )


def _validate_cost_identity(
    artifacts: F01CanonicalArtifacts,
    *,
    artifact_name: str,
) -> None:
    trades = artifacts.canonical_trades

    if trades.empty:
        return

    implied_cost = (
        pd.Series(
            trades[
                "base_price_gross_pnl"
            ],
            dtype="float64",
        )
        - pd.Series(
            trades["net_pnl"],
            dtype="float64",
        )
    )

    recorded_cost = pd.Series(
        trades["transaction_cost"],
        dtype="float64",
    )

    if (
        implied_cost < -1e-12
    ).any():
        raise F01FoldHarnessArtifactError(
            f"{artifact_name} contains net PnL above "
            "gross PnL."
        )

    if not (
        implied_cost.subtract(
            recorded_cost
        ).abs()
        <= 1e-12
    ).all():
        raise F01FoldHarnessArtifactError(
            f"{artifact_name} has inconsistent "
            "transaction costs."
        )


def run_f01_fold_execution_harness(
    history: pd.DataFrame,
    ranking: pd.DataFrame,
    *,
    configuration: Mapping[str, Any],
    fold: AmsV2FoldDefinition,
    engine_runner: F01EngineRunner = (
        run_f01_trend_momentum_engine_core
    ),
) -> F01FoldHarnessArtifacts:
    configuration_copy = copy.deepcopy(
        dict(configuration)
    )

    configuration_id = _configuration_id(
        configuration_copy
    )

    baseline_policy = (
        F01TrendMomentumPolicy
        .from_registered_configuration(
            configuration_copy,
            research_start=(
                fold.evaluation_start
            ),
            research_end_exclusive=(
                fold.evaluation_end_exclusive
            ),
        )
    )

    stress_policy = replace(
        baseline_policy,
        transaction_cost_fraction=(
            STRESS_TRANSACTION_COST_FRACTION
        ),
    )

    if not math.isclose(
        stress_policy.transaction_cost_fraction,
        STRESS_TRANSACTION_COST_FRACTION,
        rel_tol=0.0,
        abs_tol=1e-12,
    ):
        raise F01FoldHarnessConfigurationError(
            "Stress cost must equal 0.004."
        )

    baseline_engine = engine_runner(
        history.copy(),
        ranking.copy(),
        policy=baseline_policy,
    )

    stress_engine = engine_runner(
        history.copy(),
        ranking.copy(),
        policy=stress_policy,
    )

    baseline_canonical = (
        build_f01_canonical_artifacts(
            raw_trade_records=(
                baseline_engine.trade_records
            ),
            raw_daily_portfolio=(
                baseline_engine.daily_portfolio
            ),
            configuration_id=configuration_id,
            fold=fold,
            transaction_cost_fraction=(
                baseline_policy
                .transaction_cost_fraction
            ),
            entry_signal_frame=(
                baseline_engine
                .composite_signals
            ),
            initial_stop_atr=float(
                baseline_policy
                .initial_stop_atr
            ),
            atr_days=int(
                getattr(
                    baseline_policy,
                    "atr_days",
                    14,
                )
            ),
        )
    )

    stress_canonical = (
        build_f01_canonical_artifacts(
            raw_trade_records=(
                stress_engine.trade_records
            ),
            raw_daily_portfolio=(
                stress_engine.daily_portfolio
            ),
            configuration_id=configuration_id,
            fold=fold,
            transaction_cost_fraction=(
                stress_policy
                .transaction_cost_fraction
            ),
            entry_signal_frame=(
                stress_engine
                .composite_signals
            ),
            initial_stop_atr=float(
                stress_policy
                .initial_stop_atr
            ),
            atr_days=int(
                getattr(
                    stress_policy,
                    "atr_days",
                    14,
                )
            ),
        )
    )

    _validate_cost_identity(
        baseline_canonical,
        artifact_name="Baseline trades",
    )

    _validate_cost_identity(
        stress_canonical,
        artifact_name="Stress trades",
    )

    _validate_baseline_stress_identity(
        baseline_canonical,
        stress_canonical,
    )

    metrics = extract_completed_fold_metrics(
        configuration_id=configuration_id,
        family_id=AmsV2FamilyId.F01,
        fold=fold,
        baseline_portfolio_frame=(
            baseline_canonical
            .canonical_portfolio
        ),
        stress_portfolio_frame=(
            stress_canonical
            .canonical_portfolio
        ),
        canonical_trade_frame=(
            baseline_canonical
            .canonical_trades
        ),
        baseline_transaction_cost_fraction=(
            baseline_policy
            .transaction_cost_fraction
        ),
    )

    return F01FoldHarnessArtifacts(
        configuration_id=configuration_id,
        fold=fold,
        baseline_policy=baseline_policy,
        stress_policy=stress_policy,
        baseline_engine_summary=(
            baseline_engine.to_summary()
        ),
        stress_engine_summary=(
            stress_engine.to_summary()
        ),
        baseline_canonical=baseline_canonical,
        stress_canonical=stress_canonical,
        completed_fold_metrics=metrics,
    )


def assert_f01_fold_harness_not_trial_executable(
) -> None:
    if F01_FOLD_HARNESS_STATUS != (
        "HARNESS_REGISTERED_NOT_TRIAL_EXECUTABLE"
    ):
        raise F01FoldHarnessConfigurationError(
            "F01 trial execution was enabled before "
            "real-data preflight authorization."
        )