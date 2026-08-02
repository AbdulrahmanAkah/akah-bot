# ruff: noqa: E501

"""Offline structural comparison primitives for RD18-P2R.

This module deliberately contains no HTTP client, exchange access, trading,
return, or candidate-generation logic.  It consumes the immutable P1R tables
and exposes deterministic structural statistics used by the P2R runner and
offline tests.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from statistics import median

P2R_STAGE = "RD18_P2R_RESTRICTED_UNIVERSE_STRUCTURAL_COMPARISON"
VARIANTS = ("A_P0", "B_P0A", "C_P0B", "D_EVIDENCE_STRONG")
TOP_NS = (4, 6, 8, 10, 30)


class P2RError(RuntimeError):
    """Raised when the frozen structural-comparison contract is violated."""


def as_float(value: object, default: float = 0.0) -> float:
    """Parse a finite numeric value, using ``default`` for empty cells."""

    if value is None or value == "":
        return default
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise P2RError(f"Expected numeric value, got {value!r}")
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise P2RError(f"Expected numeric value, got {value!r}") from exc
    return parsed if math.isfinite(parsed) else default


def as_int(value: object, default: int = 0) -> int:
    """Parse an integer-like rank value."""

    if value is None or value == "":
        return default
    if isinstance(value, bool):
        raise P2RError("Boolean cannot be a rank")
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        return int(float(value))
    raise P2RError(f"Expected integer value, got {value!r}")


def bool_cell(value: object) -> bool:
    """Parse CSV boolean cells without truthiness surprises."""

    return str(value).strip().lower() in {"true", "1", "yes"}


def split_channels(value: object) -> tuple[str, ...]:
    """Return normalized discovery channels in deterministic order."""

    return tuple(sorted({part.strip() for part in str(value or "").split(";") if part.strip()}))


def classify_provenance(channels: Iterable[str]) -> str:
    """Classify discovery lineage while preserving the source channels separately."""

    values = set(channels)
    if not values:
        return "EVIDENCE_STRONG"
    if values == {"current_currency_non_causal_seed"}:
        return "CURRENT_SEED_ONLY_KLINE_CONFIRMED"
    if any("delist" in value for value in values):
        return "DELISTING_EVIDENCE_CONFIRMED"
    if "rd18_p0_historical_evidence" in values and len(values) == 1:
        return "REPOSITORY_SEEDED_CONFIRMED"
    if len(values) > 1:
        return "MULTI_CHANNEL_CONFIRMED"
    if "rd18_p0_historical_evidence" in values:
        return "REPOSITORY_SEEDED_CONFIRMED"
    return "EVIDENCE_STRONG"


def set_jaccard(left: Iterable[str], right: Iterable[str]) -> float:
    """Calculate Jaccard similarity, including the empty-set convention."""

    a, b = set(left), set(right)
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b)


def exact_match(left: Iterable[str], right: Iterable[str]) -> bool:
    """Return exact set equality."""

    return set(left) == set(right)


def rank_displacement(
    left: Mapping[str, int], right: Mapping[str, int], *, common_only: bool = True
) -> float:
    """Mean absolute rank displacement on common ranked assets."""

    common = sorted(set(left) & set(right)) if common_only else sorted(set(left) | set(right))
    if not common:
        return 0.0
    return sum(abs(left.get(key, 0) - right.get(key, 0)) for key in common) / len(common)


def spearman_common(left: Mapping[str, int], right: Mapping[str, int]) -> float | None:
    """Compute Spearman rho on common assets without a scipy dependency."""

    common = sorted(set(left) & set(right))
    if len(common) < 2:
        return None
    x = [float(left[key]) for key in common]
    y = [float(right[key]) for key in common]
    x_bar, y_bar = sum(x) / len(x), sum(y) / len(y)
    numerator = sum((a - x_bar) * (b - y_bar) for a, b in zip(x, y, strict=True))
    x_var = sum((a - x_bar) ** 2 for a in x)
    y_var = sum((b - y_bar) ** 2 for b in y)
    if x_var == 0 or y_var == 0:
        return 1.0 if x == y else 0.0
    return numerator / math.sqrt(x_var * y_var)


def run_lengths(values: Sequence[bool]) -> tuple[int, ...]:
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


def membership_summary(
    decisions: Sequence[str], members_by_decision: Mapping[str, set[str]]
) -> list[dict[str, object]]:
    """Summarize persistence, turnover, duration, and re-entry."""

    ordered = list(decisions)
    rows: list[dict[str, object]] = []
    assets = sorted(set().union(*(members_by_decision.get(key, set()) for key in ordered)))
    for asset in assets:
        flags = [asset in members_by_decision.get(key, set()) for key in ordered]
        runs = run_lengths(flags)
        entries = sum(
            flags[index] and (index == 0 or not flags[index - 1]) for index in range(len(flags))
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
                "median_duration_weeks": median(runs) if runs else 0.0,
                "mean_duration_weeks": sum(runs) / len(runs) if runs else 0.0,
                "maximum_duration_weeks": max(runs, default=0),
            }
        )
    return rows


def turnover_summary(
    decisions: Sequence[str], members_by_decision: Mapping[str, set[str]]
) -> list[dict[str, object]]:
    """Return one-week and four-week symmetric-difference turnover."""

    rows: list[dict[str, object]] = []
    for index, decision in enumerate(decisions):
        current = members_by_decision.get(decision, set())
        previous = members_by_decision.get(decisions[index - 1], set()) if index else set()
        four_back = members_by_decision.get(decisions[index - 4], set()) if index >= 4 else set()
        rows.append(
            {
                "decision_time": decision,
                "member_count": len(current),
                "one_week_turnover_count": len(current ^ previous),
                "four_week_turnover_count": len(current ^ four_back),
                "one_week_retention_rate": (
                    len(current & previous) / len(previous) if previous else 1.0
                ),
                "four_week_retention_rate": (
                    len(current & four_back) / len(four_back) if four_back else 1.0
                ),
                "changed": bool(current ^ previous),
            }
        )
    return rows


def concentration_metrics(rows: Sequence[Mapping[str, object]]) -> dict[str, object]:
    """Calculate liquidity concentration from one deterministic ranking."""

    ordered = sorted(rows, key=lambda row: as_int(row.get("rank", row.get("liquidity_rank", 0))))
    values = [
        as_float(row.get("liquidity", row.get("trailing_28d_median_daily_quote_turnover_usdt")))
        for row in ordered
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
        "total_liquidity": total,
        "top_1_share": share(1),
        "top_3_share": share(3),
        "top_6_share": share(6),
        "top_10_share": share(10),
        "hhi": sum(weight * weight for weight in weights),
        "effective_number_assets": 1 / sum(weight * weight for weight in weights)
        if weights and sum(weight * weight for weight in weights)
        else 0.0,
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
        absolute = values[upper - 1] - values[lower - 1] if len(values) >= lower else None
        margin = (
            absolute / values[upper - 1] if absolute is not None and values[upper - 1] else None
        )
        result[f"rank_{upper}_{lower}_absolute_difference"] = absolute
        result[f"rank_{upper}_{lower}_margin"] = margin
        for threshold in (0.01, 0.02, 0.05, 0.10, 0.20):
            result[f"rank_{upper}_{lower}_margin_below_{int(threshold * 100)}pct"] = (
                margin is not None and margin < threshold
            )
    return result


def classify_omission_risk(
    *,
    d_top6_exact: float,
    d_top10_exact: float,
    mean_top10_jaccard: float,
    current_seed_top6_share: float,
    max_year_seed_share: float,
    rank6_rank7_above_10_share: float,
    unresolved_top10: bool,
    reproducible: bool,
) -> str:
    """Apply the frozen LOW/MODERATE/HIGH/SEVERE rules exactly."""

    if (
        d_top6_exact < 0.50
        or mean_top10_jaccard < 0.70
        or current_seed_top6_share > 0.40
        or unresolved_top10
        or not reproducible
    ):
        return "SEVERE"
    low = (
        d_top6_exact >= 0.95
        and d_top10_exact >= 0.90
        and mean_top10_jaccard >= 0.95
        and current_seed_top6_share <= 0.05
        and max_year_seed_share <= 0.10
        and rank6_rank7_above_10_share >= 0.90
    )
    if low:
        return "LOW"
    moderate = (
        d_top6_exact >= 0.80
        and mean_top10_jaccard >= 0.85
        and current_seed_top6_share <= 0.15
        and max_year_seed_share <= 0.25
    )
    if moderate:
        return "MODERATE"
    if (
        d_top6_exact < 0.80
        or mean_top10_jaccard < 0.85
        or current_seed_top6_share > 0.15
        or max_year_seed_share > 0.25
    ):
        return "HIGH"
    return "INCONCLUSIVE"


def decision_for_risk(risk: str, *, integrity_pass: bool) -> tuple[str, str, dict[str, bool]]:
    """Return the frozen P2R decision, next stage, and authorization flags."""

    if not integrity_pass:
        return (
            "RD18_P2R_RESTRICTED_UNIVERSE_STRUCTURAL_RISK_UNACCEPTABLE",
            "RD18_BLOCKED_PENDING_UNIVERSE_RISK_REDESIGN",
            {
                "single_universe_research_authorized": False,
                "dual_universe_required": False,
                "strategy_candidate_generation_authorized": False,
                "production_authorized": False,
            },
        )
    if risk == "LOW":
        return (
            "RD18_P2R_SINGLE_RESTRICTED_UNIVERSE_ACCEPTABLE",
            "RD18_P3R_PREREGISTERED_RESTRICTED_STRATEGY_REPLAY",
            {
                "single_universe_research_authorized": True,
                "dual_universe_required": False,
                "strategy_candidate_generation_authorized": False,
                "production_authorized": False,
            },
        )
    if risk in {"MODERATE", "HIGH"}:
        return (
            "RD18_P2R_DUAL_UNIVERSE_ROBUSTNESS_REQUIRED",
            "RD18_P3R_PREREGISTERED_DUAL_UNIVERSE_REPLAY",
            {
                "single_universe_research_authorized": False,
                "dual_universe_required": True,
                "strategy_candidate_generation_authorized": False,
                "production_authorized": False,
            },
        )
    return (
        "RD18_P2R_RESTRICTED_UNIVERSE_STRUCTURAL_RISK_UNACCEPTABLE",
        "RD18_BLOCKED_PENDING_UNIVERSE_RISK_REDESIGN",
        {
            "single_universe_research_authorized": False,
            "dual_universe_required": False,
            "strategy_candidate_generation_authorized": False,
            "production_authorized": False,
        },
    )


__all__ = [
    "P2R_STAGE",
    "P2RError",
    "TOP_NS",
    "VARIANTS",
    "as_float",
    "as_int",
    "bool_cell",
    "classify_omission_risk",
    "classify_provenance",
    "concentration_metrics",
    "decision_for_risk",
    "exact_match",
    "membership_summary",
    "rank_displacement",
    "run_lengths",
    "set_jaccard",
    "spearman_common",
    "split_channels",
    "turnover_summary",
]
