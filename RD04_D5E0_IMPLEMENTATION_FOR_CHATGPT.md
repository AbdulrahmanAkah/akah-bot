# RD04-D5E0 implementation

`RD04-D5E0-MIDWEEK-PULLBACK-DIAGNOSTIC` is a fixed, descriptive analysis of
the immutable D5B2 `PIT_UNIVERSE` / `CONTROL` trade projection.  It does not
simulate a portfolio, create an entry, execute a re-entry, or alter trade
logic.

The runner verifies the D5B2 trade-source SHA256 and the D0C adjudicated 4H
dataset SHA256 before it reads either input.  It rejects all bars opening in
2025 and every close after the research lock.  It permits only the three
already-recorded `END_OF_FOLD_EXIT` trades that close exactly at the lock.

For each unique `fold_id`, `symbol`, and Monday 00:00 UTC trade-associated
week, the implementation requires precisely 42 ordered four-hour bars.  A
missing or duplicate bar makes that weekly path incomplete; incomplete paths
are reported but cannot contribute a weekly-low or Friday-close observation.
Tied weekly lows select the earliest bar deterministically.

The pattern gate is frozen: Tuesday's weekly-low share must exceed one seventh
and every other weekday, the aggregate Tuesday-to-Friday return must be
positive, and Tuesday observations plus positive fold means must occur in at
least two folds.  No weekday search or alternate threshold is performed.
