"""Frozen calendar uncertainty implementation. No market reader or policy fit."""

from __future__ import annotations

import hashlib

import numpy as np
import pandas as pd

from .gate3_precommit import basic_lcb, stationary_indices


def evaluate_calendar_claims(
    yearly_arms: dict[int, pd.DataFrame], claims: dict[str, dict[str, float]]
):
    """Run only on already-certified daily log-return ledgers in a future mission.

    Frames must include *every UTC day* of each year, including zero cash returns.
    Claims map registered IDs to fixed linear combinations of arm columns. All
    arms share the same year-specific bootstrap indices. No family reduction.
    """
    from arch.bootstrap import optimal_block_length

    if set(yearly_arms) != {2022, 2023} or not claims:
        raise ValueError("FIXED_YEAR_OR_CLAIM_FAMILY_MISSING")
    series, lengths, counts = {}, {}, {}
    arm_names = None
    for year, frame in sorted(yearly_arms.items()):
        expected = pd.date_range(f"{year}-01-01", f"{year}-12-31", freq="D", tz="UTC")
        if not frame.index.equals(expected):
            raise ValueError("MISSING_CALENDAR_OR_CASH_DAYS")
        if arm_names is None:
            arm_names = list(frame.columns)
        if list(frame.columns) != arm_names or not np.isfinite(frame.to_numpy()).all():
            raise ValueError("ARM_ALIGNMENT_OR_FINITE_RETURN_FAILURE")
        estimate = optimal_block_length(frame)
        stationary = estimate["stationary"].to_numpy(dtype=float)
        # Exactly constant series add no stochastic dependence; nonconstant NaN
        # estimation is inconclusive, not an arbitrary fallback length.
        variance = frame.var().to_numpy()
        if any(not np.isfinite(b) and v > 0 for b, v in zip(stationary, variance, strict=True)):
            raise ValueError("EVIDENCE_INCONCLUSIVE_BLOCK_ESTIMATION")
        lengths[year] = max([1.0, *stationary[np.isfinite(stationary)].tolist()])
        counts[year] = len(frame)
        if lengths[year] >= len(frame):
            raise ValueError("EVIDENCE_INCONCLUSIVE_BLOCK_SUPPORT")
        series[year] = frame.to_numpy()
    matrix = []
    for coefficients in claims.values():
        if set(coefficients) - set(arm_names):
            raise ValueError("UNBOUND_CLAIM_ARM")
        matrix.append([coefficients.get(arm, 0.0) for arm in arm_names])
    weights = np.asarray(matrix).T
    total_days = sum(counts.values())
    observed = sum(series[y].sum(axis=0) for y in series) / total_days
    theta = observed @ weights
    seed = int.from_bytes(hashlib.sha256(b"AKAH_GATE3_UNCERTAINTY_V1").digest()[:8], "big")
    rng = np.random.default_rng(seed)
    replicates = np.empty((9999, len(claims)))
    for k in range(9999):
        sums = np.zeros(len(arm_names))
        for year in sorted(series):
            indices = stationary_indices(counts[year], lengths[year], rng)
            sums += series[year][indices].sum(axis=0)
        replicates[k] = (sums / total_days) @ weights
    return {
        "block_lengths": lengths,
        "year_day_weights": counts,
        "primary_family_size": len(claims),
        "replications": 9999,
        "claims": {
            name: {
                "theta": float(theta[j]),
                "lcb": basic_lcb(float(theta[j]), replicates[:, j], len(claims)),
                "status": "PROVEN"
                if basic_lcb(float(theta[j]), replicates[:, j], len(claims)) > 0
                else "NOT_PROVEN",
            }
            for j, name in enumerate(claims)
        },
    }
