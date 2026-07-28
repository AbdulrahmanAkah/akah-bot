# RD04 Final Adjudication and Closure

## Final decision

- Status: `COMPLETE`
- Decision: `RD04_RESEARCH_SEQUENCE_COMPLETE_NO_EDGE_CONFIRMED`
- Completed stages: `22`
- Rejected hypotheses: `6`
- Confirmed registered edges: `0`
- Trading, production, and PIT-baseline authorization: `false`.
- RD05 authorization: `RD05_PROTOCOL_REGISTRATION_ONLY`.

## Why RD04 started and what D0--D4 established

RD04 tested whether the favorable historical Fixed-universe result could survive a causal point-in-time replay.  D0 registered and adjudicated the PIT data path.  D1 showed that PIT did not pass its registered base or stress gates.  D2 and D3 isolated membership interactions: entrant underperformance and removed-survivor displacement are diagnostic associations, not authorized rules.
D4 froze exactly six D5 hypotheses.

- D1 Fixed base compounded return: `2.6861470605832247`
- D1 PIT base compounded return: `-0.4810345157020558`
- D1 PIT base profit factor: `0.8533000104768909`
- D3 entrant PIT net PnL: `-94301.5435961918`
- D3 removed-survivor Fixed net PnL: `99489.7769194499`

## D5 evidence-only adjudication

- D5A liquidity-floor treatment failed; it is not an authorized universe change.
  Base return delta: `-0.055126588705641244`; PF delta: `-0.05545703538888003`.
- D5D recovered BF01 accounting and defined PIT equal weight correctly.
  M05 still did not establish benchmark-relative edge.
  M05 base return: `-0.4810345157020558`; equal-weight base return: `-0.3477089988835531`.
- D5B structural stops improved aggregate containment but only one fold.
  No production exit change is authorized.
  Base return delta: `0.14798842236375032`; improved folds: `1`.
- D5C external-event labels covered only a minority of loss.
  They do not authorize a blacklist.
- D5E Tuesday weekly-low share was `0.13157894736842105` versus Monday   `0.24342105263157895`; the pre-registered pattern gate failed.
- D5F found no support for a membership-exit treatment.
  Events: `54`; unique symbols: `16`;   later re-entry share: `0.7962962962962963`; Fixed-minus-PIT gap share:   `-0.006496207717361605`.

## Root-cause adjudication

- Primary supported failure: survivorship-biased Fixed performance did not survive PIT replay.
- Primary supported failure: M05 did not beat matched PIT equal weight on base or stress costs.
- Secondary contributors: entrant underperformance and survivor displacement are diagnostics, not treatments.
- Rejected explanations: liquidity floor, Tuesday timing, and membership-exit treatment.
- Unresolved: the independent economic predictive value of the momentum signal.

## Pinned facts

- D5C1 labelled-loss share: `0.07157930646497127`
- D5E0 Tuesday weekly-low share: `0.13157894736842105`
- D5F membership exits: `54`
- D5F Fixed-vs-PIT diagnostic gap share: `-0.006496207717361605`

## Future work outside RD04

The only permitted next action is RD05 protocol registration.
Its candidate program is recorded in the companion CSV.
It isolates signal prediction,
alpha layers, benchmark definition, and pre-holdout stopping rules.
It authorizes no simulation automatically.

No 2025 test or 2026 holdout data were accessed by this closure.
