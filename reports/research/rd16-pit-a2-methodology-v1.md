# RD16-PIT-A2 Dynamic V3 Replay Methodology

A2 starts from the corrected A1B result at commit
`682bf4f4029a04015086c357c645199b6cabf717`.

## Control replay

The stage first loads the frozen RD16-K `STRONG_BULL_HOLD_96` candidate ledger
and re-executes the original deterministic router without PIT filtering. The
result must reproduce all three registered RD16-L ledgers—candidates,
evaluated candidates, and admitted trades—by content hash. It must also
reproduce the frozen RD16-M 1x and 2x-cost economics. A mismatch stops A2.

## Causal PIT gate

Each candidate is assigned to its Monday rebalance week using its entry time.
The weekly universe comes from corrected A1B membership and therefore uses the
previous Sunday market-cap observation through the established one-day lag.
Candidates ranked 1–6 are eligible. Absence from a complete Top-30 snapshot is
resolved as rank greater than 30 and is ineligible.

## Dynamic rerouting

PIT-ineligible candidates are removed before routing. Conflict rank is then
recomputed so that an eligible lower-priority engine can become the valid owner
when the former owner was not PIT eligible. The original V3 router is
re-executed with unchanged ordering, same-symbol exclusion, engine cooldowns,
five-position capacity, 2.25% maximum open risk, fixed risk sizing, holding
policy, and costs. This can create newly admitted trades that a ledger-only
filter would miss.

## Portfolio evaluation

The dynamically admitted ledger is marked to the same hourly data and evaluated
at 1.0x, 1.5x, 2.0x, and 3.0x transaction costs. The 2x scenario doubles costs
only; it is not leverage. Outputs include return, geometric monthly return,
profit factor, maximum drawdown, minimum cash and equity, capital feasibility,
annual results, concentration, asset and engine attribution, routing decisions,
admission changes, bull-window capture, and equity curves.

## Scope limitation

The market-cap panel covers 281 assets, but signal candidates exist only for the
registered pilot universe. A2 therefore measures a causal dynamic reroute inside
the registered candidate universe. It does not claim full-market signal
regeneration. The report calculates how often that candidate universe contains
all six true historical Top-6 assets. If coverage is below 95%, a surviving
strategy proceeds to A2B full Top-6 signal-data expansion rather than to
production or RD16-U.

No 2025 or 2026 data, optimization, formal p-value gate, leverage, borrowing,
shorting, derivatives, DCA, Kelly sizing, pyramiding, or production authorization
is permitted.
