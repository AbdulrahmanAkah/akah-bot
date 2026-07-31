# RD16-L Causality and Holding-Policy Audit

## Constraints

- `source_variant_retained`: **True** — RD16-K retained exactly STRONG_BULL_HOLD_96.
- `same_symbol_overlap_absent`: **True** — No concurrent positions share a symbol.
- `engine_cooldowns_respected`: **True** — Trend 12h and Compression 24h cooldowns are preserved.
- `maximum_positions_respected`: **True** — Configured position capacity remains five.
- `maximum_open_risk_respected`: **True** — Open risk remains capped at 2.25% of initial equity.
- `holding_policy_respected`: **True** — Strong Bull uses 96 bars; all other regimes use 48.
- `sealed_cutoff_respected`: **True** — No candidate signal reaches the sealed cutoff.
- `spot_long_only_preserved`: **True** — No leverage, margin, short, or derivative path exists.

## Holding policy

- `BEAR`: 33 trades, configured max 48 bars, observed max 48 bars.
- `BULL`: 23 trades, configured max 48 bars, observed max 48 bars.
- `STRONG_BULL`: 511 trades, configured max 96 bars, observed max 96 bars.
