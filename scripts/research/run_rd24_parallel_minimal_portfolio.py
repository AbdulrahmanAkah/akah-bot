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

from spotbot.research.rd24_minimal_portfolio import (  # noqa: E402
    COST_MULTIPLIERS,
    DATA_CUTOFF,
    DATA_START,
    PERIODS,
    QUALIFIED_FAMILIES,
    concentration_diagnostics,
    family_attribution,
    fixed_path_pf1_break_even_multiplier,
    normalize_economic_bars,
    period_metrics,
    prepare_frozen_events,
    replay_portfolio,
    standalone_events,
    standalone_hard_gate_rows,
    union_events,
    validate_constants,
)

EXPECTED_PARENT = "f0120353dac3a3ac47ad44039c749c4e46cf2069"
RD23_SIGNAL_EVENTS = Path("data/research/rd23_p2_runtime/signal-events.csv")
RD23_QUALIFIED_FREEZE = Path("data/research/rd23_p2_runtime/qualified-family-freeze.json")
RD23_REPORT = Path("data/research/rd23_p2_runtime/rd23-p2-multifamily-raw-edge-report-v1.json")
RD23_MANIFEST = Path("data/research/rd23_p2_runtime/output-manifest.json")
PROTOCOL = Path("data/research/rd24_p2/rd24-p2-parallel-minimal-portfolio-protocol-v1.json")
OUTPUT = Path("data/research/rd24_p2_runtime")
DEFAULT_RAW_ROOT = Path("data/raw/rd16b/kucoin")

EXPECTED_INPUT_HASHES = {
    RD23_SIGNAL_EVENTS: "cdd6f078a5851a38be3f44722dcca7d6ccccb771b4647e9b467d14de3fc9d264",
    RD23_QUALIFIED_FREEZE: "10707f5f381532f24d68f3264c6345de4eeadd0f356ae764f0c95e33f8b1c629",
    RD23_REPORT: "e6ac534bff6b1a11517480987c31897c4c4cb21647fbb5c2c811282fe7424917",
    RD23_MANIFEST: "4229056263041507265ee329addec71e518b88a8b80e91d9bf4e9df2131db777",
}

