# ruff: noqa: E501 -- evidence declarations and report strings, not decision rules
"""Package non-economic closure evidence. Does not complete governance or run replay."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "governance/post_dual_review_gate2_adjudication_pre_gate3_closure_v2"
TASK = "AKAH_POST_DUAL_REVIEW_GATE2_ADJUDICATION_PRE_GATE3_CLOSURE_V2"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def read(name):
    return json.loads((OUT / name).read_text(encoding="utf-8"))


def save(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main():
    active = json.loads((ROOT / ".akah_bot/active_task.json").read_text())
    assert active["task_id"] == TASK and active["starting_charter_revision"] == 772
    proof = read("authority_verification.json")["proof"]
    assert [
        proof[k] for k in ("cases", "agreement", "disagreement", "consensus_vs_actionable_engine")
    ] == [98, 50, 48, 15]
    assert proof["locks_verified_before_trace"] and proof["corpus_reconstructed"]
    sample = read("supplemental_sampling_audit.json")
    view = read("supplemental_view_certificate.json")
    assert sample["all_positive_targets_met"] and sample["protected_rows_loaded"] == 0
    assert view["status"] == "PASS" and view["pre_drawn_reserve_unchanged"]
    assert (
        not view["new_locks_present"]
        and sha(OUT / "SUPPLEMENTAL_BLIND_VIEW_ONLY.zip") == view["packet_sha256"]
    )
    suites = [
        "tests/research/test_multi_school_fidelity.py",
        "tests/research/test_multi_school_evidence_review.py",
        "tests/research/test_post_dual_review_closure.py",
    ]
    cp = subprocess.run(
        [sys.executable, "-B", "-m", "pytest", "-q", "-p", "no:cacheprovider", *suites],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert cp.returncode == 0, cp.stdout + cp.stderr
    assert "49 passed" in cp.stdout
    bindings = {}
    files = [
        "bound_hybrid.py",
        "event_execution_bridge.py",
        "operational_ai_review.py",
        "source_router.py",
        "evidence_selector.py",
        "portfolio_kernel.py",
        "akah_full_fidelity_runtime_v1.py",
        "akah_replay_ready_detectors_v1.py",
        "gate3_precommit.py",
        "qualification_uncertainty.py",
        "review_validation.py",
    ]
    paths = [ROOT / "src/spotbot/research/multi_school_fidelity" / n for n in files]
    paths += [ROOT / p for p in suites]
    paths += [
        ROOT / "scripts/research" / p
        for p in (
            "run_post_dual_review_adjudication.py",
            "prepare_post_review_supplemental_packet.py",
            "finalize_post_dual_review_evidence.py",
        )
    ]
    for path in paths:
        compile(path.read_text(encoding="utf-8"), str(path), "exec")
        bindings[path.relative_to(ROOT).as_posix()] = sha(path)
    save(
        "engineering_verification.json",
        {
            "synthetic_tests": {
                "returncode": cp.returncode,
                "stdout": cp.stdout,
                "stderr": cp.stderr,
                "suites": suites,
                "passed": 49,
            },
            "compile": "PASS_IN_MEMORY_NO_PYC",
            "source_sha256": bindings,
            "school_semantic_rules_changed": False,
            "original_human_protocol_changed": False,
            "market_adapter_certification": False,
            "production_changed": False,
        },
    )
    blockers = [
        {
            "id": "WY_LPS_LIVE_OWNERSHIP",
            "kind": "IMPLEMENTATION_BUG",
            "open": True,
            "evidence": "Synthetic stale/below-LPS intent reproduction; G2-P-0087/0091",
            "closure_needed": "Source-bound owned LPS lifecycle, checkpoint adjudication and reserve recertification; no invented TTL",
        },
        {
            "id": "WY_REACCUMULATION_CONTEXT_LOSS",
            "kind": "IMPLEMENTATION_BUG",
            "open": True,
            "evidence": "HIGHER_LEVEL_RANGE_FORMS deletes SC/AR/ST/sc_time still required by readiness/cause; G2-P-0014",
            "closure_needed": "Authoritative reaccumulation cause/readiness ownership before semantic repair; reserve not primary pass",
        },
        {
            "id": "LEGACY_HYBRID_LIVE_GRAPH",
            "kind": "IMPLEMENTATION_BUG",
            "open": True,
            "evidence": "Legacy accumulation of role events lacks live parent graph binding; opt-in BoundHybrid is synthetic-tested only",
            "closure_needed": "Bind authorized role semantics and wire the new graph into actual runtime; legacy output remains quarantined",
        },
        {
            "id": "CLASSICAL_PREENTRY_FAILURE",
            "kind": "SPEC_AMBIGUITY",
            "open": True,
            "evidence": "Deep throwback permitted by low<=boundary && close>boundary; G2-P-0052",
            "closure_needed": "Source authority for pattern invalidation; owner-neutral anchors and reserve review; no depth threshold from dislike",
        },
        {
            "id": "WY_SPRING_TEST_AND_CAUSE",
            "kind": "DOCTRINE_SCOPE_GAP",
            "open": True,
            "evidence": "G2-P-0093/0094 spring reclaim vs separately owned later test; unresolved P&F segment/countline/downside stride",
            "closure_needed": "Bind doctrine before any funded Wyckoff rule",
        },
        {
            "id": "LOCKED_SUPPLEMENTAL_AND_RESERVE_REVIEWS",
            "kind": "INSUFFICIENT_VIEW",
            "open": True,
            "evidence": "34-case neutral packet exists; 14 new positives plus 20 original primary controls; no new locks",
            "closure_needed": "Lock independent AI responses on new view; unresolved old cases and any repaired semantic version require reserve adjudication",
        },
        {
            "id": "HISTORICAL_PIT_QUANTITY_AUTHORITY",
            "kind": "DOCTRINE_SCOPE_GAP",
            "open": True,
            "evidence": "No exact dated exchange tick/lot/min-notional source bound; synthetic QuantityRule is not historical authority",
            "closure_needed": "Provide an existing authoritative effective/available-dated historical source; never infer from price decimal precision",
        },
        {
            "id": "FULL_MARKET_EVENT_ADAPTER",
            "kind": "DOCTRINE_SCOPE_GAP",
            "open": True,
            "evidence": "Event bridge tested on synthetic fixtures, deliberately refuses real-market arming",
            "closure_needed": "Source-bound event, quantity, capacity and management integration certified without economics; synthetic prototype is not a full adapter",
        },
        {
            "id": "ROUTER_FUNDED_PHASE_MAPPING",
            "kind": "DOCTRINE_SCOPE_GAP",
            "open": True,
            "evidence": "SourceBoundRouter implemented; empty source table denies all funding",
            "closure_needed": "Bind phase-to-complete-grammar authority and actual runtime permissions; no invented map",
        },
        {
            "id": "ARCH_OFFLINE_DEPENDENCY",
            "kind": "DOCTRINE_SCOPE_GAP",
            "open": True,
            "evidence": "arch unavailable in current .venv; frozen estimator arch.bootstrap.optimal_block_length:stationary unchanged",
            "closure_needed": "Exact approved offline dependency/version binding; no estimator substitution",
        },
        {
            "id": "HARMONIC_FAMILY_MATRIX",
            "kind": "DOCTRINE_SCOPE_GAP",
            "open": True,
            "closure_needed": "Bind direction/ratio/stop/management matrix; remain unfunded",
        },
        {
            "id": "ELLIOTT_OWNER_PARENT_CHILD",
            "kind": "DOCTRINE_SCOPE_GAP",
            "open": True,
            "closure_needed": "Bind owner-count and parent-child grammar; consensus stays diagnostic",
        },
        {
            "id": "DOW_STOP_AND_CONTEXT",
            "kind": "DOCTRINE_SCOPE_GAP",
            "open": True,
            "closure_needed": "Reconcile context vs full setup and source-bound protective stop; bounded frozen scarcity alone is not closure",
        },
    ]
    save("remaining_blockers.json", blockers)
    save(
        "authority_search_scope.json",
        {
            "scope": "Current multi_school_fidelity source/contracts, frozen precommit handoff/source manifests and scoped local dependency metadata; not a whole-repository historical audit",
            "historical_quantity_status": "NOT_BOUND_IN_AUTHORIZED_LOCAL_AUTHORITY",
            "non_authorities": [
                "OHLC decimal precision",
                "present-day exchange metadata",
                "NO_TICK candle canonicalization policy",
            ],
            "arch_import_available": importlib.util.find_spec("arch") is not None,
            "arch_estimator": "arch.bootstrap.optimal_block_length:stationary",
            "offline_wheel_binding": None,
            "network_lookup": False,
            "scarcity": read("dow_frozen_frame_exhaustion.json"),
        },
    )
    unfunded = {
        "FS_WYCKOFF_FULL_LONG": [
            "WY_LPS_LIVE_OWNERSHIP",
            "WY_REACCUMULATION_CONTEXT_LOSS",
            "WY_SPRING_TEST_AND_CAUSE",
        ],
        "FS_ICT_2022_CORE_CRYPTO_LONG": ["LOCKED_SUPPLEMENTAL_AND_RESERVE_REVIEWS"],
        "FS_CLASSICAL_FULL_LONG": [
            "CLASSICAL_PREENTRY_FAILURE",
            "LOCKED_SUPPLEMENTAL_AND_RESERVE_REVIEWS",
        ],
        "FS_HARMONIC_FULL_LONG": ["HARMONIC_FAMILY_MATRIX"],
        "FS_ELLIOTT_FULL_LONG": ["ELLIOTT_OWNER_PARENT_CHILD"],
        "FS_DOW_CRYPTO_ADAPTED_LONG": ["DOW_STOP_AND_CONTEXT"],
        "HYB_MARKUP_CONTINUATION": ["LEGACY_HYBRID_LIVE_GRAPH", "ROUTER_FUNDED_PHASE_MAPPING"],
        "HYB_FAILED_AUCTION_REVERSAL": ["LEGACY_HYBRID_LIVE_GRAPH", "ROUTER_FUNDED_PHASE_MAPPING"],
        "HYB_CORRECTIVE_COMPLETION_RESUMPTION": [
            "LEGACY_HYBRID_LIVE_GRAPH",
            "ROUTER_FUNDED_PHASE_MAPPING",
        ],
    }
    certificate = {
        "GATE2_PIPELINE": "PASS",
        "GATE2_REVIEW_RECONCILIATION": "FAIL",
        "GATE2_SAMPLE_VALID": "YES",
        "GATE2_SAMPLE_COMPLETE_OR_PROVEN_SCARCE": "YES",
        "MATERIAL_IMPLEMENTATION_BUGS_OPEN": 3,
        "MATERIAL_SPEC_AMBIGUITIES_IN_FUNDED_SCOPE": 0,
        "FUNDED_GRAMMARS": [],
        "UNFUNDED_GRAMMARS": unfunded,
        "GATE3_TECHNICAL_PRECONDITIONS": "FAIL",
        "GATE3_PRECOMMIT_FREEZE": "FAIL",
        "READY_FOR_SINGLE_GATE3_REPLAY": "NO",
        "2024_ROWS_ACCESSED": "NO",
        "2025_ROWS_ACCESSED": "NO",
        "ECONOMIC_REPLAY_EXECUTED": "NO",
        "PNL_QUALIFICATION_EXECUTED": "NO",
        "PNL_READ": "NO",
        "PUSH": "NO",
        "sample_statement_scope": "Mechanical corpus/count integrity only; supplemental reviews are not locked and reserve fidelity is not certified. Dow scarcity is ONLY the exhausted 104-row frozen BTC context frame (2 positives in 2022, 0 in 2023).",
        "zero_funded_ambiguities_explanation": "Empty funded scope, NOT proof that school specifications are resolved",
        "pipeline_pass_explanation": "Locked-input verification, exact corpus/trace binding, non-economic sampling/view integrity and synthetic fixtures; NOT Gate2 or market-adapter certification",
    }
    save("final_certificate.json", certificate)
    governance = {
        "lookahead_or_future_information_used": False,
        "pair_or_event_identity_used_as_runtime_rule": False,
        "posthoc_outcome_threshold_search_used": False,
        "2023_new_raw_or_replay_accessed": True,
        "2024_used_as_fresh_holdout": False,
        "2024_used_to_define_new_runtime_rule": False,
        "2025_accessed": False,
        "production_changed": False,
    }
    save(
        "governance_report.json",
        {
            "task_id": TASK,
            "outcome": "FAIL_CLOSED",
            "declarations": governance,
            "2023_access_explanation": "Authorized pre-2024 non-economic detector census and prefix-only blind views; no trading replay or PnL",
            "remote_sync": "NOT_EXECUTED_USER_PUSH_NO",
            "next_governed_task_requires_sync_or_explicit_governance_resolution": True,
            "closeout": "cmd_complete and cmd_verify required after scoped implementation commit",
        },
    )
    result = {
        "schema_version": "akah-post-dual-review-pre-gate3-closure-v2",
        "task_id": TASK,
        "classification": "SOURCE_ADJUDICATED_GAPS_QUARANTINED_GATE3_NOT_READY",
        "outcome": "FAIL_CLOSED",
        "scientific_conclusion": "NONE_NO_ECONOMIC_QUALIFICATION",
        "starting_charter_revision": 772,
        "starting_head": active["starting_head"],
        "reconciliation_counts": [98, 50, 48, 15],
        "reconciliation_input_hashes": read("authority_verification.json")["input_sha256"],
        "synthetic_tests_passed": 49,
        "new_positive_cases": 14,
        "new_pair_scans": 28,
        "supplemental_packet": {
            "path": str(OUT / "SUPPLEMENTAL_BLIND_VIEW_ONLY.zip"),
            "sha256": view["packet_sha256"],
            "corpus_sha256": view["corpus_sha256"],
            "cases": 34,
            "new_locks": False,
        },
        "original_corpus_and_reserve_unchanged": True,
        "open_disposition_case_ids": read("operational_review_disposition_result.json")[
            "open_case_ids"
        ],
        "final_certificate": certificate,
        "remaining_blockers": blockers,
        "fixed_engineering_defects": [
            "CHILD_AVAILABLE_BEFORE_PARENT",
            "DUPLICATE_ACCEPTED_THESIS_ID",
            "SAME_ASSET_STAGED_CAPACITY_DOUBLE_SPEND",
        ],
        "school_semantic_rules_changed": False,
        "reserve_semantic_recertification_executed": False,
        "next_bottleneck": "MASTER_GATE2_SOURCE_AUTHORITY_LOCKED_SUPPLEMENTAL_REVIEW_AND_EXECUTION_PRECONDITIONS_V3",
        "new_economic_task_authorized": False,
        "github_sync_executed": False,
    }
    save("canonical_result.json", result)
    report = """# Post-dual-review Gate2 adjudication / pre-Gate3 closure V2

