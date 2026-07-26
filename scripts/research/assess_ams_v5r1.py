"""Assess all 24 native V5R1 trials without changing the frozen criteria."""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

import numpy as np
import pandas as pd
from ams_v5r1_native_common import REPORTS, ROOT, atomic_json, atomic_text, sha256

LEDGER = REPORTS / "ams-v5r1-experiment-ledger-v1.json"


def bootstrap_interval(values: list[float]) -> list[float] | str:
    if len(values) < 20:
        return "INSUFFICIENT_SAMPLE"
    generator = np.random.default_rng(5_001)
    samples = np.asarray(values, dtype=float)
    means = [
        float(generator.choice(samples, len(samples), replace=True).mean())
        for _ in range(2_000)
    ]
    return [float(np.quantile(means, 0.025)), float(np.quantile(means, 0.975))]


def _activity(trades_per_year: float) -> str:
    if trades_per_year < 90:
        return "VERY_SPARSE"
    if trades_per_year < 120:
        return "SPARSE"
    if trades_per_year < 160:
        return "MODERATE_ACTIVITY"
    if trades_per_year <= 220:
        return "TARGET_ACTIVITY"
    if trades_per_year <= 320:
        return "HIGH_ACTIVITY"
    return "POTENTIAL_OVERTRADING"


