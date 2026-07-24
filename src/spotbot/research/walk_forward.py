from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from math import isfinite
from typing import Any


class WalkForwardEvaluationError(
    RuntimeError
):
    pass


class WalkForwardConfigurationError(
    WalkForwardEvaluationError
):
    pass


class WalkForwardDataError(
    WalkForwardEvaluationError
):
    pass


def _require_finite(
    value: float,
    *,
    name: str,
) -> None:
    if not isfinite(value):
        raise WalkForwardDataError(
            f"{name} must be finite."
        )


@dataclass(frozen=True, slots=True)
class FoldMetricSnapshot:
    fold_name: str
    executed_trade_count: int
    base_price_gross_pnl: float
    net_pnl: float
    total_return: float
    maximum_drawdown: float
    gross_profit: float
    gross_loss_abs: float
    total_r_multiple: float

    def __post_init__(self) -> None:
        if not self.fold_name.strip():
            raise WalkForwardDataError(
                "fold_name cannot be empty."
            )

        if (
            isinstance(
                self.executed_trade_count,
                bool,
            )
            or self.executed_trade_count < 0
        ):
            raise WalkForwardDataError(
                "executed_trade_count must be "
                "a nonnegative integer."
            )

        numeric_values = {
            "base_price_gross_pnl": (
                self.base_price_gross_pnl
            ),
            "net_pnl": self.net_pnl,
            "total_return": self.total_return,
            "maximum_drawdown": (
                self.maximum_drawdown
            ),
            "gross_profit": (
                self.gross_profit
            ),
            "gross_loss_abs": (
                self.gross_loss_abs
            ),
            "total_r_multiple": (
                self.total_r_multiple
            ),
        }

        for name, value in (
            numeric_values.items()
        ):
            _require_finite(
                value,
                name=name,
            )

        if not (
            0.0
            <= self.maximum_drawdown
            <= 1.0
        ):
            raise WalkForwardDataError(
                "maximum_drawdown must be "
                "within [0, 1]."
            )

        if self.gross_profit < 0.0:
            raise WalkForwardDataError(
                "gross_profit cannot be negative."
            )

        if self.gross_loss_abs < 0.0:
            raise WalkForwardDataError(
                "gross_loss_abs cannot be negative."
            )

        if (
            self.executed_trade_count == 0
            and (
                self.gross_profit != 0.0
                or self.gross_loss_abs != 0.0
                or self.total_r_multiple != 0.0
                or self.base_price_gross_pnl
                != 0.0
                or self.net_pnl != 0.0
                or self.total_return != 0.0
            )
        ):
            raise WalkForwardDataError(
                "A zero-trade fold cannot contain "
                "trade performance."
            )

    @property
    def profit_factor(
        self,
    ) -> float | None:
        if self.gross_loss_abs == 0.0:
            return None

        return (
            self.gross_profit
            / self.gross_loss_abs
        )

    @property
    def average_r_multiple(
        self,
    ) -> float | None:
        if self.executed_trade_count == 0:
            return None

        return (
            self.total_r_multiple
            / self.executed_trade_count
        )

    @property
    def has_infinite_profit_factor(
        self,
    ) -> bool:
        return (
            self.gross_profit > 0.0
            and self.gross_loss_abs == 0.0
        )

    def to_dict(
        self,
    ) -> dict[str, object]:
        return {
            "fold_name": self.fold_name,
            "executed_trade_count": (
                self.executed_trade_count
            ),
            "base_price_gross_pnl": (
                self.base_price_gross_pnl
            ),
            "net_pnl": self.net_pnl,
            "total_return": self.total_return,
            "maximum_drawdown": (
                self.maximum_drawdown
            ),
            "gross_profit": (
                self.gross_profit
            ),
            "gross_loss_abs": (
                self.gross_loss_abs
            ),
            "profit_factor": (
                self.profit_factor
            ),
            "profit_factor_is_infinite": (
                self.has_infinite_profit_factor
            ),
            "total_r_multiple": (
                self.total_r_multiple
            ),
            "average_r_multiple": (
                self.average_r_multiple
            ),
        }


