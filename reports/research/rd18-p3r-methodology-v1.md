# RD18-P3R methodology

## Purpose

RD18-P3R freezes the three-universe replay before any performance from C2, D2 or E2 is observed. It does not execute the strategy.

## Frozen candidate

The registered candidate is `COMPOSITE_ALPHA_V3`, sourced from `STRONG_BULL_HOLD_96`. The architecture is Spot-only and Long-only, uses 1-hour signals with causal 4-hour, daily and weekly context, allows at most five positions, caps open risk at 2.25%, and uses 0.50% or 0.75% risk per trade under the registered conditions.

No candidate was selected in P3R. RD16P retained no later alternative, so the RD16L/RD16M candidate remains the unambiguous frozen candidate.

## Frozen universes

The future replay must run independently on:

- C2: corrected broad restricted KuCoin liquidity universe.
- D2: corrected Evidence-Strong universe.
- E2: committed E10 confidence-aware universe.

Operational membership is the unchanged Top-6 entry / Top-8 retention hysteresis. The 301 post-warm-up weekly decisions from 2019-04-01 through 2024-12-31 are primary.

## Critical readiness finding

The previous dynamic V3 replay reused a candidate ledger containing only AVAX, BTC, ETH, LINK, NEAR and SOL. Its average true Top-6 coverage was 38.07%, and complete Top-6 coverage was 0%. That ledger is valid as a legacy control but cannot serve as the signal source for C2/D2/E2.

The universe work is daily, while the strategy requires 1-hour data. P3X must therefore build and validate the full operational hourly input set before any return is calculated.

## Frozen evaluation policy

All universes use identical strategy code, parameters, costs, risk controls and timing. The base cost model is a 0.10% fee per side with no separately registered slippage deduction; 2x is a transaction-cost stress, never leverage.

The worst universe controls advancement. Thresholds are inherited from RD16 where available and frozen before results. The 24% geometric monthly target remains a separate strategic objective; a robust replay may still be classified strategically inadequate.

## Prohibitions

P3R and P3X may not use 2025 or 2026, tune by universe, select a new strategy, delete trades post hoc, use synthetic OHLCV fills, or introduce leverage, margin, derivatives, DCA, Kelly sizing, pyramiding or averaging down.
