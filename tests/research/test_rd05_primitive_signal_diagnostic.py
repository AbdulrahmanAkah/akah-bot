"""Tests for deterministic S1 statistical helpers."""

from spotbot.research.rd05_primitive_signal_diagnostic import benjamini_hochberg


def test_bh_preserves_all_declared_nulls() -> None:
    adjusted = benjamini_hochberg({"A": 0.01, "B": 0.2, "C": 1.0})
    assert set(adjusted) == {"A", "B", "C"}
    assert adjusted["A"] <= adjusted["B"] <= adjusted["C"]
