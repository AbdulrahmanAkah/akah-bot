"""Source-bound repair certificate; no economic or market qualification."""

from __future__ import annotations

import hashlib
import json
import subprocess
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "governance/source_integrity_closure_v11"
TASK = "AKAH_V11_REVIEW_SOURCE_INTEGRITY_AND_EXPORT_CLOSURE"
START = "23020400d26d24dfa02decfbca2f74d0086812f7"
REVIEW = Path("C:/Users/abdul/Downloads/AKAH_REV782_V10_INDEPENDENT_REVIEW.zip")
REVIEW_SHA = "FA6D3758A0811D6CA70EEE3271EC7D35D9A023708D6327EEABE66285F86A3D45"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest().upper()


def ref(path):
    path = Path(path)
    if not path.is_absolute():
        path = ROOT / path
    name = path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else str(path)
    return dict(path=name, sha256=sha(path), bytes=path.stat().st_size)


def save(name, value):
    path = OUT / name
    path.write_text(
        json.dumps(value, sort_keys=True, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    return ref(path)


def totals(path):
    tree = ET.parse(path)
    counts = {
        k: sum(int(s.get(k, "0")) for s in tree.iter("testsuite"))
        for k in ("tests", "errors", "failures", "skipped")
    }
    assert counts == dict(tests=465, errors=0, failures=0, skipped=0), counts
    assert sum("integration_v11" in t.get("classname", "") for t in tree.iter("testcase")) == 68
    return counts


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def main():
    active = json.loads((ROOT / ".akah_bot/active_task.json").read_text())
    assert active["task_id"] == TASK and active["starting_charter_revision"] == 782
    assert active["starting_head"] == START and git("rev-parse", "HEAD") == START
    assert not git("diff", "--name-only") and not git("diff", "--cached", "--name-only")
    assert sha(REVIEW) == REVIEW_SHA
    with zipfile.ZipFile(REVIEW) as archive:
        manifest = json.loads(archive.read("MANIFEST.json"))
        members = []
        for name, metadata in manifest.items():
            raw = archive.read(name)
            assert hashlib.sha256(raw).hexdigest().upper() == metadata["sha256"]
            members.append(dict(path=name, sha256=metadata["sha256"], bytes=len(raw)))
        review = json.loads(archive.read("AKAH_REV782_V10_INDEPENDENT_REVIEW.json"))
    save("locked_review_input_snapshot.json", review)
    old = json.loads(
        (ROOT / "governance/four_source_repairs_v10/input_authority_manifest.json").read_text()
    )
    preserved = old["inputs"] + old["preserved_sources_and_authorities"]
    for item in preserved:
        assert sha(ROOT / item["path"]) == item["sha256"], item["path"]
    sources = []
    for directory in (
        "src/spotbot/research/multi_school_fidelity/integration_v11",
        "tests/research/integration_v11",
        "scripts/research/integration_v11",
    ):
        for path in sorted((ROOT / directory).iterdir()):
            if path.suffix == ".py" or path.name == ".gitattributes":
                if path.suffix == ".py":
                    compile(path.read_text(encoding="utf-8-sig"), str(path), "exec")
                assert (
                    subprocess.run(
                        ["git", "check-ignore", "--", str(path.relative_to(ROOT))],
                        cwd=ROOT,
                        capture_output=True,
                    ).returncode
                    == 1
                )
                sources.append(ref(path))
    sources.extend(
        ref(OUT / name)
        for name in (
            "research_protocol.json",
            "IMPLEMENTATION_CONTRACT.md",
            "REVIEW_TASK.md",
            "SUMMARY.md",
            ".gitattributes",
        )
    )
    version = hashlib.sha256(json.dumps(sources, sort_keys=True).encode()).hexdigest().upper()
    repository_tests = totals(OUT / "synthetic_results.xml")
    export_tests = totals(OUT / "EXPORTED_TEST_RESULTS.xml")
    isolation = json.loads((OUT / "EXPORT_ISOLATION_RESULT.json").read_text())
    assert isolation["exit_code"] == 0 and not isolation["editable_source_fallback"]
    assert isolation["arch_version"] == "8.0.0" and not isolation["market_rows_read"]
    stage = Path(json.loads((OUT / "export_receipt.json").read_text())["stage"])
    for item in json.loads((OUT / "EXPORT_INPUT_MANIFEST.json").read_text()):
        assert sha(stage / item["path"]) == item["sha256"]
        if item["path"].startswith(("src/", "tests/", "scripts/", "governance/")):
            assert sha(ROOT / item["path"]) == item["sha256"]
    bindings = []
    bindings.append(
        save(
            "input_authority_manifest.json",
            dict(
                source_version_sha256=version,
                inputs=sources,
                preserved_sources_and_authorities=preserved,
                independent_review_archive=ref(REVIEW),
                independent_review_members=members,
            ),
        )
    )
    repairs = [
        dict(
            id="F1",
            status="CLOSED_TECHNICALLY",
            defect="PREBIND_ADD_STOP_SCALAR_UNBOUND",
            proof="Immutable native LPS bar + original stage stop + actual fill receipt; "
            "exact source derivation at bind and actual kernel; B0 unchanged",
        ),
        dict(
            id="F2",
            status="CLOSED_TECHNICALLY",
            defect="PREBIND_PIT_BOOLEAN_CAN_BE_FLIPPED",
            proof="Explicit Known[PitMembership], live source parents, pair/checkpoint/period "
            "parity and false preservation through actual kernel; caller bool denied",
        ),
        dict(
            id="F3",
            status="CLOSED_TECHNICALLY",
            defect="SHALLOW_FROZEN_PRODUCED_MUTABLE_DICTIONARIES",
            proof="Recursive immutable payload + exact emission seal; full issue fields "
            "checked before bind and actual admission; parent/router liveness",
        ),
        dict(
            id="EXPORT_DEPENDENCIES",
            status="CLOSED_TECHNICALLY",
            defect="MISSING_ARCH_AND_SPOTBOT_DATA_IN_OLD_HANDOFF",
            proof="Exact dependency lock arch8.0.0 + data/core source; 465 exported "
            "tests pass in python -S with no editable spotbot fallback",
        ),
    ]
    bindings.append(
        save(
            "repair_closure_matrix.json",
            dict(
                repairs=repairs,
                supplied_review_items_closed_in_synthetic_scope=True,
                V10_unconditional_R2_closure="INVALIDATED_BY_LOCKED_REVIEW_SUPERSEDED_BY_V11",
                V10_R1_R3_R4="UNCHANGED_WITH_ORIGINAL_SCOPE_NOT_INDEPENDENTLY_RECERTIFIED",
                old_versions_preserved=True,
                targets_risk_grammar_changed=False,
            ),
        )
    )
    blockers = [
        "V11_INDEPENDENT_CODE_SPEC_REVIEW_NOT_EXECUTED",
        "EXACT_VERSION_HISTORICAL_SEMANTIC_PRODUCERS_NOT_RECERTIFIED",
        "FRESH_UNUSED_MARKET_RESERVE_NOT_MATERIALIZED_OR_REVIEWED",
        "HISTORICAL_EXCHANGE_RULE_SOURCE_COVERAGE_NOT_CERTIFIED_BY_THIS_TASK",
    ]
    bindings.append(
        save(
            "evidence_snapshot.json",
            dict(
                task_id=TASK,
                starting_head=START,
                starting_revision=782,
                source_version_sha256=version,
                source_inputs=sources,
                repository_tests=repository_tests,
                exported_tests=export_tests,
                new_tests=68,
                old_regressions=397,
                old_sources_unchanged=True,
                synthetic_only=True,
                independent_reviewer_for_V11=False,
                warnings=dict(
                    count=12,
                    source="UNCHANGED_ARCH_CONSTANT_SYNTHETIC_SERIES_TEST",
                    gates_weakened=False,
                ),
                execution_routes=[
                    "HARMONIC",
                    "WYCKOFF_STAGE_AND_LPS_ADD",
                    "WYCKOFF_NO_SPRING",
                    "WYCKOFF_REACCUMULATION",
                    "ELLIOTT",
                    "ICT_SESSION",
                    "H2",
                    "CLASSICAL_SEALED_LEGACY",
                    "H1_SEALED_LEGACY",
                    "H3_ISOLATED_COMPOSITION",
                ],
                Dow="UNCHANGED_CONTEXT_ONLY",
                historical_certification=False,
            ),
        )
    )
    bindings.append(
        save(
            "governance_report.json",
            dict(
                task_id=TASK,
                technical_closure="PASS_SCOPED_TO_SUPPLIED_REVIEW_DEFECTS",
                full_market_fidelity_closure=False,
                funding_authorized=False,
                begin="PASS_AFTER_REV782_VERIFIED_REMOTE_SYNC",
                complete_verify="REQUIRED_AFTER_IMPLEMENTATION_COMMIT",
                final_governance_sync="REQUIRED_AFTER_COMPLETE_VERIFY",
                research_push=False,
                unrelated_user_files_preserved=True,
            ),
        )
    )
    for name in (
        "synthetic_results.xml",
        "EXPORTED_TEST_RESULTS.xml",
        "EXPORT_INPUT_MANIFEST.json",
        "EXPORT_ISOLATION_RESULT.json",
        "export_receipt.json",
        "DEPENDENCY_LOCK.json",
        "requirements-review-lock.txt",
        "exported_tests_stdout.txt",
        "exported_tests_stderr.txt",
        "locked_review_input_snapshot.json",
    ):
        bindings.append(ref(OUT / name))
    result = dict(
        task_id=TASK,
        classification="V11_SOURCE_INTEGRITY_AND_EXPORT_TECHNICAL_CLOSURE_PASS",
        technical_status="PASS",
        review_items_closed=True,
        new_tests=68,
        repository_tests=repository_tests,
        exported_tests=export_tests,
        source_version_sha256=version,
        artifact_bindings=bindings,
        protocol_sha256=sha(OUT / "research_protocol.json"),
        old_sources_unchanged=True,
        independent_V11_review=False,
        unused_market_reserve_ready=False,
        ready_for_gate3_replay=False,
        funded_grammars=[],
        remaining_blockers=blockers,
        economic_conclusion="NONE",
        economic_replay_executed=False,
        market_rows_accessed=False,
        pnl_read=False,
        model_fit=False,
        threshold_search=False,
        production_changed=False,
        research_branch_push=False,
        **{"2024_rows_accessed": False, "2025_rows_accessed": False},
        next_bottleneck="V11_INDEPENDENT_SOURCE_INTEGRITY_REVIEW_AND_HISTORICAL_RESERVE_RECERTIFICATION",
    )
    save("canonical_result.json", result)
    print(
        json.dumps(
            dict(
                technical="PASS",
                tests=repository_tests,
                exported_tests=export_tests,
                source_version_sha256=version,
                canonical_sha256=sha(OUT / "canonical_result.json"),
                gate3_ready=False,
            )
        )
    )


if __name__ == "__main__":
    main()
