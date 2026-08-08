from __future__ import annotations

import ast
import inspect

import pandas as pd
import pytest

from spotbot.research import rd32_mb_signal_quality_replay as replay
from spotbot.research.rd26_exit_architecture import (
    FAMILY_MOMENTUM_BREAKOUT,
)
from spotbot.research.rd32_mb_signal_quality_admission import (
    MB_BREADTH_ACCELERATION_CONFIRMATION,
    MB_CROSS_SECTIONAL_BREAKOUT_LEADER,
    MB_RELATIVE_STRENGTH_LEADER_CONFIRMATION,
    RD31_REGIME_HYSTERESIS_CONTROL,
)

MB = FAMILY_MOMENTUM_BREAKOUT


def _raw_events() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "universe_id": "C2",
                "timestamp": "2022-01-01T00:00:00Z",
                "family_id": MB,
                "pair": "AAA-USDT",
                "candidate_rank": 1,
            },
            {
                "universe_id": "C2",
                "timestamp": "2022-01-01T00:00:00Z",
                "family_id": MB,
                "pair": "BBB-USDT",
                "candidate_rank": 2,
            },
            {
                "universe_id": "D2",
                "timestamp": "2022-01-01T00:00:00Z",
                "family_id": MB,
                "pair": "CCC-USDT",
                "candidate_rank": 1,
            },
        ]
    )


def test_contract_is_pre_economic() -> None:
    contract = replay.contract_summary()
    assert contract["economic_runner_implemented"] is False
    assert contract["economic_execution_performed"] is False
    assert contract["real_market_data_loader_present"] is False
    assert contract["raw_market_data_loaded"] is False
    assert contract["candidate_results_observed"] is False
    assert contract["2024_accessed"] is False
    assert contract["post_2024_accessed"] is False
    assert contract["production_authorized"] is False


def test_contract_control_is_exact_rd31_delegate() -> None:
    contract = replay.contract_summary()
    assert contract["control_delegate"] == (
        "EXACT_RD31_REGIME_HYSTERESIS_ADMISSION_GOVERNOR_REPLAY"
    )
    assert contract["rd31_governor_runs_once_before_mb_veto"] is True
    assert contract["governor_transition_recomputed_after_veto"] is False


def test_contract_freezes_exact_raw_candidate_rank_source() -> None:
    contract = replay.contract_summary()
    assert contract["raw_focus_signal_source_required"] is True
    assert contract["breakout_leader_rank_source"] == ("EXACT_RD26_RAW_FOCUS_EVENT_CANDIDATE_RANK")
    assert contract["union_event_candidate_rank_reconstruction"] is False


def test_contract_freezes_causal_breadth_cutoffs() -> None:
    contract = replay.contract_summary()
    assert contract["breadth_current_cutoff"] == ("SIGNAL_BAR_CLOSE_VIA_EXACT_RD31_ENTRY_CONTEXT")
    assert contract["breadth_prior_cutoff"] == (
        "SIGNAL_TIME_MINUS_1H_COMPLETED_CLOSE_VIA_CAUSAL_CONTEXT"
    )
    assert contract["breadth_prior_unavailable_fail_closed"] is True


def test_contract_freezes_rs_leader_context_source() -> None:
    assert replay.contract_summary()["rs_leader_current_context_source"] == (
        "EXACT_RD31_ENTRY_CONTEXT_MEMBERS_AND_RETURN72"
    )


def test_contract_freezes_lifecycle_and_no_changes() -> None:
    contract = replay.contract_summary()
    assert contract["lifecycle"] == ("EXACT_RD31_TIME_FAIL72_MAX168_NO_PROFIT_NO_REPLACEMENT")
    for key in (
        "parameter_grid_search",
        "calendar_year_feature",
        "pair_blacklist",
        "exit_change",
        "sizing_change",
        "cost_change",
        "replacement",
        "profit_giveback",
        "thesis_failure_exit",
        "forced_regime_exit",
    ):
        assert contract[key] is False


def test_raw_rank_lookup_exact() -> None:
    lookup = replay.build_mb_candidate_rank_lookup(
        _raw_events(),
        universe_id="C2",
    )
    timestamp = pd.Timestamp("2022-01-01T00:00:00Z")
    assert lookup[(int(timestamp.value), "AAA-USDT")] == 1
    assert lookup[(int(timestamp.value), "BBB-USDT")] == 2
    assert len(lookup) == 2


def test_raw_rank_lookup_scopes_universe() -> None:
    lookup = replay.build_mb_candidate_rank_lookup(
        _raw_events(),
        universe_id="D2",
    )
    timestamp = pd.Timestamp("2022-01-01T00:00:00Z")
    assert lookup == {(int(timestamp.value), "CCC-USDT"): 1}


