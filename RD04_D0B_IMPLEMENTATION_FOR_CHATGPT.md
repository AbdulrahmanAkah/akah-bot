# RD04-D0B — Point-in-Time Venue Data Expansion

## Scope

- Repair residual D0A identities such as `USDT_OMNI`, `PAX`, `SDAI`, `HBTC`,
  `LEO_EOS`, `FLOW_NATIVE`, and `AVAXX`.
- Rebuild the complete weekly market-cap ranking after those repairs.
- Probe KuCoin Spot historical 4H candles directly without requiring current
  market-list membership.
- Support both legacy and UTA KuCoin public kline payloads.
- Cache acquired pair history locally and derive deterministic 8H and 1D bars.
- Preserve disconnected candle histories as separate observed availability intervals.
- Build 157 venue-eligible weekly top-30 snapshots.
- Prove the registered MD01-M05 control remains financially invariant.

## Dataset boundary

- The registered AMS-V3 files are read-only.
- Expanded data are written under
  `data/research/rd04/kucoin-spot-usdt-expanded-v1/`.
- No candle is forward-filled, backfilled, interpolated, or price-filled.
- No 2025 test or 2026 holdout data are requested or used.

## Decision gate

- `PIT_UNIVERSE_REPLAY_READY` authorizes only RD04-D1 replay research.
- `PIT_UNIVERSE_SOURCE_EXPANSION_REQUIRED` authorizes only another data-source stage.
- `BLOCKED_BY_DATA_INTEGRITY` prevents replay until the acquired evidence is repaired.

## Safety

- No universe change is authorized by D0B.
- No ranking, alignment, target weight, entry, fill, exit, or cash logic changes.
- No production, live trading, MD02, Kelly, leverage, pyramiding, or averaging down.
