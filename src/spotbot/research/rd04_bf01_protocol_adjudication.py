"""Adjudicate the exact BF01 B02 protocol before any PIT benchmark execution."""

from __future__ import annotations

import ast
import hashlib
from collections.abc import Mapping, Sequence
from typing import Any, Final

SCHEMA_VERSION: Final = "ams-rd04-d5d1-bf01-protocol-adjudication-v1"
LEGACY_COMMIT: Final = "0c90d338ea7390e17ec8906fa0ae91ee9b15c2c4"
LEGACY_PATH: Final = "scripts/research/run_ams_md01_benchmarks.py"
LEGACY_NORMALIZED_SHA256: Final = "595d793b5c055bb052afebd75329c0b2d0076c1b871d324866c5247b27063bff"
BENCHMARK_ID: Final = "B02"
BENCHMARK_NAME: Final = "EQUAL_WEIGHT_ELIGIBLE_UNIVERSE"
REPAIR_DECISION: Final = "BF01_PROTOCOL_RECOVERED_ACCOUNTING_REPAIR_REGISTERED"

_REQUIRED_SIGNATURES: Final[tuple[str, ...]] = (
    '"B02": "EQUAL_WEIGHT_ELIGIBLE_UNIVERSE"',
    "if timestamp.weekday() != 6:",
    'schedules["B02"][timestamp]',
    "{symbol: 1.0 / len(symbols) for symbol in symbols}",
    "asset_returns = prices.pct_change(fill_method=None).fillna(0.0)",
    "decision_time = pd.Timestamp(timestamp) - pd.Timedelta(days=1)",
    'if pd.Timestamp(timestamp).weekday() == 0 or benchmark_id in {"B03", "B04"}:',
    "weights = weight_schedule.get(decision_time, weights)",
    "prior_weights = dict(weights)",
    "equity_values[-1] -= fee",
    "portfolio_return = sum(",
    "weight * float(row.get(symbol, 0.0)) for symbol, weight in weights.items()",
)

_DEFECT_IDS: Final[tuple[str, ...]] = (
    "DAILY_CONSTANT_TARGET_WEIGHTS_WITH_WEEKLY_TURNOVER",
    "TURNOVER_IGNORES_INTER_REBALANCE_WEIGHT_DRIFT",
    "ENTRY_FEE_CAN_MUTATE_REPORTED_INITIAL_CAPITAL",
    "HELD_MISSING_RETURN_IS_COERCED_TO_ZERO",
)


class BF01ProtocolAdjudicationError(RuntimeError):
    """Raised when the exact historical BF01 source cannot be adjudicated safely."""


