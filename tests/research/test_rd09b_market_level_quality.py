from datetime import date

from spotbot.research.rd09b_market_level_quality import (
    MonthQuality,
    feasibility_decision,
    largest_missing_run,
    passing_namespace,
)


def test_daily_quality_and_missing_run_contract() -> None:
    expected = tuple(date(2024, 3, day) for day in range(1, 8))
    observed = {expected[0], expected[1], expected[5], expected[6]}
    assert largest_missing_run(expected, observed) == 3
    quality = MonthQuality(31, 30, 0, 1, 1, 0, 0, 0)
    assert quality.passed


def test_four_of_five_and_common_family_gate() -> None:
    families = {"TRANSACTION_ACTIVITY", "FEES_OR_BLOCK_PRODUCTION"}
    assert passing_namespace((True, True, True), families, "B_RECONSTRUCTABLE_FROM_RAW_CHAIN")
    decision, score, authorized = feasibility_decision(
        passing_namespace_count=4,
        common_family_namespace_count=4,
        zero_paid_spend=True,
        conflicts=0,
    )
    assert decision == "RD09B_DUNE_MARKET_LEVEL_FEASIBILITY_CONFIRMED"
    assert score >= 70
    assert authorized


def test_incomplete_pilot_cannot_authorize_source_freeze() -> None:
    decision, _score, authorized = feasibility_decision(
        passing_namespace_count=3,
        common_family_namespace_count=3,
        zero_paid_spend=True,
        conflicts=0,
    )
    assert decision == "RD09B_DUNE_MARKET_LEVEL_FEASIBILITY_INSUFFICIENT"
    assert not authorized
