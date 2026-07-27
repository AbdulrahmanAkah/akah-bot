from __future__ import annotations

from typing import Any

import pytest

from spotbot.research.rd04_bf01_protocol_adjudication import (
    BENCHMARK_ID,
    BENCHMARK_NAME,
    LEGACY_COMMIT,
    LEGACY_NORMALIZED_SHA256,
    LEGACY_PATH,
    REPAIR_DECISION,
    SCHEMA_VERSION,
    BF01ProtocolAdjudicationError,
    adjudicated_contract,
    analyze_legacy_source,
    build_decision,
    normalize_newlines,
    sha256_text,
    validate_report,
)


def legacy_source() -> str:
    return """
BENCHMARKS = {
    "B02": "EQUAL_WEIGHT_ELIGIBLE_UNIVERSE",
}

def _metrics():
    pass

def _daily_matrix():
    pass

def _weight_schedules():
    for timestamp in []:
        if timestamp.weekday() != 6:
            continue
        symbols = []
        schedules = {"B02": {}}
        schedules["B02"][timestamp] = (
            {symbol: 1.0 / len(symbols) for symbol in symbols}
            if symbols
            else {}
        )

def _fold():
    prices = object()
    asset_returns = prices.pct_change(fill_method=None).fillna(0.0)
    for timestamp in []:
        decision_time = pd.Timestamp(timestamp) - pd.Timedelta(days=1)
        benchmark_id = "B02"
        weights = {}
        weight_schedule = {}
        if pd.Timestamp(timestamp).weekday() == 0 or benchmark_id in {"B03", "B04"}:
            weights = weight_schedule.get(decision_time, weights)
            prior_weights = dict(weights)
            equity_values = [100000.0]
            fee = 0.0
            equity_values[-1] -= fee
        row = {}
        portfolio_return = sum(
            weight * float(row.get(symbol, 0.0)) for symbol, weight in weights.items()
        )
"""


def complete_analysis() -> dict[str, Any]:
    analysis = analyze_legacy_source(legacy_source())
    analysis["hash_matches"] = True
    analysis["normalized_sha256"] = LEGACY_NORMALIZED_SHA256
    return analysis


def complete_report() -> dict[str, Any]:
    analysis = complete_analysis()
    return {
        "schema_version": SCHEMA_VERSION,
        "research_stage": "RD04-D5D1",
        "status": "COMPLETE",
        "decision": build_decision(analysis),
        "legacy_analysis": analysis,
        "adjudicated_contract": adjudicated_contract(),
        "safety": {
            "portfolio_simulation_executed": False,
            "test_2025_accessed": False,
            "holdout_2026_accessed": False,
            "parameter_optimisation_used": False,
            "candidate_universe_created": False,
            "trade_logic_changed": False,
        },
    }


def test_normalize_newlines_is_deterministic() -> None:
    assert normalize_newlines("a\r\nb\rc\n") == "a\nb\nc\n"


def test_sha256_text_normalizes_newlines() -> None:
    assert sha256_text("a\r\nb") == sha256_text("a\nb")


def test_legacy_identifiers_are_frozen() -> None:
    assert BENCHMARK_ID == "B02"
    assert BENCHMARK_NAME == "EQUAL_WEIGHT_ELIGIBLE_UNIVERSE"
    assert LEGACY_COMMIT == "0c90d338ea7390e17ec8906fa0ae91ee9b15c2c4"
    assert LEGACY_PATH == "scripts/research/run_ams_md01_benchmarks.py"


def test_analyze_recovers_b02_protocol() -> None:
    analysis = analyze_legacy_source(legacy_source())
    assert analysis["protocol_recovered"] is True
    assert analysis["benchmark_map"]["B02"] == BENCHMARK_NAME
    assert analysis["missing_signatures"] == []
    assert analysis["missing_functions"] == []


def test_analyze_rejects_missing_equal_weight_signature() -> None:
    source = legacy_source().replace(
        "{symbol: 1.0 / len(symbols) for symbol in symbols}",
        "{symbol: 0.25 for symbol in symbols}",
    )
    analysis = analyze_legacy_source(source)
    assert analysis["protocol_recovered"] is False
    assert analysis["missing_signatures"]


def test_analyze_rejects_invalid_python() -> None:
    with pytest.raises(BF01ProtocolAdjudicationError):
        analyze_legacy_source("def broken(")


def test_confirmed_defects_are_frozen() -> None:
    analysis = analyze_legacy_source(legacy_source())
    assert analysis["confirmed_defect_ids"] == [
        "DAILY_CONSTANT_TARGET_WEIGHTS_WITH_WEEKLY_TURNOVER",
        "TURNOVER_IGNORES_INTER_REBALANCE_WEIGHT_DRIFT",
        "ENTRY_FEE_CAN_MUTATE_REPORTED_INITIAL_CAPITAL",
        "HELD_MISSING_RETURN_IS_COERCED_TO_ZERO",
    ]


def test_contract_registers_self_financing_weekly_accounting() -> None:
    contract = {str(row["field"]): str(row["value"]) for row in adjudicated_contract()}
    assert contract["rebalance_frequency"] == "WEEKLY_MONDAY"
    assert contract["between_rebalances"] == "SELF_FINANCING_HOLDINGS_DRIFT"
    assert contract["initial_capital"] == "100000_FIXED_PER_FOLD"
    assert contract["missing_held_return"] == "DATA_CONTRACT_FAILURE"


def test_contract_uses_pit_not_survivor_universe() -> None:
    contract = {str(row["field"]): str(row["value"]) for row in adjudicated_contract()}
    assert "PIT_WEEKLY_TOP30" in contract["universe"]
    assert "SURVIVOR" not in contract["universe"]


def test_contract_defines_matched_weekly_expectancy() -> None:
    contract = {str(row["field"]): str(row["value"]) for row in adjudicated_contract()}
    assert contract["expectancy_metric"] == "MEAN_MATCHED_MONDAY_TO_MONDAY_NET_RETURN"


def test_decision_authorizes_only_repaired_d5d2_research() -> None:
    decision = build_decision(complete_analysis())
    assert decision["decision"] == REPAIR_DECISION
    assert decision["d5d2_benchmark_execution_research_authorized"] is True
    assert decision["legacy_benchmark_execution_authorized"] is False
    assert decision["point_in_time_universe_research_baseline_authorized"] is False


def test_decision_blocks_hash_mismatch() -> None:
    analysis = complete_analysis()
    analysis["hash_matches"] = False
    decision = build_decision(analysis)
    assert decision["decision"] == "BF01_PROTOCOL_ADJUDICATION_BLOCKED"
    assert decision["d5d2_benchmark_execution_research_authorized"] is False


def test_validate_report_accepts_safe_complete_report() -> None:
    validate_report(complete_report())


def test_validate_report_rejects_legacy_execution_authorization() -> None:
    report = complete_report()
    report["decision"]["legacy_benchmark_execution_authorized"] = True
    with pytest.raises(BF01ProtocolAdjudicationError):
        validate_report(report)


def test_validate_report_rejects_simulation() -> None:
    report = complete_report()
    report["safety"]["portfolio_simulation_executed"] = True
    with pytest.raises(BF01ProtocolAdjudicationError):
        validate_report(report)


def test_validate_report_rejects_contract_drift() -> None:
    report = complete_report()
    report["adjudicated_contract"] = report["adjudicated_contract"][:-1]
    with pytest.raises(BF01ProtocolAdjudicationError):
        validate_report(report)
