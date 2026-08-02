# ruff: noqa: E501

"""Validate RD18-P2S outputs offline and fail closed on forbidden scope."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "research" / "rd18_p2s"
CLAIM = "RESTRICTED_TO_376_KLINE_CONFIRMED_HISTORICAL_KUCOIN_SPOT_PAIRS"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate RD18-P2S offline structural outputs.")
    parser.parse_args()
    required = [
        "rd18-p2s-protocol-v1.json",
        "input-reconciliation.json",
        "exact-threshold-brittleness.csv",
        "set-disagreement-distribution.csv",
        "weekly-membership-distance.csv",
        "disagreement-duration.csv",
        "substitution-liquidity-audit.csv",
        "current-seed-asset-impact.csv",
        "current-seed-impact-concentration.csv",
        "hysteresis-robustness.csv",
        "consensus-core.csv",
        "robust-consensus-top6.csv",
        "consensus-diagnostics.csv",
        "dual-scenario-feasibility.json",
        "future-dual-universe-replay-requirements.json",
        "request-manifest.json",
        "output-manifest.json",
        "rd18-p2s-final-report-v1.json",
    ]
    missing = [name for name in required if not (OUT / name).exists()]
    if missing:
        raise SystemExit(f"missing required outputs: {missing}")
    reconciliation = json.loads((OUT / "input-reconciliation.json").read_text(encoding="utf-8"))
    if reconciliation.get("passed") is not True:
        raise SystemExit("P2S input reconciliation failed")
    report = json.loads((OUT / "rd18-p2s-final-report-v1.json").read_text(encoding="utf-8"))
    if report.get("restricted_claim") != CLAIM or report.get("full_inventory_claim") is not False:
        raise SystemExit("restricted claim missing or full-inventory claim enabled")
    if report.get("network_requests") != 0 or report.get("no_new_market_data") is not True:
        raise SystemExit("P2S must make zero market-data requests")
    if any(
        report.get(key) is not True
        for key in (
            "no_post_2024_observations",
            "no_futures",
            "no_margin",
            "no_strategy_returns",
            "no_trading",
            "no_candidate_generation",
            "no_optimization",
        )
    ):
        raise SystemExit("forbidden scope flag failed")
    request = json.loads((OUT / "request-manifest.json").read_text(encoding="utf-8"))
    if request.get("network_requests") != 0 or request.get("archive_search") is not False:
        raise SystemExit("network or archive request recorded")
    manifest = json.loads((OUT / "output-manifest.json").read_text(encoding="utf-8"))
    entries = manifest.get("files", [])
    encoded = "\n".join(f"{entry['path']}:{entry['sha256']}" for entry in entries).encode()
    if hashlib.sha256(encoded).hexdigest() != manifest.get("deterministic_hash"):
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
        text = path.read_text(encoding="utf-8")
        if "2025-" in text or "2026-" in text:
            raise SystemExit(f"sealed-period timestamp found in {path.name}")
    feasibility = json.loads((OUT / "dual-scenario-feasibility.json").read_text(encoding="utf-8"))
    if not isinstance(feasibility.get("gates"), dict):
        raise SystemExit("dual-scenario gate record missing")
    future = json.loads(
        (OUT / "future-dual-universe-replay-requirements.json").read_text(encoding="utf-8")
    )
    if (
        future.get("strategy_replay_executed") is not False
        or future.get("production_authorized") is not False
    ):
        raise SystemExit("future replay must remain design-only")
    print(
        json.dumps(
            {
                "passed": True,
                "files": len(entries),
                "network_requests": 0,
                "decision": report.get("decision"),
                "next_stage": report.get("next_stage"),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
