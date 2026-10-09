from __future__ import annotations

import json
from dataclasses import replace
from decimal import Decimal

import pandas as pd
import pytest

from spotbot.research.multi_school_fidelity import akah_thesis_engine_foundation_v1 as f
from spotbot.research.multi_school_fidelity.bound_hybrid import BoundHybrid
from spotbot.research.multi_school_fidelity.event_execution_bridge import (
    CompletedBar,
    EventExecutionBridge,
    QuantityRule,
)
from spotbot.research.multi_school_fidelity.evidence_selector import EvidenceStore
from spotbot.research.multi_school_fidelity.operational_ai_review import locked_ai
from spotbot.research.multi_school_fidelity.portfolio_kernel import PortfolioKernel
from spotbot.research.multi_school_fidelity.review_validation import ROLES, validate_locked

T = pd.Timestamp("2022-05-03T14:00:00Z")


def test_ai_override_preserves_identity_and_does_not_bypass_original_protocol(tmp_path):
    doc = {
        "protocol_id": "AKAH_GATE2_AI_DIAGNOSTIC_REVIEW_V1",
        "reviewer_id": "CODEX_AI_DIAGNOSTIC",
        "reviewer_type": "AI_ASSISTANT",
        "locked": True,
        "locked_at": "2026-10-02T12:00:00Z",
        "corpus_sha256": "sha",
        "responses": [
            {
                "case_id": "c",
                "reviewer_id": "CODEX_AI_DIAGNOSTIC",
                "human_action": "ACCEPT",
                "differences": [],
                **dict.fromkeys(ROLES, "fixture"),
            }
        ],
    }
    path = tmp_path / "ai.json"
    path.write_text(json.dumps(doc))
    assert locked_ai(path, "proxy", {"c"}, "sha")["human_attestation"] is False
    with pytest.raises(ValueError, match="REVIEWER_ID_NOT_BOUND"):
        validate_locked(path, "USER_MANUAL_TRADER", {"c"}, "sha")
    doc["distinct_human_attestation"] = True
    path.write_text(json.dumps(doc))
    with pytest.raises(ValueError, match="FALSE_HUMAN"):
        locked_ai(path, "proxy", {"c"}, "sha")


def test_bound_hybrid_rechecks_all_roles_and_absorbing_context_invalidation():
    store = EvidenceStore()
    for name in ("context", "trigger"):
        store.register(
            f.EvidenceRecord(
                name, name.upper(), "s", T, T, "fixture", valid_until=T + pd.Timedelta(hours=2)
            )
        )
    h = BoundHybrid("H1", "s", ("CONTEXT", "TRIGGER"), store, "fixture")
    assert h.observe("CONTEXT", "context", T) == "AWAIT_NEXT_ROLE"
    store.terminate("context", f.EvidenceStatus.INVALIDATED)
    assert h.observe("TRIGGER", "trigger", T + pd.Timedelta(hours=1)) == "INVALIDATED"
    assert not h.ready(T)
    with pytest.raises(ValueError, match="RESURRECTION"):
        h.observe("TRIGGER", "trigger", T)


def rule():
    return QuantityRule(
        "X",
        T,
        T,
        T + pd.Timedelta(days=3),
        Decimal("0.1"),
        Decimal("0.1"),
        Decimal("1"),
        "fixture",
        "SYNTHETIC_FIXTURE",
    )


def bridge():
    row = {
        "pair": "X",
        "identity": "i",
        "target": 120.0,
        "owner_structure_id": "s",
        "owner_grammar": "FS_CLASSICAL_FULL_LONG",
    }
    p = {1: {"episode": row, "current_stop": 90.0, "qty_current": 1.0, "campaign_id": "c"}}
    return EventExecutionBridge(
        PortfolioKernel(99900.0, p, {}, 0.00125),
        EvidenceStore(),
        {"X": rule()},
        synthetic_fixture=True,
    )


def test_quantity_authority_clocks_and_floor_not_current_metadata():
    r = rule()
    assert r.normalize("X", 1.23, 100, T) == 1.2
    assert replace(r, available_at=T + pd.Timedelta(hours=1)).normalize("X", 1, 100, T) == 0
    assert r.normalize("X", 1, 100, T + pd.Timedelta(days=4)) == 0
    assert r.normalize("OTHER", 1, 100, T) == 0


