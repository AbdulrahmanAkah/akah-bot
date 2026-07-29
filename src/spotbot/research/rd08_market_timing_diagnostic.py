"""Statistical primitives for RD08 temporal market-timing diagnostics."""

from __future__ import annotations

from math import ceil

import numpy as np
import numpy.typing as npt
import pandas as pd

FloatArray = npt.NDArray[np.float64]


def temporal_quintiles(scores: pd.Series, times: pd.Series) -> npt.NDArray[np.int64]:
    order = np.lexsort(
        (
            pd.to_datetime(times, utc=True).astype("int64").to_numpy(),
            scores.to_numpy(dtype=float),
        )
    )
    result = np.empty(len(scores), dtype=np.int64)
    for ordinal, index in enumerate(order):
        result[index] = min(5, int(ordinal * 5 / len(scores)) + 1)
    return result


def moving_block_spearman_p_value(
    scores: FloatArray,
    labels: FloatArray,
    *,
    seed: int,
    block_length: int,
    replications: int = 10_000,
) -> float:
    valid = np.isfinite(scores) & np.isfinite(labels)
    score_rank = pd.Series(scores[valid]).rank(method="average").to_numpy(dtype=float)
    label_rank = pd.Series(labels[valid]).rank(method="average").to_numpy(dtype=float)
    count = len(score_rank)
    if count < 3:
        return 1.0
    block_count = int(ceil(count / block_length))
    generator = np.random.default_rng(seed)
    starts = generator.integers(0, count, size=(replications, block_count))
    offsets = np.arange(block_length)
    indexes = (starts[:, :, None] + offsets[None, None, :]) % count
    indexes = indexes.reshape(replications, -1)[:, :count]
    score_samples = score_rank[indexes]
    label_samples = label_rank[indexes]
    score_samples -= score_samples.mean(axis=1, keepdims=True)
    label_samples -= label_samples.mean(axis=1, keepdims=True)
    numerator = np.sum(score_samples * label_samples, axis=1)
    denominator = np.sqrt(np.sum(score_samples**2, axis=1) * np.sum(label_samples**2, axis=1))
    correlations = np.divide(
        numerator,
        denominator,
        out=np.zeros_like(numerator),
        where=denominator > 0,
    )
    return float((1 + np.count_nonzero(correlations <= 0)) / (replications + 1))


def temporal_effective_sample_size(
    values: FloatArray, maximum_lag: int = 28
) -> dict[str, float | int]:
    finite = values[np.isfinite(values)]
    count = len(finite)
    positive_sum = 0.0
    maximum_used = 0
    lag_one = 0.0
    series = pd.Series(finite)
    for lag in range(1, min(maximum_lag, count - 1) + 1):
        correlation = float(series.autocorr(lag=lag))
        if lag == 1 and np.isfinite(correlation):
            lag_one = correlation
        if not np.isfinite(correlation) or correlation <= 0:
            break
        positive_sum += correlation
        maximum_used = lag
    ess = count / max(1.0, 1.0 + 2.0 * positive_sum) if count else 0.0
    return {
        "raw_decision_count": count,
        "effective_sample_size": ess,
        "ess_raw_ratio": ess / count if count else 0.0,
        "lag_1_autocorrelation": lag_one,
        "maximum_positive_lag_used": maximum_used,
    }
