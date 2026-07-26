"""Extract the immutable executable specification for AMS V4 T12."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from ams_v5r1_native_common import atomic_json, atomic_text, sha256

ROOT = Path.cwd()
REPORTS = ROOT / "reports" / "research"
OUTSIDE = Path(r"C:\SIRAJ\Reports")


def item(field: str, value: Any, source: str, key: str, confidence: str = "HIGH") -> dict[str, Any]:
    return {
        "field": field,
        "value": value,
        "source_paths": [source],
        "source_lines_or_keys": [key],
        "confidence": confidence,
        "ambiguity": None,
    }


def build() -> dict[str, Any]:
    protocol = json.loads((REPORTS / "ams-v4-active-conviction-protocol-v1.json").read_text())
    ledger = json.loads((REPORTS / "ams-v4-experiment-ledger-v1.json").read_text())
    trial = json.loads((REPORTS / "ams-v4-ams-v4-t12-trial-v1.json").read_text())
    configuration = next(
        value
        for value in ledger["alpha_configurations"]
        if value["configuration_id"] == "AMS-V4-A06"
    )
    profile = next(
        value
        for value in ledger["portfolio_profiles"]
        if value["profile_id"] == "AMS-V4-PORTFOLIO-P02"
    )
    params = configuration["parameters"]
    fields = [
        item(
            "configuration_id",
            "AMS-V4-A06",
            "reports/research/ams-v4-experiment-ledger-v1.json",
            "alpha_configurations[A06]",
        ),
        item(
            "entry_family",
            params["entry_family"],
            "reports/research/ams-v4-experiment-ledger-v1.json",
            "A06.parameters.entry_family",
        ),
        item(
            "exit_model",
            params["exit_model"],
            "reports/research/ams-v4-experiment-ledger-v1.json",
            "A06.parameters.exit_model",
        ),
        item(
            "fibonacci_mode",
            params["fibonacci_mode"],
            "reports/research/ams-v4-experiment-ledger-v1.json",
            "A06.parameters.fibonacci_mode",
        ),
        item(
            "score_threshold",
            protocol["frozen_score_threshold"],
            "reports/research/ams-v4-active-conviction-protocol-v1.json",
            "frozen_score_threshold",
        ),
        item(
            "execution_rule",
            params["execution_rule"],
            "reports/research/ams-v4-active-conviction-protocol-v1.json",
            "execution_rule",
        ),
        item(
            "minimum_stop_atr",
            params["minimum_stop_atr"],
            "reports/research/ams-v4-experiment-ledger-v1.json",
            "A06.parameters.minimum_stop_atr",
        ),
        item(
            "typical_stop_atr",
            params["typical_stop_atr"],
            "reports/research/ams-v4-experiment-ledger-v1.json",
            "A06.parameters.typical_stop_atr",
        ),
        item(
            "maximum_stop_atr",
            params["maximum_stop_atr"],
            "reports/research/ams-v4-experiment-ledger-v1.json",
            "A06.parameters.maximum_stop_atr",
        ),
        item(
            "trailing_atr",
            params["trailing_atr"],
            "reports/research/ams-v4-experiment-ledger-v1.json",
            "A06.parameters.trailing_atr",
        ),
        item(
            "base_cost",
            params["base_transaction_cost"],
            "reports/research/ams-v4-experiment-ledger-v1.json",
            "A06.parameters.base_transaction_cost",
        ),
        item(
            "stress_cost",
            params["stress_transaction_cost"],
            "reports/research/ams-v4-experiment-ledger-v1.json",
            "A06.parameters.stress_transaction_cost",
        ),
        item(
            "portfolio_profile",
            profile,
            "reports/research/ams-v4-experiment-ledger-v1.json",
            "portfolio_profiles[P02]",
        ),
        item(
            "walk_forward",
            [fold["fold"] for fold in trial["fold_results"]],
            "reports/research/ams-v4-ams-v4-t12-trial-v1.json",
            "fold_results[].fold",
        ),
        item(
            "initial_capital",
            100000.0,
            "scripts/research/run_ams_v4_trial.py",
            "simulate_portfolio default",
        ),
        item(
            "candidate_ordering",
            "score_desc, relative_strength_desc, symbol_asc",
            "src/spotbot/research/ams_v4_active_conviction_swing.py",
            "simulate_portfolio candidates sort",
        ),
        item(
            "daily_logic",
            "BTC EMA50/EMA200, breadth, drawdown score and multiplier",
            "src/spotbot/research/ams_v4_active_conviction_swing.py",
            "build_execution_panel daily_btc",
        ),
        item(
            "eight_hour_logic",
            "EMA21/EMA55 trend, slope and BTC-relative 20-bar strength",
            "src/spotbot/research/ams_v4_active_conviction_swing.py",
            "build_execution_panel per-symbol features",
        ),
        item(
            "four_hour_logic",
            "Donchian breakout or EMA pullback reclaim",
            "src/spotbot/research/ams_v4_active_conviction_swing.py",
            "breakout/pullback",
        ),
        item(
            "fibonacci_contribution",
            "8, 4, 0, or -5 points; never hard reject",
            "src/spotbot/research/ams_v4_active_conviction_swing.py",
            "fib_score",
        ),
        item(
            "add_on",
            "one 30% legacy add after +1R pullback",
            "src/spotbot/research/ams_v4_active_conviction_swing.py",
            "pending_adds",
        ),
        item(
            "reentry",
            "one after stop and legacy two-bar condition",
            "src/spotbot/research/ams_v4_active_conviction_swing.py",
            "stopped/reentry_attempts",
        ),
    ]
    return {
        "schema_version": "ams-ed01-v4-t12-spec-extraction-v1",
        "status": "PASS",
        "protocol_id": "AMS-ED01-V4-T12-NATIVE-EDGE-VERIFICATION",
        "historical_trial_id": trial["trial_id"],
        "historical_trial_sha256": sha256(REPORTS / "ams-v4-ams-v4-t12-trial-v1.json"),
        "fields": fields,
        "spec_conflicts": [
            {
                "status": "SPEC_CONFLICT",
                "field": "add_on_quantity",
                "protocol_value": "25% to 35%",
                "executed_t12_value": "30% of legacy initial quantity",
                "resolution": (
                    "ED01 preserves executed T12 behavior for parity. Native corrected uses "
                    "its audited 25% policy only when add-on is enabled."
                ),
            },
            {
                "status": "SPEC_CONFLICT",
                "field": "threshold_selection",
                "protocol_value": "frozen 55",
                "executed_t12_value": "frozen 55; no train selection record",
                "resolution": "ED01 does not introduce threshold optimisation.",
            },
        ],
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
    }


def main() -> None:
    payload = build()
    json_path = REPORTS / "ams-ed01-v4-t12-spec-extraction-v1.json"
    md_path = REPORTS / "ams-ed01-v4-t12-spec-extraction-v1.md"
    atomic_json(json_path, payload)
    atomic_text(
        md_path,
        "# AMS ED01 V4 T12 executable specification\n\n"
        "- Historical cell: AMS-V4-T12 / A06 / P02.\n"
        "- Threshold: frozen 55.\n"
        "- Entry: signal close, next-bar open.\n"
        "- Conflicts: add-on sizing and absent train threshold-selection record are "
        "explicitly retained.\n"
        "- No 2025/2026 data accessed.\n",
    )
    OUTSIDE.mkdir(parents=True, exist_ok=True)
    shutil.copy2(json_path, OUTSIDE / json_path.name)
    shutil.copy2(md_path, OUTSIDE / md_path.name)
    print(json_path)


if __name__ == "__main__":
    main()
