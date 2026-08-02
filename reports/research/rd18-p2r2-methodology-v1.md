# RD18-P2R2 methodology

RD18-P2R2 recomputes the structural comparison from the immutable corrected
P1R2 baseline.  It uses only the committed KuCoin Spot panel and committed
P0/P0A/P2T/P2U/RD17 diagnostic files; no network request or new market-data
acquisition is permitted.

The research claim remains **RESTRICTED_TO_376_KLINE_CONFIRMED_HISTORICAL_KUCOIN_SPOT_PAIRS**.  C2 is the 364-pair corrected ordinary
Spot panel derived from the raw 376 Kline-confirmed pairs after the frozen
12-product exclusion.  D2 is the 299-pair evidence-strong panel.  A2 and B2
are corrected diagnostics derived from the original P0 and P0A inventories.

All four variants use the same 313 Monday decisions and the same P1R2 causal
eligibility, 90-day listing-age, 26-of-28 observation, 24-hour availability,
Sunday-exclusion, ranking, and hysteresis rules.  Full-period metrics use all
313 decisions; post-warm-up metrics use the registered final 301 decisions.
Set distance, Jaccard, substitution, rank-displacement, turnover,
concentration, cutoff, provenance, delisted-pair, frozen-CMC and legacy-list
diagnostics are descriptive only.  No strategy returns, signals, trades,
candidates, optimization, production authorization, or post-2024 observations
are produced.

The old P1R/P2R/P2S numerical conclusions are preserved as historical
artifacts.  Where this report recomputes a value from C2/D2, the old derived
value is **SUPERSEDED_FOR_FUTURE_RESEARCH_BY_CORRECTED_P1R2_BASELINE**; no old
file is rewritten.
