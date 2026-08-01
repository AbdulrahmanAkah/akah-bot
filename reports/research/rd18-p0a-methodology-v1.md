# RD18-P0A KuCoin Symbol Inventory Recovery Methodology

This stage is source and inventory infrastructure only.  The execution venue is
KuCoin Spot.  Current currencies are a non-causal candidate seed; they never
establish historical membership.  A historical BASE-USDT pair is confirmed only
when the official Classic Spot Kline endpoint returns valid dated rows.

The causal timing rule remains Monday 00:00 UTC with a conservative 24-hour
availability delay, excluding Sunday candles.  All market observations are
strictly before 2025-01-01 UTC.  No strategy, trading, returns or optimization
work is performed.

The Historical Market Data page was inspected as a public UI.  It exposes Spot
and Futures tabs and a candlestick download control, but no stable unauthenticated
machine-readable catalogue or file identifier was observed; this channel is
therefore documented as inaccessible for reproducible inventory discovery.
