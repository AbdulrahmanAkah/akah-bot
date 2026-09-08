from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC)) if str(SRC) not in sys.path else None
from spotbot.research.rd41_multivariate_hazard_economic_alignment import (  # noqa: E402
    build_base_rows,
    decide,
    hazard_eval,
    qualify,
    rcv_eval,
    score_ledger,
    tail_eval,
    validate_constants,
)

P5_FREEZE = "c8abd1915ebe4bae0545dc82da24ee9f12f48276"
P5_PROTOCOL = Path(
    "data/research/rd41_p5/rd41-p5-multivariate-hazard-integration-economic-alignment-preregistration-v1.json"
)
P5_PROTOCOL_BLOB = "daff48e68d30024d2a6ed3db2359f0f7ba44f28e"
P5_PROTOCOL_SHA256 = "c9ff7b29c033bd861271859300fb98a9dc2ba887634465f94b6c9d56b2973d83"
P5_AUDIT = Path("data/research/rd41_p5/rd41-p5-preregistration-audit-v1.json")
P5_AUDIT_BLOB = "2db440fd26e680d072c25b3fc5194b982531d376"
P4_TARGET = Path("data/research/rd41_p4_runtime/target-ledger.csv")
P4_TARGET_SHA256 = "857881f3a7268b4c68293707045e84f8d358316736f2b4d9ff5e780f0b8af9e6"
P4_FEATURE = Path("data/research/rd41_p4_runtime/feature-ledger.csv")
P4_FEATURE_SHA256 = "e6a31cc14c07866818cf695b883e4e665ed3212a517226dd539357e179b6b4ba"
OUTPUT = Path("data/research/rd41_p6_runtime")
NAMES = (
    "transport-score-ledger.csv",
    "hazard-transport-evaluation.csv",
    "rcv-alignment-evaluation.csv",
    "negative-rcv-tail-evaluation.csv",
    "landmark-transport-qualification.csv",
    "qualified-multivariate-evidence-freeze.json",
    "rd41-p6-multivariate-hazard-economic-alignment-report-v1.json",
)


class E(RuntimeError):
    pass


def git(repo, *args):
    r = subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    if r.returncode:
        raise E(r.stderr)
    return r.stdout.strip()


def sha(p):
    h = hashlib.sha256()
    with p.open("rb") as f:
        while b := f.read(1048576):
            h.update(b)
    return h.hexdigest()


def load(p):
    return json.loads(p.read_text(encoding="utf-8-sig"))


def write(p, v):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps(v, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False, default=str)
        + "\n",
        encoding="utf-8",
        newline="\n",
    )


def lineage(repo, expected):
    if git(repo, "rev-parse", "HEAD") != expected or git(repo, "rev-parse", "HEAD^") != P5_FREEZE:
        raise E("lineage mismatch")
    if (
        git(repo, "rev-parse", f"HEAD:{P5_PROTOCOL.as_posix()}") != P5_PROTOCOL_BLOB
        or git(repo, "rev-parse", f"HEAD:{P5_AUDIT.as_posix()}") != P5_AUDIT_BLOB
    ):
        raise E("P5 blob mismatch")
    if (
        sha(repo / P5_PROTOCOL) != P5_PROTOCOL_SHA256
        or sha(repo / P4_TARGET) != P4_TARGET_SHA256
        or sha(repo / P4_FEATURE) != P4_FEATURE_SHA256
    ):
        raise E("source SHA drift")
    a = load(repo / P5_AUDIT)
    if a.get("protocol_sha256") != P5_PROTOCOL_SHA256:
        raise E("P5 audit drift")
    validate_constants()
    return {
        "runner_freeze_commit": expected,
        "p5_freeze_commit": P5_FREEZE,
        "p5_protocol_sha256": P5_PROTOCOL_SHA256,
        "p4_target_ledger_sha256": P4_TARGET_SHA256,
        "p4_feature_ledger_sha256": P4_FEATURE_SHA256,
    }


def compact(q):
    out = []
    for r in q.to_dict("records"):
        out.append(
            {
                k: (
                    bool(r[k])
                    if k
                    in (
                        "hazard_transports_both_directions",
                        "economically_aligned_both_directions",
                        "advances_to_action_mapping_preregistration",
                    )
                    else int(r[k])
                    if k.endswith("universes") or k == "landmark_age_hours"
                    else r[k]
                )
                for k in (
                    "landmark_age_hours",
                    "forward_hazard_qualified_universes",
                    "forward_rcv_qualified_universes",
                    "forward_negative_tail_qualified_universes",
                    "reverse_hazard_qualified_universes",
                    "reverse_rcv_qualified_universes",
                    "reverse_negative_tail_qualified_universes",
                    "hazard_transports_both_directions",
                    "economically_aligned_both_directions",
                    "advances_to_action_mapping_preregistration",
                )
            }
        )
    return out


