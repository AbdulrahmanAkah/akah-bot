from __future__ import annotations

import pandas as pd
import pytest

from spotbot.research.rd04_universe_membership_attribution import (
    DECISION_ENTRANTS,
    DECISION_INTERACTION,
    DECISION_MIXED,
    DECISION_NO_FAILURE,
    DECISION_REMOVALS,
    EXPECTED_SNAPSHOTS,
    MODE_FIXED,
    MODE_INTERSECTION,
    MODE_PIT,
    MODE_UNION,
    MembershipAttributionError,
    build_attribution_decision,
    build_counterfactual_universe_maps,
    classify_membership_failure,
    factorial_attribution,
    filter_ranked_for_membership,
    membership_snapshot_rows,
    normalize_symbols,
    validate_pit_universe_map,
)


def fixed_symbols() -> list[str]:
    return [f"F{index:02d}" for index in range(30)]


def pit_map() -> dict[pd.Timestamp, frozenset[str]]:
    members = frozenset([*fixed_symbols()[:25], *[f"P{index:02d}" for index in range(5)]])
    timestamps = pd.date_range(
        "2022-01-03T00:00:00Z",
        periods=EXPECTED_SNAPSHOTS,
        freq="7D",
    )
    return {pd.Timestamp(timestamp): members for timestamp in timestamps}


def test_normalize_symbols_rejects_count_drift() -> None:
    with pytest.raises(MembershipAttributionError):
        normalize_symbols(["BTC", "ETH"], expected_count=30)


def test_validate_pit_universe_map_accepts_frozen_schedule() -> None:
    validation = validate_pit_universe_map(pit_map())
    assert validation["passed"] is True
    assert validation["snapshot_count"] == EXPECTED_SNAPSHOTS


def test_counterfactual_maps_form_exact_2x2_membership() -> None:
    maps = build_counterfactual_universe_maps(pit_map(), fixed_symbols())
    timestamp = sorted(maps[MODE_PIT])[0]
    assert len(maps[MODE_FIXED][timestamp]) == 30
    assert len(maps[MODE_PIT][timestamp]) == 30
    assert len(maps[MODE_INTERSECTION][timestamp]) == 25
    assert len(maps[MODE_UNION][timestamp]) == 35
    assert maps[MODE_UNION][timestamp] == (maps[MODE_FIXED][timestamp] | maps[MODE_PIT][timestamp])
    assert maps[MODE_INTERSECTION][timestamp] == (
        maps[MODE_FIXED][timestamp] & maps[MODE_PIT][timestamp]
    )


def test_membership_snapshot_rows_report_additions_and_removals() -> None:
    maps = build_counterfactual_universe_maps(pit_map(), fixed_symbols())
    rows = membership_snapshot_rows(maps)
    assert len(rows) == EXPECTED_SNAPSHOTS
    assert rows[0]["entrant_count"] == 5
    assert rows[0]["removed_survivor_count"] == 5
    assert rows[0]["intersection_count"] == 25


def test_filter_ranked_membership_allows_variable_universe_size() -> None:
    timestamp = pd.Timestamp("2022-01-03T00:00:00Z")
    ranked = pd.DataFrame(
        {
            "symbol": ["BTC", "ETH", "SOL"],
            "momentum_return": [0.1, 0.3, 0.2],
            "percentile_rank": [0.5, 1.0, 0.0],
        }
    )
    filtered, audit = filter_ranked_for_membership(
        ranked,
        {"excluded_symbols_by_reason": {}},
        timestamp=timestamp,
        universe_by_time={timestamp: frozenset({"BTC", "SOL"})},
        universe_mode=MODE_INTERSECTION,
    )
    assert filtered["symbol"].tolist() == ["SOL", "BTC"]
    assert filtered["percentile_rank"].tolist() == [1.0, 0.0]
    assert audit["membership_universe_count"] == 2


def test_factorial_attribution_is_exact() -> None:
    record = factorial_attribution(
        fixed={"compounded_return": 1.0},
        union={"compounded_return": 0.8},
        intersection={"compounded_return": 0.4},
        pit={"compounded_return": 0.1},
        metric="compounded_return",
    )
    assert record["total_pit_minus_fixed"] == pytest.approx(-0.9)
    assert record["addition_shapley"] == pytest.approx(-0.25)
    assert record["removal_shapley"] == pytest.approx(-0.65)
    assert record["decomposition_exact"] is True


def attribution(
    *,
    total: float,
    addition: float,
    removal: float,
    interaction: float = 0.0,
    addition_paths: tuple[float, float] | None = None,
    removal_paths: tuple[float, float] | None = None,
) -> dict[str, float | bool]:
    add_paths = addition_paths or (addition, addition)
    remove_paths = removal_paths or (removal, removal)
    return {
        "total_pit_minus_fixed": total,
        "addition_shapley": addition,
        "removal_shapley": removal,
        "interaction": interaction,
        "addition_on_fixed": add_paths[0],
        "addition_after_removal": add_paths[1],
        "removal_without_entrants": remove_paths[0],
        "removal_with_entrants": remove_paths[1],
        "decomposition_exact": True,
    }


def test_classification_detects_entrant_dominance() -> None:
    result = classify_membership_failure(attribution(total=-1.0, addition=-0.8, removal=-0.2))
    assert result["decision"] == DECISION_ENTRANTS


def test_classification_detects_removal_dominance() -> None:
    result = classify_membership_failure(attribution(total=-1.0, addition=-0.2, removal=-0.8))
    assert result["decision"] == DECISION_REMOVALS


def test_classification_detects_mixed_harm() -> None:
    result = classify_membership_failure(attribution(total=-1.0, addition=-0.55, removal=-0.45))
    assert result["decision"] == DECISION_MIXED


def test_classification_detects_nonlinear_sign_flip() -> None:
    result = classify_membership_failure(
        attribution(
            total=-1.0,
            addition=-0.4,
            removal=-0.6,
            interaction=-0.8,
            addition_paths=(0.2, -1.0),
            removal_paths=(0.1, -1.3),
        )
    )
    assert result["decision"] == DECISION_INTERACTION


def test_classification_detects_no_membership_failure() -> None:
    result = classify_membership_failure(attribution(total=0.1, addition=0.05, removal=0.05))
    assert result["decision"] == DECISION_NO_FAILURE


def test_decision_never_authorizes_universe_or_trade_changes() -> None:
    result = build_attribution_decision(
        base_return_attribution=attribution(
            total=-1.0,
            addition=-0.8,
            removal=-0.2,
        ),
        structural_checks={
            "d1_failure_verified": True,
            "all_fold_statuses_passed": True,
            "dataset_hashes_invariant": True,
            "counterfactual_maps_valid": True,
        },
    )
    assert result["rd04_d3_diagnostic_research_authorized"] is True
    assert result["point_in_time_universe_research_baseline_authorized"] is False
    assert result["universe_change_authorized"] is False
    assert result["ranking_change_authorized"] is False
    assert result["weight_change_authorized"] is False
    assert result["entry_change_authorized"] is False
    assert result["exit_change_authorized"] is False
