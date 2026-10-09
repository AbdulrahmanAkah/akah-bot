# ruff: noqa: E501 -- generated evidence report literals.
"""Finalize engineering evidence only. Never load raw prices or run a policy."""

from __future__ import annotations

import argparse
import ast
import csv
import importlib.util
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

from spotbot.research.multi_school_fidelity import gate3_precommit as gate3
from spotbot.research.multi_school_fidelity.fidelity_pipeline import source_hash
from spotbot.research.multi_school_fidelity.review_validation import audit_blinding


def save(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--package-only", action="store_true")
    parser.add_argument("--record-governance", action="store_true")
    args = parser.parse_args()
    output = args.output.resolve()
    repo = Path.cwd()
    if not args.package_only:
        finalize(repo, output)
    if args.record_governance:
        record_governance(repo, output)
    package(repo, output)


def record_governance(repo, output):
    """Read the real local closeout; no remote or Git mutation."""
    charter = repo / "governance/AKAH_BOT_SYSTEM_CHARTER.json"
    doc = json.loads(charter.read_text(encoding="utf-8"))
    task = "AKAH_MASTER_GATE2_CLOSURE_GATE3_PRECOMMIT_FREEZE_MEGA_V1"
    if doc["last_completed_task"]["task_id"] != task:
        raise RuntimeError("LOCAL_GOVERNANCE_CLOSEOUT_NOT_BOUND")

    def git(*args):
        return subprocess.check_output(["git", *args], cwd=repo, text=True).strip()

    tracked = git("status", "--porcelain", "--untracked-files=no")
    active = (repo / ".akah_bot/active_task.json").exists()
    if tracked or active:
        raise RuntimeError("FINAL_LOCAL_GOVERNANCE_NOT_CLEAN")
    verify = subprocess.check_output(
        [
            sys.executable,
            "-B",
            "-m",
            "spotbot.governance.task_completion_gate",
            "--repo",
            str(repo),
            "verify",
            "--task-id",
            task,
        ],
        cwd=repo,
        text=True,
    ).strip()
    record = {
        "FINAL_CHARTER_REVISION": doc["charter_revision"],
        "FINAL_CHARTER_SHA256": source_hash(charter),
        "FINAL_HEAD": git("rev-parse", "HEAD"),
        "branch": git("branch", "--show-current"),
        "ACTIVE_TASK": "NONE",
        "FINAL_TRACKED_CLEAN": "PASS",
        "FINAL_INDEX_CLEAN": "PASS",
        "governance_outcome": doc["last_completed_task"]["outcome"],
        "next_bottleneck": doc["current_state"]["current_bottleneck"],
        "implementation_commit": git("rev-parse", "HEAD^"),
        "changed_paths": git(
            "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD^"
        ).splitlines(),
        "PUSH": "NO",
        "GITHUB_SYNC_PERFORMED": "NO",
        "RESYNC_REQUIRED_BEFORE_NEXT_GOVERNED_TASK": "YES_REQUIRES_SEPARATE_AUTHORIZATION",
        "result_ref": doc["last_completed_task"]["result_ref"],
        "result_sha256": doc["last_completed_task"]["result_sha256"],
        "completion_verification": verify,
    }
    save(output / "19_LOCAL_GOVERNANCE_CLOSEOUT.json", record)
    print(json.dumps(record, indent=2))


def finalize(repo, output):
    delta_path = output / "ICT_SEMANTIC_DELTA_AND_RECERTIFICATION_V2.json"
    if not delta_path.exists():
        raise RuntimeError("AFFECTED_ICT_RECERTIFICATION_MISSING")
    delta = json.loads(delta_path.read_text())
    if delta.get("unaffected_sample_identity") != "PASS" or delta.get("version") != 2:
        raise RuntimeError("AFFECTED_ICT_RECERTIFICATION_INVALID")
    tests = [
        "tests/research/test_multi_school_fidelity.py",
        "tests/research/test_multi_school_evidence_review.py",
        "tests/test_causal_aggregation.py",
        *[
            f"tests/research/{name}.py"
            for name in (
                "test_rd27_adaptive_lifecycle",
                "test_rd27_lifecycle_replay",
                "test_rd27_async_memory_state",
                "test_rd27_async_memory_shadow_replay",
                "test_rd27_later_trigger_v2_shadow_replay",
                "test_rd27_later_trigger_v2_native_hook",
                "test_rd27_observable_memory_adapter",
                "test_rd27_observable_later_trigger_v2",
                "test_rd27_observable_memory_predicate",
                "test_rd27_observable_later_trigger_predicate",
            )
        ],
    ]
    commands = [
        (
            "RUFF",
            [
                sys.executable,
                "-B",
                "-m",
                "ruff",
                "check",
                "src/spotbot/research/multi_school_fidelity",
                "tests/research/test_multi_school_fidelity.py",
                "tests/research/test_multi_school_evidence_review.py",
                "scripts/research/run_master_gate2_closure.py",
                "scripts/research/finalize_master_gate2_evidence.py",
                "scripts/research/recertify_master_gate2_ict.py",
            ],
        ),
        (
            "TARGETED_SYNTHETIC_AND_RD27_REGRESSION",
            [sys.executable, "-B", "-m", "pytest", *tests, "-q", "-p", "no:cacheprovider"],
        ),
    ]
    results = []
    with (output / "18_FULL_LOG.txt").open("a", encoding="utf-8") as log:
        for name, command in commands:
            result = subprocess.run(
                command, cwd=repo, capture_output=True, text=True, encoding="utf-8"
            )
            log.write("\nCOMMAND=" + repr(command) + "\n" + result.stdout + result.stderr)
            print(result.stdout, result.stderr)
            results.append(
                {
                    "test": name,
                    "status": "PASS" if result.returncode == 0 else "FAIL",
                    "command": json.dumps(command),
                    "output": result.stdout.strip(),
                }
            )
            if result.returncode:
                raise RuntimeError(f"FINAL_TEST_FAILED:{name}")
    paths = [
        *sorted((repo / "src/spotbot/research/multi_school_fidelity").glob("*.py")),
        repo / "scripts/research/run_master_gate2_closure.py",
        Path(__file__).resolve(),
        repo / "scripts/research/recertify_master_gate2_ict.py",
        repo / "tests/research/test_multi_school_fidelity.py",
        repo / "tests/research/test_multi_school_evidence_review.py",
    ]
    for p in paths:
        compile(p.read_text(encoding="utf-8"), str(p), "exec")
    results.append(
        {
            "test": "PYTHON_COMPILE",
            "status": "PASS",
            "command": "compile source without writing pyc",
            "output": str(len(paths)) + " files",
        }
    )
    packet_audits = {
        name: audit_blinding(output / name)
        for name in ("07_GATE2_BLIND_USER_PACKET.zip", "08_GATE2_BLIND_SECOND_REVIEWER_PACKET.zip")
    }
    results.append(
        {
            "test": "BLINDING_AND_SEALED_TRACE_SEPARATION",
            "status": "PASS",
            "command": "audit_blinding",
            "output": json.dumps(packet_audits),
        }
    )
    with (output / "04_GATE1_TEST_MATRIX.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(results[0]))
        writer.writeheader()
        writer.writerows(results)
    manifest = json.loads((output / "15_GATE3_FROZEN_HASH_MANIFEST.json").read_text())
    manifest["source_files"] = {str(p.relative_to(repo)): source_hash(p) for p in paths}
    manifest["source_files"][
        "governance/master_gate2_gate3_precommit_v1/source_provenance.json"
    ] = source_hash(repo / "governance/master_gate2_gate3_precommit_v1/source_provenance.json")
    manifest["prospective_rules_sha256"] = {
        p.name: source_hash(p) for p in output.iterdir() if p.name.startswith(("12_", "13_", "14_"))
    }
    manifest["bootstrap_dependency"] = {
        "name": "arch",
        "available_in_repo_environment": bool(importlib.util.find_spec("arch")),
        "policy": "NO_NETWORK_INSTALL_IN_THIS_MISSION",
    }
    save(output / "15_GATE3_FROZEN_HASH_MANIFEST.json", manifest)
    shutil.copyfile(Path(gate3.__file__), output / "16_GATE3_REPLAY_RUNNER_DISABLED.py")
    proof = json.loads((output / "05_GATE2_PIPELINE_PROOF.json").read_text())
    prior_zip = output / "PRE_ICT_REPAIR/PREVIOUS_UNPUBLISHED_EVIDENCE_ARCHIVE.zip"
    with zipfile.ZipFile(prior_zip) as archived:
        proof["pre_recertification_smoke"] = json.loads(
            archived.read("05_GATE2_PIPELINE_PROOF.json")
        )["smoke"]
    updated_ict = {
        row["pair"]: row for row in proof["ict_affected_scope_recertification"]["results"]
    }
    for row in proof["smoke"]:
        if row["school"] == "FS_ICT_2022_CORE_CRYPTO_LONG":
            for field in ("transitions_count", "events_count", "intents_count", "error_count"):
                row[field] = updated_ict[row["pair"]][field]
            row["semantic_version"] = 2
    proof["source_boundary_note"] = (
        "Original census hashes bind the five unaffected detectors. ICT changed under semantic version 2 and is separately recertified on exactly the same bounded panel. Final source freeze is the separate manifest."
    )
    proof["final_tests"] = results
    save(output / "05_GATE2_PIPELINE_PROOF.json", proof)
    integration = json.loads((output / "03_GATE1_INTEGRATION_REPORT.json").read_text())
    integration["post_census_synthetic_corrections"] = [
        "ICT NY16 decision cannot backdate fill to previous hour open",
        "numeric positive stop and finite capacity required",
        "distinct-assets limit in common-lambda projection",
        "malformed authority JSON raises instead of empty metadata",
        "explicit disabled-runner CLI denial",
        "ICT pending raid protection checked before MSS/FVG; affected detector recertified separately",
        "human agreement cannot bypass trace-bound disposition of every case's six comments",
    ]
    integration["known_runtime_issue_quarantine"] = [
        "legacy HybridFSM.observe has no live-parent graph binding and remains unfunded",
        "full market replay bridge remains disabled pending executable grammar/quantity authority",
    ]
    save(output / "03_GATE1_INTEGRATION_REPORT.json", integration)
    sampling = json.loads((output / "06_GATE2_SAMPLING_AUDIT.json").read_text())
    shortages = [
        {"school": r["system_id"], "year": r["year"], "category": k, "missing": v["shortage"]}
        for r in sampling["cells"]
        for k, v in r["categories"].items()
        if v["shortage"]
    ]
    certificate = json.loads((output / "17_FINAL_PRE_REPLAY_CERTIFICATE.json").read_text())
    certificate.update(
        GATE3_RUNNER_SYNTHETIC_TESTS="PASS",
        GATE3_RUNNER_BUILT="NO",
        GATE3_RUNNER_SCOPE="DISABLED_PRECONDITION_VALIDATOR_AND_QUALIFICATION_RULES_ONLY_NOT_FULL_MARKET_REPLAY",
        GATE3_PRECOMMIT_FREEZE="FAIL",
        GATE2_HUMAN_REVIEW_REQUIRED="YES",
        GATE2_STATUS="FAIL",
        GATE2_STATUS_REASON="HUMAN_REVIEWS_REQUIRED_BUT_NOT_THE_ONLY_OPEN_PREREQUISITE",
        GATE2_SAMPLE_VALID="NO",
        GATE2_BOUNDED_BLIND_CORPUS_VALID="YES",
        GATE2_SAMPLE_COMPLETENESS="TARGET_SHORTFALL_NOT_PROVEN_AS_GLOBAL_SOURCE_SCARCITY",
        GATE2_MATERIAL_IMPLEMENTATION_BUGS_OPEN=1,
        GATE2_MATERIAL_SPEC_AMBIGUITIES_IN_FUNDED_SCOPE=0,
        review_defect_counts_status="LEGACY_UNFUNDED_HYBRID_LIVE_GRAPH_GAP; HUMAN_REVIEW_COUNTS_UNADJUDICATED; FUNDED_SCOPE_EMPTY",
        qualification_pipeline_status="PREPARATORY_ENGINEERING_PARTIAL_NOT_FULL_MISSION_PASS",
        shortcomings=shortages,
        TARGETED_TESTS="PASS",
        RD27_REGRESSION="PASS",
        RUFF="PASS",
        sample_count=sampling["case_count"],
        reserve_count=sampling["reserve_count"],
    )
    certificate["blockers"].extend(
        [
            "GATE2_TARGET_PANEL_POSITIVE_COVERAGE_NOT_CLOSED",
            "KNOWN_UNFUNDED_HYBRID_LIVE_GRAPH_GAP",
            "ARCH_BOOTSTRAP_DEPENDENCY_UNAVAILABLE_OFFLINE",
        ]
    )
    certificate["next_bottleneck"] = (
        "MASTER_GATE2_REVIEW_AND_COMPLETE_EXECUTABLE_SCOPE_AUTHORITY_RESIDUAL_V1"
    )
    certificate["blockers"] = sorted(
        set(certificate["blockers"])
        - {"KNOWN_UNFUNDED_ICT_PRE_FVG_INVALIDATION_AND_HYBRID_LIVE_GRAPH_GAPS"}
    )
    save(output / "17_FINAL_PRE_REPLAY_CERTIFICATE.json", certificate)
    readme = """# Engineering closeout, not replay readiness

This mission repaired the concrete Series/callable boundary and preserved visible fail-fast errors.
BTC and ETH scans passed; twelve PIT panel pairs were scanned once; ICT alone was recertified
after a pending-raid protection fix. Exact primary/reserve counts are in sampling audit version 2.
Target 120 coverage is NOT closed. Shortages outside the panel are
not adjudicated as global scarcity. Dow's frozen non-economic context input was fully consumed.

Send ONLY 07_GATE2_BLIND_USER_PACKET.zip to the primary reviewer and ONLY
08_GATE2_BLIND_SECOND_REVIEWER_PACKET.zip to the independent domain reviewer.
These are bounded, incomplete fidelity-discovery packets, NOT a completed 120-case qualification
corpus. Do not treat their review as closing the missing sample coverage or funded scope.
Never distribute the outer archive, sealed trace or reserve as the normal review packet.
Both must export genuine locked answers before trace disclosure. No human answers were created.

No complete funded grammar exists yet: historical PIT quantity normalization, execution bridge,
router/evidence integration and human fidelity remain blocking. The old hybrid live-parent
binding remains quarantined; the ICT pre-FVG invalidation gap is repaired and recertified.
The future bootstrap contract is frozen, but arch is absent from the existing environment.
No network install, source-doctrine invention, economic replay, PnL qualification or production
promotion occurred. Gate3 rules are prospective; the disabled validator is NOT a market runner.

The original failed smoke log is retained separately. No repeated full-universe census was run.
All native RD27 production sources are unchanged. Legacy untracked files are outside staging.
"""
    (output / "README_FINAL_BOUNDARY.md").write_text(readme, encoding="utf-8")
    failed = output.parent / "AKAH_MASTER_GATE2_GATE3_PRECOMMIT_V1_20261002_1221/18_FULL_LOG.txt"
    if failed.exists():
        shutil.copyfile(failed, output / "FAILED_SMOKE_LOG_PRESERVED.txt")
    tree = ast.parse((repo / "tests/research/test_multi_school_fidelity.py").read_text())
    save(
        output / "SYNTHETIC_TEST_CASE_INDEX.json",
        [
            n.name
            for n in tree.body
            if isinstance(n, ast.FunctionDef) and n.name.startswith("test_")
        ],
    )


def package(repo, output):
    manifest = {}
    for p in output.iterdir():
        if p.is_file() and p.name != "ARTIFACT_SHA256_MANIFEST.json":
            manifest[p.name] = source_hash(p)
    save(output / "ARTIFACT_SHA256_MANIFEST.json", manifest)
    zip_path = output.with_suffix(".zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for p in sorted(output.iterdir()):
            if p.is_file():
                archive.write(p, p.name)
        # Preserve the superseded task-local packet evidence, never replace history silently.
        prior = output / "PRE_ICT_REPAIR"
        if prior.exists():
            for p in sorted(prior.iterdir()):
                if p.is_file():
                    archive.write(p, "PRE_ICT_REPAIR/" + p.name)
        result = repo / "governance/master_gate2_gate3_precommit_v1/canonical_result.json"
        if result.exists():
            archive.write(result, "GOVERNANCE/canonical_result.json")
        freeze = json.loads((output / "15_GATE3_FROZEN_HASH_MANIFEST.json").read_text())
        for relative, expected in freeze["source_files"].items():
            path = repo / relative
            if source_hash(path) != expected:
                raise RuntimeError("SOURCE_FREEZE_DRIFT:" + relative)
            archive.write(path, "MAINTAINED_SOURCE/" + relative)
    print("FINAL_OUTPUT=" + str(output))
    print("FINAL_ZIP=" + str(zip_path))
    print("FINAL_ZIP_SHA256=" + source_hash(zip_path))


if __name__ == "__main__":
    main()
