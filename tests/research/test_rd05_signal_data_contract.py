"""Regression tests for non-evaluating RD05 P1 source-contract behaviour."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from spotbot.research.rd05_protocol_registration import SIGNAL_VARIANTS, TRIAL_BUDGET
from spotbot.research.rd05_signal_data_contract import (
    LABEL_CONTRACTS,
    MAX_FORWARD_HORIZON_DAYS,
    RESEARCH_END,
    P1ContractError,
    closed_bar_eligible,
    ensure_research_boundary,
    expected_label_ids,
    formula_rows,
    regime_rows,
    validate_contracts,
)


def test_registered_counts_are_preserved_without_execution() -> None:
    validate_contracts()
    assert len(SIGNAL_VARIANTS) == 33
    assert len(LABEL_CONTRACTS) == 7
    assert len(regime_rows()) == 6
    assert TRIAL_BUDGET["total_declared_trial_count"] == 261


def test_closed_bar_cutoff_excludes_bar_opening_at_decision() -> None:
    decision = datetime(2024, 1, 1, tzinfo=UTC)
    assert closed_bar_eligible(decision - timedelta(hours=4), decision, decision)
    assert not closed_bar_eligible(decision, decision + timedelta(hours=4), decision)


def test_research_boundary_allows_terminal_2024_bar_only() -> None:
    ensure_research_boundary([RESEARCH_END - timedelta(hours=4)], [RESEARCH_END])
    with pytest.raises(P1ContractError, match="research-boundary"):
        ensure_research_boundary([RESEARCH_END], [RESEARCH_END + timedelta(hours=4)])


def test_label_contracts_are_future_only_and_never_zero_imputed() -> None:
    assert set(expected_label_ids()) == {
        "FORWARD_1D_RETURN",
        "FORWARD_3D_RETURN",
        "FORWARD_7D_CLOSE_TO_CLOSE_RETURN",
        "FORWARD_14D_RETURN",
        "FORWARD_28D_RETURN",
        "FORWARD_7D_MAX_FAVOURABLE_EXCURSION",
        "FORWARD_7D_MAX_ADVERSE_EXCURSION",
    }
    assert max(item.horizon_days for item in LABEL_CONTRACTS) == MAX_FORWARD_HORIZON_DAYS
    assert all(item.last_permissible_decision_time < RESEARCH_END for item in LABEL_CONTRACTS)


def test_formula_contract_accounts_for_each_registered_signal() -> None:
    statuses = {
        "OHLCV_1D": "SOURCE_READY",
        "AVAILABILITY": "SOURCE_READY",
        "PIT_MEMBERSHIP": "SOURCE_READY",
        "QUOTE_TURNOVER_4H": "SOURCE_READY",
    }
    rows = formula_rows(statuses)
    assert len(rows) == 33
    assert {str(row["signal_id"]) for row in rows} == {item.signal_id for item in SIGNAL_VARIANTS}
    assert any(row["source_readiness"] == "BLOCKED_FORMULA_AMBIGUITY" for row in rows)
    assert not Path("data/research/rd04").joinpath("synthetic_2021_membership.parquet").exists()
