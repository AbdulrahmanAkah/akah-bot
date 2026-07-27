# RD04-D0C — Source Integrity Adjudication

## Scope

- Reclassify deterministic unavailable KuCoin pairs as venue absence, not data corruption.
- Preserve unresolved transport or payload failures as blocking source-integrity failures.
- Recover complete cached primary or migration sources that D0B rejected only because
  an optional alias failed.
- Rebuild the isolated expanded 4H, 8H, daily, and availability datasets.
- Rebuild 157 venue-eligible weekly top-30 snapshots and resolve replay readiness.
- Prove the registered MD01-M05 simulation remains financially invariant.

## Expected evidence repair

- `BCH-USDT` remains usable even though `BCHABC-USDT` is unavailable.
- `POL-USDT` supplies the observed MATIC history even though `MATIC-USDT` is unavailable.
- Symbols with deterministic KuCoin pair-unavailable responses remain excluded causally.
- No unavailable symbol is backfilled, substituted, or assigned synthetic availability.

## Safety

- No ranking, alignment, entry, sizing, exit, fill, or cash rule changes.
- No original registered dataset overwrite.
- No 2025 test or 2026 holdout access.
- No production, live, MD02, Kelly, leverage, pyramiding, or averaging-down authorization.
