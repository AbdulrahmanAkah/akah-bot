# AMS BF02 — Daily-Series Source Discovery

## Repository state

- Branch: `research/ams-bf02-aligned-daily-series-evidence-v1`
- HEAD: `88eb0d7d7fca63a7e8b197ad435fead80be98bf8`
- Discovery status: `DAILY_SERIES_CANDIDATES_FOUND`
- JSON sources inspected: `9`
- Candidate series found: `12`
- Referenced artifacts found: `5`

## Source summaries

| Source | Schema | Size | Candidates | References |
|---|---|---:|---:|---:|
| `reports/research/ams-md01-final-assessment-v1.json` | `ams-md01-final-assessment-v1` | 337102 | 0 | 0 |
| `reports/research/ams-md01-benchmark-comparison-v1.json` | `ams-md01-benchmark-comparison-v1` | 37295 | 0 | 0 |
| `reports/research/ams-md01-m05-base-cost-v1.json` | `ams-md01-variant-result-v1` | 1225029 | 12 | 0 |
| `reports/research/ams-md01r1-survivor30-reproduction-v1.json` | `ams-md01r1-survivor30-reproduction-v1` | 196624 | 0 | 5 |
| `reports/research/ams-rd01-benchmark-comparison-v1.json` | `ams-rd01-benchmark-comparison-v1` | 644 | 0 | 0 |
| `reports/research/ams-rd01-benchmark-comparison-v2.json` | `ams-rd01-causal-benchmark-comparison-v2` | 1423 | 0 | 0 |
| `reports/research/ams-rd01-btc-beta-diagnostics-v1.json` | `ams-rd01-btc-beta-diagnostics-v1` | 10585 | 0 | 0 |
| `reports/research/ams-rd01-concentration-diagnostics-v1.json` | `ams-rd01-concentration-diagnostics-v1` | 2679 | 0 | 0 |
| `reports/research/ams-rd01-ati-v1-final-assessment.json` | `ams-rd01-ati-v1-final-assessment` | 4299 | 0 | 0 |

## Highest-value series candidates

| Source | JSON path | Kind | Length | Date keys | Value keys |
|---|---|---|---:|---|---|
| `reports/research/ams-md01-m05-base-cost-v1.json` | `fold_results/[1]/fill_ledger` | `RECORD_LIST` | 118 | `timestamp` | `cash_after, cash_before, portfolio_heat_after, portfolio_heat_before, price` |
| `reports/research/ams-md01-m05-base-cost-v1.json` | `fold_results/[2]/fill_ledger` | `RECORD_LIST` | 118 | `timestamp` | `cash_after, cash_before, portfolio_heat_after, portfolio_heat_before, price` |
| `reports/research/ams-md01-m05-base-cost-v1.json` | `fold_results/[0]/fill_ledger` | `RECORD_LIST` | 58 | `timestamp` | `cash_after, cash_before, portfolio_heat_after, portfolio_heat_before, price` |
| `reports/research/ams-md01-m05-base-cost-v1.json` | `fold_results/[2]/selection_ledger` | `RECORD_LIST` | 53 | `timestamp` | `` |
| `reports/research/ams-md01-m05-base-cost-v1.json` | `fold_results/[0]/selection_ledger` | `RECORD_LIST` | 52 | `timestamp` | `` |
| `reports/research/ams-md01-m05-base-cost-v1.json` | `fold_results/[1]/selection_ledger` | `RECORD_LIST` | 52 | `timestamp` | `` |
| `reports/research/ams-md01-m05-base-cost-v1.json` | `fold_results/[2]/candidate_ledger` | `RECORD_LIST` | 61 | `` | `fill_price, target_weight` |
| `reports/research/ams-md01-m05-base-cost-v1.json` | `fold_results/[1]/candidate_ledger` | `RECORD_LIST` | 59 | `` | `fill_price, target_weight` |
| `reports/research/ams-md01-m05-base-cost-v1.json` | `fold_results/[1]/trade_ledger` | `RECORD_LIST` | 59 | `` | `entry_price, exit_price, gross_pnl, net_pnl, return_fraction` |
| `reports/research/ams-md01-m05-base-cost-v1.json` | `fold_results/[2]/trade_ledger` | `RECORD_LIST` | 59 | `` | `entry_price, exit_price, gross_pnl, net_pnl, return_fraction` |
| `reports/research/ams-md01-m05-base-cost-v1.json` | `fold_results/[0]/candidate_ledger` | `RECORD_LIST` | 31 | `` | `fill_price, target_weight` |
| `reports/research/ams-md01-m05-base-cost-v1.json` | `fold_results/[0]/trade_ledger` | `RECORD_LIST` | 29 | `` | `entry_price, exit_price, gross_pnl, net_pnl, return_fraction` |

## Referenced artifacts

| Reference | Resolved path | Exists | Suffix | Size | Rows | Columns |
|---|---|---|---|---:|---:|---|
| `ams-md01r1-survivor30-md01-m01-base-cost-reproduction-v1.json` | `ams-md01r1-survivor30-md01-m01-base-cost-reproduction-v1.json` | `False` | `.json` |  |  | `` |
| `ams-md01r1-survivor30-md01-m01-stress-cost-reproduction-v1.json` | `ams-md01r1-survivor30-md01-m01-stress-cost-reproduction-v1.json` | `False` | `.json` |  |  | `` |
| `ams-md01r1-survivor30-md01-m01-zero-cost-reproduction-v1.json` | `ams-md01r1-survivor30-md01-m01-zero-cost-reproduction-v1.json` | `False` | `.json` |  |  | `` |
| `ams-md01r1-survivor30-md01-m02-base-cost-reproduction-v1.json` | `ams-md01r1-survivor30-md01-m02-base-cost-reproduction-v1.json` | `False` | `.json` |  |  | `` |
| `ams-md01r1-survivor30-md01-m02-zero-cost-reproduction-v1.json` | `ams-md01r1-survivor30-md01-m02-zero-cost-reproduction-v1.json` | `False` | `.json` |  |  | `` |

## Interpretation boundary

This file is schema discovery only. It does not authorise an Alpha conclusion, production use, MD02, Kelly sizing, leverage, or access to 2025/2026.
