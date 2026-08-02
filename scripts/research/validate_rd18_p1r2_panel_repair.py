# ruff: noqa: E501

"""Validate RD18-P1R2 corrected-panel outputs offline."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "research" / "rd18_p1r2"
CLAIM = "RESTRICTED_TO_376_KLINE_CONFIRMED_HISTORICAL_KUCOIN_SPOT_PAIRS"
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
EXPECTED_HASHES = {
    "p1r": "3956041409448c3fb547d18917d46f423e07b88b8815961a1a61866fd4ab03b0",
    "p2r": "5ef8deefaa512e07cac33150399a4cb3bdfa685e623d690e3a804bf3a9ef5b1a",
    "p2s": "38e19370f3e98539b7d55502c6d5b97acf80829d3332df3c7c56a6232f3eccfd",
    "p2t": "afcbabc0a5dbd77791adde75fe895d2d55386e51df568d391d9df77d007aa0bf",
    "p2u": "583be92b9880364a53ecabcf53e5980350c2ef06b11da2c3612f78269feae551",
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
        raise SystemExit(f"Expected JSON object: {path.name}")
    return value


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate offline RD18-P1R2 corrected-panel outputs."
    )
    parser.parse_args()
    required = [
        "rd18-p1r2-protocol-v1.json",
        "input-reconciliation.json",
        "raw-inventory-classification.csv",
        "excluded-product-audit.csv",
        "contaminated-ranking-provenance.csv",
        "weekly-displacement-audit.csv",
        "corrected-daily-liquidity-panel.parquet",
        "corrected-daily-coverage-audit.csv",
        "corrected-weekly-eligibility.csv",
        "corrected-weekly-rankings.csv",
        "corrected-weekly-topn.csv",
        "corrected-hysteresis.csv",
        "old-vs-corrected-membership.csv",
        "corrected-inventory-sensitivity.csv",
        "corrected-universe-turnover.csv",
        "corrected-liquidity-concentration.csv",
        "corrected-cutoff-stability.csv",
        "delisted-pair-retention-audit.csv",
        "dependency-impact-assessment.json",
        "request-manifest.json",
        "output-manifest.json",
        "rd18-p1r2-final-report-v1.json",
        "validation-report.json",
    ]
    missing = [name for name in required if not (OUT / name).exists()]
    if missing:
        raise SystemExit(f"Missing required outputs: {missing}")
    reconciliation = read_json(OUT / "input-reconciliation.json")
    if reconciliation.get("passed") is not True:
        raise SystemExit("P1R2 input reconciliation failed")
    expected_counts = {
        "raw_inventory_pairs": 376,
        "variant_d_pairs": 299,
        "c_minus_d_pairs": 77,
        "p2t_temporally_distinct": 65,
        "p2t_products": 12,
        "p2t_unresolved": 0,
        "p2u_contaminated_ranking_rows": 321,
        "weekly_decisions": 313,
        "post_warmup_decisions": 301,
        "product_policy_matches": 12,
    }
    if reconciliation.get("counts") != expected_counts:
        raise SystemExit(f"Unexpected input counts: {reconciliation.get('counts')}")
    if reconciliation.get("hashes") != EXPECTED_HASHES:
        raise SystemExit("Frozen input hashes do not reconcile")
    report = read_json(OUT / "rd18-p1r2-final-report-v1.json")
    if report.get("decision") != "RD18_P1R2_RESTRICTED_PANEL_REPAIRED":
        raise SystemExit(f"Unexpected P1R2 decision: {report.get('decision')}")
    if report.get("next_stage") != "RD18_P2R2_CORRECTED_RESTRICTED_UNIVERSE_STRUCTURAL_COMPARISON":
        raise SystemExit("Unexpected P1R2 next stage")
    if report.get("restricted_claim") != CLAIM:
        raise SystemExit("Restricted claim missing")
    gates = report.get("acceptance_gates", {})
    if not isinstance(gates, dict) or not all(value is True for value in gates.values()):
        raise SystemExit("P1R2 acceptance gate failure")
    raw = read_rows(OUT / "raw-inventory-classification.csv")
    if len(raw) != 376 or {row.get("pair") for row in raw}.__len__() != 376:
        raise SystemExit("Raw inventory is not exactly 376 unique pairs")
    excluded = read_rows(OUT / "excluded-product-audit.csv")
    if {row.get("pair") for row in excluded} != PRODUCTS:
        raise SystemExit("Excluded product audit does not cover exactly 12 products")
    if any(row.get("product_eligible", "").lower() == "true" for row in excluded):
        raise SystemExit("Excluded product marked eligible")
    classification = {row["pair"]: row for row in raw}
    if {
        pair for pair, row in classification.items() if row.get("is_product", "").lower() == "true"
    } != PRODUCTS:
        raise SystemExit("Raw product classifier mismatch")
    panel = pd.read_parquet(OUT / "corrected-daily-liquidity-panel.parquet")
    if len(set(panel["pair"].astype(str))) != 376:
        raise SystemExit("Corrected panel does not retain raw 376-pair provenance")
    if "product_eligible" not in panel.columns or "exclusion_reason" not in panel.columns:
        raise SystemExit("Corrected panel exclusion columns missing")
    product_panel = panel[panel["pair"].isin(PRODUCTS)]
    if product_panel.empty or bool(product_panel["product_eligible"].any()):
        raise SystemExit("Product eligibility flags are incorrect")
    if set(product_panel["exclusion_reason"].astype(str)) != {"LEVERAGED_OR_SYNTHETIC_PRODUCT"}:
        raise SystemExit("Product exclusion reason mismatch")
    if panel["open_time"].max() >= pd.Timestamp("2025-01-01T00:00:00Z"):
        raise SystemExit("Post-2024 observation in corrected panel")
    corrected_files = [
        "corrected-weekly-eligibility.csv",
        "corrected-weekly-rankings.csv",
        "corrected-weekly-topn.csv",
        "corrected-hysteresis.csv",
    ]
    for name in corrected_files:
        rows = read_rows(OUT / name)
        if any(
            row.get("pair") in PRODUCTS
            or row.get("canonical_asset_id") in {pair.removesuffix("-USDT") for pair in PRODUCTS}
            for row in rows
        ):
            raise SystemExit(f"Excluded product entered corrected output: {name}")
        text = (OUT / name).read_text(encoding="utf-8")
        if "2025-" in text or "2026-" in text:
            raise SystemExit(f"Sealed period found in {name}")
    contaminated = read_rows(OUT / "contaminated-ranking-provenance.csv")
    if (
        len(contaminated) != 321
        or set(row.get("excluded_product") for row in contaminated) != PRODUCTS
    ):
        raise SystemExit("Contaminated ranking-row count was not reproduced")
    coverage = read_rows(OUT / "corrected-daily-coverage-audit.csv")
    if len(coverage) != 364 or any(float(row["coverage_ratio"]) < 0 for row in coverage):
        raise SystemExit("Corrected daily coverage audit invalid")
    sensitivity = read_rows(OUT / "corrected-inventory-sensitivity.csv")
    if not sensitivity or not {row.get("comparison") for row in sensitivity} == {
        "A_P0_vs_C2",
        "B_P0A_vs_C2",
        "D2_vs_C2",
    }:
        raise SystemExit("Corrected inventory sensitivity incomplete")
    delisted = read_rows(OUT / "delisted-pair-retention-audit.csv")
    if len(delisted) != 6 or not all(
        row.get("retained_in_corrected_panel", "").lower() == "true" for row in delisted
    ):
        raise SystemExit("Delisted-pair retention failed")
    request = read_json(OUT / "request-manifest.json")
    if request.get("network_requests") != 0:
        raise SystemExit("P1R2 made or recorded a network request")
    forbidden = ("pnl", "return", "trade", "signal", "candidate", "optimization")
    for path in OUT.glob("*.csv"):
        with path.open("r", encoding="utf-8", newline="") as handle:
            header = next(csv.reader(handle), [])
        if any(any(token in column.lower() for token in forbidden) for column in header):
            raise SystemExit(f"Forbidden scope column in {path.name}")
    manifest = read_json(OUT / "output-manifest.json")
    entries = manifest.get("files", [])
    encoded = "\n".join(f"{entry['path']}:{entry['sha256']}" for entry in entries).encode()
    if hashlib.sha256(encoded).hexdigest() != manifest.get("deterministic_hash"):
        raise SystemExit("Output manifest deterministic hash mismatch")
    for entry in entries:
        path = ROOT / str(entry["path"])
        if not path.exists() or sha256(path) != entry["sha256"]:
            raise SystemExit(f"Output hash mismatch: {path}")
    validation = read_json(OUT / "validation-report.json")
    if validation.get("passed") is not True:
        raise SystemExit("Validation report is not passing")
    print(
        json.dumps(
            {"passed": True, "decision": report["decision"], "network_requests": 0}, sort_keys=True
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
