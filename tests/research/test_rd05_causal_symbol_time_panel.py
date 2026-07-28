"""Contracts for the authorised causal P2 artifacts."""

from spotbot.research.rd05_causal_symbol_time_panel import LABEL_IDS, REGIME_IDS, SIGNAL_IDS


def test_p2_registry_columns_are_complete() -> None:
    assert len(SIGNAL_IDS) == 33
    assert len(LABEL_IDS) == 7
    assert len(REGIME_IDS) == 6
