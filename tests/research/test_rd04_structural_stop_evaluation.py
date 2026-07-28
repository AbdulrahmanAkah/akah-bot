from __future__ import annotations

import importlib
from dataclasses import replace
from pathlib import Path

import pandas as pd
import pytest

from spotbot.research.ams_md01_momentum import (
    MD01FoldResult,
    MD01Reconciliation,
    MD01Trade,
)
from spotbot.research.rd04_structural_stop_evaluation import (
    DECISION_BLOCKED,
    DECISION_CONFIRMED,
    DECISION_COST_FRAGILE,
    DECISION_NOT_CONFIRMED,
    build_decision,
    full_result_equal,
    trade_cvar_10,
)


def make_trade(return_fraction: float) -> MD01Trade:
    return MD01Trade(
        trade_id=f"T-{return_fraction}",
        position_id="P",
        candidate_id="C",
        symbol="BTC",
        entry_time=pd.Timestamp("2022-01-01", tz="UTC"),
        exit_time=pd.Timestamp("2022-01-02", tz="UTC"),
        entry_price=100.0,
        exit_price=100.0 * (1.0 + return_fraction),
        quantity=1.0,
        gross_pnl=100.0 * return_fraction,
        net_pnl=100.0 * return_fraction,
        return_fraction=return_fraction,
        exit_reason="EXIT",
        alignment_tier="FULL",
        holding_hours=24.0,
        mfe=max(return_fraction, 0.0),
        mae=min(return_fraction, 0.0),
        natural_reselection_sequence=0,
        previous_position_id=None,
    )


def empty_result() -> MD01FoldResult:
    reconciliation = MD01Reconciliation(
        "PASS",
        100_000.0,
        0.0,
        0.0,
        0.0,
        {},
        0.0,
        0.0,
        0.0,
        0.0,
    )
    return MD01FoldResult(
        "WF01",
        "PASS",
        100_000.0,
        100_000.0,
        (),
        (),
        (),
        (),
        (),
        {},
        reconciliation,
        0,
    )


def test_trade_cvar_10_uses_worst_tail() -> None:
    trades = [make_trade(value) for value in (-0.5, -0.4, -0.1, 0.2)]
    assert trade_cvar_10(trades) == -0.5


def test_full_result_equal_detects_exact_parity() -> None:
    result = empty_result()
    assert full_result_equal(result, result)


def test_full_result_equal_detects_cash_drift() -> None:
    result = empty_result()
    drifted = replace(result, final_cash=99_999.0)
    assert not full_result_equal(result, drifted)


def metrics(
    *,
    ret: float,
    expectancy: float,
    drawdown: float,
    cvar: float,
    folds: int,
) -> dict[str, float | int]:
    return {
        "compounded_return_delta": ret,
        "expectancy_delta": expectancy,
        "maximum_drawdown_reduction": drawdown,
        "trade_cvar_10_improvement": cvar,
        "improved_folds": folds,
    }


def test_confirmed_decision_requires_all_gates() -> None:
    decision = build_decision(
        data_contract_passed=True,
        control_replay_passed=True,
        base_metrics=metrics(
            ret=0.1,
            expectancy=1.0,
            drawdown=0.1,
            cvar=0.1,
            folds=2,
        ),
        zero_metrics=metrics(
            ret=0.1,
            expectancy=1.0,
            drawdown=0.1,
            cvar=0.1,
            folds=2,
        ),
        stress_metrics=metrics(
            ret=0.0,
            expectancy=1.0,
            drawdown=0.1,
            cvar=0.1,
            folds=2,
        ),
    )
    assert decision["decision"] == DECISION_CONFIRMED


def test_cost_fragile_decision() -> None:
    decision = build_decision(
        data_contract_passed=True,
        control_replay_passed=True,
        base_metrics=metrics(
            ret=0.1,
            expectancy=1.0,
            drawdown=0.1,
            cvar=0.1,
            folds=2,
        ),
        zero_metrics=metrics(
            ret=0.1,
            expectancy=1.0,
            drawdown=0.1,
            cvar=0.1,
            folds=2,
        ),
        stress_metrics=metrics(
            ret=-0.01,
            expectancy=1.0,
            drawdown=0.1,
            cvar=0.1,
            folds=2,
        ),
    )
    assert decision["decision"] == DECISION_COST_FRAGILE


def test_not_confirmed_decision() -> None:
    decision = build_decision(
        data_contract_passed=True,
        control_replay_passed=True,
        base_metrics=metrics(
            ret=-0.1,
            expectancy=1.0,
            drawdown=0.1,
            cvar=0.1,
            folds=2,
        ),
        zero_metrics=metrics(
            ret=0.1,
            expectancy=1.0,
            drawdown=0.1,
            cvar=0.1,
            folds=2,
        ),
        stress_metrics=metrics(
            ret=0.1,
            expectancy=1.0,
            drawdown=0.1,
            cvar=0.1,
            folds=2,
        ),
    )
    assert decision["decision"] == DECISION_NOT_CONFIRMED


def test_blocked_decision() -> None:
    decision = build_decision(
        data_contract_passed=False,
        control_replay_passed=True,
        base_metrics=metrics(
            ret=1.0,
            expectancy=1.0,
            drawdown=1.0,
            cvar=1.0,
            folds=3,
        ),
        zero_metrics=metrics(
            ret=1.0,
            expectancy=1.0,
            drawdown=1.0,
            cvar=1.0,
            folds=3,
        ),
        stress_metrics=metrics(
            ret=1.0,
            expectancy=1.0,
            drawdown=1.0,
            cvar=1.0,
            folds=3,
        ),
    )
    assert decision["decision"] == DECISION_BLOCKED


def test_full_result_equal_is_nan_safe_and_boolean() -> None:
    result = empty_result()
    first = replace(result, final_cash=float("nan"))
    second = replace(result, final_cash=float("nan"))
    observed = full_result_equal(first, second)
    assert isinstance(observed, bool)
    assert observed is True


def test_d1_aggregate_lookup_stringifies_record_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scripts_research = Path(__file__).resolve().parents[2] / "scripts" / "research"
    monkeypatch.syspath_prepend(str(scripts_research))
    d5b2_runner = importlib.import_module("run_rd04_d5b2_structural_stop_evaluation")
    frame = pd.DataFrame(
        [
            {
                "universe_mode": "PIT_UNIVERSE",
                "cost_mode": "BASE_COST",
                7: 3.5,
            }
        ]
    )
    monkeypatch.setattr(d5b2_runner.pd, "read_csv", lambda _: frame)
    observed = d5b2_runner.d1_aggregate_lookup()
    row = observed[("PIT_UNIVERSE", "BASE_COST")]
    assert row["7"] == 3.5
    assert all(isinstance(key, str) for key in row)
