# RD16-S Limited Expanded-Universe Signal Methodology

RD16-S tests whether the fixed RD16-Q market-internal signal domains become materially more useful when the research universe expands from six to ten verified KuCoin Spot assets.

## Frozen universe

The stage uses exactly the ten assets classified as eligible by RD16-R:

- Tier A: BTC, ETH, SOL, XRP, NEAR, AVAX.
- Tier B: ADA, LTC, LINK, ATOM.
- Incremental non-core assets: XRP, ADA, LTC, ATOM.

No other market is loaded or substituted.

## Fixed signal domains

The five RD16-Q domains and every threshold remain unchanged:

1. `BREADTH_THRUST_LEADER_BREAKOUT`
2. `BTC_TO_ALT_ROTATION_BREAKOUT`
3. `DISPERSION_EXPANSION_LEADER`
4. `VOLUME_BREADTH_THRUST`
5. `CORRELATION_RELEASE_ROTATION`

Cross-sectional ranks, breadth, dispersion, volume breadth, BTC leadership, and average correlation are recomputed causally across the ten-asset universe.

## Evaluation

Each domain is evaluated standalone and as an additive overlay on frozen `COMPOSITE_ALPHA_V3`. Frozen V3 trades retain priority and cannot be displaced. The router preserves the five-position limit, 2.25% maximum open risk, same-symbol exclusivity, and engine cooldowns.

Results are compared directly with the corresponding six-asset RD16-Q domain. The stage separately attributes candidate counts, overlay trades, PnL, profit factor, and win rate to the four incremental non-core assets.

A pre-registered combined overlay of all five expanded-universe domains is diagnostic only. It cannot override individual carry-forward decisions.

## Causality and data

- All local 1H, 4H, 1D, and 1W datasets are verified against the RD16-R manifest.
- No network acquisition occurs.
- Signals use completed bars only.
- Entry remains the next hourly bar open.
- Higher-timeframe context cannot exceed the signal timestamp.
- The 2025 test period and 2026 holdout remain sealed.

## Restrictions

RD16-S is Spot-only and long-only. It uses no leverage, margin, shorting, derivatives, borrowing, interest, DCA, Kelly sizing, pyramiding, averaging down, Dune, optimization, winner selection, or production authorization.
