"""Create the immutable AMS V4 comparison and recommendation artifacts."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from spotbot.research.ams_v4_active_conviction_swing import file_sha256

ROOT = Path.cwd()
REPORTS = ROOT / "reports/research"
LEDGER_PATH = REPORTS / "ams-v4-experiment-ledger-v1.json"
ASSESSMENT_PATH = REPORTS / "ams-v4-final-assessment-v1.json"
MARKDOWN_PATH = REPORTS / "ams-v4-final-assessment-v1.md"


def write_text_atomically(path: Path, text: str) -> None:
    descriptor, temporary = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        os.replace(temporary, path)
    except BaseException:
        if os.path.exists(temporary):
            os.unlink(temporary)
        raise


def _bootstrap_expectancy(trades: list[dict[str, Any]]) -> dict[str, Any]:
    values = np.array([float(trade["return_fraction"]) for trade in trades], dtype=float)
    if len(values) < 30:
        return {"status": "INSUFFICIENT_SAMPLE", "trade_count": len(values)}
    generator = np.random.default_rng(20260726)
    samples = generator.choice(values, size=(2000, len(values)), replace=True).mean(axis=1)
    return {
        "status": "PASS",
        "trade_count": len(values),
        "expectancy": float(values.mean()),
        "confidence_interval_95": [
            float(np.quantile(samples, 0.025)),
            float(np.quantile(samples, 0.975)),
        ],
    }


def _activity(mean_trades_per_year: float) -> str:
    if mean_trades_per_year < 100.0:
        return "SPARSE"
    if mean_trades_per_year < 150.0:
        return "LOW_ACTIVITY"
    if mean_trades_per_year <= 300.0:
        return "TARGET_ACTIVITY"
    if mean_trades_per_year <= 450.0:
        return "HIGH_ACTIVITY"
    return "POTENTIAL_OVERTRADING"


def _summary(report: dict[str, Any]) -> dict[str, Any]:
    base = report["aggregate"]["base"]
    stress = report["aggregate"]["stress"]
    base_folds = [fold["base"]["metrics"] for fold in report["fold_results"]]
    trades = [trade for fold in report["fold_results"] for trade in fold["base"]["trades"]]
    return {
        "trial_id": report["trial_id"],
        "configuration_id": report["configuration_id"],
        "portfolio_profile_id": report["portfolio_profile_id"],
        "base_compounded_return": base["aggregate_compounded_return"],
        "stress_compounded_return": stress["aggregate_compounded_return"],
        "worst_fold_return": base["worst_fold_return"],
        "worst_fold_drawdown": base["worst_fold_drawdown"],
        "positive_fold_ratio": base["positive_fold_ratio"],
        "trade_count": base["total_trade_count"],
        "trades_per_year": base["mean_trades_per_year"],
        "activity_classification": _activity(float(base["mean_trades_per_year"])),
        "calmar": base["mean_calmar"],
        "profit_factor_base": base["mean_profit_factor"],
        "profit_factor_stress": stress["mean_profit_factor"],
        "mean_maximum_drawdown": float(
            pd.Series([item["maximum_drawdown"] for item in base_folds]).mean()
        ),
        "win_rate": float(pd.Series([item["win_rate"] for item in base_folds]).mean()),
        "payoff_ratio": float(
            pd.Series(
                [item["payoff_ratio"] for item in base_folds if item["payoff_ratio"] is not None]
            ).mean()
        ),
        "mfe_capture_ratio": float(
            pd.Series(
                [
                    item["mfe_capture_ratio"]
                    for item in base_folds
                    if item["mfe_capture_ratio"] is not None
                ]
            ).mean()
        ),
        "pnl_concentration_by_symbol": float(
            pd.Series([item["pnl_concentration_by_symbol"] for item in base_folds]).mean()
        ),
        "bootstrap_expectancy": _bootstrap_expectancy(trades),
        "fold_rank_inputs": [item["net_return"] for item in base_folds],
    }


def _score(summary: dict[str, Any]) -> float:
    return float(summary["base_compounded_return"]) / max(
        float(summary["mean_maximum_drawdown"]), 0.01
    )


def main() -> None:
    ledger = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
    accounting = ledger["trial_accounting"]
    if int(accounting["executed_trials"]) != 24 or int(accounting["remaining_trials"]) != 0:
        raise RuntimeError("AMS V4 assessment requires all 24 registered trials.")
    reports: list[dict[str, Any]] = []
    for trial in ledger["trial_plan"]:
        if trial["trial_status"] != "EXECUTED":
            raise RuntimeError(f"Trial not executed: {trial['trial_id']}")
        path = ROOT / trial["report_path"]
        if file_sha256(path) != trial["report_sha256"]:
            raise RuntimeError(f"Report hash mismatch: {path}")
        reports.append(json.loads(path.read_text(encoding="utf-8")))
    summaries = [_summary(report) for report in reports]
    ranked = sorted(summaries, key=lambda item: (-_score(item), item["trial_id"]))
    for fold_index in range(3):
        ordered = sorted(
            summaries,
            key=lambda item: (-float(item["fold_rank_inputs"][fold_index]), item["trial_id"]),
        )
        for rank, item in enumerate(ordered, start=1):
            item.setdefault("fold_ranks", []).append(rank)
    for item in summaries:
        ranks = item["fold_ranks"]
        item["rank_stability_standard_deviation"] = float(pd.Series(ranks).std(ddof=0))
    best = ranked[0]
    profile_limit = 0.25 if best["portfolio_profile_id"].endswith("P01") else 0.30
    expectancy = best["bootstrap_expectancy"]
    strong = (
        best["positive_fold_ratio"] >= 2.0 / 3.0
        and best["worst_fold_return"] >= -0.12
        and best["mean_maximum_drawdown"] <= profile_limit
        and best["calmar"] >= 1.5
        and best["profit_factor_base"] >= 1.3
        and best["profit_factor_stress"] >= 1.1
        and best["stress_compounded_return"] > 0.0
        and best["pnl_concentration_by_symbol"] < 0.60
        and best["activity_classification"] not in {"SPARSE", "POTENTIAL_OVERTRADING"}
        and expectancy.get("status") == "PASS"
        and expectancy["confidence_interval_95"][0] > 0.0
    )
    assessment = (
        "REQUEST_2025_TEST_CANDIDATE"
        if strong
        else ("REVISE_WITHOUT_2025" if best["base_compounded_return"] > 0.0 else "FAIL")
    )
    paired = []
    by_key = {(item["configuration_id"], item["portfolio_profile_id"]): item for item in summaries}
    for sequence in range(1, 13, 2):
        for profile in ("AMS-V4-PORTFOLIO-P01", "AMS-V4-PORTFOLIO-P02"):
            no_fib = by_key[(f"AMS-V4-A{sequence:02d}", profile)]
            soft_fib = by_key[(f"AMS-V4-A{sequence + 1:02d}", profile)]
            paired.append(
                {
                    "profile": profile,
                    "no_fibonacci": no_fib["configuration_id"],
                    "soft_fibonacci": soft_fib["configuration_id"],
                    "base_return_difference": soft_fib["base_compounded_return"]
                    - no_fib["base_compounded_return"],
                    "stress_return_difference": soft_fib["stress_compounded_return"]
                    - no_fib["stress_compounded_return"],
                }
            )
    payload = {
        "schema_version": "ams-v4-final-assessment-v1",
        "status": "PASS",
        "assessment": assessment,
        "authorized_trials": 24,
        "executed_trials": 24,
        "remaining_trials": 0,
        "best_return_drawdown_model": best,
        "best_robustness_model": min(
            summaries,
            key=lambda item: (
                item["worst_fold_drawdown"],
                -item["positive_fold_ratio"],
                item["trial_id"],
            ),
        ),
        "best_stress_model": max(
            summaries, key=lambda item: (item["stress_compounded_return"], item["trial_id"])
        ),
        "all_trials": sorted(summaries, key=lambda item: item["trial_id"]),
        "top_five": ranked[:5],
        "paired_fibonacci_comparison": paired,
        "overfitting": {
            "models_tested": 24,
            "deflated_sharpe_ratio": "INSUFFICIENT_INDEPENDENT_FOLDS",
            "probability_of_backtest_overfitting": "INSUFFICIENT_FOLDS_FOR_VALID_CSCV",
            "parameter_plateau_analysis": (
                "Twelve pre-registered behavioral configurations; compare ranked paired "
                "results, not a post-hoc optimum."
            ),
        },
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
        "next_action": "DO_NOT_OPEN_2025"
        if assessment != "REQUEST_2025_TEST_CANDIDATE"
        else "REQUEST_GOVERNED_2025_OPENING",
    }
    text = json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n"
    write_text_atomically(ASSESSMENT_PATH, text)
    table = "\n".join(
        f"| {item['trial_id']} | {item['configuration_id']} | {item['portfolio_profile_id']} | "
        f"{item['base_compounded_return']:.2%} | {item['stress_compounded_return']:.2%} | "
        f"{item['mean_maximum_drawdown']:.2%} | {item['trade_count']} |"
        for item in sorted(summaries, key=lambda value: value["trial_id"])
    )
    markdown = (
        "# AMS V4 Active Conviction Swing — Final Assessment\n\n"
        f"Assessment: **{assessment}**\n\n"
        f"Best return/drawdown model: `{best['trial_id']}` / `{best['configuration_id']}` / "
        f"`{best['portfolio_profile_id']}`.\n\n"
        "| Trial | Alpha | Profile | Base | Stress | Mean Max DD | Trades |\n"
        "|---|---|---|---:|---:|---:|---:|\n"
        f"{table}\n\n"
        "The 2025 and 2026 locks were not opened. Deflated Sharpe and PBO are reported "
        "as insufficient because three folds cannot support valid independent CSCV.\n"
    )
    write_text_atomically(MARKDOWN_PATH, markdown)
    ledger["final_assessment"] = {
        "report_path": str(ASSESSMENT_PATH.relative_to(ROOT)).replace("\\", "/"),
        "report_sha256": file_sha256(ASSESSMENT_PATH),
        "assessment": assessment,
    }
    write_text_atomically(
        LEDGER_PATH, json.dumps(ledger, indent=2, sort_keys=True, allow_nan=False) + "\n"
    )
    print(ASSESSMENT_PATH)


if __name__ == "__main__":
    main()
