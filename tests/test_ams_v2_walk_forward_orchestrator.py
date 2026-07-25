from __future__ import annotations

import copy
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from spotbot.research.ams_v2_walk_forward_orchestrator import (
    BASELINE_PROCEED_DECISION,
    AmsV2CompletedFoldMetrics,
    AmsV2OrchestratorDataError,
    AmsV2TrialExecution,
    AmsV2TrialStateError,
    TrialLedgerStatus,
    TrialTerminalStatus,
    apply_trial_execution_to_ledger,
    build_pending_alpha_execution_plan,
    default_ams_v2_fold_definitions,
    evaluate_ams_v2_completed_trial,
    load_json_object,
    validate_ams_v2_experiment_ledger,
    write_json_atomically,
)

ROOT = Path(__file__).resolve().parents[1]

LEDGER_PATH = (
    ROOT
    / "reports/research/"
    "ams-v2-experiment-ledger-v1.json"
)


def pristine_ledger() -> dict[str, object]:
    import copy as copy_module

    from spotbot.research.ams_v2_walk_forward_orchestrator import (
        validate_ams_v2_experiment_ledger,
    )

    ledger = load_json_object(
        LEDGER_PATH
    )

    configurations = ledger.get(
        "alpha_configurations"
    )

    if not isinstance(
        configurations,
        list,
    ):
        raise RuntimeError(
            "Test ledger has no configuration list."
        )

    pending_template = next(
        (
            configuration
            for configuration in configurations
            if (
                isinstance(configuration, dict)
                and configuration.get("trial_status")
                == "REGISTERED_NOT_EXECUTED"
            )
        ),
        None,
    )

    if not isinstance(
        pending_template,
        dict,
    ):
        raise RuntimeError(
            "Test ledger has no pending configuration template."
        )

    all_configuration_keys = {
        str(key)
        for configuration in configurations
        if isinstance(configuration, dict)
        for key in configuration
    }

    operational_keys = {
        key
        for key in all_configuration_keys
        if (
            key == "trial_status"
            or key.endswith("_result")
            or key.endswith("_results")
            or "execution" in key.casefold()
            or "failure" in key.casefold()
            or "invalidation" in key.casefold()
            or "terminal" in key.casefold()
        )
    }

    for configuration in configurations:
        if not isinstance(
            configuration,
            dict,
        ):
            raise RuntimeError(
                "Test configuration is not an object."
            )

        for key in operational_keys:
            if key in pending_template:
                configuration[key] = (
                    copy_module.deepcopy(
                        pending_template[key]
                    )
                )
            else:
                configuration.pop(
                    key,
                    None,
                )

        configuration["trial_status"] = (
            "REGISTERED_NOT_EXECUTED"
        )

    accounting = ledger.get(
        "trial_accounting"
    )

    if not isinstance(
        accounting,
        dict,
    ):
        raise RuntimeError(
            "Test ledger has no trial accounting."
        )

    accounting["trials_executed"] = 0
    accounting["trials_invalidated"] = 0
    accounting["remaining_authorized_trials"] = 100
    accounting["test_2025_accessed"] = False
    accounting["holdout_2026_accessed"] = False

    if "family_decisions" in ledger:
        ledger["family_decisions"] = []

    if "ensemble_result" in ledger:
        ledger["ensemble_result"] = None

    for key in (
        "trial_executions",
        "completed_trials",
        "invalidated_trials",
    ):
        if key in ledger:
            ledger[key] = []

    validate_ams_v2_experiment_ledger(
        ledger
    )

    return ledger




def passing_metrics() -> tuple[
    AmsV2CompletedFoldMetrics,
    ...,
]:
    return tuple(
        AmsV2CompletedFoldMetrics(
            fold_name=definition.name,
            evaluation_start=(
                definition.evaluation_start
            ),
            evaluation_end_exclusive=(
                definition
                .evaluation_end_exclusive
            ),
            executed_trade_count=12,
            base_price_gross_pnl=0.30,
            net_pnl=0.20,
            total_return=0.15,
            maximum_drawdown=0.20,
            gross_profit=0.40,
            gross_loss_abs=0.15,
            total_r_multiple=2.40,
            stress_cost_total_return_0_004=0.08,
        )
        for definition
        in default_ams_v2_fold_definitions()
    )


def first_execution(
    terminal_status: TrialTerminalStatus,
    *,
    fold_metrics: tuple[
        AmsV2CompletedFoldMetrics,
        ...,
    ] = (),
    failure_reason: str | None = None,
    invalidation_reason: str | None = None,
) -> AmsV2TrialExecution:
    configuration = pristine_ledger()[
        "alpha_configurations"
    ][0]

    timestamp = datetime(
        2026,
        7,
        25,
        12,
        0,
        tzinfo=UTC,
    )

    return AmsV2TrialExecution(
        configuration_id=configuration[
            "configuration_id"
        ],
        family_id=configuration[
            "family_id"
        ],
        parameter_hash_sha256=configuration[
            "parameter_hash_sha256"
        ],
        source_commit="a" * 40,
        started_at=timestamp,
        completed_at=timestamp,
        terminal_status=terminal_status,
        fold_metrics=fold_metrics,
        failure_reason=failure_reason,
        invalidation_reason=invalidation_reason,
    )


def test_frozen_fold_boundaries() -> None:
    folds = default_ams_v2_fold_definitions()

    assert [
        value.name
        for value in folds
    ] == [
        "WF_2022",
        "WF_2023",
        "WF_2024",
    ]

    assert (
        folds[-1].evaluation_end_exclusive
        == datetime(
            2025,
            1,
            1,
            tzinfo=UTC,
        )
    )


