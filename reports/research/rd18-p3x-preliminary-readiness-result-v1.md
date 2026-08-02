# RD18-P3X Preliminary Readiness Result

## Decision

`RD18_P3X_DATA_AND_GENERATOR_BUILD_REQUIRED`

Next stage:

`RD18_P3X_A1_FULL_C2_HOURLY_DATA_AND_GENERATOR_BUILD`

## Data status

The corrected acquisition scope contains 364 C2 pairs. The committed RD16B 1h manifest contains six symbols: AVAX, BTC, ETH, LINK, NEAR and SOL. At manifest level, 358 corrected pairs have no registered hourly source, so maximum manifest coverage is 1.6484% before pair-specific window and file checks.

The included offline runner produces the exact 364-row acquisition plan from committed local artifacts. It checks file presence, hashes, pair-specific historical starts, the sealed cutoff and prior readiness evidence.

## Generator status

The registered V3 architecture starts from prepared ledgers. It does not expose a raw-OHLCV candidate-regeneration entrypoint. The retained Trend and Compression engines must be extracted and then matched exactly against the six-symbol control before any new symbol is evaluated.

This is not permission to redesign the strategy. Parameters, timing, engine priority, cooldowns, risk rules and holding rules remain frozen.

## Authorization

Authorized:

- full corrected C2 hourly data acquisition;
- frozen raw candidate-generator extraction;
- control-parity testing.

Not authorized:

- three-universe economic replay;
- return or PnL calculation;
- trade generation;
- optimization;
- production.
