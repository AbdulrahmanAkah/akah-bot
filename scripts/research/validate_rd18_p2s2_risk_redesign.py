"""Validate the offline RD18-P2S2 corrected-universe redesign outputs."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "research" / "rd18_p2s2"
CLAIM = "RESTRICTED_TO_376_KLINE_CONFIRMED_HISTORICAL_KUCOIN_SPOT_PAIRS"
DECISION = "RD18_P2S2_CONFIDENCE_AWARE_UNIVERSE_DESIGN_REQUIRED"
NEXT_STAGE = "RD18_P2U2_CONFIDENCE_AWARE_UNIVERSE_DESIGN"
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
    "p1r2": "0cc3d273e55aa1d1425de97b47fb5cad7610c6c2c7da6aec348850a635947048",
    "p2r": "5ef8deefaa512e07cac33150399a4cb3bdfa685e623d690e3a804bf3a9ef5b1a",
    "p2s": "38e19370f3e98539b7d55502c6d5b97acf80829d3332df3c7c56a6232f3eccfd",
    "p2t": "afcbabc0a5dbd77791adde75fe895d2d55386e51df568d391d9df77d007aa0bf",
    "p2u": "583be92b9880364a53ecabcf53e5980350c2ef06b11da2c3612f78269feae551",
    "p2r2": "4ff50cc2c209ea68e31b95467581a9b651a9b1a17b37c505a1de280902fb3ee3",
}
REQUIRED_OUTPUTS = {
    "rd18-p2s2-protocol-v1.json",
    "input-reconciliation.json",
    "corrected-exact-threshold-brittleness.csv",
    "corrected-weekly-membership-distance.csv",
    "corrected-substitution-distribution.csv",
    "corrected-disagreement-duration.csv",
    "corrected-substitution-liquidity-audit.csv",
    "corrected-current-seed-asset-impact.csv",
    "corrected-current-seed-impact-concentration.csv",
    "corrected-hysteresis-robustness.csv",
    "corrected-liquidity-flag-disagreement-audit.csv",
    "corrected-dual-scenario-feasibility.json",
    "confidence-aware-design-necessity.json",
    "boundary-local-intervention-opportunity.csv",
    "future-universe-protocol-requirements.json",
    "old-vs-corrected-p2s-conclusions.csv",
    "request-manifest.json",
    "output-manifest.json",
    "rd18-p2s2-final-report-v1.json",
}
REQUIRED_REPORTS = {
    "rd18-p2s2-methodology-v1.md",
    "rd18-p2s2-results-v1.md",
    "rd18-p2s2-decisions-v1.md",
}


class ValidationError(RuntimeError):
    """Raised when a frozen P2S2 output contract is violated."""


def load_json(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def fail(message: str) -> None:
    raise ValidationError(message)


def require(condition: bool, message: str) -> None:
    if not condition:
        fail(message)


def validate_files() -> dict[str, Any]:
    require(OUT.is_dir(), "P2S2 output directory is missing")
    missing = sorted(name for name in REQUIRED_OUTPUTS if not (OUT / name).is_file())
    require(not missing, f"missing required output files: {missing}")
    reports = ROOT / "reports" / "research"
    missing_reports = sorted(name for name in REQUIRED_REPORTS if not (reports / name).is_file())
    require(not missing_reports, f"missing required reports: {missing_reports}")
    manifest = load_json(OUT / "output-manifest.json")
    require(manifest.get("network_requests") == 0, "output manifest records network requests")
    entries = cast(list[dict[str, Any]], manifest.get("files", []))
    listed = {str(entry.get("path", "")).replace("\\", "/") for entry in entries}
    expected_paths = {
        f"data/research/rd18_p2s2/{name}"
        for name in REQUIRED_OUTPUTS
        if name != "output-manifest.json"
    }
    require(listed == expected_paths, "output manifest file set does not match required outputs")
    for entry in entries:
        relative = str(entry["path"]).replace("/", "\\")
        path = ROOT / relative
        require(path.is_file(), f"manifest file missing: {entry['path']}")
        require(path.stat().st_size == int(entry["bytes"]), f"byte count mismatch: {entry['path']}")
        require(sha256_file(path) == entry["sha256"], f"SHA-256 mismatch: {entry['path']}")
    encoded = "\n".join(f"{entry['path']}:{entry['sha256']}" for entry in entries).encode()
    require(
        hashlib.sha256(encoded).hexdigest() == manifest.get("deterministic_hash"),
        "manifest hash mismatch",
    )
    require(
        manifest.get("deterministic_offline_rebuild") is True, "deterministic rebuild flag is false"
    )
    return manifest


def validate_inputs_and_decision() -> dict[str, Any]:
    final = load_json(OUT / "rd18-p2s2-final-report-v1.json")
    reconciliation = cast(dict[str, Any], final.get("input_reconciliation", {}))
    counts = cast(dict[str, Any], reconciliation.get("counts", {}))
    expected_counts = {
        "raw_inventory_pairs": 376,
        "c2_pairs": 364,
        "d2_pairs": 299,
        "c2_minus_d2_pairs": 65,
        "excluded_products": 12,
        "post_warmup_decisions": 301,
        "weekly_decisions": 313,
        "p2t_temporally_distinct": 65,
        "p2t_unresolved": 0,
        "d2_post_warmup_six_asset_weeks": 301,
        "d2_post_warmup_ten_asset_weeks": 275,
    }
    for key, value in expected_counts.items():
        require(counts.get(key) == value, f"count mismatch for {key}: {counts.get(key)!r}")
    hashes = cast(dict[str, Any], reconciliation.get("hashes", {}))
    for key, expected in EXPECTED_HASHES.items():
        require(hashes.get(key) == expected, f"input hash mismatch for {key}")
    require(reconciliation.get("passed") is True, "input reconciliation did not pass")
    require(final.get("decision") == DECISION, "unexpected P2S2 decision")
    require(final.get("next_stage") == NEXT_STAGE, "unexpected P2S2 next stage")
    require(final.get("restricted_claim") == CLAIM, "restricted claim missing")
    require(final.get("full_historical_inventory_claim") is False, "full inventory claim enabled")
    require(
        final.get("p2r2_decision_preserved")
        == "RD18_P2R2_CORRECTED_UNIVERSE_ROBUSTNESS_REDESIGN_REQUIRED",
        "P2R2 decision changed",
    )
    require(final.get("p2r2_risk_classification") == "HIGH", "P2R2 risk changed")
    require(final.get("network_requests") == 0, "final report records network requests")
    require(final.get("post_2024_observations") == 0, "post-2024 observations recorded")
    for key in ("futures", "margin", "returns", "signals", "trades", "candidates", "optimization"):
        require(final.get(key) == 0, f"forbidden activity counter is non-zero: {key}")
    require(
        final.get("no_intersection_universe") is True, "intersection universe was not prohibited"
    )
    require(final.get("variant_e_constructed") is False, "Variant E was constructed")
    require(final.get("p2u2_executed") is False, "P2U2 was executed")
    return final


def validate_product_and_prohibitions() -> None:
    for path in sorted(OUT.glob("*.csv")):
        text = path.read_text(encoding="utf-8")
        require(
            not any(product in text for product in PRODUCTS),
            f"excluded product in output: {path.name}",
        )
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            fields = reader.fieldnames or []
            for row in reader:
                for key, value in row.items():
                    if key and any(token in key.lower() for token in ("date", "time", "week")):
                        for year_text in re.findall(r"(20\d{2})-\d{2}-\d{2}", str(value)):
                            require(
                                int(year_text) < 2025, f"post-2024 date in {path.name}: {value}"
                            )
        forbidden = {
            "return",
            "returns",
            "trade",
            "trades",
            "signal",
            "signals",
            "candidate",
            "candidates",
        }
        require(
            not forbidden.intersection(field.lower() for field in fields),
            f"forbidden output column in {path.name}",
        )
    future = load_json(OUT / "future-universe-protocol-requirements.json")
    require(future.get("variant_e_constructed") is False, "future requirements construct Variant E")
    require(future.get("p2u2_execution") is False, "future requirements execute P2U2")
    require(future.get("restricted_claim") == CLAIM, "future requirements lack restricted claim")
    reports = ROOT / "reports" / "research"
    for name in REQUIRED_REPORTS:
        require(
            CLAIM in (reports / name).read_text(encoding="utf-8"),
            f"restricted claim missing from {name}",
        )
    require(not list(OUT.glob("*variant-e*")), "Variant E output exists")
    request = load_json(OUT / "request-manifest.json")
    require(
        request.get("network_requests") == 0 and request.get("requests") == [],
        "request manifest is not zero-network",
    )


def validate() -> dict[str, Any]:
    manifest = validate_files()
    final = validate_inputs_and_decision()
    validate_product_and_prohibitions()
    dual = load_json(OUT / "corrected-dual-scenario-feasibility.json")
    require(dual.get("feasible") is False, "dual-scenario feasibility incorrectly passed")
    require(
        any(value is False for value in cast(dict[str, Any], dual.get("gates", {})).values()),
        "dual gates contain no failure",
    )
    confidence = load_json(OUT / "confidence-aware-design-necessity.json")
    require(confidence.get("justified") is True, "confidence-aware design necessity did not pass")
    require(
        confidence.get("variant_e_constructed") is False, "confidence output constructs Variant E"
    )
    return {
        "decision": final["decision"],
        "next_stage": final["next_stage"],
        "network_requests": 0,
        "manifest_hash": manifest["deterministic_hash"],
        "variant_e_constructed": False,
        "p2u2_executed": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate offline RD18-P2S2 outputs")
    parser.add_argument(
        "--offline", action="store_true", required=True, help="required; no network is allowed"
    )
    args = parser.parse_args()
    if not args.offline:
        raise SystemExit("--offline is required")
    try:
        print(json.dumps(validate(), sort_keys=True))
    except ValidationError as exc:
        raise SystemExit(f"RD18-P2S2 validation failed: {exc}") from exc


if __name__ == "__main__":
    main()
