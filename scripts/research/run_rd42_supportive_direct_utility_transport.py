from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from spotbot.research.rd42_supportive_direct_utility_transport import (  # noqa: E402
    DIRECTIONS,
    FEATURES,
    LANDMARKS,
    UNIVERSES,
    build_analysis_base,
    build_score_ledger,
    decide,
    evaluate_continuous_rcv,
    evaluate_negative_rcv,
    evaluate_negative_tail,
    qualified_pairs,
    qualify_feature_landmarks,
    validate_constants,
)

P3_FREEZE = "30b907ef50b4dc0ea94074ce14d608144a33ae24"
P3_PROTOCOL = Path(
    "data/research/rd42_p3/"
    "rd42-p3-supportive-context-direct-utility-feature-hypotheses-"
    "preregistration-v1.json"
)
P3_PROTOCOL_BLOB = "2cdef3adf7407c96101c9190bc3838a85e475d49"
P3_PROTOCOL_SHA256 = "9d85dfaaf4b4d286097f56cb0f7ca436e008d5d09edfb5f66bb12414ade5f145"
P3_AUDIT = Path("data/research/rd42_p3/rd42-p3-preregistration-audit-v1.json")
P3_AUDIT_BLOB = "4b1eeae6ec626bd7dedeb55db246325f250f4c82"

P2_RESULTS = "7ea0493c55178cd0f34571c1e18c8dee7383c44a"
P2_FREEZE = "e2f92550d0a2115d05d8d34a5395c436c7b8b190"
P2_MANIFEST = Path("data/research/rd42_p2_runtime/output-manifest.json")
P2_MANIFEST_BLOB = "2e4ea2d675f6e62c45ab49e22ee7df1e05b9b4e0"
P2_MANIFEST_DETERMINISTIC_HASH = "c394027c93cb66b540fbc6ca3f038da57bbb1a713cb848125c1bb5e42c5fc97d"
P2_CONTEXT = Path("data/research/rd42_p2_runtime/context-assignment-ledger.csv")
P2_CONTEXT_BLOB = "0c4133b8bf54da0a4ecd07bfbb814be24fdeb18e"
P2_CONTEXT_SHA256 = "5fc3401fb369a6c8d54a4156cb63a1dac7d583723aebec239a3f6150b4426673"

RD41_TARGET = Path("data/research/rd41_p4_runtime/target-ledger.csv")
RD41_TARGET_BLOB = "c05773164b753aca2b1eb07d668888e1d05b0dae"
RD41_TARGET_SHA256 = "857881f3a7268b4c68293707045e84f8d358316736f2b4d9ff5e780f0b8af9e6"
RD41_FEATURE = Path("data/research/rd41_p4_runtime/feature-ledger.csv")
RD41_FEATURE_BLOB = "b030b26c98e4da33c60c21c5d05119874b412c66"
RD41_FEATURE_SHA256 = "e6a31cc14c07866818cf695b883e4e665ed3212a517226dd539357e179b6b4ba"

OUTPUT = Path("data/research/rd42_p4_runtime")
OUTPUT_NAMES = (
    "supportive-feature-transport-score-ledger.csv",
    "supportive-continuous-rcv-cell-evaluation.csv",
    "supportive-negative-rcv-cell-evaluation.csv",
    "supportive-negative-utility-tail-evaluation.csv",
    "supportive-feature-landmark-qualification.csv",
    "qualified-direct-utility-evidence-freeze.json",
    "rd42-p4-supportive-context-direct-utility-report-v1.json",
)


class RunnerError(RuntimeError):
    pass


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser()
    value.add_argument("--repo-root", type=Path, required=True)
    value.add_argument("--execute", action="store_true")
    value.add_argument("--validate-only", action="store_true")
    value.add_argument("--expected-freeze-commit", default=None)
    return value


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode:
        raise RunnerError(f"git {' '.join(args)} failed: {result.stderr}")
    return result.stdout.strip()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise RunnerError(f"JSON object expected: {path}")
    return value


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            value,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
            default=str,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )


def verify_blob(
    repo: Path,
    path: Path,
    expected: str,
    label: str,
) -> None:
    actual = git(repo, "rev-parse", f"HEAD:{path.as_posix()}")
    if actual != expected:
        raise RunnerError(f"{label} blob drift: {actual} != {expected}")