def test_pending_plan_has_96_configurations() -> None:
    plan = build_pending_alpha_execution_plan(
        pristine_ledger()
    )

    assert len(plan) == 96
    assert plan[0]["configuration_id"] == (
        "AMS-V2-F01-C01"
    )
    assert plan[-1]["configuration_id"] == (
        "AMS-V2-F06-C16"
    )


def test_completed_trial_advances() -> None:
    result = evaluate_ams_v2_completed_trial(
        passing_metrics()
    )

    assert result.baseline_walk_forward[
        "decision"
    ] == BASELINE_PROCEED_DECISION

    assert result.decision == "ADVANCE"
    assert all(result.strict_gates.values())


def test_profit_factor_below_1_1_rejects() -> None:
    metrics = tuple(
        AmsV2CompletedFoldMetrics(
            fold_name=definition.name,
            evaluation_start=(
                definition.evaluation_start
            ),
            evaluation_end_exclusive=(
                definition
                .evaluation_end_exclusive
            ),
            executed_trade_count=12,
            base_price_gross_pnl=0.10,
            net_pnl=0.05,
            total_return=0.02,
            maximum_drawdown=0.20,
            gross_profit=1.05,
            gross_loss_abs=1.0,
            total_r_multiple=0.6,
            stress_cost_total_return_0_004=0.01,
        )
        for definition
        in default_ams_v2_fold_definitions()
    )

    result = evaluate_ams_v2_completed_trial(
        metrics
    )

    assert result.decision == "REJECT"

    assert not result.strict_gates[
        "aggregate_profit_factor_above_1_1"
    ]


def test_completed_execution_consumes_one() -> None:
    original = pristine_ledger()

    updated = apply_trial_execution_to_ledger(
        original,
        first_execution(
            TrialTerminalStatus.COMPLETED,
            fold_metrics=passing_metrics(),
        ),
    )

    assert updated[
        "trial_accounting"
    ]["trials_executed"] == 1

    assert updated[
        "trial_accounting"
    ]["remaining_authorized_trials"] == 99

    assert updated[
        "alpha_configurations"
    ][0]["trial_status"] == (
        TrialLedgerStatus
        .COMPLETED_ADVANCE
        .value
    )

    assert original[
        "trial_accounting"
    ]["trials_executed"] == 0


def test_failed_trial_is_consumed() -> None:
    updated = apply_trial_execution_to_ledger(
        pristine_ledger(),
        first_execution(
            TrialTerminalStatus.FAILED,
            failure_reason="Synthetic failure.",
        ),
    )

    assert updated[
        "trial_accounting"
    ]["trials_executed"] == 1

    assert updated[
        "alpha_configurations"
    ][0]["trial_status"] == (
        TrialLedgerStatus
        .FAILED_CONSUMED
        .value
    )


def test_invalidated_trial_is_consumed() -> None:
    updated = apply_trial_execution_to_ledger(
        pristine_ledger(),
        first_execution(
            TrialTerminalStatus.INVALIDATED,
            invalidation_reason="CODE_DEFECT",
        ),
    )

    assert updated[
        "trial_accounting"
    ]["trials_invalidated"] == 1


def test_consumed_configuration_cannot_rerun() -> None:
    execution = first_execution(
        TrialTerminalStatus.FAILED,
        failure_reason="Synthetic failure.",
    )

    updated = apply_trial_execution_to_ledger(
        pristine_ledger(),
        execution,
    )

    with pytest.raises(
        AmsV2TrialStateError,
        match="already consumed",
    ):
        apply_trial_execution_to_ledger(
            updated,
            execution,
        )


def test_locked_date_is_rejected() -> None:
    with pytest.raises(
        AmsV2OrchestratorDataError,
        match="locked 2025",
    ):
        AmsV2CompletedFoldMetrics(
            fold_name="WF_2022",
            evaluation_start=datetime(
                2022,
                1,
                1,
                tzinfo=UTC,
            ),
            evaluation_end_exclusive=datetime(
                2025,
                1,
                2,
                tzinfo=UTC,
            ),
            executed_trade_count=10,
            base_price_gross_pnl=0.1,
            net_pnl=0.1,
            total_return=0.1,
            maximum_drawdown=0.1,
            gross_profit=0.2,
            gross_loss_abs=0.1,
            total_r_multiple=1.0,
            stress_cost_total_return_0_004=0.05,
        )


def test_parameter_hash_mismatch_is_rejected() -> None:
    ledger = pristine_ledger()

    ledger[
        "alpha_configurations"
    ][0]["parameters"][
        "maximum_positions"
    ] = 99

    with pytest.raises(
        AmsV2OrchestratorDataError,
        match="Parameter hash mismatch",
    ):
        validate_ams_v2_experiment_ledger(
            ledger
        )


def test_atomic_write_replaces_json(
    tmp_path: Path,
) -> None:
    path = tmp_path / "ledger.json"

    write_json_atomically(
        path,
        {
            "version": 1,
        },
    )

    write_json_atomically(
        path,
        {
            "version": 2,
        },
    )

    assert json.loads(
        path.read_text(
            encoding="utf-8"
        )
    ) == {
        "version": 2,
    }

    assert not list(
        tmp_path.glob("*.tmp")
    )


def test_input_ledger_is_not_mutated() -> None:
    ledger = pristine_ledger()
    before = copy.deepcopy(ledger)

    apply_trial_execution_to_ledger(
        ledger,
        first_execution(
            TrialTerminalStatus.FAILED,
            failure_reason="Synthetic failure.",
        ),
    )

    assert ledger == before