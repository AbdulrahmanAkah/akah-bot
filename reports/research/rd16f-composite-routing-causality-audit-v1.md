# RD16-F Composite Routing Causality Audit v1

Routing is fixed, deterministic, and does not use realized outcomes.

| Engine | Decision | Count | Fraction |
|---|---|---:|---:|
| COMPRESSION_EXPANSION_SPECIALIST | ADMITTED | 275 | 0.8786 |
| COMPRESSION_EXPANSION_SPECIALIST | REJECTED_ENGINE_CONFLICT | 35 | 0.1118 |
| COMPRESSION_EXPANSION_SPECIALIST | REJECTED_GLOBAL_COOLDOWN | 3 | 0.0096 |
| TREND_CONTINUATION_CORE | ADMITTED | 279 | 0.8774 |
| TREND_CONTINUATION_CORE | REJECTED_GLOBAL_COOLDOWN | 9 | 0.0283 |
| TREND_CONTINUATION_CORE | REJECTED_MAX_POSITIONS | 1 | 0.0031 |
| TREND_CONTINUATION_CORE | REJECTED_SAME_SYMBOL_ACTIVE | 29 | 0.0912 |

## Fixed ordering

- Trend priority: 10.
- Compression priority: 20.
- Same-symbol simultaneous candidates are coalesced before admission.
- Exits at the entry timestamp are treated as completed before admission.
- Global cooldown and portfolio limits use only information available by entry time.
