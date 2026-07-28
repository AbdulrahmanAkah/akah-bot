# AMS RD04-D5D2 — PIT Equal-Weight Benchmark

## Executive result

- Status: `COMPLETE`
- Decision: `M05_RELATIVE_EDGE_NOT_CONFIRMED`
- Reason: `M05_FAILED_BASE_RELATIVE_RETURN_EXPECTANCY_DRAWDOWN_OR_FOLD_GATE`
- M05 control replay passed: `True`
- Matched weekly intervals passed: `True`
- Base return delta, M05 minus equal-weight: `-0.133326`
- Base weekly expectancy delta: `-0.003431`
- Base drawdown improvement: `0.006498`
- Base fold wins: `1/3`
- Stress return delta: `-0.177763`
- Stress weekly expectancy delta: `-0.004096`
- Next stage: `RD04-D5B0-V5R1-ATR-GRID-RECOVERY`
- Point-in-time universe baseline authorized: `False`
- Trade logic changed: `False`
- ATI-V1 authorized: `False`

## Accounting contract

- Equal weight is applied only to causally daily-ready PIT members.
- Holdings drift between weekly Monday rebalances.
- Turnover is measured against pre-trade drifted holdings.
- Missing held-asset returns are data-contract failures, never zero returns.
- Initial capital remains 100000 per fold; fees reduce equity.
- Every fold ends with full costed liquidation.
- Expectancy is matched Monday-to-Monday portfolio return for both portfolios.

## Safety boundary

- No 2025 test or 2026 holdout access.
- No parameter search, outcome-based filter, or survivor universe.
- No universe, ranking, weighting, entry, exit, production, live, or ATI change.