@dataclass(frozen=True, slots=True)
class FoldPassRules:
    minimum_executed_trades: int = 8
    maximum_drawdown: float = 0.15

    def __post_init__(self) -> None:
        if (
            isinstance(
                self.minimum_executed_trades,
                bool,
            )
            or self.minimum_executed_trades
            < 1
        ):
            raise WalkForwardConfigurationError(
                "minimum_executed_trades must "
                "be a positive integer."
            )

        _require_finite(
            self.maximum_drawdown,
            name="maximum_drawdown",
        )

        if not (
            0.0
            <= self.maximum_drawdown
            <= 1.0
        ):
            raise WalkForwardConfigurationError(
                "maximum_drawdown must be "
                "within [0, 1]."
            )

    def to_dict(
        self,
    ) -> dict[str, int | float | str]:
        return {
            "minimum_executed_trades": (
                self.minimum_executed_trades
            ),
            "base_price_gross_pnl": "> 0",
            "net_total_return": "> 0",
            "profit_factor": "> 1",
            "average_r_multiple": "> 0",
            "maximum_drawdown": (
                self.maximum_drawdown
            ),
        }


@dataclass(frozen=True, slots=True)
class FamilyAdvancementRules:
    minimum_total_executed_trades: int = 30
    minimum_passing_folds: int = 2
    latest_fold_name: str = "WF_2024"
    maximum_single_fold_drawdown: float = 0.15

    def __post_init__(self) -> None:
        integer_values = {
            "minimum_total_executed_trades": (
                self.minimum_total_executed_trades
            ),
            "minimum_passing_folds": (
                self.minimum_passing_folds
            ),
        }

        for name, value in (
            integer_values.items()
        ):
            if (
                isinstance(value, bool)
                or value < 1
            ):
                raise WalkForwardConfigurationError(
                    f"{name} must be a positive "
                    "integer."
                )

        if not self.latest_fold_name.strip():
            raise WalkForwardConfigurationError(
                "latest_fold_name cannot be empty."
            )

        _require_finite(
            self.maximum_single_fold_drawdown,
            name=(
                "maximum_single_fold_drawdown"
            ),
        )

        if not (
            0.0
            <= self.maximum_single_fold_drawdown
            <= 1.0
        ):
            raise WalkForwardConfigurationError(
                "maximum_single_fold_drawdown "
                "must be within [0, 1]."
            )

    def to_dict(
        self,
    ) -> dict[str, int | float | str | bool]:
        return {
            "minimum_total_executed_trades": (
                self.minimum_total_executed_trades
            ),
            "minimum_passing_folds": (
                self.minimum_passing_folds
            ),
            "latest_fold_name": (
                self.latest_fold_name
            ),
            "latest_fold_must_pass": True,
            "aggregate_base_price_gross_pnl": (
                "> 0"
            ),
            "aggregate_net_pnl": "> 0",
            "aggregate_profit_factor": "> 1",
            "aggregate_average_r_multiple": (
                "> 0"
            ),
            "maximum_single_fold_drawdown": (
                self.maximum_single_fold_drawdown
            ),
        }


@dataclass(frozen=True, slots=True)
class FoldEvaluation:
    metrics: FoldMetricSnapshot
    gates: dict[str, bool]
    passed: bool

    def to_dict(
        self,
    ) -> dict[str, object]:
        return {
            "metrics": self.metrics.to_dict(),
            "gates": dict(self.gates),
            "passed": self.passed,
        }


@dataclass(frozen=True, slots=True)
class AggregateEvaluationMetrics:
    total_executed_trades: int
    aggregate_base_price_gross_pnl: float
    aggregate_net_pnl: float
    aggregate_gross_profit: float
    aggregate_gross_loss_abs: float
    aggregate_total_r_multiple: float
    maximum_single_fold_drawdown: float

    @property
    def aggregate_profit_factor(
        self,
    ) -> float | None:
        if self.aggregate_gross_loss_abs == 0.0:
            return None

        return (
            self.aggregate_gross_profit
            / self.aggregate_gross_loss_abs
        )

    @property
    def aggregate_profit_factor_is_infinite(
        self,
    ) -> bool:
        return (
            self.aggregate_gross_profit > 0.0
            and self.aggregate_gross_loss_abs
            == 0.0
        )

    @property
    def aggregate_average_r_multiple(
        self,
    ) -> float | None:
        if self.total_executed_trades == 0:
            return None

        return (
            self.aggregate_total_r_multiple
            / self.total_executed_trades
        )

    def to_dict(
        self,
    ) -> dict[str, object]:
        return {
            "total_executed_trades": (
                self.total_executed_trades
            ),
            "aggregate_base_price_gross_pnl": (
                self.aggregate_base_price_gross_pnl
            ),
            "aggregate_net_pnl": (
                self.aggregate_net_pnl
            ),
            "aggregate_gross_profit": (
                self.aggregate_gross_profit
            ),
            "aggregate_gross_loss_abs": (
                self.aggregate_gross_loss_abs
            ),
            "aggregate_profit_factor": (
                self.aggregate_profit_factor
            ),
            "aggregate_profit_factor_is_infinite": (
                self
                .aggregate_profit_factor_is_infinite
            ),
            "aggregate_total_r_multiple": (
                self.aggregate_total_r_multiple
            ),
            "aggregate_average_r_multiple": (
                self.aggregate_average_r_multiple
            ),
            "maximum_single_fold_drawdown": (
                self.maximum_single_fold_drawdown
            ),
        }


