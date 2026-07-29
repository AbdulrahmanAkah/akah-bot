WITH bounds AS (
    SELECT
        TIMESTAMP '2023-03-01 00:00:00' AS start_utc,
        TIMESTAMP '2023-04-01 00:00:00' AS end_utc
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
