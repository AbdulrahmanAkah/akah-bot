# RD12 Regime and Component Attribution v1

## Result

All twelve frozen configurations completed with matching deterministic
replays and full reconciliation. The RD11 baseline reproduced exactly.
Technical status is PASS. No variant was selected as a replacement strategy.

## Portfolio comparison

| Configuration | Return | Delta | Trades | PF | Expectancy | Max DD | DD delta |
|---|---:|---:|---:|---:|---:|---:|---:|
| Baseline | 7.3472% | 0.0000% | 24 | 1.5752 | 306.14 | 5.6140% | 0.0000% |
| E01 no long-term trend | 7.3472% | 0.0000% | 24 | 1.5752 | 306.14 | 5.6140% | 0.0000% |
| E02 no medium alignment | 30.2050% | +22.8578% | 30 | 2.7786 | 1,006.83 | 6.2930% | +0.6790% |
| E03 no RSI entry | 11.5481% | +4.2008% | 29 | 1.7193 | 398.21 | 5.0630% | -0.5510% |
| E04 no volume | 5.3361% | -2.0111% | 28 | 1.3680 | 190.58 | 7.2243% | +1.6103% |
| E05 no volatility sanity | 6.7732% | -0.5740% | 26 | 1.4926 | 260.51 | 6.5741% | +0.9601% |
| X01 no trailing stop | 7.2510% | -0.0963% | 24 | 1.5423 | 302.12 | 6.2059% | +0.5919% |
| X02 no EMA50 exit | 6.6649% | -0.6824% | 24 | 1.4990 | 277.70 | 6.2010% | +0.5871% |
| X03 no RSI exit | 5.3994% | -1.9479% | 24 | 1.3900 | 224.97 | 6.3272% | +0.7133% |
| X04 no time stop | 6.1132% | -1.2340% | 21 | 1.6054 | 291.11 | 6.9529% | +1.3389% |
| G01 breakout core only | 37.9518% | +30.6045% | 44 | 2.6267 | 862.54 | 9.2528% | +3.6388% |
| G02 stop and time only | 6.9941% | -0.3532% | 24 | 1.4426 | 291.42 | 7.4937% | +1.8797% |

The equal-weight buy-and-hold benchmark remains 232.5038% and is a general
reference only, not a component classifier.

## Component attribution

All nine individual component labels are INCONCLUSIVE because the frozen
baseline has 24 closed trades, below the preregistered minimum of 30. This
sample gate takes precedence over attractive or weak point estimates.

- Long-term trend was observationally neutral: its removal changed nothing.
- Medium-term alignment removal improved three assets and portfolio return,
  but remains inconclusive rather than being labeled harmful.
- RSI entry removal improved all five per-asset point estimates, but produced
  only 29 portfolio trades and remains inconclusive.
- Volume-confirmation removal reduced portfolio return and profit factor and
  increased drawdown, but agreement was only two improved and two worsened
  assets; it remains inconclusive rather than supportive.
- Volatility sanity and all four exit rules remain inconclusive.
- G01 and G02 are DIAGNOSTIC_ONLY and cannot receive component labels.

## Concentration

Baseline BTC contribution divided by portfolio net profit was 113.19%.
Removing medium-term alignment shifted the largest contribution to ADA and
reduced the ratio to 70.27%. The grouped breakout-core diagnostic reduced the
largest-asset ratio to 51.78% and increased profitable assets to three.
Conversely, removing RSI entry raised BTC dependence to 134.30%, and the
grouped stop/time exit diagnostic raised it to 157.16%.

These are attribution observations, not redesign choices.

## Years and regimes

Baseline returned 1.3665% in 2023 and 5.9001% in 2024. The strongest
descriptive configuration, G01, returned 11.4357% and 23.7949%; the weakest,
E04, returned 0.0652% and 5.2675%.

Baseline bull return was 7.3472% from 23 trades. G01 produced 27.0052% in bull,
2.3354% during the ten-day bear sample, and 9.5216% in transition. E04
produced 5.3361% in bull and 0.1027% in transition. The bear sample is too
small for reliable inference.

## Technical validity

Every configuration passed chronological processing, next-bar execution,
no-look-ahead, signal/order/fill/trade linkage, PnL, fee, cash, position,
equity, asset-contribution, and benchmark reconciliation. No negative cash,
leverage, margin, short, DCA, Kelly sizing, pyramiding, or averaging down was
observed.

Quality gates passed: 502 research tests with warnings treated as errors,
10 focused RD12 tests, 9 engine regression tests, strict mypy, Ruff check and
format verification, Python byte compilation, JSON and CSV parsing, validation
report checks, secret scanning, and `git diff --check`.

## Decision

- Decision: `RD12_REGIME_AND_COMPONENT_ATTRIBUTION_COMPLETED`
- Evidence: component effects remain predominantly inconclusive due sample size
- Next stage: `RD13_SAMPLE_EXPANSION_WITH_FROZEN_RULES`

RD13 was not started.
