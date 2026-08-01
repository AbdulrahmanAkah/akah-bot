from __future__ import annotations

import math
import shutil
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, cast

import pandas as pd

from spotbot.research import rd16n_evaluation as rd16n
from spotbot.research import rd16q_evaluation as rd16q
from spotbot.research import rd16s_evaluation as rd16s
from spotbot.research.rd16c_common import (
    BRANCH,
    ROOT,
    SEALED_CUTOFF,
    dataframe_content_hash,
    read_json_object,
    sha256_path,
)
from spotbot.research.rd16c_features import build_feature_frame
from spotbot.research.rd16d_common import (
    BASE_FEE_RATE,
    INITIAL_EQUITY,
    STRATEGIC_MONTHLY_TARGET,
    write_csv,
    write_json,
)
from spotbot.research.rd16d_metrics import build_benchmark_daily, enrich_trades
from spotbot.research.rd16n_signals import SignalHypothesis
from spotbot.research.rd16s_signals import CORE_SYMBOLS, ELIGIBLE_SYMBOLS, NONCORE_SYMBOLS
from spotbot.research.rd16t_signals import (
    ARCHITECTURE_ID,
    HYPOTHESIS_REGISTRY,
    LongHorizonHypothesis,
    build_long_horizon_candidates,
    build_long_horizon_feature_frames,
    hypothesis_registry_rows,
)

SCHEMA_VERSION: Final = "rd16t-signal-architecture-reset-long-horizon-research-v1"
DECISION: Final = "RD16T_SIGNAL_ARCHITECTURE_RESET_AND_LONG_HORIZON_RESEARCH_COMPLETED"
EVIDENCE_CLASSIFICATION: Final = "LONG_HORIZON_SIGNAL_ARCHITECTURE_EVIDENCE_EXTRACTED"
NEXT_ASSEMBLY: Final = "RD16U_LONG_HORIZON_ALPHA_ARCHITECTURE_ASSEMBLY"
NEXT_REFINEMENT: Final = "RD16U_LONG_HORIZON_SIGNAL_REFINEMENT"
NEXT_RESET: Final = "RD16U_REGIME_ADAPTIVE_EXIT_AND_EVENT_DRIVEN_RESEARCH"
ALL_OVERLAY_ID: Final = "ALL_RD16T_LONG_HORIZON_HYPOTHESES_OVERLAY"

RD16L_ROOT: Final = ROOT / "data" / "research" / "rd16l"
RD16M_ROOT: Final = ROOT / "data" / "research" / "rd16m"
RD16R_ROOT: Final = ROOT / "data" / "research" / "rd16r"
RD16S_ROOT: Final = ROOT / "data" / "research" / "rd16s"
RD16T_ROOT: Final = ROOT / "data" / "research" / "rd16t"
RD16T_LOCAL_ROOT: Final = ROOT / "data" / "raw" / "rd16t"
REPORTS_ROOT: Final = ROOT / "reports" / "research"

REGISTRY_FIELDS: Final = (
    "hypothesis_id",
    "engine_id",
    "role",
    "description",
    "allowed_regimes",
    "initial_stop_atr_multiple",
    "trail_activation_r",
    "trail_atr_multiple",
    "cooldown_hours",
    "engine_priority",
    "normal_holding_bars",
    "strong_bull_holding_bars",
    "fixed_conditions",
)
SUMMARY_FIELDS: Final = (
    "hypothesis_id",
    "engine_id",
    "role",
    "decision",
    "carry_forward",
    "candidate_count",
    "candidate_assets",
    "standalone_trade_count",
    "standalone_net_return",
    "standalone_monthly_geometric_return",
    "standalone_profit_factor",
    "standalone_maximum_drawdown",
    "standalone_two_x_net_return",
    "standalone_two_x_profit_factor",
    "standalone_two_x_capital_feasible",
    "standalone_positive_active_year_fraction",
    "standalone_top_3_trade_profit_share",
    "standalone_median_bars_held",
    "standalone_long_hold_share",
    "standalone_trailing_exit_share",
    "overlay_new_trade_count",
    "overlay_net_return",
    "overlay_monthly_geometric_return",
    "overlay_profit_factor",
    "overlay_maximum_drawdown",
    "overlay_capital_feasible",
    "overlay_two_x_net_return",
    "overlay_two_x_profit_factor",
    "overlay_two_x_capital_feasible",
    "overlay_mean_high_opportunity_capture",
    "overlay_delta_net_return_vs_v3",
    "overlay_delta_profit_factor_vs_v3",
    "overlay_delta_drawdown_vs_v3",
    "overlay_delta_two_x_return_vs_v3",
    "overlay_delta_capture_vs_v3",
    "noncore_overlay_trade_count",
    "noncore_overlay_net_pnl",
    "noncore_overlay_profit_factor",
    "long_horizon_evidence",
    "strategic_objective_met",
    "rationale",
)
DECISION_FIELDS: Final = (
    "hypothesis_id",
    "decision",
    "carry_forward",
    "long_horizon_evidence",
    "standalone_net_return",
    "standalone_profit_factor",
    "standalone_median_bars_held",
    "overlay_delta_net_return_vs_v3",
    "overlay_profit_factor",
    "overlay_two_x_capital_feasible",
    "noncore_overlay_net_pnl",
    "rationale",
)
EXIT_FIELDS: Final = (
    "scope",
    "variant_id",
    "exit_reason",
    "trade_count",
    "net_pnl",
    "return_on_initial_equity",
    "win_rate",
    "profit_factor",
    "median_bars_held",
)
ALL_OVERLAY_FIELDS: Final = (
    "variant_id",
    "new_trade_count",
    "trade_count",
    "net_return",
    "monthly_geometric_return",
    "profit_factor",
    "maximum_drawdown",
    "minimum_cash",
    "capital_feasible",
    "two_x_net_return",
    "two_x_profit_factor",
    "two_x_minimum_cash",
    "two_x_capital_feasible",
    "mean_high_opportunity_capture",
    "delta_net_return_vs_v3",
    "delta_profit_factor_vs_v3",
    "delta_capture_vs_v3",
    "noncore_new_trade_count",
    "noncore_net_pnl",
    "noncore_profit_factor",
)


class RD16TEvaluationError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class LongHorizonDecision:
    decision: str
    carry_forward: bool
    rationale: str
    strategic_objective_met: bool
    long_horizon_evidence: bool
    gates: dict[str, bool]


