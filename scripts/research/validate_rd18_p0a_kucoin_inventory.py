"""Validate RD18-P0A outputs without network access."""

from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "data" / "research" / "rd18_p0a"
SEALED_CUTOFF = datetime.fromisoformat("2025-01-01T00:00:00+00:00")
ALLOWED_DECISIONS = {
    "RD18_P0A_KUCOIN_CAUSAL_SYMBOL_INVENTORY_CONFIRMED",
    "RD18_P0A_KUCOIN_INVENTORY_PARTIAL",
    "RD18_P0A_KUCOIN_DELISTED_PAIR_RETENTION_FAILED",
    "RD18_P0A_KUCOIN_INVENTORY_SURVIVORSHIP_RISK",
    "RD18_P0A_NO_SUFFICIENT_OFFICIAL_KUCOIN_INVENTORY",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def load(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def main() -> int:
    failures: list[str] = []
    report = load(OUTPUT / "rd18-p0a-final-report-v1.json")
    protocol = load(OUTPUT / "rd18-p0a-protocol-v1.json")
    manifest = load(OUTPUT / "output-manifest.json")
    request_manifest = load(OUTPUT / "request-manifest.json")
    if report.get("decision") not in ALLOWED_DECISIONS:
        failures.append("unexpected P0A decision")
    if protocol.get("execution_venue") != "KUCOIN_SPOT":
        failures.append("venue mismatch")
    if report.get("p1_ran"):
        failures.append("P1 ran despite conditional stop")
    if report.get("test_2025_accessed") or report.get("holdout_2026_accessed"):
        failures.append("sealed-period flag is true")
    if report.get("futures_data_used") or report.get("trading_run_authorized"):
        failures.append("forbidden work flag is true")
    if report.get("optimization_performed"):
        failures.append("optimization flag is true")
    if int(report.get("p0a_delisting_audit_row_count", -1)) != 16:
        failures.append("frozen unresolved delisting audit is not 16 rows")

    request_count = 0
    for request in request_manifest.get("requests", []):
        request_count += 1
        for field in ("start", "end_exclusive"):
            value = request.get(field)
            if value:
                try:
                    timestamp = datetime.fromisoformat(str(value))
                except ValueError:
                    failures.append(f"invalid request timestamp: {field}")
                    continue
                if timestamp >= SEALED_CUTOFF:
                    failures.append(f"sealed request bound: {request.get('request_id')}")
        raw_path = request.get("raw_path")
        if raw_path:
            path = ROOT / str(raw_path)
            if not path.exists():
                failures.append(f"missing raw response: {path}")
            elif (
                request.get("raw_payload_sha256") and sha256(path) != request["raw_payload_sha256"]
            ):
                failures.append(f"raw hash mismatch: {path}")

    union_path = OUTPUT / "candidate-union.csv"
    union_rows = list(csv.DictReader(union_path.open(encoding="utf-8", newline="")))
    if not union_rows:
        failures.append("candidate union is empty")
    for row in union_rows:
        if (
            row.get("current_metadata_only") == "True"
            and row.get("membership_classification", "").startswith("CONFIRMED")
            and int(float(row.get("valid_kline_observation_count", "0") or 0)) <= 0
        ):
            failures.append(
                f"current-only seed used without Kline proof: {row.get('candidate_pair')}"
            )

    retention = list(
        csv.DictReader(
            (OUTPUT / "delisted-pair-retention-audit.csv").open(encoding="utf-8", newline="")
        )
    )
    if len(retention) != 16:
        failures.append("delisted-pair audit row count mismatch")
    csv_names = [
        "historical-download-catalogue.csv",
        "historical-download-symbols.csv",
        "historical-download-date-coverage.csv",
        "historical-download-delisted-pair-audit.csv",
        "current-currency-seed.csv",
        "current-currency-identity-audit.csv",
        "announcement-base-symbol-candidates.csv",
        "announcement-explicit-pairs-v2.csv",
        "announcement-parser-coverage-v2.csv",
        "rename-migration-events.csv",
        "candidate-union.csv",
        "kline-existence-probes.csv",
        "historical-pair-boundaries.csv",
        "delisted-pair-retention-audit.csv",
        "inventory-completeness-audit.csv",
        "identity-audit.csv",
    ]
    csv_count = 0
    for name in csv_names:
        path = OUTPUT / name
        if not path.exists() or path.stat().st_size == 0:
            failures.append(f"missing or empty CSV: {name}")
            continue
        with path.open(encoding="utf-8", newline="") as handle:
            if not next(csv.reader(handle), None):
                failures.append(f"invalid CSV header: {name}")
        csv_count += 1

    manifest_checks = 0
    for item in manifest.get("files", []):
        path = ROOT / str(item["path"])
        if not path.exists():
            failures.append(f"missing manifest file: {path}")
            continue
        if sha256(path) != item.get("sha256"):
            failures.append(f"output manifest hash mismatch: {path}")
        manifest_checks += 1

    scanned = [path for path in OUTPUT.rglob("*") if path.is_file() and "raw" not in path.parts]
    if any("DUNE_API_KEY" in path.read_text(encoding="utf-8", errors="ignore") for path in scanned):
        failures.append("secret marker found")

    validation = {
        "schema_version": "rd18-p0a-offline-validation-v1",
        "decision": report.get("decision"),
        "network_requests": 0,
        "request_manifest_count": request_count,
        "raw_hash_checks": request_count,
        "csv_checks": csv_count,
        "manifest_hash_checks": manifest_checks,
        "p1_ran": False,
        "passed": not failures,
        "failures": failures,
    }
    (OUTPUT / "validation-report.json").write_text(
        json.dumps(validation, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(validation, ensure_ascii=False, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
