# V11 source integrity repair — frozen technical scope

This opt-in research adapter does not replace production or rewrite V4–V10.
Native price targets, school grammar, risk sizing and quantity rules are unchanged.

## F1: Wyckoff staged add

The add holds a typed `LpsAddProof`: actual completed LPS bar claim, original
stage-stop proof claim, actual first-fill receipt, checkpoint and cause/campaign
identities. The live graph binds the proof to these exact three parents.
`stop_floor = max(original_stage_stop, actual_lps_bar.low)` is recomputed before
binding and at actual admission. A caller cannot weaken OR tighten the scalar
to a different value. Existing kernel non-loosening rules still apply. Initial
campaign risk B0 is never reset by the add. All other native readiness/PNF/SOS,
market/RS and fill-receipt dependencies remain live requirements.

## F2: PIT eligibility

Public producer methods keep the historical keyword `pit_eligible`, but V11
requires a `Known[PitMembership]`, NOT a bool. Fields: pair, checkpoint,
eligible (strict bool), effective_from inclusive, effective_until exclusive.
The live source node must have SUPPLIED_SEMANTIC_PRODUCER origin and real source
parents, matching pair/structure and decision checkpoint, availability no later
than checkpoint and a valid effective interval. No membership inference from
OHLC and no default True. False is preserved through event/binding/kernel.
This typed snapshot does not certify that its underlying historical membership
source is correct. Historical semantic producer certification remains required.

## F3: emission integrity

Producer emissions use recursively immutable `FrozenMap`/tuples and frozen
contracts. SHA256 covers event (including opaque metadata bytes), full thesis,
staged flag, instruction, stop proof, membership/add proof and evidence IDs.
An `EmissionSeal` source node commits to payload, owner, source SHA and exact
parents. Its deterministic ID includes kind/structure/checkpoint/payload SHA.
Any pre-bind replacement or mutation is denied unless a producer explicitly
issues a new source-backed emission. The seal itself is not a runtime signal.

The pipeline verifies issuance first; the execution kernel verifies it again
at actual admission, with row, campaign, binding, objectives/mode/partial plan,
staging, add evidence and every required live source (including router context).
Prebatch preview remains isolated and does not substitute for final admission.
Source graphs are trusted source-authority objects, not a security sandbox
against arbitrary Python code modifying or replacing the authority registry.

Classical/H1 legacy events require `seal_legacy`; bare caller dictionaries are
not accepted by V11. This repairs integrity, not unproved pattern fidelity.
H3 verifies both parent seals and requires the same PIT snapshot, retaining
count ownership. Its tests certify composition, not a full historical detector.
Dow remains context-only. Actual mode remains unfunded pending reserve/source
certification; synthetic_fixture_execution is not a production authorization.

## Review export

Export includes fidelity Python source, data/core Python dependencies, selected
synthetic tests, exact installed dependency contract (`arch==8.0.0`), protocol
and this specification. No raw market files, economic outputs or hidden charts.
Python -S runner skips editable .pth hooks, checks file hashes and dependencies,
loads spotbot exclusively from export/src, disables network and runs tests.
Third-party wheels are not vendored: missing dependencies mean FAIL CLOSED,
not alternate estimator substitution. Synthetic tests may create synthetic
temporary CSV/parquet files; they never read historical market rows.

## Scope and outstanding claims

V10's unconditional R2 technical closure is superseded by F1/F3. Stop provenance
R1, feasibility R3 and explicitly restricted Elliott R4 remain unchanged, subject
to the original scope. The supplied independent V10 rejection remains evidence,
not overwritten. V11 requires a new independent code/spec review before claiming
independent acceptance. Fresh unused market reserve, historical semantic producer
recertification, historical exchange source coverage and economics are NOT
closed by these synthetic tests. No 2024/2025 access, model fit, threshold search,
market replay or production change is permitted in this repair mission.
