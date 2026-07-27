# AMS RD01-D0 — Dominance Data and Causality Validation

## Executive result

- Status: `PASS`
- Reason: `FULL_CAUSAL_COVERAGE`
- Research stage: `RD01-D0`
- Scope: data ingestion and causality validation only
- Trading decisions changed: `NO`
- Overlay authorized: `NO`
- ATI-V1 authorized: `NO`

## Validation

- Aligned observations: `1461`
- Expected observations: `1461`
- No forward fill: `True`
- Causal availability enforced: `True`
- Future mutation invariance: `True`

## Coverage

| Source | Observations | Coverage | Missing | Maximum gap |
|---|---:|---:|---:|---:|
| `COINMETRICS_COMMUNITY_RECONSTRUCTED_MARKET_CAP` | 1461 | 1.0000 | 0 | 0 |
| `DEFILLAMA_STABLECOINS_ALL` | 1461 | 1.0000 | 0 | 0 |
| `ALIGNED_COINMETRICS_DEFILLAMA` | 1461 | 1.0000 | 0 | 0 |

## Raw source provenance

- `COINMETRICS_COMMUNITY_RECONSTRUCTED_MARKET_CAP`: `sha256:f78c608f47d01da4853011c86ded2a6e9478a8e8ece472d27dc80bc0ba1ec9c9` (17665158 bytes)
- `DEFILLAMA_STABLECOINS_ALL`: `sha256:8b45f555eb122248058ec3821b7cae1c083f8dd6bdeae8dd783403a85d29fce4` (1206254 bytes)

## Safety boundaries

- No 2025 test data access.
- No 2026 holdout access.
- No M05 entry, exit, sizing, or ranking change.
- No production, live trading, MD02, Kelly, or leverage authorization.
