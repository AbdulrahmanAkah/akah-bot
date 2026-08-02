"""Offline primitives for the RD18-P1R2 restricted-panel repair.

The repair keeps the raw 376-pair provenance panel, but excludes only the
registered leveraged/synthetic products before any eligibility or ranking
aggregation.  No network, trading, return, or candidate-generation logic is
present here.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

REGISTERED_PRODUCTS = frozenset(
    {
        "AGIX2L-USDT",
        "AGIX2S-USDT",
        "APT2L-USDT",
        "APT2S-USDT",
        "BLUR2L-USDT",
        "BLUR2S-USDT",
        "CFX2L-USDT",
        "CFX2S-USDT",
        "GRT2L-USDT",
        "GRT2S-USDT",
        "OP2L-USDT",
        "OP2S-USDT",
    }
)
PRODUCT_CLASSIFICATION = "LEVERAGED_OR_SYNTHETIC_PRODUCT"
PRODUCT_EXCLUSION_REASON = "LEVERAGED_OR_SYNTHETIC_PRODUCT"
PRODUCT_SUFFIX_RE = re.compile(r"(?P<multiplier>2|3|5)(?P<direction>L|S)$", re.IGNORECASE)
# KuCoin's leveraged-token shape is an explicit multiplier followed by a
# long/short direction.  Do not treat arbitrary symbols ending in words such
# as ``UP`` or ``BULL`` as products: those suffixes are not sufficient evidence
# to exclude an otherwise legitimate Spot asset.
GENERAL_PRODUCT_RE = PRODUCT_SUFFIX_RE


class P1R2Error(RuntimeError):
    """Raised when a frozen P1R2 invariant is violated."""


def parse_bool(value: object) -> bool:
    """Parse the repository's deterministic CSV boolean convention."""

    return str(value).strip().lower() in {"true", "1", "yes"}


def finite_float(value: object) -> float:
    """Parse a finite number and reject NaN or infinity."""

    try:
        parsed = float(str(value))
    except (TypeError, ValueError) as exc:
        raise P1R2Error(f"invalid numeric value: {value!r}") from exc
    if not math.isfinite(parsed):
        raise P1R2Error(f"non-finite numeric value: {value!r}")
    return parsed


def product_base(pair: str) -> str:
    """Return a normalized base symbol for a KuCoin BASE-USDT pair."""

    if not pair.upper().endswith("-USDT"):
        raise P1R2Error(f"not a USDT pair: {pair}")
    return pair[:-5].upper()


def classify_product_pair(pair: str) -> dict[str, object]:
    """Classify one pair using the frozen explicit/general product policy.

    The registered set is immutable evidence.  The general suffix policy is
    used only as an audit for unexpected additional products; ordinary symbols
    without an explicit product suffix remain ordinary Spot pairs.
    """

    normalized = pair.upper()
    base = product_base(normalized)
    suffix = GENERAL_PRODUCT_RE.search(base)
    is_product = bool(suffix)
    match = PRODUCT_SUFFIX_RE.search(base)
    multiplier = int(match.group("multiplier")) if match else ""
    direction = (
        match.group("direction").upper()
        if match
        else ("UP" if base.endswith("UP") else "DOWN" if base.endswith("DOWN") else "")
    )
    registered = normalized in REGISTERED_PRODUCTS
    return {
        "pair": normalized,
        "canonical_product_id": base,
        "base_token": base,
        "leverage_direction": direction,
        "leverage_multiplier": multiplier,
        "is_product": is_product,
        "registered": registered,
        "classification": PRODUCT_CLASSIFICATION if is_product else "ORDINARY_SPOT",
        "exclusion_reason": PRODUCT_EXCLUSION_REASON if is_product else "",
        "classification_evidence": (
            "P2T_frozen_product_classification_and_frozen_general_suffix_policy"
            if is_product
            else "frozen_identity_and_product_policy_no_match"
        ),
    }


def product_pairs(pairs: Iterable[str]) -> tuple[str, ...]:
    """Return all pairs matching the general policy in stable order."""

    return tuple(sorted(pair for pair in pairs if bool(classify_product_pair(pair)["is_product"])))


def corrected_pairs(raw_pairs: Iterable[str]) -> tuple[str, ...]:
    """Filter product pairs before any corrected aggregation."""

    return tuple(sorted(set(raw_pairs).difference(product_pairs(raw_pairs))))


def set_jaccard(left: Iterable[str], right: Iterable[str]) -> float:
    """Return deterministic Jaccard similarity, including empty sets."""

    a, b = set(left), set(right)
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b)


def symmetric_difference_size(left: Iterable[str], right: Iterable[str]) -> int:
    """Return the number of members present in only one set."""

    return len(set(left) ^ set(right))


def contiguous_ranks(rows: Sequence[Mapping[str, Any]], field: str = "liquidity_rank") -> bool:
    """Check that ranking rows have exactly 1..N ranks."""

    ranks = sorted(int(float(str(row[field]))) for row in rows)
    return ranks == list(range(1, len(ranks) + 1))


def safe_rate(numerator: int | float, denominator: int | float) -> float:
    """Return zero for an empty denominator."""

    return float(numerator) / float(denominator) if denominator else 0.0


def turnover(previous: Iterable[str], current: Iterable[str]) -> dict[str, object]:
    """Return deterministic set turnover diagnostics."""

    old, new = set(previous), set(current)
    added, removed = sorted(new - old), sorted(old - new)
    return {
        "added_count": len(added),
        "removed_count": len(removed),
        "turnover_count": len(added) + len(removed),
        "added_members": ";".join(added),
        "removed_members": ";".join(removed),
    }


__all__ = [
    "GENERAL_PRODUCT_RE",
    "PRODUCT_CLASSIFICATION",
    "PRODUCT_EXCLUSION_REASON",
    "REGISTERED_PRODUCTS",
    "P1R2Error",
    "classify_product_pair",
    "contiguous_ranks",
    "corrected_pairs",
    "finite_float",
    "parse_bool",
    "product_pairs",
    "set_jaccard",
    "safe_rate",
    "symmetric_difference_size",
    "turnover",
]
