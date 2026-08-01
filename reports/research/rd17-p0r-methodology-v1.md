# RD17-P0R Source and Metric Diagnosis

## Objective

Diagnose why the registered Coin Metrics universe failed all four independent
CoinMarketCap Top-6 checks despite correct dates and USD-scale values for several
large assets.

## Hypotheses

1. The registered panel mixed `CapMrktCurUSD` with `CapMrktEstUSD`.
2. Estimated capitalization inflated assets such as XRP and XLM relative to
   circulating-cap rankings.
3. Coin Metrics Community lacks usable circulating-cap coverage for historically
   important assets such as BNB or SOL.

## Method

For the four frozen manual dates, acquire both Coin Metrics metrics without
fallback. Construct and compare:

- current-only rankings;
- estimated-only rankings;
- current-then-estimated fallback rankings;
- the registered local rankings.

For each independent Top-6 asset, record whether each metric exists. For each
registered local Top-10 row, identify whether its stored value is closer to the
current or estimated Coin Metrics metric.

## Decision

RD17-P1 is authorized only if current-only Coin Metrics rankings exactly match
all four independent Top-6 sets and all independent Top-6 assets have current
metric coverage. Otherwise the project must select and validate an alternate
historical market-cap source.

No signal generation, optimization, portfolio replay, or 2025/2026 access occurs
in this phase.