def test_event_bridge_gap_executes_open_not_stop_and_never_arms_market():
    b = bridge()
    b.on_open(T, {"X": 80.0}, {"X": 1000.0})
    assert not b.kernel.positions and b.trace[-1]["price"] == 80
    with pytest.raises(PermissionError, match="NOT_ARMED"):
        EventExecutionBridge(b.kernel, b.evidence, b.rules, synthetic_fixture=False)


def test_stop_target_collision_stop_first_and_missing_capacity_not_fake_fill():
    b = bridge()
    b.on_open(T, {"X": 100.0}, {"X": 1000.0})
    bar = CompletedBar("X", T, T + pd.Timedelta(hours=1), 100, 130, 80, 110)
    b.on_close(
        T + pd.Timedelta(hours=1), {"X": bar}, {"i": {"known_at": T, "exit_capacity": 1000.0}}
    )
    assert b.trace[-1]["reason"] == "STRUCTURAL_STOP" and b.trace[-1]["price"] == 90
    b = bridge()
    b.on_open(T, {"X": 100.0}, {})
    b.on_close(T + pd.Timedelta(hours=1), {"X": bar}, {})
    assert b.kernel.positions and b.kernel.risk_breach_unresolved


def test_native_close_decision_executes_only_next_open_and_stops_not_retroactive():
    b = bridge()
    b.on_open(T, {"X": 100.0}, {"X": 1000.0})
    close = T + pd.Timedelta(hours=1)
    bar = CompletedBar("X", T, close, 100, 110, 95, 108)
    b.on_close(close, {"X": bar}, {"i": {"known_at": close, "confirmed_primary_down": True}})
    assert b.kernel.positions and b.pending_exit
    b.on_open(close, {"X": 107.0}, {"X": 1000.0})
    assert not b.kernel.positions and b.trace[-1]["price"] == 107


def test_completed_bar_and_event_future_unavailable_and_protected_boundary():
    b = bridge()
    b.on_open(T, {"X": 100.0}, {})
    close = T + pd.Timedelta(hours=1)
    bar = CompletedBar("X", T, close, 100, 110, 95, 108)
    with pytest.raises(ValueError, match="AVAILABILITY"):
        b.on_close(close, {"X": bar}, {"i": {"known_at": close + pd.Timedelta(hours=1)}})
    with pytest.raises(ValueError, match="PROTECTED"):
        b.on_open(pd.Timestamp("2024-01-01T00:00:00Z"), {"X": 100.0}, {})


def test_target_gap_has_source_bound_open_priority_before_later_stop():
    b = bridge()
    b.on_open(T, {"X": 130.0}, {"X": 1000.0})
    assert not b.kernel.positions
    assert b.trace[-1]["reason"] == "TARGET_GAP"
    assert b.trace[-1]["price"] == 120.0


def test_wyckoff_stale_lps_api_risk_and_reaccumulation_context_loss_are_reproduced():
    from spotbot.research.multi_school_fidelity import akah_full_fidelity_runtime_v1 as rt

    w = rt.WyckoffRuntime("X", state="E_MARKUP", context={"lps": {"low": 100}})
    intent = w.entry_intent(
        T + pd.Timedelta(days=30),
        branch="NO_SPRING_LPS",
        market_state="E_MARKUP",
        rs={"eligible": True},
        readiness={"all_fixture_concepts": True},
        entry=95,
        structural_low=80,
        pnf_objective=200,
    )
    # Demonstrates what the API permits, not whether a named real checkpoint violated its LPS.
    assert intent is not None
    w.context.update(sc={"low": 80}, ar={"high": 110}, st={"low": 85}, sc_time=T)
    w.step(T, "HIGHER_LEVEL_RANGE_FORMS", {"low": 105, "high": 120})
    assert w.state == "REACCUMULATION" and "sc_time" not in w.context
    readiness = w.readiness_vector(
        downward_objective_context=True,
        bullish_activity=True,
        downward_stride_broken=True,
        higher_lows=True,
        higher_highs=True,
        relative_strength=True,
        base_formed=True,
        upward_potential_r=5,
    )
    assert readiness["PS_SC_ST"] is False


def test_classical_deep_throwback_permissiveness_is_not_silently_tightened():
    from spotbot.research.multi_school_fidelity import akah_full_fidelity_runtime_v1 as rt

    r = rt.ClassicalRuntime("X")
    r.mature(rt.ClassicalPattern("p", "ASC_TRIANGLE", 100, 90, 10, "UP", T))
    assert r.update_breakout(T, "p", 101, 100, 90)
    intent = r.entry_intent(T + pd.Timedelta(hours=4), "p", 70, 101)
    assert intent is not None and intent.stop == 70
    # This test records the current specification gap; it does not endorse that entry.


