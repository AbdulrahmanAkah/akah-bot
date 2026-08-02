# RD18-P2S2 methodology

RD18-P2S2 recomputes graded structural uncertainty using the corrected C2
and D2 panels.  The valid claim remains `RESTRICTED_TO_376_KLINE_CONFIRMED_HISTORICAL_KUCOIN_SPOT_PAIRS`; this is not an exhaustive
KuCoin inventory claim.  The primary feasibility window is the 301
post-warm-up Monday decisions; all 313 decisions are retained diagnostically.

The committed P1R2 C2 rankings are reused.  D2 rankings are derived
deterministically from the same corrected eligibility rows, liquidity metric,
listing-age tie-break, and canonical-ID tie-break.  No market-data acquisition
occurs.  No set intersection is used to create a universe, Variant E is not
constructed, and no returns, trades, signals, candidates, or optimization are
performed.

The old P2S consensus construction is not repeated.  P2S2 only audits whether
a future confidence-aware design is justified at adjacent operational
boundaries.
