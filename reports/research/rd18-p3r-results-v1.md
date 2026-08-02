# RD18-P3R results

## Candidate audit

`COMPOSITE_ALPHA_V3 / STRONG_BULL_HOLD_96` is the only retained registered candidate.

Reference economics from RD16M:

- 1x return: 108.16%
- 1x profit factor: 1.5058
- 1x maximum drawdown: 11.03%
- 2x-cost return: 59.47%
- 2x-cost profit factor: 1.2435
- 567 trades

These values are historical references, not P3R replay results.

## Input audit

C2, D2 and E2 are structurally ready as universe scenarios. Performance execution is not ready because:

1. the prior candidate ledger contains only six symbols;
2. complete historical Top-6 candidate coverage was 0%;
3. the full operational 1-hour KuCoin data store has not been registered;
4. the complete signal-lineage source hash manifest has not been frozen;
5. canonical C2 and D2 operational membership inputs still need materialization for replay.

## Registered outcome

The candidate, execution contract and performance gates are frozen. A performance replay remains prohibited until a dedicated input-build and dry-run stage passes.
