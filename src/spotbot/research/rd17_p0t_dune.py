# RD17-P0T bounded Dune historical supply-component probe.
from __future__ import annotations

import csv
import hashlib
import json
import math
import time
import urllib.error
import urllib.request
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Final, cast

SCHEMA_VERSION: Final = "rd17-p0t-dune-report-v1"
DECISION_PASS: Final = "RD17_P0T_DUNE_COMPONENT_PROBE_PASS_CIRCULATING_SUPPLY_UNPROVEN"
DECISION_COVERAGE: Final = "RD17_P0T_DUNE_COMPONENT_COVERAGE_INSUFFICIENT"
DECISION_BLOCKED: Final = "RD17_P0T_DUNE_API_OR_SCHEMA_BLOCKED"
API_BASE: Final = "https://api.dune.com/api"


class DuneProbeError(RuntimeError):
    pass


@dataclass(frozen=True)
class AssetSpec:
    asset_id: str
    blockchain: str
    contract_address: str
    case_type: str


ASSETS: Final[tuple[AssetSpec, ...]] = (
    AssetSpec("LINK", "ethereum", "0x514910771af9ca656af840dff83e8264ecf986ca", "preissued_supply"),
    AssetSpec("WBTC", "ethereum", "0x2260fac5e5542a773aa44fbcfedf7c193bc2c599", "mint_burn_supply"),
    AssetSpec(
        "UNI", "ethereum", "0x1f9840a85d5af5bf1d1762f925bdaddc4201f984", "treasury_exclusions"
    ),
    AssetSpec(
        "AAVE", "ethereum", "0x7fc66500c84a76ad7e9c93437bfc5ac33e2ddae9", "migration_and_treasury"
    ),
)


def canonical_json_bytes(payload: object) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _parse_date(value: object) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            return None


