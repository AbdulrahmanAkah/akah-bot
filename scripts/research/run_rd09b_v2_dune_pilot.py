"""Run the sequential RD09B v2 Dune pilot when credential gates permit."""

from __future__ import annotations

import csv
import hashlib
import json
import os
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path

from spotbot.research.rd09b_market_level_acquisition import (
    DuneClient,
    UsageSnapshot,
    budget_state,
    environment_gate,
    may_start_next_query,
    sanitized_execution_error,
)
from spotbot.research.rd09b_market_level_protocol import (
    MAX_PAID_SPEND_USD,
    MAX_PILOT_CREDITS,
    PERFORMANCE_TIER,
    registered_queries,
    sql_sha256,
)

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "reports" / "research"
QUERY_DIR = REPORTS / "rd09b-v2-queries"
LOCAL_ROOT = ROOT / "data" / "research" / "rd09b" / "v2"
MANIFEST_FIELDS = [
    "query_id_internal",
    "namespace",
    "pilot_month",
    "query_sha256",
    "execution_id",
    "execution_state",
    "submitted_at",
    "started_at",
    "completed_at",
    "execution_cost_credits",
    "usage_credits_before",
    "usage_credits_after",
    "observed_credit_delta",
    "raw_response_path",
    "raw_response_sha256",
    "normalized_path",
    "normalized_sha256",
    "row_count",
    "first_day",
    "last_day",
    "result_download_count",
    "status",
    "failure_reason",
]
CREDIT_FIELDS = [
    "event_sequence",
    "event_type",
    "query_id_internal",
    "checked_at_utc",
    "billing_period_start",
    "billing_period_end",
    "credits_included",
    "credits_used",
    "baseline_credits_used",
    "pilot_consumed",
    "remaining_included_credits",
    "remaining_pilot_budget",
    "usage_endpoint_credit_cost",
]


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


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def optional_float(value: object) -> float:
    if value is None:
        return 0.0
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise RuntimeError("Dune execution cost has invalid type")
    return float(value)


def _extract_rows(payload: dict[str, object]) -> list[dict[str, object]]:
    result = payload.get("result")
    if not isinstance(result, dict):
        raise RuntimeError("Dune result lacks result object")
    rows = result.get("rows")
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise RuntimeError("Dune result rows have invalid shape")
    return [dict(row) for row in rows]


def _usage_row(
    *,
    sequence: int,
    event_type: str,
    query_id: str,
    snapshot: UsageSnapshot,
    baseline: float,
) -> dict[str, object]:
    state = budget_state(baseline, snapshot.credits_used)
    return {
        "event_sequence": sequence,
        "event_type": event_type,
        "query_id_internal": query_id,
        "checked_at_utc": datetime.now(UTC).isoformat(),
        "billing_period_start": snapshot.period_start,
        "billing_period_end": snapshot.period_end,
        "credits_included": snapshot.credits_included,
        "credits_used": snapshot.credits_used,
        "baseline_credits_used": baseline,
        "pilot_consumed": state.pilot_consumed,
        "remaining_included_credits": max(0.0, snapshot.credits_included - snapshot.credits_used),
        "remaining_pilot_budget": state.remaining_pilot_budget,
        "usage_endpoint_credit_cost": 0,
    }


def _blocked_outputs(decision: str, credential: bool, attested: bool) -> None:
    now = datetime.now(UTC).isoformat()
    rows = []
    for spec in registered_queries():
        sql = (QUERY_DIR / spec.sql_filename).read_text(encoding="utf-8")
        rows.append(
            {
                "query_id_internal": spec.query_id_internal,
                "namespace": spec.namespace,
                "pilot_month": spec.pilot_month,
                "query_sha256": sql_sha256(sql),
                "execution_id": "",
                "execution_state": "NOT_SUBMITTED",
                "submitted_at": "",
                "started_at": "",
                "completed_at": "",
                "execution_cost_credits": 0,
                "usage_credits_before": "",
                "usage_credits_after": "",
                "observed_credit_delta": 0,
                "raw_response_path": "",
                "raw_response_sha256": "",
                "normalized_path": "",
                "normalized_sha256": "",
                "row_count": 0,
                "first_day": "",
                "last_day": "",
                "result_download_count": 0,
                "status": "NOT_EXECUTED",
                "failure_reason": decision,
            }
        )
    write_csv(
        REPORTS / "ams-rd09b-v2-query-execution-manifest-v1.csv",
        rows,
        MANIFEST_FIELDS,
    )
    write_csv(
        REPORTS / "ams-rd09b-v2-credit-usage-v1.csv",
        [],
        CREDIT_FIELDS,
    )
    account = {
        "stage": "RD09B-M1-DUNE-NATIVE-CHAIN-PILOT",
        "checked_at_utc": now,
        "credential_present": credential,
        "zero_spend_attested": attested,
        "user_attested_spend_limit_usd": 0,
        "usage_endpoint_called": False,
        "usage_endpoint_credit_cost": 0,
        "credits_included_user_reported": 2500,
        "credits_included_observed": None,
        "credits_used_observed": None,
        "pilot_credits_consumed": 0,
        "paid_spending_usd": 0,
        "performance_tier": PERFORMANCE_TIER,
        "request_count": 0,
        "credential_serialized": False,
        "decision": decision,
    }
    write_text(
        REPORTS / "ams-rd09b-v2-account-usage-v1.json",
        json.dumps(account, indent=2, sort_keys=True) + "\n",
    )


