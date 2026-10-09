"""Close only the completed V9 engineering task, never fund or run a replay."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
REL = "governance/producer_integration_bundle_v9"
TASK = "AKAH_PACKAGE2_CAUSAL_PRODUCER_ROUTER_EXECUTION_INTEGRATION_V9"


def main():
    result_path = ROOT / REL / "canonical_result.json"
    result = json.loads(result_path.read_text())
    assert result["technical_package_status"] == "PASS"
    assert result["full_authority_package_status"] == "NOT_CLOSED"
    assert not result["ready_for_gate3_replay"] and not result["funded_grammars"]
    assert result["synthetic_tests"]["tests"] == 339
    assert result["new_package_tests"] == 68
    evidence = result["artifact_bindings"] + [
        {
            "path": REL + "/synthetic_results.xml",
            "sha256": hashlib.sha256((ROOT / REL / "synthetic_results.xml").read_bytes())
            .hexdigest()
            .upper(),
        }
    ]
    for ref in evidence:
        assert (
            hashlib.sha256((ROOT / ref["path"]).read_bytes()).hexdigest().upper() == ref["sha256"]
        )
    declarations = {
        k: False
        for k in [
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
        ]
    }
    command = [
        sys.executable,
        "-B",
        "-m",
        "spotbot.governance.task_completion_gate",
        "--repo",
        str(ROOT),
    ]
    subprocess.run(
        command
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
            (
                "V9 opt-in causal source/router/kernel integration technical PASS; "
                "339 synthetic tests including 68 new; integer-ID owner-state carryover "
                "repaired; full producer semantic authority, reserve and historical "
                "quantity remain unclosed; no economics"
            ),
            "--north-star-effect",
            (
                "Establishes causal proof-linked distinct ownership execution without "
                "inheriting stale source evidence or prior position lifecycle state; "
                "does not assert profit or funding"
            ),
            "--next-bottleneck",
            result["next_bottleneck"],
            "--result-ref",
            REL + "/canonical_result.json",
            "--result-sha256",
            hashlib.sha256(result_path.read_bytes()).hexdigest().upper(),
            "--evidence-json",
            json.dumps(evidence),
            "--governance-json",
            json.dumps(declarations),
        ],
        cwd=ROOT,
        check=True,
    )
    subprocess.run(command + ["verify", "--task-id", TASK], cwd=ROOT, check=True)


if __name__ == "__main__":
    main()
