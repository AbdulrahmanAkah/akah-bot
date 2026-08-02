"""Pure offline primitives for RD18-P2U2 confidence-aware universe design.

The module operates on the corrected C2 ranking only.  Confidence can alter
only the registered 6/7 and 8/9 adjacent boundaries; it never changes the
eligible inventory, applies a global weight, or constructs an intersection
with D2.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from statistics import median
from typing import Any

STAGE = "RD18_P2U2_CONFIDENCE_AWARE_UNIVERSE_DESIGN"
EVIDENCE_STRONG = "EVIDENCE_STRONG"
CURRENT_SEED = "CURRENT_SEED_KLINE_CONFIRMED"
EXCLUDED_PRODUCT = "EXCLUDED_LEVERAGED_OR_SYNTHETIC"
CONFIDENCE_CLASSES = (EVIDENCE_STRONG, CURRENT_SEED, EXCLUDED_PRODUCT)
BOUNDARIES = (("TOP6_ENTRY", 6, 7), ("TOP8_RETENTION", 8, 9))
THRESHOLDS = {"E05": 0.05, "E10": 0.10, "E15": 0.15}
TOP_NS = (4, 6, 8, 10, 30)


class P2U2Error(ValueError):
    """Raised when a frozen P2U2 primitive receives invalid input."""


def parse_bool(value: object) -> bool:
    """Parse the repository's deterministic CSV boolean convention."""

    return str(value).strip().lower() in {"true", "1", "yes"}


def _number(value: object) -> float:
    if isinstance(value, bool):
        raise P2U2Error("boolean is not numeric")
    try:
        result = float(str(value))
    except (TypeError, ValueError) as exc:
        raise P2U2Error(f"invalid numeric value: {value!r}") from exc
    if not math.isfinite(result):
        raise P2U2Error(f"non-finite numeric value: {value!r}")
    return result


def _optional_number(value: object) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    return _number(value)


def relative_gap(upper: object, lower: object) -> float | None:
    """Return ``(upper-lower)/upper`` for finite positive values."""

    high = _optional_number(upper)
    low = _optional_number(lower)
    if high is None or low is None or high <= 0.0 or low <= 0.0:
        return None
    return (high - low) / high


def _rank(row: Mapping[str, Any], field: str = "original_c_rank") -> int:
    value = row.get(field, row.get("liquidity_rank", row.get("rank", "")))
    try:
        result = int(float(str(value)))
    except (TypeError, ValueError) as exc:
        raise P2U2Error(f"invalid rank in row: {row!r}") from exc
    if result < 1:
        raise P2U2Error(f"rank must be positive: {result}")
    return result


def _liquidity(row: Mapping[str, Any]) -> float | None:
    return _optional_number(
        row.get(
            "liquidity",
            row.get("trailing_28d_median_daily_quote_turnover_usdt", row.get("liquidity_num")),
        )
    )


def _confidence(row: Mapping[str, Any]) -> str:
    value = str(row.get("confidence_class", ""))
    if value not in CONFIDENCE_CLASSES:
        raise P2U2Error(f"unknown confidence class: {value!r}")
    return value


def _pair(row: Mapping[str, Any]) -> str:
    pair = str(row.get("pair", ""))
    if not pair:
        raise P2U2Error("ranking row has no pair")
    return pair


def _canonical(row: Mapping[str, Any]) -> str:
    value = str(row.get("canonical_asset_id", ""))
    return value or _pair(row).removesuffix("-USDT")


def _reason_for_boundary(
    upper: Mapping[str, Any], lower: Mapping[str, Any], gap: float | None, threshold: float
) -> tuple[bool, str]:
    upper_class = _confidence(upper)
    lower_class = _confidence(lower)
    if upper_class == EXCLUDED_PRODUCT or lower_class == EXCLUDED_PRODUCT:
        raise P2U2Error("excluded products cannot enter E2 rankings")
    if upper_class == lower_class:
        return False, "SAME_CONFIDENCE_CLASS"
    if upper_class != CURRENT_SEED:
        return False, "UPPER_ALREADY_EVIDENCE_STRONG"
    if lower_class != EVIDENCE_STRONG:
        return False, "LOWER_NOT_EVIDENCE_STRONG"
    if gap is None:
        return False, "INVALID_LIQUIDITY"
    if gap > threshold + 1e-12:
        return False, "GAP_ABOVE_THRESHOLD"
    return True, "SWAP_APPLIED_CONFIDENCE_TIEBREAK"


