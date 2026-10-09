# AKAH Exit Brain — Research Doctrine & Architecture Compass V1

**Authority class:** Project research doctrine / architecture compass  
**Purpose:** Prevent research drift, loss of architectural intent, and confusion between simple causal probes and the final adaptive exit intelligence.  
**Important:** This document is **not** an execution protocol and does not authorize runtime behavior by itself. Frozen experiment protocols, causal authority bindings, and governed task contracts control implementation when they are more specific.

---

## 1. North Star

AKAH Bot is not trying to discover one clever static exit rule.

The target is an **intelligent, adaptive spot-long exit brain** that can respond to different lifecycle conditions and market environments without using future information, pair identity, year identity, post-hoc outcome rules, or hidden optimization.

The final exit system should answer a richer question than:

> “Did one threshold fire?”

It should answer:

> “What phase is this trade in, what evidence has it produced, what kind of deterioration or progress is occurring, what is the cost of continuing to hold it, and what action is causally justified now?”

Complexity is not the goal. **Causal state awareness** is the goal.

---

## 2. The key distinction: causal probes vs final architecture

The first-round candidates A/B/C are deliberately simple.

That simplicity must never be misread as the intended final intelligence.

They are **causal probes** designed to isolate three different mechanisms:

- **C — Pre-progress non-confirmation:** the trade has not proven its thesis within a fixed opportunity window.
- **A — Structural deterioration:** current market structure has broken.
- **B — Post-progress protection:** the trade proved progress, then gave back more than volatility-adjusted protection allows.

The scientific role of these candidates is to answer:

> “Does this mechanism contain incremental information over the frozen native exit system?”

They are not the final answer to:

> “What should AKAH’s complete exit brain be?”

### Canonical reminder

**Simple primitive ≠ simple final system.**

We first prove primitives because a complicated system that works cannot be understood causally if its components were never isolated.

---

## 3. Current primitive families

### 3.1 C — Pre-progress confirmation failure

Conceptual question:

> “Did the trade receive enough causal opportunity to prove progress, but fail to do so?”

Current frozen first-round hypothesis:

`NO_STRUCTURAL_PROGRESS_AFTER_12_BARS_V1`

Role:

- Operates in the **pre-progress** phase.
- Does not wait for a later structural breakdown.
- Does not protect an already successful trade.
- Tests whether capital is being held in a thesis that never became structurally confirmed.

Canonical shorthand:

**C = It never really started.**

This family may later evolve into a richer **time-to-confirmation / thesis-validation state machine**, but only after the simple mechanism is measured independently.

---

### 3.2 A — Structural deterioration

Conceptual question:

> “Has current price structure broken enough that the trade thesis should no longer be treated as intact?”

Current frozen first-round hypothesis:

`DONCHIAN_CLOSE_BREAK_10_V1`

Role:

- Observes recent market structure.
- Does not require the trade to have made progress first.
- Does not use profit state as the primary trigger.
- Tests a **structure failure** mechanism rather than a time failure mechanism.

Canonical shorthand:

**A = The structure broke.**

Future versions may distinguish soft deterioration, confirmed break, false break, volatility shock, or trend exhaustion, but those distinctions are **not yet authorized rules**.

---

### 3.3 B — Post-progress volatility-adjusted protection

Conceptual question:

> “After the trade proved progress, has the giveback become too large relative to observed volatility?”

Current frozen first-round hypothesis:

`POST_MEMORY_ATR_RATCHET_22_3_V1`

Role:

- Inactive before progress has been proven.
- Activates after Memory.
- Protects progress using a volatility-adjusted ratchet.
- Separates normal fluctuation from post-progress deterioration.

Canonical shorthand:

**B = It started, succeeded, then gave back too much.**

Future versions may adapt protection strength to progress quality, trend persistence, volatility regime, MFE/MAE, or time since last progress. Such adaptation is a future research layer, not part of the primitive proof.

---

## 4. Lifecycle architecture we are trying to reach

The conceptual exit brain should eventually reason in lifecycle phases rather than treating every open trade identically.

```text
ENTRY
  |
  v
PRE_PROGRESS
  |
  | evidence of structural progress / Memory
  v
POST_PROGRESS
  |
  +--> HEALTHY_PROGRESS
  |
  +--> STALLED
  |
  +--> STRUCTURAL_DETERIORATION
  |
  +--> VOLATILITY_DAMAGE
  |
  +--> THESIS_FAILURE
  |
  v
EXIT / NATIVE SAFETY
```

These names are an **architecture map**, not a currently authorized classifier.

The long-term objective is a causal state machine in which transitions are based only on information observable at decision time.

---

## 5. Candidate future lifecycle states

A deeper architecture may eventually distinguish states such as:

- `UNCONFIRMED`
- `EARLY_PROGRESS`
- `CONFIRMED`
- `HEALTHY_TREND`
- `STALLED`
- `DETERIORATING`
- `STRUCTURAL_BREAK`
- `VOLATILITY_DAMAGE`
- `FAILED`

These are theoretical states.

