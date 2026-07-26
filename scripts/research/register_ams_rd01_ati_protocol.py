"""Register the non-promotable Survivor-30 RD01/ATI diagnostic protocol."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from ams_md01r2_common import REPORTS, atomic_json, atomic_text, sha256

ROOT = Path(__file__).resolve().parents[2]
DATASET_REGISTRATION = REPORTS / "ams-v3-4h-dataset-registration-v1.json"


def _policy_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def main() -> None:
    registration = json.loads(DATASET_REGISTRATION.read_text(encoding="utf-8"))
    dataset_paths = {
        name: ROOT / record["path"]
        for name, record in registration["datasets"].items()
    }
    report_files = [
        path
        for path in REPORTS.glob("ams-md01r1-survivor30-*-reproduction-v1.json")
        if path.is_file()
    ]
    policies: dict[str, Any] = {
        "study_mode": [
            "SURVIVOR_DIAGNOSTIC",
            "NOT_POINT_IN_TIME",
            "NOT_PROMOTABLE",
            "UNIVERSE_PARTIAL",
        ],
        "timeframes": {
            "daily": "strategic regime; last closed UTC daily bar",
            "eight_hour": "transition confirmation; last closed UTC 8H bar",
            "four_hour": "execution timing; last closed UTC 4H bar",
            "effectiveness": "decision at close, effective next bar",
        },
        "regime_specifications": ["R1_CONSERVATIVE", "R2_BALANCED", "R3_PERSISTENT"],
        "sample_gate": {
            "minimum_pooled_trades": 20,
            "minimum_folds": 2,
            "minimum_trades_per_represented_fold": 5,
        },
        "negative_controls": [
            "BLOCK_SHUFFLE",
            "FREQUENCY_MATCHED_LABELS",
            "DELAY_1_BAR",
            "DELAY_2_BARS",
            "INVERTED_INTERPRETATION",
            "FUTURE_MUTATION",
            "DUMMY_FEATURE",
        ],
        "ablations": [f"A{index}" for index in range(10)],
        "overlays": ["O0", "O1", "O2", "O3"],
        "overlay_budget": {"configurations": 4, "cost_modes": 3, "maximum": 12},
        "ati_policies": ["ATI0", "ATI1", "ATI2", "ATI3"],
        "ati_invariants": [
            "NO_KELLY",
            "NO_RISK_MULTIPLIER_ABOVE_ONE",
            "NO_STOP_WIDENING",
            "NO_NEGATIVE_WEIGHT",
            "TOTAL_EXPOSURE_AT_MOST_ONE",
            "SHADOW_DOES_NOT_CHANGE_TRADES_OR_PNL",
        ],
    }
    protocol = {
        "schema_version": "ams-rd01-ati-v1-protocol",
        "status": "REGISTERED",
        "source_commit": "1f3029483311a1ecfb3e794bb4abdb46d70c2d01",
        "branch": "research/ams-rd01-survivor-diagnostics-ati-foundation-v1",
        "research_period": {
            "start": "2021-01-01T00:00:00Z",
            "end_exclusive": "2025-01-01T00:00:00Z",
        },
        "alpha_changed": False,
        "allowed": [
            "SURVIVOR_30_TAGGING",
            "DOMINANCE_DIAGNOSTICS",
            "BETA_AND_BENCHMARKS",
            "CONCENTRATION_AND_PLACEBOS",
            "ATI_SHADOW",
            "LIMITED_COUNTERFACTUAL_REPLAY_IF_GATES_PASS",
        ],
        "blocked": [
            "POINT_IN_TIME_CLAIM",
            "EDGE_PASS",
            "PRODUCTION_READY",
            "DYNAMIC_MD01_MATRIX",
            "MD02",
            "KELLY",
            "2025_DATA",
            "2026_DATA",
        ],
        "policies": policies,
        "policy_hashes": {
            name: _policy_hash(value) for name, value in sorted(policies.items())
        },
        "dynamic_md01_budget_consumed": 0,
        "cost_budget_consumed": 0,
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
    }
    inventory = {
        "schema_version": "ams-rd01-repository-inventory-v1",
        "status": "COMPLETE",
        "available_trade_level_data": (
            "REPRODUCIBLE_FROM_NATIVE_MD01_FOLD_ENGINE_NOT_PERSISTED_IN_R1_SUMMARY"
        ),
        "available_daily_portfolio_data": "EQUITY_CURVE_REPRODUCIBLE",
        "available_four_hour_asset_candles": True,
        "available_btc_data": True,
        "available_market_cap_data": False,
        "available_dominance_data": False,
        "available_turnover_data": True,
        "available_liquidity_proxies": ["4H_QUOTE_VOLUME_PROXY"],
        "available_trade_mfe_mae_inputs": True,
        "missing_fields": [
            "HISTORICAL_MARKET_CAP_SERIES",
            "HISTORICAL_STABLECOIN_SUPPLY_SERIES",
            "POINT_IN_TIME_TOP10_RANKINGS",
            "HISTORICAL_SPREAD_AND_ORDER_BOOK",
        ],
        "reusable_modules": [
            "spotbot.research.ams_md01_momentum",
            "scripts.research.ams_md01_common",
            "spotbot.research.ams_md01r2_phase_gate",
        ],
        "risk_of_duplicated_accounting": "LOW_IF_NATIVE_FOLD_RESULTS_ARE_REUSED",
        "dataset_hashes": {
            name: sha256(path) for name, path in sorted(dataset_paths.items())
        },
        "survivor_reproduction_report_count": len(report_files),
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
    }
    atomic_json(REPORTS / "ams-rd01-ati-v1-protocol.json", protocol)
    atomic_json(REPORTS / "ams-rd01-repository-inventory-v1.json", inventory)
    atomic_text(
        REPORTS / "ams-rd01-ati-v1-protocol.md",
        "\n".join(
            [
                "# AMS RD01 / ATI V1 Survivor Diagnostic Protocol",
                "",
                "- Status: **REGISTERED**",
                "- Universe: **SURVIVOR_DIAGNOSTIC / NOT_POINT_IN_TIME**",
                "- Promotion: **NOT_PROMOTABLE**",
                "- Alpha changed: **false**",
                "- Dynamic MD01 budget consumed: **0**",
                "- Cost budget consumed: **0**",
                "- 2025/2026: **locked**",
                "",
                "Dominance, beta, concentration, and ATI are diagnostic only. Missing "
                "market-cap series must fail closed; they may not be reconstructed "
                "from current supply or current Top-10 membership.",
                "",
            ]
        ),
    )
    print("PROTOCOL=REGISTERED")
    print("MODE=SURVIVOR_DIAGNOSTIC")
    print("DYNAMIC_MD01_BUDGET_CONSUMED=0")
    print("COST_BUDGET_CONSUMED=0")


if __name__ == "__main__":
    main()
