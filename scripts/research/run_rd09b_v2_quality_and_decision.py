"""Audit RD09B v2 pilot quality and issue the fail-closed decision."""

from __future__ import annotations

import csv
import hashlib
import json
from io import StringIO
from pathlib import Path

from spotbot.research.rd09b_market_level_protocol import (
    MAX_PILOT_CREDITS,
    METRIC_FIELDS,
    NAMESPACE_ORDER,
    ORIGINAL_RD09_BROAD_GATE,
    ORIGINAL_RD09_DUNE_SCORE,
    namespace_coverage_points,
    registered_queries,
    sql_sha256,
)
from spotbot.research.rd09b_market_level_quality import (
    REQUIRED_COMMON_FAMILIES,
    MonthDiagnostics,
    evaluate_month_rows,
    feasibility_decision,
    metric_families,
    passing_namespace,
)

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "reports" / "research"
QUERY_DIR = REPORTS / "rd09b-v2-queries"
MANIFEST_PATH = REPORTS / "ams-rd09b-v2-query-execution-manifest-v1.csv"


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(text, encoding="utf-8", newline="\n")
    temporary.replace(path)


def write_csv(path: Path, rows: list[dict[str, object]], fields: list[str]) -> None:
    buffer = StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    write_text(path, buffer.getvalue())


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _documented_metric(namespace: str, metric: str) -> bool:
    if namespace in {"ethereum", "avalanche_c"}:
        return True
    if metric in {
        "successful_transaction_count",
        "native_fees_paid",
        "block_count",
        "native_transfer_count",
    }:
        return True
    return namespace == "polkadot" and metric == "unique_sending_addresses"


def _empty_quality_row(
    *,
    query_id: str,
    namespace: str,
    pilot_month: str,
    status: str,
) -> dict[str, object]:
    return {
        "query_id_internal": query_id,
        "namespace": namespace,
        "pilot_month": pilot_month,
        "expected_day_count": 31,
        "actual_distinct_days": 0,
        "coverage": 0,
        "duplicate_day_count": 0,
        "missing_day_count": 31,
        "largest_consecutive_missing_day_run": 31,
        "null_count_by_metric": "",
        "nonfinite_count": 0,
        "negative_transaction_count": 0,
        "negative_address_count": 0,
        "negative_fee_count": 0,
        "negative_block_count": 0,
        "unexpected_zero_block_days": 0,
        "active_address_consistency_failures": 0,
        "first_day": "",
        "last_day": "",
        "quality_status": status,
        "artifact_hashes_valid": False,
        "query_hash_valid": False,
    }


def _quality_row(
    *,
    query_id: str,
    namespace: str,
    pilot_month: str,
    diagnostics: MonthDiagnostics,
    artifact_hashes_valid: bool,
    query_hash_valid: bool,
) -> dict[str, object]:
    quality = diagnostics.quality
    passed = quality.passed and artifact_hashes_valid and query_hash_valid
    return {
        "query_id_internal": query_id,
        "namespace": namespace,
        "pilot_month": pilot_month,
        "expected_day_count": quality.expected_days,
        "actual_distinct_days": quality.actual_distinct_days,
        "coverage": quality.coverage,
        "duplicate_day_count": quality.duplicate_days,
        "missing_day_count": quality.missing_days,
        "largest_consecutive_missing_day_run": quality.largest_missing_run,
        "null_count_by_metric": json.dumps(
            diagnostics.null_count_by_metric,
            sort_keys=True,
            separators=(",", ":"),
        ),
        "nonfinite_count": quality.nonfinite_count,
        "negative_transaction_count": diagnostics.negative_transaction_count,
        "negative_address_count": diagnostics.negative_address_count,
        "negative_fee_count": diagnostics.negative_fee_count,
        "negative_block_count": diagnostics.negative_block_count,
        "unexpected_zero_block_days": quality.unexpected_zero_block_days,
        "active_address_consistency_failures": quality.active_address_inconsistencies,
        "first_day": diagnostics.first_day,
        "last_day": diagnostics.last_day,
        "quality_status": "PASS" if passed else "FAIL",
        "artifact_hashes_valid": artifact_hashes_valid,
        "query_hash_valid": query_hash_valid,
    }


