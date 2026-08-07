from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from spotbot.research.rd20_p2_minimal_pullback import (  # noqa: E402
    DATA_CUTOFF,
    PARTITIONS,
)
from spotbot.research.rd20_p3_core_edge import (  # noqa: E402
    CANDIDATE_ID,
    COST_MULTIPLIERS,
    INITIAL_EQUITY,
    aggregate_forward_horizons,
    contribution_diagnostics,
    fixed_path_pf1_break_even_multiplier,
    forward_horizon_rows,
    hard_gate_evaluation,
    performance_metrics,
    prepare_economic_frame,
    replay_universe,
    validate_protocol_constants,
    validate_signal_event_parity,
)

EXPECTED_PARENT = "2d35b39497916d63c4026f367b2257710a3e4d0c"
P2A_R1_OUTPUT = Path("data/research/rd20_p2a_r1_runtime")
SIGNAL_EVENTS = P2A_R1_OUTPUT / "signal-events.csv"
FROZEN_CANDIDATE = P2A_R1_OUTPUT / "frozen-candidate-contract.json"
PRE_PNL_FUNNEL = P2A_R1_OUTPUT / "pre-pnl-signal-funnel.csv"
P2A_R1_REPORT = P2A_R1_OUTPUT / "rd20-p2a-r1-pre-pnl-report-v1.json"
P3_PROTOCOL = Path("data/research/rd20_p3/rd20-p3-core-edge-economic-protocol-v1.json")
OUTPUT = Path("data/research/rd20_p3_runtime")
DEFAULT_RAW_ROOT = Path("data/raw/rd16b/kucoin")

EXPECTED_INPUT_HASHES = {
    SIGNAL_EVENTS: "d501c80b4a0baaf42f543df793b5485d16eaf586cdb493ebe01362536d6cde13",
    FROZEN_CANDIDATE: "4991ec6db3a63f7af73471a86d4f45c7121af084429af2181a01ced6a520bb39",
    PRE_PNL_FUNNEL: "678d9cf04c8d804d73c5ac6781c9e60142f48302eef8979f82e486624071879d",
    P2A_R1_REPORT: "06e7ecf483f587edb15588908fe5a58bb13f8e95ef399dcf9221bb7d8fee789d",
}

