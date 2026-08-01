# RD16-R Data Acquisition and Causality Audit

- Public KuCoin Spot OHLCV only.
- No credentials or trading methods are used.
- Download range begins 2020-01-01 UTC and ends exclusively at 2025-01-01 UTC.
- 2025 test data and 2026 holdout data remain sealed.
- Core six datasets are copied from the verified frozen RD16-B store.
- Non-core acquisition failures are classified per market and timeframe rather than aborting the stage.
- Liquidity tiers use fixed ranks from median daily approximate quote volume.
- Recorded acquisition failure rows: 18.
