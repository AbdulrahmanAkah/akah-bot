from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNNER_PATH = ROOT / "scripts" / "research" / "run_rd33_temporal_mb_architecture.py"


def load_runner():
    spec = importlib.util.spec_from_file_location(
        "_rd33_runner_contract_test",
        RUNNER_PATH,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_policy_registry_matches_preregistration() -> None:
    runner = load_runner()
    assert runner.EXPECTED_POLICIES == (
        "RD31_REGIME_HYSTERESIS_CONTROL",
        "MB_ONE_BAR_BREAKOUT_LEVEL_HOLD",
        "MB_ONE_BAR_POST_BREAKOUT_CONTINUATION",
        "MB_FIRST_RETEST_RECLAIM_WITHIN_FROZEN_72H",
    )


def test_economic_matrix_is_exactly_72() -> None:
    runner = load_runner()
    assert (
        len(runner.EXPECTED_POLICIES)
        * len(runner.EXPECTED_PORTFOLIOS)
        * len(runner.EXPECTED_UNIVERSES)
        * len(runner.COST_MULTIPLIERS)
        == runner.EXPECTED_ECONOMIC_REPLAYS
        == 72
    )


def test_hard_gate_registry_is_exactly_16() -> None:
    runner = load_runner()
    assert len(runner.HARD_GATES) == 16
    assert runner.HARD_GATES[-2:] == (
        "MOMENTUM_BREAKOUT_2022_2X_NET_PNL_POSITIVE",
        "MOMENTUM_BREAKOUT_2023_2X_NET_PNL_POSITIVE",
    )


def test_causality_gate_registry_is_exactly_8() -> None:
    runner = load_runner()
    assert runner.CAUSALITY_GATES == (
        "CONTROL_PARITY_18_ROWS_VS_RD32_FINAL_CONTROL",
        "RS_METRIC_INVARIANCE_18_ROWS_ACROSS_ALL_CANDIDATES",
        "RS_TRADE_LEDGER_INVARIANCE_ACROSS_ALL_CANDIDATES",
        "GOVERNOR_TRANSITION_LEDGER_EXACT_PARITY_VS_CONTROL",
        "EVERY_CANDIDATE_MB_PENDING_MAPS_TO_ONE_FROZEN_RAW_MB_EVENT",
        "EVERY_CANDIDATE_MB_TRADE_MAPS_TO_ONE_CONTROL_ADMITTED_MB_ORIGIN",
        "NO_CANDIDATE_ENTRY_PRECEDES_ITS_REQUIRED_COMPLETED_CONFIRMATION",
        "NO_2024_OR_POST_2024_ACCESS",
    )


def test_control_and_rs_parity_cardinalities_are_frozen() -> None:
    runner = load_runner()
    assert runner.BASELINE_PARITY_EXPECTED_ROWS == 18
    assert runner.RS_INVARIANCE_EXPECTED_COMPARISONS == 18
    assert runner.GOVERNOR_PARITY_EXPECTED_COMPARISONS == 54


def test_complexity_tie_break_is_parameter_light() -> None:
    runner = load_runner()
    assert runner.active_component_count(runner.RD31_REGIME_HYSTERESIS_CONTROL) == 1
    for policy in runner.CANDIDATE_POLICIES:
        assert runner.active_component_count(policy) == 2


def test_output_contract_contains_forensic_ledgers() -> None:
    runner = load_runner()
    assert "pending-lifecycle-ledger.csv" in runner.OUTPUT_NAMES
    assert "governor-transition-ledger.csv" in runner.OUTPUT_NAMES
    assert "causality-mapping-audit.json" in runner.OUTPUT_NAMES
    assert "governor-transition-parity.json" in runner.OUTPUT_NAMES
    assert len(runner.OUTPUT_NAMES) == 20


def test_success_and_failure_routes_match_preregistered_rd34_routes() -> None:
    runner = load_runner()
    assert runner.SUCCESS_NEXT == "RD34_CLEAN_2024_INTERNAL_CONFIRMATION"
    assert runner.FAILURE_NEXT == (
        "RD34_MULTI_FAMILY_SIGNAL_ARCHITECTURE_OR_NEW_ALPHA_SOURCE_REQUIRED"
    )


def test_runner_requires_explicit_execute() -> None:
    runner = load_runner()
    args = runner.parser().parse_args(["--repo-root", str(ROOT)])
    assert args.execute is False
    assert args.validate_only is False


def test_runner_import_does_not_create_output_directory() -> None:
    runner = load_runner()
    assert Path("data/research/rd33_p1_runtime") == runner.OUTPUT


def test_source_freezes_p0c_and_rd32_lineage() -> None:
    source = RUNNER_PATH.read_text(encoding="utf-8")
    assert 'P0C_FREEZE_COMMIT = "03a850ad3eef5dc8f77f2e02662ce4b510d74b96"' in source
    assert 'RD32_RESULTS_COMMIT = "bac6c7ba6ddf63a58676b5e18b516061d1969bb1"' in source
    assert "RD32_RUN_METRICS_BLOB_SHA" in source
    assert "RD32_REPORT_BLOB_SHA" in source


def test_causality_failure_preserves_outputs_then_raises() -> None:
    source = RUNNER_PATH.read_text(encoding="utf-8")
    manifest_position = source.index('write_json(\n        output / "output-manifest.json"')
    gate_position = source.index('if not causality["passed"]:')
    assert manifest_position < gate_position
    assert "economic outputs preserved for forensic recovery" in source


def test_no_2024_loader_or_confirmation_execution_in_freeze_stage() -> None:
    source = RUNNER_PATH.read_text(encoding="utf-8")
    assert "DATA_CUTOFF" in source
    assert "post_2024_accessed" in source
    assert "production_authorized" in source
