# RD16-C Execution and Constraint Audit v1

- Family/asset coverage rows: 24
- Detailed candidate and trade ledgers: local, under `data/raw/rd16c`
- Committed ledger manifest: `data/research/rd16c/local-ledger-manifest-v1.json`

| Family | Spot | Long | No leverage | Max positions | Max risk | Next bar |
|---|---:|---:|---:|---:|---:|---:|
| MTF_TREND_BREAKOUT | PASS | PASS | PASS | PASS | PASS | PASS |
| MTF_PULLBACK_RECLAIM | PASS | PASS | PASS | PASS | PASS | PASS |
| MTF_COMPRESSION_EXPANSION | PASS | PASS | PASS | PASS | PASS | PASS |
| MTF_RANGE_RECLAIM | PASS | PASS | PASS | PASS | PASS | PASS |

No derivatives, margin, shorts, leverage, DCA, Kelly sizing,
pyramiding or averaging down are present in the smoke harness.
