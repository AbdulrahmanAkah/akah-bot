# RD18-P2R2 results

## Scope and reconciliation

- Restricted claim: **RESTRICTED_TO_376_KLINE_CONFIRMED_HISTORICAL_KUCOIN_SPOT_PAIRS**
- Raw inventory: 376 pairs
- Corrected C2: 364 pairs
- Corrected D2: 299 pairs
- Corrected C2-minus-D2: 65 pairs
- Registered excluded products: 12
- Weekly decisions: 313 (post-warm-up: 301)
- Exact boundaries: 376

## Corrected D2 versus C2

Full-period exact Top-6 match is **0.504792332268371** and
exact Top-10 match is **0.252396166134185**.  Mean
Top-10 Jaccard is **0.763159524181888**.
Post-warm-up values are respectively
**0.491694352159468**,
**0.229235880398671**, and
**0.756375186275518**.  The complete
substitution distribution is in `corrected-substitution-distribution.csv`.

## Provenance, flags and historical retention

Current-seed Top-6 slot share is **0.087326943556975**
for the full period and **0.089700996677741**
post-warm-up.  No unresolved identity or unresolved liquidity-integrity flag
enters corrected Top-10.  All six retained historically delisted ordinary Spot
pairs remain represented; their contribution is in
`corrected-delisted-pair-impact.csv`.  P2T liquidity flags are joined without
removing or demoting any asset.

## Corrected omission risk

The frozen P2R thresholds classify this corrected full-period structure as
**HIGH**.  This is a structural classification, not a probability estimate.
P2R's historical SEVERE result is unchanged; it is not rewritten.  The new
P2R2 result is the decision recorded below.
