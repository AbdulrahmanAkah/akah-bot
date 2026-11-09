# AKAH R55 — Mega One-Pass comparative research

**Why this run:** all six R54 reclaim strategies failed 2X whole-period profitability; W168 was closest to breakeven. This R55 run does *not* promote any strategy. It compares predefined past-only gates and two new distinct mechanisms against byte-identical R54 baseline economics.

## Run
Save `RUN_AKAH_R55_MEGA_V1.ps1` into `Downloads` and run one PowerShell command:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$HOME\Downloads\RUN_AKAH_R55_MEGA_V1.ps1"
```

Upload `UPLOAD_THIS_AKAH_R55_MEGA_<timestamp>.zip` from Downloads.

## Work completed in one pass
- Re-read 20 frozen 1H tape slices for 2022 and 2023; SHA verify 2022 and 8759 hours 2023 per pair; recompute frozen 13,830 reclaim event count.
- Run R54 W168 & D24 exact-parity baselines and verify five benchmark cells.
- 12 research policies × 4 cost/latency scenarios; 12 leave-largest-positive-pair-out full portfolio reruns.
- Export 2X trade-by-trade journals, daily NAV and weekly mark-to-market for all 12 arms.
- Independent sum-of-journal, daily NAV, weekly and annual reconciliation; 2024 market rows read = 0.
- Report positive-both-years, 2X, delay, extra slip, drawdown, top-pair-exclusion, and trade count gates; no result is automatically selected.

## Policy definitions (fixed before rerun)
- BASE_W168 and BASE_D24: R54 comparators, no modification of signal definitions.
- W168_BTC30_RISE: weekly reclaim only if 30-day mean and 7-day trend of BTC support entry.
- W168_BTC90_RISE: same with 90-day moving mean.
- W168_ASSET30_RISE: weekly reclaim only if own asset beats its 30-day mean and 7-day past close.
- W168_BTC30_ASSET30: both market and asset 30-day conditions.
- W168_HOLD336: weekly reclaim with 14-day instead of 7-day maximum hold, unchanged 12% stop.
- D24_BTC30_ASSET30: daily reclaim gated by market and own-asset positive trend.
- B20_CLOSED_BREAKOUT: close of completed bar above prior 20-day high; next-hour-open entry; 14-day hold/15% stop.
- B20_BTC30_BREAKOUT: same with BTC 30-day gate.
- XS_28D_WEEKLY_TOP3: weekly positive 28-day momentum ranking, 3 highest assets, first fill after Sunday 23:00 UTC close.
- XS_28D_BTC30_TOP3: same cross-sectional momentum but only when BTC 30-day trend is positive.

## Boundaries and caveats
- Dataset: 20 retrospectively selected assets, not exchange PIT-qualified. No venue spread/order book, no certified execution capacity. NO 2024.
- Fee/slippage scenarios come from R54, NOT from RD33/R50. Original reference results are not directly comparable across cohorts.
- Repeated prior inspection of 2022–2023 means results cannot establish independent alpha. These are mechanistic rejection/discovery tests only.
- No live orders, no private keys, no production changes; output files are written to Downloads only.
- Warmup: the 30- and 90-day rules cannot issue signals until sufficient in-contract 2022 hourly history is available; this can materially affect 2022 trade frequency and economics.
- The spot-only stop is triggered by a **completed bar close**, with execution at the next open, not an intrabar guaranteed stop.
- We keep one command per stage while maximizing related tasks per bundle.
