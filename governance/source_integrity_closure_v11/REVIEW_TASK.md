# Independent V11 repair review

Review actual source/spec and synthetic regressions. This packet is NOT a blind
market reserve and must not be certified as one. Preserve your actual reviewer
identity; no human attestation is implied. Do not access market data or PnL.

1. Verify EXPORT_INPUT_MANIFEST SHA256s. Inspect DEPENDENCY_LOCK: arch==8.0.0,
   original estimator, data/core source present. Missing offline dependencies
   are an environment blocker, not permission to substitute another estimator.
2. In a disposable environment with these dependencies, run:

   `python -S -B scripts/research/integration_v11/isolated_tests.py --site-packages <absolute-site-packages>`

   It must load spotbot only from this packet and run all selected synthetic
   tests without editable source fallback, market rows or network access.
3. Reproduce V10 findings against V11: pre-bind mutable event/instruction,
   stop_floor 118->100, false->true PIT. Test dataclass replacements, source
   termination, parent death, wrong pair/clock/campaign and post-preview mutation.
   All must fail before fills. Verify native positive controls still execute.
4. Trace source -> producer -> seal -> bind -> preview -> actual kernel admission.
   Independently check stages preserve B0; stop derived from original LPS;
   all parent evidence and router context remain live through actual fill.
5. Do not treat green old regression tests as rejection of the review findings.
   Confirm new adversarial tests reach intended checks, not unrelated fixture
   exceptions. Classify further findings with path/line, reproduction and scope.
6. Return locked JSON: packet SHA256, reviewer identity, dependency/isolation
   evidence, F1/F2/F3 verdicts, export verdict, regressions, remaining findings,
   and limitations. Economic conclusion MUST be NONE; reserve certification FALSE.

No replay, model refit, thresholds, production, Git mutation or network required.
