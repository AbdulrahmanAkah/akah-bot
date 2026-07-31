# RD16-B Hourly Data Readiness Methodology v1

## Purpose

RD16-B validates the data foundation required by the intraday
multi-timeframe architecture. It does not test or optimize a trading
strategy.

## Frozen architecture

- Canonical source: completed 1H Spot OHLCV candles.
- Structure context: 4H.
- Regime context: 1D.
- Macro context: 1W.
- Exchange: KuCoin Spot.
- Pilot universe: BTC, ETH, SOL, LINK, AVAX and NEAR against USDT.
- Official cutoff: 2025-01-01T00:00:00Z.
- 2025 post-cutoff and 2026 holdout data remain sealed.

## Acquisition

The runner validates every market as explicitly Spot and rejects
contracts, swaps, futures and options. Listing discovery is
point-in-time aware: each asset begins at its first available hourly
candle rather than being forced into a common pre-listing start. The
official gate also requires at least 1,000 days of pre-cutoff hourly
coverage per asset.

Raw and derived Parquet datasets are stored under `data/raw/rd16b`.
That directory is local and ignored by Git.

## Aggregation

Context candles are derived only from the canonical hourly source.

- 4H requires exactly 4 consecutive hourly children.
- 1D requires exactly 24.
- 1W requires exactly 168.
- 4H and 1D boundaries are anchored to UTC midnight.
- 1W boundaries close Monday at 00:00 UTC.
- Partial edge groups are rejected.
- Groups with missing children are rejected.
- OHLCV values are never forward-filled.

Hourly timestamps represent candle close time. Each context candle is
therefore labeled by the close of its completed aggregation window.

## Causal alignment

Every 1H signal row receives the latest completed 4H, 1D and 1W
context whose close timestamp is less than or equal to the signal
candle close. Future context and context older than one full context
duration are hard failures.

## Readiness gates

An asset passes only when:

1. Hourly OHLCV is valid, unique and continuous.
2. The dataset reaches the official cutoff without exceeding it.
3. All three derived timeframes contain complete bars.
4. No interior aggregation group is dropped.
5. Derived timeframes remain continuous.
6. Multi-timeframe alignment contains no future or stale context.
7. Deterministic replay reproduces the same audit records.

RD16-C may begin only when all six pilot assets pass.
