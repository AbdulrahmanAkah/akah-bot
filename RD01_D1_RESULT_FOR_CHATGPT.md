# AMS RD01-D1 — Dominance Trade Tagging

## Executive result

- Status: `COMPLETE`
- Variant: `MD01-M05`
- Fold count: `3`
- Financial invariance: `True`
- Trade logic changed: `NO`
- Overlay authorized: `NO`
- ATI-V1 authorized: `NO`

## Ledger rows

- `candidates`: `151` rows
- `selections`: `157` rows
- `fills`: `294` rows
- `trades`: `147` rows

## Fold fingerprints

| Fold | Before | After | Invariant |
|---|---|---|---|
| `WF01` | `bfea9d7c82c79716e6ce19b60a537de5f83c802c3b758e876fb4c3198ae6bd99` | `bfea9d7c82c79716e6ce19b60a537de5f83c802c3b758e876fb4c3198ae6bd99` | `True` |
| `WF02` | `1b7a649b8f7ca64a0232be4f65cecc879abebb5cd7a9d8f03d520d49e4dfecb6` | `1b7a649b8f7ca64a0232be4f65cecc879abebb5cd7a9d8f03d520d49e4dfecb6` | `True` |
| `WF03` | `e0c95a0d11e46bd1e4a348802277e775129d8d85c3bb310ff7b0e3321fef5848` | `e0c95a0d11e46bd1e4a348802277e775129d8d85c3bb310ff7b0e3321fef5848` | `True` |

## Safety boundaries

- Tags are derived after simulation.
- No candidate, selection, fill, or trade is modified.
- No production, live trading, MD02, Kelly, or leverage authorization.
