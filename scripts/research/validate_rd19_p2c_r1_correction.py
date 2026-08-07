"""Validate RD19-P2C-R1 corrected replay and local evidence."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from spotbot.research import rd19_p2c_discovery as p2c  # noqa: E402
from spotbot.research.rd19_p2c_r1_engine import (  # noqa: E402
    DECISION,
    EXPECTED_RUNS,
    REPAIR_IDS,
    P2CR1Error,
)

REQUIRED_SUMMARY_FILES = {
    "run-metrics.csv",
    "combined-2019-2023-metrics.csv",
    "variant-gate-evaluation.csv",
    "finalist-ranking.csv",
    "signal-funnel.csv",
    "local-evidence-manifest.csv",
    "timing-report.json",
    "correction-audit.json",
    "rd19-p2c-r1-correction-report-v1.json",
}


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    result.add_argument("--repo-root", type=Path, default=ROOT)
    result.add_argument("--summary-output-dir", type=Path, required=True)
    result.add_argument("--offline", action="store_true")
    return result


def sha256(path: Path) -> str:
    return p2c.sha256(path)


def main() -> int:
    args = parser().parse_args()
    if not args.offline:
        raise P2CR1Error("--offline is required")
    repo = args.repo_root.resolve()
    summary = args.summary_output_dir.resolve()

    report = p2c.load_json_object(summary / "rd19-p2c-r1-correction-report-v1.json")
    expected = {
        "passed": True,
        "decision": DECISION,
        "original_p2c_result_disposition": ("INVALIDATED_FOR_IMPLEMENTATION_NONCONFORMANCE"),
        "parameter_changes": 0,
        "matrix_changes": 0,
        "hard_gate_changes": 0,
        "authorized_run_count": EXPECTED_RUNS,
        "completed_run_count": EXPECTED_RUNS,
        "variant_count": 12,
        "feature_signature_count": 2,
        "daily_rank_cache_count": 6,
        "candidate_plan_count": 36,
        "combined_metric_rows": 72,
        "signal_funnel_rows": EXPECTED_RUNS,
        "raw_evidence_committed_to_git": False,
        "raw_evidence_local_and_hashed": True,
        "2024_internal_confirmation_executed": False,
        "2024_market_data_accessed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
    }
    drift = {
        key: {"expected": wanted, "actual": report.get(key)}
        for key, wanted in expected.items()
        if report.get(key) != wanted
    }
    if drift:
        raise P2CR1Error(f"corrected report semantic drift: {drift}")
    if report.get("repair_ids") != list(REPAIR_IDS):
        raise P2CR1Error("repair ID set drifted")

    selected = report.get("selected_for_2024_variants")
    if not isinstance(selected, list) or len(selected) > 2:
        raise P2CR1Error("selected finalist set is invalid")

    run_metrics = pd.read_csv(summary / "run-metrics.csv")
    combined = pd.read_csv(summary / "combined-2019-2023-metrics.csv")
    gates = pd.read_csv(summary / "variant-gate-evaluation.csv")
    finalists = pd.read_csv(summary / "finalist-ranking.csv")
    funnel = pd.read_csv(summary / "signal-funnel.csv")

    if len(run_metrics) != EXPECTED_RUNS:
        raise P2CR1Error("run metrics row count drifted")
    if len(combined) != 72:
        raise P2CR1Error("combined metric rows drifted")
    if len(gates) != 12 or gates["variant_id"].nunique() != 12:
        raise P2CR1Error("gate coverage drifted")
    if len(funnel) != EXPECTED_RUNS:
        raise P2CR1Error("signal funnel coverage drifted")
    if bool((run_metrics["minimum_cash"] < -1e-7).any()):
        raise P2CR1Error("corrected replay contains negative cash")
    if bool(run_metrics["2024_market_data_accessed"].astype(bool).any()):
        raise P2CR1Error("corrected replay accessed 2024")
    if bool(run_metrics["post_2024_accessed"].astype(bool).any()):
        raise P2CR1Error("corrected replay accessed post-2024 data")

    selected_from_file = (
        finalists.loc[
            finalists["selected_for_2024"].astype(bool),
            "variant_id",
        ]
        .astype(str)
        .tolist()
        if not finalists.empty
        else []
    )
    if selected_from_file != selected:
        raise P2CR1Error("finalist identity drifted")

    audit = p2c.load_json_object(summary / "correction-audit.json")
    defects = audit.get("confirmed_defects")
    if not isinstance(defects, dict) or not defects:
        raise P2CR1Error("original defect audit is missing")
    if not all(bool(value) for value in defects.values()):
        raise P2CR1Error("original defect audit contains an unconfirmed item")
    if audit.get("parameter_changes") != 0:
        raise P2CR1Error("correction changed frozen parameters")

    timing = p2c.load_json_object(summary / "timing-report.json")
    if timing.get("feature_store_build_count") != 2:
        raise P2CR1Error("feature-store reuse did not collapse to 2 builds")
    if timing.get("daily_rank_cache_count") != 6:
        raise P2CR1Error("daily-rank cache count drifted")
    if timing.get("candidate_plan_count") != 36:
        raise P2CR1Error("candidate-plan cache count drifted")
    if timing.get("hot_loop_pandas_snapshot_builds") != 0:
        raise P2CR1Error("hot-loop pandas snapshot regression detected")

    evidence_relative = report.get("local_evidence_relative_path")
    if not isinstance(evidence_relative, str) or not evidence_relative:
        raise P2CR1Error("local evidence path missing")
    evidence_root = Path(evidence_relative)
    if not evidence_root.is_absolute():
        evidence_root = repo / evidence_root
    if not evidence_root.is_dir():
        raise P2CR1Error(f"local evidence directory missing: {evidence_root}")

    evidence = pd.read_csv(summary / "local-evidence-manifest.csv")
    if len(evidence) != EXPECTED_RUNS * 7:
        raise P2CR1Error("local evidence manifest row count drifted")
    if bool(evidence["path"].astype(str).duplicated().any()):
        raise P2CR1Error("local evidence manifest contains duplicate paths")
    for raw in evidence.to_dict(orient="records"):
        path = evidence_root / str(raw["path"])
        if not path.is_file():
            raise P2CR1Error(f"local evidence file missing: {path}")
        if sha256(path) != str(raw["sha256"]):
            raise P2CR1Error(f"local evidence hash drift: {path}")

    manifest = p2c.load_json_object(summary / "output-manifest.json")
    files = manifest.get("files")
    if not isinstance(files, list):
        raise P2CR1Error("summary manifest files invalid")
    observed: set[str] = set()
    for raw in files:
        if not isinstance(raw, dict):
            raise P2CR1Error("summary manifest row invalid")
        name = str(raw["path"])
        path = summary / name
        if not path.is_file():
            raise P2CR1Error(f"summary manifest file missing: {name}")
        if sha256(path) != str(raw["sha256"]):
            raise P2CR1Error(f"summary manifest hash drift: {name}")
        observed.add(name)
    if observed != REQUIRED_SUMMARY_FILES:
        raise P2CR1Error(
            f"summary manifest file set drift: {sorted(observed ^ REQUIRED_SUMMARY_FILES)}"
        )

    print(
        json.dumps(
            {
                "status": "PASS",
                "decision": DECISION,
                "completed_run_count": EXPECTED_RUNS,
                "hard_gate_pass_variant_count": report["hard_gate_pass_variant_count"],
                "selected_for_2024_variants": selected,
                "feature_store_build_count": timing["feature_store_build_count"],
                "execution_seconds": timing["execution_seconds"],
                "next_stage": report["next_stage"],
                "summary_output_dir": str(summary),
                "evidence_output_dir": str(evidence_root),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
