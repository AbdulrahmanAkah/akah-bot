from datetime import date

from spotbot.research.rd09b_market_level_quality import (
    MonthQuality,
    evaluate_month_rows,
    feasibility_decision,
    largest_missing_run,
    metric_families,
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
    assert passing_namespace(
        (True, True, True),
        families,
        "B_RECONSTRUCTABLE_FROM_RAW_CHAIN",
    )
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


def test_month_rows_are_evaluated_without_silent_filling() -> None:
    rows = [
        {
            "day": f"2024-03-{day:02d}",
            "successful_transaction_count": 10,
            "unique_sending_addresses": 4,
            "unique_receiving_addresses": 5,
            "unique_active_addresses": 8,
            "native_fees_paid": 1.5,
            "block_count": 100,
            "native_transfer_count": 9,
        }
        for day in range(1, 32)
    ]
    diagnostics = evaluate_month_rows(
        rows,
        start="2024-03-01T00:00:00Z",
        end_exclusive="2024-04-01T00:00:00Z",
    )
    assert diagnostics.quality.passed
    assert diagnostics.quality.coverage == 1
    assert diagnostics.null_count_by_metric["native_fees_paid"] == 0
    assert metric_families(set(diagnostics.observed_metrics)) == {
        "TRANSACTION_ACTIVITY",
        "FEES_OR_BLOCK_PRODUCTION",
    }


def test_duplicate_and_nonfinite_values_fail_quality() -> None:
    rows = [
        {
            "day": "2024-03-01",
            "successful_transaction_count": "nan",
            "unique_sending_addresses": "",
            "unique_receiving_addresses": "",
            "unique_active_addresses": "",
            "native_fees_paid": 1,
            "block_count": 1,
            "native_transfer_count": 1,
        },
        {
            "day": "2024-03-01",
            "successful_transaction_count": 1,
            "unique_sending_addresses": "",
            "unique_receiving_addresses": "",
            "unique_active_addresses": "",
            "native_fees_paid": 1,
            "block_count": 1,
            "native_transfer_count": 1,
        },
    ]
    diagnostics = evaluate_month_rows(
        rows,
        start="2024-03-01T00:00:00Z",
        end_exclusive="2024-04-01T00:00:00Z",
    )
    assert diagnostics.quality.duplicate_days == 1
    assert diagnostics.quality.nonfinite_count == 1
    assert not diagnostics.quality.passed
