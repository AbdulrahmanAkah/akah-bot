from __future__ import annotations

import copy
import json
import math
import os
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from spotbot.research.ams_v2_protocol import (
    PROTOCOL_ID,
    canonical_sha256,
)
from spotbot.research.walk_forward import (
    FoldMetricSnapshot,
    default_family_advancement_rules,
    default_fold_pass_rules,
    evaluate_walk_forward_family,
)

ORCHESTRATOR_VERSION = (
    "AMS_V2_WALK_FORWARD_ORCHESTRATOR_V1"
)

BASELINE_PROCEED_DECISION = (
    "PROCEED_TO_FROZEN_TEST"
)

LOCKED_TEST_START = datetime(
    2025,
    1,
    1,
    tzinfo=UTC,
)


class AmsV2OrchestratorError(RuntimeError):
    pass


class AmsV2OrchestratorDataError(
    AmsV2OrchestratorError
):
    pass


class AmsV2TrialStateError(
    AmsV2OrchestratorError
):
    pass


class TrialTerminalStatus(StrEnum):
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    INVALIDATED = "INVALIDATED"


class TrialLedgerStatus(StrEnum):
    REGISTERED_NOT_EXECUTED = (
        "REGISTERED_NOT_EXECUTED"
    )
    COMPLETED_ADVANCE = "COMPLETED_ADVANCE"
    COMPLETED_REJECTED = "COMPLETED_REJECTED"
    FAILED_CONSUMED = "FAILED_CONSUMED"
    INVALIDATED_CONSUMED = "INVALIDATED_CONSUMED"


ALLOWED_INVALIDATION_REASONS = {
    "CODE_DEFECT",
    "DATA_CORRUPTION",
    "PROTOCOL_VIOLATION",
}


@dataclass(frozen=True, slots=True)
class AmsV2FoldDefinition:
    name: str
    train_start: datetime
    train_end_exclusive: datetime
    evaluation_start: datetime
    evaluation_end_exclusive: datetime

    def __post_init__(self) -> None:
        timestamps = (
            self.train_start,
            self.train_end_exclusive,
            self.evaluation_start,
            self.evaluation_end_exclusive,
        )

        if any(
            value.tzinfo is None
            or value.utcoffset() is None
            for value in timestamps
        ):
            raise AmsV2OrchestratorDataError(
                "Fold timestamps must be timezone-aware."
            )

        if not (
            self.train_start
            < self.train_end_exclusive
            == self.evaluation_start
            < self.evaluation_end_exclusive
            <= LOCKED_TEST_START
        ):
            raise AmsV2OrchestratorDataError(
                f"Invalid frozen fold: {self.name}."
            )

    def to_dict(self) -> dict[str, str]:
        return {
            "name": self.name,
            "train_start": self.train_start.isoformat(),
            "train_end_exclusive": (
                self.train_end_exclusive.isoformat()
            ),
            "evaluation_start": (
                self.evaluation_start.isoformat()
            ),
            "evaluation_end_exclusive": (
                self.evaluation_end_exclusive.isoformat()
            ),
        }


def default_ams_v2_fold_definitions(
) -> tuple[AmsV2FoldDefinition, ...]:
    start = datetime(
        2021,
        7,
        20,
        tzinfo=UTC,
    )

    boundaries = (
        (
            "WF_2022",
            datetime(2022, 1, 1, tzinfo=UTC),
            datetime(2023, 1, 1, tzinfo=UTC),
        ),
        (
            "WF_2023",
            datetime(2023, 1, 1, tzinfo=UTC),
            datetime(2024, 1, 1, tzinfo=UTC),
        ),
        (
            "WF_2024",
            datetime(2024, 1, 1, tzinfo=UTC),
            LOCKED_TEST_START,
        ),
    )

    return tuple(
        AmsV2FoldDefinition(
            name=name,
            train_start=start,
            train_end_exclusive=evaluation_start,
            evaluation_start=evaluation_start,
            evaluation_end_exclusive=evaluation_end,
        )
        for (
            name,
            evaluation_start,
            evaluation_end,
        ) in boundaries
    )


