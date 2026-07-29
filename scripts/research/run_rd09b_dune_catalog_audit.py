"""Create the credential-free RD09B catalog audit and manual SQL query pack."""

from __future__ import annotations

import csv
from collections import Counter
from io import StringIO
from pathlib import Path

from spotbot.research.rd09b_dune_acquisition import query_sha256
from spotbot.research.rd09b_dune_feasibility import (
    PILOT_RANGES,
    EntityClass,
    NamespaceCandidate,
    rank_namespaces,
)

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "reports" / "research"
QUERIES = REPORTS / "rd09b-queries"
MAPPING = REPORTS / "ams-rd09-economic-entity-mapping-v1.csv"

SUPPORTED_RAW = {
    "avalanche_c",
    "bitcoin",
    "cardano",
    "ethereum",
    "polkadot",
    "polygon",
}
NAMESPACE_ALIASES = {"avalanche": "avalanche_c"}


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


def evm_sql(namespace: str, start: str, end: str) -> str:
    return f"""WITH transaction_daily AS (
    SELECT
        CAST(date_trunc('day', block_time) AS date) AS day,
        count(*) FILTER (WHERE success) AS successful_transaction_count,
        approx_distinct("from") FILTER (WHERE success) AS unique_sending_addresses,
        approx_distinct("to") FILTER (WHERE success AND "to" IS NOT NULL)
            AS unique_receiving_addresses,
        sum(
            CASE
                WHEN success THEN
                    CAST(gas_used AS decimal(38, 0))
                    * CAST(gas_price AS decimal(38, 0))
                ELSE CAST(0 AS decimal(38, 0))
            END
        ) AS native_fees_paid_raw,
        count(*) FILTER (WHERE success AND value > 0) AS native_transfer_count
    FROM {namespace}.transactions
    WHERE block_time >= TIMESTAMP '{start} 00:00:00 UTC'
      AND block_time < TIMESTAMP '{end} 00:00:00 UTC'
    GROUP BY 1
),
active_daily AS (
    SELECT
        CAST(date_trunc('day', block_time) AS date) AS day,
        approx_distinct(address) AS unique_active_addresses
    FROM (
        SELECT block_time, "from" AS address
        FROM {namespace}.transactions
        WHERE block_time >= TIMESTAMP '{start} 00:00:00 UTC'
          AND block_time < TIMESTAMP '{end} 00:00:00 UTC'
          AND success
        UNION ALL
        SELECT block_time, "to" AS address
        FROM {namespace}.transactions
        WHERE block_time >= TIMESTAMP '{start} 00:00:00 UTC'
          AND block_time < TIMESTAMP '{end} 00:00:00 UTC'
          AND success
          AND "to" IS NOT NULL
    )
    GROUP BY 1
),
block_daily AS (
    SELECT
        CAST(date_trunc('day', time) AS date) AS day,
        count(DISTINCT number) AS block_count
    FROM {namespace}.blocks
    WHERE time >= TIMESTAMP '{start} 00:00:00 UTC'
      AND time < TIMESTAMP '{end} 00:00:00 UTC'
    GROUP BY 1
)
SELECT
    coalesce(transaction_daily.day, block_daily.day) AS day,
    transaction_daily.successful_transaction_count,
    transaction_daily.unique_sending_addresses,
    transaction_daily.unique_receiving_addresses,
    active_daily.unique_active_addresses,
    transaction_daily.native_fees_paid_raw,
    block_daily.block_count,
    transaction_daily.native_transfer_count
FROM transaction_daily
LEFT JOIN active_daily USING (day)
FULL OUTER JOIN block_daily USING (day)
ORDER BY day
"""


