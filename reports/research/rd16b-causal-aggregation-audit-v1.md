# RD16-B Causal Aggregation Audit v1

## Aggregation audit

| Asset | Target | Children | Accepted | Edge drops | Gap drops | Target gaps |
|---|---:|---:|---:|---:|---:|---:|
| BTC/USDT | 4h | 4 | 13152 | 0 | 0 | 0 |
| BTC/USDT | 1d | 24 | 2192 | 0 | 0 | 0 |
| BTC/USDT | 1w | 168 | 312 | 2 | 0 | 0 |
| ETH/USDT | 4h | 4 | 13152 | 0 | 0 | 0 |
| ETH/USDT | 1d | 24 | 2192 | 0 | 0 | 0 |
| ETH/USDT | 1w | 168 | 312 | 2 | 0 | 0 |
| SOL/USDT | 4h | 4 | 7212 | 0 | 0 | 0 |
| SOL/USDT | 1d | 24 | 1202 | 0 | 0 | 0 |
| SOL/USDT | 1w | 168 | 171 | 2 | 0 | 0 |
| LINK/USDT | 4h | 4 | 9372 | 0 | 0 | 0 |
| LINK/USDT | 1d | 24 | 1562 | 0 | 0 | 0 |
| LINK/USDT | 1w | 168 | 222 | 2 | 0 | 0 |
| AVAX/USDT | 4h | 4 | 8292 | 0 | 0 | 0 |
| AVAX/USDT | 1d | 24 | 1382 | 0 | 0 | 0 |
| AVAX/USDT | 1w | 168 | 197 | 2 | 0 | 0 |
| NEAR/USDT | 4h | 4 | 7212 | 0 | 0 | 0 |
| NEAR/USDT | 1d | 24 | 1202 | 0 | 0 | 0 |
| NEAR/USDT | 1w | 168 | 171 | 2 | 0 | 0 |

## Causal alignment audit

| Asset | Context | Rows | Future | Stale | Max age hours |
|---|---:|---:|---:|---:|---:|
| BTC/USDT | 4h | 52297 | 0 | 0 | 3.00 |
| BTC/USDT | 1d | 52297 | 0 | 0 | 23.00 |
| BTC/USDT | 1w | 52297 | 0 | 0 | 167.00 |
| ETH/USDT | 4h | 52297 | 0 | 0 | 3.00 |
| ETH/USDT | 1d | 52297 | 0 | 0 | 23.00 |
| ETH/USDT | 1w | 52297 | 0 | 0 | 167.00 |
| SOL/USDT | 4h | 28609 | 0 | 0 | 3.00 |
| SOL/USDT | 1d | 28609 | 0 | 0 | 23.00 |
| SOL/USDT | 1w | 28609 | 0 | 0 | 167.00 |
| LINK/USDT | 4h | 37177 | 0 | 0 | 3.00 |
| LINK/USDT | 1d | 37177 | 0 | 0 | 23.00 |
| LINK/USDT | 1w | 37177 | 0 | 0 | 167.00 |
| AVAX/USDT | 4h | 32977 | 0 | 0 | 3.00 |
| AVAX/USDT | 1d | 32977 | 0 | 0 | 23.00 |
| AVAX/USDT | 1w | 32977 | 0 | 0 | 167.00 |
| NEAR/USDT | 4h | 28609 | 0 | 0 | 3.00 |
| NEAR/USDT | 1d | 28609 | 0 | 0 | 23.00 |
| NEAR/USDT | 1w | 28609 | 0 | 0 | 167.00 |

## Enforcement

No incomplete 4H, 1D or 1W candle is accepted. No missing child candle
is synthesized. No context timestamp may exceed the corresponding 1H
signal close. Raw and derived Parquet files remain local; the committed
artifacts contain hashes, row counts and audit summaries only.