@dataclass(frozen=True, slots=True)
class AmsV2CompletedFoldMetrics:
    fold_name: str
    evaluation_start: datetime
    evaluation_end_exclusive: datetime
    executed_trade_count: int
    base_price_gross_pnl: float
    net_pnl: float
    total_return: float
    maximum_drawdown: float
    gross_profit: float
    gross_loss_abs: float
    total_r_multiple: float
    stress_cost_total_return_0_004: float

    def __post_init__(self) -> None:
        if (
            self.evaluation_start.tzinfo is None
            or self.evaluation_start.utcoffset() is None
            or self.evaluation_end_exclusive.tzinfo is None
            or self.evaluation_end_exclusive.utcoffset()
            is None
        ):
            raise AmsV2OrchestratorDataError(
                "Evaluation timestamps must be timezone-aware."
            )

        if not (
            self.evaluation_start
            < self.evaluation_end_exclusive
            <= LOCKED_TEST_START
        ):
            raise AmsV2OrchestratorDataError(
                "Fold metrics reach the locked 2025 test."
            )

        if self.executed_trade_count < 0:
            raise AmsV2OrchestratorDataError(
                "Trade count cannot be negative."
            )

        values = (
            self.base_price_gross_pnl,
            self.net_pnl,
            self.total_return,
            self.maximum_drawdown,
            self.gross_profit,
            self.gross_loss_abs,
            self.total_r_multiple,
            self.stress_cost_total_return_0_004,
        )

        if not all(
            math.isfinite(value)
            for value in values
        ):
            raise AmsV2OrchestratorDataError(
                "Fold metrics contain non-finite values."
            )

        if not 0.0 <= self.maximum_drawdown <= 1.0:
            raise AmsV2OrchestratorDataError(
                "Maximum drawdown must be inside [0, 1]."
            )

        if (
            self.gross_profit < 0.0
            or self.gross_loss_abs < 0.0
        ):
            raise AmsV2OrchestratorDataError(
                "Gross profit/loss magnitudes cannot be negative."
            )

        if (
            self.total_return <= -1.0
            or self.stress_cost_total_return_0_004
            <= -1.0
        ):
            raise AmsV2OrchestratorDataError(
                "Fold return implies complete capital loss."
            )

    def to_snapshot(self) -> FoldMetricSnapshot:
        return FoldMetricSnapshot(
            fold_name=self.fold_name,
            executed_trade_count=(
                self.executed_trade_count
            ),
            base_price_gross_pnl=(
                self.base_price_gross_pnl
            ),
            net_pnl=self.net_pnl,
            total_return=self.total_return,
            maximum_drawdown=self.maximum_drawdown,
            gross_profit=self.gross_profit,
            gross_loss_abs=self.gross_loss_abs,
            total_r_multiple=self.total_r_multiple,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "fold_name": self.fold_name,
            "evaluation_start": (
                self.evaluation_start.isoformat()
            ),
            "evaluation_end_exclusive": (
                self.evaluation_end_exclusive.isoformat()
            ),
            "executed_trade_count": (
                self.executed_trade_count
            ),
            "base_price_gross_pnl": (
                self.base_price_gross_pnl
            ),
            "net_pnl": self.net_pnl,
            "total_return": self.total_return,
            "maximum_drawdown": self.maximum_drawdown,
            "gross_profit": self.gross_profit,
            "gross_loss_abs": self.gross_loss_abs,
            "total_r_multiple": self.total_r_multiple,
            "stress_cost_total_return_0_004": (
                self.stress_cost_total_return_0_004
            ),
        }


