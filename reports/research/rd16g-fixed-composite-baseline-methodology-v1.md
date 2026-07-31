# RD16-G Fixed Composite Alpha Baseline Methodology v1

## Purpose

RD16-G performs the first complete economic baseline of the preregistered `COMPOSITE_ALPHA_V1` architecture. It evaluates the architecture exactly as registered by RD16-F and does not change engines, component filters, routing priority, cooldown, position limits, risk budgets, quantities, exits, or sealed-period boundaries.

## Frozen architecture

The architecture contains two enabled engines:

1. `TREND_CONTINUATION_CORE`, sourced from `MTF_TREND_BREAKOUT::FULL_REMEDIATION_STACK`.
2. `COMPRESSION_EXPANSION_SPECIALIST`, sourced from `MTF_COMPRESSION_EXPANSION::FULL_REMEDIATION_STACK`.

The deterministic RD16-F router remains frozen. Trend priority is 10 and Compression priority is 20. The router enforces exit-before-entry processing, one active position per symbol, a global 24-hour same-symbol cooldown, a maximum of three positions, and a maximum frozen open-risk budget of 1.5% of initial equity.

## Economic reconstruction

RD16-G loads the verified local RD16-F composite trade ledger and reconstructs an hourly marked-to-market portfolio. It uses the recorded quantities, entry prices, exit prices, risk budgets, and trade paths. Transaction-cost stress scales the recorded 10 bps fee per side while preserving all trade decisions and quantities.

The evaluation reports full-period metrics, annual and monthly performance, engine and asset attribution, market and volatility regimes, exits, holding periods, trade-distribution diagnostics, concentration, rolling windows, drawdown episodes, router opportunity audit, benchmark capture, bull-window adequacy, and capital feasibility.

## Classification

The architecture is classified independently of the strategic target:

- `ROBUST_POSITIVE_COMPOSITE_BASELINE`: passes every fixed economic and robustness gate.
- `FRAGILE_POSITIVE_COMPOSITE_BASELINE`: profitable but fails one or more fixed robustness gates.
- `FAILED_ECONOMIC_COMPOSITE_BASELINE`: non-positive return or profit factor below 1.0.
- `CAPITAL_INFEASIBLE`: the frozen ledger requires unavailable capital or reaches non-positive equity.

The strategic target remains approximately 24% geometric monthly growth. Passing the robustness baseline does not imply that the strategic objective is met.

## Integrity rules

- RD16-F tracked outputs and local Parquet ledgers must match their manifests.
- Deterministic replay must match.
- Frozen inputs must remain unchanged.
- No 2025 or 2026 data may be accessed.
- No Dune API, optimization, parameter sweep, architecture change, winner selection, leverage, margin, shorting, derivatives, DCA, Kelly sizing, pyramiding, or averaging down is permitted.
