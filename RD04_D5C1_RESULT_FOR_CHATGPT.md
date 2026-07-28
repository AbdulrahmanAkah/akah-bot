# AMS RD04-D5C1 — Idiosyncratic Tail-Label Diagnostic

## Executive result

- Status: `COMPLETE`
- Decision: `IDIOSYNCRATIC_TAIL_LABEL_DIAGNOSTIC_COMPLETE`
- Total PIT control trades retained: `153`
- Labelled trade count: `7`
- Unlabelled trade count: `146`
- Labelled trade net PnL: `-10657.287679340297`
- Unlabelled trade net PnL: `-21008.370120243668`
- Labelled loss share: `0.07157930646497127`
- Labelled maximum adverse excursion: `-0.4514224369296833`

## Interpretation

- Events were frozen independently before this join.
- Every PIT control trade remains present and unchanged.
- Loss share uses `max(-net_pnl, 0)` and is not netted by wins.
- Association is not a causal attribution.
- Event and category tables are diagnostic only.

## Safety boundary

- No market data or portfolio simulation was used.
- No symbol, trade or loss was excluded.
- No production, universe, ranking, entry, exit or weight change is authorized.
- No 2025 test or 2026 holdout access.