OUTPUT_NAMES = (
    "input-and-conformance-audit.json",
    "portfolio-run-metrics.csv",
    "portfolio-period-metrics.csv",
    "routing-summary.csv",
    "trade-ledger.csv",
    "daily-equity.csv",
    "concentration-diagnostics.csv",
    "break-even-cost-multiplier.csv",
    "hard-gate-evaluation.csv",
    "family-attribution.csv",
    "union-leave-one-family-out.csv",
    "portfolio-qualified-family-freeze.json",
    "rd24-p2-parallel-minimal-portfolio-report-v1.json",
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


def verify_inputs(
    *,
    repo: Path,
    raw_root: Path,
    expected_freeze_commit: str | None,
    executing: bool,
) -> tuple[pd.DataFrame, list[str], dict[str, Any]]:
    validate_constants()
    for relative, expected in EXPECTED_INPUT_HASHES.items():
        path = repo / relative
        if not path.is_file():
            raise RunnerError(f"frozen RD23 input missing: {path}")
        actual = sha256(path)
        if actual != expected:
            raise RunnerError(f"RD23 input hash drift: {relative}: {actual} != {expected}")

    head = git(repo, "rev-parse", "HEAD")
    if executing:
        if not expected_freeze_commit:
            raise RunnerError("expected freeze commit is required for execution")
        if head != expected_freeze_commit:
            raise RunnerError(f"RD24 execution HEAD {head} != freeze {expected_freeze_commit}")
    elif head != EXPECTED_PARENT:
        raise RunnerError(f"RD24 preflight HEAD {head} != expected parent {EXPECTED_PARENT}")

    freeze = load_json(repo / RD23_QUALIFIED_FREEZE)
    if freeze.get("qualified_families") != list(QUALIFIED_FAMILIES):
        raise RunnerError("RD23 qualified family set drifted")
    horizons = freeze.get("selected_horizon_hours")
    if not isinstance(horizons, dict) or set(horizons) != set(QUALIFIED_FAMILIES):
        raise RunnerError("RD23 selected horizon mapping drifted")
    if any(int(horizons[family]) != 168 for family in QUALIFIED_FAMILIES):
        raise RunnerError("RD23 selected horizon is not uniformly 168h")
    if freeze.get("2024_accessed") is not False:
        raise RunnerError("RD23 freeze indicates 2024 access")

    report = load_json(repo / RD23_REPORT)
    if report.get("decision") != (
        "RD23_P2_MULTIFAMILY_RAW_EDGE_TOURNAMENT_"
        "MULTIPLE_FAMILIES_CONFIRMED_RD24_PARALLEL_MINIMAL_PORTFOLIO_AUTHORIZED"
    ):
        raise RunnerError("RD23 does not authorize RD24")

    raw_events = pd.read_csv(repo / RD23_SIGNAL_EVENTS, low_memory=False)
    events = prepare_frozen_events(raw_events)
    pairs = sorted(set(events["pair"].astype(str)))
    missing = [pair for pair in pairs if not (raw_root / pair / "1h.parquet").is_file()]
    if missing:
        raise RunnerError(f"qualified signal raw sources missing: {missing[:20]}")

    audit = {
        "schema_version": "rd24-input-conformance-audit-v1",
        "source_commit": EXPECTED_PARENT,
        "head": head,
        "rd23_input_hashes": {
            str(path): expected for path, expected in EXPECTED_INPUT_HASHES.items()
        },
        "qualified_families": list(QUALIFIED_FAMILIES),
        "selected_horizon_hours": {family: 168 for family in QUALIFIED_FAMILIES},
        "qualified_signal_rows": len(events),
        "qualified_pair_count": len(pairs),
        "qualified_pairs": pairs,
        "selection_data_start": DATA_START.isoformat(),
        "selection_data_cutoff_exclusive": DATA_CUTOFF.isoformat(),
        "2022_2023_used_for_selection": False,
        "2024_accessed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
    }
    return events, pairs, audit


def load_frames(
    *,
    raw_root: Path,
    pairs: list[str],
) -> dict[str, pd.DataFrame]:
    frames: dict[str, pd.DataFrame] = {}
    cutoff = DATA_CUTOFF.to_pydatetime()
    for index, pair in enumerate(pairs, start=1):
        path = raw_root / pair / "1h.parquet"
        raw = pd.read_parquet(
            path,
            engine="pyarrow",
            filters=[("timestamp", "<", cutoff)],
        )
        frame = normalize_economic_bars(raw)
        frames[pair] = frame
        print(
            f"RD24_ECONOMIC_SOURCE={index}/{len(pairs)}:{pair}:{len(frame)}",
            flush=True,
        )
    return frames


def _run_one(
    *,
    portfolio_id: str,
    universe_id: str,
    cost_multiplier: float,
    events: pd.DataFrame,
    frames: dict[str, pd.DataFrame],
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any], dict[str, Any]]:
    trades, daily, metrics, counters = replay_portfolio(
        portfolio_id=portfolio_id,
        universe_id=universe_id,
        cost_multiplier=cost_multiplier,
        events=events,
        frames=frames,
    )
    print(
        "RD24_RUN="
        f"{portfolio_id}:{universe_id}:{cost_multiplier}x:"
        f"trades={metrics['trade_count']}:"
        f"net={metrics['net_return']:.6f}:"
        f"pf={metrics['profit_factor']:.6f}:"
        f"dd={metrics['maximum_drawdown']:.6f}",
        flush=True,
    )
    routing = {
        "portfolio_id": portfolio_id,
        "universe_id": universe_id,
        "cost_multiplier": cost_multiplier,
        **counters,
    }
    return trades, daily, metrics, routing


