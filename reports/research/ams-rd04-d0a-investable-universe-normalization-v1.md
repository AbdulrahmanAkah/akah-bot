# AMS RD04-D0A — Investable Universe Normalization

## Executive result

- Status: `COMPLETE`
- Decision: `NORMALIZED_PIT_UNIVERSE_DATA_EXPANSION_REQUIRED`
- Reason: `CANONICAL_INVESTABLE_ASSETS_LACK_LOCAL_OHLCV_OR_AVAILABILITY`
- Weekly snapshots: `157`
- Complete normalized top-30 snapshots: `157`
- Refined missing local assets: `29`
- Stablecoin symbols frozen: `328`
- Raw asset identities excluded as stablecoins: `26`
- Raw asset identities canonicalized: `38`
- Minimum registered overlap: `0.400000`
- Financial invariance: `True`
- Universe change authorized: `NO`
- Trade logic changed: `NO`
- ATI-V1 authorized: `NO`

## Largest refined local-data gaps

| Canonical asset | Weekly appearances | Best rank | Mean rank | Source forms |
|---|---:|---:|---:|---|
| `CRO` | 157 | 4 | 8.465 | `cro` |
| `MATIC` | 157 | 4 | 11.064 | `matic_eth,pol_eth` |
| `BCH` | 157 | 11 | 16.338 | `bch` |
| `ICP` | 157 | 12 | 16.885 | `icp` |
| `ETC` | 157 | 14 | 17.834 | `etc` |
| `QNT` | 157 | 14 | 20.261 | `qnt` |
| `ALGO` | 157 | 14 | 21.414 | `algo` |
| `GNO` | 157 | 18 | 24.210 | `gno` |
| `LEO` | 156 | 14 | 18.641 | `leo_eth` |
| `LDO` | 142 | 15 | 22.746 | `ldo` |
| `LEO_EOS` | 135 | 21 | 24.852 | `leo_eos` |
| `CRV` | 125 | 18 | 24.328 | `crv` |
| `NEO` | 113 | 23 | 27.956 | `neo` |
| `HT` | 109 | 14 | 21.128 | `ht` |
| `MANA` | 95 | 18 | 24.853 | `mana` |
| `XVG` | 87 | 4 | 11.805 | `xvg` |
| `MKR` | 84 | 19 | 23.762 | `mkr` |
| `USDT_OMNI` | 68 | 24 | 28.574 | `usdt_omni` |
| `FTT` | 52 | 7 | 12.846 | `ftt` |
| `1INCH` | 38 | 26 | 29.211 | `1inch` |

## Identity contract

- Stablecoins are removed before ranking.
- Coin Metrics network-specific suffix forms are mapped to the parent asset.
- WBTC/WETH and registered migration aliases are collapsed to one parent identity.
- Duplicate forms use one maximum market-cap observation; they are never summed.
- Ranking is rebuilt after exclusions so every snapshot still contains 30 assets.

## Decision meaning

- `NORMALIZED_PIT_UNIVERSE_DATA_EXPANSION_REQUIRED` authorizes only RD04-D0B data-acquisition research.
- `NORMALIZED_PIT_UNIVERSE_REPLAY_READY` authorizes only RD04-D1 point-in-time replay research.
- `BLOCKED_BY_ASSET_IDENTITY_OR_COVERAGE` means identity or normalized coverage is incomplete.

## Interpretation boundary

- No fixed-universe member is removed from the registered simulation.
- No normalized candidate is traded in D0A.
- No ranking, alignment, weight, entry, exit, or portfolio cash is changed.
- No 2025 test data or 2026 holdout data are accessed.
- No production, live trading, MD02, Kelly, leverage, pyramiding, or averaging down is authorized.
