#!/usr/bin/env python3
"""Validate the committed RD18-P3R preregistration bundle offline."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, cast

from spotbot.research.rd18_p3r_protocol import validate_protocol_bundle

ROOT = Path(__file__).resolve().parents[2]
OUT_REL = Path("data/research/rd18_p3r")


def _read_json(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate(root: Path) -> dict[str, Any]:
    out = root / OUT_REL
    protocol = _read_json(out / "rd18-p3r-protocol-v1.json")
    candidate = _read_json(out / "frozen-strategy-candidate.json")
    gates = _read_json(out / "performance-gate-registry.json")
    contract = _read_json(out / "replay-execution-contract.json")
    readiness = _read_json(out / "preexecution-readiness.json")
    final_report = _read_json(out / "rd18-p3r-final-report-v1.json")
    request = _read_json(out / "request-manifest.json")
    manifest = _read_json(out / "output-manifest.json")

    validate_protocol_bundle(protocol, candidate, gates, contract, readiness)

    errors: list[str] = []
    if final_report.get("decision") != protocol.get("decision"):
        errors.append("final report decision mismatch")
    if final_report.get("next_stage") != protocol.get("next_stage"):
        errors.append("final report next-stage mismatch")
    if request.get("network_requests") != 0:
        errors.append("network request manifest is non-zero")
    if request.get("post_2024_observations") != 0:
        errors.append("post-2024 observation manifest is non-zero")
    if request.get("strategy_replay_runs") != 0:
        errors.append("P3R unexpectedly executed a replay")
    if request.get("return_calculations") != 0:
        errors.append("P3R unexpectedly calculated returns")

    p2u2_manifest = _read_json(root / "data/research/rd18_p2u2/output-manifest.json")
    expected_p2u2 = (
        "f61ed396977e8b85faaad5e670e193d216a5d6e1c87bee8406301cbe0666b227"
    )
    if p2u2_manifest.get("deterministic_hash") != expected_p2u2:
        errors.append("P2U2 deterministic hash mismatch")

    rd16m_hashes = _read_json(root / "data/research/rd16m/output-hashes.json")
    expected_rd16m = {
        "rd16m-final-report-v1.json": "45f22e3b45beb1b7ec7263a2743dd451a020fd307d1109f984fa6ce7f1d0a295",
        "rd16m-protocol-v1.json": "3a9aaafefecb6ea2925b1a882bd5f05c01443e550339989bdb644145d74bc2e5",
        "cost-stress.csv": "3f46cb36cf4a955b21392f4009e1791290686065729f2a370fb874adef46200a",
        "validation-report.json": "0c308779fa0a50222c22231006c6c792e1d5a84e44ae9454afcd6474ead1ea04",
    }
    for name, expected in expected_rd16m.items():
        if rd16m_hashes.get(name) != expected:
            errors.append(f"RD16M registered hash mismatch: {name}")

    files = manifest.get("files")
    if not isinstance(files, list):
        errors.append("P3R output manifest has no files list")
        files = []
    for entry in files:
        if not isinstance(entry, dict):
            errors.append("invalid P3R manifest entry")
            continue
        rel = entry.get("path")
        expected = entry.get("sha256")
        if not isinstance(rel, str) or not isinstance(expected, str):
            errors.append("invalid P3R manifest fields")
            continue
        path = root / rel
        if not path.is_file():
            errors.append(f"missing P3R output: {rel}")
        elif _sha256(path) != expected:
            errors.append(f"P3R output hash mismatch: {rel}")

    passed = not errors
    return {
        "schema_version": "rd18-p3r-validator-result-v1",
        "passed": passed,
        "decision": protocol.get("decision"),
        "next_stage": protocol.get("next_stage"),
        "candidate": candidate.get("architecture_id"),
        "replay_execution_ready": readiness.get("replay_execution_ready"),
        "network_requests": request.get("network_requests"),
        "error_count": len(errors),
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true", help="Required no-network validation mode.")
    parser.add_argument("--root", type=Path, default=ROOT, help="Repository root.")
    args = parser.parse_args()
    if not args.offline:
        parser.error("--offline is required")
    result = validate(args.root.resolve())
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
