"""Audit and pre-register the immutable AMS-MD01 study before variant execution."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

import numpy as np
import pandas as pd
from ams_md01_common import (
    REPORTS,
    atomic_json,
    atomic_text,
    copy_external,
    load_registered_data,
    sha256,
    write_registered_state,
)

from spotbot.research.ams_md01_momentum import (
    CLUSTER_CORRELATION,
    CLUSTER_LOOKBACK_DAYS,
    EMA_FAST,
    EMA_SLOW,
    FOLDS,
    MAX_CLUSTER_POSITIONS,
    OVEREXTENSION_ATR,
    RESEARCH_LOCK,
    VARIANTS,
    build_trend_features,
    causal_cluster_snapshot,
    eligible_universe_at,
    weekly_rebalance_times,
)


def _source_evidence() -> dict[str, Any]:
    return {
        "registered_policy": "POINT_IN_TIME_KUCOIN_SPOT_ELIGIBILITY",
        "fixed_symbol_list_source": [
            "scripts/research/run_ams_v1_h01.py",
            "reports/research/ams-v3-4h-dataset-manifest-v1.json",
        ],
        "list_creation_time": "2026-07-25 registration artifact",
        "future_independent_selection_proven": False,
        "delisted_or_failed_assets_outside_fixed_list_represented": False,
        "point_in_time_venue_availability": True,
        "point_in_time_liquidity_filter_available": False,
        "market_cap_filter_used": False,
        "conclusion": "SURVIVORSHIP_RISK",
        "research_label": "PROVISIONAL_UNDER_SURVIVORSHIP_RISK",
        "reason": (
            "Venue eligibility is causal inside the registered thirty-symbol list, "
            "but the later-created fixed membership cannot be proved independent of "
            "2021-2024 survival and omits an auditable historical delisting universe."
        ),
    }


def _year_counts(records: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    grouped: dict[str, list[int]] = defaultdict(list)
    for record in records:
        grouped[str(pd.Timestamp(record["timestamp"]).year)].append(
            int(record["final_rankable_count"])
        )
    return {
        year: {
            "minimum": min(values),
            "maximum": max(values),
            "mean": float(np.mean(values)),
            "median": float(np.median(values)),
        }
        for year, values in sorted(grouped.items())
    }


def main() -> None:
    frames, hashes = load_registered_data()
    daily = build_trend_features(frames["daily"])
    eight = build_trend_features(frames["eight_hour"])
    four = build_trend_features(frames["four_hour"], four_hour=True)
    timestamps = weekly_rebalance_times(
        pd.Timestamp("2021-01-01T00:00:00Z"),
        RESEARCH_LOCK,
    )
    audit_rows: list[dict[str, Any]] = []
    correlation_dispersions: list[float] = []
    for timestamp in timestamps:
        ranked, record = eligible_universe_at(
            timestamp=timestamp,
            horizon_days=84,
            daily=daily,
            eight_hour=eight,
            four_hour=four,
            availability=frames["availability"],
        )
        _, start, end, dispersion = causal_cluster_snapshot(
            daily,
            timestamp=timestamp,
            symbols=ranked["symbol"].astype(str).tolist(),
        )
        record["cluster_window_start"] = start.isoformat()
        record["cluster_window_end"] = end.isoformat()
        record["correlation_dispersion"] = dispersion
        audit_rows.append(record)
        correlation_dispersions.append(dispersion)
    source = _source_evidence()
    report: dict[str, Any] = {
        "schema_version": "ams-md01-universe-audit-v1",
        "status": "PASS_WITH_LIMITATION",
        "universe_status": source["conclusion"],
        "research_label": source["research_label"],
        "source_audit": source,
        "registered_symbol_count": int(frames["availability"]["symbol"].nunique()),
        "availability_complete": bool(
            frames["availability"][["tradable_from", "tradable_until"]].notna().all().all()
        ),
        "dynamic_eligibility": audit_rows,
        "eligible_count_by_year": _year_counts(audit_rows),
        "rank_dispersion": {
            "mean": float(np.mean([row["rank_dispersion"] for row in audit_rows])),
            "median": float(np.median([row["rank_dispersion"] for row in audit_rows])),
            "minimum": float(min(row["rank_dispersion"] for row in audit_rows)),
            "maximum": float(max(row["rank_dispersion"] for row in audit_rows)),
        },
        "correlation_dispersion": {
            "mean": float(np.mean(correlation_dispersions)),
            "median": float(np.median(correlation_dispersions)),
            "minimum": float(min(correlation_dispersions)),
            "maximum": float(max(correlation_dispersions)),
        },
        "dataset_hashes": hashes,
        "known_registration_artifact_defect": (
            "The AMS-V3 registration JSON contains nanosecond-like 1970 values in "
            "some universe_first_timestamp fields; MD01 derives eligibility directly "
            "from verified bars and availability instead of those defective fields."
        ),
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
    }
    protocol: dict[str, Any] = {
        "schema_version": "ams-md01-protocol-v1",
        "protocol_id": "AMS-MD01-MOMENTUM-UNIVERSE-GROSS-EDGE",
        "study_type": "MOMENTUM_GROSS_EDGE_DISCOVERY",
        "new_strategy_school": True,
        "parameter_optimisation": False,
        "universe_status": source["conclusion"],
        "research_label": source["research_label"],
        "market_contract": {
            "market_type": "SPOT",
            "direction": "LONG_ONLY",
            "leverage": False,
            "borrowing": False,
            "negative_cash": False,
        },
        "research_boundary": {
            "bar_open_time": "< 2025-01-01T00:00:00Z",
            "bar_close_time": "<= 2025-01-01T00:00:00Z",
        },
        "trend_alignment": {
            "ema_fast": EMA_FAST,
            "ema_slow": EMA_SLOW,
            "ema_slow_slope_bars": 5,
            "recovery_ema_slope_bars": 3,
            "reclaim_window_bars": 3,
            "breakout_window_bars": 3,
            "atr_period": 14,
            "overextension_atr": OVEREXTENSION_ATR,
            "strength_multipliers": {
                "FULL": 1.0,
                "MEDIUM": 0.67,
                "FOUR_HOUR_ONLY": 0.33,
                "NONE": 0.0,
            },
        },
        "crisis": {
            "definition": (
                "BTC daily DOWNTREND and close at least 20% below causal "
                "trailing-84-completed-bar high"
            ),
            "blocks_new_entry_and_rotation": True,
            "forces_intrabar_exit": False,
        },
        "momentum_horizons_calendar_days": [28, 84],
        "rebalance": {"weekday": "MONDAY", "time": "00:00:00Z", "frequency": "WEEKLY"},
        "clusters": {
            "returns": "DAILY",
            "causal_lookback_days": CLUSTER_LOOKBACK_DAYS,
            "correlation_threshold": CLUSTER_CORRELATION,
            "maximum_positions_per_cluster": MAX_CLUSTER_POSITIONS,
        },
        "allocation": {
            "TSM": {"maximum_positions": 5, "maximum_weight": 0.20},
            "XSM": {"maximum_positions": 3, "base_weight": 0.25},
            "DUAL": {"maximum_positions": 3, "base_weight": 0.25},
            "renormalise": False,
        },
        "execution": {
            "entry": "4H signal close then next 4H open",
            "exits": [
                "REBALANCE_EXIT",
                "VENUE_EXIT",
                "END_OF_FOLD_EXIT",
            ],
            "tactical_stop": False,
            "trailing": False,
            "add_on": False,
            "mid_week_reentry": False,
            "natural_reselection_cooldown_days": 7,
        },
        "folds": [
            {"fold_id": fold, "validation_start": start, "validation_end": end}
            for fold, start, end in FOLDS
        ],
        "variants": [
            {
                "variant_id": identity,
                "school": values[0],
                "horizon_days": values[1],
            }
            for identity, values in VARIANTS.items()
        ],
        "cost_modes": {"ZERO_COST": 0.0, "BASE_COST": 0.002, "STRESS_0_4_PERCENT": 0.004},
        "controls": ["FLAT_ALIGNMENT", "CRISIS_OFF"],
        "gross_edge_gate": {
            "positive_return": True,
            "minimum_positive_folds": 2,
            "minimum_profit_factor": 1.05,
            "positive_expectancy": True,
            "maximum_top_1_symbol_contribution": 0.60,
            "minimum_trade_count": 20,
        },
        "authorized_primary_variants": 6,
        "executed_primary_variants": 0,
        "remaining_primary_variants": 6,
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
    }
    ledger = {
        "schema_version": "ams-md01-experiment-ledger-v1",
        "protocol_id": protocol["protocol_id"],
        "trial_accounting": {
            "authorized_primary_variants": 6,
            "executed_primary_variants": 0,
            "remaining_primary_variants": 6,
        },
        "trial_plan": [
            {
                "variant_id": record["variant_id"],
                "school": record["school"],
                "horizon_days": record["horizon_days"],
                "status": "REGISTERED_NOT_EXECUTED",
            }
            for record in protocol["variants"]
        ],
        "dataset_hashes": hashes,
        "report_hashes": {},
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
    }
    readiness = {
        "schema_version": "ams-md01-data-readiness-v1",
        "status": "REGISTERED_NOT_EXECUTED",
        "universe_status": source["conclusion"],
        "dataset_hashes": hashes,
        "registered_symbol_count": int(frames["availability"]["symbol"].nunique()),
        "boundary_validation": "PASS",
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
    }
    audit_json = REPORTS / "ams-md01-universe-audit-v1.json"
    audit_markdown = REPORTS / "ams-md01-universe-audit-v1.md"
    atomic_json(audit_json, report)
    atomic_text(
        audit_markdown,
        "\n".join(
            [
                "# AMS-MD01 Universe Audit",
                "",
                f"- Status: **{report['universe_status']}**",
                f"- Research label: **{report['research_label']}**",
                f"- Registered symbols: {report['registered_symbol_count']}",
                "- Venue availability is point-in-time and complete.",
                "- The fixed thirty-symbol membership was registered later and cannot be "
                "proved independent of survivor knowledge.",
                "- No point-in-time liquidity series exists, so no liquidity filter was invented.",
                "",
                "Results are provisional and cannot establish a final cross-sectional edge.",
                "",
            ]
        ),
    )
    write_registered_state(protocol, ledger, readiness)
    ledger["report_hashes"] = {
        audit_json.name: sha256(audit_json),
        audit_markdown.name: sha256(audit_markdown),
    }
    write_registered_state(protocol, ledger, readiness)
    copy_external([audit_json.name, audit_markdown.name])
    print(f"UNIVERSE_STATUS={report['universe_status']}")
    print("REGISTERED_NOT_EXECUTED")
    print("PRIMARY_VARIANTS_EXECUTED=0")
    print("PRIMARY_VARIANTS_REMAINING=6")


if __name__ == "__main__":
    main()
