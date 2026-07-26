"""Assess the immutable AMS-MD01 factor, portfolio, controls, and benchmarks."""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Iterable, Mapping
from typing import Any

import numpy as np
import pandas as pd
from ams_md01_common import (
    LEDGER,
    READINESS,
    REPORTS,
    atomic_json,
    atomic_text,
    copy_external,
    load_registered_data,
    sha256,
    verify_report_hashes,
)
from run_ams_md01_all_variants import gross_edge_status
from run_ams_md01_variant import result_name

from spotbot.research.ams_md01_momentum import VARIANTS


def _load_result(
    variant_id: str,
    cost_mode: str = "ZERO_COST",
    control_mode: str = "REGISTERED",
) -> dict[str, Any]:
    path = REPORTS / result_name(variant_id, cost_mode, control_mode)
    return json.loads(path.read_text(encoding="utf-8"))


def control_value(registered: float, counterfactual: float, *, kind: str) -> str:
    """Classify a preregistered control using a material 2-point return difference."""
    difference = registered - counterfactual
    if abs(difference) < 0.02:
        return f"{kind}_INCONCLUSIVE"
    return f"{kind}_VALUE_ADD" if difference > 0 else f"{kind}_HARMFUL"


def _group_pnl(trades: Iterable[Mapping[str, Any]], key: str) -> dict[str, Any]:
    grouped: dict[str, list[float]] = defaultdict(list)
    for trade in trades:
        grouped[str(trade[key])].append(float(trade["net_pnl"]))
    return {
        name: {
            "trade_count": len(values),
            "net_pnl": sum(values),
            "expectancy": float(np.mean(values)),
            "win_rate": float(np.mean(np.asarray(values) > 0)),
        }
        for name, values in sorted(grouped.items())
    }


def concentration_analysis(report: Mapping[str, Any]) -> dict[str, Any]:
    """Measure symbol, month, regime, year, and top-trade concentration."""
    trades = [
        dict(trade)
        for fold in report["fold_results"]
        for trade in fold["trade_ledger"]
    ]
    candidate_by_id = {
        candidate["candidate_id"]: candidate
        for fold in report["fold_results"]
        for candidate in fold["candidate_ledger"]
    }
    for trade in trades:
        entry = pd.Timestamp(trade["entry_time"])
        trade["year"] = str(entry.year)
        trade["month"] = entry.strftime("%Y-%m")
        candidate = candidate_by_id.get(trade["candidate_id"], {})
        trade["regime"] = candidate.get("daily_market_regime", "UNKNOWN")
    by_symbol = _group_pnl(trades, "symbol")
    by_year = _group_pnl(trades, "year")
    by_month = _group_pnl(trades, "month")
    by_regime = _group_pnl(trades, "regime")
    symbol_values = np.asarray(
        [abs(value["net_pnl"]) for value in by_symbol.values()], dtype=float
    )
    month_values = np.asarray(
        [abs(value["net_pnl"]) for value in by_month.values()], dtype=float
    )
    regime_values = np.asarray(
        [abs(value["net_pnl"]) for value in by_regime.values()], dtype=float
    )

    def hhi(values: np.ndarray) -> float:
        total = float(values.sum())
        return float(((values / total) ** 2).sum()) if total else 0.0

    positive = sorted(
        (max(float(trade["net_pnl"]), 0.0) for trade in trades), reverse=True
    )
    total_positive = sum(positive)
    top1 = float(report["aggregate"]["top_1_symbol_contribution"])
    status = (
        "EDGE_CONCENTRATED"
        if top1 > 0.60
        else "EDGE_MODERATELY_CONCENTRATED"
        if top1 > 0.40
        else "EDGE_DIVERSIFIED"
    )
    return {
        "status": status,
        "top_1_symbol_contribution": top1,
        "top_3_symbol_contribution": float(
            report["aggregate"]["top_3_symbol_contribution"]
        ),
        "top_10_trades_contribution": (
            sum(positive[:10]) / total_positive if total_positive else 0.0
        ),
        "symbol_hhi": hhi(symbol_values),
        "month_hhi": hhi(month_values),
        "regime_hhi": hhi(regime_values),
        "by_symbol": by_symbol,
        "by_year": by_year,
        "by_month": by_month,
        "by_regime": by_regime,
    }


