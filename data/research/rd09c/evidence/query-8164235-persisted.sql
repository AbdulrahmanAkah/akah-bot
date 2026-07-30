-- RD09C canonical native-chain daily template
-- namespace: cardano
-- allowed research interval: 2021-01-01 <= start_date < end_date <= 2025-01-01
-- end_date is exclusive
-- 2025 test and 2026 holdout are prohibited
WITH bounds AS (
    SELECT
        CAST('{{start_date}}' AS TIMESTAMP) AS start_utc,
        CAST('{{end_date}}' AS TIMESTAMP) AS end_utc
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
