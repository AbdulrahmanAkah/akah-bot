# ruff: noqa: E501

"""Validate RD18-P2U outputs without network access."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "research" / "rd18_p2u"
PRODUCTS = {
    "AGIX2L-USDT",
    "AGIX2S-USDT",
    "APT2L-USDT",
    "APT2S-USDT",
    "BLUR2L-USDT",
    "BLUR2S-USDT",
    "CFX2L-USDT",
    "CFX2S-USDT",
    "GRT2L-USDT",
    "GRT2S-USDT",
    "OP2L-USDT",
    "OP2S-USDT",
}
EXPECTED = {
    "p1r": "3956041409448c3fb547d18917d46f423e07b88b8815961a1a61866fd4ab03b0",
    "p2r": "5ef8deefaa512e07cac33150399a4cb3bdfa685e623d690e3a804bf3a9ef5b1a",
    "p2s": "38e19370f3e98539b7d55502c6d5b97acf80829d3332df3c7c56a6232f3eccfd",
    "p2t": "afcbabc0a5dbd77791adde75fe895d2d55386e51df568d391d9df77d007aa0bf",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SystemExit(f"expected JSON object: {path.name}")
    return value


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate offline RD18-P2U outputs.")
    parser.parse_args()
    required = [
        "rd18-p2u-protocol-v1.json",
        "input-reconciliation.json",
        "confidence-classification.csv",
        "excluded-product-audit.csv",
        "weekly-variant-e-ranking.csv",
        "weekly-variant-e-topn.csv",
        "variant-e-hysteresis.csv",
        "confidence-intervention-audit.csv",
        "variant-e-c-d-comparison.csv",
        "liquidity-sacrifice-audit.csv",
        "provenance-effect-by-year.csv",
        "p2t-liquidity-flag-membership-audit.csv",
        "threshold-sensitivity.csv",
        "operational-hysteresis-audit.csv",
        "future-three-universe-replay-requirements.json",
        "request-manifest.json",
        "output-manifest.json",
        "rd18-p2u-final-report-v1.json",
        "validation-report.json",
    ]
    missing = [name for name in required if not (OUT / name).exists()]
    if missing:
        raise SystemExit(f"missing required files: {missing}")
    reconciliation = read_json(OUT / "input-reconciliation.json")
    if reconciliation.get("baseline_reconciled") is not True:
        raise SystemExit("P2U frozen input baseline did not reconcile")
    counts = reconciliation.get("counts", {})
    expected_counts = {
        "variant_c_pairs": 376,
        "variant_d_pairs": 299,
        "current_seed_only_pairs": 77,
        "c_minus_d_pairs": 77,
        "weekly_decisions": 313,
        "post_warmup_decisions": 301,
        "p2t_temporally_distinct": 65,
        "p2t_excluded_products": 12,
        "p2t_unresolved": 0,
    }
    if counts != expected_counts:
        raise SystemExit(f"unexpected reconciliation counts: {counts}")
    if reconciliation.get("hashes") != EXPECTED:
        raise SystemExit("frozen input deterministic hashes do not reconcile")
    excluded = read_rows(OUT / "excluded-product-audit.csv")
    if {row.get("pair") for row in excluded} != PRODUCTS or not all(
        row.get("contamination", "").lower() == "true" for row in excluded
    ):
        raise SystemExit("excluded-product audit does not record all contaminated products")
    if any(row.get("appears_in_c_rankings", "").lower() != "true" for row in excluded):
        raise SystemExit("product contamination was not detected in C rankings")
    classifications = read_rows(OUT / "confidence-classification.csv")
    if len(classifications) != 376:
        raise SystemExit("confidence classification must cover all C pairs")
    if {
        row.get("pair")
        for row in classifications
        if row.get("confidence_class") == "EXCLUDED_LEVERAGED_OR_SYNTHETIC"
    } != PRODUCTS:
        raise SystemExit("excluded confidence class mismatch")
    report = read_json(OUT / "rd18-p2u-final-report-v1.json")
    if report.get("decision") != "RD18_P2U_EXCLUDED_PRODUCT_CONTAMINATION":
        raise SystemExit("unexpected P2U decision")
    if report.get("next_stage") != "RD18_BLOCKED_PENDING_RESTRICTED_PANEL_REPAIR":
        raise SystemExit("unexpected P2U next stage")
    if (
        report.get("variant_e_generated") is not False
        or report.get("variant_e_authorized") is not False
    ):
        raise SystemExit("Variant E must not be generated or authorized")
    if report.get("network_requests") != 0 or report.get("product_contamination") is not True:
        raise SystemExit("P2U scope flags failed")
    for key in (
        "no_network",
        "no_post_2024_observations",
        "no_futures",
        "no_margin",
        "no_returns",
        "no_signals",
        "no_trading",
        "no_optimization",
    ):
        if report.get(key) is not True:
            raise SystemExit(f"forbidden scope flag failed: {key}")
    for name in (
        "weekly-variant-e-ranking.csv",
        "weekly-variant-e-topn.csv",
        "variant-e-hysteresis.csv",
        "confidence-intervention-audit.csv",
        "variant-e-c-d-comparison.csv",
    ):
        if read_rows(OUT / name):
            raise SystemExit(f"Variant E output was generated despite contamination: {name}")
    forbidden = ("pnl", "return", "trade", "signal", "candidate", "optimization")
    for path in OUT.glob("*.csv"):
        with path.open("r", encoding="utf-8", newline="") as handle:
            header = next(csv.reader(handle), [])
        if any(any(token in column.lower() for token in forbidden) for column in header):
            raise SystemExit(f"forbidden research column in {path.name}")
        text = path.read_text(encoding="utf-8")
        if "2025-" in text or "2026-" in text:
            raise SystemExit(f"sealed period found in {path.name}")
    request = read_json(OUT / "request-manifest.json")
    if request.get("network_requests") != 0:
        raise SystemExit("network request recorded")
    manifest = read_json(OUT / "output-manifest.json")
    entries = manifest.get("files", [])
    encoded = "\n".join(f"{entry['path']}:{entry['sha256']}" for entry in entries).encode()
    if hashlib.sha256(encoded).hexdigest() != manifest.get("deterministic_hash"):
        raise SystemExit("output manifest deterministic hash mismatch")
    for entry in entries:
        path = ROOT / str(entry["path"])
        if not path.exists() or sha256(path) != entry["sha256"]:
            raise SystemExit(f"output hash mismatch: {path}")
    future = read_json(OUT / "future-three-universe-replay-requirements.json")
    if (
        future.get("strategy_replay_executed") is not False
        or future.get("production_authorized") is not False
    ):
        raise SystemExit("future replay is not design-only")
    print(
        json.dumps(
            {"passed": True, "decision": report["decision"], "network_requests": 0}, sort_keys=True
        )
    )


if __name__ == "__main__":
    main()
