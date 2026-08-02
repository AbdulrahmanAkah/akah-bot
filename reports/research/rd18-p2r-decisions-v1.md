# RD18-P2R decision

Decision: `RD18_P2R_RESTRICTED_UNIVERSE_STRUCTURAL_RISK_UNACCEPTABLE`

Next stage: `RD18_BLOCKED_PENDING_UNIVERSE_RISK_REDESIGN`

The P1R restricted universe remains valid for restricted research use only,
but the frozen omission-risk rules classify its structural provenance risk as
SEVERE. The evidence-strong sensitivity does not reproduce the final panel's
Top-6 membership at the required 50% boundary (0.4984025559), and its mean
Top-10 Jaccard is 0.7604971174. Therefore a single restricted universe is not
structurally acceptable and this stage does not authorize a dual-universe
strategy replay either; the severe branch requires explicit redesign before
strategy work.

Authorization flags:

- `single_universe_research_authorized = false`
- `dual_universe_required = false` (structural block takes precedence)
- `strategy_candidate_generation_authorized = false`
- `production_authorized = false`

No new market-data request, archive search, return calculation, trading
simulation, candidate generation, or optimization occurred. Prior RD17 and
RD18 decisions and hashes are unchanged.
