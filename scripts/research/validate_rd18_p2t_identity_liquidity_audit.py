# ruff: noqa: E501

"""Validate RD18-P2T outputs without network access."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

import pandas as pd

from spotbot.research.kucoin_rd18_p2t import IDENTITY_CLASSES

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "research" / "rd18_p2t"
CLAIM = "RESTRICTED_TO_376_KLINE_CONFIRMED_HISTORICAL_KUCOIN_SPOT_PAIRS"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate RD18-P2T offline audit outputs.")
    parser.parse_args()
    required = [
        "rd18-p2t-protocol-v1.json",
        "input-reconciliation.json",
        "current_seed_identity_audit.csv",
        "current_seed_impact_audit.csv",
        "liquidity_integrity_audit.csv",
        "structural_impact_assessment.json",
        "request-manifest.json",
        "validation-report.json",
        "rd18-p2t-final-report-v1.json",
        "output-manifest.json",
    ]
    missing = [name for name in required if not (OUT / name).exists()]
    if missing:
        raise SystemExit(f"missing required P2T outputs: {missing}")
    reconciliation = json.loads((OUT / "input-reconciliation.json").read_text(encoding="utf-8"))
    if reconciliation.get("passed") is not True:
        raise SystemExit("P2T input reconciliation failed")
    if reconciliation.get("counts") != {
        "variant_c_pairs": 376,
        "variant_d_pairs": 299,
        "current_seed_only_pairs": 77,
        "weekly_decisions": 313,
        "post_warmup_decisions": 301,
    }:
        raise SystemExit("P2T frozen counts do not reconcile")
    identity = pd.read_csv(
        OUT / "current_seed_identity_audit.csv", dtype=str, keep_default_na=False
    )
    if len(identity) != 77 or identity["asset_id"].nunique() != 77:
        raise SystemExit("identity audit must contain exactly 77 unique current-seed-only assets")
    if set(identity["classification"]) - set(IDENTITY_CLASSES):
        raise SystemExit("identity taxonomy contains an unregistered class")
    if identity["classification"].isna().any() or (identity["classification"] == "").any():
        raise SystemExit("identity classification is incomplete")
    impact = pd.read_csv(OUT / "current_seed_impact_audit.csv", dtype=str, keep_default_na=False)
    if len(impact) != 77 or set(impact["asset_id"]) != set(identity["asset_id"]):
        raise SystemExit("current-seed impact audit does not cover exactly the identity audit")
    liquidity = pd.read_csv(OUT / "liquidity_integrity_audit.csv", dtype=str, keep_default_na=False)
    required_liquidity = {
        "asset",
        "week",
        "entered_top6",
        "entered_top10",
        "classification_flags",
        "max_day_share",
        "turnover_stability",
        "pre_entry_volume",
        "post_entry_volume",
        "volume_change_ratio",
        "relative_to_btc_volume",
        "relative_to_eth_volume",
        "notes",
    }
    if not required_liquidity.issubset(liquidity.columns):
        raise SystemExit("liquidity audit columns are incomplete")
    if any(
        "2025-" in str(value) or "2026-" in str(value) for value in liquidity.to_numpy().ravel()
    ):
        raise SystemExit("sealed-period observation found in liquidity audit")
    report = json.loads((OUT / "rd18-p2t-final-report-v1.json").read_text(encoding="utf-8"))
    if report.get("restricted_claim") != CLAIM:
        raise SystemExit("restricted claim missing")
    for key in (
        "no_network",
        "no_post_2024_observations",
        "no_futures",
        "no_margin",
        "no_returns",
        "no_trading",
        "no_strategy_replay",
        "no_optimization",
    ):
        if report.get(key) is not True:
            raise SystemExit(f"scope flag failed: {key}")
    if report.get("assets_removed") != 0 or report.get("variant_e_created") is not False:
        raise SystemExit("P2T mutated the universe")
    request = json.loads((OUT / "request-manifest.json").read_text(encoding="utf-8"))
    if request.get("network_requests") != 0 or request.get("external_data") is not False:
        raise SystemExit("P2T recorded a network or external-data request")
    manifest = json.loads((OUT / "output-manifest.json").read_text(encoding="utf-8"))
    entries = manifest.get("files", [])
    encoded = "\n".join(f"{entry['path']}:{entry['sha256']}" for entry in entries).encode()
    if hashlib.sha256(encoded).hexdigest() != manifest.get("deterministic_hash"):
        raise SystemExit("P2T manifest deterministic hash mismatch")
    for entry in entries:
        path = ROOT / str(entry["path"])
        if not path.exists() or sha256(path) != entry["sha256"]:
            raise SystemExit(f"P2T output hash mismatch: {path}")
    for path in OUT.glob("*.csv"):
        with path.open("r", encoding="utf-8", newline="") as handle:
            header = next(csv.reader(handle), [])
        lowered = {column.lower() for column in header}
        forbidden = {"pnl", "return", "trade", "signal", "candidate", "optimization"}
        if any(any(token in column for token in forbidden) for column in lowered):
            raise SystemExit(f"forbidden strategy/trading column in {path.name}")
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
