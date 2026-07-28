"""Run RD04-D5B2 structural-stop evaluation on fixed and PIT universes."""

from __future__ import annotations

import json
import math
import subprocess
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pandas as pd
import run_rd04_d1_pit_universe_replay as d1
from ams_md01_common import atomic_json, atomic_text, sha256

import spotbot.research.ams_md01_momentum as md01
import spotbot.research.rd04_structural_stop_overlay_engine as overlay
from spotbot.research.ams_md01_momentum import (
    FOLDS,
    MD01FoldResult,
    aggregate_fold_metrics,
    fold_metrics,
)
from spotbot.research.rd04_pit_universe_replay import (
    filter_ranked_universe,
    validate_weekly_universe,
    weekly_universe_map,
)
from spotbot.research.rd04_structural_stop_evaluation import (
    DECISION_BLOCKED,
    RESEARCH_STAGE,
    SCHEMA_VERSION,
    build_decision,
    comparison_metrics,
    full_result_equal,
    validate_report,
)
from spotbot.research.rd04_structural_stop_source_transform import (
    BASE_SOURCE_SHA256,
    sha256_text,
    validate_generated_source,
)

D1_RUNTIME: Any = d1
OVERLAY_RUNTIME: Any = overlay

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "reports" / "research"

D1_AGGREGATE = REPORTS / "ams-rd04-d1-aggregate-metrics-v1.csv"
D1_REPORT = REPORTS / "ams-rd04-d1-pit-universe-replay-v1.json"
D5B1_REPORT = REPORTS / "ams-rd04-d5b1-stop-protocol-adjudication-v1.json"
BASE_SOURCE = ROOT / "src/spotbot/research/ams_md01_momentum.py"
OVERLAY_SOURCE = ROOT / "src/spotbot/research/rd04_structural_stop_overlay_engine.py"

FOLD_CSV = REPORTS / "ams-rd04-d5b2-fold-metrics-v1.csv"
AGGREGATE_CSV = REPORTS / "ams-rd04-d5b2-aggregate-metrics-v1.csv"
COMPARISON_CSV = REPORTS / "ams-rd04-d5b2-comparison-v1.csv"
PARITY_CSV = REPORTS / "ams-rd04-d5b2-control-parity-v1.csv"
STOP_AUDIT_CSV = REPORTS / "ams-rd04-d5b2-stop-audit-v1.csv"
RECOVERY_CSV = REPORTS / "ams-rd04-d5b2-stopped-trade-recovery-v1.csv"
BASE_TRADES_CSV = REPORTS / "ams-rd04-d5b2-base-cost-trades-v1.csv"
REPORT_JSON = REPORTS / "ams-rd04-d5b2-structural-stop-evaluation-v1.json"
REPORT_MD = REPORTS / "ams-rd04-d5b2-structural-stop-evaluation-v1.md"
FINAL_COPY = ROOT / "RD04_D5B2_RESULT_FOR_CHATGPT.md"

COST_MODES: tuple[tuple[str, float], ...] = (
    ("ZERO_COST", 0.0),
    ("BASE_COST", 0.002),
    ("STRESS_0_4_PERCENT", 0.004),
)
UNIVERSE_MODES = ("FIXED_SURVIVOR_30", "PIT_UNIVERSE")


class StructuralStopEvaluationRunError(RuntimeError):
    """Raised when live D5B2 evidence is structurally unsafe."""


def utc_now() -> str:
    return datetime.now(tz=UTC).isoformat().replace("+00:00", "Z")


def source_commit() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
    ).strip()


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise StructuralStopEvaluationRunError(f"Expected JSON object: {path}")
    return cast(dict[str, Any], payload)


def file_sha256(path: Path) -> str:
    return sha256(path)


def canonical_float_equal(
    observed: float,
    expected: float,
    *,
    tolerance: float = 1e-10,
) -> bool:
    return math.isclose(
        observed,
        expected,
        rel_tol=tolerance,
        abs_tol=tolerance,
    )


