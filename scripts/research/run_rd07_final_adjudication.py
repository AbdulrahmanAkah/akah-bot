"""Reconcile RD07 evidence and record the final non-portfolio decision."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "reports" / "research"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    diagnostic = json.loads(
        (REPORTS / "ams-rd07-signal-diagnostic-v1.json").read_text(encoding="utf-8")
    )
    expected = "RD07_CROSS_VENUE_SPOT_FLOW_EDGE_NOT_CONFIRMED"
    if diagnostic["decision"] != expected:
        raise RuntimeError("RD07 final adjudication requires the registered S1 decision")
    evidence_paths = sorted(
        path
        for path in REPORTS.glob("ams-rd07-*")
        if path.name
        not in {
            "ams-rd07-final-adjudication-v1.json",
            "ams-rd07-final-adjudication-v1.md",
            "ams-rd07-output-hashes-v1.csv",
        }
    )
    hashes = [
        {
            "path": str(path.relative_to(ROOT)),
            "size_bytes": path.stat().st_size,
            "sha256": sha256(path),
        }
        for path in evidence_paths
    ]
    pd.DataFrame(hashes).to_csv(REPORTS / "ams-rd07-output-hashes-v1.csv", index=False)
    report = {
        "stage": "RD07-FINAL-ADJUDICATION",
        "status": "COMPLETE",
        "decision": expected,
        "confirmed_signal_count": 0,
        "confirmed_signal_ids": [],
        "external_replication_candidate_ids": [],
        "next_stage": "RD07_TERMINATION_OR_NEW_INFORMATION_SOURCE",
        "portfolio_simulation_authorized": False,
        "portfolio_construction_authorized": False,
        "production_change_authorized": False,
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
        "evidence_file_count": len(hashes),
        "output_hash_manifest": "reports/research/ams-rd07-output-hashes-v1.csv",
    }
    (REPORTS / "ams-rd07-final-adjudication-v1.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    summary = (
        "# RD07 Final Adjudication\n\n"
        f"- Decision: `{expected}`\n"
        "- Confirmed signals: `0`\n"
        "- Portfolio construction authorized: `false`\n"
        "- 2025/2026 accessed: `false/false`\n"
    )
    (REPORTS / "ams-rd07-final-adjudication-v1.md").write_text(
        summary, encoding="utf-8", newline="\n"
    )
    (ROOT / "RD07_FINAL_RESULT_FOR_CHATGPT.md").write_text(summary, encoding="utf-8", newline="\n")
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
