# AMS RD04-D1 — Point-in-Time Universe Full-Portfolio Replay

## Executive result

- Status: `COMPLETE`
- Decision: `PIT_UNIVERSE_REPLAY_FAIL`
- Reason: `PIT_REPLAY_FAILED_STRUCTURAL_OR_REGISTERED_GROSS_EDGE_GATE`
- Variant: `MD01-M05`
- PIT base-cost compounded return: `-0.481035`
- Fixed base-cost compounded return: `2.686147`
- PIT stress-cost compounded return: `-0.548174`
- PIT base-cost positive folds: `2`
- PIT base-cost profit factor: `0.8533000104768909`
- PIT base-cost trade count: `153`
- Point-in-time universe research baseline authorized: `False`
- Universe change authorized: `False`
- Trade logic changed: `False`
- ATI-V1 authorized: `False`

## Replay contract

- The original trusted MD01-M05 simulator is used for both universes.
- PIT filtering occurs only at each registered Monday rebalance.
- The D0C venue-eligible market-cap top 30 is the only PIT membership source.
- Fixed-universe base-cost fingerprints must match D0C exactly.
- Zero, registered 0.2%, and stress 0.4% transaction costs are replayed.

## Safety boundary

- No momentum, alignment, cluster, crisis, entry, exit, fill, or cash rule changes.
- No 2025 test data or 2026 holdout data are accessed.
- No production, live, Kelly, leverage, pyramiding, or averaging down is authorized.
