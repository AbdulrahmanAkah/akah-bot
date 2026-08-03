from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = ROOT / "data/research/rd18_p3x_a1_runtime"
RUNNER_RELATIVE = Path("scripts/research/run_rd18_p3x_a1.py")
PLAN_NAME = "full-c2-hourly-acquisition-plan.csv"
DOWNLOAD_ACTION = "DOWNLOAD_OR_BACKFILL_CURRENT_API"
TERMINAL_ACTIONS = frozenset(
    {
        "READY_LOCAL",
        "HISTORICAL_MARKET_SOURCE_REQUIRED",
        "CORPORATE_ACTION_POLICY_REQUIRED",
    }
)


class ResumeError(RuntimeError):
    """Raised when the resumable acquisition session cannot proceed safely."""


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description=(
            "Resume all currently obtainable RD18-P3X-A1 KuCoin Spot pairs in "
            "bounded batches without retrying a pair twice in the same session."
        )
    )
    result.add_argument("--repo-root", type=Path, default=ROOT)
    result.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    result.add_argument("--python", default=sys.executable)
    result.add_argument("--batch-size", type=int, default=50)
    result.add_argument("--retries", type=int, default=3)
    result.add_argument(
        "--max-batches",
        type=int,
        default=0,
        help="Zero means no session batch limit.",
    )
    result.add_argument(
        "--execute-network",
        action="store_true",
        help="Required acknowledgement for public KuCoin Spot requests.",
    )
    return result


