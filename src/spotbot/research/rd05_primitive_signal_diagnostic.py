"""Statistical helpers for RD05 S1; no portfolio construction functions exist here."""

from __future__ import annotations

import numpy as np


def benjamini_hochberg(p_values: dict[str, float]) -> dict[str, float]:
    ordered = sorted(p_values.items(), key=lambda item: item[1])
    count = len(ordered); adjusted: dict[str, float] = {}; previous = 1.0
    for index, (key, value) in reversed(list(enumerate(ordered, start=1))):
        previous = min(previous, value * count / index); adjusted[key] = previous
    return adjusted


def bootstrap_p_value(values: np.ndarray, seed: int, replications: int = 10_000) -> float:
    if len(values) < 2: return 1.0
    rng = np.random.default_rng(seed); picks = rng.integers(0, len(values), size=(replications, len(values)))
    means = values[picks].mean(axis=1)
    return float((1 + np.count_nonzero(means <= 0)) / (replications + 1))
