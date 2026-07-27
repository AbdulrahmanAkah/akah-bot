# RD04-D5A — Causal KuCoin Quote-Turnover Liquidity Floor

## Scope

- Acquire native KuCoin Spot 4H klines only for the frozen 2021–2024 D0C source pairs.
- Preserve the native seventh kline field as USDT transaction amount.
- Prove native OHLC and base volume match every frozen D0C 4H source row.
- Never approximate quote turnover with `close * base volume`.
- Calculate the frozen 30-completed-day median quote turnover before Monday 00:00 UTC.
- Compare the unchanged PIT MD01-M05 replay with and without the registered 250,000 USDT floor.
- Apply zero, 0.2%, and 0.4% transaction-cost modes.

## Registered gates

- Structural integrity and exact control replay against RD04-D1.
- Positive registered base edge and the original concentration/trade-count gates.
- Positive 0.4% stress-cost return and expectancy.
- Base-cost net-return improvement in at least two of three folds.

## Safety

- No symbol blacklist, rank threshold, tenure threshold, or parameter search.
- No entry, exit, weight, rank, cluster, crisis, fill, or cash-rule change.
- A pass authorizes research continuation only, never a live or production change.
- No 2025 test data or 2026 holdout access.
