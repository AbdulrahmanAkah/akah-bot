# RD11 Baseline Methodology v1

## Frozen strategy

RD11 uses `AKAH_REGIME_MOMENTUM_BREAKOUT_V1` exactly as committed by RD10. The
machine specification SHA-256 is
`dda3e786f473320139290cebde2edf551ba3255cd89834684e5afc2b67c696ad`.
No entry, exit, indicator, risk, cost, sizing, or timing parameter may change.

## Universe and data gate

The preregistered target universe is BTC/USDT, ETH/USDT, ADA/USDT, AVAX/USDT,
and DOT/USDT. An asset is eligible only with local daily OHLCV, exact required
columns, unique chronological timestamps, no gap above one day, at least 565
bars, and no included timestamp on or after 2025-01-01.

## Window rule

Use the longest complete daily intersection across all eligible target assets.
The observed intersection is 2022-06-17 through 2024-12-31 inclusive. The first
200 bars are warm-up; performance begins on 2023-01-03. The exclusive end
boundary is 2025-01-01 and contains no 2025 observation. This rule was frozen
before any strategy result was calculated.

## Portfolio scheduling

All symbols at a UTC timestamp are processed as one batch. Existing pending
orders execute at that timestamp's opens; stops are then evaluated; all closes
become visible; only then are new signals generated. Simultaneous buy signals
rank by breakout strength, volume ratio, RSI, then symbol alphabetically.
Shared cash, two positions maximum, one position per asset, 1% risk, and 25%
position allocation are enforced.

## Benchmark and regimes

The benchmark invests equal capital in all eligible assets at the first
evaluation open, applies the same entry and exit fee and slippage, never
rebalances, and exits at the last close. BTC defines the common descriptive
regime: bull when close and EMA50 are above EMA200, bear when both are below,
and sideways/transition otherwise.

## Classification

The POSITIVE, MIXED, and NEGATIVE rules are frozen in
`data/research/rd11/rd11-config-v1.json`. Technical validity is separate from
evidence strength. Weak or negative performance does not block completion.
