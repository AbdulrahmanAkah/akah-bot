"""Hash-bound technical closure of two confirmed source-lineage findings."""

from __future__ import annotations

import hashlib
import json
import subprocess
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "governance/causal_lineage_closure_v12"
TASK = "AKAH_V12_H3_PARENT_SEAL_AND_HARMONIC_COMPLETION_LINEAGE_CLOSURE"
START = "203ee785c1546937172aaee6f487f6b76821d3ad"
REVIEW = Path("C:/Users/abdul/Downloads/AKAH_REV783_V11_INDEPENDENT_REVIEW_RESULT.zip")
REVIEW_SHA = "D9B94E84AC1F5B363E3776B1B5FD7AC7D93E6077A74C513FC1F7DC859A264148"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest().upper()


def ref(path):
    path = Path(path)
    if not path.is_absolute():
        path = ROOT / path
    return dict(
        path=path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else str(path),
        sha256=sha(path),
        bytes=path.stat().st_size,
    )


def save(name, value):
    path = OUT / name
    path.write_text(
        json.dumps(value, sort_keys=True, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    return ref(path)


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def test_totals(path):
    tree = ET.parse(path)
    total = {
        key: sum(int(s.get(key, "0")) for s in tree.iter("testsuite"))
        for key in ("tests", "failures", "errors", "skipped")
    }
    assert total == dict(tests=494, failures=0, errors=0, skipped=0), total
    assert sum("integration_v12" in t.get("classname", "") for t in tree.iter("testcase")) == 29
    return total


def main():
    active = json.loads((ROOT / ".akah_bot/active_task.json").read_text())
    assert active["task_id"] == TASK and active["starting_charter_revision"] == 783
    assert active["starting_head"] == START and git("rev-parse", "HEAD") == START
    assert not git("diff", "--name-only") and not git("diff", "--cached", "--name-only")
    assert sha(REVIEW) == REVIEW_SHA
    members = []
    with zipfile.ZipFile(REVIEW) as archive:
        for name, item in json.loads(archive.read("MANIFEST.json")).items():
            raw = archive.read(name)
            assert hashlib.sha256(raw).hexdigest().upper() == item["sha256"]
            members.append(dict(path=name, sha256=item["sha256"], bytes=len(raw)))
        review = json.loads(archive.read("AKAH_REV783_V11_INDEPENDENT_LOCKED_REVIEW.json"))
    assert review["locked"] and not review["human_attestation"]
    assert review["packet_sha256"] == sha(
        "C:/Users/abdul/Downloads/AKAH_REV783_V11_INDEPENDENT_REVIEW.zip"
    )
    assert len(review["new_remaining_findings"]) == 2
    review_ref = save("locked_v11_independent_review_snapshot.json", review)
    old_path = ROOT / "governance/source_integrity_closure_v11/input_authority_manifest.json"
    old = json.loads(old_path.read_text())
    preserved = [
        *old["inputs"],
        *old["preserved_sources_and_authorities"],
        ref(old_path),
        ref("governance/source_integrity_closure_v11/canonical_result.json"),
    ]
    for item in preserved:
        assert sha(ROOT / item["path"]) == item["sha256"], item["path"]
    preflight = json.loads((OUT / "preflight_reproduction_result.json").read_text())
    assert preflight["findings_confirmed"] == ["F4", "F5"] and len(preflight["reproductions"]) == 3
    assert preflight["preflight_script_sha256"] == sha(OUT / "preflight_reproduction_source.txt")
    sources = []
    for directory in (
        "src/spotbot/research/multi_school_fidelity/integration_v12",
        "tests/research/integration_v12",
        "scripts/research/integration_v12",
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
    local = test_totals(OUT / "synthetic_results.xml")
    exported = test_totals(OUT / "EXPORTED_TEST_RESULTS.xml")
    isolation = json.loads((OUT / "EXPORT_ISOLATION_RESULT.json").read_text())
    assert isolation["exit_code"] == 0 and not isolation["editable_source_fallback"]
    assert not isolation["market_rows_read"] and isolation["arch_version"] == "8.0.0"
    stage = Path(json.loads((OUT / "export_receipt.json").read_text())["stage"])
    for item in json.loads((OUT / "EXPORT_INPUT_MANIFEST.json").read_text()):
        assert sha(stage / item["path"]) == item["sha256"]
        if item["path"].startswith(("src/", "tests/", "scripts/", "governance/")):
            assert sha(ROOT / item["path"]) == item["sha256"]
    bindings = [review_ref]
    bindings.append(
        save(
            "input_authority_manifest.json",
            dict(
                source_version_sha256=version,
                inputs=sources,
                preserved_sources_and_authorities=preserved,
                review_archive=ref(REVIEW),
                review_members=members,
            ),
        )
    )
    bindings.append(
        save(
            "repair_closure_matrix.json",
            dict(
                repairs=[
                    dict(
                        id="F4",
                        status="CLOSED_TECHNICALLY",
                        proof="Exact count and location emission IDs "
                        "in H3 thesis/evidence/seal/kernel "
                        "guard. Each revocation denies compose/bind/open/actual admission.",
                    ),
                    dict(
                        id="F5",
                        status="CLOSED_TECHNICALLY",
                        proof="Exact actual Type-I closure receipt retained by producer, "
                        "clock/source/owner "
                        "bound into Type-II thesis/evidence/seal/actual guard; revocation/missing "
                        "receipt cannot be replaced by mutable state.",
                    ),
                ],
                original_F1_F2_F3="CONFIRMED_BY_LOCKED_INDEPENDENT_V11_REVIEW_AND_RETAINED",
                broad_V11_full_lineage_claim="WEAKENED_BY_F4_F5_SUPERSEDED_IN_V12_TECHNICAL_SCOPE",
                targets_grammar_risk_prices_costs_changed=False,
                live_revocation_semantics_explicit=True,
                new_independent_V12_review=False,
            ),
        )
    )
    blockers = [
        "V12_INDEPENDENT_CODE_SPEC_REVIEW_NOT_EXECUTED",
        "EXACT_VERSION_HISTORICAL_SEMANTIC_PRODUCERS_NOT_RECERTIFIED",
        "FRESH_UNUSED_MARKET_RESERVE_NOT_MATERIALIZED_OR_REVIEWED",
        "HISTORICAL_EXCHANGE_RULE_SOURCE_COVERAGE_NOT_CERTIFIED",
    ]
    bindings.append(
        save(
            "evidence_snapshot.json",
            dict(
                task_id=TASK,
                starting_head=START,
                starting_revision=783,
                source_version_sha256=version,
                local_tests=local,
                exported_tests=exported,
                new_tests=29,
                unchanged_regressions=465,
                old_sources_unchanged=True,
                preflight=ref(OUT / "preflight_reproduction_result.json"),
                corrections="F4/F5_ONLY_NO_TRADING_RULE_OR_OUTCOME_CHANGE",
                independent_V11_review=dict(
                    identity=review["reviewer_id"],
                    human_attestation=False,
                    findings_F1_F2_F3="CONFIRMED",
                    new_findings_F4_F5="LOCALLY_REPRODUCED",
                    independent_arch_dependent_rerun=False,
                    limitation="PRESERVED_NOT_RELABELLED_AS_PASS",
                ),
                synthetic_only=True,
                warnings=dict(
                    count=12,
                    source="UNCHANGED_ARCH_CONSTANT_SYNTHETIC_TEST",
                    estimator_substituted=False,
                    gates_weakened=False,
                ),
            ),
        )
    )
    bindings.append(
        save(
            "governance_report.json",
            dict(
                task_id=TASK,
                technical_F4_F5_closure="PASS",
                scientific_conclusion="NONE",
                begin="PASS_AFTER_VERIFIED_REV783_REMOTE_MANIFEST",
                complete_verify="REQUIRED_AFTER_IMPLEMENTATION_COMMIT",
                final_governance_sync="REQUIRED_AFTER_COMPLETE_VERIFY",
                historical_reserve_or_production_certified=False,
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
        "preflight_reproduction_result.json",
        "preflight_reproduction_source.txt",
    ):
        bindings.append(ref(OUT / name))
    result = dict(
        task_id=TASK,
        classification="V12_F4_F5_CAUSAL_LINEAGE_TECHNICAL_CLOSURE_PASS",
        technical_status="PASS",
        review_findings_confirmed=["F4", "F5"],
        review_findings_closed=True,
        new_tests=29,
        local_tests=local,
        exported_tests=exported,
        source_version_sha256=version,
        artifact_bindings=bindings,
        protocol_sha256=sha(OUT / "research_protocol.json"),
        old_sources_unchanged=True,
        independent_V11_review=True,
        independent_V12_review=False,
        ready_for_gate3_replay=False,
        unused_market_reserve_ready=False,
        funded_grammars=[],
        remaining_blockers=blockers,
        economic_conclusion="NONE",
        market_rows_accessed=False,
        pnl_read=False,
        economic_replay_executed=False,
        model_fit=False,
        threshold_search=False,
        production_changed=False,
        research_branch_push=False,
        **{"2024_rows_accessed": False, "2025_rows_accessed": False},
        next_bottleneck="V12_INDEPENDENT_LINEAGE_REVIEW_AND_HISTORICAL_PRODUCER_UNUSED_RESERVE_RECERTIFICATION",
    )
    save("canonical_result.json", result)
    print(
        json.dumps(
            dict(
                technical="PASS",
                tests=local,
                exported_tests=exported,
                canonical_sha256=sha(OUT / "canonical_result.json"),
                source_version_sha256=version,
                ready_for_gate3=False,
            )
        )
    )


if __name__ == "__main__":
    main()
