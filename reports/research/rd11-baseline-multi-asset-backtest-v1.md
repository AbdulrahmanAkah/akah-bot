# RD11 Baseline Multi-Asset Backtest v1

## Executive summary

RD11 completed a frozen, non-optimized baseline for
`AKAH_REGIME_MOMENTUM_BREAKOUT_V1` across BTC/USDT, ETH/USDT, ADA/USDT,
AVAX/USDT, and DOT/USDT. The strategy specification remained byte-for-byte
unchanged at SHA-256
`dda3e786f473320139290cebde2edf551ba3255cd89834684e5afc2b67c696ad`.

Technical status is PASS. Evidence classification is MIXED under the
preregistered rule, but the result is not a claim of superior performance:
the strategy returned 7.3472% while the equal-weight buy-and-hold benchmark
returned 232.5038%. The main measured benefit was a materially lower maximum
drawdown, 5.6140% versus 50.0130%.

## Data and window

- Local source: `data/research/multi_asset_daily/kucoin`
- Eligible assets: all five target assets; no exclusions
- Common data window: 2022-06-17 through 2024-12-31 inclusive
- Warm-up: first 200 completed daily bars
- Evaluation: 2023-01-03 through 2024-12-31 inclusive
- Initial cash: 100,000 USDT
- No 2025 or 2026 observation was opened or evaluated
- No Dune API or network acquisition was used

The longest complete daily intersection was selected before calculating
strategy results. The exclusive boundary `2025-01-01` is only a range guard.

## Frozen execution assumptions

- Signal at completed daily close; fill at the next daily open
- 0.10% fee and 0.05% adverse slippage per fill
- 1% equity risk budget per trade
- 25% maximum allocation per position
- Two simultaneous positions maximum
- One position per asset, shared cash, long-only Spot
- No leverage, margin, shorts, DCA, Kelly, pyramiding, or averaging down
- Simultaneous entries rank by breakout strength, volume ratio, RSI, then
  symbol
- At a shared open, eligible sell orders execute before buy orders

## Per-asset results

| Asset | Signals | Trades | Net return | Final equity | Profit factor | Expectancy | Max drawdown | Buy-and-hold |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| ADA/USDT | 5 | 3 | 2.1743% | 102,174.32 | 2.5022 | 724.77 | 1.8410% | 243.6048% |
| AVAX/USDT | 3 | 2 | -1.4320% | 98,568.05 | 0.0000 | -715.98 | 3.0759% | 230.0106% |
| BTC/USDT | 21 | 13 | 8.3594% | 108,359.40 | 2.3348 | 643.03 | 5.1538% | 456.7853% |
| DOT/USDT | 5 | 4 | -2.6391% | 97,360.93 | 0.1357 | -659.77 | 4.1220% | 52.8973% |
| ETH/USDT | 9 | 6 | -1.5390% | 98,461.00 | 0.5710 | -256.50 | 3.4304% | 179.2212% |

All per-asset samples contain fewer than 30 closed trades and are explicitly
marked `insufficient_trade_sample=true`.

## Portfolio and benchmark

- Signals: 43; entry signals: 29
- Orders: 53; fills: 48; closed trades: 24; open positions at end: 0
- Slot rejections: 5; cash rejections: 0
- Final equity: 107,347.24 USDT
- Net return: 7.3472%; CAGR: 3.6211%
- Gross profit: 20,394.91; gross loss: -12,388.49
- Fees: 659.18; slippage cost: 329.59
- Win rate: 37.50%; expectancy: 306.14; profit factor: 1.5752
- Maximum drawdown: 5.6140%; Sharpe: 0.5596; Sortino: 0.4445
- Exposure: 32.7846%; average positions: 0.4444; observed maximum: 2
- Benchmark final equity: 332,503.84
- Benchmark net return: 232.5038%; CAGR: 82.7234%
- Benchmark maximum drawdown: 50.0130%; Sharpe: 1.3039
- Strategy minus benchmark: -225.1566 percentage points
- Drawdown improvement: 44.3990 percentage points

Net PnL contribution was BTC +8,316.35, ADA +2,141.96, AVAX -423.73,
DOT -1,001.31, and ETH -1,686.04. BTC supplied 113.19% of portfolio net
profit because other assets had negative contributions. This exceeds the
preregistered 80% concentration limit.

## Time and regime attribution

The strategy returned 1.3665% in 2023 and 5.9001% in 2024, versus benchmark
returns of 143.4071% and 36.1613%. Under the frozen BTC EMA regime:

- Bull: 623 days, 23 trades, 7.3472% strategy return, profit factor 1.7191
- Bear: 10 days, no trades, 0% strategy return
- Sideways/transition: 96 days, one losing trade, expectancy -1,069.52

This attribution is descriptive only and does not alter the strategy.

## Validation and repairs

All signal/order/fill/trade, fee, slippage, cash, position, equity,
contribution, and benchmark reconciliations passed. Replay hashes matched for
all five independent runs and the portfolio run.

One integration defect was found before finalization: same-timestamp pending
orders were executed in symbol order, which could evaluate a buy before a
different asset's exit. Batch execution now processes all eligible sells
before buys at the shared open. A regression test covers this behavior. A
portfolio reporting defect that inherited a single-asset buy-and-hold return
was also corrected to use the equal-weight portfolio benchmark.

Quality gates passed: 492 research tests with warnings treated as errors,
8 focused RD11 tests, 9 engine regression tests, strict mypy on all changed
Python files, Ruff check and format verification, Python byte compilation,
27 JSON parses, 38 CSV validations, six run-validation reports, secret scan,
and `git diff --check`.

## Interpretation

RD12 corrected the original POSITIVE label to MIXED. The original calculation
incorrectly divided BTC contribution by total positive contributions rather
than portfolio net profit. BTC contribution of 8,316.35 divided by portfolio
net profit of 7,347.24 is 113.19%, which violates the frozen 80% limit.
Technical gates still pass, but sample sizes are small and absolute return
substantially trails buy-and-hold.

## Decision

- Decision: `RD11_BASELINE_MULTI_ASSET_BACKTEST_COMPLETED`
- Evidence classification: `MIXED`
- Correction: `RD11_EVIDENCE_CLASSIFICATION_CORRECTED_TO_MIXED`
- Next stage: `RD12_REGIME_AND_COMPONENT_ATTRIBUTION`

RD12 was not started.
