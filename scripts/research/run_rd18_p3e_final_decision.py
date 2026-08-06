from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, cast

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from spotbot.research.rd18_p3e_final_decision import (  # noqa: E402
    PUBLICATION_DECISION,
    STAGE,
    FinalDecisionError,
    decision_precedence_rows,
    derive_final_decision,
    failed_gate_rows,
    publication_markdown,
    sensitivity_aggregate_rows,
)

EXPECTED_HASHES = {
    "data/research/rd18_p3r/performance-gate-registry.json": (
        "033a955c3d13826886692a20690bfb74b6029fedd7778dd7e7d25fea5dd50105"
    ),
    "data/research/rd18_p3r/replay-execution-contract.json": (
        "31ee2bf443332826bbd5a0b8b470bc4dec686d758d91f0d6328dddc7af6d967a"
    ),
    "data/research/rd18_p3r/rd18-p3r-protocol-v1.json": (
        "9754a96ecbeb8f0ff8e2ca7831731e156f43469844edd6835204f5461ec8ca3e"
    ),
}
RUNTIME_HASHES = {
    "dry_report": ("9a51c375a9a59ea3d50328a38c518afce4645de378088650cb1286a50850b4fb"),
    "dry_manifest": ("dd24def921bf5bcc013d2cb38dd6e7fdde6b6cde7099560864f9ff4864f5bfca"),
    "cash_report": ("d918bf20c44e3ca2e422933b201105ae6b57b2e8fb8595be3fed7ecc837f74e4"),
    "cash_manifest": ("8836b397e594eaaa696523cf9c2dfc5b475ab3cbd81a2a7cf36e8b4a5c0bcca9"),
    "sensitivity_report": ("59edeca6b13511e724cac43709e45c2be3ffbc6041574d3525906ff299885697"),
    "sensitivity_manifest": ("d24bd028b7f3add5037c077417c8a3e90ac722fc97f2e378c5322ba72d5feb6b"),
}


class RunnerError(RuntimeError):
    """Raised when final decision evidence cannot be published."""


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    result.add_argument("--repo-root", type=Path, default=ROOT)
    result.add_argument(
        "--dry-run-runtime",
        type=Path,
        default=ROOT / "data/research/rd18_p3e_dry_run_runtime",
    )
    result.add_argument(
        "--cash-runtime",
        type=Path,
        default=(ROOT / "data/research/rd18_p3e_cash_remediation_runtime"),
    )
    result.add_argument(
        "--sensitivity-runtime",
        type=Path,
        default=(ROOT / "data/research/rd18_p3e_sensitivity_runtime"),
    )
    result.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "data/research/rd18_p3e_final_runtime",
    )
    result.add_argument("--preflight-only", action="store_true")
    result.add_argument("--publish", action="store_true")
    return result


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise RunnerError(f"JSON missing: {path}")
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise RunnerError(f"JSON object expected: {path}")
    return value


def load_json_object_list(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise RunnerError(f"JSON missing: {path}")
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise RunnerError(f"JSON object list expected: {path}")
    return value


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise RunnerError(f"CSV missing: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def json_ready(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_ready(item) for item in value]
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if hasattr(value, "item"):
        return json_ready(cast(Any, value).item())
    if isinstance(value, float) and not pd.notna(value):
        return None
    return value


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            json_ready(value),
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )


def write_rows(
    path: Path,
    rows: Sequence[Mapping[str, object]],
) -> None:
    if not rows:
        raise RunnerError(f"empty CSV rows: {path}")
    fields = sorted({str(key) for row in rows for key in row})
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fields,
            extrasaction="raise",
            lineterminator="\n",
        )
        writer.writeheader()
        for row in rows:
            writer.writerow({field: json_ready(row.get(field)) for field in fields})


