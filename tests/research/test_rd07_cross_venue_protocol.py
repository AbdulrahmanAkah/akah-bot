from spotbot.research.rd07_cross_venue_protocol import (
    CONFIRMATORY_IDS,
    POST_HOC_IDS,
    SIGNAL_IDS,
    validate_protocol,
)


def test_protocol_trial_budget() -> None:
    validate_protocol()
    assert len(SIGNAL_IDS) == 14
    assert len(CONFIRMATORY_IDS) == 13
    assert POST_HOC_IDS == ("BN_LOW_REALIZED_VOLATILITY_42",)
