# RD18-P2R restricted-universe structural comparison methodology

This stage is an offline, structural comparison of the restricted KuCoin Spot
universe. It consumes only committed RD18-P1R outputs and does not acquire new
market data. The research claim is explicitly
`RESTRICTED_TO_376_KLINE_CONFIRMED_HISTORICAL_KUCOIN_SPOT_PAIRS`; it is not a
claim that all KuCoin pairs that ever existed were recovered.

The frozen inputs are the P0 68-pair, P0A 300-pair, P0B/P1R 376-pair and
evidence-strong 299-pair variants. The comparison uses the same 313 Monday
decision timestamps and reports the 301 post-warm-up decisions separately.
All rankings use the P1R trailing 28-day median daily USDT quote turnover,
deterministic liquidity/listing-age/canonical-ID tie breaking, Top-4/6/8/10/30
sets, and Top-6 entry/Top-8 retention hysteresis.

The analyses cover growth, persistence, turnover, liquidity concentration,
cutoff margins, provenance sensitivity, current-seed-only influence, retained
delisted pairs, the four already-frozen RD17 CMC snapshots, and the configured
legacy asset list as a non-causal diagnostic. No strategy returns, trades,
signals, candidates, post-2024 observations, archive search, or network request
is permitted in this stage.

Omission risk is classified by the preregistered exact thresholds in
`data/research/rd18_p2r/rd18-p2r-protocol-v1.json`. The restricted limitation is
carried into every report and production authorization remains false.
