import numpy as np

from spotbot.research.rd06_final_adjudication import (
    classify_quintile_shape,
    effective_sample_size,
)


def test_effective_sample_size_contract() -> None:
    result = effective_sample_size(np.asarray([1.0, 0.8, 0.6, 0.4, 0.2]))
    assert 0 < result.effective_sample_size <= result.raw_decision_count
    assert 0 < result.ratio <= 1


def test_quintile_shape_rules() -> None:
    assert classify_quintile_shape({1: -2, 2: -1, 3: 0, 4: 1, 5: 2}) == "MONOTONIC_BROAD_RANKING"
    assert classify_quintile_shape({1: 0, 2: 0, 3: 0, 4: 0, 5: 2}) == "TOP_TAIL_SELECTION"
