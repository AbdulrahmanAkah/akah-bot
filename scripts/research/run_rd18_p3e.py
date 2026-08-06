from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from spotbot.data.store import ParquetCandleStore  # noqa: E402
from spotbot.research.rd18_p3e_replay import (  # noqa: E402
    EXPECTED_MEMBERSHIP_ROWS,
    REQUIRED_A2_COLUMNS,
    validate_effective_membership,
)

EXPECTED_HEAD = "45794dc0cd0908cccd106ba9c591071f6836e1cd"
EXPECTED_A2_PARTITIONS = 341
EXPECTED_GENERATED = 339
EXPECTED_NO_FEATURE = 2
EXPECTED_A3B_AUDIT_ROWS = 825912

P3R_HASHES = {
    "frozen-strategy-candidate.json": (
        "b3748664aefa334c702c36a8e34ae8b0d339e265b15b0cdb99eeec06bb37a3b6"
    ),
    "performance-gate-registry.json": (
        "033a955c3d13826886692a20690bfb74b6029fedd7778dd7e7d25fea5dd50105"
    ),
    "preexecution-readiness.json": (
        "72b14e0703a1eb68bd504aad97cf4d4addc44a87c68dca0a6459cd9afae1ddd3"
    ),
    "replay-execution-contract.json": (
        "31ee2bf443332826bbd5a0b8b470bc4dec686d758d91f0d6328dddc7af6d967a"
    ),
    "rd18-p3r-protocol-v1.json": (
        "9754a96ecbeb8f0ff8e2ca7831731e156f43469844edd6835204f5461ec8ca3e"
    ),
}

OUTPUT_FLAGS = {
    "network_requests": 0,
    "strategy_replay_executed": False,
    "portfolio_routing_executed": False,
    "exit_simulation_executed": False,
    "return_calculation_executed": False,
    "post_2024_accessed": False,
    "production_authorized": False,
}


