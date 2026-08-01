"""Validate RD18-P0 outputs offline without making network requests."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any, cast

from spotbot.research.kucoin_rd18 import (
    SPOT_CANDLES_PATH,
    KuCoinRD18Error,
    parse_announcements,
    parse_kline_payload,
)

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "data" / "research" / "rd18_p0"
SEALED_CUTOFF = "2025-01-01T00:00:00+00:00"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def load(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def main() -> int:
    report = load(OUTPUT / "rd18-p0-final-report-v1.json")
    protocol = load(OUTPUT / "rd18-p0-protocol-v1.json")
    request_manifest = load(OUTPUT / "request-manifest.json")
    output_manifest = load(OUTPUT / "output-manifest.json")
    failures: list[str] = []
    if report["decision"] != "RD18_P0_KUCOIN_HISTORICAL_SYMBOL_INVENTORY_INSUFFICIENT":
        failures.append("unexpected P0 decision")
    if protocol["execution_venue"] != "KUCOIN_SPOT":
        failures.append("venue protocol mismatch")
    if report["test_2025_accessed"] or report["holdout_2026_accessed"]:
        failures.append("sealed-period flag is not false")
    if report["futures_data_used"] or report["trading_run_authorized"]:
        failures.append("forbidden work flag is not false")

    kline_requests = [row for row in request_manifest["requests"] if row.get("kind") == "kline"]
    replay_count = 0
    for request in kline_requests:
        raw_path = ROOT / request["raw_path"]
        if not raw_path.exists():
            failures.append(f"missing raw response: {raw_path}")
            continue
        payload = load(raw_path)
        symbol = request["symbol"]
        endpoint = request.get("endpoint", SPOT_CANDLES_PATH)
        start = request.get("start")
        end = request.get("end_exclusive")
        if start is None or end is None:
            failures.append(f"missing kline bounds: {request['request_id']}")
            continue
        from datetime import datetime

        start_dt = datetime.fromisoformat(start)
        end_dt = datetime.fromisoformat(end)
        try:
            first = parse_kline_payload(
                payload,
                symbol=symbol,
                endpoint=endpoint,
                start=start_dt,
                end=end_dt,
            )
            second = parse_kline_payload(
                payload,
                symbol=symbol,
                endpoint=endpoint,
                start=start_dt,
                end=end_dt,
            )
        except KuCoinRD18Error as error:
            failures.append(f"offline Kline parse failed: {request['request_id']}: {error}")
            continue
        if first != second:
            failures.append(f"offline replay mismatch: {request['request_id']}")
        replay_count += 1

    for request in request_manifest["requests"]:
        if request.get("kind") != "announcement" or request.get("status") != "SUCCESS":
            continue
        raw_path = ROOT / request["raw_path"]
        if not raw_path.exists():
            failures.append(f"missing announcement raw response: {raw_path}")
            continue
        payload = load(raw_path)
        try:
            parse_announcements(
                payload,
                category=request["category"],
                request_id=request["request_id"],
            )
        except KuCoinRD18Error as error:
            failures.append(f"offline announcement parse failed: {request['request_id']}: {error}")

    manifest_checks = 0
    for item in output_manifest["files"]:
        path = ROOT / item["path"]
        if not path.exists():
            failures.append(f"missing manifest file: {path}")
            continue
        # The validator report is written below.  Exclude it from the first
        # pass to avoid a self-referential hash, then refresh its manifest
        # entry after the report has been written.
        if path.name == "validation-report.json":
            continue
        if sha256(path) != item["sha256"]:
            failures.append(f"manifest hash mismatch: {path}")
        manifest_checks += 1

    csv_checks = 0
    for name in (
        "announcement-coverage-by-year.csv",
        "listing-announcements.csv",
        "delisting-announcements.csv",
        "candidate-discovery-provenance.csv",
        "historical-pair-inventory.csv",
        "identity-audit.csv",
        "kline-probe-plan.csv",
        "kline-probe-results.csv",
        "timing-audit.csv",
        "probe-weekly-rankings.csv",
    ):
        path = OUTPUT / name
        if not path.exists() or path.stat().st_size == 0:
            failures.append(f"missing or empty CSV: {path}")
            continue
        with path.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.reader(handle))
        if not rows or not rows[0]:
            failures.append(f"invalid CSV header: {path}")
        csv_checks += 1

    scanned = [path for path in OUTPUT.rglob("*") if path.is_file() and "raw" not in path.parts]
    if any("DUNE_API_KEY" in path.read_text(encoding="utf-8", errors="ignore") for path in scanned):
        failures.append("secret marker found in RD18-P0 outputs")

    validation = {
        "schema_version": "rd18-p0-offline-validation-v1",
        "decision": report["decision"],
        "sealed_cutoff": SEALED_CUTOFF,
        "offline_kline_replays": replay_count,
        "manifest_hash_checks": manifest_checks,
        "csv_checks": csv_checks,
        "network_requests": 0,
        "passed": not failures,
        "failures": failures,
    }
    path = OUTPUT / "validation-report.json"
    path.write_text(json.dumps(validation, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    for item in output_manifest["files"]:
        if Path(str(item["path"])).name == "validation-report.json":
            item["sha256"] = sha256(path)
            item["bytes"] = path.stat().st_size
    (OUTPUT / "output-manifest.json").write_text(
        json.dumps(output_manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(validation, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
