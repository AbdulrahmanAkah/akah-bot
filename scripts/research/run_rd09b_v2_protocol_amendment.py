"""Register the pre-acquisition RD09B v2 amendment and frozen SQL pack."""

from __future__ import annotations

import csv
import json
from io import StringIO
from pathlib import Path

from spotbot.research.rd09b_market_level_protocol import (
    MAX_PAID_SPEND_USD,
    MAX_PILOT_CREDITS,
    MAX_SINGLE_QUERY_CREDITS,
    NAMESPACE_ORDER,
    NEXT_STAGE,
    ORIGINAL_RD09_BROAD_GATE,
    ORIGINAL_RD09_DUNE_SCORE,
    PERFORMANCE_TIER,
    PILOT_RANGES,
    PROTOCOL_DECISION,
    SCORE_WEIGHTS,
    STAGE_ID,
    registered_queries,
    sql_sha256,
    validate_protocol,
)

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "reports" / "research"
QUERY_DIR = REPORTS / "rd09b-v2-queries"


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


def _bounds(start: str, end: str) -> str:
    return (
        f"TIMESTAMP '{start.replace('T', ' ').replace('Z', '')}' AS start_utc,\n"
        f"        TIMESTAMP '{end.replace('T', ' ').replace('Z', '')}' AS end_utc"
    )


def _evm_sql(namespace: str, start: str, end: str) -> str:
    bounds = _bounds(start, end)
    return f"""WITH bounds AS (
    SELECT
        {bounds}
),
tx AS (
    SELECT
        block_time,
        success,
        "from" AS sender,
        "to" AS receiver,
        gas_used,
        gas_price,
        value
    FROM {namespace}.transactions
    CROSS JOIN bounds
    WHERE block_time >= bounds.start_utc
        AND block_time < bounds.end_utc
),
tx_aggregate AS (
    SELECT
        DATE_TRUNC('day', block_time) AS day,
        COUNT(*) FILTER (WHERE success) AS successful_transaction_count,
        COUNT(DISTINCT sender) FILTER (WHERE success) AS unique_sending_addresses,
        COUNT(DISTINCT receiver) FILTER (WHERE success AND receiver IS NOT NULL)
            AS unique_receiving_addresses,
        SUM(
            CASE WHEN success
                THEN CAST(gas_used AS DOUBLE) * CAST(gas_price AS DOUBLE)
                ELSE 0.0
            END
        ) AS native_fees_paid,
        COUNT(*) FILTER (WHERE success AND value > 0) AS native_transfer_count
    FROM tx
    GROUP BY 1
),
active_addresses AS (
    SELECT
        day,
        COUNT(DISTINCT address) AS unique_active_addresses
    FROM (
        SELECT DATE_TRUNC('day', block_time) AS day, sender AS address
        FROM tx
        WHERE success AND sender IS NOT NULL
        UNION ALL
        SELECT DATE_TRUNC('day', block_time) AS day, receiver AS address
        FROM tx
        WHERE success AND receiver IS NOT NULL
    )
    GROUP BY 1
),
blocks AS (
    SELECT
        DATE_TRUNC('day', time) AS day,
        COUNT(DISTINCT number) AS block_count
    FROM {namespace}.blocks
    CROSS JOIN bounds
    WHERE time >= bounds.start_utc
        AND time < bounds.end_utc
    GROUP BY 1
)
SELECT
    blocks.day,
    tx_aggregate.successful_transaction_count,
    tx_aggregate.unique_sending_addresses,
    tx_aggregate.unique_receiving_addresses,
    active_addresses.unique_active_addresses,
    tx_aggregate.native_fees_paid,
    blocks.block_count,
    tx_aggregate.native_transfer_count
FROM blocks
LEFT JOIN tx_aggregate ON blocks.day = tx_aggregate.day
LEFT JOIN active_addresses ON blocks.day = active_addresses.day
ORDER BY blocks.day
"""


