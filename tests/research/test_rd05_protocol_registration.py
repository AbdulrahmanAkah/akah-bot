"""Behavioural tests for non-executing RD05 protocol registration."""

from __future__ import annotations

import pytest

from spotbot.research.rd05_protocol_registration import (
    LABELS,
    NEXT_STAGE,
    PROTOCOL_DECISION,
    REGIMES,
    SAFETY,
    SIGNAL_FAMILIES,
    SIGNAL_VARIANTS,
    STAGES,
    TRIAL_BUDGET,
    RD05ProtocolError,
    build_protocol,
    text_contract_valid,
    validate_protocol,
    variant_by_id,
)


def test_signal_registry_is_exact_unique_and_not_executed() -> None:
    assert len(SIGNAL_FAMILIES) == 8
    assert len(SIGNAL_VARIANTS) == 33
    assert len({item.signal_id for item in SIGNAL_VARIANTS}) == 33
    assert all(item.execution_status == "REGISTERED_NOT_EXECUTED" for item in SIGNAL_VARIANTS)
    with pytest.raises(RD05ProtocolError, match="undeclared"):
        variant_by_id("POST_HOC_WINNER")


def test_labels_are_future_only_and_never_computed_during_p0() -> None:
    assert len(LABELS) == 7
    assert LABELS[0].label_id == "FORWARD_7D_CLOSE_TO_CLOSE_RETURN"
    assert max(item.horizon_days for item in LABELS) == 28
    assert all(item.execution_status == "REGISTERED_NOT_COMPUTED" for item in LABELS)


def test_regime_and_trial_contracts_are_frozen() -> None:
    assert len(REGIMES) == 6
    assert all("expanding-history" in item["threshold_contract"] for item in REGIMES[1:])
    assert TRIAL_BUDGET == {
        "maximum_primitive_trials": 33,
        "maximum_regime_interactions": 198,
        "maximum_ensemble_candidates": 28,
        "maximum_model_families": 2,
        "total_declared_trial_count": 261,
    }


def test_stage_chain_and_safety_forbid_a_portfolio() -> None:
    assert len(STAGES) == 10
    assert STAGES[0] == "RD05-P0-PROTOCOL-REGISTRATION"
    assert STAGES[-1] == "RD05-FINAL-PRE-HOLDOUT-ADJUDICATION"
    protocol = build_protocol({"RD04_FINAL": "a" * 64})
    assert protocol["decision"]["decision"] == PROTOCOL_DECISION
    assert protocol["decision"]["next_stage"] == NEXT_STAGE
    assert protocol["decision"]["portfolio_simulation_authorized"] is False
    assert SAFETY["test_2025_accessed"] is False
    assert SAFETY["holdout_2026_accessed"] is False
    assert SAFETY["point_in_time_universe_research_baseline_authorized"] is False


def test_protocol_and_text_contracts_pass() -> None:
    validate_protocol()
    assert text_contract_valid("registered\n")
    assert not text_contract_valid("missing newline")
    assert not text_contract_valid("trailing space \n")