def main() -> None:
    gate = environment_gate()
    if not gate.request_authorized:
        _blocked_outputs(
            gate.decision,
            gate.credential_present,
            gate.zero_spend_attested,
        )
        print(f"RD09B_V2_PILOT_DECISION={gate.decision}")
        print(f"CREDENTIAL_PRESENT={str(gate.credential_present).lower()}")
        print(f"ZERO_SPEND_ATTESTED={str(gate.zero_spend_attested).lower()}")
        print("DUNE_REQUEST_COUNT=0")
        return

    api_key = os.environ["DUNE_API_KEY"]
    client = DuneClient(api_key)
    baseline = client.usage()
    baseline_used = baseline.credits_used
    usage_rows = [
        _usage_row(
            sequence=1,
            event_type="PRE_FIRST_EXECUTION",
            query_id="",
            snapshot=baseline,
            baseline=baseline_used,
        )
    ]
    manifest: list[dict[str, object]] = []
    total_failures = 0
    consecutive_failures = 0
    usage_sequence = 2

    for spec in registered_queries():
        before = client.usage()
        before_state = budget_state(baseline_used, before.credits_used)
        if not may_start_next_query(before_state):
            raise RuntimeError("RD09B_DUNE_CREDIT_BUDGET_EXHAUSTED")
        sql = (QUERY_DIR / spec.sql_filename).read_text(encoding="utf-8")
        submitted = datetime.now(UTC).isoformat()
        execution = client.execute_sql(sql)
        execution_id = execution.get("execution_id")
        if not isinstance(execution_id, str) or not execution_id:
            raise RuntimeError("RD09B_DUNE_API_EXECUTION_BLOCKED")
        status = client.poll(execution_id)
        after_execution = client.usage()
        usage_rows.append(
            _usage_row(
                sequence=usage_sequence,
                event_type="POST_EXECUTION",
                query_id=spec.query_id_internal,
                snapshot=after_execution,
                baseline=baseline_used,
            )
        )
        usage_sequence += 1
        execution_cost = optional_float(status.get("execution_cost_credits"))
        observed_delta = after_execution.credits_used - before.credits_used
        if execution_cost > 100 or observed_delta > 100:
            raise RuntimeError("RD09B_DUNE_CREDIT_BUDGET_EXHAUSTED")
        if status.get("state") != "QUERY_STATE_COMPLETED":
            total_failures += 1
            consecutive_failures += 1
            manifest.append(
                {
                    "query_id_internal": spec.query_id_internal,
                    "namespace": spec.namespace,
                    "pilot_month": spec.pilot_month,
                    "query_sha256": sql_sha256(sql),
                    "execution_id": execution_id,
                    "execution_state": status.get("state", ""),
                    "submitted_at": submitted,
                    "started_at": status.get("started_at", ""),
                    "completed_at": status.get("completed_at", ""),
                    "execution_cost_credits": execution_cost,
                    "usage_credits_before": before.credits_used,
                    "usage_credits_after": after_execution.credits_used,
                    "observed_credit_delta": observed_delta,
                    "raw_response_path": "",
                    "raw_response_sha256": "",
                    "normalized_path": "",
                    "normalized_sha256": "",
                    "row_count": 0,
                    "first_day": "",
                    "last_day": "",
                    "result_download_count": 0,
                    "status": "FAILED",
                    "failure_reason": sanitized_execution_error(status),
                }
            )
            if total_failures >= 3 or consecutive_failures >= 2:
                break
            continue
        consecutive_failures = 0
        result = client.execution_results(execution_id)
        after_download = client.usage()
        usage_rows.append(
            _usage_row(
                sequence=usage_sequence,
                event_type="POST_RESULT_DOWNLOAD",
                query_id=spec.query_id_internal,
                snapshot=after_download,
                baseline=baseline_used,
            )
        )
        usage_sequence += 1
        rows = _extract_rows(result)
        raw = json.dumps(result, sort_keys=True, separators=(",", ":")).encode("utf-8")
        raw_path = LOCAL_ROOT / "raw" / f"{spec.query_id_internal}.json"
        normalized_path = LOCAL_ROOT / "normalized" / f"{spec.query_id_internal}.csv"
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        normalized_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path.write_bytes(raw)
        fields = list(rows[0]) if rows else ["day"]
        write_csv(normalized_path, rows, fields)
        normalized_raw = normalized_path.read_bytes()
        days = sorted(str(row.get("day", "")) for row in rows if row.get("day"))
        manifest.append(
            {
                "query_id_internal": spec.query_id_internal,
                "namespace": spec.namespace,
                "pilot_month": spec.pilot_month,
                "query_sha256": sql_sha256(sql),
                "execution_id": execution_id,
                "execution_state": status.get("state", ""),
                "submitted_at": submitted,
                "started_at": status.get("started_at", ""),
                "completed_at": status.get("completed_at", ""),
                "execution_cost_credits": execution_cost,
                "usage_credits_before": before.credits_used,
                "usage_credits_after": after_download.credits_used,
                "observed_credit_delta": after_download.credits_used - before.credits_used,
                "raw_response_path": raw_path.relative_to(ROOT).as_posix(),
                "raw_response_sha256": sha256_bytes(raw),
                "normalized_path": normalized_path.relative_to(ROOT).as_posix(),
                "normalized_sha256": sha256_bytes(normalized_raw),
                "row_count": len(rows),
                "first_day": days[0] if days else "",
                "last_day": days[-1] if days else "",
                "result_download_count": 1,
                "status": "COMPLETE",
                "failure_reason": "",
            }
        )

    final_usage = client.usage()
    usage_rows.append(
        _usage_row(
            sequence=usage_sequence,
            event_type="FINAL",
            query_id="",
            snapshot=final_usage,
            baseline=baseline_used,
        )
    )
    final_state = budget_state(baseline_used, final_usage.credits_used)
    if final_state.pilot_consumed > MAX_PILOT_CREDITS:
        raise RuntimeError("RD09B_DUNE_CREDIT_BUDGET_EXHAUSTED")
    write_csv(
        REPORTS / "ams-rd09b-v2-query-execution-manifest-v1.csv",
        manifest,
        MANIFEST_FIELDS,
    )
    write_csv(
        REPORTS / "ams-rd09b-v2-credit-usage-v1.csv",
        usage_rows,
        CREDIT_FIELDS,
    )
    account = {
        "stage": "RD09B-M1-DUNE-NATIVE-CHAIN-PILOT",
        "credential_present": True,
        "zero_spend_attested": True,
        "user_attested_spend_limit_usd": MAX_PAID_SPEND_USD,
        "usage_endpoint_called": True,
        "usage_endpoint_credit_cost": 0,
        "billing_period_start": final_usage.period_start,
        "billing_period_end": final_usage.period_end,
        "credits_included_observed": final_usage.credits_included,
        "baseline_credits_used": baseline_used,
        "final_credits_used": final_usage.credits_used,
        "pilot_credits_consumed": final_state.pilot_consumed,
        "paid_spending_usd": 0,
        "performance_tier": PERFORMANCE_TIER,
        "request_count": len(manifest),
        "credential_serialized": False,
        "decision": "PILOT_ACQUISITION_FINISHED",
    }
    write_text(
        REPORTS / "ams-rd09b-v2-account-usage-v1.json",
        json.dumps(account, indent=2, sort_keys=True) + "\n",
    )
    print("RD09B_V2_PILOT_DECISION=PILOT_ACQUISITION_FINISHED")
    print(f"PILOT_CREDITS_CONSUMED={final_state.pilot_consumed}")


if __name__ == "__main__":
    main()
