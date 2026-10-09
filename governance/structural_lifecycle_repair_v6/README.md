# V6 owner-linked structural lifecycle repair

Research-only implementation. V4/V5 and their frozen outcomes are preserved.
This is **not** a certificate that all six schools and hybrids are faithful, all
defects are closed, or the changed version is profitable. No market replay ran.

## What is actually implemented

- A source-bound target book; targets are checkpoints for trend campaigns, not a
  fixed percentage cap. Finite trades require an actual owner goal after fees.
- Strict alternating owner structure `L0 -> H0 -> L1 -> H1`; independent bags of
  highs/lows cannot silently become trade ownership.
- Nondecreasing protected low and nondecreasing hard safety stop. Hard protection
  retains one earned structural level of room. A wick under the newer protected
  low alone is not an exit. An initial/standing hard stop still executes on touch.
- First owner close below protection opens suspicion. A contiguous later owner
  close failing to reclaim schedules exit at the next executable open. Reclaim
  cancels suspicion. Missing bars do not count as confirming observations.
- Native owner failures are typed, source-bound, causal and cannot be replaced by
  arbitrary strings. They retain authority independently of OHLC confirmation.
- Pending-setup live evidence graph with expiry/consumption/invalidation and no
  resurrection. This is a producer-facing API, not a completed detector rewrite.
- Actual research-kernel execution bridge across all nine grammars, explicitly
  opt-in. H3 owner is Elliott/count, not inherited Harmonic dispatcher.
- Capacity-aware exits remain pending until filled; no fake liquidation or exit
  authority from a future bar. Fee/cash records come from the existing kernel.
- Targeted risk restoration instead of blanket trimming unaffected assets; same
  hard limits, no diversification credit for correlated spot longs.

## Usage boundary

`LifecycleExecution.admit` requires a `Binding` with actual initial invalidation,
owner structure, owner timeframe, source SHA and known-at time. It will not choose
an arbitrary acceptance-bar low. Supply ALL current marks for existing holdings.
It is not armed by default. The caller must have separate research authority.

At each legal OPEN call `on_open`, then `restore_risk_at_open` and block admissions
if limits remain unresolved. At each completed 1H bar call `on_completed_hour`;
only supply an owner bar at its actual completed close. New protection applies to
the following hour. Do not run the V5 runner expecting it to consume this engine.

## Not solved by claiming a larger goal

A 10,000 dollar position does not entitle the trade to a 1,000 dollar profit.
The source-observable market structure must support a level; otherwise upside is
unknown. A tiny finite payoff may be economically weak, but no outcome-selected
minimum-profit threshold is invented here. There is no every-trade guarantee.

## Remaining authoritative blockers

1. Historical PIT exchange tick/lot/minimum archive not available.
2. Full Harmonic family-specific ratio/invalidation/management doctrine unbound.
3. Elliott parent-child/owner-count grammar not adjudicated.
4. Fresh Wyckoff reaccumulation cause/readiness contract missing.
5. Changed-version blind reserve fidelity not executed.
6. Raw detector producers/router are not all rebound to the new validity graph;
   the new bridge must not be misrepresented as a full market replay integration.
7. H2/ICT higher-timeframe trend grammars still require distinct source ownership.
8. No proven shared expected-opportunity selector or economic policy qualification.

These are quarantined, not filled with guesses. The user requested all defects
closed; this delivery closes the implemented management defects, but **cannot
truthfully claim that broader success condition**. Gate3 is not armed.

## Verification

See canonical_result.json, test_results.xml and source/output manifests. All
verification uses synthetic fixtures only; no 2024/2025 market rows, model fit,
new market economics, production changes or push.
