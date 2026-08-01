# RD18-P0 KuCoin Spot Liquidity Feasibility Methodology

This bounded probe evaluates the registered KuCoin Spot venue using only the
public `api.kucoin.com` announcement and Spot Kline interfaces. Announcements
are discovery evidence; current symbols and current market observations are
not used for historical membership. The primary Kline contract is the Classic
`/api/v1/market/candles` endpoint, whose observed pre-2025 row order is open,
close, high, low, base volume, quote transaction amount. The UTA endpoint is
probed independently and is not used when normalized rows disagree.

Causal timing is Monday 00:00 UTC with a preregistered 24-hour availability
lag: the latest usable daily candle opens Saturday 00:00 UTC and closes Sunday
00:00 UTC; Sunday is excluded. No market observation at or after 2025-01-01
UTC is accepted. No trading, strategy, optimization, or return analysis is
performed.
