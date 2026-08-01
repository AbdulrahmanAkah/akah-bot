# RD16-O — Second-Generation Intraday Alpha Engine Redesign

## Purpose

RD16-N rejected all six first-generation engines. RD16-O therefore does not
change risk, capacity, or the frozen COMPOSITE_ALPHA_V3 baseline. It tests five
new, lower-frequency hypotheses derived from the failure evidence.

## Failure evidence carried forward

- Trend Reacceleration and VWAP Reclaim showed positive standalone economics,
  but excessive frequency and poor interaction with V3 destroyed overlay value.
- Fast Momentum and Squeeze were too weak under stressed costs.
- Relative Strength Leader Breakout and Defensive Sweep Reversal failed even
  before integration.
- The all-six overlay added 2,539 trades and produced a deeply negative result.

## Pre-registered second-generation hypotheses

1. `QUALITY_MOMENTUM_BREAKOUT_V2`
2. `PULLBACK_REACCELERATION_V2`
3. `SQUEEZE_TREND_RELEASE_V2`
4. `BULL_LIQUIDITY_SWEEP_RECLAIM_V2`
5. `RELATIVE_STRENGTH_ROTATION_RECLAIM_V2`

The redesign adds market-breadth, relative-strength rank, anti-extension,
volume-quality, and regime gates. It removes the weak-daily defensive-long
concept.

## Frozen portfolio rules

- Spot-only and Long-only.
- Maximum five positions.
- Maximum open risk 2.25% of frozen initial equity.
- 0.50% base risk and 0.75% Strong-Bull risk.
- Frozen V3 trades are never displaced.
- Same-symbol overlap is prohibited.
- 48-bar normal and 96-bar Strong-Bull maximum holding.
- 2025 and 2026 remain sealed.
- No parameter sweep, winner selection, leverage, DCA, Kelly, or production
  authorization.

## Evaluation

Each family is evaluated standalone and as a non-displacing overlay on V3.
Cost stress is calculated at 1x, 1.5x, 2x, and 3x. Retention requires positive
standalone evidence, stressed-cost survival, additive overlay return, preserved
profit factor and drawdown, capital feasibility, and role-specific evidence.

The pre-registered all-second-generation overlay is diagnostic only and cannot
override family-level gates.
