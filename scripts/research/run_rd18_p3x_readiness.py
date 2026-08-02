from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from spotbot.research.atomic_output import atomic_write_csv, atomic_write_json  # noqa: E402
from spotbot.research.rd18_p3x_readiness import (  # noqa: E402
    ACQUISITION_FIELDS,
    SOURCE_AUDIT_FIELDS,
    acquisition_plan,
    audit_sources,
    deterministic_manifest,
    feature_lookback_audit,
    generator_readiness_audit,
    load_c2_requirements,
    load_committed_readiness,
    load_hourly_sources,
    reconcile_input_manifests,
    report_jsonable,
    summarize,
)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Audit RD18-P3X full-C2 hourly data and raw candidate-generator readiness."
    )
    result.add_argument("--repo-root", type=Path, default=ROOT)
    result.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "data" / "research" / "rd18_p3x_runtime",
    )
    result.add_argument("--offline", action="store_true", required=True)
    result.add_argument(
        "--skip-file-hashes",
        action="store_true",
        help="Diagnostic only; a skipped hash cannot make a source READY.",
    )
    return result


def run(repo_root: Path, output_dir: Path, *, verify_hashes: bool) -> dict[str, object]:
    repo_root = repo_root.resolve()
    output_dir = output_dir.resolve()
    p1r2 = repo_root / "data" / "research" / "rd18_p1r2"
    rd16b = repo_root / "data" / "research" / "rd16b"
    input_reconciliation = reconcile_input_manifests(repo_root)
    requirements = load_c2_requirements(p1r2 / "corrected-daily-coverage-audit.csv")
    sources = load_hourly_sources(rd16b / "source-manifest-v1.json")
    committed = load_committed_readiness(rd16b / "data-readiness.csv")
    source_rows = audit_sources(
        repo_root,
        sources,
        committed,
        verify_hashes=verify_hashes,
    )
    plan_rows = acquisition_plan(requirements, sources, source_rows)
    feature_audit = feature_lookback_audit(
        repo_root / "src" / "spotbot" / "research" / "rd16c_features.py"
    )
    generator_audit = generator_readiness_audit(
        repo_root / "src" / "spotbot" / "research" / "rd16l_architecture.py",
        repo_root / "src" / "spotbot" / "research" / "rd16c_features.py",
    )
    report = report_jsonable(
        summarize(requirements, sources, plan_rows, generator_audit, feature_audit)
    )
    report["input_reconciliation"] = input_reconciliation
    if not bool(input_reconciliation["all_inputs_match"]):
        report["decision"] = "RD18_P3X_INPUT_RECONCILIATION_FAILED"
        report["next_stage"] = "RD18_BLOCKED_PENDING_P3R_OR_P1R2_REPAIR"
        report["authorizations"]["full_c2_hourly_data_acquisition_authorized"] = False
        report["authorizations"]["raw_candidate_generator_extraction_authorized"] = False
        report["authorizations"]["three_universe_candidate_dry_run_authorized"] = False
    report["runtime"] = {
        "repo_root": str(repo_root),
        "output_dir": str(output_dir),
        "source_hashes_verified": verify_hashes,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_csv(
        output_dir / "full-c2-hourly-acquisition-plan.csv",
        plan_rows,
        ACQUISITION_FIELDS,
    )
    atomic_write_csv(
        output_dir / "current-hourly-source-audit.csv",
        source_rows,
        SOURCE_AUDIT_FIELDS,
    )
    atomic_write_json(output_dir / "input-reconciliation.json", input_reconciliation)
    atomic_write_json(output_dir / "feature-lookback-audit.json", feature_audit)
    atomic_write_json(output_dir / "raw-candidate-generator-readiness.json", generator_audit)
    atomic_write_json(output_dir / "rd18-p3x-runtime-report-v1.json", report)
    atomic_write_json(
        output_dir / "request-manifest.json",
        {
            "schema_version": "rd18-p3x-runtime-request-manifest-v1",
            "network_requests": 0,
            "requests": [],
            "offline": True,
        },
    )
    generated = [
        "current-hourly-source-audit.csv",
        "feature-lookback-audit.json",
        "full-c2-hourly-acquisition-plan.csv",
        "input-reconciliation.json",
        "raw-candidate-generator-readiness.json",
        "rd18-p3x-runtime-report-v1.json",
        "request-manifest.json",
    ]
    manifest = deterministic_manifest(output_dir, generated)
    atomic_write_json(output_dir / "output-manifest.json", manifest)
    return report


def main() -> int:
    args = parser().parse_args()
    report = run(
        args.repo_root,
        args.output_dir,
        verify_hashes=not args.skip_file_hashes,
    )
    print(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
