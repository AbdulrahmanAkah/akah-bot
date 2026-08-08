from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "scripts/research/run_rd32_mb_signal_quality_admission.py"


def _load():
    spec = importlib.util.spec_from_file_location(
        "_rd32_runner_test",
        RUNNER,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _metric(
    *,
    net_return: float = 0.10,
    pf: float = 1.20,
    dd: float = 0.10,
    trades: int = 100,
    cash: float = 1000.0,
) -> pd.Series:
    return pd.Series(
        {
            "net_return": net_return,
            "profit_factor": pf,
            "maximum_drawdown": dd,
            "trade_count": trades,
            "minimum_cash": cash,
        }
    )


def _periods(a: float, b: float) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "period_id": "ROBUSTNESS_2022",
                "net_pnl": a,
            },
            {
                "period_id": "ROBUSTNESS_2023",
                "net_pnl": b,
            },
        ]
    )


def _conc() -> pd.Series:
    return pd.Series(
        {
            "net_pnl_without_largest_winner": 10.0,
            "minimum_loao_remaining_net_pnl": 10.0,
            "minimum_loyo_remaining_net_pnl": 10.0,
        }
    )


def _be() -> pd.Series:
    return pd.Series({"pf1_break_even_cost_multiplier": 2.5})


def test_policy_registry_exact() -> None:
    module = _load()
    assert len(module.EXPECTED_POLICIES) == 4
    assert module.EXPECTED_POLICIES[0] == ("RD31_REGIME_HYSTERESIS_CONTROL")


def test_hard_gate_registry_exact_16() -> None:
    module = _load()
    assert len(module.HARD_GATES) == 16
    assert module.HARD_GATES[-2:] == (
        "MOMENTUM_BREAKOUT_2022_2X_NET_PNL_POSITIVE",
        "MOMENTUM_BREAKOUT_2023_2X_NET_PNL_POSITIVE",
    )


def test_economic_matrix_exact_72() -> None:
    module = _load()
    assert module.EXPECTED_ECONOMIC_REPLAYS == 72
    assert (
        len(module.EXPECTED_POLICIES)
        * len(module.EXPECTED_UNIVERSES)
        * len(module.EXPECTED_PORTFOLIOS)
        * len(module.COST_MULTIPLIERS)
        == 72
    )


def test_output_contract_is_frozen() -> None:
    module = _load()
    assert len(module.OUTPUT_NAMES) == 16
    assert Path("data/research/rd32_p3_runtime") == module.OUTPUT


def test_gate_checks_all_pass() -> None:
    module = _load()
    checks = module.gate_checks_for_one(
        base=_metric(),
        stress=_metric(),
        mb=_metric(),
        rs=_metric(),
        union_periods=_periods(1.0, 2.0),
        mb_periods=_periods(3.0, 4.0),
        concentration=_conc(),
        break_even=_be(),
    )
    assert tuple(checks) == module.HARD_GATES
    assert all(checks.values())


def test_mb_2022_gate_fails_independently() -> None:
    module = _load()
    checks = module.gate_checks_for_one(
        base=_metric(),
        stress=_metric(),
        mb=_metric(),
        rs=_metric(),
        union_periods=_periods(1.0, 2.0),
        mb_periods=_periods(-0.01, 4.0),
        concentration=_conc(),
        break_even=_be(),
    )
    assert checks["MOMENTUM_BREAKOUT_2022_2X_NET_PNL_POSITIVE"] is False
    assert checks["MOMENTUM_BREAKOUT_2023_2X_NET_PNL_POSITIVE"] is True


def test_mb_2023_gate_fails_independently() -> None:
    module = _load()
    checks = module.gate_checks_for_one(
        base=_metric(),
        stress=_metric(),
        mb=_metric(),
        rs=_metric(),
        union_periods=_periods(1.0, 2.0),
        mb_periods=_periods(3.0, -0.01),
        concentration=_conc(),
        break_even=_be(),
    )
    assert checks["MOMENTUM_BREAKOUT_2022_2X_NET_PNL_POSITIVE"] is True
    assert checks["MOMENTUM_BREAKOUT_2023_2X_NET_PNL_POSITIVE"] is False


