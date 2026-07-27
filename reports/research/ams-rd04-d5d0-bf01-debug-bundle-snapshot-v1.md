# BF01 Debug Bundle for Source-Mapping Repair

This bundle is diagnostic only. The current BF01 result contains invalid units and source mappings.

Generated: 2026-07-26T23:20:54+03:00

## Git State

```text
Branch: research/ams-bf01-benchmark-fairness-alpha-audit-v1
HEAD: d4b1563c8a92ee48b6cfca2461e7dafc71ee2d28

Latest commits:
d4b1563 research: complete bf01 benchmark fairness and alpha audit
02d91d6 research: complete causal high beta benchmarks
fb40c00 research: complete rd01 ati v1 assessment
6d51abd research: implement ati foundation and survivor shadow diagnostics
22bb80a research: add btc beta and survivor concentration diagnostics

Working tree before bundle:

```

## User-Facing BF01 Result

Path: `BF01_RESULT_FOR_CHATGPT.md`

```text
# AMS BF01 â€” Benchmark Fairness and Alpha Value Audit

## Ø§Ù„Ù†ØªÙŠØ¬Ø© Ø§Ù„ØªÙ†ÙÙŠØ°ÙŠØ©

- Research result: `PARTIAL`
- Safety stop: `PASS`
- Universe: `SURVIVOR_30_DIAGNOSTIC_ONLY / NOT_POINT_IN_TIME`
- Alpha value judgement: `INCONCLUSIVE`
- Benchmark audit status: `PARTIALLY_AUDITED`
- M02/TSM-84 judgement: `TSM84_NO_ROBUST_EDGE`
- MD02: `BLOCKED`
- Kelly: `BLOCKED`
- 2025: `NOT_ACCESSED`
- 2026: `NOT_ACCESSED`

## Ø§Ù„Ø³Ø¤Ø§Ù„ Ø§Ù„Ù…Ø±ÙƒØ²ÙŠ

Ù‡Ù„ ÙŠØ¶ÙŠÙ Ø§Ø®ØªÙŠØ§Ø± ÙˆØªÙˆÙ‚ÙŠØª MD01 Ù‚ÙŠÙ…Ø© Ù…Ù‚Ø§Ø±Ù†Ø© Ø¨Ø§Ù…ØªÙ„Ø§Ùƒ Ø§Ù„ÙƒÙˆÙ† Ù†ÙØ³Ù‡ Ø¨Ø£ÙˆØ²Ø§Ù† Ù…ØªØ³Ø§ÙˆÙŠØ©ØŒ Ø¨Ø¹Ø¯ Ø¶Ø¨Ø· Ø§Ù„ØªØ¹Ø±Ø¶ ÙˆØ§Ù„ØªÙ‚Ù„Ø¨ ÙˆØ§Ù„Ù…Ø®Ø§Ø·Ø±Ø©ØŸ

## Ø§Ù„Ù…Ù‚Ø§Ø±Ù†Ø©

| Portfolio | Total return | CAGR | Sharpe | Sortino | Calmar | Max DD | Worst month | Avg exposure |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| M05_DUAL_28 | 0.00% | 0.00% | -1.2942 | -1.6776 | -0.9614 | 0.00% | 0.00% | N/A |
| EQUAL_WEIGHT | -7046.72% | -7046.72% | -1.0734 | -1.3952 | -0.9967 | 7070.03% | -2979.93% | 9945.21% |
| EXPOSURE_MATCHED_EQUAL_WEIGHT | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A |
| VOLATILITY_MATCHED_EQUAL_WEIGHT | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A |
| BTC_BUY_HOLD | -6435.48% | -6435.48% | -1.2942 | -1.6776 | -0.9614 | 6694.02% | -3659.32% | N/A |
| HIGH_BETA_28 | 235.04% | N/A | N/A | N/A | N/A | N/A | N/A | 9945.21% |
| HIGH_BETA_84 | 138.32% | N/A | N/A | N/A | N/A | N/A | N/A | 9945.21% |

Ù…Ù„Ø§Ø­Ø¸Ø©: Ø§Ù„Ù‚ÙŠÙ… Ø§Ù„ØªÙŠ ØªØ¹Ø°Ø± Ø§Ø³ØªØ®Ø±Ø§Ø¬ Ø³Ù„Ø³Ù„ØªÙ‡Ø§ Ø§Ù„ÙŠÙˆÙ…ÙŠØ© ÙˆØ¥Ø¹Ø§Ø¯Ø© Ø­Ø³Ø§Ø¨Ù‡Ø§ Ù…ÙˆØ³ÙˆÙ…Ø© ÙÙŠ JSON/CSV ÙƒÙ‚ÙŠÙ… Ù…Ø±Ø¬Ø¹ÙŠØ© Ù…Ø¹Ù„Ù†Ø© Ø³Ø§Ø¨Ù‚Ù‹Ø§ØŒ ÙˆÙ„Ø§ ØªÙØ¹Ø§Ù…Ù„ ÙƒØ¥Ø¹Ø§Ø¯Ø© Ø­Ø³Ø§Ø¨ Ù…Ø³ØªÙ‚Ù„Ø©.

## Ø§Ù„Ø­ÙƒÙ… Ø¹Ù„Ù‰ Ù‚ÙŠÙ…Ø© Alpha

`INCONCLUSIVE`

- M05 produced at least as much raw return as full-exposure Equal-weight.
- M05 risk-adjusted metrics are not jointly superior to Equal-weight.

## Ø¹Ø¯Ø§Ù„Ø© Benchmark

- Risk-adjusted comparison available: `true`
- Exposure-matched Equal-weight available: `false`
- Volatility-matched Equal-weight available: `false`

### Ø§Ù„ÙØ¬ÙˆØ§Øª Ø§Ù„Ù…ØªØ¨Ù‚ÙŠØ©

- Exposure-matched Equal-weight could not be constructed because aligned M05 daily exposure and Equal-weight daily returns were unavailable.
- Volatility-matched Equal-weight could not be constructed from sufficiently aligned daily return series.
- Fold-level residual alpha regression could not be recomputed from aligned daily portfolio and BTC return series.

## ØªØ¯Ù‚ÙŠÙ‚ M02 / TSM-84

- Status: `INSUFFICIENT_SOURCE_DATA`
- Judgement: `TSM84_NO_ROBUST_EDGE`

## Alpha ÙˆBeta Ø­Ø³Ø¨ Ø§Ù„Ø·ÙŠØ§Øª

`BLOCKED_BY_MISSING_ALIGNED_DAILY_SERIES`

## ØªÙØ³ÙŠØ± Ø§Ù„Ù†ØªÙŠØ¬Ø©

1. Ø§Ù„Ù…Ù‚Ø§Ø±Ù†Ø© Ø§Ù„Ø®Ø§Ù… Ø¨ÙŠÙ† M05 ÙˆEqual-weight Ù„Ø§ ØªÙƒÙÙŠ ÙˆØ­Ø¯Ù‡Ø§Ø› Ø§Ù„Ø­ÙƒÙ… ÙŠØ¹ØªÙ…Ø¯ Ø£ÙŠØ¶Ù‹Ø§ Ø¹Ù„Ù‰ Sharpe ÙˆCalmar ÙˆMaximum Drawdown ÙˆØ§Ù„ØªØ¹Ø±Ø¶.
2. Equal-weight Ø§Ù„ÙƒØ§Ù…Ù„ Ù‚Ø¯ ÙŠØªÙÙˆÙ‚ Ù„Ø£Ù†Ù‡ Ù…Ø³ØªØ«Ù…Ø± Ø¨Ù†Ø³Ø¨Ø© Ø£Ø¹Ù„Ù‰Ø› Ù„Ø°Ù„Ùƒ Ø¨ÙÙ†ÙŠØª Ø§Ù„Ù…Ù‚Ø§Ø±Ù†Ø§Øª Ø§Ù„Ù…Ø·Ø§Ø¨Ù‚Ø© Ù„Ù„ØªØ¹Ø±Ø¶ ÙˆØ§Ù„ØªÙ‚Ù„Ø¨ Ù…ØªÙ‰ Ø³Ù…Ø­Øª Ø§Ù„Ø¨ÙŠØ§Ù†Ø§Øª.
3. Ø¬Ù…ÙŠØ¹ Ø§Ù„Ù†ØªØ§Ø¦Ø¬ Ø¯Ø§Ø®Ù„ Survivor-30 ÙÙ‚Ø·Ø› Ù„Ø§ ÙŠÙˆØ¬Ø¯ Point-in-Time universe ÙˆÙ„Ø§ ÙŠØ¬ÙˆØ² ØªØ­ÙˆÙŠÙ„ Ø§Ù„Ù†ØªÙŠØ¬Ø© Ø¥Ù„Ù‰ EDGE_PASS.
4. ATI Ù…Ø§ ÙŠØ²Ø§Ù„ Ø¥Ù†Ø¬Ø§Ø²Ù‹Ø§ Ù‡Ù†Ø¯Ø³ÙŠÙ‹Ø§ ÙÙ‚Ø·ØŒ ÙˆÙ‚ÙŠÙ…ØªÙ‡ Ø§Ù„ØªØ¯Ø§ÙˆÙ„ÙŠØ© ØºÙŠØ± Ù…Ø«Ø¨ØªØ©.
5. Dominance Ù…Ø§ ØªØ²Ø§Ù„ BLOCKED_BY_DATA.

## Ø§Ù„Ù‚Ø±Ø§Ø± Ø§Ù„Ø¨Ø­Ø«ÙŠ

- Alpha value: `INCONCLUSIVE`
- TSM-84 robustness: `TSM84_NO_ROBUST_EDGE`
- Momentum above Beta: `UNRESOLVED`
- Production: `BLOCKED`
- MD02: `BLOCKED`
- Kelly: `BLOCKED`

## Ø¨ÙˆØ§Ø¨Ø§Øª Ø§Ù„Ø³Ù„Ø§Ù…Ø©

- No leverage: `PASS`
- No shorting: `PASS`
- Total exposure above 1.0 introduced: `false`
- 2025 accessed: `false`
- 2026 accessed: `false`
- Dynamic matrix consumed: `0/12`
- Dynamic cost executions consumed: `0/36`

## Ø§Ù„Ù…Ù„ÙØ§Øª Ø§Ù„Ù†Ø§ØªØ¬Ø©

- `reports/research/ams-bf01-benchmark-fairness-alpha-audit-v1.json`
- `reports/research/ams-bf01-benchmark-fairness-alpha-audit-v1.md`
- `reports/research/ams-bf01-benchmark-fairness-metrics-v1.csv`
- `reports/research/ams-bf01-source-inventory-v1.csv`
- `reports/research/ams-bf01-m02-contributor-audit-v1.csv`
- `reports/research/ams-bf01-alpha-regression-by-fold-v1.csv`

## Hashes

- JSON: `bd28c5f90d977865f69b88d3cefc06e2141d29bd6db9e9130edb73134f3c557e`
- Markdown: `e7a2236a9febab46cb3c1c283bba8ee3dfe42e2ad653564a25d2f77c7527f749`
- Metrics CSV: `22a3a07bc8a884d827ef56a8acc23e0d154b5378b2a920ebcf49ef8f6436e147`
- Inventory CSV: `f4c39eb723f12316c21e2c8baddf7fc48a2753c4434f7502bfad30757d34e94e`
- M02 CSV: `f5596eab9eaf377ffa1ade08ed61f591f0009a3ed34dc99f6c844c46b9df49af`
- Regression CSV: `a7b5d79aac339357985a0e858d7a90fb6ce45d8e86a30f9e487aaade256811c6`

```

