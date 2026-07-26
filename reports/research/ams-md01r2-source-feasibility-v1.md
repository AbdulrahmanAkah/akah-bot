# AMS-MD01R2 Source Feasibility

- Status: **PARTIAL**
- Sample cases: 8
- Fully resolved cases: 0

KuCoin announcements can resolve selected effective events, but the current symbols endpoint is not historical and the sampled retired symbols are not available through the public kline endpoint. Aggregated market prices do not prove venue membership.

| Case | Symbol | Evidence | Fully resolved | 4H rows |
|---|---|---|---:|---:|
| CURRENT_OLD | BTC-USDT | CANDLE_DERIVED | false | 1500 |
| CURRENT_POST_2021 | SOL-USDT | CANDLE_DERIVED | false | 1500 |
| KNOWN_DELISTED | ARRR-USDT | EXCHANGE_ANNOUNCEMENT_EFFECTIVE_TIME | false | 0 |
| SYMBOL_CHANGE | RNDR-USDT | EXCHANGE_ANNOUNCEMENT_EFFECTIVE_TIME | false | 0 |
| CONTRACT_MIGRATION | MATIC-USDT | CONFLICTED | false | 0 |
| REDENOMINATION | BTT-USDT | UNRESOLVED | false | 1500 |
| MULTIPLE_IDENTITIES | LUNA-USDT | CONFLICTED | false | 1500 |
| UNRESOLVED_IDENTITY | GRAM-USDT | UNRESOLVED | false | 1500 |
