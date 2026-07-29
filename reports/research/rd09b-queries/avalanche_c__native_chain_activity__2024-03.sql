WITH transaction_daily AS (
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
    FROM avalanche_c.transactions
    WHERE block_time >= TIMESTAMP '2024-03-01 00:00:00 UTC'
      AND block_time < TIMESTAMP '2024-04-01 00:00:00 UTC'
    GROUP BY 1
),
active_daily AS (
    SELECT
        CAST(date_trunc('day', block_time) AS date) AS day,
        approx_distinct(address) AS unique_active_addresses
    FROM (
        SELECT block_time, "from" AS address
        FROM avalanche_c.transactions
        WHERE block_time >= TIMESTAMP '2024-03-01 00:00:00 UTC'
          AND block_time < TIMESTAMP '2024-04-01 00:00:00 UTC'
          AND success
        UNION ALL
        SELECT block_time, "to" AS address
        FROM avalanche_c.transactions
        WHERE block_time >= TIMESTAMP '2024-03-01 00:00:00 UTC'
          AND block_time < TIMESTAMP '2024-04-01 00:00:00 UTC'
          AND success
          AND "to" IS NOT NULL
    )
    GROUP BY 1
),
block_daily AS (
    SELECT
        CAST(date_trunc('day', time) AS date) AS day,
        count(DISTINCT number) AS block_count
    FROM avalanche_c.blocks
    WHERE time >= TIMESTAMP '2024-03-01 00:00:00 UTC'
      AND time < TIMESTAMP '2024-04-01 00:00:00 UTC'
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
