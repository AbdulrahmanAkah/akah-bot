"""RD04-D2 causal attribution of the failed point-in-time universe replay."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Final

import pandas as pd

SCHEMA_VERSION: Final = "ams-rd04-d2-universe-membership-attribution-v1"
EXPECTED_SNAPSHOTS: Final = 157
FIXED_UNIVERSE_SIZE: Final = 30
PIT_UNIVERSE_SIZE: Final = 30

MODE_FIXED: Final = "FIXED_SURVIVOR_30"
MODE_PIT: Final = "PIT_UNIVERSE"
MODE_UNION: Final = "UNION_FIXED_AND_PIT"
MODE_INTERSECTION: Final = "INTERSECTION_FIXED_AND_PIT"
MODES: Final[tuple[str, ...]] = (
    MODE_FIXED,
    MODE_PIT,
    MODE_UNION,
    MODE_INTERSECTION,
)

DECISION_ENTRANTS: Final = "PIT_ENTRANT_ADDITION_DOMINATES"
DECISION_REMOVALS: Final = "FIXED_SURVIVOR_REMOVAL_DOMINATES"
DECISION_INTERACTION: Final = "NONLINEAR_MEMBERSHIP_INTERACTION_DOMINATES"
DECISION_MIXED: Final = "MIXED_MEMBERSHIP_FAILURE"
DECISION_NO_FAILURE: Final = "MEMBERSHIP_ATTRIBUTION_NO_FAILURE"
DECISION_INVALID: Final = "MEMBERSHIP_ATTRIBUTION_INVALID"


class MembershipAttributionError(RuntimeError):
    """Raised when RD04-D2 evidence violates the frozen attribution contract."""


def utc_timestamp(value: Any) -> pd.Timestamp:
    """Return one timezone-aware UTC timestamp."""

    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        return timestamp.tz_localize("UTC")
    return timestamp.tz_convert("UTC")


def normalize_symbols(
    symbols: Sequence[str],
    *,
    expected_count: int | None = None,
) -> frozenset[str]:
    """Normalize and validate one deterministic symbol set."""

    normalized = frozenset(str(symbol).strip().upper() for symbol in symbols)
    if "" in normalized:
        raise MembershipAttributionError("Symbol sets cannot contain empty symbols.")
    if expected_count is not None and len(normalized) != expected_count:
        raise MembershipAttributionError(
            f"Symbol-count drift: {len(normalized)} != {expected_count}"
        )
    return normalized


def validate_pit_universe_map(
    pit_by_time: Mapping[pd.Timestamp, frozenset[str]],
) -> dict[str, Any]:
    """Validate the D0C/D1 weekly point-in-time top-30 mapping."""

    timestamps = sorted(utc_timestamp(value) for value in pit_by_time)
    snapshot_count = len(timestamps)
    invalid_size_count = 0
    monday_midnight_only = True
    pre_2025_only = True
    for timestamp in timestamps:
        members = pit_by_time.get(timestamp)
        if members is None:
            invalid_size_count += 1
            continue
        if len(normalize_symbols(tuple(members))) != PIT_UNIVERSE_SIZE:
            invalid_size_count += 1
        monday_midnight_only = monday_midnight_only and (
            timestamp.weekday() == 0 and timestamp.hour == 0
        )
        pre_2025_only = pre_2025_only and (timestamp < pd.Timestamp("2025-01-01T00:00:00Z"))
    passed = all(
        (
            snapshot_count == EXPECTED_SNAPSHOTS,
            invalid_size_count == 0,
            monday_midnight_only,
            pre_2025_only,
        )
    )
    return {
        "passed": passed,
        "snapshot_count": snapshot_count,
        "invalid_size_snapshot_count": invalid_size_count,
        "monday_midnight_only": monday_midnight_only,
        "pre_2025_only": pre_2025_only,
    }


def build_counterfactual_universe_maps(
    pit_by_time: Mapping[pd.Timestamp, frozenset[str]],
    fixed_symbols: Sequence[str],
) -> dict[str, dict[pd.Timestamp, frozenset[str]]]:
    """Build the frozen 2x2 membership counterfactual schedules."""

    validation = validate_pit_universe_map(pit_by_time)
    if validation["passed"] is not True:
        raise MembershipAttributionError(f"Invalid PIT universe map: {validation}")
    fixed = normalize_symbols(
        fixed_symbols,
        expected_count=FIXED_UNIVERSE_SIZE,
    )
    result: dict[str, dict[pd.Timestamp, frozenset[str]]] = {mode: {} for mode in MODES}
    for raw_timestamp in sorted(pit_by_time):
        timestamp = utc_timestamp(raw_timestamp)
        pit = normalize_symbols(
            tuple(pit_by_time[raw_timestamp]),
            expected_count=PIT_UNIVERSE_SIZE,
        )
        intersection = fixed.intersection(pit)
        union = fixed.union(pit)
        if not intersection:
            raise MembershipAttributionError(
                f"Fixed/PIT intersection is empty at {timestamp.isoformat()}."
            )
        result[MODE_FIXED][timestamp] = fixed
        result[MODE_PIT][timestamp] = pit
        result[MODE_UNION][timestamp] = frozenset(union)
        result[MODE_INTERSECTION][timestamp] = frozenset(intersection)
    return result


def filter_ranked_for_membership(
    ranked: pd.DataFrame,
    audit: Mapping[str, Any],
    *,
    timestamp: pd.Timestamp,
    universe_by_time: Mapping[pd.Timestamp, frozenset[str]],
    universe_mode: str,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Filter momentum ranks to one frozen diagnostic membership schedule."""

    key = utc_timestamp(timestamp)
    allowed = universe_by_time.get(key)
    if allowed is None:
        raise MembershipAttributionError(f"No {universe_mode} universe at {key.isoformat()}.")
    normalized_allowed = normalize_symbols(tuple(allowed))
    if not normalized_allowed:
        raise MembershipAttributionError(f"Empty {universe_mode} universe at {key.isoformat()}.")
    if "symbol" not in ranked.columns:
        raise MembershipAttributionError("Ranked momentum frame lacks symbol column.")

    source = ranked.copy()
    source["symbol"] = source["symbol"].astype(str).str.upper()
    outside = sorted(set(source["symbol"]).difference(normalized_allowed))
    filtered = source.loc[source["symbol"].isin(normalized_allowed)].copy()
    filtered.sort_values(
        ["momentum_return", "symbol"],
        ascending=[False, True],
        kind="stable",
        inplace=True,
    )
    filtered.reset_index(drop=True, inplace=True)
    if len(filtered) == 1:
        filtered["percentile_rank"] = 1.0
    elif len(filtered) > 1:
        index_series = filtered.index.to_series(index=filtered.index)
        filtered["percentile_rank"] = 1.0 - index_series / (len(filtered) - 1)

    updated = dict(audit)
    exclusions_raw = updated.get("excluded_symbols_by_reason", {})
    exclusions = (
        {str(reason): list(values) for reason, values in exclusions_raw.items()}
        if isinstance(exclusions_raw, Mapping)
        else {}
    )
    exclusions[f"OUTSIDE_{universe_mode}"] = outside
    updated["excluded_symbols_by_reason"] = exclusions
    updated["membership_attribution_mode"] = universe_mode
    updated["membership_universe_count"] = len(normalized_allowed)
    updated["membership_universe_symbols"] = sorted(normalized_allowed)
    updated["pre_membership_filter_rankable_count"] = len(source)
    updated["final_rankable_count"] = len(filtered)
    return filtered, updated


