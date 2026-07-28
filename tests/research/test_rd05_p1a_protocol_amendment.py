"""Tests for the pre-execution RD05 P1A amendment."""

from spotbot.research.rd05_p1a_protocol_amendment import (
    FOLDS,
    FORMULAS,
    amendment_document,
    validate_amendment,
)


def test_p1a_freezes_three_covered_folds_and_six_formulas() -> None:
    validate_amendment()
    assert len(FOLDS) == 3
    assert len(FORMULAS) == 6
    assert amendment_document()["trial_budget"]["total_declared_trial_count"] == 261


def test_p1a_explicitly_forbids_synthetic_2021_membership() -> None:
    document = amendment_document()
    assert document["membership_contract"]["no_synthetic_2021_membership"] is True
    assert document["membership_contract"]["2021_ohlcv_warmup_only"] is True
