"""Market-level aggregation primitives for RD08."""

from __future__ import annotations

import numpy as np
import pandas as pd


def average_pairwise_correlation(
    returns: pd.DataFrame,
    *,
    minimum_pairs: int = 10,
) -> float | None:
    correlation = returns.corr(min_periods=len(returns))
    values = correlation.to_numpy(dtype=float)
    upper = values[np.triu_indices_from(values, k=1)]
    finite = upper[np.isfinite(upper)]
    if len(finite) < minimum_pairs:
        return None
    return float(finite.mean())


def valid_market_label(
    values: pd.Series,
    *,
    member_count: int,
    minimum_members: int = 20,
    minimum_share: float = 0.70,
) -> float | None:
    finite = values.dropna().astype(float)
    if len(finite) < minimum_members:
        return None
    if len(finite) / member_count < minimum_share:
        return None
    return float(finite.mean())


def aggregate_return(values: pd.Series) -> float | None:
    finite = values.dropna().astype(float)
    if len(finite) < 20:
        return None
    return float(np.log1p(finite).mean())


def dispersion(values: pd.Series) -> float | None:
    finite = np.log1p(values.dropna().astype(float))
    if len(finite) < 20:
        return None
    return float(finite.std(ddof=1))
