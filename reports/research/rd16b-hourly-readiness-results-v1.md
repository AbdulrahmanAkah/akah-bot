# RD16-B Hourly Data Readiness Results v1

## Decision

- Decision: `RD16B_HOURLY_DATA_READINESS_AND_CAUSAL_AGGREGATION_COMPLETED`
- Evidence classification: `READY`
- Technical status: `COMPLETED`
- Assets passed: **6 / 6**
- Next stage: `RD16C_REGISTERED_INTRADAY_STRATEGY_FAMILIES_SMOKE_TESTS`

## Technical gates

| Gate | Result |
|---|---:|
| Frozen asset configuration | PASS |
| Canonical source is 1H | PASS |
| All six assets ready | PASS |
| Deterministic replay | PASS |
| Listing start verified online | PASS |
| Frozen inputs unchanged | PASS |
| No partial aggregate bars | PASS |
| 2025 test sealed | PASS |
| 2026 holdout sealed | PASS |

## Asset readiness

| Asset | Status | 1H rows | First close | Last close | Coverage gate | Missing | Aligned rows |
|---|---:|---:|---|---|---:|---:|---:|
| BTC/USDT | PASS | 52608 | 2019-01-01T01:00:00+00:00 | 2025-01-01T00:00:00+00:00 | True | 0 | 52297 |
| ETH/USDT | PASS | 52608 | 2019-01-01T01:00:00+00:00 | 2025-01-01T00:00:00+00:00 | True | 0 | 52297 |
| SOL/USDT | PASS | 28848 | 2021-09-17T01:00:00+00:00 | 2025-01-01T00:00:00+00:00 | True | 0 | 28609 |
| LINK/USDT | PASS | 37488 | 2020-09-22T01:00:00+00:00 | 2025-01-01T00:00:00+00:00 | True | 0 | 37177 |
| AVAX/USDT | PASS | 33168 | 2021-03-21T01:00:00+00:00 | 2025-01-01T00:00:00+00:00 | True | 0 | 32977 |
| NEAR/USDT | PASS | 28848 | 2021-09-17T01:00:00+00:00 | 2025-01-01T00:00:00+00:00 | True | 0 | 28609 |

## Interpretation

RD16-B is a pipeline gate. A `READY` result authorizes registered
intraday strategy-family smoke tests. `PARTIAL` or `BLOCKED` requires
data remediation and does not authorize strategy evaluation.