def main() -> None:
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    accounting = ledger["trial_accounting"]
    if accounting["executed_trials"] != 24 or accounting["remaining_trials"] != 0:
        raise RuntimeError("all 24 V5R1 trials must execute before assessment")
    rows: list[dict[str, Any]] = []
    fold_returns: dict[str, list[float]] = {}
    hash_mismatches = 0
    for trial in ledger["trial_plan"]:
        path = ROOT / trial["report_path"]
        if sha256(path) != trial["report_sha256"]:
            hash_mismatches += 1
            continue
        report = json.loads(path.read_text(encoding="utf-8"))
        base = report["aggregate"]["base"]
        stress = report["aggregate"]["stress"]
        base_metrics = [fold["base"]["metrics"] for fold in report["fold_results"]]
        trades = [
            trade
            for fold in report["fold_results"]
            for trade in fold["base"]["trade_ledger"]
        ]
        trade_returns = [float(trade["return_fraction"]) for trade in trades]
        payoff_values = [
            float(item["payoff_ratio"])
            for item in base_metrics
            if item["payoff_ratio"] is not None
        ]
        fold_returns[trial["trial_id"]] = [
            float(item["net_return"]) for item in base_metrics
        ]
        row = {
            "trial_id": trial["trial_id"],
            "configuration_id": trial["configuration_id"],
            "portfolio_profile_id": trial["portfolio_profile_id"],
            "entry_family": report["configuration"]["family"],
            "stop_model": report["configuration"]["stop_model"],
            "fibonacci_mode": report["configuration"]["fibonacci_mode"],
            "base_compounded_return": base["aggregate_compounded_return"],
            "stress_compounded_return": stress["aggregate_compounded_return"],
            "maximum_drawdown": base["mean_maximum_drawdown"],
            "worst_drawdown": base["worst_maximum_drawdown"],
            "calmar": base["mean_calmar"],
            "profit_factor_base": base["mean_profit_factor"],
            "profit_factor_stress": stress["mean_profit_factor"],
            "trades_per_year": base["mean_trades_per_year"],
            "trade_count": base["total_trade_count"],
            "activity": _activity(base["mean_trades_per_year"]),
            "positive_fold_ratio": base["positive_fold_ratio"],
            "worst_fold_return": base["worst_fold_return"],
            "win_rate": base["mean_win_rate"],
            "payoff_ratio": float(pd.Series(payoff_values).mean()) if payoff_values else None,
            "expectancy": base["mean_expectancy"],
            "bootstrap_expectancy_ci": bootstrap_interval(trade_returns),
            "mfe_capture": base["mean_mfe_capture"],
            "add_on_count": base["total_add_ons"],
            "reentry_count": base["total_reentries"],
            "pnl_concentration_by_symbol": float(
                pd.Series(
                    [item["pnl_concentration_by_symbol"] for item in base_metrics]
                ).mean()
            ),
            "selected_thresholds": [
                fold["fold"]["threshold_selection"]["selected_threshold"]
                for fold in report["fold_results"]
            ],
        }
        rows.append(row)
    if hash_mismatches:
        raise RuntimeError(f"{hash_mismatches} trial report hash mismatches")
    ranked = sorted(
        rows,
        key=lambda item: (
            -item["base_compounded_return"] / max(item["maximum_drawdown"], 0.001),
            -item["stress_compounded_return"],
            item["trial_id"],
        ),
    )
    for rank, item in enumerate(ranked, start=1):
        item["overall_rank"] = rank
    rank_frame = pd.DataFrame(
        {
            trial_id: pd.Series(values).rank(ascending=False)
            for trial_id, values in fold_returns.items()
        }
    ).T
    correlations = []
    for left in range(3):
        for right in range(left + 1, 3):
            value = rank_frame[left].corr(rank_frame[right], method="spearman")
            if pd.notna(value):
                correlations.append(float(value))
    rank_stability = float(pd.Series(correlations).mean()) if correlations else None
    best = ranked[0]
    candidate = (
        best["positive_fold_ratio"] >= 2 / 3
        and best["worst_fold_return"] >= -0.10
        and best["stress_compounded_return"] > 0
        and best["calmar"] is not None
        and best["calmar"] >= 1.20
        and best["profit_factor_base"] >= 1.30
        and best["profit_factor_stress"] >= 1.12
        and (
            best["trades_per_year"] >= 120
            or best["base_compounded_return"] > 0.4149
        )
        and best["pnl_concentration_by_symbol"] < 0.60
        and rank_stability is not None
        and rank_stability > 0
    )
    if candidate:
        assessment = "REQUEST_2025_TEST_CANDIDATE"
    elif any(item["base_compounded_return"] > 0 for item in rows):
        assessment = "REVISE_WITHOUT_2025"
    else:
        assessment = "FAIL"
    group_comparisons: dict[str, dict[str, float]] = {}
    for dimension in ("entry_family", "stop_model", "fibonacci_mode", "portfolio_profile_id"):
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for item in rows:
            grouped[str(item[dimension])].append(item)
        group_comparisons[dimension] = {
            key: float(pd.Series([item["base_compounded_return"] for item in values]).mean())
            for key, values in grouped.items()
        }
    payload = {
        "schema_version": "ams-v5r1-final-assessment-v1",
        "status": "PASS",
        "assessment": assessment,
        "authorized_trials": 24,
        "executed_trials": 24,
        "remaining_trials": 0,
        "hash_mismatches": 0,
        "best_model": best,
        "top_five": ranked[:5],
        "all_trials": sorted(rows, key=lambda item: item["trial_id"]),
        "group_comparisons": group_comparisons,
        "rank_stability": {
            "mean_fold_spearman": rank_stability,
            "pairwise": correlations,
        },
        "multiple_testing": {
            "models_tested": 24,
            "deflated_sharpe_ratio": "INSUFFICIENT_INDEPENDENT_FOLDS",
            "cscv_pbo": "INSUFFICIENT_FOLDS_FOR_VALID_CSCV",
            "white_reality_check": "INSUFFICIENT_INDEPENDENT_TIME_BLOCKS",
            "parameter_plateau": group_comparisons,
        },
        "comparison_v4_t12": {
            "reference": {
                "base_return": 0.4149,
                "stress_return": 0.2610,
                "maximum_drawdown": 0.0945,
                "profit_factor_base": 1.41,
                "profit_factor_stress": 1.19,
                "trades_per_year": 78,
            },
            "difference": {
                "base_return": best["base_compounded_return"] - 0.4149,
                "stress_return": best["stress_compounded_return"] - 0.2610,
                "maximum_drawdown": best["maximum_drawdown"] - 0.0945,
                "profit_factor_base": best["profit_factor_base"] - 1.41,
                "profit_factor_stress": best["profit_factor_stress"] - 1.19,
                "trades_per_year": best["trades_per_year"] - 78,
            },
        },
        "comparison_v5_legacy_t12": {
            "reference": {
                "base_return": 0.0272,
                "stress_return": 0.0236,
                "maximum_drawdown": 0.0071,
                "profit_factor_base": 2.84,
                "profit_factor_stress": 2.43,
                "trades_per_year": 2.3,
            },
            "difference": {
                "base_return": best["base_compounded_return"] - 0.0272,
                "stress_return": best["stress_compounded_return"] - 0.0236,
                "maximum_drawdown": best["maximum_drawdown"] - 0.0071,
                "trades_per_year": best["trades_per_year"] - 2.3,
            },
        },
        "limitations": [
            "Only three independent validation years are available.",
            "CSCV, Deflated Sharpe, and Reality Check samples are insufficient.",
            "No 2025 or 2026 data was opened.",
        ],
        "next_action": (
            "REQUEST_GOVERNED_2025_OPENING"
            if assessment == "REQUEST_2025_TEST_CANDIDATE"
            else "DO_NOT_OPEN_2025"
        ),
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
    }
    output = REPORTS / "ams-v5r1-final-assessment-v1.json"
    atomic_json(output, payload)
    table = "\n".join(
        "| {trial_id} | {configuration_id} | {portfolio_profile_id} | "
        "{base_compounded_return:.2%} | {stress_compounded_return:.2%} | "
        "{maximum_drawdown:.2%} | {trades_per_year:.1f} |".format(**item)
        for item in sorted(rows, key=lambda value: value["trial_id"])
    )
    markdown = (
        "# AMS V5R1 Native Final Assessment\n\n"
        f"Assessment: **{assessment}**\n\n"
        f"Best model: **{best['trial_id']} / {best['configuration_id']} / "
        f"{best['portfolio_profile_id']}**\n\n"
        "| Trial | Alpha | Profile | Base | Stress | Mean DD | Trades/year |\n"
        "|---|---|---|---:|---:|---:|---:|\n"
        f"{table}\n\n"
        f"- Rank stability: {rank_stability}\n"
        "- Hash mismatches: 0\n"
        "- 2025 accessed: false\n"
        "- 2026 accessed: false\n"
    )
    atomic_text(REPORTS / "ams-v5r1-final-assessment-v1.md", markdown)
    ledger["final_assessment"] = {
        "report_path": "reports/research/ams-v5r1-final-assessment-v1.json",
        "report_sha256": sha256(output),
        "assessment": assessment,
    }
    atomic_json(LEDGER, ledger)
    readiness_path = REPORTS / "ams-v5r1-data-readiness-v1.json"
    readiness = json.loads(readiness_path.read_text(encoding="utf-8"))
    readiness.update(
        {
            "status": "AMS_V5R1_COMPLETE",
            "assessment": assessment,
            "executed_trials": 24,
            "remaining_trials": 0,
            "next_action": payload["next_action"],
            "test_2025_accessed": False,
            "holdout_2026_accessed": False,
        }
    )
    atomic_json(readiness_path, readiness)
    print(assessment)


if __name__ == "__main__":
    main()
