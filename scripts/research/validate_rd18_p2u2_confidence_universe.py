"""Offline validator for the RD18-P2U2 confidence-aware design outputs."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "research" / "rd18_p2u2"
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
EXPECTED_INPUT_HASHES = {
    "p1r": "3956041409448c3fb547d18917d46f423e07b88b8815961a1a61866fd4ab03b0",
    "p1r2": "0cc3d273e55aa1d1425de97b47fb5cad7610c6c2c7da6aec348850a635947048",
    "p2r": "5ef8deefaa512e07cac33150399a4cb3bdfa685e623d690e3a804bf3a9ef5b1a",
    "p2s": "38e19370f3e98539b7d55502c6d5b97acf80829d3332df3c7c56a6232f3eccfd",
    "p2t": "afcbabc0a5dbd77791adde75fe895d2d55386e51df568d391d9df77d007aa0bf",
    "p2u": "583be92b9880364a53ecabcf53e5980350c2ef06b11da2c3612f78269feae551",
    "p2r2": "4ff50cc2c209ea68e31b95467581a9b651a9b1a17b37c505a1de280902fb3ee3",
    "p2s2": "5faeee9ac872fad360d4b56aad5a442224bebee24dae69a3f69ac59e236136de",
    "t0": "4c2239cdd1fc71fe52aab06c5e8aa75770a48074a47be57e4db94e030b34f659",
}


class ValidationError(RuntimeError):
    """Raised for an invalid or incomplete P2U2 output set."""


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValidationError(f"expected JSON object: {path}")
    return value


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def bool_value(value: object) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes"}


def canonical(value: str) -> str:
    return value.removesuffix("-USDT")


def validate_manifest() -> None:
    manifest = read_json(OUT / "output-manifest.json")
    entries = manifest.get("files")
    if not isinstance(entries, list) or not entries:
        raise ValidationError("manifest has no files")
    normalized: list[dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValidationError("malformed manifest entry")
        relative = str(entry.get("path", ""))
        path = ROOT / Path(relative)
        if not path.is_file():
            raise ValidationError(f"manifest file missing: {relative}")
        actual_bytes = path.stat().st_size
        actual_hash = sha256(path)
        if actual_bytes != int(entry.get("bytes", -1)) or actual_hash != entry.get("sha256"):
            raise ValidationError(f"manifest mismatch: {relative}")
        normalized.append({"path": relative, "sha256": actual_hash})
    encoded = "\n".join(
        f"{entry['path']}:{entry['sha256']}"
        for entry in sorted(normalized, key=lambda item: str(item["path"]).lower())
    ).encode("utf-8")
    expected = hashlib.sha256(encoded).hexdigest()
    if expected != manifest.get("deterministic_hash"):
        raise ValidationError("deterministic output-manifest hash mismatch")
    if int(manifest.get("network_requests", -1)) != 0:
        raise ValidationError("manifest records network access")


def validate_rankings() -> dict[str, Any]:
    report = read_json(OUT / "rd18-p2u2-final-report-v1.json")
    if report.get("decision") != "RD18_P2U2_CONFIDENCE_AWARE_UNIVERSE_DESIGN_CONFIRMED":
        raise ValidationError(f"unexpected decision: {report.get('decision')}")
    if (
        report.get("restricted_claim")
        != "RESTRICTED_TO_376_KLINE_CONFIRMED_HISTORICAL_KUCOIN_SPOT_PAIRS"
    ):
        raise ValidationError("restricted claim missing")
    if report.get("network_requests") != 0 or report.get("post_2024_observations") != 0:
        raise ValidationError("sealed-data/network gate failed")
    for field in ("futures", "margin", "returns", "signals", "trades", "optimization"):
        if report.get(field) != 0:
            raise ValidationError(f"forbidden activity recorded: {field}")
    protocol = read_json(OUT / "rd18-p2u2-protocol-v1.json")
    if protocol.get("input_hashes") != EXPECTED_INPUT_HASHES:
        raise ValidationError("protocol input hashes do not reconcile")
    reconciliation = read_json(OUT / "input-reconciliation.json")
    if not reconciliation.get("passed"):
        raise ValidationError("input reconciliation failed")
    counts = reconciliation.get("counts", {})
    expected_counts = {
        "c2_pairs": 364,
        "d2_pairs": 299,
        "c2_minus_d2_pairs": 65,
        "current_seed_pairs": 65,
        "excluded_products": 12,
        "weekly_decisions": 313,
        "post_warmup_decisions": 301,
    }
    for key, expected in expected_counts.items():
        if int(counts.get(key, -1)) != expected:
            raise ValidationError(f"count mismatch: {key}")

    classification = read_csv(OUT / "confidence-classification.csv")
    if len(classification) != 364:
        raise ValidationError("confidence classification does not contain C2")
    if (
        sum(row.get("confidence_class") == "CURRENT_SEED_KLINE_CONFIRMED" for row in classification)
        != 65
    ):
        raise ValidationError("current-seed class count mismatch")

    for filename in (
        "weekly-e05-ranking.csv",
        "weekly-e10-ranking.csv",
        "weekly-e15-ranking.csv",
        "weekly-e-topn.csv",
        "e05-hysteresis.csv",
        "e10-hysteresis.csv",
        "e15-hysteresis.csv",
    ):
        rows = read_csv(OUT / filename)
        if any(row.get("pair") in PRODUCTS for row in rows):
            raise ValidationError(f"excluded product in {filename}")

    e10 = read_csv(OUT / "weekly-e10-ranking.csv")
    grouped: dict[str, list[dict[str, str]]] = {}
    for row in e10:
        grouped.setdefault(row["decision_time"], []).append(row)
        old_rank = int(float(row["original_c_rank"]))
        adjusted = int(float(row["adjusted_rank"]))
        if abs(adjusted - old_rank) > 1:
            raise ValidationError("non-adjacent movement in E10")
    if len(grouped) != 310:
        raise ValidationError("E10 ranking decision count mismatch")
    for decision, rows in grouped.items():
        ranks = sorted(int(float(row["adjusted_rank"])) for row in rows)
        if ranks != list(range(1, len(rows) + 1)):
            raise ValidationError(f"non-contiguous E10 ranks: {decision}")
    interventions = read_csv(OUT / "confidence-intervention-audit.csv")
    e10_interventions = [row for row in interventions if row.get("variant") == "E10"]
    if not e10_interventions:
        raise ValidationError("E10 has no qualifying intervention")
    for row in e10_interventions:
        if (
            row.get("promoted_confidence") != "EVIDENCE_STRONG"
            or row.get("displaced_confidence") != "CURRENT_SEED_KLINE_CONFIRMED"
        ):
            raise ValidationError("E10 intervention confidence direction failed")
        if float(row.get("relative_liquidity_sacrifice", "inf")) > 0.10 + 1e-12:
            raise ValidationError("E10 intervention exceeds 10 percent")
    gates = report.get("gates")
    if not isinstance(gates, dict) or not all(bool(value) for value in gates.values()):
        raise ValidationError("final report contains a failed gate")
    return {
        "decision": report["decision"],
        "e10_interventions": len(e10_interventions),
        "manifest_hash": read_json(OUT / "output-manifest.json")["deterministic_hash"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate offline RD18-P2U2 outputs.")
    parser.add_argument("--offline", action="store_true", help="assert zero-network validation")
    parser.parse_args()
    validate_manifest()
    result = validate_rankings()
    print(json.dumps({"passed": True, **result}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
