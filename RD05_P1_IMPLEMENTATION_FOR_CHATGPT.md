# RD05 P1 implementation

P1 audits registered sources, schemas, UTC timestamps, OHLCV aggregation, coverage,
native quote-turnover keys, and causal decision-time contracts. It deliberately does
not create a panel, signal, label, return, regime value, rank, model, backtest, or
portfolio result.

The critical PIT membership source is checked independently for causal 2021 coverage.
Absent registered coverage is a blocking finding, not a reason to reconstruct history.
