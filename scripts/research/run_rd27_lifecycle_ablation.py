from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from spotbot.research.rd26_exit_architecture import (  # noqa: E402
    COST_MULTIPLIERS,
    DATA_CUTOFF,
    DATA_START,
    FAMILY_MOMENTUM_BREAKOUT,
    FAMILY_RELATIVE_STRENGTH_ROTATION,
    FOCUS_FAMILIES,
    MAXIMUM_DRAWDOWN_HARD,
    MINIMUM_BREAK_EVEN_COST_MULTIPLIER,
    MINIMUM_PROFIT_FACTOR_2X,
    MINIMUM_TRADES,
    ROBUSTNESS_PERIODS,
    concentration_diagnostics,
    exit_reason_summary,
    filter_robustness_events,
    fixed_path_pf1_break_even_multiplier,
    period_metrics,
    prepare_features,
    standalone_events,
    union_events,
)
from spotbot.research.rd27_adaptive_lifecycle import (  # noqa: E402
    build_market_state_frame,
)
from spotbot.research.rd27_lifecycle_replay import (  # noqa: E402
    POLICIES,
    active_component_count,
    build_state_lookup,
    replay_lifecycle_policy,
    validate_policy_constants,
)

P0B_FREEZE_COMMIT = "b61267adb69b058b9fbd9b11e45a42ebdeb0c333"
PROTOCOL = Path(
    "data/research/rd27_p0/"
    "rd27-p0-adaptive-position-lifecycle-brain-protocol-v1.json"
)
PROTOCOL_SHA256 = "82e19cd9f996f0592614f4b56de7dd1bbd13f96d6cf378ae182d2726b18e3143"
P0B_AUDIT = Path(
    "data/research/rd27_p0b/"
    "rd27-p0b-causal-state-engine-audit-v1.json"
)
P0B_AUDIT_SHA256 = "1e3b68bf9cb9b50aaef4b1cf53e224a3634732e81d4fc74db999a5eac1fa3773"
STATE_ENGINE = Path("src/spotbot/research/rd27_adaptive_lifecycle.py")
STATE_ENGINE_SHA256 = "ee205cda74d70a530734bbfb4843c2dbfc8bf950122254aa2aceb8766a90f9ad"

RD26_SIGNAL_EVENTS = Path("data/research/rd26_p1_runtime/signal-events-2022-2023.csv")
RD26_SIGNAL_EVENTS_SHA256 = "6462f576cee9681751368a7755d3ca51ebf945ced54ea7b7f18b47bc469ba725"
EXPECTED_SIGNAL_EVENT_COUNT = 7073
RD26_RUN_METRICS = Path("data/research/rd26_p1_runtime/portfolio-run-metrics.csv")

DEFAULT_RAW_ROOT = Path("data/raw/rd16b/kucoin")
OUTPUT = Path("data/research/rd27_p1_runtime")

OUTPUT_NAMES = (
    "input-and-conformance-audit.json",
    "market-state-summary.csv",
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
    "selected-lifecycle-policy-freeze.json",
    "rd27-p1-adaptive-lifecycle-report-v1.json",
)


class RunnerError(RuntimeError):
    pass


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser()
    value.add_argument("--repo-root", type=Path, required=True)
    value.add_argument("--raw-root", type=Path, default=None)
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


