"""Run the sequential, resumable RD09B v2 Dune pilot."""

from __future__ import annotations

import csv
import hashlib
import json
import os
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path
from typing import Final

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
    QuerySpec,
    registered_queries,
    sql_sha256,
)

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "reports" / "research"
QUERY_DIR = REPORTS / "rd09b-v2-queries"
LOCAL_ROOT = ROOT / "data" / "research" / "rd09b" / "v2"
LOCAL_MANIFEST = LOCAL_ROOT / "manifests" / "query-execution-manifest.csv"
LOCAL_CREDITS = LOCAL_ROOT / "manifests" / "credit-usage.csv"
LOCAL_STATE = LOCAL_ROOT / "manifests" / "pilot-state.json"
REPORT_MANIFEST = REPORTS / "ams-rd09b-v2-query-execution-manifest-v1.csv"
REPORT_CREDITS = REPORTS / "ams-rd09b-v2-credit-usage-v1.csv"
REPORT_ACCOUNT = REPORTS / "ams-rd09b-v2-account-usage-v1.json"
MAX_RESULT_PAGES: Final = 10
RESULT_PAGE_LIMIT: Final = 1000

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


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


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


def _blank_row(spec: QuerySpec, reason: str = "") -> dict[str, object]:
    sql = (QUERY_DIR / spec.sql_filename).read_text(encoding="utf-8")
    return {
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
        "failure_reason": reason,
    }


def _manifest_map() -> dict[str, dict[str, object]]:
    specs = registered_queries()
    rows: dict[str, dict[str, object]] = {
        spec.query_id_internal: _blank_row(spec) for spec in specs
    }
    local_rows = read_csv(LOCAL_MANIFEST)
    valid_ids = set(rows)
    if local_rows and {row.get("query_id_internal", "") for row in local_rows} != valid_ids:
        raise RuntimeError("RD09B local manifest identity set changed")
    for row in local_rows:
        query_id = row["query_id_internal"]
        rows[query_id] = dict(row)
    return rows


def _complete_artifacts_valid(row: dict[str, object]) -> bool:
    if row.get("status") != "COMPLETE":
        return False
    raw_rel = str(row.get("raw_response_path", ""))
    normalized_rel = str(row.get("normalized_path", ""))
    if not raw_rel or not normalized_rel:
        return False
    raw_path = ROOT / raw_rel
    normalized_path = ROOT / normalized_rel
    if not raw_path.is_file() or not normalized_path.is_file():
        return False
    return sha256_bytes(raw_path.read_bytes()) == str(
        row.get("raw_response_sha256", "")
    ) and sha256_bytes(normalized_path.read_bytes()) == str(row.get("normalized_sha256", ""))


def _load_or_create_state(snapshot: UsageSnapshot) -> dict[str, object]:
    if LOCAL_STATE.exists():
        state = json.loads(LOCAL_STATE.read_text(encoding="utf-8"))
        if not isinstance(state, dict):
            raise RuntimeError("RD09B local state has invalid shape")
        if (
            state.get("billing_period_start") != snapshot.period_start
            or state.get("billing_period_end") != snapshot.period_end
        ):
            raise RuntimeError("RD09B_DUNE_BILLING_PERIOD_CHANGED")
        baseline = optional_float(state.get("baseline_credits_used"))
        if baseline > snapshot.credits_used:
            raise RuntimeError("RD09B local credit baseline exceeds observed usage")
        return state
    state = {
        "stage": "RD09B-M1-DUNE-NATIVE-CHAIN-PILOT",
        "billing_period_start": snapshot.period_start,
        "billing_period_end": snapshot.period_end,
        "baseline_credits_used": snapshot.credits_used,
        "created_at_utc": datetime.now(UTC).isoformat(),
        "last_updated_utc": datetime.now(UTC).isoformat(),
    }
    write_text(LOCAL_STATE, json.dumps(state, indent=2, sort_keys=True) + "\n")
    return state


