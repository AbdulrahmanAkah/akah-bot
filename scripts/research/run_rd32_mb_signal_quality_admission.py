from __future__ import annotations

import argparse
import hashlib
import importlib.util
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
    FAMILY_MOMENTUM_BREAKOUT,
    FAMILY_RELATIVE_STRENGTH_ROTATION,
    MAXIMUM_DRAWDOWN_HARD,
    MINIMUM_BREAK_EVEN_COST_MULTIPLIER,
    MINIMUM_PROFIT_FACTOR_2X,
    MINIMUM_TRADES,
    ROBUSTNESS_PERIODS,
    concentration_diagnostics,
    exit_reason_summary,
    fixed_path_pf1_break_even_multiplier,
    period_metrics,
)
from spotbot.research.rd32_mb_signal_quality_admission import (  # noqa: E402
    MB_BREADTH_ACCELERATION_CONFIRMATION,
    MB_CROSS_SECTIONAL_BREAKOUT_LEADER,
    MB_RELATIVE_STRENGTH_LEADER_CONFIRMATION,
    RD31_REGIME_HYSTERESIS_CONTROL,
    active_component_count,
)
from spotbot.research.rd32_mb_signal_quality_replay import (  # noqa: E402
    replay_rd32_policy,
)

SCHEMA_VERSION = "rd32-mb-signal-quality-economic-runner-v1"

P2C_FREEZE_COMMIT = "c23659615c2e96c357cb4b3545a2b205b22e5a7a"
P2D_ORIGINAL_FREEZE_COMMIT = "06b7e1ebc99abfed015f2d9676e5d1d2f409d6f1"
P2D_BLOB_RECOVERY_COMMIT = "00449dc89029a41dd3d1dcc31d43e64b424f9594"
P2B_FREEZE_COMMIT = "119d9b9b34276ba52e1d5fe4ac914cda20c2ced5"
P2_COMMIT = "1384aadda84623440d95c48998e16c227b048c2e"
P1_RESULTS_COMMIT = "4df12b682108eddf8ecba0239bb26f1cb8392f79"
RD31_RESULTS_COMMIT = "f95a165e3c0a17dc53b021740f4e0810148af28f"

P2_PROTOCOL = Path(
    "data/research/rd32_p2/rd32-p2-mb-signal-quality-admission-redesign-protocol-v1.json"
)
P2_PROTOCOL_SHA256 = "88fea5c729bef3e815a6a8f731b1614720e9fc402e7e550c4288ae6e39ef4292"
P2_AUDIT = Path("data/research/rd32_p2/rd32-p2-mb-signal-quality-admission-redesign-audit-v1.json")
P2_AUDIT_SHA256 = "fee5c705b220005c75804a14d52f4a970a3054ebdd887f8d2672da1d374f0f3d"
P2B_ENGINE = Path("src/spotbot/research/rd32_mb_signal_quality_admission.py")
P2B_ENGINE_SHA256 = "c8c2d02412356c0afc6194f5a61be945996a7e731a07edc691a2fa00be25f5b6"
P2B_TEST = Path("tests/research/test_rd32_mb_signal_quality_admission.py")
P2B_TEST_SHA256 = "0f5cc81e89c138f6ec5e3c1ecfbd599b387e35d4384871ea90bc30e7c00eff65"
P2B_AUDIT = Path("data/research/rd32_p2b/rd32-p2b-mb-signal-quality-admission-engine-audit-v1.json")
P2B_AUDIT_SHA256 = "747d9cccb9b984188700e0f708e684d5602106b65b4eeb68ec21ae25b7fe6aae"
P2C_REPLAY = Path("src/spotbot/research/rd32_mb_signal_quality_replay.py")
P2C_REPLAY_SHA256 = "7c8a0ea168a16367da62fa32d6bf797d78c03789ce906067f5fe252599f543c0"
P2C_TEST = Path("tests/research/test_rd32_mb_signal_quality_replay.py")
P2C_TEST_SHA256 = "4f80b3329a51c8474f9929f2bec56d4a0d2dc73b9dba7aeabf4a6de3deae5b22"
P2C_AUDIT = Path("data/research/rd32_p2c/rd32-p2c-mb-signal-quality-portfolio-replay-audit-v1.json")
P2C_AUDIT_SHA256 = "6303c812c7fa2bfe907ea8037e9c1b24e904b07ece9b427e338574d5155ed519"

