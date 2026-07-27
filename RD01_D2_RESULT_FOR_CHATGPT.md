# AMS RD01-D2 — Dominance Attribution and BTC-Beta Controls

## Executive result

- Status: `COMPLETE`
- Daily attribution rows: `16`
- Trade attribution rows: `16`
- Stability rows: `4`
- Overlay decision made: `NO`
- ATI-V1 authorized: `NO`

## Stability summary

| Quadrant | Valid daily folds | Valid trade folds | Daily excess consistent | Trade expectancy consistent |
|---|---:|---:|---|---|
| `BTC_DOWN_STABLE_DOWN` | 3 | 3 | `True` | `False` |
| `BTC_DOWN_STABLE_UP` | 3 | 3 | `True` | `False` |
| `BTC_UP_STABLE_DOWN` | 3 | 3 | `False` | `False` |
| `BTC_UP_STABLE_UP` | 3 | 3 | `False` | `False` |

## Safety boundaries

- D2 is attribution only.
- No M05 decision or execution rule is changed.
- D3 remains the only overlay authorization gate.
- No production, live trading, MD02, Kelly, or leverage authorization.
