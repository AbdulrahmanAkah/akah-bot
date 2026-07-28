"""Warning-free statistics for the RD05 S1 primitive-signal diagnostic."""

from __future__ import annotations

from collections.abc import Sequence
from math import ceil
from typing import Final

import numpy as np
import numpy.typing as npt

MINIMUM_MATCHED_SYMBOLS: Final = 5
FloatArray = npt.NDArray[np.float64]


def average_ranks(values: Sequence[float] | FloatArray) -> FloatArray:
    """Return ascending average ranks for ties without scipy-dependent warnings."""

    array = np.asarray(values, dtype=float)
    order = np.argsort(array, kind="mergesort")
    ranks = np.empty(array.size, dtype=float)
    position = 0
    while position < array.size:
        end = position + 1
        while end < array.size and array[order[end]] == array[order[position]]:
            end += 1
        ranks[order[position:end]] = (position + 1 + end) / 2.0
        position = end
    return ranks


def safe_spearman(
    signal: Sequence[float] | FloatArray,
    label: Sequence[float] | FloatArray,
) -> tuple[float | None, str]:
    """Compute Spearman only for finite, non-constant arrays with at least five entries."""

    signal_array = np.asarray(signal, dtype=float)
    label_array = np.asarray(label, dtype=float)
    if signal_array.size < MINIMUM_MATCHED_SYMBOLS:
        return None, "INSUFFICIENT_MATCHED_SYMBOLS"
    if not np.isfinite(signal_array).all():
        return None, "NONFINITE_SIGNAL"
    if not np.isfinite(label_array).all():
        return None, "NONFINITE_LABEL"
    if np.unique(signal_array).size < 2:
        return None, "CONSTANT_SIGNAL"
    if np.unique(label_array).size < 2:
        return None, "CONSTANT_LABEL"
    ranked_signal = average_ranks(signal_array)
    ranked_label = average_ranks(label_array)
    signal_delta = ranked_signal - float(np.mean(ranked_signal))
    label_delta = ranked_label - float(np.mean(ranked_label))
    denominator = float(
        np.sqrt(np.dot(signal_delta, signal_delta) * np.dot(label_delta, label_delta))
    )
    if denominator <= 0.0 or not np.isfinite(denominator):
        return None, "UNDEFINED_CORRELATION"
    return float(np.dot(signal_delta, label_delta) / denominator), ""


def deterministic_quintiles(
    symbols: Sequence[str], signal: Sequence[float] | FloatArray
) -> tuple[list[npt.NDArray[np.intp]], npt.NDArray[np.int_]]:
    """Partition every observation exactly once; Q5 is the highest deterministic score bin."""

    order = np.lexsort((np.asarray(symbols, dtype=str), -np.asarray(signal, dtype=float)))
    positions = np.array_split(order, 5)
    quantile = np.empty(len(order), dtype=int)
    for index, group in enumerate(positions, start=1):
        quantile[group] = 6 - index
    return positions, quantile


def top_count(observation_count: int) -> int:
    """Return the registered non-empty top-quintile size."""

    return max(1, int(ceil(observation_count / 5.0)))


def benjamini_hochberg(p_values: dict[str, float]) -> dict[str, float]:
    """Adjust the full declared family of p-values using Benjamini-Hochberg."""

    ordered = sorted(p_values.items(), key=lambda item: (item[1], item[0]))
    count = len(ordered)
    adjusted: dict[str, float] = {}
    previous = 1.0
    for rank, (signal_id, value) in reversed(list(enumerate(ordered, start=1))):
        clipped = min(1.0, max(0.0, float(value)))
        previous = min(previous, clipped * count / rank)
        adjusted[signal_id] = previous
    return adjusted


def bootstrap_p_value(
    values: Sequence[float] | FloatArray,
    seed: int,
    replications: int = 10_000,
) -> float:
    """One-sided clustered bootstrap p-value for mean IC greater than zero."""

    finite = np.asarray(values, dtype=float)
    finite = finite[np.isfinite(finite)]
    if finite.size < 2:
        return 1.0
    generator = np.random.default_rng(seed)
    choices = generator.integers(0, finite.size, size=(replications, finite.size))
    means = np.mean(finite[choices], axis=1)
    return float((1 + np.count_nonzero(means <= 0.0)) / (replications + 1))


def gate_pass(value: float | None, threshold: float, comparator: str = ">=") -> bool:
    """A missing/non-finite observed value never passes a scientific gate."""

    if value is None or not np.isfinite(value):
        return False
    return value >= threshold if comparator == ">=" else value > threshold
