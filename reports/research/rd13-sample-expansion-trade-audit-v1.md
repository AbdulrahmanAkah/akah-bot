# RD13 Trade Audit

All samples below reconcile to the generated ledgers. Entry fills occur after
the close-time signal, use next-bar execution, include fee and adverse slippage,
and preserve non-negative shared cash with at most two long Spot positions.

| configuration | asset | entry | exit | exit reason | net PnL |
|---|---|---|---|---|---:|
| RD12_BASELINE | BTC/USDT | 2020-07-24T00:00:00Z | 2020-08-23T00:00:00Z | time_stop_30_bars | 5480.440740 |
| RD12_BASELINE | BTC/USDT | 2020-07-24T00:00:00Z | 2020-08-23T00:00:00Z | time_stop_30_bars | 5480.440740 |
| RD12_BASELINE | BTC/USDT | 2021-11-10T00:00:00Z | 2021-11-17T00:00:00Z | stop_loss | -1509.211339 |
| RD12_BASELINE | ETH/USDT | 2020-06-01T00:00:00Z | 2020-06-16T00:00:00Z | stop_loss | -1054.760254 |
| RD12_BASELINE | ETH/USDT | 2020-07-24T00:00:00Z | 2020-08-23T00:00:00Z | time_stop_30_bars | 7914.000743 |
| RD12_BASELINE | ETH/USDT | 2020-06-01T00:00:00Z | 2020-06-16T00:00:00Z | stop_loss | -1054.760254 |
| RD12_BASELINE | ADA/USDT | 2020-05-21T00:00:00Z | 2020-06-20T00:00:00Z | rsi_failure_below_45 | 3678.882104 |
| RD12_BASELINE | ADA/USDT | 2020-05-21T00:00:00Z | 2020-06-20T00:00:00Z | rsi_failure_below_45 | 3678.882104 |
| RD12_BASELINE | ADA/USDT | 2021-04-15T00:00:00Z | 2021-04-19T00:00:00Z | stop_loss | -1424.695598 |
| RD12_E02_NO_MEDIUM_TERM_ALIGNMENT | ADA/USDT | 2020-01-30T00:00:00Z | 2020-02-14T00:00:00Z | stop_loss | -1015.761286 |
| RD12_E03_NO_RSI_ENTRY_FILTER | ETH/USDT | 2020-02-16T00:00:00Z | 2020-02-17T00:00:00Z | stop_loss | -1020.192137 |
| RD12_E04_NO_VOLUME_CONFIRMATION | ETH/USDT | 2020-05-30T00:00:00Z | 2020-06-17T00:00:00Z | rsi_failure_below_45 | 459.725783 |
| RD12_X03_NO_RSI_EXIT | ETH/USDT | 2020-06-01T00:00:00Z | 2020-06-16T00:00:00Z | stop_loss | -1054.760254 |
| RD12_X04_NO_TIME_STOP | ETH/USDT | 2020-06-01T00:00:00Z | 2020-06-16T00:00:00Z | stop_loss | -1054.760254 |
| RD12_G01_BREAKOUT_CORE_ONLY | ADA/USDT | 2020-01-23T00:00:00Z | 2020-02-14T00:00:00Z | stop_loss | -1015.936073 |

The first simultaneous ranking and slot/cash decisions are retained in each
full portfolio ranked-signals, orders, positions, and cash-ledger artifact.
The descriptive best and weakest variants are reported only as attribution;
no variant was selected. Chronological validity is PASS for every run.
