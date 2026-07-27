# RD01 Dominance Research Implementation

## Implemented stages

- `RD01-D0`: dominance source ingestion, raw hashing, daily UTC normalization,
  coverage checks, research-window locks, causal availability lag, no-forward-fill
  enforcement, and future-mutation invariance.
- `RD01-D1`: post-simulation tagging for candidate, selection, fill, and trade
  ledgers, with exact financial fingerprint invariance.
- `RD01-D2`: fold and aggregate attribution by directional dominance quadrant,
  including return, drawdown, Sharpe, BTC beta, equal-weight beta, MFE, MAE,
  holding time, win rate, profit factor, and cross-fold sign stability.
- `RD01-D3`: conservative decision gate returning exactly one of:
  `MINIMAL_OVERLAY_JUSTIFIED`, `NO_OVERLAY_JUSTIFIED`, or
  `INCONCLUSIVE_MORE_EVIDENCE_REQUIRED`.

## Data sources

- Coin Metrics Community API supplies free daily BTC/ETH estimated market-cap
  dominance and market-cap history without an API key. Total market cap is
  reconstructed causally from BTC estimated market cap and BTC dominance.
- DefiLlama `/stablecoincharts/all` supplies aggregate stablecoin market-cap
  history.

## Safety

- No M05 signal, ranking, sizing, entry, exit, or execution logic is modified.
- D0 and D1 cannot authorize an overlay.
- D2 performs attribution only.
- D3 may authorize only a future ATI-V1 experiment that reduces new-entry target
  weight in one stable harmful quadrant.
- Exit changes, pyramiding, averaging down, MD02, Kelly, leverage, production,
  live trading, and access to 2025/2026 data remain prohibited.

## Local validation completed in the isolated build

- Python compilation: PASS
- Focused tests: 23 PASS
- Full synthetic D0 run:
  - 1,461 aligned days
  - status `PASS`
  - future-mutation invariance `True`
  - no trading-logic change

Ruff and mypy were not installed in the isolated runtime. The repository runners
are structured for the existing repository environment, where those checks are
already available.