def membership_snapshot_rows(
    maps: Mapping[str, Mapping[pd.Timestamp, frozenset[str]]],
) -> list[dict[str, Any]]:
    """Describe the four membership states at every weekly rebalance."""

    fixed_map = maps.get(MODE_FIXED)
    pit_map = maps.get(MODE_PIT)
    union_map = maps.get(MODE_UNION)
    intersection_map = maps.get(MODE_INTERSECTION)
    if not all(item is not None for item in (fixed_map, pit_map, union_map, intersection_map)):
        raise MembershipAttributionError("Counterfactual maps are incomplete.")
    assert fixed_map is not None
    assert pit_map is not None
    assert union_map is not None
    assert intersection_map is not None

    timestamps = sorted(fixed_map)
    rows: list[dict[str, Any]] = []
    for timestamp in timestamps:
        fixed = fixed_map[timestamp]
        pit = pit_map[timestamp]
        union = union_map[timestamp]
        intersection = intersection_map[timestamp]
        entrants = pit.difference(fixed)
        removed = fixed.difference(pit)
        rows.append(
            {
                "rebalance_time": timestamp,
                "fixed_count": len(fixed),
                "pit_count": len(pit),
                "union_count": len(union),
                "intersection_count": len(intersection),
                "entrant_count": len(entrants),
                "removed_survivor_count": len(removed),
                "entrants": ",".join(sorted(entrants)),
                "removed_survivors": ",".join(sorted(removed)),
                "jaccard_similarity": len(intersection) / len(union),
            }
        )
    return rows


