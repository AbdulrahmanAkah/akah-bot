# ruff: noqa: E501

"""Offline primitives for the RD18-P2T identity and liquidity audit.

P2T is diagnostic only.  The functions in this module deliberately do not
alter universe membership, acquire market data, calculate returns, or create
trading artifacts.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable, Mapping, Sequence
from statistics import median, pstdev

IDENTITY_CLASSES = (
    "TEMPORALLY_DISTINCT_ASSET",
    "TEMPORAL_ALIAS_OF_EXISTING_ASSET",
    "TOKEN_MIGRATION",
    "REBRAND_WITH_CONTINUOUS_IDENTITY",
    "CONTRACT_MIGRATION",
    "DUPLICATE_REPRESENTATION",
    "WRAPPED_OR_BRIDGED_REPRESENTATION",
    "SYMBOL_COLLISION",
    "LEVERAGED_OR_SYNTHETIC_PRODUCT",
    "UNRESOLVED",
)

LIQUIDITY_FLAGS = (
    "VOLUME_PATTERN_PLAUSIBLE",
    "SHORT_LIVED_VOLUME_SPIKE",
    "EXTREME_SINGLE_DAY_CONCENTRATION",
    "PRICE_RANGE_VOLUME_DIVERGENCE",
    "REPEATED_VOLUME_PATTERN",
    "SPARSE_INTRADAY_ACTIVITY",
    "UNRESOLVED_LIQUIDITY_INTEGRITY",
)

PRODUCT_RE = re.compile(r"(?:2L|2S|3L|3S|5L|5S|UP|DOWN|BULL|BEAR)$", re.IGNORECASE)
WRAPPED_SYMBOLS = frozenset({"WBTC", "WETH", "STETH", "RETH", "CBETH"})


class P2TError(RuntimeError):
    """Raised when the frozen P2T contract is violated."""


def parse_bool(value: object) -> bool:
    """Parse the repository's string boolean convention."""

    return str(value).strip().lower() in {"true", "1", "yes"}


def finite(value: object) -> float | None:
    """Return a finite float, or ``None`` for an unavailable value."""

    if value is None or value == "":
        return None
    try:
        parsed = float(str(value))
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def safe_ratio(numerator: float | None, denominator: float | None) -> float | None:
    """Divide only finite, non-negative diagnostic quantities."""

    if numerator is None or denominator is None or denominator == 0:
        return None
    result = numerator / denominator
    return result if math.isfinite(result) else None


def product_like(symbol: str) -> bool:
    """Recognize the frozen leveraged/synthetic suffix policy."""

    return bool(PRODUCT_RE.search(symbol.removesuffix("-USDT").strip()))


def classify_identity(
    *,
    pair: str,
    canonical_id: str,
    variant_d_canonical_ids: Iterable[str],
    historical_symbols: Mapping[str, str],
    identity_status: str,
    evidence_source: str,
) -> dict[str, str]:
    """Classify one current-seed-only asset without symbol-only merging.

    A distinct canonical identifier with no committed temporal mapping is
    intentionally classified as a distinct asset.  Product exclusions are
    retained as an identity diagnostic rather than removed from the input.
    """

    base = pair.removesuffix("-USDT").upper()
    d_ids = set(variant_d_canonical_ids)
    exact_match = canonical_id in d_ids
    matched = ""
    if exact_match:
        matched = canonical_id
    if product_like(base):
        classification = "LEVERAGED_OR_SYNTHETIC_PRODUCT"
        confidence = "HIGH"
        notes = "Suffix matches the frozen KuCoin leveraged/synthetic-product policy; retained for diagnosis only."
    elif base in WRAPPED_SYMBOLS:
        classification = "WRAPPED_OR_BRIDGED_REPRESENTATION"
        confidence = "MEDIUM"
        notes = "Symbol matches an existing wrapped-asset policy entry; no merge performed."
    elif exact_match:
        classification = "SYMBOL_COLLISION"
        confidence = "HIGH"
        notes = "Canonical ID is already present in Variant D; identity requires explicit temporal review."
    elif identity_status.strip().upper() != "RESOLVED":
        classification = "UNRESOLVED"
        confidence = "LOW"
        notes = "The committed P1R identity audit is not resolved."
    else:
        classification = "TEMPORALLY_DISTINCT_ASSET"
        confidence = "MEDIUM"
        notes = (
            "Unique canonical ID absent from Variant D; no committed migration, alias, rebrand, "
            "contract, duplicate, or collision mapping supports a merge."
        )
    return {
        "classification": classification,
        "matched_asset_if_any": matched,
        "confidence": confidence,
        "notes": notes,
        "evidence_source": evidence_source,
        "variant_d_match": str(exact_match).lower(),
        "historical_symbol": base,
    }