def verify_upstream() -> dict[str, Any]:
    d0c_report = load_json(d1.D0C_REPORT)
    d0c_registration = load_json(d1.D0C_REGISTRATION)
    d1_report = load_json(D1_REPORT)
    d5b1_report = load_json(D5B1_REPORT)

    d0c_decision = d0c_report.get("decision")
    if not isinstance(d0c_decision, Mapping):
        raise StructuralStopEvaluationRunError("RD04-D0C decision is missing.")
    if d0c_decision.get("decision") != "PIT_UNIVERSE_REPLAY_READY":
        raise StructuralStopEvaluationRunError("RD04-D0C replay contract is not ready.")
    if d0c_decision.get("rd04_d1_pit_universe_replay_research_authorized") is not True:
        raise StructuralStopEvaluationRunError("RD04-D0C did not authorize replay research.")
    if d0c_registration.get("status") != "PASS":
        raise StructuralStopEvaluationRunError("RD04-D0C dataset registration is not PASS.")
    if d1_report.get("status") != "COMPLETE":
        raise StructuralStopEvaluationRunError("RD04-D1 is not COMPLETE.")
    if d5b1_report.get("status") != "COMPLETE":
        raise StructuralStopEvaluationRunError("RD04-D5B1 is not COMPLETE.")

    decision = d5b1_report.get("decision")
    if not isinstance(decision, Mapping):
        raise StructuralStopEvaluationRunError("D5B1 decision is missing.")
    if decision.get("decision") != "V5R1_DERIVED_EXIT_ONLY_STOP_OVERLAY_REGISTERED":
        raise StructuralStopEvaluationRunError("D5B1 decision drifted.")
    if decision.get("d5b2_stop_execution_research_authorized") is not True:
        raise StructuralStopEvaluationRunError("D5B2 execution research is not authorized.")
    if decision.get("trade_logic_changed") is not False:
        raise StructuralStopEvaluationRunError("D5B1 improperly changed trade logic.")

    contract = d5b1_report.get("contract")
    if not isinstance(contract, Mapping):
        raise StructuralStopEvaluationRunError("D5B1 contract is missing.")
    formula = contract.get("stop_formula")
    execution = contract.get("execution_contract")
    comparison = contract.get("comparison_contract")
    if not isinstance(formula, Mapping):
        raise StructuralStopEvaluationRunError("Stop formula is missing.")
    if formula.get("minimum_atr") != 2.2:
        raise StructuralStopEvaluationRunError("Minimum ATR drifted.")
    if formula.get("maximum_atr") != 3.4:
        raise StructuralStopEvaluationRunError("Maximum ATR drifted.")
    if not isinstance(execution, Mapping):
        raise StructuralStopEvaluationRunError("Execution contract is missing.")
    if execution.get("fixed_stop") is not True:
        raise StructuralStopEvaluationRunError("Fixed stop was not frozen.")
    if execution.get("trailing_allowed") is not False:
        raise StructuralStopEvaluationRunError("Trailing was enabled.")
    if not isinstance(comparison, Mapping):
        raise StructuralStopEvaluationRunError("Comparison contract is missing.")
    if comparison.get("control_replay_must_match_d1") is not True:
        raise StructuralStopEvaluationRunError("D1 replay gate drifted.")

    base_text = BASE_SOURCE.read_text(encoding="utf-8")
    if sha256_text(base_text) != BASE_SOURCE_SHA256:
        raise StructuralStopEvaluationRunError("M05 source hash drifted.")
    overlay_text = OVERLAY_SOURCE.read_text(encoding="utf-8")
    validate_generated_source(overlay_text)

    return {
        "d1_decision": cast(Mapping[str, Any], d1_report["decision"]).get("decision"),
        "d5b1_decision": decision.get("decision"),
        "d5b1_evidence_commit": ("518e3ce6bdb653046ff66e15d5ef7139c64b4587"),
        "base_source_sha256": file_sha256(BASE_SOURCE),
        "overlay_source_sha256": file_sha256(OVERLAY_SOURCE),
    }


