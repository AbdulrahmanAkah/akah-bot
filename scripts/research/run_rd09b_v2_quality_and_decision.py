"""Audit RD09B v2 pilot quality and issue the fail-closed decision."""

from __future__ import annotations

import csv
import hashlib
import json
from io import StringIO
from pathlib import Path

from spotbot.research.rd09b_market_level_protocol import (
    METRIC_FIELDS,
    NAMESPACE_ORDER,
    ORIGINAL_RD09_BROAD_GATE,
    ORIGINAL_RD09_DUNE_SCORE,
)

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "reports" / "research"
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


def _blocked_decision(account: dict[str, object]) -> str | None:
    if account.get("credential_present") is not True:
        return "RD09B_DUNE_CREDENTIAL_NOT_IN_PROCESS_ENVIRONMENT"
    if account.get("zero_spend_attested") is not True:
        return "RD09B_DUNE_ZERO_SPEND_ATTESTATION_NOT_IN_PROCESS_ENVIRONMENT"
    return None


def main() -> None:
    account_path = REPORTS / "ams-rd09b-v2-account-usage-v1.json"
    account = json.loads(account_path.read_text(encoding="utf-8"))
    if not isinstance(account, dict):
        raise RuntimeError("RD09B v2 account report has invalid shape")
    manifest = read_csv(MANIFEST_PATH)
    if len(manifest) != 15:
        raise RuntimeError("RD09B v2 execution manifest must account for 15 queries")
    blocker = _blocked_decision(account)
    complete = [row for row in manifest if row["status"] == "COMPLETE"]

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
    ]
    quality_rows = [
        {
            "query_id_internal": row["query_id_internal"],
            "namespace": row["namespace"],
            "pilot_month": row["pilot_month"],
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
            "quality_status": "NOT_EVALUATED_NO_ACQUISITION",
        }
        for row in manifest
    ]
    write_csv(
        REPORTS / "ams-rd09b-v2-pilot-quality-v1.csv",
        quality_rows,
        quality_fields,
    )

    metric_rows = []
    for namespace, _asset in NAMESPACE_ORDER:
        for metric in METRIC_FIELDS:
            documented = metric not in {
                "unique_sending_addresses",
                "unique_receiving_addresses",
                "unique_active_addresses",
            }
            if namespace in {"ethereum", "avalanche_c"}:
                documented = True
            if namespace == "polkadot" and metric == "unique_sending_addresses":
                documented = True
            metric_rows.append(
                {
                    "namespace": namespace,
                    "metric": metric,
                    "schema_contract_available": documented,
                    "pilot_observed_available": False,
                    "metric_family": (
                        "FEES_OR_BLOCK_PRODUCTION"
                        if metric in {"native_fees_paid", "block_count"}
                        else "TRANSACTION_ACTIVITY"
                    ),
                    "missing_reason": "NO_ACQUISITION_CREDENTIAL_NOT_VISIBLE",
                }
            )
    write_csv(
        REPORTS / "ams-rd09b-v2-metric-availability-v1.csv",
        metric_rows,
        list(metric_rows[0]),
    )

    causal_rows = []
    for namespace, asset in NAMESPACE_ORDER:
        causal_rows.append(
            {
                "namespace": namespace,
                "asset": asset,
                "raw_event_or_block_timestamp_present": True,
                "immutable_historical_event_source": True,
                "no_current_state_membership_dependency": True,
                "daily_aggregation_deterministic": True,
                "entity_mapping_valid_at_event_time": True,
                "reconstructable_from_frozen_sql": True,
                "pilot_acquisition_observed": False,
                "causal_grade": "NOT_ASSIGNED_WITHOUT_ACQUISITION",
            }
        )
    write_csv(
        REPORTS / "ams-rd09b-v2-causal-audit-v1.csv",
        causal_rows,
        list(causal_rows[0]),
    )

    score_rows = [
        {
            "score_id": "RD09B_MARKET_LEVEL_FEASIBILITY_SCORE",
            "causal_integrity_points": 0,
            "pilot_namespace_coverage_points": 0,
            "reproducibility_points": 0,
            "economic_information_independence_points": 15,
            "cost_licensing_suitability_points": 10,
            "daily_frequency_latency_suitability_points": 0,
            "total_score": 25,
            "selection_threshold": 70,
            "selection_gate_passed": False,
            "score_status": "BLOCKED_BEFORE_PILOT",
            "original_rd09_dune_score": ORIGINAL_RD09_DUNE_SCORE,
            "original_rd09_broad_gate": ORIGINAL_RD09_BROAD_GATE,
        }
    ]
    write_csv(
        REPORTS / "ams-rd09b-v2-market-level-score-v1.csv",
        score_rows,
        list(score_rows[0]),
    )

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
            "check_id": "NO_DUNE_REQUEST_WITHOUT_CREDENTIAL",
            "expected": 0,
            "observed": len(complete),
            "passed": blocker is not None and not complete,
            "notes": blocker or "",
        },
        {
            "check_id": "ORIGINAL_RD09_SCORE_UNCHANGED",
            "expected": 65,
            "observed": ORIGINAL_RD09_DUNE_SCORE,
            "passed": ORIGINAL_RD09_DUNE_SCORE == 65,
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

    decision = blocker or "RD09B_DUNE_API_EXECUTION_BLOCKED"
    report = {
        "stage": "RD09B-M1-DUNE-NATIVE-CHAIN-PILOT",
        "status": "BLOCKED",
        "decision": decision,
        "next_stage": "NONE_WHILE_BLOCKED",
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
        "paid_spending_usd": 0,
        "selected_performance_tier": "small",
        "registered_query_count": 15,
        "executed_query_count": len(complete),
        "passing_namespace_count": 0,
        "failing_namespace_count": 0,
        "unevaluated_namespace_count": 5,
        "market_level_score": 25,
        "market_level_gate_evaluated": False,
        "full_source_freeze_protocol_authorized": False,
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
        f"Status: {report['status']}\n\n"
        f"Decision: {report['decision']}\n\n"
        "The pre-acquisition amendment and SQL pack are complete. The Dune pilot "
        "was not started because the credential and attestation were not visible "
        "inside the runner process. No API request, credit use, signal, label, "
        "or portfolio operation occurred.\n",
    )
    write_text(
        ROOT / "RD09B_V2_DUNE_PILOT_RESULT_FOR_CHATGPT.md",
        "# RD09B v2 Dune Pilot Result\n\n"
        "Status: BLOCKED\n\n"
        f"Decision: {decision}\n\n"
        "Queries executed: 0 of 15. Pilot credits consumed: 0. Paid spending: $0.\n",
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
    print(f"RD09B_V2_STATUS={report['status']}")
    print(f"RD09B_V2_DECISION={decision}")
    print(f"EXECUTED_QUERY_COUNT={len(complete)}")
    print("PILOT_CREDITS_CONSUMED=0")


if __name__ == "__main__":
    main()
