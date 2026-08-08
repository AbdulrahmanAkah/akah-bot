from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
RUNNER_PATH = ROOT / "scripts/research/run_rd30_family_specialist_replacement_aware.py"

spec = importlib.util.spec_from_file_location(
    "rd30_runner_contract_target",
    RUNNER_PATH,
)
assert spec is not None
assert spec.loader is not None
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def metric_rows(policy_id: str) -> pd.DataFrame:
    rows = []
    for universe in ("C2", "D2", "E2"):
        for cost in (1.0, 2.0):
            rows.append(
                {
                    "policy_id": policy_id,
                    "portfolio_id": runner.FAMILY_MOMENTUM_BREAKOUT,
                    "universe_id": universe,
                    "cost_multiplier": cost,
                    "trade_count": 100,
                    "final_equity": 110000.0,
                    "net_return": 0.10,
                    "net_pnl": 10000.0,
                    "profit_factor": 1.20,
                    "win_rate": 0.50,
                    "maximum_drawdown": 0.10,
                    "turnover": 3.0,
                    "mean_holding_hours": 48.0,
                    "minimum_cash": 1000.0,
                }
            )
    return pd.DataFrame(rows)


def test_policy_registry_matches_preregistration():
    assert runner.POLICIES == (
        runner.ROUTER_TIME_FAIL_72_CONTROL,
        runner.FAMILY_QUALITY_CONTROL_EXITS,
        runner.FAMILY_QUALITY_REPLACEMENT_AWARE_RS,
        runner.FULL_FAMILY_SPECIALIST_REPLACEMENT_BRAIN,
    )


def test_hard_gate_registry_has_exact_14_gates():
    assert len(runner.HARD_GATES) == 14
    assert runner.HARD_GATES[-1] == "NO_2024_OR_POST_2024_ACCESS"


def test_output_contract_includes_replacement_diagnostics():
    assert "replacement-diagnostics.csv" in runner.OUTPUT_NAMES
    assert "rd30-p1-family-specialist-replacement-aware-report-v1.json" in runner.OUTPUT_NAMES
    assert len(runner.OUTPUT_NAMES) == 15


def test_mb_parity_registry_targets_only_control_lifecycle_candidates():
    assert runner.MB_PARITY_POLICIES == (
        runner.FAMILY_QUALITY_CONTROL_EXITS,
        runner.FAMILY_QUALITY_REPLACEMENT_AWARE_RS,
    )
    assert runner.MB_PARITY_EXPECTED_ROWS == 12


def test_mb_control_lifecycle_parity_passes_identical_metrics():
    control = metric_rows(runner.ROUTER_TIME_FAIL_72_CONTROL)
    family = metric_rows(runner.FAMILY_QUALITY_CONTROL_EXITS)
    replacement = metric_rows(runner.FAMILY_QUALITY_REPLACEMENT_AWARE_RS)
    frame = pd.concat(
        [control, family, replacement],
        ignore_index=True,
    )
    result = runner.verify_mb_control_lifecycle_parity(frame)
    assert result["passed"] is True
    assert result["row_count"] == 12
    assert result["maximum_numeric_absolute_error"] == pytest.approx(0.0)


def test_mb_control_lifecycle_parity_rejects_drift():
    control = metric_rows(runner.ROUTER_TIME_FAIL_72_CONTROL)
    family = metric_rows(runner.FAMILY_QUALITY_CONTROL_EXITS)
    replacement = metric_rows(runner.FAMILY_QUALITY_REPLACEMENT_AWARE_RS)
    family.loc[0, "net_return"] = 0.09
    frame = pd.concat(
        [control, family, replacement],
        ignore_index=True,
    )
    with pytest.raises(runner.RunnerError):
        runner.verify_mb_control_lifecycle_parity(frame)


def test_replacement_diagnostics_fills_control_missing_counters_with_zero():
    routing = pd.DataFrame(
        [
            {
                "policy_id": runner.ROUTER_TIME_FAIL_72_CONTROL,
                "portfolio_id": "UNION_FOCUS",
                "universe_id": "C2",
                "cost_multiplier": 1.0,
            }
        ]
    )
    result = runner.replacement_diagnostics(routing)
    for column in runner.REPLACEMENT_COUNTERS:
        assert int(result.iloc[0][column]) == 0


def test_parser_requires_exactly_one_mode_at_runtime_not_parse_time():
    parsed = runner.parser().parse_args(["--repo-root", str(ROOT), "--execute"])
    assert parsed.execute is True
    assert parsed.validate_only is False


def test_decision_strings_keep_2024_sealed_until_selection():
    source = RUNNER_PATH.read_text(encoding="utf-8")
    assert "RD31_CLEAN_2024_INTERNAL_CONFIRMATION" in source
    assert "RD31_REPLACEMENT_AWARE_OR_SIGNAL_FAMILY_MODEL_REDESIGN_REQUIRED" in source
    assert '"2024_accessed": False' in source


def test_runner_has_no_post_result_parameter_mutation_flag():
    source = RUNNER_PATH.read_text(encoding="utf-8")
    assert "candidate_parameters_changed_after_economic_execution" in source
    assert "research_logic_changed_after_economic_execution" in source
