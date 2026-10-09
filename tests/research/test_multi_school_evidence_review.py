from __future__ import annotations

import json
import zipfile
from dataclasses import replace

import pandas as pd
import pytest

from spotbot.research.multi_school_fidelity import akah_thesis_engine_foundation_v1 as f
from spotbot.research.multi_school_fidelity.evidence_selector import (
    EvidenceStore,
    Feasibility,
    select_prebatch,
)
from spotbot.research.multi_school_fidelity.review_validation import (
    ROLES,
    audit_blinding,
    reconcile,
    validate_locked,
)

T = pd.Timestamp("2022-01-01T00:00:00Z")


def test_evidence_absorbing_identity_and_parent_types():
    store = EvidenceStore()
    parent = f.EvidenceRecord("parent", "CONTEXT", "s", T, T, "sha")
    store.register(parent)
    live = f.EvidenceRecord(
        "live",
        "TRIGGER",
        "s",
        T,
        T,
        "sha",
        parent_edges=(f.ParentEdge("parent", f.ParentEdgeType.LIVE_REQUIREMENT),),
    )
    historical = replace(
        live,
        event_id="history",
        parent_edges=(f.ParentEdge("parent", f.ParentEdgeType.HISTORICAL_PREREQUISITE),),
    )
    store.register(live)
    store.register(historical)
    store.terminate("parent", f.EvidenceStatus.INVALIDATED)
    assert not store.live("live", T)
    assert store.live("history", T)
    with pytest.raises(ValueError, match="DUPLICATE"):
        store.register(parent)
    with pytest.raises(ValueError, match="RESURRECTION"):
        store.terminate("parent", f.EvidenceStatus.ACTIVE)


def candidate(grammar="ICT", identity="id"):
    thesis = f.ThesisRecord(
        identity,
        grammar,
        "structure",
        "BTC-USDT",
        T,
        "entry",
        "invalid",
        "manage",
        500,
        ("e",),
        0.5,
        funded_ready=True,
    )
    router = f.RouterState(
        f.Direction.UP, f.Direction.UP, f.StructuralPhase.MARKUP, f.Activity.NORMAL
    )
    return Feasibility(thesis, router, True, True, True, True, True)


def test_shared_selector_conflict_unknown_normalizer_and_no_displacement():
    store = EvidenceStore()
    store.register(f.EvidenceRecord("e", "TRIGGER", "s", T, T, "sha"))
    a, b = candidate(), candidate("CLASSICAL", "id2")
    accepted, rejected = select_prebatch([a, b], store, T, {})
    assert not accepted and len(rejected) == 2
    assert select_prebatch([replace(a, quantity_authority_bound=False)], store, T, {})[1]
    assert select_prebatch([a], store, T, {"BTC-USDT": "winner"})[1]
    assert select_prebatch([a], store, T, {})[0] == [a.thesis]


def locked(reviewer):
    return {
        "protocol_id": "AKAH_BLIND_TRANSLATION_FIDELITY_V1",
        "reviewer_id": reviewer,
        "corpus_sha256": "sha",
        "locked": True,
        "locked_at": "2026-10-02T00:00:00Z",
        "responses": [
            {
                "case_id": "G2-P-0001",
                "reviewer_id": reviewer,
                "human_action": "ACCEPT",
                "differences": [],
                **dict.fromkeys(ROLES, "synthetic fixture only"),
            }
        ],
    }


def test_review_schema_validation_does_not_impute_answers(tmp_path):
    path = tmp_path / "review.json"
    data = locked("USER_MANUAL_TRADER")
    path.write_text(json.dumps(data))
    proof = validate_locked(path, "USER_MANUAL_TRADER", {"G2-P-0001"}, "sha")
    assert proof["schema_lock_valid"]
    with pytest.raises(ValueError, match="CURRENT_CORPUS"):
        validate_locked(path, "USER_MANUAL_TRADER", {"G2-P-0001"}, "different")
    data["responses"][0]["trigger"] = ""
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="INCOMPLETE"):
        validate_locked(path, "USER_MANUAL_TRADER", {"G2-P-0001"}, "sha")


def test_review_reconciliation_requires_humans_not_majority_vote():
    a, b = locked("USER_MANUAL_TRADER"), locked("INDEPENDENT_DOMAIN_REVIEWER")
    assert not reconcile(
        a, b, [], distinct_humans_attested=True, funded_branch_fixtures_closed=True
    )["gate2_pass"]
    assert not reconcile(
        a, b, [], distinct_humans_attested=False, funded_branch_fixtures_closed=True
    )["gate2_pass"]
    b["responses"][0]["human_action"] = "REJECT"
    assert not reconcile(
        a, b, [], distinct_humans_attested=True, funded_branch_fixtures_closed=True
    )["gate2_pass"]


def test_sealed_trace_and_identity_not_in_normal_packet(tmp_path):
    path = tmp_path / "packet.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            "prefixes/case.csv", "rel_bar,open,high,low,close,volume\n0,1,2,.5,1,100\n"
        )
    assert audit_blinding(path)["status"] == "PASS"
    with zipfile.ZipFile(path, "a") as archive:
        archive.writestr("SEALED_ENGINE_TRACE.json", "{}")
    with pytest.raises(ValueError, match="LEAK"):
        audit_blinding(path)
