from __future__ import annotations

import numpy as np
import pandas as pd

from spotbot.research.rd08_market_timing_diagnostic import (
    moving_block_spearman_p_value,
    temporal_effective_sample_size,
    temporal_quintiles,
)


def test_temporal_quintiles_are_ordered() -> None:
    scores = pd.Series(np.arange(20, dtype=float))
    times = pd.Series(pd.date_range("2024-01-01", periods=20, tz="UTC"))
    quintiles = temporal_quintiles(scores, times)
    assert quintiles[0] == 1
    assert quintiles[-1] == 5
    assert set(quintiles) == {1, 2, 3, 4, 5}


def test_bootstrap_and_ess_are_deterministic() -> None:
    scores = np.linspace(-1, 1, 100)
    labels = scores + 0.01
    first = moving_block_spearman_p_value(scores, labels, seed=7, block_length=7, replications=100)
    second = moving_block_spearman_p_value(scores, labels, seed=7, block_length=7, replications=100)
    assert first == second
    ess = temporal_effective_sample_size(scores)
    assert 0 < float(ess["effective_sample_size"]) <= 100