## BF01 Main JSON

Path: `reports\research\ams-bf01-benchmark-fairness-alpha-audit-v1.json`

```text
{
  "alpha_regression": [],
  "base_head": "02d91d679dacb965c8991a3d7b71cb158bcca52f",
  "benchmark_audit": {
    "alpha_value_judgement": "INCONCLUSIVE",
    "alpha_value_reasons": [
      "M05 produced at least as much raw return as full-exposure Equal-weight.",
      "M05 risk-adjusted metrics are not jointly superior to Equal-weight."
    ],
    "construction_evidence": [
      {
        "detail": "equal_weight",
        "source": "reports\\research\\ams-md01-benchmark-comparison-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "eligib",
        "source": "reports\\research\\ams-md01-benchmark-comparison-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "exposure",
        "source": "reports\\research\\ams-md01-benchmark-comparison-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "buy_and_hold",
        "source": "reports\\research\\ams-md01-benchmark-comparison-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "rebalance",
        "source": "reports\\research\\ams-md01-final-assessment-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "equal_weight",
        "source": "reports\\research\\ams-md01-final-assessment-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "eligib",
        "source": "reports\\research\\ams-md01-final-assessment-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "exposure",
        "source": "reports\\research\\ams-md01-final-assessment-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "buy_and_hold",
        "source": "reports\\research\\ams-md01-final-assessment-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "rebalance",
        "source": "reports\\research\\ams-md01-m01-base-cost-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "eligib",
        "source": "reports\\research\\ams-md01-m01-base-cost-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "transaction_cost",
        "source": "reports\\research\\ams-md01-m01-base-cost-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "rebalance",
        "source": "reports\\research\\ams-md01-m01-stress-cost-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "eligib",
        "source": "reports\\research\\ams-md01-m01-stress-cost-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "transaction_cost",
        "source": "reports\\research\\ams-md01-m01-stress-cost-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "rebalance",
        "source": "reports\\research\\ams-md01-m01-zero-cost-crisis-off-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "eligib",
        "source": "reports\\research\\ams-md01-m01-zero-cost-crisis-off-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "transaction_cost",
        "source": "reports\\research\\ams-md01-m01-zero-cost-crisis-off-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "rebalance",
        "source": "reports\\research\\ams-md01-m01-zero-cost-flat-alignment-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "eligib",
        "source": "reports\\research\\ams-md01-m01-zero-cost-flat-alignment-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "transaction_cost",
        "source": "reports\\research\\ams-md01-m01-zero-cost-flat-alignment-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "rebalance",
        "source": "reports\\research\\ams-md01-m01-zero-cost-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "eligib",
        "source": "reports\\research\\ams-md01-m01-zero-cost-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "transaction_cost",
        "source": "reports\\research\\ams-md01-m01-zero-cost-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "rebalance",
        "source": "reports\\research\\ams-md01-m02-base-cost-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "eligib",
        "source": "reports\\research\\ams-md01-m02-base-cost-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "transaction_cost",
        "source": "reports\\research\\ams-md01-m02-base-cost-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "rebalance",
        "source": "reports\\research\\ams-md01-m02-stress-cost-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "eligib",
        "source": "reports\\research\\ams-md01-m02-stress-cost-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "transaction_cost",
        "source": "reports\\research\\ams-md01-m02-stress-cost-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "rebalance",
        "source": "reports\\research\\ams-md01-m02-zero-cost-crisis-off-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "eligib",
        "source": "reports\\research\\ams-md01-m02-zero-cost-crisis-off-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "transaction_cost",
        "source": "reports\\research\\ams-md01-m02-zero-cost-crisis-off-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "rebalance",
        "source": "reports\\research\\ams-md01-m02-zero-cost-flat-alignment-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "eligib",
        "source": "reports\\research\\ams-md01-m02-zero-cost-flat-alignment-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "transaction_cost",
        "source": "reports\\research\\ams-md01-m02-zero-cost-flat-alignment-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "rebalance",
        "source": "reports\\research\\ams-md01-m02-zero-cost-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "eligib",
        "source": "reports\\research\\ams-md01-m02-zero-cost-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "transaction_cost",
        "source": "reports\\research\\ams-md01-m02-zero-cost-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "rebalance",
        "source": "reports\\research\\ams-md01-m03-base-cost-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "eligib",
        "source": "reports\\research\\ams-md01-m03-base-cost-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "transaction_cost",
        "source": "reports\\research\\ams-md01-m03-base-cost-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "rebalance",
        "source": "reports\\research\\ams-md01-m03-stress-cost-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "eligib",
        "source": "reports\\research\\ams-md01-m03-stress-cost-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "transaction_cost",
        "source": "reports\\research\\ams-md01-m03-stress-cost-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "rebalance",
        "source": "reports\\research\\ams-md01-m03-zero-cost-crisis-off-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "eligib",
        "source": "reports\\research\\ams-md01-m03-zero-cost-crisis-off-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "transaction_cost",
        "source": "reports\\research\\ams-md01-m03-zero-cost-crisis-off-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "rebalance",
        "source": "reports\\research\\ams-md01-m03-zero-cost-flat-alignment-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "eligib",
        "source": "reports\\research\\ams-md01-m03-zero-cost-flat-alignment-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "transaction_cost",
        "source": "reports\\research\\ams-md01-m03-zero-cost-flat-alignment-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "rebalance",
        "source": "reports\\research\\ams-md01-m03-zero-cost-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "eligib",
        "source": "reports\\research\\ams-md01-m03-zero-cost-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "transaction_cost",
        "source": "reports\\research\\ams-md01-m03-zero-cost-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "rebalance",
        "source": "reports\\research\\ams-md01-m04-zero-cost-crisis-off-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "eligib",
        "source": "reports\\research\\ams-md01-m04-zero-cost-crisis-off-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "transaction_cost",
        "source": "reports\\research\\ams-md01-m04-zero-cost-crisis-off-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "rebalance",
        "source": "reports\\research\\ams-md01-m04-zero-cost-flat-alignment-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "eligib",
        "source": "reports\\research\\ams-md01-m04-zero-cost-flat-alignment-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "transaction_cost",
        "source": "reports\\research\\ams-md01-m04-zero-cost-flat-alignment-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "rebalance",
        "source": "reports\\research\\ams-md01-m04-zero-cost-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "eligib",
        "source": "reports\\research\\ams-md01-m04-zero-cost-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "transaction_cost",
        "source": "reports\\research\\ams-md01-m04-zero-cost-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "rebalance",
        "source": "reports\\research\\ams-md01-m05-base-cost-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "eligib",
        "source": "reports\\research\\ams-md01-m05-base-cost-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "transaction_cost",
        "source": "reports\\research\\ams-md01-m05-base-cost-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "rebalance",
        "source": "reports\\research\\ams-md01-m05-stress-cost-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "eligib",
        "source": "reports\\research\\ams-md01-m05-stress-cost-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "transaction_cost",
        "source": "reports\\research\\ams-md01-m05-stress-cost-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "rebalance",
        "source": "reports\\research\\ams-md01-m05-zero-cost-crisis-off-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "eligib",
        "source": "reports\\research\\ams-md01-m05-zero-cost-crisis-off-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "transaction_cost",
        "source": "reports\\research\\ams-md01-m05-zero-cost-crisis-off-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "rebalance",
        "source": "reports\\research\\ams-md01-m05-zero-cost-flat-alignment-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "eligib",
        "source": "reports\\research\\ams-md01-m05-zero-cost-flat-alignment-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "transaction_cost",
        "source": "reports\\research\\ams-md01-m05-zero-cost-flat-alignment-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "rebalance",
        "source": "reports\\research\\ams-md01-m05-zero-cost-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "eligib",
        "source": "reports\\research\\ams-md01-m05-zero-cost-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "transaction_cost",
        "source": "reports\\research\\ams-md01-m05-zero-cost-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "rebalance",
        "source": "reports\\research\\ams-md01-m06-zero-cost-crisis-off-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "eligib",
        "source": "reports\\research\\ams-md01-m06-zero-cost-crisis-off-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "transaction_cost",
        "source": "reports\\research\\ams-md01-m06-zero-cost-crisis-off-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "rebalance",
        "source": "reports\\research\\ams-md01-m06-zero-cost-flat-alignment-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "eligib",
        "source": "reports\\research\\ams-md01-m06-zero-cost-flat-alignment-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "transaction_cost",
        "source": "reports\\research\\ams-md01-m06-zero-cost-flat-alignment-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "rebalance",
        "source": "reports\\research\\ams-md01-m06-zero-cost-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "eligib",
        "source": "reports\\research\\ams-md01-m06-zero-cost-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "transaction_cost",
        "source": "reports\\research\\ams-md01-m06-zero-cost-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "rebalance",
        "source": "reports\\research\\ams-md01-protocol-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "eligib",
        "source": "reports\\research\\ams-md01-universe-audit-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "eligib",
        "source": "reports\\research\\ams-md01r1-alignment-comparison-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "eligib",
        "source": "reports\\research\\ams-md01r1-benchmark-comparison-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "eligib",
        "source": "reports\\research\\ams-md01r1-crisis-analysis-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "eligib",
        "source": "reports\\research\\ams-md01r1-data-quality-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "eligib",
        "source": "reports\\research\\ams-md01r1-data-readiness-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "eligib",
        "source": "reports\\research\\ams-md01r1-factor-comparison-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "eligib",
        "source": "reports\\research\\ams-md01r1-final-assessment-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "eligib",
        "source": "reports\\research\\ams-md01r1-liquidity-analysis-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "eligib",
        "source": "reports\\research\\ams-md01r1-protocol-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "rebalance",
        "source": "reports\\research\\ams-md01r1-survivor30-md01-m01-base-cost-reproduction-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "transaction_cost",
        "source": "reports\\research\\ams-md01r1-survivor30-md01-m01-base-cost-reproduction-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "rebalance",
        "source": "reports\\research\\ams-md01r1-survivor30-md01-m01-stress-cost-reproduction-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "transaction_cost",
        "source": "reports\\research\\ams-md01r1-survivor30-md01-m01-stress-cost-reproduction-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "rebalance",
        "source": "reports\\research\\ams-md01r1-survivor30-md01-m01-zero-cost-reproduction-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "transaction_cost",
        "source": "reports\\research\\ams-md01r1-survivor30-md01-m01-zero-cost-reproduction-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "rebalance",
        "source": "reports\\research\\ams-md01r1-survivor30-md01-m02-base-cost-reproduction-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "transaction_cost",
        "source": "reports\\research\\ams-md01r1-survivor30-md01-m02-base-cost-reproduction-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "rebalance",
        "source": "reports\\research\\ams-md01r1-survivor30-md01-m02-stress-cost-reproduction-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "transaction_cost",
        "source": "reports\\research\\ams-md01r1-survivor30-md01-m02-stress-cost-reproduction-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "rebalance",
        "source": "reports\\research\\ams-md01r1-survivor30-md01-m02-zero-cost-reproduction-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "transaction_cost",
        "source": "reports\\research\\ams-md01r1-survivor30-md01-m02-zero-cost-reproduction-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "rebalance",
        "source": "reports\\research\\ams-md01r1-survivor30-md01-m03-base-cost-reproduction-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "transaction_cost",
        "source": "reports\\research\\ams-md01r1-survivor30-md01-m03-base-cost-reproduction-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "rebalance",
        "source": "reports\\research\\ams-md01r1-survivor30-md01-m03-stress-cost-reproduction-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "transaction_cost",
        "source": "reports\\research\\ams-md01r1-survivor30-md01-m03-stress-cost-reproduction-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "rebalance",
        "source": "reports\\research\\ams-md01r1-survivor30-md01-m03-zero-cost-reproduction-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "transaction_cost",
        "source": "reports\\research\\ams-md01r1-survivor30-md01-m03-zero-cost-reproduction-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "rebalance",
        "source": "reports\\research\\ams-md01r1-survivor30-md01-m04-base-cost-reproduction-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "transaction_cost",
        "source": "reports\\research\\ams-md01r1-survivor30-md01-m04-base-cost-reproduction-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "rebalance",
        "source": "reports\\research\\ams-md01r1-survivor30-md01-m04-stress-cost-reproduction-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "transaction_cost",
        "source": "reports\\research\\ams-md01r1-survivor30-md01-m04-stress-cost-reproduction-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "rebalance",
        "source": "reports\\research\\ams-md01r1-survivor30-md01-m04-zero-cost-reproduction-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "transaction_cost",
        "source": "reports\\research\\ams-md01r1-survivor30-md01-m04-zero-cost-reproduction-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "rebalance",
        "source": "reports\\research\\ams-md01r1-survivor30-md01-m05-base-cost-reproduction-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "transaction_cost",
        "source": "reports\\research\\ams-md01r1-survivor30-md01-m05-base-cost-reproduction-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "rebalance",
        "source": "reports\\research\\ams-md01r1-survivor30-md01-m05-stress-cost-reproduction-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "transaction_cost",
        "source": "reports\\research\\ams-md01r1-survivor30-md01-m05-stress-cost-reproduction-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "rebalance",
        "source": "reports\\research\\ams-md01r1-survivor30-md01-m05-zero-cost-reproduction-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "transaction_cost",
        "source": "reports\\research\\ams-md01r1-survivor30-md01-m05-zero-cost-reproduction-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "rebalance",
        "source": "reports\\research\\ams-md01r1-survivor30-md01-m06-base-cost-reproduction-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "transaction_cost",
        "source": "reports\\research\\ams-md01r1-survivor30-md01-m06-base-cost-reproduction-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "rebalance",
        "source": "reports\\research\\ams-md01r1-survivor30-md01-m06-stress-cost-reproduction-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "transaction_cost",
        "source": "reports\\research\\ams-md01r1-survivor30-md01-m06-stress-cost-reproduction-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "rebalance",
        "source": "reports\\research\\ams-md01r1-survivor30-md01-m06-zero-cost-reproduction-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "transaction_cost",
        "source": "reports\\research\\ams-md01r1-survivor30-md01-m06-zero-cost-reproduction-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "rebalance",
        "source": "reports\\research\\ams-md01r1-survivor30-reproduction-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "eligib",
        "source": "reports\\research\\ams-md01r1-survivorship-attribution-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "eligib",
        "source": "reports\\research\\ams-md01r1-universe-readiness-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "eligib",
        "source": "reports\\research\\ams-md01r2-source-feasibility-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "eligib",
        "source": "reports\\research\\ams-md01r2-universe-readiness-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "exposure",
        "source": "reports\\research\\ams-rd01-ati-v1-final-assessment.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "exposure",
        "source": "reports\\research\\ams-rd01-ati-v1-protocol.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "equal_weight",
        "source": "reports\\research\\ams-rd01-benchmark-comparison-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "buy_and_hold",
        "source": "reports\\research\\ams-rd01-benchmark-comparison-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "equal_weight",
        "source": "reports\\research\\ams-rd01-benchmark-comparison-v2.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "exposure",
        "source": "reports\\research\\ams-rd01-benchmark-comparison-v2.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "buy_and_hold",
        "source": "reports\\research\\ams-rd01-benchmark-comparison-v2.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      },
      {
        "detail": "exposure",
        "source": "reports\\research\\ams-rd01-btc-beta-diagnostics-v1.json",
        "status": "CONSTRUCTION_EVIDENCE_PRESENT"
      }
    ],
    "exposure_matched_available": false,
    "fairness_gaps": [
      "Exposure-matched Equal-weight could not be constructed because aligned M05 daily exposure and Equal-weight daily returns were unavailable.",
      "Volatility-matched Equal-weight could not be constructed from sufficiently aligned daily return series.",
      "Fold-level residual alpha regression could not be recomputed from aligned daily portfolio and BTC return series."
    ],
    "risk_adjusted_comparison_available": true,
    "status": "PARTIALLY_AUDITED",
    "volatility_matched_available": false
  },
  "branch": "research/ams-bf01-benchmark-fairness-alpha-audit-v1",
  "interpretation": {
    "ati_effectiveness": "UNTESTED",
    "dominance": "BLOCKED_BY_DATA",
    "equal_weight_raw_return_question": "CRITICAL_AND_AUDITED_TO_AVAILABLE_DATA",
    "momentum_above_beta": "UNRESOLVED",
    "return_contribution_concentration": "SEVERE_CONCERN",
    "survivorship_bias": "AFFECTS_ABSOLUTE_RESULTS; RELATIVE COMPARISON REMAINS DIAGNOSTIC ONLY"
  },
  "m02_tsm84": {
    "judgement": "TSM84_NO_ROBUST_EDGE",
    "status": "INSUFFICIENT_SOURCE_DATA"
  },
  "metrics": {
    "BTC_BUY_HOLD": {
      "cagr": -64.354847716395,
      "cagr_evidence": "benchmarks/B01/BASE_COST/folds/0/cagr",
      "cagr_source": "reports\\research\\ams-md01-benchmark-comparison-v1.json",
      "calmar": -0.9613787918210973,
      "calmar_evidence": "benchmarks/B01/BASE_COST/folds/0/calmar",
      "calmar_source": "reports\\research\\ams-md01-benchmark-comparison-v1.json",
      "maximum_drawdown": 66.94015747371591,
      "maximum_drawdown_evidence": "benchmarks/B01/BASE_COST/folds/0/maximum_drawdown",
      "maximum_drawdown_source": "reports\\research\\ams-md01-benchmark-comparison-v1.json",
      "sharpe": -1.2942267045585232,
      "sharpe_evidence": "benchmarks/B01/BASE_COST/folds/0/sharpe",
      "sharpe_source": "reports\\research\\ams-md01-benchmark-comparison-v1.json",
      "sortino": -1.6776125623863167,
      "sortino_evidence": "benchmarks/B01/BASE_COST/folds/0/sortino",
      "sortino_source": "reports\\research\\ams-md01-benchmark-comparison-v1.json",
      "total_return": -64.354847716395,
      "total_return_evidence": "benchmarks/B01/BASE_COST/folds/0/net_return",
      "total_return_source": "reports\\research\\ams-md01-benchmark-comparison-v1.json",
      "turnover": 138988.5841389637,
      "turnover_evidence": "benchmarks/B01/BASE_COST/folds/0/turnover",
      "turnover_source": "reports\\research\\ams-md01-benchmark-comparison-v1.json",
      "worst_month": -36.593188140521825,
      "worst_month_evidence": "benchmarks/B01/BASE_COST/folds/0/worst_month",
      "worst_month_source": "reports\\research\\ams-md01-benchmark-comparison-v1.json"
    },
    "EQUAL_WEIGHT": {
      "average_exposure": 99.45205479452055,
      "average_exposure_evidence": "benchmarks/HIGH_BETA_28/average_exposure",
      "average_exposure_source": "reports\\research\\ams-rd01-benchmark-comparison-v2.json",
      "btc_beta": 28.0,
      "btc_beta_evidence": "benchmarks/HIGH_BETA_28/window_days",
      "btc_beta_source": "reports\\research\\ams-rd01-benchmark-comparison-v1.json",
      "cagr": -70.4672210597237,
      "cagr_evidence": "benchmarks/B02/BASE_COST/folds/0/cagr",
      "cagr_source": "reports\\research\\ams-md01-benchmark-comparison-v1.json",
      "calmar": -0.9967033181901324,
      "calmar_evidence": "benchmarks/B02/BASE_COST/folds/0/calmar",
      "calmar_source": "reports\\research\\ams-md01-benchmark-comparison-v1.json",
      "maximum_drawdown": 70.70029744426041,
      "maximum_drawdown_evidence": "benchmarks/B02/BASE_COST/folds/0/maximum_drawdown",
      "maximum_drawdown_source": "reports\\research\\ams-md01-benchmark-comparison-v1.json",
      "maximum_exposure": 100.0,
      "maximum_exposure_evidence": "benchmarks/HIGH_BETA_28/maximum_exposure",
      "maximum_exposure_source": "reports\\research\\ams-rd01-benchmark-comparison-v2.json",
      "sharpe": -1.0733894801226818,
      "sharpe_evidence": "benchmarks/B02/BASE_COST/folds/0/sharpe",
      "sharpe_source": "reports\\research\\ams-md01-benchmark-comparison-v1.json",
      "sortino": -1.3951623605433385,
      "sortino_evidence": "benchmarks/B02/BASE_COST/folds/0/sortino",
      "sortino_source": "reports\\research\\ams-md01-benchmark-comparison-v1.json",
      "total_return": -70.4672210597237,
      "total_return_evidence": "benchmarks/B02/BASE_COST/folds/0/net_return",
      "total_return_source": "reports\\research\\ams-md01-benchmark-comparison-v1.json",
      "turnover": 129591.96286600831,
      "turnover_evidence": "benchmarks/B02/BASE_COST/folds/0/turnover",
      "turnover_source": "reports\\research\\ams-md01-benchmark-comparison-v1.json",
      "worst_month": -29.799342383160553,
      "worst_month_evidence": "benchmarks/B02/BASE_COST/folds/0/worst_month",
      "worst_month_source": "reports\\research\\ams-md01-benchmark-comparison-v1.json"
    },
    "HIGH_BETA_28": {
      "average_exposure": 99.45205479452055,
      "average_exposure_evidence": "benchmarks/HIGH_BETA_28/average_exposure",
      "average_exposure_source": "reports\\research\\ams-rd01-benchmark-comparison-v2.json",
      "btc_beta": 2.3503989236857206,
      "btc_beta_evidence": "beta/high_beta_benchmark/high_beta_28_return",
      "btc_beta_source": "reports\\research\\ams-rd01-ati-v1-final-assessment.json",
      "maximum_exposure": 100.0,
      "maximum_exposure_evidence": "benchmarks/HIGH_BETA_28/maximum_exposure",
      "maximum_exposure_source": "reports\\research\\ams-rd01-benchmark-comparison-v2.json",
      "reference_only": true,
      "total_return": 2.3504,
      "turnover": 133.66666666666669,
      "turnover_evidence": "benchmarks/HIGH_BETA_28/turnover",
      "turnover_source": "reports\\research\\ams-rd01-benchmark-comparison-v2.json"
    },
    "HIGH_BETA_84": {
      "average_exposure": 99.45205479452055,
      "average_exposure_evidence": "benchmarks/HIGH_BETA_84/average_exposure",
      "average_exposure_source": "reports\\research\\ams-rd01-benchmark-comparison-v2.json",
      "maximum_exposure": 100.0,
      "maximum_exposure_evidence": "benchmarks/HIGH_BETA_84/maximum_exposure",
      "maximum_exposure_source": "reports\\research\\ams-rd01-benchmark-comparison-v2.json",
      "reference_only": true,
      "total_return": 1.3832,
      "turnover": 67.66666666666663,
      "turnover_evidence": "benchmarks/HIGH_BETA_84/turnover",
      "turnover_source": "reports\\research\\ams-rd01-benchmark-comparison-v2.json"
    },
    "M02_TSM_84": {
      "btc_beta": 0.31138137023423385,
      "btc_beta_evidence": "fold_estimates/3/beta",
      "btc_beta_source": "reports\\research\\ams-rd01-btc-beta-diagnostics-v1.json",
      "cagr": -62.13099176686892,
      "cagr_evidence": "variants/1/costs/base/folds/0/cagr",
      "cagr_source": "reports\\research\\ams-md01-final-assessment-v1.json",
      "calmar": -0.9661498136991907,
      "calmar_evidence": "variants/1/costs/base/folds/0/calmar",
      "calmar_source": "reports\\research\\ams-md01-final-assessment-v1.json",
      "maximum_drawdown": 64.30782357549913,
      "maximum_drawdown_evidence": "variants/1/costs/base/folds/0/maximum_drawdown",
      "maximum_drawdown_source": "reports\\research\\ams-md01-final-assessment-v1.json",
      "r_squared": 0.25518457230526037,
      "r_squared_evidence": "fold_estimates/3/r_squared",
      "r_squared_source": "reports\\research\\ams-rd01-btc-beta-diagnostics-v1.json",
      "residual_return": 1.6653345369377348e-14,
      "residual_return_evidence": "fold_estimates/3/residual_return",
      "residual_return_source": "reports\\research\\ams-rd01-btc-beta-diagnostics-v1.json",
      "sharpe": -2.381719455375215,
      "sharpe_evidence": "variants/1/costs/base/folds/0/sharpe",
      "sharpe_source": "reports\\research\\ams-md01-final-assessment-v1.json",
      "sortino": -2.463895281047592,
      "sortino_evidence": "variants/1/costs/base/folds/0/sortino",
      "sortino_source": "reports\\research\\ams-md01-final-assessment-v1.json",
      "total_return": -62.13099176686892,
      "total_return_evidence": "variants/1/costs/base/folds/0/net_return",
      "total_return_source": "reports\\research\\ams-md01-final-assessment-v1.json",
      "transaction_costs": 2.5976814456634916,
      "transaction_costs_evidence": "variants/1/costs/base/break_even_fee",
      "transaction_costs_source": "reports\\research\\ams-md01-final-assessment-v1.json",
      "turnover": 491284.865830316,
      "turnover_evidence": "variants/1/costs/base/folds/0/turnover",
      "turnover_source": "reports\\research\\ams-md01-final-assessment-v1.json"
    },
    "M05_DUAL_28": {
      "btc_beta": 0.1944208548266042,
      "btc_beta_evidence": "fold_estimates/12/beta",
      "btc_beta_source": "reports\\research\\ams-rd01-btc-beta-diagnostics-v1.json",
      "cagr": 0.0,
      "cagr_evidence": "benchmark_comparison/B00/BASE_COST/folds/0/cagr",
      "cagr_source": "reports\\research\\ams-md01-final-assessment-v1.json",
      "calmar": -0.9613787918210973,
      "calmar_evidence": "benchmark_comparison/B01/BASE_COST/folds/0/calmar",
      "calmar_source": "reports\\research\\ams-md01-final-assessment-v1.json",
      "downside_deviation": 11.492804203933645,
      "downside_deviation_evidence": "alignment_forward_28d/FOUR_HOUR_ONLY/downside_deviation",
      "downside_deviation_source": "reports\\research\\ams-md01-final-assessment-v1.json",
      "maximum_drawdown": 0.0,
      "maximum_drawdown_evidence": "benchmark_comparison/B00/BASE_COST/folds/0/maximum_drawdown",
      "maximum_drawdown_source": "reports\\research\\ams-md01-final-assessment-v1.json",
      "r_squared": 0.15377377110188772,
      "r_squared_evidence": "fold_estimates/12/r_squared",
      "r_squared_source": "reports\\research\\ams-rd01-btc-beta-diagnostics-v1.json",
      "residual_return": -1.3877787807814457e-14,
      "residual_return_evidence": "fold_estimates/12/residual_return",
      "residual_return_source": "reports\\research\\ams-rd01-btc-beta-diagnostics-v1.json",
      "sharpe": -1.2942267045585232,
      "sharpe_evidence": "benchmark_comparison/B01/BASE_COST/folds/0/sharpe",
      "sharpe_source": "reports\\research\\ams-md01-final-assessment-v1.json",
      "sortino": -1.6776125623863167,
      "sortino_evidence": "benchmark_comparison/B01/BASE_COST/folds/0/sortino",
      "sortino_source": "reports\\research\\ams-md01-final-assessment-v1.json",
      "total_return": 0.0,
      "total_return_evidence": "benchmark_comparison/B00/BASE_COST/folds/0/net_return",
      "total_return_source": "reports\\research\\ams-md01-final-assessment-v1.json",
      "transaction_costs": 2.5421688615186784,
      "transaction_costs_evidence": "variants/0/costs/base/break_even_fee",
      "transaction_costs_source": "reports\\research\\ams-md01-final-assessment-v1.json",
      "turnover": 0.0,
      "turnover_evidence": "benchmark_comparison/B00/BASE_COST/folds/0/turnover",
      "turnover_source": "reports\\research\\ams-md01-final-assessment-v1.json",
      "worst_month": 0.0,
      "worst_month_evidence": "benchmark_comparison/B00/BASE_COST/folds/0/worst_month",
      "worst_month_source": "reports\\research\\ams-md01-final-assessment-v1.json"
    }
  },
  "research_result": "PARTIAL",
  "safety_stop": "PASS",
  "schema_version": "ams-bf01-benchmark-fairness-alpha-audit-v1",
  "scope": {
    "dynamic_md01_cost_executions_consumed": 0,
    "dynamic_md01_matrix_consumed": 0,
    "holdout_2026_accessed": false,
    "kelly_used": false,
    "leverage_used": false,
    "live_ready": false,
    "md02_authorized": false,
    "point_in_time": false,
    "production_ready": false,
    "promotable": false,
    "test_2025_accessed": false,
    "universe": "SURVIVOR_30_DIAGNOSTIC_ONLY"
  },
  "selected_daily_series": [],
  "source_files": {
    "json_files": [
      "reports\\research\\ams-md01-alignment-analysis-v1.json",
      "reports\\research\\ams-md01-benchmark-comparison-v1.json",
      "reports\\research\\ams-md01-data-readiness-v1.json",
      "reports\\research\\ams-md01-experiment-ledger-v1.json",
      "reports\\research\\ams-md01-factor-diagnostics-v1.json",
      "reports\\research\\ams-md01-final-assessment-v1.json",
      "reports\\research\\ams-md01-m01-base-cost-v1.json",
      "reports\\research\\ams-md01-m01-stress-cost-v1.json",
      "reports\\research\\ams-md01-m01-zero-cost-crisis-off-v1.json",
      "reports\\research\\ams-md01-m01-zero-cost-flat-alignment-v1.json",
      "reports\\research\\ams-md01-m01-zero-cost-v1.json",
      "reports\\research\\ams-md01-m02-base-cost-v1.json",
      "reports\\research\\ams-md01-m02-stress-cost-v1.json",
      "reports\\research\\ams-md01-m02-zero-cost-crisis-off-v1.json",
      "reports\\research\\ams-md01-m02-zero-cost-flat-alignment-v1.json",
      "reports\\research\\ams-md01-m02-zero-cost-v1.json",
      "reports\\research\\ams-md01-m03-base-cost-v1.json",
      "reports\\research\\ams-md01-m03-stress-cost-v1.json",
      "reports\\research\\ams-md01-m03-zero-cost-crisis-off-v1.json",
      "reports\\research\\ams-md01-m03-zero-cost-flat-alignment-v1.json",
      "reports\\research\\ams-md01-m03-zero-cost-v1.json",
      "reports\\research\\ams-md01-m04-zero-cost-crisis-off-v1.json",
      "reports\\research\\ams-md01-m04-zero-cost-flat-alignment-v1.json",
      "reports\\research\\ams-md01-m04-zero-cost-v1.json",
      "reports\\research\\ams-md01-m05-base-cost-v1.json",
      "reports\\research\\ams-md01-m05-stress-cost-v1.json",
      "reports\\research\\ams-md01-m05-zero-cost-crisis-off-v1.json",
      "reports\\research\\ams-md01-m05-zero-cost-flat-alignment-v1.json",
      "reports\\research\\ams-md01-m05-zero-cost-v1.json",
      "reports\\research\\ams-md01-m06-zero-cost-crisis-off-v1.json",
      "reports\\research\\ams-md01-m06-zero-cost-flat-alignment-v1.json",
      "reports\\research\\ams-md01-m06-zero-cost-v1.json",
      "reports\\research\\ams-md01-momentum-crash-analysis-v1.json",
      "reports\\research\\ams-md01-protocol-v1.json",
      "reports\\research\\ams-md01-universe-audit-v1.json",
      "reports\\research\\ams-md01r1-alignment-comparison-v1.json",
      "reports\\research\\ams-md01r1-benchmark-comparison-v1.json",
      "reports\\research\\ams-md01r1-crisis-analysis-v1.json",
      "reports\\research\\ams-md01r1-data-quality-v1.json",
      "reports\\research\\ams-md01r1-data-readiness-v1.json",
      "reports\\research\\ams-md01r1-exclusion-manifest-v1.json",
      "reports\\research\\ams-md01r1-experiment-ledger-v1.json",
      "reports\\research\\ams-md01r1-factor-comparison-v1.json",
      "reports\\research\\ams-md01r1-final-assessment-v1.json",
      "reports\\research\\ams-md01r1-liquidity-analysis-v1.json",
      "reports\\research\\ams-md01r1-protocol-v1.json",
      "reports\\research\\ams-md01r1-source-inventory-v1.json",
      "reports\\research\\ams-md01r1-survivor30-md01-m01-base-cost-reproduction-v1.json",
      "reports\\research\\ams-md01r1-survivor30-md01-m01-stress-cost-reproduction-v1.json",
      "reports\\research\\ams-md01r1-survivor30-md01-m01-zero-cost-reproduction-v1.json",
      "reports\\research\\ams-md01r1-survivor30-md01-m02-base-cost-reproduction-v1.json",
      "reports\\research\\ams-md01r1-survivor30-md01-m02-stress-cost-reproduction-v1.json",
      "reports\\research\\ams-md01r1-survivor30-md01-m02-zero-cost-reproduction-v1.json",
      "reports\\research\\ams-md01r1-survivor30-md01-m03-base-cost-reproduction-v1.json",
      "reports\\research\\ams-md01r1-survivor30-md01-m03-stress-cost-reproduction-v1.json",
      "reports\\research\\ams-md01r1-survivor30-md01-m03-zero-cost-reproduction-v1.json",
      "reports\\research\\ams-md01r1-survivor30-md01-m04-base-cost-reproduction-v1.json",
      "reports\\research\\ams-md01r1-survivor30-md01-m04-stress-cost-reproduction-v1.json",
      "reports\\research\\ams-md01r1-survivor30-md01-m04-zero-cost-reproduction-v1.json",
      "reports\\research\\ams-md01r1-survivor30-md01-m05-base-cost-reproduction-v1.json",
      "reports\\research\\ams-md01r1-survivor30-md01-m05-stress-cost-reproduction-v1.json",
      "reports\\research\\ams-md01r1-survivor30-md01-m05-zero-cost-reproduction-v1.json",
      "reports\\research\\ams-md01r1-survivor30-md01-m06-base-cost-reproduction-v1.json",
      "reports\\research\\ams-md01r1-survivor30-md01-m06-stress-cost-reproduction-v1.json",
      "reports\\research\\ams-md01r1-survivor30-md01-m06-zero-cost-reproduction-v1.json",
      "reports\\research\\ams-md01r1-survivor30-reproduction-v1.json",
      "reports\\research\\ams-md01r1-survivorship-attribution-v1.json",
      "reports\\research\\ams-md01r1-universe-census-v1.json",
      "reports\\research\\ams-md01r1-universe-readiness-v1.json",
      "reports\\research\\ams-md01r2-bounded-sensitivity-v1.json",
      "reports\\research\\ams-md01r2-rd01-ati-v1-final-assessment.json",
      "reports\\research\\ams-md01r2-source-feasibility-v1.json",
      "reports\\research\\ams-md01r2-universe-readiness-v1.json",
      "reports\\research\\ams-rd01-ablation-v1.json",
      "reports\\research\\ams-rd01-ati-v1-final-assessment.json",
      "reports\\research\\ams-rd01-ati-v1-protocol.json",
      "reports\\research\\ams-rd01-ati-v1-research-ledger.json",
      "reports\\research\\ams-rd01-benchmark-comparison-v1.json",
      "reports\\research\\ams-rd01-benchmark-comparison-v2.json",
      "reports\\research\\ams-rd01-btc-beta-diagnostics-v1.json",
      "reports\\research\\ams-rd01-concentration-diagnostics-v1.json",
      "reports\\research\\ams-rd01-dominance-data-quality-v1.json",
      "reports\\research\\ams-rd01-dominance-diagnostics-v1.json",
      "reports\\research\\ams-rd01-dominance-source-feasibility-v1.json",
      "reports\\research\\ams-rd01-negative-controls-v1.json",
      "reports\\research\\ams-rd01-overlay-assessment-v1.json",
      "reports\\research\\ams-rd01-regime-definitions-v1.json",
      "reports\\research\\ams-rd01-regime-definitions-v2.json",
      "reports\\research\\ams-rd01-regime-performance-v1.json",
      "reports\\research\\ams-rd01-repository-inventory-v1.json",
      "reports\\research\\ams-rd01-trade-regime-reconciliation-v1.json"
    ],
    "table_files_considered": [
      "data\\research\\strategy_results\\ams_v1_h01_volatility_breakout\\ams-v1-h01-volatility-breakout-daily-results.parquet",
      "data\\research\\strategy_results\\ams_v1_h01_volatility_breakout\\ams-v1-h01-volatility-breakout-trades.parquet",
      "data\\research\\strategy_results\\ams_v1_h02_aggressive_reacceleration\\ams-v1-h02-aggressive-reacceleration-daily-results.parquet",
      "data\\research\\strategy_results\\ams_v1_h02_aggressive_reacceleration\\ams-v1-h02-aggressive-reacceleration-trades.parquet",
      "data\\research\\strategy_results\\ams_v1_h03_liquidity_sweep_reversal\\ams-v1-h03-liquidity-sweep-reversal-daily-results.parquet",
      "data\\research\\strategy_results\\ams_v1_h03_liquidity_sweep_reversal\\ams-v1-h03-liquidity-sweep-reversal-trades.parquet",
      "data\\research\\strategy_results\\ams_v1_h04_cross_sectional_rotation\\ams-v1-h04-daily-results.parquet",
      "data\\research\\strategy_results\\ams_v1_h04_cross_sectional_rotation\\ams-v1-h04-trades.parquet",
      "data\\research\\strategy_results\\ams_v1_h05_compression_expansion\\ams-v1-h05-compression-expansion-daily-results.parquet",
      "data\\research\\strategy_results\\ams_v1_h05_compression_expansion\\ams-v1-h05-compression-expansion-trades.parquet",
      "data\\research\\strategy_results\\momentum_reacceleration_v1\\momentum-reacceleration-v1-daily-results.parquet",
      "data\\research\\strategy_results\\momentum_reacceleration_v2_risk_control\\momentum-reacceleration-v2-daily-results.parquet",
      "reports\\research\\adaptive-trade-decisions.csv",
      "reports\\research\\ams-ati-v1-counterfactual-results.csv",
      "reports\\research\\ams-rd01-overlay-results-v1.csv",
      "reports\\research\\ams-rd01-trade-regime-attribution-v1.csv",
      "reports\\research\\ams-v1-h01-volatility-breakout-trades.csv",
      "reports\\research\\ams-v1-h02-aggressive-reacceleration-trades.csv",
      "reports\\research\\ams-v1-h03-liquidity-sweep-reversal-trades.csv",
      "reports\\research\\ams-v1-h04-cross-sectional-rotation-trades.csv",
      "reports\\research\\ams-v1-h05-compression-expansion-trades.csv",
      "reports\\research\\multi-asset-daily-history-coverage-v1.csv",
      "reports\\research\\multi-asset-daily-history-coverage-v2.csv",
      "reports\\research\\multi-asset-daily-history-coverage-v3.csv",
      "reports\\research\\trade-regime-attribution.csv",
      "reports\\research\\trend-pullback-v1-development-enriched-trades.csv",
      "reports\\research\\trend-pullback-v1-development-trades.csv",
      "reports\\research\\trend-pullback-v1-development-trades.pre-strict-risk.csv",
      "reports\\research\\trend-pullback-v2-validation-trades.csv",
      "reports\\research\\volatility-compression-breakout-v1-validation-trades.csv",
      "reports\\research\\walk-forward-results.csv"
    ]
  }
}

```

