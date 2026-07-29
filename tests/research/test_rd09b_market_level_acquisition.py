import json
import urllib.request
from collections.abc import Mapping

from spotbot.research.rd09b_market_level_acquisition import (
    DuneClient,
    budget_state,
    environment_gate,
    may_start_next_query,
    parse_usage,
)


class FakeResponse:
    def __init__(self, payload: Mapping[str, object]) -> None:
        self._raw = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._raw


def test_credential_is_never_serialized_and_header_authentication_is_used() -> None:
    secret = "do-not-serialize"
    captured: list[urllib.request.Request] = []

    def opener(request: urllib.request.Request, timeout: int) -> FakeResponse:
        assert timeout == 60
        captured.append(request)
        return FakeResponse(
            {
                "billingPeriods": [
                    {
                        "start_date": "2026-07-01",
                        "end_date": "2026-08-01",
                        "credits_included": 2500,
                        "credits_used": 10,
                    }
                ]
            }
        )

    client = DuneClient(secret, opener=opener)
    usage = client.usage()
    request = captured[0]
    assert usage.credits_included == 2500
    assert request.full_url == "https://api.dune.com/api/v1/usage"
    assert "api_key" not in request.full_url.lower()
    assert request.get_header("X-dune-api-key") == secret
    assert secret not in repr(client)
    assert request.data is not None
    assert secret not in request.data.decode("utf-8")


def test_result_pagination_uses_header_authentication() -> None:
    secret = "do-not-serialize"
    captured: list[urllib.request.Request] = []

    def opener(request: urllib.request.Request, timeout: int) -> FakeResponse:
        assert timeout == 60
        captured.append(request)
        return FakeResponse({"result": {"rows": []}, "next_offset": None})

    client = DuneClient(secret, opener=opener)
    client.execution_results("execution-id", offset=100, limit=500)
    request = captured[0]
    assert request.full_url == (
        "https://api.dune.com/api/v1/execution/execution-id/results?offset=100&limit=500"
    )
    assert request.get_header("X-dune-api-key") == secret
    assert secret not in request.full_url
    assert request.data is None


def test_process_environment_gate_and_credit_stops() -> None:
    missing = environment_gate({})
    assert missing.decision == "RD09B_DUNE_CREDENTIAL_NOT_IN_PROCESS_ENVIRONMENT"
    assert not missing.request_authorized
    ready = environment_gate({"DUNE_API_KEY": "secret", "DUNE_ZERO_SPEND_CONFIRMED": "true"})
    assert ready.request_authorized
    assert "secret" not in repr(ready)
    assert may_start_next_query(budget_state(100, 499))
    assert not may_start_next_query(budget_state(100, 501))


def test_usage_schema_must_make_credits_determinable() -> None:
    usage = parse_usage(
        {
            "billingPeriods": [
                {
                    "start_date": "2026-07-01",
                    "end_date": "2026-08-01",
                    "credits_included": 2500,
                    "credits_used": 100,
                }
            ]
        }
    )
    assert usage.credits_used == 100
    try:
        parse_usage({"billingPeriods": []})
    except ValueError:
        pass
    else:
        raise AssertionError("unknown usage schema did not fail closed")
