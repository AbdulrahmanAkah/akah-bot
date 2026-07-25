from __future__ import annotations

import copy
import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from spotbot.research.ams_v2_f01_fold_harness import (
    F01_FOLD_HARNESS_STATUS,
    F01_FOLD_HARNESS_VERSION,
    F01FoldHarnessArtifactError,
    assert_f01_fold_harness_not_trial_executable,
    run_f01_fold_execution_harness,
)
from spotbot.research.ams_v2_f01_trend_momentum import (
    F01EngineCoreArtifacts,
    F01TrendMomentumPolicy,
)
from spotbot.research.ams_v2_walk_forward_orchestrator import (
    default_ams_v2_fold_definitions,
    load_json_object,
)

ROOT = Path(__file__).resolve().parents[1]

LEDGER_PATH = (
    ROOT
    / "reports/research/"
    "ams-v2-experiment-ledger-v1.json"
)


def experiment() -> dict[str, Any]:
    return load_json_object(
        LEDGER_PATH
    )


def configuration() -> dict[str, Any]:
    value = next(
        item
        for item in experiment()[
            "alpha_configurations"
        ]
        if item["configuration_id"]
        == "AMS-V2-F01-C01"
    )

    return copy.deepcopy(value)


def fold():
    return default_ams_v2_fold_definitions()[0]


class SyntheticRunner:
    def __init__(
        self,
        *,
        mismatch_stress_trade: bool = False,
    ) -> None:
        self.costs: list[float] = []
        self.mismatch_stress_trade = (
            mismatch_stress_trade
        )

    def __call__(
        self,
        history: pd.DataFrame,
        ranking: pd.DataFrame,
        *,
        policy: F01TrendMomentumPolicy,
    ) -> F01EngineCoreArtifacts:
        cost = policy.transaction_cost_fraction

        self.costs.append(cost)

        is_stress = math.isclose(
            cost,
            0.004,
            rel_tol=0.0,
            abs_tol=1e-12,
        )

        first_exit = datetime(
            2022,
            2,
            11 if (
                self.mismatch_stress_trade
                and is_stress
            ) else 10,
            tzinfo=UTC,
        )

        trades = pd.DataFrame(
            {
                "symbol": [
                    "BTC/USDT",
                    "ETH/USDT",
                ],
                "entry_time": [
                    datetime(
                        2022,
                        2,
                        1,
                        tzinfo=UTC,
                    ),
                    datetime(
                        2022,
                        4,
                        1,
                        tzinfo=UTC,
                    ),
                ],
                "exit_time": [
                    first_exit,
                    datetime(
                        2022,
                        4,
                        10,
                        tzinfo=UTC,
                    ),
                ],
                "gross_return": [
                    0.20,
                    -0.10,
                ],
                "net_return": [
                    0.20 - cost,
                    -0.10 - cost,
                ],
                "r_multiple": [
                    2.0,
                    -1.0,
                ],
                "transaction_cost": [
                    cost,
                    cost,
                ],
            }
        )

        daily = pd.DataFrame(
            {
                "snapshot_time": [
                    datetime(
                        2022,
                        1,
                        1,
                        tzinfo=UTC,
                    ),
                    datetime(
                        2022,
                        6,
                        1,
                        tzinfo=UTC,
                    ),
                    datetime(
                        2022,
                        12,
                        31,
                        tzinfo=UTC,
                    ),
                ],
                "equity": (
                    [1.0, 0.88, 1.10]
                    if is_stress
                    else [1.0, 0.90, 1.20]
                ),
            }
        )

        signals = pd.DataFrame(
            {
                "snapshot_time": [
                    datetime(
                        2022,
                        2,
                        1,
                        tzinfo=UTC,
                    )
                ],
                "symbol": ["BTC/USDT"],
                "candidate": [True],
            }
        )

        weights = pd.DataFrame(
            {
                "snapshot_time": [
                    datetime(
                        2022,
                        2,
                        1,
                        tzinfo=UTC,
                    )
                ],
                "symbol": ["BTC/USDT"],
                "target_weight": [0.5],
            }
        )

        return F01EngineCoreArtifacts(
            composite_signals=signals,
            target_weights=weights,
            trade_records=trades,
            daily_portfolio=daily,
        )


def test_contract_and_real_stress_rerun() -> None:
    assert F01_FOLD_HARNESS_VERSION == (
        "AMS_V2_F01_FOLD_EXECUTION_HARNESS_V1"
    )

    assert F01_FOLD_HARNESS_STATUS == (
        "HARNESS_REGISTERED_NOT_TRIAL_EXECUTABLE"
    )

    assert_f01_fold_harness_not_trial_executable()

    runner = SyntheticRunner()

    result = run_f01_fold_execution_harness(
        pd.DataFrame(),
        pd.DataFrame(),
        configuration=configuration(),
        fold=fold(),
        engine_runner=runner,
    )

    assert runner.costs == pytest.approx(
        [
            0.002,
            0.004,
        ]
    )

    assert (
        result
        .stress_policy
        .transaction_cost_fraction
        == pytest.approx(0.004)
    )


def test_standardized_metrics() -> None:
    result = run_f01_fold_execution_harness(
        pd.DataFrame(),
        pd.DataFrame(),
        configuration=configuration(),
        fold=fold(),
        engine_runner=SyntheticRunner(),
    )

    metrics = result.completed_fold_metrics

    assert metrics.fold_name == "WF_2022"
    assert metrics.executed_trade_count == 2

    assert (
        metrics.base_price_gross_pnl
        == pytest.approx(0.10)
    )

    assert metrics.net_pnl == pytest.approx(
        0.096
    )

    assert metrics.total_return == pytest.approx(
        0.20
    )

    assert (
        metrics.maximum_drawdown
        == pytest.approx(0.10)
    )

    assert metrics.gross_profit == pytest.approx(
        0.198
    )

    assert (
        metrics.gross_loss_abs
        == pytest.approx(0.102)
    )

    assert metrics.total_r_multiple == pytest.approx(
        1.0
    )

    assert (
        metrics
        .stress_cost_total_return_0_004
        == pytest.approx(0.10)
    )


def test_trade_identity_mismatch_rejected() -> None:
    with pytest.raises(
        F01FoldHarnessArtifactError,
        match="different trade identities",
    ):
        run_f01_fold_execution_harness(
            pd.DataFrame(),
            pd.DataFrame(),
            configuration=configuration(),
            fold=fold(),
            engine_runner=SyntheticRunner(
                mismatch_stress_trade=True
            ),
        )


def test_configuration_is_not_mutated() -> None:
    value = configuration()
    before = copy.deepcopy(value)

    run_f01_fold_execution_harness(
        pd.DataFrame(),
        pd.DataFrame(),
        configuration=value,
        fold=fold(),
        engine_runner=SyntheticRunner(),
    )

    assert value == before


def test_summary_contract() -> None:
    result = run_f01_fold_execution_harness(
        pd.DataFrame(),
        pd.DataFrame(),
        configuration=configuration(),
        fold=fold(),
        engine_runner=SyntheticRunner(),
    )

    summary = result.to_summary()

    assert summary[
        "configuration_id"
    ] == "AMS-V2-F01-C01"

    assert summary["family_id"] == "AMS-V2-F01"
    assert summary["fold_name"] == "WF_2022"

    assert summary[
        "baseline_canonical"
    ] == {
        "canonical_trade_rows": 2,
        "canonical_portfolio_rows": 3,
    }