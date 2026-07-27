# RD04-D0 — Point-in-Time Universe Readiness

## Purpose

Audit whether the frozen 2021–2024 Coin Metrics market-cap panel and the
registered local OHLCV/availability datasets are sufficient to replace the
fixed thirty-symbol survivor-risk universe with a causal changing universe.

## Scope

- Reuse the RD01 frozen raw market-cap panel.
- Construct Monday 00:00 UTC market-cap candidate snapshots from observations
  available with a one-day lag.
- Rank the top 30 raw market-cap candidates at each M05 rebalance.
- Compare those candidates with the symbols that have complete registered
  4H, 8H, 1D, and venue-availability data.
- Produce a local-data gap manifest with appearance counts and historical ranks.
- Measure current M05 symbol-level PnL concentration.
- Preserve exact financial fingerprints for all three M05 folds.

## Decision gate

- `PIT_UNIVERSE_REPLAY_READY`: all 157 weekly top-30 snapshots are complete and
  every candidate has registered local OHLCV and availability.
- `PIT_UNIVERSE_DATA_EXPANSION_REQUIRED`: market-cap snapshots are complete but
  one or more candidates lack required local data.
- `BLOCKED_BY_MARKET_CAP_DATA`: the frozen panel cannot produce complete weekly
  top-30 snapshots.

Only `PIT_UNIVERSE_REPLAY_READY` authorizes RD04-D1 full-portfolio replay
research. It does not authorize a universe change.

## Safety boundaries

- No ranking, alignment, target weight, entry, fill, exit, or cash decision changes.
- No 2025 test or 2026 holdout access.
- No production, live trading, MD02, Kelly, leverage, pyramiding, or averaging down.
- Raw market-cap rank is not treated as proof of venue tradability.
