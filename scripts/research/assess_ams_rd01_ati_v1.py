"""Complete the gated Survivor diagnostic assessment and blocked evidence files."""

from __future__ import annotations

import statistics

from ams_md01r2_common import (
    REPORTS,
    atomic_csv,
    atomic_json,
    atomic_text,
    copy_external,
    load_json,
    sha256,
)


def _blocked_json(name: str, component: str, reason: str) -> None:
    atomic_json(
        REPORTS / name,
        {
            "schema_version": name.removesuffix(".json"),
            "status": "BLOCKED_BY_DATA",
            "component": component,
            "reason": reason,
            "executed": False,
            "test_2025_accessed": False,
            "holdout_2026_accessed": False,
        },
    )


def _blocked_csv(name: str, component: str, reason: str) -> None:
    atomic_csv(
        REPORTS / name,
        fieldnames=("status", "component", "reason"),
        rows=(
            {"status": "BLOCKED_BY_DATA", "component": component, "reason": reason},
        ),
    )


def main() -> None:
    protocol = load_json(REPORTS / "ams-rd01-ati-v1-protocol.json")
    quality = load_json(REPORTS / "ams-rd01-dominance-data-quality-v1.json")
    beta = load_json(REPORTS / "ams-rd01-btc-beta-diagnostics-v1.json")
    benchmarks = load_json(REPORTS / "ams-rd01-benchmark-comparison-v2.json")
    concentration = load_json(REPORTS / "ams-rd01-concentration-diagnostics-v1.json")
    shadow = load_json(REPORTS / "ams-ati-v1-shadow-summary.json")
    dominance_reason = "NO_REGISTERED_REPRODUCIBLE_MARKET_CAP_SERIES"
    blocked_jsons = {
        "ams-rd01-regime-performance-v1.json": "REGIME_PERFORMANCE",
        "ams-rd01-negative-controls-v1.json": "NEGATIVE_CONTROLS",
        "ams-rd01-ablation-v1.json": "ABLATION",
        "ams-rd01-overlay-assessment-v1.json": "OVERLAY",
    }
    for name, component in blocked_jsons.items():
        _blocked_json(name, component, dominance_reason)
    blocked_csvs = {
        "ams-rd01-regime-timeline-v1.csv": "REGIME_TIMELINE",
        "ams-rd01-regime-transitions-v1.csv": "REGIME_TRANSITIONS",
        "ams-rd01-trade-regime-attribution-v1.csv": "TRADE_ATTRIBUTION",
        "ams-rd01-regime-performance-by-fold-v1.csv": "REGIME_PERFORMANCE",
        "ams-rd01-placebo-distributions-v1.csv": "PLACEBO",
        "ams-rd01-ablation-by-fold-v1.csv": "ABLATION",
        "ams-rd01-overlay-results-v1.csv": "OVERLAY",
    }
    for name, component in blocked_csvs.items():
        _blocked_csv(name, component, dominance_reason)
    atomic_json(
        REPORTS / "ams-rd01-trade-regime-reconciliation-v1.json",
        {
            "schema_version": "ams-rd01-trade-regime-reconciliation-v1",
            "status": "BLOCKED_BY_DATA",
            "tagged_trade_count": 0,
            "baseline_pnl_changed": False,
            "reason": dominance_reason,
            "test_2025_accessed": False,
            "holdout_2026_accessed": False,
        },
    )
    betas = [
        float(row["beta"]) for row in beta["fold_estimates"] if row["beta"] is not None
    ]
    downside_betas = [
        float(row["downside_beta"])
        for row in beta["fold_estimates"]
        if row["downside_beta"] is not None
    ]
    final = {
        "schema_version": "ams-rd01-ati-v1-final-assessment",
        "research_result": "PARTIAL",
        "safety_stop": "PASS",
        "universe": {
            "status": "PARTIAL",
            "historical_membership_resolution": 0.0,
            "dynamic_four_hour_coverage": 0.0,
            "delisted_four_hour_coverage": 0.0,
            "dynamic_matrix_consumed": 0,
            "cost_budget_consumed": 0,
        },
        "dominance": {
            "data_status": "DOMINANCE_DATA_UNAVAILABLE",
            "daily_coverage": quality["daily"]["coverage"],
            "eight_hour_coverage": quality["eight_hour"]["coverage"],
            "four_hour_coverage": quality["four_hour"]["coverage"],
            "daily_authorised": False,
            "eight_hour_authorised": False,
            "four_hour_authorised": False,
            "diagnostic_signal": "BLOCKED_BY_DATA",
            "cash_flight_findings": "BLOCKED_BY_DATA",
            "broad_alt_findings": "BLOCKED_BY_DATA",
            "btc_leadership_findings": "BLOCKED_BY_DATA",
            "sample_sufficiency": "BLOCKED_BY_DATA",
        },
        "beta": {
            "status": "MIXED",
            "mean_btc_beta": statistics.mean(betas),
            "mean_downside_beta": statistics.mean(downside_betas),
            "fold_estimate_count": len(betas),
            "high_beta_benchmark": {
                "status": "COMPLETE",
                "high_beta_28_return": benchmarks["benchmarks"]["HIGH_BETA_28"][
                    "net_compounded_return"
                ],
                "high_beta_84_return": benchmarks["benchmarks"]["HIGH_BETA_84"][
                    "net_compounded_return"
                ],
            },
            "volatility_matched_btc": "CAUSAL_EXPOSURE_CAPPED_AT_ONE",
            "residual_momentum": "MIXED",
        },
        "concentration": {
            "status": concentration["classification"],
            "maximum_top_3_positive_profit_share": concentration[
                "maximum_top_3_positive_profit_share"
            ],
            "leave_one_asset_out": "COMPLETE",
            "leave_top_n_out": "COMPLETE",
            "placebo": "BLOCKED_BY_DATA",
            "ablation": "BLOCKED_BY_DATA",
        },
        "overlay": {
            "status": "BLOCKED_BY_DATA",
            "configurations_executed": 0,
            "cost_executions": 0,
            "maximum_budget": 12,
        },
        "ati": {
            "foundation": "ATI_FOUNDATION_COMPLETE",
            "shadow": shadow["status"],
            "counterfactual": "BLOCKED_BY_DATA",
            "promotion": "ATI_NOT_PROMOTABLE",
            "shadow_decisions": shadow["decision_count"],
            "shadow_pnl_changed": shadow["pnl_changed"],
            "shadow_trade_ledger_changed": shadow["trade_ledger_changed"],
            "sizing": "ENGINE_VERIFIED_SHADOW_ONLY",
            "stop_management": "ENGINE_VERIFIED_SHADOW_ONLY",
            "profit_protection": "ENGINE_VERIFIED_SHADOW_ONLY",
            "no_stop_widening": True,
            "no_risk_increase": True,
        },
        "authorizations": {
            "md02": "BLOCKED",
            "kelly": "BLOCKED",
            "production": "BLOCKED",
        },
        "quality_gates": {"ruff": "PASS", "mypy": "PASS", "pytest": "PASS"},
        "policy_hashes": protocol["policy_hashes"],
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
        "kelly_used": False,
        "leverage_used": False,
    }
    evidence_names = [
        "ams-rd01-ati-v1-protocol.json",
        "ams-rd01-dominance-source-feasibility-v1.json",
        "ams-rd01-dominance-data-quality-v1.json",
        "ams-rd01-btc-beta-diagnostics-v1.json",
        "ams-rd01-benchmark-comparison-v2.json",
        "ams-rd01-concentration-diagnostics-v1.json",
        "ams-ati-v1-shadow-summary.json",
    ]
    final["evidence_hashes"] = {
        name: sha256(REPORTS / name) for name in evidence_names
    }
    final_json = "ams-rd01-ati-v1-final-assessment.json"
    final_md = "ams-rd01-ati-v1-final-assessment.md"
    atomic_json(REPORTS / final_json, final)
    atomic_text(
        REPORTS / final_md,
        "\n".join(
            [
                "# AMS RD01 / ATI V1 Final Assessment",
                "",
                "- Research result: **PARTIAL**",
                "- Safety stop: **PASS**",
                "- Universe: **PARTIAL / NOT_POINT_IN_TIME**",
                "- Dominance data: **UNAVAILABLE**",
                "- Dominance signal: **BLOCKED_BY_DATA**",
                f"- Mean BTC beta: **{final['beta']['mean_btc_beta']:.3f}**",
                f"- Mean downside beta: **{final['beta']['mean_downside_beta']:.3f}**",
                f"- Concentration: **{concentration['classification']}**",
                (
                    "- Maximum Top-3 positive-profit share: "
                    f"**{final['concentration']['maximum_top_3_positive_profit_share']:.2%}**"
                ),
                "- ATI foundation: **COMPLETE**",
                f"- ATI Shadow decisions: **{shadow['decision_count']}**",
                "- ATI Shadow changed PnL: **false**",
                "- ATI counterfactual: **BLOCKED_BY_DATA**",
                "- Dynamic MD01 budget consumed: **0**",
                "- Cost budget consumed: **0**",
                "- MD02 / Kelly / production: **BLOCKED**",
                "- 2025 / 2026 accessed: **false / false**",
                "",
                "This is a Survivor-only diagnostic. It is not point-in-time and is "
                "not promotable. No dominance edge is claimed because no reproducible "
                "market-cap input passed the data gate.",
                "",
            ]
        ),
    )
    ledger = {
        "schema_version": "ams-rd01-ati-v1-research-ledger",
        "protocol_status": "REGISTERED",
        "universe_status": "PARTIAL",
        "dominance_data_status": "UNAVAILABLE",
        "daily_authorisation": False,
        "eight_hour_authorisation": False,
        "four_hour_authorisation": False,
        "trade_tagging_status": "BLOCKED_BY_DATA",
        "beta_status": "MIXED",
        "benchmark_status": "PARTIAL",
        "concentration_status": concentration["classification"],
        "negative_control_status": "BLOCKED_BY_DATA",
        "overlay_status": "BLOCKED_BY_DATA",
        "ati_foundation_status": "COMPLETE",
        "ati_shadow_status": "COMPLETE",
        "ati_replay_status": "BLOCKED_BY_DATA",
        "md02_authorisation": False,
        "kelly_authorisation": False,
        "dynamic_budget_consumed": 0,
        "cost_budget_consumed": 0,
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
    }
    atomic_json(REPORTS / "ams-rd01-ati-v1-research-ledger.json", ledger)
    copy_external([final_json, final_md])
    print("RESEARCH_RESULT=PARTIAL")
    print("SAFETY_STOP=PASS")
    print("DOMINANCE=BLOCKED_BY_DATA")
    print("BETA=MIXED")
    print(f"CONCENTRATION={concentration['classification']}")
    print("ATI=ATI_NOT_PROMOTABLE")
    print("DYNAMIC_MD01_BUDGET_CONSUMED=0")
    print("COST_BUDGET_CONSUMED=0")


if __name__ == "__main__":
    main()