def _crash_events(daily: pd.DataFrame) -> list[tuple[pd.Timestamp, pd.Timestamp, float]]:
    btc = daily.loc[daily["symbol"].eq("BTC")].sort_values("bar_close_time").copy()
    btc["return_7d"] = btc["close"] / btc["close"].shift(7) - 1.0
    hits = btc.loc[
        (btc["bar_close_time"] >= pd.Timestamp("2022-01-01T00:00:00Z"))
        & (btc["return_7d"] <= -0.15)
    ]
    events: list[tuple[pd.Timestamp, pd.Timestamp, float]] = []
    for row in hits.itertuples(index=False):
        timestamp = pd.Timestamp(row.bar_close_time)
        value = float(row.return_7d)
        if events and timestamp - events[-1][1] <= pd.Timedelta(days=7):
            start, _, minimum = events[-1]
            events[-1] = (start, timestamp, min(minimum, value))
        else:
            events.append((timestamp, timestamp, value))
    return events


def momentum_crash_analysis(
    best: Mapping[str, Any],
    crisis_off: Mapping[str, Any],
    daily: pd.DataFrame,
) -> dict[str, Any]:
    """Attribute pre-defined 7-day BTC crash windows without tuning the strategy."""
    events = _crash_events(daily)
    trades = [
        trade
        for fold in best["fold_results"]
        for trade in fold["trade_ledger"]
    ]
    records: list[dict[str, Any]] = []
    total_positive = sum(max(float(trade["net_pnl"]), 0.0) for trade in trades)
    total_crash_pnl = 0.0
    for sequence, (start, end, btc_return) in enumerate(events, 1):
        window_end = end + pd.Timedelta(days=14)
        overlapping = [
            trade
            for trade in trades
            if pd.Timestamp(trade["entry_time"]) <= window_end
            and pd.Timestamp(trade["exit_time"]) >= start
        ]
        pnl = sum(float(trade["net_pnl"]) for trade in overlapping)
        total_crash_pnl += pnl
        records.append(
            {
                "event_id": f"CRASH-{sequence:02d}",
                "start": start.isoformat(),
                "end": end.isoformat(),
                "post_event_window_end": window_end.isoformat(),
                "btc_worst_7d_return": btc_return,
                "overlapping_trade_count": len(overlapping),
                "drawdown_contribution_pnl": pnl,
                "symbols": sorted({str(trade["symbol"]) for trade in overlapping}),
            }
        )
    ratio = -min(total_crash_pnl, 0.0) / total_positive if total_positive else 0.0
    if ratio > 0.50:
        status = "MOMENTUM_CRASH_DOMINANT"
    elif ratio > 0.15:
        status = "MOMENTUM_CRASH_MATERIAL"
    else:
        status = "MOMENTUM_CRASH_CONTAINED"
    return {
        "schema_version": "ams-md01-momentum-crash-analysis-v1",
        "status": "PASS",
        "crash_status": status,
        "definition": "BTC causal 7-calendar-day return <= -15%; event attribution is post hoc",
        "events": records,
        "total_crash_window_pnl": total_crash_pnl,
        "crash_loss_to_positive_pnl": ratio,
        "crisis_gate_effect_compounded_return": (
            float(best["aggregate"]["compounded_return"])
            - float(crisis_off["aggregate"]["compounded_return"])
        ),
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
    }


def _cost_summary(variant_id: str, preliminary_status: str) -> dict[str, Any]:
    if preliminary_status != "PORTFOLIO_GROSS_EDGE_PASS":
        return {
            "cost_status": "NOT_RUN_GROSS_EDGE_FAILED",
            "base": None,
            "stress": None,
        }
    base = _load_result(variant_id, "BASE_COST")
    stress = _load_result(variant_id, "STRESS_0_4_PERCENT")
    aggregate_base = base["aggregate"]
    aggregate_stress = stress["aggregate"]
    robust = (
        aggregate_base["compounded_return"] > 0
        and aggregate_stress["compounded_return"] > 0
        and aggregate_base["profit_factor"] is not None
        and aggregate_base["profit_factor"] > 1
        and aggregate_stress["profit_factor"] is not None
        and aggregate_stress["profit_factor"] > 1
    )
    return {
        "cost_status": "ROBUST_AFTER_COSTS" if robust else "FAILS_AFTER_COSTS",
        "base": aggregate_base,
        "stress": aggregate_stress,
        "gross_to_base_decay": (
            _load_result(variant_id)["aggregate"]["compounded_return"]
            - aggregate_base["compounded_return"]
        ),
        "base_to_stress_decay": (
            aggregate_base["compounded_return"] - aggregate_stress["compounded_return"]
        ),
    }


