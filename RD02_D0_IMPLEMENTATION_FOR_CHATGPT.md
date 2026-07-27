# AMS RD02-D0 — Trade Lifecycle Diagnostics Implementation

## Scope

RD02-D0 is a post-simulation diagnostic stage for the registered `MD01-M05`
variant. It reconstructs every completed trade path from registered four-hour
bars and measures lifecycle behaviour without changing any trading decision.

## Locked inputs

- Upstream RD01 evidence commit: `a2ccccf31500af18b412011b150a264371bf5ba9`
- Upstream BF02 evidence commit: `630e2cbc6bc528be989c064855838a0457491abe`
- Registered research interval: 2021-01-01 through 2024-12-31
- Variant: `MD01-M05`
- Transaction cost: `0.002`

## Diagnostics

For each trade the stage records:

- reconstructed MFE and MAE with exact reconciliation to the immutable trade ledger;
- completed-bar time to MFE and MAE;
- peak-to-exit giveback and captured-MFE fraction;
- close-based time in profit;
- recovery after deep MAE;
- 5%, 10%, and 20% favourable-threshold timing;
- excursion ordering;
- holding-duration bucket;
- pre-registered descriptive flags for winner-to-loser reversals, severe giveback,
  early-peak giveback, deep-MAE recovery, and stale losers.

## Interpretation boundary

The flags are descriptive observations only. RD02-D0 does not test or authorize
stop-loss, breakeven, trailing-stop, partial-profit, time-exit, pyramiding,
averaging-down, leverage, Kelly sizing, production, or live-trading rules.

## Required validation

- all registered trades are represented exactly once;
- every trade has a non-empty four-hour path;
- MFE, MAE, gross return, and holding duration reconcile;
- financial fingerprints are unchanged before and after diagnostics;
- no 2025 or 2026 data are accessed;
- no candidate, selection, fill, trade, size, or exit decision is changed.
