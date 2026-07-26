"""Run one registered AMS V4 trial with atomic ledger accounting.

The command deliberately executes both registered transaction-cost regimes for
one alpha/profile cell.  It never reads bars owned by 2025 or later.
"""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pandas as pd

from spotbot.research.ams_v4_active_conviction_swing import (
    SimulationResult,
    assert_research_boundary,
    build_execution_panel,
    file_sha256,
    metrics,
    portfolio_profiles,
    simulate_portfolio,
    specification,
)

ROOT = Path.cwd()
REPORTS = ROOT / "reports/research"
LEDGER_PATH = REPORTS / "ams-v4-experiment-ledger-v1.json"
REGISTRATION_PATH = REPORTS / "ams-v3-4h-dataset-registration-v1.json"

FOLDS = (
    ("AMS-V4-WF01", "2021-01-01T00:00:00Z", "2022-01-01T00:00:00Z", "2023-01-01T00:00:00Z"),
    ("AMS-V4-WF02", "2021-01-01T00:00:00Z", "2023-01-01T00:00:00Z", "2024-01-01T00:00:00Z"),
    ("AMS-V4-WF03", "2021-01-01T00:00:00Z", "2024-01-01T00:00:00Z", "2025-01-01T00:00:00Z"),
)


def load_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"Expected JSON object: {path}")
    return payload


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


def load_panel() -> pd.DataFrame:
    registration = load_object(REGISTRATION_PATH)
    datasets = registration["datasets"]
    loaded: dict[str, pd.DataFrame] = {}
    for name in ("four_hour", "availability"):
        record = datasets[name]
        path = ROOT / str(record["path"])
        if file_sha256(path) != str(record["file_sha256"]):
            raise RuntimeError(f"Dataset hash mismatch: {path}")
        loaded[name] = pd.read_parquet(path)
    assert_research_boundary(loaded["four_hour"])
    panel = build_execution_panel(loaded["four_hour"], loaded["availability"])
    assert_research_boundary(panel)
    return panel


def _trade_json(result: SimulationResult) -> list[dict[str, Any]]:
    return [
        {
            **asdict(trade),
            "entry_time": trade.entry_time.isoformat(),
            "exit_time": trade.exit_time.isoformat(),
        }
        for trade in result.trades
    ]


def _fold_result(
    panel: pd.DataFrame, configuration: dict[str, Any], profile: Any
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    timestamps = pd.to_datetime(panel["bar_open_time"], utc=True, errors="raise")
    for fold_id, train_start, validation_start, validation_end in FOLDS:
        start = pd.Timestamp(validation_start)
        end = pd.Timestamp(validation_end)
        validation = panel.loc[timestamps.ge(start) & timestamps.lt(end)].copy()
        assert_research_boundary(validation)
        regimes: dict[str, Any] = {}
        for cost_mode in ("BASE", "STRESS"):
            result = simulate_portfolio(
                validation, specification(configuration, profile, cost_mode=cost_mode)
            )
            regimes[cost_mode.lower()] = {"metrics": metrics(result), "trades": _trade_json(result)}
        results.append(
            {
                "fold": {
                    "fold_id": fold_id,
                    "train_start": train_start,
                    "validation_start": validation_start,
                    "validation_end_exclusive": validation_end,
                    "train_usage": "WARM_UP_AND_CAUSAL_FEATURE_HISTORY_ONLY",
                },
                "base": regimes["base"],
                "stress": regimes["stress"],
            }
        )
    return results


def _aggregate(folds: list[dict[str, Any]], regime: str) -> dict[str, Any]:
    values = [item[regime]["metrics"] for item in folds]
    returns = [float(value["net_return"]) for value in values]
    drawdowns = [float(value["maximum_drawdown"]) for value in values]
    trade_count = sum(int(value["trade_count"]) for value in values)
    return {
        "aggregate_compounded_return": float(
            pd.Series([1.0 + value for value in returns]).prod() - 1.0
        ),
        "mean_fold_return": float(pd.Series(returns).mean()),
        "worst_fold_return": min(returns),
        "worst_fold_drawdown": max(drawdowns),
        "median_fold_return": float(pd.Series(returns).median()),
        "positive_fold_ratio": sum(value > 0.0 for value in returns) / len(returns),
        "total_trade_count": trade_count,
        "mean_trades_per_year": float(
            pd.Series([value["trades_per_year"] for value in values]).mean()
        ),
        "mean_calmar": float(
            pd.Series([value["calmar"] for value in values if value["calmar"] is not None]).mean()
        ),
        "mean_profit_factor": float(
            pd.Series(
                [value["profit_factor"] for value in values if value["profit_factor"] is not None]
            ).mean()
        ),
    }


def run_trial(
    configuration_id: str, portfolio_profile_id: str, *, panel: pd.DataFrame | None = None
) -> Path:
    ledger = load_object(LEDGER_PATH)
    accounting = ledger["trial_accounting"]
    if int(accounting["remaining_trials"]) <= 0:
        raise RuntimeError("No authorized AMS V4 trials remain.")
    trial = next(
        (
            item
            for item in ledger["trial_plan"]
            if item["configuration_id"] == configuration_id
            and item["portfolio_profile_id"] == portfolio_profile_id
        ),
        None,
    )
    if trial is None or trial["trial_status"] != "REGISTERED_NOT_EXECUTED":
        raise RuntimeError("Trial is not registered and pending execution.")
    configuration = next(
        item
        for item in ledger["alpha_configurations"]
        if item["configuration_id"] == configuration_id
    )
    profile = next(item for item in portfolio_profiles() if item.profile_id == portfolio_profile_id)
    execution_panel = panel if panel is not None else load_panel()
    assert_research_boundary(execution_panel)
    folds = _fold_result(execution_panel, configuration, profile)
    report = {
        "schema_version": "ams-v4-trial-v1",
        "protocol_id": ledger["protocol_id"],
        "trial_id": trial["trial_id"],
        "configuration_id": configuration_id,
        "portfolio_profile_id": portfolio_profile_id,
        "status": "EXECUTED",
        "cost_modes": ["BASE", "STRESS"],
        "fold_results": folds,
        "aggregate": {"base": _aggregate(folds, "base"), "stress": _aggregate(folds, "stress")},
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
    }
    report_path = REPORTS / f"ams-v4-{trial['trial_id'].lower()}-trial-v1.json"
    write_json_atomically(report_path, report)
    report_hash = file_sha256(report_path)
    if file_sha256(report_path) != report_hash:
        raise RuntimeError("Trial report hash verification failed.")
    trial["trial_status"] = "EXECUTED"
    trial["report_path"] = str(report_path.relative_to(ROOT)).replace("\\", "/")
    trial["report_sha256"] = report_hash
    accounting["executed_trials"] = int(accounting["executed_trials"]) + 1
    accounting["remaining_trials"] = int(accounting["remaining_trials"]) - 1
    if int(accounting["executed_trials"]) + int(accounting["remaining_trials"]) != int(
        accounting["authorized_trials"]
    ):
        raise RuntimeError("Trial accounting invariant failed.")
    write_json_atomically(LEDGER_PATH, ledger)
    return report_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--configuration-id", required=True)
    parser.add_argument("--portfolio-profile-id", required=True)
    parser.add_argument("--cost-mode", default="BOTH", choices=("BOTH", "BASE", "STRESS"))
    args = parser.parse_args()
    if args.cost_mode != "BOTH":
        raise RuntimeError("Registered trial accounting requires BASE and STRESS together.")
    print(run_trial(args.configuration_id, args.portfolio_profile_id))


if __name__ == "__main__":
    main()
