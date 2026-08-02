# RD18-P1R methodology

This stage reconstructs a **restricted** causal KuCoin Spot liquidity universe.
The claim is exactly `RESTRICTED_TO_376_KLINE_CONFIRMED_HISTORICAL_KUCOIN_SPOT_PAIRS`;
it is not a claim that every KuCoin pair is historically inventoried.

The immutable input is the RD18-P0B final inventory.  No current symbol list,
current ticker, archive search, or new discovery channel was used.  P0C
demonstrated bounded Common Crawl index-access failure; it did not prove that
Common Crawl contains no KuCoin captures.  No further archive work is
authorized here because the marginal research value is insufficient.

Daily Classic Spot Klines are reused from P0B immutable raw responses.  A
Monday 00:00 UTC decision uses only candles with
`causal_available_at = close_time + 24 hours <= decision_time`, which excludes
Sunday and normally makes Saturday the latest usable candle.  Eligibility is
90 calendar days of listing age plus at least 26 valid observations in the
preceding 28 calendar days.  Ranking uses the median daily USDT quote turnover,
then listing age and canonical asset ID as deterministic tie-breakers.

Inventory variants are A=P0 (68), B=P0A (300), C=P0B (376, primary), and
D=evidence-strong (P0B pairs not discovered solely by current-currency seeding).
No strategy returns, trades or optimization are produced.