def trailing_metrics(values: Sequence[float]) -> dict[str, float | int | None]:
    """Calculate deterministic daily turnover diagnostics for one window."""

    clean = [float(value) for value in values if math.isfinite(float(value)) and float(value) >= 0]
    if not clean:
        return {
            "valid_day_count": 0,
            "zero_volume_days": 0,
            "max_day_share": None,
            "turnover_stability": None,
            "median_turnover": None,
            "mean_turnover": None,
            "max_turnover": None,
            "max_jump_ratio": None,
        }
    med = float(median(clean))
    mean = sum(clean) / len(clean)
    max_value = max(clean)
    stability = pstdev(clean) / mean if mean else None
    previous_median = float(median(clean[:-1])) if len(clean) > 1 else None
    jump_ratio = safe_ratio(max_value, previous_median)
    return {
        "valid_day_count": len(clean),
        "zero_volume_days": sum(value == 0 for value in clean),
        "max_day_share": safe_ratio(max_value, med),
        "turnover_stability": stability,
        "median_turnover": med,
        "mean_turnover": mean,
        "max_turnover": max_value,
        "max_jump_ratio": jump_ratio,
    }


def classify_liquidity(
    metrics: Mapping[str, object],
    *,
    post_entry_ratio: float | None = None,
    post_entry_valid_days: int | None = None,
    price_range_divergence: bool = False,
    repeated_volume_pattern: bool = False,
    intraday_available: bool = False,
) -> tuple[str, ...]:
    """Apply the preregistered diagnostic liquidity flags."""

    flags: list[str] = []
    raw_valid = metrics.get("valid_day_count")
    valid = int(float(str(raw_valid))) if raw_valid not in (None, "") else 0
    max_share = finite(metrics.get("max_day_share"))
    if max_share is not None and max_share > 10:
        flags.append("EXTREME_SINGLE_DAY_CONCENTRATION")
    if (
        post_entry_ratio is not None
        and post_entry_ratio >= 5
        and post_entry_valid_days is not None
        and post_entry_valid_days < 26
    ):
        flags.append("SHORT_LIVED_VOLUME_SPIKE")
    if price_range_divergence:
        flags.append("PRICE_RANGE_VOLUME_DIVERGENCE")
    if repeated_volume_pattern:
        flags.append("REPEATED_VOLUME_PATTERN")
    if valid < 26 or (intraday_available and valid < 26):
        flags.append("SPARSE_INTRADAY_ACTIVITY")
    if valid == 0:
        flags.append("UNRESOLVED_LIQUIDITY_INTEGRITY")
    if not flags:
        flags.append("VOLUME_PATTERN_PLAUSIBLE")
    return tuple(flags)


def consecutive_true(values: Sequence[bool]) -> int:
    """Return the longest contiguous true run."""

    best = current = 0
    for value in values:
        if value:
            current += 1
            best = max(best, current)
        else:
            current = 0
    return best


def set_counts(left: Iterable[str], right: Iterable[str]) -> dict[str, int | float]:
    """Return structural overlap counts without a universe mutation."""

    a, b = set(left), set(right)
    union = a | b
    intersection = a & b
    return {
        "left_count": len(a),
        "right_count": len(b),
        "intersection_count": len(intersection),
        "union_count": len(union),
        "symmetric_difference_count": len(a ^ b),
        "jaccard": len(intersection) / len(union) if union else 1.0,
    }


__all__ = [
    "IDENTITY_CLASSES",
    "LIQUIDITY_FLAGS",
    "P2TError",
    "classify_identity",
    "classify_liquidity",
    "consecutive_true",
    "finite",
    "parse_bool",
    "product_like",
    "safe_ratio",
    "set_counts",
    "trailing_metrics",
]
