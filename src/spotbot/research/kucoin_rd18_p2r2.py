"""Offline primitives for RD18-P2R2 corrected structural comparison.

The module is intentionally structural-only.  It contains deterministic set,
rank, persistence, concentration, cutoff and omission-risk helpers and has no
network, market acquisition, trading, return or candidate-generation logic.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from statistics import median

P2R2_STAGE = "RD18_P2R2_CORRECTED_RESTRICTED_UNIVERSE_STRUCTURAL_COMPARISON"
VARIANTS = ("A2", "B2", "C2", "D2")
COMPARISONS = ("A2_vs_C2", "B2_vs_C2", "D2_vs_C2")
TOP_NS = (4, 6, 8, 10, 30)
MEMBERSHIP_TYPES = ("TOP_4", "TOP_6", "TOP_8", "TOP_10", "TOP_6_TOP_8_HYSTERESIS")


class P2R2Error(RuntimeError):
    """Raised when a frozen P2R2 invariant is violated."""


def bool_cell(value: object) -> bool:
    """Parse a deterministic CSV boolean cell."""

    return str(value).strip().lower() in {"true", "1", "yes"}


def finite_float(value: object, default: float = 0.0) -> float:
    """Parse a finite numeric value, returning ``default`` for blank cells."""

    if value is None or value == "":
        return default
    try:
        parsed = float(str(value))
    except (TypeError, ValueError) as exc:
        raise P2R2Error(f"invalid numeric value: {value!r}") from exc
    if not math.isfinite(parsed):
        raise P2R2Error(f"non-finite numeric value: {value!r}")
    return parsed


def set_jaccard(left: Iterable[str], right: Iterable[str]) -> float:
    """Return Jaccard similarity with a deterministic empty-set convention."""

    a, b = set(left), set(right)
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b)


def symmetric_difference_size(left: Iterable[str], right: Iterable[str]) -> int:
    """Return the number of members present in only one set."""

    return len(set(left) ^ set(right))


def substitution_count(left: Iterable[str], right: Iterable[str]) -> float:
    """Return equal-size substitution count from symmetric difference."""

    a, b = set(left), set(right)
    difference = symmetric_difference_size(a, b)
    return difference / 2.0 if len(a) == len(b) else float(difference)


def rank_displacement(left: Mapping[str, int], right: Mapping[str, int]) -> float:
    """Return mean absolute displacement over common ranked assets."""

    common = sorted(set(left) & set(right))
    if not common:
        return 0.0
    return sum(abs(left[key] - right[key]) for key in common) / len(common)


def spearman_common(left: Mapping[str, int], right: Mapping[str, int]) -> float | None:
    """Return Spearman correlation over common assets without scipy."""

    common = sorted(set(left) & set(right))
    if len(common) < 2:
        return None
    x = [float(left[key]) for key in common]
    y = [float(right[key]) for key in common]
    x_bar = sum(x) / len(x)
    y_bar = sum(y) / len(y)
    numerator = sum((a - x_bar) * (b - y_bar) for a, b in zip(x, y, strict=True))
    x_var = sum((a - x_bar) ** 2 for a in x)
    y_var = sum((b - y_bar) ** 2 for b in y)
    if x_var == 0 or y_var == 0:
        return 1.0 if x == y else 0.0
    return numerator / math.sqrt(x_var * y_var)


def run_lengths(values: Sequence[bool]) -> tuple[int, ...]:
    """Return contiguous true-run lengths."""

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


def persistence_summary(
    decisions: Sequence[str], members_by_decision: Mapping[str, set[str]]
) -> list[dict[str, object]]:
    """Summarize membership duration, entries and exits per asset."""

    ordered = list(decisions)
    assets = sorted(
        set().union(*(members_by_decision.get(decision, set()) for decision in ordered))
    )
    rows: list[dict[str, object]] = []
    for asset in assets:
        flags = [asset in members_by_decision.get(decision, set()) for decision in ordered]
        runs = run_lengths(flags)
        entries = sum(
            flag and (index == 0 or not flags[index - 1]) for index, flag in enumerate(flags)
        )
        first = next((ordered[index] for index, flag in enumerate(flags) if flag), "")
        last = next((ordered[index] for index in range(len(flags) - 1, -1, -1) if flags[index]), "")
        rows.append(
            {
                "asset": asset,
                "membership_weeks": sum(flags),
                "entry_count": entries,
                "reentry_count": max(0, entries - 1),
                "first_entry": first,
                "final_exit": last,
                "mean_duration_weeks": sum(runs) / len(runs) if runs else 0.0,
                "median_duration_weeks": median(runs) if runs else 0.0,
                "maximum_duration_weeks": max(runs, default=0),
            }
        )
    return rows


def turnover_rows(
    decisions: Sequence[str], members_by_decision: Mapping[str, set[str]]
) -> list[dict[str, object]]:
    """Return one-week/four-week retention and turnover rows."""

    ordered = list(decisions)
    rows: list[dict[str, object]] = []
    for index, decision in enumerate(ordered):
        current = members_by_decision.get(decision, set())
        previous = members_by_decision.get(ordered[index - 1], set()) if index else set()
        four_back = members_by_decision.get(ordered[index - 4], set()) if index >= 4 else set()
        rows.append(
            {
                "decision_time": decision,
                "member_count": len(current),
                "one_week_turnover_count": len(current ^ previous),
                "four_week_turnover_count": len(current ^ four_back),
                "one_week_retention_rate": len(current & previous) / len(previous)
                if previous
                else 1.0,
                "four_week_retention_rate": len(current & four_back) / len(four_back)
                if four_back
                else 1.0,
                "changed": bool(current ^ previous),
            }
        )
    return rows


def concentration_metrics(rows: Sequence[Mapping[str, object]]) -> dict[str, object]:
    """Calculate concentration and rank-cutoff metrics for one ranking."""

    ordered = sorted(rows, key=lambda row: int(float(str(row.get("liquidity_rank", 0)))))
    values = [
        finite_float(row.get("trailing_28d_median_daily_quote_turnover_usdt")) for row in ordered
    ]
    total = sum(values)
    weights = [value / total for value in values] if total > 0 else []

    def share(n: int) -> float:
        return sum(values[:n]) / total if total > 0 else 0.0

    def ratio(a: int, b: int) -> float | None:
        if len(values) < b or values[b - 1] == 0:
            return None
        return values[a - 1] / values[b - 1]

    result: dict[str, object] = {
        "eligible_count": len(values),
        "top_1_share": share(1),
        "top_3_share": share(3),
        "top_6_share": share(6),
        "top_10_share": share(10),
        "hhi": sum(weight * weight for weight in weights),
        "effective_number_assets": (
            1 / sum(weight * weight for weight in weights)
            if weights and sum(weight * weight for weight in weights)
            else 0.0
        ),
        "rank_1_rank_6_ratio": ratio(1, 6),
        "rank_6_rank_7_ratio": ratio(6, 7),
        "rank_10_rank_11_ratio": ratio(10, 11),
        "rank_30_rank_31_ratio": ratio(30, 31),
        "top_6_median_liquidity": median(values[:6]) if values else 0.0,
        "top_6_min_liquidity": min(values[:6], default=0.0),
        "top_10_median_liquidity": median(values[:10]) if values else 0.0,
        "top_10_min_liquidity": min(values[:10], default=0.0),
    }
    for upper, lower in ((4, 5), (6, 7), (8, 9), (10, 11), (30, 31)):
        margin = (
            (values[upper - 1] - values[lower - 1]) / values[upper - 1]
            if len(values) >= lower and values[upper - 1] > 0
            else None
        )
        result[f"rank_{upper}_{lower}_margin"] = margin
        for threshold in (0.01, 0.02, 0.05, 0.10, 0.20):
            result[f"rank_{upper}_{lower}_below_{int(threshold * 100)}pct"] = (
                margin is not None and margin < threshold
            )
    return result


def classify_omission_risk(
    *,
    top6_exact: float,
    top10_exact: float,
    mean_top10_jaccard: float,
    current_seed_top6_share: float,
    max_year_seed_share: float,
    rank6_margin_above_10_share: float,
    unresolved_top10: bool,
    unresolved_liquidity_top10: bool,
    reproducible: bool,
) -> str:
    """Apply the frozen P2R omission-risk rules exactly."""

    if (
        top6_exact < 0.50
        or mean_top10_jaccard < 0.70
        or current_seed_top6_share > 0.40
        or unresolved_top10
        or unresolved_liquidity_top10
        or not reproducible
    ):
        return "SEVERE"
    low = (
        top6_exact >= 0.95
        and top10_exact >= 0.90
        and mean_top10_jaccard >= 0.95
        and current_seed_top6_share <= 0.05
        and max_year_seed_share <= 0.10
        and rank6_margin_above_10_share >= 0.90
    )
    if low:
        return "LOW"
    moderate = (
        top6_exact >= 0.80
        and mean_top10_jaccard >= 0.85
        and current_seed_top6_share <= 0.15
        and max_year_seed_share <= 0.25
    )
    if moderate:
        return "MODERATE"
    return "HIGH"


def decision_for_risk(risk: str, *, integrity_pass: bool) -> tuple[str, str, dict[str, bool]]:
    """Return the frozen P2R2 decision, next stage and authorizations."""

    if not integrity_pass:
        return (
            "RD18_P2R2_STRUCTURAL_RECONSTRUCTION_FAILED",
            "RD18_BLOCKED_PENDING_P1R2_OUTPUT_REPAIR",
            {
                "single_corrected_universe_structural_use": False,
                "dual_universe_required_pending_p2s2": False,
                "strategy_replay_authorized": False,
                "candidate_generation_authorized": False,
                "production_authorized": False,
            },
        )
    if risk == "LOW":
        return (
            "RD18_P2R2_SINGLE_CORRECTED_RESTRICTED_UNIVERSE_ACCEPTABLE",
            "RD18_P2U2_CONFIDENCE_AWARE_UNIVERSE_NECESSITY_REVIEW",
            {
                "single_corrected_universe_structural_use": True,
                "dual_universe_required": False,
                "strategy_replay_authorized": False,
                "candidate_generation_authorized": False,
                "production_authorized": False,
            },
        )
    if risk in {"MODERATE", "HIGH"}:
        return (
            "RD18_P2R2_CORRECTED_UNIVERSE_ROBUSTNESS_REDESIGN_REQUIRED",
            "RD18_P2S2_CORRECTED_UNIVERSE_RISK_REDESIGN",
            {
                "single_corrected_universe_structural_use": False,
                "dual_universe_required_pending_p2s2": True,
                "strategy_replay_authorized": False,
                "candidate_generation_authorized": False,
                "production_authorized": False,
            },
        )
    return (
        "RD18_P2R2_CORRECTED_STRUCTURAL_RISK_UNACCEPTABLE",
        "RD18_P2S2_CORRECTED_UNIVERSE_RISK_REDESIGN",
        {
            "single_corrected_universe_structural_use": False,
            "dual_universe_required_pending_p2s2": False,
            "strategy_replay_authorized": False,
            "candidate_generation_authorized": False,
            "production_authorized": False,
        },
    )


__all__ = [
    "COMPARISONS",
    "MEMBERSHIP_TYPES",
    "P2R2_STAGE",
    "P2R2Error",
    "TOP_NS",
    "VARIANTS",
    "bool_cell",
    "classify_omission_risk",
    "concentration_metrics",
    "decision_for_risk",
    "finite_float",
    "persistence_summary",
    "rank_displacement",
    "run_lengths",
    "set_jaccard",
    "spearman_common",
    "substitution_count",
    "symmetric_difference_size",
    "turnover_rows",
]
