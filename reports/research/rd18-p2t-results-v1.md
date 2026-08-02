# RD18-P2T results v1

## Input and identity

- Variant C: 376 pairs.
- Variant D: 299 pairs.
- Current-seed-only difference: 77 pairs.
- Weekly decisions: 313; post-warm-up: 301.
- Identity classifications: {"LEVERAGED_OR_SYNTHETIC_PRODUCT": 12, "TEMPORALLY_DISTINCT_ASSET": 65}.
- Identity corrections: 0.

The current-seed-only rows have valid committed KuCoin Kline identity records.
No symbol-only alias or migration was inferred.  Product-suffix exclusions
remain diagnostic and do not remove the source pairs.

## Liquidity scope

The audit covers 58 assets and
11904 asset-weeks selected by the frozen
P2T scope.  Diagnostic flags: {"EXTREME_SINGLE_DAY_CONCENTRATION": 627, "PRICE_RANGE_VOLUME_DIVERGENCE": 9, "SPARSE_INTRADAY_ACTIVITY": 3, "VOLUME_PATTERN_PLAUSIBLE": 11269}.
Metrics use only the existing P1R daily quote-turnover panel, with rows after
2024 excluded and no intraday data added.  Where available, each row also
records the asset median turnover relative to BTC-USDT and ETH-USDT in the
same causal window.

## Structural impact

No Variant E was created.  No universe membership was changed.  Possible
membership impact from actual identity corrections is
0 Top-6 rows and
0 Top-10 rows.
