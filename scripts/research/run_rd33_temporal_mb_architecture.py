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
from spotbot.research.rd33_temporal_mb_architecture import (  # noqa: E402
    CANDIDATE_POLICIES,
    CONFIRMED,
    MB_FIRST_RETEST_RECLAIM_WITHIN_FROZEN_72H,
    MB_ONE_BAR_BREAKOUT_LEVEL_HOLD,
    MB_ONE_BAR_POST_BREAKOUT_CONTINUATION,
    RD31_REGIME_HYSTERESIS_CONTROL,
)
from spotbot.research.rd33_temporal_mb_replay import (  # noqa: E402
    governor_ledger_parity,
    replay_rd33_policy,
)

SCHEMA_VERSION = "rd33-temporal-mb-economic-runner-v1"

P0C_FREEZE_COMMIT = "03a850ad3eef5dc8f77f2e02662ce4b510d74b96"
P0B_FREEZE_COMMIT = "5b0368f5c8bb11a81e846f51d794d375032c8870"
P0_FREEZE_COMMIT = "1ded76672b0d8dd7261d0257deb3f5637805336a"
RD32_RESULTS_COMMIT = "bac6c7ba6ddf63a58676b5e18b516061d1969bb1"

P0_PROTOCOL = Path(
    "data/research/rd33_p0/rd33-p0-signal-family-architecture-redesign-protocol-v1.json"
)
P0_PROTOCOL_SHA256 = "9b75c6bcaa1ad6acb0646b6b674fe16adb0b1546848efb2971030d0d9c182236"
P0_AUDIT = Path("data/research/rd33_p0/rd33-p0-preregistration-audit-v1.json")
P0_AUDIT_SHA256 = "9548b90ac764af3924ddbc1cbb2222319fc74856227e76f516e473ed35765c7c"

P0B_ENGINE = Path("src/spotbot/research/rd33_temporal_mb_architecture.py")
P0B_ENGINE_SHA256 = "be916a603942f2c17f4227bac0ef295754cd35ed5b90d7ff8b6916c3a5fe550f"
P0B_TEST = Path("tests/research/test_rd33_temporal_mb_architecture.py")
P0B_TEST_SHA256 = "715747057ba5051e8378fe92513951a84c3629959025f514bcac8c9064f69364"
P0B_AUDIT = Path(
    "data/research/rd33_p0b/rd33-p0b-temporal-mb-architecture-engine-freeze-audit-v1.json"
)
P0B_AUDIT_SHA256 = "02c0892f9d5b3e2c3dc126bb1ac896863290642d73cb8a51b4c29df95443c335"

P0C_REPLAY = Path("src/spotbot/research/rd33_temporal_mb_replay.py")
P0C_REPLAY_SHA256 = "a0b37c791e37821405f9ac8c1a24ae97eeabd38f6c52cf7cc942124d519d7179"
P0C_TEST = Path("tests/research/test_rd33_temporal_mb_replay.py")
P0C_TEST_SHA256 = "8137db1cb82089e5061d6f92dbc807f669caeb429e11fb09e3a291741f95833f"
P0C_AUDIT = Path(
    "data/research/rd33_p0c/rd33-p0c-temporal-mb-portfolio-replay-freeze-audit-v1.json"
)
P0C_AUDIT_SHA256 = "d9e53fc30642e2534e038f3bf4a08e9c1ffa95109c70e448a8e5f021e1b6aa5e"

RD31_RUNNER = Path("scripts/research/run_rd31_market_regime_admission_governor.py")
RD31_RUNNER_BLOB_SHA = "3b5c6916e34be6c9642702fe2807e42e445ee083"

RD32_RUN_METRICS = Path("data/research/rd32_p3_runtime/portfolio-run-metrics.csv")
RD32_RUN_METRICS_BLOB_SHA = "93a5f17b74b6dc1be8c6dcb561fa99922bec5bea"
RD32_REPORT = Path(
    "data/research/rd32_p3_runtime/rd32-p3-mb-signal-quality-admission-report-v1.json"
)
RD32_REPORT_BLOB_SHA = "1690e25b4af4f6c3f4166030ab71643c18e823da"

DEFAULT_RAW_ROOT = Path("data/raw/rd16b/kucoin")
OUTPUT = Path("data/research/rd33_p1_runtime")

EXPECTED_POLICIES = (
    RD31_REGIME_HYSTERESIS_CONTROL,
    MB_ONE_BAR_BREAKOUT_LEVEL_HOLD,
    MB_ONE_BAR_POST_BREAKOUT_CONTINUATION,
    MB_FIRST_RETEST_RECLAIM_WITHIN_FROZEN_72H,
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
GOVERNOR_PARITY_EXPECTED_COMPARISONS = 54

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
    "MOMENTUM_BREAKOUT_2022_2X_NET_PNL_POSITIVE",
    "MOMENTUM_BREAKOUT_2023_2X_NET_PNL_POSITIVE",
)

