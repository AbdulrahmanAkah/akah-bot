"""Statistical primitives for RD06 intraweek signal diagnostics."""

from __future__ import annotations

from math import ceil
from typing import Final

import numpy as np
import numpy.typing as npt

from spotbot.research.rd05_primitive_signal_diagnostic import (
    average_ranks,
    benjamini_hochberg,
    deterministic_quintiles,
    safe_spearman,
    top_count,
)

FloatArray = npt.NDArray[np.float64]
BLOCK_LENGTH: Final = 7


def moving_block_bootstrap_p_value(
    values: FloatArray,
    *,
    seed: int,
    replications: int = 10_000,
    block_length: int = BLOCK_LENGTH,
) -> float:
    finite = np.asarray(values, dtype=float)
    finite = finite[np.isfinite(finite)]
    if finite.size < 2:
        return 1.0
    blocks = int(ceil(finite.size / block_length))
    generator = np.random.default_rng(seed)
    starts = generator.integers(0, finite.size, size=(replications, blocks))
    offsets = np.arange(block_length)
    indexes = (starts[:, :, None] + offsets[None, None, :]) % finite.size
    means = finite[indexes.reshape(replications, -1)[:, : finite.size]].mean(axis=1)
    return float((1 + np.count_nonzero(means <= 0.0)) / (replications + 1))


__all__ = [
    "average_ranks",
    "benjamini_hochberg",
    "deterministic_quintiles",
    "moving_block_bootstrap_p_value",
    "safe_spearman",
    "top_count",
]