def verify_lineage(repo: Path, expected_freeze_commit: str) -> dict[str, Any]:
    validate_policy_constants()
    if git(repo, "diff", "--cached", "--name-only", "--"):
        raise RunnerError("staged tracked changes exist before RD27-P1 execution")
    if git(repo, "diff", "--name-only", "--"):
        raise RunnerError("unstaged tracked changes exist before RD27-P1 execution")

    head = git(repo, "rev-parse", "HEAD")
    if head != expected_freeze_commit:
        raise RunnerError(
            f"RD27-P1 HEAD {head} != integration freeze {expected_freeze_commit}"
        )
    parent = git(repo, "rev-parse", "HEAD^")
    if parent != P0B_FREEZE_COMMIT:
        raise RunnerError(f"RD27-P1 integration-freeze parent drifted: {parent}")

    checks = (
        (PROTOCOL, PROTOCOL_SHA256, "RD27 protocol"),
        (P0B_AUDIT, P0B_AUDIT_SHA256, "RD27 P0B audit"),
        (STATE_ENGINE, STATE_ENGINE_SHA256, "RD27 state engine"),
        (RD26_SIGNAL_EVENTS, RD26_SIGNAL_EVENTS_SHA256, "RD26 signal events"),
    )
    for relative, expected_hash, label in checks:
        path = repo / relative
        if not path.is_file():
            raise RunnerError(f"{label} missing: {path}")
        actual = sha256(path)
        if actual != expected_hash:
            raise RunnerError(f"{label} hash drifted: {actual} != {expected_hash}")

    p0b = load_json(repo / P0B_AUDIT)
    if p0b.get("status") != "PASS":
        raise RunnerError("RD27 P0B audit is not PASS")
    if p0b.get("research_logic_changed") is not False:
        raise RunnerError("RD27 P0B audit indicates research logic changed")
    if p0b.get("candidate_parameters_changed") is not False:
        raise RunnerError("RD27 P0B audit indicates candidate parameters changed")
    for field in (
        "economic_execution_performed",
        "2024_accessed",
        "post_2024_accessed",
        "production_authorized",
    ):
        if p0b.get(field) is not False:
            raise RunnerError(f"RD27 P0B prohibited flag is true: {field}")

    protocol = load_json(repo / PROTOCOL)
    expected_policies = set(
        protocol.get("candidate_ablation", {}).get("policies", {}).keys()
    )
    if expected_policies != set(POLICIES):
        raise RunnerError(
            f"RD27 preregistered policy set drifted: {sorted(expected_policies)}"
        )

    return {
        "integration_freeze_commit": expected_freeze_commit,
        "p0b_freeze_commit": P0B_FREEZE_COMMIT,
        "protocol_sha256": PROTOCOL_SHA256,
        "p0b_audit_sha256": P0B_AUDIT_SHA256,
        "state_engine_sha256": STATE_ENGINE_SHA256,
        "rd26_signal_events_sha256": RD26_SIGNAL_EVENTS_SHA256,
        "policies": list(POLICIES),
    }


def load_signal_events(repo: Path) -> pd.DataFrame:
    events = pd.read_csv(repo / RD26_SIGNAL_EVENTS, low_memory=False)
    events["timestamp"] = pd.to_datetime(events["timestamp"], utc=True, errors="raise")
    if len(events) != EXPECTED_SIGNAL_EVENT_COUNT:
        raise RunnerError(
            f"RD26 signal event count drifted: {len(events)} != {EXPECTED_SIGNAL_EVENT_COUNT}"
        )
    if bool((events["timestamp"] < DATA_START).any()):
        raise RunnerError("RD27 signal ledger contains pre-2022 event")
    if bool((events["timestamp"] >= DATA_CUTOFF).any()):
        raise RunnerError("RD27 signal ledger crossed sealed 2024 cutoff")
    events = filter_robustness_events(events)
    if events.empty:
        raise RunnerError("RD27 robustness signal ledger is empty")
    return events


def load_feature_frames(
    *,
    raw_root: Path,
    pairs: list[str],
) -> dict[str, pd.DataFrame]:
    frames: dict[str, pd.DataFrame] = {}
    cutoff_value = DATA_CUTOFF.to_pydatetime()
    for index, pair in enumerate(pairs, start=1):
        path = raw_root / pair / "1h.parquet"
        if not path.is_file():
            raise RunnerError(f"raw 1h source missing: {path}")
        raw = pd.read_parquet(
            path,
            engine="pyarrow",
            filters=[("timestamp", "<", cutoff_value)],
        )
        frame = prepare_features(raw, cutoff=DATA_CUTOFF)
        frames[pair] = frame
        print(
            f"RD27_FEATURE_SOURCE={index}/{len(pairs)}:{pair}:{len(frame)}:"
            f"cutoff={DATA_CUTOFF.date()}",
            flush=True,
        )
    return frames


