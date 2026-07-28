from spotbot.research.rd06_protocol_registration import (
    CONFIRMATORY_IDS,
    GRIDS,
    LABEL_IDS,
    POST_HOC_IDS,
    REGIME_IDS,
    SIGNAL_IDS,
    validate_protocol,
)


def test_registry_counts_and_uniqueness() -> None:
    validate_protocol()
    assert len(SIGNAL_IDS) == len(set(SIGNAL_IDS)) == 15
    assert len(CONFIRMATORY_IDS) == 13
    assert len(POST_HOC_IDS) == 2
    assert len(LABEL_IDS) == 5
    assert len(REGIME_IDS) == 6
    assert set(GRIDS.values()) == {0, 8, 16}


def test_age_is_not_a_trial() -> None:
    assert "AGE_OR_TENURE" not in SIGNAL_IDS