def _write_account(
    *,
    decision: str,
    snapshot: UsageSnapshot | None,
    baseline_used: float | None,
    request_count: int,
    credential: bool = True,
    attested: bool = True,
) -> None:
    current_used = snapshot.credits_used if snapshot is not None else None
    consumed = (
        budget_state(baseline_used, current_used).pilot_consumed
        if baseline_used is not None and current_used is not None
        else 0.0
    )
    account = {
        "stage": "RD09B-M1-DUNE-NATIVE-CHAIN-PILOT",
        "checked_at_utc": datetime.now(UTC).isoformat(),
        "credential_present": credential,
        "zero_spend_attested": attested,
        "user_zero_spend_attestation_recorded": True,
        "process_zero_spend_attestation_visible": attested,
        "user_attested_spend_limit_usd": 0,
        "usage_endpoint_called": snapshot is not None,
        "usage_endpoint_credit_cost": 0,
        "credits_included_user_reported": 2500,
        "credits_included_observed": (snapshot.credits_included if snapshot is not None else None),
        "baseline_credits_used": baseline_used,
        "credits_used_observed": current_used,
        "pilot_credits_consumed": consumed,
        "paid_spending_usd": MAX_PAID_SPEND_USD,
        "performance_tier": PERFORMANCE_TIER,
        "request_count": request_count,
        "credential_serialized": False,
        "decision": decision,
    }
    write_text(REPORT_ACCOUNT, json.dumps(account, indent=2, sort_keys=True) + "\n")


def _persist(
    manifest_by_id: dict[str, dict[str, object]],
    credit_rows: list[dict[str, object]],
) -> None:
    ordered = [manifest_by_id[spec.query_id_internal] for spec in registered_queries()]
    write_csv(LOCAL_MANIFEST, ordered, MANIFEST_FIELDS)
    write_csv(REPORT_MANIFEST, ordered, MANIFEST_FIELDS)
    write_csv(LOCAL_CREDITS, credit_rows, CREDIT_FIELDS)
    write_csv(REPORT_CREDITS, credit_rows, CREDIT_FIELDS)


def _blocked_outputs(decision: str, credential: bool, attested: bool) -> None:
    manifest = {spec.query_id_internal: _blank_row(spec, decision) for spec in registered_queries()}
    _persist(manifest, [])
    _write_account(
        decision=decision,
        snapshot=None,
        baseline_used=None,
        request_count=0,
        credential=credential,
        attested=attested,
    )


