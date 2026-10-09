"""Bounded synthetic engineering certificate; cannot run a market replay."""

from __future__ import annotations

import hashlib
import json
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "governance/producer_integration_bundle_v9"
START = "afa0aa3c527c969cbbaaf60d2f1b9a6a2b23c1da"
TASK = "AKAH_PACKAGE2_CAUSAL_PRODUCER_ROUTER_EXECUTION_INTEGRATION_V9"
DIRS = [
    "src/spotbot/research/multi_school_fidelity/integration_v9",
    "tests/research/integration_v9",
    "scripts/research/integration_v9",
]


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest().upper()


def binding(path):
    p = ROOT / path
    return dict(path=path, sha256=sha(p), bytes=p.stat().st_size)


def save(name, value):
    path = OUT / name
    path.write_text(
        json.dumps(value, sort_keys=True, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    return binding(path.relative_to(ROOT).as_posix())


def main():
    active = json.loads((ROOT / ".akah_bot/active_task.json").read_text())
    assert active["task_id"] == TASK and active["starting_head"] == START
    assert active["starting_charter_revision"] == 780
    assert git("branch", "--show-current") == active["starting_branch"]
    protocol = json.loads((OUT / "research_protocol.json").read_text())
    assert protocol["market_data_access"] == "NONE" and not protocol["economic_replay"]
    assert not git("diff", "--name-only") and not git("diff", "--cached", "--name-only")
    old = git(
        "ls-tree", "-r", "--name-only", START, "--", "src/spotbot/research/multi_school_fidelity"
    ).splitlines()
    preserved = []
    for path in old:
        if path.endswith(".py"):
            assert not git("diff", "--name-only", START, "--", path), path
            preserved.append(dict(binding(path), blob=git("rev-parse", f"{START}:{path}")))
    inputs = []
    for directory in DIRS:
        for path in sorted((ROOT / directory).glob("*")):
            if path.suffix == ".py" or path.name == ".gitattributes":
                rel = path.relative_to(ROOT).as_posix()
                assert (
                    subprocess.run(
                        ["git", "check-ignore", "--", rel], cwd=ROOT, capture_output=True
                    ).returncode
                    == 1
                )
                if path.suffix == ".py":
                    compile(path.read_text(), str(path), "exec")
                inputs.append(binding(rel))
    inputs.extend(
        binding("governance/producer_integration_bundle_v9/" + name)
        for name in [
            ".gitattributes",
            "research_protocol.json",
            "IMPLEMENTATION_CONTRACT.md",
            "SUMMARY.md",
        ]
    )
    authorities = [
        binding(path)
        for path in [
            "governance/school_ownership_bundle_v8/canonical_result.json",
            "governance/school_ownership_bundle_v8/profile_binding.json",
            "governance/structural_gap_closure_v7/gap_adjudication.json",
            "governance/final_gate2_to_gate3_replay_ready_mega_v3/05_GATE2_RESERVE_RECERTIFICATION.json",
            "governance/final_gate2_to_gate3_replay_ready_mega_v3/09_HISTORICAL_QUANTITY_AUTHORITY_MANIFEST.json",
        ]
    ]
    tree = ET.parse(OUT / "synthetic_results.xml")
    totals = {
        k: sum(int(s.get(k, "0")) for s in tree.iter("testsuite"))
        for k in ("tests", "failures", "errors", "skipped")
    }
    own = [x for x in tree.iter("testcase") if "integration_v9" in x.get("classname", "")]
    assert len(own) >= 64 and totals["tests"] >= 335
    assert not any(totals[k] for k in ("failures", "errors", "skipped"))
    refs = [
        save(
            "input_authority_manifest.json",
            dict(inputs=inputs, authorities=authorities, preserved_source_blobs=preserved),
        )
    ]
    routes = {
        "HARMONIC": "NATIVE_PIVOTS_ATR_TO_V8_PROJECTION_CONFIRMATION_AND_V7_PARTIAL_KERNEL",
        "ELLIOTT": "NATIVE_MULTI_DEGREE_PIVOTS_WITH_SUPPLIED_RECURSIVE_PROOF_TO_V8_COUNT_BOOK",
        "WYCKOFF": "BOUND_SOURCE_ACTIVITY_PIVOTS_RANGE_SEGMENTS_TO_V8_READINESS_PNF_AND_STAGE_ADD",
        "ICT": "ACTUAL_THREE_BAR_FVG_AND_BOUND_AUCTION_CHAIN_TO_NATIVE_SESSION_OWNER",
        "CLASSICAL": "UNCHANGED_EXPLICIT_V7_SOURCE_ENVELOPE_ROUTE",
        "DOW": "NATIVE_BREADTH_AND_LEADER_TREND_FROM_COMPLETE_PIT_FRAME_CONTEXT_ONLY",
        "H1": "UNCHANGED_CLASSICAL_OWNER_V7_ENVELOPE_ROUTE",
        "H2": "AUCTION_CHAIN_PRIOR_DAILY_CURRENT_4H_ACCEPTANCE_SEPARATE_HTF_OWNER",
        "H3": "SAME_CHECKPOINT_PROOF_COUNT_AND_LIVE_GEOMETRIC_LOCATION_COUNT_OWNER",
    }
    refs.append(
        save(
            "producer_binding_matrix.json",
            {
                "routes": routes,
                "technical_routes_implemented": 9,
                "historical_market_producer_recertification": False,
                "supplied_semantic_claims_independently_certified": False,
                "proof_requirement_is_not_an_automatic_full_count_or_phase_detector": True,
                "dow_funded": False,
                "funded_grammars": [],
                "H3_test_scope": "ISOLATED_COMPOSITION_NOT_HISTORICAL_CROSS_SCHOOL_SOURCE_STREAM",
            },
        )
    )
    version_sha = hashlib.sha256(json.dumps(inputs, sort_keys=True).encode()).hexdigest().upper()
    refs.append(
        save(
            "reserve_readiness.json",
            {
                "source_version_manifest_sha256": version_sha,
                "independent_review": "NOT_EXECUTED",
                "old_reserve_certifies_changed_version": False,
                "reserve_chart_packet_generated": False,
                "blocked_by": [
                    "NEW_VERSION_INDEPENDENT_RESERVE_REVIEW_NOT_AVAILABLE",
                    "HISTORICAL_EXCHANGE_RULES_NOT_AVAILABLE",
                    "SUPPLIED_SEMANTIC_PRODUCERS_NOT_HISTORICALLY_RECERTIFIED",
                ],
                "gate2_closed": False,
                "gate3_ready": False,
            },
        )
    )
    refs.append(
        save(
            "evidence_snapshot.json",
            dict(
                starting_head=START,
                starting_revision=780,
                task_id=TASK,
                tests=totals,
                new_tests=len(own),
                junit=binding("governance/producer_integration_bundle_v9/synthetic_results.xml"),
                inputs=inputs,
                authorities=authorities,
                all_old_sources_unchanged=True,
                all_inputs_synthetic=True,
                market_data_rows_accessed=False,
            ),
        )
    )
    refs.append(
        save(
            "gap_status_delta.json",
            {
                "original_eleven_remaining_gaps_fully_closed": False,
                "producer_integration": "PARTIAL_WITH_NEW_OPT_IN_SOURCE_GRAPH_AND_KERNEL_BINDING",
                "reserve_fidelity": "OPEN_INDEPENDENT_REVIEW",
                "historical_exchange_rules": "OPEN_AUTHORITY",
                "dow_live_broad_context": (
                    "SYNTHETIC_SOURCE_ADAPTER_IMPLEMENTED_NOT_HISTORICALLY_RECERTIFIED"
                ),
                "economic_value": "NOT_TESTED",
                "opportunity_selector": "INHERITED_NOT_NEW_VALUE_MODEL",
            },
        )
    )
    result = {
        "task_id": TASK,
        "classification": (
            "PACKAGE2_CAUSAL_INTEGRATION_TECHNICAL_PASS_WITH_UNFUNDED_AUTHORITY_BOUNDARY"
        ),
        "technical_package_status": "PASS",
        "full_authority_package_status": "NOT_CLOSED",
        "synthetic_tests": totals,
        "new_package_tests": len(own),
        "artifact_bindings": refs,
        "protocol_sha256": sha(OUT / "research_protocol.json"),
        "old_sources_unchanged": True,
        "market_rows_accessed": False,
        "2024_rows_accessed": False,
        "2025_rows_accessed": False,
        "economic_replay_executed": False,
        "economic_conclusion": "NONE",
        "model_fit": False,
        "threshold_search": False,
        "production_changed": False,
        "research_push": False,
        "independent_review_executed": False,
        "funded_grammars": [],
        "ready_for_gate3_replay": False,
        "all_original_eleven_gaps_closed": False,
        "next_bottleneck": (
            "V9_SEMANTIC_PRODUCER_AUTHORITY_AND_EXACT_VERSION_"
            "INDEPENDENT_RESERVE_AND_HISTORICAL_QUANTITY"
        ),
    }
    save("canonical_result.json", result)
    save(
        "governance_report.json",
        dict(
            task_id=TASK,
            objective="TECHNICAL_OPT_IN_INTEGRATION_ONLY_PASS",
            full_authority_closure=False,
            independent_attestation=False,
            economic_qualification=False,
            charter_start_revision=780,
            complete_verify="REQUIRED_AFTER_IMPLEMENTATION_COMMIT",
            governance_sync="REQUIRED_BEFORE_NEXT_GOVERNED_TASK",
            unrelated_untracked_files="PRESERVED_NOT_STAGED",
        ),
    )
    print(
        json.dumps(
            dict(result_sha256=sha(OUT / "canonical_result.json"), tests=totals, new_tests=len(own))
        )
    )


if __name__ == "__main__":
    main()
