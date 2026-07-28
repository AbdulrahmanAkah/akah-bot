# AMS RD04-D5C0 — External Tail-Event Source Freeze

## Executive result

- Status: `COMPLETE`
- Decision: `EXTERNAL_TAIL_EVENT_SOURCE_REGISTRY_FROZEN`
- Frozen events: `5`
- Frozen sources: `10`
- Registry fingerprint: `83a12b88d47715e551d8fee78688e0005a8e9cf3be6f386a9393c4e30b52d3be`
- D5C1 diagnostic join authorized: `True`
- Trade join executed: `False`
- Trade outcomes read: `False`
- Trade logic changed: `False`

## Frozen events

- `TERRA_UST_LUNA_COLLAPSE_2022`: LUNA,UST; 2022-05-09T00:00:00Z to 2025-01-01T00:00:00Z; TERMINAL_IMPAIRMENT
- `CELSIUS_INSOLVENCY_2022`: CEL; 2022-06-12T00:00:00Z to 2025-01-01T00:00:00Z; TERMINAL_IMPAIRMENT
- `VOYAGER_INSOLVENCY_2022`: VGX; 2022-07-01T18:00:00Z to 2025-01-01T00:00:00Z; TERMINAL_IMPAIRMENT
- `FTX_FTT_COLLAPSE_2022`: FTT; 2022-11-11T00:00:00Z to 2025-01-01T00:00:00Z; TERMINAL_IMPAIRMENT
- `USDC_SVB_DEPEG_2023`: USDC; 2023-03-10T00:00:00Z to 2023-03-14T00:00:00Z; ACUTE_RECOVERED

## Join boundary

- Direct symbols and frozen aliases only.
- Half-open UTC event intervals.
- All PIT control trades remain unchanged.
- Labels indicate association, not causation.
- No event-derived blacklist or trade exclusion.

## Safety boundary

- Registration only; no trade ledger or market data read.
- No 2025 test or 2026 holdout access.
- No production, live, ATI, universe, ranking, entry, exit, or weight authorization.