def load_frozen_snapshot_dates(path: Path) -> tuple[date, ...]:
    if not path.is_file():
        raise DuneProbeError(f"Frozen snapshot CSV not found: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise DuneProbeError("Frozen snapshot CSV is empty.")
    candidates = ("snapshot_date", "snapshot_day", "date", "day", "timestamp", "snapshot_timestamp")
    columns = tuple(rows[0])
    chosen = next((name for name in candidates if name in columns), None)
    if chosen is None:
        chosen = next(
            (
                name
                for name in columns
                if any(part in name.lower() for part in ("date", "snapshot", "time"))
            ),
            None,
        )
    if chosen is None:
        raise DuneProbeError(f"No date-like column found: {columns}")
    dates = sorted({parsed for row in rows if (parsed := _parse_date(row.get(chosen))) is not None})
    if not dates:
        raise DuneProbeError(f"No valid dates in {chosen!r}.")
    forbidden = [item for item in dates if item.year >= 2025]
    if forbidden:
        raise DuneProbeError(f"Forbidden 2025/2026 dates: {forbidden}")
    return tuple(dates)


def _date_values(dates: Sequence[date]) -> str:
    return ",\n        ".join(f"(DATE '{item.isoformat()}')" for item in dates)


def _asset_values(assets: Sequence[AssetSpec]) -> str:
    return ",\n        ".join(
        f"('{a.asset_id}', '{a.blockchain}', {a.contract_address}, '{a.case_type}')" for a in assets
    )


def build_supply_price_sql(dates: Sequence[date], assets: Sequence[AssetSpec] = ASSETS) -> str:
    if not dates:
        raise DuneProbeError("No snapshot dates supplied.")
    start, end = min(dates).isoformat(), max(dates).isoformat()
    addresses = ", ".join(a.contract_address for a in assets)
    return f"""WITH
snapshots(snapshot_date) AS (VALUES
        {_date_values(dates)}
),
assets(asset_id, blockchain, token_address, case_type) AS (VALUES
        {_asset_values(assets)}
),
balances_at_snapshot AS (
    SELECT
        a.asset_id,
        b.block_date AS snapshot_date,
        SUM(CASE WHEN b.balance > 0 THEN b.balance ELSE 0 END) AS onchain_supply_component,
        COUNT_IF(b.balance > 0) AS positive_holder_count
    FROM balances.erc20_daily b
    JOIN assets a
      ON b.blockchain = a.blockchain
     AND b.token_address = a.token_address
    JOIN snapshots s ON b.block_date = s.snapshot_date
    WHERE b.blockchain = 'ethereum'
      AND b.block_date BETWEEN DATE '{start}' AND DATE '{end}'
      AND b.token_address IN ({addresses})
    GROUP BY 1, 2
),
prices_at_snapshot AS (
    SELECT
        a.asset_id,
        CAST(p.timestamp AS DATE) AS snapshot_date,
        MAX_BY(p.price, p.timestamp) AS external_price_usd,
        MAX_BY(p.source, p.timestamp) AS price_source
    FROM prices_external.day p
    JOIN assets a
      ON p.blockchain = a.blockchain
     AND p.contract_address = a.token_address
    JOIN snapshots s ON CAST(p.timestamp AS DATE) = s.snapshot_date
    WHERE p.blockchain = 'ethereum'
      AND CAST(p.timestamp AS DATE) BETWEEN DATE '{start}' AND DATE '{end}'
      AND p.contract_address IN ({addresses})
    GROUP BY 1, 2
)
SELECT
    a.asset_id,
    a.case_type,
    s.snapshot_date,
    b.onchain_supply_component,
    b.positive_holder_count,
    p.external_price_usd,
    p.price_source,
    b.onchain_supply_component * p.external_price_usd AS onchain_component_market_value_usd,
    'NOT_CIRCULATING_SUPPLY_WITHOUT_HISTORICAL_EXCLUSIONS' AS interpretation
FROM assets a
CROSS JOIN snapshots s
LEFT JOIN balances_at_snapshot b ON b.asset_id = a.asset_id AND b.snapshot_date = s.snapshot_date
LEFT JOIN prices_at_snapshot p ON p.asset_id = a.asset_id AND p.snapshot_date = s.snapshot_date
ORDER BY s.snapshot_date, a.asset_id
"""


def build_top_holders_sql(
    dates: Sequence[date], assets: Sequence[AssetSpec] = ASSETS, top_n: int = 25
) -> str:
    if not 1 <= top_n <= 100:
        raise DuneProbeError("top_n must be in 1..100")
    start, end = min(dates).isoformat(), max(dates).isoformat()
    addresses = ", ".join(a.contract_address for a in assets)
    return f"""WITH
snapshots(snapshot_date) AS (VALUES
        {_date_values(dates)}
),
assets(asset_id, blockchain, token_address, case_type) AS (VALUES
        {_asset_values(assets)}
),
ranked AS (
    SELECT
        a.asset_id,
        a.case_type,
        b.block_date AS snapshot_date,
        b.address,
        b.balance,
        ROW_NUMBER() OVER (
            PARTITION BY a.asset_id, b.block_date
            ORDER BY b.balance DESC, b.address
        ) AS holder_rank
    FROM balances.erc20_daily b
    JOIN assets a
      ON b.blockchain = a.blockchain
     AND b.token_address = a.token_address
    JOIN snapshots s ON b.block_date = s.snapshot_date
    WHERE b.blockchain = 'ethereum'
      AND b.block_date BETWEEN DATE '{start}' AND DATE '{end}'
      AND b.token_address IN ({addresses})
      AND b.balance > 0
)
SELECT
    asset_id, case_type, snapshot_date, holder_rank, address, balance,
    'UNCLASSIFIED_HISTORICALLY' AS circulation_classification
FROM ranked
WHERE holder_rank <= {top_n}
ORDER BY snapshot_date, asset_id, holder_rank
"""


def validate_sql_safety(sql: str) -> None:
    lowered = sql.lower()
    for forbidden in ("2025-", "2026-", "insert ", "update ", "delete ", "drop ", "alter "):
        if forbidden in lowered:
            raise DuneProbeError(f"Forbidden SQL token: {forbidden!r}")
    for required in ("blockchain = 'ethereum'", "block_date", "token_address"):
        if required not in lowered:
            raise DuneProbeError(f"Missing bounded filter: {required}")


class DuneClient:
    def __init__(self, api_key: str, timeout_seconds: float = 30.0) -> None:
        if not api_key.strip():
            raise DuneProbeError("DUNE_API_KEY is empty.")
        self._api_key = api_key.strip()
        self.timeout_seconds = timeout_seconds

    def _request(
        self, method: str, path: str, payload: Mapping[str, object] | None = None
    ) -> dict[str, Any]:
        request = urllib.request.Request(
            API_BASE + path,
            data=None if payload is None else canonical_json_bytes(payload),
            method=method,
            headers={
                "X-Dune-Api-Key": self._api_key,
                "Content-Type": "application/json",
                "User-Agent": "spotbot-rd17-p0t-dune/1",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                content = response.read()
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")[:2000]
            raise DuneProbeError(f"Dune HTTP {error.code}: {detail}") from error
        except urllib.error.URLError as error:
            raise DuneProbeError(f"Dune network error: {error.reason}") from error
        parsed = json.loads(content)
        if not isinstance(parsed, dict):
            raise DuneProbeError("Dune response is not an object.")
        return cast(dict[str, Any], parsed)

    def run_sql(self, sql: str, max_wait_seconds: float = 150.0) -> dict[str, Any]:
        validate_sql_safety(sql)
        started = self._request("POST", "/v1/sql/execute", {"sql": sql, "performance": "small"})
        execution_id = str(started.get("execution_id") or "")
        if not execution_id:
            raise DuneProbeError(f"No execution_id: {started}")
        deadline = time.monotonic() + max_wait_seconds
        while True:
            result = self._request("GET", f"/v1/execution/{execution_id}/results?limit=1000")
            state = str(result.get("state") or "")
            if state in {"QUERY_STATE_COMPLETED", "QUERY_STATE_FAILED", "QUERY_STATE_CANCELLED"}:
                return result
            if time.monotonic() >= deadline:
                raise DuneProbeError(f"Execution timed out: {execution_id}")
            time.sleep(2.0)


def result_rows(payload: Mapping[str, object]) -> list[dict[str, Any]]:
    if str(payload.get("state") or "") != "QUERY_STATE_COMPLETED":
        raise DuneProbeError(f"Query failed: {payload.get('state')} {payload.get('error')}")
    result = payload.get("result")
    if not isinstance(result, Mapping) or not isinstance(result.get("rows"), list):
        raise DuneProbeError("Completed response has no rows.")
    return [
        {str(k): v for k, v in cast(Mapping[object, object], row).items()}
        for row in cast(list[object], result["rows"])
        if isinstance(row, Mapping)
    ]


def _positive(value: object) -> bool:
    try:
        number = float(cast(Any, value))
    except (TypeError, ValueError):
        return False
    return math.isfinite(number) and number > 0


def classify_probe(
    dates: Sequence[date],
    supply_rows: Sequence[Mapping[str, object]],
    holder_rows: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    expected = len(dates) * len(ASSETS)
    supply_keys = {
        (str(r.get("asset_id") or ""), str(r.get("snapshot_date") or "")[:10]) for r in supply_rows
    }
    holder_keys = {
        (str(r.get("asset_id") or ""), str(r.get("snapshot_date") or "")[:10]) for r in holder_rows
    }
    supply_ok = (
        len(supply_keys) == expected
        and len(supply_rows) == expected
        and all(_positive(r.get("onchain_supply_component")) for r in supply_rows)
    )
    price_ok = len(supply_rows) == expected and all(
        _positive(r.get("external_price_usd")) for r in supply_rows
    )
    holders_ok = len(holder_keys) == expected
    decision = DECISION_PASS if supply_ok and price_ok and holders_ok else DECISION_COVERAGE
    return {
        "schema_version": SCHEMA_VERSION,
        "decision": decision,
        "expected_asset_snapshot_rows": expected,
        "observed_supply_price_rows": len(supply_rows),
        "observed_holder_asset_snapshot_keys": len(holder_keys),
        "supply_component_coverage_passed": supply_ok,
        "external_price_coverage_passed": price_ok,
        "historical_top_holder_coverage_passed": holders_ok,
        "historical_noncirculating_exclusions_proven": False,
        "circulating_supply_proven": False,
        "top30_universe_reconstruction_authorized": False,
        "rd17_trading_run_authorized": False,
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
        "next_stage": "RD17_P0U_HISTORICAL_NONCIRCULATING_ADDRESS_EVIDENCE_PROBE"
        if decision == DECISION_PASS
        else "RD17_BLOCKED_PENDING_FREE_PIT_SOURCE",
    }
