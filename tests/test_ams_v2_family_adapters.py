from __future__ import annotations

import copy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from spotbot.research.ams_v2_family_adapters import (
    ADAPTER_CONTRACT_VERSION,
    STRESS_TRANSACTION_COST_FRACTION,
    AdapterExecutionStatus,
    AdapterImplementationKind,
    AmsV2CanonicalArtifactError,
    AmsV2FamilyAdapterConfigurationError,
    AmsV2FamilyId,
    assert_no_family_adapter_is_executable,
    build_family_adapter_plan,
    default_family_adapter_registry,
    extract_completed_fold_metrics,
    validate_registered_family_configuration,
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


def ledger() -> dict[str, Any]:
    return load_json_object(
        LEDGER_PATH
    )


def fold():
    return default_ams_v2_fold_definitions()[0]


def portfolio(
    equity: list[float],
    cost: float,
) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "snapshot_time": [
                datetime(2022, 1, 1, tzinfo=UTC),
                datetime(2022, 6, 1, tzinfo=UTC),
                datetime(2022, 12, 31, tzinfo=UTC),
            ],
            "equity": equity,
            "transaction_cost_fraction": [
                cost,
                cost,
                cost,
            ],
        }
    )


def trades() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "trade_id": ["T1", "T2", "T3"],
            "configuration_id": [
                "AMS-V2-F01-C01",
            ]
            * 3,
            "family_id": [
                "AMS-V2-F01",
            ]
            * 3,
            "fold_name": [
                "WF_2022",
            ]
            * 3,
            "symbol": [
                "BTC/USDT",
                "ETH/USDT",
                "SOL/USDT",
            ],
            "entry_time": [
                datetime(2022, 2, 1, tzinfo=UTC),
                datetime(2022, 4, 1, tzinfo=UTC),
                datetime(2022, 8, 1, tzinfo=UTC),
            ],
            "exit_time": [
                datetime(2022, 2, 10, tzinfo=UTC),
                datetime(2022, 4, 10, tzinfo=UTC),
                datetime(2022, 8, 10, tzinfo=UTC),
            ],
            "base_price_gross_pnl": [
                0.20,
                -0.10,
                0.15,
            ],
            "net_pnl": [
                0.18,
                -0.12,
                0.12,
            ],
            "r_multiple": [
                2.0,
                -1.0,
                1.5,
            ],
            "transaction_cost": [
                0.02,
                0.02,
                0.03,
            ],
        }
    )


def test_registry_contract() -> None:
    registry = default_family_adapter_registry()

    assert ADAPTER_CONTRACT_VERSION == (
        "AMS_V2_FAMILY_ADAPTER_CONTRACTS_V1"
    )

    assert len(registry) == 6

    assert all(
        item.execution_status
        == (
            AdapterExecutionStatus
            .CONTRACT_REGISTERED_NOT_EXECUTABLE
        )
        for item in registry.values()
    )

    assert_no_family_adapter_is_executable()


def test_f01_and_f05_require_correct_engine_types() -> None:
    registry = default_family_adapter_registry()

    assert registry[
        AmsV2FamilyId.F01
    ].implementation_kind == (
        AdapterImplementationKind
        .COMPOSITE_ENGINE_REQUIRED
    )

    assert registry[
        AmsV2FamilyId.F05
    ].implementation_kind == (
        AdapterImplementationKind
        .NEW_ENGINE_REQUIRED
    )


def test_all_96_configurations_match_contracts() -> None:
    plan = build_family_adapter_plan(
        ledger()
    )

    assert len(plan) == 96


def test_missing_transaction_cost_is_rejected() -> None:
    configuration = copy.deepcopy(
        ledger()[
            "alpha_configurations"
        ][0]
    )

    configuration["parameters"].pop(
        "transaction_cost_fraction"
    )

    with pytest.raises(
        AmsV2FamilyAdapterConfigurationError,
        match="parameter contract mismatch",
    ):
        validate_registered_family_configuration(
            configuration
        )


