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

from spotbot.research.rd20_p2_minimal_pullback import (  # noqa: E402
    MembershipSnapshot,
    load_membership,
)
from spotbot.research.rd26_exit_architecture import (  # noqa: E402
    COST_MULTIPLIERS,
    DATA_CUTOFF,
    DATA_START,
    FAMILY_MOMENTUM_BREAKOUT,
    FAMILY_RELATIVE_STRENGTH_ROTATION,
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
from spotbot.research.rd27_lifecycle_replay import build_state_lookup  # noqa: E402
from spotbot.research.rd29_thesis_context import (  # noqa: E402
    POLICIES,
    ROUTER_TIME_FAIL_72_CONTROL,
    active_component_count,
)
from spotbot.research.rd29_thesis_replay import (  # noqa: E402
    membership_at,
    replay_rd29_policy,
    validate_replay_constants,
)

P0C_FREEZE_COMMIT = "24c66ea786e19f6acb8b5a167579197938fbc871"
P0B_FREEZE_COMMIT = "b58d1beabc5c1ca47d00d5a5c62bfce2e5da8bf6"
P0_FREEZE_COMMIT = "0e736639a42ab094b20c24d1155ab6879761e5fe"
RD28_RESULTS_COMMIT = "2ec43cfdab0a72ec10b9197c5a8dfb579595fe4b"

PROTOCOL = Path("data/research/rd29_p0/rd29-p0-thesis-confidence-lifecycle-protocol-v1.json")
PROTOCOL_SHA256 = "ad30538caf437aa67b803263795eb06185bc23073ba5de1c7eb59ce6710c41c1"
P0_AUDIT = Path("data/research/rd29_p0/rd29-p0-preregistration-audit-v1.json")
P0_AUDIT_SHA256 = "946048e43213860af815913a2f0beb62a348ef815f8c820b0f675dfae2312aef"
P0B_AUDIT = Path("data/research/rd29_p0b/rd29-p0b-thesis-context-engine-audit-v1.json")
P0B_AUDIT_SHA256 = "07c7ba7c1762b6539b9921be3d736e332609c1d6be494a7741f5a2019bf575e9"
P0C_AUDIT = Path("data/research/rd29_p0c/rd29-p0c-thesis-portfolio-replay-audit-v1.json")
P0C_AUDIT_SHA256 = "3b92f57b87d90a91d8e85fab480bb00f7377189f0730151d70e7cad7531fe10e"

ENGINE = Path("src/spotbot/research/rd29_thesis_context.py")
ENGINE_SHA256 = "53e189efd8eabe7b8f3560077e11c2d3dc9757229b6ec6553e501142ad90f2c4"
REPLAY = Path("src/spotbot/research/rd29_thesis_replay.py")
REPLAY_SHA256 = "c499946623cfde87812bd63442bd9d67fe7baa3ef7de55bfb83355140984144b"
MEMBERSHIP = Path("data/research/rd18_p3x_a3b_runtime/effective-operational-membership.csv")
MEMBERSHIP_SHA256 = "f7d6012ce8cd691583b9b6276ddf36371bfe0bbd9b28f810b676ad0177fb559e"

RD26_SIGNAL_EVENTS = Path("data/research/rd26_p1_runtime/signal-events-2022-2023.csv")
RD26_SIGNAL_EVENTS_SHA256 = "6462f576cee9681751368a7755d3ca51ebf945ced54ea7b7f18b47bc469ba725"
EXPECTED_SIGNAL_EVENT_COUNT = 7073
RD28_RUN_METRICS = Path("data/research/rd28_p1_runtime/portfolio-run-metrics.csv")

DEFAULT_RAW_ROOT = Path("data/raw/rd16b/kucoin")
OUTPUT = Path("data/research/rd29_p1_runtime")

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
    "selected-thesis-policy-freeze.json",
    "rd29-p1-thesis-confidence-lifecycle-report-v1.json",
)