def _result_pages(
    client: DuneClient,
    execution_id: str,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    pages: list[dict[str, object]] = []
    rows: list[dict[str, object]] = []
    offset = 0
    for _ in range(MAX_RESULT_PAGES):
        payload = client.execution_results(
            execution_id,
            offset=offset,
            limit=RESULT_PAGE_LIMIT,
        )
        pages.append(payload)
        rows.extend(_extract_rows(payload))
        next_offset = payload.get("next_offset")
        if next_offset is None:
            return pages, rows
        if isinstance(next_offset, bool) or not isinstance(next_offset, int):
            raise RuntimeError("Dune result next_offset has invalid type")
        if next_offset <= offset:
            raise RuntimeError("Dune result pagination did not advance")
        offset = next_offset
    raise RuntimeError("Dune result exceeded registered page limit")


def _timestamps(status: dict[str, object]) -> tuple[object, object]:
    started = status.get("execution_started_at", status.get("started_at", ""))
    ended = status.get("execution_ended_at", status.get("completed_at", ""))
    return started, ended


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
    try:
        current = client.usage()
    except RuntimeError:
        _blocked_outputs("RD09B_DUNE_USAGE_UNAVAILABLE", True, True)
        print("RD09B_V2_PILOT_DECISION=RD09B_DUNE_USAGE_UNAVAILABLE")
        return

    state = _load_or_create_state(current)
    baseline_used = optional_float(state["baseline_credits_used"])
    manifest = _manifest_map()
    credit_rows: list[dict[str, object]] = [dict(row) for row in read_csv(LOCAL_CREDITS)]
    usage_sequence = max((int(row["event_sequence"]) for row in credit_rows), default=0) + 1
    if not credit_rows:
        credit_rows.append(
            _usage_row(
                sequence=usage_sequence,
                event_type="PRE_FIRST_EXECUTION",
                query_id="",
                snapshot=current,
                baseline=baseline_used,
            )
        )
        usage_sequence += 1
    _persist(manifest, credit_rows)
    _write_account(
        decision="PILOT_ACQUISITION_IN_PROGRESS",
        snapshot=current,
        baseline_used=baseline_used,
        request_count=sum(row.get("status") in {"COMPLETE", "FAILED"} for row in manifest.values()),
    )

    total_failures = sum(row.get("status") == "FAILED" for row in manifest.values())
    consecutive_failures = 0
    blocker: str | None = None

    for spec in registered_queries():
        prior = manifest[spec.query_id_internal]
        if _complete_artifacts_valid(prior):
            consecutive_failures = 0
            continue

        try:
            before = client.usage()
        except RuntimeError:
            blocker = "RD09B_DUNE_USAGE_UNAVAILABLE"
            break
        credit_rows.append(
            _usage_row(
                sequence=usage_sequence,
                event_type="PRE_EXECUTION",
                query_id=spec.query_id_internal,
                snapshot=before,
                baseline=baseline_used,
            )
        )
        usage_sequence += 1
        before_state = budget_state(baseline_used, before.credits_used)
        if not may_start_next_query(before_state):
            blocker = "RD09B_DUNE_CREDIT_BUDGET_EXHAUSTED"
            break

        sql = (QUERY_DIR / spec.sql_filename).read_text(encoding="utf-8")
        submitted = datetime.now(UTC).isoformat()
        try:
            execution = client.execute_sql(sql)
            execution_id = execution.get("execution_id")
            if not isinstance(execution_id, str) or not execution_id:
                raise RuntimeError("Dune execute response lacks execution_id")
            status = client.poll(execution_id)
        except RuntimeError as exc:
            try:
                after_error = client.usage()
            except RuntimeError:
                blocker = "RD09B_DUNE_USAGE_UNAVAILABLE"
                break
            observed_delta = after_error.credits_used - before.credits_used
            credit_rows.append(
                _usage_row(
                    sequence=usage_sequence,
                    event_type="POST_EXECUTION_ERROR",
                    query_id=spec.query_id_internal,
                    snapshot=after_error,
                    baseline=baseline_used,
                )
            )
            usage_sequence += 1
            total_failures += 1
            consecutive_failures += 1
            failed = _blank_row(spec)
            failed.update(
                {
                    "execution_state": "REQUEST_FAILED",
                    "submitted_at": submitted,
                    "usage_credits_before": before.credits_used,
                    "usage_credits_after": after_error.credits_used,
                    "observed_credit_delta": observed_delta,
                    "status": "FAILED",
                    "failure_reason": str(exc),
                }
            )
            manifest[spec.query_id_internal] = failed
            _persist(manifest, credit_rows)
            _write_account(
                decision="PILOT_ACQUISITION_IN_PROGRESS",
                snapshot=after_error,
                baseline_used=baseline_used,
                request_count=sum(
                    row.get("status") in {"COMPLETE", "FAILED"} for row in manifest.values()
                ),
            )
            if observed_delta > 100:
                blocker = "RD09B_DUNE_CREDIT_BUDGET_EXHAUSTED"
                break
            if total_failures >= 3 or consecutive_failures >= 2:
                blocker = "RD09B_DUNE_API_EXECUTION_BLOCKED"
                break
            continue

        try:
            after_execution = client.usage()
        except RuntimeError:
            blocker = "RD09B_DUNE_USAGE_UNAVAILABLE"
            break
        credit_rows.append(
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
        started, completed = _timestamps(status)

        if execution_cost > 100 or observed_delta > 100:
            blocker = "RD09B_DUNE_CREDIT_BUDGET_EXHAUSTED"

        if status.get("state") != "QUERY_STATE_COMPLETED":
            total_failures += 1
            consecutive_failures += 1
            failed = _blank_row(spec)
            failed.update(
                {
                    "execution_id": execution_id,
                    "execution_state": status.get("state", ""),
                    "submitted_at": submitted,
                    "started_at": started,
                    "completed_at": completed,
                    "execution_cost_credits": execution_cost,
                    "usage_credits_before": before.credits_used,
                    "usage_credits_after": after_execution.credits_used,
                    "observed_credit_delta": observed_delta,
                    "status": "FAILED",
                    "failure_reason": sanitized_execution_error(status),
                }
            )
            manifest[spec.query_id_internal] = failed
            _persist(manifest, credit_rows)
            _write_account(
                decision="PILOT_ACQUISITION_IN_PROGRESS",
                snapshot=after_execution,
                baseline_used=baseline_used,
                request_count=sum(
                    row.get("status") in {"COMPLETE", "FAILED"} for row in manifest.values()
                ),
            )
            if blocker is not None or total_failures >= 3 or consecutive_failures >= 2:
                blocker = blocker or "RD09B_DUNE_API_EXECUTION_BLOCKED"
                break
            continue

        consecutive_failures = 0
        try:
            pages, rows = _result_pages(client, execution_id)
            after_download = client.usage()
        except RuntimeError:
            blocker = "RD09B_DUNE_API_EXECUTION_BLOCKED"
            break
        credit_rows.append(
            _usage_row(
                sequence=usage_sequence,
                event_type="POST_RESULT_DOWNLOAD",
                query_id=spec.query_id_internal,
                snapshot=after_download,
                baseline=baseline_used,
            )
        )
        usage_sequence += 1
        download_delta = after_download.credits_used - before.credits_used
        if download_delta > 100:
            blocker = "RD09B_DUNE_CREDIT_BUDGET_EXHAUSTED"

        raw = json.dumps(
            {"pages": pages},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        raw_path = LOCAL_ROOT / "raw" / f"{spec.query_id_internal}.json"
        normalized_path = LOCAL_ROOT / "normalized" / f"{spec.query_id_internal}.csv"
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        normalized_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path.write_bytes(raw)
        fields = list(rows[0]) if rows else ["day"]
        write_csv(normalized_path, rows, fields)
        normalized_raw = normalized_path.read_bytes()
        days = sorted(str(row.get("day", "")) for row in rows if row.get("day"))
        complete = _blank_row(spec)
        complete.update(
            {
                "execution_id": execution_id,
                "execution_state": status.get("state", ""),
                "submitted_at": submitted,
                "started_at": started,
                "completed_at": completed,
                "execution_cost_credits": execution_cost,
                "usage_credits_before": before.credits_used,
                "usage_credits_after": after_download.credits_used,
                "observed_credit_delta": download_delta,
                "raw_response_path": raw_path.relative_to(ROOT).as_posix(),
                "raw_response_sha256": sha256_bytes(raw),
                "normalized_path": normalized_path.relative_to(ROOT).as_posix(),
                "normalized_sha256": sha256_bytes(normalized_raw),
                "row_count": len(rows),
                "first_day": days[0] if days else "",
                "last_day": days[-1] if days else "",
                "result_download_count": len(pages),
                "status": "COMPLETE",
                "failure_reason": "",
            }
        )
        manifest[spec.query_id_internal] = complete
        _persist(manifest, credit_rows)
        _write_account(
            decision="PILOT_ACQUISITION_IN_PROGRESS",
            snapshot=after_download,
            baseline_used=baseline_used,
            request_count=sum(
                row.get("status") in {"COMPLETE", "FAILED"} for row in manifest.values()
            ),
        )
        if blocker is not None:
            break

    try:
        final_usage = client.usage()
        credit_rows.append(
            _usage_row(
                sequence=usage_sequence,
                event_type="FINAL",
                query_id="",
                snapshot=final_usage,
                baseline=baseline_used,
            )
        )
    except RuntimeError:
        final_usage = current
        blocker = blocker or "RD09B_DUNE_USAGE_UNAVAILABLE"

    final_state = budget_state(baseline_used, final_usage.credits_used)
    if final_state.pilot_consumed > MAX_PILOT_CREDITS:
        blocker = "RD09B_DUNE_CREDIT_BUDGET_EXHAUSTED"

    decision = blocker or "PILOT_ACQUISITION_FINISHED"
    for spec in registered_queries():
        row = manifest[spec.query_id_internal]
        if row.get("status") == "NOT_EXECUTED" and blocker is not None:
            row["failure_reason"] = blocker
    state["last_updated_utc"] = datetime.now(UTC).isoformat()
    state["last_decision"] = decision
    write_text(LOCAL_STATE, json.dumps(state, indent=2, sort_keys=True) + "\n")
    _persist(manifest, credit_rows)
    _write_account(
        decision=decision,
        snapshot=final_usage,
        baseline_used=baseline_used,
        request_count=sum(row.get("status") in {"COMPLETE", "FAILED"} for row in manifest.values()),
    )
    print(f"RD09B_V2_PILOT_DECISION={decision}")
    print(f"PILOT_CREDITS_CONSUMED={final_state.pilot_consumed}")
    print(
        "EXECUTED_QUERY_COUNT="
        f"{sum(row.get('status') in {'COMPLETE', 'FAILED'} for row in manifest.values())}"
    )


if __name__ == "__main__":
    main()