def verify_manifest(
    root: Path,
    manifest: Mapping[str, object],
) -> None:
    files = manifest.get("files")
    if not isinstance(files, list):
        raise RunnerError("manifest file list is invalid")
    for raw in files:
        if not isinstance(raw, Mapping):
            raise RunnerError("manifest row is invalid")
        relative = str(raw["path"])
        path = root / relative
        if not path.is_file():
            raise RunnerError(f"manifest file missing: {relative}")
        if path.stat().st_size != int(cast(int, raw["bytes"])) or sha256(path) != str(
            raw["sha256"]
        ):
            raise RunnerError(f"manifest mismatch: {relative}")


def verify_inputs(
    repo: Path,
    dry: Path,
    cash: Path,
    sensitivity: Path,
) -> dict[str, object]:
    for relative, expected in EXPECTED_HASHES.items():
        path = repo / relative
        if not path.is_file() or sha256(path) != expected:
            raise RunnerError(f"frozen input drifted: {relative}")

    paths = {
        "dry_report": (dry / "rd18-p3e-technical-dry-run-report-v1.json"),
        "dry_manifest": dry / "output-manifest.json",
        "cash_report": (cash / "rd18-p3e-cash-feasibility-remediation-report-v1.json"),
        "cash_manifest": cash / "output-manifest.json",
        "sensitivity_report": (sensitivity / "rd18-p3e-loyo-loao-sensitivity-report-v1.json"),
        "sensitivity_manifest": sensitivity / "output-manifest.json",
    }
    observed = {name: sha256(path) for name, path in paths.items()}
    if observed != RUNTIME_HASHES:
        raise RunnerError(f"runtime evidence hash drift: {observed}")

    dry_report = load_json(paths["dry_report"])
    dry_manifest = load_json(paths["dry_manifest"])
    cash_report = load_json(paths["cash_report"])
    cash_manifest = load_json(paths["cash_manifest"])
    sensitivity_report = load_json(paths["sensitivity_report"])
    sensitivity_manifest = load_json(paths["sensitivity_manifest"])
    verify_manifest(dry, dry_manifest)
    verify_manifest(cash, cash_manifest)
    verify_manifest(sensitivity, sensitivity_manifest)

    checks = {
        "dry_passed": dry_report.get("passed") is True,
        "dry_decision": (dry_report.get("decision") == "RD18_P3E_TECHNICAL_DRY_RUN_COMPLETE"),
        "cash_passed": cash_report.get("passed") is True,
        "cash_decision": (
            cash_report.get("decision") == ("RD18_P3E_CASH_FEASIBILITY_REMEDIATION_COMPLETE")
        ),
        "cash_corrected_runs": cash_report.get("corrected_runs") == 6,
        "sensitivity_passed": (sensitivity_report.get("passed") is True),
        "sensitivity_decision": (
            sensitivity_report.get("decision") == "RD18_P3E_LOYO_AND_LOAO_SENSITIVITY_COMPLETE"
        ),
        "sensitivity_loyo": (sensitivity_report.get("loyo_run_count") == 36),
        "sensitivity_loao": (sensitivity_report.get("loao_run_count") == 158),
        "final_ready": (sensitivity_report.get("final_decision_ready") is True),
        "final_not_made": (sensitivity_report.get("final_decision_made") is False),
        "no_post_2024": all(
            report.get("post_2024_accessed") is False
            for report in (
                dry_report,
                cash_report,
                sensitivity_report,
            )
        ),
        "no_production": all(
            report.get("production_authorized") is False
            for report in (
                dry_report,
                cash_report,
                sensitivity_report,
            )
        ),
        "no_tuning": (
            cash_report.get("per_universe_tuning") is False
            and sensitivity_report.get("per_universe_tuning") is False
        ),
    }
    if not all(checks.values()):
        failed = sorted(name for name, value in checks.items() if not value)
        raise RunnerError(f"final input checks failed: {failed}")
    return {
        "checks": checks,
        "hashes": observed,
        "dry_report": dry_report,
        "cash_report": cash_report,
        "sensitivity_report": sensitivity_report,
        "manifest_deterministic_hashes": {
            "dry": dry_manifest["deterministic_hash"],
            "cash": cash_manifest["deterministic_hash"],
            "sensitivity": sensitivity_manifest["deterministic_hash"],
        },
    }


