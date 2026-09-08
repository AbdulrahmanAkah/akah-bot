from __future__ import annotations

import math

import numpy as np
import pandas as pd

from spotbot.research.rd42_supportive_direct_utility_transport import (
    FEATURES,
    FORWARD,
    REVERSE,
    auc_binary,
    bool_series,
    direction_periods,
    empirical_positive_score,
    score_evaluation_rows,
    training_q25,
    validate_constants,
)


def test_constants() -> None:
    validate_constants()
    assert FEATURES == (
        "ENTRY_MARGIN",
        "RECENT_12H_RETURN",
        "PATH_POSITION",
    )


def test_bool_series_parses_false_as_false() -> None:
    result = bool_series(
        pd.Series(["True", "False", "1", "0"]),
        field="x",
    )
    assert result.tolist() == [True, False, True, False]


def test_direction_periods() -> None:
    assert direction_periods(FORWARD) == (
        "ROBUSTNESS_2022",
        "ROBUSTNESS_2023",
    )
    assert direction_periods(REVERSE) == (
        "ROBUSTNESS_2023",
        "ROBUSTNESS_2022",
    )


def test_training_only_empirical_positive_score() -> None:
    train = np.asarray([1.0, 2.0, 3.0, 4.0])
    test = np.asarray([1.0, 2.5, 5.0])
    result = empirical_positive_score(train, test)
    assert np.allclose(result, [0.25, 0.50, 1.00])


def test_training_q25_is_linear_and_frozen() -> None:
    train = np.asarray([0.0, 1.0, 2.0, 3.0])
    assert math.isclose(training_q25(train), 0.75)


def test_score_ledger_tail_uses_training_q25() -> None:
    calibration = pd.DataFrame({"feature_value": [0.0, 1.0, 2.0, 3.0]})
    evaluation = pd.DataFrame({"feature_value": [0.5, 1.0, 2.5]})
    scored = score_evaluation_rows(calibration, evaluation)
    assert scored["negative_utility_tail"].tolist() == [
        True,
        False,
        False,
    ]
    assert np.allclose(
        scored["positive_score"].to_numpy(),
        [0.25, 0.50, 0.75],
    )


def test_auc_direction() -> None:
    labels = pd.Series([1, 1, 0, 0])
    adverse = pd.Series([0.9, 0.8, 0.2, 0.1])
    assert math.isclose(auc_binary(labels, adverse), 1.0)
