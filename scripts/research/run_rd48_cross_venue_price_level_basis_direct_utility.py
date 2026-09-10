from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

import pandas as pd

from spotbot.research.rd48_cross_venue_price_level_basis_direct_utility import (
    EvaluationError,
    evaluate,
    strict_join,
    write_outputs,
)

BRANCH = "research/rd48-cross-venue-price-level-basis-direct-utility-v1"
P3_FREEZE = "8a206a555c6c22be0d9461a12d633ed53ccba04a"
P3_PROTOCOL = Path(
    "data/research/rd48_p3/"
    "rd48-p3-cross-venue-price-level-basis-direct-utility-"
    "temporal-transport-evaluation-preregistration-v1.json"
)
P3_PROTOCOL_BLOB = "4e80c0394894b71f440ecdb075868e12749aaba7"
P3_PROTOCOL_SHA256 = "ab99c92280a678383619634407d212eecb98315e80eb0762b400301c07da6ca4"
STATE = Path("data/research/rd48_p2_runtime/cross-venue-price-level-basis-ledger.csv")
STATE_BLOB = "50054a315ff13268842fb7610f151ad1e4e34689"
TARGET = Path("data/research/rd41_p4_runtime/target-ledger.csv")
TARGET_BLOB = "c05773164b753aca2b1eb07d668888e1d05b0dae"
OUT = Path("data/research/rd48_p4_runtime")
EXPOSURE_GUARD = Path("data/research/rd48_p4_exposure_guard/first-rcv-exposure-started-v1.json")


def git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=repo,
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if proc.stdout.strip():
        print(proc.stdout.rstrip(), flush=True)
    if proc.stderr.strip():
        print(proc.stderr.rstrip(), flush=True)
    if proc.returncode:
        raise EvaluationError(f"git failed rc={proc.returncode}: {' '.join(args)}")
    return proc.stdout.strip()


def git_bytes(repo: Path, *args: str) -> bytes:
    proc = subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        check=False,
    )
    if proc.returncode:
        raise EvaluationError(f"git bytes failed rc={proc.returncode}: {' '.join(args)}")
    return bytes(proc.stdout)


def committed_sha256(repo: Path, path: Path) -> str:
    return hashlib.sha256(git_bytes(repo, "show", f"HEAD:{path.as_posix()}")).hexdigest()


def write_guard(
    repo: Path,
    freeze_commit: str,
) -> None:
    path = repo / EXPOSURE_GUARD
    path.parent.mkdir(parents=True, exist_ok=False)
    payload = {
        "schema_version": "rd48-p4-first-rcv-exposure-guard-v1",
        "status": "RCV_EXPOSURE_ASSUMED_STARTED_FAIL_CLOSED",
        "branch": BRANCH,
        "p4_engine_freeze_commit": freeze_commit,
        "p3_freeze_commit": P3_FREEZE,
        "target_ledger_git_blob": TARGET_BLOB,
        "scientific_criteria_locked": True,
        "automatic_rerun_forbidden": True,
        "target_values_embedded": False,
        "rcv_values_embedded": False,
    }
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--expected-freeze-commit", required=True)
    args = parser.parse_args()
    if not args.execute:
        raise EvaluationError("--execute required")

    repo = Path(args.repo_root).resolve()
    print("RD48_P4_RUNTIME_VERSION=FROZEN_CROSS_VENUE_PRICE_LEVEL_BASIS_DIRECT_UTILITY_V1")
    print(f"RD48_P4_RUNTIME_REPO={repo}")

    head = git(repo, "rev-parse", "HEAD")
    if head != args.expected_freeze_commit:
        raise EvaluationError(f"HEAD {head} != expected freeze {args.expected_freeze_commit}")
    if git(repo, "rev-parse", "HEAD^") != P3_FREEZE:
        raise EvaluationError("P4 engine freeze parent is not P3 freeze")
    if git(repo, "branch", "--show-current") != BRANCH:
        raise EvaluationError("wrong branch")
    if git(repo, "diff", "--cached", "--name-only", "--"):
        raise EvaluationError("staged tracked changes exist")
    if git(repo, "diff", "--name-only", "--"):
        raise EvaluationError("unstaged tracked changes exist")
    if git(repo, "rev-parse", f"HEAD:{P3_PROTOCOL.as_posix()}") != P3_PROTOCOL_BLOB:
        raise EvaluationError("P3 protocol blob drift")
    if committed_sha256(repo, P3_PROTOCOL) != P3_PROTOCOL_SHA256:
        raise EvaluationError("P3 protocol SHA drift")
    if git(repo, "rev-parse", f"HEAD:{STATE.as_posix()}") != STATE_BLOB:
        raise EvaluationError("state ledger blob drift")

    # Hash-only identity check: target content remains unopened here.
    if git(repo, "rev-parse", f"HEAD:{TARGET.as_posix()}") != TARGET_BLOB:
        raise EvaluationError("target ledger blob drift")
    if (repo / OUT).exists():
        raise EvaluationError("P4 runtime output already exists; one-shot rerun forbidden")
    if (repo / EXPOSURE_GUARD).exists():
        raise EvaluationError("P4 exposure guard already exists; automatic rerun forbidden")

    print("RD48_P4_RUNTIME_PREFLIGHT=VERIFIED_FROZEN_ENGINE_PRE_TARGET_OPEN")

    # Fail closed: once this guard is written, any later failure is treated
    # as potential RCV exposure and requires forensic recovery, never rerun.
    write_guard(repo, head)
    print("RD48_P4_EXPOSURE_GUARD_WRITTEN=PASS")
    print("RD48_P4_FIRST_RCV_EXPOSURE_BEGIN")

    state = pd.read_csv(repo / STATE, low_memory=False)
    target = pd.read_csv(repo / TARGET, low_memory=False)
    joined = strict_join(state, target)
    print(f"RD48_P4_TARGET_JOIN_PARITY=PASS;rows={len(joined)}")

    result = evaluate(joined)
    report = write_outputs(joined, result, repo / OUT)

    print("RD48_P4_RUNTIME_FINAL_SUMMARY_BEGIN")
    print(json.dumps(report, indent=2, sort_keys=True))
    print("RD48_P4_RUNTIME_FINAL_SUMMARY_END")
    print("RD48_P4_FIRST_RCV_EXPOSURE_END")


if __name__ == "__main__":
    main()