HARD_GATES = (
    "BASE_NET_RETURN_POSITIVE",
    "STRESS_2X_NET_RETURN_POSITIVE",
    "STRESS_2X_PROFIT_FACTOR_GTE_1_05",
    "STRESS_2X_MAX_DRAWDOWN_LTE_20PCT",
    "STRESS_2X_TRADES_GTE_75",
    "BOTH_2022_2023_NET_PNL_POSITIVE",
    "STRESS_2X_LARGEST_WINNER_REMOVAL_POSITIVE",
    "STRESS_2X_LOAO_MIN_REMAINING_PNL_POSITIVE",
    "STRESS_2X_LOYO_MIN_REMAINING_PNL_POSITIVE",
    "PF1_BREAK_EVEN_COST_MULTIPLIER_GTE_2",
    "CASH_FEASIBLE_BASE_AND_2X",
    "MOMENTUM_BREAKOUT_STANDALONE_2X_POSITIVE",
    "RELATIVE_STRENGTH_STANDALONE_2X_POSITIVE",
    "NO_2024_OR_POST_2024_ACCESS",
)
CONTROL_PARITY_EXPECTED_ROWS = 18


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


def _assert_blob_unchanged(
    repo: Path,
    *,
    source_commit: str,
    relative: Path,
    label: str,
) -> str:
    source_blob = git(
        repo,
        "rev-parse",
        f"{source_commit}:{relative.as_posix()}",
    )
    current_blob = git(repo, "rev-parse", f"HEAD:{relative.as_posix()}")
    if source_blob != current_blob:
        raise RunnerError(f"{label} tracked blob drifted: {current_blob} != {source_blob}")
    return current_blob


def verify_lineage(
    repo: Path,
    expected_freeze_commit: str,
) -> dict[str, Any]:
    validate_replay_constants()
    if git(repo, "diff", "--cached", "--name-only", "--"):
        raise RunnerError("staged tracked changes exist before RD29-P1")
    if git(repo, "diff", "--name-only", "--"):
        raise RunnerError("unstaged tracked changes exist before RD29-P1")

    head = git(repo, "rev-parse", "HEAD")
    if head != expected_freeze_commit:
        raise RunnerError(f"RD29-P1 HEAD {head} != runner freeze {expected_freeze_commit}")
    parent = git(repo, "rev-parse", "HEAD^")
    if parent != P0C_FREEZE_COMMIT:
        raise RunnerError(f"RD29 runner-freeze parent {parent} != {P0C_FREEZE_COMMIT}")

    checks = (
        (PROTOCOL, PROTOCOL_SHA256, "RD29 protocol"),
        (P0_AUDIT, P0_AUDIT_SHA256, "RD29 P0 audit"),
        (P0B_AUDIT, P0B_AUDIT_SHA256, "RD29 P0B audit"),
        (P0C_AUDIT, P0C_AUDIT_SHA256, "RD29 P0C audit"),
        (ENGINE, ENGINE_SHA256, "RD29 context engine"),
        (REPLAY, REPLAY_SHA256, "RD29 portfolio replay"),
        (MEMBERSHIP, MEMBERSHIP_SHA256, "PIT membership"),
        (RD26_SIGNAL_EVENTS, RD26_SIGNAL_EVENTS_SHA256, "RD26 signals"),
    )
    for relative, expected_hash, label in checks:
        path = repo / relative
        if not path.is_file():
            raise RunnerError(f"{label} missing: {path}")
        actual = sha256(path)
        if actual != expected_hash:
            raise RunnerError(f"{label} hash drifted: {actual} != {expected_hash}")

    for relative, label in (
        (P0_AUDIT, "P0"),
        (P0B_AUDIT, "P0B"),
        (P0C_AUDIT, "P0C"),
    ):
        audit = load_json(repo / relative)
        if audit.get("status") != "PASS":
            raise RunnerError(f"RD29 {label} audit is not PASS")
        for field in (
            "economic_execution_performed",
            "2024_accessed",
            "post_2024_accessed",
            "production_authorized",
        ):
            if audit.get(field) is not False:
                raise RunnerError(f"RD29 {label} prohibited flag true: {field}")

    protocol = load_json(repo / PROTOCOL)
    expected_policies = set(protocol.get("candidate_ablation", {}).get("policies", {}).keys())
    if expected_policies != set(POLICIES):
        raise RunnerError("RD29 policy registry differs from preregistration")
    expected_gates = tuple(protocol.get("hard_gates_each_policy_each_universe", []))
    if expected_gates != HARD_GATES:
        raise RunnerError("RD29 hard-gate registry drifted")

    rd28_metrics_blob = _assert_blob_unchanged(
        repo,
        source_commit=RD28_RESULTS_COMMIT,
        relative=RD28_RUN_METRICS,
        label="RD28 control metrics",
    )
    return {
        "runner_freeze_commit": expected_freeze_commit,
        "p0c_freeze_commit": P0C_FREEZE_COMMIT,
        "p0b_freeze_commit": P0B_FREEZE_COMMIT,
        "p0_freeze_commit": P0_FREEZE_COMMIT,
        "protocol_sha256": PROTOCOL_SHA256,
        "p0_audit_sha256": P0_AUDIT_SHA256,
        "p0b_audit_sha256": P0B_AUDIT_SHA256,
        "p0c_audit_sha256": P0C_AUDIT_SHA256,
        "engine_sha256": ENGINE_SHA256,
        "replay_sha256": REPLAY_SHA256,
        "membership_sha256": MEMBERSHIP_SHA256,
        "signal_sha256": RD26_SIGNAL_EVENTS_SHA256,
        "rd28_run_metrics_blob": rd28_metrics_blob,
        "policies": list(POLICIES),
        "hard_gates": list(HARD_GATES),
    }


