# ruff: noqa: E501

"""Validate committed RD18-P2R structural outputs without network access."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "research" / "rd18_p2r"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate RD18-P2R offline structural outputs.")
    parser.parse_args()
    required = [
        "rd18-p2r-protocol-v1.json",
        "input-reconciliation.json",
        "pair-discovery-provenance.csv",
        "weekly-universe-growth.csv",
        "annual-universe-summary.csv",
        "membership-persistence.csv",
        "weekly-turnover.csv",
        "liquidity-concentration.csv",
        "cutoff-stability.csv",
        "inventory-variant-weekly-comparison.csv",
        "inventory-variant-annual-summary.csv",
        "current-seed-influence.csv",
        "current-seed-influence-by-year.csv",
        "delisted-pair-structural-impact.csv",
        "cmc-snapshot-liquidity-comparison.csv",
        "legacy-universe-diagnostic.csv",
        "omission-risk-assessment.json",
        "future-universe-requirements.json",
        "request-manifest.json",
        "output-manifest.json",
        "rd18-p2r-final-report-v1.json",
    ]
    missing = [name for name in required if not (OUT / name).exists()]
    if missing:
        raise SystemExit(f"missing required outputs: {missing}")
    reconciliation = json.loads((OUT / "input-reconciliation.json").read_text(encoding="utf-8"))
    if not reconciliation.get("passed"):
        raise SystemExit("input reconciliation failed")
    report = json.loads((OUT / "rd18-p2r-final-report-v1.json").read_text(encoding="utf-8"))
    if (
        report.get("restricted_claim")
        != "RESTRICTED_TO_376_KLINE_CONFIRMED_HISTORICAL_KUCOIN_SPOT_PAIRS"
    ):
        raise SystemExit("restricted claim missing")
    if report.get("full_historical_inventory_claim") is not False:
        raise SystemExit("full-inventory claim must remain false")
    request_manifest = json.loads((OUT / "request-manifest.json").read_text(encoding="utf-8"))
    if request_manifest.get("network_requests") != 0:
        raise SystemExit("P2R must make zero network requests")
    output_manifest = json.loads((OUT / "output-manifest.json").read_text(encoding="utf-8"))
    entries = output_manifest.get("files", [])
    encoded = "\n".join(f"{entry['path']}:{entry['sha256']}" for entry in entries).encode()
    if hashlib.sha256(encoded).hexdigest() != output_manifest.get("deterministic_hash"):
        raise SystemExit("output manifest deterministic hash mismatch")
    for entry in entries:
        path = ROOT / str(entry["path"])
        if not path.exists() or sha256(path) != entry["sha256"]:
            raise SystemExit(f"output hash mismatch: {path}")
    forbidden_columns = {"pnl", "return", "trade", "signal", "candidate"}
    for path in OUT.glob("*.csv"):
        with path.open("r", encoding="utf-8", newline="") as handle:
            header = next(csv.reader(handle), [])
        lowered = {column.lower() for column in header}
        if any(any(token in column for token in forbidden_columns) for column in lowered):
            raise SystemExit(f"forbidden strategy/trading column in {path.name}")
    for path in OUT.glob("*.csv"):
        text = path.read_text(encoding="utf-8")
        if "2025-" in text or "2026-" in text:
            raise SystemExit(f"sealed-period timestamp found in {path.name}")
    print(
        json.dumps(
            {
                "passed": True,
                "files": len(entries),
                "network_requests": 0,
                "decision": report.get("decision"),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
