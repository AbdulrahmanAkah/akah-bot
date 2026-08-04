from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from spotbot.research.rd16c_common import dataframe_content_hash  # noqa: E402
from spotbot.research.rd18_p3x_a1 import load_json, sha256_path  # noqa: E402
from spotbot.research.rd18_p3x_a3b_audit import (  # noqa: E402
    CUTOFF,
    EXPECTED_CONTROL_ROWS,
    EXPECTED_DECISIONS,
    EXPECTED_MEMBERSHIP_ROWS,
    NAMED_OMISSIONS,
    STAGE,
)

EXPECTED_FILES = {
    "legacy-control-candidate-parity.json",
    "legacy-control-evaluated-parity.json",
    "legacy-control-trade-parity.json",
    "effective-operational-membership.csv",
    "omission-replacement-readiness.csv",
    "historical-gap-resolution.csv",
    "selected-member-completed-bar-audit.parquet",
    "selected-member-evaluation-coverage.json",
    "historical-gap-membership-resolution.json",
    "omission-replacement-readiness.json",
    "a3b-authorization-decision.json",
    "rd18-p3x-a3b-runtime-report-v1.json",
}


class A3BValidationError(RuntimeError):
    """Raised when A3B runtime evidence is malformed."""


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    result.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "data/research/rd18_p3x_a3b_runtime",
    )
    result.add_argument("--offline", action="store_true")
    return result


