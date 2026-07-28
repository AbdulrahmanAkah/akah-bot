from __future__ import annotations

import json

import pytest

from spotbot.research.rd04_v5r1_atr_grid_recovery import (
    DECISION_BLOCKED,
    DECISION_BOUNDED,
    DECISION_GRID,
    AtrGridRecoveryError,
    GridCandidate,
    build_recovery_decision,
    extract_add_on_floors,
    extract_configuration_variants,
    extract_stop_models,
    extract_trial_summary,
    recover_source_contract,
    scan_json_grid_candidates,
    scan_python_grid_candidates,
    validate_report,
)

SOURCE = """
def configuration_grid():
    variants = (
        ("SHALLOW_PULLBACK_RECLAIM", "STRUCTURE_BALANCED"),
        ("SHALLOW_PULLBACK_RECLAIM", "STRUCTURE_WIDE"),
        ("DEEP_PULLBACK_RECOVERY", "STRUCTURE_BALANCED"),
        ("DEEP_PULLBACK_RECOVERY", "STRUCTURE_WIDE"),
        ("MOMENTUM_REACCELERATION", "STRUCTURE_BALANCED"),
        ("HYBRID_ALL_THREE", "STRUCTURE_BALANCED"),
    )
    return variants

def stop_distance(entry, atr, structural, model):
    minimum, maximum = (
        (2.2, 3.4)
        if model == "STRUCTURE_BALANCED"
        else (2.6, 4.0)
    )
    structural_distance = entry - structural
    if structural_distance <= 0 or structural_distance / atr > maximum:
        return None
    return max(structural_distance, minimum * atr)

def make_candidate(row, params, fold_id, action="ENTRY"):
    atr = float(row["atr"])
    structural = float(row["structure_reference"])
    distance = (
        (2.2 if params.stop_model == "STRUCTURE_BALANCED" else 2.6) * atr
        if action == "ADD_ON"
        else stop_distance(float(row["close"]), atr, structural, params.stop_model)
    )
    return distance
"""


def test_extract_stop_models() -> None:
    models = extract_stop_models(SOURCE)
    assert [(item.name, item.minimum_atr, item.maximum_atr) for item in models] == [
        ("STRUCTURE_BALANCED", 2.2, 3.4),
        ("STRUCTURE_WIDE", 2.6, 4.0),
    ]


def test_extract_stop_models_rejects_drift() -> None:
    with pytest.raises(AtrGridRecoveryError):
        extract_stop_models(SOURCE.replace("(2.2, 3.4)", "(2.2, 3.5)"))


def test_extract_configuration_variants() -> None:
    variants = extract_configuration_variants(SOURCE)
    assert len(variants) == 6
    assert variants[-1] == ("HYBRID_ALL_THREE", "STRUCTURE_BALANCED")


def test_extract_configuration_variants_rejects_missing_row() -> None:
    changed = SOURCE.replace(
        '        ("HYBRID_ALL_THREE", "STRUCTURE_BALANCED"),\n',
        "",
    )
    with pytest.raises(AtrGridRecoveryError):
        extract_configuration_variants(changed)


def test_extract_add_on_floors() -> None:
    assert extract_add_on_floors(SOURCE) == {
        "STRUCTURE_BALANCED": 2.2,
        "STRUCTURE_WIDE": 2.6,
    }


def test_recover_source_contract_matches_d4_range() -> None:
    contract = recover_source_contract(SOURCE)
    assert contract["d4_range_matches_balanced"] is True
    assert contract["effective_stop_atr_is_continuous_within_bounds"] is True


def test_python_grid_scanner_finds_exact_literal() -> None:
    source = "STOP_ATR_GRID = (2.2, 2.6, 3.0, 3.4)\n"
    found = scan_python_grid_candidates("grid.py", source)
    assert len(found) == 1
    assert found[0].values == (2.2, 2.6, 3.0, 3.4)


def test_python_grid_scanner_ignores_bounds_assignment() -> None:
    source = "minimum, maximum = (2.2, 3.4)\n"
    assert scan_python_grid_candidates("bounds.py", source) == ()


def test_python_grid_scanner_finds_arange_definition() -> None:
    source = "ATR_STOP_GRID = np.arange(2.2, 3.5, 0.4)\n"
    found = scan_python_grid_candidates("grid.py", source)
    assert len(found) == 1
    assert found[0].values == (2.2, 3.5, 0.4)


def test_json_grid_scanner_finds_only_named_grid() -> None:
    source = json.dumps(
        {
            "atr_stop_grid": [2.2, 2.6, 3.0, 3.4],
            "observed_stop_atr": [2.31, 2.82],
        }
    )
    found = scan_json_grid_candidates("grid.json", source)
    assert len(found) == 1
    assert found[0].values == (2.2, 2.6, 3.0, 3.4)


