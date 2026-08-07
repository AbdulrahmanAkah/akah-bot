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
from spotbot.research.rd26_exit_architecture import (  # noqa: E402
    CONCENTRATION_TRIGGER,
    COST_MULTIPLIERS,
    DATA_CUTOFF,
    DATA_START,
    FAMILY_MOMENTUM_BREAKOUT,
    FAMILY_RELATIVE_STRENGTH_ROTATION,
    FOCUS_FAMILIES,
    POLICIES,
    PREFLIGHT_CUTOFF,
    PREFLIGHT_PERIODS,
    PREFLIGHT_START,
    ROBUSTNESS_PERIODS,
    compare_focus_signal_equivalence,
    concentration_diagnostics,
    evaluate_policy_hard_gates,
    exit_reason_summary,
    filter_robustness_events,
    fixed_path_pf1_break_even_multiplier,
    period_metrics,
    prepare_features,
    replay_policy,
    scan_focus_signals,
    standalone_events,
    union_events,
    validate_constants,
)

EXPECTED_PARENT = "f40107fab876d709c353fc47b63d1347fabf2ada"
RD25_DIAGNOSIS = Path("data/research/rd25_p1_runtime/diagnosis.json")
RD25_DIAGNOSIS_SHA256 = "e9102397d6337801c163d4e78b5f365a7ea79f47b2db4469c67da04a537bc69e"
RD23_SIGNAL_EVENTS = Path("data/research/rd23_p2_runtime/signal-events.csv")
RD23_SIGNAL_EVENTS_SHA256 = "cdd6f078a5851a38be3f44722dcca7d6ccccb771b4647e9b467d14de3fc9d264"
MEMBERSHIP = Path("data/research/rd18_p3x_a3b_runtime/effective-operational-membership.csv")
PROTOCOL = Path("data/research/rd26_p1/rd26-p1-exit-architecture-robustness-protocol-v1.json")
PREFLIGHT_AUDIT = Path("data/research/rd26_p0_runtime/rd23-focus-signal-equivalence-audit-v1.json")
OUTPUT = Path("data/research/rd26_p1_runtime")
DEFAULT_RAW_ROOT = Path("data/raw/rd16b/kucoin")

OUTPUT_NAMES = (
    "input-and-conformance-audit.json",
    "signal-events-2022-2023.csv",
    "signal-funnel-2022-2023.csv",
    "portfolio-run-metrics.csv",
    "portfolio-period-metrics.csv",
    "routing-summary.csv",
    "trade-ledger.csv",
    "daily-equity.csv",
    "concentration-diagnostics.csv",
    "break-even-cost-multiplier.csv",
    "exit-reason-summary.csv",
    "hard-gate-evaluation.csv",
    "policy-selection.csv",
    "selected-exit-architecture-freeze.json",
    "rd26-p1-exit-architecture-robustness-report-v1.json",
)


class RunnerError(RuntimeError):
    pass


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser()
    value.add_argument("--repo-root", type=Path, required=True)
    value.add_argument("--raw-root", type=Path, default=None)
    value.add_argument("--preflight-only", action="store_true")
    value.add_argument("--execute", action="store_true")
    value.add_argument("--validate-only", action="store_true")
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


