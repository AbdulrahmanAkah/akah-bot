"""Complete/verify focused repair without market or reviewer certification."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from runpy import run_path

ROOT = Path(__file__).resolve().parents[3]
REL = "governance/causal_lineage_closure_v12"
TASK = "AKAH_V12_H3_PARENT_SEAL_AND_HARMONIC_COMPLETION_LINEAGE_CLOSURE"


def main():
    utility = run_path(str(ROOT / "scripts/research/integration_v12/certify.py"))
    sha = utility["sha"]
    path = ROOT / REL / "canonical_result.json"
    result = json.loads(path.read_text())
    assert result["technical_status"] == "PASS" and result["review_findings_closed"]
    assert not result["ready_for_gate3_replay"] and not result["independent_V12_review"]
    for item in result["artifact_bindings"]:
        assert sha(ROOT / item["path"]) == item["sha256"]
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
            "Confirmed V11 review F4 H3 omitted exact parent seals and F5 Type-II omitted actual "
            "Type-I closure receipt, reproduced pre-BEGIN. V12 live dependencies repair both; "
            "494 local and 494 isolated exported synthetic tests pass, 29 new; V4-V11 unchanged. "
            "No new independent V12 acceptance, historical producer/reserve, "
            "economics or funding claimed.",
            "--north-star-effect",
            "Preserves exact causal permission through producer, seal, bind, "
            "preview and actual admission without trading-rule changes or outcome fitting.",
            "--next-bottleneck",
            result["next_bottleneck"],
            "--result-ref",
            REL + "/canonical_result.json",
            "--result-sha256",
            sha(path),
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
