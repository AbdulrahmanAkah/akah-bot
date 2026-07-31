# RD16-H Return Expansion and Bull Capture Remediation v1

## Purpose

RD16-H evaluates a preregistered set of causal return-expansion variants over the
frozen COMPOSITE_ALPHA_V1 development period. It does not authorize production,
select a winner, tune parameters, or access the sealed 2025/2026 periods.

## Evidence used

RD16-G established a robust positive composite baseline but only 0.556% geometric
monthly return and weak high-opportunity bull capture. The router audit supports
three narrow research directions:

1. broaden Trend participation during STRONG_BULL conditions;
2. test a shorter Trend-only cooldown while preserving Compression cooldown;
3. apply fixed, non-compounding risk increases only during STRONG_BULL conditions
   or when both registered engines signal the same symbol and entry time.

Same-symbol active-position rejection remains unchanged because rejected overlap
opportunities were negative in aggregate. The maximum-position limit remains three
because only one rejected max-position observation existed.

## Frozen variants

The stage evaluates exactly ten variants:

- BASELINE
- TREND_STRONG_BULL_STRUCTURE_BREADTH
- TREND_STRONG_BULL_DIAGNOSTIC_BREADTH
- COMPRESSION_STRONG_BULL_STRUCTURE_BREADTH
- DUAL_STRONG_BULL_STRUCTURE_BREADTH
- TREND_COOLDOWN_12H
- CONSENSUS_RISK_075
- STRONG_BULL_RISK_075
- STRONG_BULL_RISK_100
- EVIDENCE_COMPOSITE_EXPANSION

Risk multipliers never compound. A trade receives the maximum applicable fixed
multiplier. Position size, notional, risk budget, gross PnL, fees, and net PnL are
scaled linearly. Entry, exit, stop distance, and holding path are unchanged.

## Constraints

- Spot only and Long only.
- No leverage, margin, shorting, borrowing, futures, perpetuals, options, or derivatives.
- No DCA, Kelly sizing, pyramiding, or averaging down.
- No concurrent same-symbol positions.
- Maximum three open positions.
- Fixed causal information available at signal time only.
- 2025 and 2026 remain sealed.
- No parameter sweep, grid search, family ranking, or winner selection.

## Interpretation

A carry-forward decision requires robust economics, positive 2x-cost performance,
acceptable concentration, positive contribution from both engines, and material
improvement in return or high-opportunity bull capture without bull-capture
regression. Carry-forward remains research evidence only.
