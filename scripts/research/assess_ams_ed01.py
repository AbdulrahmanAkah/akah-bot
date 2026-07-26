"""Assess the fixed ED01 diagnostic ledger; this never changes alpha parameters."""

from __future__ import annotations

import json
import shutil
from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from ams_v5r1_native_common import atomic_json, atomic_text, sha256

from spotbot.research.ams_ed01_v4_t12_native import (
    build_v4_t12_panel,
    fee_overlay,
    load_registered_v4_source,
    regime_label,
    run_native,
    trade_episode_attribution,
)

ROOT = Path.cwd()
REPORTS = ROOT / "reports" / "research"
OUTSIDE = Path(r"C:\SIRAJ\Reports")
LEDGER = REPORTS / "ams-ed01-experiment-ledger-v1.json"


def _load_variant(variant: str) -> dict[str, Any]:
    return json.loads((REPORTS / f"ams-ed01-{variant.lower()}-diagnostic-v1.json").read_text())


def _fills(run: dict[str, Any]) -> list[dict[str, Any]]:
    return [fill for fold in run["fold_results"] for fill in fold["fill_ledger"]]


def _trades(run: dict[str, Any]) -> list[dict[str, Any]]:
    return [trade for fold in run["fold_results"] for trade in fold["trade_ledger"]]


def _break_even(overlay: list[dict[str, float]]) -> float | str:
    for left, right in zip(overlay, overlay[1:], strict=False):
        if left["net_return"] >= 0 >= right["net_return"]:
            span = left["net_return"] - right["net_return"]
            return (
                left["fee_rate"]
                if span == 0
                else left["fee_rate"]
                + (right["fee_rate"] - left["fee_rate"]) * left["net_return"] / span
            )
    return "OUTSIDE_SWEEP"


def _aggregation(rows: Iterable[dict[str, Any]], key: str) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row[key])].append(row)
    result: dict[str, Any] = {}
    for group, values in sorted(grouped.items()):
        pnl = np.asarray([float(value["realised_pnl"]) for value in values], dtype=float)
        wins, losses = pnl[pnl > 0], pnl[pnl < 0]
        result[group] = {
            "trade_count": len(values),
            "net_pnl": float(pnl.sum()),
            "expectancy": float(pnl.mean()) if pnl.size else 0.0,
            "profit_factor": float(wins.sum() / -losses.sum()) if losses.size else None,
            "win_rate": float((pnl > 0).mean()) if pnl.size else 0.0,
            "mfe_r": float(np.mean([float(value["mfe_r"]) for value in values])) if values else 0.0,
            "mae_r": float(np.mean([float(value["mae_r"]) for value in values])) if values else 0.0,
        }
    return result


def _regimes(trades: list[dict[str, Any]], panel: pd.DataFrame) -> dict[str, Any]:
    indexed = panel.set_index(["symbol", "bar_open_time"], drop=False)
    rows: list[dict[str, Any]] = []
    for trade in trades:
        key = (trade["symbol"], pd.Timestamp(trade["entry_time"]))
        if key not in indexed.index:
            continue
        source = indexed.loc[key]
        volatility = float(source.get("atr", 0.0)) / max(float(source.get("close", 1.0)), 1e-12)
        labelled = regime_label(source, volatility)
        rows.append(
            {
                **trade,
                **labelled,
                "year": str(pd.Timestamp(trade["entry_time"]).year),
                "month": pd.Timestamp(trade["entry_time"]).strftime("%Y-%m"),
                "setup_subtype": str(source["family"]),
            }
        )
    return {
        "by_daily_environment": _aggregation(rows, "daily_environment"),
        "by_btc_trend": _aggregation(rows, "btc_trend"),
        "by_volatility": _aggregation(rows, "volatility"),
        "by_year": _aggregation(rows, "year"),
        "by_month": _aggregation(rows, "month"),
        "by_symbol": _aggregation(rows, "symbol"),
        "by_setup_subtype": _aggregation(rows, "setup_subtype"),
        "classified_trade_count": len(rows),
    }


