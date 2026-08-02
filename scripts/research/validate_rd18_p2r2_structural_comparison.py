"""Validate committed/offline RD18-P2R2 structural-comparison outputs."""

from __future__ import annotations

import csv
import hashlib
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "research" / "rd18_p2r2"
REPORT_DIR = ROOT / "reports" / "research"
EXPECTED_MANIFEST = ""  # populated by the runner and checked structurally
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
REQUIRED_DATA_FILES = {
    "rd18-p2r2-protocol-v1.json",
    "input-reconciliation.json",
    "corrected-pair-discovery-provenance.csv",
    "corrected-weekly-universe-growth.csv",
    "corrected-annual-universe-summary.csv",
    "corrected-membership-persistence.csv",
    "corrected-weekly-turnover.csv",
    "corrected-liquidity-concentration.csv",
    "corrected-cutoff-stability.csv",
    "corrected-variant-weekly-comparison.csv",
    "corrected-variant-annual-summary.csv",
    "corrected-substitution-distribution.csv",
    "corrected-current-seed-influence.csv",
    "corrected-current-seed-influence-by-year.csv",
    "p2t-liquidity-flag-structural-audit.csv",
    "corrected-delisted-pair-impact.csv",
    "corrected-cmc-snapshot-comparison.csv",
    "corrected-legacy-universe-diagnostic.csv",
    "old-vs-corrected-conclusions.csv",
    "corrected-omission-risk-assessment.json",
    "corrected-future-universe-requirements.json",
    "request-manifest.json",
    "output-manifest.json",
    "rd18-p2r2-final-report-v1.json",
}


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def manifest_hash(manifest: dict[str, Any]) -> str:
    entries = manifest.get("files", [])
    encoded = "\n".join(f"{item['path']}:{item['sha256']}" for item in entries).encode()
    return hashlib.sha256(encoded).hexdigest()


def csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def validate() -> list[str]:
    errors: list[str] = []
    missing = sorted(name for name in REQUIRED_DATA_FILES if not (OUT / name).is_file())
    errors.extend(f"missing:{name}" for name in missing)
    if missing:
        return errors
    protocol = read_json(OUT / "rd18-p2r2-protocol-v1.json")
    reconciliation = read_json(OUT / "input-reconciliation.json")
    report = read_json(OUT / "rd18-p2r2-final-report-v1.json")
    request = read_json(OUT / "request-manifest.json")
    manifest = read_json(OUT / "output-manifest.json")
    if protocol.get("source_commit") != "55d33c941cb72b9c3e097720387b05b76ed6e3a7":
        errors.append("protocol source commit mismatch")
    if reconciliation.get("passed") is not True:
        errors.append("input reconciliation not passed")
    counts = reconciliation.get("counts", {})
    expected_counts = {
        "raw_inventory_unique_pairs": 376,
        "c2_pairs": 364,
        "d2_pairs": 299,
        "c2_minus_d2_pairs": 65,
        "excluded_products": 12,
        "weekly_decisions": 313,
        "post_warmup_decisions": 301,
        "p1r2_boundaries": 376,
    }
    for key, expected in expected_counts.items():
        if counts.get(key) != expected:
            errors.append(f"count:{key}={counts.get(key)!r}, expected {expected}")
    if report.get("decision") != "RD18_P2R2_CORRECTED_UNIVERSE_ROBUSTNESS_REDESIGN_REQUIRED":
        errors.append("unexpected P2R2 decision")
    if report.get("risk_classification") != "HIGH":
        errors.append("unexpected corrected risk classification")
    if report.get("next_stage") != "RD18_P2S2_CORRECTED_UNIVERSE_RISK_REDESIGN":
        errors.append("unexpected next stage")
    if request.get("network_requests") != 0 or manifest.get("network_requests") != 0:
        errors.append("network request count is not zero")
    if manifest_hash(manifest) != manifest.get("deterministic_hash"):
        errors.append("output manifest deterministic hash mismatch")
    manifest_paths = {Path(str(item.get("path", ""))).name for item in manifest.get("files", [])}
    if not REQUIRED_DATA_FILES - {"output-manifest.json"} <= manifest_paths:
        errors.append("output manifest is missing required files")
    corrected_rank_files = (
        "corrected-weekly-eligibility.csv",
        "corrected-weekly-rankings.csv",
        "corrected-weekly-topn.csv",
    )
    # These three upstream files are not P2R2 outputs but remain the frozen
    # product-exclusion source.  Validate them directly as an integrity gate.
    for source_name in corrected_rank_files:
        source = ROOT / "data" / "research" / "rd18_p1r2" / source_name
        if source.is_file():
            rows = csv_rows(source)
            if any(str(row.get("pair", "")) in PRODUCTS for row in rows):
                errors.append(f"excluded product present in upstream corrected file:{source_name}")
    for filename in sorted(REQUIRED_DATA_FILES):
        path = OUT / filename
        if not path.is_file() or path.suffix != ".csv":
            continue
        text = path.read_text(encoding="utf-8")
        # Match date/year cells, not incidental digit substrings inside floats.
        if re.search(r"(?:^|[,;])202(?:5|6)(?:[-T,;]|$)", text):
            errors.append(f"post-2024 marker in:{filename}")
        rows = csv_rows(path)
        if rows:
            headers = {str(key).lower() for key in rows[0]}
            forbidden = {
                key
                for key in headers
                if any(
                    token in key
                    for token in (
                        "return",
                        "trade",
                        "signal",
                        "candidate",
                        "profit",
                        "optimization",
                    )
                )
            }
            if forbidden:
                errors.append(f"forbidden research-output columns:{filename}:{sorted(forbidden)}")
    for name in (
        "rd18-p2r2-methodology-v1.md",
        "rd18-p2r2-results-v1.md",
        "rd18-p2r2-decisions-v1.md",
    ):
        path = REPORT_DIR / name
        if not path.is_file():
            errors.append(f"missing report:{name}")
        elif "RESTRICTED_TO_376_KLINE_CONFIRMED_HISTORICAL_KUCOIN_SPOT_PAIRS" not in path.read_text(
            encoding="utf-8"
        ):
            errors.append(f"restricted claim missing:{name}")
    if report.get("network_requests") != 0 or report.get("post_2024_observations") != 0:
        errors.append("report sealed/network declarations failed")
    if any(
        report.get(key) != 0
        for key in (
            "futures",
            "margin",
            "returns",
            "signals",
            "trades",
            "candidates",
            "optimization",
        )
    ):
        errors.append("report forbidden-work declaration failed")
    return errors


def main() -> int:
    errors = validate()
    if errors:
        for error in errors:
            print(f"FAIL {error}")
        return 1
    print(
        "RD18-P2R2 validation passed: zero network requests, corrected HIGH risk, "
        "restricted claim preserved"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
