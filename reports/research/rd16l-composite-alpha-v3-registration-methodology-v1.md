# RD16-L — Registered COMPOSITE_ALPHA_V3 Architecture

## Purpose

RD16-L registers the only RD16-K remediation variant that passed all fixed
capital, robustness, return-preservation, and bull-capture gates:
`STRONG_BULL_HOLD_96`.

This is an architecture-registration and deterministic smoke-test stage.
It is not a new economic baseline, optimization stage, winner-selection
exercise, or production authorization.

## Frozen source

- Source architecture: `COMPOSITE_ALPHA_V2`
- Source stage: RD16-K
- Source variant: `STRONG_BULL_HOLD_96`
- Source candidate ledger: 688 rows
- Source admitted trades: 567 rows
- Source development period remains sealed at the registered cutoff.
- 2025 and 2026 are not accessed.

## COMPOSITE_ALPHA_V3 policy

V3 preserves all V2 entry, routing, risk, and capacity rules:

- Spot-only and Long-only.
- No leverage, margin, shorts, derivatives, borrowing, DCA, Kelly,
  pyramiding, or averaging down.
- Maximum configured positions: 5.
- Maximum open risk: 2.25% of frozen initial equity.
- Base trade risk: 0.50%.
- Strong-Bull or engine-agreement risk: 0.75%, non-compounding.
- Trend cooldown: 12 hours.
- Compression cooldown: 24 hours.
- Same-symbol overlap remains prohibited.
- Trend retains routing priority over Compression.

The sole registered change is the holding horizon:

- `STRONG_BULL`: maximum 96 bars.
- All other regimes: maximum 48 bars.

The hard-stop-first and profit-floor logic inherited by the retained RD16-K
ledger is preserved exactly.

## Registration checks

RD16-L verifies:

1. RD16-K completed and retained exactly `STRONG_BULL_HOLD_96`.
2. Tracked RD16-K output hashes.
3. Local candidate, evaluated, and trade ledger file and content hashes.
4. Source row counts and candidate identity alignment.
5. Deterministic V3 identifier and engine remapping.
6. No same-symbol overlap.
7. Engine cooldown compliance.
8. Maximum five positions and 2.25% open-risk compliance.
9. 96/48 holding-policy compliance.
10. Sealed cutoff, Spot-only, and Long-only constraints.

## Next stage

`RD16M_FIXED_COMPOSITE_ALPHA_V3_BASELINE_EVALUATION`

RD16-M must independently reconstruct V3 economics and cost stress. The
diagnostic PnL emitted by registration is not an economic pass gate.
