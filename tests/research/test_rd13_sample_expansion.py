from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from spotbot.research.rd12_component_attribution import VARIANTS
from spotbot.research.rd13_sample_expansion import (
    BOOTSTRAP_RESAMPLES,
    BOOTSTRAP_SEED,
    FULL_VARIANTS,
    SELECTED,
)


def test_rd13_registry_is_frozen_to_twelve_configurations() -> None:
    assert len(VARIANTS) == 12
    assert len({variant.variant_id for variant in VARIANTS}) == 12
    assert len(FULL_VARIANTS) == 7


def test_rd13_long_history_cohort_is_objective_three_asset_set() -> None:
    assert SELECTED == ("BTC/USDT", "ETH/USDT", "ADA/USDT")


def test_rd13_bootstrap_contract_is_frozen() -> None:
    assert BOOTSTRAP_SEED == 20260730
    assert BOOTSTRAP_RESAMPLES == 2000


def test_rd13_final_report_contract_when_generated() -> None:
    path = Path("data/research/rd13/rd13-final-report-v1.json")
    if not path.exists():
        return
    report = json.loads(path.read_text(encoding="utf-8"))
    assert report["variant_count"] == 12
    assert report["cohort_count"] == 2
    assert report["test_2025_accessed"] is False
    assert report["holdout_2026_accessed"] is False
    assert report["dune_api_called"] is False
    assert report["optimization_performed"] is False
    assert report["winner_selected"] is False
    assert report["frozen_inputs_unchanged"] is True


def test_rd13_every_configuration_completed_deterministically() -> None:
    report = json.loads(
        Path("data/research/rd13/rd13-final-report-v1.json").read_text(encoding="utf-8")
    )
    assert report["executed_variants"] == [variant.variant_id for variant in VARIANTS]
    assert report["deterministic_replay_pass"] is True
    assert report["no_lookahead_pass"] is True
    assert report["reconciliation_pass"] is True


def test_rd13_all_run_validation_reports_pass() -> None:
    reports = sorted(Path("data/research/rd13/long-history").rglob("validation-report.json"))
    assert len(reports) == 48
    for path in reports:
        validation = json.loads(path.read_text(encoding="utf-8"))
        assert validation["status"] == "PASS"
        assert validation["no_lookahead"] is True
        assert validation["next_bar_execution"] is True
        assert validation["negative_cash_observed"] is False


def test_rd13_output_reduction_contract() -> None:
    root = Path("data/research/rd13/long-history")
    for variant in VARIANTS:
        path = root / variant.variant_id
        if variant.variant_id in FULL_VARIANTS:
            assert (path / "portfolio" / "signals.csv").exists()
            assert (path / "portfolio" / "cash-ledger.csv").exists()
        else:
            assert (path / "output-hashes.json").exists()
            assert not (path / "portfolio" / "signals.csv").exists()
            assert (path / "portfolio" / "trades.csv").exists()


def test_rd13_variant_diffs_change_only_declared_flags() -> None:
    report = json.loads(
        Path("data/research/rd13/rd13-variant-registry-validation-v1.json").read_text(
            encoding="utf-8"
        )
    )
    assert set(report) == {variant.variant_id for variant in VARIANTS}
    assert all(row["all_other_flags_unchanged"] for row in report.values())
    assert all(
        row["observed_changed_fields"] == sorted(row["declared_changes"]) for row in report.values()
    )


def test_rd13_inventory_and_acquisition_are_locked_safe() -> None:
    inventory = pd.read_csv("data/research/rd13/rd13-local-data-inventory-v1.csv")
    assert len(inventory) == 10
    assert set(inventory["contains_2025"].astype(str).str.lower()) == {"false"}
    assert set(inventory["contains_2026"].astype(str).str.lower()) == {"false"}
    manifest = json.loads(
        Path("data/research/rd13/rd13-acquisition-manifest-v1.json").read_text(encoding="utf-8")
    )
    assert manifest["batch_count"] == 1
    assert manifest["authentication_used"] is False
    assert manifest["test_2025_accessed"] is False
    assert manifest["holdout_2026_accessed"] is False


def test_rd13_bootstrap_is_complete_and_deterministic() -> None:
    frame = pd.read_csv("data/research/rd13/rd13-bootstrap-summary-v1.csv")
    assert len(frame) == 12
    assert set(frame["seed"]) == {BOOTSTRAP_SEED}
    assert set(frame["resamples"]) == {BOOTSTRAP_RESAMPLES}


def test_rd13_no_optimizer_or_winner_selection() -> None:
    report = json.loads(
        Path("data/research/rd13/rd13-final-report-v1.json").read_text(encoding="utf-8")
    )
    assert report["optimization_performed"] is False
    assert report["winner_selected"] is False
    assert report["dune_api_called"] is False
