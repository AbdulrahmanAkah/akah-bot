# AMS RD04-D5B0 — V5R1 ATR Grid Recovery

## Executive result

- Status: `COMPLETE`
- Decision: `V5R1_BOUNDED_STRUCTURAL_ATR_PROTOCOL_RECOVERED`
- Reason: `V5R1_SOURCE_DEFINES_BOUNDED_STRUCTURAL_MODELS_NOT_A_DISCRETE_ATR_GRID`
- V5R1 source blob matched: `True`
- D4 range matches STRUCTURE_BALANCED: `True`
- Explicit discrete ATR-grid candidates found: `0`
- D5B1 stop-protocol adjudication authorized: `True`
- D5B execution authorized: `False`

## Source-derived contract

- `STRUCTURE_BALANCED`: minimum `2.2 ATR`, maximum `3.4 ATR`.
- `STRUCTURE_WIDE`: minimum `2.6 ATR`, maximum `4.0 ATR`.
- Entry stop distance is the larger of structural distance and the model minimum; a structural distance above the model maximum is rejected.
- Effective entry `stop_atr` can vary continuously inside the model bounds.
- D4's frozen `2.2–3.4 ATR` range identifies `STRUCTURE_BALANCED`, not an outcome-selected stop.

## Safety boundary

- No portfolio simulation or parameter optimisation was executed.
- No realised outcome was used to select a stop.
- No 2025 test or 2026 holdout data was accessed.
- No trading, universe, ranking, weight, entry, exit, ATI, or production change.