def verify_lineage(
    repo: Path,
    expected_freeze_commit: str,
) -> dict[str, Any]:
    if git(repo, "diff", "--cached", "--name-only", "--"):
        raise RunnerError("staged changes before RD42-P4")
    if git(repo, "diff", "--name-only", "--"):
        raise RunnerError("unstaged tracked changes before RD42-P4")

    head = git(repo, "rev-parse", "HEAD")
    if head != expected_freeze_commit:
        raise RunnerError(f"RD42-P4 HEAD {head} != freeze {expected_freeze_commit}")
    if git(repo, "rev-parse", "HEAD^") != P3_FREEZE:
        raise RunnerError("RD42-P4 freeze parent is not P3")

    for path, blob, label in (
        (P3_PROTOCOL, P3_PROTOCOL_BLOB, "P3 protocol"),
        (P3_AUDIT, P3_AUDIT_BLOB, "P3 audit"),
        (P2_MANIFEST, P2_MANIFEST_BLOB, "P2 manifest"),
        (P2_CONTEXT, P2_CONTEXT_BLOB, "P2 context assignment"),
        (RD41_TARGET, RD41_TARGET_BLOB, "RD41 target ledger"),
        (RD41_FEATURE, RD41_FEATURE_BLOB, "RD41 feature ledger"),
    ):
        verify_blob(repo, path, blob, label)

    for path, expected, label in (
        (P3_PROTOCOL, P3_PROTOCOL_SHA256, "P3 protocol"),
        (P2_CONTEXT, P2_CONTEXT_SHA256, "P2 context assignment"),
        (RD41_TARGET, RD41_TARGET_SHA256, "RD41 target ledger"),
        (RD41_FEATURE, RD41_FEATURE_SHA256, "RD41 feature ledger"),
    ):
        if sha256(repo / path) != expected:
            raise RunnerError(f"{label} SHA drifted")

    protocol = load_json(repo / P3_PROTOCOL)
    audit = load_json(repo / P3_AUDIT)
    manifest = load_json(repo / P2_MANIFEST)

    if protocol.get("status") != "FROZEN_PRE_DIRECT_UTILITY_TARGET_EXPOSURE":
        raise RunnerError("P3 protocol status drifted")
    if protocol.get("next_stage") != (
        "RD42_P4_FREEZE_AND_RUN_SUPPORTIVE_CONTEXT_DIRECT_UTILITY_"
        "TEMPORAL_TRANSPORT_DIAGNOSTIC_ONCE"
    ):
        raise RunnerError("P3 next-stage drifted")
    if audit.get("protocol_sha256") != P3_PROTOCOL_SHA256:
        raise RunnerError("P3 audit protocol SHA drifted")
    if audit.get("rcv_values_seen_in_p3") is not False:
        raise RunnerError("P3 RCV exposure flag drifted")
    if audit.get("2024_accessed") is not False:
        raise RunnerError("P3 2024 flag drifted")

    if manifest.get("status") != "PASS":
        raise RunnerError("P2 manifest status drifted")
    if manifest.get("deterministic_hash") != P2_MANIFEST_DETERMINISTIC_HASH:
        raise RunnerError("P2 manifest deterministic hash drifted")
    if manifest.get("rcv_values_loaded") is not False:
        raise RunnerError("P2 RCV exposure flag drifted")

    validate_constants()
    return {
        "runner_freeze_commit": expected_freeze_commit,
        "p3_freeze_commit": P3_FREEZE,
        "p3_protocol_git_blob": P3_PROTOCOL_BLOB,
        "p3_protocol_sha256": P3_PROTOCOL_SHA256,
        "p3_audit_git_blob": P3_AUDIT_BLOB,
        "p2_results_commit": P2_RESULTS,
        "p2_freeze_commit": P2_FREEZE,
        "p2_manifest_git_blob": P2_MANIFEST_BLOB,
        "p2_manifest_deterministic_hash": P2_MANIFEST_DETERMINISTIC_HASH,
        "p2_context_git_blob": P2_CONTEXT_BLOB,
        "p2_context_sha256": P2_CONTEXT_SHA256,
        "rd41_target_git_blob": RD41_TARGET_BLOB,
        "rd41_target_sha256": RD41_TARGET_SHA256,
        "rd41_feature_git_blob": RD41_FEATURE_BLOB,
        "rd41_feature_sha256": RD41_FEATURE_SHA256,
    }


