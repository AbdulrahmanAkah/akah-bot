# AKAH BOT — Independent Decision Ledger Authority Protocol Freeze V1

Status: PASS_INDEPENDENT_DECISION_LEDGER_AUTHORITY_PROTOCOL_FROZEN

Grain: ONE_LIFECYCLE_X_ONE_LEGAL_4H_DECISION_CHECKPOINT
Primary key: (lifecycle_id, decision_time_utc)
Y_t=(NetCash(HOLD one legal 4h step then pi0)-NetCash(EXIT now))/CurrentNotional

Semantics only; no rows materialized. Target/future fields are forbidden from runtime state. All materialization sources require exact authority and SHA lineage. M1/M2 are forbidden until ledger certification.

Next: ABC_LIFECYCLE_STATE_MACHINE_INDEPENDENT_DECISION_LEDGER_AUTHORITY_PROTOCOL_FREEZE_HUMAN_REVIEW_V1
