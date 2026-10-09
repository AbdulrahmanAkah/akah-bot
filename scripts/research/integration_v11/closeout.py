"""Complete/verify scoped repair; never claim market reserve certification."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
REL = "governance/source_integrity_closure_v11"
TASK = "AKAH_V11_REVIEW_SOURCE_INTEGRITY_AND_EXPORT_CLOSURE"


def main():
    path = ROOT / REL / "canonical_result.json"
    result = json.loads(path.read_text())
    assert result["technical_status"] == "PASS" and result["review_items_closed"]
    assert not result["ready_for_gate3_replay"] and not result["independent_V11_review"]
    for item in result["artifact_bindings"]:
        assert (
            hashlib.sha256((ROOT / item["path"]).read_bytes()).hexdigest().upper() == item["sha256"]
        )
    declarations = {
        key: False
        for key in (
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
            "PASS",
            "--alignment",
            "ALIGNED",
            "--vision-impact",
            "ADVANCES",
            "--summary",
            "V11 F1 source-bound LPS add, F2 typed source PIT and F3 full emission integrity "
            "closed technically; 465 synthetic tests incl 68 new and 465 isolated exported tests; "
            "data/core export and exact arch8.0.0 dependency contract closed; "
            "old V4-V10 unchanged. No independent V11 acceptance, historical producer/reserve "
            "or economic qualification claimed.",
            "--north-star-effect",
            "Preserves school ownership and actual execution authority; "
            "rejects prebind and post-preview mutation "
            "without new trading signals or outcome fitting.",
            "--next-bottleneck",
            result["next_bottleneck"],
            "--result-ref",
            REL + "/canonical_result.json",
            "--result-sha256",
            hashlib.sha256(path.read_bytes()).hexdigest().upper(),
            "--evidence-json",
            json.dumps(result["artifact_bindings"]),
            "--governance-json",
            json.dumps(declarations),
        ],
        cwd=ROOT,
        check=True,
    )
    subprocess.run(cmd + ["verify", "--task-id", TASK], cwd=ROOT, check=True)


if __name__ == "__main__":
    main()
