# RD16-Q Signal-Domain Expansion and Alternative-Data Methodology

## Purpose

RD16-Q tests whether causal market-internal information derived from the frozen KuCoin Spot OHLCV universe can add material alpha above `COMPOSITE_ALPHA_V3`.

This stage does not retune RD16-N, RD16-O, or RD16-P. It changes the information domain.

## Fixed domains

1. `BREADTH_THRUST_LEADER_BREAKOUT`
2. `BTC_TO_ALT_ROTATION_BREAKOUT`
3. `DISPERSION_EXPANSION_LEADER`
4. `VOLUME_BREADTH_THRUST`
5. `CORRELATION_RELEASE_ROTATION`

The domains use cross-sectional breadth, leadership, return dispersion, spot-volume participation, and pairwise-correlation regimes.

## Causality

- Every signal is computed from completed bars only.
- Rolling thresholds use historical observations available at the signal close.
- Entry is at the next hourly bar open.
- Higher-timeframe context timestamps cannot exceed the signal timestamp.
- The 2025 test period and 2026 holdout remain sealed.

## Data restrictions

Only the registered six-pair KuCoin Spot OHLCV dataset is used. No funding rates, open interest, liquidations, perpetuals, futures, options, margin, borrowing, external alternative-data provider, or Dune API are used.

The phrase “alternative data” in this stage refers only to causal market internals derived from the registered Spot universe.

## Evaluation

Each domain is evaluated:

- standalone;
- as an additive overlay that cannot displace frozen V3 trades;
- under 1.0x, 1.5x, 2.0x, and 3.0x transaction-cost assumptions;
- for capital feasibility, drawdown, concentration, active-year stability, and bull-market capture.

A pre-registered combined overlay of all five domains is also evaluated. It is diagnostic and cannot override individual carry-forward decisions.

## Carry-forward rule

A domain is retained only if it passes all fixed standalone, stressed-cost, capital, concentration, overlay-additivity, drawdown, and benchmark-capture gates.

No winner is selected and no production authorization is granted in RD16-Q.
