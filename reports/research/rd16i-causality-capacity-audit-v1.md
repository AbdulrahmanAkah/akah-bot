# RD16-I Causality and Capacity Audit v1

## User-directed capacity change

- Previous maximum positions: 3
- Registered maximum positions: 5
- Maximum open-risk fraction remains 2.25%.
- Position capacity and open-risk capacity are independent gates.

## Routing decisions

| Engine | Decision | Candidates |
|---|---|---:|
| COMPRESSION_EXPANSION_SPECIALIST_V2 | ADMITTED | 272 |
| COMPRESSION_EXPANSION_SPECIALIST_V2 | REJECTED_ENGINE_CONFLICT | 38 |
| COMPRESSION_EXPANSION_SPECIALIST_V2 | REJECTED_ENGINE_COOLDOWN | 2 |
| COMPRESSION_EXPANSION_SPECIALIST_V2 | REJECTED_SAME_SYMBOL_ACTIVE | 1 |
| TREND_CONTINUATION_CORE_V2 | ADMITTED | 324 |
| TREND_CONTINUATION_CORE_V2 | REJECTED_ENGINE_COOLDOWN | 17 |
| TREND_CONTINUATION_CORE_V2 | REJECTED_MAX_OPEN_RISK | 1 |
| TREND_CONTINUATION_CORE_V2 | REJECTED_SAME_SYMBOL_ACTIVE | 33 |

## Capacity states

| Positions before | Decision | Candidates |
|---:|---|---:|
| 0 | ADMITTED | 395 |
| 0 | REJECTED_ENGINE_COOLDOWN | 8 |
| 1 | ADMITTED | 168 |
| 1 | REJECTED_ENGINE_CONFLICT | 17 |
| 1 | REJECTED_ENGINE_COOLDOWN | 9 |
| 1 | REJECTED_SAME_SYMBOL_ACTIVE | 15 |
| 2 | ADMITTED | 33 |
| 2 | REJECTED_ENGINE_CONFLICT | 20 |
| 2 | REJECTED_ENGINE_COOLDOWN | 2 |
| 2 | REJECTED_SAME_SYMBOL_ACTIVE | 17 |
| 3 | REJECTED_ENGINE_CONFLICT | 1 |
| 3 | REJECTED_MAX_OPEN_RISK | 1 |
| 3 | REJECTED_SAME_SYMBOL_ACTIVE | 2 |

Realized PnL, MFE, MAE, holding duration, and exit reason were not used to admit or reject candidates.
