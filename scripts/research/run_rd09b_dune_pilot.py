"""Apply RD09B credential and zero-spend gates before any Dune request."""

from __future__ import annotations

import csv
import json
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path

from spotbot.research.rd09b_dune_acquisition import execution_gate

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "reports" / "research"


def write_text(path: Path, text: str) -> None:
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(text, encoding="utf-8", newline="\n")
    temporary.replace(path)


def write_csv(path: Path, rows: list[dict[str, object]], fields: list[str]) -> None:
    buffer = StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    write_text(path, buffer.getvalue())


def main() -> None:
    gate = execution_gate()
    now = datetime.now(UTC).isoformat()
    account = {
        "stage": "RD09B-DUNE-ZERO-SPEND-RAW-CHAIN-FEASIBILITY",
        "checked_at_utc": now,
        "credential_present": gate.credential_present,
        "zero_spend_attested": gate.zero_spend_attested,
        "user_attested_spend_limit_usd": (0 if gate.zero_spend_attested else None),
        "usage_endpoint": "POST https://api.dune.com/api/v1/usage",
        "usage_endpoint_called": False,
        "usage_endpoint_call_reason": (
            "CREDENTIAL_MISSING"
            if not gate.credential_present
            else "ZERO_SPEND_ATTESTATION_MISSING"
        ),
        "credits_included": None,
        "credits_used": None,
        "pilot_credit_budget": 0,
        "paid_or_extra_credits_authorized": False,
        "credential_serialized": False,
        "request_count": 0,
        "decision": gate.decision,
    }
    write_text(
        REPORTS / "ams-rd09b-dune-account-usage-v1.json",
        json.dumps(account, indent=2, sort_keys=True) + "\n",
    )
    write_csv(
        REPORTS / "ams-rd09b-query-execution-manifest-v1.csv",
        [],
        [
            "query_id",
            "query_sha256",
            "execution_id",
            "started_at",
            "completed_at",
            "credits_before",
            "credits_after",
            "credits_consumed",
            "row_count",
            "response_sha256",
            "normalized_sha256",
            "status",
        ],
    )
    write_csv(
        REPORTS / "ams-rd09b-pilot-quality-v1.csv",
        [],
        [
            "query_id",
            "namespace",
            "rows",
            "first_day",
            "last_day",
            "expected_day_count",
            "duplicate_days",
            "missing_days",
            "null_count",
            "nonfinite_count",
            "impossible_negative_count",
            "address_count_consistent",
            "transaction_count_consistent",
            "raw_response_sha256",
            "normalized_sha256",
            "status",
        ],
    )
    write_csv(
        REPORTS / "ams-rd09b-credit-usage-v1.csv",
        [
            {
                "checked_at_utc": now,
                "credits_included": "",
                "credits_used_before": "",
                "credits_used_after": "",
                "pilot_budget": 0,
                "credits_consumed": 0,
                "paid_credits_consumed": 0,
                "usage_checked_before": False,
                "usage_checked_after": False,
                "status": "NOT_CALCULABLE_CREDENTIAL_MISSING",
            }
        ],
        [
            "checked_at_utc",
            "credits_included",
            "credits_used_before",
            "credits_used_after",
            "pilot_budget",
            "credits_consumed",
            "paid_credits_consumed",
            "usage_checked_before",
            "usage_checked_after",
            "status",
        ],
    )
    print(f"RD09B_EXECUTION_DECISION={gate.decision}")
    print(f"DUNE_CREDENTIAL_PRESENT={str(gate.credential_present).lower()}")
    print(f"ZERO_SPEND_ATTESTED={str(gate.zero_spend_attested).lower()}")
    print("DUNE_REQUESTS_EXECUTED=0")
    print("CREDITS_CONSUMED=0")


if __name__ == "__main__":
    main()
