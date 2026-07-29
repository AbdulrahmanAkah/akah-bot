WITH bounds AS (
    SELECT
        TIMESTAMP '2022-03-01 00:00:00' AS start_utc,
        TIMESTAMP '2022-04-01 00:00:00' AS end_utc
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