@dataclass(frozen=True, slots=True)
class AmsV2TrialDecision:
    fold_metrics: tuple[
        AmsV2CompletedFoldMetrics,
        ...,
    ]
    baseline_walk_forward: dict[str, object]
    strict_gates: dict[str, bool]
    aggregate_stress_cost_total_return_0_004: float
    decision: str

    def to_dict(self) -> dict[str, object]:
        return {
            "fold_metrics": [
                value.to_dict()
                for value in self.fold_metrics
            ],
            "baseline_walk_forward": (
                self.baseline_walk_forward
            ),
            "strict_gates": dict(
                self.strict_gates
            ),
            (
                "aggregate_stress_cost_"
                "total_return_0_004"
            ): (
                self
                .aggregate_stress_cost_total_return_0_004
            ),
            "decision": self.decision,
        }


@dataclass(frozen=True, slots=True)
class AmsV2TrialExecution:
    configuration_id: str
    family_id: str
    parameter_hash_sha256: str
    source_commit: str
    started_at: datetime
    completed_at: datetime
    terminal_status: TrialTerminalStatus
    fold_metrics: tuple[
        AmsV2CompletedFoldMetrics,
        ...,
    ] = ()
    failure_reason: str | None = None
    invalidation_reason: str | None = None

    def __post_init__(self) -> None:
        if not all(
            value.strip()
            for value in (
                self.configuration_id,
                self.family_id,
                self.source_commit,
            )
        ):
            raise AmsV2OrchestratorDataError(
                "Execution identifiers cannot be empty."
            )

        parameter_hash = (
            self.parameter_hash_sha256.lower()
        )

        if (
            len(parameter_hash) != 64
            or any(
                value not in "0123456789abcdef"
                for value in parameter_hash
            )
        ):
            raise AmsV2OrchestratorDataError(
                "Invalid parameter SHA-256."
            )

        if (
            self.started_at.tzinfo is None
            or self.started_at.utcoffset() is None
            or self.completed_at.tzinfo is None
            or self.completed_at.utcoffset() is None
            or self.completed_at < self.started_at
        ):
            raise AmsV2OrchestratorDataError(
                "Invalid execution timestamps."
            )

        if (
            self.terminal_status
            == TrialTerminalStatus.COMPLETED
        ):
            if len(self.fold_metrics) != 3:
                raise AmsV2OrchestratorDataError(
                    "Completed trials require three folds."
                )

            if (
                self.failure_reason is not None
                or self.invalidation_reason is not None
            ):
                raise AmsV2OrchestratorDataError(
                    "Completed trial contains an error reason."
                )

        elif (
            self.terminal_status
            == TrialTerminalStatus.FAILED
        ):
            if not self.failure_reason:
                raise AmsV2OrchestratorDataError(
                    "Failed trial requires failure_reason."
                )

        elif (
            self.invalidation_reason
            not in ALLOWED_INVALIDATION_REASONS
        ):
            raise AmsV2OrchestratorDataError(
                "Invalid invalidation reason."
            )


def _validate_fold_alignment(
    metrics: Sequence[AmsV2CompletedFoldMetrics],
) -> None:
    definitions = (
        default_ams_v2_fold_definitions()
    )

    if len(metrics) != len(definitions):
        raise AmsV2OrchestratorDataError(
            "Exactly three fold results are required."
        )

    for metric, definition in zip(
        metrics,
        definitions,
        strict=True,
    ):
        if (
            metric.fold_name != definition.name
            or metric.evaluation_start
            != definition.evaluation_start
            or metric.evaluation_end_exclusive
            != definition.evaluation_end_exclusive
        ):
            raise AmsV2OrchestratorDataError(
                "Fold result does not match frozen boundaries."
            )


def _profit_factor_gate(
    metrics: Sequence[AmsV2CompletedFoldMetrics],
    profit_factor: float | None,
) -> bool:
    if profit_factor is not None:
        return profit_factor > 1.1

    total_profit = sum(
        value.gross_profit
        for value in metrics
    )

    total_loss = sum(
        value.gross_loss_abs
        for value in metrics
    )

    return (
        total_profit > 0.0
        and total_loss == 0.0
    )


