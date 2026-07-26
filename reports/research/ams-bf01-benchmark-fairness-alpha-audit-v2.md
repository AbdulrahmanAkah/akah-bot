# AMS BF01 V2 — Exact-Schema Benchmark Fairness Audit

## النتيجة التنفيذية

- Research result: `PARTIAL`
- Safety stop: `PASS`
- Entity matching: `EXACT_ONLY`
- Aggregate/fold separation: `ENFORCED`
- Metric units: `EXPLICIT`
- Domain gates: `ENFORCED`
- Alpha value judgement: `INCONCLUSIVE`
- M02 contributor robustness: `NOT_EVALUATED`

## Raw return evidence

- M05 DUAL-28: `268.61%`
- Equal-weight Survivor-30: `783.33%`
- M05 minus Equal-weight: `-514.71%`

هذه مقارنة خام فقط. لا يُسمح بتحويلها إلى حكم Alpha لأن السلاسل اليومية المحاذاة والمتحقق منها غير متاحة في المصادر الحالية.

## M02 / TSM-84

- Status: `NOT_EVALUATED`
- Judgement: `NOT_EVALUATED`
- Reason: The concentration summary contains no per-symbol contribution ledger and no leave-one-asset-out outcomes.

## الملفات الناتجة

- `reports/research/ams-bf01-source-inventory-v2.csv`
- `reports/research/ams-bf01-benchmark-fairness-metrics-v2.csv`
- `reports/research/ams-bf01-m02-contributors-v2.csv`
- `reports/research/ams-bf01-regression-v2.csv`
- `reports/research/ams-bf01-benchmark-fairness-alpha-audit-v2.json`
- `reports/research/ams-bf01-benchmark-fairness-alpha-audit-v2.md`
- `BF01_V2_RESULT_FOR_CHATGPT.md`

## Safety boundaries

- Survivor universe only; not point-in-time.
- No promotion, production, live trading, MD02, Kelly or leverage authorization.
- 2025 and 2026 remain unaccessed.
