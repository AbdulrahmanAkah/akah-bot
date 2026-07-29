"""Frozen RD09B v2 market-level native-chain feasibility protocol."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Final

STAGE_ID: Final = "RD09B-P0A-MARKET-LEVEL-NATIVE-CHAIN-FEASIBILITY-AMENDMENT"
PROTOCOL_DECISION: Final = "RD09B_MARKET_LEVEL_NATIVE_CHAIN_PROTOCOL_REGISTERED"
NEXT_STAGE: Final = "RD09B-M1-DUNE-NATIVE-CHAIN-PILOT"
MAX_PILOT_CREDITS: Final = 500.0
MAX_SINGLE_QUERY_CREDITS: Final = 100.0
MAX_PAID_SPEND_USD: Final = 0.0
PERFORMANCE_TIER: Final = "small"
ORIGINAL_RD09_DUNE_SCORE: Final = 65
ORIGINAL_RD09_BROAD_GATE: Final = False

NAMESPACE_ORDER: Final[tuple[tuple[str, str], ...]] = (
    ("bitcoin", "BTC"),
    ("ethereum", "ETH"),
    ("cardano", "ADA"),
    ("avalanche_c", "AVAX"),
    ("polkadot", "DOT"),
)
PILOT_RANGES: Final[tuple[tuple[str, str], ...]] = (
    ("2022-03-01T00:00:00Z", "2022-04-01T00:00:00Z"),
    ("2023-03-01T00:00:00Z", "2023-04-01T00:00:00Z"),
    ("2024-03-01T00:00:00Z", "2024-04-01T00:00:00Z"),
)
SCORE_WEIGHTS: Final[dict[str, int]] = {
    "causal_integrity": 30,
    "pilot_namespace_coverage": 25,
    "reproducibility": 15,
    "economic_information_independence": 15,
    "cost_licensing_suitability": 10,
    "daily_frequency_latency_suitability": 5,
}
METRIC_FIELDS: Final[tuple[str, ...]] = (
    "successful_transaction_count",
    "unique_sending_addresses",
    "unique_receiving_addresses",
    "unique_active_addresses",
    "native_fees_paid",
    "block_count",
    "native_transfer_count",
)


@dataclass(frozen=True)
class QuerySpec:
    """One immutable namespace-month SQL unit."""

    sequence: int
    query_id_internal: str
    namespace: str
    asset: str
    start: str
    end_exclusive: str
    sql_filename: str

    @property
    def pilot_month(self) -> str:
        return self.start[:7]


def registered_queries() -> tuple[QuerySpec, ...]:
    """Return the preregistered sequential execution order."""
    rows: list[QuerySpec] = []
    sequence = 1
    for start, end_exclusive in PILOT_RANGES:
        year = start[:4]
        for namespace, asset in NAMESPACE_ORDER:
            query_id = f"{namespace}_{year}_03"
            rows.append(
                QuerySpec(
                    sequence=sequence,
                    query_id_internal=query_id,
                    namespace=namespace,
                    asset=asset,
                    start=start,
                    end_exclusive=end_exclusive,
                    sql_filename=f"{query_id}.sql",
                )
            )
            sequence += 1
    return tuple(rows)


def validate_protocol() -> None:
    """Fail closed if the amendment drifts."""
    queries = registered_queries()
    if len(NAMESPACE_ORDER) != 5 or len(PILOT_RANGES) != 3 or len(queries) != 15:
        raise RuntimeError("RD09B v2 registered query cardinality changed")
    if sum(SCORE_WEIGHTS.values()) != 100:
        raise RuntimeError("RD09B v2 score weights changed")
    if len({query.query_id_internal for query in queries}) != 15:
        raise RuntimeError("duplicate RD09B v2 query identity")
    if any(query.end_exclusive > "2024-12-31T23:59:59Z" for query in queries):
        raise RuntimeError("RD09B v2 request crosses research lock")
    if NAMESPACE_ORDER[-1] != ("polkadot", "DOT"):
        raise RuntimeError("Polkadot must be preregistered as the fifth namespace")


def sql_sha256(sql: str) -> str:
    return hashlib.sha256(sql.encode("utf-8")).hexdigest()


def namespace_coverage_points(passing_namespace_count: int) -> int:
    if not 0 <= passing_namespace_count <= 5:
        raise ValueError("passing namespace count outside registered bounds")
    if passing_namespace_count == 5:
        return 25
    if passing_namespace_count == 4:
        return 20
    if passing_namespace_count == 3:
        return 10
    return 0


def market_level_score(
    *,
    passing_namespace_count: int,
    causal_integrity_passed: bool,
    reproducibility_passed: bool,
    independent_information: bool,
    zero_paid_spend: bool,
    daily_frequency_suitable: bool,
) -> int:
    """Calculate the non-predictive market-level feasibility score."""
    return (
        (30 if causal_integrity_passed else 0)
        + namespace_coverage_points(passing_namespace_count)
        + (15 if reproducibility_passed else 0)
        + (15 if independent_information else 0)
        + (10 if zero_paid_spend else 0)
        + (5 if daily_frequency_suitable else 0)
    )
