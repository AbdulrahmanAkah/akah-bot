# AKAH BOT — Decision-Value Feasibility Certificate V1

Status: PASS_DECISION_VALUE_FEASIBILITY_CERTIFICATE_COMPLETE

Disposition: NEEDS_DERIVED_AUTHORITY_BINDING

Reason:
A row-level decision-value core appears present, but explicit baseline-action or notional/cashflow semantics are not sufficiently bound by header-level authority for a canonical DirectGain ledger.

## Bound endpoint

Y_t = [NetCash(HOLD one legal step then pi0) - NetCash(EXIT now)] / CurrentNotional

This package does not train a model and does not claim economic edge.

## Old inference result

validation_fpr=None
validation_upper95=None
linear_power=None
interaction_power=None

These remain diagnostics for the old MSE proxy only.

## Existing derived authority

Authority scope: GIT_TRACKED_FILES_ONLY
Pre-existing untracked used: False
Tracked paths considered: 7657
Scanned files: 3509
Forbidden 2024/2025/raw-like paths skipped: 17
Exact decision-value core candidates: 1
Policy cash-ready candidates: 0

## Next gate

Human review is required before any M1/M2 pilot, D2 expansion, derived export, or policy execution.

Next bottleneck:
ABC_LIFECYCLE_STATE_MACHINE_DECISION_VALUE_FEASIBILITY_CERTIFICATE_HUMAN_REVIEW_V1
