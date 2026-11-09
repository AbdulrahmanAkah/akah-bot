# AKAH — C2 original 364 pairs: Fast bulk historical market collection V4

## Scope and authority

Primary source is **not** `c2-operational-membership.csv` (29/35). It is:
`data/research/rd18_p3x_a1_runtime/full-c2-hourly-acquisition-plan.csv`, with exact 364 unique pairs and two required columns `pair` / `symbol`. Original inventory classification file: `data/research/rd18_p1r2/raw-inventory-classification.csv`.

The old RD18 data-acquisition inventory is NOT a historical point-in-time trading eligibility certificate. No portfolio trades, no 2024, no live orders, no repo changes.

## Major speed improvements

1. Check pre-existing `data/raw/rd16b/kucoin/<pair>/1h.parquet` first, with a *pre-2024 timestamp predicate* and only approved rows included in outputs.
2. Reuse cached 29-asset files in `Downloads/AKAH_C2_MARKET_VAULT_V2/raw/kucoin/spot/<pair>`.
3. KuCoin historical *1day/1hour* candles are paged in 1,200-candle windows instead of downloading monthly day, hour, minute, and aggTrades ZIPs one by one.
4. Concurrent processing of up to 10 assets with global request pacing, limited back-off for 429/418, a network circuit breaker, and checkpoints after successful windows. Interrupted execution can be restarted via the same PowerShell command.
5. Independent Binance spot daily history for cross-venue evidence, with 1h fallback only when KuCoin 1h coverage is insufficient. **Never silently merge different exchanges**.
6. Historical USD-M funding when published, independent from spot candles.
7. Export full pre-2024 daily features (SMA/EMA/RSI/ATR/MACD, returns), descriptive observed breadth, per-pair log price SVG charts, and exact asset-level coverage. These are descriptive, not trained strategies.

## What this cannot truthfully guarantee

- Before exchange listing or coin invention no candle source exists for that symbol/venue.
- Some original 21 historical-only symbols may need specific archival providers that public current APIs do not serve.
- Historical BTC/stablecoin global dominance, total market cap and complete historical orderbook depth cannot be inferred reliably from OHLCV. These are **not supplied** by this package and must not be claimed as complete.
- Historical full-resolution minute and trade-tick data for all 364 symbols would be much larger and slower; this package prioritizes the complete, usable daily+hourly panel before supplementary tick acquisition.
- 2022–2023 are already exposed to research; none of these outputs demonstrate independent trading profitability.

## Running one command

Download `RUN_AKAH_C2_364_FAST_BULK_V4.ps1` to `%USERPROFILE%\Downloads`, then:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$HOME\Downloads\RUN_AKAH_C2_364_FAST_BULK_V4.ps1"
```

Files are preserved in `Downloads\AKAH_C2_364_FAST_V4`. Rerun the **same command** if connectivity fails.

## Uploads

First upload `Downloads\AKAH_C2_364_FAST_UPLOAD_PACKETS_V4\UPLOAD_THIS_AKAH_C2_364_ANALYSIS_AND_COVERAGE_V4.zip`.
This includes exact 364 source plan, coverage per pair, annual summary, observed breadth and the actual per-pair charts. For full inspection of raw hourly/daily, upload `UPLOAD_THIS_AKAH_C2_364_RAW_PART_0001.zip` and subsequent parts. Each file is packetized with a maximum approximately 65 MB of raw gz content.

The machine-level test was run on synthetic files, not the user's actual Windows environment, and proves program behavior rather than real historical completeness.
