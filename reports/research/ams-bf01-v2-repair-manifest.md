# AMS BF01 V2 — Exact-Schema Repair

This branch repairs the confirmed BF01 V1 extraction and interpretation failures.

## Enforced invariants

- Exact entity IDs only.
- Aggregate and fold metrics remain separate.
- Explicit units for every metric.
- Percent scaling exactly once.
- `snapshot_time` retained as a date alias.
- Metadata cannot become performance metrics.
- Missing M02 contributor evidence returns `NOT_EVALUATED`.
- Spot return, drawdown and exposure domain gates are enforced.
- Risk-adjusted Alpha remains unauthorized without aligned validated series.

## Generated outputs

- `reports/research/ams-bf01-source-inventory-v2.csv`
- `reports/research/ams-bf01-benchmark-fairness-metrics-v2.csv`
- `reports/research/ams-bf01-m02-contributors-v2.csv`
- `reports/research/ams-bf01-regression-v2.csv`
- `reports/research/ams-bf01-benchmark-fairness-alpha-audit-v2.json`
- `reports/research/ams-bf01-benchmark-fairness-alpha-audit-v2.md`
- `BF01_V2_RESULT_FOR_CHATGPT.md`