def test_common_reduction_cannot_spend_same_asset_capacity_twice():
    from spotbot.research.multi_school_fidelity import akah_native_replay_engine_v1 as e

    positions = {
        i: {"episode": {"pair": "X"}, "qty_current": 800, "current_stop": 90, "campaign_id": "same"}
        for i in (1, 2)
    }
    k = PortfolioKernel(10000, positions, {}, 0.00125)
    lam, _ = e.proportional_risk_reduction_lambda(k.cash, k.positions, lambda *a: 100, T, 0.00125)
    per_leg = (1 - lam) * 800 * 100
    assert not k.reduce_common(lambda *a: 100, T, {"X": per_leg * 1.5}, lambda *a: a[1])
    assert k.cash == 10000 and k.positions[1]["qty_current"] == 800


def test_event_admission_is_graph_bound_and_capacity_spent_once():
    from spotbot.research.multi_school_fidelity.evidence_selector import Feasibility

    store = EvidenceStore()
    store.register(f.EvidenceRecord("e", "TRIGGER", "s", T, T, "fixture"))
    thesis = f.ThesisRecord(
        "i",
        "FS_CLASSICAL_FULL_LONG",
        "s",
        "X",
        T,
        "breakout",
        "stop",
        "native",
        500,
        ("e",),
        0.5,
        funded_ready=True,
    )
    router = f.RouterState(
        f.Direction.UP, f.Direction.UP, f.StructuralPhase.MARKUP, f.Activity.NORMAL
    )
    request = Feasibility(thesis, router, True, True, True, True, True)
    row = {
        "pair": "X",
        "identity": "i",
        "owner_grammar": thesis.owner_grammar,
        "owner_structure_id": "s",
        "stop": 90.0,
        "target": 130.0,
    }
    b = EventExecutionBridge(
        PortfolioKernel(100000, {}, {}, 0.00125), store, {"X": rule()}, synthetic_fixture=True
    )
    assert not b.on_open(T, {"X": 100.0}, {"X": 20000.0}, [(request, row, "c")])
    assert b.kernel.positions and b.kernel.campaigns["c"].committed_risk <= 500


def test_future_parent_and_duplicate_selector_identity_rejected():
    from spotbot.research.multi_school_fidelity.evidence_selector import (
        Feasibility,
        select_prebatch,
    )

    store = EvidenceStore()
    store.register(f.EvidenceRecord("p", "CONTEXT", "s", T, T + pd.Timedelta(hours=1), "sha"))
    child = f.EvidenceRecord(
        "child",
        "TRIGGER",
        "s",
        T,
        T,
        "sha",
        parent_edges=(f.ParentEdge("p", f.ParentEdgeType.HISTORICAL_PREREQUISITE),),
    )
    with pytest.raises(ValueError, match="BEFORE_PARENT"):
        store.register(child)
    thesis = f.ThesisRecord("dup", "g", "s", "X", T, "entry", "stop", "manage", 500, (), 0.5)
    router = f.RouterState(
        f.Direction.UP, f.Direction.UP, f.StructuralPhase.MARKUP, f.Activity.NORMAL
    )
    candidate = Feasibility(thesis, router, True, True, True, True, True)
    with pytest.raises(ValueError, match="DUPLICATE_THESIS"):
        select_prebatch([candidate, candidate], store, T, {})


def test_source_router_unknown_table_denies_risk_and_higher_veto_has_priority():
    from spotbot.research.multi_school_fidelity.source_router import (
        GrammarPermission,
        SourceBoundRouter,
    )

    state = f.RouterState(
        f.Direction.UP, f.Direction.UP, f.StructuralPhase.MARKUP, f.Activity.NORMAL
    )
    assert not SourceBoundRouter(()).permission("ICT", state)[0]
    permission = GrammarPermission(
        "ICT", frozenset({f.StructuralPhase.MARKUP}), "fixture", True, True
    )
    router = SourceBoundRouter((permission,))
    assert router.permission("ICT", state)[0]
    assert not router.permission("ICT", replace(state, market_direction_1d=f.Direction.DOWN))[0]
    assert not router.permission(
        "ICT", replace(state, structural_phase_4h=f.StructuralPhase.BASE_CANDIDATE)
    )[0]
