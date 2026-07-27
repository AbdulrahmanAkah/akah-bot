# AMS RD02-D0 — Trade Lifecycle Diagnostics

## Executive result

- Status: `COMPLETE`
- Variant: `MD01-M05`
- Trade rows: `147`
- Financial invariance: `True`
- Maximum MFE reconstruction error: `0.0`
- Maximum MAE reconstruction error: `0.0`
- Trade logic changed: `NO`
- Exit rule authorized: `NO`
- ATI-V1 authorized: `NO`

## Aggregate lifecycle

- Win rate: `0.428571`
- Median net return: `-0.032754`
- Median holding hours: `228.000000`
- Median MFE: `0.102930`
- Median MAE: `-0.097059`
- Trades reaching at least 10% MFE: `74.0`
- 10% winners ending nonpositive: `19.0` (rate `0.256757`)
- Severe giveback after 10% MFE: `30.0` (rate `0.405405`)
- Deep-MAE trades: `73.0`; close recoveries: `26.0`
- Stale losers held at least 14 days: `20.0`

## Fold pattern stability

| Pattern | Aggregate denominator | Events | Rate | Observed folds | Valid folds |
|---|---:|---:|---:|---:|---:|
| `winner_to_loser_10pct` | 74 | 19 | 0.256757 | 3 | 3 |
| `severe_giveback_after_10pct` | 74 | 30 | 0.405405 | 3 | 3 |
| `early_peak_severe_giveback` | 74 | 16 | 0.216216 | 3 | 3 |
| `deep_mae_close_recovery` | 73 | 26 | 0.356164 | 3 | 3 |
| `deep_mae_profitable_exit` | 73 | 14 | 0.191781 | 3 | 3 |
| `stale_loser_14d` | 147 | 20 | 0.136054 | 3 | 3 |

## Interpretation boundary

- This stage measures completed trade paths after simulation.
- It does not test, select, or authorize a stop, breakeven, trailing, partial-profit, or time-exit rule.
- No M05 candidate, rank, entry, size, fill, exit, or portfolio decision is changed.
- No 2025 test data or 2026 holdout data are accessed.
- No production, live trading, MD02, Kelly, leverage, pyramiding, or averaging-down authorization.
