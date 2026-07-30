# RD14 Scored Breakout Trade Audit V1

All decisions below use completed-bar features. Entries and health exits execute on a later bar; initial stops use the engine's conservative gap rule.

## First trades

- `TRADE-000001` BTC/USDT: 2019-10-28T00:00:00Z -> 2019-11-17T00:00:00Z; exit `HEALTH_SCORE_CONFIRMED_DETERIORATION`; net PnL `-833.554734`.
- `TRADE-000002` BTC/USDT: 2020-01-09T00:00:00Z -> 2020-03-02T00:00:00Z; exit `HEALTH_SCORE_CONFIRMED_DETERIORATION`; net PnL `693.994569`.
- `TRADE-000003` ETH/USDT: 2020-01-08T00:00:00Z -> 2020-03-13T00:00:00Z; exit `INITIAL_PROTECTIVE_STOP`; net PnL `-1021.766591`.

## Coverage

- Candidates inspected: `3740`.
- Position-health observations inspected: `2101`.
- Closed trades inspected programmatically: `23`.
- Audit cases include first trades, first trade per asset, best and worst trade, health exits, hard stops, group-floor rejections, cooldowns, and score-ranked simultaneous candidates when present.
