# RD16-E Intraday Family Remediation and Component Extraction Methodology v1

## Purpose

RD16-E converts the RD16-D diagnosis into a fixed causal ablation study. It does not search parameters, rank the four families, choose a winner, or authorize deployment. It asks which regime, volatility, asset, structural-confirmation, fee-buffer, and cooldown components improve the frozen RD16-C trade streams.

## Frozen inputs

- The completed RD16-D report and its tracked output hashes.
- The verified local RD16-D enriched trade Parquets.
- The same KuCoin Spot-only, Long-only six-asset pilot universe.
- Completed 1H execution data with completed 4H, 1D, and 1W context.
- Exclusive cutoff `2025-01-01T00:00:00Z`; 2025 and 2026 remain sealed.
- Frozen trade quantities, exits, hard-stop-first behavior, and recorded fees.

RD16-E only removes trades through preregistered causal gates. It never selects trades using realized PnL, MFE, MAE, exit reason, or any future information.

## Preregistered ablation matrix

Every family is evaluated under ten variants:

1. `BASELINE`
2. `REGIME_GATE`
3. `VOLATILITY_GATE`
4. `ASSET_GATE`
5. `REGIME_VOLATILITY_GATE`
6. `REGIME_ASSET_GATE`
7. `ALL_DIAGNOSTIC_GATES`
8. `STRUCTURAL_CONFIRMATION`
9. `DIAGNOSTIC_PLUS_STRUCTURE`
10. `FULL_REMEDIATION_STACK`

The full stack combines the family-specific regime, volatility, and asset gates with stronger causal signal confirmation, a fixed fee buffer, and a 24-hour same-symbol cooldown.

## Family-specific diagnosis converted into gates

- Trend Breakout removes Transition, High Volatility, NEAR, and AVAX from the diagnostic stack while preserving BTC, ETH, LINK, and SOL.
- Pullback Reclaim removes Transition, High/Low Volatility, LINK, and NEAR from the diagnostic stack.
- Compression Expansion retains Bear and Strong Bull, removes LINK, and strengthens the compression-to-expansion confirmation.
- Range Reclaim is treated as component salvage only: Transition and SOL are isolated; the full family is not rehabilitated by assumption.

## Structural confirmation

Structural gates strengthen the original registered trigger without changing the original numerical parameters through search:

- Trend Breakout requires a stronger breakout displacement, full median-volume participation, and positive 4H EMA separation.
- Pullback Reclaim requires a bullish reclaim body, positive EMA20 displacement, and aligned 4H EMA20/EMA50 structure.
- Compression Expansion requires a full-ATR expansion, deeper pre-expansion compression, and breakout displacement.
- Range Reclaim requires a high close location in the signal candle and a meaningful reclaim displacement.

## Evaluation

Each variant is reconstructed on the hourly portfolio timeline at 1.0x, 1.5x, 2.0x, and 3.0x recorded costs. RD16-E reports return, CAGR, geometric monthly return, drawdown, profit factor, expectancy, R-multiples, fees, turnover, exposure, capital feasibility, annual consistency, asset/regime attribution, and bull-window capture.

## Decisions

- `REFERENCE_BASELINE`: comparison only.
- `RETAIN_FOR_COMPOSITE_RESEARCH`: passes all fixed component retention gates.
- `PROMISING_BUT_FRAGILE`: remains positive and shows material multi-dimensional improvement but does not pass all retention gates.
- `INSUFFICIENT_SAMPLE`: fewer than 50 trades after filtering.
- `REJECT_COMPONENT`: lacks positive, feasible, or material evidence.

A retained component is not a production strategy. RD16-E is an in-sample diagnostic and extraction stage. Surviving components must be preregistered into a new composite architecture in RD16-F before further evaluation.