@contextmanager
def pit_universe_filter(
    universe_by_time: Mapping[pd.Timestamp, frozenset[str]],
) -> Iterator[None]:
    original_base = md01.eligible_universe_at
    original_overlay = OVERLAY_RUNTIME.eligible_universe_at

    def scheduled_eligibility(
        *,
        timestamp: pd.Timestamp,
        horizon_days: int,
        daily: pd.DataFrame,
        eight_hour: pd.DataFrame,
        four_hour: pd.DataFrame,
        availability: pd.DataFrame,
    ) -> tuple[pd.DataFrame, dict[str, Any]]:
        ranked, audit = original_base(
            timestamp=timestamp,
            horizon_days=horizon_days,
            daily=daily,
            eight_hour=eight_hour,
            four_hour=four_hour,
            availability=availability,
        )
        return filter_ranked_universe(
            ranked,
            audit,
            timestamp=timestamp,
            universe_by_time=universe_by_time,
        )

    md01._REBALANCE_CACHE.clear()
    OVERLAY_RUNTIME._REBALANCE_CACHE.clear()
    md01.eligible_universe_at = scheduled_eligibility
    OVERLAY_RUNTIME.eligible_universe_at = scheduled_eligibility
    try:
        yield
    finally:
        md01.eligible_universe_at = original_base
        OVERLAY_RUNTIME.eligible_universe_at = original_overlay
        md01._REBALANCE_CACHE.clear()
        OVERLAY_RUNTIME._REBALANCE_CACHE.clear()


def run_original_fold(
    frames: Mapping[str, pd.DataFrame],
    *,
    fold_id: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
    transaction_cost: float,
    universe_by_time: Mapping[pd.Timestamp, frozenset[str]] | None,
) -> MD01FoldResult:
    md01._REBALANCE_CACHE.clear()
    if universe_by_time is None:
        return md01.simulate_md01_fold(
            four_hour=frames["four_hour"],
            daily=frames["daily"],
            eight_hour=frames["eight_hour"],
            availability=frames["availability"],
            variant_id="MD01-M05",
            fold_id=fold_id,
            validation_start=start,
            validation_end=end,
            transaction_cost=transaction_cost,
        )
    with pit_universe_filter(universe_by_time):
        return md01.simulate_md01_fold(
            four_hour=frames["four_hour"],
            daily=frames["daily"],
            eight_hour=frames["eight_hour"],
            availability=frames["availability"],
            variant_id="MD01-M05",
            fold_id=fold_id,
            validation_start=start,
            validation_end=end,
            transaction_cost=transaction_cost,
        )


def run_generated_fold(
    frames: Mapping[str, pd.DataFrame],
    *,
    fold_id: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
    transaction_cost: float,
    universe_by_time: Mapping[pd.Timestamp, frozenset[str]] | None,
    stop_overlay: bool,
) -> MD01FoldResult:
    OVERLAY_RUNTIME._REBALANCE_CACHE.clear()
    if universe_by_time is None:
        return overlay.simulate_md01_fold_overlay(
            four_hour=frames["four_hour"],
            daily=frames["daily"],
            eight_hour=frames["eight_hour"],
            availability=frames["availability"],
            variant_id="MD01-M05",
            fold_id=fold_id,
            validation_start=start,
            validation_end=end,
            transaction_cost=transaction_cost,
            stop_overlay=stop_overlay,
        )
    with pit_universe_filter(universe_by_time):
        return overlay.simulate_md01_fold_overlay(
            four_hour=frames["four_hour"],
            daily=frames["daily"],
            eight_hour=frames["eight_hour"],
            availability=frames["availability"],
            variant_id="MD01-M05",
            fold_id=fold_id,
            validation_start=start,
            validation_end=end,
            transaction_cost=transaction_cost,
            stop_overlay=stop_overlay,
        )


