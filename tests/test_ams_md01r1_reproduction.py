from __future__ import annotations

from spotbot.research.ams_md01r1_universe import reproduction_status


def test_exact_reproduction_tolerances() -> None:
    expected = {
        "trade_count": 100.0,
        "compounded_return": 0.25,
        "mean_maximum_drawdown": 0.10,
    }
    assert reproduction_status(expected=expected, observed=expected) == "EXACT_REPRODUCTION"


def test_failed_reproduction_is_not_softened() -> None:
    expected = {
        "trade_count": 100.0,
        "compounded_return": 0.25,
        "mean_maximum_drawdown": 0.10,
    }
    observed = {
        "trade_count": 80.0,
        "compounded_return": 0.10,
        "mean_maximum_drawdown": 0.20,
    }
    assert (
        reproduction_status(expected=expected, observed=observed)
        == "FAILED_REPRODUCTION"
    )
