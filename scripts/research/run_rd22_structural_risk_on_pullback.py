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
from spotbot.research.rd22_structural_risk_on_pullback import (  # noqa: E402
    CANDIDATE_FAMILY_ID,
    COST_MULTIPLIERS,
    DISCOVERY_CUTOFF,
    DISCOVERY_START,
    HORIZON_HOURS,
    build_btc_daily_ema200_regime,
    replay_fixed_horizon,
    validate_constants,
    variant_gate_rows,
)

EXPECTED_SOURCE_COMMIT = "6dc05e52bdc8479e3b9b5328a72c3c1fb4ae4626"
P2A_EVENTS = Path("data/research/rd20_p2a_r1_runtime/signal-events.csv")
RD21_REPORT = Path("data/research/rd21_p2_runtime/rd21-p2-discovery-report-v1.json")
RD21_METRICS = Path("data/research/rd21_p2_runtime/variant-metrics.csv")
RD21_CONCENTRATION = Path("data/research/rd21_p2_runtime/concentration-diagnostics.csv")
RD21_TRADES = Path("data/research/rd21_p2_runtime/trade-ledger.csv")
RD21_GATES = Path("data/research/rd21_p2_runtime/variant-hard-gates.csv")
RD21_DIAGNOSIS = Path("data/research/rd22_p0_runtime/rd21-no-finalist-diagnosis-v1.json")
PROTOCOL = Path("data/research/rd22_p2/rd22-p2-structural-risk-on-pullback-protocol-v1.json")
OUTPUT = Path("data/research/rd22_p2_runtime")
DEFAULT_RAW_ROOT = Path("data/raw/rd16b/kucoin")

EXPECTED_HASHES = {
    P2A_EVENTS: "d501c80b4a0baaf42f543df793b5485d16eaf586cdb493ebe01362536d6cde13",
    RD21_REPORT: "32661ff49a365e6c7671e854d1039ecd5f67aee469687fff440dd2dbc726a2b4",
    RD21_METRICS: "43bec69fd8a0dbf70d59d99c2086b4233b43300455ba04e8e6f4a733d9350c17",
    RD21_CONCENTRATION: "c19563b413ffbd4137f38ab9dfd8c9087535fc2efe778e717335c1dc6e306776",
    RD21_TRADES: "270235a7cafb5d5a495931ceb95b18aebed6746fc14f25342de315e1a92744b4",
    RD21_GATES: "622b34b09efa655e782f083857d8cf55e4f2313604ca5e8dec25549c2f522dbf",
}

