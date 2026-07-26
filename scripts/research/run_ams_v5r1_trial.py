"""Execute and atomically record one registered AMS V5R1 native trial."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pandas as pd
from ams_v5r1_native_common import (
    REPORTS,
    atomic_json,
    load_registered_panel,
    metrics,
    parameters_from_record,
    profile_from_record,
    serialize_threshold,
    sha256,
)

from spotbot.research.ams_v5_native_engine import (
    result_as_json,
    select_native_fold_threshold,
    simulate_native_fold,
)

LEDGER = REPORTS / "ams-v5r1-experiment-ledger-v1.json"
FOLDS = (
    (
        "AMS-V5R1-WF01",
        "2021-01-01T00:00:00Z",
        "2022-01-01T00:00:00Z",
        "2023-01-01T00:00:00Z",
    ),
    (
        "AMS-V5R1-WF02",
        "2021-01-01T00:00:00Z",
        "2023-01-01T00:00:00Z",
        "2024-01-01T00:00:00Z",
    ),
    (
        "AMS-V5R1-WF03",
        "2021-01-01T00:00:00Z",
        "2024-01-01T00:00:00Z",
        "2025-01-01T00:00:00Z",
    ),
)


def _aggregate(folds: list[dict[str, Any]], mode: str) -> dict[str, Any]:
    values = [fold[mode]["metrics"] for fold in folds]
    returns = [float(item["net_return"]) for item in values]
    valid_calmar = [float(item["calmar"]) for item in values if item["calmar"] is not None]
    return {
        "aggregate_compounded_return": float(
            pd.Series([1 + value for value in returns]).prod() - 1
        ),
        "mean_fold_return": float(pd.Series(returns).mean()),
        "worst_fold_return": min(returns),
        "positive_fold_ratio": sum(value > 0 for value in returns) / len(returns),
        "total_trade_count": sum(int(item["trade_count"]) for item in values),
        "mean_trades_per_year": float(
            pd.Series([item["trades_per_year"] for item in values]).mean()
        ),
        "mean_maximum_drawdown": float(
            pd.Series([item["maximum_drawdown"] for item in values]).mean()
        ),
        "worst_maximum_drawdown": max(float(item["maximum_drawdown"]) for item in values),
        "mean_calmar": float(pd.Series(valid_calmar).mean()) if valid_calmar else None,
        "mean_profit_factor": float(
            pd.Series([item["profit_factor"] for item in values]).mean()
        ),
        "mean_win_rate": float(pd.Series([item["win_rate"] for item in values]).mean()),
        "mean_expectancy": float(pd.Series([item["expectancy"] for item in values]).mean()),
        "mean_mfe_capture": float(
            pd.Series([item["mfe_capture_ratio"] for item in values]).mean()
        ),
        "total_add_ons": sum(int(item["add_on_count"]) for item in values),
        "total_reentries": sum(int(item["reentry_count"]) for item in values),
    }


def run_trial(
    configuration_id: str,
    portfolio_profile_id: str,
    *,
    panel: pd.DataFrame | None = None,
) -> Path:
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    accounting = ledger["trial_accounting"]
    trial = next(
        item
        for item in ledger["trial_plan"]
        if item["configuration_id"] == configuration_id
        and item["portfolio_profile_id"] == portfolio_profile_id
    )
    if trial["trial_status"] != "REGISTERED_NOT_EXECUTED":
        raise RuntimeError("trial is not eligible or was already executed")
    if accounting["remaining_trials"] <= 0:
        raise RuntimeError("V5R1 trial budget exhausted")
    configuration_record = next(
        item
        for item in ledger["alpha_configurations"]
        if item["configuration_id"] == configuration_id
    )
    profile_record = next(
        item
        for item in ledger["portfolio_profiles"]
        if item["profile_id"] == portfolio_profile_id
    )
    configuration = parameters_from_record(configuration_record)
    profile = profile_from_record(profile_record)
    full_panel = panel if panel is not None else load_registered_panel()[0]
    opens = pd.to_datetime(full_panel["bar_open_time"], utc=True)
    fold_records: list[dict[str, Any]] = []
    for fold_id, train_start, validation_start, validation_end in FOLDS:
        train = full_panel.loc[
            opens.ge(pd.Timestamp(train_start)) & opens.lt(pd.Timestamp(validation_start))
        ]
        validation = full_panel.loc[
            opens.ge(pd.Timestamp(validation_start)) & opens.lt(pd.Timestamp(validation_end))
        ]
        selection = select_native_fold_threshold(
            train_panel=train,
            configuration=configuration,
            portfolio_profile=profile,
            fold_id=f"{fold_id}-TRAIN",
        )
        regimes: dict[str, Any] = {}
        for mode, cost in (("base", 0.002), ("stress", 0.004)):
            result = simulate_native_fold(
                four_hour_panel=validation,
                configuration=configuration,
                portfolio_profile=profile,
                selected_threshold=selection.selected_threshold,
                transaction_cost=cost,
                fold_id=f"{trial['trial_id']}-{fold_id}-{mode.upper()}",
            )
            if result.status != "PASS" or result.reconciliation.status != "PASS":
                raise RuntimeError(f"invalid native Fold: {fold_id} {mode}")
            serialized = result_as_json(result)
            regimes[mode] = {
                "metrics": metrics(result),
                "candidate_ledger": serialized["candidates"],
                "scheduled_entry_ledger": serialized["scheduled_entries"],
                "fill_ledger": serialized["fills"],
                "trade_ledger": serialized["trades"],
                "reconciliation": serialized["reconciliation"],
            }
        fold_records.append(
            {
                "fold": {
                    "fold_id": fold_id,
                    "train_start": train_start,
                    "validation_start": validation_start,
                    "validation_end_exclusive": validation_end,
                    "threshold_selection": serialize_threshold(selection),
                },
                **regimes,
            }
        )
    report = {
        "schema_version": "ams-v5r1-native-trial-v1",
        "trial_id": trial["trial_id"],
        "configuration_id": configuration_id,
        "portfolio_profile_id": portfolio_profile_id,
        "configuration": asdict(configuration),
        "portfolio_profile": asdict(profile),
        "status": "EXECUTED",
        "fold_results": fold_records,
        "aggregate": {
            "base": _aggregate(fold_records, "base"),
            "stress": _aggregate(fold_records, "stress"),
        },
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
    }
    path = REPORTS / f"ams-v5r1-{trial['trial_id'].lower()}-trial-v1.json"
    atomic_json(path, report)
    report_hash = sha256(path)
    if sha256(path) != report_hash:
        raise RuntimeError("trial report hash verification failed")
    trial.update(
        {
            "trial_status": "EXECUTED",
            "report_path": str(path.relative_to(REPORTS.parent.parent)).replace("\\", "/"),
            "report_sha256": report_hash,
        }
    )
    accounting["executed_trials"] += 1
    accounting["remaining_trials"] -= 1
    if accounting["executed_trials"] + accounting["remaining_trials"] != 24:
        raise RuntimeError("trial accounting invariant failed")
    atomic_json(LEDGER, ledger)
    return path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--configuration-id", required=True)
    parser.add_argument("--portfolio-profile-id", required=True)
    parser.add_argument("--cost-mode", choices=("BOTH", "BASE", "STRESS"), default="BOTH")
    arguments = parser.parse_args()
    if arguments.cost_mode != "BOTH":
        raise RuntimeError("registered trials require both Base and Stress")
    print(run_trial(arguments.configuration_id, arguments.portfolio_profile_id))


if __name__ == "__main__":
    main()
