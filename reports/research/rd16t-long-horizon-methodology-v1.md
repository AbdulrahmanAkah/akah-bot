# RD16-T Signal Architecture Reset and Long-Horizon Methodology

RD16-T stops extending the rejected hourly breakout architecture. It evaluates a new
Spot-only, Long-only research architecture driven by completed daily and weekly bars.
The ten-asset universe frozen by RD16-R is used without additions or substitutions.

## Fixed hypotheses

1. `DAILY_PULLBACK_RECLAIM`: daily EMA20 reclaim inside a rising weekly trend.
2. `DAILY_COMPRESSION_BREAKOUT`: twenty-day breakout after a causal daily volatility base.
3. `WEEKLY_TREND_ACCELERATION`: weekly EMA20 recapture with positive four-week slope.
4. `CROSS_SECTIONAL_LEADER_PULLBACK`: top 20-day and 60-day leader on a controlled pullback.
5. `DEEP_PULLBACK_RECOVERY`: bounded 10%-30% correction followed by daily trend recovery.

All thresholds, holding horizons, and exit parameters are pre-registered. No parameter
search, winner selection, or outcome-conditioned alteration is permitted.

## Architecture reset

- Signal state is computed only from completed daily and weekly candles.
- Cross-sectional 20-day and 60-day ranks are causal and use the frozen ten-asset universe.
- Entry occurs at the next hourly bar open after the completed higher-timeframe signal.
- Initial risk distance uses daily ATR14 fixed at signal time.
- The previous short-horizon profit-floor exit is not used.
- Exits use a hard stop, a causal hourly Chandelier-style trailing stop, and a fixed time cap.
- Maximum holding periods range from 10 to 45 days according to the hypothesis and regime.
- Risk remains fixed at 0.50%, or 0.75% in Strong Bull, without compounding.

## Evaluation

Each hypothesis is tested standalone and as an additive overlay on frozen
`COMPOSITE_ALPHA_V3`. Frozen V3 trades retain routing priority. The five-position limit,
2.25% maximum open risk, same-symbol exclusivity, and engine cooldowns remain enforced.

The stage records standalone and overlay economics, 1x-3x cost stress, annual results,
bull-window capture, asset contribution, exit-policy outcomes, holding-duration evidence,
routing decisions, deterministic replay, and causality checks.

## Data and prohibitions

RD16-T reuses the locally verified RD16-R datasets. It performs no network acquisition.
The 2025 test period and 2026 holdout remain sealed. No leverage, margin, shorting,
derivatives, borrowing, interest, DCA, Kelly sizing, pyramiding, averaging down, Dune,
optimization, winner selection, or production authorization is allowed.