RD31_RUNNER = Path("scripts/research/run_rd31_market_regime_admission_governor.py")
RD31_RUNNER_BLOB_SHA = "3b5c6916e34be6c9642702fe2807e42e445ee083"
RD31_RUN_METRICS = Path("data/research/rd31_p1_runtime/portfolio-run-metrics.csv")
RD31_RUN_METRICS_BLOB_SHA = "5bf3d95677876442d622088309d78e1e727355ba"
RD31_REPORT = Path(
    "data/research/rd31_p1_runtime/rd31-p1-market-regime-admission-governor-report-v1.json"
)
RD31_REPORT_SHA256 = "0afff069e6c8838e8944a93b2cbb0154c989eb6cb664e89cbf470060372f9e4d"

DEFAULT_RAW_ROOT = Path("data/raw/rd16b/kucoin")
OUTPUT = Path("data/research/rd32_p3_runtime")

EXPECTED_POLICIES = (
    RD31_REGIME_HYSTERESIS_CONTROL,
    MB_CROSS_SECTIONAL_BREAKOUT_LEADER,
    MB_BREADTH_ACCELERATION_CONFIRMATION,
    MB_RELATIVE_STRENGTH_LEADER_CONFIRMATION,
)
EXPECTED_UNIVERSES = ("C2", "D2", "E2")
EXPECTED_PORTFOLIOS = (
    "UNION_FOCUS",
    FAMILY_MOMENTUM_BREAKOUT,
    FAMILY_RELATIVE_STRENGTH_ROTATION,
)
EXPECTED_ECONOMIC_REPLAYS = 72
BASELINE_PARITY_EXPECTED_ROWS = 18
RS_INVARIANCE_EXPECTED_COMPARISONS = 18

ORIGINAL_14_GATES = (
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
NEW_MB_YEAR_GATES = (
    "MOMENTUM_BREAKOUT_2022_2X_NET_PNL_POSITIVE",
    "MOMENTUM_BREAKOUT_2023_2X_NET_PNL_POSITIVE",
)
HARD_GATES = (*ORIGINAL_14_GATES, *NEW_MB_YEAR_GATES)

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
    "baseline-parity-vs-rd31.json",
    "rs-only-invariance.json",
    "selected-mb-signal-quality-policy-freeze.json",
    "rd32-p3-mb-signal-quality-admission-report-v1.json",
)

SUCCESS_DECISION = "RD32_MB_SIGNAL_QUALITY_ADMISSION_POLICY_SELECTED_2024_CONFIRMATION_AUTHORIZED"
FAILURE_DECISION = (
    "RD32_MB_SIGNAL_QUALITY_ADMISSION_NO_FINALIST_SIGNAL_FAMILY_ARCHITECTURE_REDESIGN_REQUIRED"
)
SUCCESS_NEXT = "RD33_CLEAN_2024_INTERNAL_CONFIRMATION"
FAILURE_NEXT = "RD33_SIGNAL_FAMILY_ARCHITECTURE_REDESIGN_REQUIRED"


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


