# RD04-D1 — Point-in-Time Universe Full-Portfolio Replay

## Scope

- Replay the registered MD01-M05 strategy on the D0C adjudicated dataset.
- Restrict every Monday rebalance to the frozen D0C venue-eligible market-cap top 30.
- Preserve the original momentum, alignment, cluster, crisis, entry, exit, fill, and cash rules.
- Compare the causal point-in-time universe with the original fixed survivor-30 baseline.
- Run zero-cost, registered 0.2%, and stress 0.4% transaction-cost modes.
- Apply the frozen MD01 gross-edge gate at registered cost and a separate stress-cost gate.

## Critical implementation boundary

- The trusted `simulate_md01_fold` engine is not copied or modified.
- A temporary eligibility wrapper filters its momentum ranking to the D0C weekly top 30.
- The original eligibility function and cache are restored after every PIT fold.
- The fixed 0.2% baseline must reproduce all three D0C financial fingerprints.

## Safety

- No parameter optimisation or strategy-rule change.
- No 2025 test or 2026 holdout access.
- No production, live, ATI, Kelly, leverage, pyramiding, or averaging-down authorization.
