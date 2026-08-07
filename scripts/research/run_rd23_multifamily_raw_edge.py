from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from spotbot.research.rd20_p2_minimal_pullback import load_membership  # noqa: E402
from spotbot.research.rd23_multifamily_raw_edge import (  # noqa: E402
    DATA_CUTOFF,
    FAMILIES,
    PERIODS,
    aggregate_raw_edge,
    evaluate_family_horizons,
    family_overlap,
    forward_event_rows,
    prepare_features,
    scan_signals,
    validate_constants,
)

EXPECTED_PARENT = "b17d37416ff617202886629dd8154569a7427ddd"
RD22_REPORT = Path("data/research/rd22_p2_runtime/rd22-p2-discovery-report-v1.json")
RD22_REPORT_SHA256 = "655e456dec5f371574d3c81cffb70d4aee90568fa77c9a60f337be91295549ff"
MEMBERSHIP = Path("data/research/rd18_p3x_a3b_runtime/effective-operational-membership.csv")
DEFAULT_RAW_ROOT = Path("data/raw/rd16b/kucoin")
PROTOCOL = Path("data/research/rd23_p2/rd23-p2-multifamily-raw-edge-protocol-v1.json")
OUTPUT = Path("data/research/rd23_p2_runtime")

OUTPUT_NAMES = (
    "input-and-conformance-audit.json",
    "family-signal-funnel.csv",
    "signal-events.csv",
    "family-overlap-matrix.csv",
    "overlap-summary.json",
    "forward-event-returns.csv",
    "raw-edge-metrics.csv",
    "family-horizon-hard-gates.csv",
    "family-selection.csv",
    "qualified-family-freeze.json",
    "rd23-p2-multifamily-raw-edge-report-v1.json",
)


class RunnerError(RuntimeError):
    pass


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser()
    value.add_argument("--repo-root", type=Path, required=True)
    value.add_argument("--raw-root", type=Path, default=None)
    value.add_argument("--preflight-only", action="store_true")
    value.add_argument("--execute", action="store_true")
    value.add_argument("--expected-freeze-commit", default=None)
    return value


def git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if completed.returncode != 0:
        raise RunnerError(f"git {' '.join(args)} failed: {completed.stderr}")
    return completed.stdout.strip()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise RunnerError(f"JSON object expected: {path}")
    return value


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            value,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
            default=str,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )


def raw_pairs(membership_path: Path) -> list[str]:
    membership = load_membership(membership_path)
    return sorted({pair for snapshot in membership for pair, _rank in snapshot.members})


def verify_inputs(repo: Path, raw_root: Path) -> dict[str, Any]:
    validate_constants()
    head = git(repo, "rev-parse", "HEAD")
    report_path = repo / RD22_REPORT
    if not report_path.is_file():
        raise RunnerError(f"RD22 report missing: {report_path}")
    if sha256(report_path) != RD22_REPORT_SHA256:
        raise RunnerError("RD22 source report hash drifted")
    report = load_json(report_path)
    if report.get("decision") != (
        "RD22_P2_STRUCTURAL_RISK_ON_PULLBACK_REJECTED_CLOSE_TREND_PULLBACK_FAMILY"
    ):
        raise RunnerError("RD22 closure decision drifted")
    if report.get("2024_accessed") is not False:
        raise RunnerError("RD22 report indicates 2024 access")
    if report.get("post_2024_accessed") is not False:
        raise RunnerError("RD22 report indicates post-2024 access")

    membership_path = repo / MEMBERSHIP
    if not membership_path.is_file():
        raise RunnerError(f"membership source missing: {membership_path}")
    pairs = raw_pairs(membership_path)
    if not pairs:
        raise RunnerError("no PIT effective pairs found")
    missing = [pair for pair in pairs if not (raw_root / pair / "1h.parquet").is_file()]
    if missing:
        raise RunnerError(f"raw 1h sources missing: {missing[:20]}")

    return {
        "head": head,
        "source_commit": EXPECTED_PARENT,
        "rd22_report_sha256": RD22_REPORT_SHA256,
        "pair_count": len(pairs),
        "pairs": pairs,
        "family_count": len(FAMILIES),
        "families": list(FAMILIES),
        "data_cutoff_exclusive": DATA_CUTOFF.isoformat(),
        "selection_periods": {
            name: [start.isoformat(), end.isoformat()] for name, (start, end) in PERIODS.items()
        },
        "portfolio_replay_authorized": False,
        "2022_2023_used_for_selection": False,
        "2024_accessed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
    }


