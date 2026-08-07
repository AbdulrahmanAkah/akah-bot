from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from spotbot.research.rd20_p3_core_edge import (  # noqa: E402
    contribution_diagnostics,
    fixed_path_pf1_break_even_multiplier,
    performance_metrics,
    prepare_economic_frame,
)
from spotbot.research.rd21_horizon_pullback import (  # noqa: E402
    CANDIDATE_FAMILY_ID,
    COST_MULTIPLIERS,
    DISCOVERY_CUTOFF,
    DISCOVERY_START,
    HORIZON_HOURS,
    replay_fixed_horizon,
    selection_table,
    validate_constants,
    variant_gate_rows,
)

EXPECTED_SOURCE_COMMIT = "24f3c8732e0c7bb968fe587753545694bae092d0"
P2A_EVENTS = Path("data/research/rd20_p2a_r1_runtime/signal-events.csv")
P3_REPORT = Path("data/research/rd20_p3_runtime/rd20-p3-core-edge-report-v1.json")
P3_RUN_METRICS = Path("data/research/rd20_p3_runtime/run-metrics.csv")
P3_FORWARD = Path("data/research/rd20_p3_runtime/forward-horizon-diagnostics.csv")
P3_TRADES = Path("data/research/rd20_p3_runtime/trade-ledger.csv")
P3_BREAK_EVEN = Path("data/research/rd20_p3_runtime/break-even-cost-multiplier.csv")
P3_DIAGNOSIS = Path("data/research/rd21_p0_runtime/rd20-p3-failure-diagnosis-v1.json")
PROTOCOL = Path("data/research/rd21_p2/rd21-p2-horizon-discovery-protocol-v1.json")
OUTPUT = Path("data/research/rd21_p2_runtime")
DEFAULT_RAW_ROOT = Path("data/raw/rd16b/kucoin")

EXPECTED_HASHES = {
    P2A_EVENTS: "d501c80b4a0baaf42f543df793b5485d16eaf586cdb493ebe01362536d6cde13",
    P3_REPORT: "812f93d222e37575ad2a9df5b1ca963f69b0b8dd86ba8967bdc726fb390689c5",
    P3_RUN_METRICS: "1cb6121b110001f0937a7ffbb65ed9d9aa6321e810232065c8e7a67e1178800a",
    P3_FORWARD: "38db97a62cca4dc74baa115682fca13d2376e88ac35db5aaa70272cdc5e19ccd",
    P3_TRADES: "bbdc943b237b49af8f5ca5520f101da10bd12e4d699d6b4a845341f99d6d31d2",
    P3_BREAK_EVEN: "89f5612812108d267b4803895b49d2259bd1fd5be77dc7d76e169903b5a6a32c",
}