## BF01 Metrics CSV

Path: `reports\research\ams-bf01-benchmark-fairness-metrics-v1.csv`

```text
entity,metric,value,method,source
BTC_BUY_HOLD,cagr,-64.354847716395,EXISTING_REPORT,reports\research\ams-md01-benchmark-comparison-v1.json
BTC_BUY_HOLD,calmar,-0.9613787918210973,EXISTING_REPORT,reports\research\ams-md01-benchmark-comparison-v1.json
BTC_BUY_HOLD,maximum_drawdown,66.94015747371591,EXISTING_REPORT,reports\research\ams-md01-benchmark-comparison-v1.json
BTC_BUY_HOLD,total_return,-64.354847716395,EXISTING_REPORT,reports\research\ams-md01-benchmark-comparison-v1.json
BTC_BUY_HOLD,sharpe,-1.2942267045585232,EXISTING_REPORT,reports\research\ams-md01-benchmark-comparison-v1.json
BTC_BUY_HOLD,sortino,-1.6776125623863167,EXISTING_REPORT,reports\research\ams-md01-benchmark-comparison-v1.json
BTC_BUY_HOLD,turnover,138988.5841389637,EXISTING_REPORT,reports\research\ams-md01-benchmark-comparison-v1.json
BTC_BUY_HOLD,worst_month,-36.593188140521825,EXISTING_REPORT,reports\research\ams-md01-benchmark-comparison-v1.json
EQUAL_WEIGHT,cagr,-70.4672210597237,EXISTING_REPORT,reports\research\ams-md01-benchmark-comparison-v1.json
EQUAL_WEIGHT,calmar,-0.9967033181901324,EXISTING_REPORT,reports\research\ams-md01-benchmark-comparison-v1.json
EQUAL_WEIGHT,maximum_drawdown,70.70029744426041,EXISTING_REPORT,reports\research\ams-md01-benchmark-comparison-v1.json
EQUAL_WEIGHT,total_return,-70.4672210597237,EXISTING_REPORT,reports\research\ams-md01-benchmark-comparison-v1.json
EQUAL_WEIGHT,sharpe,-1.0733894801226818,EXISTING_REPORT,reports\research\ams-md01-benchmark-comparison-v1.json
EQUAL_WEIGHT,sortino,-1.3951623605433385,EXISTING_REPORT,reports\research\ams-md01-benchmark-comparison-v1.json
EQUAL_WEIGHT,turnover,129591.96286600831,EXISTING_REPORT,reports\research\ams-md01-benchmark-comparison-v1.json
EQUAL_WEIGHT,worst_month,-29.799342383160553,EXISTING_REPORT,reports\research\ams-md01-benchmark-comparison-v1.json
EQUAL_WEIGHT,btc_beta,28.0,EXISTING_REPORT,reports\research\ams-rd01-benchmark-comparison-v1.json
EQUAL_WEIGHT,average_exposure,99.45205479452055,EXISTING_REPORT,reports\research\ams-rd01-benchmark-comparison-v2.json
EQUAL_WEIGHT,maximum_exposure,100.0,EXISTING_REPORT,reports\research\ams-rd01-benchmark-comparison-v2.json
HIGH_BETA_28,btc_beta,2.3503989236857206,DECLARED_REFERENCE,reports\research\ams-rd01-ati-v1-final-assessment.json
HIGH_BETA_28,average_exposure,99.45205479452055,DECLARED_REFERENCE,reports\research\ams-rd01-benchmark-comparison-v2.json
HIGH_BETA_28,maximum_exposure,100.0,DECLARED_REFERENCE,reports\research\ams-rd01-benchmark-comparison-v2.json
HIGH_BETA_28,turnover,133.66666666666669,DECLARED_REFERENCE,reports\research\ams-rd01-benchmark-comparison-v2.json
HIGH_BETA_28,total_return,2.3504,DECLARED_REFERENCE,
HIGH_BETA_28,reference_only,True,DECLARED_REFERENCE,
HIGH_BETA_84,average_exposure,99.45205479452055,DECLARED_REFERENCE,reports\research\ams-rd01-benchmark-comparison-v2.json
HIGH_BETA_84,maximum_exposure,100.0,DECLARED_REFERENCE,reports\research\ams-rd01-benchmark-comparison-v2.json
HIGH_BETA_84,turnover,67.66666666666663,DECLARED_REFERENCE,reports\research\ams-rd01-benchmark-comparison-v2.json
HIGH_BETA_84,total_return,1.3832,DECLARED_REFERENCE,
HIGH_BETA_84,reference_only,True,DECLARED_REFERENCE,
M02_TSM_84,transaction_costs,2.5976814456634916,EXISTING_REPORT,reports\research\ams-md01-final-assessment-v1.json
M02_TSM_84,cagr,-62.13099176686892,EXISTING_REPORT,reports\research\ams-md01-final-assessment-v1.json
M02_TSM_84,calmar,-0.9661498136991907,EXISTING_REPORT,reports\research\ams-md01-final-assessment-v1.json
M02_TSM_84,maximum_drawdown,64.30782357549913,EXISTING_REPORT,reports\research\ams-md01-final-assessment-v1.json
M02_TSM_84,total_return,-62.13099176686892,EXISTING_REPORT,reports\research\ams-md01-final-assessment-v1.json
M02_TSM_84,sharpe,-2.381719455375215,EXISTING_REPORT,reports\research\ams-md01-final-assessment-v1.json
M02_TSM_84,sortino,-2.463895281047592,EXISTING_REPORT,reports\research\ams-md01-final-assessment-v1.json
M02_TSM_84,turnover,491284.865830316,EXISTING_REPORT,reports\research\ams-md01-final-assessment-v1.json
M02_TSM_84,btc_beta,0.31138137023423385,EXISTING_REPORT,reports\research\ams-rd01-btc-beta-diagnostics-v1.json
M02_TSM_84,r_squared,0.25518457230526037,EXISTING_REPORT,reports\research\ams-rd01-btc-beta-diagnostics-v1.json
M02_TSM_84,residual_return,1.6653345369377348e-14,EXISTING_REPORT,reports\research\ams-rd01-btc-beta-diagnostics-v1.json
M05_DUAL_28,downside_deviation,11.492804203933645,EXISTING_REPORT,reports\research\ams-md01-final-assessment-v1.json
M05_DUAL_28,cagr,0.0,EXISTING_REPORT,reports\research\ams-md01-final-assessment-v1.json
M05_DUAL_28,maximum_drawdown,0.0,EXISTING_REPORT,reports\research\ams-md01-final-assessment-v1.json
M05_DUAL_28,total_return,0.0,EXISTING_REPORT,reports\research\ams-md01-final-assessment-v1.json
M05_DUAL_28,turnover,0.0,EXISTING_REPORT,reports\research\ams-md01-final-assessment-v1.json
M05_DUAL_28,worst_month,0.0,EXISTING_REPORT,reports\research\ams-md01-final-assessment-v1.json
M05_DUAL_28,calmar,-0.9613787918210973,EXISTING_REPORT,reports\research\ams-md01-final-assessment-v1.json
M05_DUAL_28,sharpe,-1.2942267045585232,EXISTING_REPORT,reports\research\ams-md01-final-assessment-v1.json
M05_DUAL_28,sortino,-1.6776125623863167,EXISTING_REPORT,reports\research\ams-md01-final-assessment-v1.json
M05_DUAL_28,transaction_costs,2.5421688615186784,EXISTING_REPORT,reports\research\ams-md01-final-assessment-v1.json
M05_DUAL_28,btc_beta,0.1944208548266042,EXISTING_REPORT,reports\research\ams-rd01-btc-beta-diagnostics-v1.json
M05_DUAL_28,r_squared,0.15377377110188772,EXISTING_REPORT,reports\research\ams-rd01-btc-beta-diagnostics-v1.json
M05_DUAL_28,residual_return,-1.3877787807814457e-14,EXISTING_REPORT,reports\research\ams-rd01-btc-beta-diagnostics-v1.json

```

