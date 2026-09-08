from __future__ import annotations

import math

import numpy as np
import pandas as pd

from spotbot.research.rd41_multivariate_hazard_economic_alignment import (
    FEATURES,
    FORWARD,
    REVERSE,
    adverse_percentile,
    auc_binary,
    direction_periods,
    score_rows,
    validate_constants,
)


def test_constants():
    validate_constants()
    assert FEATURES == ("ENTRY_MARGIN", "RECENT_12H_RETURN", "PATH_POSITION")


def test_direction_periods():
    assert direction_periods(FORWARD) == ("ROBUSTNESS_2022", "ROBUSTNESS_2023")
    assert direction_periods(REVERSE) == ("ROBUSTNESS_2023", "ROBUSTNESS_2022")


def test_adverse_percentile():
    assert np.allclose(
        adverse_percentile(np.array([1.0, 2.0, 3.0, 4.0]), np.array([1.0, 2.5, 5.0])),
        [1.0, 0.5, 0.0],
    )


def test_equal_weight():
    cal = pd.DataFrame({f: [1.0, 2.0, 3.0, 4.0] for f in FEATURES})
    ev = pd.DataFrame({f: [2.5] for f in FEATURES})
    scored = score_rows(cal, ev)
    assert math.isclose(float(scored.iloc[0]["adverse_score"]), 0.5)


def test_auc():
    assert math.isclose(auc_binary(pd.Series([1, 1, 0, 0]), pd.Series([0.9, 0.8, 0.2, 0.1])), 1.0)