## Decision

FAIL_CLOSED. No funded grammar; Gate2 review closure FAIL; Gate3 preconditions/freeze FAIL; replay NOT READY. This is a completed source-adjudication mission, not economic qualification. No PnL, 2024/2025 rows, economic replay, production change or push.

## Authority and packaging

Both supplied SHA256s match, both reviews are locked truthful AI reviews of the same 98 IDs/corpus. Counts reproduced 98/50/48/15 before opening trace. Intermediate evidence is not an engine BUY/REJECT decision. The stale root trace extraction is quarantined; the ICT-recertified ZIP member independently reconstructs the exact original corpus. Authority paths and hashes: authority_verification.json. Human protocol unchanged.

## Source adjudication

All 98 original responses and six role comments from both reviewers are preserved in case_adjudications.json/CSV. Dispositions use only the five requested categories. Quarantine of unresolved Harmonic/Elliott/Dow doctrine is NOT school approval. 32 original case dispositions remain open.

- Wyckoff: synthetic tests prove the API can issue stale/unowned LPS intents and that reaccumulation deletes SC/AR/ST inputs still needed for cause/readiness. They do NOT prove a particular real case should trade. G2-P-0014/0087/0091 remain open. Spring reclaim versus later spring-test ownership is unresolved for 0093/0094. No TTL or new readiness rule invented.
- Classical: deep throwback is permitted by the existing low<=boundary AND close>boundary formula; pre-entry failure authority is not bound. 0052 remains a specification ambiguity. 0007/0057/0058/0060 mix local chart interpretation with a hidden 4H owner structure: insufficient view. No outcome-driven tightening.
- ICT: raid < MSS/FVG creation < later retracement is bound; 0096/0097 need source-neutral anchors and locked expanded coverage. No same-bar retracement added; OB remains diagnostic.
- Dow: frozen 104-row context frame exhausted; two context positives in 2022 and zero in 2023. This is bounded scarcity, not proof of market-wide absence. No protective-stop owner; context-only.
- Harmonic: family/direction/ratio/stop/management matrix unresolved. Elliott: parent-child/owner-count unresolved; consensus diagnostic. Neither funded.

