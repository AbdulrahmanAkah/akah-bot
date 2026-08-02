"""Pure structural diagnostics for RD18-P2S.

The module is deliberately independent of pandas, HTTP clients, exchange
state, trading, returns, and candidate generation.  It contains the frozen
set-distance, duration, proximity, and dual-scenario gate primitives used by
the offline P2S runner and its tests.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from statistics import median

P2S_STAGE = "RD18_P2S_UNIVERSE_RISK_REDESIGN"
TOP_NS = (4, 6, 8, 10, 30)
METRICS = ("TOP_4", "TOP_6", "TOP_8", "TOP_10", "TOP_30", "HYSTERESIS")
PROXIMITY_CLASSES = ("NEAR_CUTOFF", "MODERATE_GAP", "LARGE_LIQUIDITY_GAP", "ABSENT_FROM_VARIANT")


class P2SError(RuntimeError):
    """Raised when a frozen P2S contract cannot be evaluated."""


def object_int(value: object) -> int:
    """Parse an integer stored in a heterogeneous diagnostic row."""

    if isinstance(value, bool):
        raise P2SError("Boolean cannot be an integer diagnostic value")
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        return int(float(value))
    raise P2SError(f"Expected integer diagnostic value, got {value!r}")


def finite_float(value: object, default: float = 0.0) -> float:
    """Parse a finite numeric value without allowing NaN or infinity."""

    if value is None or value == "":
        return default
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise P2SError(f"Expected numeric value, got {value!r}")
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise P2SError(f"Expected numeric value, got {value!r}") from exc
    return parsed if math.isfinite(parsed) else default


def set_jaccard(left: Iterable[str], right: Iterable[str]) -> float:
    """Return Jaccard similarity with a deterministic empty convention."""

    a, b = set(left), set(right)
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b)


def exact_match(left: Iterable[str], right: Iterable[str]) -> bool:
    """Return exact set equality, ignoring ordering."""

    return set(left) == set(right)


def symmetric_difference_size(left: Iterable[str], right: Iterable[str]) -> int:
    """Return the number of members present in only one set."""

    return len(set(left) ^ set(right))


def substitution_count(left: Iterable[str], right: Iterable[str]) -> float:
    """Return substitutions, using half the symmetric difference for equal sets."""

    a, b = set(left), set(right)
    if len(a) == len(b):
        return symmetric_difference_size(a, b) / 2.0
    return float(symmetric_difference_size(a, b))


def safe_rate(numerator: int | float, denominator: int | float) -> float:
    """Return a bounded rate, using zero for an empty denominator."""

    return float(numerator) / float(denominator) if denominator else 0.0


def classify_liquidity_gap(left: float | None, right: float | None) -> str:
    """Classify a substitution using the frozen 10/25 percent thresholds."""

    if left is None or right is None or left <= 0 or right <= 0:
        return "ABSENT_FROM_VARIANT"
    relative = abs(left - right) / max(left, right)
    if relative <= 0.10:
        return "NEAR_CUTOFF"
    if relative <= 0.25:
        return "MODERATE_GAP"
    return "LARGE_LIQUIDITY_GAP"


def disagreement_distribution(substitutions: Sequence[float]) -> dict[str, int | float]:
    """Summarize zero, one, two, and three-or-more substitutions."""

    values = [float(value) for value in substitutions]
    return {
        "total_weeks": len(values),
        "zero_substitution_weeks": sum(value == 0 for value in values),
        "one_substitution_weeks": sum(value == 1 for value in values),
        "two_substitution_weeks": sum(value == 2 for value in values),
        "three_or_more_substitution_weeks": sum(value >= 3 for value in values),
        "mean_substitutions": sum(values) / len(values) if values else 0.0,
        "median_substitutions": float(median(values)) if values else 0.0,
    }


def true_run_lengths(values: Sequence[bool]) -> tuple[int, ...]:
    """Return lengths of contiguous true runs."""

    lengths: list[int] = []
    current = 0
    for value in values:
        if value:
            current += 1
        elif current:
            lengths.append(current)
            current = 0
    if current:
        lengths.append(current)
    return tuple(lengths)


def disagreement_segments(
    decisions: Sequence[str],
    left_members: Mapping[str, set[str]],
    right_members: Mapping[str, set[str]],
) -> list[dict[str, object]]:
    """Build consecutive disagreement segments with stable signatures."""

    segments: list[dict[str, object]] = []
    active: dict[str, object] | None = None
    for index, decision in enumerate(decisions):
        left = set(left_members.get(decision, set()))
        right = set(right_members.get(decision, set()))
        left_only = tuple(sorted(left - right))
        right_only = tuple(sorted(right - left))
        signature = (left_only, right_only)
        if not left_only and not right_only:
            if active is not None:
                active["final_decision"] = decisions[index - 1]
                active["duration_weeks"] = object_int(active["duration_weeks"])
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
            active["duration_weeks"] = object_int(active["duration_weeks"]) + 1
    if active is not None:
        segments.append(active)
    for segment in segments:
        duration = object_int(segment["duration_weeks"])
        segment.pop("signature", None)
        segment["resolved_within_one_week"] = duration <= 1
        segment["resolved_within_four_weeks"] = duration <= 4
        segment["persistent_4_weeks"] = duration >= 4
        segment["persistent_8_weeks"] = duration >= 8
        segment["persistent_13_weeks"] = duration >= 13
        segment["persistent_26_weeks"] = duration >= 26
    return segments


def classify_dual_scenario(
    gates: Mapping[str, bool], *, consensus_complete: bool, integrity_pass: bool
) -> tuple[str, str, dict[str, bool]]:
    """Apply the frozen P2S decision tree without using returns."""

    all_gates = integrity_pass and all(gates.values())
    if all_gates:
        return (
            "RD18_P2S_DUAL_UNIVERSE_REPLAY_DESIGN_CONFIRMED",
            "RD18_P3R_PREREGISTERED_DUAL_UNIVERSE_REPLAY",
            {
                "full_inventory_claim": False,
                "single_universe_research_authorized": False,
                "dual_universe_replay_design_authorized": True,
                "strategy_candidate_generation_authorized": False,
                "production_authorized": False,
            },
        )
    if integrity_pass and consensus_complete:
        return (
            "RD18_P2S_CONSENSUS_UNIVERSE_REDESIGN_REQUIRED",
            "RD18_BLOCKED_PENDING_CONSENSUS_UNIVERSE_PROTOCOL",
            {
                "full_inventory_claim": False,
                "single_universe_research_authorized": False,
                "dual_universe_replay_design_authorized": False,
                "strategy_candidate_generation_authorized": False,
                "production_authorized": False,
            },
        )
    return (
        "RD18_P2S_UNIVERSE_UNCERTAINTY_REMAINS_UNACCEPTABLE",
        "RD18_BLOCKED_PENDING_ALTERNATE_EXECUTION_UNIVERSE_DESIGN",
        {
            "full_inventory_claim": False,
            "single_universe_research_authorized": False,
            "dual_universe_replay_design_authorized": False,
            "strategy_candidate_generation_authorized": False,
            "production_authorized": False,
        },
    )


__all__ = [
    "METRICS",
    "P2S_STAGE",
    "P2SError",
    "PROXIMITY_CLASSES",
    "TOP_NS",
    "classify_dual_scenario",
    "classify_liquidity_gap",
    "disagreement_distribution",
    "disagreement_segments",
    "exact_match",
    "finite_float",
    "object_int",
    "safe_rate",
    "set_jaccard",
    "substitution_count",
    "symmetric_difference_size",
    "true_run_lengths",
]
