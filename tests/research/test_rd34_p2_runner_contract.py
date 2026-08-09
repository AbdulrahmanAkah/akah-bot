from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
RUNNER_PATH = ROOT / "scripts/research/run_rd34_dual_family_persistence_diagnostic.py"


def load_runner() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "_rd34_p2_runner_contract",
        RUNNER_PATH,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_runner_freezes_non_economic_diagnostic_contract() -> None:
    runner = load_runner()
    assert runner.P1_FREEZE_COMMIT == ("9b1db409e10aa505c4402485d01d008a1553d62a")
    assert runner.ADMISSION_PORTFOLIO == "UNION_FOCUS"
    assert Path("data/research/rd34_p3_runtime") == runner.OUTPUT
    assert runner.FAMILIES == (
        runner.FAMILY_MOMENTUM_BREAKOUT,
        runner.FAMILY_RELATIVE_STRENGTH_ROTATION,
    )
    assert len(runner.ALL_RULES) == 4
    assert runner.QUALIFICATION_GATES == (
        "EVENT_COUNT_GTE_20",
        "NET_72H_MEAN_GT_0",
        "NET_72H_MEDIAN_GT_0",
        "NET_168H_MEAN_GT_0",
    )


def test_period_id_is_sealed_to_2022_2023() -> None:
    runner = load_runner()
    assert runner.period_id_for(pd.Timestamp("2022-06-01T00:00:00Z")) == "ROBUSTNESS_2022"
    assert runner.period_id_for(pd.Timestamp("2023-06-01T00:00:00Z")) == "ROBUSTNESS_2023"
    with pytest.raises(
        runner.RunnerError,
        match="outside 2022-2023",
    ):
        runner.period_id_for(pd.Timestamp("2024-01-01T00:00:00Z"))


def test_admitted_union_keys_require_unique_union_path() -> None:
    runner = load_runner()
    frame = pd.DataFrame(
        [
            {
                "policy_id": runner.ADMISSION_POLICY,
                "portfolio_id": runner.ADMISSION_PORTFOLIO,
                "universe_id": "C2",
                "signal_time": "2022-01-01T00:00:00Z",
                "pair": "AAA-USDT",
                "admission_outcome": "ADMIT",
            },
            {
                "policy_id": runner.ADMISSION_POLICY,
                "portfolio_id": runner.ADMISSION_PORTFOLIO,
                "universe_id": "C2",
                "signal_time": "2022-01-01T00:00:00Z",
                "pair": "AAA-USDT",
                "admission_outcome": "SUPPRESS",
            },
        ]
    )
    with pytest.raises(
        runner.RunnerError,
        match="not unique",
    ):
        runner.admitted_union_keys(frame)


def test_build_admitted_origins_maps_overlap_to_each_family() -> None:
    runner = load_runner()
    admission = pd.DataFrame(
        [
            {
                "policy_id": runner.ADMISSION_POLICY,
                "portfolio_id": runner.ADMISSION_PORTFOLIO,
                "universe_id": "C2",
                "signal_time": "2022-01-01T00:00:00Z",
                "pair": "AAA-USDT",
                "admission_outcome": "ADMIT",
            }
        ]
    )
    events = pd.DataFrame(
        [
            {
                "family_id": runner.FAMILY_MOMENTUM_BREAKOUT,
                "universe_id": "C2",
                "timestamp": "2022-01-01T00:00:00Z",
                "pair": "AAA-USDT",
                "membership_rank": 1,
                "aux_value": 100.0,
            },
            {
                "family_id": (runner.FAMILY_RELATIVE_STRENGTH_ROTATION),
                "universe_id": "C2",
                "timestamp": "2022-01-01T00:00:00Z",
                "pair": "AAA-USDT",
                "membership_rank": 1,
                "aux_value": None,
            },
        ]
    )
    origins = runner.build_admitted_origins(
        events,
        admission,
    )
    assert len(origins) == 2
    assert set(origins["family_id"]) == set(runner.FAMILIES)
    assert set(origins["period_id"]) == {"ROBUSTNESS_2022"}


def test_non_admitted_origin_is_removed_before_rules() -> None:
    runner = load_runner()
    admission = pd.DataFrame(
        [
            {
                "policy_id": runner.ADMISSION_POLICY,
                "portfolio_id": runner.ADMISSION_PORTFOLIO,
                "universe_id": "C2",
                "signal_time": "2022-01-01T00:00:00Z",
                "pair": "AAA-USDT",
                "admission_outcome": "ADMIT",
            }
        ]
    )
    events = pd.DataFrame(
        [
            {
                "family_id": runner.FAMILY_MOMENTUM_BREAKOUT,
                "universe_id": "C2",
                "timestamp": "2022-01-01T00:00:00Z",
                "pair": "AAA-USDT",
                "membership_rank": 1,
                "aux_value": 100.0,
            },
            {
                "family_id": runner.FAMILY_MOMENTUM_BREAKOUT,
                "universe_id": "C2",
                "timestamp": "2022-01-02T00:00:00Z",
                "pair": "BBB-USDT",
                "membership_rank": 2,
                "aux_value": 50.0,
            },
        ]
    )
    origins = runner.build_admitted_origins(
        events,
        admission,
    )
    assert len(origins) == 1
    assert origins.iloc[0]["pair"] == "AAA-USDT"


def test_runner_source_requires_explicit_execute() -> None:
    source = RUNNER_PATH.read_text(encoding="utf-8")
    assert "if not args.execute:" in source
    assert "diagnostic execution requires explicit --execute" in source
    assert "replay_rd31_policy(" not in source
    assert "replay_rd33_policy(" not in source
    assert "portfolio_economics_executed" in source


def test_output_registry_is_diagnostic_only() -> None:
    runner = load_runner()
    assert runner.OUTPUT_NAMES == (
        "input-and-conformance-audit.json",
        "admitted-origin-ledger.csv",
        "persistence-outcome-ledger.csv",
        "markout-ledger.csv",
        "markout-summary.csv",
        "qualification-evaluation.csv",
        "family-rule-selection.csv",
        "selected-dual-family-rules-freeze.json",
        "rd34-p3-dual-family-persistence-diagnostic-report-v1.json",
    )
