"""Reproduce the V7 engineering certificate from saved synthetic outputs only.

No market reader, model fit, economic replay, production hook, or network call.
Never promote absent authority/independent review/economic evidence to PASS.
"""

from __future__ import annotations

import ast
import hashlib
import json
import subprocess
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "governance/structural_gap_closure_v7"
START = "10f6967db0118b14c6f9e6832f424decfaa62f3c"
TASK = "AKAH_ALL_TWELVE_STRUCTURAL_GAPS_SOURCE_BOUND_CLOSURE_V7"
PREFIX = "src/spotbot/research/multi_school_fidelity/"
NEW = [
    PREFIX + "campaign_execution_v7.py",
    PREFIX + "owned_event_pipeline_v7.py",
    PREFIX + "live_dow_context_v7.py",
    "tests/research/test_campaign_execution_v7.py",
    "scripts/research/certify_structural_gap_closure_v7.py",
]
INPUTS = [
    PREFIX + "structural_lifecycle_v6.py",
    PREFIX + "lifecycle_execution_v6.py",
    PREFIX + "full_replay_v4.py",
    PREFIX + "full_replay_v5.py",
    PREFIX + "owned_runtime_v3.py",
    PREFIX + "akah_full_fidelity_runtime_v1.py",
    PREFIX + "akah_replay_ready_detectors_v1.py",
    PREFIX + "akah_thesis_engine_foundation_v1.py",
    PREFIX + "evidence_selector.py",
    PREFIX + "source_router.py",
    "governance/structural_lifecycle_repair_v6/remaining_gaps.json",
    "governance/structural_lifecycle_repair_v6/research_protocol.json",
    "governance/final_gate2_to_gate3_replay_ready_mega_v3/09_HISTORICAL_QUANTITY_AUTHORITY_MANIFEST.json",
    "governance/final_gate2_to_gate3_replay_ready_mega_v3/08_QUARANTINED_GRAMMARS.json",
    "governance/final_gate2_to_gate3_replay_ready_mega_v3/05_GATE2_RESERVE_RECERTIFICATION.json",
    "governance/final_gate2_to_gate3_replay_ready_mega_v3/19_REMAINING_NONBLOCKING_RESEARCH_GAPS.json",
]


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def save(name, value):
    (OUT / name).write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def main():
    protocol = json.loads((OUT / "research_protocol.json").read_text(encoding="utf-8"))
    gaps = json.loads((OUT / "gap_adjudication.json").read_text(encoding="utf-8"))["gaps"]
    original = json.loads((ROOT / INPUTS[10]).read_text(encoding="utf-8"))["gaps"]
    assert protocol["task_id"] == TASK
    assert {g["id"] for g in gaps} == {g["id"] for g in original} and len(gaps) == 12
    changed = set(git("diff", "--name-only", START).decode().splitlines())
    allowed = set(NEW) | {"governance/AKAH_BOT_SYSTEM_CHARTER.json"}
    assert all(
        p in allowed or p.startswith("governance/structural_gap_closure_v7/") for p in changed
    )
    manifest = []
    for name in INPUTS:
        path = ROOT / name
        raw = path.read_bytes()
        blob = git("show", f"{START}:{name}")
        assert raw.replace(b"\r\n", b"\n") == blob.replace(b"\r\n", b"\n"), name
        manifest.append({"path": name, "sha256": sha(path), "unchanged_from": START})
    for name in NEW:
        ast.parse((ROOT / name).read_text(encoding="utf-8"), filename=name)
        manifest.append({"path": name, "sha256": sha(ROOT / name), "role": "NEW_V7_SOURCE"})
    suite = {}
    for name in ("test_results.xml", "v7_targeted_tests.xml"):
        doc = ET.parse(OUT / name).getroot()
        entries = [doc] if doc.tag == "testsuite" else list(doc.iter("testsuite"))
        counts = {
            k: sum(int(z.attrib.get(k, 0)) for z in entries)
            for k in ("tests", "failures", "errors", "skipped")
        }
        assert counts["tests"] > 0 and counts["failures"] == counts["errors"] == 0
        suite[name] = dict(counts, sha256=sha(OUT / name))
    # Subset counts must not be added to the full suite as extra independent tests.
    assert suite["v7_targeted_tests.xml"]["tests"] <= suite["test_results.xml"]["tests"]
    quantity = json.loads((ROOT / INPUTS[12]).read_text(encoding="utf-8"))
    assert quantity["historical_PIT_exchange_authority_found"] is False
    reserve = json.loads((ROOT / INPUTS[14]).read_text(encoding="utf-8"))
    assert reserve["ICT_reserve_positive_count"] == 0 and not reserve["human_attestation"]
    counts = dict(Counter(g["status"] for g in gaps))
    closed = sum(v for k, v in counts.items() if k == "CLOSED_TECHNICAL")
    assert closed < 12, "MISSING_REQUIRED_EVIDENCE_CANNOT_BE_CERTIFIED"
    save("source_manifest.json", {"starting_head": START, "sources": manifest})
    design = Path("C:/Users/abdul/Downloads/AKAH_STATEFUL_FULL_SYSTEMS_DESIGN_V1.zip")
    assert sha(design) == "8A38DE43A59B5EFA79F554C0F34D20556AC810147DF702C18575338A46B15904"
    with zipfile.ZipFile(design) as archive:
        members = []
        for name in (
            "AKAH_STATEFUL_FULL_SYSTEM_REGISTRY_V1.json",
            "AKAH_DOCTRINE_TO_IMPLEMENTATION_LEDGER_V1.csv",
            "AKAH_FULL_SYSTEM_SOURCE_AUTHORITY_V1.csv",
        ):
            members.append(
                {
                    "member": name,
                    "sha256": hashlib.sha256(archive.read(name)).hexdigest().upper(),
                }
            )
    save(
        "external_design_authority.json",
        {
            "path": str(design),
            "sha256": sha(design),
            "members": members,
            "role": "FROZEN_DESIGN_NOT_A_FULL_RUNTIME_OR_INDEPENDENT_REVIEW_CERTIFICATE",
        },
    )
    save(
        "evidence_snapshot.json",
        {
            "original_gap_ids": [g["id"] for g in original],
            "all_original_gaps_adjudicated": True,
            "status_counts": counts,
            "quantity_archive_found": False,
            "old_reserve_is_new_version_independent_certificate": False,
            "actual_six_producer_streams_recertified": False,
            "economic_replay_executed": False,
            "synthetic_dispatch_is_not_full_school_fidelity": True,
            "inherited_dow_volume_input_is_not_a_new_veto": True,
            "search_scope": [
                "Current source-bound foundation/runtime/detector/owner/selector code",
                "Prior V3 quantity authority audit and quarantine source adjudication",
                "Git history of quantity/cause/owner authority changes, no checkout",
                "Existing local design registry/doctrine ledger/source-authority archive metadata",
                "Old reserve recertification authority; no future/PnL chart review",
            ],
            "not_claimed": [
                "Exhaustive new exchange archival acquisition",
                "Independent V7 blind review",
                "Broad-market historical producer certification",
                "Profitable or superior market policy",
            ],
        },
    )
    save(
        "canonical_result.json",
        {
            "task_id": TASK,
            "classification": (
                "SOURCE_OWNED_CAMPAIGN_EXECUTION_TECHNICAL_PASS_ALL_TWELVE_NOT_CLOSED"
            ),
            "technical_verification": "PASS",
            "all_twelve_closed": False,
            "fully_closed_original_gap_count": closed,
            "remaining_original_gap_count": 12 - closed,
            "status_counts": counts,
            "gate3_ready": False,
            "economic_conclusion": "NONE",
            "economic_replay_executed": False,
            "market_rows_accessed": False,
            "2024_rows_accessed": False,
            "2025_rows_accessed": False,
            "model_fit": False,
            "parameter_search": False,
            "production_change": False,
            "governance_push_authorized": True,
            "research_push": False,
            "v4_v5_v6_authorities_unchanged": True,
            "synthetic_suites": suite,
            "protocol_sha256": sha(OUT / "research_protocol.json"),
            "gap_adjudication_sha256": sha(OUT / "gap_adjudication.json"),
            "source_manifest_sha256": sha(OUT / "source_manifest.json"),
            "evidence_snapshot_sha256": sha(OUT / "evidence_snapshot.json"),
            "external_design_authority_sha256": sha(OUT / "external_design_authority.json"),
            "next_bottleneck": (
                "V7_FULL_SCHOOL_OWNER_AUTHORITY_AND_INDEPENDENT_RESERVE_CERTIFICATION"
            ),
        },
    )
    save(
        "governance_report.json",
        {
            "task_id": TASK,
            "outcome": "NO_DECISION",
            "technical_outcome": "PASS",
            "all_twelve_success_condition_met": False,
            "next_task_before_governance_sync": "FORBIDDEN",
            "declarations": {
                k: False
                for k in (
                    "lookahead_or_future_information_used",
                    "pair_or_event_identity_used_as_runtime_rule",
                    "posthoc_outcome_threshold_search_used",
                    "2023_new_raw_or_replay_accessed",
                    "2024_used_as_fresh_holdout",
                    "2024_used_to_define_new_runtime_rule",
                    "2025_accessed",
                    "production_changed",
                )
            },
            "synthetic_boundary_date_literals_are_not_market_data": True,
            "no_claimed_human_or_independent_review": True,
        },
    )
    print(json.dumps({"technical": "PASS", "counts": counts, "all_twelve_closed": False}))


if __name__ == "__main__":
    main()
