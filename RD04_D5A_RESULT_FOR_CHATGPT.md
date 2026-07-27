# AMS RD04-D5A — Causal Quote-Turnover Liquidity Floor

## Executive result

- Status: `COMPLETE`
- Decision: `LIQUIDITY_FLOOR_FAIL`
- Reason: `LIQUIDITY_FLOOR_FAILED_STRUCTURAL_BASE_EDGE_OR_FOLD_GATE`
- Native quote-turnover contract passed: `True`
- Frozen floor: `250000 USDT` median over 30 completed days
- Quote-turnover approximation used: `False`
- Control base-cost compounded return: `-0.481035`
- Treatment base-cost compounded return: `-0.536161`
- Treatment base-cost expectancy: `-279.418044`
- Treatment base-cost profit factor: `0.7978429750880108`
- Treatment stress-cost compounded return: `-0.596523`
- Improved base-cost folds: `2`
- Liquidity-floor change authorized: `False`
- Point-in-time universe baseline authorized: `False`
- Trade logic changed: `False`
- ATI-V1 authorized: `False`

## Contract

- Native KuCoin Spot 4H field seven is used as USDT transaction amount.
- Native OHLC and base volume must match every frozen D0C source row.
- `close * base volume` is never used as quote turnover.
- Only completed observations available by Monday 00:00 UTC are used.

## Safety boundary

- No symbol blacklist, rank threshold, tenure threshold, or parameter search.
- No entry, exit, weight, rank, cluster, crisis, fill, or cash-rule change.
- No 2025 test data or 2026 holdout data are accessed.
- No production, live, leverage, Kelly, pyramiding, or averaging down.