def load_rd31_runner() -> Any:
    path = ROOT / RD31_RUNNER
    spec = importlib.util.spec_from_file_location(
        "_rd31_frozen_economic_runner",
        path,
    )
    if spec is None or spec.loader is None:
        raise RunnerError("cannot load frozen RD31 runner")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def verify_lineage(
    repo: Path,
    expected_freeze_commit: str,
) -> dict[str, Any]:
    if git(repo, "diff", "--cached", "--name-only", "--"):
        raise RunnerError("staged tracked changes exist before RD32-P3")
    if git(repo, "diff", "--name-only", "--"):
        raise RunnerError("unstaged tracked changes exist before RD32-P3")

    head = git(repo, "rev-parse", "HEAD")
    if head != expected_freeze_commit:
        raise RunnerError(f"RD32-P3 HEAD {head} != runner freeze {expected_freeze_commit}")
    parent = git(repo, "rev-parse", "HEAD^")
    grandparent = git(repo, "rev-parse", "HEAD^^")
    great_grandparent = git(repo, "rev-parse", "HEAD^^^")
    if parent != P2D_BLOB_RECOVERY_COMMIT:
        raise RunnerError("RD32 final runner-freeze parent is not the frozen blob recovery")
    if grandparent != P2D_ORIGINAL_FREEZE_COMMIT:
        raise RunnerError("RD32 blob-recovery parent is not the original P2D freeze")
    if great_grandparent != P2C_FREEZE_COMMIT:
        raise RunnerError("RD32 original-P2D parent is not the frozen P2C replay")

    checks = (
        (P2_PROTOCOL, P2_PROTOCOL_SHA256, "P2 protocol"),
        (P2_AUDIT, P2_AUDIT_SHA256, "P2 audit"),
        (P2B_ENGINE, P2B_ENGINE_SHA256, "P2B admission engine"),
        (P2B_TEST, P2B_TEST_SHA256, "P2B admission tests"),
        (P2B_AUDIT, P2B_AUDIT_SHA256, "P2B audit"),
        (P2C_REPLAY, P2C_REPLAY_SHA256, "P2C replay"),
        (P2C_TEST, P2C_TEST_SHA256, "P2C replay tests"),
        (P2C_AUDIT, P2C_AUDIT_SHA256, "P2C audit"),
        (RD31_REPORT, RD31_REPORT_SHA256, "RD31 frozen report"),
    )
    verified: dict[str, str] = {}
    for relative, expected, label in checks:
        path = repo / relative
        if not path.is_file():
            raise RunnerError(f"{label} missing: {path}")
        actual = sha256(path)
        if actual != expected:
            raise RunnerError(f"{label} hash drifted: {actual} != {expected}")
        verified[relative.as_posix()] = actual

    if (
        git(
            repo,
            "rev-parse",
            f"HEAD:{RD31_RUNNER.as_posix()}",
        )
        != RD31_RUNNER_BLOB_SHA
    ):
        raise RunnerError("frozen RD31 runner blob drifted")
    if (
        git(
            repo,
            "rev-parse",
            f"{RD31_RESULTS_COMMIT}:{RD31_RUN_METRICS.as_posix()}",
        )
        != RD31_RUN_METRICS_BLOB_SHA
    ):
        raise RunnerError("frozen RD31 metrics blob drifted")

    p2 = load_json(repo / P2_AUDIT)
    p2b = load_json(repo / P2B_AUDIT)
    p2c = load_json(repo / P2C_AUDIT)
    for label, audit in (("P2", p2), ("P2B", p2b), ("P2C", p2c)):
        if audit.get("status") != "PASS":
            raise RunnerError(f"RD32 {label} audit not PASS")
        for field in (
            "economic_execution_performed",
            "raw_market_data_loaded",
            "candidate_results_observed",
            "2024_accessed",
            "post_2024_accessed",
            "production_authorized",
        ):
            if audit.get(field) is not False:
                raise RunnerError(f"RD32 {label} prohibited flag true: {field}")

    if p2.get("hard_gate_count") != 16:
        raise RunnerError("P2 hard-gate count drifted")
    if p2.get("policy_count") != 4:
        raise RunnerError("P2 policy count drifted")
    if p2c.get("portfolio_replay_implemented") is not True:
        raise RunnerError("P2C replay not implemented")
    if p2c.get("economic_runner_implemented") is not False:
        raise RunnerError("P2C unexpectedly implemented runner")
    if p2c.get("next_stage") != ("RD32_P2D_FREEZE_MB_SIGNAL_QUALITY_ECONOMIC_RUNNER_PRE_EXECUTION"):
        raise RunnerError("P2C next stage drifted")

    protocol = load_json(repo / P2_PROTOCOL)
    if tuple(protocol.get("candidate_policy_order", [])) != EXPECTED_POLICIES:
        raise RunnerError("P2 policy order drifted")
    if tuple(protocol.get("hard_gates", [])) != HARD_GATES:
        raise RunnerError("P2 hard-gate registry drifted")
    matrix = protocol.get("economic_matrix_for_later_execution")
    if not isinstance(matrix, dict) or matrix.get("expected_rows") != 72:
        raise RunnerError("P2 economic matrix drifted")

    rd31_report = load_json(repo / RD31_REPORT)
    if rd31_report.get("status") != "PASS":
        raise RunnerError("RD31 report not PASS")
    if rd31_report.get("runner_freeze_commit") != ("bf5c69f64e47e5a90684954c7416d0f3d749c645"):
        raise RunnerError("RD31 report lineage drifted")
    if rd31_report.get("2024_accessed") is not False:
        raise RunnerError("RD31 report crossed 2024")

    return {
        "runner_freeze_commit": expected_freeze_commit,
        "p2d_blob_recovery_commit": P2D_BLOB_RECOVERY_COMMIT,
        "p2d_original_freeze_commit": P2D_ORIGINAL_FREEZE_COMMIT,
        "p2c_freeze_commit": P2C_FREEZE_COMMIT,
        "p2b_freeze_commit": P2B_FREEZE_COMMIT,
        "p2_commit": P2_COMMIT,
        "p1_results_commit": P1_RESULTS_COMMIT,
        "rd31_results_commit": RD31_RESULTS_COMMIT,
        "verified_sha256": verified,
        "rd31_runner_blob_sha": RD31_RUNNER_BLOB_SHA,
        "rd31_metrics_blob_sha": RD31_RUN_METRICS_BLOB_SHA,
        "policies": list(EXPECTED_POLICIES),
        "hard_gates": list(HARD_GATES),
        "expected_economic_replays": EXPECTED_ECONOMIC_REPLAYS,
    }