CAUSALITY_GATES = (
    "CONTROL_PARITY_18_ROWS_VS_RD32_FINAL_CONTROL",
    "RS_METRIC_INVARIANCE_18_ROWS_ACROSS_ALL_CANDIDATES",
    "RS_TRADE_LEDGER_INVARIANCE_ACROSS_ALL_CANDIDATES",
    "GOVERNOR_TRANSITION_LEDGER_EXACT_PARITY_VS_CONTROL",
    "EVERY_CANDIDATE_MB_PENDING_MAPS_TO_ONE_FROZEN_RAW_MB_EVENT",
    "EVERY_CANDIDATE_MB_TRADE_MAPS_TO_ONE_CONTROL_ADMITTED_MB_ORIGIN",
    "NO_CANDIDATE_ENTRY_PRECEDES_ITS_REQUIRED_COMPLETED_CONFIRMATION",
    "NO_2024_OR_POST_2024_ACCESS",
)

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
    "control-parity-vs-rd32.json",
    "rs-only-invariance.json",
    "governor-transition-parity.json",
    "causality-mapping-audit.json",
    "pending-lifecycle-ledger.csv",
    "governor-transition-ledger.csv",
    "selected-temporal-mb-policy-freeze.json",
    "rd33-p1-temporal-mb-architecture-report-v1.json",
)

SUCCESS_DECISION = "RD33_TEMPORAL_MB_ARCHITECTURE_POLICY_SELECTED_2024_CONFIRMATION_AUTHORIZED"
FAILURE_DECISION = (
    "RD33_TEMPORAL_MB_ARCHITECTURE_NO_FINALIST_"
    "MULTI_FAMILY_SIGNAL_ARCHITECTURE_OR_NEW_ALPHA_SOURCE_REQUIRED"
)
SUCCESS_NEXT = "RD34_CLEAN_2024_INTERNAL_CONFIRMATION"
FAILURE_NEXT = "RD34_MULTI_FAMILY_SIGNAL_ARCHITECTURE_OR_NEW_ALPHA_SOURCE_REQUIRED"


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
        "_rd31_frozen_economic_runner_for_rd33",
        path,
    )
    if spec is None or spec.loader is None:
        raise RunnerError("cannot load frozen RD31 runner")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def active_component_count(policy_id: str) -> int:
    if policy_id == RD31_REGIME_HYSTERESIS_CONTROL:
        return 1
    if policy_id in CANDIDATE_POLICIES:
        return 2
    raise RunnerError(f"unknown RD33 policy for complexity count: {policy_id}")