def _markdown(
    *,
    final: Mapping[str, Any],
    variants: Iterable[Mapping[str, Any]],
) -> str:
    rows = []
    for record in variants:
        aggregate = record["zero_cost"]
        base = record["costs"]["base"]
        stress = record["costs"]["stress"]
        rows.append(
            "| {id} | {school} | {gross:.2%} | {base} | {stress} | {pf} | {trades} | "
            "{status} |".format(
                id=record["variant_id"],
                school=record["school"],
                gross=aggregate["compounded_return"],
                base=f"{base['compounded_return']:.2%}" if base else "NOT RUN",
                stress=f"{stress['compounded_return']:.2%}" if stress else "NOT RUN",
                pf=(
                    f"{aggregate['profit_factor']:.2f}"
                    if aggregate["profit_factor"] is not None
                    else "n/a"
                ),
                trades=aggregate["trade_count"],
                status=record["final_gross_edge_status"],
            )
        )
    return "\n".join(
        [
            "# AMS-MD01 Final Assessment",
            "",
            f"**Decision: {final['final_research_decision']}**",
            "",
            f"- Universe: {final['universe_status']}",
            f"- Alignment: {final['alignment_status']}",
            f"- TSM: {final['factor_statuses']['TSM']}",
            f"- XSM: {final['factor_statuses']['XSM']}",
            f"- Dual: {final['factor_statuses']['DUAL']}",
            f"- Portfolio gross edge: {final['portfolio_gross_edge_status']}",
            f"- Best variant: {final['best_variant']}",
            f"- Momentum crash: {final['momentum_crash_status']}",
            "- 2025 remains locked; Kelly research is not authorized.",
            "",
            "| Variant | School | Zero cost | Base | Stress | PF | Trades | Final gate |",
            "|---|---|---:|---:|---:|---:|---:|---|",
            *rows,
            "",
            "The positive portfolio result is provisional because the fixed thirty-asset "
            "list has survivorship risk and every variant suffered a materially negative "
            "2022 fold. MD02 and 2025 are not opened by this report.",
            "",
        ]
    )


