"""Credential-safe Dune acquisition boundary for RD09B."""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from spotbot.research.rd09b_dune_feasibility import credit_budget, validate_pilot_range

DUNE_KEY_NAME: Final = "DUNE_API_KEY"
ZERO_SPEND_NAME: Final = "DUNE_ZERO_SPEND_CONFIRMED"


@dataclass(frozen=True)
class ExecutionGate:
    credential_present: bool
    zero_spend_attested: bool
    decision: str
    request_authorized: bool


def execution_gate(environment: dict[str, str] | None = None) -> ExecutionGate:
    values = os.environ if environment is None else environment
    credential_present = bool(values.get(DUNE_KEY_NAME))
    attested = values.get(ZERO_SPEND_NAME, "").lower() == "true"
    if not credential_present:
        return ExecutionGate(
            False,
            attested,
            "RD09B_DUNE_CREDENTIAL_REQUIRED",
            False,
        )
    if not attested:
        return ExecutionGate(
            True,
            False,
            "RD09B_ZERO_SPEND_ATTESTATION_REQUIRED",
            False,
        )
    return ExecutionGate(True, True, "USAGE_METADATA_CHECK_REQUIRED", False)


def query_sha256(sql: str) -> str:
    return hashlib.sha256(sql.encode("utf-8")).hexdigest()


def result_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def may_execute(
    *,
    estimated_credits: float | None,
    credits_included: float,
    credits_used: float,
) -> bool:
    if estimated_credits is None or estimated_credits < 0:
        return False
    return estimated_credits <= credit_budget(credits_included, credits_used)


def validate_query_identity(
    *,
    start: str,
    end_exclusive: str,
    prior_successful_hashes: set[str],
    sql: str,
) -> str:
    validate_pilot_range(start, end_exclusive)
    digest = query_sha256(sql)
    if digest in prior_successful_hashes:
        raise RuntimeError("successful query must not be re-executed")
    return digest