def execute(repo, expected):
    lin = lineage(repo, expected)
    if (repo / OUTPUT).exists():
        raise E("runtime exists")
    t = pd.read_csv(repo / P4_TARGET, low_memory=False)
    f = pd.read_csv(repo / P4_FEATURE, low_memory=False)
    base = build_base_rows(t, f)
    scores = score_ledger(base)
    h = hazard_eval(base)
    r = rcv_eval(base)
    tail = tail_eval(base)
    q = qualify(h, r, tail)
    decision, next_stage = decide(q)
    out = repo / OUTPUT
    out.mkdir(parents=True)
    scores.to_csv(out / NAMES[0], index=False, lineterminator="\n")
    h.to_csv(out / NAMES[1], index=False, lineterminator="\n")
    r.to_csv(out / NAMES[2], index=False, lineterminator="\n")
    tail.to_csv(out / NAMES[3], index=False, lineterminator="\n")
    q.to_csv(out / NAMES[4], index=False, lineterminator="\n")
    advancing = [
        int(x)
        for x in q.loc[
            q["advances_to_action_mapping_preregistration"].astype(bool), "landmark_age_hours"
        ]
    ]
    hazard = [
        int(x)
        for x in q.loc[q["hazard_transports_both_directions"].astype(bool), "landmark_age_hours"]
        if int(x) not in advancing
    ]
    write(
        out / NAMES[5],
        {
            "schema_version": "rd41-p6-qualified-multivariate-evidence-freeze-v1",
            "status": "PASS",
            "decision": decision,
            "next_stage": next_stage,
            "advancing_landmarks_hours": advancing,
            "hazard_transport_only_landmarks_hours": hazard,
            "best_landmark_selection_used": False,
            "feature_subset_selection_used": False,
            "feature_weight_search_used": False,
            "economic_action_executed": False,
            "production_authorized": False,
        },
    )
    report = {
        "schema_version": "rd41-p6-multivariate-hazard-economic-alignment-report-v1",
        "status": "PASS",
        "lineage": lin,
        "runner_freeze_commit": expected,
        "source_p5_freeze_commit": P5_FREEZE,
        "base_decision_row_count": len(base),
        "transport_score_row_count": len(scores),
        "landmark_qualification": compact(q),
        "advancing_landmarks_hours": advancing,
        "hazard_transport_only_landmarks_hours": hazard,
        "decision": decision,
        "next_stage": next_stage,
        "best_landmark_selection_used": False,
        "feature_subset_selection_used": False,
        "feature_weight_search_used": False,
        "governor_incremental_test_performed": False,
        "economic_action_executed": False,
        "full_liquidation_performed": False,
        "partial_derisk_performed": False,
        "portfolio_replay_performed": False,
        "capital_reuse_performed": False,
        "parameter_search_used": False,
        "threshold_optimization_used": False,
        "winner_selection_used": False,
        "2024_accessed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
    }
    write(out / NAMES[6], report)
    files = {n: {"sha256": sha(out / n), "bytes": (out / n).stat().st_size} for n in NAMES}
    canon = json.dumps(files, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    write(
        out / "output-manifest.json",
        {
            "schema_version": "rd41-p6-output-manifest-v1",
            "file_count": len(files),
            "files": files,
            "deterministic_hash": hashlib.sha256(canon).hexdigest(),
            "decision": decision,
            "runner_freeze_commit": expected,
        },
    )
    return validate(repo)


def validate(repo):
    out = repo / OUTPUT
    report = load(out / NAMES[6])
    q = pd.read_csv(out / NAMES[4])
    decision, next_stage = decide(q)
    manifest = load(out / "output-manifest.json")
    if (
        report["decision"] != decision
        or report["next_stage"] != next_stage
        or manifest["decision"] != decision
    ):
        raise E("decision validation failed")
    return {
        "status": "PASS",
        "decision": decision,
        "next_stage": next_stage,
        "base_decision_row_count": int(report["base_decision_row_count"]),
        "transport_score_row_count": int(report["transport_score_row_count"]),
        "landmark_qualification": compact(q),
        "advancing_landmarks_hours": report["advancing_landmarks_hours"],
        "hazard_transport_only_landmarks_hours": report["hazard_transport_only_landmarks_hours"],
        "best_landmark_selection_used": False,
        "economic_action_executed": False,
        "2024_accessed": False,
        "production_authorized": False,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--repo-root", type=Path, required=True)
    p.add_argument("--execute", action="store_true")
    p.add_argument("--validate-only", action="store_true")
    p.add_argument("--expected-freeze-commit")
    a = p.parse_args()
    repo = a.repo_root.resolve()
    if int(a.execute) + int(a.validate_only) != 1:
        raise E("choose one mode")
    print(
        json.dumps(
            validate(repo) if a.validate_only else execute(repo, a.expected_freeze_commit),
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
