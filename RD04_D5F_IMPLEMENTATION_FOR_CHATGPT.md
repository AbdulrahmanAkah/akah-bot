# RD04-D5F implementation contract

RD04-D5F is a descriptive membership-exit path diagnostic registered by D4.
It receives no authority to change a universe, rank, entry, exit, weight, or
production behavior.  It does not run a portfolio counterfactual.

A causal membership exit is defined once: a symbol belongs to the frozen PIT
schedule at Monday 00:00 UTC in week *t-1* and is absent at Monday 00:00 UTC in
week *t*.  The event is known at the latter decision time.  A removed survivor
is such an event whose symbol belongs to the pre-existing D3 fixed-survivor
set; all other events are removed PIT entrants.

The predeclared descriptive horizons are 1, 2, 4, and 8 weeks.  The base price
is the registered four-hour open at the removal decision.  Each horizon return
uses the final four-hour close before the horizon endpoint.  Eight-week MFE and
MAE use the same complete post-decision path.  Missing bars and data ending
before a horizon remain missing; they are never treated as zero return.

The descriptive classification is fixed before execution.  A result is
`MATERIAL` only when removed-survivor Fixed post-exit contribution is positive,
at least ten percent of the recorded Fixed-minus-PIT gap, and the measurable
four-week positive-return share is at least fifty percent.  It confers no
treatment authorization.  Positive contribution below that condition is
`LIMITED`; otherwise it is `NOT_EVIDENT`.