def _bitcoin_sql(start: str, end: str) -> str:
    bounds = _bounds(start, end)
    return f"""WITH bounds AS (
    SELECT
        {bounds}
),
tx AS (
    SELECT
        DATE_TRUNC('day', block_time) AS day,
        COUNT(*) AS successful_transaction_count,
        SUM(COALESCE(fee, 0.0)) AS native_fees_paid,
        SUM(output_count) AS native_transfer_count
    FROM bitcoin.transactions
    CROSS JOIN bounds
    WHERE block_time >= bounds.start_utc
        AND block_time < bounds.end_utc
    GROUP BY 1
),
blocks AS (
    SELECT
        DATE_TRUNC('day', time) AS day,
        COUNT(DISTINCT height) AS block_count
    FROM bitcoin.blocks
    CROSS JOIN bounds
    WHERE time >= bounds.start_utc
        AND time < bounds.end_utc
    GROUP BY 1
)
SELECT
    blocks.day,
    tx.successful_transaction_count,
    CAST(NULL AS BIGINT) AS unique_sending_addresses,
    CAST(NULL AS BIGINT) AS unique_receiving_addresses,
    CAST(NULL AS BIGINT) AS unique_active_addresses,
    tx.native_fees_paid,
    blocks.block_count,
    tx.native_transfer_count
FROM blocks
LEFT JOIN tx ON blocks.day = tx.day
ORDER BY blocks.day
"""


def _cardano_sql(start: str, end: str) -> str:
    bounds = _bounds(start, end)
    return f"""WITH bounds AS (
    SELECT
        {bounds}
),
tx AS (
    SELECT
        DATE_TRUNC('day', block_time) AS day,
        COUNT(*) FILTER (WHERE NOT is_invalid) AS successful_transaction_count,
        SUM(CASE WHEN NOT is_invalid THEN fee_lovelace ELSE 0 END) AS native_fees_paid,
        SUM(CASE WHEN NOT is_invalid THEN output_count ELSE 0 END)
            AS native_transfer_count
    FROM cardano.transaction
    CROSS JOIN bounds
    WHERE block_time >= bounds.start_utc
        AND block_time < bounds.end_utc
    GROUP BY 1
),
blocks AS (
    SELECT
        DATE_TRUNC('day', block_time) AS day,
        COUNT(DISTINCT block_number) AS block_count
    FROM cardano.block
    CROSS JOIN bounds
    WHERE block_time >= bounds.start_utc
        AND block_time < bounds.end_utc
    GROUP BY 1
)
SELECT
    blocks.day,
    tx.successful_transaction_count,
    CAST(NULL AS BIGINT) AS unique_sending_addresses,
    CAST(NULL AS BIGINT) AS unique_receiving_addresses,
    CAST(NULL AS BIGINT) AS unique_active_addresses,
    tx.native_fees_paid,
    blocks.block_count,
    tx.native_transfer_count
FROM blocks
LEFT JOIN tx ON blocks.day = tx.day
ORDER BY blocks.day
"""


def _polkadot_sql(start: str, end: str) -> str:
    bounds = _bounds(start, end)
    return f"""WITH bounds AS (
    SELECT
        {bounds}
),
extrinsics AS (
    SELECT
        DATE_TRUNC('day', block_time) AS day,
        COUNT(*) FILTER (WHERE status) AS successful_transaction_count,
        COUNT(DISTINCT signer_ss58) FILTER (WHERE status AND signer_ss58 IS NOT NULL)
            AS unique_sending_addresses,
        SUM(CASE WHEN status THEN COALESCE(fee, 0.0) ELSE 0.0 END)
            AS native_fees_paid
    FROM polkadot.extrinsics
    CROSS JOIN bounds
    WHERE block_time >= bounds.start_utc
        AND block_time < bounds.end_utc
    GROUP BY 1
),
blocks AS (
    SELECT
        DATE_TRUNC('day', block_time) AS day,
        COUNT(DISTINCT number) AS block_count,
        SUM(transfer_count) AS native_transfer_count
    FROM polkadot.blocks
    CROSS JOIN bounds
    WHERE block_time >= bounds.start_utc
        AND block_time < bounds.end_utc
    GROUP BY 1
)
SELECT
    blocks.day,
    extrinsics.successful_transaction_count,
    extrinsics.unique_sending_addresses,
    CAST(NULL AS BIGINT) AS unique_receiving_addresses,
    CAST(NULL AS BIGINT) AS unique_active_addresses,
    extrinsics.native_fees_paid,
    blocks.block_count,
    blocks.native_transfer_count
FROM blocks
LEFT JOIN extrinsics ON blocks.day = extrinsics.day
ORDER BY blocks.day
"""


def query_sql(namespace: str, start: str, end: str) -> str:
    if namespace in {"ethereum", "avalanche_c"}:
        return _evm_sql(namespace, start, end)
    if namespace == "bitcoin":
        return _bitcoin_sql(start, end)
    if namespace == "cardano":
        return _cardano_sql(start, end)
    if namespace == "polkadot":
        return _polkadot_sql(start, end)
    raise ValueError("unregistered namespace")