class P3EBuildError(RuntimeError):
    """Raised when the P3E implementation preflight is not reproducible."""


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description=(
            "Validate and materialize the P3E implementation build without "
            "executing the three-universe replay or calculating returns."
        )
    )
    result.add_argument("--repo-root", type=Path, default=ROOT)
    result.add_argument(
        "--a2-runtime",
        type=Path,
        default=ROOT / "data/research/rd18_p3x_a2_runtime",
    )
    result.add_argument(
        "--a3-runtime",
        type=Path,
        default=ROOT / "data/research/rd18_p3x_a3_runtime",
    )
    result.add_argument(
        "--a3b-runtime",
        type=Path,
        default=ROOT / "data/research/rd18_p3x_a3b_runtime",
    )
    result.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "data/research/rd18_p3e_build_runtime",
    )
    result.add_argument("--preflight-only", action="store_true")
    result.add_argument("--write-ledgers", action="store_true")
    return result


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise P3EBuildError(f"required JSON missing: {path}")
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise P3EBuildError(f"JSON object expected: {path}")
    return value


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise P3EBuildError(f"required CSV missing: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            value,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )


def write_csv(
    path: Path,
    rows: list[dict[str, object]],
    fields: tuple[str, ...],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fields,
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def verify_p3r(repo: Path) -> dict[str, object]:
    root = repo / "data/research/rd18_p3r"
    hashes: dict[str, str] = {}
    for name, expected in P3R_HASHES.items():
        path = root / name
        if not path.is_file():
            raise P3EBuildError(f"P3R contract file missing: {path}")
        actual = sha256(path)
        if actual != expected:
            raise P3EBuildError(f"P3R hash drift: {name}: expected={expected}, actual={actual}")
        hashes[name] = actual

    frozen = load_json(root / "frozen-strategy-candidate.json")
    contract = load_json(root / "replay-execution-contract.json")
    gates = load_json(root / "performance-gate-registry.json")
    if not (
        frozen.get("architecture_id") == "COMPOSITE_ALPHA_V3"
        and frozen.get("source_variant_id") == "STRONG_BULL_HOLD_96"
        and contract.get("status") == "PREREGISTERED_NOT_EXECUTED"
        and contract.get("strategy", {}).get("parameter_changes_allowed") is False
        and contract.get("strategy", {}).get("per_universe_tuning_allowed") is False
        and contract.get("time", {}).get("2025_access") is False
        and contract.get("time", {}).get("2026_access") is False
        and gates.get("thresholds_may_change_after_results") is False
    ):
        raise P3EBuildError("P3R frozen semantics drifted")
    return {
        "hashes": hashes,
        "architecture_id": frozen.get("architecture_id"),
        "source_variant_id": frozen.get("source_variant_id"),
        "contract_status": contract.get("status"),
        "cost_multipliers": contract.get("execution", {}).get("cost_multipliers"),
        "universes": [
            row.get("id") for row in contract.get("universes", []) if isinstance(row, dict)
        ],
    }


def verify_a3(repo: Path, runtime: Path) -> dict[str, object]:
    report = load_json(runtime / "authorization-decision.json")
    if not all(
        (
            report.get("authorized") is True,
            report.get("technical_valid") is True,
            report.get("decision") == "RD18_P3X_A3_REPLAY_AUTHORIZED",
            report.get("blockers") == [],
            report.get("next_stage") == "RD18_P3E_EXECUTE_PREREGISTERED_THREE_UNIVERSE_REPLAY",
            report.get("strategy_replay_executed") is False,
            report.get("return_calculation_executed") is False,
            report.get("network_requests") == 0,
        )
    ):
        raise P3EBuildError("A3 authorization is not valid")

    lineage = read_csv(runtime / "lineage-hash-manifest.csv")
    if len(lineage) != 17:
        raise P3EBuildError("A3 lineage manifest row count drifted")
    for row in lineage:
        relative = str(row.get("path", "")).strip()
        path = repo / relative
        expected = str(row.get("sha256", "")).strip()
        if not path.is_file() or sha256(path) != expected:
            raise P3EBuildError(f"A3 frozen lineage drift: {relative}")
    return {
        "decision": report.get("decision"),
        "authorized": report.get("authorized"),
        "lineage_rows": len(lineage),
    }


def verify_a3b(runtime: Path) -> tuple[pd.DataFrame, dict[str, object]]:
    report = load_json(runtime / "rd18-p3x-a3b-runtime-report-v1.json")
    if not all(
        (
            report.get("passed") is True,
            report.get("decision") == "RD18_P3X_A3B_EVIDENCE_COMPLETE",
            report.get("membership_rows") == EXPECTED_MEMBERSHIP_ROWS,
            report.get("completed_bar_audit_rows") == EXPECTED_A3B_AUDIT_ROWS,
            report.get("member_evaluation_audit_coverage") == 1.0,
            report.get("historical_gap_resolution_complete") is True,
            report.get("omission_resolution_ready") is True,
            report.get("named_omission_actual_replacements_ready") is True,
            report.get("strategy_replay_executed") is False,
            report.get("return_calculation_executed") is False,
            report.get("network_requests") == 0,
        )
    ):
        raise P3EBuildError("A3B evidence drifted")

    membership = validate_effective_membership(
        pd.read_csv(runtime / "effective-operational-membership.csv")
    )
    omission_path = runtime / "omission-replacement-readiness.csv"
    omission = pd.read_csv(omission_path)
    required_omission = {
        "universe_id",
        "decision_time",
        "effective_end",
        "omitted_pair",
        "replacement_pair",
        "replacement_ready",
        "omission_resolution_ready",
        "resolution_mode",
        "capacity_after_omission",
    }
    missing = sorted(required_omission.difference(omission.columns))
    if missing:
        raise P3EBuildError(f"A3B omission columns missing: {missing}")
    if len(omission) != EXPECTED_MEMBERSHIP_ROWS:
        raise P3EBuildError("A3B omission row count drifted")
    if set(omission["resolution_mode"].astype(str).unique()) - {
        "REPLACEMENT",
        "EMPTY_DOMAIN_CAPACITY_REDUCTION",
        "STRUCTURAL_CAPACITY_REDUCTION",
        "INTERVAL_CAPACITY_REDUCTION",
    }:
        raise P3EBuildError("A3B omission resolution mode drifted")
    return membership, {
        "decision": report.get("decision"),
        "membership_rows": len(membership),
        "audit_rows": report.get("completed_bar_audit_rows"),
        "omission_rows": len(omission),
    }


def _manifest_file_map(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    files = manifest.get("files")
    if not isinstance(files, list):
        raise P3EBuildError("A2 manifest files invalid")
    result: dict[str, dict[str, Any]] = {}
    for raw in files:
        if not isinstance(raw, dict):
            raise P3EBuildError("A2 manifest row invalid")
        name = str(raw.get("path", ""))
        if not name or name in result:
            raise P3EBuildError("A2 manifest path missing or duplicated")
        result[name] = raw
    return result


def verify_a2(
    repo: Path,
    runtime: Path,
    membership: pd.DataFrame,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    report_path = runtime / "rd18-p3x-a2-runtime-report-v1.json"
    manifest_path = runtime / "output-manifest.json"
    report = load_json(report_path)
    manifest = load_json(manifest_path)

    report_checks = {
        "schema_version": (report.get("schema_version") == "rd18-p3x-a2-runtime-report-v1"),
        "stage": report.get("stage") == "RD18_P3X_A2_C2_GENERATOR_BUILD",
        "passed": report.get("passed") is True,
        "sealed_cutoff": (report.get("sealed_cutoff") == "2025-01-01T00:00:00+00:00"),
        "architecture_id": (report.get("architecture_id") == "COMPOSITE_ALPHA_V3"),
        "generator_scope": (report.get("generator_scope") == "PRE_ROUTER_SIGNAL_CANDIDATES"),
        "ready_symbols_processed": (
            report.get("ready_symbols_processed") == EXPECTED_A2_PARTITIONS
        ),
        "expected_ready_symbols": (report.get("expected_ready_symbols") == EXPECTED_A2_PARTITIONS),
        "raw_signal_rows": report.get("raw_signal_rows") == 89117,
        "selected_candidate_rows": (report.get("selected_candidate_rows") == 21543),
        "generation_status_counts": (
            report.get("generation_status_counts")
            == {
                "GENERATED": EXPECTED_GENERATED,
                "NO_FEATURE_ROWS_AFTER_CAUSAL_WARMUP": EXPECTED_NO_FEATURE,
            }
        ),
        "no_feature_symbol_count": (report.get("no_feature_symbol_count") == EXPECTED_NO_FEATURE),
        "a1b_gate_applied": report.get("a1b_gate_applied") is True,
        "a1c_exclusions_applied": (
            report.get("a1c_exclusions_applied") == ["ETN-USDT", "STRAX-USDT"]
        ),
        "next_stage": (
            report.get("next_stage") == "RD18_P3X_A3_SEALED_REPLAY_AUTHORIZATION_REVIEW"
        ),
    }
    failed_report_checks = sorted(name for name, passed in report_checks.items() if not passed)
    if failed_report_checks:
        raise P3EBuildError("A2 runtime report drifted: " + ",".join(failed_report_checks))

    expected_authorizations = {
        "strategy_candidate_generation": True,
        "strategy_replay": False,
        "trade_routing": False,
        "return_calculation": False,
        "threshold_optimization": False,
        "production": False,
        "post_2024_access": False,
    }
    authorizations = report.get("authorizations")
    if authorizations != expected_authorizations:
        raise P3EBuildError(
            "A2 runtime authorizations drifted: "
            f"expected={expected_authorizations}, "
            f"actual={authorizations}"
        )

    manifest_checks = {
        "schema_version": (manifest.get("schema_version") == "rd18-p3x-a2-output-manifest-v1"),
        "network_requests": manifest.get("network_requests") == 0,
        "raw_market_data_written": (manifest.get("raw_market_data_written") is False),
        "synthetic_candles_written": (manifest.get("synthetic_candles_written") is False),
        "normalization_executed": (manifest.get("normalization_executed") is False),
        "candidate_generation": (manifest.get("strategy_candidate_generation_executed") is True),
        "strategy_replay": (manifest.get("strategy_replay_executed") is False),
        "trade_routing": (manifest.get("trade_routing_executed") is False),
        "return_calculation": (manifest.get("return_calculation_executed") is False),
        "threshold_optimization": (manifest.get("threshold_optimization_executed") is False),
        "production": manifest.get("production_authorized") is False,
    }
    failed_manifest_checks = sorted(name for name, passed in manifest_checks.items() if not passed)
    if failed_manifest_checks:
        raise P3EBuildError("A2 output manifest flags drifted: " + ",".join(failed_manifest_checks))

    file_map = _manifest_file_map(manifest)
    summary_rows = read_csv(runtime / "symbol-generation-summary.csv")
    if len(summary_rows) != EXPECTED_A2_PARTITIONS:
        raise P3EBuildError("A2 symbol summary row count drifted")
    statuses = Counter(row["generation_status"] for row in summary_rows)
    expected_statuses = Counter(
        {
            "GENERATED": EXPECTED_GENERATED,
            "NO_FEATURE_ROWS_AFTER_CAUSAL_WARMUP": EXPECTED_NO_FEATURE,
        }
    )
    if statuses != expected_statuses:
        raise P3EBuildError(f"A2 generation status drifted: {statuses}")

    store = ParquetCandleStore(repo / "data/raw/rd16b")
    inventory: list[dict[str, object]] = []
    generated_pairs: set[str] = set()
    for row in sorted(summary_rows, key=lambda value: value["pair"]):
        pair = row["pair"]
        symbol = row["symbol"]
        status = row["generation_status"]
        partition = runtime / "partitions" / pair
        candidates = partition / "candidates.parquet"
        audit = partition / "audit.parquet"
        partition_summary = partition / "summary.json"
        for path in (candidates, audit, partition_summary):
            if not path.is_file():
                raise P3EBuildError(f"A2 partition file missing: {path}")
            relative = path.relative_to(runtime).as_posix()
            manifest_row = file_map.get(relative)
            if manifest_row is None:
                raise P3EBuildError(f"A2 partition is absent from manifest: {relative}")
            bytes_match = path.stat().st_size == int(manifest_row.get("bytes", -1))
            hash_match = sha256(path) == str(manifest_row.get("sha256", ""))
            if not bytes_match or not hash_match:
                raise P3EBuildError(f"A2 partition manifest mismatch: {relative}")

        candidate_file = pq.ParquetFile(candidates)
        audit_file = pq.ParquetFile(audit)
        candidate_meta = candidate_file.metadata
        audit_meta = audit_file.metadata
        candidate_columns = set(candidate_file.schema_arrow.names)
        if not REQUIRED_A2_COLUMNS.issubset(candidate_columns):
            missing = sorted(REQUIRED_A2_COLUMNS - candidate_columns)
            raise P3EBuildError(f"{pair} A2 candidate schema missing: {missing}")

        source_1h = store.dataset_path(
            exchange_id="kucoin",
            symbol=symbol,
            timeframe="1h",
        )
        if not source_1h.is_file():
            raise P3EBuildError(f"sealed 1h source missing: {source_1h}")
        if status == "GENERATED":
            generated_pairs.add(pair)
        inventory.append(
            {
                "pair": pair,
                "symbol": symbol,
                "generation_status": status,
                "candidate_rows": candidate_meta.num_rows,
                "audit_rows": audit_meta.num_rows,
                "source_1h_bytes": source_1h.stat().st_size,
                "source_1h_sha256": sha256(source_1h),
            }
        )

    candidate_rows = sum(int(row["candidate_rows"]) for row in inventory)
    audit_rows = sum(int(row["audit_rows"]) for row in inventory)
    if candidate_rows != report["selected_candidate_rows"]:
        raise P3EBuildError("A2 partition candidate total does not match report")
    if audit_rows != report["raw_signal_rows"]:
        raise P3EBuildError("A2 partition audit total does not match report")

    effective_pairs = set(membership["effective_pair"].astype(str))
    if not effective_pairs.issubset(generated_pairs):
        missing_effective = sorted(effective_pairs - generated_pairs)
        raise P3EBuildError(
            f"effective membership contains non-GENERATED A2 pairs: {missing_effective}"
        )
    return inventory, {
        "runtime_report_sha256": sha256(report_path),
        "output_manifest_sha256": sha256(manifest_path),
        "partitions": len(summary_rows),
        "generated_pairs": len(generated_pairs),
        "no_feature_pairs": statuses["NO_FEATURE_ROWS_AFTER_CAUSAL_WARMUP"],
        "effective_pair_count": len(effective_pairs),
        "candidate_rows": candidate_rows,
        "audit_rows": audit_rows,
        "report_checks": report_checks,
        "manifest_checks": manifest_checks,
    }


def deterministic_manifest(
    output: Path,
    names: list[str],
) -> dict[str, object]:
    rows: list[dict[str, object]] = []
    aggregate = hashlib.sha256()
    for name in sorted(names):
        path = output / name
        digest = sha256(path)
        rows.append(
            {
                "path": name,
                "bytes": path.stat().st_size,
                "sha256": digest,
            }
        )
        aggregate.update(name.encode("utf-8"))
        aggregate.update(b"\0")
        aggregate.update(digest.encode("ascii"))
        aggregate.update(b"\n")
    return {
        "schema_version": "rd18-p3e-build-output-manifest-v1",
        "files": rows,
        "deterministic_hash": aggregate.hexdigest(),
        **OUTPUT_FLAGS,
    }


def build_preflight(
    repo: Path,
    a2_runtime: Path,
    a3_runtime: Path,
    a3b_runtime: Path,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    p3r = verify_p3r(repo)
    a3 = verify_a3(repo, a3_runtime)
    membership, a3b = verify_a3b(a3b_runtime)
    inventory, a2 = verify_a2(
        repo,
        a2_runtime,
        membership,
    )
    report = {
        "schema_version": "rd18-p3e-implementation-build-report-v1",
        "stage": "RD18_P3E_IMPLEMENTATION_BUILD",
        "decision": "RD18_P3E_IMPLEMENTATION_BUILD_COMPLETE",
        "passed": True,
        "p3r": p3r,
        "a3": a3,
        "a3b": a3b,
        "a2": a2,
        "implementation": {
            "core_module": "src/spotbot/research/rd18_p3e_replay.py",
            "base_candidate_path_implemented": True,
            "strong_bull_96_path_implemented": True,
            "frozen_router_reused": True,
            "v3_registration_reused": True,
            "cost_multiplier_transform_implemented": True,
            "base_universe_selection_implemented": True,
            "loyo_execution_implemented": False,
            "loao_execution_implemented": False,
            "performance_gate_classification_implemented": False,
        },
        "next_stage": "RD18_P3E_TECHNICAL_DRY_RUN",
        **OUTPUT_FLAGS,
    }
    return report, inventory


def main() -> int:
    args = parser().parse_args()
    if not args.preflight_only and not args.write_ledgers:
        raise SystemExit("P3E implementation build requires --write-ledgers")

    repo = args.repo_root.resolve()
    output = args.output_dir.resolve()
    report, inventory = build_preflight(
        repo,
        args.a2_runtime.resolve(),
        args.a3_runtime.resolve(),
        args.a3b_runtime.resolve(),
    )
    if args.preflight_only:
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0

    output.mkdir(parents=True, exist_ok=True)
    write_csv(
        output / "input-partition-inventory.csv",
        inventory,
        (
            "pair",
            "symbol",
            "generation_status",
            "candidate_rows",
            "audit_rows",
            "source_1h_bytes",
            "source_1h_sha256",
        ),
    )
    write_json(
        output / "rd18-p3e-implementation-build-report-v1.json",
        report,
    )
    manifest = deterministic_manifest(
        output,
        [
            "input-partition-inventory.csv",
            "rd18-p3e-implementation-build-report-v1.json",
        ],
    )
    write_json(output / "output-manifest.json", manifest)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except P3EBuildError as exc:
        print(f"P3E_BUILD_ERROR={exc}", file=sys.stderr)
        raise SystemExit(2) from exc