def bitcoin_sql(start: str, end: str) -> str:
    return f"""WITH transaction_daily AS (
    SELECT
        block_date AS day,
        count(*) AS successful_transaction_count,
        sum(fee) AS native_fees_paid,
        count(*) FILTER (WHERE NOT is_coinbase) AS native_transfer_count
    FROM bitcoin.transactions
    WHERE block_time >= TIMESTAMP '{start} 00:00:00 UTC'
      AND block_time < TIMESTAMP '{end} 00:00:00 UTC'
    GROUP BY 1
),
sender_daily AS (
    SELECT block_date AS day, approx_distinct(address) AS unique_sending_addresses
    FROM bitcoin.inputs
    WHERE block_time >= TIMESTAMP '{start} 00:00:00 UTC'
      AND block_time < TIMESTAMP '{end} 00:00:00 UTC'
      AND NOT is_coinbase
      AND address IS NOT NULL
    GROUP BY 1
),
receiver_daily AS (
    SELECT block_date AS day, approx_distinct(address) AS unique_receiving_addresses
    FROM bitcoin.outputs
    WHERE block_time >= TIMESTAMP '{start} 00:00:00 UTC'
      AND block_time < TIMESTAMP '{end} 00:00:00 UTC'
      AND address IS NOT NULL
    GROUP BY 1
),
active_daily AS (
    SELECT day, approx_distinct(address) AS unique_active_addresses
    FROM (
        SELECT block_date AS day, address
        FROM bitcoin.inputs
        WHERE block_time >= TIMESTAMP '{start} 00:00:00 UTC'
          AND block_time < TIMESTAMP '{end} 00:00:00 UTC'
          AND NOT is_coinbase
          AND address IS NOT NULL
        UNION ALL
        SELECT block_date AS day, address
        FROM bitcoin.outputs
        WHERE block_time >= TIMESTAMP '{start} 00:00:00 UTC'
          AND block_time < TIMESTAMP '{end} 00:00:00 UTC'
          AND address IS NOT NULL
    )
    GROUP BY 1
),
block_daily AS (
    SELECT date AS day, count(DISTINCT height) AS block_count
    FROM bitcoin.blocks
    WHERE time >= TIMESTAMP '{start} 00:00:00 UTC'
      AND time < TIMESTAMP '{end} 00:00:00 UTC'
    GROUP BY 1
)
SELECT
    transaction_daily.day,
    transaction_daily.successful_transaction_count,
    sender_daily.unique_sending_addresses,
    receiver_daily.unique_receiving_addresses,
    active_daily.unique_active_addresses,
    transaction_daily.native_fees_paid,
    block_daily.block_count,
    transaction_daily.native_transfer_count
FROM transaction_daily
LEFT JOIN sender_daily USING (day)
LEFT JOIN receiver_daily USING (day)
LEFT JOIN active_daily USING (day)
LEFT JOIN block_daily USING (day)
ORDER BY transaction_daily.day
"""


def cardano_sql(start: str, end: str) -> str:
    return f"""WITH transaction_daily AS (
    SELECT
        CAST(date_trunc('day', block_time) AS date) AS day,
        count(*) FILTER (WHERE NOT is_invalid) AS successful_transaction_count,
        sum(fee_lovelace) FILTER (WHERE NOT is_invalid) AS native_fees_paid_lovelace,
        count(*) FILTER (WHERE NOT is_invalid) AS native_transfer_count
    FROM cardano.transaction
    WHERE block_time >= TIMESTAMP '{start} 00:00:00 UTC'
      AND block_time < TIMESTAMP '{end} 00:00:00 UTC'
    GROUP BY 1
),
block_daily AS (
    SELECT
        CAST(date_trunc('day', block_time) AS date) AS day,
        count(DISTINCT block_number) AS block_count
    FROM cardano.block
    WHERE block_time >= TIMESTAMP '{start} 00:00:00 UTC'
      AND block_time < TIMESTAMP '{end} 00:00:00 UTC'
    GROUP BY 1
)
SELECT
    transaction_daily.day,
    transaction_daily.successful_transaction_count,
    CAST(NULL AS bigint) AS unique_sending_addresses,
    CAST(NULL AS bigint) AS unique_receiving_addresses,
    CAST(NULL AS bigint) AS unique_active_addresses,
    transaction_daily.native_fees_paid_lovelace,
    block_daily.block_count,
    transaction_daily.native_transfer_count
FROM transaction_daily
LEFT JOIN block_daily USING (day)
ORDER BY transaction_daily.day
"""


def sql_for(namespace: str, start: str, end: str) -> str:
    if namespace == "bitcoin":
        return bitcoin_sql(start, end)
    if namespace == "cardano":
        return cardano_sql(start, end)
    return evm_sql(namespace, start, end)


def classify_entity(row: dict[str, str]) -> str:
    asset_type = row["asset_type"]
    native_chain = row["native_chain"]
    contract = row["contract_address"]
    if asset_type == "NATIVE_L1" and native_chain:
        return EntityClass.NATIVE_CHAIN_ASSET
    if contract and native_chain.lower() in {"ethereum", "avalanche", "polygon"}:
        return EntityClass.EVM_CONTRACT_TOKEN
    if row["protocol_entity"]:
        return EntityClass.PROTOCOL_ENTITY
    if native_chain:
        return EntityClass.NON_EVM_TOKEN
    return EntityClass.UNSUPPORTED_CHAIN_OR_ENTITY