def verify_lineage(repo: Path) -> dict[str, Any]:
    validate_constants()
    diagnosis_path = repo / RD25_DIAGNOSIS
    if not diagnosis_path.is_file():
        raise RunnerError("corrected RD25 diagnosis is missing")
    if sha256(diagnosis_path) != RD25_DIAGNOSIS_SHA256:
        raise RunnerError("corrected RD25 diagnosis hash drifted")
    diagnosis = load_json(diagnosis_path)
    if diagnosis.get("decision") != (
        "RD25_DIAGNOSIS_COMPLETE_ARCHITECTURE_PREREGISTRATION_REQUIRED"
    ):
        raise RunnerError("RD25 decision does not authorize RD26")
    if diagnosis.get("dd_only_failure_families") != list(FOCUS_FAMILIES):
        raise RunnerError("RD25 corrected focus-family classification drifted")
    if diagnosis.get("multi_failure_families") != [
        "MOMENTUM_ACCELERATION",
        "VOLATILITY_EXPANSION",
    ]:
        raise RunnerError("RD25 corrected multi-failure classification drifted")
    for field in (
        "2022_2023_accessed",
        "2024_accessed",
        "post_2024_accessed",
        "production_authorized",
    ):
        if diagnosis.get(field) is not False:
            raise RunnerError(f"RD25 prohibited flag is true: {field}")

    signal_path = repo / RD23_SIGNAL_EVENTS
    if not signal_path.is_file():
        raise RunnerError("frozen RD23 signal ledger is missing")
    if sha256(signal_path) != RD23_SIGNAL_EVENTS_SHA256:
        raise RunnerError("frozen RD23 signal ledger hash drifted")

    return {
        "source_commit": EXPECTED_PARENT,
        "rd25_diagnosis_sha256": RD25_DIAGNOSIS_SHA256,
        "rd23_signal_events_sha256": RD23_SIGNAL_EVENTS_SHA256,
        "focus_families": list(FOCUS_FAMILIES),
        "policies": list(POLICIES),
    }


def load_feature_frames(
    *,
    raw_root: Path,
    pairs: list[str],
    cutoff: pd.Timestamp,
) -> dict[str, pd.DataFrame]:
    frames: dict[str, pd.DataFrame] = {}
    cutoff_value = cutoff.to_pydatetime()
    for index, pair in enumerate(pairs, start=1):
        path = raw_root / pair / "1h.parquet"
        raw = pd.read_parquet(
            path,
            engine="pyarrow",
            filters=[("timestamp", "<", cutoff_value)],
        )
        frame = prepare_features(raw, cutoff=cutoff)
        frames[pair] = frame
        print(
            f"RD26_FEATURE_SOURCE={index}/{len(pairs)}:{pair}:{len(frame)}:cutoff={cutoff.date()}",
            flush=True,
        )
    return frames


def run_preflight(
    *,
    repo: Path,
    raw_root: Path,
) -> dict[str, Any]:
    lineage = verify_lineage(repo)
    head = git(repo, "rev-parse", "HEAD")
    if head != EXPECTED_PARENT:
        raise RunnerError(f"RD26 preflight HEAD {head} != expected parent {EXPECTED_PARENT}")

    membership_path = repo / MEMBERSHIP
    if not membership_path.is_file():
        raise RunnerError("PIT membership source is missing")
    membership = load_membership(membership_path)
    pairs = raw_pairs(membership_path)
    if not pairs:
        raise RunnerError("no PIT pairs found")
    missing = [pair for pair in pairs if not (raw_root / pair / "1h.parquet").is_file()]
    if missing:
        raise RunnerError(f"raw 1h sources missing: {missing[:20]}")

    features = load_feature_frames(
        raw_root=raw_root,
        pairs=pairs,
        cutoff=PREFLIGHT_CUTOFF,
    )
    generated, _funnel = scan_focus_signals(
        membership=membership,
        features=features,
        periods=PREFLIGHT_PERIODS,
        data_start=PREFLIGHT_START,
        data_cutoff=PREFLIGHT_CUTOFF,
        guard_each_period_hours=168,
    )
    frozen = pd.read_csv(repo / RD23_SIGNAL_EVENTS, low_memory=False)
    equivalence = compare_focus_signal_equivalence(generated, frozen)

    audit = {
        "schema_version": "rd26-p0-rd23-focus-signal-equivalence-audit-v1",
        "stage": "RD26_ARCHITECTURE_PREREGISTRATION_PRE_2022_2023",
        "head": head,
        "lineage": lineage,
        "membership_sha256": sha256(membership_path),
        "pair_count": len(pairs),
        "pairs": pairs,
        "signal_equivalence": equivalence,
        "preflight_data_cutoff_exclusive": PREFLIGHT_CUTOFF.isoformat(),
        "2022_2023_accessed": False,
        "2024_accessed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
    }
    write_json(repo / PREFLIGHT_AUDIT, audit)
    return audit


