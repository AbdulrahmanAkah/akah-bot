# AKAH C2 — V20 Independent Research Decision (9 November 2026)

**Status: exploratory research, not certified trading edge; 2024 sealed; no live orders.**

## What was independently checked

- 305 daily asset tapes / 295,119 daily bars assembled from 481 underlying source records, with 2020–2023 cutoff.
- Signals taken as of the previous daily close, no future outcome filtering to decide when a signal exists.
- Deduplicated per-pair per-day signals; one entry event at least 90 days apart per asset to reduce outcome-window overlap. This is a diagnostic sample, **not a realistic portfolio**.
- Compared ex-post >5x wave discovery to *actual entries and closed-trade net PnL*, not only the signal's presence in hindsight.
- Checked accounting: sum of closed PnL equals end-liquidated balance minus $100,000, while last daily marked NAV differs by exit liquidation costs. This explains observed -$871 to -$2,177 differences in six inspected portfolios, not unexplained arithmetic drift.

## 90-day +50% before -20% signal criterion, 90d nonoverlap per asset

| Year | N | Successful |
|---|---:|---:|
| 2020 | 152 | 52.63% |
| 2021 | 389 | 48.33% |
| 2022 | 320 | 14.06% |
| 2023 | 273 | 32.60% |

This label is an ex-post outcome and does not correspond to a guaranteed sale at +50%, especially with daily OHLC intrabar ambiguity, fees or depth.

## Fixed pre-October-2021 multilayer model (price, technical, hourly and funding)

- AUC 2022: **0.5614**; AUC 2023: **0.5829**; weak distinction outside training. Training metrics above 0.8 are misleading if used as proof of deployability. The 2022/2023 evaluations are not virgin holdouts, because prior AKAH versions have repeatedly inspected those years.
- Portfolio evaluation of 2022–2023 after same nominal transaction assumptions: model learned rank **+39.51%, max drawdown -23.04%**, original unranked all-signal policy **+15.94%, drawdown -29.85%**; comparable BTC-core baseline **+59.29%, drawdown -19.37%**. Thus the multilayer learned rank failed to beat simple BTC at matched engine settings.

## Ex-post 2023 fivefold wave opportunity coverage

**54 waves >=5×** under the source study's ex-post yearly trough-to-peak definition, of which **24** reached estimated $3m prior-day liquidity *at some point during the wave*. That does **not** prove adequate liquidity at the actual entry or exit.

| Portfolio | Entered of 54 waves | Positive aggregate trade PnL in wave | Entered of 24 tagged liquid | Positive aggregate trade PnL |
|---|---:|---:|---:|---:|
| Early new 75% | 14 | 9 | 12 | 7 |
| Early consolidation 75% | 7 | 3 | 6 | 2 |
| Continuation 60% | 9 | 4 | 8 | 3 |
| High-conviction 60% | 13 | 6 | 12 | 6 |

Even a wave being entered is *not* a profitable capture. A wave appearing liquid at some point is not contemporaneous liquidity qualification for execution.

## Multi-regime portfolio stress 2020–2023

- Continuation 60%: +490.29% total, -41.43% maximum daily close drawdown; 2022 -1.55%, 2023 +56.31%. Under double fees/slippage and exclude top 3 profit pairs, +246.59% total, drawdown -49.44%, 2023 +19.80%.
- High conviction 60%: +451.78% total, drawdown -38.02%; 2022 -0.84%, 2023 +53.64%. Double costs and excluded top 3: +196.30%, drawdown -52.90%.
- BTC-only: +340.31% total, drawdown -53.24%, 2023 +59.93%.
- Earlier-stage 75% early-new: +263.00%, drawdown -64.91%, 2022 -33.12%. Early consolidation: +353.55%, drawdown -39.57%, 2022 -18.46%.

**None of these established an empirically validated +10% per week or +1000% per year system, nor consistent gains in downtrends.** Relative performance depends on regime, vintage and chosen family.

## Main constraints / reasons to withhold certification

1. Original C2 universe membership is not historically PIT-certified; relistings/renames and survival bias need explicit point-in-time treatment.
2. Quote-side volume for many underlying hourly bars was estimated; order books, depth, spreads, queue and participation certainty remain unvalidated.
3. Signal features vary by available source; missing hourly/funding is explicit, not uniformly comprehensive across every asset.
4. Only a fraction of the large-wave universe is actually entered and closed profitably.
5. Ticker winners contribute disproportionally to performance; removing top 3 drastically reduces performance.
6. 2022/2023 previously inspected; parameters and architectures are research products, not independently precommitted tests.
7. Trailing stops on historical daily bars depend on intrabar ordering assumptions. This engine conservatively checks pre-existing stops before raising them using today's high, but unknown stop liquidity/gaps remain.
8. Testing more variants against the same history will increase selection bias, not credibility.

## Next research gate

**V21** should target *ranking and capital competition* at each decision timestamp, with a precommitted and logged score that compares every eligible active wave, and a multi-state portfolio controller (trend, recovery, chop, cash/BTC). Treat replay funding and hourly context as optional factors only if they add incremental predictive value in strictly chronological folds. Include a fixed cross-sectional audit for all missed 5× waves and their first causal signal, and calculate ex-post opportunity ceiling vs real PnL captured. After this design, require a truly unexamined evaluation source/time period prior to claiming edge. 2024 market data remain off limits.

The strategy's aim may be aggressive, but outcomes must be grounded in executable signals and realized net return, not selecting historical winners or promising wins in all conditions.
