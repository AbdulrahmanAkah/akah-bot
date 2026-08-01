"""Validate deterministic RD18-P0B outputs without network access."""

from __future__ import annotations

import csv
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "data" / "research" / "rd18_p0b"
P0A = ROOT / "data" / "research" / "rd18_p0a"
FORBIDDEN = re.compile(r"(?:2025|2026)")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def validate() -> dict[str, object]:
    failures: list[str] = []
    report = load_json(OUTPUT / "rd18-p0b-final-report-v1.json")
    if not isinstance(report, dict):
        raise ValueError("P0B final report is not an object")
    if report.get("decision") != "RD18_P0B_EXTERNAL_ARCHIVE_INSUFFICIENT":
        failures.append("unexpected decision")
    if report.get("next_stage") != "RD18_BLOCKED_PENDING_FREE_PRE2019_KUCOIN_INVENTORY":
        failures.append("unexpected next stage")
    if report.get("p1_ran") is not False:
        failures.append("P1 must not run")
    if (
        report.get("test_2025_accessed") is not False
        or report.get("holdout_2026_accessed") is not False
    ):
        failures.append("forbidden-year flag")
    if (
        report.get("futures_data_used") is not False
        or report.get("trading_run_authorized") is not False
    ):
        failures.append("forbidden activity flag")
    protocol = load_json(OUTPUT / "rd18-p0b-protocol-v1.json")
    if not isinstance(protocol, dict) or protocol.get("starting_commit") != (
        "12028034259216329ae7b2103bea89f006f4b621"
    ):
        failures.append("protocol starting commit")
    union = load_csv(OUTPUT / "original-candidate-resolution.csv")
    if len(union) != 2269:
        failures.append("candidate union count")
    if any(not row.get("p0b_terminal_resolution") for row in union):
        failures.append("non-terminal candidate")
    if any(row.get("p0b_probe_completed") != "True" for row in union):
        failures.append("incomplete candidate probe")
    boundaries = load_csv(OUTPUT / "full-daily-kline-boundaries.csv")
    if len(boundaries) != int(report.get("confirmed_historical_pair_count", 0)):
        failures.append("boundary count")
    if any(row.get("boundary_status") != "EXACT_FULL_HISTORY" for row in boundaries):
        failures.append("incomplete boundary")
    if any(
        FORBIDDEN.search(str(row.get("first_valid_open", "")))
        or FORBIDDEN.search(str(row.get("last_valid_open", "")))
        for row in boundaries
    ):
        failures.append("forbidden year in boundaries")
    delistings = load_csv(OUTPUT / "delisting-resolution-v2.csv")
    if len(delistings) != 16:
        failures.append("delisting audit row count")
    if sum(row.get("p0b_pre_delisting_kline_found") != "True" for row in delistings) != 10:
        failures.append("ten unresolved delisting outcomes")
    archive = load_csv(OUTPUT / "archive-cdx-captures.csv")
    if archive:
        failures.append("unexpected usable archive captures for blocked archive probe")
    manifest = load_json(OUTPUT / "output-manifest.json")
    if not isinstance(manifest, dict) or not manifest.get("deterministic_offline_parser"):
        failures.append("output manifest")
    request_manifest = load_json(OUTPUT / "request-manifest.json")
    if not isinstance(request_manifest, dict):
        failures.append("request manifest object")
    else:
        if request_manifest.get("no_post_2024_market_observation_requests") is not True:
            failures.append("request sealed boundary")
        for request in request_manifest.get("requests", []):
            if FORBIDDEN.search(str(request.get("url", ""))):
                failures.append("forbidden-year request URL")
                break
    for path in OUTPUT.glob("*.json"):
        if path.name in {"output-manifest.json", "validation-report.json"}:
            continue
        try:
            load_json(path)
        except json.JSONDecodeError:
            failures.append(f"invalid JSON: {path.name}")
    for path in OUTPUT.glob("*.csv"):
        rows = load_csv(path)
        # Archive evidence tables may legitimately contain only their header
        # when the public CDX probe is inaccessible; their schema is still
        # validated by the committed header.
        if not rows and path.name not in {
            "archive-cdx-captures.csv",
            "archive-kline-reconciliation.csv",
            "archive-symbol-candidates.csv",
        }:
            failures.append(f"empty CSV: {path.name}")
    return {
        "schema_version": "rd18-p0b-validation-v1",
        "decision": report.get("decision"),
        "candidate_count": len(union),
        "boundary_count": len(boundaries),
        "delisting_rows": len(delistings),
        "request_count": (
            len(request_manifest.get("requests", [])) if isinstance(request_manifest, dict) else 0
        ),
        "output_manifest_entries": (
            len(manifest.get("files", [])) if isinstance(manifest, dict) else 0
        ),
        "failures": failures,
        "passed": not failures,
    }


def main() -> int:
    try:
        result = validate()
    except Exception as error:  # noqa: BLE001
        print(json.dumps({"passed": False, "error": str(error)}, sort_keys=True))
        return 1
    (OUTPUT / "validation-report.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