def load_state_frame(raw_root: Path) -> pd.DataFrame:
    path = raw_root / "BTC-USDT" / "1h.parquet"
    if not path.is_file():
        raise RunnerError(f"BTC state-sensor source missing: {path}")
    raw = pd.read_parquet(
        path,
        engine="pyarrow",
        filters=[("timestamp", "<", DATA_CUTOFF.to_pydatetime())],
    )
    frame = build_market_state_frame(raw, cutoff=DATA_CUTOFF)
    selection = frame.loc[
        (frame["timestamp"] >= DATA_START)
        & (frame["timestamp"] < DATA_CUTOFF)
    ].copy()
    if selection.empty:
        raise RunnerError("BTC state frame has no 2022-2023 rows")
    if not bool(selection["state_ready"].all()):
        first_bad = selection.loc[~selection["state_ready"], "timestamp"].iloc[0]
        raise RunnerError(f"BTC state sensor not ready inside selection window: {first_bad}")
    return frame


def validate_signal_state_coverage(
    events: pd.DataFrame,
    state_frame: pd.DataFrame,
) -> dict[str, Any]:
    lookup = build_state_lookup(state_frame)
    missing = [
        timestamp
        for timestamp in sorted(set(events["timestamp"]))
        if int(pd.Timestamp(timestamp).value) not in lookup
    ]
    if missing:
        raise RunnerError(f"market state unavailable for signal timestamps: {missing[:5]}")
    states = [lookup[int(pd.Timestamp(timestamp).value)] for timestamp in events["timestamp"]]
    counts = pd.Series(states, dtype="string").value_counts().sort_index()
    return {
        "covered_signal_events": len(states),
        "entry_state_event_counts": {
            str(state): int(count)
            for state, count in counts.items()
        },
    }


def market_state_summary(state_frame: pd.DataFrame) -> pd.DataFrame:
    frame = state_frame.loc[
        (state_frame["timestamp"] >= DATA_START)
        & (state_frame["timestamp"] < DATA_CUTOFF)
        & state_frame["state_ready"]
    ].copy()
    counts = (
        frame.groupby("market_state", as_index=False, sort=True)
        .size()
        .rename(columns={"size": "hour_count"})
    )
    counts["hour_fraction"] = counts["hour_count"] / float(len(frame))
    return counts


def verify_control_parity(repo: Path, run_metrics: pd.DataFrame) -> dict[str, Any]:
    path = repo / RD26_RUN_METRICS
    if not path.is_file():
        raise RunnerError(f"RD26 run metrics missing for control parity: {path}")
    frozen = pd.read_csv(path, low_memory=False)
    frozen = frozen.loc[frozen["policy_id"] == "TIME_FAIL_72_H168"].copy()
    current = run_metrics.loc[
        run_metrics["policy_id"] == "CONTROL_TIME_FAIL_72_FIXED_CAPITAL"
    ].copy()
    keys = ["portfolio_id", "universe_id", "cost_multiplier"]
    frozen = frozen.sort_values(keys, kind="stable").reset_index(drop=True)
    current = current.sort_values(keys, kind="stable").reset_index(drop=True)
    if len(frozen) != len(current) or len(current) != 18:
        raise RunnerError(
            f"RD27 control parity cardinality drift: {len(current)} vs {len(frozen)}"
        )
    for key in keys:
        if frozen[key].astype(str).tolist() != current[key].astype(str).tolist():
            raise RunnerError(f"RD27 control parity key drift: {key}")

    numeric = [
        "trade_count",
        "final_equity",
        "net_return",
        "net_pnl",
        "profit_factor",
        "win_rate",
        "maximum_drawdown",
        "turnover",
        "mean_holding_hours",
        "minimum_cash",
    ]
    maximum_absolute_error = 0.0
    for column in numeric:
        left = pd.to_numeric(frozen[column], errors="raise").astype(float)
        right = pd.to_numeric(current[column], errors="raise").astype(float)
        errors = (left - right).abs()
        current_max = float(errors.max()) if len(errors) else 0.0
        maximum_absolute_error = max(maximum_absolute_error, current_max)
        tolerance = 1e-9 * (1.0 + left.abs())
        if bool((errors > tolerance).any()):
            index = int((errors > tolerance).to_numpy().nonzero()[0][0])
            raise RunnerError(
                f"RD27 control parity mismatch {column} row={index}: "
                f"{left.iloc[index]} != {right.iloc[index]}"
            )
    return {
        "passed": True,
        "row_count": len(current),
        "maximum_numeric_absolute_error": maximum_absolute_error,
        "rd26_run_metrics_sha256": sha256(path),
    }


