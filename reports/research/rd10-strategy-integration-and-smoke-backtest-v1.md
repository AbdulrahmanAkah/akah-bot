# RD10 Strategy Integration and Smoke Backtest v1

## Executive summary

`AKAH_REGIME_MOMENTUM_BREAKOUT_V1` was registered, integrated with the existing
event-driven Spot engine, and executed on a frozen local BTC/USDT daily window.
The run produced two entries and two closed trades with deterministic replay,
causal next-bar execution, complete cost accounting, and no breach of Spot or
capital constraints.

Decision: `RD10_STRATEGY_INTEGRATION_AND_SMOKE_BACKTEST_CONFIRMED`.

Next stage: `RD11_BASELINE_MULTI_ASSET_BACKTEST`.

## Strategy and source specification

- Name: Akah Regime-Adaptive Momentum Breakout V1.
- Registration: `reports/research/rd10-strategy-specification-v1.md`.
- Machine contract: `data/research/rd10/strategy-specification-v1.json`.
- New independent baseline assembled from EMA50/EMA200 regime alignment,
  RSI14, prior-20 breakout, prior-20 volume confirmation, ATR sanity, and
  fixed-risk exits.
- No rejected strategy was copied verbatim and no optimization was performed.

## Smoke selection and data

- Asset: BTC/USDT.
- Source: frozen local KuCoin daily OHLCV parquet.
- Period: 2022-06-17 through 2023-06-18 exclusive.
- Selection rule frozen before results: the first connected 366-day interval
  in the local BTC series, containing 200 warm-up bars and 166 later bars.
- The period was not expanded and the 1.10 volume threshold was not relaxed.

## Execution assumptions

- Initial cash: 100,000 USDT.
- Fee: 0.10% per fill.
- Slippage: 0.05% adverse per fill.
- Risk: 1% current equity; position value capped at 25%.
- Maximum positions: two portfolio-wide and one per asset.
- Signal evaluation: completed daily close.
- Entry and close-based exit: next daily open.
- Protective stop: intrabar; a gap below stop uses the worse open.
- Final position policy: forced close at final close with adverse slippage.

## Leakage controls

Indicators are computed in chronological streaming order. Breakout and volume
windows are captured before the current bar is appended. There are no centered
windows, negative shifts, future backfills, or same-close entries. Focused tests
verify next-bar execution and deterministic replay.

## Results

- Signals: 3 total, including 2 entries.
- Orders: 4, including one synthetic protective-stop order record.
- Fills: 4.
- Closed trades: 2.
- Open positions at end: 0.
- Initial equity: 100,000.00.
- Final equity: 101,385.160195.
- Net return: 1.385160%.
- Gross profit: 2,447.384924.
- Gross loss: -1,007.493244.
- Total fees: 54.731485.
- Estimated slippage cost: 27.366109.
- Win rate: 50%.
- Average win: 2,423.618923.
- Average loss: -1,038.458728.
- Expectancy: 692.580097 per trade.
- Profit factor: 2.333862.
- Maximum drawdown: 1.532571%.
- Exposure: 10.655738%.
- Average holding period: 19.5 daily bars.
- Turnover: 0.547315 times initial capital.
- Buy-and-hold return over the recorded comparison interval: 59.297707%.

These short-window metrics verify functionality only. They are not a final
profitability assessment and are not suitable for annualized inference.

## Validation and tests

- RD10 focused tests with warnings as errors: 11 passed.
- All `tests/research` with warnings as errors: 484 passed.
- Core engine regressions with warnings as errors: 9 passed.
- Strict mypy: PASS across 139 source files.
- Ruff check and format check: PASS.
- Python compilation: PASS.
- Signal/order/fill linkage: PASS.
- Trade PnL reconciliation: PASS.
- Equity reconciliation: PASS.
- Deterministic replay: PASS.
- Spot-only, long-only, no leverage, no margin, no short, no DCA, no Kelly,
  no pyramiding, and no negative cash: PASS.

## Manual audit

All three signals and both trades were reviewed in
`reports/research/rd10-smoke-trade-audit-v1.md`. The sample contains one stopped
loss and one profitable 30-bar time exit. Signal timestamps precede their
normal fills, costs are non-zero, and all indicator inputs were available at
decision time.

## Bug and fix

The initial run found one reporting-gate bug: false-valued safety fields such
as `test_2025_accessed=false` were incorrectly included among required true
invariants. The gate was corrected to separate positive invariants from
negative safety flags, and regression coverage was added. No strategy rule,
period, fee, slippage, or result was changed.

## Limitations

This is a one-asset functional smoke run with only two trades. Market-level
RD09C data was not joined because RD10's registered entry contract uses local
OHLCV only. No 2025 or 2026 data, Dune API, optimization, grid search, or
production operation was used.
