"""Validate actual human lock files; never generate or impute human responses."""

from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

ROLES = ("context", "structure", "location", "trigger", "invalidation", "management")
REVIEWERS = ("USER_MANUAL_TRADER", "INDEPENDENT_DOMAIN_REVIEWER")
DISPOSITIONS = {
    "IMPLEMENTATION_BUG",
    "SPEC_AMBIGUITY",
    "DOCTRINE_SCOPE_GAP",
    "MANUAL_PREFERENCE_NOT_IN_SPEC",
    "INSUFFICIENT_VIEW",
}


def validate_locked(path: Path, reviewer: str, case_ids: set[str], corpus_sha: str):
    raw = path.read_bytes()
    doc = json.loads(raw)
    if reviewer not in REVIEWERS or doc.get("reviewer_id") != reviewer:
        raise ValueError("REVIEWER_ID_NOT_BOUND")
    if (
        doc.get("protocol_id") != "AKAH_BLIND_TRANSLATION_FIDELITY_V1"
        or doc.get("corpus_sha256") != corpus_sha
        or doc.get("locked") is not True
        or not doc.get("locked_at")
    ):
        raise ValueError("REVIEW_NOT_LOCKED_TO_CURRENT_CORPUS")
    rows = doc.get("responses", [])
    ids = [r.get("case_id") for r in rows]
    if set(ids) != case_ids or len(ids) != len(case_ids):
        raise ValueError("INCOMPLETE_OR_DUPLICATED_REVIEW_CASES")
    for row in rows:
        if row.get("reviewer_id") != reviewer or row.get("human_action") not in {
            "ACCEPT",
            "REJECT",
            "UNRESOLVED",
        }:
            raise ValueError("REVIEW_ACTION_INVALID")
        if not all(isinstance(row.get(k), str) and row[k].strip() for k in ROLES):
            raise ValueError("REVIEW_ROLES_INCOMPLETE")
        if not isinstance(row.get("differences"), list) or any(
            d not in {"DIFFERENT_" + r.upper() for r in ROLES} for d in row["differences"]
        ):
            raise ValueError("REVIEW_DIFFERENCES_SCHEMA")
    return {
        "path": str(path),
        "sha256": hashlib.sha256(raw).hexdigest().upper(),
        "reviewer_id": reviewer,
        "responses": rows,
        "schema_lock_valid": True,
        "human_identity_verification": "REQUIRED_EXTERNAL_ATTESTATION_NOT_INFERRED_FROM_JSON",
    }


def reconcile(
    primary: dict,
    second: dict,
    dispositions: list[dict],
    *,
    distinct_humans_attested: bool,
    funded_branch_fixtures_closed: bool,
    case_adjudications: dict | None = None,
):
    if not distinct_humans_attested or not funded_branch_fixtures_closed:
        return {"gate2_pass": False, "status": "HUMAN_OR_FIXTURE_AUTHORITY_REQUIRED"}
    a = {r["case_id"]: r for r in primary["responses"]}
    b = {r["case_id"]: r for r in second["responses"]}
    if set(a) != set(b):
        raise ValueError("REVIEW_CORPUS_MISMATCH")
    # Agreement between humans is not agreement with the engine/spec. Every
    # case's six comments need a trace-bound materiality disposition, including
    # cases where both reviewers selected ACCEPT and checked no difference box.
    if case_adjudications is None or set(case_adjudications) != set(a):
        return {"gate2_pass": False, "status": "ALL_COMMENTS_TRACE_ADJUDICATION_REQUIRED"}
    for review in (primary, second):
        if not review.get("sha256"):
            return {"gate2_pass": False, "status": "LOCKED_REVIEW_HASH_REQUIRED"}
    for case, decision in case_adjudications.items():
        if (
            decision.get("primary_review_sha256") != primary["sha256"]
            or decision.get("second_review_sha256") != second["sha256"]
            or not decision.get("engine_trace_sha256")
            or not decision.get("spec_sha256")
            or set(decision.get("roles_reviewed", [])) != set(ROLES)
            or decision.get("materiality_adjudicated") is not True
        ):
            raise ValueError("CASE_COMMENT_ADJUDICATION_NOT_AUTHORITY_BOUND:" + case)
    issues = []
    for case in sorted(a):
        if (
            a[case]["human_action"] != b[case]["human_action"]
            or "UNRESOLVED" in (a[case]["human_action"], b[case]["human_action"])
            or a[case]["differences"]
            or b[case]["differences"]
            or case_adjudications[case].get("open_material_issue") is not False
        ):
            issues.append(case)
    closed = {}
    for d in dispositions:
        if d.get("case_id") not in a or d.get("disposition") not in DISPOSITIONS:
            raise ValueError("UNBOUND_REVIEW_DISPOSITION")
        if d.get("closed") is True and d.get("resolution_evidence_sha256"):
            closed[d["case_id"]] = d
    unresolved = [case for case in issues if case not in closed]
    return {
        "gate2_pass": not unresolved,
        "unresolved_cases": unresolved,
        "majority_vote_used": False,
        "open_issue_count": len(unresolved),
    }


def audit_blinding(packet: Path):
    with zipfile.ZipFile(packet) as archive:
        names = archive.namelist()
        if any("SEALED" in n.upper() or "ENGINE_TRACE" in n.upper() for n in names):
            raise ValueError("SEALED_TRACE_LEAK")
        for name in names:
            if name.endswith(".csv"):
                header = archive.read(name).decode("utf-8").splitlines()[0].lower().split(",")
                forbidden = {
                    "timestamp",
                    "pair",
                    "symbol",
                    "pnl",
                    "mfe",
                    "mae",
                    "engine_action",
                    "sampling_kind",
                }
                if forbidden.intersection(header):
                    raise ValueError("BLIND_PREFIX_FIELD_LEAK")
    return {"status": "PASS", "file_count": len(names), "sealed_trace_in_packet": False}