OUTPUT_NAMES = (
    "input-and-conformance-audit.json",
    "variant-metrics.csv",
    "year-metrics.csv",
    "routing-summary.csv",
    "trade-ledger.csv",
    "daily-equity.csv",
    "concentration-diagnostics.csv",
    "leave-one-asset-out.csv",
    "leave-one-year-out.csv",
    "break-even-cost-multiplier.csv",
    "variant-hard-gates.csv",
    "selection-ranking.csv",
    "finalist-freeze.json",
    "rd21-p2-discovery-report-v1.json",
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
    import subprocess

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


def write_csv(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, encoding="utf-8", lineterminator="\n")


def verify_inputs(repo: Path, *, expected_freeze_commit: str | None) -> dict[str, Any]:
    validate_constants()
    head = git(repo, "rev-parse", "HEAD")
    if expected_freeze_commit is not None and head != expected_freeze_commit:
        raise RunnerError(
            f"freeze commit mismatch: expected={expected_freeze_commit}, observed={head}"
        )
    for relative, expected in EXPECTED_HASHES.items():
        path = repo / relative
        if not path.is_file():
            raise RunnerError(f"required frozen input missing: {path}")
        actual = sha256(path)
        if actual != expected:
            raise RunnerError(f"input hash drift: {relative}: {actual} != {expected}")

    report = load_json(repo / P3_REPORT)
    if report.get("decision") != "RD20_P3_CORE_EDGE_REJECTED_NO_ADVANCEMENT":
        raise RunnerError("RD20 P3 rejection decision drifted")
    if report.get("p4_authorized") is not False:
        raise RunnerError("RD20 P3 unexpectedly authorized P4")
    if report.get("2024_accessed") is not False:
        raise RunnerError("RD20 P3 accessed 2024")

    diagnosis = load_json(repo / P3_DIAGNOSIS)
    if diagnosis.get("decision") != "RD21_P0_HORIZON_COST_CHURN_DIAGNOSIS_COMPLETE":
        raise RunnerError("RD21 P0 diagnosis missing or drifted")

    protocol = load_json(repo / PROTOCOL)
    if protocol.get("starting_commit") != EXPECTED_SOURCE_COMMIT:
        raise RunnerError("RD21 protocol starting commit drifted")
    if protocol.get("variant_horizons_hours") != [24, 72, 168]:
        raise RunnerError("RD21 horizon matrix drifted")
    if protocol.get("selection_data") != "DISCOVERY_2019_2021_ONLY":
        raise RunnerError("RD21 selection-data contract drifted")
    if protocol.get("prohibitions", {}).get("access_2022_2023_for_variant_selection") is not False:
        raise RunnerError("RD21 protocol incorrectly authorizes 2022/2023 selection access")
    if protocol.get("prohibitions", {}).get("access_2024") is not False:
        raise RunnerError("RD21 protocol incorrectly authorizes 2024")

    return {
        "source_commit": EXPECTED_SOURCE_COMMIT,
        "freeze_commit": head,
        "signal_events_sha256": EXPECTED_HASHES[P2A_EVENTS],
        "p3_report_sha256": EXPECTED_HASHES[P3_REPORT],
        "p3_run_metrics_sha256": EXPECTED_HASHES[P3_RUN_METRICS],
        "p3_forward_sha256": EXPECTED_HASHES[P3_FORWARD],
        "p3_trade_ledger_sha256": EXPECTED_HASHES[P3_TRADES],
        "p3_break_even_sha256": EXPECTED_HASHES[P3_BREAK_EVEN],
        "p3_diagnosis_sha256": sha256(repo / P3_DIAGNOSIS),
        "protocol_sha256": sha256(repo / PROTOCOL),
        "2022_2023_used_for_variant_selection": False,
        "2024_accessed": False,
    }


def load_discovery_events(repo: Path) -> pd.DataFrame:
    events = pd.read_csv(repo / P2A_EVENTS, low_memory=False)
    required = {
        "universe_id",
        "partition_id",
        "timestamp",
        "candidate_rank",
        "pair",
        "membership_rank",
        "score",
        "initial_stop_reference",
    }
    missing = sorted(required.difference(events.columns))
    if missing:
        raise RunnerError(f"signal event columns missing: {missing}")
    events = events.loc[events["partition_id"].astype(str) == "DISCOVERY_2019_2021"].copy()
    events["timestamp"] = pd.to_datetime(events["timestamp"], utc=True, errors="raise")
    if bool((events["timestamp"] >= DISCOVERY_CUTOFF).any()):
        raise RunnerError("discovery event selection crossed into 2022")
    if bool((events["timestamp"] < DISCOVERY_START).any()):
        raise RunnerError("discovery event selection predates 2019")
    if events.empty:
        raise RunnerError("discovery event set is empty")
    return events


def load_features(
    raw_root: Path,
    pairs: list[str],
) -> dict[str, pd.DataFrame]:
    features: dict[str, pd.DataFrame] = {}
    cutoff = DISCOVERY_CUTOFF.to_pydatetime()
    for index, pair in enumerate(pairs, start=1):
        path = raw_root / pair / "1h.parquet"
        if not path.is_file():
            raise RunnerError(f"raw source missing: {path}")
        raw = pd.read_parquet(
            path,
            engine="pyarrow",
            filters=[("timestamp", "<", cutoff)],
        )
        featured = prepare_economic_frame(raw)
        if len(featured) and featured["timestamp"].max() >= DISCOVERY_CUTOFF:
            raise RunnerError(f"2022+ raw row loaded during discovery: {pair}")
        features[pair] = featured
        print(
            f"RD21_DISCOVERY_FEATURE_SOURCE={index}/{len(pairs)}:{pair}:{len(featured)}",
            flush=True,
        )
    return features


def output_manifest(output: Path, decision: str) -> dict[str, Any]:
    files = []
    for name in OUTPUT_NAMES:
        path = output / name
        if not path.is_file():
            raise RunnerError(f"output missing before manifest: {path}")
        files.append(
            {
                "path": name,
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
        )
    digest = hashlib.sha256()
    for row in sorted(files, key=lambda item: str(item["path"])):
        digest.update(str(row["path"]).encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(row["sha256"]).encode("ascii"))
        digest.update(b"\n")
    return {
        "schema_version": "rd21-p2-horizon-discovery-output-manifest-v1",
        "candidate_family_id": CANDIDATE_FAMILY_ID,
        "decision": decision,
        "files": files,
        "deterministic_hash": digest.hexdigest(),
        "selection_data": "DISCOVERY_2019_2021_ONLY",
        "2022_2023_used_for_variant_selection": False,
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
    audit = verify_inputs(
        repo,
        expected_freeze_commit=args.expected_freeze_commit,
    )
    events = load_discovery_events(repo)
    pairs = sorted(events["pair"].astype(str).unique().tolist())

    if args.preflight_only:
        missing = [pair for pair in pairs if not (raw_root / pair / "1h.parquet").is_file()]
        if missing:
            raise RunnerError(f"discovery raw sources missing: {missing[:20]}")
        print(
            json.dumps(
                {
                    "status": "PASS",
                    "candidate_family_id": CANDIDATE_FAMILY_ID,
                    "variant_horizons_hours": list(HORIZON_HOURS),
                    "discovery_event_count": len(events),
                    "discovery_pair_count": len(pairs),
                    "selection_data": "DISCOVERY_2019_2021_ONLY",
                    "2022_2023_used_for_variant_selection": False,
                    "2024_accessed": False,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    if not args.execute:
        raise RunnerError("use --preflight-only or --execute")
    if args.expected_freeze_commit is None:
        raise RunnerError("--expected-freeze-commit is required for discovery execution")

    output = repo / OUTPUT
    if output.exists():
        raise RunnerError(f"refusing to overwrite discovery output: {output}")
    output.mkdir(parents=True, exist_ok=False)

    features = load_features(raw_root, pairs)

    metric_rows: list[dict[str, Any]] = []
    year_parts: list[pd.DataFrame] = []
    route_rows: list[dict[str, Any]] = []
    trade_parts: list[pd.DataFrame] = []
    equity_parts: list[pd.DataFrame] = []
    concentration_rows: list[dict[str, Any]] = []
    loao_parts: list[pd.DataFrame] = []
    loyo_parts: list[pd.DataFrame] = []
    break_even_rows: list[dict[str, Any]] = []

    base_trade_paths: dict[tuple[int, str], pd.DataFrame] = {}

    for horizon in HORIZON_HOURS:
        for universe in ("C2", "D2", "E2"):
            for multiplier in COST_MULTIPLIERS:
                trades, equity, route = replay_fixed_horizon(
                    universe_id=universe,
                    cost_multiplier=multiplier,
                    horizon_hours=horizon,
                    events=events,
                    features=features,
                )
                metrics, years = performance_metrics(trades, equity, route)
                metrics["horizon_hours"] = horizon
                metric_rows.append(metrics)

                years = years.copy()
                years["run_id"] = route["run_id"]
                years["universe_id"] = universe
                years["horizon_hours"] = horizon
                years["cost_multiplier"] = multiplier
                year_parts.append(years)

                route_rows.append(dict(route))
                trade_parts.append(trades.assign(horizon_hours=horizon))
                equity_parts.append(equity)

                diag, loao, loyo = contribution_diagnostics(trades)
                concentration_rows.append(
                    {
                        **diag,
                        "run_id": route["run_id"],
                        "universe_id": universe,
                        "horizon_hours": horizon,
                        "cost_multiplier": multiplier,
                    }
                )
                if len(loao):
                    loao = loao.copy()
                    loao["run_id"] = route["run_id"]
                    loao["universe_id"] = universe
                    loao["horizon_hours"] = horizon
                    loao["cost_multiplier"] = multiplier
                    loao_parts.append(loao)
                if len(loyo):
                    loyo = loyo.copy()
                    loyo["run_id"] = route["run_id"]
                    loyo["universe_id"] = universe
                    loyo["horizon_hours"] = horizon
                    loyo["cost_multiplier"] = multiplier
                    loyo_parts.append(loyo)

                if multiplier == 1.0:
                    base_trade_paths[(horizon, universe)] = trades.copy()

    metrics = pd.DataFrame.from_records(metric_rows)
    years = pd.concat(year_parts, ignore_index=True)
    routes = pd.DataFrame.from_records(route_rows)
    all_trades = pd.concat(trade_parts, ignore_index=True)
    all_equity = pd.concat(equity_parts, ignore_index=True)
    concentration = pd.DataFrame.from_records(concentration_rows)
    loao = pd.concat(loao_parts, ignore_index=True) if loao_parts else pd.DataFrame()
    loyo = pd.concat(loyo_parts, ignore_index=True) if loyo_parts else pd.DataFrame()

    for horizon in HORIZON_HOURS:
        for universe in ("C2", "D2", "E2"):
            base_path = base_trade_paths[(horizon, universe)]
            break_even_rows.append(
                {
                    "horizon_hours": horizon,
                    "universe_id": universe,
                    "pf1_break_even_cost_multiplier_fixed_base_path": (
                        fixed_path_pf1_break_even_multiplier(base_path)
                    ),
                    "method": ("BASE_ROUTED_QUANTITIES_AND_FILLS_FIXED_COST_SCALED_UNTIL_PF_1"),
                }
            )
    break_even = pd.DataFrame.from_records(break_even_rows)

    gate_rows: list[dict[str, Any]] = []
    horizon_pass: dict[int, bool] = {}
    for horizon in HORIZON_HOURS:
        rows, passed = variant_gate_rows(
            horizon_hours=horizon,
            metrics=metrics,
            break_even=break_even,
            concentration=concentration,
        )
        gate_rows.extend(rows)
        horizon_pass[horizon] = passed
    gates = pd.DataFrame.from_records(gate_rows)
    ranking = selection_table(metrics, horizon_pass)

    passing = ranking.loc[ranking["hard_gates_passed"]].copy()
    if passing.empty:
        selected_horizon = None
        decision = "RD21_P2_HORIZON_DISCOVERY_CLOSED_NO_FINALIST"
        next_stage = "RD21_NEW_CORE_SIGNAL_OR_REGIME_HYPOTHESIS_REQUIRED"
    else:
        selected_horizon = int(passing.iloc[0]["horizon_hours"])
        decision = "RD21_P2_HORIZON_DISCOVERY_FINALIST_SELECTED"
        next_stage = "RD21_P3_EXPOSED_2022_2023_ROBUSTNESS_AFTER_FINALIST_FREEZE"

    finalist = {
        "schema_version": "rd21-p2-finalist-freeze-v1",
        "candidate_family_id": CANDIDATE_FAMILY_ID,
        "selected_horizon_hours": selected_horizon,
        "selection_rule": (
            "PASS_ALL_HARD_GATES_THEN_MAXIMIZE_WORST_UNIVERSE_2X_NET_RETURN_"
            "THEN_PF_THEN_MINIMIZE_DRAWDOWN_THEN_TURNOVER"
        ),
        "signal_ledger_sha256": EXPECTED_HASHES[P2A_EVENTS],
        "signal_logic_changed": False,
        "entry_logic_changed": False,
        "initial_stop_changed": False,
        "sizing_changed": False,
        "capacity_changed": False,
        "cost_model_changed": False,
        "only_economic_dimension_screened": "FIXED_HORIZON_EXIT_HOURS",
        "variant_horizons_hours": list(HORIZON_HOURS),
        "selection_data": "DISCOVERY_2019_2021_ONLY",
        "2022_2023_used_for_variant_selection": False,
        "2024_accessed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
        "decision": decision,
        "next_stage": next_stage,
    }

    report = {
        "schema_version": "rd21-p2-horizon-discovery-report-v1",
        "stage": "RD21_P2_HORIZON_ALIGNED_PULLBACK_DISCOVERY",
        "candidate_family_id": CANDIDATE_FAMILY_ID,
        "decision": decision,
        "selected_horizon_hours": selected_horizon,
        "next_stage": next_stage,
        "variant_count": len(HORIZON_HOURS),
        "discovery_event_count": len(events),
        "discovery_pair_count": len(pairs),
        "hard_gate_pass_by_horizon": {str(k): bool(v) for k, v in horizon_pass.items()},
        "selection_data": "DISCOVERY_2019_2021_ONLY",
        "2022_2023_used_for_variant_selection": False,
        "2024_accessed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
        "parameter_search_dimensions": 1,
        "screened_dimension": "FIXED_HORIZON_EXIT_HOURS",
        "screened_values_hours": list(HORIZON_HOURS),
        "market_gate_added": False,
        "score_logic_changed": False,
        "adaptive_exit_added": False,
        "partial_selling_added": False,
        "capital_arbitration_added": False,
    }

    write_json(output / "input-and-conformance-audit.json", audit)
    write_csv(output / "variant-metrics.csv", metrics)
    write_csv(output / "year-metrics.csv", years)
    write_csv(output / "routing-summary.csv", routes)
    write_csv(output / "trade-ledger.csv", all_trades)
    write_csv(output / "daily-equity.csv", all_equity)
    write_csv(output / "concentration-diagnostics.csv", concentration)
    write_csv(output / "leave-one-asset-out.csv", loao)
    write_csv(output / "leave-one-year-out.csv", loyo)
    write_csv(output / "break-even-cost-multiplier.csv", break_even)
    write_csv(output / "variant-hard-gates.csv", gates)
    write_csv(output / "selection-ranking.csv", ranking)
    write_json(output / "finalist-freeze.json", finalist)
    write_json(output / "rd21-p2-discovery-report-v1.json", report)
    write_json(output / "output-manifest.json", output_manifest(output, decision))

    print(json.dumps(report, indent=2, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RunnerError as exc:
        print(f"RD21_RUNNER_ERROR={exc}", file=sys.stderr)
        raise SystemExit(2) from exc
