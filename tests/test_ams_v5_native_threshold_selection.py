from __future__ import annotations

from ams_v5_native_support import configuration, panel, row

from spotbot.research.ams_v5_native_engine import (
    choose_threshold,
    profiles,
    select_native_fold_threshold,
)


def metric(value: float) -> dict[str, float]:
    return {
        "profit_factor": 1.2,
        "maximum_drawdown": 0.1,
        "expectancy": value,
        "calmar": value,
        "activity_alignment": value,
        "stress_resilience": value,
    }


def test_exact_objective_tie_chooses_55_and_unsafe_is_excluded() -> None:
    assert choose_threshold({50: metric(1), 55: metric(1)})["selected"] == 55
    unsafe = metric(2)
    unsafe["profit_factor"] = 1.09
    decision = choose_threshold({50: unsafe, 55: metric(1)})
    assert decision["selected"] == 55
    assert decision["excluded"][50] == "TRAIN_PROFIT_FACTOR_BELOW_1_10"


def test_selector_accepts_train_only_and_validation_mutation_cannot_change_it() -> None:
    train = panel(
        row(0, family="SHALLOW_PULLBACK_RECLAIM"),
        row(1),
        row(2),
    )
    validation = panel(row(10, family="SHALLOW_PULLBACK_RECLAIM", score=100))
    first = select_native_fold_threshold(
        train_panel=train,
        configuration=configuration(),
        portfolio_profile=profiles()[0],
    )
    validation.loc[:, "close"] = 1_000_000
    second = select_native_fold_threshold(
        train_panel=train,
        configuration=configuration(),
        portfolio_profile=profiles()[0],
    )
    assert first.selected_threshold == second.selected_threshold
    assert first.train_hash_sha256 == second.train_hash_sha256
    assert not first.validation_inspected