OUTPUT_NAMES = (
    "input-and-conformance-audit.json",
    "btc-daily-ema200-regime.csv",
    "candidate-metrics.csv",
    "year-metrics.csv",
    "routing-summary.csv",
    "trade-ledger.csv",
    "daily-equity.csv",
    "concentration-diagnostics.csv",
    "leave-one-asset-out.csv",
    "leave-one-year-out.csv",
    "break-even-cost-multiplier.csv",
    "candidate-hard-gates.csv",
    "finalist-freeze.json",
    "rd22-p2-discovery-report-v1.json",
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

    report = load_json(repo / RD21_REPORT)
    if report.get("decision") != "RD21_P2_HORIZON_DISCOVERY_CLOSED_NO_FINALIST":
        raise RunnerError("RD21 no-finalist decision drifted")
    if report.get("selected_horizon_hours") is not None:
        raise RunnerError("RD21 unexpectedly selected a finalist")
    if int(report.get("top_ranked_horizon_hours", 168)) != 168:
        raise RunnerError("RD21 top-ranked horizon drifted from 168")

    diagnosis = load_json(repo / RD21_DIAGNOSIS)
    if diagnosis.get("decision") != "RD22_P0_RD21_NO_FINALIST_DIAGNOSIS_COMPLETE":
        raise RunnerError("RD22 P0 diagnosis missing or drifted")

    protocol = load_json(repo / PROTOCOL)
    if protocol.get("starting_commit") != EXPECTED_SOURCE_COMMIT:
        raise RunnerError("RD22 protocol starting commit drifted")
    if protocol.get("fixed_horizon_hours") != 168:
        raise RunnerError("RD22 fixed horizon drifted")
    gate = protocol.get("market_regime_gate", {})
    if gate.get("id") != "BTC_COMPLETED_DAILY_CLOSE_GT_EMA200":
        raise RunnerError("RD22 regime gate identity drifted")
    if gate.get("ema_span_days") != 200:
        raise RunnerError("RD22 EMA span drifted")
    if protocol.get("selection_data") != "DISCOVERY_2019_2021_ONLY":
        raise RunnerError("RD22 selection-data contract drifted")
    if protocol.get("prohibitions", {}).get("access_2022_2023_for_selection") is not False:
        raise RunnerError("RD22 protocol incorrectly authorizes 2022/2023 selection access")
    if protocol.get("prohibitions", {}).get("access_2024") is not False:
        raise RunnerError("RD22 protocol incorrectly authorizes 2024")

    return {
        "source_commit": EXPECTED_SOURCE_COMMIT,
        "freeze_commit": head,
        "signal_events_sha256": EXPECTED_HASHES[P2A_EVENTS],
        "rd21_report_sha256": EXPECTED_HASHES[RD21_REPORT],
        "rd21_metrics_sha256": EXPECTED_HASHES[RD21_METRICS],
        "rd21_concentration_sha256": EXPECTED_HASHES[RD21_CONCENTRATION],
        "rd21_trade_ledger_sha256": EXPECTED_HASHES[RD21_TRADES],
        "rd21_gate_sha256": EXPECTED_HASHES[RD21_GATES],
        "rd21_diagnosis_sha256": sha256(repo / RD21_DIAGNOSIS),
        "protocol_sha256": sha256(repo / PROTOCOL),
        "fixed_horizon_hours": 168,
        "new_research_dimension_count": 1,
        "new_research_dimension": "BTC_COMPLETED_DAILY_CLOSE_GT_EMA200_REGIME_GATE",
        "2022_2023_used_for_selection": False,
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
            f"RD22_DISCOVERY_FEATURE_SOURCE={index}/{len(pairs)}:{pair}:{len(featured)}",
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
        "schema_version": "rd22-p2-structural-risk-on-pullback-output-manifest-v1",
        "candidate_family_id": CANDIDATE_FAMILY_ID,
        "decision": decision,
        "files": files,
        "deterministic_hash": digest.hexdigest(),
        "selection_data": "DISCOVERY_2019_2021_ONLY",
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
    audit = verify_inputs(
        repo,
        expected_freeze_commit=args.expected_freeze_commit,
    )
    events = load_discovery_events(repo)
    pairs = sorted(events["pair"].astype(str).unique().tolist())

    if args.preflight_only:
        required_pairs = sorted(set(pairs) | {"BTC-USDT"})
        missing = [
            pair for pair in required_pairs if not (raw_root / pair / "1h.parquet").is_file()
        ]
        if missing:
            raise RunnerError(f"discovery raw sources missing: {missing[:20]}")
        print(
            json.dumps(
                {
                    "status": "PASS",
                    "candidate_family_id": CANDIDATE_FAMILY_ID,
                    "fixed_horizon_hours": 168,
                    "market_regime_gate": "BTC_COMPLETED_DAILY_CLOSE_GT_EMA200",
                    "discovery_event_count": len(events),
                    "discovery_pair_count": len(pairs),
                    "selection_data": "DISCOVERY_2019_2021_ONLY",
                    "2022_2023_used_for_selection": False,
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

    feature_pairs = sorted(set(pairs) | {"BTC-USDT"})
    features = load_features(raw_root, feature_pairs)
    regime = build_btc_daily_ema200_regime(features["BTC-USDT"])
    if regime.empty:
        raise RunnerError("BTC daily EMA200 regime schedule is empty")
    if not bool(regime["regime_ready"].any()):
        raise RunnerError("BTC daily EMA200 never becomes ready in discovery")

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
                    regime=regime,
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

    all_pass = bool(horizon_pass.get(168, False))
    selected_horizon = 168 if all_pass else None
    if all_pass:
        decision = "RD22_P2_STRUCTURAL_RISK_ON_PULLBACK_FINALIST_SELECTED"
        next_stage = "RD22_P3_EXPOSED_2022_2023_ROBUSTNESS_AFTER_FINALIST_FREEZE"
    else:
        decision = "RD22_P2_STRUCTURAL_RISK_ON_PULLBACK_REJECTED_CLOSE_TREND_PULLBACK_FAMILY"
        next_stage = "RD23_INDEPENDENT_SETUP_FAMILY_REQUIRED"

    finalist = {
        "schema_version": "rd22-p2-finalist-freeze-v1",
        "candidate_family_id": CANDIDATE_FAMILY_ID,
        "selected_horizon_hours": selected_horizon,
        "market_regime_gate": "BTC_COMPLETED_DAILY_CLOSE_GT_EMA200",
        "ema_span_days": 200,
        "signal_ledger_sha256": EXPECTED_HASHES[P2A_EVENTS],
        "signal_logic_changed": False,
        "entry_logic_changed": False,
        "initial_stop_changed": False,
        "sizing_changed": False,
        "capacity_changed": False,
        "cost_model_changed": False,
        "score_logic_changed": False,
        "fixed_horizon_hours": 168,
        "only_new_research_dimension": "STRUCTURAL_RISK_ON_REGIME_GATE",
        "selection_data": "DISCOVERY_2019_2021_ONLY",
        "2022_2023_used_for_selection": False,
        "2024_accessed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
        "decision": decision,
        "next_stage": next_stage,
    }

    stress = metrics.loc[metrics["cost_multiplier"] == 2.0].copy()
    base = metrics.loc[metrics["cost_multiplier"] == 1.0].copy()
    report = {
        "schema_version": "rd22-p2-structural-risk-on-pullback-report-v1",
        "stage": "RD22_P2_STRUCTURAL_RISK_ON_PULLBACK_DISCOVERY",
        "candidate_family_id": CANDIDATE_FAMILY_ID,
        "decision": decision,
        "selected_horizon_hours": selected_horizon,
        "next_stage": next_stage,
        "fixed_horizon_hours": 168,
        "market_regime_gate": "BTC_COMPLETED_DAILY_CLOSE_GT_EMA200",
        "ema_span_days": 200,
        "discovery_event_count": len(events),
        "discovery_pair_count": len(pairs),
        "hard_gates_passed": all_pass,
        "base_all_universes_positive": bool((base["net_return"] > 0.0).all()),
        "stress_2x_all_universes_positive": bool((stress["net_return"] > 0.0).all()),
        "worst_universe_2x_net_return": float(stress["net_return"].min()),
        "worst_universe_2x_profit_factor": float(stress["profit_factor"].min()),
        "worst_universe_2x_maximum_drawdown": float(stress["maximum_drawdown"].max()),
        "minimum_2x_positive_year_count": int(stress["positive_year_count"].min()),
        "regime_schedule_rows": len(regime),
        "regime_ready_rows": int(regime["regime_ready"].sum()),
        "regime_on_rows": int(regime["regime_on"].sum()),
        "selection_data": "DISCOVERY_2019_2021_ONLY",
        "2022_2023_used_for_selection": False,
        "2024_accessed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
        "parameter_search_dimensions": 1,
        "new_dimension": "BTC_COMPLETED_DAILY_CLOSE_GT_EMA200_REGIME_GATE",
        "score_threshold_added": False,
        "adaptive_exit_added": False,
        "partial_selling_added": False,
        "capital_arbitration_added": False,
        "trend_pullback_family_closes_if_rejected": True,
    }

    write_json(output / "input-and-conformance-audit.json", audit)
    write_csv(output / "btc-daily-ema200-regime.csv", regime)
    write_csv(output / "candidate-metrics.csv", metrics)
    write_csv(output / "year-metrics.csv", years)
    write_csv(output / "routing-summary.csv", routes)
    write_csv(output / "trade-ledger.csv", all_trades)
    write_csv(output / "daily-equity.csv", all_equity)
    write_csv(output / "concentration-diagnostics.csv", concentration)
    write_csv(output / "leave-one-asset-out.csv", loao)
    write_csv(output / "leave-one-year-out.csv", loyo)
    write_csv(output / "break-even-cost-multiplier.csv", break_even)
    write_csv(output / "candidate-hard-gates.csv", gates)
    write_json(output / "finalist-freeze.json", finalist)
    write_json(output / "rd22-p2-discovery-report-v1.json", report)
    write_json(output / "output-manifest.json", output_manifest(output, decision))

    print(json.dumps(report, indent=2, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RunnerError as exc:
        print(f"RD22_RUNNER_ERROR={exc}", file=sys.stderr)
        raise SystemExit(2) from exc
