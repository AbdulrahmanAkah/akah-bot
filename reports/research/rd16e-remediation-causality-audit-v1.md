# RD16-E Remediation Audit v1

## Interpretation rules

- Improvements are measured against each family’s frozen RD16-D baseline.
- Structural and fee-buffer gates use signal-time information only.
- Full-stack cooldown only removes later same-symbol entries; it never adds rejected trades.
- Outcome variables such as realized PnL, MFE, MAE, holding duration, and exit reason are not used for filtering.
- The 24% geometric monthly research objective remains unchanged.

## Next step

RD16-F must preregister a composite alpha architecture using only carry-forward components and must not tune against RD16-E outcomes.