def evaluate_ams_v2_completed_trial(
    fold_metrics: Sequence[
        AmsV2CompletedFoldMetrics
    ],
) -> AmsV2TrialDecision:
    metrics = tuple(
        fold_metrics
    )

    _validate_fold_alignment(
        metrics
    )

    fold_rules = replace(
        default_fold_pass_rules(),
        maximum_drawdown=0.45,
    )

    family_rules = replace(
        default_family_advancement_rules(),
        maximum_single_fold_drawdown=0.45,
    )

    baseline = evaluate_walk_forward_family(
        tuple(
            value.to_snapshot()
            for value in metrics
        ),
        fold_rules=fold_rules,
        family_rules=family_rules,
    )

    stress_growth = math.prod(
        (
            1.0
            + value
            .stress_cost_total_return_0_004
        )
        for value in metrics
    )

    aggregate_stress_return = (
        stress_growth - 1.0
    )

    strict_gates = {
        "baseline_proceeds_to_frozen_test": (
            baseline.decision
            == BASELINE_PROCEED_DECISION
        ),
        "aggregate_profit_factor_above_1_1": (
            _profit_factor_gate(
                metrics,
                baseline
                .aggregate_metrics
                .aggregate_profit_factor,
            )
        ),
        "aggregate_0_004_cost_return_positive": (
            aggregate_stress_return > 0.0
        ),
        "latest_fold_0_004_cost_return_positive": (
            metrics[-1]
            .stress_cost_total_return_0_004
            > 0.0
        ),
        "maximum_fold_drawdown_at_most_0_45": (
            max(
                value.maximum_drawdown
                for value in metrics
            )
            <= 0.45
        ),
        "minimum_total_executed_trades_30": (
            sum(
                value.executed_trade_count
                for value in metrics
            )
            >= 30
        ),
    }

    return AmsV2TrialDecision(
        fold_metrics=metrics,
        baseline_walk_forward=baseline.to_dict(),
        strict_gates=strict_gates,
        aggregate_stress_cost_total_return_0_004=(
            aggregate_stress_return
        ),
        decision=(
            "ADVANCE"
            if all(
                strict_gates.values()
            )
            else "REJECT"
        ),
    )


def _mapping(
    value: object,
    *,
    name: str,
) -> dict[str, Any]:
    if not isinstance(
        value,
        Mapping,
    ):
        raise AmsV2OrchestratorDataError(
            f"{name} must be a mapping."
        )

    return {
        str(key): item
        for key, item in value.items()
    }