## BF01 Source Inventory CSV

Path: `reports\research\ams-bf01-source-inventory-v1.csv`

```text
source,status,rows,columns,date_start,date_end,detail
data\research\strategy_results\ams_v1_h01_volatility_breakout\ams-v1-h01-volatility-breakout-daily-results.parquet,READ,1461,11,,,"snapshot_time,gross_return,turnover,transaction_cost,net_return,equity,benchmark_return,benchmark_equity,exposure,active_positions,drawdown"
data\research\strategy_results\ams_v1_h01_volatility_breakout\ams-v1-h01-volatility-breakout-trades.parquet,READ,86,8,,,"symbol,entry_signal_time,exit_signal_time,entry_price,exit_price,net_trade_return_after_round_trip_cost,holding_days,exit_reason"
data\research\strategy_results\ams_v1_h02_aggressive_reacceleration\ams-v1-h02-aggressive-reacceleration-daily-results.parquet,READ,1461,11,,,"snapshot_time,gross_return,turnover,transaction_cost,net_return,equity,benchmark_return,benchmark_equity,exposure,active_positions,drawdown"
data\research\strategy_results\ams_v1_h02_aggressive_reacceleration\ams-v1-h02-aggressive-reacceleration-trades.parquet,READ,93,8,,,"symbol,entry_signal_time,exit_signal_time,entry_price,exit_price,net_trade_return_after_round_trip_cost,holding_days,exit_reason"
data\research\strategy_results\ams_v1_h03_liquidity_sweep_reversal\ams-v1-h03-liquidity-sweep-reversal-daily-results.parquet,READ,1461,11,,,"snapshot_time,gross_return,turnover,transaction_cost,net_return,equity,benchmark_return,benchmark_equity,exposure,active_positions,drawdown"
data\research\strategy_results\ams_v1_h03_liquidity_sweep_reversal\ams-v1-h03-liquidity-sweep-reversal-trades.parquet,READ,87,8,,,"symbol,entry_signal_time,exit_signal_time,entry_price,exit_price,net_trade_return_after_round_trip_cost,holding_days,exit_reason"
data\research\strategy_results\ams_v1_h04_cross_sectional_rotation\ams-v1-h04-daily-results.parquet,READ,1461,11,,,"snapshot_time,gross_return,turnover,transaction_cost,net_return,equity,benchmark_return,benchmark_equity,exposure,active_positions,drawdown"
data\research\strategy_results\ams_v1_h04_cross_sectional_rotation\ams-v1-h04-trades.parquet,READ,637,8,,,"symbol,entry_signal_time,exit_signal_time,entry_price,exit_price,net_trade_return_after_round_trip_cost,holding_days,exit_reason"
data\research\strategy_results\ams_v1_h05_compression_expansion\ams-v1-h05-compression-expansion-daily-results.parquet,READ,1461,11,,,"snapshot_time,gross_return,turnover,transaction_cost,net_return,equity,benchmark_return,benchmark_equity,exposure,active_positions,drawdown"
data\research\strategy_results\ams_v1_h05_compression_expansion\ams-v1-h05-compression-expansion-trades.parquet,READ,57,8,,,"symbol,entry_signal_time,exit_signal_time,entry_price,exit_price,net_trade_return_after_round_trip_cost,holding_days,exit_reason"
data\research\strategy_results\momentum_reacceleration_v1\momentum-reacceleration-v1-daily-results.parquet,READ,1461,11,,,"snapshot_time,gross_return,turnover,transaction_cost,net_return,equity,benchmark_return,benchmark_equity,exposure,active_positions,drawdown"
data\research\strategy_results\momentum_reacceleration_v2_risk_control\momentum-reacceleration-v2-daily-results.parquet,READ,1461,17,,,"snapshot_time,base_gross_return,trailing_annualized_volatility,volatility_scale,drawdown_scale,risk_scale,gross_return,turnover,transaction_cost,net_return,equity,drawdown,benchmark_return,effective_exposure,next_target_exposure,active_positions,benchmark_equity"
reports\research\adaptive-trade-decisions.csv,READ,1,3,,,"status,component,reason"
reports\research\ams-ati-v1-counterfactual-results.csv,READ,1,2,,,"status,reason"
reports\research\ams-rd01-overlay-results-v1.csv,READ,1,3,,,"status,component,reason"
reports\research\ams-rd01-trade-regime-attribution-v1.csv,READ,1,3,,,"status,component,reason"
reports\research\ams-v1-h01-volatility-breakout-trades.csv,READ,86,8,,,"symbol,entry_signal_time,exit_signal_time,entry_price,exit_price,net_trade_return_after_round_trip_cost,holding_days,exit_reason"
reports\research\ams-v1-h02-aggressive-reacceleration-trades.csv,READ,93,8,,,"symbol,entry_signal_time,exit_signal_time,entry_price,exit_price,net_trade_return_after_round_trip_cost,holding_days,exit_reason"
reports\research\ams-v1-h03-liquidity-sweep-reversal-trades.csv,READ,87,8,,,"symbol,entry_signal_time,exit_signal_time,entry_price,exit_price,net_trade_return_after_round_trip_cost,holding_days,exit_reason"
reports\research\ams-v1-h04-cross-sectional-rotation-trades.csv,READ,637,8,,,"symbol,entry_signal_time,exit_signal_time,entry_price,exit_price,net_trade_return_after_round_trip_cost,holding_days,exit_reason"
reports\research\ams-v1-h05-compression-expansion-trades.csv,READ,57,8,,,"symbol,entry_signal_time,exit_signal_time,entry_price,exit_price,net_trade_return_after_round_trip_cost,holding_days,exit_reason"
reports\research\multi-asset-daily-history-coverage-v1.csv,READ,40,15,,,"symbol,row_count,first_close_timestamp,last_close_timestamp,first_tradable_timestamp_proxy,history_present_in_research,present_at_research_start,eligible_at_research_start_proxy,missing_daily_candle_count,coverage_status,data_quality_status,parquet_path,parquet_sha256,metadata_path,metadata_sha256"
reports\research\multi-asset-daily-history-coverage-v2.csv,READ,40,16,,,"symbol,row_count,first_close_timestamp,last_close_timestamp,first_tradable_timestamp_proxy,history_present_in_research,present_at_research_start,eligible_at_research_start_proxy,missing_daily_candle_count,coverage_status,data_quality_status,backward_page_count,parquet_path,parquet_sha256,metadata_path,metadata_sha256"
reports\research\multi-asset-daily-history-coverage-v3.csv,READ,40,18,,,"symbol,exchange_symbol,status,row_count,research_row_count,pre_research_row_count,first_open_time,last_open_time,last_close_time,has_pre_2025_history,listing_age_90d_proxy,recent_at_research_start_proxy,eligible_at_research_start_proxy,covers_research_end_proxy,calendar_gap_count,quote_volume_source,test_period_accessed,holdout_period_accessed"
reports\research\trade-regime-attribution.csv,READ,1,3,,,"status,component,reason"
reports\research\trend-pullback-v1-development-enriched-trades.csv,READ,121,47,,,"signal_timestamp,entry_bar_timestamp,exit_bar_timestamp,exit_reason,entry_base_price,entry_price,exit_base_price,exit_price,stop_price,quantity,entry_notional,entry_fee,exit_fee,gross_pnl,net_pnl,initial_risk,r_multiple,holding_bars,slippage_cost,signal_close,signal_volume,1h_ema_fast,1h_ema_slow,1h_atr,1h_rsi,1h_volume_median,4h_close,4h_ema_fast,4h_ema_slow,1d_close,1d_ema_fast,1d_ema_slow,stop_distance_atr,base_price_gross_pnl,total_trade_fees,accounting_residual,volume_ratio,entry_extension_atr,one_hour_ema_spread_atr,four_hour_ema_spread_pct,daily_ema_spread_pct,signal_year,signal_quarter,rsi_bucket,stop_bucket,extension_bucket,holding_bucket"
reports\research\trend-pullback-v1-development-trades.csv,READ,121,19,,,"signal_timestamp,entry_bar_timestamp,exit_bar_timestamp,exit_reason,entry_base_price,entry_price,exit_base_price,exit_price,stop_price,quantity,entry_notional,entry_fee,exit_fee,gross_pnl,net_pnl,initial_risk,r_multiple,holding_bars,slippage_cost"
reports\research\trend-pullback-v1-development-trades.pre-strict-risk.csv,READ,121,19,,,"signal_timestamp,entry_bar_timestamp,exit_bar_timestamp,exit_reason,entry_base_price,entry_price,exit_base_price,exit_price,stop_price,quantity,entry_notional,entry_fee,exit_fee,gross_pnl,net_pnl,initial_risk,r_multiple,holding_bars,slippage_cost"
reports\research\trend-pullback-v2-validation-trades.csv,READ,40,19,,,"signal_timestamp,entry_bar_timestamp,exit_bar_timestamp,exit_reason,entry_base_price,entry_price,exit_base_price,exit_price,stop_price,quantity,entry_notional,entry_fee,exit_fee,gross_pnl,net_pnl,initial_risk,r_multiple,holding_bars,slippage_cost"
reports\research\volatility-compression-breakout-v1-validation-trades.csv,READ,23,19,,,"signal_timestamp,entry_bar_timestamp,exit_bar_timestamp,exit_reason,entry_base_price,entry_price,exit_base_price,exit_price,stop_price,quantity,entry_notional,entry_fee,exit_fee,gross_pnl,net_pnl,initial_risk,r_multiple,holding_bars,slippage_cost"
reports\research\walk-forward-results.csv,READ,1,3,,,"status,component,reason"

```

