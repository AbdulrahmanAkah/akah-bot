"""Validate RD18-P0C outputs offline without making network requests."""

from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "data" / "research" / "rd18_p0c"
SEALED = datetime(2025, 1, 1)


REQUIRED = (
    "rd18-p0c-protocol-v1.json",
    "baseline-reconciliation.json",
    "common-crawl-collections.csv",
    "common-crawl-index-queries.csv",
    "common-crawl-captures.csv",
    "common-crawl-content-audit.csv",
    "archived-announcement-index.csv",
    "archived-launch-era-events.csv",
    "archive-symbol-candidates.csv",
    "archive-kline-reconciliation.csv",
    "current-registry-retention-audit.csv",
    "launch-era-inventory-audit.csv",
    "final-historical-pair-inventory.csv",
    "full-daily-kline-boundaries.csv",
    "identity-audit.csv",
    "request-manifest.json",
    "output-manifest.json",
    "rd18-p0c-final-report-v1.json",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def validate() -> dict[str, object]:
    failures: list[str] = []
    for name in REQUIRED:
        if not (OUTPUT / name).exists():
            failures.append(f"missing:{name}")
    if failures:
        return {"pass": False, "failures": failures}
    protocol = json.loads((OUTPUT / "rd18-p0c-protocol-v1.json").read_text(encoding="utf-8"))
    report = json.loads((OUTPUT / "rd18-p0c-final-report-v1.json").read_text(encoding="utf-8"))
    baseline = json.loads((OUTPUT / "baseline-reconciliation.json").read_text(encoding="utf-8"))
    request_manifest = json.loads((OUTPUT / "request-manifest.json").read_text(encoding="utf-8"))
    output_manifest = json.loads((OUTPUT / "output-manifest.json").read_text(encoding="utf-8"))
    if report.get("decision") != "RD18_P0C_COMMON_CRAWL_COVERAGE_INSUFFICIENT":
        failures.append("decision-not-blocked-by-coverage")
    if report.get("next_stage") != "RD18_BLOCKED_PENDING_FREE_PRE2019_KUCOIN_INVENTORY":
        failures.append("next-stage-changed")
    if report.get("p1_ran") is not False:
        failures.append("p1-ran")
    if (
        report.get("test_2025_accessed") is not False
        or report.get("holdout_2026_accessed") is not False
    ):
        failures.append("sealed-data-flag")
    if report.get("futures_or_margin_used") is not False:
        failures.append("futures-or-margin-used")
    if (
        report.get("trading_run_authorized") is not False
        or report.get("optimization_performed") is not False
    ):
        failures.append("trading-or-optimization")
    if (
        baseline.get("candidate_union_count") != 2269
        or baseline.get("confirmed_historical_pair_count") != 376
    ):
        failures.append("baseline-counts")
    captures = load_csv(OUTPUT / "common-crawl-captures.csv")
    for row in captures:
        stamp = str(row.get("capture_timestamp", ""))[:19].replace("T", " ")
        try:
            if datetime.fromisoformat(stamp) >= SEALED:
                failures.append("post-2024-capture")
        except ValueError:
            failures.append("malformed-capture-time")
    for item in request_manifest.get("requests", []):
        url = str(item.get("url", ""))
        if "2025" in url or "2026" in url:
            failures.append("sealed-request-url")
        if any(token in url.lower() for token in ("futures", "margin")):
            failures.append("non-spot-url")
    files = output_manifest.get("files", [])
    for item in files:
        path = ROOT / str(item.get("path", ""))
        if not path.exists() or sha256(path) != item.get("sha256"):
            failures.append(f"output-hash:{path}")
    deterministic = output_manifest.get("deterministic_hash")
    expected = hashlib.sha256(json.dumps(files, sort_keys=True).encode("utf-8")).hexdigest()
    if deterministic != expected:
        failures.append("manifest-deterministic-hash")
    return {
        "pass": not failures,
        "failures": failures,
        "decision": report.get("decision"),
        "candidate_union_count": baseline.get("candidate_union_count"),
        "confirmed_historical_pair_count": baseline.get("confirmed_historical_pair_count"),
        "capture_count": report.get("capture_count"),
        "usable_official_capture_count": report.get("usable_official_capture_count"),
        "no_post_2024_market_observations": report.get("test_2025_accessed") is False
        and report.get("holdout_2026_accessed") is False,
        "p1_ran": report.get("p1_ran"),
        "protocol_starting_commit": protocol.get("starting_commit"),
    }


def main() -> int:
    result = validate()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("pass") else 1


if __name__ == "__main__":
    raise SystemExit(main())
