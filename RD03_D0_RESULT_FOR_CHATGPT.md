# AMS RD03-D0 — Alignment-Tier Stability Diagnostics

## Executive result

- Status: `COMPLETE`
- Variant: `MD01-M05`
- Trade rows: `147`
- Financial invariance: `True`
- Decision: `INCONCLUSIVE`
- RD03-D1 weight-replay research authorized: `False`
- Alignment weight change authorized: `NO`
- Trade logic changed: `NO`
- ATI-V1 authorized: `NO`

## Aggregate tier evidence

| Tier | Trades | Win rate | Mean return | Median return | Total net PnL | Profit factor |
|---|---:|---:|---:|---:|---:|---:|
| `FOUR_HOUR_ONLY` | 5 | 0.400000 | 0.101942 | -0.041141 | 7063.313702 | 7.577605 |
| `FULL` | 117 | 0.461538 | 0.075498 | -0.032754 | 299452.656651 | 2.219924 |
| `MEDIUM` | 25 | 0.280000 | -0.040108 | -0.028513 | -22540.348380 | 0.378140 |

## MEDIUM versus FULL by walk-forward fold

| Fold | MEDIUM trades | FULL trades | Mean gap | Median gap | Win-rate gap | Outlier-adjusted gap | Valid |
|---|---:|---:|---:|---:|---:|---:|---|
| `WF01` | 7 | 19 | 0.052547 | 0.081034 | 0.022556 | 0.091592 | `True` |
| `WF02` | 10 | 48 | -0.072739 | -0.005097 | -0.200000 | -0.014976 | `True` |
| `WF03` | 8 | 50 | -0.231826 | -0.164547 | -0.250000 | -0.175028 | `True` |

## Pre-registered decision gate

- Valid comparison folds: `3` / `3`
- All valid fold mean gaps negative: `False`
- MEDIUM median weaker folds: `2`
- MEDIUM win rate weaker folds: `2`
- MEDIUM negative-mean folds: `2`
- Outlier-robust weaker folds: `2`
- FOUR_HOUR_ONLY sample sufficient: `False`

## Interpretation boundary

- D0 measures completed M05 trades after simulation.
- It does not change alignment classification, target weights, ranking, entries, fills, exits, or portfolio cash.
- A positive D0 gate authorizes only RD03-D1 full-portfolio weight replay.
- No alignment multiplier, production use, live trading, MD02, Kelly, leverage, pyramiding, or averaging down is authorized.
- No 2025 test data or 2026 holdout data are accessed.