OUTPUT_NAMES = (
    "input-and-conformance-audit.json",
    "forward-horizon-diagnostics.csv",
    "run-metrics.csv",
    "year-metrics.csv",
    "partition-metrics.csv",
    "routing-summary.csv",
    "trade-ledger.csv",
    "daily-equity.csv",
    "concentration-diagnostics.csv",
    "leave-one-asset-out.csv",
    "leave-one-year-out.csv",
    "break-even-cost-multiplier.csv",
    "hard-gate-evaluation.csv",
    "rd20-p3-core-edge-report-v1.json",
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


def verify_inputs(repo: Path) -> dict[str, Any]:
    validate_protocol_constants()
    for relative, expected in EXPECTED_INPUT_HASHES.items():
        path = repo / relative
        if not path.is_file():
            raise RunnerError(f"frozen P3 input missing: {path}")
        actual = sha256(path)
        if actual != expected:
            raise RunnerError(f"frozen P3 input hash drift: {relative}: {actual} != {expected}")

    report = load_json(repo / P2A_R1_REPORT)
    if report.get("decision") != "RD20_P2A_R1_PRE_PNL_SIGNAL_AUDIT_COMPLETE_P3_AUTHORIZED":
        raise RunnerError("P2A-R1 does not authorize P3")
    if report.get("p3_economic_evaluation_authorized") is not True:
        raise RunnerError("P2A-R1 P3 authorization flag is false")
    if report.get("2024_accessed") is not False:
        raise RunnerError("P2A-R1 accessed 2024 unexpectedly")
    if report.get("return_calculation_executed") is not False:
        raise RunnerError("P2A-R1 unexpectedly calculated returns")

    candidate = load_json(repo / FROZEN_CANDIDATE)
    if candidate.get("candidate_id") != CANDIDATE_ID:
        raise RunnerError("frozen candidate id drifted")
    if candidate.get("take_profit") is not None:
        raise RunnerError("upside cap entered frozen candidate")
    if candidate.get("adaptive_trailing") is not False:
        raise RunnerError("adaptive trailing entered frozen candidate")
    if candidate.get("capital_replacement") is not False:
        raise RunnerError("capital replacement entered frozen candidate")

    protocol = load_json(repo / P3_PROTOCOL)
    if protocol.get("candidate_id") != CANDIDATE_ID:
        raise RunnerError("P3 protocol candidate drift")
    if protocol.get("starting_commit") != EXPECTED_PARENT:
        raise RunnerError("P3 protocol starting commit drift")
    if protocol.get("prohibitions", {}).get("2024_access") is not False:
        raise RunnerError("P3 protocol accidentally authorizes 2024")
    if (
        protocol.get("capacity", {}).get(
            "maximum_entry_notional_fraction_of_trailing_24h_quote_turnover_proxy"
        )
        != 0.005
    ):
        raise RunnerError("P3 liquidity capacity rule drifted")
    return {
        "candidate_id": CANDIDATE_ID,
        "p2a_r1_report_sha256": EXPECTED_INPUT_HASHES[P2A_R1_REPORT],
        "signal_events_sha256": EXPECTED_INPUT_HASHES[SIGNAL_EVENTS],
        "frozen_candidate_contract_sha256": EXPECTED_INPUT_HASHES[FROZEN_CANDIDATE],
        "pre_pnl_signal_funnel_sha256": EXPECTED_INPUT_HASHES[PRE_PNL_FUNNEL],
        "p3_protocol_sha256": sha256(repo / P3_PROTOCOL),
    }


def load_features(
    raw_root: Path,
    pairs: list[str],
) -> dict[str, pd.DataFrame]:
    features: dict[str, pd.DataFrame] = {}
    cutoff = DATA_CUTOFF.to_pydatetime()
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
        if len(featured) and featured["timestamp"].max() >= DATA_CUTOFF:
            raise RunnerError(f"sealed row loaded: {pair}")
        features[pair] = featured
        print(
            f"RD20_P3_FEATURE_SOURCE={index}/{len(pairs)}:{pair}:{len(featured)}",
            flush=True,
        )
    return features


def partition_metrics(
    daily: pd.DataFrame,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    frame = daily.copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, errors="raise")
    for (run_id, universe_id, cost_multiplier), run in frame.groupby(
        ["run_id", "universe_id", "cost_multiplier"],
        sort=True,
    ):
        for partition_id, (start, end) in PARTITIONS.items():
            selected = run.loc[
                (run["timestamp"] >= start.floor("D")) & (run["timestamp"] < end.floor("D"))
            ].copy()
            if selected.empty:
                continue
            before = run.loc[run["timestamp"] < selected["timestamp"].min()]
            start_equity = float(before.iloc[-1]["equity"]) if len(before) else INITIAL_EQUITY
            end_equity = float(selected.iloc[-1]["equity"])
            rows.append(
                {
                    "run_id": str(run_id),
                    "universe_id": str(universe_id),
                    "cost_multiplier": float(cost_multiplier),
                    "partition_id": partition_id,
                    "start_equity": start_equity,
                    "end_equity": end_equity,
                    "net_return": end_equity / start_equity - 1.0,
                }
            )
    return pd.DataFrame.from_records(rows)


def output_manifest(output: Path, decision: str) -> dict[str, Any]:
    files = []
    for name in OUTPUT_NAMES:
        path = output / name
        if not path.is_file():
            raise RunnerError(f"P3 output missing for manifest: {path}")
        files.append(
            {
                "path": name,
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
        )
    digest = hashlib.sha256()
    for row in sorted(files, key=lambda value: str(value["path"])):
        digest.update(str(row["path"]).encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(row["sha256"]).encode("ascii"))
        digest.update(b"\n")
    return {
        "schema_version": "rd20-p3-core-edge-output-manifest-v1",
        "candidate_id": CANDIDATE_ID,
        "decision": decision,
        "files": files,
        "deterministic_hash": digest.hexdigest(),
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

    input_audit = verify_inputs(repo)
    head = git(repo, "rev-parse", "HEAD")
    events = pd.read_csv(repo / SIGNAL_EVENTS, low_memory=False)
    events["timestamp"] = pd.to_datetime(events["timestamp"], utc=True, errors="raise")
    pairs = sorted(set(events["pair"].astype(str)))
    if len(events) != 24_560:
        raise RunnerError(f"frozen signal row count drift: {len(events)}")
    if len(pairs) != 28:
        raise RunnerError(f"frozen signal pair count drift: {len(pairs)}")

    if args.preflight_only:
        if head != EXPECTED_PARENT:
            raise RunnerError(
                f"P3 preflight must run before freeze from {EXPECTED_PARENT}, found {head}"
            )
        for pair in pairs:
            path = raw_root / pair / "1h.parquet"
            if not path.is_file():
                raise RunnerError(f"raw source missing: {path}")
            columns = set(pq.ParquetFile(path).schema_arrow.names)
            if "volume" not in columns:
                raise RunnerError(f"volume missing from raw source: {pair}")
        print(
            json.dumps(
                {
                    "status": "PASS",
                    "stage": "RD20_P3_PROTOCOL_PREFLIGHT",
                    "candidate_id": CANDIDATE_ID,
                    "signal_event_count": len(events),
                    "signal_pair_count": len(pairs),
                    "economic_output_exposed": False,
                    "2024_accessed": False,
                    "input_audit": input_audit,
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
    if head != args.expected_freeze_commit:
        raise RunnerError(
            f"P3 execution must run from frozen commit {args.expected_freeze_commit}, found {head}"
        )
    if git(repo, "diff", "--name-only", "HEAD", "--").strip():
        raise RunnerError("P3 execution requires a clean frozen working tree")

    features = load_features(raw_root, pairs)
    parity = validate_signal_event_parity(events, features)
    if not parity["full_signal_event_feature_parity"]:
        raise RunnerError("frozen signal parity failed")

    forward_rows = forward_horizon_rows(events, features)
    forward_summary = aggregate_forward_horizons(forward_rows)

    all_trades = []
    all_daily = []
    all_metrics = []
    all_years = []
    all_routes = []
    all_concentration = []
    all_loao = []
    all_loyo = []
    base_trade_by_universe: dict[str, pd.DataFrame] = {}

    for universe in ("C2", "D2", "E2"):
        for multiplier in COST_MULTIPLIERS:
            print(
                f"RD20_P3_REPLAY={universe}:{multiplier:.0f}x",
                flush=True,
            )
            trades, equity_hourly, route = replay_universe(
                universe_id=universe,
                cost_multiplier=multiplier,
                events=events,
                features=features,
            )
            metrics, years = performance_metrics(trades, equity_hourly, route)
            daily = equity_hourly.copy()
            daily["timestamp"] = pd.to_datetime(
                daily["timestamp"],
                utc=True,
                errors="raise",
            )
            daily["date"] = daily["timestamp"].dt.floor("D")
            daily = (
                daily.groupby("date", as_index=False)
                .agg(
                    equity=("equity", "last"),
                    cash=("cash", "last"),
                    gross_market_value=("gross_market_value", "last"),
                    position_count=("position_count", "last"),
                    drawdown=("drawdown", "last"),
                    active=("active", "max"),
                )
                .rename(columns={"date": "timestamp"})
            )
            daily.insert(0, "cost_multiplier", multiplier)
            daily.insert(0, "universe_id", universe)
            daily.insert(0, "run_id", str(route["run_id"]))

            concentration, loao, loyo = contribution_diagnostics(trades)
            concentration.update(
                {
                    "run_id": str(route["run_id"]),
                    "universe_id": universe,
                    "cost_multiplier": multiplier,
                }
            )
            loao.insert(0, "cost_multiplier", multiplier)
            loao.insert(0, "universe_id", universe)
            loao.insert(0, "run_id", str(route["run_id"]))
            loyo.insert(0, "cost_multiplier", multiplier)
            loyo.insert(0, "universe_id", universe)
            loyo.insert(0, "run_id", str(route["run_id"]))

            years.insert(0, "cost_multiplier", multiplier)
            years.insert(0, "universe_id", universe)
            years.insert(0, "run_id", str(route["run_id"]))

            all_trades.append(trades)
            all_daily.append(daily)
            all_metrics.append(metrics)
            all_years.append(years)
            all_routes.append(route)
            all_concentration.append(concentration)
            all_loao.append(loao)
            all_loyo.append(loyo)
            if multiplier == 1.0:
                base_trade_by_universe[universe] = trades.copy()

    trade_frame = pd.concat(all_trades, ignore_index=True)
    daily_frame = pd.concat(all_daily, ignore_index=True)
    metrics_frame = pd.DataFrame.from_records(all_metrics)
    year_frame = pd.concat(all_years, ignore_index=True)
    route_frame = pd.DataFrame.from_records(all_routes)
    concentration_frame = pd.DataFrame.from_records(all_concentration)
    loao_frame = pd.concat(all_loao, ignore_index=True)
    loyo_frame = pd.concat(all_loyo, ignore_index=True)

    break_even_rows = []
    for universe in ("C2", "D2", "E2"):
        value = fixed_path_pf1_break_even_multiplier(base_trade_by_universe[universe])
        break_even_rows.append(
            {
                "universe_id": universe,
                "pf1_break_even_cost_multiplier_fixed_base_path": value,
                "method": "BASE_ROUTED_QUANTITIES_AND_FILLS_FIXED_COST_SCALED_UNTIL_PF_1",
            }
        )
    break_even = pd.DataFrame.from_records(break_even_rows)
    gates, hard_pass = hard_gate_evaluation(
        metrics_frame,
        break_even,
        concentration_frame,
    )

    cross_review = bool(
        concentration_frame.loc[
            concentration_frame["cost_multiplier"] == 2.0,
            "cross_venue_trade_review_triggered",
        ]
        .astype(bool)
        .any()
    )
    if hard_pass and cross_review:
        decision = "RD20_P3_CORE_EDGE_CONFIRMED_CROSS_VENUE_REVIEW_REQUIRED"
        next_stage = "RD20_P3X_CROSS_VENUE_CONTRIBUTION_REVIEW"
        p4_authorized = False
    elif hard_pass:
        decision = "RD20_P3_CORE_EDGE_CONFIRMED_P4_AUTHORIZED"
        next_stage = "RD20_P4_ADAPTIVE_EXIT_ABLATION_PROTOCOL_FREEZE"
        p4_authorized = True
    else:
        decision = "RD20_P3_CORE_EDGE_REJECTED_NO_ADVANCEMENT"
        next_stage = "RD20_P3_CLOSED_NEW_CORE_CANDIDATE_REQUIRED"
        p4_authorized = False

    partition_frame = partition_metrics(daily_frame)

    output = repo / OUTPUT
    output.mkdir(parents=True, exist_ok=True)
    input_audit.update(
        {
            "freeze_commit": args.expected_freeze_commit,
            "signal_event_feature_parity": parity,
            "raw_pair_count": len(features),
            "capacity_source": "BASE_VOLUME_X_COMPLETED_BAR_CLOSE",
            "capacity_fraction_trailing_24h": 0.005,
            "2024_accessed": False,
        }
    )
    write_json(output / "input-and-conformance-audit.json", input_audit)
    forward_summary.to_csv(
        output / "forward-horizon-diagnostics.csv",
        index=False,
        lineterminator="\n",
    )
    metrics_frame.to_csv(output / "run-metrics.csv", index=False, lineterminator="\n")
    year_frame.to_csv(output / "year-metrics.csv", index=False, lineterminator="\n")
    partition_frame.to_csv(
        output / "partition-metrics.csv",
        index=False,
        lineterminator="\n",
    )
    route_frame.to_csv(
        output / "routing-summary.csv",
        index=False,
        lineterminator="\n",
    )
    trade_frame.to_csv(
        output / "trade-ledger.csv",
        index=False,
        lineterminator="\n",
    )
    daily_frame.to_csv(
        output / "daily-equity.csv",
        index=False,
        lineterminator="\n",
    )
    concentration_frame.to_csv(
        output / "concentration-diagnostics.csv",
        index=False,
        lineterminator="\n",
    )
    loao_frame.to_csv(
        output / "leave-one-asset-out.csv",
        index=False,
        lineterminator="\n",
    )
    loyo_frame.to_csv(
        output / "leave-one-year-out.csv",
        index=False,
        lineterminator="\n",
    )
    break_even.to_csv(
        output / "break-even-cost-multiplier.csv",
        index=False,
        lineterminator="\n",
    )
    gates.to_csv(
        output / "hard-gate-evaluation.csv",
        index=False,
        lineterminator="\n",
    )

    stress = metrics_frame.loc[metrics_frame["cost_multiplier"] == 2.0].copy()
    base = metrics_frame.loc[metrics_frame["cost_multiplier"] == 1.0].copy()
    report = {
        "schema_version": "rd20-p3-core-edge-report-v1",
        "stage": "RD20_P3_CORE_EDGE_ECONOMIC_EVALUATION",
        "candidate_id": CANDIDATE_ID,
        "decision": decision,
        "next_stage": next_stage,
        "p4_authorized": p4_authorized,
        "hard_gates_passed": hard_pass,
        "cross_venue_contribution_review_required": cross_review,
        "freeze_commit": args.expected_freeze_commit,
        "economic_replay_executed": True,
        "return_calculation_executed": True,
        "base_all_universes_positive": bool((base["net_return"] > 0.0).all()),
        "stress_2x_all_universes_positive": bool((stress["net_return"] > 0.0).all()),
        "worst_universe_base_net_return": float(base["net_return"].min()),
        "worst_universe_2x_net_return": float(stress["net_return"].min()),
        "worst_universe_2x_profit_factor": float(stress["profit_factor"].min()),
        "worst_universe_2x_maximum_drawdown": float(stress["maximum_drawdown"].max()),
        "minimum_2x_trade_count": int(stress["trade_count"].min()),
        "minimum_2x_positive_year_count": int(stress["positive_year_count"].min()),
        "minimum_pf1_break_even_cost_multiplier": float(
            break_even["pf1_break_even_cost_multiplier_fixed_base_path"].min()
        ),
        "candidate_event_count": len(events),
        "trade_ledger_rows": len(trade_frame),
        "capacity_fraction_trailing_24h_quote_turnover_proxy": 0.005,
        "daily_growth_aspiration_is_hard_gate": False,
        "monthly_growth_aspiration_is_hard_gate": False,
        "upside_cap": None,
        "2024_accessed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
    }
    write_json(output / "rd20-p3-core-edge-report-v1.json", report)
    manifest = output_manifest(output, decision)
    write_json(output / "output-manifest.json", manifest)

    print(json.dumps(report, indent=2, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