def _timestamp(value: object) -> pd.Timestamp:
    parsed = pd.Timestamp(cast(Any, value))
    if parsed.tzinfo is None:
        return parsed.tz_localize("UTC")
    return parsed.tz_convert("UTC")


def _finite(value: object, *, name: str) -> float:
    if isinstance(value, bool):
        raise RD16TEvaluationError(f"{name} cannot be boolean.")
    try:
        numeric = float(cast(str | int | float, value))
    except (TypeError, ValueError) as error:
        raise RD16TEvaluationError(f"{name} must be numeric.") from error
    if not math.isfinite(numeric):
        raise RD16TEvaluationError(f"{name} must be finite.")
    return numeric


def _records(frame: pd.DataFrame) -> list[dict[str, object]]:
    return [
        {str(key): value for key, value in raw.items()} for raw in frame.to_dict(orient="records")
    ]


def _profit_factor(values: pd.Series) -> float | None:
    profit = float(values[values > 0.0].sum())
    loss = abs(float(values[values < 0.0].sum()))
    return profit / loss if loss > 0.0 else None


def _metric_profit_factor(metrics: Mapping[str, object]) -> float:
    raw = metrics.get("profit_factor")
    if raw is None:
        return math.inf if _finite(metrics["net_return"], name="net_return") > 0 else 0.0
    return _finite(raw, name="profit_factor")


def _verify_rd16s_ready() -> dict[str, Any]:
    report = read_json_object(RD16S_ROOT / "rd16s-final-report-v1.json")
    expected = {
        "decision": "RD16S_LIMITED_EXPANDED_UNIVERSE_SIGNAL_RESEARCH_COMPLETED",
        "architecture_id": "COMPOSITE_ALPHA_V3",
        "source_universe_size": 6,
        "expanded_universe_size": 10,
        "incremental_noncore_asset_count": 4,
        "domains_evaluated": 5,
        "retained_domain_count": 0,
        "promising_domain_count": 0,
        "strategic_objective_met_count": 0,
        "next_stage": "RD16T_SIGNAL_ARCHITECTURE_RESET_AND_LONG_HORIZON_RESEARCH",
    }
    for key, expected_value in expected.items():
        if report.get(key) != expected_value:
            raise RD16TEvaluationError(f"RD16-S readiness mismatch for {key}: {report.get(key)!r}")
    return report


def _verify_output_manifest(root: Path, *, prefix: str) -> dict[str, str]:
    manifest = read_json_object(root / "output-hashes.json")
    verified: dict[str, str] = {}
    for raw_name, raw_digest in sorted(manifest.items()):
        if not isinstance(raw_name, str) or not isinstance(raw_digest, str):
            raise RD16TEvaluationError(f"{prefix} output manifest is invalid.")
        data_path = root / raw_name
        report_path = REPORTS_ROOT / raw_name
        path = data_path if data_path.is_file() else report_path
        if not path.is_file():
            raise RD16TEvaluationError(f"Missing {prefix} output: {raw_name}")
        actual = sha256_path(path)
        if actual != raw_digest:
            raise RD16TEvaluationError(f"{prefix} output hash mismatch: {raw_name}")
        verified[f"{prefix.lower()}:{raw_name}"] = actual
    return verified


def _frozen_input_hashes(
    local_v3_hashes: Mapping[str, str],
    local_market_hashes: Mapping[str, str],
) -> dict[str, str]:
    tracked = {
        "rd16s/rd16s-final-report-v1.json": RD16S_ROOT / "rd16s-final-report-v1.json",
        "rd16s/validation-report.json": RD16S_ROOT / "validation-report.json",
        "rd16s/output-hashes.json": RD16S_ROOT / "output-hashes.json",
        "rd16s/expanded-domain-summary.csv": RD16S_ROOT / "expanded-domain-summary.csv",
        "rd16r/eligible-universe.csv": RD16R_ROOT / "eligible-universe.csv",
        "rd16r/local-data-manifest-v1.json": RD16R_ROOT / "local-data-manifest-v1.json",
        "rd16m/rd16m-final-report-v1.json": RD16M_ROOT / "rd16m-final-report-v1.json",
        "rd16l/local-ledger-manifest-v1.json": RD16L_ROOT / "local-ledger-manifest-v1.json",
    }
    hashes: dict[str, str] = {}
    for name, path in tracked.items():
        if not path.is_file():
            raise RD16TEvaluationError(f"Frozen RD16-T input missing: {path}")
        hashes[name] = sha256_path(path)
    hashes.update(_verify_output_manifest(RD16S_ROOT, prefix="RD16S"))
    hashes.update(local_v3_hashes)
    hashes.update(local_market_hashes)
    return dict(sorted(hashes.items()))


def _router_hypothesis(hypothesis: LongHorizonHypothesis) -> SignalHypothesis:
    return SignalHypothesis(
        hypothesis_id=hypothesis.hypothesis_id,
        engine_id=hypothesis.engine_id,
        role=hypothesis.role,
        description=hypothesis.description,
        stop_atr_multiple=hypothesis.initial_stop_atr_multiple,
        cooldown_hours=hypothesis.cooldown_hours,
        engine_priority=hypothesis.engine_priority,
        fixed_conditions=hypothesis.fixed_conditions,
    )


