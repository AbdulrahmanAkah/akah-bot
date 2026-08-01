# RD16-PIT-A1 Methodology

A1 attempts to resolve the 2019-2020 membership gap without network access.

Only local market-cap files whose names explicitly bound their contents to 2024
or earlier are eligible for reading. Files with generic names, or names
containing 2025 or 2026, are recorded but not read.

The registered 567-trade V3 ledger is joined to the A0 attribution by exact row,
symbol, entry timestamp, and net PnL identity. Weekly market-cap membership uses
Monday decisions and a one-day information lag.

A1 produces attribution by year, symbol, and engine. It also computes bounded
ledger-level scenarios. These scenarios do not replay portfolio routing,
position admission, cash, drawdown, or maximum concurrent risk.

Effective sample size and moving-block bootstrap outputs are descriptive only.
They are not p-values, confirmation gates, or inputs to Benjamini-Hochberg.

No 2025 or 2026 data may be accessed. RD16-U remains stopped.