def verify_execution_inputs(
    *,
    repo: Path,
    raw_root: Path,
    expected_freeze_commit: str,
) -> tuple[list[Any], list[str], dict[str, Any]]:
    lineage = verify_lineage(repo)
    head = git(repo, "rev-parse", "HEAD")
    if head != expected_freeze_commit:
        raise RunnerError(f"RD26 execution HEAD {head} != freeze {expected_freeze_commit}")
    audit = load_json(repo / PREFLIGHT_AUDIT)
    if audit.get("signal_equivalence", {}).get("equivalence_passed") is not True:
        raise RunnerError("pre-freeze RD23 focus signal equivalence did not pass")
    if audit.get("2022_2023_accessed") is not False:
        raise RunnerError("pre-freeze audit indicates 2022-2023 access")

    membership_path = repo / MEMBERSHIP
    if sha256(membership_path) != audit.get("membership_sha256"):
        raise RunnerError("membership source changed after freeze")
    membership = load_membership(membership_path)
    pairs = raw_pairs(membership_path)
    if pairs != audit.get("pairs"):
        raise RunnerError("PIT pair set changed after freeze")
    missing = [pair for pair in pairs if not (raw_root / pair / "1h.parquet").is_file()]
    if missing:
        raise RunnerError(f"raw 1h sources missing: {missing[:20]}")
    return membership, pairs, lineage


def run_all_portfolios(
    *,
    events: pd.DataFrame,
    frames: dict[str, pd.DataFrame],
) -> tuple[
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
]:
    run_rows: list[dict[str, Any]] = []
    trade_sets: list[pd.DataFrame] = []
    daily_sets: list[pd.DataFrame] = []
    routing_rows: list[dict[str, Any]] = []
    concentration_rows: list[dict[str, Any]] = []
    break_even_rows: list[dict[str, Any]] = []

    for policy_id in POLICIES:
        for universe in ("C2", "D2", "E2"):
            portfolios = {
                "UNION_FOCUS": union_events(events, universe_id=universe),
                FAMILY_MOMENTUM_BREAKOUT: standalone_events(
                    events,
                    universe_id=universe,
                    family_id=FAMILY_MOMENTUM_BREAKOUT,
                ),
                FAMILY_RELATIVE_STRENGTH_ROTATION: standalone_events(
                    events,
                    universe_id=universe,
                    family_id=FAMILY_RELATIVE_STRENGTH_ROTATION,
                ),
            }
            for portfolio_id, portfolio_events in portfolios.items():
                base_trade_for_be: pd.DataFrame | None = None
                for cost_multiplier in COST_MULTIPLIERS:
                    trades, daily, metrics, counters = replay_policy(
                        policy_id=policy_id,
                        portfolio_id=portfolio_id,
                        universe_id=universe,
                        cost_multiplier=cost_multiplier,
                        events=portfolio_events,
                        frames=frames,
                    )
                    run_rows.append(metrics)
                    if len(trades):
                        trade_sets.append(trades)
                    if len(daily):
                        daily_sets.append(daily)
                    routing_rows.append(
                        {
                            "policy_id": policy_id,
                            "portfolio_id": portfolio_id,
                            "universe_id": universe,
                            "cost_multiplier": cost_multiplier,
                            **counters,
                        }
                    )
                    concentration_rows.append(
                        {
                            "policy_id": policy_id,
                            "portfolio_id": portfolio_id,
                            "universe_id": universe,
                            "cost_multiplier": cost_multiplier,
                            **concentration_diagnostics(trades),
                        }
                    )
                    if cost_multiplier == 1.0:
                        base_trade_for_be = trades.copy()
                    print(
                        "RD26_PORTFOLIO="
                        f"{policy_id}:{portfolio_id}:{universe}:{cost_multiplier}x:"
                        f"net={metrics['net_return']:.6f}:"
                        f"pf={metrics['profit_factor']:.6f}:"
                        f"dd={metrics['maximum_drawdown']:.6f}:"
                        f"trades={metrics['trade_count']}",
                        flush=True,
                    )
                if base_trade_for_be is None:
                    raise RunnerError("base-cost trade ledger missing")
                break_even_rows.append(
                    {
                        "policy_id": policy_id,
                        "portfolio_id": portfolio_id,
                        "universe_id": universe,
                        "pf1_break_even_cost_multiplier": (
                            fixed_path_pf1_break_even_multiplier(base_trade_for_be)
                        ),
                        "method": ("BASE_ROUTED_QUANTITIES_AND_FILLS_FIXED_COST_SCALED_UNTIL_PF_1"),
                    }
                )

    run_metrics = pd.DataFrame.from_records(run_rows)
    trades = pd.concat(trade_sets, ignore_index=True) if trade_sets else pd.DataFrame()
    daily = pd.concat(daily_sets, ignore_index=True) if daily_sets else pd.DataFrame()
    routing = pd.DataFrame.from_records(routing_rows)
    concentrations = pd.DataFrame.from_records(concentration_rows)
    break_even = pd.DataFrame.from_records(break_even_rows)
    return run_metrics, trades, daily, routing, concentrations, break_even