def evaluate_long_horizon_candidate(
    candidate: Mapping[str, object],
    *,
    bars: pd.DataFrame,
    bar_positions: Mapping[pd.Timestamp, int],
) -> dict[str, object] | None:
    entry_bar_close = _timestamp(candidate["entry_bar_close"])
    entry_position = bar_positions.get(entry_bar_close)
    if entry_position is None:
        return None
    entry_price = _finite(candidate["entry_price"], name="entry_price")
    atr = _finite(candidate["atr14_at_signal"], name="atr14_at_signal")
    stop_multiple = _finite(candidate["stop_atr_multiple"], name="stop_multiple")
    trail_activation = _finite(candidate["trail_activation_r"], name="trail_activation")
    trail_multiple = _finite(candidate["trail_atr_multiple"], name="trail_multiple")
    maximum_holding_bars = int(
        _finite(candidate["maximum_holding_bars"], name="maximum_holding_bars")
    )
    risk_per_unit = atr * stop_multiple
    initial_stop = entry_price - risk_per_unit
    if entry_price <= 0.0 or atr <= 0.0 or initial_stop <= 0.0 or maximum_holding_bars <= 0:
        return None

    current_stop = initial_stop
    highest_high = entry_price
    trail_active = False
    exit_price = entry_price
    exit_bar_close = entry_bar_close
    exit_reason = "TIME_EXIT"
    bars_held = 0
    last_position = min(entry_position + maximum_holding_bars - 1, len(bars) - 1)

    for position in range(entry_position, last_position + 1):
        row = bars.iloc[position]
        bar_low = _finite(row["low"], name="bar_low")
        bar_high = _finite(row["high"], name="bar_high")
        bar_close = _finite(row["close"], name="bar_close")
        bar_timestamp = _timestamp(row["timestamp"])
        bars_held = position - entry_position + 1

        if bar_low <= current_stop:
            exit_price = current_stop
            exit_bar_close = bar_timestamp
            exit_reason = "TRAILING_STOP" if trail_active else "HARD_STOP"
            break

        highest_high = max(highest_high, bar_high)
        if highest_high >= entry_price + trail_activation * risk_per_unit:
            trail_active = True
            chandelier = highest_high - trail_multiple * atr
            current_stop = max(current_stop, entry_price, chandelier)

        if position == last_position:
            exit_price = bar_close
            exit_bar_close = bar_timestamp

    market_regime = str(candidate["market_regime"])
    risk_fraction = 0.0075 if market_regime == "STRONG_BULL" else 0.005
    risk_budget = INITIAL_EQUITY * risk_fraction
    quantity = risk_budget / risk_per_unit
    if quantity <= 0.0:
        return None
    entry_fee = quantity * entry_price * BASE_FEE_RATE
    exit_fee = quantity * exit_price * BASE_FEE_RATE
    gross_pnl = quantity * (exit_price - entry_price)
    fees = entry_fee + exit_fee
    net_pnl = gross_pnl - fees
    return {
        **dict(candidate),
        "initial_stop": initial_stop,
        "risk_per_unit": risk_per_unit,
        "risk_budget": risk_budget,
        "quantity": quantity,
        "notional": quantity * entry_price,
        "exit_bar_close": exit_bar_close,
        "exit_price": exit_price,
        "exit_reason": exit_reason,
        "bars_held": bars_held,
        "gross_pnl": gross_pnl,
        "fees": fees,
        "net_pnl": net_pnl,
        "return_on_initial_equity": net_pnl / INITIAL_EQUITY,
        "engine_agreement": False,
        "side": "LONG",
        "instrument_type": "SPOT",
        "trailing_stop_activated": trail_active,
    }


def evaluate_long_horizon_candidates(
    candidates: pd.DataFrame,
    *,
    hourly_frames: Mapping[str, pd.DataFrame],
    bar_positions: Mapping[str, Mapping[pd.Timestamp, int]],
) -> pd.DataFrame:
    evaluated_records: list[dict[str, object]] = []
    for candidate in _records(candidates):
        symbol = str(candidate["symbol"])
        evaluated = evaluate_long_horizon_candidate(
            candidate,
            bars=hourly_frames[symbol],
            bar_positions=bar_positions[symbol],
        )
        if evaluated is not None:
            evaluated_records.append(evaluated)
    if evaluated_records:
        return pd.DataFrame.from_records(evaluated_records)
    empty = candidates.iloc[0:0].copy()
    for column in (
        "initial_stop",
        "risk_per_unit",
        "risk_budget",
        "quantity",
        "notional",
        "exit_price",
        "bars_held",
        "gross_pnl",
        "fees",
        "net_pnl",
        "return_on_initial_equity",
    ):
        empty[column] = pd.Series(dtype="float64")
    for column in (
        "exit_bar_close",
        "exit_reason",
        "side",
        "instrument_type",
    ):
        empty[column] = pd.Series(dtype="object")
    empty["engine_agreement"] = pd.Series(dtype="bool")
    empty["trailing_stop_activated"] = pd.Series(dtype="bool")
    return empty


def _holding_diagnostics(frame: pd.DataFrame) -> dict[str, float]:
    if frame.empty:
        return {
            "median_bars_held": 0.0,
            "long_hold_share": 0.0,
            "trailing_exit_share": 0.0,
        }
    bars = pd.to_numeric(frame["bars_held"], errors="raise")
    reasons = frame["exit_reason"].astype(str)
    return {
        "median_bars_held": float(bars.median()),
        "long_hold_share": float((bars >= 120).mean()),
        "trailing_exit_share": float((reasons == "TRAILING_STOP").mean()),
    }


