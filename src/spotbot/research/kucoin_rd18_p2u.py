"""Pure, offline primitives for the RD18-P2U confidence-aware design.

The module intentionally contains no exchange access, portfolio logic, return
calculation, signal generation, or candidate generation.  Its boundary rule
is usable by fixture tests and by a later run only after the P1R input panel is
repaired.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

P2U_STAGE = "RD18_P2U_CONFIDENCE_AWARE_LIQUIDITY_UNIVERSE_DESIGN"
CONFIDENCE_CLASSES = (
    "EVIDENCE_STRONG",
    "CURRENT_SEED_KLINE_CONFIRMED",
    "EXCLUDED_LEVERAGED_OR_SYNTHETIC",
)
ENTRY_BOUNDARY = (6, 7)
RETENTION_BOUNDARY = (8, 9)


class P2UError(RuntimeError):
    """Raised when a frozen P2U primitive receives invalid input."""


def _number(value: object) -> float:
    if isinstance(value, bool):
        raise P2UError("boolean is not a numeric liquidity value")
    try:
        result = float(str(value))
    except (TypeError, ValueError) as exc:
        raise P2UError(f"invalid numeric value: {value!r}") from exc
    if not math.isfinite(result):
        raise P2UError(f"non-finite numeric value: {value!r}")
    return result


def relative_gap(upper: object, lower: object) -> float | None:
    """Return ``(upper-lower)/upper`` for positive adjacent liquidity values."""

    high = _number(upper)
    low = _number(lower)
    if high <= 0 or low <= 0:
        return None
    return (high - low) / high


def _rank(row: Mapping[str, Any]) -> int:
    value = row.get("rank_num", row.get("liquidity_rank", 0))
    try:
        return int(float(value))
    except (TypeError, ValueError) as exc:
        raise P2UError(f"invalid ranking row: {row!r}") from exc


def _liquidity(row: Mapping[str, Any]) -> float:
    return _number(
        row.get("liquidity_num", row.get("trailing_28d_median_daily_quote_turnover_usdt", 0))
    )


def _confidence(row: Mapping[str, Any]) -> str:
    value = str(row.get("confidence_class", ""))
    if value not in CONFIDENCE_CLASSES:
        raise P2UError(f"unknown confidence class: {value!r}")
    return value


def confidence_swap_pair(
    rows: Sequence[Mapping[str, Any]], threshold: float = 0.10
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Apply the frozen one-adjacent-swap boundary rule.

    Rows must be the eligible C ranking in original rank order.  Only 6/7 and
    then 8/9 are inspected; a current-seed row can move down by one position
    in favour of an evidence-strong row when the relative liquidity gap is at
    most ``threshold``.  Excluded products are rejected rather than silently
    removed, so contamination cannot be hidden by this primitive.
    """

    if not 0 <= threshold <= 1:
        raise P2UError("threshold must be between zero and one")
    ordered = [dict(row) for row in rows]
    ordered.sort(key=_rank)
    if any(_confidence(row) == "EXCLUDED_LEVERAGED_OR_SYNTHETIC" for row in ordered):
        raise P2UError("excluded products cannot enter the confidence-aware ranking")
    audits: list[dict[str, Any]] = []
    for boundary_name, upper_rank, lower_rank in (
        ("ENTRY_6_7", *ENTRY_BOUNDARY),
        ("RETENTION_8_9", *RETENTION_BOUNDARY),
    ):
        upper_index = upper_rank - 1
        lower_index = lower_rank - 1
        if lower_index >= len(ordered):
            continue
        upper = ordered[upper_index]
        lower = ordered[lower_index]
        gap = relative_gap(_liquidity(upper), _liquidity(lower))
        eligible = (
            _confidence(upper) == "CURRENT_SEED_KLINE_CONFIRMED"
            and _confidence(lower) == "EVIDENCE_STRONG"
            and gap is not None
            and gap <= threshold
        )
        record: dict[str, Any] = {
            "boundary": boundary_name,
            "upper_original_rank": upper_rank,
            "lower_original_rank": lower_rank,
            "upper_pair": upper.get("pair", ""),
            "lower_pair": lower.get("pair", ""),
            "upper_confidence": _confidence(upper),
            "lower_confidence": _confidence(lower),
            "upper_liquidity": _liquidity(upper),
            "lower_liquidity": _liquidity(lower),
            "relative_gap": gap if gap is not None else "",
            "intervention_eligible": eligible,
            "intervention_applied": False,
            "reason": "adjacent_boundary_rule",
        }
        if eligible:
            ordered[upper_index], ordered[lower_index] = lower, upper
            record["intervention_applied"] = True
        audits.append(record)
    for index, row in enumerate(ordered, start=1):
        row["adjusted_rank"] = index
    return ordered, audits


def hysteresis_membership(
    ranked_rows: Sequence[Mapping[str, Any]],
    previous: Sequence[str] = (),
    capacity: int = 6,
    retention_rank: int = 8,
) -> list[str]:
    """Compute deterministic Top-6 entry and Top-8 retention membership."""

    eligible = [dict(row) for row in ranked_rows]
    eligible.sort(key=_rank)
    by_pair = {str(row.get("pair", "")): row for row in eligible}
    retained = [
        pair for pair in previous if pair in by_pair and _rank(by_pair[pair]) <= retention_rank
    ]
    for row in eligible:
        pair = str(row.get("pair", ""))
        if pair not in retained and _rank(row) <= capacity:
            retained.append(pair)
        if len(retained) >= capacity:
            break
    return sorted(retained[:capacity])


def set_metrics(left: Sequence[str], right: Sequence[str]) -> dict[str, float | int]:
    """Return deterministic set-distance diagnostics for two memberships."""

    a, b = set(left), set(right)
    union = a | b
    intersection = a & b
    return {
        "left_size": len(a),
        "right_size": len(b),
        "intersection_size": len(intersection),
        "union_size": len(union),
        "symmetric_difference_size": len(a ^ b),
        "jaccard": len(intersection) / len(union) if union else 1.0,
        "shared_slot_rate": len(intersection) / max(len(a), len(b), 1),
    }


def safe_rate(numerator: int | float, denominator: int | float) -> float:
    """Return zero for an empty denominator."""

    return float(numerator) / float(denominator) if denominator else 0.0


def max_true_run(values: Sequence[bool]) -> int:
    """Return the longest contiguous true run."""

    best = current = 0
    for value in values:
        current = current + 1 if value else 0
        best = max(best, current)
    return best
