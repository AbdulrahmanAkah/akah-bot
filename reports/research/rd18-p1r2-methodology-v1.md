# RD18-P1R2 methodology

P1R2 repairs the restricted KuCoin Spot panel at the eligibility layer. The raw
376-pair Kline-confirmed inventory is retained for provenance, while the 12
registered leveraged/synthetic products are marked ineligible before weekly
metrics, ranking, Top-N selection, or hysteresis. The corrected claim remains
`RESTRICTED_TO_376_KLINE_CONFIRMED_HISTORICAL_KUCOIN_SPOT_PAIRS`; it is not an
exhaustive KuCoin inventory claim.

The rebuild is offline-only and reuses the committed P1R daily panel and P0B
boundary metadata. It preserves Monday 00:00 UTC decisions, the 24-hour
availability delay, Sunday exclusion, 90-day listing age, 26-of-28 coverage,
median daily USDT quote turnover, deterministic ranking, and Top-6/Top-8
hysteresis. Previous P1R, P2R, P2S, P2T, and P2U artifacts are historical
inputs and are not edited. Their derived structural results are
`SUPERSEDED_FOR_FUTURE_RESEARCH_BY_CORRECTED_P1R2_BASELINE`.
