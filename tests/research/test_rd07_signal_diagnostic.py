from __future__ import annotations

import numpy as np

from spotbot.research.rd07_signal_diagnostic import (
    effective_sample_size,
    moving_block_p_value,
)


def test_moving_block_bootstrap_is_deterministic() -> None:
    values = np.linspace(-0.1, 0.2, 100)
    first = moving_block_p_value(values, seed=123, block_length=7, replications=100)
    second = moving_block_p_value(values, seed=123, block_length=7, replications=100)
    assert first == second


def test_effective_sample_size_is_bounded() -> None:
    values = np.sin(np.arange(100, dtype=float) / 10)
    result = effective_sample_size(values)
    assert 0 < float(result["effective_sample_size"]) <= 100
    assert 0 < float(result["ess_raw_ratio"]) <= 1
