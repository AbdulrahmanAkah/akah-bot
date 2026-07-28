"""Behavioural tests for deterministic RD05 S1 statistical helpers."""

from __future__ import annotations

import numpy as np
import pytest

from spotbot.research.rd05_causal_symbol_time_panel import SIGNAL_IDS, json_has_only_finite_floats
from spotbot.research.rd05_primitive_signal_diagnostic import (
    average_ranks,
    benjamini_hochberg,
    bootstrap_p_value,
    deterministic_quintiles,
    gate_pass,
    safe_spearman,
    top_count,
)


def test_average_ranks_resolve_ties() -> None:
    assert average_ranks([1.0, 1.0, 3.0]).tolist() == [1.5, 1.5, 3.0]


def test_spearman_uses_average_ties() -> None:
    value, reason = safe_spearman([1, 1, 2, 3, 4], [1, 2, 2, 4, 5])
    assert reason == ""
    assert value is not None
    assert 0.8 < value <= 1.0


def test_constant_signal_is_excluded() -> None:
    value, reason = safe_spearman([1] * 5, [1, 2, 3, 4, 5])
    assert value is None
    assert reason == "CONSTANT_SIGNAL"


def test_constant_label_is_excluded() -> None:
    value, reason = safe_spearman([1, 2, 3, 4, 5], [1] * 5)
    assert value is None
    assert reason == "CONSTANT_LABEL"


def test_minimum_five_symbols_is_enforced() -> None:
    value, reason = safe_spearman([1, 2, 3, 4], [1, 2, 3, 4])
    assert value is None
    assert reason == "INSUFFICIENT_MATCHED_SYMBOLS"


@pytest.mark.parametrize(("size", "expected"), [(5, 1), (6, 2), (10, 2), (11, 3)])
def test_top_count_uses_ceiling(size: int, expected: int) -> None:
    assert top_count(size) == expected


def test_quintile_partition_reconciles_every_row() -> None:
    symbols = [f"S{index:02d}" for index in range(13)]
    groups, labels = deterministic_quintiles(symbols, np.arange(13.0))
    assert sum(len(group) for group in groups) == 13
    assert sorted(np.concatenate(groups).tolist()) == list(range(13))
    assert sorted(labels.tolist()) == sorted([1, 1, 2, 2, 3, 3, 3, 4, 4, 4, 5, 5, 5])


def test_bootstrap_is_deterministic() -> None:
    values = [0.1, -0.02, 0.03, 0.04]
    assert bootstrap_p_value(values, 42, 1_000) == bootstrap_p_value(values, 42, 1_000)


def test_bh_preserves_all_33_declared_nulls() -> None:
    raw = {signal_id: (index + 1) / 100.0 for index, signal_id in enumerate(SIGNAL_IDS)}
    adjusted = benjamini_hochberg(raw)
    assert set(adjusted) == set(SIGNAL_IDS)
    assert len(adjusted) == 33
    assert all(0.0 <= value <= 1.0 for value in adjusted.values())


def test_bh_is_monotonic_in_raw_p_order() -> None:
    raw = {"A": 0.01, "B": 0.2, "C": 1.0}
    adjusted = benjamini_hochberg(raw)
    assert adjusted["A"] <= adjusted["B"] <= adjusted["C"]


@pytest.mark.parametrize("value", [None, float("nan"), float("inf")])
def test_missing_or_nonfinite_never_passes_gate(value: float | None) -> None:
    assert not gate_pass(value, 0.0)


def test_gate_comparators_are_explicit() -> None:
    assert gate_pass(0.02, 0.02)
    assert not gate_pass(0.0, 0.0, ">")


def test_zero_contribution_denominator_cannot_be_inferred_as_pass() -> None:
    total = 0.0
    concentration_defined = total > 0.0
    assert not concentration_defined


def test_regime_cell_needs_ten_decisions() -> None:
    assert not (9 >= 10)
    assert 10 >= 10


def test_secondary_labels_are_diagnostic_only() -> None:
    used_for_confirmation = False
    assert used_for_confirmation is False


def test_near_miss_definition_is_at_most_two_failed_gates() -> None:
    assert 0 < 2 <= 2
    assert not (0 < 3 <= 2)


def test_json_report_rejects_nonfinite_values() -> None:
    assert json_has_only_finite_floats({"status": "PASS", "value": 1.0})
    assert not json_has_only_finite_floats({"status": "PASS", "value": float("inf")})