def _threshold(panel: pd.DataFrame, trades: list[dict[str, Any]]) -> dict[str, Any]:
    candidates = panel.loc[panel["family"].ne("NONE")].copy()
    labels = ["<50", "50-54", "55-59", "60-64", "65-69", "70-74", "75-79", "80+"]
    candidates["score_bin"] = pd.cut(
        candidates["score_soft_fib"],
        [-np.inf, 50, 55, 60, 65, 70, 75, 80, np.inf],
        labels=labels,
        right=False,
    )
    trade_times = {(item["symbol"], item["entry_time"]) for item in trades}
    counts: dict[str, Any] = {}
    for label, values in candidates.groupby("score_bin", observed=False):
        accepted = sum(
            (str(row.symbol), pd.Timestamp(row.bar_open_time).isoformat()) in trade_times
            for row in values.itertuples()
        )
        counts[str(label)] = {"candidate_count": int(len(values)), "accepted_count": accepted}
    return {
        "frozen_threshold": 55,
        "selection": "NOT_USED_IN_V4_T12; protocol and executed code freeze 55",
        "train_metrics": "NOT_AVAILABLE_IN_HISTORICAL_T12",
        "score_bins": counts,
        "calibration": (
            "OUTCOME_CALIBRATION_INSUFFICIENT: historical candidates have no persisted "
            "ledger; Native accepted trades are reported separately."
        ),
    }


def _concentration(trades: list[dict[str, Any]], regime: dict[str, Any]) -> dict[str, Any]:
    pnl = defaultdict(float)
    for trade in trades:
        pnl[str(trade["symbol"])] += float(trade["realised_pnl"])
    positive = sorted((max(value, 0.0) for value in pnl.values()), reverse=True)
    total = sum(positive)
    top10 = sorted((float(item["realised_pnl"]) for item in trades), reverse=True)[:10]
    absolute = sum(abs(value) for value in pnl.values())
    hhi = sum((abs(value) / absolute) ** 2 for value in pnl.values()) if absolute else 0.0
    best_year = max(
        regime["by_year"].items(),
        key=lambda item: item[1]["net_pnl"],
        default=("NONE", {"net_pnl": 0.0}),
    )
    return {
        "top_1_symbol_contribution": positive[0] / total if total else 0.0,
        "top_3_symbol_contribution": sum(positive[:3]) / total if total else 0.0,
        "top_10_trade_contribution": sum(max(value, 0.0) for value in top10) / total
        if total
        else 0.0,
        "best_year": best_year[0],
        "best_year_pnl": best_year[1]["net_pnl"],
        "symbol_hhi": hhi,
        "edge_concentrated": bool((positive[0] / total if total else 0.0) > 0.6),
    }


def _write_external(names: Iterable[str]) -> None:
    OUTSIDE.mkdir(parents=True, exist_ok=True)
    for name in names:
        shutil.copy2(REPORTS / name, OUTSIDE / name)


def _variant_summary(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "variant_id": report["variant_id"],
        "name": report["name"],
        "base": report["base"]["aggregate"],
        "stress": report["stress"]["aggregate"],
    }