def numeric_metric(record: Mapping[str, Any], metric: str) -> float:
    """Read one finite numeric metric from an aggregate or fold record."""

    raw = record.get(metric)
    if not isinstance(raw, (int, float)):
        raise MembershipAttributionError(f"Metric is not numeric: {metric}")
    value = float(raw)
    if value != value or value in {float("inf"), float("-inf")}:
        raise MembershipAttributionError(f"Metric is not finite: {metric}")
    return value


def factorial_attribution(
    *,
    fixed: Mapping[str, Any],
    union: Mapping[str, Any],
    intersection: Mapping[str, Any],
    pit: Mapping[str, Any],
    metric: str,
) -> dict[str, Any]:
    """Compute exact 2x2 paths, interaction, and two-factor Shapley effects."""

    fixed_value = numeric_metric(fixed, metric)
    union_value = numeric_metric(union, metric)
    intersection_value = numeric_metric(intersection, metric)
    pit_value = numeric_metric(pit, metric)

    addition_on_fixed = union_value - fixed_value
    addition_after_removal = pit_value - intersection_value
    removal_without_entrants = intersection_value - fixed_value
    removal_with_entrants = pit_value - union_value
    addition_shapley = 0.5 * (addition_on_fixed + addition_after_removal)
    removal_shapley = 0.5 * (removal_without_entrants + removal_with_entrants)
    total_delta = pit_value - fixed_value
    interaction = pit_value - intersection_value - union_value + fixed_value
    decomposition_error = total_delta - addition_shapley - removal_shapley

    return {
        "metric": metric,
        "fixed_value": fixed_value,
        "union_value": union_value,
        "intersection_value": intersection_value,
        "pit_value": pit_value,
        "total_pit_minus_fixed": total_delta,
        "addition_on_fixed": addition_on_fixed,
        "addition_after_removal": addition_after_removal,
        "removal_without_entrants": removal_without_entrants,
        "removal_with_entrants": removal_with_entrants,
        "addition_shapley": addition_shapley,
        "removal_shapley": removal_shapley,
        "interaction": interaction,
        "decomposition_error": decomposition_error,
        "decomposition_exact": abs(decomposition_error) <= 1e-12,
    }