def test_trial_summary_detects_continuous_values() -> None:
    source = json.dumps(
        {
            "configuration": {
                "configuration_id": "AMS-V5R1-A09",
                "family": "MOMENTUM_REACCELERATION",
                "stop_model": "STRUCTURE_BALANCED",
                "fibonacci_mode": "NO_FIBONACCI",
                "threshold": 55,
            },
            "fold_results": [
                {"base": {"candidate_ledger": [{"stop_atr": 2.2}, {"stop_atr": 3.12}]}}
            ],
        }
    )
    row = extract_trial_summary("trial.json", source)
    assert row["observed_min_stop_atr"] == 2.2
    assert row["observed_max_stop_atr"] == 3.12
    assert row["observed_contains_non_grid_values"] is True


def test_trial_summary_rejects_no_stop_evidence() -> None:
    source = json.dumps({"configuration": {}})
    with pytest.raises(AtrGridRecoveryError):
        extract_trial_summary("trial.json", source)


def test_decision_recovers_bounded_model_without_grid() -> None:
    decision = build_recovery_decision(
        source_contract=recover_source_contract(SOURCE),
        explicit_grid_candidates=(),
        all_trial_sources_present=True,
        d4_dependency_matches=True,
        source_blob_matches=True,
    )
    assert decision["decision"] == DECISION_BOUNDED
    assert decision["d5b1_stop_protocol_adjudication_research_authorized"] is True
    assert decision["d5b_execution_authorized"] is False


def test_decision_recovers_one_explicit_grid() -> None:
    candidate = GridCandidate(
        "source.py",
        "ATR_STOP_GRID",
        (2.2, 2.6, 3.0, 3.4),
        "PYTHON_LITERAL_SEQUENCE",
    )
    decision = build_recovery_decision(
        source_contract=recover_source_contract(SOURCE),
        explicit_grid_candidates=(candidate,),
        all_trial_sources_present=True,
        d4_dependency_matches=True,
        source_blob_matches=True,
    )
    assert decision["decision"] == DECISION_GRID


def test_decision_blocks_conflicting_grids() -> None:
    candidates = (
        GridCandidate("a.py", "ATR_GRID", (2.2, 2.6), "PYTHON_LITERAL_SEQUENCE"),
        GridCandidate("b.py", "ATR_GRID", (2.2, 3.4), "PYTHON_LITERAL_SEQUENCE"),
    )
    decision = build_recovery_decision(
        source_contract=recover_source_contract(SOURCE),
        explicit_grid_candidates=candidates,
        all_trial_sources_present=True,
        d4_dependency_matches=True,
        source_blob_matches=True,
    )
    assert decision["decision"] == DECISION_BLOCKED
    assert decision["d5b1_stop_protocol_adjudication_research_authorized"] is False


def test_decision_blocks_source_failure() -> None:
    decision = build_recovery_decision(
        source_contract=recover_source_contract(SOURCE),
        explicit_grid_candidates=(),
        all_trial_sources_present=False,
        d4_dependency_matches=True,
        source_blob_matches=True,
    )
    assert decision["decision"] == DECISION_BLOCKED


def test_validate_report_accepts_safe_bounded_result() -> None:
    report = {
        "schema_version": "ams-rd04-d5b0-v5r1-atr-grid-recovery-v1",
        "status": "COMPLETE",
        "decision": build_recovery_decision(
            source_contract=recover_source_contract(SOURCE),
            explicit_grid_candidates=(),
            all_trial_sources_present=True,
            d4_dependency_matches=True,
            source_blob_matches=True,
        ),
        "safety": {
            "portfolio_simulation_executed": False,
            "parameter_optimisation_used": False,
            "outcome_based_stop_selection_used": False,
            "test_2025_accessed": False,
            "holdout_2026_accessed": False,
            "trade_logic_changed": False,
        },
    }
    validate_report(report)


def test_validate_report_rejects_execution_authorization() -> None:
    decision = build_recovery_decision(
        source_contract=recover_source_contract(SOURCE),
        explicit_grid_candidates=(),
        all_trial_sources_present=True,
        d4_dependency_matches=True,
        source_blob_matches=True,
    )
    decision["d5b_execution_authorized"] = True
    report = {
        "schema_version": "ams-rd04-d5b0-v5r1-atr-grid-recovery-v1",
        "status": "COMPLETE",
        "decision": decision,
        "safety": {
            "portfolio_simulation_executed": False,
            "parameter_optimisation_used": False,
            "outcome_based_stop_selection_used": False,
            "test_2025_accessed": False,
            "holdout_2026_accessed": False,
            "trade_logic_changed": False,
        },
    }
    with pytest.raises(AtrGridRecoveryError):
        validate_report(report)