def validate_ams_v2_experiment_ledger(
    ledger: Mapping[str, Any],
) -> None:
    if ledger.get("protocol_id") != PROTOCOL_ID:
        raise AmsV2OrchestratorDataError(
            "Unexpected protocol ID."
        )

    accounting = _mapping(
        ledger.get("trial_accounting"),
        name="trial_accounting",
    )

    if (
        accounting.get("test_2025_accessed")
        is not False
        or accounting.get("holdout_2026_accessed")
        is not False
    ):
        raise AmsV2OrchestratorDataError(
            "A locked period was accessed."
        )

    raw_configurations = ledger.get(
        "alpha_configurations"
    )

    if not isinstance(
        raw_configurations,
        list,
    ):
        raise AmsV2OrchestratorDataError(
            "alpha_configurations must be a list."
        )

    if len(raw_configurations) != 96:
        raise AmsV2OrchestratorDataError(
            "Exactly 96 Alpha configurations are required."
        )

    allowed_statuses = {
        status.value
        for status in TrialLedgerStatus
    }

    configuration_ids: set[str] = set()
    parameter_hashes: set[str] = set()
    consumed = 0

    for raw_configuration in raw_configurations:
        configuration = _mapping(
            raw_configuration,
            name="alpha_configuration",
        )

        configuration_id = str(
            configuration.get(
                "configuration_id",
                "",
            )
        )

        parameter_hash = str(
            configuration.get(
                "parameter_hash_sha256",
                "",
            )
        )

        parameters = _mapping(
            configuration.get("parameters"),
            name="parameters",
        )

        if (
            not configuration_id
            or not configuration.get("family_id")
        ):
            raise AmsV2OrchestratorDataError(
                "Configuration identifiers are missing."
            )

        if (
            canonical_sha256(parameters)
            != parameter_hash
        ):
            raise AmsV2OrchestratorDataError(
                f"Parameter hash mismatch: {configuration_id}."
            )

        status = str(
            configuration.get(
                "trial_status",
                "",
            )
        )

        if status not in allowed_statuses:
            raise AmsV2OrchestratorDataError(
                f"Unknown trial status: {status}."
            )

        if (
            status
            != (
                TrialLedgerStatus
                .REGISTERED_NOT_EXECUTED
                .value
            )
        ):
            consumed += 1

        configuration_ids.add(
            configuration_id
        )

        parameter_hashes.add(
            parameter_hash
        )

    if (
        len(configuration_ids) != 96
        or len(parameter_hashes) != 96
    ):
        raise AmsV2OrchestratorDataError(
            "Configuration registrations are not unique."
        )

    executed = int(
        accounting.get(
            "trials_executed",
            -1,
        )
    )

    remaining = int(
        accounting.get(
            "remaining_authorized_trials",
            -1,
        )
    )

    if (
        executed < 0
        or remaining != 100 - executed
        or consumed != executed
    ):
        raise AmsV2OrchestratorDataError(
            "Trial accounting is inconsistent."
        )


def build_pending_alpha_execution_plan(
    ledger: Mapping[str, Any],
) -> tuple[dict[str, Any], ...]:
    validate_ams_v2_experiment_ledger(
        ledger
    )

    raw_configurations = ledger[
        "alpha_configurations"
    ]

    if not isinstance(
        raw_configurations,
        list,
    ):
        raise AmsV2OrchestratorDataError(
            "Invalid configuration list."
        )

    pending = [
        copy.deepcopy(
            _mapping(
                value,
                name="alpha_configuration",
            )
        )
        for value in raw_configurations
        if _mapping(
            value,
            name="alpha_configuration",
        ).get("trial_status")
        == (
            TrialLedgerStatus
            .REGISTERED_NOT_EXECUTED
            .value
        )
    ]

    return tuple(
        sorted(
            pending,
            key=lambda value: str(
                value["configuration_id"]
            ),
        )
    )