def report_payload(
    *,
    run_metrics: pd.DataFrame,
    concentrations: pd.DataFrame,
    selection: pd.DataFrame,
    event_count: int,
    freeze_commit: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    selected_rows = selection.loc[selection["selected"]]
    selected_policy = str(selected_rows.iloc[0]["policy_id"]) if len(selected_rows) == 1 else None

    policy_summaries: dict[str, dict[str, Any]] = {}
    for policy_id in POLICIES:
        stress = run_metrics.loc[
            (run_metrics["policy_id"] == policy_id)
            & (run_metrics["portfolio_id"] == "UNION_FOCUS")
            & (run_metrics["cost_multiplier"] == 2.0)
        ]
        policy_summaries[policy_id] = {
            "worst_universe_2x_net_return": float(stress["net_return"].min()),
            "worst_universe_2x_profit_factor": float(stress["profit_factor"].min()),
            "worst_universe_2x_maximum_drawdown": float(stress["maximum_drawdown"].max()),
            "minimum_2x_trade_count": int(stress["trade_count"].min()),
        }

    concentration_trigger = False
    maximum_largest_winner_share = 0.0
    if selected_policy is not None:
        selected_conc = concentrations.loc[
            (concentrations["policy_id"] == selected_policy)
            & (concentrations["portfolio_id"] == "UNION_FOCUS")
            & (concentrations["cost_multiplier"] == 2.0)
        ]
        maximum_largest_winner_share = float(
            selected_conc["largest_winner_positive_pnl_share"].max()
        )
        concentration_trigger = maximum_largest_winner_share > CONCENTRATION_TRIGGER

    if selected_policy is None:
        decision = "RD26_EXIT_ARCHITECTURE_NO_FINALIST_RISK_OR_ROUTER_REDESIGN_REQUIRED"
        next_stage = "RD27_RISK_SIZING_OR_CAPITAL_ROUTER_ARCHITECTURE_REQUIRED"
    elif concentration_trigger:
        decision = "RD26_EXIT_ARCHITECTURE_SELECTED_CROSS_VENUE_CONTRIBUTION_REVIEW_REQUIRED"
        next_stage = "RD26X_CROSS_VENUE_CONTRIBUTION_REVIEW"
    else:
        decision = "RD26_EXIT_ARCHITECTURE_SELECTED_2024_CONFIRMATION_AUTHORIZED"
        next_stage = "RD27_CLEAN_2024_INTERNAL_CONFIRMATION"

    selected_freeze = {
        "schema_version": "rd26-p1-selected-exit-architecture-freeze-v1",
        "stage": "RD26_EXIT_ARCHITECTURE_EXPOSED_ROBUSTNESS_2022_2023",
        "selected_policy": selected_policy,
        "selection_basis": ("PASS_ALL_HARD_GATES_THEN_MAXIMIZE_WORST_UNIVERSE_2X_NET_RETURN"),
        "policy_summaries": policy_summaries,
        "cross_venue_contribution_review_required": concentration_trigger,
        "maximum_selected_largest_winner_positive_pnl_share": (maximum_largest_winner_share),
        "freeze_commit": freeze_commit,
        "2022_2023_used_for_architecture_selection": True,
        "2024_accessed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
    }
    report = {
        "schema_version": "rd26-p1-exit-architecture-robustness-report-v1",
        "stage": "RD26_EXIT_ARCHITECTURE_EXPOSED_ROBUSTNESS_2022_2023",
        "status": "PASS",
        "decision": decision,
        "next_stage": next_stage,
        "source_commit": EXPECTED_PARENT,
        "freeze_commit": freeze_commit,
        "focus_families": list(FOCUS_FAMILIES),
        "policy_count": len(POLICIES),
        "policies": list(POLICIES),
        "selected_policy": selected_policy,
        "policy_summaries": policy_summaries,
        "signal_event_count_2022_2023": event_count,
        "cross_venue_contribution_review_required": concentration_trigger,
        "2022_2023_used_for_architecture_selection": True,
        "2024_accessed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
    }
    return report, selected_freeze


def output_manifest(output: Path, decision: str) -> dict[str, Any]:
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
        "schema_version": "rd26-p1-output-manifest-v1",
        "decision": decision,
        "deterministic_hash": deterministic,
        "files": files,
        "2022_2023_used_for_architecture_selection": True,
        "2024_accessed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
    }


