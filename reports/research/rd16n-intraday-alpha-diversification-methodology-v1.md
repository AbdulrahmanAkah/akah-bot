# RD16-N — Intraday Alpha Engine Diversification and New Signal Research

## Objective

RD16-N moves beyond incremental risk and holding-period changes. It evaluates
six pre-registered causal signal hypotheses that are structurally different
from the existing Trend Continuation and Compression Expansion engines.

Each hypothesis is evaluated twice:

1. As a standalone Spot-only, Long-only engine.
2. As an additive overlay to frozen `COMPOSITE_ALPHA_V3`.

Frozen V3 trades are never displaced. A new trade is admitted only when its
entire holding interval preserves the five-position limit, the 2.25% open-risk
limit, and same-symbol exclusivity.

## Fixed hypotheses

- `FAST_MOMENTUM_BREAKOUT`
- `TREND_REACCELERATION`
- `VWAP_RECLAIM_CONTINUATION`
- `VOLATILITY_SQUEEZE_RELEASE`
- `RELATIVE_STRENGTH_LEADER_BREAKOUT`
- `DEFENSIVE_SWEEP_REVERSAL`

The exact conditions, stop multiples, engine priorities and cooldowns are
registered in code before execution. No threshold sweep or parameter search is
permitted.

## Shared execution policy

- Signal decisions use completed 1H bars.
- Entry occurs at the next 1H bar open.
- Hard stop is checked before profit-floor updates.
- Base risk is 0.50% of frozen initial equity.
- Strong-Bull risk is 0.75%, non-compounding.
- Maximum holding is 96 bars in Strong Bull and 48 bars elsewhere.
- Maximum configured positions: 5.
- Maximum open risk: 2.25%.
- Same-symbol overlap is prohibited.
- Costs are evaluated at 1×, 1.5×, 2× and 3×.

## Retention logic

Retention is gate-based, not winner selection. A family must show:

- sufficient candidate and asset coverage;
- positive standalone economics;
- minimum standalone Profit Factor;
- positive and capital-feasible 2× cost stress;
- acceptable concentration and yearly consistency;
- at least five percentage points of additive overlay return;
- preserved overlay Profit Factor and drawdown;
- capital feasibility at 1× and 2×;
- role-specific evidence:
  - offensive engines must improve high-opportunity bull capture;
  - diversifying/defensive engines must add non-Strong-Bull profit without
    materially worsening drawdown.

## Sealed-period policy

2025 and 2026 remain sealed. RD16-N uses only the previously registered
development dataset and verifies all tracked and local input hashes.

## Next stage

If one or more hypotheses pass every gate:

`RD16O_COMPOSITE_ALPHA_V4_CANDIDATE_ASSEMBLY_AND_INTERACTION_TEST`

Otherwise:

`RD16O_INTRADAY_ALPHA_ENGINE_REDESIGN_AND_SECOND_GENERATION_SIGNAL_RESEARCH`
