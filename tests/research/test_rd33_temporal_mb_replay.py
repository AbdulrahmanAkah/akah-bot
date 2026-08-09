from __future__ import annotations

import ast
import inspect

import pandas as pd
import pytest

import spotbot.research.rd33_temporal_mb_replay as replay
from spotbot.research.rd26_exit_architecture import (
    FAMILY_MOMENTUM_BREAKOUT,
    FAMILY_RELATIVE_STRENGTH_ROTATION,
)


def minimal_events(*, support: str) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "timestamp": pd.Timestamp("2023-01-01T00:00:00Z"),
                "pair": "AAA-USDT",
                "membership_rank": 1,
                "support_families": support,
                "period_id": "ROBUSTNESS_2023",
                "atr24_at_signal": 2.0,
            }
        ]
    )


def fake_rd31_outputs():
    trades = pd.DataFrame(
        [
            {
                "policy_id": "REGIME_HYSTERESIS_ADMISSION_GOVERNOR",
                "pair": "AAA-USDT",
            }
        ]
    )
    daily = pd.DataFrame(
        [
            {
                "policy_id": "REGIME_HYSTERESIS_ADMISSION_GOVERNOR",
                "equity": 100000.0,
            }
        ]
    )
    metrics = {
        "policy_id": "REGIME_HYSTERESIS_ADMISSION_GOVERNOR",
        "net_return": 0.0,
    }
    counters = {"admitted_entries": 1}
    return trades, daily, metrics, counters


def test_eligible_original_events_use_exact_rd31_control_window() -> None:
    events = minimal_events(support=FAMILY_MOMENTUM_BREAKOUT)
    rows = replay._eligible_original_events(
        events,
        replay_start=pd.Timestamp("2022-01-01T00:00:00Z"),
        replay_cutoff=pd.Timestamp("2024-01-01T00:00:00Z"),
    )
    assert len(rows) == 1
    assert rows[0]["normal_entry_time"] == pd.Timestamp("2023-01-01T01:00:00Z")
    assert rows[0]["control_max_exit_time"] == pd.Timestamp("2023-01-08T01:00:00Z")
    assert rows[0]["event_seq"] == 0


def test_portfolio_has_mb_distinguishes_rs_only() -> None:
    assert replay._portfolio_has_mb(minimal_events(support=FAMILY_MOMENTUM_BREAKOUT))
    assert not replay._portfolio_has_mb(minimal_events(support=FAMILY_RELATIVE_STRENGTH_ROTATION))


def test_output_relabel_changes_namespace_only() -> None:
    trades, daily, metrics, _ = fake_rd31_outputs()
    out_trades, out_daily, out_metrics = replay._relabel_outputs(
        requested_policy_id="MB_ONE_BAR_BREAKOUT_LEVEL_HOLD",
        trades=trades,
        daily=daily,
        metrics=metrics,
    )
    assert set(out_trades["policy_id"]) == {"MB_ONE_BAR_BREAKOUT_LEVEL_HOLD"}
    assert set(out_daily["policy_id"]) == {"MB_ONE_BAR_BREAKOUT_LEVEL_HOLD"}
    assert out_metrics["policy_id"] == "MB_ONE_BAR_BREAKOUT_LEVEL_HOLD"
    assert float(out_daily.iloc[0]["equity"]) == 100000.0


def test_temporal_counter_augmentation_preserves_baseline_values() -> None:
    events = minimal_events(support=FAMILY_RELATIVE_STRENGTH_ROTATION)
    counters = replay._augment_temporal_counters(
        {"admitted_entries": 7, "time_failure_exits": 2},
        events,
    )
    assert counters["admitted_entries"] == 7
    assert counters["time_failure_exits"] == 2
    assert counters["mb_pending_registered"] == 0
    assert counters["signal_events"] == 1