They must not become runtime logic merely because they sound reasonable.

Every transition requires:

1. causal observable inputs,
2. frozen semantics,
3. isolated evidence,
4. cross-period robustness,
5. no outcome-selected thresholds.

---

## 6. Future adaptive inputs

Potential future adaptive inputs include:

- realized / causal volatility,
- structural progress,
- favorable excursion,
- adverse excursion,
- holding age,
- time since last progress,
- trend persistence,
- relative momentum,
- market state,
- portfolio occupancy,
- capital scarcity / pressure,
- native exit proximity,
- replacement-opportunity context if causally available.

These are **research candidates**, not automatically valid features.

Any future feature must answer:

> “What causal mechanism does this variable represent, and does it add information beyond already-proven components?”

---

## 7. What a deeper post-progress protector may look like

The final B-family logic should not necessarily remain a static `3 × ATR` distance.

A future architecture may conceptually do:

```text
if Memory has not been proven:
    post-progress protection is inactive

if Memory is proven:
    measure progress quality
    measure peak-to-current giveback
    measure volatility
    measure trend persistence
    measure time since new progress

    if progress remains healthy:
        allow sufficient room

    if progress stalls:
        increase caution

    if deterioration strengthens:
        tighten protection

    if structural failure is independently confirmed:
        allow a separate structural exit mechanism to act
```

This is the intended direction of intelligence.

The exact formulas must be earned by evidence rather than written from intuition.

---

## 8. What a deeper pre-progress engine may look like

The primitive C asks only whether a fixed confirmation deadline expired.

A future pre-progress engine may reason about:

```text
Progress evidence
+ structural confirmation
+ relative momentum
+ trend persistence
- adverse excursion
- elapsed-time cost
```

The eventual state may be richer than a binary deadline:

```text
UNCONFIRMED
EARLY_PROGRESS
CONFIRMED
STALLED
FAILED
```

But no weighted `ProgressScore`, threshold, or state transition should be introduced after seeing outcomes unless it is separately preregistered and causally justified.

---

## 9. Structural logic may also deepen

Primitive A uses a clean structural-break test.

A future structural layer may distinguish:

- temporary wick/noise,
- close-confirmed structural break,
- false break,
- range failure,
- trend exhaustion,
- post-peak collapse,
- volatility shock combined with structure loss.

Again: these are architecture concepts, not permission to add filters now.

---

## 10. Portfolio context is a separate layer

A trade-level exit can be locally good but portfolio-level bad.

Example:

```text
Early exit saves: +300
Freed slot admits replacement trade: -700
Total portfolio effect: -400
```

Therefore AKAH must keep two questions separate:

1. **Was the exit decision itself good for the fixed trade?**
2. **What did freeing capital/slots do to the executable portfolio path?**

This is why the research program separates:

- `DirectEffect`
- `PortfolioPathResidual` / full portfolio effect

A future intelligent exit brain may eventually care about capital pressure, but portfolio feedback must not be added merely because path effects exist.

---

## 11. Conceptual exit utility

A mature arbiter may eventually reason in terms similar to:

```text
Exit Utility
    = value of avoiding further downside
    + value of preserving realized progress
    + value of freeing scarce capital
    - expected value of continuing to hold
    - cost/slippage of exit
    - cost of replacing the position badly
```

This is **not a calibrated equation** and must never be implemented as written.

It is a conceptual checklist showing why final exit intelligence is broader than a price threshold.

---

## 12. Future Exit Arbiter

The intended final architecture is not independent rules firing blindly.

It is closer to:

```text
lifecycle_state = evaluate_trade_phase()

pre_progress_evidence = evaluate_confirmation_state()
post_progress_evidence = evaluate_progress_retention()
structural_evidence = evaluate_structure()
volatility_evidence = evaluate_volatility_adjusted_damage()

portfolio_context = evaluate_capital_context_if_proven_and_authorized()

decision = exit_arbiter(
    lifecycle_state,
    pre_progress_evidence,
    post_progress_evidence,
    structural_evidence,
    volatility_evidence,
    portfolio_context,
    native_safety
)
```

The arbiter itself must remain simple until component interactions are measured.

No ensemble should be created simply because multiple components individually look useful.

---

## 13. Research ladder

The project should advance through these layers in order.

### Layer 1 — Primitive isolation

Test simple mechanisms independently.

Current examples:

- C: pre-progress non-confirmation.
- A: structural break.
- B: post-progress ATR protection.

Goal:

Determine whether each mechanism adds real information over native exits.

---

### Layer 2 — Causal proof

For every candidate separate:

- fixed-entry direct exit effect,
- full executable portfolio effect,
- portfolio-path residual,
- redundancy with native exits,
- intervention opportunity.

A candidate is not considered understood merely because total PnL improved.

---

### Layer 3 — Overlap and redundancy

Only after individual evidence exists, ask:

- Do A and B exit the same trades?
- Does B usually act before A?
- Does C remove trades that A would later remove anyway?
- Is one component redundant once another exists?

Do not combine components before this analysis.