def main() -> None:
    validate_protocol()
    query_rows: list[dict[str, object]] = []
    for spec in registered_queries():
        sql = query_sql(spec.namespace, spec.start, spec.end_exclusive)
        write_text(QUERY_DIR / spec.sql_filename, sql)
        query_rows.append(
            {
                "sequence": spec.sequence,
                "query_id_internal": spec.query_id_internal,
                "namespace": spec.namespace,
                "asset": spec.asset,
                "pilot_month": spec.pilot_month,
                "start_utc": spec.start,
                "end_exclusive_utc": spec.end_exclusive,
                "sql_path": f"reports/research/rd09b-v2-queries/{spec.sql_filename}",
                "query_sha256": sql_sha256(sql),
                "performance_tier": PERFORMANCE_TIER,
                "schema_review_status": "OFFICIAL_DOCUMENTATION_REVIEWED",
                "price_fields_present": False,
                "predictive_fields_present": False,
            }
        )
    namespace_rows = []
    for rank, (namespace, asset) in enumerate(NAMESPACE_ORDER, start=1):
        namespace_rows.append(
            {
                "rank": rank,
                "namespace": namespace,
                "asset": asset,
                "raw_catalog_supported": True,
                "mapping_effective_history_known": True,
                "selected_before_acquisition": True,
                "selection_reason": (
                    "FIFTH_PREVIOUS_DETERMINISTIC_RANK"
                    if namespace == "polkadot"
                    else "PREVIOUS_DETERMINISTIC_NAMESPACE_REGISTRY"
                ),
            }
        )
    write_csv(
        REPORTS / "ams-rd09b-v2-namespace-registry-v1.csv",
        namespace_rows,
        list(namespace_rows[0]),
    )
    write_csv(
        REPORTS / "ams-rd09b-v2-query-registry-v1.csv",
        query_rows,
        list(query_rows[0]),
    )
    report = {
        "stage": STAGE_ID,
        "status": "COMPLETE",
        "decision": PROTOCOL_DECISION,
        "next_stage": NEXT_STAGE,
        "previous_rd09b_decision_superseded": False,
        "previous_rd09b_blocker_resolved_operationally": True,
        "amendment_timing": "PRE_ACQUISITION",
        "pilot_output_observed_before_amendment": False,
        "previous_broad_gate_minimum_assets": 20,
        "previous_query_pack_maximum_assets": 4,
        "previous_sector_gate_minimum_assets": 15,
        "valid_historical_contract_token_mappings": 0,
        "market_level_not_cross_sectional": True,
        "alpha_test": False,
        "namespaces": [item[0] for item in NAMESPACE_ORDER],
        "pilot_ranges": PILOT_RANGES,
        "registered_query_count": len(query_rows),
        "execution_order": [row["query_id_internal"] for row in query_rows],
        "performance_tier": PERFORMANCE_TIER,
        "max_pilot_credits": MAX_PILOT_CREDITS,
        "max_single_query_credits": MAX_SINGLE_QUERY_CREDITS,
        "max_paid_spend_usd": MAX_PAID_SPEND_USD,
        "score_weights": SCORE_WEIGHTS,
        "original_rd09_dune_score": ORIGINAL_RD09_DUNE_SCORE,
        "original_rd09_broad_coverage_gate": ORIGINAL_RD09_BROAD_GATE,
        "signal_computation_authorized": False,
        "label_computation_authorized": False,
        "portfolio_construction_authorized": False,
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
    }
    write_text(
        REPORTS / "ams-rd09b-v2-protocol-amendment-v1.json",
        json.dumps(report, indent=2, sort_keys=True) + "\n",
    )
    write_text(
        ROOT / "RD09B_V2_PROTOCOL_AMENDMENT_FOR_CHATGPT.md",
        "# RD09B v2 Protocol Amendment\n\n"
        "Status: COMPLETE\n\n"
        "Decision: RD09B_MARKET_LEVEL_NATIVE_CHAIN_PROTOCOL_REGISTERED\n\n"
        "The amendment was frozen before acquisition. It defines a market-level, "
        "non-predictive feasibility pilot for five native chains and 15 fixed "
        "namespace-month SQL queries. The original RD09 and RD09B evidence remains "
        "unchanged.\n",
    )
    print(f"RD09B_V2_PROTOCOL_STATUS={report['status']}")
    print(f"RD09B_V2_PROTOCOL_DECISION={report['decision']}")
    print(f"REGISTERED_QUERY_COUNT={len(query_rows)}")


if __name__ == "__main__":
    main()