def validate_outputs(repo: Path) -> dict[str, Any]:
    output = repo / OUTPUT
    manifest_path = output / "output-manifest.json"
    if not manifest_path.is_file():
        raise RunnerError("RD26 output manifest missing")
    manifest = load_json(manifest_path)
    by_name = {
        str(item["path"]): item for item in manifest.get("files", []) if isinstance(item, dict)
    }
    if set(by_name) != set(OUTPUT_NAMES):
        raise RunnerError("RD26 manifest output set drifted")
    for name in OUTPUT_NAMES:
        path = output / name
        if not path.is_file():
            raise RunnerError(f"RD26 output missing: {name}")
        item = by_name[name]
        if path.stat().st_size != int(item["bytes"]):
            raise RunnerError(f"RD26 byte-size drift: {name}")
        if sha256(path) != str(item["sha256"]):
            raise RunnerError(f"RD26 hash drift: {name}")

    report = load_json(output / "rd26-p1-exit-architecture-robustness-report-v1.json")
    if report.get("status") != "PASS":
        raise RunnerError("RD26 report status drifted")
    if report.get("2022_2023_used_for_architecture_selection") is not True:
        raise RunnerError("RD26 selection-use flag drifted")
    for field in (
        "2024_accessed",
        "post_2024_accessed",
        "production_authorized",
    ):
        if report.get(field) is not False:
            raise RunnerError(f"RD26 prohibited flag true: {field}")

    signals = pd.read_csv(output / "signal-events-2022-2023.csv", low_memory=False)
    signal_times = pd.to_datetime(signals["timestamp"], utc=True, errors="raise")
    if bool((signal_times < DATA_START).any()) or bool((signal_times >= DATA_CUTOFF).any()):
        raise RunnerError("RD26 signal ledger crossed sealed boundary")
    trades = pd.read_csv(output / "trade-ledger.csv", low_memory=False)
    if len(trades):
        exits = pd.to_datetime(trades["exit_time"], utc=True, errors="raise")
        if bool((exits >= DATA_CUTOFF).any()):
            raise RunnerError("RD26 trade exit crossed into 2024")
    return {
        "status": "PASS",
        "decision": report["decision"],
        "selected_policy": report["selected_policy"],
        "signal_event_count_2022_2023": len(signals),
        "manifest_hash": sha256(manifest_path),
        "2024_accessed": False,
    }


