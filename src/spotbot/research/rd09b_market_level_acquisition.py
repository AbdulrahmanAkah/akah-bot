"""Secret-safe, sequential Dune acquisition boundary for RD09B v2."""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Final, Protocol

from spotbot.research.rd09b_market_level_protocol import (
    MAX_PILOT_CREDITS,
    MAX_SINGLE_QUERY_CREDITS,
    PERFORMANCE_TIER,
)

API_HOST: Final = "api.dune.com"
API_BASE: Final = f"https://{API_HOST}/api/v1"
KEY_ENV: Final = "DUNE_API_KEY"
ATTESTATION_ENV: Final = "DUNE_ZERO_SPEND_CONFIRMED"
TERMINAL_STATES: Final = {
    "QUERY_STATE_COMPLETED",
    "QUERY_STATE_FAILED",
    "QUERY_STATE_CANCELLED",
    "QUERY_STATE_EXPIRED",
}


@dataclass(frozen=True)
class EnvironmentGate:
    credential_present: bool
    zero_spend_attested: bool
    user_attested_spend_limit_usd: int
    request_authorized: bool
    decision: str


@dataclass(frozen=True)
class UsageSnapshot:
    period_start: str
    period_end: str
    credits_included: float
    credits_used: float


@dataclass(frozen=True)
class BudgetState:
    baseline_credits_used: float
    current_credits_used: float
    pilot_consumed: float
    remaining_pilot_budget: float


class ResponseLike(Protocol):
    def read(self) -> bytes: ...


def environment_gate(environment: Mapping[str, str] | None = None) -> EnvironmentGate:
    values = os.environ if environment is None else environment
    credential_present = bool(values.get(KEY_ENV))
    attested = values.get(ATTESTATION_ENV, "").lower() == "true"
    if not credential_present:
        return EnvironmentGate(
            False,
            attested,
            0,
            False,
            "RD09B_DUNE_CREDENTIAL_NOT_IN_PROCESS_ENVIRONMENT",
        )
    if not attested:
        return EnvironmentGate(
            True,
            False,
            0,
            False,
            "RD09B_DUNE_ZERO_SPEND_ATTESTATION_NOT_IN_PROCESS_ENVIRONMENT",
        )
    return EnvironmentGate(True, True, 0, True, "USAGE_CHECK_REQUIRED")


def parse_usage(payload: Mapping[str, object]) -> UsageSnapshot:
    periods = payload.get("billingPeriods")
    if periods is None:
        periods = payload.get("billing_periods")
    if not isinstance(periods, list) or not periods:
        keys = ",".join(sorted(str(key) for key in payload))
        raise ValueError(f"usage response lacks billing periods; top-level keys={keys}")
    item = periods[-1]
    if not isinstance(item, dict):
        raise ValueError("usage billing period has invalid shape")
    try:
        start = str(item["start_date"])
        end = str(item["end_date"])
        included = float(item["credits_included"])
        used = float(item["credits_used"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("usage response credits are not determinable") from exc
    if included < 0 or used < 0:
        raise ValueError("usage response contains negative credits")
    return UsageSnapshot(start, end, included, used)


def budget_state(baseline: float, current: float) -> BudgetState:
    if baseline < 0 or current < 0:
        raise ValueError("credit usage cannot be negative")
    consumed = max(0.0, current - baseline)
    return BudgetState(
        baseline_credits_used=baseline,
        current_credits_used=current,
        pilot_consumed=consumed,
        remaining_pilot_budget=max(0.0, MAX_PILOT_CREDITS - consumed),
    )


def may_start_next_query(state: BudgetState) -> bool:
    return (
        state.pilot_consumed < MAX_PILOT_CREDITS
        and state.remaining_pilot_budget >= MAX_SINGLE_QUERY_CREDITS
    )


class DuneClient:
    """Minimal Dune API client that never serializes the credential."""

    def __init__(
        self,
        api_key: str,
        *,
        opener: Callable[..., ResponseLike] = urllib.request.urlopen,
    ) -> None:
        if not api_key:
            raise ValueError("Dune credential is unavailable")
        self._api_key = api_key
        self._opener = opener

    def _request(
        self,
        method: str,
        path: str,
        payload: Mapping[str, object] | None = None,
    ) -> dict[str, object]:
        if not path.startswith("/") or "://" in path:
            raise ValueError("Dune request path must be relative")
        url = f"{API_BASE}{path}"
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=body,
            method=method,
            headers={
                "Content-Type": "application/json",
                "X-Dune-API-Key": self._api_key,
            },
        )
        try:
            response = self._opener(request, timeout=60)
            raw = response.read()
        except urllib.error.HTTPError as exc:
            raw_error = exc.read().decode("utf-8", errors="replace")
            try:
                error_payload = json.loads(raw_error)
            except json.JSONDecodeError:
                error_payload = {}

            message = error_payload.get("error")
            if not isinstance(message, str):
                message = f"Dune API HTTP status {exc.code}"

            if exc.code == 400 and "performance tier is not available" in message.lower():
                raise RuntimeError("DUNE_SUBSCRIPTION_BLOCKS_API_EXECUTION") from None

            raise RuntimeError(f"Dune API HTTP status {exc.code}: {message}") from None
        except urllib.error.URLError:
            raise RuntimeError("Dune API network request failed") from None
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            raise RuntimeError("Dune API returned a non-object response")
        return parsed

    def usage(self) -> UsageSnapshot:
        return parse_usage(self._request("POST", "/usage", {}))

    def execute_sql(self, sql: str) -> dict[str, object]:
        return self._request(
            "POST",
            "/sql/execute",
            {"sql": sql, "performance": PERFORMANCE_TIER},
        )

    def execution_status(self, execution_id: str) -> dict[str, object]:
        return self._request("GET", f"/execution/{execution_id}/status")

    def execution_results(
        self,
        execution_id: str,
        *,
        offset: int = 0,
        limit: int = 1000,
    ) -> dict[str, object]:
        if offset < 0 or limit <= 0:
            raise ValueError("Dune result pagination bounds are invalid")
        return self._request(
            "GET",
            f"/execution/{execution_id}/results?offset={offset}&limit={limit}",
        )

    def poll(
        self,
        execution_id: str,
        *,
        interval_seconds: float = 2.0,
        max_polls: int = 900,
    ) -> dict[str, object]:
        for _ in range(max_polls):
            status = self.execution_status(execution_id)
            if status.get("state") in TERMINAL_STATES:
                return status
            time.sleep(interval_seconds)
        raise RuntimeError("Dune execution polling limit reached")


def sanitized_execution_error(payload: Mapping[str, object]) -> str:
    error = payload.get("error")
    if isinstance(error, dict):
        error_type = error.get("type")
        if isinstance(error_type, str):
            return error_type
    return "DUNE_EXECUTION_FAILED"