---

### Layer 4 — Lifecycle state machine

Once independent mechanisms are established, organize them around trade phases:

- before progress,
- after progress,
- healthy continuation,
- stall,
- deterioration,
- failure.

The state machine should explain **why** a component is eligible to act.

---

### Layer 5 — Adaptive logic

Only then test whether proven components should adapt to causal variables such as:

- volatility,
- progress magnitude,
- trend strength,
- time since progress,
- market state.

No automatic grid search merely to improve historical performance.

---

### Layer 6 — Portfolio context

After trade-level intelligence is understood, test capital and slot effects separately.

Questions include:

- Is capital actually scarce?
- Does early exit systematically admit better or worse replacements?
- Is portfolio pressure informative enough to justify modifying exit behavior?

Do not add feedback loops before these questions are answered.

---

### Layer 7 — Exit Arbiter

Only after the above layers are evidenced should AKAH combine mechanisms under a final decision authority.

The arbiter should resolve:

- simultaneous signals,
- native safety precedence,
- conflicting lifecycle evidence,
- whether to hold or exit,
- later, whether any authorized dynamic protection is justified.

---

### Layer 8 — Prospective / unused-period validation

A sophisticated architecture is not accepted because it survived repeated historical iteration.

Once architecture development stabilizes, it requires genuinely unused or prospective evidence under a frozen protocol.

---

## 14. Anti-overfitting laws

The following principles are architectural, not optional:

- Do not create a different best rule for each year.
- Do not use year identity as runtime logic.
- Do not use pair identity as a runtime whitelist/blacklist.
- Do not select thresholds after seeing the target outcome and call them validation.
- Do not mix direct exit quality with downstream portfolio-path effects.
- Do not interpret lower holding time as success by itself.
- Do not call a PnL/MDD trade-off a win without a preregistered product/risk objective.
- Do not add a new detector merely to repair the latest failed backtest.
- Do not hide missing data as `no signal`.
- Do not use post-exit/future state to justify earlier decisions.
- Do not let implementation sophistication substitute for causal evidence.

---

## 15. What A/B/C can and cannot prove

If A/B/C work, they may establish that particular mechanisms have incremental value.

They cannot by themselves prove:

- that their current numeric parameters are optimal,
- that the final system should use fixed parameters,
- that combining them will improve results,
- that market-state switching is useful,
- that a portfolio-pressure loop is useful,
- that a complex arbiter is already justified,
- that historical robustness equals future profitability.

If they fail, that rejects the frozen versions under AKAH’s test contract.

It does not prove the underlying Donchian, ATR, or time-to-confirmation families are universally useless.

---

## 16. Definition of “intelligent” for AKAH

An intelligent exit brain is **not** one with the largest number of indicators or branches.

For AKAH, intelligence means:

- recognizing the trade’s causal lifecycle state,
- remembering relevant progress without future leakage,
- distinguishing normal noise from deterioration,
- changing behavior only when causal evidence justifies adaptation,
- preserving mandatory safety,
- understanding trade-level and portfolio-level effects separately,
- remaining interpretable enough to attribute failures,
- generalizing across periods without using period identity.

This definition should be used whenever the project is tempted to equate complexity with intelligence.

---

## 17. If the research gets lost: return to this compass

When the project becomes scattered, ask these questions in order:

1. **What mechanism are we testing?**
2. **Is it pre-progress, post-progress, structural, volatility, or portfolio-level?**
3. **Has this primitive been isolated from the others?**
4. **Do we know its DirectEffect separately from portfolio-path effects?**
5. **Is it actually non-redundant with native exits?**
6. **Has it behaved consistently enough across periods to deserve another layer?**
7. **Are we adding complexity because evidence demands it, or because the last result disappointed us?**
8. **Are all decision inputs causally available at decision time?**
9. **Are we still pursuing the North Star: adaptive lifecycle-aware exit intelligence?**

Canonical recovery sequence:

```text
PRIMITIVE ISOLATION
        ↓
CAUSAL PROOF
        ↓
OVERLAP / REDUNDANCY
        ↓
LIFECYCLE STATE MACHINE
        ↓
ADAPTIVE LOGIC
        ↓
PORTFOLIO CONTEXT
        ↓
EXIT ARBITER
        ↓
UNUSED / PROSPECTIVE VALIDATION
```

If a proposed task jumps several levels without evidence, stop and justify the jump before execution.

---

## 18. Relationship to the expert A/B/C protocol

The expert’s frozen A/B/C execution contract controls the exact first-round experiments.

This doctrine explains **why** those experiments exist and how they fit the long-term architecture.

Therefore:

- the experiment protocol governs exact implementation semantics;
- this doctrine governs architectural intent;
- neither should be silently rewritten based on backtest results.

---

## 19. Permanent project reminder

> AKAH Bot should not become a pile of increasingly complicated exits.

It should become a layered, causal, lifecycle-aware decision system in which every added component has a demonstrated reason to exist.

The purpose of simple early experiments is to make the final intelligence **more trustworthy**, not permanently simple.