def run_all_portfolios(
    *,
    events: pd.DataFrame,
    frames: dict[str, pd.DataFrame],
    state_frame: pd.DataFrame,
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
                    trades, daily, metrics, counters = replay_lifecycle_policy(
                        policy_id=policy_id,
                        portfolio_id=portfolio_id,
                        universe_id=universe,
                        cost_multiplier=cost_multiplier,
                        events=portfolio_events,
                        frames=frames,
                        state_frame=state_frame,
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
                        "RD27_PORTFOLIO="
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
                        "method": (
                            "BASE_ROUTED_QUANTITIES_AND_FILLS_FIXED_COST_SCALED_UNTIL_PF_1"
                        ),
                    }
                )

    run_metrics = pd.DataFrame.from_records(run_rows)
    trades = pd.concat(trade_sets, ignore_index=True) if trade_sets else pd.DataFrame()
    daily = pd.concat(daily_sets, ignore_index=True) if daily_sets else pd.DataFrame()
    routing = pd.DataFrame.from_records(routing_rows)
    concentrations = pd.DataFrame.from_records(concentration_rows)
    break_even = pd.DataFrame.from_records(break_even_rows)
    return run_metrics, trades, daily, routing, concentrations, break_even


def evaluate_hard_gates(
    *,
    run_metrics: pd.DataFrame,
    periods: pd.DataFrame,
    concentrations: pd.DataFrame,
    break_even: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows: list[dict[str, Any]] = []
    selections: list[dict[str, Any]] = []

    for policy_id in POLICIES:
        policy_pass = True
        worst_return = math.inf
        worst_pf = math.inf
        worst_dd = 0.0
        worst_turnover = 0.0

        for universe in ("C2", "D2", "E2"):

            def one(
                portfolio: str,
                cost: float,
                current_policy: str = policy_id,
                current_universe: str = universe,
            ) -> pd.Series:
                subset = run_metrics.loc[
                    (run_metrics["policy_id"] == current_policy)
                    & (run_metrics["portfolio_id"] == portfolio)
                    & (run_metrics["universe_id"] == current_universe)
                    & (run_metrics["cost_multiplier"] == cost)
                ]
                if len(subset) != 1:
                    raise RunnerError(
                        f"run metric cardinality drift: {current_policy} "
                        f"{portfolio} {current_universe} {cost}"
                    )
                return subset.iloc[0]

            base = one("UNION_FOCUS", 1.0)
            stress = one("UNION_FOCUS", 2.0)
            mb = one(FAMILY_MOMENTUM_BREAKOUT, 2.0)
            rs = one(FAMILY_RELATIVE_STRENGTH_ROTATION, 2.0)

            period_subset = periods.loc[
                (periods["policy_id"] == policy_id)
                & (periods["portfolio_id"] == "UNION_FOCUS")
                & (periods["universe_id"] == universe)
                & (periods["cost_multiplier"] == 2.0)
            ]
            concentration = concentrations.loc[
                (concentrations["policy_id"] == policy_id)
                & (concentrations["portfolio_id"] == "UNION_FOCUS")
                & (concentrations["universe_id"] == universe)
                & (concentrations["cost_multiplier"] == 2.0)
            ]
            be = break_even.loc[
                (break_even["policy_id"] == policy_id)
                & (break_even["portfolio_id"] == "UNION_FOCUS")
                & (break_even["universe_id"] == universe)
            ]
            if len(concentration) != 1 or len(be) != 1:
                raise RunnerError("diagnostic cardinality drifted")
            conc = concentration.iloc[0]
            year_positive = len(period_subset) == len(ROBUSTNESS_PERIODS) and bool(
                (period_subset["net_pnl"] > 0.0).all()
            )
            checks = {
                "BASE_NET_RETURN_POSITIVE": float(base["net_return"]) > 0.0,
                "STRESS_2X_NET_RETURN_POSITIVE": float(stress["net_return"]) > 0.0,
                "STRESS_2X_PROFIT_FACTOR_GTE_1_05": (
                    float(stress["profit_factor"]) >= MINIMUM_PROFIT_FACTOR_2X
                ),
                "STRESS_2X_MAX_DRAWDOWN_LTE_20PCT": (
                    float(stress["maximum_drawdown"]) <= MAXIMUM_DRAWDOWN_HARD
                ),
                "STRESS_2X_TRADES_GTE_75": int(stress["trade_count"]) >= MINIMUM_TRADES,
                "BOTH_2022_2023_NET_PNL_POSITIVE": year_positive,
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
                    float(be.iloc[0]["pf1_break_even_cost_multiplier"])
                    >= MINIMUM_BREAK_EVEN_COST_MULTIPLIER
                ),
                "CASH_FEASIBLE_BASE_AND_2X": (
                    float(base["minimum_cash"]) >= -1e-7
                    and float(stress["minimum_cash"]) >= -1e-7
                ),
                "MOMENTUM_BREAKOUT_STANDALONE_2X_POSITIVE": (
                    float(mb["net_return"]) > 0.0
                ),
                "RELATIVE_STRENGTH_STANDALONE_2X_POSITIVE": (
                    float(rs["net_return"]) > 0.0
                ),
                "NO_2024_OR_POST_2024_ACCESS": True,
            }
            for gate_id, passed in checks.items():
                rows.append(
                    {
                        "policy_id": policy_id,
                        "universe_id": universe,
                        "gate_id": gate_id,
                        "passed": bool(passed),
                    }
                )
                policy_pass = policy_pass and bool(passed)

            worst_return = min(worst_return, float(stress["net_return"]))
            worst_pf = min(worst_pf, float(stress["profit_factor"]))
            worst_dd = max(worst_dd, float(stress["maximum_drawdown"]))
            worst_turnover = max(worst_turnover, float(stress["turnover"]))

        selections.append(
            {
                "policy_id": policy_id,
                "hard_gates_passed": policy_pass,
                "worst_universe_2x_net_return": worst_return,
                "worst_universe_2x_profit_factor": worst_pf,
                "worst_universe_2x_maximum_drawdown": worst_dd,
                "worst_universe_2x_turnover": worst_turnover,
                "active_adaptive_component_count": active_component_count(policy_id),
            }
        )

    selection = pd.DataFrame.from_records(selections)
    passers = selection.loc[selection["hard_gates_passed"]].copy()
    if len(passers):
        passers = passers.sort_values(
            [
                "worst_universe_2x_net_return",
                "worst_universe_2x_profit_factor",
                "worst_universe_2x_maximum_drawdown",
                "worst_universe_2x_turnover",
                "active_adaptive_component_count",
                "policy_id",
            ],
            ascending=[False, False, True, True, True, True],
            kind="stable",
        )
        winner = str(passers.iloc[0]["policy_id"])
        selection["selected"] = selection["policy_id"] == winner
    else:
        selection["selected"] = False
    return pd.DataFrame.from_records(rows), selection


