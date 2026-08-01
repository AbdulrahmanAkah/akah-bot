# RD16-R Universe Expansion and Liquidity Tier Methodology

RD16-R separates data acquisition and universe validation from signal evaluation.

- The frozen six-asset pilot data are copied from the verified RD16-B local store.
- Non-core candidates are resolved against active KuCoin Spot markets only.
- Public OHLCV data are requested from 2020-01-01 UTC until, but not beyond, 2025-01-01 UTC.
- Missing, inactive, renamed, or failed markets are classified rather than aborting the stage.
- Eligibility requires verified 1H, 4H, 1D, and 1W datasets and fixed minimum row counts.
- Liquidity uses median approximate daily quote volume (`daily close × base volume`) over the final 365 available daily bars.
- Tier A contains ranks 1-6, Tier B ranks 7-12, and Tier C all remaining eligible assets.
- No strategy result, production authorization, optimization, or winner selection is produced in this stage.