@dataclass(frozen=True, slots=True)
class WalkForwardFamilyDecision:
    fold_evaluations: tuple[
        FoldEvaluation,
        ...,
    ]
    aggregate_metrics: (
        AggregateEvaluationMetrics
    )
    family_gates: dict[str, bool]
    passing_fold_count: int
    decision: str

    def to_dict(
        self,
    ) -> dict[str, object]:
        return {
            "fold_evaluations": {
                evaluation.metrics.fold_name: (
                    evaluation.to_dict()
                )
                for evaluation in (
                    self.fold_evaluations
                )
            },
            "aggregate_metrics": (
                self.aggregate_metrics.to_dict()
            ),
            "family_gates": dict(
                self.family_gates
            ),
            "passing_fold_count": (
                self.passing_fold_count
            ),
            "decision": self.decision,
        }


def default_fold_pass_rules(
) -> FoldPassRules:
    return FoldPassRules()


def default_family_advancement_rules(
) -> FamilyAdvancementRules:
    return FamilyAdvancementRules()


def _profit_factor_above_one(
    *,
    gross_profit: float,
    gross_loss_abs: float,
    profit_factor: float | None,
) -> bool:
    if (
        gross_profit > 0.0
        and gross_loss_abs == 0.0
    ):
        return True

    return (
        profit_factor is not None
        and profit_factor > 1.0
    )


def evaluate_fold(
    metrics: FoldMetricSnapshot,
    *,
    rules: FoldPassRules,
) -> FoldEvaluation:
    gates = {
        "minimum_executed_trades": (
            metrics.executed_trade_count
            >= rules.minimum_executed_trades
        ),
        "positive_base_price_gross_pnl": (
            metrics.base_price_gross_pnl
            > 0.0
        ),
        "positive_net_total_return": (
            metrics.total_return > 0.0
        ),
        "profit_factor_above_one": (
            _profit_factor_above_one(
                gross_profit=(
                    metrics.gross_profit
                ),
                gross_loss_abs=(
                    metrics.gross_loss_abs
                ),
                profit_factor=(
                    metrics.profit_factor
                ),
            )
        ),
        "positive_average_r_multiple": (
            metrics.average_r_multiple
            is not None
            and metrics.average_r_multiple
            > 0.0
        ),
        "maximum_drawdown_within_limit": (
            metrics.maximum_drawdown
            <= rules.maximum_drawdown
        ),
    }

    return FoldEvaluation(
        metrics=metrics,
        gates=gates,
        passed=all(gates.values()),
    )


def aggregate_fold_metrics(
    snapshots: Iterable[
        FoldMetricSnapshot
    ],
) -> AggregateEvaluationMetrics:
    values = tuple(snapshots)

    if not values:
        raise WalkForwardDataError(
            "At least one fold snapshot "
            "is required."
        )

    fold_names = [
        snapshot.fold_name
        for snapshot in values
    ]

    if len(fold_names) != len(
        set(fold_names)
    ):
        raise WalkForwardDataError(
            "Fold names must be unique."
        )

    return AggregateEvaluationMetrics(
        total_executed_trades=sum(
            snapshot.executed_trade_count
            for snapshot in values
        ),
        aggregate_base_price_gross_pnl=sum(
            snapshot.base_price_gross_pnl
            for snapshot in values
        ),
        aggregate_net_pnl=sum(
            snapshot.net_pnl
            for snapshot in values
        ),
        aggregate_gross_profit=sum(
            snapshot.gross_profit
            for snapshot in values
        ),
        aggregate_gross_loss_abs=sum(
            snapshot.gross_loss_abs
            for snapshot in values
        ),
        aggregate_total_r_multiple=sum(
            snapshot.total_r_multiple
            for snapshot in values
        ),
        maximum_single_fold_drawdown=max(
            snapshot.maximum_drawdown
            for snapshot in values
        ),
    )


