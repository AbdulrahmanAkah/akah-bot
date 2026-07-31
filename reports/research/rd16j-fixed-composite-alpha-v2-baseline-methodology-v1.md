# RD16-J Fixed COMPOSITE_ALPHA_V2 Baseline Methodology v1

## Purpose

RD16-J evaluates the registered `COMPOSITE_ALPHA_V2` architecture as one frozen economic system. It does not change routing, risk, cooldown, source components, or exit logic.

## Frozen architecture

- Source: `EVIDENCE_COMPOSITE_EXPANSION`.
- Trend cooldown: 12 hours.
- Compression cooldown: 24 hours.
- Normal fixed risk: 0.50% of initial equity.
- Expanded fixed risk: 0.75% in `STRONG_BULL` or engine agreement.
- Maximum open risk: 2.25% of initial equity.
- Maximum positions: 5.
- Same-symbol overlap remains prohibited.

## Evaluation

The stage builds hourly mark-to-market equity curves at 1x, 1.5x, 2x, and 3x recorded transaction costs. It reports return, CAGR, geometric monthly return, drawdown, profit factor, cash feasibility, exposure, annual and monthly performance, assets, engines, regimes, exits, holding periods, concentration, rolling windows, benchmarks, and bull capture.

## Capacity audit

The five-position user-directed limit is evaluated separately from the 2.25% open-risk cap. RD16-J records hourly position occupancy and hypothetical PnL for candidates rejected by either the position-count limit or the open-risk limit.

## Comparison

The fixed V2 baseline is compared directly with the tracked RD16-G `COMPOSITE_ALPHA_V1` baseline.

## Restrictions

2025 and 2026 remain sealed. No optimization, winner selection, leverage, margin, shorting, derivatives, DCA, Kelly sizing, pyramiding, averaging down, or production authorization is permitted.
