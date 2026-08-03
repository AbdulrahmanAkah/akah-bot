from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/research/resume_rd18_p3x_a1_acquisition.py"


FAKE_RUNNER = r"""from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--repo-root", type=Path)
parser.add_argument("--output-dir", type=Path)
subparsers = parser.add_subparsers(dest="mode", required=True)
plan = subparsers.add_parser("plan")
plan.add_argument("--probe-current-markets", action="store_true")
download = subparsers.add_parser("download")
download.add_argument("--max-pairs", type=int)
download.add_argument("--retries", type=int)
download.add_argument("--execute-network", action="store_true")
download.add_argument("--pair", action="append", default=[])
args = parser.parse_args()
output = args.output_dir
output.mkdir(parents=True, exist_ok=True)
state_path = output / "fake-state.json"
completed = (
    set(json.loads(state_path.read_text()).get("completed", []))
    if state_path.exists()
    else set()
)

if args.mode == "download":
    results = []
    for pair in args.pair:
        if pair == "T007-USDT":
            results.append({"pair": pair, "state": "FAILED_RETRYABLE", "error": "fake"})
        else:
            completed.add(pair)
            results.append({"pair": pair, "state": "COMPLETE"})
    state_path.write_text(json.dumps({"completed": sorted(completed)}), encoding="utf-8")
    print(json.dumps({
        "schema_version": "rd18-p3x-a1-acquisition-batch-v1",
        "selected_pairs": len(args.pair),
        "results": results,
        "network_requests": "PUBLIC_KUCOIN_CCXT_ONLY",
        "post_2024_access": False,
    }))
else:
    plan_path = output / "full-c2-hourly-acquisition-plan.csv"
    with plan_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["pair", "action"])
        writer.writeheader()
        for index in range(364):
            pair = f"T{index:03d}-USDT"
            if pair in completed:
                action = "READY_LOCAL"
            elif index < 12:
                action = "DOWNLOAD_OR_BACKFILL_CURRENT_API"
            else:
                action = "HISTORICAL_MARKET_SOURCE_REQUIRED"
            writer.writerow({"pair": pair, "action": action})
    print(json.dumps({"schema_version": "fake-plan"}))
"""


def test_resume_attempts_each_current_candidate_once(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    runner = repo / "scripts/research/run_rd18_p3x_a1.py"
    runner.parent.mkdir(parents=True)
    runner.write_text(FAKE_RUNNER, encoding="utf-8")
    output = repo / "data/research/rd18_p3x_a1_runtime"

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--repo-root",
            str(repo),
            "--output-dir",
            str(output),
            "--python",
            sys.executable,
            "--batch-size",
            "5",
            "--retries",
            "2",
            "--execute-network",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    summaries = list((output / "logs").glob("resume-session-*/resume-summary.json"))
    assert len(summaries) == 1
    summary = json.loads(summaries[0].read_text(encoding="utf-8"))
    assert summary["batches_executed"] == 3
    assert summary["pairs_attempted_once_this_session"] == 12
    assert summary["batch_result_state_counts"] == {
        "COMPLETE": 11,
        "FAILED_RETRYABLE": 1,
    }
    assert summary["final_action_counts"] == {
        "DOWNLOAD_OR_BACKFILL_CURRENT_API": 1,
        "HISTORICAL_MARKET_SOURCE_REQUIRED": 352,
        "READY_LOCAL": 11,
    }
    assert summary["unattempted_download_pairs"] == []
    assert summary["failed_retryable_pairs"] == [{"error": "fake", "pair": "T007-USDT"}]
    assert summary["authorizations"]["post_2024_access"] is False
    assert summary["authorizations"]["strategy_replay"] is False
    assert summary["authorizations"]["return_calculation"] is False


def test_resume_requires_explicit_network_acknowledgement(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    runner = repo / "scripts/research/run_rd18_p3x_a1.py"
    runner.parent.mkdir(parents=True)
    runner.write_text("raise SystemExit(99)\n", encoding="utf-8")

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--repo-root",
            str(repo),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode != 0
    assert "resume requires --execute-network" in completed.stderr