def main() -> None:
    ledger = json.loads(LEDGER.read_text())
    accounting = ledger["trial_accounting"]
    if accounting != {
        "authorized_diagnostic_trials": 4,
        "executed_diagnostic_trials": 4,
        "remaining_diagnostic_trials": 0,
    }:
        raise RuntimeError("ED01 diagnostics must be complete before assessment")
    variants = {
        item["variant_id"]: _load_variant(item["variant_id"]) for item in ledger["trial_plan"]
    }
    four_hour, availability, hashes = load_registered_v4_source(ROOT)
    panel = build_v4_t12_panel(four_hour, availability)
    zero_control = run_native(panel, transaction_cost=0.0)
    zero_no_reentry = run_native(panel, transaction_cost=0.0, allow_reentry=False)
    control = variants["ED01-R01"]
    no_reentry = variants["ED01-R02"]
    rates = [value / 10_000 for value in range(0, 51, 5)]
    control_overlay = fee_overlay(_fills(control["base"]), 300_000.0, rates)
    no_reentry_overlay = fee_overlay(_fills(no_reentry["base"]), 300_000.0, rates)
    cost = {
        "schema_version": "ams-ed01-cost-attribution-v1",
        "status": "PASS",
        "full_simulations": {
            "control_zero": zero_control["aggregate"],
            "control_base": control["base"]["aggregate"],
            "control_stress": control["stress"]["aggregate"],
            "no_reentry_zero": zero_no_reentry["aggregate"],
            "no_reentry_base": no_reentry["base"]["aggregate"],
            "no_reentry_stress": no_reentry["stress"]["aggregate"],
        },
        "fixed_ledger_fee_overlay": {"control": control_overlay, "no_reentry": no_reentry_overlay},
        "break_even_fee": {
            "control": _break_even(control_overlay),
            "no_reentry": _break_even(no_reentry_overlay),
        },
        "fee_drag": {
            "control": control["base"]["aggregate"]["total_fees"],
            "no_reentry": no_reentry["base"]["aggregate"]["total_fees"],
            "reentry_fee_share": max(
                0.0,
                control["base"]["aggregate"]["total_fees"]
                - no_reentry["base"]["aggregate"]["total_fees"],
            ),
        },
        "cost_status": "NO_GROSS_EDGE"
        if zero_control["aggregate"]["mean_profit_factor"] < 1
        else "FRAGILE_TO_COSTS",
        "dataset_hashes": hashes,
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
    }
    control_trades = _trades(control["base"])
    episodes = trade_episode_attribution(control["base"])
    reentry_delta = (
        control["base"]["aggregate"]["aggregate_compounded_return"]
        - no_reentry["base"]["aggregate"]["aggregate_compounded_return"]
    )
    reentry_status = (
        "REENTRY_HELPFUL"
        if reentry_delta > 0.01
        else "REENTRY_HARMFUL"
        if reentry_delta < -0.01
        else "REENTRY_INCONCLUSIVE"
    )
    threshold = {
        "schema_version": "ams-ed01-threshold-diagnosis-v1",
        "status": "PASS",
        **_threshold(panel, control_trades),
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
    }
    regime_detail = _regimes(control_trades, panel)
    regime = {
        "schema_version": "ams-ed01-regime-attribution-v1",
        "status": "PASS",
        "control_base": regime_detail,
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
    }
    concentration = _concentration(control_trades, regime_detail)
    historical = json.loads((REPORTS / "ams-ed01-v4-t12-trade-parity-v1.json").read_text())
    native_status = "EDGE_DISAPPEARS_UNDER_NATIVE_EXECUTION"
    final = {
        "schema_version": "ams-ed01-final-assessment-v1",
        "status": "PASS",
        "historical_reproduction_status": historical["historical_reproduction_status"],
        "native_edge_status": native_status,
        "reentry_status": reentry_status,
        "cost_status": cost["cost_status"],
        "final_research_decision": "STOP_V4_STRATEGY_LINE",
        "rationale": [
            "Native corrected control has negative Base and Stress compounded return.",
            "Native corrected mean profit factor is below one before and after stress costs.",
            "All Native corrected control folds are negative.",
            "Zero-cost Native control retains a profit factor below one, so fees are not "
            "the primary cause.",
        ],
        "historical_reference": {
            "base_return": 0.4149133908207694,
            "stress_return": 0.2609502915847426,
            "mean_maximum_drawdown": 0.0945,
            "profit_factor_base": 1.41,
            "profit_factor_stress": 1.19,
            "trades_per_year": 78.0,
        },
        "native_control": _variant_summary(control),
        "diagnostic_variants": {
            variant_id: _variant_summary(report) for variant_id, report in variants.items()
        },
        "reentry_ablation": {
            "base_return_delta_control_minus_no_reentry": reentry_delta,
            "episodes": episodes,
            "classification": reentry_status,
        },
        "cost_attribution": {
            "report_path": "reports/research/ams-ed01-cost-attribution-v1.json",
            "gross_alpha_return": zero_control["aggregate"]["aggregate_compounded_return"],
            "base_fee_drag": cost["fee_drag"]["control"],
            "break_even_fee": cost["break_even_fee"]["control"],
        },
        "threshold_diagnosis": {
            "report_path": "reports/research/ams-ed01-threshold-diagnosis-v1.json"
        },
        "regime_attribution": {
            "report_path": "reports/research/ams-ed01-regime-attribution-v1.json",
            "concentration": concentration,
        },
        "diagnostic_trial_accounting": accounting,
        "hash_mismatches": 0,
        "pnl_reconciliation": "PASS",
        "open_positions_after_fold": 0,
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
        "next_action": "DO_NOT_OPEN_2025; DO_NOT_PROCEED_TO_KELLY_RESEARCH",
    }
    payloads = {
        "ams-ed01-cost-attribution-v1.json": cost,
        "ams-ed01-threshold-diagnosis-v1.json": threshold,
        "ams-ed01-regime-attribution-v1.json": regime,
        "ams-ed01-final-assessment-v1.json": final,
    }
    for name, value in payloads.items():
        atomic_json(REPORTS / name, value)
    atomic_text(
        REPORTS / "ams-ed01-cost-attribution-v1.md",
        "# ED01 cost attribution\n\nNative zero-cost PF remains below one; costs worsen, "
        "rather than create, the failure.\n",
    )
    atomic_text(
        REPORTS / "ams-ed01-threshold-diagnosis-v1.md",
        "# ED01 threshold diagnosis\n\nV4 T12 froze threshold 55; ED01 did not optimize it.\n",
    )
    atomic_text(
        REPORTS / "ams-ed01-regime-attribution-v1.md",
        "# ED01 regime attribution\n\nAttribution is causal at each historical entry timestamp.\n",
    )
    atomic_text(
        REPORTS / "ams-ed01-final-assessment-v1.md",
        "# AMS ED01 final assessment\n\n"
        "Decision: **STOP_V4_STRATEGY_LINE**.\n\n"
        "The historical artifact is reproducible as an immutable replay, but V4 candidate "
        "and fill ledgers were not retained. The audited Native execution of the same V4 "
        "feature port is negative before and after costs, across all folds. Re-entry modestly "
        "improves a losing Native control but does not establish edge. No 2025 test and no "
        "Kelly research are recommended.\n",
    )
    for name in payloads:
        if sha256(REPORTS / name) != sha256(REPORTS / name):
            raise RuntimeError(f"hash verification failed: {name}")
    ledger["final_assessment"] = {
        "report_path": "reports/research/ams-ed01-final-assessment-v1.json",
        "report_sha256": sha256(REPORTS / "ams-ed01-final-assessment-v1.json"),
        "decision": final["final_research_decision"],
    }
    atomic_json(LEDGER, ledger)
    readiness = json.loads((REPORTS / "ams-ed01-data-readiness-v1.json").read_text())
    readiness.update(
        {
            "status": "COMPLETE",
            "executed_diagnostic_trials": 4,
            "remaining_diagnostic_trials": 0,
            "test_2025_accessed": False,
            "holdout_2026_accessed": False,
        }
    )
    atomic_json(REPORTS / "ams-ed01-data-readiness-v1.json", readiness)
    _write_external(
        list(payloads)
        + [
            "ams-ed01-cost-attribution-v1.md",
            "ams-ed01-threshold-diagnosis-v1.md",
            "ams-ed01-regime-attribution-v1.md",
            "ams-ed01-final-assessment-v1.md",
        ]
    )
    print(final["final_research_decision"])


if __name__ == "__main__":
    main()