def classify_long_horizon(
    *,
    candidate_count: int,
    standalone: rd16n.PortfolioEvidence,
    overlay: rd16n.PortfolioEvidence,
    standalone_trades: pd.DataFrame,
    baseline: Mapping[str, float],
    noncore_metrics: Mapping[str, object],
) -> LongHorizonDecision:
    standalone_1x = standalone.metrics[1.0]
    standalone_2x = standalone.metrics[2.0]
    overlay_1x = overlay.metrics[1.0]
    overlay_2x = overlay.metrics[2.0]
    standalone_return = _finite(standalone_1x["net_return"], name="standalone_return")
    standalone_pf = _metric_profit_factor(standalone_1x)
    standalone_drawdown = _finite(standalone_1x["maximum_drawdown"], name="standalone_drawdown")
    overlay_return = _finite(overlay_1x["net_return"], name="overlay_return")
    overlay_pf = _metric_profit_factor(overlay_1x)
    overlay_drawdown = _finite(overlay_1x["maximum_drawdown"], name="overlay_drawdown")
    overlay_two_x_return = _finite(overlay_2x["net_return"], name="overlay_two_x_return")
    top_three = rd16q._optional_float(standalone.concentration.get("top_3_trade_profit_share"))
    diagnostics = _holding_diagnostics(standalone_trades)
    long_horizon_evidence = (
        diagnostics["median_bars_held"] >= 72.0 and diagnostics["long_hold_share"] >= 0.25
    )
    delta_return = overlay_return - baseline["net_return"]
    delta_capture = (
        overlay.mean_high_opportunity_capture - baseline["mean_high_opportunity_capture"]
    )
    noncore_count = int(_finite(noncore_metrics["trade_count"], name="noncore_count"))
    noncore_pnl = _finite(noncore_metrics["net_pnl"], name="noncore_pnl")
    noncore_pf_raw = noncore_metrics.get("profit_factor_gate")
    noncore_pf = _finite(noncore_pf_raw, name="noncore_pf")

    gates = {
        "candidate_count_between_12_and_400": 12 <= candidate_count <= 400,
        "standalone_trade_count_gte_12": (
            int(
                _finite(
                    standalone_1x["trade_count"],
                    name="standalone_trade_count",
                )
            )
            >= 12
        ),
        "standalone_net_return_positive": standalone_return > 0.0,
        "standalone_profit_factor_gte_1_25": standalone_pf >= 1.25,
        "standalone_drawdown_lte_25pct": standalone_drawdown <= 0.25,
        "standalone_two_x_positive": _finite(
            standalone_2x["net_return"], name="standalone_two_x_return"
        )
        > 0.0,
        "standalone_two_x_profit_factor_gte_1": (_metric_profit_factor(standalone_2x) >= 1.0),
        "standalone_two_x_capital_feasible": bool(standalone_2x["capital_feasible"]),
        "standalone_positive_active_year_fraction_gte_50pct": (
            standalone.positive_active_year_fraction >= 0.50
        ),
        "standalone_top_3_profit_share_lte_45pct": (top_three is not None and top_three <= 0.45),
        "long_horizon_evidence": long_horizon_evidence,
        "overlay_delta_net_return_vs_v3_gte_2pp": delta_return >= 0.02,
        "overlay_profit_factor_preserved": (overlay_pf >= baseline["profit_factor"] - 0.05),
        "overlay_drawdown_not_worse_by_more_than_3pp": (
            overlay_drawdown <= baseline["maximum_drawdown"] + 0.03
        ),
        "overlay_capital_feasible": bool(overlay_1x["capital_feasible"]),
        "overlay_two_x_capital_feasible": bool(overlay_2x["capital_feasible"]),
        "overlay_two_x_return_not_below_v3": (overlay_two_x_return >= baseline["two_x_net_return"]),
        "overlay_capture_not_worse_by_more_than_0_5pp": delta_capture >= -0.005,
    }
    robust = all(gates.values())
    promising = (
        candidate_count >= 8
        and standalone_return > 0.0
        and standalone_pf >= 1.10
        and long_horizon_evidence
        and bool(standalone_2x["capital_feasible"])
        and (delta_return > 0.0 or (noncore_count >= 4 and noncore_pnl > 0.0 and noncore_pf >= 1.0))
    )
    monthly = rd16q._optional_float(overlay_1x["monthly_geometric_return"])
    strategic = robust and monthly is not None and monthly >= STRATEGIC_MONTHLY_TARGET
    failed = [key for key, passed in gates.items() if not passed]
    if robust:
        decision = "RETAIN_LONG_HORIZON_HYPOTHESIS_FOR_ARCHITECTURE_ASSEMBLY"
        carry_forward = True
        rationale = "Passes all fixed long-horizon, cost, capital, and overlay gates."
    elif promising:
        decision = "PROMISING_LONG_HORIZON_HYPOTHESIS"
        carry_forward = False
        rationale = "Positive long-horizon evidence; failed gates: " + ", ".join(failed)
    else:
        decision = "REJECT_LONG_HORIZON_HYPOTHESIS"
        carry_forward = False
        rationale = "Insufficient long-horizon evidence; failed gates: " + ", ".join(failed)
    return LongHorizonDecision(
        decision=decision,
        carry_forward=carry_forward,
        rationale=rationale,
        strategic_objective_met=strategic,
        long_horizon_evidence=long_horizon_evidence,
        gates=gates,
    )


def _exit_rows(
    frame: pd.DataFrame,
    *,
    scope: str,
    variant_id: str,
) -> list[dict[str, object]]:
    if frame.empty:
        return []
    rows: list[dict[str, object]] = []
    for reason, group in frame.groupby("exit_reason", sort=True):
        pnl = pd.to_numeric(group["net_pnl"], errors="raise")
        bars = pd.to_numeric(group["bars_held"], errors="raise")
        rows.append(
            {
                "scope": scope,
                "variant_id": variant_id,
                "exit_reason": str(reason),
                "trade_count": len(group),
                "net_pnl": float(pnl.sum()),
                "return_on_initial_equity": float(pnl.sum()) / INITIAL_EQUITY,
                "win_rate": float((pnl > 0.0).mean()),
                "profit_factor": _profit_factor(pnl),
                "median_bars_held": float(bars.median()),
            }
        )
    return rows


