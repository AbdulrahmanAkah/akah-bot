# RD16-C Registered Intraday Families Results v1

## Official classification

- Decision: `RD16C_REGISTERED_INTRADAY_STRATEGY_FAMILIES_SMOKE_TESTS_COMPLETED`
- Technical status: `COMPLETED`
- Evidence classification: `READY_FOR_FIXED_BASELINE`
- Families passed: `4/4`
- Next stage: `RD16D_FIXED_INTRADAY_FAMILY_BASELINE_EVALUATION`

## Family smoke summary

| Family | Status | Candidates | Trades | Assets | Diagnostic return | PF |
|---|---:|---:|---:|---:|---:|---:|
| MTF_TREND_BREAKOUT | PASS | 1994 | 968 | 6 | 0.320155 | 1.115226 |
| MTF_PULLBACK_RECLAIM | PASS | 3711 | 1839 | 6 | 0.188076 | 1.037216 |
| MTF_COMPRESSION_EXPANSION | PASS | 2613 | 1332 | 6 | 0.378985 | 1.106717 |
| MTF_RANGE_RECLAIM | PASS | 3781 | 2937 | 6 | -1.690037 | 0.801161 |

Diagnostic returns are descriptive only. They were not used as a
pass/fail gate, ranking input, optimization target, or winner-selection
criterion.

## Technical gates

| Gate | Result |
|---|---:|
| Four families registered | PASS |
| Four smoke tests passed | PASS |
| Constraints pass | PASS |
| Causality pass | PASS |
| Deterministic replay | PASS |
| Frozen inputs unchanged | PASS |
| 2025 sealed | PASS |
| 2026 sealed | PASS |
| Winner selection absent | PASS |
| Optimization absent | PASS |
