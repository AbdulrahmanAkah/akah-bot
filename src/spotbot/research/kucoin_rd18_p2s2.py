"""Pure offline primitives for RD18-P2S2 corrected risk redesign.

The module intentionally has no HTTP, exchange, strategy, return, signal, or
candidate-generation dependency.  It provides deterministic set-distance,
duration, liquidity-gap, threshold, boundary, and decision helpers.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from statistics import median
from typing import cast

P2S2_STAGE = "RD18_P2S2_CORRECTED_UNIVERSE_RISK_REDESIGN"
TOP_NS = (4, 6, 8, 10, 30)
METRICS = ("TOP_4", "TOP_6", "TOP_8", "TOP_10", "TOP_30", "HYSTERESIS")
GAP_CLASSES = ("NEAR_CUTOFF", "MODERATE_GAP", "LARGE_LIQUIDITY_GAP", "ABSENT_FROM_VARIANT")


class P2S2Error(RuntimeError):
    """Raised when a frozen P2S2 diagnostic cannot be evaluated."""


def safe_rate(numerator: int | float, denominator: int | float) -> float:
    """Return a zero-safe ratio."""

    return float(numerator) / float(denominator) if denominator else 0.0


def set_jaccard(left: Iterable[str], right: Iterable[str]) -> float:
    """Return deterministic Jaccard similarity."""

    a, b = set(left), set(right)
    if not a and not b:
        return 1.0
    return safe_rate(len(a & b), len(a | b))


def symmetric_difference_size(left: Iterable[str], right: Iterable[str]) -> int:
    """Return members present in only one set."""

    return len(set(left) ^ set(right))


def substitution_count(left: Iterable[str], right: Iterable[str]) -> float:
    """Return substitutions, halving symmetric difference for equal sizes."""

    a, b = set(left), set(right)
    difference = symmetric_difference_size(a, b)
    return difference / 2.0 if len(a) == len(b) else float(difference)


def exact_match(left: Iterable[str], right: Iterable[str]) -> bool:
    """Return set equality independent of row order."""

    return set(left) == set(right)


def classify_liquidity_gap(left: float | None, right: float | None) -> str:
    """Apply frozen 10% and 25% relative-liquidity classifications."""

    if left is None or right is None or left <= 0.0 or right <= 0.0:
        return "ABSENT_FROM_VARIANT"
    relative = abs(left - right) / max(left, right)
    if relative <= 0.10:
        return "NEAR_CUTOFF"
    if relative <= 0.25:
        return "MODERATE_GAP"
    return "LARGE_LIQUIDITY_GAP"


def relative_gap(left: float | None, right: float | None) -> float | None:
    """Return an absolute relative difference, or None for missing values."""

    if left is None or right is None or left <= 0.0 or right <= 0.0:
        return None
    return abs(left - right) / max(left, right)


def disagreement_distribution(substitutions: Sequence[float]) -> dict[str, int | float]:
    """Summarize zero, one, two, three, and more substitution weeks."""

    values = [float(value) for value in substitutions]
    return {
        "total_weeks": len(values),
        "zero_substitution_weeks": sum(value == 0.0 for value in values),
        "one_substitution_weeks": sum(value == 1.0 for value in values),
        "two_substitution_weeks": sum(value == 2.0 for value in values),
        "three_substitution_weeks": sum(value == 3.0 for value in values),
        "more_than_three_substitution_weeks": sum(value > 3.0 for value in values),
        "mean_substitutions": safe_rate(sum(values), len(values)),
        "median_substitutions": float(median(values)) if values else 0.0,
    }


def disagreement_segments(
    decisions: Sequence[str],
    left_members: Mapping[str, set[str]],
    right_members: Mapping[str, set[str]],
) -> list[dict[str, object]]:
    """Build consecutive disagreement segments with stable member signatures."""

    segments: list[dict[str, object]] = []
    active: dict[str, object] | None = None
    for index, decision in enumerate(decisions):
        left_set = set(left_members.get(decision, set()))
        right_set = set(right_members.get(decision, set()))
        left_only = tuple(sorted(left_set - right_set))
        right_only = tuple(sorted(right_set - left_set))
        signature = (left_only, right_only)
        if not left_only and not right_only:
            if active is not None:
                active["final_decision"] = decisions[index - 1]
                segments.append(active)
                active = None
            continue
        if active is None or active["signature"] != signature:
            if active is not None:
                active["final_decision"] = decisions[index - 1]
                segments.append(active)
            active = {
                "first_decision": decision,
                "final_decision": decision,
                "duration_weeks": 1,
                "left_only": ";".join(left_only),
                "right_only": ";".join(right_only),
                "signature": signature,
            }
        else:
            active["final_decision"] = decision
            active["duration_weeks"] = int(cast(int, active["duration_weeks"])) + 1
    if active is not None:
        segments.append(active)
    for segment in segments:
        duration = int(cast(int, segment["duration_weeks"]))
        segment.pop("signature", None)
        segment["resolved_within_one_week"] = duration <= 1
        segment["resolved_within_four_weeks"] = duration <= 4
        segment["persistent_4_weeks"] = duration >= 4
        segment["persistent_8_weeks"] = duration >= 8
        segment["persistent_13_weeks"] = duration >= 13
        segment["persistent_26_weeks"] = duration >= 26
    return segments


def true_run_lengths(values: Sequence[bool]) -> tuple[int, ...]:
    """Return lengths of contiguous true runs."""

    result: list[int] = []
    current = 0
    for value in values:
        if value:
            current += 1
        elif current:
            result.append(current)
            current = 0
    if current:
        result.append(current)
    return tuple(result)


def leave_one_out_rate(values: Sequence[bool]) -> dict[str, float | int]:
    """Summarize exact-match rate and its leave-one-week range."""

    total = len(values)
    count = sum(values)
    rates = [safe_rate(count - int(value), total - 1) for value in values] if total > 1 else []
    return {
        "count": count,
        "total": total,
        "rate": safe_rate(count, total),
        "leave_one_out_min": min(rates, default=0.0),
        "leave_one_out_max": max(rates, default=0.0),
    }


def classify_boundary_opportunity(gap: float | None) -> str:
    """Classify a boundary gap for the diagnostic 5/10/15% audit."""

    if gap is None or not math.isfinite(gap):
        return "UNAVAILABLE"
    if gap <= 0.05:
        return "UP_TO_5_PERCENT"
    if gap <= 0.10:
        return "ABOVE_5_THROUGH_10_PERCENT"
    if gap <= 0.15:
        return "ABOVE_10_THROUGH_15_PERCENT"
    return "ABOVE_15_PERCENT"


def dual_scenario_decision(
    gates: Mapping[str, bool], *, integrity_pass: bool
) -> tuple[str, str, dict[str, bool]]:
    """Apply the frozen P2S2 dual-scenario branch."""

    if integrity_pass and all(gates.values()):
        return (
            "RD18_P2S2_DUAL_UNIVERSE_REPLAY_DESIGN_CONFIRMED",
            "RD18_P3R_PREREGISTERED_DUAL_UNIVERSE_REPLAY_PROTOCOL",
            {
                "full_historical_inventory_claim": False,
                "single_universe_research_authorized": False,
                "dual_universe_protocol_design_authorized": True,
                "confidence_aware_design_required": False,
                "strategy_replay_authorized": False,
                "candidate_generation_authorized": False,
                "production_authorized": False,
            },
        )
    return (
        "RD18_P2S2_CORRECTED_UNIVERSE_UNCERTAINTY_REMAINS_UNACCEPTABLE",
        "RD18_BLOCKED_PENDING_ALTERNATE_UNIVERSE_POLICY",
        {
            "full_historical_inventory_claim": False,
            "single_universe_research_authorized": False,
            "dual_universe_protocol_design_authorized": False,
            "confidence_aware_design_required": False,
            "confidence_aware_design_authorized": False,
            "strategy_replay_authorized": False,
            "candidate_generation_authorized": False,
            "production_authorized": False,
        },
    )


def confidence_aware_decision(
    gates: Mapping[str, bool], *, integrity_pass: bool
) -> tuple[str, str, dict[str, bool]]:
    """Apply the frozen P2S2 Confidence-Aware necessity branch."""

    if integrity_pass and all(gates.values()):
        return (
            "RD18_P2S2_CONFIDENCE_AWARE_UNIVERSE_DESIGN_REQUIRED",
            "RD18_P2U2_CONFIDENCE_AWARE_UNIVERSE_DESIGN",
            {
                "full_historical_inventory_claim": False,
                "single_universe_research_authorized": False,
                "dual_universe_protocol_design_authorized": False,
                "confidence_aware_design_authorized": True,
                "strategy_replay_authorized": False,
                "candidate_generation_authorized": False,
                "production_authorized": False,
            },
        )
    return (
        "RD18_P2S2_CORRECTED_UNIVERSE_UNCERTAINTY_REMAINS_UNACCEPTABLE",
        "RD18_BLOCKED_PENDING_ALTERNATE_UNIVERSE_POLICY",
        {
            "full_historical_inventory_claim": False,
            "single_universe_research_authorized": False,
            "dual_universe_protocol_design_authorized": False,
            "confidence_aware_design_authorized": False,
            "strategy_replay_authorized": False,
            "candidate_generation_authorized": False,
            "production_authorized": False,
        },
    )


__all__ = [
    "GAP_CLASSES",
    "METRICS",
    "P2S2_STAGE",
    "P2S2Error",
    "TOP_NS",
    "classify_boundary_opportunity",
    "classify_liquidity_gap",
    "confidence_aware_decision",
    "disagreement_distribution",
    "disagreement_segments",
    "dual_scenario_decision",
    "exact_match",
    "leave_one_out_rate",
    "relative_gap",
    "safe_rate",
    "set_jaccard",
    "substitution_count",
    "symmetric_difference_size",
    "true_run_lengths",
]