def load_features(raw_root: Path, pairs: list[str]) -> dict[str, pd.DataFrame]:
    features: dict[str, pd.DataFrame] = {}
    cutoff = DATA_CUTOFF.to_pydatetime()
    for index, pair in enumerate(pairs, start=1):
        path = raw_root / pair / "1h.parquet"
        raw = pd.read_parquet(
            path,
            engine="pyarrow",
            filters=[("timestamp", "<", cutoff)],
        )
        frame = prepare_features(raw)
        if len(frame) and frame["timestamp"].max() >= DATA_CUTOFF:
            raise RunnerError(f"sealed 2022+ bar loaded: {pair}")
        features[pair] = frame
        print(
            f"RD23_FEATURE_SOURCE={index}/{len(pairs)}:{pair}:{len(frame)}",
            flush=True,
        )
    return features


def manifest(output: Path, decision: str) -> dict[str, Any]:
    files = []
    for name in OUTPUT_NAMES:
        path = output / name
        files.append(
            {
                "path": name,
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
        )
    deterministic = hashlib.sha256(
        "".join(f"{item['path']}:{item['sha256']}\n" for item in files).encode("utf-8")
    ).hexdigest()
    return {
        "schema_version": "rd23-p2-multifamily-output-manifest-v1",
        "stage": "RD23_P2_MULTIFAMILY_RAW_EDGE_TOURNAMENT",
        "decision": decision,
        "deterministic_hash": deterministic,
        "files": files,
        "portfolio_replay_executed": False,
        "position_sizing_executed": False,
        "historical_exit_simulation_executed": False,
        "2022_2023_used_for_selection": False,
        "2024_accessed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
    }


def main() -> int:
    args = parser().parse_args()
    repo = args.repo_root.resolve()
    raw_root = (
        args.raw_root.resolve()
        if args.raw_root is not None
        else (repo / DEFAULT_RAW_ROOT).resolve()
    )
    audit = verify_inputs(repo, raw_root)

    if args.preflight_only:
        print(
            json.dumps(
                {
                    "status": "PASS",
                    "stage": "RD23_MULTIFAMILY_RAW_EDGE_PREFLIGHT",
                    "source_commit": EXPECTED_PARENT,
                    "pair_count": audit["pair_count"],
                    "family_count": audit["family_count"],
                    "portfolio_replay_executed": False,
                    "2022_2023_used_for_selection": False,
                    "2024_accessed": False,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    if not args.execute:
        raise RunnerError("one of --preflight-only or --execute is required")
    if not args.expected_freeze_commit:
        raise RunnerError("--expected-freeze-commit is required for execution")
    head = git(repo, "rev-parse", "HEAD")
    if head != args.expected_freeze_commit:
        raise RunnerError(f"freeze commit mismatch: {head} != {args.expected_freeze_commit}")

    protocol_path = repo / PROTOCOL
    if not protocol_path.is_file():
        raise RunnerError(f"frozen protocol missing: {protocol_path}")
    audit["freeze_commit"] = head
    audit["frozen_protocol_sha256"] = sha256(protocol_path)

    membership = load_membership(repo / MEMBERSHIP)
    pairs = list(audit["pairs"])
    features = load_features(raw_root, pairs)
    events, funnel = scan_signals(membership=membership, features=features)
    if events.empty:
        raise RunnerError("all six setup families produced zero events")
    events["timestamp"] = pd.to_datetime(events["timestamp"], utc=True, errors="raise")
    if bool((events["timestamp"] >= DATA_CUTOFF).any()):
        raise RunnerError("2022+ signal entered tournament")

    forward = forward_event_rows(events=events, features=features)
    if forward.empty:
        raise RunnerError("forward-return table is empty")
    forward["signal_time"] = pd.to_datetime(forward["signal_time"], utc=True, errors="raise")
    forward["entry_time"] = pd.to_datetime(forward["entry_time"], utc=True, errors="raise")
    forward["exit_time"] = pd.to_datetime(forward["exit_time"], utc=True, errors="raise")
    if bool((forward["exit_time"] >= DATA_CUTOFF).any()):
        raise RunnerError("forward outcome crossed 2022 cutoff")

    metrics = aggregate_raw_edge(forward)
    hard_gates, selection = evaluate_family_horizons(metrics)
    overlap_matrix, overlap_summary = family_overlap(events)

    qualified = selection.loc[selection["raw_edge_confirmed"]].copy()
    qualified_families = qualified["family_id"].astype(str).tolist()
    selected_horizons = {
        str(row["family_id"]): int(row["selected_horizon_hours"])
        for row in qualified.to_dict(orient="records")
    }
    if len(qualified_families) >= 2:
        decision = (
            "RD23_P2_MULTIFAMILY_RAW_EDGE_TOURNAMENT_MULTIPLE_FAMILIES_CONFIRMED_"
            "RD24_PARALLEL_MINIMAL_PORTFOLIO_AUTHORIZED"
        )
        next_stage = "RD24_QUALIFIED_FAMILY_MINIMAL_PORTFOLIO_EVALUATION_PARALLEL"
    elif len(qualified_families) == 1:
        decision = (
            "RD23_P2_MULTIFAMILY_RAW_EDGE_TOURNAMENT_ONE_FAMILY_CONFIRMED_"
            "RD24_MINIMAL_PORTFOLIO_AUTHORIZED"
        )
        next_stage = "RD24_QUALIFIED_FAMILY_MINIMAL_PORTFOLIO_EVALUATION_PARALLEL"
    else:
        decision = "RD23_P2_MULTIFAMILY_RAW_EDGE_TOURNAMENT_NO_FAMILY_CONFIRMED"
        next_stage = "RD24_NEW_ALPHA_SOURCE_OR_FEATURE_RESEARCH_REQUIRED"

    output = repo / OUTPUT
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "input-and-conformance-audit.json", audit)
    funnel.to_csv(output / "family-signal-funnel.csv", index=False, lineterminator="\n")
    events.to_csv(output / "signal-events.csv", index=False, lineterminator="\n")
    overlap_matrix.to_csv(
        output / "family-overlap-matrix.csv",
        index=False,
        lineterminator="\n",
    )
    write_json(output / "overlap-summary.json", overlap_summary)
    forward.to_csv(output / "forward-event-returns.csv", index=False, lineterminator="\n")
    metrics.to_csv(output / "raw-edge-metrics.csv", index=False, lineterminator="\n")
    hard_gates.to_csv(
        output / "family-horizon-hard-gates.csv",
        index=False,
        lineterminator="\n",
    )
    selection.to_csv(output / "family-selection.csv", index=False, lineterminator="\n")

    family_freeze = {
        "schema_version": "rd23-qualified-family-freeze-v1",
        "decision": decision,
        "qualified_family_count": len(qualified_families),
        "qualified_families": qualified_families,
        "selected_horizon_hours": selected_horizons,
        "selection_data": "DISCOVERY_2019_2020_PLUS_TEMPORAL_REPLICATION_2021",
        "portfolio_replay_executed": False,
        "2022_2023_used_for_selection": False,
        "2024_accessed": False,
        "post_2024_accessed": False,
    }
    write_json(output / "qualified-family-freeze.json", family_freeze)

    event_counts = {
        family: int((events["family_id"].astype(str) == family).sum()) for family in FAMILIES
    }
    report = {
        "schema_version": "rd23-p2-multifamily-raw-edge-report-v1",
        "stage": "RD23_P2_MULTIFAMILY_RAW_EDGE_TOURNAMENT",
        "decision": decision,
        "next_stage": next_stage,
        "passed": True,
        "family_count": len(FAMILIES),
        "families": list(FAMILIES),
        "event_counts_by_family": event_counts,
        "qualified_family_count": len(qualified_families),
        "qualified_families": qualified_families,
        "selected_horizon_hours": selected_horizons,
        "overlap_summary": overlap_summary,
        "portfolio_replay_executed": False,
        "position_sizing_executed": False,
        "historical_exit_simulation_executed": False,
        "selection_data": "2019_2020_DISCOVERY_AND_2021_TEMPORAL_REPLICATION",
        "2022_2023_used_for_selection": False,
        "2024_accessed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
    }
    write_json(output / "rd23-p2-multifamily-raw-edge-report-v1.json", report)
    write_json(output / "output-manifest.json", manifest(output, decision))

    print(json.dumps(report, indent=2, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RunnerError as exc:
        print(f"RD23_RUNNER_ERROR={exc}", file=sys.stderr)
        raise SystemExit(2) from exc