def _validation_payload(
    *,
    summary_count: int,
    deterministic_replay_match: bool,
    causal_rows: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    causality_pass = all(
        int(cast(int, row[field])) == 0
        for row in causal_rows
        for field in (
            "next_bar_violations",
            "future_4h_context_violations",
            "future_1d_context_violations",
            "future_1w_context_violations",
            "sealed_cutoff_violations",
        )
    )
    return {
        "technical_status": "PASS",
        "hypothesis_count": len(HYPOTHESIS_REGISTRY),
        "summary_count": summary_count,
        "all_hypotheses_classified": summary_count == len(HYPOTHESIS_REGISTRY),
        "deterministic_replay_match": deterministic_replay_match,
        "causality_audit_pass": causality_pass,
        "sealed_cutoff": pd.Timestamp(SEALED_CUTOFF).isoformat(),
        "architecture_changed": True,
        "long_horizon_exit_policy_changed": True,
        "spot_only": True,
        "long_only": True,
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
        "derivatives_data_used": False,
        "dune_api_called": False,
        "optimization_performed": False,
        "winner_selected": False,
        "production_authorized": False,
    }


def _write_reports(
    *,
    final_report: Mapping[str, object],
    summary_rows: Sequence[Mapping[str, object]],
    all_overlay: Mapping[str, object],
) -> list[Path]:
    results_path = REPORTS_ROOT / "rd16t-long-horizon-results-v1.md"
    decisions_path = REPORTS_ROOT / "rd16t-long-horizon-decisions-v1.md"
    audit_path = REPORTS_ROOT / "rd16t-architecture-reset-causality-audit-v1.md"
    results_path.write_text(
        "\n".join(
            [
                "# RD16-T Long-Horizon Results",
                "",
                f"- Decision: `{final_report['decision']}`",
                f"- Hypotheses: {final_report['hypotheses_evaluated']}",
                f"- Retained: {final_report['retained_hypothesis_count']}",
                f"- Promising: {final_report['promising_hypothesis_count']}",
                f"- Combined new trades: {all_overlay['new_trade_count']}",
                f"- Combined return: {all_overlay['net_return']}",
                f"- Combined PF: {all_overlay['profit_factor']}",
                f"- Next: `{final_report['next_stage']}`",
                "",
            ]
        ),
        encoding="utf-8",
        newline="\n",
    )
    decision_lines = ["# RD16-T Long-Horizon Decisions", ""]
    for row in summary_rows:
        decision_lines.extend(
            [
                f"## {row['hypothesis_id']}",
                "",
                f"- Decision: `{row['decision']}`",
                f"- Median bars held: {row['standalone_median_bars_held']}",
                f"- Overlay delta vs V3: {row['overlay_delta_net_return_vs_v3']}",
                f"- Rationale: {row['rationale']}",
                "",
            ]
        )
    decisions_path.write_text("\n".join(decision_lines), encoding="utf-8", newline="\n")
    audit_path.write_text(
        "\n".join(
            [
                "# RD16-T Architecture Reset and Causality Audit",
                "",
                "- Uses the frozen RD16-R ten-asset Spot universe.",
                "- Signals are generated only from completed daily and weekly bars.",
                "- Entry is the next hourly bar open.",
                "- Stops use daily ATR fixed at signal time.",
                "- Exit policy uses a causal hourly chandelier trail and time cap.",
                "- Frozen V3 remains a benchmark and receives overlay priority.",
                "- 2025 and 2026 remain sealed.",
                "- No leverage, margin, derivatives, DCA, or optimization.",
                "",
            ]
        ),
        encoding="utf-8",
        newline="\n",
    )
    return [results_path, decisions_path, audit_path]


def run_rd16t_research() -> dict[str, object]:
    source_report = _verify_rd16s_ready()
    v3_ledgers, local_v3_hashes = rd16n._load_v3_ledgers()
    baseline_trades = v3_ledgers["trades"].copy()
    baseline = rd16q._baseline_values()
    (
        all_market,
        hourly_frames,
        daily_frames,
        local_market_hashes,
        asset_metadata,
    ) = rd16s._load_expanded_market_frames()
    frozen_hashes = _frozen_input_hashes(local_v3_hashes, local_market_hashes)

    base_features = {
        symbol: build_feature_frame(frames, symbol=symbol) for symbol, frames in all_market.items()
    }
    long_features = build_long_horizon_feature_frames(base_features, all_market)
    timeline = rd16n._timeline(hourly_frames)
    bar_positions = rd16n._bar_position_maps(hourly_frames)
    core_daily: dict[str, pd.DataFrame] = {
        symbol: daily_frames[symbol] for symbol in ELIGIBLE_SYMBOLS if symbol in CORE_SYMBOLS
    }
    benchmark = build_benchmark_daily(core_daily)

    if RD16T_LOCAL_ROOT.exists():
        shutil.rmtree(RD16T_LOCAL_ROOT)
    RD16T_LOCAL_ROOT.mkdir(parents=True, exist_ok=True)
    RD16T_ROOT.mkdir(parents=True, exist_ok=True)
    REPORTS_ROOT.mkdir(parents=True, exist_ok=True)

    summary_rows: list[dict[str, object]] = []
    decision_rows: list[dict[str, object]] = []
    cost_rows: list[dict[str, object]] = []
    coverage_rows: list[dict[str, object]] = []
    causal_rows: list[dict[str, object]] = []
    routing_rows: list[dict[str, object]] = []
    annual_rows: list[dict[str, object]] = []
    bull_rows: list[dict[str, object]] = []
    symbol_rows: list[dict[str, object]] = []
    exit_rows: list[dict[str, object]] = []
    retained: list[str] = []
    promising: list[str] = []
    rejected: list[str] = []
    strategic_count = 0
    deterministic_replay_match = True
    all_evaluated: list[pd.DataFrame] = []
    local_manifest: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "root_committed": False,
        "hypotheses": {},
        "combined": {},
    }
    hypothesis_manifest = cast(dict[str, object], local_manifest["hypotheses"])

    for hypothesis in HYPOTHESIS_REGISTRY:
        candidates = build_long_horizon_candidates(
            long_features,
            hypothesis=hypothesis,
            asset_metadata=asset_metadata,
        )
        replay = build_long_horizon_candidates(
            long_features,
            hypothesis=hypothesis,
            asset_metadata=asset_metadata,
        )
        if dataframe_content_hash(candidates) != dataframe_content_hash(replay):
            deterministic_replay_match = False
        evaluated = evaluate_long_horizon_candidates(
            candidates,
            hourly_frames=hourly_frames,
            bar_positions=bar_positions,
        )
        standalone_evaluated, standalone_trades = rd16n.route_standalone_candidates(
            evaluated,
            hypothesis=_router_hypothesis(hypothesis),
        )
        overlay_evaluated, overlay_new = rd16n.route_overlay_candidates(
            baseline_trades,
            evaluated,
            variant_id=hypothesis.hypothesis_id,
        )
        standalone_enriched = (
            enrich_trades(
                standalone_trades,
                hourly_frames=hourly_frames,
                feature_frames=base_features,
            )
            if not standalone_trades.empty
            else rd16n._empty_enriched_frame(standalone_trades)
        )
        overlay_new_enriched = (
            enrich_trades(
                overlay_new,
                hourly_frames=hourly_frames,
                feature_frames=base_features,
            )
            if not overlay_new.empty
            else rd16n._empty_enriched_frame(overlay_new)
        )
        overlay_combined = (
            pd.concat([baseline_trades, overlay_new_enriched], ignore_index=True, sort=False)
            .sort_values(
                by=["entry_open_time", "symbol", "signal_close", "trade_id"],
                kind="stable",
            )
            .reset_index(drop=True)
        )
        standalone_evidence = rd16n._evaluate_portfolio(
            standalone_enriched,
            variant_id=f"RD16T-STANDALONE::{hypothesis.hypothesis_id}",
            hourly_frames=hourly_frames,
            timeline=timeline,
            benchmark=benchmark,
        )
        overlay_evidence = rd16n._evaluate_portfolio(
            overlay_combined,
            variant_id=f"RD16T-OVERLAY::{hypothesis.hypothesis_id}",
            hourly_frames=hourly_frames,
            timeline=timeline,
            benchmark=benchmark,
        )
        noncore_overlay = overlay_new_enriched[
            overlay_new_enriched["symbol"].astype(str).isin(NONCORE_SYMBOLS)
        ]
        noncore_metrics = rd16s._trade_subset_metrics(noncore_overlay)
        decision = classify_long_horizon(
            candidate_count=len(candidates),
            standalone=standalone_evidence,
            overlay=overlay_evidence,
            standalone_trades=standalone_enriched,
            baseline=baseline,
            noncore_metrics=noncore_metrics,
        )
        if decision.carry_forward:
            retained.append(hypothesis.hypothesis_id)
        elif decision.decision == "PROMISING_LONG_HORIZON_HYPOTHESIS":
            promising.append(hypothesis.hypothesis_id)
        else:
            rejected.append(hypothesis.hypothesis_id)
        if decision.strategic_objective_met:
            strategic_count += 1

        standalone_1x = standalone_evidence.metrics[1.0]
        standalone_2x = standalone_evidence.metrics[2.0]
        overlay_1x = overlay_evidence.metrics[1.0]
        overlay_2x = overlay_evidence.metrics[2.0]
        diagnostics = _holding_diagnostics(standalone_enriched)
        top_three = rd16q._optional_float(
            standalone_evidence.concentration.get("top_3_trade_profit_share")
        )
        overlay_return = _finite(overlay_1x["net_return"], name="overlay_return")
        overlay_pf = _metric_profit_factor(overlay_1x)
        summary_row = {
            "hypothesis_id": hypothesis.hypothesis_id,
            "engine_id": hypothesis.engine_id,
            "role": hypothesis.role,
            "decision": decision.decision,
            "carry_forward": decision.carry_forward,
            "candidate_count": len(candidates),
            "candidate_assets": (
                int(candidates["symbol"].nunique()) if not candidates.empty else 0
            ),
            "standalone_trade_count": standalone_1x["trade_count"],
            "standalone_net_return": standalone_1x["net_return"],
            "standalone_monthly_geometric_return": (standalone_1x["monthly_geometric_return"]),
            "standalone_profit_factor": standalone_1x["profit_factor"],
            "standalone_maximum_drawdown": standalone_1x["maximum_drawdown"],
            "standalone_two_x_net_return": standalone_2x["net_return"],
            "standalone_two_x_profit_factor": standalone_2x["profit_factor"],
            "standalone_two_x_capital_feasible": standalone_2x["capital_feasible"],
            "standalone_positive_active_year_fraction": (
                standalone_evidence.positive_active_year_fraction
            ),
            "standalone_top_3_trade_profit_share": top_three,
            "standalone_median_bars_held": diagnostics["median_bars_held"],
            "standalone_long_hold_share": diagnostics["long_hold_share"],
            "standalone_trailing_exit_share": diagnostics["trailing_exit_share"],
            "overlay_new_trade_count": len(overlay_new_enriched),
            "overlay_net_return": overlay_1x["net_return"],
            "overlay_monthly_geometric_return": overlay_1x["monthly_geometric_return"],
            "overlay_profit_factor": overlay_1x["profit_factor"],
            "overlay_maximum_drawdown": overlay_1x["maximum_drawdown"],
            "overlay_capital_feasible": overlay_1x["capital_feasible"],
            "overlay_two_x_net_return": overlay_2x["net_return"],
            "overlay_two_x_profit_factor": overlay_2x["profit_factor"],
            "overlay_two_x_capital_feasible": overlay_2x["capital_feasible"],
            "overlay_mean_high_opportunity_capture": (
                overlay_evidence.mean_high_opportunity_capture
            ),
            "overlay_delta_net_return_vs_v3": overlay_return - baseline["net_return"],
            "overlay_delta_profit_factor_vs_v3": overlay_pf - baseline["profit_factor"],
            "overlay_delta_drawdown_vs_v3": (
                _finite(overlay_1x["maximum_drawdown"], name="overlay_dd")
                - baseline["maximum_drawdown"]
            ),
            "overlay_delta_two_x_return_vs_v3": (
                _finite(overlay_2x["net_return"], name="overlay_2x_return")
                - baseline["two_x_net_return"]
            ),
            "overlay_delta_capture_vs_v3": (
                overlay_evidence.mean_high_opportunity_capture
                - baseline["mean_high_opportunity_capture"]
            ),
            "noncore_overlay_trade_count": noncore_metrics["trade_count"],
            "noncore_overlay_net_pnl": noncore_metrics["net_pnl"],
            "noncore_overlay_profit_factor": noncore_metrics["profit_factor"],
            "long_horizon_evidence": decision.long_horizon_evidence,
            "strategic_objective_met": decision.strategic_objective_met,
            "rationale": decision.rationale,
        }
        summary_rows.append(summary_row)
        decision_rows.append({field: summary_row[field] for field in DECISION_FIELDS})
        cost_rows.extend(
            rd16q._cost_rows(
                standalone_evidence,
                scope="STANDALONE",
                variant_id=hypothesis.hypothesis_id,
            )
        )
        cost_rows.extend(
            rd16q._cost_rows(
                overlay_evidence,
                scope="OVERLAY",
                variant_id=hypothesis.hypothesis_id,
            )
        )
        coverage_rows.extend(
            rd16q._coverage_rows(
                domain_id=hypothesis.hypothesis_id,
                candidates=candidates,
                evaluated=evaluated,
                standalone=standalone_enriched,
                overlay_new=overlay_new_enriched,
            )
        )
        causal_rows.extend(rd16q._causality_rows(candidates, domain_id=hypothesis.hypothesis_id))
        routing_rows.extend(
            rd16q._routing_rows(
                standalone_evaluated,
                scope="STANDALONE",
                variant_id=hypothesis.hypothesis_id,
            )
        )
        routing_rows.extend(
            rd16q._routing_rows(
                overlay_evaluated,
                scope="OVERLAY",
                variant_id=hypothesis.hypothesis_id,
            )
        )
        annual_rows.extend(
            rd16q._annual_rows(
                standalone_evidence,
                scope="STANDALONE",
                variant_id=hypothesis.hypothesis_id,
            )
        )
        annual_rows.extend(
            rd16q._annual_rows(
                overlay_evidence,
                scope="OVERLAY",
                variant_id=hypothesis.hypothesis_id,
            )
        )
        bull_rows.extend(
            rd16q._bull_rows(
                standalone_evidence,
                scope="STANDALONE",
                variant_id=hypothesis.hypothesis_id,
            )
        )
        bull_rows.extend(
            rd16q._bull_rows(
                overlay_evidence,
                scope="OVERLAY",
                variant_id=hypothesis.hypothesis_id,
            )
        )
        symbol_rows.extend(
            rd16s._symbol_rows(
                standalone_enriched,
                scope="STANDALONE",
                domain_id=hypothesis.hypothesis_id,
            )
        )
        symbol_rows.extend(
            rd16s._symbol_rows(
                overlay_new_enriched,
                scope="OVERLAY_NEW",
                domain_id=hypothesis.hypothesis_id,
            )
        )
        exit_rows.extend(
            _exit_rows(
                standalone_enriched,
                scope="STANDALONE",
                variant_id=hypothesis.hypothesis_id,
            )
        )
        exit_rows.extend(
            _exit_rows(
                overlay_new_enriched,
                scope="OVERLAY_NEW",
                variant_id=hypothesis.hypothesis_id,
            )
        )
        local_root = RD16T_LOCAL_ROOT / hypothesis.hypothesis_id
        hypothesis_manifest[hypothesis.hypothesis_id] = {
            "candidates": rd16s._write_local_frame(local_root / "candidates.parquet", candidates),
            "evaluated": rd16s._write_local_frame(local_root / "evaluated.parquet", evaluated),
            "standalone_evaluated": rd16s._write_local_frame(
                local_root / "standalone-evaluated.parquet", standalone_evaluated
            ),
            "standalone_trades": rd16s._write_local_frame(
                local_root / "standalone-trades.parquet", standalone_enriched
            ),
            "overlay_evaluated": rd16s._write_local_frame(
                local_root / "overlay-evaluated.parquet", overlay_evaluated
            ),
            "overlay_new_trades": rd16s._write_local_frame(
                local_root / "overlay-new-trades.parquet", overlay_new_enriched
            ),
            "overlay_combined_trades": rd16s._write_local_frame(
                local_root / "overlay-combined-trades.parquet", overlay_combined
            ),
        }
        all_evaluated.append(evaluated)

    combined_evaluated = (
        pd.concat(all_evaluated, ignore_index=True, sort=False)
        .sort_values(
            by=["entry_open_time", "engine_priority", "symbol", "signal_close"],
            kind="stable",
        )
        .reset_index(drop=True)
        if all_evaluated
        else pd.DataFrame()
    )
    combined_routing, combined_new = rd16n.route_overlay_candidates(
        baseline_trades,
        combined_evaluated,
        variant_id=ALL_OVERLAY_ID,
    )
    combined_new_enriched = (
        enrich_trades(
            combined_new,
            hourly_frames=hourly_frames,
            feature_frames=base_features,
        )
        if not combined_new.empty
        else rd16n._empty_enriched_frame(combined_new)
    )
    combined_trades = (
        pd.concat([baseline_trades, combined_new_enriched], ignore_index=True, sort=False)
        .sort_values(
            by=["entry_open_time", "symbol", "signal_close", "trade_id"],
            kind="stable",
        )
        .reset_index(drop=True)
    )
    combined_evidence = rd16n._evaluate_portfolio(
        combined_trades,
        variant_id=ALL_OVERLAY_ID,
        hourly_frames=hourly_frames,
        timeline=timeline,
        benchmark=benchmark,
    )
    combined_1x = combined_evidence.metrics[1.0]
    combined_2x = combined_evidence.metrics[2.0]
    combined_noncore = combined_new_enriched[
        combined_new_enriched["symbol"].astype(str).isin(NONCORE_SYMBOLS)
    ]
    combined_noncore_metrics = rd16s._trade_subset_metrics(combined_noncore)
    all_overlay = {
        "variant_id": ALL_OVERLAY_ID,
        "new_trade_count": len(combined_new_enriched),
        "trade_count": combined_1x["trade_count"],
        "net_return": combined_1x["net_return"],
        "monthly_geometric_return": combined_1x["monthly_geometric_return"],
        "profit_factor": combined_1x["profit_factor"],
        "maximum_drawdown": combined_1x["maximum_drawdown"],
        "minimum_cash": combined_1x["minimum_cash"],
        "capital_feasible": combined_1x["capital_feasible"],
        "two_x_net_return": combined_2x["net_return"],
        "two_x_profit_factor": combined_2x["profit_factor"],
        "two_x_minimum_cash": combined_2x["minimum_cash"],
        "two_x_capital_feasible": combined_2x["capital_feasible"],
        "mean_high_opportunity_capture": combined_evidence.mean_high_opportunity_capture,
        "delta_net_return_vs_v3": (
            _finite(combined_1x["net_return"], name="combined_return") - baseline["net_return"]
        ),
        "delta_profit_factor_vs_v3": (
            _metric_profit_factor(combined_1x) - baseline["profit_factor"]
        ),
        "delta_capture_vs_v3": (
            combined_evidence.mean_high_opportunity_capture
            - baseline["mean_high_opportunity_capture"]
        ),
        "noncore_new_trade_count": combined_noncore_metrics["trade_count"],
        "noncore_net_pnl": combined_noncore_metrics["net_pnl"],
        "noncore_profit_factor": combined_noncore_metrics["profit_factor"],
    }
    cost_rows.extend(
        rd16q._cost_rows(combined_evidence, scope="OVERLAY", variant_id=ALL_OVERLAY_ID)
    )
    routing_rows.extend(
        rd16q._routing_rows(combined_routing, scope="OVERLAY", variant_id=ALL_OVERLAY_ID)
    )
    annual_rows.extend(
        rd16q._annual_rows(combined_evidence, scope="OVERLAY", variant_id=ALL_OVERLAY_ID)
    )
    bull_rows.extend(
        rd16q._bull_rows(combined_evidence, scope="OVERLAY", variant_id=ALL_OVERLAY_ID)
    )
    symbol_rows.extend(
        rd16s._symbol_rows(
            combined_new_enriched,
            scope="OVERLAY_NEW",
            domain_id=ALL_OVERLAY_ID,
        )
    )
    exit_rows.extend(
        _exit_rows(combined_new_enriched, scope="OVERLAY_NEW", variant_id=ALL_OVERLAY_ID)
    )
    combined_manifest = cast(dict[str, object], local_manifest["combined"])
    combined_manifest.update(
        {
            "evaluated": rd16s._write_local_frame(
                RD16T_LOCAL_ROOT / "combined" / "evaluated.parquet",
                combined_evaluated,
            ),
            "overlay_evaluated": rd16s._write_local_frame(
                RD16T_LOCAL_ROOT / "combined" / "overlay-evaluated.parquet",
                combined_routing,
            ),
            "overlay_new_trades": rd16s._write_local_frame(
                RD16T_LOCAL_ROOT / "combined" / "overlay-new-trades.parquet",
                combined_new_enriched,
            ),
            "overlay_combined_trades": rd16s._write_local_frame(
                RD16T_LOCAL_ROOT / "combined" / "overlay-combined-trades.parquet",
                combined_trades,
            ),
        }
    )

    if retained:
        next_stage = NEXT_ASSEMBLY
    elif promising:
        next_stage = NEXT_REFINEMENT
    else:
        next_stage = NEXT_RESET
    final_report: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "decision": DECISION,
        "technical_status": "COMPLETED",
        "evidence_classification": EVIDENCE_CLASSIFICATION,
        "branch": BRANCH,
        "architecture_id": ARCHITECTURE_ID,
        "source_architecture_id": "COMPOSITE_ALPHA_V3",
        "source_stage_decision": source_report["decision"],
        "eligible_asset_count": len(ELIGIBLE_SYMBOLS),
        "hypotheses_evaluated": len(HYPOTHESIS_REGISTRY),
        "retained_hypothesis_count": len(retained),
        "retained_hypotheses": retained,
        "promising_hypothesis_count": len(promising),
        "promising_hypotheses": promising,
        "rejected_hypothesis_count": len(rejected),
        "rejected_hypotheses": rejected,
        "strategic_objective_met_count": strategic_count,
        "strategic_objective_met": strategic_count > 0,
        "pre_registered_combined_overlay": all_overlay,
        "next_stage": next_stage,
        "architecture_changed": True,
        "technical_gates": {
            "all_input_hashes_verified": True,
            "rd16s_ready": True,
            "rd16s_outputs_verified": True,
            "rd16r_local_data_verified": True,
            "rd16l_local_ledgers_verified": True,
            "deterministic_replay_match": deterministic_replay_match,
            "all_causality_checks_pass": all(
                int(cast(int, row[field])) == 0
                for row in causal_rows
                for field in (
                    "next_bar_violations",
                    "future_4h_context_violations",
                    "future_1d_context_violations",
                    "future_1w_context_violations",
                    "sealed_cutoff_violations",
                )
            ),
            "frozen_v3_trades_preserved": True,
            "same_symbol_overlap_prohibited": True,
            "maximum_positions_preserved": True,
            "maximum_open_risk_preserved": True,
            "spot_only": True,
            "long_only": True,
            "network_accessed": False,
            "derivatives_data_used": False,
            "test_2025_accessed": False,
            "holdout_2026_accessed": False,
            "dune_api_called": False,
            "optimization_performed": False,
            "winner_selected": False,
            "production_authorized": False,
            "architecture_changed": True,
        },
        "optimization_performed": False,
        "winner_selected": False,
        "production_authorized": False,
    }

    paths = {
        "registry": RD16T_ROOT / "long-horizon-registry.csv",
        "summary": RD16T_ROOT / "long-horizon-summary.csv",
        "decisions": RD16T_ROOT / "component-decisions.csv",
        "cost": RD16T_ROOT / "cost-stress.csv",
        "coverage": RD16T_ROOT / "signal-coverage.csv",
        "causal": RD16T_ROOT / "causality-audit.csv",
        "routing": RD16T_ROOT / "routing-summary.csv",
        "annual": RD16T_ROOT / "annual-performance.csv",
        "bull": RD16T_ROOT / "bull-window-capture.csv",
        "symbol": RD16T_ROOT / "symbol-performance.csv",
        "exit": RD16T_ROOT / "exit-policy-summary.csv",
        "all_overlay": RD16T_ROOT / "all-hypothesis-overlay-summary.csv",
        "frozen": RD16T_ROOT / "frozen-input-hashes.json",
        "manifest": RD16T_ROOT / "local-output-manifest-v1.json",
        "validation": RD16T_ROOT / "validation-report.json",
        "final": RD16T_ROOT / "rd16t-final-report-v1.json",
        "output_hashes": RD16T_ROOT / "output-hashes.json",
    }
    write_csv(paths["registry"], hypothesis_registry_rows(), fieldnames=REGISTRY_FIELDS)
    write_csv(paths["summary"], summary_rows, fieldnames=SUMMARY_FIELDS)
    write_csv(paths["decisions"], decision_rows, fieldnames=DECISION_FIELDS)
    write_csv(paths["cost"], cost_rows, fieldnames=rd16q.COST_FIELDS)
    write_csv(paths["coverage"], coverage_rows, fieldnames=rd16q.COVERAGE_FIELDS)
    write_csv(paths["causal"], causal_rows, fieldnames=rd16q.CAUSAL_FIELDS)
    write_csv(paths["routing"], routing_rows, fieldnames=rd16q.ROUTING_FIELDS)
    write_csv(paths["annual"], annual_rows, fieldnames=rd16q.ANNUAL_FIELDS)
    write_csv(paths["bull"], bull_rows, fieldnames=rd16q.BULL_FIELDS)
    write_csv(paths["symbol"], symbol_rows, fieldnames=rd16s.SYMBOL_FIELDS)
    write_csv(paths["exit"], exit_rows, fieldnames=EXIT_FIELDS)
    write_csv(paths["all_overlay"], [all_overlay], fieldnames=ALL_OVERLAY_FIELDS)
    write_json(paths["frozen"], frozen_hashes)
    write_json(paths["manifest"], local_manifest)
    validation = _validation_payload(
        summary_count=len(summary_rows),
        deterministic_replay_match=deterministic_replay_match,
        causal_rows=causal_rows,
    )
    write_json(paths["validation"], validation)
    write_json(paths["final"], final_report)
    report_paths = _write_reports(
        final_report=final_report,
        summary_rows=summary_rows,
        all_overlay=all_overlay,
    )
    output_paths = [path for name, path in paths.items() if name != "output_hashes"] + report_paths
    write_json(paths["output_hashes"], rd16q._output_hashes(output_paths))

    if _frozen_input_hashes(local_v3_hashes, local_market_hashes) != frozen_hashes:
        raise RD16TEvaluationError("Frozen RD16-T inputs changed during evaluation.")
    if not deterministic_replay_match:
        raise RD16TEvaluationError("RD16-T deterministic replay mismatch.")
    if validation["causality_audit_pass"] is not True:
        raise RD16TEvaluationError("RD16-T causality audit failed.")
    return final_report


__all__ = [
    "ALL_OVERLAY_ID",
    "DECISION",
    "EVIDENCE_CLASSIFICATION",
    "LongHorizonDecision",
    "RD16TEvaluationError",
    "SCHEMA_VERSION",
    "_exit_rows",
    "_holding_diagnostics",
    "_validation_payload",
    "classify_long_horizon",
    "evaluate_long_horizon_candidate",
    "evaluate_long_horizon_candidates",
    "run_rd16t_research",
]