def aggregate_row(
    results: Sequence[MD01FoldResult],
    *,
    universe_mode: str,
    portfolio_mode: str,
    cost_mode: str,
    transaction_cost: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    aggregate = {str(key): value for key, value in aggregate_fold_metrics(results).items()}
    row = {
        "universe_mode": universe_mode,
        "portfolio_mode": portfolio_mode,
        "cost_mode": cost_mode,
        "transaction_cost": transaction_cost,
        **{key: value for key, value in aggregate.items() if key != "folds"},
    }
    return row, aggregate


def fold_rows(
    results: Sequence[MD01FoldResult],
    *,
    universe_mode: str,
    portfolio_mode: str,
    cost_mode: str,
    transaction_cost: float,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for result in results:
        metric_values = {str(key): value for key, value in fold_metrics(result).items()}
        rows.append(
            {
                "universe_mode": universe_mode,
                "portfolio_mode": portfolio_mode,
                "cost_mode": cost_mode,
                "transaction_cost": transaction_cost,
                "fold_id": result.fold_id,
                "status": result.status,
                **metric_values,
            }
        )
    return rows


def d1_aggregate_lookup() -> dict[tuple[str, str], dict[str, Any]]:
    frame = pd.read_csv(D1_AGGREGATE)
    return {
        (str(row["universe_mode"]), str(row["cost_mode"])): {
            str(key): value for key, value in row.items()
        }
        for row in frame.to_dict(orient="records")
    }


def required_metric_float(
    values: Mapping[str, Any],
    field: str,
) -> float:
    raw_value = values.get(field)
    if raw_value is None:
        raise StructuralStopEvaluationRunError(f"Required aggregate metric is missing: {field}")
    try:
        return float(cast(Any, raw_value))
    except (TypeError, ValueError) as error:
        raise StructuralStopEvaluationRunError(
            f"Aggregate metric is not scalar numeric: {field}"
        ) from error


def aggregate_matches_d1(
    aggregate_row_value: Mapping[str, Any],
    expected: Mapping[str, Any],
) -> bool:
    fields = (
        "compounded_return",
        "mean_fold_return",
        "positive_folds",
        "worst_fold_return",
        "mean_maximum_drawdown",
        "profit_factor",
        "expectancy",
        "trade_count",
        "turnover",
        "fees",
    )
    for field in fields:
        observed = aggregate_row_value.get(field)
        reference = expected.get(field)
        if pd.isna(observed) and pd.isna(reference):
            continue
        observed_float = required_metric_float(
            aggregate_row_value,
            field,
        )
        reference_float = required_metric_float(expected, field)
        if not canonical_float_equal(observed_float, reference_float):
            return False
    return bool(
        aggregate_row_value.get("reconciliation_status") == expected.get("reconciliation_status")
    )


def stop_audit_rows(
    results: Sequence[MD01FoldResult],
    *,
    universe_mode: str,
    cost_mode: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for result in results:
        for candidate in result.candidates:
            if not candidate.get("rd04_stop_overlay_registered"):
                continue
            rows.append(
                {
                    "universe_mode": universe_mode,
                    "cost_mode": cost_mode,
                    "fold_id": result.fold_id,
                    "candidate_id": candidate.get("candidate_id"),
                    "symbol": candidate.get("symbol"),
                    "signal_bar_close": candidate.get("signal_bar_close"),
                    "scheduled_entry": candidate.get("scheduled_entry"),
                    "accepted": candidate.get("accepted"),
                    "fill_timestamp": candidate.get("fill_timestamp"),
                    "fill_price": candidate.get("fill_price"),
                    "signal_atr": candidate.get("rd04_signal_atr"),
                    "structural_reference": candidate.get("rd04_structural_reference"),
                    "raw_distance_atr": candidate.get("rd04_raw_distance_atr"),
                    "applied_distance_atr": candidate.get("rd04_applied_distance_atr"),
                    "stop_price": candidate.get("rd04_stop_price"),
                    "stop_classification": candidate.get("rd04_stop_classification"),
                    "stop_exit_time": candidate.get("rd04_stop_exit_time"),
                    "stop_exit_price": candidate.get("rd04_stop_exit_price"),
                    "stop_exit_reason": candidate.get("rd04_stop_exit_reason"),
                }
            )
    return rows


def trade_rows(
    results: Sequence[MD01FoldResult],
    *,
    universe_mode: str,
    portfolio_mode: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for result in results:
        for trade in result.trades:
            rows.append(
                {
                    "universe_mode": universe_mode,
                    "portfolio_mode": portfolio_mode,
                    "fold_id": result.fold_id,
                    **d1.finite(asdict(trade)),
                }
            )
    return rows


def stopped_trade_recovery_rows(
    *,
    control_results: Sequence[MD01FoldResult],
    treatment_results: Sequence[MD01FoldResult],
    four_hour: pd.DataFrame,
    universe_mode: str,
) -> list[dict[str, Any]]:
    control_index = {
        (
            result.fold_id,
            trade.symbol,
            trade.candidate_id,
            trade.entry_time,
        ): trade
        for result in control_results
        for trade in result.trades
    }
    source = four_hour.copy()
    source["bar_open_time"] = pd.to_datetime(
        source["bar_open_time"],
        utc=True,
    )
    rows: list[dict[str, Any]] = []
    for result in treatment_results:
        for trade in result.trades:
            if trade.exit_reason not in {
                "STRUCTURAL_ATR_GAP_STOP",
                "STRUCTURAL_ATR_STOP",
            }:
                continue
            key = (
                result.fold_id,
                trade.symbol,
                trade.candidate_id,
                trade.entry_time,
            )
            control_trade = control_index.get(key)
            matched = control_trade is not None
            recovery_mfe: float | None = None
            if control_trade is not None:
                interval = source.loc[
                    source["symbol"].eq(trade.symbol)
                    & (source["bar_open_time"] > trade.exit_time)
                    & (source["bar_open_time"] < control_trade.exit_time)
                ]
                recovery_mfe = (
                    float(interval["high"].max()) / trade.exit_price - 1.0
                    if not interval.empty
                    else 0.0
                )
            rows.append(
                {
                    "universe_mode": universe_mode,
                    "fold_id": result.fold_id,
                    "symbol": trade.symbol,
                    "candidate_id": trade.candidate_id,
                    "entry_time": trade.entry_time,
                    "stop_exit_time": trade.exit_time,
                    "stop_exit_price": trade.exit_price,
                    "stop_exit_reason": trade.exit_reason,
                    "matched_control_trade": matched,
                    "control_exit_time": (
                        control_trade.exit_time if control_trade is not None else None
                    ),
                    "control_exit_price": (
                        control_trade.exit_price if control_trade is not None else None
                    ),
                    "stopped_trade_recovery_mfe": recovery_mfe,
                }
            )
    return rows


def markdown_report(report: Mapping[str, Any]) -> str:
    decision = cast(Mapping[str, Any], report["decision"])
    pit = cast(Mapping[str, Any], report["pit_comparison"])
    base = cast(Mapping[str, Any], pit["BASE_COST"])
    stress = cast(Mapping[str, Any], pit["STRESS_0_4_PERCENT"])
    lines = [
        "# AMS RD04-D5B2 — Structural Stop Evaluation",
        "",
        "## Executive result",
        "",
        f"- Status: `{report['status']}`",
        f"- Decision: `{decision['decision']}`",
        (f"- PIT base compounded-return delta: `{base['compounded_return_delta']}`"),
        f"- PIT base expectancy delta: `{base['expectancy_delta']}`",
        (f"- PIT mean-drawdown reduction: `{base['maximum_drawdown_reduction']}`"),
        (f"- PIT trade CVaR10 improvement: `{base['trade_cvar_10_improvement']}`"),
        f"- Improved PIT base folds: `{base['improved_folds']}`",
        (f"- PIT stress compounded-return delta: `{stress['compounded_return_delta']}`"),
        "",
        "## Validation",
        "",
        "- Generated control equals the original M05 engine exactly.",
        "- Generated control reproduces the committed RD04-D1 aggregates.",
        "- All control and treatment ledgers reconcile.",
        "- Entry logic and entry-weight source expressions are unchanged.",
        "",
        "## Safety boundary",
        "",
        "- Research-only exit overlay; no production authorization.",
        "- No PIT baseline, universe, ranking, entry, or weight authorization.",
        "- No 2025 test or 2026 holdout access.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    upstream = verify_upstream()

    registration = d1.load_json(d1.D0C_REGISTRATION)
    fixed_frames, fixed_hashes = D1_RUNTIME.load_registered_data()
    pit_frames, pit_hashes = d1.load_adjudicated_data(registration)
    candidates = pd.read_csv(d1.D0C_CANDIDATES)
    schedule_validation = validate_weekly_universe(candidates)
    if schedule_validation["passed"] is not True:
        raise StructuralStopEvaluationRunError(
            f"PIT schedule validation failed: {schedule_validation}"
        )
    pit_schedule = weekly_universe_map(candidates)

    d1_lookup = d1_aggregate_lookup()
    fold_output: list[dict[str, Any]] = []
    aggregate_output: list[dict[str, Any]] = []
    comparison_output: list[dict[str, Any]] = []
    parity_output: list[dict[str, Any]] = []
    stop_output: list[dict[str, Any]] = []
    base_trade_output: list[dict[str, Any]] = []
    recovery_output: list[dict[str, Any]] = []

    original_vs_generated_exact = True
    generated_matches_d1 = True
    all_reconciliations = True

    for cost_mode, transaction_cost in COST_MODES:
        print(f"RD04_D5B2_COST_MODE={cost_mode}")
        for universe_mode in UNIVERSE_MODES:
            universe = None if universe_mode == "FIXED_SURVIVOR_30" else pit_schedule
            frames = fixed_frames if universe_mode == "FIXED_SURVIVOR_30" else pit_frames
            original_results: list[MD01FoldResult] = []
            control_results: list[MD01FoldResult] = []
            treatment_results: list[MD01FoldResult] = []
            for fold_id, start, end in FOLDS:
                original = run_original_fold(
                    frames,
                    fold_id=fold_id,
                    start=start,
                    end=end,
                    transaction_cost=transaction_cost,
                    universe_by_time=universe,
                )
                control = run_generated_fold(
                    frames,
                    fold_id=fold_id,
                    start=start,
                    end=end,
                    transaction_cost=transaction_cost,
                    universe_by_time=universe,
                    stop_overlay=False,
                )
                treatment = run_generated_fold(
                    frames,
                    fold_id=fold_id,
                    start=start,
                    end=end,
                    transaction_cost=transaction_cost,
                    universe_by_time=universe,
                    stop_overlay=True,
                )
                exact = full_result_equal(original, control)
                original_vs_generated_exact &= exact
                parity_output.append(
                    {
                        "universe_mode": universe_mode,
                        "cost_mode": cost_mode,
                        "fold_id": fold_id,
                        "original_vs_generated_control_exact": exact,
                        "original_final_cash": original.final_cash,
                        "generated_final_cash": control.final_cash,
                        "original_trade_count": len(original.trades),
                        "generated_trade_count": len(control.trades),
                    }
                )
                original_results.append(original)
                control_results.append(control)
                treatment_results.append(treatment)

            for portfolio_mode, results in (
                ("CONTROL", control_results),
                ("TREATMENT", treatment_results),
            ):
                fold_output.extend(
                    fold_rows(
                        results,
                        universe_mode=universe_mode,
                        portfolio_mode=portfolio_mode,
                        cost_mode=cost_mode,
                        transaction_cost=transaction_cost,
                    )
                )
                aggregate_row_value, aggregate = aggregate_row(
                    results,
                    universe_mode=universe_mode,
                    portfolio_mode=portfolio_mode,
                    cost_mode=cost_mode,
                    transaction_cost=transaction_cost,
                )
                aggregate_output.append(aggregate_row_value)
                all_reconciliations &= (
                    aggregate.get("reconciliation_status") == "PASS"
                    and aggregate.get("open_positions_after_fold") == 0
                )

            control_row = next(
                row
                for row in aggregate_output
                if row["universe_mode"] == universe_mode
                and row["portfolio_mode"] == "CONTROL"
                and row["cost_mode"] == cost_mode
            )
            expected = d1_lookup[(universe_mode, cost_mode)]
            generated_matches_d1 &= aggregate_matches_d1(
                control_row,
                expected,
            )

            control_aggregate = dict(aggregate_fold_metrics(control_results))
            treatment_aggregate = dict(aggregate_fold_metrics(treatment_results))
            metrics = comparison_metrics(
                control_aggregate=control_aggregate,
                treatment_aggregate=treatment_aggregate,
                control_results=control_results,
                treatment_results=treatment_results,
            )
            comparison_output.append(
                {
                    "universe_mode": universe_mode,
                    "cost_mode": cost_mode,
                    "transaction_cost": transaction_cost,
                    **metrics,
                }
            )
            stop_output.extend(
                stop_audit_rows(
                    treatment_results,
                    universe_mode=universe_mode,
                    cost_mode=cost_mode,
                )
            )

            if cost_mode == "BASE_COST":
                base_trade_output.extend(
                    trade_rows(
                        control_results,
                        universe_mode=universe_mode,
                        portfolio_mode="CONTROL",
                    )
                )
                base_trade_output.extend(
                    trade_rows(
                        treatment_results,
                        universe_mode=universe_mode,
                        portfolio_mode="TREATMENT",
                    )
                )
                recovery_output.extend(
                    stopped_trade_recovery_rows(
                        control_results=control_results,
                        treatment_results=treatment_results,
                        four_hour=frames["four_hour"],
                        universe_mode=universe_mode,
                    )
                )

    pit_comparison = {
        cost_mode: next(
            row
            for row in comparison_output
            if row["universe_mode"] == "PIT_UNIVERSE" and row["cost_mode"] == cost_mode
        )
        for cost_mode, _ in COST_MODES
    }
    decision = build_decision(
        data_contract_passed=all_reconciliations,
        control_replay_passed=(original_vs_generated_exact and generated_matches_d1),
        base_metrics=pit_comparison["BASE_COST"],
        zero_metrics=pit_comparison["ZERO_COST"],
        stress_metrics=pit_comparison["STRESS_0_4_PERCENT"],
    )
    if decision["decision"] == DECISION_BLOCKED:
        raise StructuralStopEvaluationRunError("D5B2 data or replay contract failed.")

    d1.write_csv(FOLD_CSV, pd.DataFrame(fold_output))
    d1.write_csv(AGGREGATE_CSV, pd.DataFrame(aggregate_output))
    d1.write_csv(COMPARISON_CSV, pd.DataFrame(comparison_output))
    d1.write_csv(PARITY_CSV, pd.DataFrame(parity_output))
    d1.write_csv(STOP_AUDIT_CSV, pd.DataFrame(stop_output))
    d1.write_csv(RECOVERY_CSV, pd.DataFrame(recovery_output))
    d1.write_csv(BASE_TRADES_CSV, pd.DataFrame(base_trade_output))

    accepted_stop_rows = [row for row in stop_output if row.get("accepted") is True]
    classification_counts = (
        pd.DataFrame(accepted_stop_rows)["stop_classification"].value_counts(dropna=False).to_dict()
        if accepted_stop_rows
        else {}
    )
    matched_recovery = [
        float(row["stopped_trade_recovery_mfe"])
        for row in recovery_output
        if row["stopped_trade_recovery_mfe"] is not None
    ]

    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "research_stage": RESEARCH_STAGE,
        "status": "COMPLETE",
        "generated_at": utc_now(),
        "source_commit": source_commit(),
        "upstream": upstream,
        "data": {
            "fixed_hashes": fixed_hashes,
            "pit_hashes": pit_hashes,
            "pit_snapshot_count": len(pit_schedule),
        },
        "validation": {
            "data_contract_passed": all_reconciliations,
            "original_vs_generated_control_exact": (original_vs_generated_exact),
            "generated_control_matches_d1": generated_matches_d1,
            "all_reconciliations_passed": all_reconciliations,
            "entry_logic_source_parity_passed": True,
            "position_weight_source_parity_passed": True,
        },
        "pit_comparison": d1.finite(pit_comparison),
        "all_comparisons": d1.finite(comparison_output),
        "stop_diagnostics": {
            "classification_counts": d1.finite(classification_counts),
            "stop_audit_row_count": len(stop_output),
            "recovery_row_count": len(recovery_output),
            "matched_recovery_count": len(matched_recovery),
            "mean_stopped_trade_recovery_mfe": (
                sum(matched_recovery) / len(matched_recovery) if matched_recovery else None
            ),
        },
        "decision": decision,
        "next_stage": "RD04-D5C0-EXTERNAL-EVENT-SOURCE-FREEZE",
        "safety": {
            "spot_only": True,
            "long_only": True,
            "portfolio_simulation_executed": True,
            "test_2025_accessed": False,
            "holdout_2026_accessed": False,
            "parameter_optimisation_used": False,
            "outcome_based_stop_selection_used": False,
            "leverage_used": False,
            "margin_used": False,
            "shorting_used": False,
            "trade_logic_changed": False,
        },
        "outputs": {
            "fold_metrics": FOLD_CSV.relative_to(ROOT).as_posix(),
            "aggregate_metrics": AGGREGATE_CSV.relative_to(ROOT).as_posix(),
            "comparison": COMPARISON_CSV.relative_to(ROOT).as_posix(),
            "control_parity": PARITY_CSV.relative_to(ROOT).as_posix(),
            "stop_audit": STOP_AUDIT_CSV.relative_to(ROOT).as_posix(),
            "stopped_trade_recovery": RECOVERY_CSV.relative_to(ROOT).as_posix(),
            "base_cost_trades": BASE_TRADES_CSV.relative_to(ROOT).as_posix(),
        },
    }

    report_text = markdown_report(report)
    atomic_text(REPORT_MD, report_text)
    atomic_text(FINAL_COPY, report_text)
    output_paths = (
        REPORT_MD,
        FINAL_COPY,
        FOLD_CSV,
        AGGREGATE_CSV,
        COMPARISON_CSV,
        PARITY_CSV,
        STOP_AUDIT_CSV,
        RECOVERY_CSV,
        BASE_TRADES_CSV,
    )
    report["output_hashes"] = {
        path.relative_to(ROOT).as_posix(): file_sha256(path) for path in output_paths
    }
    atomic_json(REPORT_JSON, d1.finite(report))
    validate_report(report)

    base = pit_comparison["BASE_COST"]
    stress = pit_comparison["STRESS_0_4_PERCENT"]
    print("RD04_D5B2_STATUS=COMPLETE")
    print(f"DECISION={decision['decision']}")
    print(f"ORIGINAL_VS_GENERATED_CONTROL_EXACT={original_vs_generated_exact}")
    print(f"GENERATED_CONTROL_MATCHES_D1={generated_matches_d1}")
    print(f"ALL_RECONCILIATIONS_PASSED={all_reconciliations}")
    print(f"PIT_BASE_RETURN_DELTA={base['compounded_return_delta']}")
    print(f"PIT_BASE_EXPECTANCY_DELTA={base['expectancy_delta']}")
    print(f"PIT_BASE_DRAWDOWN_REDUCTION={base['maximum_drawdown_reduction']}")
    print(f"PIT_BASE_CVAR10_IMPROVEMENT={base['trade_cvar_10_improvement']}")
    print(f"IMPROVED_PIT_BASE_FOLDS={base['improved_folds']}")
    print(f"PIT_STRESS_RETURN_DELTA={stress['compounded_return_delta']}")
    print("NEXT_STAGE=RD04-D5C0-EXTERNAL-EVENT-SOURCE-FREEZE")
    print("POINT_IN_TIME_UNIVERSE_RESEARCH_BASELINE_AUTHORIZED=False")
    print("PRODUCTION_EXIT_CHANGE_AUTHORIZED=False")
    print("TRADE_LOGIC_CHANGED=False")
    print("ATI_V1_AUTHORIZED=False")


if __name__ == "__main__":
    main()
