WITH transaction_daily AS (
    SELECT
        block_date AS day,
        count(*) AS successful_transaction_count,
        sum(fee) AS native_fees_paid,
        count(*) FILTER (WHERE NOT is_coinbase) AS native_transfer_count
    FROM bitcoin.transactions
    WHERE block_time >= TIMESTAMP '2024-03-01 00:00:00 UTC'
      AND block_time < TIMESTAMP '2024-04-01 00:00:00 UTC'
    GROUP BY 1
),
sender_daily AS (
    SELECT block_date AS day, approx_distinct(address) AS unique_sending_addresses
    FROM bitcoin.inputs
    WHERE block_time >= TIMESTAMP '2024-03-01 00:00:00 UTC'
      AND block_time < TIMESTAMP '2024-04-01 00:00:00 UTC'
      AND NOT is_coinbase
      AND address IS NOT NULL
    GROUP BY 1
),
receiver_daily AS (
    SELECT block_date AS day, approx_distinct(address) AS unique_receiving_addresses
    FROM bitcoin.outputs
    WHERE block_time >= TIMESTAMP '2024-03-01 00:00:00 UTC'
      AND block_time < TIMESTAMP '2024-04-01 00:00:00 UTC'
      AND address IS NOT NULL
    GROUP BY 1
),
active_daily AS (
    SELECT day, approx_distinct(address) AS unique_active_addresses
    FROM (
        SELECT block_date AS day, address
        FROM bitcoin.inputs
        WHERE block_time >= TIMESTAMP '2024-03-01 00:00:00 UTC'
          AND block_time < TIMESTAMP '2024-04-01 00:00:00 UTC'
          AND NOT is_coinbase
          AND address IS NOT NULL
        UNION ALL
        SELECT block_date AS day, address
        FROM bitcoin.outputs
        WHERE block_time >= TIMESTAMP '2024-03-01 00:00:00 UTC'
          AND block_time < TIMESTAMP '2024-04-01 00:00:00 UTC'
          AND address IS NOT NULL
    )
    GROUP BY 1
),
block_daily AS (
    SELECT date AS day, count(DISTINCT height) AS block_count
    FROM bitcoin.blocks
    WHERE time >= TIMESTAMP '2024-03-01 00:00:00 UTC'
      AND time < TIMESTAMP '2024-04-01 00:00:00 UTC'
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
