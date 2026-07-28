# RD04-D5C0 Implementation

This stage freezes the external source registry required by the registered
RD04-D5C idiosyncratic-tail diagnostic before any source is joined to a trade.

The registry contains five direct-asset events and ten public sources:

- Terra UST/LUNA collapse.
- Celsius insolvency.
- Voyager insolvency.
- FTX/FTT collapse.
- USDC's recovered SVB-related depeg.

The registry fixes taxonomy, direct symbols, aliases, UTC event intervals,
persistence, source provenance, inclusion boundaries and D5C1 join semantics.
Terminal issuer or protocol failures remain associated through the end of the
2021–2024 research window. The recovered USDC event uses a finite acute window.

This stage does not read market data, the trade ledger, trade outcomes or PnL.
It does not join labels, exclude symbols or change any strategy behaviour. A
successful result authorizes the D5C1 diagnostic join only.
