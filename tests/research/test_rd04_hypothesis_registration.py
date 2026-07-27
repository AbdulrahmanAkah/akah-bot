"""Tests for RD04-D4 hypothesis registration."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest

from spotbot.research.rd04_hypothesis_registration import (
    DECISION,
    HYPOTHESIS_IDS,
    HypothesisRegistrationError,
    build_registry,
    decision_gates,
    registered_hypotheses,
    validate_d3_authorization,
    validate_registry,
)


def d3_report() -> dict[str, Any]:
    return {
        "status": "COMPLETE",
        "decision": {
            "decision": "ENTRANT_EDGE_AND_SURVIVOR_DISPLACEMENT_CONFIRMED",
            "rd04_d4_hypothesis_registration_research_authorized": True,
            "entrant_negative_edge_confirmed": True,
            "survivor_displacement_confirmed": True,
            "entrant_union_net_pnl": -97193.91766048955,
            "entrant_pit_net_pnl": -94301.5435961918,
            "removed_survivor_fixed_net_pnl": 99489.7769194499,
            "removed_survivor_union_net_pnl": 90613.37963955523,
        },
        "authorizations": {
            "candidate_universe_authorized": False,
            "entry_change_authorized": False,
            "exit_change_authorized": False,
            "live_ready": False,
            "point_in_time_universe_research_baseline_authorized": False,
            "production_ready": False,
            "ranking_change_authorized": False,
            "universe_change_authorized": False,
            "weight_change_authorized": False,
        },
        "safety": {
            "candidate_universe_created": False,
            "holdout_2026_accessed": False,
            "parameter_optimisation_used": False,
            "portfolio_simulation_executed": False,
            "test_2025_accessed": False,
            "trade_logic_changed": False,
        },
    }


def registry() -> dict[str, Any]:
    return build_registry(
        d3_report=d3_report(),
        d3_evidence_commit="a" * 40,
        d3_report_sha256="b" * 64,
        generated_at="2026-07-27T00:00:00Z",
    )


def test_validate_d3_authorization_accepts_frozen_trigger() -> None:
    result = validate_d3_authorization(d3_report())
    assert result["status"] == "PASS"
    assert result["entrant_union_net_pnl"] < 0.0


def test_validate_d3_authorization_rejects_wrong_decision() -> None:
    payload = d3_report()
    payload["decision"]["decision"] = "OTHER"
    with pytest.raises(HypothesisRegistrationError):
        validate_d3_authorization(payload)


def test_hypothesis_identifiers_and_order_are_frozen() -> None:
    identifiers = tuple(item["hypothesis_id"] for item in registered_hypotheses())
    assert identifiers == HYPOTHESIS_IDS


def test_liquidity_floor_is_exact_and_causal() -> None:
    item = registered_hypotheses()[0]
    parameters = item["frozen_parameters"]
    assert parameters["lookback_completed_days"] == 30
    assert parameters["median_quote_turnover_floor_usdt"] == 250000.0
    assert parameters["future_data_allowed"] is False


def test_stop_ablation_cannot_guess_discrete_grid() -> None:
    item = registered_hypotheses()[1]
    assert item["status"] == "BLOCKED_PENDING_FROZEN_V5R1_GRID_RECOVERY"
    assert item["frozen_parameters"]["exact_discrete_grid"] == ("MUST_BE_RECOVERED_FROM_V5R1")


def test_tail_labels_never_exclude_trades() -> None:
    item = registered_hypotheses()[2]
    assert item["authorization_if_passed"] == "NONE_DIAGNOSTIC_ONLY"
    assert item["frozen_parameters"]["outcome_based_exclusion_allowed"] is False


def test_equal_weight_requires_exact_bf01_protocol() -> None:
    item = registered_hypotheses()[3]
    assert item["status"] == "BLOCKED_PENDING_EXACT_BF01_PROTOCOL_RECOVERY"
    assert item["frozen_parameters"]["benchmark_reconstruction_from_memory_allowed"] is False


def test_midweek_hypothesis_is_diagnostic_before_reentry() -> None:
    item = registered_hypotheses()[4]
    assert item["status"] == "READY_FOR_DIAGNOSTIC_ONLY"
    assert item["frozen_parameters"]["primary_weekday"] == "TUESDAY"
    assert item["frozen_parameters"]["reentry_attempts_if_later_tested"] == 1


def test_membership_exit_hypothesis_does_not_authorize_grace() -> None:
    item = registered_hypotheses()[5]
    assert item["frozen_parameters"]["existing_position_grandfathering_authorized"] is False
    assert item["frozen_parameters"]["new_entry_outside_pit_authorized"] is False


def test_registered_gate_preserves_original_edge_thresholds() -> None:
    gates = {item["gate_id"]: item["requirements"] for item in decision_gates()}
    gate = gates["REGISTERED_BASE_EDGE"]
    assert "profit factor >= 1.05" in gate
    assert "positive folds >= 2" in gate
    assert "top-1 contribution <= 0.60" in gate


def test_registry_marks_expert_text_as_user_supplied() -> None:
    payload = registry()
    expert = payload["evidence_basis"]["expert_review"]
    assert expert["provenance"] == "USER_SUPPLIED_TEXT"
    assert expert["independently_verified_in_d4"] is False


def test_registry_does_not_treat_tuesday_observation_as_fact() -> None:
    payload = registry()
    observation = payload["evidence_basis"]["user_hypothesis"]
    assert observation["treated_as_fact"] is False
    assert observation["registered_for_diagnostic_only"] is True


def test_registry_refuses_outcome_based_rules() -> None:
    payload = registry()
    proposals = {item["proposal"]: item["status"] for item in payload["deferred_or_prohibited"]}
    assert proposals["BLACKLIST_FTT_CRV_ALGO_ETC_OR_ANY_REALIZED_LOSER"] == "PROHIBITED"
    assert proposals["TUESDAY_ONLY_ENTRY_RULE"] == "DEFERRED"


def test_validate_registry_rejects_universe_authorization() -> None:
    payload = registry()
    payload["authorizations"]["universe_change_authorized"] = True
    with pytest.raises(HypothesisRegistrationError):
        validate_registry(payload)


def test_build_registry_completes_registration_only() -> None:
    payload = registry()
    assert payload["decision"] == DECISION
    assert payload["safety"]["portfolio_simulation_executed"] is False
    assert payload["authorizations"]["d5_research_sequence_authorized"] is True
    validate_registry(payload)


def test_validate_registry_rejects_hypothesis_order_drift() -> None:
    payload = deepcopy(registry())
    payload["hypotheses"] = list(reversed(payload["hypotheses"]))
    with pytest.raises(HypothesisRegistrationError):
        validate_registry(payload)
