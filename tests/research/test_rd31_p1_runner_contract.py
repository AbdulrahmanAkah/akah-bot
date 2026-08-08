from __future__ import annotations

import importlib.util
import math
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
RUNNER_PATH = ROOT / "scripts/research/run_rd31_market_regime_admission_governor.py"

spec = importlib.util.spec_from_file_location(
    "rd31_runner_contract_target",
    RUNNER_PATH,
)
assert spec is not None
assert spec.loader is not None
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def baseline_metric_rows() -> pd.DataFrame:
    rows = []
    for portfolio in runner.EXPECTED_PORTFOLIOS:
        for universe in runner.EXPECTED_UNIVERSES:
            for cost in (1.0, 2.0):
                rows.append(
                    {
                        "policy_id": (runner.FAMILY_QUALITY_CONTROL_EXITS),
                        "portfolio_id": portfolio,
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
    assert tuple(runner.POLICIES) == (
        "FAMILY_QUALITY_CONTROL_EXITS",
        "STRESSED_CONTEXT_MB_EXCLUSION",
        "SUPPORTIVE_ONLY_ALL_FAMILIES",
        "REGIME_HYSTERESIS_ADMISSION_GOVERNOR",
    )


def test_hard_gate_registry_has_exact_14_gates():
    assert len(runner.HARD_GATES) == 14
    assert runner.HARD_GATES[-1] == "NO_2024_OR_POST_2024_ACCESS"


def test_expected_economic_replay_count_is_72():
    assert runner.EXPECTED_ECONOMIC_REPLAYS == 72


def test_baseline_parity_contract_is_18_rows():
    assert runner.BASELINE_PARITY_EXPECTED_ROWS == 18


def test_numeric_parity_passes_identical_baseline():
    frame = baseline_metric_rows()
    result = runner._numeric_parity(
        frozen=frame,
        current=frame.copy(),
        keys=[
            "portfolio_id",
            "universe_id",
            "cost_multiplier",
        ],
        numeric=(
            "trade_count",
            "final_equity",
            "net_return",
            "net_pnl",
            "profit_factor",
            "win_rate",
            "maximum_drawdown",
            "turnover",
            "mean_holding_hours",
            "minimum_cash",
        ),
        label="synthetic",
        expected_rows=18,
    )
    assert result["passed"] is True
    assert result["row_count"] == 18
    assert result["maximum_numeric_absolute_error"] == pytest.approx(0.0)


def test_numeric_parity_rejects_drift():
    left = baseline_metric_rows()
    right = left.copy()
    right.loc[0, "net_return"] = 0.09
    with pytest.raises(runner.RunnerError):
        runner._numeric_parity(
            frozen=left,
            current=right,
            keys=[
                "portfolio_id",
                "universe_id",
                "cost_multiplier",
            ],
            numeric=("net_return",),
            label="synthetic",
            expected_rows=18,
        )


def test_output_contract_contains_extended_diagnostics():
    required = {
        "governor-clock-hour-occupancy.csv",
        "governor-signal-time-occupancy.csv",
        "governor-transition-ledger.csv",
        "admission-attribution.csv",
        "entry-pnl-attribution.csv",
        "regime-deterioration-position-attribution.csv",
        "crisis-window-diagnostics.csv",
        "universe-attribution.csv",
    }
    assert required.issubset(set(runner.OUTPUT_NAMES))
    assert len(runner.OUTPUT_NAMES) == 22


def test_crisis_windows_are_exactly_three_and_diagnostic_only():
    assert len(runner.CRISIS_WINDOWS) == 3
    assert {item["crisis_id"] for item in runner.CRISIS_WINDOWS} == {
        "TERRA_UST_DEPEG",
        "THREE_ARROWS_LIQUIDATION_ORDER",
        "FTX_BANKRUPTCY",
    }
    assert all(item["window_hours_each_side"] == 72 for item in runner.CRISIS_WINDOWS)
    assert all(item["selection_influence"] is False for item in runner.CRISIS_WINDOWS)


def test_research_aspirations_are_not_hard_gates():
    daily = runner.RESEARCH_ASPIRATIONS["daily_0_5pct_compounded_365d"]
    monthly = runner.RESEARCH_ASPIRATIONS["monthly_24pct_compounded_12m"]
    assert daily["hard_gate"] is False
    assert monthly["hard_gate"] is False
    assert math.isclose(
        daily["annual_compounded_net_return"],
        (1.005**365) - 1.0,
    )
    assert math.isclose(
        monthly["annual_compounded_net_return"],
        (1.24**12) - 1.0,
    )


def test_design_principles_freeze_prediction_asymmetry_and_freed_slot_feedback():
    assert "prediction_asymmetry" in (runner.DESIGN_PRINCIPLES)
    assert "freed_slot_feedback" in (runner.DESIGN_PRINCIPLES)
    assert "future_exit_research_requirement" in (runner.DESIGN_PRINCIPLES)


def test_rs_supportive_semantics_conformance_passes():
    result = runner.verify_rs_supportive_semantics()
    assert result["passed"] is True
    assert result["definition_changed_after_rd29_rd30"] is False
    assert len(result["cases"]) == 4


def test_parser_requires_mode_at_runtime_not_parse_time():
    parsed = runner.parser().parse_args(
        [
            "--repo-root",
            str(ROOT),
            "--execute",
        ]
    )
    assert parsed.execute is True
    assert parsed.validate_only is False


def test_decision_strings_keep_2024_sealed_until_selection():
    source = RUNNER_PATH.read_text(encoding="utf-8")
    assert "RD32_CLEAN_2024_INTERNAL_CONFIRMATION" in source
    assert "RD32_REGIME_OR_SIGNAL_FAMILY_ARCHITECTURE_REDESIGN_REQUIRED" in source
    assert '"2024_accessed": False' in source


def test_diagnostics_are_explicitly_nonselective():
    source = RUNNER_PATH.read_text(encoding="utf-8")
    assert "diagnostics_do_not_influence_hard_gates_or_selection" in source
    assert "crisis_windows_are_diagnostic_only" in source
    assert "universe_attribution_is_diagnostic_only" in source


def test_runner_has_no_post_result_parameter_mutation_flag():
    source = RUNNER_PATH.read_text(encoding="utf-8")
    assert "candidate_parameters_changed_after_economic_execution" in source
    assert "research_logic_changed_after_economic_execution" in source
