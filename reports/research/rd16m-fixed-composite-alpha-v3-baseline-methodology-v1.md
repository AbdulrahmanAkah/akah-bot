# RD16-M — Fixed COMPOSITE_ALPHA_V3 Baseline Methodology

## Purpose

RD16-M performs the first independent economic baseline of the registered
`COMPOSITE_ALPHA_V3` architecture. It does not tune, select, or modify the
architecture.

## Frozen source

- Registration stage: RD16-L
- Architecture: `COMPOSITE_ALPHA_V3`
- Source retained variant: `STRONG_BULL_HOLD_96`
- Candidate ledger: 688 rows
- Registered trade ledger: 567 rows
- Maximum configured positions: 5
- Maximum open risk: 2.25% of frozen initial equity
- Holding horizon: 96 bars in `STRONG_BULL`, 48 bars otherwise
- 2025 and 2026 remain sealed

RD16-M verifies tracked RD16-L hashes and the local candidate, evaluated, and
trade ledger hashes before using them.

## Evaluation

The fixed V3 ledger is reconstructed on the registered hourly timeline at the
same 1.0x, 1.5x, 2.0x, and 3.0x cost multipliers used by prior composite
baselines.

The stage produces:

- full economic metrics and equity curves
- annual and monthly results
- asset, regime, exit, holding, and engine attribution
- routing opportunity and capacity audits
- cash and capital feasibility under cost stress
- concentration, distribution, rolling-window, and drawdown evidence
- benchmark and high-opportunity bull-window capture
- direct V2-to-V3 comparison

## Independent parity gate

V3 identifiers and engine names differ from the retained RD16-K variant, but
the economics must match `STRONG_BULL_HOLD_96`. RD16-M independently rebuilds
the equity curves and requires base and 2x metrics to match the retained
source evidence.

## Classification

A robust V3 baseline requires:

- positive and cash-feasible base results
- profit factor at least 1.20
- maximum drawdown no more than 30%
- positive, PF-at-least-1.0, cash-feasible results at 2x costs
- at least half of active years positive
- top-three trade profit share no more than 35%
- both engines contributing positively
- at least 100 trades
- higher return and no lower profit factor than V2
- drawdown no more than five percentage points worse than V2

The strategic target remains approximately 24% geometric monthly return plus
adequate capture in every high-opportunity bull window.

A technically robust result that remains strategically inadequate proceeds to
new intraday alpha-engine and signal research rather than further micro-tuning
of the same two-engine architecture.
