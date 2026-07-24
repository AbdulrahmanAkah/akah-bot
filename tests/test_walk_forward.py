import math

import pytest

from spotbot.research.walk_forward import (
    FamilyAdvancementRules,
    FoldMetricSnapshot,
    WalkForwardDataError,
    aggregate_fold_metrics,
    default_family_advancement_rules,
    default_fold_pass_rules,
    evaluate_fold,
    evaluate_walk_forward_family,
    snapshot_from_mapping,
)


def passing_snapshot(
    fold_name: str,
    *,
    trades: int = 12,
    gross_profit: float = 30.0,
    gross_loss_abs: float = 15.0,
    net_pnl: float = 12.0,
    total_return: float = 0.012,
    total_r_multiple: float = 3.0,
    maximum_drawdown: float = 0.05,
) -> FoldMetricSnapshot:
    return FoldMetricSnapshot(
        fold_name=fold_name,
        executed_trade_count=trades,
        base_price_gross_pnl=20.0,
        net_pnl=net_pnl,
        total_return=total_return,
        maximum_drawdown=maximum_drawdown,
        gross_profit=gross_profit,
        gross_loss_abs=gross_loss_abs,
        total_r_multiple=(
            total_r_multiple
        ),
    )


def failing_snapshot(
    fold_name: str,
) -> FoldMetricSnapshot:
    return FoldMetricSnapshot(
        fold_name=fold_name,
        executed_trade_count=10,
        base_price_gross_pnl=-4.0,
        net_pnl=-8.0,
        total_return=-0.008,
        maximum_drawdown=0.04,
        gross_profit=8.0,
        gross_loss_abs=16.0,
        total_r_multiple=-2.0,
    )


def test_profitable_fold_passes_all_gates() -> None:
    evaluation = evaluate_fold(
        passing_snapshot("WF_2022"),
        rules=default_fold_pass_rules(),
    )

    assert evaluation.passed
    assert all(
        evaluation.gates.values()
    )


def test_unprofitable_fold_fails_edge_gates() -> None:
    evaluation = evaluate_fold(
        failing_snapshot("WF_2022"),
        rules=default_fold_pass_rules(),
    )

    assert not evaluation.passed
    assert not evaluation.gates[
        "positive_base_price_gross_pnl"
    ]
    assert not evaluation.gates[
        "positive_net_total_return"
    ]
    assert not evaluation.gates[
        "profit_factor_above_one"
    ]
    assert not evaluation.gates[
        "positive_average_r_multiple"
    ]


def test_aggregate_metrics_are_exact() -> None:
    aggregate = aggregate_fold_metrics(
        (
            passing_snapshot(
                "WF_2022",
                trades=10,
                gross_profit=30.0,
                gross_loss_abs=10.0,
                net_pnl=15.0,
                total_r_multiple=4.0,
            ),
            passing_snapshot(
                "WF_2023",
                trades=20,
                gross_profit=20.0,
                gross_loss_abs=10.0,
                net_pnl=5.0,
                total_r_multiple=2.0,
            ),
        )
    )

    assert (
        aggregate.total_executed_trades
        == 30
    )
    assert (
        aggregate.aggregate_net_pnl
        == pytest.approx(20.0)
    )
    assert (
        aggregate.aggregate_profit_factor
        == pytest.approx(2.5)
    )
    assert (
        aggregate
        .aggregate_average_r_multiple
        == pytest.approx(0.2)
    )


def test_family_advances_when_all_rules_pass() -> None:
    decision = evaluate_walk_forward_family(
        (
            passing_snapshot("WF_2022"),
            passing_snapshot("WF_2023"),
            passing_snapshot("WF_2024"),
        ),
        fold_rules=(
            default_fold_pass_rules()
        ),
        family_rules=(
            default_family_advancement_rules()
        ),
    )

    assert decision.passing_fold_count == 3
    assert (
        decision.decision
        == "PROCEED_TO_FROZEN_TEST"
    )
    assert all(
        decision.family_gates.values()
    )


def test_latest_fold_failure_blocks_advancement() -> None:
    decision = evaluate_walk_forward_family(
        (
            passing_snapshot("WF_2022"),
            passing_snapshot("WF_2023"),
            failing_snapshot("WF_2024"),
        ),
        fold_rules=(
            default_fold_pass_rules()
        ),
        family_rules=(
            default_family_advancement_rules()
        ),
    )

    assert decision.passing_fold_count == 2
    assert not decision.family_gates[
        "latest_fold_passed"
    ]
    assert (
        decision.decision
        == "DO_NOT_PROCEED"
    )


def test_insufficient_total_trades_blocks_family() -> None:
    rules = FamilyAdvancementRules(
        minimum_total_executed_trades=30,
        minimum_passing_folds=2,
        latest_fold_name="WF_2024",
    )

    decision = evaluate_walk_forward_family(
        (
            passing_snapshot(
                "WF_2023",
                trades=8,
            ),
            passing_snapshot(
                "WF_2024",
                trades=8,
            ),
        ),
        fold_rules=(
            default_fold_pass_rules()
        ),
        family_rules=rules,
    )

    assert not decision.family_gates[
        "minimum_total_executed_trades"
    ]
    assert (
        decision.decision
        == "DO_NOT_PROCEED"
    )


def test_duplicate_fold_names_are_rejected() -> None:
    with pytest.raises(
        WalkForwardDataError,
        match="unique",
    ):
        aggregate_fold_metrics(
            (
                passing_snapshot("WF_2022"),
                passing_snapshot("WF_2022"),
            )
        )


def test_mapping_and_nonfinite_validation() -> None:
    snapshot = snapshot_from_mapping(
        {
            "fold_name": "WF_2024",
            "executed_trade_count": 12,
            "base_price_gross_pnl": 20.0,
            "net_pnl": 10.0,
            "total_return": 0.01,
            "maximum_drawdown": 0.04,
            "gross_profit": 25.0,
            "gross_loss_abs": 10.0,
            "total_r_multiple": 2.4,
        }
    )

    assert snapshot.fold_name == "WF_2024"
    assert snapshot.profit_factor == (
        pytest.approx(2.5)
    )
    assert snapshot.average_r_multiple == (
        pytest.approx(0.2)
    )

    with pytest.raises(
        WalkForwardDataError,
        match="finite",
    ):
        passing_snapshot(
            "WF_BAD",
            net_pnl=math.inf,
        )