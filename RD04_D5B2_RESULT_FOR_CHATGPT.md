# AMS RD04-D5B2 — Structural Stop Evaluation

## Executive result

- Status: `COMPLETE`
- Decision: `STRUCTURAL_STOP_EDGE_NOT_CONFIRMED`
- PIT base compounded-return delta: `0.14798842236375032`
- PIT base expectancy delta: `76.46523597601754`
- PIT mean-drawdown reduction: `0.09336308058567527`
- PIT trade CVaR10 improvement: `0.12707453506600966`
- Improved PIT base folds: `1`
- PIT stress compounded-return delta: `0.10811248939783058`

## Validation

- Generated control equals the original M05 engine exactly.
- Generated control reproduces the committed RD04-D1 aggregates.
- All control and treatment ledgers reconcile.
- Entry logic and entry-weight source expressions are unchanged.

## Safety boundary

- Research-only exit overlay; no production authorization.
- No PIT baseline, universe, ranking, entry, or weight authorization.
- No 2025 test or 2026 holdout access.
