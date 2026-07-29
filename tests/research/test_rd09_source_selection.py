from spotbot.research.rd09_source_selection import (
    CausalGrade,
    SelectionScore,
    account_for_all_symbols,
    unknown_publication_grade,
    validate_pilot_range,
    validate_selection_weights,
)


def test_selection_weights_and_non_predictive_gate() -> None:
    validate_selection_weights()
    score = SelectionScore(
        "SOURCE",
        30,
        25,
        15,
        15,
        10,
        5,
        CausalGrade.D_DERIVED_HISTORICAL_SERIES_WITH_UNKNOWN_REVISION,
        True,
        0,
        False,
    )
    score.validate()
    assert score.total == 100
    assert not score.selected
    assert "rank_ic" not in score.dimensions()


def test_pilot_dates_and_symbol_accounting() -> None:
    validate_pilot_range("2022-03-01", "2022-03-31")
    account_for_all_symbols(["BTC", "ETH"], ["ETH", "BTC"])


def test_unknown_publication_time_cannot_receive_confirmatory_grade() -> None:
    grade = unknown_publication_grade(
        event_time_available=True,
        publication_time_available=False,
        raw_data_reconstructable=False,
    )
    assert grade == CausalGrade.D_DERIVED_HISTORICAL_SERIES_WITH_UNKNOWN_REVISION


def test_paid_source_cannot_pass_without_approval() -> None:
    score = SelectionScore(
        "PAID",
        30,
        25,
        15,
        15,
        10,
        5,
        CausalGrade.A_RAW_IMMUTABLE_EVENT_TIME,
        True,
        0,
        True,
    )
    assert not score.selected
