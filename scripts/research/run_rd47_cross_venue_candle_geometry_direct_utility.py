from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

import pandas as pd

from spotbot.research.rd47_cross_venue_candle_geometry_direct_utility import (
    EvaluationError,
    evaluate,
    strict_join,
    write_outputs,
)

BRANCH = "research/rd47-cross-venue-candle-geometry-direct-utility-v1"
P3_FREEZE = "3ec39f8f840cb775843c12940d4343bf8415cd19"
P3_PROTOCOL = Path(
    "data/research/rd47_p3/"
    "rd47-p3-cross-venue-candle-geometry-direct-utility-"
    "temporal-transport-evaluation-preregistration-v1.json"
)
P3_PROTOCOL_BLOB = "cc102ade29a5188e3d1536e1d50b4746aa4ed87d"
P3_PROTOCOL_SHA256 = "20e49e2825f9722c0e24fd074aaef2f6c083222390a02f23c4ecf55b751eb034"
STATE = Path("data/research/rd47_p2_runtime/cross-venue-candle-geometry-ledger.csv")
STATE_BLOB = "29e393b2daa5fb89f22720206d3b9c1abd8d8101"
TARGET = Path("data/research/rd41_p4_runtime/target-ledger.csv")
TARGET_BLOB = "c05773164b753aca2b1eb07d668888e1d05b0dae"
OUT = Path("data/research/rd47_p4_runtime")


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
    print("RD47_P4_RUNTIME_VERSION=FROZEN_CROSS_VENUE_CANDLE_GEOMETRY_DIRECT_UTILITY_V1")
    print(f"RD47_P4_RUNTIME_REPO={repo}")

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
    if (
        git(
            repo,
            "rev-parse",
            f"HEAD:{P3_PROTOCOL.as_posix()}",
        )
        != P3_PROTOCOL_BLOB
    ):
        raise EvaluationError("P3 protocol blob drift")
    if sha256(repo / P3_PROTOCOL) != P3_PROTOCOL_SHA256:
        raise EvaluationError("P3 protocol SHA drift")
    if git(repo, "rev-parse", f"HEAD:{STATE.as_posix()}") != STATE_BLOB:
        raise EvaluationError("state ledger blob drift")

    # Final hash-only check. The target is not opened until all frozen
    # engine/protocol/state checks above pass.
    if git(repo, "rev-parse", f"HEAD:{TARGET.as_posix()}") != TARGET_BLOB:
        raise EvaluationError("target ledger blob drift")
    if (repo / OUT).exists():
        raise EvaluationError("P4 runtime output already exists; one-shot rerun forbidden")

    print("RD47_P4_RUNTIME_PREFLIGHT=VERIFIED_FROZEN_ENGINE_PRE_TARGET_OPEN")
    print("RD47_P4_FIRST_RCV_EXPOSURE_BEGIN")

    state = pd.read_csv(repo / STATE, low_memory=False)
    target = pd.read_csv(repo / TARGET, low_memory=False)
    joined = strict_join(state, target)
    print(f"RD47_P4_TARGET_JOIN_PARITY=PASS;rows={len(joined)}")

    result = evaluate(joined)
    report = write_outputs(joined, result, repo / OUT)

    print("RD47_P4_RUNTIME_FINAL_SUMMARY_BEGIN")
    print(json.dumps(report, indent=2, sort_keys=True))
    print("RD47_P4_RUNTIME_FINAL_SUMMARY_END")
    print("RD47_P4_FIRST_RCV_EXPOSURE_END")


if __name__ == "__main__":
    main()
