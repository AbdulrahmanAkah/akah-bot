"""Statistical helpers for the RD07 cross-venue diagnostic."""

from __future__ import annotations

from math import ceil

import numpy as np
import numpy.typing as npt
import pandas as pd

from spotbot.research.rd05_primitive_signal_diagnostic import (
    benjamini_hochberg,
    safe_spearman,
)

FloatArray = npt.NDArray[np.float64]


def moving_block_p_value(
    values: FloatArray,
    *,
    seed: int,
    block_length: int,
    replications: int = 10_000,
) -> float:
    finite = values[np.isfinite(values)]
    if finite.size < 2:
        return 1.0
    block_count = int(ceil(finite.size / block_length))
    generator = np.random.default_rng(seed)
    starts = generator.integers(0, finite.size, size=(replications, block_count))
    offsets = np.arange(block_length)
    indexes = (starts[:, :, None] + offsets[None, None, :]) % finite.size
    samples = finite[indexes.reshape(replications, -1)[:, : finite.size]]
    means = samples.mean(axis=1)
    return float((1 + np.count_nonzero(means <= 0.0)) / (replications + 1))


def effective_sample_size(values: FloatArray, maximum_lag: int = 28) -> dict[str, float | int]:
    finite = values[np.isfinite(values)]
    count = len(finite)
    if count < 2 or float(np.std(finite, ddof=1)) == 0.0:
        return {
            "raw_decision_count": count,
            "effective_sample_size": float(count),
            "ess_raw_ratio": 1.0 if count else 0.0,
            "lag_1_autocorrelation": 0.0,
            "maximum_positive_lag_used": 0,
        }
    positive_sum = 0.0
    lag_one = 0.0
    maximum_used = 0
    series = pd.Series(finite)
    for lag in range(1, min(maximum_lag, count - 1) + 1):
        correlation = float(series.autocorr(lag=lag))
        if lag == 1 and np.isfinite(correlation):
            lag_one = correlation
        if not np.isfinite(correlation) or correlation <= 0:
            break
        positive_sum += correlation
        maximum_used = lag
    ess = count / max(1.0, 1.0 + 2.0 * positive_sum)
    return {
        "raw_decision_count": count,
        "effective_sample_size": ess,
        "ess_raw_ratio": ess / count,
        "lag_1_autocorrelation": lag_one,
        "maximum_positive_lag_used": maximum_used,
    }


__all__ = [
    "benjamini_hochberg",
    "effective_sample_size",
    "moving_block_p_value",
    "safe_spearman",
]
