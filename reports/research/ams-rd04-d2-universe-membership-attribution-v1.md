# AMS RD04-D2 — Universe Membership Failure Attribution

## Executive result

- Status: `COMPLETE`
- Decision: `MIXED_MEMBERSHIP_FAILURE`
- Reason: `ENTRANT_AND_REMOVAL_EFFECTS_ARE_BOTH_MATERIAL`
- Variant: `MD01-M05`
- Fixed base-cost compounded return: `2.686147`
- Union base-cost compounded return: `0.555542`
- Intersection base-cost compounded return: `0.149880`
- PIT base-cost compounded return: `-0.481035`
- Entrant-addition Shapley effect: `-1.380760`
- Survivor-removal Shapley effect: `-1.786422`
- Membership interaction: `1.499690`
- RD04-D3 diagnostic research authorized: `True`
- Point-in-time universe baseline authorized: `False`
- Universe change authorized: `False`
- Trade logic changed: `False`
- ATI-V1 authorized: `False`

## Attribution contract

- The same trusted MD01-M05 simulator is used for all four schedules.
- FIXED keeps the original survivor 30 at every Monday rebalance.
- UNION adds PIT entrants without removing fixed survivors.
- INTERSECTION removes fixed survivors without adding PIT entrants.
- PIT applies both removal and addition exactly as observed in D0C.
- Shapley effects average both orders of the two membership changes.

## Safety boundary

- This is attribution, not a candidate universe or parameter search.
- No entry, exit, rank, weight, fill, cost, or cash rule changes.
- No 2025 test data or 2026 holdout data are accessed.
- No production, live, Kelly, leverage, pyramiding, or averaging down.
