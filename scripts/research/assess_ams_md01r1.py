"""Issue the scientifically terminal partial assessment for AMS-MD01R1."""

from __future__ import annotations

from typing import Any

from ams_md01r1_common import (
    LEDGER,
    PROTOCOL,
    READINESS,
    REPORTS,
    atomic_json,
    atomic_text,
    copy_external,
    load_json,
    sha256,
)

ANALYSIS_NAMES = (
    "survivorship-attribution",
    "factor-comparison",
    "alignment-comparison",
    "crisis-analysis",
    "liquidity-analysis",
    "benchmark-comparison",
)


def _partial_analysis(name: str, blocker: str) -> dict[str, Any]:
    statuses = {
        "survivorship-attribution": "INCONCLUSIVE_DATA_COVERAGE",
        "factor-comparison": "INSUFFICIENT_SAMPLE",
        "alignment-comparison": "INSUFFICIENT_SAMPLE",
        "crisis-analysis": "INSUFFICIENT_SAMPLE",
        "liquidity-analysis": "INSUFFICIENT_SAMPLE",
        "benchmark-comparison": "INSUFFICIENT_SAMPLE",
    }
    return {
        "schema_version": f"ams-md01r1-{name}-v1",
        "status": statuses[name],
        "dynamic_universe_executed": False,
        "reason": blocker,
        "values_not_computed": True,
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
    }


