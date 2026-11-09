# AKAH BOT — Direct-Chart / Data-First Research Archive (through C2 V20)

**Archive snapshot:** 2026-11-09. **Research-only. Not a certified trading strategy.**

This repository subtree preserves the research work created after AKAH shifted from pre-invented rules to studying historical charts, every available candle, wave starts/peaks/reentries, and portfolio economics. It includes the original stage packets, scripts, result tables, detailed reports, and source-lineage inventories. It does not overwrite production trading code or change live settings.

## Research lineage

- **R54–R57:** causal reclaim tests, external paper-lab and independent broker accounting checks; no verified profitable alpha. Independence of broker arithmetic is not independence of the shared entry signal.
- **C2 V1–V5:** source-first market acquisition and local offline recovery; original C2 plan **364 assets**, but not point-in-time certified. Multi-venue market history, derived indicators and available external sources inventoried. Data coverage uneven.
- **C2 V6:** roughly 6.4M hourly rows and 335 usable local-pair tapes. Price/volume/breadth studies and 24 scenarios independently reconciled. **Fatal signal-admission error:** future contiguous bars were required in the event generator; false impression of clean causality. ~96.9% of hourly quote turnover estimated rather than source-native; major apparent profit removed by excluding RATS.
- **V7:** fourteen timeframes and multi-timeframe conditional profiles; no general proof of positive net alpha.
- **V8:** all hourly candles rising >=1%; peak finality, later reclaim and daily-as-of indicators; "ultimate top" cannot be known at entry and trailing reversal alone does not ensure finality.
- **V9:** scored impulse signals/exit policy trials; initial +22.02% 2022–2023 defensive portfolio not causally reliable, profits concentrated.
- **V10:** historic wave census and attribution of missed waves; V9 entered only a tiny proportion of large waves. Removing the filters entirely also performed poorly.
- **V11:** corrected time-ordered portfolio and signal admission; prior +22.02% became roughly +14.80% in not-fully-identical comparison, 2022 remained negative. Several dynamic exits failed.
- **V12:** sustained trend riders, pyramiding, platform selection and BTC comparisons. Individual INJ and SOL outsized winners discovered, but portfolio profits dependent on few assets and BTC benchmark strong.
- **V13–V18:** integrated BTC/alt allocation, top-N rotation, swap budget, ATR-based trailing, daily risk guard and pre-2024 multi-regime comparison. No durable alt superiority; 2020–2023 baseline itself may have large drawdowns.
- **V19:** eight signal policies, 44 economic scenarios; some historical multi-regime outcomes beat a restricted BTC baseline but max drawdowns remained substantial. 2023 >=5x wave capture remained incomplete. Historical validation contaminated by repeated iteration.
- **V20:** independent 2023 5× opportunity mapping and economics, causal previous-day signal execution, technical/hourly/funding feature ranking. 2020–2023 continuation portfolio +490.29%, max daily DD -41.43%; double-cost/exclude-top3 +246.59%, max DD -49.44%. Learned pre-Oct-2021 model produced AUC **0.5614** in 2022, **0.5829** in 2023; learned ranking did not beat matched BTC baseline. 54 post-hoc 5× waves in 2023; 14 waves entered, only nine had positive aggregate trade PnL in the broad early-new engine. No certified edge.

## Non-negotiable data rules

1. **2024 and all later market data remain sealed.** The user explicitly restricts research through 2023-12-31. No live exchange orders or activation.
2. PIT eligibility at each timestamp must be proved. A universe built from survivors or later listings is **not** time-tradable retroactively.
3. Event existence and candidate ranking must not be conditioned on future bar availability, profitability, completed labels or historical winners.
4. Daily/weekly/monthly indicators and external data must be lagged to actual publication/close availability. 2022–2023 have repeatedly been inspected and are **not pristine holdouts**.
5. A historical high or future max drawup is an **ex-post diagnostic only**, never an executable sell price; missing end-of-tape is right-censored. Intrabar stop order cannot be invented from OHLC.
6. Quote turnover based on base-volume × price is a **proxy**, not an exchange-reported original. Order-book slippage, liquidity, fees, gaps, and delistings require fail-closed treatment.
7. Realized trade returns and continually marked-to-market cash/equity are distinct; accounting parity does not prove profitable entry signals. Record `scenario_id`, venue/pair identity and allocation opportunity costs.
8. The user's objective is aggressive upside capture, but results cannot be described as guaranteed +10% weekly or +1000% yearly. No path to guaranteed profit in every regime has been demonstrated.

## Structure

- `stage_packets/`: original delivered small/medium research packets, including V8 analytical and V10 wave-census intermediate files.
- `stage_results/`: per-version source code, trade ledgers, NAVs, integrity checks, model features and comparisons.
- `loose_source_and_reports/`: scripts and independent reports provided across the research.
- `reconciled_sources/`: C2 candidate plans, symbol sets, independent rally audit, provenance tables.
- `inventory/UPSTREAM_LOCAL_ASSET_REGISTRY_SHA256.json`: local root-level archive inventory and SHA-256 including raw archives **not embedded in Git**.
- `inventory/INTEGRITY_MANIFEST.json`: SHA-256 and byte count for every archived payload file.

## Material not embedded in Git

Large raw historical candle/volume-part archives (including multiple V4/V5/V6 upload pieces and the ~95.5MB all-1% V8 event ZIP) remain on the user's local disk / conversation attachments. The inventory retains their names, byte counts and SHA-256. This Git snapshot preserves research evidence and code, **not a self-contained replica of every original market-data byte**. Exact market-data replay requires the user's raw-tape files.

**Workflow:** branch-only archival snapshot; review before merge; no production settings altered, and no live order sent.
