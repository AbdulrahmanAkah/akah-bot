WITH bounds AS (
    SELECT
        TIMESTAMP '2023-03-01 00:00:00' AS start_utc,
        TIMESTAMP '2023-04-01 00:00:00' AS end_utc
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
    FROM ethereum.transactions
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
    FROM ethereum.blocks
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
