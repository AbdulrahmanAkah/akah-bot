# AMS RD04-D0 — Point-in-Time Universe Readiness

## Executive result

- Status: `COMPLETE`
- Decision: `PIT_UNIVERSE_DATA_EXPANSION_REQUIRED`
- Reason: `HISTORICAL_TOP_CANDIDATES_LACK_LOCAL_OHLCV_OR_AVAILABILITY`
- Weekly snapshots: `157`
- Complete top-30 snapshots: `157`
- Missing local assets: `36`
- Minimum registered overlap: `0.300000`
- Median registered overlap: `0.333333`
- Financial invariance: `True`
- Universe change authorized: `NO`
- Trade logic changed: `NO`
- ATI-V1 authorized: `NO`

## Existing M05 contribution concentration

- Symbols with trades: `29`
- Top-1 share of positive symbol PnL: `0.18040560400257025`
- Top-3 share of positive symbol PnL: `0.48170563639752245`
- Absolute-PnL HHI: `0.07314752346236476`

## Largest local-data gaps

| Asset | Weekly appearances | Best rank | Mean rank |
|---|---:|---:|---:|
| `USDT` | 157 | 3 | 3.057 |
| `USDT_TRX` | 157 | 4 | 5.758 |
| `USDC` | 157 | 4 | 6.025 |
| `USDT_ETH` | 157 | 5 | 6.643 |
| `USDC_ETH` | 157 | 5 | 7.274 |
| `SHIB_ETH` | 157 | 7 | 11.764 |
| `CRO` | 157 | 5 | 13.879 |
| `AVAXP` | 157 | 10 | 16.745 |
| `WETH` | 157 | 13 | 17.490 |
| `MATIC_ETH` | 157 | 9 | 17.631 |
| `WBTC` | 157 | 13 | 19.548 |
| `DAI` | 151 | 16 | 23.139 |
| `BCH` | 141 | 16 | 23.716 |
| `ETC` | 139 | 23 | 26.540 |
| `ICP` | 132 | 19 | 24.636 |
| `LEO_ETH` | 130 | 22 | 26.623 |
| `BUSD` | 95 | 9 | 15.253 |
| `XVG` | 87 | 9 | 18.540 |
| `QNT` | 77 | 23 | 26.519 |
| `ALGO` | 69 | 20 | 26.435 |

## Decision meaning

- `PIT_UNIVERSE_REPLAY_READY`: market-cap candidates and all required local OHLCV/availability data are complete; only then may D1 replay research run.
- `PIT_UNIVERSE_DATA_EXPANSION_REQUIRED`: the market-cap history is usable, but the local dataset must be expanded before any point-in-time universe replay.
- `BLOCKED_BY_MARKET_CAP_DATA`: the market-cap panel itself is incomplete.

## Interpretation boundary

- D0 is a data-readiness and survivor-concentration audit only.
- Raw market-cap rank does not prove venue tradability or strategy eligibility.
- No fixed-universe member is removed and no new asset is traded.
- No ranking, alignment, weight, entry, exit, or portfolio cash is changed.
- No 2025 test data or 2026 holdout data are accessed.
- No production, live trading, MD02, Kelly, leverage, pyramiding, or averaging down is authorized.
