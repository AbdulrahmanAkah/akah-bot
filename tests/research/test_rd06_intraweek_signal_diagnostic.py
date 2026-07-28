import numpy as np

from spotbot.research.rd06_intraweek_signal_diagnostic import (
    moving_block_bootstrap_p_value,
)


def test_moving_block_bootstrap_is_deterministic() -> None:
    values = np.asarray([0.01, 0.02, -0.01, 0.03] * 10, dtype=float)
    first = moving_block_bootstrap_p_value(values, seed=42, replications=500)
    second = moving_block_bootstrap_p_value(values, seed=42, replications=500)
    assert first == second
    assert 0 <= first <= 1


def test_missing_sample_cannot_be_significant() -> None:
    assert moving_block_bootstrap_p_value(np.asarray([], dtype=float), seed=1) == 1
