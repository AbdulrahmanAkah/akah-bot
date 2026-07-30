-- RD09C canonical native-chain daily template
-- namespace: polkadot
-- allowed research interval: 2021-01-01 <= start_date < end_date <= 2025-01-01
-- end_date is exclusive
-- 2025 test and 2026 holdout are prohibited
WITH bounds AS (
    SELECT
        CAST('{{start_date}}' AS TIMESTAMP) AS start_utc,
        CAST('{{end_date}}' AS TIMESTAMP) AS end_utc
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
