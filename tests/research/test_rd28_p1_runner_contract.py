from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd

RUNNER_PATH = Path("scripts/research/run_rd28_evidence_gated_lifecycle.py")


def _load_runner():
    spec = importlib.util.spec_from_file_location(
        "rd28_p1_runner_contract",
        RUNNER_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load RD28 P1 runner")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_control_label_normalization_changes_only_policy_label(monkeypatch) -> None:
    module = _load_runner()

    def fake_replay(**kwargs):
        assert kwargs["policy_id"] == module.ROUTER_TIME_FAIL_72_CONTROL
        trades = pd.DataFrame(
            [
                {
                    "policy_id": module.STATIC_EXIT_STATE_ROUTER,
                    "net_pnl": 12.5,
                }
            ]
        )
        daily = pd.DataFrame(
            [
                {
                    "policy_id": module.STATIC_EXIT_STATE_ROUTER,
                    "equity": 101_000.0,
                }
            ]
        )
        metrics = {
            "policy_id": module.STATIC_EXIT_STATE_ROUTER,
            "net_return": 0.01,
            "trade_count": 1,
        }
        return trades, daily, metrics, {"admitted_entries": 1}

    monkeypatch.setattr(module, "replay_rd28_policy", fake_replay)
    trades, daily, metrics, counters = module.replay_with_rd28_label(
        policy_id=module.ROUTER_TIME_FAIL_72_CONTROL,
        portfolio_id="UNION_FOCUS",
        universe_id="C2",
        cost_multiplier=1.0,
        events=pd.DataFrame(),
        frames={},
        state_frame=pd.DataFrame(),
    )

    assert trades.iloc[0]["net_pnl"] == 12.5
    assert daily.iloc[0]["equity"] == 101_000.0
    assert metrics["net_return"] == 0.01
    assert counters == {"admitted_entries": 1}
    assert set(trades["policy_id"]) == {module.ROUTER_TIME_FAIL_72_CONTROL}
    assert set(daily["policy_id"]) == {module.ROUTER_TIME_FAIL_72_CONTROL}
    assert metrics["policy_id"] == module.ROUTER_TIME_FAIL_72_CONTROL


def test_control_source_policy_is_rd27_static_router() -> None:
    module = _load_runner()
    assert module.CONTROL_SOURCE_POLICY == module.STATIC_EXIT_STATE_ROUTER


def test_rd28_output_set_contains_report_and_selection_freeze() -> None:
    module = _load_runner()
    assert "rd28-p1-evidence-gated-lifecycle-report-v1.json" in module.OUTPUT_NAMES
    assert "selected-lifecycle-policy-freeze.json" in module.OUTPUT_NAMES
    assert len(module.OUTPUT_NAMES) == 14
