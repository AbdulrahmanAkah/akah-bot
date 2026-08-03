from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd

EXPECTED_DECISIONS = 301
INPUT_NAMES = (
    "c2-operational-membership.csv",
    "d2-operational-membership.csv",
    "e2-operational-membership.csv",
    "legacy-six-asset-control-parity.json",
    "selected-member-evaluation-coverage.json",
    "historical-gap-membership-resolution.json",
    "omission-replacement-readiness.json",
)


class A3AValidationError(RuntimeError):
    pass


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    result.add_argument("--input-dir", type=Path, required=True)
    result.add_argument("--output-dir", type=Path, required=True)
    result.add_argument("--offline", action="store_true")
    return result


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise A3AValidationError(f"JSON object expected: {path}")
    return value


def read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, low_memory=False)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def validate_manifest(
    base: Path,
    manifest: dict[str, Any],
) -> dict[str, bool]:
    checks: dict[str, bool] = {}
    raw_files = manifest.get("files")
    if not isinstance(raw_files, list):
        raise A3AValidationError("manifest files are invalid")
    aggregate = hashlib.sha256()
    for raw in raw_files:
        if not isinstance(raw, dict):
            raise A3AValidationError("manifest row is invalid")
        name = str(raw["path"])
        path = base / name
        digest = str(raw["sha256"])
        checks[f"file:{name}"] = path.is_file()
        checks[f"bytes:{name}"] = path.is_file() and path.stat().st_size == int(raw["bytes"])
        checks[f"hash:{name}"] = path.is_file() and sha256(path) == digest
        aggregate.update(name.encode("utf-8"))
        aggregate.update(b"\0")
        aggregate.update(digest.encode("ascii"))
        aggregate.update(b"\n")
    checks["manifest_hash"] = manifest.get("deterministic_hash") == aggregate.hexdigest()
    checks["manifest_no_replay"] = manifest.get("strategy_replay_executed") is False
    checks["manifest_no_returns"] = manifest.get("return_calculation_executed") is False
    return checks


def membership_checks(
    frame: pd.DataFrame,
    *,
    universe: str,
) -> dict[str, bool]:
    required = {
        "universe_id",
        "decision_time",
        "effective_end",
        "pair",
        "canonical_asset_id",
        "rank",
        "member",
        "top6",
        "membership_source",
    }
    times = pd.to_datetime(
        frame["decision_time"],
        utc=True,
        errors="raise",
    )
    ranks = pd.to_numeric(frame["rank"], errors="raise")
    counts = frame.groupby("decision_time").size()
    return {
        f"{universe}:schema": required.issubset(frame.columns),
        f"{universe}:universe_id": (set(frame["universe_id"].astype(str).unique()) == {universe}),
        f"{universe}:decisions": (int(times.nunique()) == EXPECTED_DECISIONS),
        f"{universe}:mondays": all(pd.Timestamp(value).weekday() == 0 for value in times.unique()),
        f"{universe}:duplicates": not bool(
            frame.duplicated(
                ["decision_time", "pair"],
                keep=False,
            ).any()
        ),
        f"{universe}:member_limit": bool((counts <= 8).all()),
        f"{universe}:positive_members": bool((counts > 0).all()),
        f"{universe}:rank_positive": bool((ranks > 0).all()),
        f"{universe}:top6_consistent": bool(
            (frame["top6"].astype(str).str.lower().isin({"true", "1"}) == (ranks <= 6)).all()
        ),
    }


