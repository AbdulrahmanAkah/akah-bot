"""Run artifact-level bounds when the MD01R2 point-in-time universe is unidentified."""

from __future__ import annotations

from typing import Any

from ams_md01r2_common import (
    BOUNDED,
    R1_REPRODUCTION,
    READINESS,
    REPORTS,
    atomic_csv,
    atomic_json,
    atomic_text,
    copy_external,
    load_json,
)

from spotbot.research.ams_md01r2_universe import (
    bounded_scenarios,
    classify_non_identification,
)


def main() -> None:
    readiness = load_json(READINESS)
    if readiness["status"] != "PARTIAL":
        raise RuntimeError("bounded analysis is authorised only when universe is PARTIAL")
    reproduction = load_json(R1_REPRODUCTION)
    records: list[dict[str, Any]] = []
    loo_rows: list[dict[str, Any]] = []
    top_rows: list[dict[str, Any]] = []
    cost_rows: list[dict[str, Any]] = []
    liquidity_rows: list[dict[str, Any]] = []
    for execution in reproduction["executions"]:
        scenarios = bounded_scenarios(execution)
        record = {
            "variant_id": execution["variant_id"],
            "cost_mode": execution["cost_mode"],
            "scenarios": scenarios,
        }
        records.append(record)
        for symbol, value in scenarios["LEAVE_ONE_ASSET_OUT"].items():
            loo_rows.append(
                {
                    "variant_id": execution["variant_id"],
                    "cost_mode": execution["cost_mode"],
                    "symbol": symbol,
                    "compounded_return": value,
                }
            )
        for scenario in ("TOP_1_CONTRIBUTOR_REMOVAL", "TOP_3_CONTRIBUTOR_REMOVAL"):
            top_rows.append(
                {
                    "variant_id": execution["variant_id"],
                    "cost_mode": execution["cost_mode"],
                    "scenario": scenario,
                    "compounded_return": scenarios[scenario],
                }
            )
        cost_rows.append(
            {
                "variant_id": execution["variant_id"],
                "cost_mode": execution["cost_mode"],
                "baseline_return": scenarios["BENIGN_MISSING_ASSETS"],
            }
        )
        liquidity_rows.append(
            {
                "variant_id": execution["variant_id"],
                "cost_mode": execution["cost_mode"],
                "extra_turnover_cost": 0.004,
                "compounded_return": scenarios["LIQUIDITY_DEGRADATION_STRESS"],
            }
        )
    judgment = classify_non_identification(records)
    report = {
        "schema_version": "ams-md01r2-bounded-sensitivity-v1",
        "status": "COMPLETE",
        "analysis_type": "BOUNDED_NON_IDENTIFICATION_ANALYSIS",
        "is_point_in_time_backtest": False,
        "judgment": judgment,
        "execution_count": len(records),
        "scenario_definitions": {
            "BENIGN_MISSING_ASSETS": "Recorded Survivor-30 artifact unchanged.",
            "CONSERVATIVE_DELISTING_STRESS": "Two percent capital shock per fold.",
            "ADVERSARIAL_DELISTING_STRESS": "Ten percent capital shock per fold.",
            "LIQUIDITY_DEGRADATION_STRESS": "Additional 0.4% of recorded turnover.",
            "XSM_RANK_DISPLACEMENT_STRESS": "Remove top contributor for XSM variants.",
            "TOP_N_CONTRIBUTOR_REMOVAL": "Remove recorded top one and top three PnL.",
            "LEAVE_ONE_ASSET_OUT": "Remove each observed asset PnL in turn.",
        },
        "records": records,
        "dynamic_matrix_budget_consumed": 0,
        "cost_execution_budget_consumed": 0,
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
    }
    atomic_json(BOUNDED, report)
    md_name = "ams-md01r2-bounded-sensitivity-v1.md"
    atomic_text(
        REPORTS / md_name,
        "\n".join(
            [
                "# AMS-MD01R2 Bounded Non-identification Analysis",
                "",
                f"- Judgment: **{judgment}**",
                f"- Recorded executions analysed: {len(records)}",
                "- Point-in-time backtest: **false**",
                "- Dynamic matrix budget consumed: **0**",
                "",
                "These are transparent artifact-level bounds. They do not reconstruct "
                "missing venue membership and cannot establish an edge.",
                "",
            ]
        ),
    )
    atomic_csv(
        REPORTS / "leave-one-asset-out.csv",
        fieldnames=("variant_id", "cost_mode", "symbol", "compounded_return"),
        rows=loo_rows,
    )
    atomic_csv(
        REPORTS / "leave-top-n-out.csv",
        fieldnames=("variant_id", "cost_mode", "scenario", "compounded_return"),
        rows=top_rows,
    )
    atomic_csv(
        REPORTS / "cost-sensitivity.csv",
        fieldnames=("variant_id", "cost_mode", "baseline_return"),
        rows=cost_rows,
    )
    atomic_csv(
        REPORTS / "liquidity-stress.csv",
        fieldnames=(
            "variant_id",
            "cost_mode",
            "extra_turnover_cost",
            "compounded_return",
        ),
        rows=liquidity_rows,
    )
    copy_external([BOUNDED.name, md_name])
    print("ANALYSIS_TYPE=BOUNDED_NON_IDENTIFICATION_ANALYSIS")
    print(f"BOUNDED_JUDGMENT={judgment}")
    print("DYNAMIC_MATRIX_BUDGET_CONSUMED=0")


if __name__ == "__main__":
    main()
