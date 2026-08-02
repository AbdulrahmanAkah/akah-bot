# RD18-P2T methodology v1

This is an offline diagnostic audit of the restricted claim
`RESTRICTED_TO_376_KLINE_CONFIRMED_HISTORICAL_KUCOIN_SPOT_PAIRS`.  It compares the 376-pair Variant C input with the 299-pair
evidence-strong Variant D input and audits all 77 current-seed-only pairs.

The P1R/P2R/P2S artifacts were read without rebuilding them.  The committed
KuCoin daily panel is the only liquidity source.  No network request, archive
search, current metadata query, strategy replay, return calculation, trade
generation, candidate generation, optimization, or universe mutation is
permitted.  Identity findings are diagnostic and no asset is removed.

Frozen identity taxonomy: TEMPORALLY_DISTINCT_ASSET, TEMPORAL_ALIAS_OF_EXISTING_ASSET, TOKEN_MIGRATION, REBRAND_WITH_CONTINUOUS_IDENTITY, CONTRACT_MIGRATION, DUPLICATE_REPRESENTATION, WRAPPED_OR_BRIDGED_REPRESENTATION, SYMBOL_COLLISION, LEVERAGED_OR_SYNTHETIC_PRODUCT, UNRESOLVED.

Frozen liquidity flags: VOLUME_PATTERN_PLAUSIBLE, SHORT_LIVED_VOLUME_SPIKE, EXTREME_SINGLE_DAY_CONCENTRATION, PRICE_RANGE_VOLUME_DIVERGENCE, REPEATED_VOLUME_PATTERN, SPARSE_INTRADAY_ACTIVITY, UNRESOLVED_LIQUIDITY_INTEGRITY.  The panel has daily
turnover but no intraday observations; absence of intraday data is disclosed
and is not used to manufacture a failure.
