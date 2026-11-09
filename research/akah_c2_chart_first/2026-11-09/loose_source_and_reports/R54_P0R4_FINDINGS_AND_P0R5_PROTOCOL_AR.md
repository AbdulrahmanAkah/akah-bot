# AKAH BOT — R54-P0R4 evidence and R54-P0R5 research protocol

## 1. What was independently checked in the upload

Source: `UPLOAD_THIS_AKAH_R54_P0R4_MTM_AND_ENTRY_20261108_155014.zip`.

- 318 weekly marked-equity records: 106 calendar-week segments per C2/D2/E2, split by calendar year (one partial period at the start of each year).
- 480 entry-to-signal rows: C2 158, D2 160, E2 162 trades at 2X.
- R54-P0R4 script asserts exact original RD33 SHA-pinned sources and reconciles the December 31 equity to originally reported figures. This remains a *derivative* calculation from original RD33 replay, not a fresh replay from market tape.
- 2024 not accessed according to uploaded execution report. Listing/venue point-in-time eligibility is **not certified**.

### Weekly MTM classification (weekly equity delta; includes open positions)

| Universe | 2022 positive / negative / flat | 2023 positive / negative / flat | Total positive / negative / flat | Final equity, 2X |
|---|---:|---:|---:|---:|
| C2 | 6 / 10 / 37 | 20 / 18 / 15 | 26 / 28 / 52 | $132,780.04 |
| D2 | 6 / 10 / 37 | 19 / 19 / 15 | 25 / 29 / 52 | $155,718.38 |
| E2 | 6 / 10 / 37 | 19 / 19 / 15 | 25 / 29 / 52 | $136,797.48 |

C2: 26/106 = 24.53% of all calendar-week segments end with positive MTM change. Excluding 52 flat periods: 26/54 = 48.15% of nonflat weekly periods. This is **not** evidence of a steady weekly-profit strategy.

C2 2022: 43 trades (10 winning), annual MTM -$9,865.92. C2 2023: 115 trades (46 winning), annual MTM +$42,645.97. For 2023 best week +$15,254.78; worst -$15,614.88. The 2022 outcomes are equal across C2/D2/E2. Adding the larger universe did not resolve the 2022 failure.

### Retrospective signal-to-entry lag (C2; 2X)

| Category | 2022 count | 2022 net | 2023 count | 2023 net |
|---|---:|---:|---:|---:|
| MB ≤2h | 5 | +$458.49 | 27 | +$10,785.70 |
| MB 3–24h | 17 | +$1,799.16 | 36 | +$20,789.20 |
| MB 25–48h | 4 | −$3,202.38 | 6 | +$756.60 |
| MB 49–74h | 1 | −$1,962.70 | 3 | +$1,554.70 |
| RS immediate | 16 | −$6,958.49 | 43 | +$8,759.90 |

These are grouped realized PnLs after the fact; the lag is known at entry, but a filter selecting lag bins based on this table is **data snooping**. There has been no portfolio counterfactual rerun showing the effect on opportunity costs, capacity and downstream position sizing.

## 2. R54-P0R5: strict diagnostic event census

Purpose: Test whether the proposed 24h, 168h and 720h sweep/reclaim event definition yields a meaningful **frequency and diversity of opportunities** on the 20 R42 SHA-pinned tape pairs from 2022–2023.

Event definition at completed bar `t` for lookback `h` hours:

- `prior_low(h) = min(low[t-h], ..., low[t-1])` — prior **completed** candles only;
- event if `low[t] < prior_low(h)` **AND** `close[t] > prior_low(h)`.
- The event is observed only at `t`'s candle close, not executable at that candle's open or within the same candle.
- A candle may qualify for more than one horizon; produce **one unique row per pair/hour**, with multi-horizon flags.
- No event can be inferred before `h` prior complete candles (720h warm-up at start of 2022; no borrowing future candles).
- no volume selection, price targets, stops, policy parameters, economic outcomes, or trades are produced here.

Input authority contract: 20 pairs from `R42_2023_8759_CANONICAL_TAPE_WITNESS.json` (embedded in tool); their exact R27 offset from `Downloads/AKAH_R13R27_MEGA_WORK/R13R27_FROZEN_PLAN.json`; pinned `r43_data.py` SHA inside old R50 archive; files `repo/.akah_bot/v2r2_common_causal_tape_v1/pairs/{PAIR}.1H.bars.bin`.

Only exactly 8760 records for 2022 and exactly 8759 records for 2023, *per pair*, are read, and annual SHA checks are mandatory. Even if the file contains later data, reads stop at the R42 contract limit and never cross 2023. An archived R43 module must match the frozen source SHA prior to import.

Results:

- `R54_P0R5_CAUSAL_RECLAIM_EVENTS_20PAIR.csv`
- `R54_P0R5_EVENT_CENSUS_REPORT.json`
- `R54_P0R5_TERMINAL.log`

All work products stay in a new `Downloads` work folder. No repo/production modification, real trading, API connection, or economic backtest. If any source is unavailable or hashes do not match, output is `BLOCKED_SOURCE_OR_AUTHORITY` and the missing requirement is reported.

### Scientific limitation

This 20-pair frozen diagnostic cohort is not certified as historically PIT-tradable. 196-pair historical listing/venue authority is still unproven. This stage is allowed only to establish counts of observable candle patterns, not to claim strategy profitability, capital deployment feasibility, or extrapolate results to all 196 assets.

## 3. What would authorize the next stage

If source proofs and event census pass, freeze the *pre-registered event definition*. Then build a second stage that tests post-entry **realizable** outcomes under next-hour execution, all-in 1X/2X costs, liquidity and opportunity costs, using a genuinely causal eligibility set and suitable negative controls. Historical 2022–2023 remains a repeatedly viewed exploratory window, not an independent holdout. Do not open 2024.