def apply_trial_execution_to_ledger(
    ledger: Mapping[str, Any],
    execution: AmsV2TrialExecution,
) -> dict[str, Any]:
    validate_ams_v2_experiment_ledger(
        ledger
    )

    updated = copy.deepcopy(
        dict(
            ledger
        )
    )

    configurations = updated[
        "alpha_configurations"
    ]

    if not isinstance(
        configurations,
        list,
    ):
        raise AmsV2OrchestratorDataError(
            "Invalid mutable configuration list."
        )

    matches = [
        value
        for value in configurations
        if isinstance(value, dict)
        and value.get("configuration_id")
        == execution.configuration_id
    ]

    if len(matches) != 1:
        raise AmsV2TrialStateError(
            "Expected one registered configuration."
        )

    configuration = matches[0]

    if (
        configuration.get("trial_status")
        != (
            TrialLedgerStatus
            .REGISTERED_NOT_EXECUTED
            .value
        )
    ):
        raise AmsV2TrialStateError(
            "Configuration was already consumed."
        )

    if (
        configuration.get("family_id")
        != execution.family_id
        or configuration.get(
            "parameter_hash_sha256"
        )
        != execution.parameter_hash_sha256
    ):
        raise AmsV2TrialStateError(
            "Execution does not match registration."
        )

    if (
        execution.terminal_status
        == TrialTerminalStatus.COMPLETED
    ):
        result = evaluate_ams_v2_completed_trial(
            execution.fold_metrics
        )

        configuration["trial_status"] = (
            TrialLedgerStatus.COMPLETED_ADVANCE.value
            if result.decision == "ADVANCE"
            else (
                TrialLedgerStatus
                .COMPLETED_REJECTED
                .value
            )
        )

        configuration["fold_results"] = [
            value.to_dict()
            for value in execution.fold_metrics
        ]

        configuration["aggregate_result"] = (
            result.to_dict()
        )

        configuration["invalidation"] = None

    elif (
        execution.terminal_status
        == TrialTerminalStatus.FAILED
    ):
        configuration["trial_status"] = (
            TrialLedgerStatus.FAILED_CONSUMED.value
        )

        configuration["fold_results"] = []

        configuration["aggregate_result"] = {
            "decision": "FAILED",
            "failure_reason": (
                execution.failure_reason
            ),
        }

        configuration["invalidation"] = None

    else:
        configuration["trial_status"] = (
            TrialLedgerStatus
            .INVALIDATED_CONSUMED
            .value
        )

        configuration["fold_results"] = [
            value.to_dict()
            for value in execution.fold_metrics
        ]

        configuration["aggregate_result"] = {
            "decision": "INVALIDATED",
        }

        configuration["invalidation"] = {
            "reason": (
                execution.invalidation_reason
            ),
            "completed_at": (
                execution.completed_at.isoformat()
            ),
        }

    configuration["execution_metadata"] = {
        "orchestrator_version": (
            ORCHESTRATOR_VERSION
        ),
        "source_commit": execution.source_commit,
        "started_at": (
            execution.started_at.isoformat()
        ),
        "completed_at": (
            execution.completed_at.isoformat()
        ),
    }

    accounting = updated[
        "trial_accounting"
    ]

    if not isinstance(
        accounting,
        dict,
    ):
        raise AmsV2OrchestratorDataError(
            "Invalid mutable trial accounting."
        )

    accounting["trials_executed"] = (
        int(
            accounting["trials_executed"]
        )
        + 1
    )

    if (
        execution.terminal_status
        == TrialTerminalStatus.INVALIDATED
    ):
        accounting["trials_invalidated"] = (
            int(
                accounting[
                    "trials_invalidated"
                ]
            )
            + 1
        )

    accounting[
        "remaining_authorized_trials"
    ] = (
        int(
            accounting[
                "total_unique_variants_registered"
            ]
        )
        - int(
            accounting[
                "trials_executed"
            ]
        )
    )

    history = updated.setdefault(
        "trial_history",
        [],
    )

    if not isinstance(
        history,
        list,
    ):
        raise AmsV2OrchestratorDataError(
            "trial_history must be a list."
        )

    history.append(
        {
            "configuration_id": (
                execution.configuration_id
            ),
            "family_id": execution.family_id,
            "terminal_status": (
                execution.terminal_status.value
            ),
            "source_commit": execution.source_commit,
            "completed_at": (
                execution.completed_at.isoformat()
            ),
        }
    )

    updated["status"] = "IN_PROGRESS"

    validate_ams_v2_experiment_ledger(
        updated
    )

    return updated


def load_json_object(
    path: Path,
) -> dict[str, Any]:
    value = json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )

    if not isinstance(
        value,
        dict,
    ):
        raise AmsV2OrchestratorDataError(
            f"Expected JSON object: {path}."
        )

    return value


def write_json_atomically(
    path: Path,
    payload: Mapping[str, Any],
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    serialized = (
        json.dumps(
            payload,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n"
    )

    temporary_path: Path | None = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            delete=False,
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
        ) as handle:
            handle.write(serialized)
            handle.flush()
            os.fsync(handle.fileno())

            temporary_path = Path(
                handle.name
            )

        os.replace(
            temporary_path,
            path,
        )

    except Exception:
        if (
            temporary_path is not None
            and temporary_path.exists()
        ):
            temporary_path.unlink()

        raise