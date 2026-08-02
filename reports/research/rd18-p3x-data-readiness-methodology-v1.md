# RD18-P3X Full-Universe Data and Candidate-Generator Readiness

## Purpose

P3X prevents the three-universe replay from repeating the RD16-PIT-A2 limitation. The old dynamic replay re-routed a candidate ledger generated from six symbols; it did not regenerate the frozen strategy for every historical universe member.

This stage therefore audits two independent prerequisites before any return calculation:

1. complete causal KuCoin Spot 1h history for the corrected C2 scope;
2. a deterministic raw-OHLCV implementation of the retained `COMPOSITE_ALPHA_V3` candidate rules.

## Acquisition scope

The acquisition scope is all 364 corrected C2 pairs, not only assets that happened to enter a Top-6 list. D2 is contained by C2 and E2 is derived from C2. Acquiring all corrected C2 pairs is a conservative, membership-independent rule and prevents data availability from becoming an implicit selection filter.

The local runner reads `corrected-daily-coverage-audit.csv`, creates one acquisition row per eligible ordinary Spot pair and compares it with the committed RD16B hourly source manifest and validation ledger.

## Timeframes and warm-up

The frozen feature implementation uses:

- 1h EMA50;
- 4h EMA50;
- 1d EMA200 with 120 minimum observations;
- 1w EMA40 with 30 minimum observations.

The binding minimum feature warm-up is therefore 30 weeks, or 5,040 hours. A pair lacking enough history is recorded as `FEATURE_WARMUP_NOT_READY`. It is not silently treated as `NO_SIGNAL`.

Context joins remain backward-looking and use completed context bars only.

## Candidate-generator requirement

`rd16l_architecture.py` validates and registers prepared candidate, evaluated and trade ledgers. It is not an end-to-end raw-OHLCV signal generator. P3X-A1 must extract the retained Trend and Compression rules into one deterministic entrypoint.

Before that entrypoint may process new assets, it must reproduce the original six-symbol control candidate ledger exactly, including timestamps, engine identity, candidate/no-signal decisions and reason codes. PnL is not used to establish parity.

## Explicit decision coverage

Every operational weekly member in C2, D2 and E2 must receive exactly one of:

- `CANDIDATE`;
- `NO_SIGNAL`;
- `FEATURE_WARMUP_NOT_READY`;
- `DATA_UNAVAILABLE_BLOCK`.

A missing row is a blocking data or implementation error. It is not a no-signal observation.

## Prohibitions

P3X does not calculate returns, construct trades, rank universes, tune parameters or access data after 2024. Strategy replay remains unauthorized until all data, generator, parity and determinism gates pass.
