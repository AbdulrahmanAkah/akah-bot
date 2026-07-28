"""Typed helpers for the RD07A post-hoc age/quality mechanism diagnostic."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

FloatArray = npt.NDArray[np.float64]


@dataclass(frozen=True)
class ResidualModel:
    coefficients: FloatArray

    def apply(self, age: FloatArray, controls: FloatArray) -> FloatArray:
        return age - controls @ self.coefficients


def fit_residual_model(age: FloatArray, controls: FloatArray) -> ResidualModel:
    if age.ndim != 1 or controls.ndim != 2 or controls.shape[0] != age.size:
        raise ValueError("residual model shape mismatch")
    finite = np.isfinite(age) & np.isfinite(controls).all(axis=1)
    if np.count_nonzero(finite) < controls.shape[1] + 2:
        raise ValueError("insufficient training observations")
    coefficients, _, _, _ = np.linalg.lstsq(controls[finite], age[finite], rcond=None)
    return ResidualModel(np.asarray(coefficients, dtype=float))


def mechanism_decision(
    mean_residual_ic: float,
    positive_fold_count: int,
    concentration: float,
) -> str:
    if concentration > 0.25:
        return "AGE_EFFECT_SYMBOL_CONCENTRATED"
    if mean_residual_ic >= 0.02 and positive_fold_count >= 2:
        return "AGE_RETAINS_INCREMENTAL_CONTENT_AFTER_CONTROLS"
    if np.isfinite(mean_residual_ic):
        return "AGE_EFFECT_ABSORBED_BY_QUALITY_CONTROLS"
    return "AGE_MECHANISM_INCONCLUSIVE"