def _diagnostic_rows(
    *,
    trade_sets: list[pd.DataFrame],
    run_metrics: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    concentration_rows: list[dict[str, Any]] = []
    break_even_rows: list[dict[str, Any]] = []
    for trades in trade_sets:
        if trades.empty:
            continue
        keys = trades[["portfolio_id", "universe_id", "cost_multiplier"]].drop_duplicates()
        if len(keys) != 1:
            raise RunnerError("trade set contains multiple run identities")
        identity = keys.iloc[0].to_dict()
        concentration_rows.append(
            {
                **identity,
                **concentration_diagnostics(trades),
            }
        )
        if float(identity["cost_multiplier"]) == 1.0:
            break_even_rows.append(
                {
                    "portfolio_id": str(identity["portfolio_id"]),
                    "universe_id": str(identity["universe_id"]),
                    "pf1_break_even_cost_multiplier": (
                        fixed_path_pf1_break_even_multiplier(trades)
                    ),
                    "method": ("BASE_ROUTED_QUANTITIES_AND_FILLS_FIXED_COST_SCALED_UNTIL_PF_1"),
                }
            )

    concentration = pd.DataFrame.from_records(concentration_rows)
    break_even = pd.DataFrame.from_records(break_even_rows)
    expected_be = run_metrics.loc[run_metrics["cost_multiplier"] == 1.0][
        ["portfolio_id", "universe_id"]
    ].drop_duplicates()
    if len(break_even) != len(expected_be):
        raise RunnerError("break-even diagnostic cardinality drifted")
    return concentration, break_even


def _union_hard_gates(
    *,
    portfolio_id: str,
    run_metrics: pd.DataFrame,
    period_frame: pd.DataFrame,
    concentrations: pd.DataFrame,
    break_even: pd.DataFrame,
    lofo: pd.DataFrame,
) -> tuple[pd.DataFrame, bool]:
    rows: list[dict[str, Any]] = []
    overall = True
    for universe in ("C2", "D2", "E2"):
        base = run_metrics.loc[
            (run_metrics["portfolio_id"] == portfolio_id)
            & (run_metrics["universe_id"] == universe)
            & (run_metrics["cost_multiplier"] == 1.0)
        ]
        stress = run_metrics.loc[
            (run_metrics["portfolio_id"] == portfolio_id)
            & (run_metrics["universe_id"] == universe)
            & (run_metrics["cost_multiplier"] == 2.0)
        ]
        concentration = concentrations.loc[
            (concentrations["portfolio_id"] == portfolio_id)
            & (concentrations["universe_id"] == universe)
            & (concentrations["cost_multiplier"] == 2.0)
        ]
        be = break_even.loc[
            (break_even["portfolio_id"] == portfolio_id) & (break_even["universe_id"] == universe)
        ]
        period_subset = period_frame.loc[
            (period_frame["portfolio_id"] == portfolio_id)
            & (period_frame["universe_id"] == universe)
            & (period_frame["cost_multiplier"] == 2.0)
        ]
        if len(base) != 1 or len(stress) != 1 or len(concentration) != 1 or len(be) != 1:
            raise RunnerError("union diagnostic cardinality drifted")
        stress_row = stress.iloc[0]
        conc = concentration.iloc[0]
        lofo_subset = lofo.loc[(lofo["universe_id"] == universe) & (lofo["cost_multiplier"] == 2.0)]
        lofo_positive = len(lofo_subset) > 0 and bool((lofo_subset["net_pnl"] > 0.0).all())
        checks = {
            "BASE_NET_RETURN_POSITIVE": float(base.iloc[0]["net_return"]) > 0.0,
            "STRESS_2X_NET_RETURN_POSITIVE": float(stress_row["net_return"]) > 0.0,
            "STRESS_2X_PROFIT_FACTOR_GTE_1_05": float(stress_row["profit_factor"]) >= 1.05,
            "STRESS_2X_MAX_DRAWDOWN_LTE_20PCT": float(stress_row["maximum_drawdown"]) <= 0.20,
            "STRESS_2X_TRADES_GTE_75": int(stress_row["trade_count"]) >= 75,
            "BOTH_SELECTION_PERIODS_NET_PNL_POSITIVE": (
                len(period_subset) == len(PERIODS) and bool((period_subset["net_pnl"] > 0.0).all())
            ),
            "STRESS_2X_LARGEST_WINNER_REMOVAL_POSITIVE": (
                float(conc["net_pnl_without_largest_winner"]) > 0.0
            ),
            "STRESS_2X_LOAO_MIN_REMAINING_PNL_POSITIVE": (
                float(conc["minimum_loao_remaining_net_pnl"]) > 0.0
            ),
            "STRESS_2X_LOYO_MIN_REMAINING_PNL_POSITIVE": (
                float(conc["minimum_loyo_remaining_net_pnl"]) > 0.0
            ),
            "PF1_BREAK_EVEN_COST_MULTIPLIER_GTE_2": (
                float(be.iloc[0]["pf1_break_even_cost_multiplier"]) >= 2.0
            ),
            "LEAVE_ONE_FAMILY_OUT_2X_NET_PNL_POSITIVE": lofo_positive,
            "CASH_FEASIBLE": float(stress_row["minimum_cash"]) >= -1e-8,
        }
        for gate_id, passed in checks.items():
            rows.append(
                {
                    "portfolio_id": portfolio_id,
                    "universe_id": universe,
                    "gate_id": gate_id,
                    "passed": bool(passed),
                }
            )
            overall = overall and bool(passed)
    return pd.DataFrame.from_records(rows), overall


def output_manifest(output: Path, names: tuple[str, ...], decision: str) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for name in names:
        path = output / name
        rows.append(
            {
                "path": name,
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
        )
    deterministic = hashlib.sha256(
        "".join(f"{row['path']}:{row['sha256']}\n" for row in rows).encode("utf-8")
    ).hexdigest()
    return {
        "schema_version": "rd24-p2-output-manifest-v1",
        "stage": "RD24_QUALIFIED_FAMILY_MINIMAL_PORTFOLIO_EVALUATION_PARALLEL",
        "decision": decision,
        "deterministic_hash": deterministic,
        "files": rows,
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

    events, pairs, audit = verify_inputs(
        repo=repo,
        raw_root=raw_root,
        expected_freeze_commit=args.expected_freeze_commit,
        executing=args.execute,
    )

    if args.preflight_only:
        print(
            json.dumps(
                {
                    "status": "PASS",
                    "stage": "RD24_PARALLEL_MINIMAL_PORTFOLIO_PREFLIGHT",
                    "qualified_families": list(QUALIFIED_FAMILIES),
                    "qualified_signal_rows": len(events),
                    "pair_count": len(pairs),
                    "holding_hours": 168,
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

    frames = load_frames(raw_root=raw_root, pairs=pairs)
    all_trades: list[pd.DataFrame] = []
    all_daily: list[pd.DataFrame] = []
    metric_rows: list[dict[str, Any]] = []
    routing_rows: list[dict[str, Any]] = []

    # Phase 1: each RD23-qualified family is translated independently.
    for family in QUALIFIED_FAMILIES:
        for universe in ("C2", "D2", "E2"):
            family_events = standalone_events(
                events,
                universe_id=universe,
                family_id=family,
            )
            for cost_multiplier in COST_MULTIPLIERS:
                trades, daily, metrics, routing = _run_one(
                    portfolio_id=family,
                    universe_id=universe,
                    cost_multiplier=cost_multiplier,
                    events=family_events,
                    frames=frames,
                )
                all_trades.append(trades)
                all_daily.append(daily)
                metric_rows.append(metrics)
                routing_rows.append(routing)

    standalone_metrics = pd.DataFrame.from_records(metric_rows)
    standalone_trades = pd.concat(all_trades, ignore_index=True) if all_trades else pd.DataFrame()
    standalone_period = period_metrics(standalone_trades)
    standalone_conc, standalone_be = _diagnostic_rows(
        trade_sets=all_trades,
        run_metrics=standalone_metrics,
    )
    standalone_gates, portfolio_qualified = standalone_hard_gate_rows(
        run_metrics=standalone_metrics,
        period_frame=standalone_period,
        concentrations=standalone_conc,
        break_even=standalone_be,
    )

    # Phase 2A: all four raw-qualified families as a diagnostic union.
    union_all_id = "UNION_ALL_RAW_QUALIFIED"
    for universe in ("C2", "D2", "E2"):
        union_all_events = union_events(
            events,
            universe_id=universe,
            families=QUALIFIED_FAMILIES,
        )
        for cost_multiplier in COST_MULTIPLIERS:
            trades, daily, metrics, routing = _run_one(
                portfolio_id=union_all_id,
                universe_id=universe,
                cost_multiplier=cost_multiplier,
                events=union_all_events,
                frames=frames,
            )
            all_trades.append(trades)
            all_daily.append(daily)
            metric_rows.append(metrics)
            routing_rows.append(routing)

    # Phase 2B: deterministic union of standalone portfolio passers.
    qualified_union_id = "UNION_PORTFOLIO_QUALIFIED"
    qualified_tuple = tuple(portfolio_qualified)
    qualified_union_executed = len(qualified_tuple) >= 2
    if qualified_union_executed:
        for universe in ("C2", "D2", "E2"):
            qualified_events = union_events(
                events,
                universe_id=universe,
                families=qualified_tuple,
            )
            for cost_multiplier in COST_MULTIPLIERS:
                trades, daily, metrics, routing = _run_one(
                    portfolio_id=qualified_union_id,
                    universe_id=universe,
                    cost_multiplier=cost_multiplier,
                    events=qualified_events,
                    frames=frames,
                )
                all_trades.append(trades)
                all_daily.append(daily)
                metric_rows.append(metrics)
                routing_rows.append(routing)

    run_metrics = pd.DataFrame.from_records(metric_rows)
    trades = pd.concat(all_trades, ignore_index=True) if all_trades else pd.DataFrame()
    daily = pd.concat(all_daily, ignore_index=True) if all_daily else pd.DataFrame()
    periods = period_metrics(trades)
    concentrations, break_even = _diagnostic_rows(
        trade_sets=all_trades,
        run_metrics=run_metrics,
    )

    # Leave-one-family-out is only defined for the deterministic union of passers.
    lofo_rows: list[dict[str, Any]] = []
    if qualified_union_executed:
        for omitted in qualified_tuple:
            retained = tuple(family for family in qualified_tuple if family != omitted)
            for universe in ("C2", "D2", "E2"):
                retained_events = union_events(
                    events,
                    universe_id=universe,
                    families=retained,
                )
                for cost_multiplier in COST_MULTIPLIERS:
                    lofo_id = f"LOFO_WITHOUT_{omitted}"
                    lofo_trades, _daily, lofo_metrics, _routing = _run_one(
                        portfolio_id=lofo_id,
                        universe_id=universe,
                        cost_multiplier=cost_multiplier,
                        events=retained_events,
                        frames=frames,
                    )
                    lofo_rows.append(
                        {
                            "omitted_family": omitted,
                            "retained_family_count": len(retained),
                            "universe_id": universe,
                            "cost_multiplier": cost_multiplier,
                            "trade_count": lofo_metrics["trade_count"],
                            "net_return": lofo_metrics["net_return"],
                            "net_pnl": lofo_metrics["net_pnl"],
                            "profit_factor": lofo_metrics["profit_factor"],
                            "maximum_drawdown": lofo_metrics["maximum_drawdown"],
                        }
                    )
    lofo = pd.DataFrame.from_records(lofo_rows)

    union_gate_rows = pd.DataFrame(columns=["portfolio_id", "universe_id", "gate_id", "passed"])
    union_pass = False
    if qualified_union_executed:
        union_gate_rows, union_pass = _union_hard_gates(
            portfolio_id=qualified_union_id,
            run_metrics=run_metrics,
            period_frame=periods,
            concentrations=concentrations,
            break_even=break_even,
            lofo=lofo,
        )

    all_gates = pd.concat(
        [standalone_gates, union_gate_rows],
        ignore_index=True,
    )
    attribution = family_attribution(
        trades.loc[trades["portfolio_id"].isin([union_all_id, qualified_union_id])].copy()
        if len(trades)
        else trades
    )

    cross_venue_review_required = False
    if len(concentrations) and portfolio_qualified:
        relevant_ids = set(portfolio_qualified)
        if union_pass:
            relevant_ids.add(qualified_union_id)
        stress_conc = concentrations.loc[
            (concentrations["cost_multiplier"] == 2.0)
            & (concentrations["portfolio_id"].isin(relevant_ids))
        ]
        if len(stress_conc):
            cross_venue_review_required = bool(
                (stress_conc["largest_winner_positive_pnl_share"] > 0.15).any()
            )

    if union_pass and len(portfolio_qualified) >= 2:
        if cross_venue_review_required:
            decision = (
                "RD24_MULTIFAMILY_MINIMAL_PORTFOLIO_CONFIRMED_"
                "CROSS_VENUE_CONTRIBUTION_REVIEW_REQUIRED"
            )
            next_stage = "RD24_X_CROSS_VENUE_CONTRIBUTION_REVIEW"
        else:
            decision = (
                "RD24_MULTIFAMILY_MINIMAL_PORTFOLIO_CONFIRMED_RD25_EXPOSED_ROBUSTNESS_AUTHORIZED"
            )
            next_stage = "RD25_EXPOSED_ROBUSTNESS_2022_2023"
    elif portfolio_qualified:
        decision = "RD24_STANDALONE_MINIMAL_PORTFOLIO_EDGE_CONFIRMED_INTEGRATION_REDESIGN_REQUIRED"
        next_stage = "RD25_INTEGRATION_ARCHITECTURE_REVIEW_PRE_2022_2023"
    else:
        decision = (
            "RD24_RAW_EDGE_DID_NOT_TRANSLATE_TO_MINIMAL_PORTFOLIO_"
            "EXECUTION_ARCHITECTURE_DIAGNOSIS_REQUIRED"
        )
        next_stage = "RD25_PORTFOLIO_TRANSLATION_DIAGNOSIS"

    output = repo / OUTPUT
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "input-and-conformance-audit.json", audit)
    run_metrics.to_csv(
        output / "portfolio-run-metrics.csv",
        index=False,
        lineterminator="\n",
    )
    periods.to_csv(
        output / "portfolio-period-metrics.csv",
        index=False,
        lineterminator="\n",
    )
    pd.DataFrame.from_records(routing_rows).to_csv(
        output / "routing-summary.csv",
        index=False,
        lineterminator="\n",
    )
    trades.to_csv(
        output / "trade-ledger.csv",
        index=False,
        lineterminator="\n",
    )
    daily.to_csv(
        output / "daily-equity.csv",
        index=False,
        lineterminator="\n",
    )
    concentrations.to_csv(
        output / "concentration-diagnostics.csv",
        index=False,
        lineterminator="\n",
    )
    break_even.to_csv(
        output / "break-even-cost-multiplier.csv",
        index=False,
        lineterminator="\n",
    )
    all_gates.to_csv(
        output / "hard-gate-evaluation.csv",
        index=False,
        lineterminator="\n",
    )
    attribution.to_csv(
        output / "family-attribution.csv",
        index=False,
        lineterminator="\n",
    )
    lofo.to_csv(
        output / "union-leave-one-family-out.csv",
        index=False,
        lineterminator="\n",
    )

    freeze = {
        "schema_version": "rd24-portfolio-qualified-family-freeze-v1",
        "decision": decision,
        "rd23_raw_qualified_families": list(QUALIFIED_FAMILIES),
        "portfolio_qualified_families": portfolio_qualified,
        "portfolio_qualified_family_count": len(portfolio_qualified),
        "selected_horizon_hours": {family: 168 for family in portfolio_qualified},
        "qualified_union_executed": qualified_union_executed,
        "qualified_union_hard_gates_passed": union_pass,
        "2022_2023_used_for_selection": False,
        "2024_accessed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
    }
    write_json(output / "portfolio-qualified-family-freeze.json", freeze)

    stress_rows = run_metrics.loc[run_metrics["cost_multiplier"] == 2.0].copy()
    standalone_stress = stress_rows.loc[stress_rows["portfolio_id"].isin(QUALIFIED_FAMILIES)]
    report = {
        "schema_version": "rd24-p2-parallel-minimal-portfolio-report-v1",
        "stage": "RD24_QUALIFIED_FAMILY_MINIMAL_PORTFOLIO_EVALUATION_PARALLEL",
        "decision": decision,
        "next_stage": next_stage,
        "passed": True,
        "rd23_raw_qualified_families": list(QUALIFIED_FAMILIES),
        "portfolio_qualified_families": portfolio_qualified,
        "portfolio_qualified_family_count": len(portfolio_qualified),
        "qualified_union_executed": qualified_union_executed,
        "qualified_union_hard_gates_passed": union_pass,
        "cross_venue_contribution_review_required": cross_venue_review_required,
        "standalone_2x_net_return_by_family_universe": {
            f"{row.portfolio_id}:{row.universe_id}": float(row.net_return)
            for row in standalone_stress.itertuples()
        },
        "standalone_2x_maximum_drawdown_by_family_universe": {
            f"{row.portfolio_id}:{row.universe_id}": float(row.maximum_drawdown)
            for row in standalone_stress.itertuples()
        },
        "union_all_2x_metrics": {
            row.universe_id: {
                "net_return": float(row.net_return),
                "profit_factor": float(row.profit_factor),
                "maximum_drawdown": float(row.maximum_drawdown),
            }
            for row in stress_rows.loc[stress_rows["portfolio_id"] == union_all_id].itertuples()
        },
        "qualified_union_2x_metrics": {
            row.universe_id: {
                "net_return": float(row.net_return),
                "profit_factor": float(row.profit_factor),
                "maximum_drawdown": float(row.maximum_drawdown),
            }
            for row in stress_rows.loc[
                stress_rows["portfolio_id"] == qualified_union_id
            ].itertuples()
        },
        "portfolio_replay_executed": True,
        "position_sizing_executed": True,
        "historical_exit_simulation_executed": True,
        "adaptive_exit_executed": False,
        "2022_2023_used_for_selection": False,
        "2024_accessed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
    }
    write_json(
        output / "rd24-p2-parallel-minimal-portfolio-report-v1.json",
        report,
    )

    manifest = output_manifest(output, OUTPUT_NAMES, decision)
    write_json(output / "output-manifest.json", manifest)

    print(json.dumps(report, indent=2, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RunnerError as exc:
        print(f"RD24_RUNNER_ERROR={exc}", file=sys.stderr)
        raise SystemExit(2) from exc