def test_raw_rank_missing_columns_fails() -> None:
    with pytest.raises(replay.RD32ReplayError, match="missing columns"):
        replay.build_mb_candidate_rank_lookup(
            _raw_events().drop(columns=["candidate_rank"]),
            universe_id="C2",
        )


def test_raw_rank_nonpositive_fails() -> None:
    frame = _raw_events()
    frame.loc[0, "candidate_rank"] = 0
    with pytest.raises(replay.RD32ReplayError, match="must be positive"):
        replay.build_mb_candidate_rank_lookup(
            frame,
            universe_id="C2",
        )


def test_raw_rank_duplicate_pair_time_family_fails() -> None:
    frame = pd.concat(
        [_raw_events(), _raw_events().iloc[[0]]],
        ignore_index=True,
    )
    with pytest.raises(
        replay.RD32ReplayError,
        match="duplicate pair-time-family",
    ):
        replay.build_mb_candidate_rank_lookup(
            frame,
            universe_id="C2",
        )


def test_breakout_quality_evidence_uses_frozen_rank() -> None:
    timestamp = pd.Timestamp("2022-01-01T00:00:00Z")
    evidence = replay.quality_evidence_for_event(
        policy_id=MB_CROSS_SECTIONAL_BREAKOUT_LEADER,
        universe_id="C2",
        pair="BBB-USDT",
        signal_time=timestamp,
        current_members=(),
        current_returns={},
        membership=[],
        frames={},
        lookups={},
        state_lookup={},
        mb_candidate_rank_lookup={(int(timestamp.value), "BBB-USDT"): 2},
    )
    assert evidence is not None
    assert evidence.mb_candidate_rank == 2


def test_breakout_missing_frozen_rank_fails() -> None:
    with pytest.raises(
        replay.RD32ReplayError,
        match="candidate rank missing",
    ):
        replay.quality_evidence_for_event(
            policy_id=MB_CROSS_SECTIONAL_BREAKOUT_LEADER,
            universe_id="C2",
            pair="AAA-USDT",
            signal_time=pd.Timestamp("2022-01-01T00:00:00Z"),
            current_members=(),
            current_returns={},
            membership=[],
            frames={},
            lookups={},
            state_lookup={},
            mb_candidate_rank_lookup={},
        )


def test_rs_leader_quality_evidence_passes_exact_context_maps() -> None:
    members = (("AAA-USDT", 1), ("BBB-USDT", 2))
    returns = {"AAA-USDT": 0.2, "BBB-USDT": 0.1}
    evidence = replay.quality_evidence_for_event(
        policy_id=MB_RELATIVE_STRENGTH_LEADER_CONFIRMATION,
        universe_id="C2",
        pair="AAA-USDT",
        signal_time=pd.Timestamp("2022-01-01T00:00:00Z"),
        current_members=members,
        current_returns=returns,
        membership=[],
        frames={},
        lookups={},
        state_lookup={},
        mb_candidate_rank_lookup={},
    )
    assert evidence is not None
    assert evidence.current_members == members
    assert evidence.current_return_72h_by_pair is returns


def test_control_quality_evidence_is_none() -> None:
    assert (
        replay.quality_evidence_for_event(
            policy_id=RD31_REGIME_HYSTERESIS_CONTROL,
            universe_id="C2",
            pair="AAA-USDT",
            signal_time=pd.Timestamp("2022-01-01T00:00:00Z"),
            current_members=(),
            current_returns={},
            membership=[],
            frames={},
            lookups={},
            state_lookup={},
            mb_candidate_rank_lookup={},
        )
        is None
    )


def test_unknown_quality_policy_fails() -> None:
    with pytest.raises(replay.RD32ReplayError, match="unknown RD32 policy"):
        replay.quality_evidence_for_event(
            policy_id="UNKNOWN",
            universe_id="C2",
            pair="AAA-USDT",
            signal_time=pd.Timestamp("2022-01-01T00:00:00Z"),
            current_members=(),
            current_returns={},
            membership=[],
            frames={},
            lookups={},
            state_lookup={},
            mb_candidate_rank_lookup={},
        )


