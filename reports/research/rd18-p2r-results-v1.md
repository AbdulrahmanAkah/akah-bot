# RD18-P2R structural results

The P1R input reconciliation passed: 68 P0 pairs, 300 P0A pairs, 376 unique
P0B/P1R confirmed pairs, 299 evidence-strong pairs, 313 weekly decisions and
301 post-warm-up decisions. The frozen P1R deterministic manifest hash was
`3956041409448c3fb547d18917d46f423e07b88b8815961a1a61866fd4ab03b0`.

Variant sensitivity is large. P0 versus the 376-pair panel has Top-6 exact
match 0.0255591054 and mean Top-10 Jaccard 0.3178932646. P0A versus the final
panel has Top-6 exact match 0.4984025559 and mean Top-10 Jaccard 0.7604971174.
Evidence-strong versus final has the same registered comparison values. The
current-seed-only lineage occupies 0.0899893504 of Top-6 slots on average, with
the highest calendar-year mean at 0.1474358974. Rank-6/rank-7 liquidity margins
exceed 10% in 0.6006389776 of weeks.

The severe omission-risk rule is triggered because the evidence-strong versus
final Top-6 exact match is below 50% (0.4984025559). This is a structural risk
classification, not a return result and not a probability estimate. The six
explicitly delisted retained pairs remain in the diagnostic analysis. The four
frozen CMC snapshots are descriptive reference comparisons only.

The resulting decision is `RD18_P2R_RESTRICTED_UNIVERSE_STRUCTURAL_RISK_UNACCEPTABLE`.
No P3R replay is authorized by this stage, and no strategy or production
authorization is granted.
