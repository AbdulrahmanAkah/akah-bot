# RD18-P3E Final Decision

## Decision

**Candidate disposition: REJECTED — WORST_UNIVERSE_ECONOMIC_FAILURE.**

The preregistered COMPOSITE_ALPHA_V3 / STRONG_BULL_HOLD_96 candidate is not eligible for advancement or production.

## Decision precedence

Technical execution was valid. The first failing category in the frozen precedence order is worst-universe economic failure. Later findings cannot override that result.

## Corrected base runs

| Universe | Cost | Trades | Net return | Profit factor | Max drawdown | Minimum cash |
|---|---:|---:|---:|---:|---:|---:|
| C2 | 1x | 1206 | 99.59% | 1.2035 | 19.61% | 1,061.29 |
| C2 | 2x | 1007 | -7.34% | 0.9842 | 54.11% | 216.59 |
| D2 | 1x | 1194 | 101.18% | 1.2104 | 18.78% | 27.59 |
| D2 | 2x | 1106 | -7.91% | 0.9842 | 53.20% | 45.17 |
| E2 | 1x | 1219 | 87.36% | 1.1769 | 20.12% | 1,061.29 |
| E2 | 2x | 1006 | -8.37% | 0.9819 | 54.77% | 216.59 |

All corrected runs were cash-feasible. All three 2x runs were negative, while D2 and E2 also failed required 1x economic gates.

## Sensitivity

| Test | Cost | Runs | Positive | PF ≥ 1 | Net-return range |
|---|---:|---:|---:|---:|---:|
| LOAO | 1x | 79 | 79 | 79 | 10.69% to 122.77% |
| LOAO | 2x | 79 | 5 | 5 | -58.29% to 12.20% |
| LOYO | 1x | 18 | 18 | 18 | 12.38% to 125.05% |
| LOYO | 2x | 18 | 7 | 7 | -35.62% to 35.43% |

All LOYO and LOAO 1x runs remained positive with profit factor at least 1.0. Named BCHSV-USDT and PEPE-USDT omissions caused no conclusion reversal. This supports sensitivity robustness but does not repair the failed base economic gates.

## Strategic objective

Frozen target: **24% geometric monthly return**. Worst corrected universe: **0.913%**.

## Failed frozen gates

- C2: `two_x_maximum_drawdown_maximum`
- C2: `two_x_net_return_strictly_positive`
- C2: `two_x_profit_factor_minimum`
- D2: `both_engines_positive`
- D2: `one_x_positive_active_year_fraction_minimum`
- D2: `top_engine_profit_share_maximum`
- D2: `two_x_maximum_drawdown_maximum`
- D2: `two_x_net_return_strictly_positive`
- D2: `two_x_profit_factor_minimum`
- E2: `one_x_profit_factor_minimum`
- E2: `top_engine_profit_share_maximum`
- E2: `two_x_maximum_drawdown_maximum`
- E2: `two_x_net_return_strictly_positive`
- E2: `two_x_profit_factor_minimum`

## Closure

- P3E is closed with no advancement.
- Production remains unauthorized.
- No 2025 or 2026 holdout data was accessed.
- No threshold or per-universe tuning is permitted.
- Any continuation requires a new candidate under a new preregistered protocol.
