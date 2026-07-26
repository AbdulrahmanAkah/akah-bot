# AMS BF01 — Benchmark Fairness and Alpha Value Audit

## النتيجة التنفيذية

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

## السؤال المركزي

هل يضيف اختيار وتوقيت MD01 قيمة مقارنة بامتلاك الكون نفسه بأوزان متساوية، بعد ضبط التعرض والتقلب والمخاطرة؟

## المقارنة

| Portfolio | Total return | CAGR | Sharpe | Sortino | Calmar | Max DD | Worst month | Avg exposure |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| M05_DUAL_28 | 0.00% | 0.00% | -1.2942 | -1.6776 | -0.9614 | 0.00% | 0.00% | N/A |
| EQUAL_WEIGHT | -7046.72% | -7046.72% | -1.0734 | -1.3952 | -0.9967 | 7070.03% | -2979.93% | 9945.21% |
| EXPOSURE_MATCHED_EQUAL_WEIGHT | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A |
| VOLATILITY_MATCHED_EQUAL_WEIGHT | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A |
| BTC_BUY_HOLD | -6435.48% | -6435.48% | -1.2942 | -1.6776 | -0.9614 | 6694.02% | -3659.32% | N/A |
| HIGH_BETA_28 | 235.04% | N/A | N/A | N/A | N/A | N/A | N/A | 9945.21% |
| HIGH_BETA_84 | 138.32% | N/A | N/A | N/A | N/A | N/A | N/A | 9945.21% |

ملاحظة: القيم التي تعذر استخراج سلسلتها اليومية وإعادة حسابها موسومة في JSON/CSV كقيم مرجعية معلنة سابقًا، ولا تُعامل كإعادة حساب مستقلة.

## الحكم على قيمة Alpha

`INCONCLUSIVE`

- M05 produced at least as much raw return as full-exposure Equal-weight.
- M05 risk-adjusted metrics are not jointly superior to Equal-weight.

## عدالة Benchmark

- Risk-adjusted comparison available: `true`
- Exposure-matched Equal-weight available: `false`
- Volatility-matched Equal-weight available: `false`

### الفجوات المتبقية

- Exposure-matched Equal-weight could not be constructed because aligned M05 daily exposure and Equal-weight daily returns were unavailable.
- Volatility-matched Equal-weight could not be constructed from sufficiently aligned daily return series.
- Fold-level residual alpha regression could not be recomputed from aligned daily portfolio and BTC return series.

## تدقيق M02 / TSM-84

- Status: `INSUFFICIENT_SOURCE_DATA`
- Judgement: `TSM84_NO_ROBUST_EDGE`

## Alpha وBeta حسب الطيات

`BLOCKED_BY_MISSING_ALIGNED_DAILY_SERIES`

## تفسير النتيجة

1. المقارنة الخام بين M05 وEqual-weight لا تكفي وحدها؛ الحكم يعتمد أيضًا على Sharpe وCalmar وMaximum Drawdown والتعرض.
2. Equal-weight الكامل قد يتفوق لأنه مستثمر بنسبة أعلى؛ لذلك بُنيت المقارنات المطابقة للتعرض والتقلب متى سمحت البيانات.
3. جميع النتائج داخل Survivor-30 فقط؛ لا يوجد Point-in-Time universe ولا يجوز تحويل النتيجة إلى EDGE_PASS.
4. ATI ما يزال إنجازًا هندسيًا فقط، وقيمته التداولية غير مثبتة.
5. Dominance ما تزال BLOCKED_BY_DATA.

## القرار البحثي

- Alpha value: `INCONCLUSIVE`
- TSM-84 robustness: `TSM84_NO_ROBUST_EDGE`
- Momentum above Beta: `UNRESOLVED`
- Production: `BLOCKED`
- MD02: `BLOCKED`
- Kelly: `BLOCKED`

## بوابات السلامة

- No leverage: `PASS`
- No shorting: `PASS`
- Total exposure above 1.0 introduced: `false`
- 2025 accessed: `false`
- 2026 accessed: `false`
- Dynamic matrix consumed: `0/12`
- Dynamic cost executions consumed: `0/36`

## الملفات الناتجة

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
