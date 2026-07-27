# AMS RD04-D5D1 — BF01 Protocol Adjudication

## Executive result

- Status: `COMPLETE`
- Decision: `BF01_PROTOCOL_RECOVERED_ACCOUNTING_REPAIR_REGISTERED`
- Exact historical source hash matched: `True`
- B02 protocol recovered: `True`
- Legacy benchmark execution authorized: `False`
- D5D2 repaired benchmark research authorized: `True`
- Point-in-time baseline authorized: `False`

## Recovered B02 intent

- Benchmark: `B02` — `EQUAL_WEIGHT_ELIGIBLE_UNIVERSE`
- Equal weight every causally eligible asset.
- Freeze the target schedule on completed Sunday daily closes.
- Apply the schedule to the following Monday daily return.
- Rebalance weekly and include entry, rebalance, and exit costs.

## Confirmed legacy accounting defects

- Daily returns reused constant target weights between weekly rebalances.
- Turnover compared target weights with prior targets, not drifted holdings.
- Entry fees could mutate the reported initial-capital denominator.
- Missing held-asset returns could be coerced to zero.

## Adjudicated D5D2 repair

- Use the frozen RD04 PIT weekly universe, never survivor-30.
- Preserve causal 84-day daily-history readiness.
- Let holdings drift between Monday rebalances.
- Charge turnover against pre-trade drifted weights.
- Keep initial capital fixed at 100,000 per fold.
- Treat a missing held-asset return as a data-contract failure.
- Compare matched Monday-to-Monday expectancy for both portfolios.

## Safety boundary

- D5D1 runs no portfolio simulation.
- No 2025 test data or 2026 holdout data are accessed.
- No universe, ranking, weight, entry, exit, or live-trading change.