def load_signal_events(repo: Path) -> pd.DataFrame:
    events = pd.read_csv(repo / RD26_SIGNAL_EVENTS, low_memory=False)
    events["timestamp"] = pd.to_datetime(
        events["timestamp"],
        utc=True,
        errors="raise",
    )
    if len(events) != EXPECTED_SIGNAL_EVENT_COUNT:
        raise RunnerError(f"signal count {len(events)} != {EXPECTED_SIGNAL_EVENT_COUNT}")
    if bool((events["timestamp"] < DATA_START).any()):
        raise RunnerError("signal ledger contains pre-2022 event")
    if bool((events["timestamp"] >= DATA_CUTOFF).any()):
        raise RunnerError("signal ledger crossed sealed 2024 cutoff")
    return filter_robustness_events(events)


def selection_membership(
    snapshots: list[MembershipSnapshot],
) -> list[MembershipSnapshot]:
    result = [
        snapshot
        for snapshot in snapshots
        if pd.Timestamp(snapshot.effective_end) > DATA_START
        and pd.Timestamp(snapshot.decision_time) < DATA_CUTOFF
    ]
    if not result:
        raise RunnerError("no PIT membership overlaps RD29 selection window")
    return result


def required_feature_pairs(
    events: pd.DataFrame,
    snapshots: list[MembershipSnapshot],
) -> list[str]:
    pairs = set(events["pair"].astype(str))
    for snapshot in snapshots:
        pairs.update(pair for pair, _rank in snapshot.members)
    return sorted(pairs)


def validate_signal_membership_coverage(
    events: pd.DataFrame,
    snapshots: list[MembershipSnapshot],
) -> dict[str, Any]:
    mismatches: list[dict[str, Any]] = []
    for row in events.to_dict(orient="records"):
        timestamp = pd.Timestamp(row["timestamp"])
        universe = str(row["universe_id"])
        pair = str(row["pair"])
        expected_rank = int(row["membership_rank"])
        members = dict(
            membership_at(
                snapshots,
                universe_id=universe,
                timestamp=timestamp,
            )
        )
        actual_rank = members.get(pair)
        if actual_rank != expected_rank:
            mismatches.append(
                {
                    "timestamp": timestamp,
                    "universe_id": universe,
                    "pair": pair,
                    "expected_rank": expected_rank,
                    "actual_rank": actual_rank,
                }
            )
            if len(mismatches) >= 10:
                break
    if mismatches:
        raise RunnerError(f"signal/PIT membership mismatch sample: {mismatches}")
    return {
        "signal_rows_checked": len(events),
        "mismatch_count": 0,
    }


