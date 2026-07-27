# AMS RD04-D3 — Membership Failure Diagnostics

## Executive result

- Status: `COMPLETE`
- Decision: `ENTRANT_EDGE_AND_SURVIVOR_DISPLACEMENT_CONFIRMED`
- Reason: `NEGATIVE_ENTRANT_EDGE_AND_POSITIVE_REMOVED_SURVIVOR_OPPORTUNITY`
- Variant: `MD01-M05`
- Entrant net PnL in UNION: `-97193.917660`
- Entrant net PnL in PIT: `-94301.543596`
- Removed-survivor net PnL in FIXED: `99489.776919`
- Removed-survivor net PnL in UNION: `90613.379640`
- Common-member UNION minus FIXED PnL: `-57335.308539`
- Common-member PIT minus INTERSECTION PnL: `23754.231915`
- RD04-D4 hypothesis registration authorized: `True`
- Point-in-time universe baseline authorized: `False`
- Candidate universe authorized: `False`
- Universe change authorized: `False`
- Trade logic changed: `False`
- ATI-V1 authorized: `False`

## Diagnostic contract

- No portfolio simulation is rerun in D3.
- D3 consumes only frozen D0C, D1, and D2 evidence.
- Every trade is classified by its active Monday membership state.
- Entrants, removed survivors, and common-member path effects are separated.
- Rank and tenure buckets are descriptive and are not optimized.

## Safety boundary

- No universe, rank, weight, entry, exit, fill, cost, or cash rule changes.
- No candidate universe or parameter optimization is created.
- No 2025 test data or 2026 holdout data are accessed.
- No production, live, Kelly, leverage, pyramiding, or averaging down.