def verify_lineage(
    repo: Path,
    expected_freeze_commit: str,
) -> dict[str, Any]:
    if git(repo, "diff", "--cached", "--name-only", "--"):
        raise RunnerError("staged tracked changes exist before RD33-P1")
    if git(repo, "diff", "--name-only", "--"):
        raise RunnerError("unstaged tracked changes exist before RD33-P1")

    head = git(repo, "rev-parse", "HEAD")
    if head != expected_freeze_commit:
        raise RunnerError(f"RD33-P1 HEAD {head} != runner freeze {expected_freeze_commit}")
    parent = git(repo, "rev-parse", "HEAD^")
    grandparent = git(repo, "rev-parse", "HEAD^^")
    if parent != P0C_FREEZE_COMMIT:
        raise RunnerError("RD33 runner-freeze parent is not P0C")
    if grandparent != P0B_FREEZE_COMMIT:
        raise RunnerError("RD33 runner-freeze grandparent is not P0B")

    checks = (
        (P0_PROTOCOL, P0_PROTOCOL_SHA256, "P0 protocol"),
        (P0_AUDIT, P0_AUDIT_SHA256, "P0 audit"),
        (P0B_ENGINE, P0B_ENGINE_SHA256, "P0B engine"),
        (P0B_TEST, P0B_TEST_SHA256, "P0B engine tests"),
        (P0B_AUDIT, P0B_AUDIT_SHA256, "P0B audit"),
        (P0C_REPLAY, P0C_REPLAY_SHA256, "P0C replay"),
        (P0C_TEST, P0C_TEST_SHA256, "P0C replay tests"),
        (P0C_AUDIT, P0C_AUDIT_SHA256, "P0C audit"),
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

    if git(repo, "rev-parse", f"HEAD:{RD31_RUNNER.as_posix()}") != RD31_RUNNER_BLOB_SHA:
        raise RunnerError("frozen RD31 runner blob drifted")

    if (
        git(
            repo,
            "rev-parse",
            f"{RD32_RESULTS_COMMIT}:{RD32_RUN_METRICS.as_posix()}",
        )
        != RD32_RUN_METRICS_BLOB_SHA
    ):
        raise RunnerError("frozen RD32 control metrics blob drifted")
    if (
        git(
            repo,
            "rev-parse",
            f"{RD32_RESULTS_COMMIT}:{RD32_REPORT.as_posix()}",
        )
        != RD32_REPORT_BLOB_SHA
    ):
        raise RunnerError("frozen RD32 report blob drifted")

    protocol = load_json(repo / P0_PROTOCOL)
    if tuple(protocol.get("candidate_policy_order", [])) != (
        MB_ONE_BAR_BREAKOUT_LEVEL_HOLD,
        MB_ONE_BAR_POST_BREAKOUT_CONTINUATION,
        MB_FIRST_RETEST_RECLAIM_WITHIN_FROZEN_72H,
    ):
        raise RunnerError("RD33 candidate policy order drifted")
    if tuple(protocol.get("hard_gates", [])) != HARD_GATES:
        raise RunnerError("RD33 hard-gate registry drifted")
    if tuple(protocol.get("causality_and_mapping_gates_pre_economic", [])) != CAUSALITY_GATES:
        raise RunnerError("RD33 causality-gate registry drifted")
    matrix = protocol.get("economic_matrix_for_later_execution")
    if not isinstance(matrix, dict) or matrix.get("expected_rows") != 72:
        raise RunnerError("RD33 economic matrix drifted")
    if tuple(matrix.get("policies", [])) != EXPECTED_POLICIES:
        raise RunnerError("RD33 economic policy matrix drifted")
    if tuple(matrix.get("portfolios", [])) != EXPECTED_PORTFOLIOS:
        raise RunnerError("RD33 economic portfolio matrix drifted")
    if tuple(matrix.get("universes", [])) != EXPECTED_UNIVERSES:
        raise RunnerError("RD33 economic universe matrix drifted")
    if tuple(float(x) for x in matrix.get("cost_multipliers", [])) != (
        1.0,
        2.0,
    ):
        raise RunnerError("RD33 cost matrix drifted")

    for label, relative in (
        ("P0B", P0B_AUDIT),
        ("P0C", P0C_AUDIT),
    ):
        audit = load_json(repo / relative)
        if audit.get("status") != "PASS":
            raise RunnerError(f"RD33 {label} audit not PASS")
        for field in (
            "economic_execution_performed",
            "raw_market_data_loaded",
            "candidate_results_observed",
            "2024_accessed",
            "post_2024_accessed",
            "production_authorized",
        ):
            if audit.get(field) is not False:
                raise RunnerError(f"RD33 {label} prohibited flag true: {field}")

    p0c = load_json(repo / P0C_AUDIT)
    if p0c.get("portfolio_replay_implemented") is not True:
        raise RunnerError("P0C replay not implemented")
    if p0c.get("economic_runner_implemented") is not False:
        raise RunnerError("P0C unexpectedly implemented runner")
    if p0c.get("next_stage") != ("RD33_P0D_FREEZE_TEMPORAL_MB_ECONOMIC_RUNNER_PRE_EXECUTION"):
        raise RunnerError("P0C next-stage lineage drifted")
    if p0c.get("candidate_confirmation_calls_governor") is not False:
        raise RunnerError("P0C confirmation/governor contract drifted")
    if p0c.get("second_governor_transition_on_confirmation") is not False:
        raise RunnerError("P0C second-transition contract drifted")

    rd32_report = load_json(repo / RD32_REPORT)
    if rd32_report.get("status") != "PASS":
        raise RunnerError("RD32 source report not PASS")
    if rd32_report.get("decision") != (
        "RD32_MB_SIGNAL_QUALITY_ADMISSION_NO_FINALIST_SIGNAL_FAMILY_ARCHITECTURE_REDESIGN_REQUIRED"
    ):
        raise RunnerError("RD32 source decision drifted")
    if rd32_report.get("2024_accessed") is not False:
        raise RunnerError("RD32 source report crossed 2024")

    return {
        "runner_freeze_commit": expected_freeze_commit,
        "p0c_freeze_commit": P0C_FREEZE_COMMIT,
        "p0b_freeze_commit": P0B_FREEZE_COMMIT,
        "p0_freeze_commit": P0_FREEZE_COMMIT,
        "rd32_results_commit": RD32_RESULTS_COMMIT,
        "verified_sha256": verified,
        "rd31_runner_blob_sha": RD31_RUNNER_BLOB_SHA,
        "rd32_control_metrics_blob_sha": RD32_RUN_METRICS_BLOB_SHA,
        "rd32_report_blob_sha": RD32_REPORT_BLOB_SHA,
        "policies": list(EXPECTED_POLICIES),
        "hard_gates": list(HARD_GATES),
        "causality_gates": list(CAUSALITY_GATES),
        "expected_economic_replays": EXPECTED_ECONOMIC_REPLAYS,
    }


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
    pd.DataFrame,
    pd.DataFrame,
]:
    run_rows: list[dict[str, Any]] = []
    trade_sets: list[pd.DataFrame] = []
    daily_sets: list[pd.DataFrame] = []
    routing_rows: list[dict[str, Any]] = []
    concentration_rows: list[dict[str, Any]] = []
    break_even_rows: list[dict[str, Any]] = []
    governor_sets: list[pd.DataFrame] = []
    pending_sets: list[pd.DataFrame] = []

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
                        diagnostics,
                    ) = replay_rd33_policy(
                        policy_id=policy_id,
                        portfolio_id=portfolio_id,
                        universe_id=universe,
                        cost_multiplier=cost_multiplier,
                        events=portfolio_events,
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

                    governor = diagnostics.governor_transition_ledger.copy()
                    governor.insert(0, "policy_id", policy_id)
                    governor.insert(1, "portfolio_id", portfolio_id)
                    governor.insert(3, "cost_multiplier", cost_multiplier)
                    governor_sets.append(governor)

                    pending = diagnostics.pending_lifecycle_ledger.copy()
                    if len(pending):
                        pending["cost_multiplier"] = cost_multiplier
                        pending_sets.append(pending)

                    if cost_multiplier == 1.0:
                        base_trades = trades.copy()

                    print(
                        "RD33_PORTFOLIO="
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
        (pd.concat(trade_sets, ignore_index=True) if trade_sets else pd.DataFrame()),
        (pd.concat(daily_sets, ignore_index=True) if daily_sets else pd.DataFrame()),
        pd.DataFrame.from_records(routing_rows),
        pd.DataFrame.from_records(concentration_rows),
        pd.DataFrame.from_records(break_even_rows),
        (pd.concat(governor_sets, ignore_index=True) if governor_sets else pd.DataFrame()),
        (pd.concat(pending_sets, ignore_index=True) if pending_sets else pd.DataFrame()),
    )


def verify_control_parity_vs_rd32(
    repo: Path,
    run_metrics: pd.DataFrame,
) -> dict[str, Any]:
    frozen = pd.read_csv(repo / RD32_RUN_METRICS, low_memory=False)
    frozen = frozen.loc[frozen["policy_id"] == RD31_REGIME_HYSTERESIS_CONTROL].copy()
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
        label="RD33 control parity vs RD32 final control",
        expected_rows=BASELINE_PARITY_EXPECTED_ROWS,
    )
    parity["source_policy"] = RD31_REGIME_HYSTERESIS_CONTROL
    parity["current_policy"] = RD31_REGIME_HYSTERESIS_CONTROL
    parity["source_results_commit"] = RD32_RESULTS_COMMIT
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
        comparisons.append({"policy_id": policy_id, **parity})

    comparison_rows = sum(int(item["row_count"]) for item in comparisons)
    if comparison_rows != RS_INVARIANCE_EXPECTED_COMPARISONS:
        raise RunnerError("RS-only metric comparison row count drifted")

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
    control_trades = trades.loc[
        (trades["policy_id"] == RD31_REGIME_HYSTERESIS_CONTROL)
        & (trades["portfolio_id"] == FAMILY_RELATIVE_STRENGTH_ROTATION)
    ].copy()
    trade_checks: list[dict[str, Any]] = []
    for policy_id in EXPECTED_POLICIES[1:]:
        candidate = trades.loc[
            (trades["policy_id"] == policy_id)
            & (trades["portfolio_id"] == FAMILY_RELATIVE_STRENGTH_ROTATION)
        ].copy()
        left = control_trades.sort_values(exact_columns, kind="stable").reset_index(drop=True)
        right = candidate.sort_values(exact_columns, kind="stable").reset_index(drop=True)
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

    return {
        "passed": True,
        "metric_comparisons": comparisons,
        "trade_comparisons": trade_checks,
        "metric_comparison_rows": comparison_rows,
        "rs_path_changed": False,
    }


