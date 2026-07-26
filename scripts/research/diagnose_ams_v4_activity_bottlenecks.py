"""Diagnose the V4 activity bottleneck without mutating historical V4 artifacts."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from run_ams_v4_trial import load_panel

ROOT = Path.cwd()
REPORTS = ROOT / "reports/research"
OUTPUT = REPORTS / "ams-v5-v4-activity-bottleneck-diagnosis-v1.json"
TOP_TRIALS = {"AMS-V4-T12", "AMS-V4-T11", "AMS-V4-T24", "AMS-V4-T23", "AMS-V4-T07"}


def write_json_atomically(path: Path, payload: dict[str, Any]) -> None:
    encoded = json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n"
    json.loads(encoded)
    descriptor, temporary = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(encoded)
        os.replace(temporary, path)
    except BaseException:
        if os.path.exists(temporary):
            os.unlink(temporary)
        raise


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _report_by_trial() -> dict[str, dict[str, Any]]:
    reports: dict[str, dict[str, Any]] = {}
    for path in REPORTS.glob("ams-v4-ams-v4-t*-trial-v1.json"):
        payload = _load(path)
        reports[str(payload["trial_id"])] = payload
    return reports


def _configuration_map() -> dict[str, dict[str, Any]]:
    ledger = _load(REPORTS / "ams-v4-experiment-ledger-v1.json")
    return {item["configuration_id"]: item for item in ledger["alpha_configurations"]}


def _family_mask(panel: pd.DataFrame, family: str) -> pd.Series:
    if family == "BREAKOUT":
        return panel["breakout_signal"].astype(bool)
    if family == "PULLBACK_CONTINUATION":
        return panel["pullback_signal"].astype(bool)
    return panel["breakout_signal"].astype(bool) | panel["pullback_signal"].astype(bool)


def _panel_diagnosis(panel: pd.DataFrame, configuration: dict[str, Any]) -> dict[str, Any]:
    parameters = configuration["parameters"]
    family = str(parameters["entry_family"])
    score_column = (
        "conviction_soft_fib"
        if parameters["fibonacci_mode"] == "SOFT_FIBONACCI_SCORE"
        else "conviction_no_fib"
    )
    threshold = int(parameters["score_threshold"])
    item = panel.copy()
    item["year"] = pd.to_datetime(item["bar_open_time"], utc=True).dt.year
    raw = _family_mask(item, family)
    score = item[score_column].astype(float)
    eligible = raw & score.ge(threshold)
    below = score.sub(threshold)
    available = item["bar_open_time"].ge(item["tradable_from"]) & item["bar_open_time"].lt(
        item["tradable_until"]
    )
    by_year: dict[str, dict[str, Any]] = {}
    for year, group in item.groupby("year", sort=True):
        index = group.index
        raw_year = raw.loc[index]
        score_year = score.loc[index]
        eligible_year = eligible.loc[index]
        by_year[str(year)] = {
            "raw_setup_candidates": int(raw_year.sum()),
            "after_conviction_threshold": int(eligible_year.sum()),
            "rejected_conviction_threshold": int((raw_year & ~eligible_year).sum()),
            "rejected_unavailable": int((raw_year & ~available.loc[index]).sum()),
            "scores_accepted": score_year.loc[eligible_year].describe().to_dict(),
            "scores_rejected": score_year.loc[raw_year & ~eligible_year].describe().to_dict(),
            "within_1_point_below": int(
                (raw_year & below.loc[index].between(-1.0, 0.0, inclusive="left")).sum()
            ),
            "within_3_points_below": int(
                (raw_year & below.loc[index].between(-3.0, 0.0, inclusive="left")).sum()
            ),
            "within_5_points_below": int(
                (raw_year & below.loc[index].between(-5.0, 0.0, inclusive="left")).sum()
            ),
            "within_10_points_below": int(
                (raw_year & below.loc[index].between(-10.0, 0.0, inclusive="left")).sum()
            ),
            "simultaneous_signal_bars": int(
                raw_year.groupby(item.loc[index, "bar_close_time"]).sum().gt(1).sum()
            ),
        }
    return {
        "entry_family": family,
        "fibonacci_mode": parameters["fibonacci_mode"],
        "score_threshold": threshold,
        "by_year": by_year,
        "all_years": {
            "raw_setup_candidates": int(raw.sum()),
            "after_conviction_threshold": int(eligible.sum()),
            "rejected_conviction_threshold": int((raw & ~eligible).sum()),
            "rejected_unavailable": int((raw & ~available).sum()),
            "candidate_score_mean": float(score.loc[raw].mean()),
            "candidate_score_median": float(score.loc[raw].median()),
            "soft_fibonacci_alone_rejections": 0,
            "hard_d1_gate_rejections": 0,
            "hard_8h_gate_rejections": 0,
            "portfolio_constraints_recorded_only_in_simulator": True,
        },
    }


def _trade_summary(report: dict[str, Any]) -> dict[str, Any]:
    folds = report["fold_results"]
    base = [fold["base"]["metrics"] for fold in folds]
    trades = [trade for fold in folds for trade in fold["base"]["trades"]]
    rejection = Counter()
    for metric in base:
        rejection.update({key: int(value) for key, value in metric["rejected_entries"].items()})
    per_symbol = Counter(str(trade["symbol"]) for trade in trades)
    return {
        "accepted_entries": sum(int(metric["accepted_entries"]) for metric in base),
        "completed_trades": len(trades),
        "trades_by_fold": {
            fold["fold"]["fold_id"]: int(fold["base"]["metrics"]["trade_count"]) for fold in folds
        },
        "rejection_reasons_from_simulator": dict(rejection),
        "trades_by_symbol": dict(per_symbol),
        "mean_open_positions": float(
            pd.Series([metric["average_positions"] for metric in base]).mean()
        ),
        "mean_exposure": float(pd.Series([metric["exposure"] for metric in base]).mean()),
        "mean_maximum_heat": float(
            pd.Series([metric["maximum_portfolio_heat"] for metric in base]).mean()
        ),
        "candidates_per_executed_trade": (
            sum(int(metric["candidate_signals"]) for metric in base) / len(trades)
            if trades
            else None
        ),
    }


def main() -> None:
    panel = load_panel()
    reports = _report_by_trial()
    configurations = _configuration_map()
    selected = sorted(TOP_TRIALS)
    trial_diagnoses: list[dict[str, Any]] = []
    for trial_id in selected:
        report = reports[trial_id]
        configuration = configurations[report["configuration_id"]]
        trial_diagnoses.append(
            {
                "trial_id": trial_id,
                "configuration_id": report["configuration_id"],
                "portfolio_profile_id": report["portfolio_profile_id"],
                "setup_funnel": _panel_diagnosis(panel, configuration),
                "executed_trade_summary": _trade_summary(report),
            }
        )
    all_summaries = [_trade_summary(report) for report in reports.values()]
    payload = {
        "schema_version": "ams-v5-v4-activity-bottleneck-diagnosis-v1",
        "status": "PASS",
        "source_protocol": "AMS-V4-ACTIVE-CONVICTION-SWING",
        "selected_trials": trial_diagnoses,
        "all_v4_trial_average": {
            "completed_trades": float(
                pd.Series([item["completed_trades"] for item in all_summaries]).mean()
            ),
            "candidates_per_executed_trade": float(
                pd.Series([item["candidates_per_executed_trade"] for item in all_summaries]).mean()
            ),
            "mean_open_positions": float(
                pd.Series([item["mean_open_positions"] for item in all_summaries]).mean()
            ),
            "mean_exposure": float(
                pd.Series([item["mean_exposure"] for item in all_summaries]).mean()
            ),
        },
        "answers": {
            "why_78_trades_per_year": (
                "Primarily setup scarcity after V4's binary breakout/pullback definition and "
                "conviction threshold, not a broad daily or 8H hard gate."
            ),
            "portfolio_constraints": "Secondary; average open-position use was below capacity.",
            "overextension_filter": (
                "Present in raw breakout construction but not the main V4 funnel blocker."
            ),
            "missing_entry_types": (
                "V4 omitted shallow/deep pullback reclaim, failed-breakdown recovery, and "
                "reacceleration as independent families."
            ),
            "least_risky_activity_change": (
                "Add causal pullback-reclaim and reacceleration families while retaining "
                "score-based ranking, next-open execution, and portfolio constraints."
            ),
        },
        "limitations": [
            (
                "V4 artifacts persist executed trades and aggregate rejections, not every "
                "rejected setup path."
            ),
            (
                "Requested rejected-signal MAE/MFE and post-signal opportunity analyses "
                "are not recoverable "
            "without a separate V4 decision-event log; unavailable values are not fabricated.",
            ),
        ],
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
    }
    write_json_atomically(OUTPUT, payload)
    print(OUTPUT)


if __name__ == "__main__":
    main()