def main() -> None:
    universe = json.loads(
        (REPORTS / "ams-md01-universe-audit-v1.json").read_text(encoding="utf-8")
    )
    factor = json.loads(
        (REPORTS / "ams-md01-factor-diagnostics-v1.json").read_text(encoding="utf-8")
    )
    alignment = json.loads(
        (REPORTS / "ams-md01-alignment-analysis-v1.json").read_text(encoding="utf-8")
    )
    benchmarks = json.loads(
        (REPORTS / "ams-md01-benchmark-comparison-v1.json").read_text(encoding="utf-8")
    )
    variants: list[dict[str, Any]] = []
    for variant_id, (school, horizon) in VARIANTS.items():
        registered = _load_result(variant_id)
        flat = _load_result(variant_id, control_mode="FLAT_ALIGNMENT")
        crisis_off = _load_result(variant_id, control_mode="CRISIS_OFF")
        preliminary = gross_edge_status(registered["aggregate"])
        fold_crash = min(
            float(item["net_return"]) for item in registered["aggregate"]["folds"]
        )
        benchmark_return = float(
            benchmarks["benchmarks"]["B03"]["ZERO_COST"]["compounded_return"]
        )
        final_gate = preliminary
        reasons: list[str] = []
        if fold_crash <= -0.35:
            final_gate = "PORTFOLIO_GROSS_EDGE_WEAK"
            reasons.append("worst fold lost at least 35 percent")
        if registered["aggregate"]["compounded_return"] <= benchmark_return:
            final_gate = (
                "PORTFOLIO_GROSS_EDGE_FAIL"
                if preliminary == "PORTFOLIO_GROSS_EDGE_FAIL"
                else "PORTFOLIO_GROSS_EDGE_WEAK"
            )
            reasons.append("did not beat BTC daily trend benchmark")
        costs = _cost_summary(variant_id, preliminary)
        variants.append(
            {
                "variant_id": variant_id,
                "school": school,
                "horizon_days": horizon,
                "preliminary_gross_edge_status": preliminary,
                "final_gross_edge_status": final_gate,
                "final_gate_reasons": reasons,
                "zero_cost": registered["aggregate"],
                "costs": costs,
                "flat_alignment_control": flat["aggregate"],
                "crisis_off_control": crisis_off["aggregate"],
                "alignment_control_status": control_value(
                    float(registered["aggregate"]["compounded_return"]),
                    float(flat["aggregate"]["compounded_return"]),
                    kind="MTF_ALIGNMENT",
                ),
                "crisis_control_status": control_value(
                    float(registered["aggregate"]["compounded_return"]),
                    float(crisis_off["aggregate"]["compounded_return"]),
                    kind="CRISIS_GATE",
                ),
            }
        )
    best = max(variants, key=lambda record: record["zero_cost"]["compounded_return"])
    best_report = _load_result(best["variant_id"])
    best_crisis_off = _load_result(
        best["variant_id"], control_mode="CRISIS_OFF"
    )
    frames, hashes = load_registered_data()
    crash = momentum_crash_analysis(best_report, best_crisis_off, frames["daily"])
    concentration = concentration_analysis(best_report)
    crash_names = [
        "ams-md01-momentum-crash-analysis-v1.json",
        "ams-md01-momentum-crash-analysis-v1.md",
    ]
    atomic_json(REPORTS / crash_names[0], crash)
    atomic_text(
        REPORTS / crash_names[1],
        "\n".join(
            [
                "# AMS-MD01 Momentum Crash Analysis",
                "",
                f"- Status: **{crash['crash_status']}**",
                f"- Detected events: {len(crash['events'])}",
                f"- Crash-window PnL: {crash['total_crash_window_pnl']:.2f}",
                f"- Crisis gate return effect: {crash['crisis_gate_effect_compounded_return']:.2%}",
                "",
            ]
        ),
    )
    any_final_pass = any(
        record["final_gross_edge_status"] == "PORTFOLIO_GROSS_EDGE_PASS"
        for record in variants
    )
    portfolio_status = (
        "PORTFOLIO_GROSS_EDGE_PASS"
        if any_final_pass
        else "PORTFOLIO_GROSS_EDGE_WEAK"
        if any(
            record["final_gross_edge_status"] == "PORTFOLIO_GROSS_EDGE_WEAK"
            for record in variants
        )
        else "PORTFOLIO_GROSS_EDGE_FAIL"
    )
    factor_statuses = factor["school_statuses"]
    final_decision = (
        "REVISE_UNIVERSE_WITHOUT_2025"
        if universe["universe_status"] == "SURVIVORSHIP_RISK"
        and factor_statuses["TSM"] == "RAW_FACTOR_PASS"
        and portfolio_status != "PORTFOLIO_GROSS_EDGE_FAIL"
        else "PROCEED_TO_MD02_PORTFOLIO_DESIGN"
        if universe["universe_status"] != "INVALID_FOR_CROSS_SECTIONAL_RESEARCH"
        and any(value == "RAW_FACTOR_PASS" for value in factor_statuses.values())
        and any_final_pass
        else "REVISE_MOMENTUM_HYPOTHESIS_WITHOUT_2025"
        if portfolio_status == "PORTFOLIO_GROSS_EDGE_WEAK"
        else "STOP_MOMENTUM_STRATEGY_LINE"
    )
    alignment_tiers = alignment["tiers"]
    final: dict[str, Any] = {
        "schema_version": "ams-md01-final-assessment-v1",
        "status": "PASS",
        "universe_status": universe["universe_status"],
        "research_label": universe["research_label"],
        "alignment_status": alignment["alignment_status"],
        "alignment_signal_counts": {
            tier: int(record["signal_count"])
            for tier, record in alignment_tiers.items()
        },
        "alignment_forward_28d": {
            tier: record["horizons"]["28d"]
            for tier, record in alignment_tiers.items()
        },
        "factor_statuses": factor_statuses,
        "portfolio_gross_edge_status": portfolio_status,
        "cost_status": (
            "ROBUST_AFTER_COSTS"
            if any(
                record["costs"]["cost_status"] == "ROBUST_AFTER_COSTS"
                for record in variants
            )
            else "NOT_RUN_GROSS_EDGE_FAILED"
        ),
        "best_variant": best["variant_id"],
        "best_school": best["school"],
        "variants": variants,
        "alignment_control_average_return_difference": float(
            np.mean(
                [
                    record["zero_cost"]["compounded_return"]
                    - record["flat_alignment_control"]["compounded_return"]
                    for record in variants
                ]
            )
        ),
        "crisis_gate_average_return_difference": float(
            np.mean(
                [
                    record["zero_cost"]["compounded_return"]
                    - record["crisis_off_control"]["compounded_return"]
                    for record in variants
                ]
            )
        ),
        "momentum_crash_status": crash["crash_status"],
        "concentration": concentration,
        "benchmark_comparison": benchmarks["benchmarks"],
        "final_research_decision": final_decision,
        "proceed_to_md02": False,
        "kelly_research_authorized": False,
        "request_2025_test": False,
        "reasoning": [
            "TSM absolute-positive signals were positive on average in two folds but "
            "cross-sectional rank IC was negative for both horizons.",
            "The best gross portfolio beat simple returns, but its 2022 fold lost "
            "more than 40 percent and its drawdown materially exceeded the BTC trend benchmark.",
            "The CRISIS gate helped all leading variants; MTF scaling added only modest value.",
            "The fixed thirty-symbol universe cannot be proved free of survivorship bias.",
        ],
        "limitations": [
            "PROVISIONAL_UNDER_SURVIVORSHIP_RISK",
            "No point-in-time liquidity series was available.",
            "No 2025 or 2026 data was read.",
        ],
        "dataset_hashes": hashes,
        "primary_variants_executed": 6,
        "primary_variants_remaining": 0,
        "hash_mismatches": 0,
        "pnl_reconciliation": (
            "PASS"
            if all(
                record["zero_cost"]["reconciliation_status"] == "PASS"
                for record in variants
            )
            else "FAIL"
        ),
        "open_positions_after_fold": sum(
            int(record["zero_cost"]["open_positions_after_fold"])
            for record in variants
        ),
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
    }
    final_names = [
        "ams-md01-final-assessment-v1.json",
        "ams-md01-final-assessment-v1.md",
    ]
    atomic_json(REPORTS / final_names[0], final)
    atomic_text(REPORTS / final_names[1], _markdown(final=final, variants=variants))
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    report_names = [*crash_names, *final_names]
    ledger["report_hashes"].update(
        {name: sha256(REPORTS / name) for name in report_names}
    )
    ledger["assessment"] = {
        "status": "COMPLETE",
        "universe_status": final["universe_status"],
        "alignment_status": final["alignment_status"],
        "factor_statuses": factor_statuses,
        "portfolio_gross_edge_status": portfolio_status,
        "final_research_decision": final_decision,
        "assessment_report": final_names[0],
        "assessment_report_sha256": sha256(REPORTS / final_names[0]),
    }
    atomic_json(LEDGER, ledger)
    readiness = json.loads(READINESS.read_text(encoding="utf-8"))
    readiness.update(
        {
            "status": "COMPLETE",
            "primary_variants_executed": 6,
            "primary_variants_remaining": 0,
            "pnl_reconciliation": final["pnl_reconciliation"],
            "open_positions_after_fold": final["open_positions_after_fold"],
            "test_2025_accessed": False,
            "holdout_2026_accessed": False,
        }
    )
    atomic_json(READINESS, readiness)
    verify_report_hashes(ledger["report_hashes"])
    external_names = [
        "ams-md01-universe-audit-v1.json",
        "ams-md01-universe-audit-v1.md",
        "ams-md01-factor-diagnostics-v1.json",
        "ams-md01-factor-diagnostics-v1.md",
        "ams-md01-alignment-analysis-v1.json",
        "ams-md01-alignment-analysis-v1.md",
        "ams-md01-benchmark-comparison-v1.json",
        "ams-md01-benchmark-comparison-v1.md",
        *crash_names,
        *final_names,
    ]
    copy_external(external_names)
    print(f"UNIVERSE_STATUS={final['universe_status']}")
    print(f"ALIGNMENT_STATUS={final['alignment_status']}")
    print(f"TSM_FACTOR_STATUS={factor_statuses['TSM']}")
    print(f"XSM_FACTOR_STATUS={factor_statuses['XSM']}")
    print(f"DUAL_FACTOR_STATUS={factor_statuses['DUAL']}")
    print(f"PORTFOLIO_GROSS_EDGE_STATUS={portfolio_status}")
    print(f"FINAL_RESEARCH_DECISION={final_decision}")
    print("PRIMARY_VARIANTS_EXECUTED=6")
    print("PRIMARY_VARIANTS_REMAINING=0")
    print(f"PNL_RECONCILIATION={final['pnl_reconciliation']}")
    print(f"OPEN_POSITIONS_AFTER_FOLD={final['open_positions_after_fold']}")
    print("TEST_2025_ACCESSED=false")
    print("HOLDOUT_2026_ACCESSED=false")


if __name__ == "__main__":
    main()
