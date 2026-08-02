# RD18-P2S methodology

This stage is an offline structural redesign of the restricted KuCoin Spot
universe.  It preserves the registered P2R result `RD18_P2R_RESTRICTED_UNIVERSE_STRUCTURAL_RISK_UNACCEPTABLE`
and does not relabel it.  The valid claim remains
`RESTRICTED_TO_376_KLINE_CONFIRMED_HISTORICAL_KUCOIN_SPOT_PAIRS`; it is not a claim of exhaustive KuCoin history.

The frozen comparison uses the same 313 weekly decisions and 301 post-warm-up
decisions for Variant C (376 pairs) and Variant D (299 evidence-strong pairs).
Exact-set match remains reported, but P2S additionally measures substitutions,
Jaccard, rank and liquidity proximity, duration, hysteresis, provenance, and
consensus diagnostics.  No market data was acquired and no strategy or return
analysis was performed.

Dual-scenario gates were frozen before results: Top-6/Top-10 overlap and
bounded substitutions, hysteresis overlap, current-seed influence, eligibility,
identity, timing, duplicate-identity, and deterministic-replay gates.