def _now() -> str:
    return datetime.now(tz=UTC).isoformat()


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _read_plan(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise ResumeError(f"acquisition plan is missing: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = [dict(row) for row in csv.DictReader(handle)]
    if len(rows) != 364:
        raise ResumeError(f"expected 364 C2 plan rows, found {len(rows)}")
    pairs = [str(row.get("pair", "")) for row in rows]
    if not all(pairs) or len(pairs) != len(set(pairs)):
        raise ResumeError("acquisition plan pairs are empty or duplicated")
    return rows


def _action_counts(rows: list[dict[str, str]]) -> dict[str, int]:
    return dict(sorted(Counter(str(row.get("action", "")) for row in rows).items()))


def _run_command(
    command: list[str],
    *,
    cwd: Path,
    log_path: Path,
) -> dict[str, Any]:
    completed = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )
    record: dict[str, Any] = {
        "command": command,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(
        json.dumps(record, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    if completed.returncode != 0:
        raise ResumeError(f"command failed with exit code {completed.returncode}; see {log_path}")
    return record


def _parse_stdout_json(record: dict[str, Any], *, source: Path) -> dict[str, Any]:
    raw = str(record.get("stdout", ""))
    try:
        payload: object = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ResumeError(f"runner stdout is not JSON; see {source}") from exc
    if not isinstance(payload, dict):
        raise ResumeError(f"runner stdout JSON is not an object; see {source}")
    return dict(payload)


def _plan_command(
    *,
    python: str,
    runner: Path,
    repo_root: Path,
    output_dir: Path,
) -> list[str]:
    return [
        python,
        str(runner),
        "--repo-root",
        str(repo_root),
        "--output-dir",
        str(output_dir),
        "plan",
        "--probe-current-markets",
    ]


def _download_command(
    *,
    python: str,
    runner: Path,
    repo_root: Path,
    output_dir: Path,
    pairs: list[str],
    retries: int,
) -> list[str]:
    command = [
        python,
        str(runner),
        "--repo-root",
        str(repo_root),
        "--output-dir",
        str(output_dir),
        "download",
        "--max-pairs",
        str(len(pairs)),
        "--retries",
        str(retries),
        "--execute-network",
    ]
    for pair in pairs:
        command.extend(("--pair", pair))
    return command


def _eligible_pairs(
    rows: list[dict[str, str]],
    *,
    attempted: set[str],
) -> list[str]:
    return [
        str(row["pair"])
        for row in rows
        if row.get("action") == DOWNLOAD_ACTION and str(row["pair"]) not in attempted
    ]


def _validate_batch_payload(payload: dict[str, Any], selected: list[str]) -> list[dict[str, Any]]:
    if payload.get("schema_version") != "rd18-p3x-a1-acquisition-batch-v1":
        raise ResumeError("unexpected acquisition batch schema")
    raw_results = payload.get("results")
    if not isinstance(raw_results, list):
        raise ResumeError("acquisition batch results are missing")
    results: list[dict[str, Any]] = []
    for raw in raw_results:
        if not isinstance(raw, dict):
            raise ResumeError("acquisition batch contains a non-object result")
        results.append(dict(raw))
    result_pairs = [str(row.get("pair", "")) for row in results]
    if len(results) != len(selected) or set(result_pairs) != set(selected):
        raise ResumeError(
            "acquisition runner result pairs differ from the explicitly selected batch"
        )
    return results


def main() -> int:
    args = parser().parse_args()
    if not args.execute_network:
        raise SystemExit("resume requires --execute-network")
    if args.batch_size <= 0:
        raise SystemExit("--batch-size must be positive")
    if args.retries <= 0:
        raise SystemExit("--retries must be positive")
    if args.max_batches < 0:
        raise SystemExit("--max-batches cannot be negative")

    repo_root = args.repo_root.resolve()
    output_dir = args.output_dir.resolve()
    runner = repo_root / RUNNER_RELATIVE
    if not runner.is_file():
        raise SystemExit(f"runner is missing: {runner}")

    stamp = datetime.now(tz=UTC).strftime("%Y%m%d-%H%M%S")
    session_dir = output_dir / "logs" / f"resume-session-{stamp}"
    session_dir.mkdir(parents=True, exist_ok=False)
    plan_path = output_dir / PLAN_NAME

    print(f"SESSION_DIR={session_dir}", flush=True)
    initial_plan_log = session_dir / "plan-initial.log.json"
    initial_plan_record = _run_command(
        _plan_command(
            python=str(args.python),
            runner=runner,
            repo_root=repo_root,
            output_dir=output_dir,
        ),
        cwd=repo_root,
        log_path=initial_plan_log,
    )
    _parse_stdout_json(initial_plan_record, source=initial_plan_log)
    plan_rows = _read_plan(plan_path)
    initial_counts = _action_counts(plan_rows)

    attempted: set[str] = set()
    batch_records: list[dict[str, Any]] = []
    result_state_counts: Counter[str] = Counter()
    failed_pairs: list[dict[str, str]] = []
    batch_index = 0

    while True:
        available = _eligible_pairs(plan_rows, attempted=attempted)
        if not available:
            break
        if args.max_batches and batch_index >= args.max_batches:
            break

        batch_index += 1
        selected = available[: args.batch_size]
        print(
            f"BATCH {batch_index}: selected={len(selected)} first={selected[0]} "
            f"last={selected[-1]}",
            flush=True,
        )
        batch_log = session_dir / f"batch-{batch_index:03d}.log.json"
        batch_record = _run_command(
            _download_command(
                python=str(args.python),
                runner=runner,
                repo_root=repo_root,
                output_dir=output_dir,
                pairs=selected,
                retries=args.retries,
            ),
            cwd=repo_root,
            log_path=batch_log,
        )
        payload = _parse_stdout_json(batch_record, source=batch_log)
        results = _validate_batch_payload(payload, selected)
        attempted.update(selected)

        states = Counter(str(row.get("state", "")) for row in results)
        result_state_counts.update(states)
        for row in results:
            state = str(row.get("state", ""))
            if state == "FAILED_RETRYABLE":
                failed_pairs.append(
                    {
                        "pair": str(row.get("pair", "")),
                        "error": str(row.get("error", "")),
                    }
                )
        batch_summary = {
            "batch_index": batch_index,
            "selected_pairs": selected,
            "state_counts": dict(sorted(states.items())),
            "result_file": str(session_dir / f"batch-{batch_index:03d}.result.json"),
            "log_file": str(batch_log),
        }
        _write_json(Path(str(batch_summary["result_file"])), payload)
        batch_records.append(batch_summary)
        print(
            f"BATCH {batch_index} COMPLETE: "
            + ", ".join(f"{key}={value}" for key, value in sorted(states.items())),
            flush=True,
        )

        refresh_log = session_dir / f"plan-after-batch-{batch_index:03d}.log.json"
        refresh_record = _run_command(
            _plan_command(
                python=str(args.python),
                runner=runner,
                repo_root=repo_root,
                output_dir=output_dir,
            ),
            cwd=repo_root,
            log_path=refresh_log,
        )
        _parse_stdout_json(refresh_record, source=refresh_log)
        plan_rows = _read_plan(plan_path)

    final_counts = _action_counts(plan_rows)
    remaining_download_pairs = [
        str(row["pair"]) for row in plan_rows if row.get("action") == DOWNLOAD_ACTION
    ]
    unattempted_download_pairs = [
        pair for pair in remaining_download_pairs if pair not in attempted
    ]
    nonterminal_actions = sorted(
        action
        for action in final_counts
        if action not in TERMINAL_ACTIONS and action != DOWNLOAD_ACTION
    )
    summary = {
        "schema_version": "rd18-p3x-a1-resume-session-v1",
        "started_at": stamp,
        "finished_at": _now(),
        "repo_root": str(repo_root),
        "output_dir": str(output_dir),
        "session_dir": str(session_dir),
        "batch_size": args.batch_size,
        "retries_per_pair": args.retries,
        "max_batches": args.max_batches,
        "batches_executed": batch_index,
        "pairs_attempted_once_this_session": len(attempted),
        "attempted_pairs": sorted(attempted),
        "batch_result_state_counts": dict(sorted(result_state_counts.items())),
        "failed_retryable_pairs": failed_pairs,
        "initial_action_counts": initial_counts,
        "final_action_counts": final_counts,
        "remaining_download_pairs": remaining_download_pairs,
        "unattempted_download_pairs": unattempted_download_pairs,
        "other_nonterminal_actions": nonterminal_actions,
        "session_exhausted_current_candidates": not unattempted_download_pairs,
        "attention_required": bool(failed_pairs or remaining_download_pairs or nonterminal_actions),
        "authorizations": {
            "public_kucoin_spot_network": True,
            "post_2024_access": False,
            "strategy_replay": False,
            "return_calculation": False,
            "broad_candidate_generation": False,
            "production": False,
        },
        "batches": batch_records,
    }
    summary_path = session_dir / "resume-summary.json"
    _write_json(summary_path, summary)
    print(json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=False), flush=True)
    print(f"SUMMARY_JSON={summary_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