def classify_membership_failure(
    attribution: Mapping[str, Any],
) -> dict[str, Any]:
    """Classify which membership mechanism dominates the failed replay."""

    total_delta = numeric_metric(attribution, "total_pit_minus_fixed")
    addition = numeric_metric(attribution, "addition_shapley")
    removal = numeric_metric(attribution, "removal_shapley")
    interaction = numeric_metric(attribution, "interaction")
    addition_on_fixed = numeric_metric(attribution, "addition_on_fixed")
    addition_after_removal = numeric_metric(
        attribution,
        "addition_after_removal",
    )
    removal_without = numeric_metric(
        attribution,
        "removal_without_entrants",
    )
    removal_with = numeric_metric(attribution, "removal_with_entrants")

    if total_delta >= 0.0:
        decision = DECISION_NO_FAILURE
        reason = "PIT_MEMBERSHIP_DID_NOT_UNDERPERFORM_FIXED_MEMBERSHIP"
    else:
        addition_sign_flip = addition_on_fixed * addition_after_removal < 0.0
        removal_sign_flip = removal_without * removal_with < 0.0
        interaction_large = abs(interaction) >= 0.75 * abs(total_delta)
        addition_harm = max(0.0, -addition)
        removal_harm = max(0.0, -removal)
        if interaction_large and (addition_sign_flip or removal_sign_flip):
            decision = DECISION_INTERACTION
            reason = "MEMBERSHIP_EFFECTS_CHANGE_SIGN_ACROSS_THE_2X2_COUNTERFACTUAL"
        elif addition_harm >= 2.0 * max(removal_harm, 1e-12):
            decision = DECISION_ENTRANTS
            reason = "AVERAGE_PIT_ENTRANT_EFFECT_DOMINATES_SURVIVOR_REMOVAL"
        elif removal_harm >= 2.0 * max(addition_harm, 1e-12):
            decision = DECISION_REMOVALS
            reason = "AVERAGE_FIXED_SURVIVOR_REMOVAL_EFFECT_DOMINATES_ENTRANTS"
        else:
            decision = DECISION_MIXED
            reason = "ENTRANT_AND_REMOVAL_EFFECTS_ARE_BOTH_MATERIAL"

    return {
        "decision": decision,
        "reason": reason,
        "total_pit_minus_fixed": total_delta,
        "addition_shapley": addition,
        "removal_shapley": removal,
        "interaction": interaction,
        "pit_entrant_addition_harm": max(0.0, -addition),
        "fixed_survivor_removal_harm": max(0.0, -removal),
    }


def build_attribution_decision(
    *,
    base_return_attribution: Mapping[str, Any],
    structural_checks: Mapping[str, bool],
) -> dict[str, Any]:
    """Resolve the RD04-D2 diagnostic conclusion without authorizing changes."""

    structural_pass = all(bool(value) for value in structural_checks.values())
    exact = base_return_attribution.get("decomposition_exact") is True
    if not structural_pass or not exact:
        classification = {
            "decision": DECISION_INVALID,
            "reason": "ATTRIBUTION_STRUCTURE_OR_DECOMPOSITION_FAILED",
        }
    else:
        classification = classify_membership_failure(base_return_attribution)

    decision = str(classification["decision"])
    if decision == DECISION_ENTRANTS:
        next_research = "PIT_ELIGIBILITY_AND_ENTRANT_QUALITY_DIAGNOSTICS"
    elif decision == DECISION_REMOVALS:
        next_research = "MD01_M05_SURVIVORSHIP_DEPENDENCE_CONFIRMATION"
    elif decision in {DECISION_INTERACTION, DECISION_MIXED}:
        next_research = "MEMBERSHIP_SELECTION_INTERACTION_DIAGNOSTICS"
    elif decision == DECISION_NO_FAILURE:
        next_research = "RECONCILE_D1_FAILURE_WITH_D2_COUNTERFACTUALS"
    else:
        next_research = "REPAIR_ATTRIBUTION_EVIDENCE"

    return {
        **classification,
        "structural_checks": dict(structural_checks),
        "structural_pass": structural_pass,
        "next_research_recommendation": next_research,
        "rd04_d3_diagnostic_research_authorized": decision != DECISION_INVALID,
        "point_in_time_universe_research_baseline_authorized": False,
        "universe_change_authorized": False,
        "ranking_change_authorized": False,
        "weight_change_authorized": False,
        "entry_change_authorized": False,
        "exit_change_authorized": False,
        "production_ready": False,
        "live_ready": False,
    }