def confidence_swap_pair(
    rows: Sequence[Mapping[str, Any]], threshold: float = THRESHOLDS["E10"]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Apply exactly the two frozen adjacent-boundary checks."""

    if not 0.0 <= threshold <= 1.0:
        raise P2U2Error("threshold must be between zero and one")
    ordered = [dict(row) for row in rows]
    ordered.sort(key=lambda row: _rank(row))
    if not ordered:
        return [], []
    expected = list(range(1, len(ordered) + 1))
    if [_rank(row) for row in ordered] != expected:
        raise P2U2Error("C2 ranks must be contiguous before E2 adjustment")
    if any(_confidence(row) == EXCLUDED_PRODUCT for row in ordered):
        raise P2U2Error("excluded products cannot enter E2 rankings")
    for _boundary, upper_rank, lower_rank in BOUNDARIES:
        upper_index = upper_rank - 1
        lower_index = lower_rank - 1
        if lower_index >= len(ordered):
            continue
        upper = ordered[upper_index]
        lower = ordered[lower_index]
        gap = relative_gap(_liquidity(upper), _liquidity(lower))
        applied, reason = _reason_for_boundary(upper, lower, gap, threshold)
        if applied:
            ordered[upper_index], ordered[lower_index] = lower, upper
    for adjusted_rank, row in enumerate(ordered, start=1):
        row["adjusted_rank"] = adjusted_rank
        movement = adjusted_rank - _rank(row)
        if abs(movement) > 1:
            raise P2U2Error("confidence intervention moved an asset more than one rank")
    return ordered, _boundary_records(rows, threshold, ordered)


def _boundary_records(
    original_rows: Sequence[Mapping[str, Any]],
    threshold: float,
    adjusted_rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Recreate boundary records with post-swap asset positions deterministically."""

    original = [dict(row) for row in original_rows]
    original.sort(key=lambda row: _rank(row))
    records: list[dict[str, Any]] = []
    for boundary, upper_rank, lower_rank in BOUNDARIES:
        if lower_rank > len(original):
            continue
        upper = original[upper_rank - 1]
        lower = original[lower_rank - 1]
        gap = relative_gap(_liquidity(upper), _liquidity(lower))
        applied, reason = _reason_for_boundary(upper, lower, gap, threshold)
        records.append(
            {
                "boundary": boundary,
                "upper_original_rank": upper_rank,
                "lower_original_rank": lower_rank,
                "upper_pair": _pair(upper),
                "lower_pair": _pair(lower),
                "upper_canonical_asset_id": _canonical(upper),
                "lower_canonical_asset_id": _canonical(lower),
                "upper_confidence": _confidence(upper),
                "lower_confidence": _confidence(lower),
                "upper_liquidity": _liquidity(upper),
                "lower_liquidity": _liquidity(lower),
                "relative_gap": gap,
                "threshold": threshold,
                "intervention_eligible": applied,
                "intervention_applied": applied,
                "reason_code": reason,
                "adjusted_upper_pair": _pair(adjusted_rows[upper_rank - 1]),
                "adjusted_lower_pair": _pair(adjusted_rows[lower_rank - 1]),
            }
        )
    return records


def hysteresis_membership(
    ranked_rows: Sequence[Mapping[str, Any]],
    previous: Iterable[str] = (),
    capacity: int = 6,
    retention_rank: int = 8,
) -> tuple[str, ...]:
    """Apply the unchanged Top-6 entry/Top-8 retention rule."""

    ordered = sorted(ranked_rows, key=lambda row: int(row["adjusted_rank"]))
    rank_by_id = {_canonical(row): int(row["adjusted_rank"]) for row in ordered}
    retained = {asset for asset in previous if rank_by_id.get(asset, 10**9) <= retention_rank}
    for row in ordered:
        if len(retained) >= capacity:
            break
        if int(row["adjusted_rank"]) <= capacity:
            retained.add(_canonical(row))
    return tuple(sorted(retained, key=lambda asset: (rank_by_id.get(asset, 10**9), asset)))


def top_members(ranked_rows: Sequence[Mapping[str, Any]], top_n: int) -> tuple[str, ...]:
    """Return canonical IDs in deterministic adjusted-rank order."""

    return tuple(
        _canonical(row)
        for row in sorted(ranked_rows, key=lambda row: int(row["adjusted_rank"]))
        if int(row["adjusted_rank"]) <= top_n
    )


def set_metrics(left: Iterable[str], right: Iterable[str]) -> dict[str, Any]:
    """Return exact, Jaccard and substitution metrics."""

    a, b = set(left), set(right)
    union = a | b
    intersection = a & b
    symmetric = len(a ^ b)
    substitutions = symmetric / 2.0 if len(a) == len(b) else float(symmetric)
    return {
        "left_size": len(a),
        "right_size": len(b),
        "intersection_size": len(intersection),
        "union_size": len(union),
        "exact_match": a == b,
        "jaccard": len(intersection) / len(union) if union else 1.0,
        "symmetric_difference_size": symmetric,
        "substitution_count": substitutions,
        "shared_slot_rate": len(intersection) / max(len(a), len(b), 1),
    }


def safe_rate(numerator: int | float, denominator: int | float) -> float:
    """Return a zero-safe ratio."""

    return float(numerator) / float(denominator) if denominator else 0.0


def duration_stats(values: Sequence[int]) -> dict[str, float | int]:
    """Return deterministic duration statistics."""

    if not values:
        return {"count": 0, "mean": 0.0, "median": 0.0, "maximum": 0}
    return {
        "count": len(values),
        "mean": sum(values) / len(values),
        "median": float(median(values)),
        "maximum": max(values),
    }


def true_runs(values: Sequence[bool]) -> tuple[int, ...]:
    """Return lengths of contiguous true runs."""

    runs: list[int] = []
    current = 0
    for value in values:
        if value:
            current += 1
        elif current:
            runs.append(current)
            current = 0
    if current:
        runs.append(current)
    return tuple(runs)


__all__ = [
    "BOUNDARIES",
    "CONFIDENCE_CLASSES",
    "CURRENT_SEED",
    "EVIDENCE_STRONG",
    "EXCLUDED_PRODUCT",
    "P2U2Error",
    "STAGE",
    "THRESHOLDS",
    "TOP_NS",
    "confidence_swap_pair",
    "duration_stats",
    "hysteresis_membership",
    "parse_bool",
    "relative_gap",
    "safe_rate",
    "set_metrics",
    "top_members",
    "true_runs",
]
