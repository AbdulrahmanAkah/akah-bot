# RD16-P Multitimeframe Structure and Cross-Sectional Portfolio Research

## Purpose

RD16-O reduced signal frequency but still found no retained or promising
second-generation engine. Several families remained profitable as standalone
trade streams, while their additive overlays damaged `COMPOSITE_ALPHA_V3`.
RD16-P therefore tests a portfolio-allocation hypothesis rather than a new
entry-pattern hypothesis:

> The candidate pool may contain usable alpha, but capital must be allocated
> only to the strongest simultaneous candidate and the new-engine sleeve must
> have its own fixed risk, notional, position, and cooldown limits.

## Frozen evidence

- Source stage: RD16-O.
- Source architecture: `COMPOSITE_ALPHA_V3`.
- Source result commit: `236b48f76eea8da1361414e5b3ac622358cadaae`.
- RD16-O evaluated candidate ledgers are loaded from the registered local
  manifest and verified by file and dataframe-content hashes.
- The fixed V3 trade ledger is preserved exactly.
- The market dataset remains sealed before 2025.
- 2025 and 2026 are not accessed.

## Cross-sectional quality score

Each candidate receives a causal score using metadata available at the
completed signal bar:

- 28%: 72-hour cross-sectional return rank.
- 22%: 24-hour cross-sectional return rank.
- 20%: market breadth.
- 15%: bounded volume-quality score.
- 10%: anti-extension quality relative to EMA20 and ATR.
- 5%: Bull or Strong-Bull regime quality.

Candidates are sorted deterministically at each entry timestamp. Depending on
the preregistered variant, only the top one or top two candidates remain.

## Fixed variants

1. `CS_TOP1_BALANCED_12PCT`
2. `CS_TOP2_DIVERSIFIED_8PCT`
3. `MTF_STRONG_BULL_TOP1_15PCT`
4. `MTF_STRUCTURE_TOP1_10PCT`
5. `CROSS_SECTIONAL_ROTATION_TOP2_6PCT`

The variants differ only in preregistered quality thresholds, family and regime
eligibility, top-k selection, risk fraction, notional cap, and sleeve capacity.

## Sizing and capacity

Sizing may only be reduced from the frozen RD16-O evaluated quantity.

For each selected candidate:

- quantity, risk budget, notional, gross PnL, fees, and net PnL are scaled by
  the same factor;
- the factor cannot exceed 1.0;
- the risk target and notional cap are both enforced;
- no candidate is scaled upward.

Before integration with V3, a separate sleeve router enforces:

- one or two new-engine positions depending on the variant;
- a fixed sleeve open-risk ceiling;
- same-symbol exclusion;
- fixed same-symbol cooldown.

The frozen V3 additive router then reapplies:

- maximum five total positions;
- maximum 2.25% total open risk;
- no same-symbol overlap;
- frozen V3 priority;
- no displacement of existing V3 trades.

## Evaluation

Every variant is evaluated as:

1. a standalone selected portfolio;
2. an additive overlay on fixed V3;
3. transaction-cost stress at 1x, 1.5x, 2x, and 3x;
4. annual performance;
5. high-opportunity Bull capture;
6. selection and routing opportunity cost;
7. capital feasibility.

## Retention

A variant is retained only when all fixed gates pass, including:

- positive standalone return;
- standalone PF at least 1.10;
- standalone drawdown no more than 30%;
- positive and feasible 2x standalone result;
- at least 2 percentage points of additive overlay return;
- overlay PF preserved within 0.05 of V3;
- overlay drawdown no more than 3 percentage points worse than V3;
- feasible 1x and 2x overlay capital;
- 2x overlay return not below V3;
- Bull capture no more than 0.5 percentage points below V3.

No winner is selected, no production authorization is granted, and the
architecture remains `COMPOSITE_ALPHA_V3`.