## BF01 M02 Contributor Audit CSV

Path: `reports\research\ams-bf01-m02-contributor-audit-v1.csv`

```text
symbol,pnl,contribution_share,leave_one_total,rank

```

## BF01 Alpha Regression CSV

Path: `reports\research\ams-bf01-alpha-regression-by-fold-v1.csv`

```text
entity,fold,rows,daily_alpha_intercept,annualised_alpha_intercept,btc_beta,downside_beta,r_squared,residual_return,residual_sharpe

```

## BF01 Terminal Log Tail

Path: `reports\research\ams-bf01-terminal-execution.log`

```text
All checks passed!
Success: no issues found in 78 source files
........................................................................ [ 14%]
........................................................................ [ 28%]
...........................................................s............ [ 42%]
........................................................................ [ 57%]
........................................................................ [ 71%]
........................................................................ [ 85%]
.......................................................................  [100%]
=========================== short test summary info ===========================
SKIPPED [1] tests\test_ams_v3_f01_walk_forward_harness.py:528: set RUN_AMS_V3_INTEGRATION=1 to read the registered local dataset
502 passed, 1 skipped in 17.37s
䈊う‱䅆䱉剕㩅吠敨映汯潬楷杮瀠瑡獨愠敲椠湧牯摥戠⁹湯⁥景礠畯⁲朮瑩杩潮敲映汩獥਺
```

## Known Semantic Failures

- M05 was reported as 0% despite the established 268.61% Base-cost result.
- Equal-weight was reported below -100%, impossible for the intended Spot long-only benchmark.
- BTC buy-and-hold was reported below -100%.
- Exposure was reported above 9,900%.
- Drawdown was reported above 7,000%.
- Risk-adjusted comparison was authorised despite invalid units.
- TSM-84 received a robustness judgement despite insufficient source data.