def preflight(
    repo: Path,
    dry: Path,
    cash: Path,
    sensitivity: Path,
) -> dict[str, object]:
    upstream = verify_inputs(repo, dry, cash, sensitivity)
    sensitivity_report = cast(
        Mapping[str, object],
        upstream["sensitivity_report"],
    )
    return {
        "schema_version": "rd18-p3e-final-preflight-v1",
        "stage": STAGE,
        "passed": True,
        "upstream_checks": upstream["checks"],
        "upstream_hashes": upstream["hashes"],
        "decision_precedence_outcome": sensitivity_report["decision_precedence_outcome"],
        "final_decision_ready": True,
        "network_requests": 0,
        "strategy_replay_executed": False,
        "portfolio_return_calculation_executed": False,
        "performance_reporting_executed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
        "next_stage": "RD18_P3E_FINAL_DECISION_MATERIALIZATION",
    }


def deterministic_manifest(root: Path) -> dict[str, object]:
    files: list[dict[str, object]] = []
    aggregate = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name == "output-manifest.json":
            continue
        relative = path.relative_to(root).as_posix()
        row = {
            "path": relative,
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
        }
        if path.suffix == ".csv":
            row["rows"] = len(read_csv(path))
        files.append(row)
        aggregate.update(relative.encode("utf-8"))
        aggregate.update(b"\0")
        aggregate.update(str(row["sha256"]).encode("ascii"))
        aggregate.update(b"\n")
    return {
        "schema_version": "rd18-p3e-final-manifest-v1",
        "files": files,
        "deterministic_hash": aggregate.hexdigest(),
        "network_requests": 0,
        "strategy_replay_executed": False,
        "portfolio_routing_executed": False,
        "exit_simulation_executed": False,
        "return_calculation_executed": False,
        "performance_reporting_executed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
    }


