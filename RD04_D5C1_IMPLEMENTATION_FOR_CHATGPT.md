# RD04-D5C1 Implementation

This stage joins the independently frozen RD04-D5C0 direct-asset event registry
to the unchanged RD04-D5B2 PIT-universe control trades at base transaction cost.

The join uses direct symbols and frozen aliases only. A trade is associated when
its canonical symbol matches an event and its interval overlaps the frozen UTC
event interval. Exposure already open when an event starts is reported as
`PRE_EVENT_EXPOSURE`; entry during the event interval is reported separately as
`EVENT_WINDOW_ENTRY`.

All 153 PIT control trades must remain present, in the same order, with every
original field byte-for-byte unchanged. Event metadata is appended only.
Overall metrics count each labelled trade once. Event and category attribution
tables are diagnostic and can be non-additive when multiple labels apply.

Loss share is calculated from loss amounts `max(-net_pnl, 0)`, not from net PnL,
so profitable trades cannot conceal labelled losses. No trade or symbol is
excluded, no market data is read and no portfolio simulation is performed.
The result is diagnostic only and cannot authorize a production change.