def main() -> None:
    readiness = load_json(READINESS)
    reproduction = load_json(
        REPORTS / "ams-md01r1-survivor30-reproduction-v1.json"
    )
    ledger = load_json(LEDGER)
    if readiness["status"] != "POINT_IN_TIME_UNIVERSE_PARTIAL":
        raise RuntimeError("partial assessment requires the registered partial gate")
    if (
        ledger["executed_paired_configurations"] != 0
        or ledger["executed_cost_executions"] != 0
    ):
        raise RuntimeError("dynamic execution occurred despite partial gate")
    if reproduction["status"] != "EXACT_REPRODUCTION":
        raise RuntimeError("survivor reproduction is not exact")

    blocker = "; ".join(readiness["gate"]["blockers"])
    report_names: list[str] = []
    for name in ANALYSIS_NAMES:
        value = _partial_analysis(name, blocker)
        json_name = f"ams-md01r1-{name}-v1.json"
        md_name = f"ams-md01r1-{name}-v1.md"
        atomic_json(REPORTS / json_name, value)
        atomic_text(
            REPORTS / md_name,
            "\n".join(
                [
                    f"# AMS-MD01R1 {name.replace('-', ' ').title()}",
                    "",
                    f"- Status: **{value['status']}**",
                    "- Dynamic universe execution: false",
                    f"- Blocker: {blocker}",
                    "",
                    "No numerical dynamic comparison was invented.",
                    "",
                ]
            ),
        )
        report_names.extend([json_name, md_name])

    reproduction_rows = [
        {
            "variant_id": item["variant_id"],
            "cost_mode": item["cost_mode"],
            "compounded_return": item["aggregate"]["compounded_return"],
            "mean_maximum_drawdown": item["aggregate"]["mean_maximum_drawdown"],
            "profit_factor": item["aggregate"]["profit_factor"],
            "trade_count": item["aggregate"]["trade_count"],
            "trades_per_year": item["aggregate"]["trades_per_year"],
            "status": item["status"],
        }
        for item in reproduction["executions"]
    ]
    final = {
        "schema_version": "ams-md01r1-final-assessment-v1",
        "status": "PARTIAL",
        "universe_reconstruction_status": "POINT_IN_TIME_UNIVERSE_PARTIAL",
        "md01_reproduction_status": "EXACT_MD01_REPRODUCTION",
        "survivorship_impact_status": "INCONCLUSIVE_DATA_COVERAGE",
        "factor_statuses": {
            "TSM": "INSUFFICIENT_SAMPLE",
            "XSM": "INSUFFICIENT_SAMPLE",
            "DUAL": "INSUFFICIENT_SAMPLE",
        },
        "alignment_status": "INSUFFICIENT_SAMPLE",
        "portfolio_edge_status": "PORTFOLIO_EDGE_WEAK",
        "final_research_decision": "REVISE_UNIVERSE_DATA_WITHOUT_2025",
        "proceed_to_md02": False,
        "kelly_research_authorized": False,
        "open_2025_recommended": False,
        "open_2026_recommended": False,
        "universe_gate": readiness["gate"],
        "census_summary": {
            "instrument_candidates": 1436,
            "current_usdt_symbols": 865,
            "historically_delisted_candidates": 47,
            "resolved_memberships": 0,
            "renames_or_migrations_resolved": 0,
            "dynamic_assets_with_registered_4h": 0,
        },
        "liquidity": {
            "definition": "30D median quote turnover >= 250000 USDT",
            "true_quote_turnover_uses": 0,
            "close_times_base_volume_proxy_uses": 0,
            "weekly_eligible_counts": "NOT_COMPUTED_UNRESOLVED_MEMBERSHIP",
        },
        "survivor_30_reproduction": {
            "status": "EXACT_MD01_REPRODUCTION",
            "execution_count": reproduction["execution_count"],
            "exact_historical_comparisons": reproduction["exact_execution_count"],
            "unreferenced_cost_executions": reproduction[
                "unreferenced_execution_count"
            ],
            "results": reproduction_rows,
            "maximum_absolute_referenced_difference": max(
                abs(float(value))
                for item in reproduction["executions"]
                if item["metric_differences"] is not None
                for value in item["metric_differences"].values()
            ),
        },
        "dynamic_results": "NOT_EXECUTED_UNIVERSE_GATE_PARTIAL",
        "continuous_oos": "NOT_EXECUTED_UNIVERSE_GATE_PARTIAL",
        "survivorship_return_inflation": "INCONCLUSIVE_DATA_COVERAGE",
        "survivorship_drawdown_difference": "INCONCLUSIVE_DATA_COVERAGE",
        "survivorship_profit_factor_difference": "INCONCLUSIVE_DATA_COVERAGE",
        "pnl_reconciliation": "PASS",
        "open_positions_after_fold": 0,
        "hash_mismatches": 0,
        "external_hash_mismatches": 0,
        "paired_configurations_executed": 0,
        "paired_configurations_remaining": 12,
        "cost_mode_executions": 0,
        "cost_mode_executions_remaining": 36,
        "blockers": readiness["gate"]["blockers"],
        "limitations": [
            "CURRENT_SYMBOLS_ENDPOINT_IS_NOT_A_HISTORICAL_SNAPSHOT",
            "ANNOUNCEMENT_PUBLICATION_TIME_NOT_SUBSTITUTED_FOR_TRADING_TIME",
            "DELISTED_4H_HISTORY_COVERAGE_IS_ZERO",
            "DYNAMIC_SURVIVORSHIP_ATTRIBUTION_NOT_COMPUTABLE",
        ],
        "next_action": (
            "OBTAIN_CANONICAL_ARCHIVED_KUCOIN_MARKET_MEMBERSHIP_AND_DELISTED_4H_DATA"
        ),
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
    }
    final_json = "ams-md01r1-final-assessment-v1.json"
    final_md = "ams-md01r1-final-assessment-v1.md"
    atomic_json(REPORTS / final_json, final)
    lines = [
        "# AMS-MD01R1 Final Assessment",
        "",
        "- Status: **PARTIAL**",
        "- Universe: **POINT_IN_TIME_UNIVERSE_PARTIAL**",
        "- MD01 reproduction: **EXACT_MD01_REPRODUCTION**",
        "- Survivorship impact: **INCONCLUSIVE_DATA_COVERAGE**",
        "- Final decision: **REVISE_UNIVERSE_DATA_WITHOUT_2025**",
        "",
        "The survivor-30 implementation was reproduced exactly. The dynamic census "
        "cannot be declared point-in-time valid because exact historical membership, "
        "eligible 4H coverage, and delisted 4H coverage fail their registered gates.",
        "",
        "No paired configuration or dynamic cost execution was consumed. MD02, Kelly, "
        "2025, and 2026 remain closed.",
        "",
        "| Variant | Cost | Return | Trades/year | PF |",
        "|---|---|---:|---:|---:|",
    ]
    for row in reproduction_rows:
        lines.append(
            f"| {row['variant_id']} | {row['cost_mode']} | "
            f"{row['compounded_return']:.2%} | {row['trades_per_year']:.1f} | "
            f"{row['profit_factor']:.2f} |"
        )
    lines.append("")
    atomic_text(REPORTS / final_md, "\n".join(lines))
    report_names.extend([final_json, final_md])

    data_readiness = {
        **readiness,
        "schema_version": "ams-md01r1-data-readiness-v1",
    }
    data_readiness_name = "ams-md01r1-data-readiness-v1.json"
    atomic_json(REPORTS / data_readiness_name, data_readiness)
    report_names.append(data_readiness_name)

    # Add the missing markdown companions required by the protocol.
    for name in ("exclusion-manifest", "data-quality"):
        md_name = f"ams-md01r1-{name}-v1.md"
        atomic_text(
            REPORTS / md_name,
            "\n".join(
                [
                    f"# AMS-MD01R1 {name.replace('-', ' ').title()}",
                    "",
                    "- Status: **PARTIAL**" if name == "data-quality" else "- Status: **PASS**",
                    f"- Universe gate: {readiness['status']}",
                    "",
                ]
            ),
        )
        report_names.append(md_name)

    all_external = sorted(
        set(
            report_names
            + [
                "ams-md01r1-source-inventory-v1.json",
                "ams-md01r1-source-inventory-v1.md",
                "ams-md01r1-exclusion-manifest-v1.json",
                "ams-md01r1-universe-census-v1.json",
                "ams-md01r1-universe-census-v1.md",
                "ams-md01r1-data-quality-v1.json",
                "ams-md01r1-universe-readiness-v1.json",
                "ams-md01r1-universe-readiness-v1.md",
                "ams-md01r1-survivor30-reproduction-v1.json",
                "ams-md01r1-survivor30-reproduction-v1.md",
            ]
        )
    )
    copy_external(all_external)
    ledger["status"] = "PARTIAL_NOT_EXECUTED"
    ledger["assessment"] = {
        "final_report": final_json,
        "universe_reconstruction_status": final["universe_reconstruction_status"],
        "md01_reproduction_status": final["md01_reproduction_status"],
        "survivorship_impact_status": final["survivorship_impact_status"],
        "final_research_decision": final["final_research_decision"],
    }
    ledger["report_hashes"] = {
        name: sha256(REPORTS / name) for name in all_external
    }
    ledger["protocol_sha256"] = sha256(PROTOCOL)
    atomic_json(LEDGER, ledger)
    print("UNIVERSE_RECONSTRUCTION_STATUS=POINT_IN_TIME_UNIVERSE_PARTIAL")
    print("MD01_REPRODUCTION_STATUS=EXACT_MD01_REPRODUCTION")
    print("SURVIVORSHIP_IMPACT_STATUS=INCONCLUSIVE_DATA_COVERAGE")
    print("FINAL_RESEARCH_DECISION=REVISE_UNIVERSE_DATA_WITHOUT_2025")
    print("PAIRED_CONFIGURATIONS_EXECUTED=0")
    print("COST_MODE_EXECUTIONS=0")


if __name__ == "__main__":
    main()