def report_payload(
    *,
    run_metrics: pd.DataFrame,
    selection: pd.DataFrame,
    event_count: int,
    freeze_commit: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    selected_rows = selection.loc[selection["selected"]]
    selected_policy = (
        str(selected_rows.iloc[0]["policy_id"])
        if len(selected_rows) == 1
        else None
    )
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
            "worst_universe_2x_maximum_drawdown": float(
                stress["maximum_drawdown"].max()
            ),
            "minimum_2x_trade_count": int(stress["trade_count"].min()),
        }

    if selected_policy is None:
        decision = "RD27_ADAPTIVE_LIFECYCLE_NO_FINALIST_REDESIGN_REQUIRED"
        next_stage = "RD28_ADAPTIVE_SIGNAL_REGIME_OR_LIFECYCLE_MODEL_REDESIGN_REQUIRED"
    else:
        decision = "RD27_ADAPTIVE_LIFECYCLE_POLICY_SELECTED_2024_CONFIRMATION_AUTHORIZED"
        next_stage = "RD28_CLEAN_2024_INTERNAL_CONFIRMATION"

    selected_freeze = {
        "schema_version": "rd27-p1-selected-lifecycle-policy-freeze-v1",
        "stage": "RD27_ADAPTIVE_LIFECYCLE_ABLATION_2022_2023",
        "selected_policy": selected_policy,
        "selection_basis": (
            "PASS_ALL_PREREGISTERED_HARD_GATES_THEN_FROZEN_RD27_TIE_BREAKS"
        ),
        "policy_summaries": policy_summaries,
        "freeze_commit": freeze_commit,
        "2022_2023_used_for_architecture_selection": True,
        "2024_accessed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
    }
    report = {
        "schema_version": "rd27-p1-adaptive-lifecycle-report-v1",
        "stage": "RD27_ADAPTIVE_LIFECYCLE_ABLATION_2022_2023",
        "status": "PASS",
        "decision": decision,
        "next_stage": next_stage,
        "p0b_freeze_commit": P0B_FREEZE_COMMIT,
        "integration_freeze_commit": freeze_commit,
        "focus_families": list(FOCUS_FAMILIES),
        "policy_count": len(POLICIES),
        "policies": list(POLICIES),
        "selected_policy": selected_policy,
        "policy_summaries": policy_summaries,
        "signal_event_count_2022_2023": event_count,
        "signal_source": "EXACT_RD26_FROZEN_SIGNAL_EVENT_LEDGER",
        "signal_source_sha256": RD26_SIGNAL_EVENTS_SHA256,
        "candidate_parameters_changed_after_economic_execution": False,
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
        "".join(
            f"{item['path']}:{item['sha256']}\n"
            for item in files
        ).encode("utf-8")
    ).hexdigest()
    return {
        "schema_version": "rd27-p1-output-manifest-v1",
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
        raise RunnerError("RD27 output manifest missing")
    manifest = load_json(manifest_path)
    by_name = {
        str(item["path"]): item
        for item in manifest.get("files", [])
        if isinstance(item, dict)
    }
    if set(by_name) != set(OUTPUT_NAMES):
        raise RunnerError("RD27 manifest output set drifted")
    for name in OUTPUT_NAMES:
        path = output / name
        if not path.is_file():
            raise RunnerError(f"RD27 output missing: {name}")
        item = by_name[name]
        if path.stat().st_size != int(item["bytes"]):
            raise RunnerError(f"RD27 byte-size drift: {name}")
        if sha256(path) != str(item["sha256"]):
            raise RunnerError(f"RD27 hash drift: {name}")

    report = load_json(output / "rd27-p1-adaptive-lifecycle-report-v1.json")
    if report.get("status") != "PASS":
        raise RunnerError("RD27 report status drifted")
    if report.get("candidate_parameters_changed_after_economic_execution") is not False:
        raise RunnerError("RD27 report indicates post-result parameter change")
    if report.get("2022_2023_used_for_architecture_selection") is not True:
        raise RunnerError("RD27 selection-use flag drifted")
    for field in ("2024_accessed", "post_2024_accessed", "production_authorized"):
        if report.get(field) is not False:
            raise RunnerError(f"RD27 prohibited flag true: {field}")

    trades = pd.read_csv(output / "trade-ledger.csv", low_memory=False)
    if len(trades):
        exits = pd.to_datetime(trades["exit_time"], utc=True, errors="raise")
        if bool((exits >= DATA_CUTOFF).any()):
            raise RunnerError("RD27 trade exit crossed into 2024")

    daily = pd.read_csv(output / "daily-equity.csv", low_memory=False)
    if len(daily):
        timestamps = pd.to_datetime(daily["timestamp"], utc=True, errors="raise")
        if bool((timestamps >= DATA_CUTOFF).any()):
            raise RunnerError("RD27 daily equity crossed into 2024")

    return {
        "status": "PASS",
        "decision": report["decision"],
        "selected_policy": report["selected_policy"],
        "signal_event_count_2022_2023": report["signal_event_count_2022_2023"],
        "manifest_sha256": sha256(manifest_path),
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
    if int(args.execute) + int(args.validate_only) != 1:
        raise RunnerError("choose exactly one runner mode")

    if args.validate_only:
        print(json.dumps(validate_outputs(repo), indent=2, sort_keys=True))
        return 0

    if not args.expected_freeze_commit:
        raise RunnerError("--expected-freeze-commit is required for execution")
    lineage = verify_lineage(repo, args.expected_freeze_commit)
    events = load_signal_events(repo)
    pairs = sorted(set(events["pair"].astype(str)))
    frames = load_feature_frames(raw_root=raw_root, pairs=pairs)
    state_frame = load_state_frame(raw_root)
    state_coverage = validate_signal_state_coverage(events, state_frame)
    state_summary = market_state_summary(state_frame)

    output = repo / OUTPUT
    output.mkdir(parents=True, exist_ok=False)

    audit = {
        "schema_version": "rd27-p1-input-conformance-audit-v1",
        "stage": "RD27_ADAPTIVE_LIFECYCLE_ABLATION_2022_2023",
        "lineage": lineage,
        "signal_source_path": RD26_SIGNAL_EVENTS.as_posix(),
        "signal_source_sha256": RD26_SIGNAL_EVENTS_SHA256,
        "signal_event_count": len(events),
        "pair_count": len(pairs),
        "pairs": pairs,
        "state_coverage": state_coverage,
        "selection_periods": {
            name: [start.isoformat(), end.isoformat()]
            for name, (start, end) in ROBUSTNESS_PERIODS.items()
        },
        "economic_execution_performed": True,
        "candidate_parameters_changed_after_economic_execution": False,
        "2022_2023_used_for_architecture_selection": True,
        "2024_accessed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
    }
    write_json(output / "input-and-conformance-audit.json", audit)

    run_metrics, trades, daily, routing, concentrations, break_even = run_all_portfolios(
        events=events,
        frames=frames,
        state_frame=state_frame,
    )
    control_parity = verify_control_parity(repo, run_metrics)
    periods = period_metrics(trades)
    reasons = exit_reason_summary(trades)
    gates, selection = evaluate_hard_gates(
        run_metrics=run_metrics,
        periods=periods,
        concentrations=concentrations,
        break_even=break_even,
    )
    report, selected_freeze = report_payload(
        run_metrics=run_metrics,
        selection=selection,
        event_count=len(events),
        freeze_commit=args.expected_freeze_commit,
    )
    report["control_parity_vs_rd26_time_fail"] = control_parity
    selected_freeze["control_parity_vs_rd26_time_fail"] = control_parity

    state_summary.to_csv(
        output / "market-state-summary.csv",
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
    write_json(output / "selected-lifecycle-policy-freeze.json", selected_freeze)
    write_json(output / "rd27-p1-adaptive-lifecycle-report-v1.json", report)
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
        print(f"RD27_P1_ERROR={exc}", file=sys.stderr)
        raise
