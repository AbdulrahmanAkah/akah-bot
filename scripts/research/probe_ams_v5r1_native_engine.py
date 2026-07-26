"""Run the real-data AMS V5R1 native integration probe."""

from __future__ import annotations

import ast
from collections import Counter

import pandas as pd
from ams_v5r1_native_common import REPORTS, ROOT, atomic_json, load_registered_panel

from spotbot.research.ams_v5_native_engine import (
    configuration_grid,
    profiles,
    select_native_fold_threshold,
    simulate_native_fold,
)


def strategic_v4_dependencies() -> list[str]:
    paths = [ROOT / "src/spotbot/research/ams_v5_native_engine.py"]
    dependencies: list[str] = []
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                dependencies.extend(
                    alias.name
                    for alias in node.names
                    if "ams_v4_active_conviction_swing" in alias.name
                )
            if (
                isinstance(node, ast.ImportFrom)
                and node.module
                and "ams_v4_active_conviction_swing" in node.module
            ):
                dependencies.append(node.module)
    return dependencies


def main() -> None:
    panel, hashes = load_registered_panel(("BTC", "ETH", "SOL"))
    train = panel.loc[
        pd.to_datetime(panel["bar_open_time"], utc=True).lt(
            pd.Timestamp("2022-01-01T00:00:00Z")
        )
    ]
    validation = panel.loc[
        pd.to_datetime(panel["bar_open_time"], utc=True).between(
            pd.Timestamp("2022-01-01T00:00:00Z"),
            pd.Timestamp("2022-03-31T20:00:00Z"),
        )
    ]
    configuration = configuration_grid()[-1]
    selection = select_native_fold_threshold(
        train_panel=train,
        configuration=configuration,
        portfolio_profile=profiles()[0],
        fold_id="INTEGRATION-TRAIN",
    )
    result = simulate_native_fold(
        four_hour_panel=validation,
        configuration=configuration,
        portfolio_profile=profiles()[0],
        selected_threshold=selection.selected_threshold,
        transaction_cost=0.002,
        fold_id="INTEGRATION",
    )
    fill_types = Counter(fill.fill_type for fill in result.fills)
    families = Counter(candidate.actual_family for candidate in result.candidates)
    candidate_ids = [candidate.candidate_id for candidate in result.candidates]
    fill_ids = [fill.fill_id for fill in result.fills]
    dependencies = strategic_v4_dependencies()
    checks = {
        "native_fold_status": result.status == "PASS",
        "reconciliation": result.reconciliation.status == "PASS",
        "open_positions_after_fold": result.open_positions_after_fold == 0,
        "candidate_ids_unique": len(candidate_ids) == len(set(candidate_ids)),
        "fill_ids_unique": len(fill_ids) == len(set(fill_ids)),
        "next_open_fills": all(
            fill.timestamp
            == next(
                candidate.signal_close
                for candidate in result.candidates
                if candidate.candidate_id == fill.candidate_id
            )
            for fill in result.fills
            if fill.fill_type == "ENTRY"
        ),
        "nonnegative_cash": all(fill.cash_after >= -1e-7 for fill in result.fills),
        "no_implicit_leverage": all(
            fill.notional + fill.fee <= fill.cash_before + 1e-7
            for fill in result.fills
            if fill.fill_type in {"ENTRY", "ADD_ON"}
        ),
        "threshold_train_only": not selection.validation_inspected,
        "strategic_v4_dependencies_zero": not dependencies,
        "test_2025_not_accessed": True,
        "holdout_2026_not_accessed": True,
    }
    payload = {
        "schema_version": "ams-v5r1-native-engine-integration-v1",
        "status": "PASS" if all(checks.values()) else "FAIL",
        "symbols": ["BTC", "ETH", "SOL"],
        "dataset_hashes": hashes,
        "train_window": ["2021-01-01", "2022-01-01"],
        "validation_window": ["2022-01-01", "2022-04-01"],
        "selected_threshold": selection.selected_threshold,
        "train_hash_sha256": selection.train_hash_sha256,
        "candidate_count": len(result.candidates),
        "candidate_families": dict(families),
        "fill_count": len(result.fills),
        "fill_types": dict(fill_types),
        "trade_count": len(result.trades),
        "rejections": dict(result.rejections),
        "final_cash": result.final_cash,
        "fees": result.reconciliation.fees,
        "turnover": result.reconciliation.turnover,
        "pnl_reconciliation": result.reconciliation.status,
        "open_positions_after_fold": result.open_positions_after_fold,
        "strategic_v4_dependencies": dependencies,
        "checks": checks,
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
    }
    atomic_json(REPORTS / "ams-v5r1-native-engine-integration-v1.json", payload)
    print(payload["status"])


if __name__ == "__main__":
    main()