def test_governor_ledger_parity_exact_and_numeric() -> None:
    base = pd.DataFrame(
        [
            {
                "event_seq": 0,
                "universe_id": "C2",
                "pair": "AAA-USDT",
                "signal_time": "2023-01-01 00:00:00+00:00",
                "normal_entry_time": "2023-01-01 01:00:00+00:00",
                "membership_rank": 1,
                "support_families": "MOMENTUM_BREAKOUT",
                "entry_market_state": "RISK_ON",
                "entry_market_context": "SUPPORTIVE",
                "breakout_reference": 100.0,
                "governor_prior_state": "OPEN",
                "governor_next_state": "OPEN",
                "governor_changed": False,
                "transition_reason": "SUPPORTIVE_OPENS_ADMISSIONS",
                "admit_position": True,
                "target_slot_fraction": 0.18,
                "admission_reason": "TEST",
                "admissible_families": "MOMENTUM_BREAKOUT",
            }
        ]
    )
    result = replay.governor_ledger_parity(base, base.copy())
    assert result["passed"] is True
    assert result["row_count"] == 1
    assert result["maximum_numeric_absolute_error"] == 0.0


def test_governor_ledger_parity_rejects_transition_change() -> None:
    base = pd.DataFrame(
        [
            {
                "event_seq": 0,
                "universe_id": "C2",
                "pair": "AAA-USDT",
                "signal_time": "2023-01-01 00:00:00+00:00",
                "normal_entry_time": "2023-01-01 01:00:00+00:00",
                "membership_rank": 1,
                "support_families": "MOMENTUM_BREAKOUT",
                "entry_market_state": "RISK_ON",
                "entry_market_context": "SUPPORTIVE",
                "breakout_reference": 100.0,
                "governor_prior_state": "OPEN",
                "governor_next_state": "OPEN",
                "governor_changed": False,
                "transition_reason": "SUPPORTIVE_OPENS_ADMISSIONS",
                "admit_position": True,
                "target_slot_fraction": 0.18,
                "admission_reason": "TEST",
                "admissible_families": "MOMENTUM_BREAKOUT",
            }
        ]
    )
    changed = base.copy()
    changed.loc[0, "governor_next_state"] = "LOCKED"
    with pytest.raises(replay.RD33ReplayError, match="governor_next_state"):
        replay.governor_ledger_parity(base, changed)


def test_rd31_governor_call_is_owned_only_by_control_ledger_builder() -> None:
    source = inspect.getsource(replay)
    tree = ast.parse(source)
    owners = []
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for child in ast.walk(node):
            if (
                isinstance(child, ast.Call)
                and isinstance(child.func, ast.Name)
                and child.func.id == "rd31_admission_decision"
            ):
                owners.append(node.name)
    assert owners == ["build_control_governor_transition_ledger"]


def test_candidate_replay_source_has_no_second_governor_call() -> None:
    source = inspect.getsource(replay.replay_rd33_policy)
    assert "rd31_admission_decision" not in source
    assert "transition_governor" not in source
    assert "build_control_governor_transition_ledger" in source


def test_rs_only_candidate_delegates_exact_rd31_replay(monkeypatch) -> None:
    events = minimal_events(support=FAMILY_RELATIVE_STRENGTH_ROTATION)
    ledger = pd.DataFrame(
        columns=[
            "event_seq",
            "universe_id",
            "pair",
            "signal_time",
            "normal_entry_time",
        ]
    )

    monkeypatch.setattr(
        replay,
        "build_control_governor_transition_ledger",
        lambda **_kwargs: ([], ledger),
    )
    monkeypatch.setattr(
        replay,
        "replay_rd31_policy",
        lambda **_kwargs: fake_rd31_outputs(),
    )

    trades, daily, metrics, counters, diagnostics = replay.replay_rd33_policy(
        policy_id=replay.MB_ONE_BAR_BREAKOUT_LEVEL_HOLD,
        portfolio_id=FAMILY_RELATIVE_STRENGTH_ROTATION,
        universe_id="C2",
        cost_multiplier=1.0,
        events=events,
        frames={},
        state_frame=pd.DataFrame(),
        membership=[],
        replay_start=pd.Timestamp("2022-01-01T00:00:00Z"),
        replay_cutoff=pd.Timestamp("2024-01-01T00:00:00Z"),
    )
    assert set(trades["policy_id"]) == {replay.MB_ONE_BAR_BREAKOUT_LEVEL_HOLD}
    assert set(daily["policy_id"]) == {replay.MB_ONE_BAR_BREAKOUT_LEVEL_HOLD}
    assert metrics["policy_id"] == replay.MB_ONE_BAR_BREAKOUT_LEVEL_HOLD
    assert counters["admitted_entries"] == 1
    assert diagnostics.pending_lifecycle_ledger.empty


