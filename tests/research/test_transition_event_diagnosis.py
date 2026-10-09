"""Synthetic checks for descriptive accounting, not trading rule tests."""

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/research"))
from transition_event_diagnosis import distribution, grouped, shapley_mean, stats  # noqa: E402


def fixture(values):
    return pd.DataFrame(
        {
            "net_pnl": values,
            "entry_notional": [100.0] * len(values),
            "holding_hours": [4.0] * len(values),
            "pair": ["A"] * len(values),
            "entry_time": [str(i) for i in range(len(values))],
            "exit_reason": ["X"] * len(values),
        }
    )


def test_distribution_and_contributions():
    s = stats(fixture([-10.0, -2.0, 0.0, 5.0, 20.0]))
    assert s["net_pnl"] == 13
    assert (s["wins"], s["losses"], s["zeros"]) == (2, 2, 1)
    assert s["winner_contribution"] + s["loser_contribution"] == s["net_pnl"]
    assert s["profit_factor"] == pytest.approx(25 / 12)
    assert s["pnl_distribution"]["p50"] == 0


def test_empty_denominators_explicit():
    s = stats(fixture([]))
    assert s["mean_pnl"] is None and s["win_rate"] is None
    assert s["profit_factor"] is None
    assert distribution([]) == {"count": 0}


def test_top_removal_and_no_mutation():
    f = fixture([-10.0, 5.0, 20.0])
    before = f.copy(deep=True)
    assert stats(f)["top_bottom"]["1"]["net_without_top"] == -5
    pd.testing.assert_frame_equal(f, before)


def test_shapley_reconciles_and_reverses():
    a, b = fixture([-10.0, -5.0, 8.0]), fixture([-4.0, 9.0, 12.0])
    x, y = shapley_mean(a, b), shapley_mean(b, a)
    assert sum(x.values()) == pytest.approx(b.net_pnl.mean() - a.net_pnl.mean())
    for field in x:
        assert x[field] == pytest.approx(-y[field])


def test_groups_reconcile():
    f = fixture([-10.0, 5.0, 20.0])
    f["pair"] = ["A", "B", "B"]
    result = grouped(f, "pair")
    assert sum(r["net_pnl"] for r in result) == 15
    assert sum(r["count"] for r in result) == 3


def test_shuffled_statistics_identical():
    f = fixture([-10.0, -2.0, 0.0, 5.0, 20.0])
    assert stats(f) == stats(f.sample(frac=1, random_state=7))