def run_all_portfolios(
    *,
    rd31: Any,
    events: pd.DataFrame,
    frames: dict[str, pd.DataFrame],
    state_frame: pd.DataFrame,
    membership: list[Any],
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

    replay_count = 0
    for policy_id in EXPECTED_POLICIES:
        for universe in EXPECTED_UNIVERSES:
            portfolios = rd31._portfolio_events(events, universe)
            for portfolio_id, portfolio_events in portfolios.items():
                if portfolio_id not in EXPECTED_PORTFOLIOS:
                    raise RunnerError(f"unexpected portfolio: {portfolio_id}")
                base_trades: pd.DataFrame | None = None
                for cost_multiplier in COST_MULTIPLIERS:
                    (
                        trades,
                        daily,
                        metrics,
                        counters,
                    ) = replay_rd32_policy(
                        policy_id=policy_id,
                        portfolio_id=portfolio_id,
                        universe_id=universe,
                        cost_multiplier=cost_multiplier,
                        events=portfolio_events,
                        raw_focus_events=events,
                        frames=frames,
                        state_frame=state_frame,
                        membership=membership,
                    )
                    replay_count += 1
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
                        "RD32_PORTFOLIO="
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

    if replay_count != EXPECTED_ECONOMIC_REPLAYS:
        raise RunnerError(f"economic replay count {replay_count} != {EXPECTED_ECONOMIC_REPLAYS}")

    return (
        pd.DataFrame.from_records(run_rows),
        pd.concat(trade_sets, ignore_index=True) if trade_sets else pd.DataFrame(),
        pd.concat(daily_sets, ignore_index=True) if daily_sets else pd.DataFrame(),
        pd.DataFrame.from_records(routing_rows),
        pd.DataFrame.from_records(concentration_rows),
        pd.DataFrame.from_records(break_even_rows),
    )


def numeric_parity(
    *,
    frozen: pd.DataFrame,
    current: pd.DataFrame,
    keys: list[str],
    numeric: tuple[str, ...],
    label: str,
    expected_rows: int,
) -> dict[str, Any]:
    frozen = frozen.sort_values(keys, kind="stable").reset_index(drop=True)
    current = current.sort_values(keys, kind="stable").reset_index(drop=True)
    if len(frozen) != expected_rows or len(current) != expected_rows:
        raise RunnerError(
            f"{label} row cardinality: {len(frozen)} != {len(current)} != {expected_rows}"
        )
    for key in keys:
        if frozen[key].astype(str).tolist() != current[key].astype(str).tolist():
            raise RunnerError(f"{label} key mismatch: {key}")
    maximum_error = 0.0
    for column in numeric:
        left = pd.to_numeric(frozen[column], errors="raise").astype(float)
        right = pd.to_numeric(current[column], errors="raise").astype(float)
        error = (left - right).abs()
        current_max = float(error.max()) if len(error) else 0.0
        maximum_error = max(maximum_error, current_max)
        tolerance = 1e-9 * (1.0 + left.abs())
        if bool((error > tolerance).any()):
            raise RunnerError(f"{label} numeric mismatch: {column}")
    return {
        "passed": True,
        "row_count": expected_rows,
        "maximum_numeric_absolute_error": maximum_error,
    }


def verify_control_parity_vs_rd31(
    repo: Path,
    run_metrics: pd.DataFrame,
) -> dict[str, Any]:
    frozen = pd.read_csv(repo / RD31_RUN_METRICS, low_memory=False)
    frozen = frozen.loc[frozen["policy_id"] == "REGIME_HYSTERESIS_ADMISSION_GOVERNOR"].copy()
    current = run_metrics.loc[run_metrics["policy_id"] == RD31_REGIME_HYSTERESIS_CONTROL].copy()
    parity = numeric_parity(
        frozen=frozen,
        current=current,
        keys=[
            "portfolio_id",
            "universe_id",
            "cost_multiplier",
        ],
        numeric=(
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
        ),
        label="RD32 control parity vs RD31 Hysteresis",
        expected_rows=BASELINE_PARITY_EXPECTED_ROWS,
    )
    parity["source_policy"] = "REGIME_HYSTERESIS_ADMISSION_GOVERNOR"
    parity["current_policy"] = RD31_REGIME_HYSTERESIS_CONTROL
    return parity


def verify_rs_only_invariance(
    *,
    run_metrics: pd.DataFrame,
    trades: pd.DataFrame,
) -> dict[str, Any]:
    comparisons: list[dict[str, Any]] = []
    numeric_columns = (
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

    control_metrics = run_metrics.loc[
        (run_metrics["policy_id"] == RD31_REGIME_HYSTERESIS_CONTROL)
        & (run_metrics["portfolio_id"] == FAMILY_RELATIVE_STRENGTH_ROTATION)
    ].copy()

    for policy_id in EXPECTED_POLICIES[1:]:
        candidate = run_metrics.loc[
            (run_metrics["policy_id"] == policy_id)
            & (run_metrics["portfolio_id"] == FAMILY_RELATIVE_STRENGTH_ROTATION)
        ].copy()
        parity = numeric_parity(
            frozen=control_metrics,
            current=candidate,
            keys=["universe_id", "cost_multiplier"],
            numeric=numeric_columns,
            label=f"RS-only invariance {policy_id}",
            expected_rows=6,
        )
        comparisons.append(
            {
                "policy_id": policy_id,
                **parity,
            }
        )

    if len(comparisons) != 3:
        raise RunnerError("RS-only comparison policy count drifted")

    # Trade-level parity is stronger than summary-metric parity.
    control_trades = trades.loc[
        (trades["policy_id"] == RD31_REGIME_HYSTERESIS_CONTROL)
        & (trades["portfolio_id"] == FAMILY_RELATIVE_STRENGTH_ROTATION)
    ].copy()
    exact_columns = [
        "universe_id",
        "cost_multiplier",
        "pair",
        "signal_time",
        "entry_time",
        "exit_time",
        "exit_reason",
        "support_families",
    ]
    numeric_trade_columns = [
        "entry_price",
        "exit_price",
        "quantity",
        "entry_cost",
        "exit_cost",
        "net_pnl",
    ]
    trade_checks: list[dict[str, Any]] = []
    for policy_id in EXPECTED_POLICIES[1:]:
        candidate = trades.loc[
            (trades["policy_id"] == policy_id)
            & (trades["portfolio_id"] == FAMILY_RELATIVE_STRENGTH_ROTATION)
        ].copy()
        left = control_trades.sort_values(
            exact_columns,
            kind="stable",
        ).reset_index(drop=True)
        right = candidate.sort_values(
            exact_columns,
            kind="stable",
        ).reset_index(drop=True)
        if len(left) != len(right):
            raise RunnerError(f"RS-only trade count drifted: {policy_id}")
        for column in exact_columns:
            if left[column].astype(str).tolist() != right[column].astype(str).tolist():
                raise RunnerError(f"RS-only trade key drifted: {policy_id} {column}")
        max_error = 0.0
        for column in numeric_trade_columns:
            a = pd.to_numeric(left[column], errors="raise").astype(float)
            b = pd.to_numeric(right[column], errors="raise").astype(float)
            error = (a - b).abs()
            maximum = float(error.max()) if len(error) else 0.0
            max_error = max(max_error, maximum)
            tolerance = 1e-9 * (1.0 + a.abs())
            if bool((error > tolerance).any()):
                raise RunnerError(f"RS-only trade numeric drift: {policy_id} {column}")
        trade_checks.append(
            {
                "policy_id": policy_id,
                "trade_row_count": len(left),
                "maximum_numeric_absolute_error": max_error,
                "passed": True,
            }
        )

    comparison_rows = sum(int(item["row_count"]) for item in comparisons)
    if comparison_rows != RS_INVARIANCE_EXPECTED_COMPARISONS:
        raise RunnerError("RS-only metric comparison row count drifted")

    return {
        "passed": True,
        "metric_comparisons": comparisons,
        "trade_comparisons": trade_checks,
        "metric_comparison_rows": comparison_rows,
        "rs_path_changed": False,
    }


def gate_checks_for_one(
    *,
    base: pd.Series,
    stress: pd.Series,
    mb: pd.Series,
    rs: pd.Series,
    union_periods: pd.DataFrame,
    mb_periods: pd.DataFrame,
    concentration: pd.Series,
    break_even: pd.Series,
) -> dict[str, bool]:
    period_ids = set(union_periods["period_id"].astype(str))
    expected_period_ids = set(ROBUSTNESS_PERIODS)
    mb_period_ids = set(mb_periods["period_id"].astype(str))
    if period_ids != expected_period_ids:
        raise RunnerError("UNION robustness period registry drifted")
    if mb_period_ids != expected_period_ids:
        raise RunnerError("MB robustness period registry drifted")

    def mb_period_pnl(period_id: str) -> float:
        subset = mb_periods.loc[mb_periods["period_id"].astype(str) == period_id]
        if len(subset) != 1:
            raise RunnerError(f"MB period cardinality drifted: {period_id}")
        return float(subset.iloc[0]["net_pnl"])

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
        "BOTH_2022_2023_NET_PNL_POSITIVE": bool((union_periods["net_pnl"] > 0.0).all()),
        "STRESS_2X_LARGEST_WINNER_REMOVAL_POSITIVE": (
            float(concentration["net_pnl_without_largest_winner"]) > 0.0
        ),
        "STRESS_2X_LOAO_MIN_REMAINING_PNL_POSITIVE": (
            float(concentration["minimum_loao_remaining_net_pnl"]) > 0.0
        ),
        "STRESS_2X_LOYO_MIN_REMAINING_PNL_POSITIVE": (
            float(concentration["minimum_loyo_remaining_net_pnl"]) > 0.0
        ),
        "PF1_BREAK_EVEN_COST_MULTIPLIER_GTE_2": (
            float(break_even["pf1_break_even_cost_multiplier"])
            >= MINIMUM_BREAK_EVEN_COST_MULTIPLIER
        ),
        "CASH_FEASIBLE_BASE_AND_2X": (
            float(base["minimum_cash"]) >= -1e-7 and float(stress["minimum_cash"]) >= -1e-7
        ),
        "MOMENTUM_BREAKOUT_STANDALONE_2X_POSITIVE": (float(mb["net_return"]) > 0.0),
        "RELATIVE_STRENGTH_STANDALONE_2X_POSITIVE": (float(rs["net_return"]) > 0.0),
        "NO_2024_OR_POST_2024_ACCESS": True,
        "MOMENTUM_BREAKOUT_2022_2X_NET_PNL_POSITIVE": (mb_period_pnl("ROBUSTNESS_2022") > 0.0),
        "MOMENTUM_BREAKOUT_2023_2X_NET_PNL_POSITIVE": (mb_period_pnl("ROBUSTNESS_2023") > 0.0),
    }
    if tuple(checks) != HARD_GATES:
        raise RunnerError("runtime hard-gate ordering drifted")
    return checks


def evaluate_hard_gates(
    *,
    run_metrics: pd.DataFrame,
    periods: pd.DataFrame,
    concentrations: pd.DataFrame,
    break_even: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    gate_rows: list[dict[str, Any]] = []
    selections: list[dict[str, Any]] = []

    for policy_id in EXPECTED_POLICIES:
        policy_pass = True
        worst_return = math.inf
        worst_pf = math.inf
        worst_dd = 0.0
        worst_turnover = 0.0

        for universe in EXPECTED_UNIVERSES:

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

            union_periods = periods.loc[
                (periods["policy_id"] == policy_id)
                & (periods["portfolio_id"] == "UNION_FOCUS")
                & (periods["universe_id"] == universe)
                & (periods["cost_multiplier"] == 2.0)
            ].copy()
            mb_periods = periods.loc[
                (periods["policy_id"] == policy_id)
                & (periods["portfolio_id"] == FAMILY_MOMENTUM_BREAKOUT)
                & (periods["universe_id"] == universe)
                & (periods["cost_multiplier"] == 2.0)
            ].copy()
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

            checks = gate_checks_for_one(
                base=base,
                stress=stress,
                mb=mb,
                rs=rs,
                union_periods=union_periods,
                mb_periods=mb_periods,
                concentration=conc.iloc[0],
                break_even=be.iloc[0],
            )
            for gate_id, gate_passed in checks.items():
                gate_rows.append(
                    {
                        "policy_id": policy_id,
                        "universe_id": universe,
                        "gate_id": gate_id,
                        "passed": bool(gate_passed),
                    }
                )
                policy_pass = policy_pass and bool(gate_passed)

            worst_return = min(
                worst_return,
                float(stress["net_return"]),
            )
            worst_pf = min(
                worst_pf,
                float(stress["profit_factor"]),
            )
            worst_dd = max(
                worst_dd,
                float(stress["maximum_drawdown"]),
            )
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

    gates = pd.DataFrame.from_records(gate_rows)
    if len(gates) != 4 * 3 * 16:
        raise RunnerError("hard-gate row count drifted")
    return gates, selection


def make_report(
    *,
    run_metrics: pd.DataFrame,
    periods: pd.DataFrame,
    selection: pd.DataFrame,
    event_count: int,
    required_pair_count: int,
    freeze_commit: str,
    control_parity: dict[str, Any],
    rs_invariance: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    selected = selection.loc[selection["selected"]]
    selected_policy = str(selected.iloc[0]["policy_id"]) if len(selected) == 1 else None
    summaries: dict[str, dict[str, Any]] = {}
    mb_years: dict[str, dict[str, dict[str, float]]] = {}

    for policy_id in EXPECTED_POLICIES:
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
        mb_years[policy_id] = {}
        for universe in EXPECTED_UNIVERSES:
            subset = periods.loc[
                (periods["policy_id"] == policy_id)
                & (periods["portfolio_id"] == FAMILY_MOMENTUM_BREAKOUT)
                & (periods["universe_id"] == universe)
                & (periods["cost_multiplier"] == 2.0)
            ]
            mb_years[policy_id][universe] = {
                str(row["period_id"]): float(row["net_pnl"])
                for row in subset.to_dict(orient="records")
            }

    if selected_policy is None:
        decision = FAILURE_DECISION
        next_stage = FAILURE_NEXT
    else:
        decision = SUCCESS_DECISION
        next_stage = SUCCESS_NEXT

    freeze = {
        "schema_version": "rd32-p3-selected-mb-signal-quality-policy-freeze-v1",
        "selected_policy": selected_policy,
        "selection_basis": (
            "PASS_ALL_16_PREREGISTERED_HARD_GATES_IN_ALL_UNIVERSES_THEN_FROZEN_RD32_TIE_BREAKS"
        ),
        "runner_freeze_commit": freeze_commit,
        "policy_summaries": summaries,
        "mb_2x_period_net_pnl": mb_years,
        "control_parity_vs_rd31": control_parity,
        "rs_only_invariance": rs_invariance,
        "2022_2023_used_for_architecture_selection": True,
        "2024_accessed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
    }
    report = {
        "schema_version": "rd32-p3-mb-signal-quality-admission-report-v1",
        "stage": "RD32_P3_MB_SIGNAL_QUALITY_ADMISSION_2022_2023",
        "status": "PASS",
        "decision": decision,
        "next_stage": next_stage,
        "p2c_freeze_commit": P2C_FREEZE_COMMIT,
        "runner_freeze_commit": freeze_commit,
        "selected_policy": selected_policy,
        "policy_summaries": summaries,
        "mb_2x_period_net_pnl": mb_years,
        "signal_event_count_2022_2023": event_count,
        "required_pit_feature_pair_count": required_pair_count,
        "hard_gate_count": 16,
        "control_parity_vs_rd31": control_parity,
        "rs_only_invariance": rs_invariance,
        "candidate_parameters_changed_after_economic_execution": False,
        "research_logic_changed_after_economic_execution": False,
        "2022_2023_used_for_architecture_selection": True,
        "2024_accessed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
    }
    return report, freeze


def output_manifest(
    output: Path,
    decision: str,
) -> dict[str, Any]:
    files: list[dict[str, Any]] = []
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
        "schema_version": "rd32-p3-output-manifest-v1",
        "decision": decision,
        "deterministic_hash": deterministic,
        "files": files,
        "runner_freeze_commit": None,
        "2024_accessed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
    }


def validate_outputs(repo: Path) -> dict[str, Any]:
    output = repo / OUTPUT
    manifest_path = output / "output-manifest.json"
    if not manifest_path.is_file():
        raise RunnerError("RD32 output manifest missing")
    manifest = load_json(manifest_path)
    items = {
        str(item["path"]): item for item in manifest.get("files", []) if isinstance(item, dict)
    }
    if set(items) != set(OUTPUT_NAMES):
        raise RunnerError("RD32 manifest output set drifted")
    for name in OUTPUT_NAMES:
        path = output / name
        if not path.is_file():
            raise RunnerError(f"RD32 output missing: {name}")
        if sha256(path) != str(items[name]["sha256"]):
            raise RunnerError(f"RD32 output hash drift: {name}")

    report = load_json(output / "rd32-p3-mb-signal-quality-admission-report-v1.json")
    if report.get("status") != "PASS":
        raise RunnerError("RD32 report status drifted")
    if report.get("hard_gate_count") != 16:
        raise RunnerError("RD32 report hard-gate count drifted")
    parity = report.get("control_parity_vs_rd31")
    if (
        not isinstance(parity, dict)
        or parity.get("passed") is not True
        or parity.get("row_count") != 18
    ):
        raise RunnerError("RD32 control parity failed")
    rs = report.get("rs_only_invariance")
    if (
        not isinstance(rs, dict)
        or rs.get("passed") is not True
        or rs.get("metric_comparison_rows") != 18
    ):
        raise RunnerError("RD32 RS-only invariance failed")

    metrics = pd.read_csv(
        output / "portfolio-run-metrics.csv",
        low_memory=False,
    )
    if len(metrics) != EXPECTED_ECONOMIC_REPLAYS:
        raise RunnerError("RD32 economic metric row count drifted")
    gates = pd.read_csv(
        output / "hard-gate-evaluation.csv",
        low_memory=False,
    )
    if len(gates) != 192:
        raise RunnerError("RD32 hard-gate row count drifted")
    selection = pd.read_csv(
        output / "policy-selection.csv",
        low_memory=False,
    )
    if len(selection) != 4:
        raise RunnerError("RD32 policy-selection row count drifted")

    trades = pd.read_csv(
        output / "trade-ledger.csv",
        low_memory=False,
    )
    if len(trades):
        exits = pd.to_datetime(
            trades["exit_time"],
            utc=True,
            errors="raise",
        )
        if bool((exits >= DATA_CUTOFF).any()):
            raise RunnerError("RD32 trade crossed sealed 2024 cutoff")
    daily = pd.read_csv(
        output / "daily-equity.csv",
        low_memory=False,
    )
    if len(daily):
        timestamps = pd.to_datetime(
            daily["timestamp"],
            utc=True,
            errors="raise",
        )
        if bool((timestamps >= DATA_CUTOFF).any()):
            raise RunnerError("RD32 daily equity crossed sealed 2024 cutoff")

    for field in (
        "candidate_parameters_changed_after_economic_execution",
        "research_logic_changed_after_economic_execution",
        "2024_accessed",
        "post_2024_accessed",
        "production_authorized",
    ):
        if report.get(field) is not False:
            raise RunnerError(f"RD32 prohibited report flag true: {field}")

    return {
        "status": "PASS",
        "decision": report["decision"],
        "next_stage": report["next_stage"],
        "selected_policy": report["selected_policy"],
        "control_parity_rows": int(parity["row_count"]),
        "rs_invariance_metric_rows": int(rs["metric_comparison_rows"]),
        "economic_replay_rows": len(metrics),
        "hard_gate_rows": len(gates),
        "manifest_deterministic_hash": manifest["deterministic_hash"],
        "2024_accessed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
    }


def main() -> int:
    args = parser().parse_args()
    repo = args.repo_root.resolve()
    if not (repo / ".git").exists():
        raise RunnerError(f"not a git repository: {repo}")

    if args.validate_only:
        print(
            json.dumps(
                validate_outputs(repo),
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    if not args.execute:
        raise RunnerError("economic execution requires explicit --execute")
    if not args.expected_freeze_commit:
        raise RunnerError("--expected-freeze-commit is required")

    lineage = verify_lineage(
        repo,
        args.expected_freeze_commit,
    )
    rd31 = load_rd31_runner()

    raw_root = (
        args.raw_root.resolve()
        if args.raw_root is not None
        else (repo / DEFAULT_RAW_ROOT).resolve()
    )
    events = rd31.load_signal_events(repo)
    membership = rd31.selection_membership(rd31.load_membership(repo / rd31.MEMBERSHIP))
    membership_check = rd31.validate_signal_membership_coverage(
        events,
        membership,
    )
    pairs = rd31.required_feature_pairs(
        events,
        membership,
    )
    frames = rd31.load_feature_frames(
        raw_root=raw_root,
        pairs=pairs,
    )
    state_frame = rd31.load_state_frame(raw_root)
    state_summary = rd31.market_state_summary(state_frame)

    output = repo / OUTPUT
    output.mkdir(parents=True, exist_ok=False)
    write_json(
        output / "input-and-conformance-audit.json",
        {
            "schema_version": ("rd32-p3-input-conformance-audit-v1"),
            "stage": ("RD32_P3_MB_SIGNAL_QUALITY_ADMISSION_2022_2023"),
            "lineage": lineage,
            "signal_event_count": len(events),
            "membership_snapshot_count": len(membership),
            "required_pit_feature_pair_count": len(pairs),
            "required_pit_feature_pairs": pairs,
            "membership_signal_coverage": membership_check,
            "economic_execution_performed": True,
            "candidate_parameters_changed_after_economic_execution": False,
            "research_logic_changed_after_economic_execution": False,
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
        rd31=rd31,
        events=events,
        frames=frames,
        state_frame=state_frame,
        membership=membership,
    )

    control_parity = verify_control_parity_vs_rd31(
        repo,
        run_metrics,
    )
    rs_invariance = verify_rs_only_invariance(
        run_metrics=run_metrics,
        trades=trades,
    )
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
        periods=periods,
        selection=selection,
        event_count=len(events),
        required_pair_count=len(pairs),
        freeze_commit=args.expected_freeze_commit,
        control_parity=control_parity,
        rs_invariance=rs_invariance,
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
        output / "baseline-parity-vs-rd31.json",
        control_parity,
    )
    write_json(
        output / "rs-only-invariance.json",
        rs_invariance,
    )
    write_json(
        output / "selected-mb-signal-quality-policy-freeze.json",
        selected_freeze,
    )
    write_json(
        output / "rd32-p3-mb-signal-quality-admission-report-v1.json",
        report,
    )
    manifest = output_manifest(
        output,
        report["decision"],
    )
    manifest["runner_freeze_commit"] = args.expected_freeze_commit
    write_json(
        output / "output-manifest.json",
        manifest,
    )

    print(
        json.dumps(
            validate_outputs(repo),
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"RD32_P3_ERROR={exc}", file=sys.stderr)
        raise
