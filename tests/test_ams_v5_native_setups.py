from __future__ import annotations

import pandas as pd
import pytest
from ams_v5_native_support import configuration, row

from spotbot.research.ams_v5_native_engine import (
    configuration_grid,
    make_candidate,
    stop_distance,
)


def test_three_native_families_and_hybrid_are_registered() -> None:
    families = {item.family for item in configuration_grid()}
    assert families == {
        "SHALLOW_PULLBACK_RECLAIM",
        "DEEP_PULLBACK_RECOVERY",
        "MOMENTUM_REACCELERATION",
        "HYBRID_ALL_THREE",
    }


def test_soft_fibonacci_changes_score_but_never_removes_candidate() -> None:
    raw = row(
        0,
        family="SHALLOW_PULLBACK_RECLAIM",
        score=60,
        overrides={"score_soft_fib": 55.0, "fib": -5.0},
    )
    no_fib = make_candidate(pd.Series(raw), configuration(), "FOLD")
    soft = make_candidate(
        pd.Series(raw),
        configuration(fibonacci_mode="SOFT_FIBONACCI_SCORE"),
        "FOLD",
    )
    assert no_fib is not None and soft is not None
    assert no_fib.score == 60
    assert soft.score == 55


@pytest.mark.parametrize(
    ("model", "minimum", "maximum"),
    [("STRUCTURE_BALANCED", 2.2, 3.4), ("STRUCTURE_WIDE", 2.6, 4.0)],
)
def test_stop_models_enforce_minimum_and_maximum(
    model: str,
    minimum: float,
    maximum: float,
) -> None:
    assert stop_distance(100, 2, 99, model) == pytest.approx(minimum * 2)
    assert stop_distance(100, 2, 100 - maximum * 2 - 0.01, model) is None