def test_union_year_gate_is_separate_from_mb_year_gate() -> None:
    module = _load()
    checks = module.gate_checks_for_one(
        base=_metric(),
        stress=_metric(),
        mb=_metric(),
        rs=_metric(),
        union_periods=_periods(-1.0, 2.0),
        mb_periods=_periods(3.0, 4.0),
        concentration=_conc(),
        break_even=_be(),
    )
    assert checks["BOTH_2022_2023_NET_PNL_POSITIVE"] is False
    assert checks["MOMENTUM_BREAKOUT_2022_2X_NET_PNL_POSITIVE"] is True


def test_missing_mb_period_fails_closed() -> None:
    module = _load()
    with pytest.raises(
        module.RunnerError,
        match="MB robustness period registry drifted",
    ):
        module.gate_checks_for_one(
            base=_metric(),
            stress=_metric(),
            mb=_metric(),
            rs=_metric(),
            union_periods=_periods(1.0, 2.0),
            mb_periods=_periods(3.0, 4.0).iloc[[0]],
            concentration=_conc(),
            break_even=_be(),
        )


def test_numeric_parity_passes_exact_frames() -> None:
    module = _load()
    frame = pd.DataFrame(
        [
            {"k": "a", "x": 1.0},
            {"k": "b", "x": 2.0},
        ]
    )
    result = module.numeric_parity(
        frozen=frame,
        current=frame.copy(),
        keys=["k"],
        numeric=("x",),
        label="synthetic",
        expected_rows=2,
    )
    assert result["passed"] is True
    assert result["maximum_numeric_absolute_error"] == 0.0


def test_numeric_parity_rejects_drift() -> None:
    module = _load()
    left = pd.DataFrame([{"k": "a", "x": 1.0}])
    right = pd.DataFrame([{"k": "a", "x": 1.1}])
    with pytest.raises(
        module.RunnerError,
        match="numeric mismatch",
    ):
        module.numeric_parity(
            frozen=left,
            current=right,
            keys=["k"],
            numeric=("x",),
            label="synthetic",
            expected_rows=1,
        )


def test_success_and_failure_routes_are_frozen() -> None:
    module = _load()
    assert module.SUCCESS_NEXT == ("RD33_CLEAN_2024_INTERNAL_CONFIRMATION")
    assert module.FAILURE_NEXT == ("RD33_SIGNAL_FAMILY_ARCHITECTURE_REDESIGN_REQUIRED")


def test_runner_import_has_no_economic_execution() -> None:
    module = _load()
    output = ROOT / module.OUTPUT
    # Importing the runner must never create its economic output.
    assert not output.exists()


def test_source_uses_rd32_replay_with_raw_focus_events() -> None:
    source = RUNNER.read_text(encoding="utf-8")
    assert "replay_rd32_policy(" in source
    assert "raw_focus_events=events" in source


def test_control_parity_source_is_rd31_hysteresis() -> None:
    source = RUNNER.read_text(encoding="utf-8")
    assert 'frozen["policy_id"] == "REGIME_HYSTERESIS_ADMISSION_GOVERNOR"' in source
    assert "BASELINE_PARITY_EXPECTED_ROWS = 18" in source


def test_rs_invariance_is_trade_and_metric_level() -> None:
    source = RUNNER.read_text(encoding="utf-8")
    assert "metric_comparisons" in source
    assert "trade_comparisons" in source
    assert "rs_path_changed" in source


def test_no_2024_output_flags() -> None:
    source = RUNNER.read_text(encoding="utf-8")
    assert '"2024_accessed": False' in source
    assert '"post_2024_accessed": False' in source