def evaluate_walk_forward_family(
    snapshots: Iterable[
        FoldMetricSnapshot
    ],
    *,
    fold_rules: FoldPassRules,
    family_rules: FamilyAdvancementRules,
) -> WalkForwardFamilyDecision:
    values = tuple(snapshots)

    aggregate = aggregate_fold_metrics(
        values
    )

    fold_evaluations = tuple(
        evaluate_fold(
            snapshot,
            rules=fold_rules,
        )
        for snapshot in values
    )

    evaluations_by_name = {
        evaluation.metrics.fold_name: (
            evaluation
        )
        for evaluation in fold_evaluations
    }

    latest_evaluation = (
        evaluations_by_name.get(
            family_rules.latest_fold_name
        )
    )

    if latest_evaluation is None:
        raise WalkForwardDataError(
            "Required latest fold is missing: "
            f"{family_rules.latest_fold_name}."
        )

    passing_fold_count = sum(
        evaluation.passed
        for evaluation in fold_evaluations
    )

    aggregate_profit_factor = (
        aggregate.aggregate_profit_factor
    )

    aggregate_average_r = (
        aggregate.aggregate_average_r_multiple
    )

    family_gates = {
        "minimum_total_executed_trades": (
            aggregate.total_executed_trades
            >= (
                family_rules
                .minimum_total_executed_trades
            )
        ),
        "minimum_passing_folds": (
            passing_fold_count
            >= family_rules.minimum_passing_folds
        ),
        "latest_fold_passed": (
            latest_evaluation.passed
        ),
        "positive_aggregate_base_price_gross_pnl": (
            aggregate
            .aggregate_base_price_gross_pnl
            > 0.0
        ),
        "positive_aggregate_net_pnl": (
            aggregate.aggregate_net_pnl
            > 0.0
        ),
        "aggregate_profit_factor_above_one": (
            _profit_factor_above_one(
                gross_profit=(
                    aggregate
                    .aggregate_gross_profit
                ),
                gross_loss_abs=(
                    aggregate
                    .aggregate_gross_loss_abs
                ),
                profit_factor=(
                    aggregate_profit_factor
                ),
            )
        ),
        "positive_aggregate_average_r_multiple": (
            aggregate_average_r is not None
            and aggregate_average_r > 0.0
        ),
        "maximum_single_fold_drawdown_within_limit": (
            aggregate
            .maximum_single_fold_drawdown
            <= (
                family_rules
                .maximum_single_fold_drawdown
            )
        ),
    }

    decision = (
        "PROCEED_TO_FROZEN_TEST"
        if all(family_gates.values())
        else "DO_NOT_PROCEED"
    )

    return WalkForwardFamilyDecision(
        fold_evaluations=fold_evaluations,
        aggregate_metrics=aggregate,
        family_gates=family_gates,
        passing_fold_count=(
            passing_fold_count
        ),
        decision=decision,
    )


def snapshot_from_mapping(
    payload: dict[str, Any],
) -> FoldMetricSnapshot:
    required_fields = {
        "fold_name",
        "executed_trade_count",
        "base_price_gross_pnl",
        "net_pnl",
        "total_return",
        "maximum_drawdown",
        "gross_profit",
        "gross_loss_abs",
        "total_r_multiple",
    }

    missing = required_fields.difference(
        payload
    )

    if missing:
        raise WalkForwardDataError(
            "Fold metric mapping is missing "
            f"fields: {sorted(missing)}."
        )

    fold_name = payload["fold_name"]
    executed_trade_count = payload[
        "executed_trade_count"
    ]

    if not isinstance(fold_name, str):
        raise WalkForwardDataError(
            "fold_name must be a string."
        )

    if (
        isinstance(executed_trade_count, bool)
        or not isinstance(
            executed_trade_count,
            int,
        )
    ):
        raise WalkForwardDataError(
            "executed_trade_count must be "
            "an integer."
        )

    numeric_values: dict[
        str,
        float,
    ] = {}

    for field in (
        required_fields
        - {
            "fold_name",
            "executed_trade_count",
        }
    ):
        value = payload[field]

        if (
            isinstance(value, bool)
            or not isinstance(
                value,
                (int, float),
            )
        ):
            raise WalkForwardDataError(
                f"{field} must be numeric."
            )

        numeric_values[field] = float(
            value
        )

    return FoldMetricSnapshot(
        fold_name=fold_name,
        executed_trade_count=(
            executed_trade_count
        ),
        base_price_gross_pnl=(
            numeric_values[
                "base_price_gross_pnl"
            ]
        ),
        net_pnl=numeric_values["net_pnl"],
        total_return=(
            numeric_values["total_return"]
        ),
        maximum_drawdown=(
            numeric_values[
                "maximum_drawdown"
            ]
        ),
        gross_profit=(
            numeric_values["gross_profit"]
        ),
        gross_loss_abs=(
            numeric_values[
                "gross_loss_abs"
            ]
        ),
        total_r_multiple=(
            numeric_values[
                "total_r_multiple"
            ]
        ),
    )