def load_sources(
    repo: Path,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    targets = pd.read_csv(repo / RD41_TARGET, low_memory=False)
    features = pd.read_csv(repo / RD41_FEATURE, low_memory=False)
    contexts = pd.read_csv(repo / P2_CONTEXT, low_memory=False)
    return targets, features, contexts


def compact_qualification(frame: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in frame.to_dict(orient="records"):
        rows.append(
            {
                "market_context": str(row["market_context"]),
                "feature_id": str(row["feature_id"]),
                "landmark_age_hours": int(row["landmark_age_hours"]),
                "forward_continuous_rcv_qualified_universes": int(
                    row["forward_continuous_rcv_qualified_universes"]
                ),
                "forward_negative_rcv_qualified_universes": int(
                    row["forward_negative_rcv_qualified_universes"]
                ),
                "forward_negative_tail_qualified_universes": int(
                    row["forward_negative_tail_qualified_universes"]
                ),
                "forward_joint_qualified_universes": int(row["forward_joint_qualified_universes"]),
                "reverse_continuous_rcv_qualified_universes": int(
                    row["reverse_continuous_rcv_qualified_universes"]
                ),
                "reverse_negative_rcv_qualified_universes": int(
                    row["reverse_negative_rcv_qualified_universes"]
                ),
                "reverse_negative_tail_qualified_universes": int(
                    row["reverse_negative_tail_qualified_universes"]
                ),
                "reverse_joint_qualified_universes": int(row["reverse_joint_qualified_universes"]),
                "both_transport_directions_pass": bool(row["both_transport_directions_pass"]),
                "advances_to_action_mapping_preregistration": bool(
                    row["advances_to_action_mapping_preregistration"]
                ),
            }
        )
    return rows


def execute(
    repo: Path,
    expected_freeze_commit: str,
) -> dict[str, Any]:
    lineage = verify_lineage(repo, expected_freeze_commit)
    if (repo / OUTPUT).exists():
        raise RunnerError("RD42-P4 runtime exists; preserve and validate/recover")

    targets, features, contexts = load_sources(repo)
    base = build_analysis_base(targets, features, contexts)

    score_ledger = build_score_ledger(base)
    continuous = evaluate_continuous_rcv(base)
    negative = evaluate_negative_rcv(base)
    tail = evaluate_negative_tail(base)
    qualification = qualify_feature_landmarks(
        continuous,
        negative,
        tail,
    )
    qualified = qualified_pairs(qualification)
    decision, next_stage = decide(qualification)

    output = repo / OUTPUT
    output.mkdir(parents=True, exist_ok=False)

    score_ledger.to_csv(
        output / "supportive-feature-transport-score-ledger.csv",
        index=False,
        lineterminator="\n",
    )
    continuous.to_csv(
        output / "supportive-continuous-rcv-cell-evaluation.csv",
        index=False,
        lineterminator="\n",
    )
    negative.to_csv(
        output / "supportive-negative-rcv-cell-evaluation.csv",
        index=False,
        lineterminator="\n",
    )
    tail.to_csv(
        output / "supportive-negative-utility-tail-evaluation.csv",
        index=False,
        lineterminator="\n",
    )
    qualification.to_csv(
        output / "supportive-feature-landmark-qualification.csv",
        index=False,
        lineterminator="\n",
    )

    freeze = {
        "schema_version": "rd42-p4-qualified-direct-utility-evidence-freeze-v1",
        "status": "PASS",
        "decision": decision,
        "next_stage": next_stage,
        "market_context": "SUPPORTIVE",
        "qualified_feature_landmark_pairs": qualified,
        "qualified_feature_landmark_pair_count": len(qualified),
        "all_qualifying_pairs_advance": True,
        "best_feature_selection_used": False,
        "best_landmark_selection_used": False,
        "composite_score_used": False,
        "threshold_search_used": False,
        "action_mapping_executed": False,
        "economic_action_executed": False,
        "portfolio_replay_performed": False,
        "capital_reuse_performed": False,
        "2024_accessed": False,
        "production_authorized": False,
    }
    write_json(
        output / "qualified-direct-utility-evidence-freeze.json",
        freeze,
    )

    report = {
        "schema_version": "rd42-p4-supportive-context-direct-utility-report-v1",
        "stage": ("RD42_P4_SUPPORTIVE_CONTEXT_DIRECT_UTILITY_TEMPORAL_TRANSPORT"),
        "status": "PASS",
        "lineage": lineage,
        "analysis_base_row_count": int(len(base)),
        "score_ledger_row_count": int(len(score_ledger)),
        "market_context": "SUPPORTIVE",
        "features": list(FEATURES),
        "landmarks_hours": list(LANDMARKS),
        "transport_directions": list(DIRECTIONS),
        "feature_landmark_qualification": compact_qualification(qualification),
        "qualified_feature_landmark_pairs": qualified,
        "qualified_feature_landmark_pair_count": len(qualified),
        "decision": decision,
        "next_stage": next_stage,
        "raw_market_data_loaded": False,
        "context_rebuilt": False,
        "features_rebuilt": False,
        "targets_rebuilt": False,
        "new_feature_engineering": False,
        "model_fit_performed": False,
        "best_feature_selection_used": False,
        "best_landmark_selection_used": False,
        "composite_score_used": False,
        "parameter_search_used": False,
        "threshold_optimization_used": False,
        "winner_selection_used": False,
        "action_mapping_executed": False,
        "economic_action_executed": False,
        "full_liquidation_performed": False,
        "partial_derisk_performed": False,
        "portfolio_replay_performed": False,
        "capital_reuse_performed": False,
        "2024_accessed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
    }
    write_json(
        output / "rd42-p4-supportive-context-direct-utility-report-v1.json",
        report,
    )

    files: dict[str, dict[str, Any]] = {}
    for name in OUTPUT_NAMES:
        path = output / name
        if not path.is_file():
            raise RunnerError(f"manifest source missing: {name}")
        files[name] = {
            "sha256": sha256(path),
            "bytes": int(path.stat().st_size),
        }
    canonical = json.dumps(
        files,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    write_json(
        output / "output-manifest.json",
        {
            "schema_version": "rd42-p4-output-manifest-v1",
            "status": "PASS",
            "decision": decision,
            "next_stage": next_stage,
            "runner_freeze_commit": expected_freeze_commit,
            "file_count": len(files),
            "files": files,
            "deterministic_hash": hashlib.sha256(canonical).hexdigest(),
            "qualified_feature_landmark_pairs": qualified,
            "qualified_feature_landmark_pair_count": len(qualified),
            "raw_market_data_loaded": False,
            "context_rebuilt": False,
            "features_rebuilt": False,
            "targets_rebuilt": False,
            "model_fit_performed": False,
            "action_mapping_executed": False,
            "economic_action_executed": False,
            "portfolio_replay_performed": False,
            "capital_reuse_performed": False,
            "2024_accessed": False,
            "production_authorized": False,
        },
    )
    return validate_outputs(repo)


def validate_outputs(repo: Path) -> dict[str, Any]:
    output = repo / OUTPUT
    if not output.is_dir():
        raise RunnerError("RD42-P4 runtime missing")

    expected = sorted((*OUTPUT_NAMES, "output-manifest.json"))
    observed = sorted(path.name for path in output.iterdir() if path.is_file())
    if observed != expected:
        raise RunnerError(f"RD42-P4 output registry drift: {observed} != {expected}")

    score = pd.read_csv(
        output / "supportive-feature-transport-score-ledger.csv",
        low_memory=False,
    )
    continuous = pd.read_csv(
        output / "supportive-continuous-rcv-cell-evaluation.csv",
        low_memory=False,
    )
    negative = pd.read_csv(
        output / "supportive-negative-rcv-cell-evaluation.csv",
        low_memory=False,
    )
    tail = pd.read_csv(
        output / "supportive-negative-utility-tail-evaluation.csv",
        low_memory=False,
    )
    qualification = pd.read_csv(
        output / "supportive-feature-landmark-qualification.csv",
        low_memory=False,
    )
    freeze = load_json(output / "qualified-direct-utility-evidence-freeze.json")
    report = load_json(output / "rd42-p4-supportive-context-direct-utility-report-v1.json")
    manifest = load_json(output / "output-manifest.json")

    expected_cells = len(DIRECTIONS) * len(LANDMARKS) * len(UNIVERSES) * len(FEATURES)
    if len(continuous) != expected_cells:
        raise RunnerError("continuous evaluation cardinality drifted")
    if len(negative) != expected_cells:
        raise RunnerError("negative-RCV evaluation cardinality drifted")
    if len(tail) != expected_cells:
        raise RunnerError("tail evaluation cardinality drifted")
    if len(qualification) != len(LANDMARKS) * len(FEATURES):
        raise RunnerError("feature-landmark qualification cardinality drifted")
    if score.empty:
        raise RunnerError("score ledger is empty")
    if (score["market_context"].astype(str) != "SUPPORTIVE").any():
        raise RunnerError("non-SUPPORTIVE row in score ledger")
    if not set(score["landmark_age_hours"].astype(int)).issubset(LANDMARKS):
        raise RunnerError("unsupported landmark in score ledger")

    recomputed_decision, recomputed_next = decide(qualification)
    recomputed_qualified = qualified_pairs(qualification)
    if freeze.get("decision") != recomputed_decision:
        raise RunnerError("qualified freeze decision drifted")
    if freeze.get("next_stage") != recomputed_next:
        raise RunnerError("qualified freeze next-stage drifted")
    if freeze.get("qualified_feature_landmark_pairs") != recomputed_qualified:
        raise RunnerError("qualified freeze pair registry drifted")
    if report.get("decision") != recomputed_decision:
        raise RunnerError("report decision drifted")
    if report.get("next_stage") != recomputed_next:
        raise RunnerError("report next-stage drifted")
    if manifest.get("decision") != recomputed_decision:
        raise RunnerError("manifest decision drifted")
    if manifest.get("next_stage") != recomputed_next:
        raise RunnerError("manifest next-stage drifted")

    for container in (freeze, report, manifest):
        for field in (
            "model_fit_performed",
            "action_mapping_executed",
            "economic_action_executed",
            "portfolio_replay_performed",
            "capital_reuse_performed",
            "2024_accessed",
            "production_authorized",
        ):
            if container.get(field) is not False:
                raise RunnerError(f"prohibited P4 flag true: {field}")

    files = manifest.get("files")
    if not isinstance(files, dict) or len(files) != len(OUTPUT_NAMES):
        raise RunnerError("manifest file registry drifted")
    canonical_files: dict[str, dict[str, Any]] = {}
    for name in OUTPUT_NAMES:
        path = output / name
        entry = files.get(name)
        if not isinstance(entry, dict):
            raise RunnerError(f"manifest missing file entry: {name}")
        actual_sha = sha256(path)
        actual_bytes = int(path.stat().st_size)
        if entry.get("sha256") != actual_sha:
            raise RunnerError(f"manifest SHA drift: {name}")
        if int(entry.get("bytes")) != actual_bytes:
            raise RunnerError(f"manifest size drift: {name}")
        canonical_files[name] = {
            "sha256": actual_sha,
            "bytes": actual_bytes,
        }
    canonical = json.dumps(
        canonical_files,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    if manifest.get("deterministic_hash") != hashlib.sha256(canonical).hexdigest():
        raise RunnerError("manifest deterministic hash drifted")

    return {
        "status": "PASS",
        "decision": recomputed_decision,
        "next_stage": recomputed_next,
        "analysis_base_row_count": int(report["analysis_base_row_count"]),
        "score_ledger_row_count": int(report["score_ledger_row_count"]),
        "feature_landmark_qualification": compact_qualification(qualification),
        "qualified_feature_landmark_pairs": recomputed_qualified,
        "qualified_feature_landmark_pair_count": len(recomputed_qualified),
        "raw_market_data_loaded": False,
        "context_rebuilt": False,
        "features_rebuilt": False,
        "targets_rebuilt": False,
        "model_fit_performed": False,
        "action_mapping_executed": False,
        "economic_action_executed": False,
        "portfolio_replay_performed": False,
        "capital_reuse_performed": False,
        "2024_accessed": False,
        "production_authorized": False,
    }


def main() -> int:
    args = parser().parse_args()
    repo = args.repo_root.resolve()
    if not (repo / ".git").exists():
        raise RunnerError(f"not a git repository: {repo}")
    if int(args.execute) + int(args.validate_only) != 1:
        raise RunnerError("choose exactly one runner mode")

    if args.validate_only:
        print(
            json.dumps(
                validate_outputs(repo),
                indent=2,
                sort_keys=True,
                ensure_ascii=False,
                allow_nan=False,
            )
        )
        return 0

    if not args.expected_freeze_commit:
        raise RunnerError("--expected-freeze-commit is required")

    print(
        json.dumps(
            execute(repo, args.expected_freeze_commit),
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