def normalize_newlines(text: str) -> str:
    """Return deterministic LF-normalized source text."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def sha256_text(text: str) -> str:
    """Hash normalized UTF-8 text."""
    normalized = normalize_newlines(text)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _function_names(tree: ast.AST) -> set[str]:
    return {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _assigned_string_mapping(tree: ast.AST, name: str) -> dict[str, str]:
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(target, ast.Name) and target.id == name for target in node.targets):
            continue
        if not isinstance(node.value, ast.Dict):
            continue
        result: dict[str, str] = {}
        for key, value in zip(node.value.keys, node.value.values, strict=True):
            if (
                isinstance(key, ast.Constant)
                and isinstance(key.value, str)
                and isinstance(value, ast.Constant)
                and isinstance(value.value, str)
            ):
                result[key.value] = value.value
        return result
    return {}


def analyze_legacy_source(source: str) -> dict[str, Any]:
    """Recover the B02 intent and detect accounting inconsistencies statically."""
    normalized = normalize_newlines(source)
    try:
        tree = ast.parse(normalized)
    except SyntaxError as error:
        raise BF01ProtocolAdjudicationError(
            "Historical benchmark source is not valid Python."
        ) from error

    benchmark_map = _assigned_string_mapping(tree, "BENCHMARKS")
    functions = _function_names(tree)
    signature_presence = {signature: signature in normalized for signature in _REQUIRED_SIGNATURES}

    missing_signatures = sorted(
        signature for signature, present in signature_presence.items() if not present
    )
    required_functions = {"_weight_schedules", "_fold", "_metrics", "_daily_matrix"}
    missing_functions = sorted(required_functions.difference(functions))

    protocol_recovered = (
        benchmark_map.get(BENCHMARK_ID) == BENCHMARK_NAME
        and not missing_signatures
        and not missing_functions
    )

    findings = [
        {
            "finding_id": "LEGACY_BENCHMARK_ID",
            "status": "PASS" if benchmark_map.get(BENCHMARK_ID) == BENCHMARK_NAME else "FAIL",
            "detail": f"{BENCHMARK_ID}={benchmark_map.get(BENCHMARK_ID)!r}",
        },
        {
            "finding_id": "SUNDAY_DECISION_SCHEDULE",
            "status": "PASS" if signature_presence["if timestamp.weekday() != 6:"] else "FAIL",
            "detail": "B02 schedule is frozen only on completed Sunday daily closes.",
        },
        {
            "finding_id": "MONDAY_NEXT_RETURN_APPLICATION",
            "status": (
                "PASS"
                if signature_presence[
                    'if pd.Timestamp(timestamp).weekday() == 0 or benchmark_id in {"B03", "B04"}:'
                ]
                else "FAIL"
            ),
            "detail": "The Sunday decision is applied on the following Monday daily return.",
        },
        {
            "finding_id": "EQUAL_WEIGHT_ALL_ELIGIBLE",
            "status": (
                "PASS"
                if signature_presence["{symbol: 1.0 / len(symbols) for symbol in symbols}"]
                else "FAIL"
            ),
            "detail": "All causally eligible symbols receive equal target weight.",
        },
        {
            "finding_id": _DEFECT_IDS[0],
            "status": "CONFIRMED",
            "detail": (
                "Daily portfolio returns reuse unchanged target weights between Mondays, "
                "while turnover and fees are charged only when the weekly target schedule changes."
            ),
        },
        {
            "finding_id": _DEFECT_IDS[1],
            "status": "CONFIRMED",
            "detail": (
                "Turnover compares the new target with prior target weights rather than "
                "pre-trade weights drifted by realized asset returns."
            ),
        },
        {
            "finding_id": _DEFECT_IDS[2],
            "status": "CONFIRMED",
            "detail": (
                "The entry fee is deducted from equity_values[-1] before the equity series is "
                "built, so the reported initial capital can become 99,800 instead of 100,000."
            ),
        },
        {
            "finding_id": _DEFECT_IDS[3],
            "status": "CONFIRMED",
            "detail": (
                "pct_change(...).fillna(0.0) can turn a missing held-asset return "
                "into a zero return "
                "instead of a data-contract failure."
            ),
        },
    ]

    return {
        "legacy_commit": LEGACY_COMMIT,
        "legacy_path": LEGACY_PATH,
        "normalized_sha256": sha256_text(normalized),
        "expected_normalized_sha256": LEGACY_NORMALIZED_SHA256,
        "hash_matches": sha256_text(normalized) == LEGACY_NORMALIZED_SHA256,
        "protocol_recovered": protocol_recovered,
        "benchmark_map": benchmark_map,
        "missing_signatures": missing_signatures,
        "missing_functions": missing_functions,
        "findings": findings,
        "confirmed_defect_ids": list(_DEFECT_IDS),
    }


def adjudicated_contract() -> list[dict[str, object]]:
    """Return the frozen outcome-independent D5D2 accounting contract."""
    return [
        {
            "field": "benchmark_identity",
            "value": BENCHMARK_ID,
            "rationale": BENCHMARK_NAME,
        },
        {
            "field": "universe",
            "value": "FROZEN_RD04_PIT_WEEKLY_TOP30_INTERSECT_CAUSAL_DAILY_DATA_READY",
            "rationale": "Use the same Monday PIT membership schedule; never use survivor-30.",
        },
        {
            "field": "history_readiness",
            "value": "84_COMPLETED_DAILY_RETURN_LOOKBACK",
            "rationale": (
                "Preserve the legacy momentum_84-not-null readiness gate without using "
                "the momentum value for ranking."
            ),
        },
        {
            "field": "decision_time",
            "value": "MONDAY_00_00_UTC",
            "rationale": (
                "Use the completed Sunday close and the frozen Monday PIT snapshot before "
                "the next daily return."
            ),
        },
        {
            "field": "target_weights",
            "value": "EQUAL_1_OVER_N",
            "rationale": "Equal weight every eligible PIT member; hold cash if N is zero.",
        },
        {
            "field": "rebalance_frequency",
            "value": "WEEKLY_MONDAY",
            "rationale": "Preserve the BF01 B02 weekly schedule.",
        },
        {
            "field": "between_rebalances",
            "value": "SELF_FINANCING_HOLDINGS_DRIFT",
            "rationale": "Do not imply free daily rebalancing.",
        },
        {
            "field": "turnover",
            "value": "SUM_ABS_TARGET_MINUS_PRETRADE_DRIFTED_WEIGHT",
            "rationale": "Charge actual one-way buy and sell notional at each weekly rebalance.",
        },
        {
            "field": "transaction_costs",
            "value": "ZERO_0_BASE_0_002_STRESS_0_004",
            "rationale": "Preserve BF01 zero/base and add the already registered D4 stress mode.",
        },
        {
            "field": "initial_capital",
            "value": "100000_FIXED_PER_FOLD",
            "rationale": "Fees reduce equity, never the reported initial-capital denominator.",
        },
        {
            "field": "fold_end",
            "value": "FULL_LIQUIDATION_WITH_COST",
            "rationale": "Close all holdings and include liquidation turnover and fees.",
        },
        {
            "field": "missing_held_return",
            "value": "DATA_CONTRACT_FAILURE",
            "rationale": "Never coerce a missing held-asset return to zero.",
        },
        {
            "field": "return_sampling",
            "value": "DAILY_CLOSE_TO_CLOSE_NEXT_RETURN",
            "rationale": "Causal completed-close decision followed by the next daily return.",
        },
        {
            "field": "expectancy_metric",
            "value": "MEAN_MATCHED_MONDAY_TO_MONDAY_NET_RETURN",
            "rationale": (
                "Compute expectancy for M05 and equal-weight on identical weekly intervals; "
                "do not compare trade expectancy with portfolio-interval expectancy."
            ),
        },
        {
            "field": "primary_delta_sign",
            "value": "M05_MINUS_EQUAL_WEIGHT",
            "rationale": (
                "Positive return and expectancy deltas favor M05; positive drawdown improvement "
                "is EQUAL_WEIGHT_DRAWDOWN_MINUS_M05_DRAWDOWN."
            ),
        },
        {
            "field": "fold_robustness",
            "value": "M05_BASE_RETURN_BEATS_EQUAL_WEIGHT_IN_AT_LEAST_2_OF_3_FOLDS",
            "rationale": "Aggregate improvement alone is insufficient.",
        },
        {
            "field": "authorization_boundary",
            "value": "D5D2_RESEARCH_ONLY",
            "rationale": (
                "A relative benchmark result cannot authorize PIT baseline, production, ATI, "
                "universe, ranking, weight, entry, or exit changes."
            ),
        },
    ]


def build_decision(analysis: Mapping[str, Any]) -> dict[str, object]:
    """Build a safe protocol-adjudication decision."""
    structural_pass = (
        analysis.get("protocol_recovered") is True
        and analysis.get("hash_matches") is True
        and set(analysis.get("confirmed_defect_ids", [])) == set(_DEFECT_IDS)
    )
    return {
        "decision": (REPAIR_DECISION if structural_pass else "BF01_PROTOCOL_ADJUDICATION_BLOCKED"),
        "reason": (
            "EXACT_B02_INTENT_RECOVERED_AND_ACCOUNTING_DEFECTS_REPAIRED_BEFORE_PIT_EXECUTION"
            if structural_pass
            else "EXACT_B02_SOURCE_OR_STATIC_DEFECT_EVIDENCE_INCOMPLETE"
        ),
        "structural_pass": structural_pass,
        "d5d2_benchmark_execution_research_authorized": structural_pass,
        "legacy_benchmark_execution_authorized": False,
        "point_in_time_universe_research_baseline_authorized": False,
        "equal_weight_change_authorized": False,
        "universe_change_authorized": False,
        "ranking_change_authorized": False,
        "weight_change_authorized": False,
        "entry_change_authorized": False,
        "exit_change_authorized": False,
        "trade_logic_changed": False,
        "production_ready": False,
        "live_ready": False,
        "ati_v1_authorized": False,
    }


def validate_report(report: Mapping[str, Any]) -> None:
    """Reject authorization or provenance drift."""
    if report.get("schema_version") != SCHEMA_VERSION:
        raise BF01ProtocolAdjudicationError("D5D1 schema version drifted.")
    if report.get("research_stage") != "RD04-D5D1":
        raise BF01ProtocolAdjudicationError("D5D1 research-stage marker drifted.")
    if report.get("status") != "COMPLETE":
        raise BF01ProtocolAdjudicationError("D5D1 report is not complete.")

    analysis = report.get("legacy_analysis")
    decision = report.get("decision")
    contract = report.get("adjudicated_contract")
    safety = report.get("safety")
    if not isinstance(analysis, Mapping):
        raise BF01ProtocolAdjudicationError("D5D1 legacy analysis is missing.")
    if not isinstance(decision, Mapping):
        raise BF01ProtocolAdjudicationError("D5D1 decision is missing.")
    if not isinstance(contract, Sequence) or isinstance(contract, (str, bytes)):
        raise BF01ProtocolAdjudicationError("D5D1 accounting contract is missing.")
    if not isinstance(safety, Mapping):
        raise BF01ProtocolAdjudicationError("D5D1 safety record is missing.")

    if analysis.get("legacy_commit") != LEGACY_COMMIT:
        raise BF01ProtocolAdjudicationError("D5D1 legacy commit drifted.")
    if analysis.get("legacy_path") != LEGACY_PATH:
        raise BF01ProtocolAdjudicationError("D5D1 legacy path drifted.")
    if analysis.get("hash_matches") is not True:
        raise BF01ProtocolAdjudicationError("D5D1 legacy source hash mismatch.")

    fields = {str(item.get("field")) for item in contract if isinstance(item, Mapping)}
    required_fields = {
        "benchmark_identity",
        "universe",
        "history_readiness",
        "decision_time",
        "target_weights",
        "rebalance_frequency",
        "between_rebalances",
        "turnover",
        "transaction_costs",
        "initial_capital",
        "fold_end",
        "missing_held_return",
        "return_sampling",
        "expectancy_metric",
        "primary_delta_sign",
        "fold_robustness",
        "authorization_boundary",
    }
    if fields != required_fields:
        raise BF01ProtocolAdjudicationError("D5D1 accounting-contract fields drifted.")

    if decision.get("legacy_benchmark_execution_authorized") is not False:
        raise BF01ProtocolAdjudicationError("Legacy flawed benchmark was authorized.")
    if decision.get("point_in_time_universe_research_baseline_authorized") is not False:
        raise BF01ProtocolAdjudicationError("PIT baseline was improperly authorized.")
    if decision.get("trade_logic_changed") is not False:
        raise BF01ProtocolAdjudicationError("D5D1 changed trading logic.")

    for field in (
        "portfolio_simulation_executed",
        "test_2025_accessed",
        "holdout_2026_accessed",
        "parameter_optimisation_used",
        "candidate_universe_created",
        "trade_logic_changed",
    ):
        if safety.get(field) is not False:
            raise BF01ProtocolAdjudicationError(f"Unsafe D5D1 safety field: {field}")
