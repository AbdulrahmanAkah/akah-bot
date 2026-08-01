# RD16-PIT-A2A Cash and Equity Floor Provenance Audit

## Objective

Verify whether the identical cash and equity floors reported by the frozen V3
control and the PIT dynamic reroute are genuine consequences of a shared
portfolio event or artifacts of reused state, shared arrays, or an incorrect
accounting path.

## Independent reconstruction

The audit reconstructs each hourly row without calling the official equity
builder. Exits are processed before entries, matching the registered execution
convention. For each timestamp it records:

- cash before events;
- exit proceeds and exit fees;
- entry notional and entry fees;
- free cash and reserved cash;
- marked market value;
- equity;
- cumulative fees;
- entering, exiting, and open trade IDs.

The accounting model has no separate reserve ledger. Therefore free cash equals
cash and reserved cash is explicitly zero.

## Identities

Cash after events must equal:

`cash_before + exit_notional - exit_fees - entry_notional - entry_fees`

Equity must equal:

`cash + market_value`

Both identities are checked on every hourly row.

## Floor provenance

For minimum cash and minimum equity at 1x, 1.5x, 2x, and 3x costs, the audit
records the exact timestamp, open positions, marks, event flows, and an event
signature. Equal numerical values are not treated as explained unless timestamp,
open trade set, and event signature also agree.

## Boundaries

This stage does not regenerate signals, optimize parameters, authorize RD16-U,
authorize an RD17 trading run, or access 2025/2026 data.