def test_unexpected_parameter_is_rejected() -> None:
    configuration = copy.deepcopy(
        ledger()[
            "alpha_configurations"
        ][0]
    )

    configuration[
        "parameters"
    ]["unexpected"] = 1

    with pytest.raises(
        AmsV2FamilyAdapterConfigurationError,
        match="parameter contract mismatch",
    ):
        validate_registered_family_configuration(
            configuration
        )


def test_metric_extraction() -> None:
    metrics = extract_completed_fold_metrics(
        configuration_id="AMS-V2-F01-C01",
        family_id=AmsV2FamilyId.F01,
        fold=fold(),
        baseline_portfolio_frame=portfolio(
            [1.0, 0.9, 1.2],
            0.002,
        ),
        stress_portfolio_frame=portfolio(
            [1.0, 0.88, 1.1],
            STRESS_TRANSACTION_COST_FRACTION,
        ),
        canonical_trade_frame=trades(),
        baseline_transaction_cost_fraction=0.002,
    )

    assert metrics.executed_trade_count == 3
    assert metrics.base_price_gross_pnl == pytest.approx(0.25)
    assert metrics.net_pnl == pytest.approx(0.18)
    assert metrics.total_return == pytest.approx(0.20)
    assert metrics.maximum_drawdown == pytest.approx(0.10)
    assert metrics.gross_profit == pytest.approx(0.30)
    assert metrics.gross_loss_abs == pytest.approx(0.12)
    assert metrics.total_r_multiple == pytest.approx(2.50)
    assert (
        metrics.stress_cost_total_return_0_004
        == pytest.approx(0.10)
    )


def test_duplicate_trade_is_rejected() -> None:
    trade_frame = trades()

    trade_frame.loc[1, "trade_id"] = "T1"

    with pytest.raises(
        AmsV2CanonicalArtifactError,
        match="not unique",
    ):
        extract_completed_fold_metrics(
            configuration_id="AMS-V2-F01-C01",
            family_id=AmsV2FamilyId.F01,
            fold=fold(),
            baseline_portfolio_frame=portfolio(
                [1.0, 0.9, 1.2],
                0.002,
            ),
            stress_portfolio_frame=portfolio(
                [1.0, 0.88, 1.1],
                0.004,
            ),
            canonical_trade_frame=trade_frame,
            baseline_transaction_cost_fraction=0.002,
        )


def test_wrong_stress_cost_is_rejected() -> None:
    with pytest.raises(
        AmsV2CanonicalArtifactError,
        match="does not equal 0.004",
    ):
        extract_completed_fold_metrics(
            configuration_id="AMS-V2-F01-C01",
            family_id=AmsV2FamilyId.F01,
            fold=fold(),
            baseline_portfolio_frame=portfolio(
                [1.0, 0.9, 1.2],
                0.002,
            ),
            stress_portfolio_frame=portfolio(
                [1.0, 0.88, 1.1],
                0.003,
            ),
            canonical_trade_frame=trades(),
            baseline_transaction_cost_fraction=0.002,
        )


def test_snapshot_mismatch_is_rejected() -> None:
    stress = portfolio(
        [1.0, 0.88, 1.1],
        0.004,
    )

    stress.loc[
        1,
        "snapshot_time",
    ] = datetime(
        2022,
        7,
        1,
        tzinfo=UTC,
    )

    with pytest.raises(
        AmsV2CanonicalArtifactError,
        match="snapshots differ",
    ):
        extract_completed_fold_metrics(
            configuration_id="AMS-V2-F01-C01",
            family_id=AmsV2FamilyId.F01,
            fold=fold(),
            baseline_portfolio_frame=portfolio(
                [1.0, 0.9, 1.2],
                0.002,
            ),
            stress_portfolio_frame=stress,
            canonical_trade_frame=trades(),
            baseline_transaction_cost_fraction=0.002,
        )