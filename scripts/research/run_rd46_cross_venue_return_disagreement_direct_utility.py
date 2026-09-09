from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

import pandas as pd

from spotbot.research.rd46_cross_venue_return_disagreement_direct_utility import (
    EvaluationError,
    evaluate,
    strict_join,
    write_outputs,
)

BRANCH = "research/rd46-cross-venue-return-disagreement-direct-utility-v1"
P3_FREEZE = "f61cd1f5cbfee30f267b3448ec158a3898385e68"
P3_PROTOCOL = Path(
    "data/research/rd46_p3/"
    "rd46-p3-cross-venue-return-disagreement-direct-utility-temporal-transport-evaluation-preregistration-v1.json"
)
P3_PROTOCOL_BLOB = "38fc7ce74105c19ce9bb72b76a4fb90b7df43e1e"
P3_PROTOCOL_SHA256 = "608d66cda2180dad24492ab8c99901a57710667ece78b78fd062635129178ce2"
STATE = Path("data/research/rd46_p2_runtime/cross-venue-return-disagreement-ledger.csv")
STATE_BLOB = "7d71d0e498206ef953ccc5f77d7e590d4f323b6d"
TARGET = Path("data/research/rd41_p4_runtime/target-ledger.csv")
TARGET_BLOB = "c05773164b753aca2b1eb07d668888e1d05b0dae"
OUT = Path("data/research/rd46_p4_runtime")


def git(repo: Path, *args: str) -> str:
    p = subprocess.run(
        ["git", *args],
        cwd=repo,
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if p.stdout.strip():
        print(p.stdout.rstrip(), flush=True)
    if p.stderr.strip():
        print(p.stderr.rstrip(), flush=True)
    if p.returncode:
        raise EvaluationError(f"git failed rc={p.returncode}: {' '.join(args)}")
    return p.stdout.strip()


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--expected-freeze-commit", required=True)
    args = parser.parse_args()
    if not args.execute:
        raise EvaluationError("--execute required")

    repo = Path(args.repo_root).resolve()
    print("RD46_P4_RUNTIME_VERSION=FROZEN_CROSS_VENUE_RETURN_DISAGREEMENT_DIRECT_UTILITY_V1")
    print(f"RD46_P4_RUNTIME_REPO={repo}")

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
    if sha256(repo / P3_PROTOCOL) != P3_PROTOCOL_SHA256:
        raise EvaluationError("P3 protocol SHA drift")
    if git(repo, "rev-parse", f"HEAD:{STATE.as_posix()}") != STATE_BLOB:
        raise EvaluationError("state ledger blob drift")
    # This is the final hash-only verification. The target file is not read
    # until every frozen-engine and protocol check above has passed.
    if git(repo, "rev-parse", f"HEAD:{TARGET.as_posix()}") != TARGET_BLOB:
        raise EvaluationError("target ledger blob drift")
    if (repo / OUT).exists():
        raise EvaluationError("P4 runtime output already exists; one-shot rerun forbidden")

    print("RD46_P4_RUNTIME_PREFLIGHT=VERIFIED_FROZEN_ENGINE_PRE_TARGET_OPEN")
    print("RD46_P4_FIRST_RCV_EXPOSURE_BEGIN")

    state = pd.read_csv(repo / STATE)
    target = pd.read_csv(repo / TARGET)
    joined = strict_join(state, target)
    print(f"RD46_P4_TARGET_JOIN_PARITY=PASS;rows={len(joined)}")

    result = evaluate(joined)
    report = write_outputs(joined, result, repo / OUT)

    print("RD46_P4_RUNTIME_FINAL_SUMMARY_BEGIN")
    print(json.dumps(report, indent=2, sort_keys=True))
    print("RD46_P4_RUNTIME_FINAL_SUMMARY_END")
    print("RD46_P4_FIRST_RCV_EXPOSURE_END")


if __name__ == "__main__":
    main()