def test_control_delegates_exact_rd31_replay(monkeypatch) -> None:
    events = minimal_events(support=FAMILY_MOMENTUM_BREAKOUT)
    ledger = pd.DataFrame()
    monkeypatch.setattr(
        replay,
        "build_control_governor_transition_ledger",
        lambda **_kwargs: ([], ledger),
    )
    monkeypatch.setattr(
        replay,
        "replay_rd31_policy",
        lambda **_kwargs: fake_rd31_outputs(),
    )
    trades, daily, metrics, _, _ = replay.replay_rd33_policy(
        policy_id=replay.RD31_REGIME_HYSTERESIS_CONTROL,
        portfolio_id="UNION_FOCUS",
        universe_id="C2",
        cost_multiplier=1.0,
        events=events,
        frames={},
        state_frame=pd.DataFrame(),
        membership=[],
        replay_start=pd.Timestamp("2022-01-01T00:00:00Z"),
        replay_cutoff=pd.Timestamp("2024-01-01T00:00:00Z"),
    )
    assert set(trades["policy_id"]) == {replay.RD31_REGIME_HYSTERESIS_CONTROL}
    assert set(daily["policy_id"]) == {replay.RD31_REGIME_HYSTERESIS_CONTROL}
    assert metrics["policy_id"] == replay.RD31_REGIME_HYSTERESIS_CONTROL


def test_candidate_entry_intent_support_is_component_specific() -> None:
    assert replay.ENTRY_KIND_RS != replay.ENTRY_KIND_MB
    assert replay.ENTRY_KINDS == (
        replay.ENTRY_KIND_RS,
        replay.ENTRY_KIND_MB,
    )


def test_contract_freezes_governor_rs_and_delayed_entry_semantics() -> None:
    contract = replay.contract_summary()
    assert contract["candidate_confirmation_calls_governor"] is False
    assert contract["candidate_confirmation_can_mutate_governor"] is False
    assert contract["second_governor_transition_on_confirmation"] is False
    assert contract["governor_transition_ledger_emitted"] is True
    assert contract["rs_only_candidate_delegate"] == (
        "EXACT_RD31_HYSTERESIS_REPLAY_POLICY_LABEL_ONLY"
    )
    assert contract["rs_same_open_priority_over_confirmed_mb"] is True
    assert contract["pending_consumes_position_slot"] is False
    assert contract["pending_reserves_cash"] is False
    assert contract["pending_reserves_gross_exposure"] is False
    assert contract["confirmed_mb_entry_fill"] == ("NEXT_1H_OPEN_AFTER_CONFIRMATION")
    assert contract["delayed_mb_exit_lifecycle_anchor"] == ("ACTUAL_DELAYED_ENTRY")
    assert contract["time_failure_hours"] == 72
    assert contract["maximum_hold_hours"] == 168


def test_contract_has_no_economic_execution_or_2024_access() -> None:
    contract = replay.contract_summary()
    assert contract["economic_execution_performed"] is False
    assert contract["real_market_data_loader_present"] is False
    assert contract["raw_market_data_loaded"] is False
    assert contract["candidate_results_observed"] is False
    assert contract["2024_accessed"] is False
    assert contract["post_2024_accessed"] is False
    assert contract["production_authorized"] is False


def test_module_source_has_no_raw_data_loader() -> None:
    source = inspect.getsource(replay)
    prohibited = (
        "read_csv(",
        "read_parquet(",
        "data/raw",
        "--execute",
    )
    assert not [token for token in prohibited if token in source]
