"""Explicit AI override adapter; the original human protocol is not rewritten."""

from __future__ import annotations

import hashlib
import json
import zipfile
from datetime import datetime
from pathlib import Path

from . import fidelity_pipeline as pipeline
from .akah_foundation_core_v1r1 import utc
from .review_validation import DISPOSITIONS, ROLES

PROTOCOL = "AKAH_GATE2_OPERATIONAL_DUAL_AI_OVERRIDE_V2"
IDENTITIES = {
    "proxy": ("CODEX_AI_DIAGNOSTIC", "AI_ASSISTANT"),
    "independent": ("INDEPENDENT_DOMAIN_REVIEWER", "AI_ASSISTANT_PER_USER_EXPLICIT_INSTRUCTION"),
}


def locked_ai(path: Path, role: str, ids: set[str], corpus: str):
    raw = path.read_bytes()
    doc = json.loads(raw)
    reviewer, identity = IDENTITIES[role]
    actual_type = doc.get("reviewer_type", doc.get("reviewer_identity_type"))
    if doc.get("reviewer_id") != reviewer or actual_type != identity:
        raise ValueError("AI_IDENTITY_NOT_BOUND")
    if doc.get("human_review_equivalent") or doc.get("distinct_human_attestation"):
        raise ValueError("FALSE_HUMAN_ATTESTATION")
    if doc.get("locked") is not True or doc.get("corpus_sha256") != corpus:
        raise ValueError("AI_LOCK_OR_CORPUS_INVALID")
    stamp = datetime.fromisoformat(doc["locked_at"].replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        raise ValueError("LOCK_CLOCK_UNBOUND")
    rows = doc.get("responses", [])
    if len(rows) != len(ids) or {r["case_id"] for r in rows} != ids:
        raise ValueError("AI_INCOMPLETE_OR_DUPLICATE_CASES")
    for row in rows:
        if row.get("reviewer_id") != reviewer:
            raise ValueError("ROW_REVIEWER_MISMATCH")
        if row.get("human_action") not in {"ACCEPT", "REJECT", "UNRESOLVED"}:
            raise ValueError("ACTION_INVALID")
        if not all(isinstance(row.get(k), str) and row[k].strip() for k in ROLES):
            raise ValueError("ROLES_INCOMPLETE")
        differences = row.get("differences")
        if not isinstance(differences, list) or set(differences) - {
            "DIFFERENT_" + k.upper() for k in ROLES
        }:
            raise ValueError("DIFFERENCES_INVALID")
    return {
        "path": str(path),
        "sha256": hashlib.sha256(raw).hexdigest().upper(),
        "reviewer_id": reviewer,
        "reviewer_type": identity,
        "locked_at": stamp.isoformat(),
        "schema_lock_valid": True,
        "human_attestation": False,
        "corpus_sha256": corpus,
        "responses": rows,
    }


def verify_dual(primary: dict, second: dict, claimed: dict):
    if not primary.get("schema_lock_valid") or not second.get("schema_lock_valid"):
        raise ValueError("TWO_VALID_AI_LOCKS_REQUIRED")
    if primary["corpus_sha256"] != second["corpus_sha256"]:
        raise ValueError("CORPUS_MISMATCH")
    a = {r["case_id"]: r for r in primary["responses"]}
    b = {r["case_id"]: r for r in second["responses"]}
    if set(a) != set(b):
        raise ValueError("CASE_MISMATCH")
    agreement = sum(a[k]["human_action"] == b[k]["human_action"] for k in a)
    counts = {"cases": len(a), "agreement": agreement, "disagreement": len(a) - agreement}
    if counts != {"cases": 98, "agreement": 50, "disagreement": 48}:
        raise ValueError("RECONCILIATION_COUNT_DRIFT")
    if claimed.get("corpus_sha256") != primary["corpus_sha256"]:
        raise ValueError("RECONCILIATION_CORPUS_DRIFT")
    for role, proof in (("codex_proxy_review", primary), ("chatgpt_independent_review", second)):
        if claimed["source_reviews"][role]["sha256"] != proof["sha256"]:
            raise ValueError("RECONCILIATION_REVIEW_HASH_DRIFT")
    a_counts = claimed["counts"]
    if [
        a_counts[k] for k in ("cases", "exact_reviewer_agreement", "exact_reviewer_disagreement")
    ] != [98, 50, 48]:
        raise ValueError("RECONCILIATION_CLAIM_DRIFT")
    listed = claimed["strong_consensus_mismatch_case_ids"]
    if (
        len(listed) != 15
        or len(set(listed)) != 15
        or any(k not in a or a[k]["human_action"] != b[k]["human_action"] for k in listed)
    ):
        raise ValueError("PRE_TRACE_CONSENSUS_LIST_INVALID")
    return {**counts, "locks_verified_before_trace": True, "consensus_list_checked": 15}


def bound_trace(path: Path, expected_sha: str, primary: dict, second: dict, claimed: dict):
    preflight = verify_dual(primary, second, claimed)
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest().upper() != expected_sha:
        raise ValueError("RECERTIFIED_TRACE_ZIP_HASH_MISMATCH")
    with zipfile.ZipFile(path) as archive:
        raw = archive.read("CASE_MAP_AND_ENGINE_TRACE.json")
    rows = json.loads(raw)
    ids = [r["case_id"] for r in rows]
    if len(ids) != len(set(ids)):
        raise ValueError("TRACE_DUPLICATE_ID")
    selected = []
    for row in rows:
        if utc(row["time"]) >= utc("2024-01-01"):
            raise ValueError("PROTECTED_TRACE_TIME")
        value = {k: v for k, v in row.items() if k not in {"case_id", "prefix_maxima"}}
        value["time"] = utc(value["time"])
        selected.append(value)
    selected.sort(key=pipeline.sampling_key)
    if pipeline.digest(selected).upper() != primary["corpus_sha256"]:
        raise ValueError("TRACE_CORPUS_DIGEST_MISMATCH")
    a = {r["case_id"]: r for r in primary["responses"]}
    b = {r["case_id"]: r for r in second["responses"]}
    trace = {r["case_id"]: r for r in rows if not r["reserve"]}
    if set(trace) != set(a):
        raise ValueError("TRACE_PRIMARY_ID_MISMATCH")
    # INTERMEDIATE is event evidence, not an engine verdict of UNRESOLVED.
    expected = {"POSITIVE": "ACCEPT", "NO_INTENT": "REJECT"}
    mismatch = sorted(
        k
        for k in a
        if trace[k]["kind"] in expected
        and a[k]["human_action"] == b[k]["human_action"]
        and a[k]["human_action"] != expected[trace[k]["kind"]]
    )
    if mismatch != sorted(claimed["strong_consensus_mismatch_case_ids"]):
        raise ValueError("TRACE_RECONCILIATION_15_CASE_DRIFT")
    return rows, {
        **preflight,
        "consensus_vs_actionable_engine": len(mismatch),
        "strong_consensus_case_ids": mismatch,
        "trace_member_sha256": hashlib.sha256(raw).hexdigest().upper(),
        "trace_zip_sha256": expected_sha,
        "corpus_reconstructed": True,
        "gate2_pass": False,
        "agreement_is_not_qualification": True,
        "original_human_protocol_unchanged": True,
    }


def operational_disposition_gate(primary, second, adjudications):
    """AI authorization changes reviewer eligibility, not evidence/closure requirements."""
    a = {r["case_id"]: r for r in primary["responses"]}
    if set(adjudications) != set(a):
        raise ValueError("EVERY_CASE_NEEDS_SOURCE_ADJUDICATION")
    open_ids = []
    for case, decision in adjudications.items():
        if (
            decision.get("primary_review_sha256") != primary["sha256"]
            or decision.get("second_review_sha256") != second["sha256"]
            or not decision.get("engine_trace_sha256")
            or not decision.get("spec_sha256")
            or set(decision.get("roles_reviewed", [])) != set(ROLES)
            or decision.get("disposition") not in DISPOSITIONS
        ):
            raise ValueError("SOURCE_BOUND_DISPOSITION_REQUIRED:" + case)
        if decision.get("closed") is not True or not decision.get("resolution_evidence_sha256"):
            open_ids.append(case)
    return {
        "protocol_id": PROTOCOL,
        "gate2_pass": not open_ids,
        "open_case_ids": sorted(open_ids),
        "human_attestation": False,
        "majority_vote_used": False,
    }
