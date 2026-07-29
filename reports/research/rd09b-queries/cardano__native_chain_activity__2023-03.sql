WITH transaction_daily AS (
    SELECT
        CAST(date_trunc('day', block_time) AS date) AS day,
        count(*) FILTER (WHERE NOT is_invalid) AS successful_transaction_count,
        sum(fee_lovelace) FILTER (WHERE NOT is_invalid) AS native_fees_paid_lovelace,
        count(*) FILTER (WHERE NOT is_invalid) AS native_transfer_count
    FROM cardano.transaction
    WHERE block_time >= TIMESTAMP '2023-03-01 00:00:00 UTC'
      AND block_time < TIMESTAMP '2023-04-01 00:00:00 UTC'
    GROUP BY 1
),
block_daily AS (
    SELECT
        CAST(date_trunc('day', block_time) AS date) AS day,
        count(DISTINCT block_number) AS block_count
    FROM cardano.block
    WHERE block_time >= TIMESTAMP '2023-03-01 00:00:00 UTC'
      AND block_time < TIMESTAMP '2023-04-01 00:00:00 UTC'
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
