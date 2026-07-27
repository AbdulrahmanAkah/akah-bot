# RD04-D2 — Universe Membership Failure Attribution

This stage diagnoses the completed RD04-D1 point-in-time replay failure without
creating or authorizing a new universe.

## Frozen 2x2 counterfactual

- `FIXED_SURVIVOR_30`: retain the original fixed survivor 30.
- `UNION_FIXED_AND_PIT`: add PIT entrants without removing fixed survivors.
- `INTERSECTION_FIXED_AND_PIT`: remove absent fixed survivors without entrants.
- `PIT_UNIVERSE`: apply both observed additions and removals.

The trusted MD01-M05 simulator, costs, folds, momentum, alignment, clusters,
crisis controls, entries, exits, fills, and cash rules remain unchanged.

## Outputs

RD04-D2 records aggregate and fold-level factorial attribution, Shapley effects,
membership snapshots, base-cost trades, and per-symbol PnL. The result may only
authorize another diagnostic research stage.

## Safety

No universe, ranking, weight, entry, exit, production, live-trading, ATI, Kelly,
leverage, pyramiding, averaging-down, 2025-test, or 2026-holdout authorization is
created by this stage.