def verify_governor_transition_parity(
    governor: pd.DataFrame,
) -> dict[str, Any]:
    comparisons: list[dict[str, Any]] = []
    for portfolio_id in EXPECTED_PORTFOLIOS:
        for universe in EXPECTED_UNIVERSES:
            for cost_multiplier in COST_MULTIPLIERS:
                control = governor.loc[
                    (governor["policy_id"] == RD31_REGIME_HYSTERESIS_CONTROL)
                    & (governor["portfolio_id"] == portfolio_id)
                    & (governor["universe_id"] == universe)
                    & (governor["cost_multiplier"] == cost_multiplier)
                ].copy()
                for policy_id in EXPECTED_POLICIES[1:]:
                    candidate = governor.loc[
                        (governor["policy_id"] == policy_id)
                        & (governor["portfolio_id"] == portfolio_id)
                        & (governor["universe_id"] == universe)
                        & (governor["cost_multiplier"] == cost_multiplier)
                    ].copy()
                    parity = governor_ledger_parity(
                        control,
                        candidate,
                    )
                    comparisons.append(
                        {
                            "policy_id": policy_id,
                            "portfolio_id": portfolio_id,
                            "universe_id": universe,
                            "cost_multiplier": cost_multiplier,
                            **parity,
                        }
                    )

    if len(comparisons) != GOVERNOR_PARITY_EXPECTED_COMPARISONS:
        raise RunnerError(
            "governor parity comparison count drifted: "
            f"{len(comparisons)} "
            f"!= {GOVERNOR_PARITY_EXPECTED_COMPARISONS}"
        )
    return {
        "passed": True,
        "comparison_count": len(comparisons),
        "comparisons": comparisons,
        "candidate_confirmation_triggered_second_transition": False,
    }


def _timestamp_key(value: Any) -> int:
    return int(pd.Timestamp(value).tz_convert("UTC").value)


