# RD16-I Composite Alpha V2 Registration Methodology v1

## Purpose

RD16-I registers `COMPOSITE_ALPHA_V2` from the retained RD16-H
`EVIDENCE_COMPOSITE_EXPANSION` variant. It is a registration and deterministic
router smoke-test stage, not an economic baseline.

## Frozen source

- Source architecture: `COMPOSITE_ALPHA_V1`
- Source RD16-H variant: `EVIDENCE_COMPOSITE_EXPANSION`
- Trend cooldown: 12 hours
- Compression cooldown: 24 hours
- Base risk: 0.50% of initial equity per trade
- Strong-bull or engine-agreement risk: 0.75%
- Risk conditions never compound
- Same-symbol overlap remains prohibited
- Trend retains priority over Compression at identical symbol and entry time

## User-directed capacity change

The maximum position count is increased from three to five. This is an explicit
architecture instruction, not a conclusion from RD16-H evidence.

The open-risk cap remains 2.25%. Therefore five positions are permitted by the
position-count rule, but the risk budget can still reject the fourth or fifth
position. RD16-J must measure the realized capacity, cash utilization, drawdown,
fees, and capital feasibility.

## Causality

Routing uses only entry time, signal time, symbol, engine identity, engine
agreement, market regime, active-position state, cooldown state, and risk budget.
Realized PnL, MFE, MAE, holding duration, and exit reason never decide admission.

## Restrictions

Spot only, Long only, no leverage, margin, shorts, derivatives, borrowing,
DCA, Kelly sizing, pyramiding, averaging down, or same-symbol overlap. The 2025
and 2026 periods remain sealed.

## Output interpretation

A successful RD16-I result means the V2 architecture is reproducibly registered
and ready for a fixed economic baseline. It does not authorize production.

## Next stage

`RD16J_FIXED_COMPOSITE_ALPHA_V2_BASELINE_EVALUATION`