## Engineering actually completed

49 synthetic tests pass. In-memory compile and lint pass. Three repairs: reject child availability before its parent; reject duplicate accepted thesis IDs; aggregate same-asset capacity across staged legs before common-risk reduction. Opt-in live evidence graph and source-bound router permissions are tested; legacy hybrid runtime remains quarantined. Event bridge tests gap/stop priority, next-open management, no retroactive trail, bounded quantity arithmetic and shared capacity. It deliberately cannot arm real market execution. Synthetic arithmetic is NOT historical exchange-rule authority or full adapter certification.

## Sample and reserve

28 additional eligible pairs scanned once with bounded pre-2024 inputs; 14 fresh Wyckoff/ICT positives complete their missing count quotas. Additional computations cached. Original primary 98 and predrawn reserve 90 are unchanged. Dow shortages documented only after frozen-frame exhaustion. Supplemental blind packet: 34 cases = 14 new positives + 20 reused PRIMARY controls; no reserve consumed. Neutral confirmed-pivot/gap/break/reclaim geometry, no hidden engine verdict or future bars. No new review locks exist. No school semantic repair was made, and no reserve semantic recertification is claimed. Do NOT review the sealed map as a blind reviewer.

## Finite blockers / stop boundary

remaining_blockers.json contains 13 distinct source, view or integration blockers. Material implementation bugs open = 3 (two Wyckoff + legacy live hybrid graph). Funded-scope ambiguity count = 0 ONLY because funded scope is empty. Exact historical PIT tick/lot/min-notional source is unbound; current metadata, OHLC precision and NO_TICK missing-candle policy are not substitutes. arch dependency unavailable offline; frozen stationary estimator unchanged. Phase-to-funded permissions and full event-driven market execution integration are not certified. No unsupported funded list or estimator substitution was created.

