"""Persist synthetic engineering evidence. No market readers or economic engine.

Run only inside the active V8 governed mission, after the exact tests PASS.
Output generation is deterministic except for test runner's original durations.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import xml.etree.ElementTree as ET
from dataclasses import asdict
from pathlib import Path

from spotbot.research.multi_school_fidelity.harmonic_contract_v8 import BASE_URL, FAMILIES

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "governance/school_ownership_bundle_v8"
TASK = "AKAH_PACKAGE1_FOUR_SCHOOL_OWNERSHIP_CONTRACT_CLOSURE_V8"
START = "c6923d86f9f34f7dfb4a0834efdfb79b4997cb70"
SOURCE_DIR = "src/spotbot/research/multi_school_fidelity"
MODULES = [
    "school_contract_common_v8.py",
    "harmonic_contract_v8.py",
    "elliott_contract_v8.py",
    "wyckoff_contract_v8.py",
    "ict_h2_contract_v8.py",
]
NEW_FILES = [f"{SOURCE_DIR}/{n}" for n in MODULES] + [
    "tests/research/test_school_ownership_bundle_v8.py",
    "scripts/research/certify_school_ownership_bundle_v8.py",
    "governance/school_ownership_bundle_v8/research_protocol.json",
    "governance/school_ownership_bundle_v8/IMPLEMENTATION_CONTRACT.md",
    "governance/school_ownership_bundle_v8/SUMMARY.md",
    "src/spotbot/research/multi_school_fidelity/.gitattributes",
    "tests/research/.gitattributes",
    "scripts/research/.gitattributes",
    "governance/school_ownership_bundle_v8/.gitattributes",
]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest().upper()


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT).decode().strip()


def save(name, value):
    path = OUT / name
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return {"path": path.relative_to(ROOT).as_posix(), "sha256": sha(path)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ack-synthetic-only", action="store_true", required=True)
    args = parser.parse_args()
    assert args.ack_synthetic_only
    active = json.loads((ROOT / ".akah_bot/active_task.json").read_text(encoding="utf-8"))
    assert active["task_id"] == TASK and active["starting_head"] == START
    assert git("branch", "--show-current") == active["starting_branch"]
    protocol = json.loads((OUT / "research_protocol.json").read_text(encoding="utf-8"))
    assert protocol["task_id"] == TASK and protocol["market_data_access"] == "NONE"
    # Existing tracked code is immutable. Never enumerate/open market datasets.
    old_sources = [
        p
        for p in git("ls-tree", "-r", "--name-only", START, "--", SOURCE_DIR).splitlines()
        if p.endswith(".py")
    ]
    for p in old_sources:
        assert not git("diff", "--name-only", START, "--", p), "OLD_SOURCE_CHANGED:" + p
    tracked_dirty = git("diff", "--name-only")
    assert not tracked_dirty, "EXISTING_TRACKED_SOURCE_CHANGED"
    assert not git("diff", "--cached", "--name-only"), "INDEX_NOT_CLEAN_BEFORE_STAGE"
    for p in NEW_FILES:
        checked = subprocess.run(["git", "check-ignore", "--", p], cwd=ROOT, capture_output=True)
        assert checked.returncode == 1, "OUTPUT_NOT_STAGEABLE:" + p
    junit = ET.parse(OUT / "synthetic_results.xml")
    suites = list(junit.iter("testsuite"))
    totals = {
        k: sum(int(s.get(k, "0")) for s in suites)
        for k in ("tests", "failures", "errors", "skipped")
    }
    assert totals["tests"] == 271 and not any(totals[k] for k in ("failures", "errors", "skipped"))
    cases = list(junit.iter("testcase"))
    own = [c for c in cases if c.get("classname", "").endswith("test_school_ownership_bundle_v8")]
    assert len(own) == 83
    # All XML inputs are synthetic fixture outputs, not historical outcome PnL.
    source_inputs = [dict(path=p, sha256=sha(ROOT / p)) for p in NEW_FILES]
    for path in OUT.iterdir():
        if path.is_file():
            checked = subprocess.run(
                ["git", "check-ignore", "--", str(path.relative_to(ROOT))],
                cwd=ROOT,
                capture_output=True,
            )
            assert checked.returncode == 1, "GENERATED_OUTPUT_NOT_STAGEABLE:" + path.name
    old_manifest = [
        dict(path=p, sha256=sha(ROOT / p), original_blob=git("rev-parse", f"{START}:{p}"))
        for p in old_sources
    ]
    matrix = {}
    for family, f in FAMILIES.items():
        rule = asdict(f)
        rule.update(
            source_url=BASE_URL + f.source_slug,
            implementation="harmonic_contract_v8.project/HarmonicContract",
            stop="GARTLEY_X_OR_BAT_1_13_XA_ELSE_TERMINAL_EXTREME_OUTSIDE_ZONE_PLUS_TICK",
            trigger="LATER_CLOSE_BEYOND_TERMINAL_EXTREME_BAR",
            fraction_targets=[0.5, 0.5],
            reaction_levels=[0.382, 0.618],
            type2="LATER_POST_COMPLETION_RETEST_THEN_LATER_CONFIRMATION",
            status="EXPLICIT_AKAH_ADAPTATION_NOT_UNIVERSAL_SOURCE_DOCTRINE",
            short_status="DIAGNOSTIC_ONLY_NOT_EXECUTABLE_SPOT_SHORT",
        )
        matrix[family] = rule
    refs = [save("family_matrix.json", matrix)]
    primary = [
        dict(
            url=BASE_URL + f.source_slug,
            family=n,
            source_role="DEFINING_PATTERN_MEASUREMENTS",
            immutable_web_snapshot_sha256=None,
            limitation="PUBLIC_URL_NOT_A_HASHED_FULL_BOOK_OR_UNIQUE_MANAGEMENT_AUTHORITY",
        )
        for n, f in FAMILIES.items()
    ]
    primary.extend(
        [
            {
                "url": "https://www.elliottwave.com/waveopedia/impulse/",
                "source_role": "IMPULSE_HARD_RULES_AND_SUBDIVISIONS",
            },
            {
                "url": "https://www.elliottwave.com/waveopedia/corrective-waves/",
                "source_role": "CORRECTIVE_FAMILY_GRAMMARS",
            },
            {
                "url": "https://www.elliottwave.com/waveopedia/zigzags/",
                "source_role": "PARENT_CHILD_CORRECTIVE_NESTING",
            },
            {
                "url": "https://www.wyckoffanalytics.com/wyckoff-method/",
                "source_role": "FRESH_CAUSE_HORIZONTAL_COUNT_AND_BRANCH_READINESS",
            },
        ]
    )
    refs.append(
        save(
            "source_authority.json",
            dict(
                primary_references=primary,
                local_code_inputs=source_inputs,
                source_ambiguities=[
                    "Butterfly complementary projections vary in public text",
                    "Crab page includes Deep-Crab prose; not a defining regular B rule",
                    "Public pages do not supply one unique stop/management table for every family",
                ],
                explicit_engineering_choices=[
                    "Harmonic bounded complementary matrix and structural terminal stops",
                    "Elliott timeframe degrees, finite leaves, bounded flat/triangle profiles",
                    "Wyckoff logarithmic percentage PNF rather than fixed-box arithmetic",
                    "H2 separate 4H AKAH thesis rather than official ICT swing doctrine",
                ],
                doctrine_fidelity_certificate=False,
                funding_authority=False,
                external_design_archive=dict(
                    path="C:/Users/abdul/Downloads/AKAH_STATEFUL_FULL_SYSTEMS_DESIGN_V1.zip",
                    sha256="8A38DE43A59B5EFA79F554C0F34D20556AC810147DF702C18575338A46B15904",
                    role="PREEXISTING_DESIGN_ONLY_NOT_FULL_FIDELITY_CERTIFICATE",
                ),
            ),
        )
    )
    profiles = {
        "harmonic_family_management": {
            "status": "COMPLETE_EXPLICIT_ADAPTATION_CONTRACT",
            "families": 9,
            "grammar": "FS_HARMONIC_CAUSAL_ADAPTATION_V8",
            "owner": "HARMONIC_TYPE_I_OR_TYPE_II",
        },
        "elliott_parent_child": {
            "status": "COMPLETE_EXPLICIT_ADAPTATION_CONTRACT",
            "grammars": 6,
            "grammar": "FS_ELLIOTT_PROOF_RESUMPTION_V8",
            "owner": "ELLIOTT_COMMON_COUNT_OWNER",
        },
        "wyckoff_reaccumulation": {
            "status": "COMPLETE_EXPLICIT_ADAPTATION_CONTRACT",
            "branches": 3,
            "grammar": "FS_WYCKOFF_FRESH_CAUSE_V8",
            "owner": "WYCKOFF_RANGE_OWNER",
        },
        "ict_h2_trend_owner": {
            "status": "COMPLETE_EXPLICIT_ADAPTATION_CONTRACT",
            "distinct_owners": 2,
            "grammars": ["FS_ICT_SESSION_OWNER_V8", "HYB_FAILED_AUCTION_HTF_OWNER_V8"],
        },
    }
    refs.append(
        save(
            "profile_binding.json",
            dict(
                profiles=profiles,
                entry_clock="COMPLETED_CAUSAL_DECISION_THEN_NEXT_HOURLY_OPEN",
                old_v6_v7_allowlists_unchanged=True,
                funded_grammars=[],
                gate3_ready=False,
                producer_binding="NOT_CERTIFIED_BY_SYNTHETIC_CONTRACT_TESTS",
            ),
        )
    )
    original = json.loads(
        (ROOT / "governance/structural_gap_closure_v7/gap_adjudication.json").read_text(
            encoding="utf-8"
        )
    )
    refs.append(
        save(
            "gap_status_delta.json",
            dict(
                original_gap_statuses_unchanged=original,
                new_profile_contracts=profiles,
                distinction=(
                    "Bounded adaptation completion does not certify full-school "
                    "fidelity, market producers or economic value"
                ),
                original_fully_closed_gap_count=1,
                original_remaining_gap_count=11,
                package1_technical_profiles_complete=4,
                package1_declared_implementation_branches_unresolved=0,
                independent_review="NOT_EXECUTED_NOT_INFERRED_FROM_OLD_RESERVE",
            ),
        )
    )
    refs.append(
        save(
            "evidence_snapshot.json",
            dict(
                starting_head=START,
                starting_revision=779,
                task_id=TASK,
                source_inputs=source_inputs,
                preserved_source_bindings=old_manifest,
                tests=dict(
                    totals,
                    new_package_tests=len(own),
                    junit_sha256=sha(OUT / "synthetic_results.xml"),
                ),
                market_rows_accessed=False,
                economic_replay_executed=False,
                original_tracked_code_unchanged=True,
                all_new_outputs_stageable=True,
                input_provenance_type="SYNTHETIC_ENGINEERING_NOT_ECONOMIC",
            ),
        )
    )
    result = dict(
        task_id=TASK,
        classification="PACKAGE1_FOUR_EXPLICIT_CAUSAL_OWNERSHIP_CONTRACTS_TECHNICAL_PASS",
        package_status="PASS",
        profiles_complete=4,
        implementation_branch_gaps_in_declared_scope=0,
        synthetic_tests=totals,
        new_package_tests=len(own),
        artifact_bindings=refs,
        protocol_sha256=sha(OUT / "research_protocol.json"),
        old_sources_unchanged=True,
        production_changed=False,
        market_rows_accessed=False,
        **{"2024_rows_accessed": False, "2025_rows_accessed": False},
        economic_replay_executed=False,
        economic_conclusion="NONE",
        model_fit=False,
        threshold_search=False,
        funded_grammars=[],
        ready_for_gate3_replay=False,
        all_original_eleven_gaps_closed=False,
        original_remaining_gap_count=11,
        next_bottleneck="V8_ACTUAL_PRODUCER_ROUTER_EXECUTION_BINDING_AND_INDEPENDENT_RESERVE_CERTIFICATION",
        research_push=False,
        governance_sync_required_after_complete=True,
    )
    refs.append(save("canonical_result.json", result))
    refs.append(
        save(
            "governance_report.json",
            dict(
                task_id=TASK,
                implementation_objective="PASS_WITHIN_EXPLICIT_PROSPECTIVE_PROFILE_SCOPE",
                doctrine_scope="BOUNDED_MECHANICAL_ADAPTATIONS_NOT_EXHAUSTIVE_SCHOOL_CERTIFICATION",
                independent_gate2="NOT_RUN",
                gate3="NOT_ARMED",
                complete_verify="REQUIRED_AFTER_IMPLEMENTATION_COMMIT",
                charter_start_revision=779,
                input_start_head=START,
                governance_sync="REQUIRED_BEFORE_NEXT_GOVERNED_TASK",
                unrelated_files="PRESERVED_NOT_STAGED",
                no_market_replay=True,
            ),
        )
    )
    print(
        json.dumps(
            dict(
                result_sha256=sha(OUT / "canonical_result.json"),
                tests=totals,
                new_tests=len(own),
                artifacts=refs,
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
