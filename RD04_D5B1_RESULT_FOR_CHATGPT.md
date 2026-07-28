# AMS RD04-D5B1 — Structural Stop Protocol Adjudication

## Executive result

- Status: `COMPLETE`
- Decision: `V5R1_DERIVED_EXIT_ONLY_STOP_OVERLAY_REGISTERED`
- D5B2 stop-execution research authorized: `True`
- Legacy exact V5R1 bundle execution authorized: `False`
- Point-in-time universe baseline authorized: `False`
- Trade logic changed: `False`

## Frozen exit-only overlay

- Control and treatment use the same M05 entries and entry quantities.
- ATR is 14-bar SMA true range on completed 4H bars.
- Structure is the minimum low of the prior 12 completed 4H bars.
- Applied distance is `clip(raw structural distance, 2.2, 3.4) ATR`.
- The stop price is frozen at signal close and is active from the entry bar.
- Gap execution: `OPEN_IF_OPEN_LE_STOP`; intrabar execution: `STOP_PRICE_IF_LOW_LE_STOP`.
- No V5R1 sizing, trailing, add-ons, re-entry, or other exits are imported.

## Conflict resolutions

- `ENTRY_REJECTION_VS_ENTRY_PARITY`: Never reject an otherwise valid M05 entry. Clip the signal-time structural distance to the closed interval [2.2, 3.4] ATR.
- `RISK_SIZING_VS_WEIGHT_PARITY`: Preserve the exact M05 entry fill quantity and cash accounting. The stop may alter exits only.
- `V5R1_EXIT_BUNDLE_VS_SINGLE_ABLATION`: Enable one fixed initial stop only. Disable all other V5R1 exits, trailing, add-ons, risk throttles, and V5R1 re-entry.
- `SIGNAL_STOP_VS_NEXT_OPEN_GAP`: Freeze the stop price at signal close. Fill M05 at the normal next open; if that open is at or below the stop, exit immediately at the same open and charge both entry and exit costs.

## Safety boundary

- Registration only; no market data or portfolio simulation.
- No 2025 test or 2026 holdout access.
- No parameter search or outcome-selected stop.
- No universe, ranking, entry, weight, production, live, or ATI change.
