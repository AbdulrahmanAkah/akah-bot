"""Close the governed repair work honestly; fresh market reserve stays blocked."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
REL = "governance/four_source_repairs_v10"
TASK = "AKAH_FOUR_SOURCE_REPAIRS_AND_UNUSED_RESERVE_PREPARATION_V10"


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest().upper()


def main():
    p = ROOT / REL / "canonical_result.json"
    r = json.loads(p.read_text())
    assert r["technical_repair_status"] == "PASS" and r["four_repairs_closed"]
    assert r["synthetic_tests"]["tests"] == 397 and r["new_tests"] == 58
    assert not r["unused_market_reserve_ready"] and not r["ready_for_gate3_replay"]
    evidence = r["artifact_bindings"] + [
        dict(path=REL + "/synthetic_results.xml", sha256=sha(ROOT / REL / "synthetic_results.xml"))
    ]
    for ref in evidence:
        assert sha(ROOT / ref["path"]) == ref["sha256"]
    declarations = {
        k: False
        for k in (
            "lookahead_or_future_information_used",
            "pair_or_event_identity_used_as_runtime_rule",
            "posthoc_outcome_threshold_search_used",
            "2023_new_raw_or_replay_accessed",
            "2024_used_as_fresh_holdout",
            "2024_used_to_define_new_runtime_rule",
            "2025_accessed",
            "production_changed",
            "economic_replay_executed",
            "gate3_replay_executed",
            "research_push",
        )
    }
    cmd = [
        sys.executable,
        "-B",
        "-m",
        "spotbot.governance.task_completion_gate",
        "--repo",
        str(ROOT),
    ]
    subprocess.run(
        cmd
        + [
            "complete",
            "--task-id",
            TASK,
            "--outcome",
            "BLOCKED",
            "--alignment",
            "ALIGNED",
            "--vision-impact",
            "ADVANCES",
            "--summary",
            (
                "Four V10 opt-in technical repairs PASS; 397 synthetic tests (58 new); "
                "explicit stop provenance, full live Wyckoff graph and actual stage campaign "
                "receipt, exact prebatch admission, declared nontruncated Elliott scope. "
                "Fresh unused historical market reserve NOT READY: missing exact-version "
                "historical producer authority; no economics or funding."
            ),
            "--north-star-effect",
            (
                "Removes source/owner/feasibility defects without fitting outcomes or "
                "fabricating market fidelity. Technical closure is distinct from fresh "
                "reserve and economic qualification."
            ),
            "--next-bottleneck",
            r["next_bottleneck"],
            "--result-ref",
            REL + "/canonical_result.json",
            "--result-sha256",
            sha(p),
            "--evidence-json",
            json.dumps(evidence),
            "--governance-json",
            json.dumps(declarations),
        ],
        cwd=ROOT,
        check=True,
    )
    subprocess.run(cmd + ["verify", "--task-id", TASK], cwd=ROOT, check=True)


if __name__ == "__main__":
    main()
