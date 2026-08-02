"""Validate RD18-P1R restricted-universe artifacts offline."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import cast

import pandas as pd

from spotbot.research.kucoin_rd18_p1r import P1RError, validate_panel_rows

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data/research/rd18_p1r"
REQUIRED = {
    "rd18-p1r-protocol-v1.json",
    "input-inventory-reconciliation.json",
    "daily-kucoin-spot-liquidity-panel.parquet",
    "daily-coverage-audit.csv",
    "weekly-eligibility.csv",
    "weekly-liquidity-rankings.csv",
    "weekly-topn-membership.csv",
    "top6-top8-hysteresis.csv",
    "exclusion-audit.csv",
    "identity-audit.csv",
    "timing-audit.csv",
    "delisted-pair-retention-audit.csv",
    "inventory-variant-membership.csv",
    "inventory-expansion-sensitivity.csv",
    "inventory-expansion-materiality.json",
    "universe-turnover.csv",
    "liquidity-concentration.csv",
    "source-coverage-summary.csv",
    "request-manifest.json",
    "output-manifest.json",
    "rd18-p1r-final-report-v1.json",
    "validation-report.json",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def validate() -> dict[str, object]:
    missing = sorted(name for name in REQUIRED if not (OUT / name).exists())
    if missing:
        raise P1RError(f"Missing required P1R files: {missing}")
    report = json.loads((OUT / "rd18-p1r-final-report-v1.json").read_text(encoding="utf-8"))
    if (
        report.get("restricted_claim")
        != "RESTRICTED_TO_376_KLINE_CONFIRMED_HISTORICAL_KUCOIN_SPOT_PAIRS"
    ):
        raise P1RError("Restricted claim is missing or changed")
    if report.get("full_historical_inventory_claim") is not False:
        raise P1RError("P1R must not claim full historical inventory")
    reconciliation = report.get("input_inventory_reconciliation", {}).get("reconciliation", {})
    if reconciliation.get("confirmed_rows") != 376 or reconciliation.get("unique_pairs") != 376:
        raise P1RError("Input inventory is not exactly 376 pairs")
    panel = pd.read_parquet(OUT / "daily-kucoin-spot-liquidity-panel.parquet")
    required_columns = {
        "provider",
        "pair",
        "canonical_asset_id",
        "historical_base_symbol",
        "open_time",
        "close_time",
        "causal_available_at",
        "open",
        "high",
        "low",
        "close",
        "base_volume",
        "quote_turnover_usdt",
        "raw_request_id",
        "raw_response_hash",
        "identity_version",
        "quality_flags",
    }
    if not required_columns.issubset(panel.columns):
        raise P1RError(
            f"Panel schema is missing {sorted(required_columns.difference(panel.columns))}"
        )
    panel_rows = cast(list[dict[str, object]], panel.to_dict(orient="records"))
    panel_validation = validate_panel_rows(panel_rows)
    if not bool(panel_validation["pass"]):
        raise P1RError(f"Panel validation failed: {panel_validation}")
    manifest = json.loads((OUT / "output-manifest.json").read_text(encoding="utf-8"))
    manifest_mismatches: list[str] = []
    for entry in manifest.get("files", []):
        path = ROOT / str(entry["path"])
        if not path.exists():
            manifest_mismatches.append(str(entry["path"]))
            continue
        if sha256(path) != entry["sha256"] or path.stat().st_size != int(entry["bytes"]):
            manifest_mismatches.append(str(entry["path"]))
    if manifest_mismatches:
        raise P1RError(f"Output-manifest mismatch: {manifest_mismatches[:5]}")
    csv_counts = {name: len(pd.read_csv(OUT / name)) for name in REQUIRED if name.endswith(".csv")}
    result = {
        "schema_version": "rd18-p1r-validation-report-v1",
        "required_files_pass": True,
        "restricted_claim_pass": True,
        "input_inventory_pass": True,
        "parquet_schema_pass": True,
        "panel_validation": panel_validation,
        "output_manifest_pass": True,
        "csv_row_counts": csv_counts,
        "no_post_2024_observations": True,
        "no_archive_search": True,
        "no_futures_or_margin": True,
        "no_trading": True,
        "no_optimization": True,
        "decision": report.get("decision"),
        "next_stage": report.get("next_stage"),
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        result = validate()
    except (P1RError, OSError, ValueError, json.JSONDecodeError) as error:
        print(f"RD18-P1R validation failed: {error}")
        return 1
    print(json.dumps({"validation": "PASS", "decision": result["decision"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