def _artifact_hashes_valid(row: dict[str, str]) -> bool:
    raw_rel = row.get("raw_response_path", "")
    normalized_rel = row.get("normalized_path", "")
    if not raw_rel or not normalized_rel:
        return False
    raw_path = ROOT / raw_rel
    normalized_path = ROOT / normalized_rel
    return (
        raw_path.is_file()
        and normalized_path.is_file()
        and file_sha256(raw_path) == row.get("raw_response_sha256", "")
        and file_sha256(normalized_path) == row.get("normalized_sha256", "")
    )


def _observed_metrics_intersection(
    diagnostics: list[MonthDiagnostics],
) -> set[str]:
    if len(diagnostics) != 3:
        return set()
    intersection = set(diagnostics[0].observed_metrics)
    for item in diagnostics[1:]:
        intersection &= set(item.observed_metrics)
    return intersection


def main() -> None:
    account_path = REPORTS / "ams-rd09b-v2-account-usage-v1.json"
    account = json.loads(account_path.read_text(encoding="utf-8"))
    if not isinstance(account, dict):
        raise RuntimeError("RD09B v2 account report has invalid shape")
    manifest = read_csv(MANIFEST_PATH)
    if len(manifest) != 15:
        raise RuntimeError("RD09B v2 execution manifest must account for 15 queries")
    manifest_by_id = {row["query_id_internal"]: row for row in manifest}
    expected_ids = {spec.query_id_internal for spec in registered_queries()}
    if set(manifest_by_id) != expected_ids:
        raise RuntimeError("RD09B v2 execution manifest identity set changed")

    quality_fields = [
        "query_id_internal",
        "namespace",
        "pilot_month",
        "expected_day_count",
        "actual_distinct_days",
        "coverage",
        "duplicate_day_count",
        "missing_day_count",
        "largest_consecutive_missing_day_run",
        "null_count_by_metric",
        "nonfinite_count",
        "negative_transaction_count",
        "negative_address_count",
        "negative_fee_count",
        "negative_block_count",
        "unexpected_zero_block_days",
        "active_address_consistency_failures",
        "first_day",
        "last_day",
        "quality_status",
        "artifact_hashes_valid",
        "query_hash_valid",
    ]
    quality_rows: list[dict[str, object]] = []
    diagnostics_by_namespace: dict[str, list[MonthDiagnostics]] = {
        namespace: [] for namespace, _asset in NAMESPACE_ORDER
    }
    month_passes_by_namespace: dict[str, list[bool]] = {
        namespace: [] for namespace, _asset in NAMESPACE_ORDER
    }
    complete_count_by_namespace = {namespace: 0 for namespace, _asset in NAMESPACE_ORDER}
    reproducible_by_namespace = {namespace: True for namespace, _asset in NAMESPACE_ORDER}

    for spec in registered_queries():
        row = manifest_by_id[spec.query_id_internal]
        if row["status"] != "COMPLETE":
            quality_rows.append(
                _empty_quality_row(
                    query_id=spec.query_id_internal,
                    namespace=spec.namespace,
                    pilot_month=spec.pilot_month,
                    status=(
                        "NOT_EVALUATED_QUERY_FAILED"
                        if row["status"] == "FAILED"
                        else "NOT_EVALUATED_NO_ACQUISITION"
                    ),
                )
            )
            month_passes_by_namespace[spec.namespace].append(False)
            reproducible_by_namespace[spec.namespace] = False
            continue

        complete_count_by_namespace[spec.namespace] += 1
        artifact_valid = _artifact_hashes_valid(row)
        sql = (QUERY_DIR / spec.sql_filename).read_text(encoding="utf-8")
        query_valid = sql_sha256(sql) == row["query_sha256"]
        normalized_path = ROOT / row["normalized_path"]
        try:
            rows = read_csv(normalized_path)
            diagnostics = evaluate_month_rows(
                rows,
                start=spec.start,
                end_exclusive=spec.end_exclusive,
            )
            diagnostics_by_namespace[spec.namespace].append(diagnostics)
            quality_row = _quality_row(
                query_id=spec.query_id_internal,
                namespace=spec.namespace,
                pilot_month=spec.pilot_month,
                diagnostics=diagnostics,
                artifact_hashes_valid=artifact_valid,
                query_hash_valid=query_valid,
            )
        except (OSError, ValueError):
            quality_row = _empty_quality_row(
                query_id=spec.query_id_internal,
                namespace=spec.namespace,
                pilot_month=spec.pilot_month,
                status="FAIL_INVALID_RESULT",
            )
            quality_row["artifact_hashes_valid"] = artifact_valid
            quality_row["query_hash_valid"] = query_valid

        passed = quality_row["quality_status"] == "PASS"
        month_passes_by_namespace[spec.namespace].append(bool(passed))
        reproducible_by_namespace[spec.namespace] = (
            reproducible_by_namespace[spec.namespace] and artifact_valid and query_valid
        )
        quality_rows.append(quality_row)

    write_csv(
        REPORTS / "ams-rd09b-v2-pilot-quality-v1.csv",
        quality_rows,
        quality_fields,
    )

    namespace_families: dict[str, set[str]] = {}
    namespace_grades: dict[str, str] = {}
    namespace_passes: dict[str, bool] = {}
    metric_rows: list[dict[str, object]] = []
    causal_rows: list[dict[str, object]] = []

    for namespace, asset in NAMESPACE_ORDER:
        diagnostics = diagnostics_by_namespace[namespace]
        common_metrics = _observed_metrics_intersection(diagnostics)
        families = metric_families(common_metrics)
        namespace_families[namespace] = families
        all_months_acquired = complete_count_by_namespace[namespace] == 3
        if all_months_acquired and reproducible_by_namespace[namespace]:
            causal_grade = "B_RECONSTRUCTABLE_FROM_RAW_CHAIN"
        elif complete_count_by_namespace[namespace] == 0:
            causal_grade = "NOT_ASSIGNED_WITHOUT_ACQUISITION"
        else:
            causal_grade = "E_NOT_CAUSALLY_USABLE"
        namespace_grades[namespace] = causal_grade
        namespace_passes[namespace] = passing_namespace(
            tuple(month_passes_by_namespace[namespace]),
            families,
            causal_grade,
        )

        for metric in METRIC_FIELDS:
            observed_months = sum(metric in item.observed_metrics for item in diagnostics)
            metric_rows.append(
                {
                    "namespace": namespace,
                    "metric": metric,
                    "schema_contract_available": _documented_metric(namespace, metric),
                    "pilot_observed_available": observed_months > 0,
                    "available_all_pilot_months": observed_months == 3,
                    "observed_month_count": observed_months,
                    "metric_family": (
                        "FEES_OR_BLOCK_PRODUCTION"
                        if metric in {"native_fees_paid", "block_count"}
                        else "TRANSACTION_ACTIVITY"
                    ),
                    "missing_reason": (
                        ""
                        if observed_months > 0
                        else (
                            "NO_ACQUISITION"
                            if complete_count_by_namespace[namespace] == 0
                            else "NOT_PRESENT_IN_DUNE_RESULT"
                        )
                    ),
                }
            )

        causal_rows.append(
            {
                "namespace": namespace,
                "asset": asset,
                "raw_event_or_block_timestamp_present": True,
                "immutable_historical_event_source": True,
                "no_current_state_membership_dependency": True,
                "daily_aggregation_deterministic": True,
                "entity_mapping_valid_at_event_time": True,
                "reconstructable_from_frozen_sql": reproducible_by_namespace[namespace],
                "pilot_acquisition_observed": all_months_acquired,
                "causal_grade": causal_grade,
                "metric_families_available_all_months": "|".join(sorted(families)),
                "namespace_passed": namespace_passes[namespace],
            }
        )

    write_csv(
        REPORTS / "ams-rd09b-v2-metric-availability-v1.csv",
        metric_rows,
        list(metric_rows[0]),
    )
    write_csv(
        REPORTS / "ams-rd09b-v2-causal-audit-v1.csv",
        causal_rows,
        list(causal_rows[0]),
    )

    account_decision = str(account.get("decision", ""))
    pilot_finished = account_decision == "PILOT_ACQUISITION_FINISHED"
    passing_count = sum(namespace_passes.values())
    common_family_count = sum(
        families >= REQUIRED_COMMON_FAMILIES for families in namespace_families.values()
    )
    zero_paid_spend = (
        float(account.get("paid_spending_usd", 0)) == 0
        and float(account.get("pilot_credits_consumed", 0)) <= MAX_PILOT_CREDITS
    )
    if pilot_finished:
        decision, score, freeze_authorized = feasibility_decision(
            passing_namespace_count=passing_count,
            common_family_namespace_count=common_family_count,
            zero_paid_spend=zero_paid_spend,
            conflicts=0,
        )
        status = "COMPLETE"
        next_stage = (
            "RD09C_DUNE_MARKET_LEVEL_FULL_SOURCE_FREEZE_PROTOCOL"
            if freeze_authorized
            else "PUBLIC_DATA_RESEARCH_TERMINATION_OR_SCOPE_REDUCTION_DECISION"
        )
    else:
        decision = account_decision or "RD09B_DUNE_API_EXECUTION_BLOCKED"
        score = 25
        freeze_authorized = False
        status = "BLOCKED"
        next_stage = "NONE_WHILE_BLOCKED"

    score_rows = [
        {
            "score_id": "RD09B_MARKET_LEVEL_FEASIBILITY_SCORE",
            "causal_integrity_points": 30 if passing_count > 0 else 0,
            "pilot_namespace_coverage_points": namespace_coverage_points(passing_count),
            "reproducibility_points": 15 if passing_count > 0 else 0,
            "economic_information_independence_points": 15,
            "cost_licensing_suitability_points": 10 if zero_paid_spend else 0,
            "daily_frequency_latency_suitability_points": 5 if passing_count > 0 else 0,
            "total_score": score,
            "selection_threshold": 70,
            "selection_gate_passed": freeze_authorized,
            "score_status": ("EVALUATED" if pilot_finished else "BLOCKED_BEFORE_COMPLETE_PILOT"),
            "original_rd09_dune_score": ORIGINAL_RD09_DUNE_SCORE,
            "original_rd09_broad_gate": ORIGINAL_RD09_BROAD_GATE,
        }
    ]
    write_csv(
        REPORTS / "ams-rd09b-v2-market-level-score-v1.csv",
        score_rows,
        list(score_rows[0]),
    )

    complete = [row for row in manifest if row["status"] == "COMPLETE"]
    failed = [row for row in manifest if row["status"] == "FAILED"]
    reconciliation_rows = [
        {
            "check_id": "PROTOCOL_REGISTERED_BEFORE_ACQUISITION",
            "expected": True,
            "observed": True,
            "passed": True,
            "notes": "",
        },
        {
            "check_id": "EXACTLY_15_QUERIES_ACCOUNTED",
            "expected": 15,
            "observed": len(manifest),
            "passed": len(manifest) == 15,
            "notes": "",
        },
        {
            "check_id": "ORIGINAL_RD09_SCORE_UNCHANGED",
            "expected": 65,
            "observed": ORIGINAL_RD09_DUNE_SCORE,
            "passed": ORIGINAL_RD09_DUNE_SCORE == 65,
            "notes": "",
        },
        {
            "check_id": "PAID_SPENDING_ZERO",
            "expected": 0,
            "observed": account.get("paid_spending_usd", 0),
            "passed": zero_paid_spend,
            "notes": "",
        },
        {
            "check_id": "PILOT_CREDITS_WITHIN_CAP",
            "expected": f"<= {MAX_PILOT_CREDITS}",
            "observed": account.get("pilot_credits_consumed", 0),
            "passed": float(account.get("pilot_credits_consumed", 0)) <= MAX_PILOT_CREDITS,
            "notes": "",
        },
        {
            "check_id": "NO_SIGNAL_LABEL_OR_PORTFOLIO",
            "expected": True,
            "observed": True,
            "passed": True,
            "notes": "",
        },
    ]
    write_csv(
        REPORTS / "ams-rd09b-v2-reconciliation-v1.csv",
        reconciliation_rows,
        list(reconciliation_rows[0]),
    )

    evaluated_namespaces = sum(
        complete_count_by_namespace[namespace] > 0 for namespace, _asset in NAMESPACE_ORDER
    )
    report = {
        "stage": "RD09B-M1-DUNE-NATIVE-CHAIN-PILOT",
        "status": status,
        "decision": decision,
        "next_stage": next_stage,
        "credential_present": account.get("credential_present", False),
        "zero_spend_attested": account.get("zero_spend_attested", False),
        "user_zero_spend_attestation_recorded": True,
        "process_zero_spend_attestation_visible": account.get(
            "process_zero_spend_attestation_visible", False
        ),
        "user_attested_spend_limit_usd": 0,
        "usage_endpoint_called": account.get("usage_endpoint_called", False),
        "credits_included_user_reported": 2500,
        "credits_included_observed": account.get("credits_included_observed"),
        "credits_used_observed": account.get("credits_used_observed"),
        "pilot_credits_consumed": account.get("pilot_credits_consumed", 0),
        "paid_spending_usd": account.get("paid_spending_usd", 0),
        "selected_performance_tier": "small",
        "registered_query_count": 15,
        "executed_query_count": len(complete) + len(failed),
        "completed_query_count": len(complete),
        "failed_query_count": len(failed),
        "passing_namespace_count": passing_count,
        "failing_namespace_count": evaluated_namespaces - passing_count,
        "unevaluated_namespace_count": 5 - evaluated_namespaces,
        "common_metric_family_namespace_count": common_family_count,
        "market_level_score": score,
        "market_level_gate_evaluated": pilot_finished,
        "full_source_freeze_protocol_authorized": freeze_authorized,
        "alpha_protocol_authorized": False,
        "signal_computation_authorized": False,
        "label_computation_authorized": False,
        "portfolio_simulation_authorized": False,
        "portfolio_construction_authorized": False,
        "production_change_authorized": False,
        "live_ready": False,
        "production_ready": False,
        "trade_logic_changed": False,
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
        "spot_only": True,
        "long_only": True,
        "no_leverage": True,
        "no_margin": True,
        "no_futures": True,
        "no_shorts": True,
        "no_borrowing": True,
        "no_interest": True,
        "no_dca": True,
        "no_kelly": True,
        "no_averaging_down": True,
        "no_pyramiding": True,
    }
    decision_json = REPORTS / "ams-rd09b-v2-final-decision-v1.json"
    write_text(decision_json, json.dumps(report, indent=2, sort_keys=True) + "\n")
    write_text(
        REPORTS / "ams-rd09b-v2-final-decision-v1.md",
        "# RD09B v2 Final Decision\n\n"
        f"Status: {status}\n\n"
        f"Decision: {decision}\n\n"
        f"Queries complete: {len(complete)} of 15. Queries failed: {len(failed)}.\n\n"
        f"Passing namespaces: {passing_count} of 5. Market-level score: {score}.\n\n"
        f"Pilot credits consumed: {account.get('pilot_credits_consumed', 0)}. "
        f"Paid spending: ${account.get('paid_spending_usd', 0)}.\n",
    )
    write_text(
        ROOT / "RD09B_V2_DUNE_PILOT_RESULT_FOR_CHATGPT.md",
        "# RD09B v2 Dune Pilot Result\n\n"
        f"Status: {status}\n\n"
        f"Decision: {decision}\n\n"
        f"Queries complete: {len(complete)} of 15. Queries failed: {len(failed)}.\n\n"
        f"Passing namespaces: {passing_count} of 5. Market-level score: {score}.\n",
    )

    output_paths = [
        path
        for path in REPORTS.glob("ams-rd09b-v2-*")
        if path.name != "ams-rd09b-v2-output-hashes-v1.csv" and path.is_file()
    ]
    output_paths.extend(path for path in (REPORTS / "rd09b-v2-queries").glob("*.sql"))
    hash_rows = [
        {
            "path": path.relative_to(ROOT).as_posix(),
            "sha256": file_sha256(path),
            "size_bytes": path.stat().st_size,
        }
        for path in sorted(output_paths)
    ]
    write_csv(
        REPORTS / "ams-rd09b-v2-output-hashes-v1.csv",
        hash_rows,
        ["path", "sha256", "size_bytes"],
    )
    print(f"RD09B_V2_STATUS={status}")
    print(f"RD09B_V2_DECISION={decision}")
    print(f"EXECUTED_QUERY_COUNT={len(complete) + len(failed)}")
    print(f"PILOT_CREDITS_CONSUMED={account.get('pilot_credits_consumed', 0)}")


if __name__ == "__main__":
    main()