def main() -> None:
    with MAPPING.open(encoding="utf-8", newline="") as handle:
        upstream = list(csv.DictReader(handle))
    if len(upstream) != 41:
        raise RuntimeError("RD09 mapping universe changed")
    native_counts: Counter[str] = Counter()
    entity_rows: list[dict[str, object]] = []
    for row in upstream:
        entity_class = classify_entity(row)
        namespace = NAMESPACE_ALIASES.get(
            row["dune_blockchain_namespace"],
            row["dune_blockchain_namespace"],
        )
        mapping_effective = bool(row["mapping_start"] or row["asset_type"] == "NATIVE_L1")
        usable = (
            entity_class == EntityClass.NATIVE_CHAIN_ASSET
            and namespace in SUPPORTED_RAW
            and mapping_effective
        )
        if usable:
            native_counts[namespace] += 1
        entity_rows.append(
            {
                "canonical_symbol": row["canonical_symbol"],
                "entity_class": entity_class,
                "namespace": namespace,
                "contract_address": row["contract_address"],
                "mapping_start": row["mapping_start"],
                "mapping_end": row["mapping_end"],
                "effective_history_known": mapping_effective,
                "raw_catalog_supported": namespace in SUPPORTED_RAW,
                "pilot_mapping_usable": usable,
                "exclusion_reason": (
                    "" if usable else "NO_CAUSAL_NATIVE_OR_CONTRACT_EFFECTIVE_MAPPING"
                ),
                "silent_exclusion": False,
            }
        )
    candidates = [
        NamespaceCandidate(namespace, count, namespace in SUPPORTED_RAW)
        for namespace, count in sorted(native_counts.items())
    ]
    selected = rank_namespaces(candidates)
    selected_names = {candidate.namespace for candidate in selected}
    namespace_rows: list[dict[str, object]] = [
        {
            "namespace": candidate.namespace,
            "mapped_pit_asset_count": candidate.mapped_pit_asset_count,
            "raw_catalog_supported": candidate.raw_catalog_supported,
            "rank": index + 1,
            "selected": candidate.namespace in selected_names,
            "selection_reason": (
                "TOP_FOUR_COUNT_DESC_NAMESPACE_ASC"
                if candidate.namespace in selected_names
                else "OUTSIDE_TOP_FOUR"
            ),
        }
        for index, candidate in enumerate(
            sorted(
                candidates,
                key=lambda item: (-item.mapped_pit_asset_count, item.namespace),
            )
        )
    ]
    catalog_rows: list[dict[str, object]] = [
        {
            "namespace": "avalanche_c",
            "table_name": "avalanche_c.transactions",
            "table_type": "RAW_TRANSACTIONS",
            "timestamp_field": "block_time",
            "success_field": "success",
            "fee_fields": "gas_used|gas_price",
            "address_fields": "from|to",
            "contract_address_field": "to",
            "token_decimal_metadata": "NOT_USED_NATIVE_BUNDLE",
            "official_reference": (
                "https://docs.dune.com/data-catalog/evm/avalanche/raw/transactions"
            ),
        },
        {
            "namespace": "avalanche_c",
            "table_name": "avalanche_c.blocks",
            "table_type": "RAW_BLOCKS",
            "timestamp_field": "time",
            "success_field": "",
            "fee_fields": "",
            "address_fields": "",
            "contract_address_field": "",
            "token_decimal_metadata": "NOT_APPLICABLE",
            "official_reference": ("https://docs.dune.com/data-catalog/evm/avalanche/raw/blocks"),
        },
        {
            "namespace": "bitcoin",
            "table_name": "bitcoin.transactions|bitcoin.inputs|bitcoin.outputs|bitcoin.blocks",
            "table_type": "RAW_UTXO_TRANSACTIONS_AND_BLOCKS",
            "timestamp_field": "block_time|time",
            "success_field": "INCLUSION_IN_BLOCK",
            "fee_fields": "fee|total_fees",
            "address_fields": "inputs.address|outputs.address",
            "contract_address_field": "NOT_APPLICABLE",
            "token_decimal_metadata": "NOT_APPLICABLE",
            "official_reference": "https://docs.dune.com/data-catalog/bitcoin/overview",
        },
        {
            "namespace": "cardano",
            "table_name": "cardano.transaction|cardano.block",
            "table_type": "RAW_LEDGER_TRANSACTIONS_AND_BLOCKS",
            "timestamp_field": "block_time",
            "success_field": "is_invalid",
            "fee_fields": "fee_lovelace|total_fees_lovelace",
            "address_fields": "NOT_USED_UNTIL_RAW_UTXO_SCHEMA_REVIEW",
            "contract_address_field": "NOT_APPLICABLE_NATIVE_BUNDLE",
            "token_decimal_metadata": "NOT_APPLICABLE",
            "official_reference": "https://docs.dune.com/data-catalog/cardano/overview",
        },
        {
            "namespace": "ethereum",
            "table_name": "ethereum.transactions|ethereum.blocks",
            "table_type": "RAW_TRANSACTIONS_AND_BLOCKS",
            "timestamp_field": "block_time|time",
            "success_field": "success",
            "fee_fields": "gas_used|gas_price",
            "address_fields": "from|to",
            "contract_address_field": "to",
            "token_decimal_metadata": "NOT_USED_NATIVE_BUNDLE",
            "official_reference": "https://docs.dune.com/data-catalog/evm/ethereum/overview",
        },
    ]
    query_rows: list[dict[str, object]] = []
    for namespace in sorted(selected_names):
        for start, end in PILOT_RANGES:
            sql = sql_for(namespace, start, end)
            month = start[:7]
            query_id = f"{namespace}__native_chain_activity__{month}"
            path = QUERIES / f"{query_id}.sql"
            write_text(path, sql)
            query_rows.append(
                {
                    "query_id": query_id,
                    "namespace": namespace,
                    "metric_bundle": "NATIVE_CHAIN_ACTIVITY",
                    "pilot_start": start,
                    "pilot_end_exclusive": end,
                    "sql_path": str(path.relative_to(ROOT)),
                    "query_sha256": query_sha256(sql),
                    "estimated_credits": "UNKNOWN",
                    "execution_authorized": False,
                    "expected_csv_path": (f"data/research/rd09b/manual/{query_id}.csv"),
                    "status": "REGISTERED_NOT_EXECUTED",
                }
            )
    write_csv(
        REPORTS / "ams-rd09b-dune-catalog-v1.csv",
        catalog_rows,
        list(catalog_rows[0]),
    )
    write_csv(
        REPORTS / "ams-rd09b-namespace-selection-v1.csv",
        namespace_rows,
        list(namespace_rows[0]),
    )
    write_csv(
        REPORTS / "ams-rd09b-entity-mapping-v1.csv",
        entity_rows,
        list(entity_rows[0]),
    )
    write_csv(
        REPORTS / "ams-rd09b-query-registry-v1.csv",
        query_rows,
        list(query_rows[0]),
    )
    write_csv(
        REPORTS / "ams-rd09b-manual-query-registry-v1.csv",
        [
            {
                **row,
                "execution_order": index + 1,
                "manual_validation_required": True,
            }
            for index, row in enumerate(query_rows)
        ],
        [
            *list(query_rows[0]),
            "execution_order",
            "manual_validation_required",
        ],
    )
    manual_lines = [
        "# RD09B Dune Manual Query Pack",
        "",
        "No query was executed. Run only after a credential, zero-spend attestation,",
        "and a verified free-credit budget are available.",
        "",
    ]
    manual_lines.extend(
        f"{index + 1}. `{row['sql_path']}` -> `{row['expected_csv_path']}`"
        for index, row in enumerate(query_rows)
    )
    write_text(
        ROOT / "RD09B_DUNE_MANUAL_QUERY_PACK_FOR_CHATGPT.md",
        "\n".join(manual_lines) + "\n",
    )
    write_text(
        ROOT / "RD09B_DUNE_FEASIBILITY_FOR_CHATGPT.md",
        "# RD09B Dune Zero-Spend Feasibility\n\n"
        "The protocol separates native chains, contract tokens, non-EVM tokens, "
        "and protocol entities. It registers twelve bounded daily raw-chain queries "
        "without executing them or serializing credentials.\n",
    )
    print(f"SELECTED_NAMESPACES={','.join(sorted(selected_names))}")
    print(f"REGISTERED_QUERIES={len(query_rows)}")
    print("QUERY_EXECUTIONS=0")


if __name__ == "__main__":
    main()