The next bottleneck is MASTER_GATE2_SOURCE_AUTHORITY_LOCKED_SUPPLEMENTAL_REVIEW_AND_EXECUTION_PRECONDITIONS_V3. This report authorizes no economic experiment. Existing Gate3 numerical specification is preserved UNARMED. Semantic rules created from disagreements must make their triggering cases development-only and use predrawn reserve; mechanical repairs alone do not certify reserve fidelity.

## Reproducibility / governance

research_protocol.json was frozen before BEGIN. Source hashes and synthetic test output: engineering_verification.json. Inputs and original trace: authority_verification.json. Bounded readers/selection: supplemental_sampling_audit.json. View integrity: supplemental_view_certificate.json. Full case dispositions, remaining blockers, final_certificate.json and canonical_result.json persist locally. artifact_manifest.json binds every output other than itself, including sealed files (kept outside blind ZIP).

Local governance completion must run cmd_complete then cmd_verify after the implementation commit. PUSH=NO: no remote sync and no subsequent governed mission permitted without satisfying its sync requirement. Final revision/head are reported from the actual closeout, not invented in this pre-closeout evidence.
"""
    (OUT / "SUMMARY.md").write_text(report, encoding="utf-8")
    manifest = {}
    for path in sorted(OUT.rglob("*")):
        if path.is_file() and path.name != "artifact_manifest.json":
            manifest[path.relative_to(OUT).as_posix()] = {
                "sha256": sha(path),
                "bytes": path.stat().st_size,
            }
    save(
        "artifact_manifest.json",
        {"files": manifest, "self_excluded": True, "raw_market_payloads_included": False},
    )
    print(json.dumps(certificate, indent=2))
    print("CANONICAL_RESULT_SHA256=" + sha(OUT / "canonical_result.json"))
    print("ARTIFACT_FILES=" + str(len(manifest)))


if __name__ == "__main__":
    main()