def main() -> int:
    args = parser().parse_args()
    if not args.offline:
        raise SystemExit("A3A validator requires --offline")

    input_dir = args.input_dir.resolve()
    output_dir = args.output_dir.resolve()
    report = load_json(output_dir / "rd18-p3x-a3a-runtime-report-v1.json")
    control = load_json(input_dir / "legacy-six-asset-control-parity.json")
    coverage = load_json(input_dir / "selected-member-evaluation-coverage.json")
    gaps = load_json(input_dir / "historical-gap-membership-resolution.json")
    omission = load_json(input_dir / "omission-replacement-readiness.json")
    replacement = read_csv(output_dir / "omission-replacement-ledger.csv")
    gap_ledger = read_csv(output_dir / "historical-gap-membership-ledger.csv")

    checks: dict[str, bool] = {
        "report_schema": (report.get("schema_version") == "rd18-p3x-a3a-runtime-report-v1"),
        "report_stage": (report.get("stage") == "RD18_P3X_A3A_CANONICAL_MEMBERSHIP_BUILD"),
        "report_passed": report.get("passed") is True,
        "report_no_replay": (report.get("strategy_replay_executed") is False),
        "report_no_returns": (report.get("return_calculation_executed") is False),
        "control_not_executed": (control.get("status") == "CONTROL_ONLY_REPLAY_NOT_EXECUTED"),
        "control_candidate_false": (control.get("candidate_hash_match") is False),
        "control_evaluated_false": (control.get("evaluated_hash_match") is False),
        "control_trade_false": (control.get("trade_hash_match") is False),
        "control_no_replay": (control.get("strategy_replay_executed") is False),
    }

    decision_counts: dict[str, int] = {}
    for universe, name in (
        ("C2", "c2-operational-membership.csv"),
        ("D2", "d2-operational-membership.csv"),
        ("E2", "e2-operational-membership.csv"),
    ):
        frame = read_csv(input_dir / name)
        checks.update(membership_checks(frame, universe=universe))
        decision_counts[universe] = int(
            pd.to_datetime(
                frame["decision_time"],
                utc=True,
                errors="raise",
            ).nunique()
        )
    checks["report_decisions_match"] = report.get("membership_decisions") == decision_counts

    candidate_coverage = float(
        coverage.get(
            "full_top6_candidate_coverage_fraction",
            -1.0,
        )
    )
    audit_coverage = float(coverage.get("member_evaluation_audit_coverage", -1.0))
    checks["candidate_coverage_range"] = 0.0 <= candidate_coverage <= 1.0
    checks["audit_coverage_explicit_zero"] = (
        audit_coverage == 0.0
        and coverage.get("member_evaluation_audit_status")
        == "COMPLETED_BAR_NO_SIGNAL_AUDIT_NOT_MATERIALIZED"
    )
    checks["coverage_report_match"] = (
        float(
            report.get(
                "full_top6_candidate_coverage_fraction",
                -1.0,
            )
        )
        == candidate_coverage
        and float(
            report.get(
                "member_evaluation_audit_coverage",
                -1.0,
            )
        )
        == audit_coverage
    )

    replacement_ready = bool(
        replacement["replacement_ready"].astype(str).str.lower().isin({"true", "1"}).all()
    )
    checks["omission_ledger_nonempty"] = not replacement.empty
    checks["omission_ready_match"] = (
        omission.get("ready") is replacement_ready
        and report.get("omission_replacement_ready") is replacement_ready
    )

    gap_complete = gap_ledger.empty
    checks["gap_complete_match"] = (
        gaps.get("complete") is gap_complete
        and report.get("historical_gap_resolution_complete") is gap_complete
    )

    input_manifest = load_json(input_dir / "output-manifest.json")
    runtime_manifest = load_json(output_dir / "output-manifest.json")
    checks.update(
        {
            f"input:{name}": passed
            for name, passed in validate_manifest(
                input_dir,
                input_manifest,
            ).items()
        }
    )
    checks.update(
        {
            f"runtime:{name}": passed
            for name, passed in validate_manifest(
                output_dir,
                runtime_manifest,
            ).items()
        }
    )
    checks["input_names_complete"] = all((input_dir / name).is_file() for name in INPUT_NAMES)

    passed = all(checks.values())
    response = {
        "schema_version": "rd18-p3x-a3a-validation-v1",
        "passed": passed,
        "membership_decisions": decision_counts,
        "full_top6_candidate_coverage_fraction": candidate_coverage,
        "member_evaluation_audit_coverage": audit_coverage,
        "historical_gap_resolution_complete": gap_complete,
        "omission_replacement_ready": replacement_ready,
        "control_parity_executed": False,
        "checks": dict(sorted(checks.items())),
        "network_requests": 0,
        "strategy_replay_executed": False,
        "return_calculation_executed": False,
    }
    print(json.dumps(response, indent=2, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
