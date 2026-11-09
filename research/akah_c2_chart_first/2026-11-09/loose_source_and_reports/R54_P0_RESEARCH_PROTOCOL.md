# AKAH BOT — R54-P0: Source Authority, Causal Event Census, and Economic Gate

**Status:** Research protocol. Not a demonstrated edge; no live/production change.

## Frozen premises

- Prior RD33 result (reported, to be re-bound to canonical sources): C2 158 trades in 2022–2023, win rate 35.44%, final $142,163 at 1X and $132,780 at 2X, max DD 14.76% at 2X, PF 1.412 at 2X. 2022 negative and 2023 positive. Yearly consistency gate failed.
- R50 (reported): 12 frozen economic cells required. The reference universe/cost/execution definitions must be recovered from canonical evidence rather than inferred from these summaries.
- R53R1 (reported): 48 recovered portfolio results, 36 comparisons, 12 R50 references. Three alternative architectures did not outperform R50 in overall growth. A had better drawdown in one top-20 configuration but sacrificed growth.
- Historical universes must be PIT-qualified. RD04's large fixed-universe vs historically dynamic-universe discrepancy means any hindsight membership invalidates economic claims.
- **2024 is sealed**: never open its tapes, rows, market files, trade files, or use it for fitting, selection, or validation. No 2024 optimization. Treat combined/mixed-year datasets containing 2024 as forbidden until separately and provably partitioned without opening the sealed portion.
- 2022–2023 are research/diagnostic years, no longer independent strategy-discovery holdouts.

## Phase 1 — source/authority binding (delivered now)

Read-only local discovery. Locate and SHA-confirm actual source files and revision state; surface candidate paths for original RD33 entry/exit code, R50 frozen comparisons, R53R1 recovery, PIT membership table, hourly price/volume tapes, fee and slippage definitions, and portfolio capital/MTM rules. ZIP central directories and 2022/2023 CSV headers may be inspected, but archive members, trade rows, and market rows are **not** parsed. No economic computations or new parameter selection.

**Stop until source authorities are pinned.** Filename resemblance is not source certification. A mechanical PASS never substitutes for historical PIT certification.

## Phase 2 — causal event census (NOT executed in Phase 1)

Once historical PIT membership and 2022–2023 per-pair tapes are certified, build a chronological event ledger for 24h, 168h, and 720h lows. For each closed hourly candle at timestamp t, compute the minimum low of previous N fully closed candles, excluding t. A *primitive* reclaim candidate occurs only if low(t) is strictly below that prior level and close(t) strictly exceeds it. This is a diagnostic event, **not** an authorized entry signal. Use original RD33 72h grammar as an independent frozen comparator after recovering its code; do not assert that the primitive equals RD33. Derive 4h confirmation only from closed 4h bars if ultimately specified, not from partially open bars. No peeking into 2024.

Emit *all* events in PIT-eligible universe with unique `(pair, timestamp, horizon)` IDs, zero-eligible windows, suppressed duplicate signals, delist/coverage censor flags, and source tape fingerprint. Track opportunity-to-execution eligibility separately. No costs/returns labels should be read while defining candidate events. Record event incidence by year/week/pair/horizon and intersection of horizons. Do not count three coincident horizons as three independent trades.

## Phase 3 — precommitted economic tests (NOT executed in Phase 1)

Replicate RD33 original and R50 original with 1X and 2X cost assumptions, same executable universe and cash accounting. Establish exact portfolio parity or explain structural noncomparability before comparing strategies. Freeze representative treatment/control entry definitions *before* calculating economic results. Test failed reclaim vs successful reclaim, adverse excursion, gap/slippage, trade occupancy, realized and marked-to-market weekly PnL, regime interactions, top-one/top-three winner removal, pair exclusion, simultaneous entries, and calendar-year 2022 and 2023 separately. Apply next-bar executable prices, never current close at information time. Use historical price/volume to estimate capacity, and explicitly label spread/depth uncertainty if unavailable. No fabricated market depth or impossible fills.

Factorial comparison design (not yet authorized to execute):

| Arm | Purpose |
|---|---|
| A0 | Frozen RD33 baseline |
| A1 | Frozen R50 baseline |
| A2 | Tactical reclaim only; candidate rules frozen ex ante |
| A3 | RD33 plus upgrade-to-trend, one intervention at a time |
| A4 | R50 plus tactical reclaim; shared capital ledger |
| A5 | Integrated lifecycle with one risk budget per asset |

All arms must use identical fees, slippage policy, chronology, and compatible historical universe. Avoid combining independently calculated PnL curves. Report incremental effect vs appropriate frozen comparator. Where year-on-year gates fail, treat the candidate as failed; do not redesign using that same result as if a fresh validation remains.

## Phase 4 — decision rule

Promote research only if causal/coverage audit passes, cross-year net results are acceptable under the pre-registered governance gates, the improvement remains after doubled costs and removing dominant winners, and portfolio-level capacity/liquidity/DD constraints hold. A stronger monthly turnover or trade count is not sufficient. A result in these two already-viewed years is exploratory and cannot certify future earnings.

## What to send back from Phase 1

Only upload the file named `UPLOAD_THIS_AKAH_R54_P0_SOURCE_DISCOVERY_<timestamp>.zip` generated locally in Downloads. It includes source candidate paths, safe ZIP entry metadata, header probes, governance status, repo HEAD, and authority decision ledger. No local trading keys or raw price data should be copied to the upload.