def load_feature_frames(
    *,
    raw_root: Path,
    pairs: list[str],
) -> dict[str, pd.DataFrame]:
    frames: dict[str, pd.DataFrame] = {}
    cutoff = DATA_CUTOFF.to_pydatetime()
    for index, pair in enumerate(pairs, start=1):
        path = raw_root / pair / "1h.parquet"
        if not path.is_file():
            raise RunnerError(f"raw 1h source missing: {path}")
        raw = pd.read_parquet(
            path,
            engine="pyarrow",
            filters=[("timestamp", "<", cutoff)],
        )
        frame = prepare_features(raw, cutoff=DATA_CUTOFF)
        frames[pair] = frame
        print(
            f"RD29_FEATURE_SOURCE={index}/{len(pairs)}:{pair}:"
            f"{len(frame)}:cutoff={DATA_CUTOFF.date()}",
            flush=True,
        )
    return frames


def load_state_frame(raw_root: Path) -> pd.DataFrame:
    path = raw_root / "BTC-USDT" / "1h.parquet"
    if not path.is_file():
        raise RunnerError(f"BTC state source missing: {path}")
    raw = pd.read_parquet(
        path,
        engine="pyarrow",
        filters=[("timestamp", "<", DATA_CUTOFF.to_pydatetime())],
    )
    frame = build_market_state_frame(raw, cutoff=DATA_CUTOFF)
    selection = frame.loc[
        (frame["timestamp"] >= DATA_START) & (frame["timestamp"] < DATA_CUTOFF)
    ].copy()
    if selection.empty or not bool(selection["state_ready"].all()):
        raise RunnerError("BTC state sensor incomplete in 2022-2023")
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
        raise RunnerError(f"market state unavailable at signal timestamps: {missing[:5]}")
    states = [lookup[int(pd.Timestamp(timestamp).value)] for timestamp in events["timestamp"]]
    counts = pd.Series(states, dtype="string").value_counts().sort_index()
    return {
        "covered_signal_events": len(states),
        "entry_state_event_counts": {str(state): int(count) for state, count in counts.items()},
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


def run_all_portfolios(
    *,
    events: pd.DataFrame,
    frames: dict[str, pd.DataFrame],
    state_frame: pd.DataFrame,
    membership: list[MembershipSnapshot],
):
    run_rows: list[dict[str, Any]] = []
    trade_sets: list[pd.DataFrame] = []
    daily_sets: list[pd.DataFrame] = []
    routing_rows: list[dict[str, Any]] = []
    concentration_rows: list[dict[str, Any]] = []
    break_even_rows: list[dict[str, Any]] = []

    for policy_id in POLICIES:
        for universe in ("C2", "D2", "E2"):
            portfolios = {
                "UNION_FOCUS": union_events(
                    events,
                    universe_id=universe,
                ),
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
                base_trades: pd.DataFrame | None = None
                for cost_multiplier in COST_MULTIPLIERS:
                    trades, daily, metrics, counters = replay_rd29_policy(
                        policy_id=policy_id,
                        portfolio_id=portfolio_id,
                        universe_id=universe,
                        cost_multiplier=cost_multiplier,
                        events=portfolio_events,
                        frames=frames,
                        state_frame=state_frame,
                        membership=membership,
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
                        base_trades = trades.copy()
                    print(
                        "RD29_PORTFOLIO="
                        f"{policy_id}:{portfolio_id}:{universe}:"
                        f"{cost_multiplier}x:"
                        f"net={metrics['net_return']:.6f}:"
                        f"pf={metrics['profit_factor']:.6f}:"
                        f"dd={metrics['maximum_drawdown']:.6f}:"
                        f"trades={metrics['trade_count']}",
                        flush=True,
                    )
                if base_trades is None:
                    raise RunnerError("base-cost trade ledger missing")
                break_even_rows.append(
                    {
                        "policy_id": policy_id,
                        "portfolio_id": portfolio_id,
                        "universe_id": universe,
                        "pf1_break_even_cost_multiplier": (
                            fixed_path_pf1_break_even_multiplier(base_trades)
                        ),
                        "method": ("BASE_ROUTED_QUANTITIES_AND_FILLS_FIXED_COST_SCALED_UNTIL_PF_1"),
                    }
                )

    return (
        pd.DataFrame.from_records(run_rows),
        (pd.concat(trade_sets, ignore_index=True) if trade_sets else pd.DataFrame()),
        (pd.concat(daily_sets, ignore_index=True) if daily_sets else pd.DataFrame()),
        pd.DataFrame.from_records(routing_rows),
        pd.DataFrame.from_records(concentration_rows),
        pd.DataFrame.from_records(break_even_rows),
    )


def verify_control_parity(
    repo: Path,
    run_metrics: pd.DataFrame,
) -> dict[str, Any]:
    frozen = pd.read_csv(repo / RD28_RUN_METRICS, low_memory=False)
    frozen = frozen.loc[frozen["policy_id"] == ROUTER_TIME_FAIL_72_CONTROL].copy()
    current = run_metrics.loc[run_metrics["policy_id"] == ROUTER_TIME_FAIL_72_CONTROL].copy()

    keys = ["portfolio_id", "universe_id", "cost_multiplier"]
    frozen = frozen.sort_values(keys, kind="stable").reset_index(drop=True)
    current = current.sort_values(keys, kind="stable").reset_index(drop=True)
    if len(frozen) != CONTROL_PARITY_EXPECTED_ROWS or len(current) != CONTROL_PARITY_EXPECTED_ROWS:
        raise RunnerError("RD29 control parity row cardinality drifted")
    for key in keys:
        if frozen[key].astype(str).tolist() != current[key].astype(str).tolist():
            raise RunnerError(f"RD29 control parity key drifted: {key}")

    numeric = (
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
    )
    max_error = 0.0
    for column in numeric:
        left = pd.to_numeric(frozen[column], errors="raise").astype(float)
        right = pd.to_numeric(current[column], errors="raise").astype(float)
        error = (left - right).abs()
        max_error = max(max_error, float(error.max()))
        tolerance = 1e-9 * (1.0 + left.abs())
        if bool((error > tolerance).any()):
            raise RunnerError(f"RD29 control parity mismatch: {column}")
    return {
        "passed": True,
        "row_count": CONTROL_PARITY_EXPECTED_ROWS,
        "maximum_numeric_absolute_error": max_error,
        "source": "RD28_ROUTER_TIME_FAIL_72_CONTROL",
        "rd28_run_metrics_sha256": sha256(repo / RD28_RUN_METRICS),
    }


def evaluate_hard_gates(
    *,
    run_metrics: pd.DataFrame,
    periods: pd.DataFrame,
    concentrations: pd.DataFrame,
    break_even: pd.DataFrame,
):
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
                *,
                _policy_id: str = policy_id,
                _universe: str = universe,
            ) -> pd.Series:
                subset = run_metrics.loc[
                    (run_metrics["policy_id"] == _policy_id)
                    & (run_metrics["portfolio_id"] == portfolio)
                    & (run_metrics["universe_id"] == _universe)
                    & (run_metrics["cost_multiplier"] == cost)
                ]
                if len(subset) != 1:
                    raise RunnerError(
                        f"metric cardinality drift: {_policy_id} {portfolio} {_universe} {cost}"
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
            conc = concentrations.loc[
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
            if len(conc) != 1 or len(be) != 1:
                raise RunnerError("diagnostic cardinality drifted")
            conc_row = conc.iloc[0]
            be_row = be.iloc[0]

            checks = {
                "BASE_NET_RETURN_POSITIVE": float(base["net_return"]) > 0.0,
                "STRESS_2X_NET_RETURN_POSITIVE": (float(stress["net_return"]) > 0.0),
                "STRESS_2X_PROFIT_FACTOR_GTE_1_05": (
                    float(stress["profit_factor"]) >= MINIMUM_PROFIT_FACTOR_2X
                ),
                "STRESS_2X_MAX_DRAWDOWN_LTE_20PCT": (
                    float(stress["maximum_drawdown"]) <= MAXIMUM_DRAWDOWN_HARD
                ),
                "STRESS_2X_TRADES_GTE_75": (int(stress["trade_count"]) >= MINIMUM_TRADES),
                "BOTH_2022_2023_NET_PNL_POSITIVE": (
                    len(period_subset) == len(ROBUSTNESS_PERIODS)
                    and bool((period_subset["net_pnl"] > 0.0).all())
                ),
                "STRESS_2X_LARGEST_WINNER_REMOVAL_POSITIVE": (
                    float(conc_row["net_pnl_without_largest_winner"]) > 0.0
                ),
                "STRESS_2X_LOAO_MIN_REMAINING_PNL_POSITIVE": (
                    float(conc_row["minimum_loao_remaining_net_pnl"]) > 0.0
                ),
                "STRESS_2X_LOYO_MIN_REMAINING_PNL_POSITIVE": (
                    float(conc_row["minimum_loyo_remaining_net_pnl"]) > 0.0
                ),
                "PF1_BREAK_EVEN_COST_MULTIPLIER_GTE_2": (
                    float(be_row["pf1_break_even_cost_multiplier"])
                    >= MINIMUM_BREAK_EVEN_COST_MULTIPLIER
                ),
                "CASH_FEASIBLE_BASE_AND_2X": (
                    float(base["minimum_cash"]) >= -1e-7 and float(stress["minimum_cash"]) >= -1e-7
                ),
                "MOMENTUM_BREAKOUT_STANDALONE_2X_POSITIVE": (float(mb["net_return"]) > 0.0),
                "RELATIVE_STRENGTH_STANDALONE_2X_POSITIVE": (float(rs["net_return"]) > 0.0),
                "NO_2024_OR_POST_2024_ACCESS": True,
            }
            if tuple(checks) != HARD_GATES:
                raise RunnerError("runtime hard-gate ordering drifted")
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
            worst_turnover = max(
                worst_turnover,
                float(stress["turnover"]),
            )

        selections.append(
            {
                "policy_id": policy_id,
                "hard_gates_passed": policy_pass,
                "worst_universe_2x_net_return": worst_return,
                "worst_universe_2x_profit_factor": worst_pf,
                "worst_universe_2x_maximum_drawdown": worst_dd,
                "worst_universe_2x_turnover": worst_turnover,
                "active_adaptive_component_count": (active_component_count(policy_id)),
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


def make_report(
    *,
    run_metrics: pd.DataFrame,
    selection: pd.DataFrame,
    event_count: int,
    required_pair_count: int,
    freeze_commit: str,
    control_parity: dict[str, Any],
):
    selected = selection.loc[selection["selected"]]
    selected_policy = str(selected.iloc[0]["policy_id"]) if len(selected) == 1 else None

    summaries: dict[str, dict[str, Any]] = {}
    for policy_id in POLICIES:
        stress = run_metrics.loc[
            (run_metrics["policy_id"] == policy_id)
            & (run_metrics["portfolio_id"] == "UNION_FOCUS")
            & (run_metrics["cost_multiplier"] == 2.0)
        ]
        summaries[policy_id] = {
            "worst_universe_2x_net_return": float(stress["net_return"].min()),
            "worst_universe_2x_profit_factor": float(stress["profit_factor"].min()),
            "worst_universe_2x_maximum_drawdown": float(stress["maximum_drawdown"].max()),
            "minimum_2x_trade_count": int(stress["trade_count"].min()),
        }

    if selected_policy is None:
        decision = "RD29_THESIS_CONFIDENCE_LIFECYCLE_NO_FINALIST_REDESIGN_REQUIRED"
        next_stage = "RD30_THESIS_CONFIDENCE_OR_SIGNAL_FAMILY_ARCHITECTURE_REDESIGN_REQUIRED"
    else:
        decision = "RD29_THESIS_CONFIDENCE_LIFECYCLE_POLICY_SELECTED_2024_CONFIRMATION_AUTHORIZED"
        next_stage = "RD30_CLEAN_2024_INTERNAL_CONFIRMATION"

    freeze = {
        "schema_version": "rd29-p1-selected-thesis-policy-freeze-v1",
        "selected_policy": selected_policy,
        "selection_basis": ("PASS_ALL_PREREGISTERED_HARD_GATES_THEN_FROZEN_RD29_TIE_BREAKS"),
        "runner_freeze_commit": freeze_commit,
        "policy_summaries": summaries,
        "control_parity_vs_rd28": control_parity,
        "2022_2023_used_for_architecture_selection": True,
        "2024_accessed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
    }
    report = {
        "schema_version": "rd29-p1-thesis-confidence-lifecycle-report-v1",
        "stage": "RD29_THESIS_CONFIDENCE_LIFECYCLE_2022_2023",
        "status": "PASS",
        "decision": decision,
        "next_stage": next_stage,
        "p0_freeze_commit": P0_FREEZE_COMMIT,
        "p0b_freeze_commit": P0B_FREEZE_COMMIT,
        "p0c_freeze_commit": P0C_FREEZE_COMMIT,
        "runner_freeze_commit": freeze_commit,
        "selected_policy": selected_policy,
        "policy_summaries": summaries,
        "signal_event_count_2022_2023": event_count,
        "required_pit_feature_pair_count": required_pair_count,
        "signal_source_sha256": RD26_SIGNAL_EVENTS_SHA256,
        "membership_source_sha256": MEMBERSHIP_SHA256,
        "control_parity_vs_rd28": control_parity,
        "candidate_parameters_changed_after_economic_execution": False,
        "2022_2023_used_for_architecture_selection": True,
        "2024_accessed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
    }
    return report, freeze


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
        "schema_version": "rd29-p1-output-manifest-v1",
        "decision": decision,
        "deterministic_hash": deterministic,
        "files": files,
        "2024_accessed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
    }


def validate_outputs(repo: Path) -> dict[str, Any]:
    output = repo / OUTPUT
    manifest_path = output / "output-manifest.json"
    if not manifest_path.is_file():
        raise RunnerError("RD29 output manifest missing")
    manifest = load_json(manifest_path)
    items = {
        str(item["path"]): item for item in manifest.get("files", []) if isinstance(item, dict)
    }
    if set(items) != set(OUTPUT_NAMES):
        raise RunnerError("RD29 manifest output set drifted")
    for name in OUTPUT_NAMES:
        path = output / name
        if not path.is_file():
            raise RunnerError(f"RD29 output missing: {name}")
        if sha256(path) != str(items[name]["sha256"]):
            raise RunnerError(f"RD29 output hash drift: {name}")

    report = load_json(output / "rd29-p1-thesis-confidence-lifecycle-report-v1.json")
    if report.get("status") != "PASS":
        raise RunnerError("RD29 report status drifted")
    parity = report.get("control_parity_vs_rd28")
    if not isinstance(parity, dict) or parity.get("passed") is not True:
        raise RunnerError("RD29 control parity missing or failed")
    if parity.get("row_count") != CONTROL_PARITY_EXPECTED_ROWS:
        raise RunnerError("RD29 control parity row count drifted")
    if report.get("candidate_parameters_changed_after_economic_execution") is not False:
        raise RunnerError("RD29 report indicates post-result tuning")
    for field in (
        "2024_accessed",
        "post_2024_accessed",
        "production_authorized",
    ):
        if report.get(field) is not False:
            raise RunnerError(f"RD29 prohibited report flag true: {field}")

    trades = pd.read_csv(output / "trade-ledger.csv", low_memory=False)
    if len(trades):
        exits = pd.to_datetime(trades["exit_time"], utc=True, errors="raise")
        if bool((exits >= DATA_CUTOFF).any()):
            raise RunnerError("RD29 trade crossed sealed 2024 cutoff")
    daily = pd.read_csv(output / "daily-equity.csv", low_memory=False)
    if len(daily):
        timestamps = pd.to_datetime(
            daily["timestamp"],
            utc=True,
            errors="raise",
        )
        if bool((timestamps >= DATA_CUTOFF).any()):
            raise RunnerError("RD29 daily equity crossed 2024 cutoff")

    return {
        "status": "PASS",
        "decision": report["decision"],
        "selected_policy": report["selected_policy"],
        "signal_event_count_2022_2023": (report["signal_event_count_2022_2023"]),
        "control_parity_rows": parity["row_count"],
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
        raise RunnerError("--expected-freeze-commit is required")

    lineage = verify_lineage(repo, args.expected_freeze_commit)
    events = load_signal_events(repo)
    all_membership = load_membership(repo / MEMBERSHIP)
    membership = selection_membership(all_membership)
    membership_check = validate_signal_membership_coverage(
        events,
        membership,
    )
    pairs = required_feature_pairs(events, membership)
    frames = load_feature_frames(raw_root=raw_root, pairs=pairs)
    state_frame = load_state_frame(raw_root)
    state_check = validate_signal_state_coverage(events, state_frame)
    state_summary = market_state_summary(state_frame)

    output = repo / OUTPUT
    output.mkdir(parents=True, exist_ok=False)

    write_json(
        output / "input-and-conformance-audit.json",
        {
            "schema_version": "rd29-p1-input-conformance-audit-v1",
            "stage": "RD29_THESIS_CONFIDENCE_LIFECYCLE_2022_2023",
            "lineage": lineage,
            "signal_event_count": len(events),
            "membership_snapshot_count": len(membership),
            "required_pit_feature_pair_count": len(pairs),
            "required_pit_feature_pairs": pairs,
            "membership_signal_coverage": membership_check,
            "signal_state_coverage": state_check,
            "economic_execution_performed": True,
            "candidate_parameters_changed_after_economic_execution": False,
            "2022_2023_used_for_architecture_selection": True,
            "2024_accessed": False,
            "post_2024_accessed": False,
            "production_authorized": False,
        },
    )

    (
        run_metrics,
        trades,
        daily,
        routing,
        concentrations,
        break_even,
    ) = run_all_portfolios(
        events=events,
        frames=frames,
        state_frame=state_frame,
        membership=membership,
    )
    parity = verify_control_parity(repo, run_metrics)
    periods = period_metrics(trades)
    reasons = exit_reason_summary(trades)
    gates, selection = evaluate_hard_gates(
        run_metrics=run_metrics,
        periods=periods,
        concentrations=concentrations,
        break_even=break_even,
    )
    report, selected_freeze = make_report(
        run_metrics=run_metrics,
        selection=selection,
        event_count=len(events),
        required_pair_count=len(pairs),
        freeze_commit=args.expected_freeze_commit,
        control_parity=parity,
    )

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
    write_json(
        output / "selected-thesis-policy-freeze.json",
        selected_freeze,
    )
    write_json(
        output / "rd29-p1-thesis-confidence-lifecycle-report-v1.json",
        report,
    )
    write_json(
        output / "output-manifest.json",
        output_manifest(output, report["decision"]),
    )

    print(json.dumps(validate_outputs(repo), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"RD29_P1_ERROR={exc}", file=sys.stderr)
        raise
