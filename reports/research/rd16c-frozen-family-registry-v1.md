# RD16-C Frozen Family Registry v1

| Family | Stop ATR | Max bars | Description |
|---|---:|---:|---|
| MTF_TREND_BREAKOUT | 1.5 | 48 | 1H breakout with aligned bullish 4H, 1D and 1W context. |
| MTF_PULLBACK_RECLAIM | 1.25 | 48 | 1H EMA20 reclaim inside aligned higher-timeframe uptrend. |
| MTF_COMPRESSION_EXPANSION | 1.5 | 48 | 1H range expansion from non-expanding 4H volatility. |
| MTF_RANGE_RECLAIM | 1.25 | 48 | 1H downside sweep and reclaim with non-bearish daily/weekly context. |

## Registration discipline

All thresholds were frozen before the official run. RD16-C does not
perform grid search, parameter tuning, family ranking, or winner
selection. Every family uses completed 1H candles, causally aligned
4H/1D/1W context, next-1H-open entry, a fixed ATR stop, conservative
stop-first intrabar handling and a fixed 48-bar maximum hold.