def _manifest_digest(files: list[dict[str, object]]) -> str:
    digest = hashlib.sha256()
    for record in sorted(files, key=lambda item: str(item["path"])):
        digest.update(str(record["path"]).encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(record["sha256"]).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def _validate_manifest(output: Path) -> dict[str, Any]:
    manifest = load_json(output / "output-manifest.json")
    if manifest.get("schema_version") != "rd18-p3x-a3b-output-manifest-v1":
        raise A3BValidationError("A3B manifest schema drifted")
    raw_files = manifest.get("files")
    if not isinstance(raw_files, list):
        raise A3BValidationError("A3B manifest files are invalid")
    names = {str(record.get("path", "")) for record in raw_files if isinstance(record, dict)}
    if names != EXPECTED_FILES:
        raise A3BValidationError(
            f"A3B manifest names differ: expected={sorted(EXPECTED_FILES)}, "
            f"observed={sorted(names)}"
        )
    normalized: list[dict[str, object]] = []
    for raw in raw_files:
        if not isinstance(raw, dict):
            raise A3BValidationError("A3B manifest record is invalid")
        name = str(raw.get("path", ""))
        path = output / name
        if not path.is_file():
            raise A3BValidationError(f"A3B output missing: {path}")
        expected_hash = raw.get("sha256")
        expected_bytes = raw.get("bytes")
        if not isinstance(expected_hash, str):
            raise A3BValidationError(f"A3B manifest hash missing: {name}")
        if sha256_path(path) != expected_hash:
            raise A3BValidationError(f"A3B output hash mismatch: {name}")
        if path.stat().st_size != expected_bytes:
            raise A3BValidationError(f"A3B output byte mismatch: {name}")
        normalized.append(
            {
                "path": name,
                "bytes": expected_bytes,
                "sha256": expected_hash,
            }
        )
    if manifest.get("deterministic_hash") != _manifest_digest(normalized):
        raise A3BValidationError("A3B deterministic manifest hash mismatch")
    for field in (
        "strategy_replay_executed",
        "portfolio_routing_executed",
        "exit_simulation_executed",
        "return_calculation_executed",
        "post_2024_accessed",
        "production_authorized",
    ):
        if manifest.get(field) is not False:
            raise A3BValidationError(f"A3B manifest prohibition drifted: {field}")
    if manifest.get("network_requests") != 0:
        raise A3BValidationError("A3B manifest network count differs from zero")
    return manifest


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.is_file():
        raise A3BValidationError(f"required CSV missing: {path}")
    return pd.read_csv(path, low_memory=False)


def _truth(values: pd.Series) -> pd.Series:
    if pd.api.types.is_bool_dtype(values):
        return values.astype(bool)
    normalized = values.astype(str).str.strip().str.lower()
    if bool(~normalized.isin({"true", "false", "1", "0"}).any()):
        raise A3BValidationError("invalid boolean column")
    return normalized.isin({"true", "1"})


def validate(output: Path) -> dict[str, object]:
    manifest = _validate_manifest(output)
    report = load_json(output / "rd18-p3x-a3b-runtime-report-v1.json")
    decision = load_json(output / "a3b-authorization-decision.json")
    coverage = load_json(output / "selected-member-evaluation-coverage.json")
    gaps = load_json(output / "historical-gap-membership-resolution.json")
    omissions_summary = load_json(output / "omission-replacement-readiness.json")
    effective = _read_csv(output / "effective-operational-membership.csv")
    omissions = _read_csv(output / "omission-replacement-readiness.csv")
    historical = _read_csv(output / "historical-gap-resolution.csv")
    audit = pd.read_parquet(output / "selected-member-completed-bar-audit.parquet")

    checks: dict[str, bool] = {
        "manifest_schema": (manifest.get("schema_version") == "rd18-p3x-a3b-output-manifest-v1"),
        "report_schema": (report.get("schema_version") == "rd18-p3x-a3b-runtime-report-v1"),
        "report_stage": report.get("stage") == STAGE,
        "report_passed": report.get("passed") is True,
        "decision_schema": (
            decision.get("schema_version") == "rd18-p3x-a3b-authorization-decision-v1"
        ),
        "decision_complete": (decision.get("decision") == "RD18_P3X_A3B_EVIDENCE_COMPLETE"),
        "decision_passed": decision.get("passed") is True,
        "a3_reauthorization_ready": (decision.get("authorized_for_a3_reauthorization") is True),
        "replay_not_authorized": decision.get("replay_authorized") is False,
        "next_stage": (decision.get("next_stage") == "RD18_P3X_A3_REAUTHORIZATION_REVIEW"),
        "effective_rows": len(effective) == EXPECTED_MEMBERSHIP_ROWS,
        "omission_rows": len(omissions) == EXPECTED_MEMBERSHIP_ROWS,
        "coverage_schema": (
            coverage.get("schema_version") == "rd18-p3x-a3b-selected-member-coverage-v1"
        ),
        "coverage_exact": (float(coverage.get("member_evaluation_audit_coverage", -1.0)) == 1.0),
        "coverage_passed": coverage.get("passed") is True,
        "audit_rows_match_coverage": (
            len(audit)
            == int(coverage.get("materialized_completed_bar_decisions", -1))
            == int(coverage.get("expected_completed_bar_decisions", -2))
        ),
        "audit_content_hash": (
            dataframe_content_hash(audit) == coverage.get("audit_content_sha256")
        ),
        "gaps_complete": gaps.get("complete") is True,
        "omissions_ready": omissions_summary.get("ready") is True,
        "omission_resolution_ready": (omissions_summary.get("omission_resolution_ready") is True),
        "named_omission_actual_replacements_ready": (
            omissions_summary.get("named_omission_actual_replacements_ready") is True
        ),
        "omissions_unready_zero": omissions_summary.get("unready_rows") == 0,
        "historical_rows_resolved": (
            historical.empty or bool(_truth(historical["resolved"]).all())
        ),
        "omission_ledger_all_resolved": bool(_truth(omissions["omission_resolution_ready"]).all()),
        "named_omission_ledger_actual_replacements": bool(
            set(
                omissions.loc[
                    omissions["omitted_pair"].astype(str).isin(NAMED_OMISSIONS),
                    "omitted_pair",
                ].astype(str)
            )
            == set(NAMED_OMISSIONS)
            and _truth(
                omissions.loc[
                    omissions["omitted_pair"].astype(str).isin(NAMED_OMISSIONS),
                    "replacement_ready",
                ]
            ).all()
            and omissions.loc[
                omissions["omitted_pair"].astype(str).isin(NAMED_OMISSIONS),
                "replacement_pair",
            ]
            .astype(str)
            .str.len()
            .gt(0)
            .all()
        ),
        "replacement_mode_consistent": bool(
            (
                (omissions["resolution_mode"].astype(str) == "REPLACEMENT")
                == _truth(omissions["replacement_ready"])
            ).all()
        ),
        "capacity_after_omission_valid": bool(
            pd.to_numeric(
                omissions["capacity_after_omission"],
                errors="raise",
            )
            .astype(int)
            .isin({5, 6})
            .all()
        ),
        "effective_bar_counts_nonnegative": bool(
            pd.to_numeric(
                effective["completed_bar_count"],
                errors="raise",
            )
            .astype(int)
            .ge(0)
            .all()
        ),
        "effective_bar_domain_nonempty": bool(
            pd.to_numeric(
                effective["completed_bar_count"],
                errors="raise",
            )
            .astype(int)
            .sum()
            > 0
        ),
        "effective_pairs_unique": not bool(
            effective.duplicated(["universe_id", "decision_time", "effective_pair"]).any()
        ),
        "audit_ids_unique": not bool(audit["audit_id"].duplicated().any()),
        "audit_domain_unique": not bool(
            audit.duplicated(
                [
                    "universe_id",
                    "decision_time",
                    "original_pair",
                    "signal_close",
                ]
            ).any()
        ),
        "audit_decisions_valid": (
            set(audit["decision"].astype(str).unique()) <= {"SIGNAL", "NO_SIGNAL"}
        ),
        "audit_pre_cutoff": bool(
            (
                pd.to_datetime(
                    audit["signal_close"],
                    utc=True,
                    errors="raise",
                )
                < CUTOFF
            ).all()
        ),
    }

    for universe in ("C2", "D2", "E2"):
        selected = effective.loc[effective["universe_id"].astype(str) == universe]
        checks[f"{universe}:membership_rows"] = len(selected) == EXPECTED_DECISIONS * 6
        checks[f"{universe}:decisions"] = (
            pd.to_datetime(
                selected["decision_time"],
                utc=True,
                errors="raise",
            ).nunique()
            == EXPECTED_DECISIONS
        )

    for singular, ledger in (
        ("candidate", "candidates"),
        ("evaluated", "evaluated"),
        ("trade", "trades"),
    ):
        payload = load_json(output / f"legacy-control-{singular}-parity.json")
        checks[f"control:{ledger}:schema"] = (
            payload.get("schema_version") == f"rd18-p3x-a3b-legacy-control-{ledger}-parity-v1"
        )
        checks[f"control:{ledger}:passed"] = payload.get("passed") is True
        checks[f"control:{ledger}:rows"] = payload.get("rows") == EXPECTED_CONTROL_ROWS[ledger]
        checks[f"control:{ledger}:authority"] = (
            payload.get("hash_authority") == "RD16L_LOCAL_LEDGER_MANIFEST"
        )
        checks[f"control:{ledger}:value_parity"] = payload.get("column_and_value_parity") is True
        checks[f"control:{ledger}:erratum"] = payload.get("p3r_hash_erratum_applied") is True
        checks[f"control:{ledger}:no_strategy_replay"] = (
            payload.get("strategy_replay_executed") is False
        )
        checks[f"control:{ledger}:no_returns"] = payload.get("return_calculation_executed") is False

    for payload_name, payload in (
        ("report", report),
        ("decision", decision),
    ):
        checks[f"{payload_name}:network_zero"] = payload.get("network_requests") == 0
        for field in (
            "strategy_replay_executed",
            "portfolio_routing_executed",
            "exit_simulation_executed",
            "return_calculation_executed",
            "post_2024_accessed",
            "production_authorized",
        ):
            checks[f"{payload_name}:{field}"] = payload.get(field) is False

    passed = all(checks.values())
    return {
        "schema_version": "rd18-p3x-a3b-validation-v1",
        "stage": STAGE,
        "passed": passed,
        "checks": dict(sorted(checks.items())),
        "membership_rows": len(effective),
        "completed_bar_audit_rows": len(audit),
        "member_evaluation_audit_coverage": float(
            coverage.get("member_evaluation_audit_coverage", 0.0)
        ),
        "historical_gap_resolution_complete": gaps.get("complete") is True,
        "omission_replacement_ready": omissions_summary.get("ready") is True,
        "omission_resolution_ready": (omissions_summary.get("omission_resolution_ready") is True),
        "named_omission_actual_replacements_ready": (
            omissions_summary.get("named_omission_actual_replacements_ready") is True
        ),
        "control_parity_executed": report.get("control_parity_executed") is True,
        "next_stage": report.get("next_stage"),
        "network_requests": 0,
        "strategy_replay_executed": False,
        "return_calculation_executed": False,
        "post_2024_accessed": False,
    }


def main() -> int:
    args = parser().parse_args()
    if not args.offline:
        raise SystemExit("A3B validation requires --offline")
    result = validate(args.output_dir.resolve())
    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except A3BValidationError as exc:
        print(f"A3B_VALIDATION_ERROR={exc}", file=sys.stderr)
        raise SystemExit(2) from exc
