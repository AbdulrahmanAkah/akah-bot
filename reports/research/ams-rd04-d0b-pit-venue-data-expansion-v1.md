# AMS RD04-D0B — Point-in-Time Venue Data Expansion

## Executive result

- Status: `COMPLETE`
- Decision: `BLOCKED_BY_DATA_INTEGRITY`
- Reason: `ONE_OR_MORE_ACQUIRED_SYMBOL_DATASETS_FAILED_INTEGRITY`
- Weekly snapshots: `157`
- Complete venue-eligible top-30 snapshots: `157`
- Minimum selected count: `30`
- Acquisition symbols attempted: `75`
- Complete acquired symbols: `34`
- Symbols without KuCoin history: `3`
- Expanded dataset symbols: `64`
- Financial invariance: `True`
- RD04-D1 replay research authorized: `False`
- Universe change authorized: `NO`
- Trade logic changed: `NO`
- ATI-V1 authorized: `NO`

## Source contract

- KuCoin Spot 4H public candles are requested directly by venue pair.
- Both the legacy Spot candle endpoint and the UTA Spot kline endpoint are supported.
- Current market-list membership is not required before probing historical candles.
- Missing candles are never forward-filled or price-filled.
- Disconnected candle segments become separate observed availability intervals.
- The original registered AMS-V3 dataset is not overwritten.

## Decision meaning

- `PIT_UNIVERSE_REPLAY_READY` authorizes only RD04-D1 full-portfolio replay research.
- `PIT_UNIVERSE_SOURCE_EXPANSION_REQUIRED` authorizes only another source-expansion stage.
- `BLOCKED_BY_DATA_INTEGRITY` means acquired data failed an immutable integrity gate.

## Safety boundary

- No ranking, alignment, weight, entry, exit, fill, or portfolio cash decision is changed.
- No 2025 test data or 2026 holdout data are accessed.
- No production, live trading, MD02, Kelly, leverage, pyramiding, or averaging down is authorized.