def verify_causality_mapping(
    *,
    events: pd.DataFrame,
    trades: pd.DataFrame,
    pending: pd.DataFrame,
    governor: pd.DataFrame,
    control_parity: dict[str, Any],
    rs_invariance: dict[str, Any],
    governor_parity: dict[str, Any],
) -> dict[str, Any]:
    event_frame = events.copy()
    event_frame["timestamp"] = pd.to_datetime(
        event_frame["timestamp"],
        utc=True,
        errors="raise",
    )
    raw_mb = event_frame.loc[
        event_frame["family_id"].astype(str) == FAMILY_MOMENTUM_BREAKOUT
    ].copy()
    raw_counts = (
        raw_mb.groupby(
            ["universe_id", "pair", "timestamp"],
            dropna=False,
        )
        .size()
        .to_dict()
    )

    pending_registered = pending.loc[pending["status"].astype(str) == "PENDING"].copy()
    pending_mismatch: list[dict[str, Any]] = []
    for row in pending_registered.to_dict(orient="records"):
        key = (
            str(row["universe_id"]),
            str(row["pair"]),
            pd.Timestamp(row["signal_time"]),
        )
        count = int(raw_counts.get(key, 0))
        if count != 1:
            pending_mismatch.append(
                {
                    "policy_id": row["policy_id"],
                    "portfolio_id": row["portfolio_id"],
                    "universe_id": row["universe_id"],
                    "cost_multiplier": row["cost_multiplier"],
                    "pair": row["pair"],
                    "signal_time": row["signal_time"],
                    "raw_mb_match_count": count,
                }
            )
            if len(pending_mismatch) >= 20:
                break

    candidate_mb_trades = trades.loc[
        trades["policy_id"].isin(EXPECTED_POLICIES[1:])
        & (trades["support_families"].astype(str) == FAMILY_MOMENTUM_BREAKOUT)
    ].copy()
    trade_origin_mismatch: list[dict[str, Any]] = []
    timing_mismatch: list[dict[str, Any]] = []

    confirmed = pending.loc[pending["status"].astype(str) == CONFIRMED].copy()

    for row in candidate_mb_trades.to_dict(orient="records"):
        subset = governor.loc[
            (governor["policy_id"] == row["policy_id"])
            & (governor["portfolio_id"] == row["portfolio_id"])
            & (governor["universe_id"] == row["universe_id"])
            & (governor["cost_multiplier"] == row["cost_multiplier"])
            & (governor["pair"] == row["pair"])
            & (
                pd.to_datetime(
                    governor["signal_time"],
                    utc=True,
                    errors="raise",
                )
                == pd.Timestamp(row["signal_time"])
            )
            & governor["admit_position"].astype(bool)
            & governor["admissible_families"]
            .astype(str)
            .str.split("|")
            .map(lambda values: FAMILY_MOMENTUM_BREAKOUT in values)
        ]
        if len(subset) != 1:
            trade_origin_mismatch.append(
                {
                    "policy_id": row["policy_id"],
                    "portfolio_id": row["portfolio_id"],
                    "universe_id": row["universe_id"],
                    "cost_multiplier": row["cost_multiplier"],
                    "pair": row["pair"],
                    "signal_time": row["signal_time"],
                    "control_admitted_mb_origin_match_count": len(subset),
                }
            )
            if len(trade_origin_mismatch) >= 20:
                break

        conf = confirmed.loc[
            (confirmed["policy_id"] == row["policy_id"])
            & (confirmed["portfolio_id"] == row["portfolio_id"])
            & (confirmed["universe_id"] == row["universe_id"])
            & (confirmed["cost_multiplier"] == row["cost_multiplier"])
            & (confirmed["pair"] == row["pair"])
            & (
                pd.to_datetime(
                    confirmed["signal_time"],
                    utc=True,
                    errors="raise",
                )
                == pd.Timestamp(row["signal_time"])
            )
        ]
        if len(conf) != 1:
            timing_mismatch.append(
                {
                    "policy_id": row["policy_id"],
                    "portfolio_id": row["portfolio_id"],
                    "universe_id": row["universe_id"],
                    "cost_multiplier": row["cost_multiplier"],
                    "pair": row["pair"],
                    "signal_time": row["signal_time"],
                    "confirmation_match_count": len(conf),
                }
            )
            if len(timing_mismatch) >= 20:
                break
            continue

        conf_row = conf.iloc[0]
        completed_time = pd.Timestamp(conf_row["event_time"])
        actual_entry_time = pd.Timestamp(conf_row["actual_entry_time"])
        trade_entry_time = pd.Timestamp(row["entry_time"])
        if (
            actual_entry_time <= completed_time
            or actual_entry_time != (completed_time + pd.Timedelta(hours=1))
            or trade_entry_time != actual_entry_time
        ):
            timing_mismatch.append(
                {
                    "policy_id": row["policy_id"],
                    "portfolio_id": row["portfolio_id"],
                    "universe_id": row["universe_id"],
                    "cost_multiplier": row["cost_multiplier"],
                    "pair": row["pair"],
                    "signal_time": row["signal_time"],
                    "confirmation_completed_time": completed_time,
                    "confirmation_actual_entry_time": actual_entry_time,
                    "trade_entry_time": trade_entry_time,
                }
            )
            if len(timing_mismatch) >= 20:
                break

    crossed_2024 = False
    timestamp_columns = (
        (trades, ("signal_time", "entry_time", "exit_time")),
        (
            pending,
            (
                "signal_time",
                "event_time",
                "actual_entry_time",
            ),
        ),
        (
            governor,
            ("signal_time", "normal_entry_time"),
        ),
    )
    for frame, columns in timestamp_columns:
        if frame.empty:
            continue
        for column in columns:
            if column not in frame.columns:
                continue
            values = pd.to_datetime(
                frame[column],
                utc=True,
                errors="coerce",
            ).dropna()
            if bool((values >= DATA_CUTOFF).any()):
                crossed_2024 = True

    gates = {
        "CONTROL_PARITY_18_ROWS_VS_RD32_FINAL_CONTROL": bool(
            control_parity.get("passed") and int(control_parity.get("row_count", 0)) == 18
        ),
        "RS_METRIC_INVARIANCE_18_ROWS_ACROSS_ALL_CANDIDATES": bool(
            rs_invariance.get("passed")
            and int(rs_invariance.get("metric_comparison_rows", 0)) == 18
        ),
        "RS_TRADE_LEDGER_INVARIANCE_ACROSS_ALL_CANDIDATES": bool(
            rs_invariance.get("passed")
            and all(bool(item.get("passed")) for item in rs_invariance.get("trade_comparisons", []))
            and len(rs_invariance.get("trade_comparisons", [])) == 3
        ),
        "GOVERNOR_TRANSITION_LEDGER_EXACT_PARITY_VS_CONTROL": bool(
            governor_parity.get("passed")
            and int(governor_parity.get("comparison_count", 0))
            == GOVERNOR_PARITY_EXPECTED_COMPARISONS
        ),
        "EVERY_CANDIDATE_MB_PENDING_MAPS_TO_ONE_FROZEN_RAW_MB_EVENT": (len(pending_mismatch) == 0),
        "EVERY_CANDIDATE_MB_TRADE_MAPS_TO_ONE_CONTROL_ADMITTED_MB_ORIGIN": (
            len(trade_origin_mismatch) == 0
        ),
        "NO_CANDIDATE_ENTRY_PRECEDES_ITS_REQUIRED_COMPLETED_CONFIRMATION": (
            len(timing_mismatch) == 0
        ),
        "NO_2024_OR_POST_2024_ACCESS": not crossed_2024,
    }
    if tuple(gates) != CAUSALITY_GATES:
        raise RunnerError("runtime causality-gate ordering drifted")

    result = {
        "schema_version": "rd33-p1-causality-mapping-audit-v1",
        "passed": bool(all(gates.values())),
        "gates": gates,
        "registered_candidate_pending_rows": len(pending_registered),
        "candidate_mb_trade_rows": len(candidate_mb_trades),
        "pending_raw_mapping_mismatch_sample": pending_mismatch,
        "trade_control_origin_mismatch_sample": trade_origin_mismatch,
        "confirmation_timing_mismatch_sample": timing_mismatch,
        "2024_accessed": crossed_2024,
        "post_2024_accessed": False,
    }
    return result


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

    gates = pd.DataFrame.from_records(gate_rows)
    if len(gates) != 4 * 3 * 16:
        raise RunnerError("hard-gate row count drifted")

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
    governor_parity: dict[str, Any],
    causality: dict[str, Any],
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
        "schema_version": ("rd33-p1-selected-temporal-mb-policy-freeze-v1"),
        "selected_policy": selected_policy,
        "selection_basis": (
            "PASS_ALL_16_PREREGISTERED_HARD_GATES_IN_ALL_"
            "UNIVERSES_AFTER_ALL_8_CAUSALITY_GATES_PASS_"
            "THEN_FROZEN_RD33_TIE_BREAKS"
        ),
        "runner_freeze_commit": freeze_commit,
        "policy_summaries": summaries,
        "mb_2x_period_net_pnl": mb_years,
        "control_parity_vs_rd32": control_parity,
        "rs_only_invariance": rs_invariance,
        "governor_transition_parity": governor_parity,
        "causality_mapping_audit": causality,
        "2022_2023_used_for_architecture_selection": True,
        "2024_accessed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
    }
    report = {
        "schema_version": ("rd33-p1-temporal-mb-architecture-report-v1"),
        "stage": "RD33_P1_TEMPORAL_MB_ARCHITECTURE_2022_2023",
        "status": "PASS",
        "decision": decision,
        "next_stage": next_stage,
        "p0c_freeze_commit": P0C_FREEZE_COMMIT,
        "runner_freeze_commit": freeze_commit,
        "selected_policy": selected_policy,
        "policy_summaries": summaries,
        "mb_2x_period_net_pnl": mb_years,
        "signal_event_count_2022_2023": event_count,
        "required_pit_feature_pair_count": required_pair_count,
        "hard_gate_count": 16,
        "causality_gate_count": 8,
        "control_parity_vs_rd32": control_parity,
        "rs_only_invariance": rs_invariance,
        "governor_transition_parity": governor_parity,
        "causality_mapping_audit": causality,
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
    files: dict[str, dict[str, Any]] = {}
    for name in OUTPUT_NAMES:
        path = output / name
        if not path.is_file():
            raise RunnerError(f"manifest source output missing: {name}")
        files[name] = {
            "sha256": sha256(path),
            "bytes": path.stat().st_size,
        }
    canonical = json.dumps(
        files,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return {
        "schema_version": "rd33-p1-output-manifest-v1",
        "decision": decision,
        "file_count": len(files),
        "files": files,
        "deterministic_hash": hashlib.sha256(canonical).hexdigest(),
    }


def validate_outputs(repo: Path) -> dict[str, Any]:
    output = repo / OUTPUT
    if not output.is_dir():
        raise RunnerError(f"RD33 output directory missing: {output}")
    observed = sorted(path.name for path in output.iterdir() if path.is_file())
    expected = sorted((*OUTPUT_NAMES, "output-manifest.json"))
    if observed != expected:
        raise RunnerError(f"RD33 output set drifted: {observed} != {expected}")

    metrics = pd.read_csv(
        output / "portfolio-run-metrics.csv",
        low_memory=False,
    )
    if len(metrics) != EXPECTED_ECONOMIC_REPLAYS:
        raise RunnerError("RD33 economic replay row count drifted")
    if set(metrics["policy_id"].astype(str)) != set(EXPECTED_POLICIES):
        raise RunnerError("RD33 policy IDs drifted in run metrics")
    if set(metrics["portfolio_id"].astype(str)) != set(EXPECTED_PORTFOLIOS):
        raise RunnerError("RD33 portfolio IDs drifted")
    if set(metrics["universe_id"].astype(str)) != set(EXPECTED_UNIVERSES):
        raise RunnerError("RD33 universe IDs drifted")
    if set(pd.to_numeric(metrics["cost_multiplier"], errors="raise").astype(float)) != {1.0, 2.0}:
        raise RunnerError("RD33 cost multipliers drifted")

    periods = pd.read_csv(
        output / "portfolio-period-metrics.csv",
        low_memory=False,
    )
    if set(periods["period_id"].astype(str)) != set(ROBUSTNESS_PERIODS):
        raise RunnerError("RD33 period IDs drifted")

    gates = pd.read_csv(
        output / "hard-gate-evaluation.csv",
        low_memory=False,
    )
    if len(gates) != 192:
        raise RunnerError("RD33 hard-gate row count drifted")
    if set(gates["gate_id"].astype(str)) != set(HARD_GATES):
        raise RunnerError("RD33 hard-gate registry drifted")

    selection = pd.read_csv(
        output / "policy-selection.csv",
        low_memory=False,
    )
    if len(selection) != 4:
        raise RunnerError("RD33 policy-selection row count drifted")

    control = load_json(output / "control-parity-vs-rd32.json")
    if not control.get("passed") or control.get("row_count") != 18:
        raise RunnerError("RD33 control parity failed")

    rs = load_json(output / "rs-only-invariance.json")
    if (
        not rs.get("passed")
        or rs.get("metric_comparison_rows") != 18
        or rs.get("rs_path_changed") is not False
    ):
        raise RunnerError("RD33 RS invariance failed")

    governor_parity = load_json(output / "governor-transition-parity.json")
    if (
        not governor_parity.get("passed")
        or governor_parity.get("comparison_count") != GOVERNOR_PARITY_EXPECTED_COMPARISONS
    ):
        raise RunnerError("RD33 governor parity failed")

    causality = load_json(output / "causality-mapping-audit.json")
    if not causality.get("passed"):
        raise RunnerError("RD33 causality mapping audit failed")
    if tuple(causality.get("gates", {})) != CAUSALITY_GATES:
        raise RunnerError("RD33 causality gate ordering drifted")
    if not all(bool(value) for value in causality.get("gates", {}).values()):
        raise RunnerError("RD33 one or more causality gates failed")

    report = load_json(output / "rd33-p1-temporal-mb-architecture-report-v1.json")
    if report.get("status") != "PASS":
        raise RunnerError("RD33 report not PASS")
    if report.get("decision") not in (
        SUCCESS_DECISION,
        FAILURE_DECISION,
    ):
        raise RunnerError("RD33 report decision drifted")
    selected_policy = report.get("selected_policy")
    selected_rows = selection.loc[selection["selected"].astype(str).str.lower() == "true"]
    if selected_policy is None:
        if len(selected_rows) != 0:
            raise RunnerError("RD33 selected row exists with null report policy")
        if report.get("decision") != FAILURE_DECISION:
            raise RunnerError("RD33 null selection with success decision")
    else:
        if selected_policy not in EXPECTED_POLICIES:
            raise RunnerError("RD33 selected policy unknown")
        if len(selected_rows) != 1:
            raise RunnerError("RD33 selected policy cardinality drifted")
        if str(selected_rows.iloc[0]["policy_id"]) != selected_policy:
            raise RunnerError("RD33 selected policy/report mismatch")
        if report.get("decision") != SUCCESS_DECISION:
            raise RunnerError("RD33 selected policy with failure decision")

    for field in (
        "candidate_parameters_changed_after_economic_execution",
        "research_logic_changed_after_economic_execution",
        "2024_accessed",
        "post_2024_accessed",
        "production_authorized",
    ):
        if report.get(field) is not False:
            raise RunnerError(f"RD33 prohibited report flag true: {field}")

    trades = pd.read_csv(
        output / "trade-ledger.csv",
        low_memory=False,
    )
    daily = pd.read_csv(
        output / "daily-equity.csv",
        low_memory=False,
    )
    pending = pd.read_csv(
        output / "pending-lifecycle-ledger.csv",
        low_memory=False,
    )
    governor = pd.read_csv(
        output / "governor-transition-ledger.csv",
        low_memory=False,
    )
    for frame, columns in (
        (
            trades,
            ("signal_time", "entry_time", "exit_time"),
        ),
        (daily, ("timestamp",)),
        (
            pending,
            (
                "signal_time",
                "event_time",
                "actual_entry_time",
            ),
        ),
        (
            governor,
            ("signal_time", "normal_entry_time"),
        ),
    ):
        for column in columns:
            if column not in frame.columns:
                continue
            timestamps = pd.to_datetime(
                frame[column],
                utc=True,
                errors="coerce",
            ).dropna()
            if bool((timestamps >= DATA_CUTOFF).any()):
                raise RunnerError(f"RD33 {column} crossed sealed 2024 cutoff")

    manifest = load_json(output / "output-manifest.json")
    if manifest.get("file_count") != len(OUTPUT_NAMES):
        raise RunnerError("RD33 manifest file count drifted")
    if set(manifest.get("files", {})) != set(OUTPUT_NAMES):
        raise RunnerError("RD33 manifest file registry drifted")
    canonical_files: dict[str, dict[str, Any]] = {}
    for name in OUTPUT_NAMES:
        path = output / name
        record = manifest["files"][name]
        actual_sha = sha256(path)
        actual_bytes = path.stat().st_size
        if record.get("sha256") != actual_sha:
            raise RunnerError(f"RD33 manifest SHA mismatch: {name}")
        if int(record.get("bytes", -1)) != actual_bytes:
            raise RunnerError(f"RD33 manifest byte mismatch: {name}")
        canonical_files[name] = {
            "sha256": actual_sha,
            "bytes": actual_bytes,
        }
    canonical = json.dumps(
        canonical_files,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    deterministic = hashlib.sha256(canonical).hexdigest()
    if manifest.get("deterministic_hash") != deterministic:
        raise RunnerError("RD33 manifest deterministic hash drifted")

    return {
        "status": "PASS",
        "decision": report["decision"],
        "next_stage": report["next_stage"],
        "selected_policy": report["selected_policy"],
        "control_parity_rows": int(control["row_count"]),
        "rs_invariance_metric_rows": int(rs["metric_comparison_rows"]),
        "governor_parity_comparisons": int(governor_parity["comparison_count"]),
        "causality_gates_passed": int(sum(bool(v) for v in causality["gates"].values())),
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
            "schema_version": ("rd33-p1-input-conformance-audit-v1"),
            "stage": ("RD33_P1_TEMPORAL_MB_ARCHITECTURE_2022_2023"),
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
        governor,
        pending,
    ) = run_all_portfolios(
        rd31=rd31,
        events=events,
        frames=frames,
        state_frame=state_frame,
        membership=membership,
    )

    control_parity = verify_control_parity_vs_rd32(
        repo,
        run_metrics,
    )
    rs_invariance = verify_rs_only_invariance(
        run_metrics=run_metrics,
        trades=trades,
    )
    governor_parity = verify_governor_transition_parity(
        governor,
    )
    causality = verify_causality_mapping(
        events=events,
        trades=trades,
        pending=pending,
        governor=governor,
        control_parity=control_parity,
        rs_invariance=rs_invariance,
        governor_parity=governor_parity,
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
        governor_parity=governor_parity,
        causality=causality,
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
    pending.to_csv(
        output / "pending-lifecycle-ledger.csv",
        index=False,
        lineterminator="\n",
    )
    governor.to_csv(
        output / "governor-transition-ledger.csv",
        index=False,
        lineterminator="\n",
    )
    write_json(
        output / "control-parity-vs-rd32.json",
        control_parity,
    )
    write_json(
        output / "rs-only-invariance.json",
        rs_invariance,
    )
    write_json(
        output / "governor-transition-parity.json",
        governor_parity,
    )
    write_json(
        output / "causality-mapping-audit.json",
        causality,
    )
    write_json(
        output / "selected-temporal-mb-policy-freeze.json",
        selected_freeze,
    )
    write_json(
        output / "rd33-p1-temporal-mb-architecture-report-v1.json",
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

    if not causality["passed"]:
        raise RunnerError(
            "RD33 causality/mapping gates failed; economic outputs preserved for forensic recovery"
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
        print(f"RD33_P1_ERROR={exc}", file=sys.stderr)
        raise
