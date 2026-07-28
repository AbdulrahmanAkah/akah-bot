"""Post-hoc evidence helpers for final RD06 closure."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np
import numpy.typing as npt

FloatArray = npt.NDArray[np.float64]
FINAL_DECISION: Final = "RD06_RESEARCH_SEQUENCE_COMPLETE_NO_EDGE_CONFIRMED"
NEXT_STAGE: Final = "RD07_CROSS_VENUE_SPOT_DATA_PROTOCOL"


@dataclass(frozen=True)
class EffectiveSampleSize:
    raw_decision_count: int
    effective_sample_size: float
    ratio: float
    lag_1_autocorrelation: float | None
    maximum_positive_lag_used: int


def effective_sample_size(values: FloatArray, maximum_lag: int = 28) -> EffectiveSampleSize:
    finite = np.asarray(values, dtype=float)
    finite = finite[np.isfinite(finite)]
    count = finite.size
    if count < 2:
        return EffectiveSampleSize(count, float(count), 1.0, None, 0)
    centered = finite - float(np.mean(finite))
    denominator = float(np.dot(centered, centered))
    correlations: list[float] = []
    for lag in range(1, min(maximum_lag, count - 1) + 1):
        correlation = float(np.dot(centered[:-lag], centered[lag:]) / denominator)
        if not np.isfinite(correlation) or correlation <= 0:
            break
        correlations.append(correlation)
    divisor = max(1.0, 1.0 + 2.0 * sum(correlations))
    ess = count / divisor
    lag_one = float(np.dot(centered[:-1], centered[1:]) / denominator) if count > 1 else None
    return EffectiveSampleSize(count, ess, ess / count, lag_one, len(correlations))


def classify_quintile_shape(means: dict[int, float]) -> str:
    """Apply frozen descriptive rules; never a confirmation gate."""

    if set(means) != {1, 2, 3, 4, 5}:
        return "NO_ECONOMIC_SHAPE"
    ordered = [means[index] for index in range(1, 6)]
    spread = max(ordered) - min(ordered)
    if not np.isfinite(ordered).all() or spread <= 1e-12:
        return "NO_ECONOMIC_SHAPE"
    if ordered[4] == max(ordered) and ordered[4] > float(np.mean(ordered[:4])):
        if len(set(ordered[:4])) <= 2:
            return "TOP_TAIL_SELECTION"
    monotonic_up = all(
        left <= right for left, right in zip(ordered[:-1], ordered[1:], strict=True)
    )
    if monotonic_up:
        return "MONOTONIC_BROAD_RANKING"
    if ordered[4] == max(ordered) and ordered[4] > float(np.mean(ordered[:4])):
        return "TOP_TAIL_SELECTION"
    if ordered[0] == min(ordered) and ordered[0] < float(np.mean(ordered[1:])):
        return "BOTTOM_TAIL_AVOIDANCE"
    if max(ordered[1:4]) == max(ordered):
        return "MIDDLE_QUINTILE_EFFECT"
    return "NON_MONOTONIC"