def materialize(
    repo: Path,
    dry: Path,
    cash: Path,
    sensitivity: Path,
    output: Path,
) -> dict[str, object]:
    upstream = verify_inputs(repo, dry, cash, sensitivity)
    dry_report = cast(
        Mapping[str, object],
        upstream["dry_report"],
    )
    cash_report = cast(
        Mapping[str, object],
        upstream["cash_report"],
    )
    sensitivity_report = cast(
        Mapping[str, object],
        upstream["sensitivity_report"],
    )
    corrected_base = pd.read_csv(cash / "corrected-base-run-summary.csv")
    universe_gates = load_json_object_list(cash / "universe-gate-evaluation.json")
    cross = load_json(cash / "cross-universe-robustness.json")
    sensitivity_gate = load_json(sensitivity / "sensitivity-gate-evaluation.json")
    loyo = pd.read_csv(sensitivity / "loyo-results.csv")
    loao = pd.read_csv(sensitivity / "loao-results.csv")

    capital_feasible = bool(
        corrected_base["capital_feasible"].astype(bool).all()
        and (
            pd.to_numeric(
                corrected_base["minimum_cash"],
                errors="raise",
            )
            >= -1e-6
        ).all()
    )
    technical_checks = {
        "dry_run_valid": dry_report.get("passed") is True,
        "cash_remediation_valid": cash_report.get("passed") is True,
        "sensitivity_execution_valid": (sensitivity_report.get("passed") is True),
        "base_parity_valid": (sensitivity_report.get("base_parity", {}).get("passed") is True),
        "cash_feasible": capital_feasible,
        "no_post_2024_access": (sensitivity_report.get("post_2024_accessed") is False),
        "no_threshold_changes": (
            sensitivity_report.get("thresholds_changed_after_results") is False
        ),
        "no_per_universe_tuning": (sensitivity_report.get("per_universe_tuning") is False),
        "no_post_hoc_trade_deletion": (sensitivity_report.get("post_hoc_trade_deletion") is False),
        "lineage_manifests_verified": True,
    }
    technical_valid = all(technical_checks.values())

    classification = cash_report.get("corrected_base_classification")
    if not isinstance(classification, Mapping):
        raise RunnerError("corrected base classification invalid")
    base_passed = bool(classification["base_economic_gates_passed"])
    cross_passed = bool(classification["cross_universe_robustness_passed"])
    sensitivity_passed = bool(sensitivity_gate["passed"])
    strategic_met = bool(classification["strategic_objective_met"])
    final = derive_final_decision(
        technical_valid=technical_valid,
        base_economic_gates_passed=base_passed,
        cross_universe_robustness_passed=cross_passed,
        sensitivity_gates_passed=sensitivity_passed,
        strategic_objective_met=strategic_met,
    )
    if final["decision_precedence_outcome"] != sensitivity_report["decision_precedence_outcome"]:
        raise RunnerError("final precedence differs from sensitivity report")
    if final["decision_precedence_outcome"] != "WORST_UNIVERSE_ECONOMIC_FAILURE":
        raise RunnerError("unexpected final P3E outcome")

    precedence = decision_precedence_rows(
        technical_valid=technical_valid,
        base_economic_gates_passed=base_passed,
        cross_universe_robustness_passed=cross_passed,
        sensitivity_gates_passed=sensitivity_passed,
        strategic_objective_met=strategic_met,
    )
    sensitivity_rows = [
        *sensitivity_aggregate_rows(loyo, run_type="LOYO"),
        *sensitivity_aggregate_rows(loao, run_type="LOAO"),
    ]
    gate_failures = failed_gate_rows(cast(Sequence[Mapping[str, object]], universe_gates))
    base_rows = corrected_base.to_dict(orient="records")
    evidence = [
        {
            "stage": "P3R",
            "role": "FROZEN_GATE_AUTHORITY",
            "path": ("data/research/rd18_p3r/performance-gate-registry.json"),
            "sha256": EXPECTED_HASHES["data/research/rd18_p3r/performance-gate-registry.json"],
        },
        {
            "stage": "P3E_TECHNICAL_DRY_RUN",
            "role": "TECHNICAL_VALIDITY",
            "path": (
                "data/research/rd18_p3e_dry_run_runtime/rd18-p3e-technical-dry-run-report-v1.json"
            ),
            "sha256": RUNTIME_HASHES["dry_report"],
        },
        {
            "stage": "P3E_CASH_FEASIBILITY_REMEDIATION",
            "role": "CORRECTED_BASE_ECONOMICS",
            "path": (
                "data/research/rd18_p3e_cash_remediation_runtime/"
                "rd18-p3e-cash-feasibility-remediation-report-v1.json"
            ),
            "sha256": RUNTIME_HASHES["cash_report"],
        },
        {
            "stage": "P3E_LOYO_LOAO_SENSITIVITY",
            "role": "SENSITIVITY_EVIDENCE",
            "path": (
                "data/research/rd18_p3e_sensitivity_runtime/"
                "rd18-p3e-loyo-loao-sensitivity-report-v1.json"
            ),
            "sha256": RUNTIME_HASHES["sensitivity_report"],
        },
    ]

    report = {
        "schema_version": "rd18-p3e-final-decision-report-v1",
        "stage": STAGE,
        "decision": PUBLICATION_DECISION,
        "passed": True,
        "execution_status": "COMPLETE",
        **final,
        "final_decision_ready": True,
        "final_decision_made": True,
        "p3e_closed": not bool(final["final_advancement_eligible"]),
        "technical_valid": technical_valid,
        "technical_checks": technical_checks,
        "base_economic_gates_passed": base_passed,
        "cross_universe_robustness_passed": cross_passed,
        "sensitivity_gates_passed": sensitivity_passed,
        "strategic_objective_met": strategic_met,
        "corrected_base_classification": classification,
        "cross_universe_robustness": cross,
        "sensitivity_gate_evaluation": sensitivity_gate,
        "base_run_count": len(base_rows),
        "loyo_run_count": len(loyo),
        "loao_run_count": len(loao),
        "loao_applicability_rows": int(sensitivity_report["loao_applicability_rows"]),
        "all_corrected_runs_cash_feasible": capital_feasible,
        "one_x_base_all_positive": bool(
            (
                corrected_base.loc[
                    corrected_base["cost_multiplier"] == 1.0,
                    "net_return",
                ]
                > 0.0
            ).all()
        ),
        "two_x_base_all_negative": bool(
            (
                corrected_base.loc[
                    corrected_base["cost_multiplier"] == 2.0,
                    "net_return",
                ]
                < 0.0
            ).all()
        ),
        "prior_negative_cash_base_superseded": True,
        "strategy_replay_executed_in_this_stage": False,
        "portfolio_routing_executed_in_this_stage": False,
        "exit_simulation_executed_in_this_stage": False,
        "return_calculation_executed_in_this_stage": False,
        "performance_reporting_executed_in_this_stage": False,
        "thresholds_changed_after_results": False,
        "per_universe_tuning": False,
        "post_hoc_trade_deletion": False,
        "network_requests": 0,
        "post_2024_accessed": False,
        "holdout_2025_accessed": False,
        "holdout_2026_accessed": False,
        "production_authorized": False,
        "recommended_followup": ("NEW_PREREGISTERED_CANDIDATE_REQUIRED"),
        "followup_constraint": (
            "Do not tune, reinterpret, or advance the rejected P3E "
            "candidate after observing results."
        ),
        "upstream_hashes": upstream["hashes"],
        "upstream_manifest_deterministic_hashes": upstream["manifest_deterministic_hashes"],
    }

    temporary = output.with_name(f".{output.name}.tmp-{os.getpid()}")
    if temporary.exists():
        shutil.rmtree(temporary)
    temporary.mkdir(parents=True)
    try:
        write_rows(
            temporary / "final-base-metrics.csv",
            base_rows,
        )
        write_rows(
            temporary / "final-sensitivity-aggregate.csv",
            sensitivity_rows,
        )
        write_rows(
            temporary / "final-gate-failures.csv",
            gate_failures,
        )
        write_rows(
            temporary / "final-decision-precedence.csv",
            precedence,
        )
        write_rows(
            temporary / "evidence-lineage.csv",
            evidence,
        )
        write_json(
            temporary / "rd18-p3e-final-decision-v1.json",
            report,
        )
        markdown = publication_markdown(
            report=report,
            base_rows=base_rows,
            sensitivity_rows=sensitivity_rows,
            failed_gates=gate_failures,
        )
        (temporary / "rd18-p3e-final-publication-v1.md").write_text(
            markdown,
            encoding="utf-8",
            newline="\n",
        )
        write_json(
            temporary / "output-manifest.json",
            deterministic_manifest(temporary),
        )
        if output.exists():
            shutil.rmtree(output)
        os.replace(temporary, output)
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise
    return report


def main() -> int:
    args = parser().parse_args()
    if not args.preflight_only and not args.publish:
        raise SystemExit("Use --preflight-only or --publish")
    repo = args.repo_root.resolve()
    common = {
        "repo": repo,
        "dry": args.dry_run_runtime.resolve(),
        "cash": args.cash_runtime.resolve(),
        "sensitivity": args.sensitivity_runtime.resolve(),
    }
    if args.preflight_only:
        result = preflight(**common)
    else:
        result = materialize(
            **common,
            output=args.output_dir.resolve(),
        )
    print(
        json.dumps(
            json_ready(result),
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
        )
    )
    return 0 if result.get("passed") is True else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RunnerError, FinalDecisionError) as exc:
        print(f"P3E_FINAL_DECISION_ERROR={exc}", file=sys.stderr)
        raise SystemExit(2) from exc