def main() -> int:
    args = parser().parse_args()
    repo = args.repo_root.resolve()
    raw_root = (
        args.raw_root.resolve()
        if args.raw_root is not None
        else (repo / DEFAULT_RAW_ROOT).resolve()
    )
    mode_count = sum(
        int(value) for value in (args.preflight_only, args.execute, args.validate_only)
    )
    if mode_count != 1:
        raise RunnerError("choose exactly one runner mode")

    if args.validate_only:
        print(json.dumps(validate_outputs(repo), indent=2, sort_keys=True))
        return 0

    if args.preflight_only:
        audit = run_preflight(repo=repo, raw_root=raw_root)
        print(json.dumps(audit, indent=2, sort_keys=True))
        return 0

    if not args.expected_freeze_commit:
        raise RunnerError("--expected-freeze-commit is required for execution")
    membership, pairs, lineage = verify_execution_inputs(
        repo=repo,
        raw_root=raw_root,
        expected_freeze_commit=args.expected_freeze_commit,
    )
    frames = load_feature_frames(
        raw_root=raw_root,
        pairs=pairs,
        cutoff=DATA_CUTOFF,
    )
    events, funnel = scan_focus_signals(
        membership=membership,
        features=frames,
        periods=ROBUSTNESS_PERIODS,
        data_start=DATA_START,
        data_cutoff=DATA_CUTOFF,
        guard_each_period_hours=None,
    )
    events = filter_robustness_events(events)

    output = repo / OUTPUT
    output.mkdir(parents=True, exist_ok=False)
    audit = {
        "schema_version": "rd26-p1-input-conformance-audit-v1",
        "source_commit": EXPECTED_PARENT,
        "freeze_commit": args.expected_freeze_commit,
        "lineage": lineage,
        "preflight_audit_sha256": sha256(repo / PREFLIGHT_AUDIT),
        "membership_sha256": sha256(repo / MEMBERSHIP),
        "pair_count": len(pairs),
        "pairs": pairs,
        "focus_families": list(FOCUS_FAMILIES),
        "policies": list(POLICIES),
        "selection_periods": {
            name: [start.isoformat(), end.isoformat()]
            for name, (start, end) in ROBUSTNESS_PERIODS.items()
        },
        "2022_2023_used_for_architecture_selection": True,
        "2024_accessed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
    }
    write_json(output / "input-and-conformance-audit.json", audit)

    run_metrics, trades, daily, routing, concentrations, break_even = run_all_portfolios(
        events=events, frames=frames
    )
    periods = period_metrics(trades)
    reasons = exit_reason_summary(trades)
    gates, selection = evaluate_policy_hard_gates(
        run_metrics=run_metrics,
        periods=periods,
        concentrations=concentrations,
        break_even=break_even,
    )
    report, selected_freeze = report_payload(
        run_metrics=run_metrics,
        concentrations=concentrations,
        selection=selection,
        event_count=len(events),
        freeze_commit=args.expected_freeze_commit,
    )

    events.to_csv(
        output / "signal-events-2022-2023.csv",
        index=False,
        lineterminator="\n",
    )
    funnel.to_csv(
        output / "signal-funnel-2022-2023.csv",
        index=False,
        lineterminator="\n",
    )
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
    routing.to_csv(
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
    reasons.to_csv(
        output / "exit-reason-summary.csv",
        index=False,
        lineterminator="\n",
    )
    gates.to_csv(
        output / "hard-gate-evaluation.csv",
        index=False,
        lineterminator="\n",
    )
    selection.to_csv(
        output / "policy-selection.csv",
        index=False,
        lineterminator="\n",
    )
    write_json(output / "selected-exit-architecture-freeze.json", selected_freeze)
    write_json(
        output / "rd26-p1-exit-architecture-robustness-report-v1.json",
        report,
    )
    write_json(
        output / "output-manifest.json",
        output_manifest(output, report["decision"]),
    )

    result = validate_outputs(repo)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"RD26_ERROR={exc}", file=sys.stderr)
        raise