def test_control_replay_delegates_exact_rd31(monkeypatch) -> None:
    sentinel = (
        pd.DataFrame([{"trade": 1}]),
        pd.DataFrame([{"daily": 1}]),
        {"net_return": 0.123},
        {"admitted_entries": 7},
    )
    observed: dict[str, object] = {}

    def fake_rd31(**kwargs):
        observed.update(kwargs)
        return sentinel

    monkeypatch.setattr(
        replay,
        "replay_rd31_policy",
        fake_rd31,
    )
    result = replay.replay_rd32_policy(
        policy_id=RD31_REGIME_HYSTERESIS_CONTROL,
        portfolio_id="UNION_FOCUS",
        universe_id="C2",
        cost_multiplier=2.0,
        events=pd.DataFrame(),
        raw_focus_events=pd.DataFrame(),
        frames={},
        state_frame=pd.DataFrame(),
        membership=[],
    )
    assert result is sentinel
    assert observed["policy_id"] == ("REGIME_HYSTERESIS_ADMISSION_GOVERNOR")
    assert observed["portfolio_id"] == "UNION_FOCUS"
    assert observed["universe_id"] == "C2"
    assert observed["cost_multiplier"] == 2.0


def test_candidate_replay_rejects_unknown_policy() -> None:
    with pytest.raises(replay.RD32ReplayError, match="unknown policy"):
        replay.replay_rd32_policy(
            policy_id="UNKNOWN",
            portfolio_id="UNION_FOCUS",
            universe_id="C2",
            cost_multiplier=2.0,
            events=pd.DataFrame(),
            raw_focus_events=pd.DataFrame(),
            frames={},
            state_frame=pd.DataFrame(),
            membership=[],
        )


def test_candidate_replay_rejects_unknown_cost() -> None:
    with pytest.raises(
        replay.RD32ReplayError,
        match="unsupported cost multiplier",
    ):
        replay.replay_rd32_policy(
            policy_id=MB_CROSS_SECTIONAL_BREAKOUT_LEADER,
            portfolio_id="UNION_FOCUS",
            universe_id="C2",
            cost_multiplier=3.0,
            events=pd.DataFrame(),
            raw_focus_events=_raw_events(),
            frames={},
            state_frame=pd.DataFrame(),
            membership=[],
        )


def test_candidate_replay_rejects_invalid_window() -> None:
    with pytest.raises(replay.RD32ReplayError, match="invalid replay window"):
        replay.replay_rd32_policy(
            policy_id=MB_CROSS_SECTIONAL_BREAKOUT_LEADER,
            portfolio_id="UNION_FOCUS",
            universe_id="C2",
            cost_multiplier=2.0,
            events=pd.DataFrame(),
            raw_focus_events=_raw_events(),
            frames={},
            state_frame=pd.DataFrame(),
            membership=[],
            replay_start=pd.Timestamp("2023-01-01T00:00:00Z"),
            replay_cutoff=pd.Timestamp("2023-01-01T00:00:00Z"),
        )


def test_source_uses_admissible_families_for_live_position() -> None:
    source = inspect.getsource(replay.replay_rd32_policy)
    assert "admitted_support = tuple(" in source
    assert "admission.admissible_families" in source
    assert "support_families=admitted_support" in source


def test_source_does_not_recompute_governor_after_veto() -> None:
    source = inspect.getsource(replay.replay_rd32_policy)
    parsed = ast.parse(source)

    admission_calls = [
        node
        for node in ast.walk(parsed)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "rd32_admission_decision"
    ]
    assert len(admission_calls) == 1

    matching_assignments = []
    for node in ast.walk(parsed):
        if not isinstance(node, ast.Assign):
            continue
        if not any(
            isinstance(target, ast.Name) and target.id == "governor_state"
            for target in node.targets
        ):
            continue
        value = node.value
        if not (
            isinstance(value, ast.Attribute)
            and value.attr == "governor_next_state"
            and isinstance(value.value, ast.Attribute)
            and value.value.attr == "rd31_control"
            and isinstance(value.value.value, ast.Name)
            and value.value.value.id == "governed"
        ):
            continue
        matching_assignments.append(node)

    assert len(matching_assignments) == 1


def test_source_preserves_exit_before_entry_order() -> None:
    source = inspect.getsource(replay.replay_rd32_policy)
    assert source.index("scheduled_exit = evaluate_scheduled_exit(") < source.index(
        "entries = sorted("
    )


def test_source_uses_no_current_high_or_low_for_entry_decision() -> None:
    contract = replay.contract_summary()
    assert contract["current_bar_high_used_for_entry_decision"] is False
    assert contract["current_bar_low_used_for_entry_decision"] is False


def test_candidate_policy_registry_exact() -> None:
    assert replay.CANDIDATE_POLICIES == (
        MB_CROSS_SECTIONAL_BREAKOUT_LEADER,
        MB_BREADTH_ACCELERATION_CONFIRMATION,
        MB_RELATIVE_STRENGTH_LEADER_CONFIRMATION,
    )
