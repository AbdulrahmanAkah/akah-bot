# RD04-D5B1 Implementation

This stage adjudicates the conflict between the recovered V5R1 bounded
`STRUCTURE_BALANCED` protocol and the frozen RD04-D4 requirements that M05 entry
logic and entry weights remain unchanged.

It registers a V5R1-derived exit-only overlay:

- 14-bar SMA true range on completed 4H bars.
- Prior 12 completed-bar low, excluding the signal bar.
- Structural distance clipped to `[2.2, 3.4] ATR`.
- Stop price frozen at signal close.
- The normal M05 next-open fill and quantity are preserved.
- The fixed stop is active from the entry bar.
- No V5R1 risk sizing, trailing, add-ons, re-entry, or other exits.

This is a protocol-registration stage only. It reads no market data and executes
no portfolio simulation. A successful result authorizes RD04-D5B2 research
execution only.
