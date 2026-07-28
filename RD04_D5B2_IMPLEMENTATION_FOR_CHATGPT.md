# RD04-D5B2 Implementation

This stage evaluates the RD04-D5B1 registered V5R1-derived exit-only structural
stop overlay on both the fixed and point-in-time universes.

The treatment engine is generated deterministically from the frozen M05 source.
Its `stop_overlay=False` path must be result-identical to the original M05
engine. The treatment preserves M05 candidate logic, next-open entries, entry
weights, and transaction-cost accounting. It adds only the registered fixed
exit overlay:

- ATR14 SMA true range from completed 4H bars.
- Prior 12 completed-bar low, excluding the signal bar.
- Distance clipped to `[2.2, 3.4] ATR`.
- Stop frozen at signal close.
- Gap-at-open and intrabar-low execution.
- No V5R1 sizing, trailing, add-ons, re-entry, or other exits.

The stage uses only 2021–2024 research data and three registered cost modes.
Even a positive result authorizes the next research stage only.
