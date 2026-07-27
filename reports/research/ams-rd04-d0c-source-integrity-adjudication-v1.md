# AMS RD04-D0C — Source Integrity Adjudication

## Executive result

- Status: `COMPLETE`
- Decision: `PIT_UNIVERSE_REPLAY_READY`
- Reason: `ALL_WEEKLY_TOP_30_DATASETS_COMPLETE_AFTER_SOURCE_ADJUDICATION`
- D0B symbols adjudicated: `75`
- Nonblocking unavailable symbols: `39`
- Recoverable symbols: `2`
- Recovered symbols: `BCH,MATIC`
- True blocking integrity failures: `0`
- Adjudicated dataset symbols: `66`
- Complete weekly snapshots: `157`
- Minimum selected count: `30`
- Financial invariance: `True`
- RD04-D1 replay research authorized: `True`
- Universe change authorized: `NO`
- Trade logic changed: `NO`
- ATI-V1 authorized: `NO`

## Adjudication rule

- A failed optional alias does not invalidate a complete acquired primary source.
- A deterministic unavailable-pair response is venue absence, not candle corruption.
- Only malformed acquired data, invalid alias transitions, or unresolved source errors block.
- Missing candles are not filled and observed availability remains causal.

## Safety boundary

- No entry, exit, ranking, alignment, weighting, fill, or cash rule is changed.
- The original registered AMS-V3 datasets remain unchanged.
- No 2025 test data or 2026 holdout data are accessed.
- No production, live trading, leverage, Kelly, pyramiding, or averaging down is authorized.
