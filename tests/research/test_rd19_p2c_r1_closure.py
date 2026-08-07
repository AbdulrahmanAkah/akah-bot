"""Tests for the RD19-P2C-R1 discovery closure."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from spotbot.research.rd19_p2c_r1_closure import (
    EXPECTED_VARIANT_COUNT,
    P2CR1ClosureError,
    build_variant_disposition,
    verify_authoritative_semantics,
)


def _runtime() -> Path:
    return Path(__file__).resolve().parents[2] / "data/research/rd19_p2c_r1_runtime"


def test_authoritative_semantics_support_closure() -> None:
    report, gates, finalists = verify_authoritative_semantics(_runtime())
    assert report["hard_gate_pass_variant_count"] == 0
    assert report["selected_for_2024_variants"] == []
    assert len(gates) == EXPECTED_VARIANT_COUNT
    assert finalists.empty


def test_all_variant_dispositions_are_rejections() -> None:
    gates = pd.read_csv(_runtime() / "variant-gate-evaluation.csv")
    rows = build_variant_disposition(gates)
    assert len(rows) == EXPECTED_VARIANT_COUNT
    assert {row["disposition"] for row in rows} == {"REJECTED_HARD_GATES"}
    assert not any(row["advancement_eligible"] for row in rows)


def test_closure_blocks_if_a_variant_is_marked_passed(
    tmp_path: Path,
) -> None:
    runtime = _runtime()
    for source in runtime.iterdir():
        if source.is_file():
            (tmp_path / source.name).write_bytes(source.read_bytes())
    gates = pd.read_csv(tmp_path / "variant-gate-evaluation.csv")
    gates.loc[0, "passed_all_hard_gates"] = True
    gates.to_csv(
        tmp_path / "variant-gate-evaluation.csv",
        index=False,
        lineterminator="\n",
    )
    with pytest.raises(P2CR1ClosureError, match="hash drift"):
        # The immutable hash contract should fail before semantic closure can proceed.
        from spotbot.research.rd19_p2c_r1_closure import (
            verify_authoritative_runtime,
        )

        verify_authoritative_runtime(tmp_path)


def test_authoritative_report_has_no_2024_access() -> None:
    report = json.loads(
        (_runtime() / "rd19-p2c-r1-correction-report-v1.json").read_text(encoding="utf-8")
    )
    assert report["2024_market_data_accessed"] is False
    assert report["post_2024_accessed"] is False
