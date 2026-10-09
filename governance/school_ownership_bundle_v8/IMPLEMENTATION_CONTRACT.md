# Package 1: four explicit causal ownership contracts, V8

## Scope and certificate meaning

This is a prospective research implementation, not a production change or an
economic experiment. The user authorized explicit implementation choices. The
protocol was fixed before BEGIN. These choices do not retrospectively certify
the old six-school detectors. All emitted theses remain `funded_ready=false`.

`PACKAGE1_TECHNICAL_CONTRACT_PASS` means the four declared profiles have concrete
algorithms, ownership and rejection paths, and passed synthetic tests. It does
NOT mean exhaustive school doctrine is uniquely defined, Gate 2 passed, actual
market producers were rebound, all eleven original gaps closed, or profit is
proven. The original V7 adjudication is retained unchanged. Unsupported wave
forms and unbound evidence fail explicitly; they are not converted to trades.

All constants below are source-defined, inherited frozen design choices, or
new explicitly labeled prospective adaptations. None was selected from PnL.

## Shared causal envelope

- Decision clock: UTC, at or before 2023-12-31; synthetic guards reject 2024/25.
- OHLC: completed canonical UTC-aligned 1H/4H/1D bars only.
- `Point.observed_at` is the pivot bar **close**, not its open. Two completed
  right bars must exist before `available_at`. An old open-stamped pivot must
  be converted by an adapter before using this API; never reinterpret it silently.
- Named source SHA, immutable structure ID, explicit availability and optional
  expiry accompany supplied evidence. This checks the contract, not the truth
  of an arbitrary producer's claim. Producer certification is a separate gate.
- Signals never execute inside their creating bar. `SchoolThesis.executable_at`
  requires the following hourly open, which can share the preceding close's
  timestamp. A late entry must be re-evaluated, not replay an old intent.
- Structure/owner/mode cannot change after entry. Invalidated IDs cannot be
  resurrected. Short geometry is diagnostic, never executable Spot short.
- `TREND_CHECKPOINTS` are real owner-sourced obstacles, not forced take profit.
  `FINITE_REACTION` objectives must remain ahead of the actual fill. Neither
  asserts a realization probability or expected dollar profit.

## Harmonic

API: `project -> HarmonicContract.on_close -> thesis`.

The generated `family_matrix.json` contains all nine families. The code measures
regular XABC, 5-0 XABC failed-impulse geometry, and Shark OXAB separately.
Shark OX retracement is measured **from X**; its last extreme wave must satisfy
the declared extension check. 5-0 includes the failed XA impulse and BC extension,
not just a 50% retracement anywhere. Bull/bear geometry is checked before ratios.

Defining public measurements are linked in `source_authority.json`. Public
Butterfly/Crab descriptions do not uniquely define every complementary variant.
The finite enumerations, common regular C band, projection tie rule, terminal
structural stops, and price-action confirmations are an **AKAH profile**, not
a falsely attributed universal Carney algorithm. No RSI/BAMM certification is
claimed. The source ambiguities are retained as provenance limitations, not
filled using economic outcomes.

Projection is frozen before D. Closest complementary level to the defining
projection is chosen deterministically before terminal observation. Convergence
uses inherited 0.25 projection-time ATR, never a later volatility value. Range
checks allow only floating-point roundoff; exact B measurements use the supplied
historical tick. A caller's tick is not certification of historical exchange rules.

| State | Required later event | Next state/action |
|---|---|---|
| PROJECTED | PRZ near edge visited and far edge actually traded; not a gap over zone | TERMINAL_COMPLETE |
| TERMINAL_COMPLETE | Later close beyond terminal bar high (long) / low (diagnostic short) | Type-I intent |
| TYPE_I_ACTIVE | Confirmed completion by execution owner | TYPE_I_COMPLETE |
| TYPE_I_COMPLETE | Later actual zone revisit, after Type-I completion | TYPE_II_RETEST |
| TYPE_II_RETEST | Later close beyond retest high/low | Type-II intent |
| Any live state | Standing stop touched / defining Gartley-X or Bat boundary violated | INVALIDATED |
| TYPE_II_ACTIVE | Confirmed execution completion | DONE |

Gartley X and local frozen Bat 1.13XA boundaries are retained. Other stops are
terminal extreme plus one tick outside the PRZ: **engineering invalidation**, not
an invented official family ratio-stop. Terminal traversal can span bars.

Inherited management: 50% initial quantity at .382 and remaining quantity at
.618 of the frozen reaction span; native V7 cost breakeven only from next bar.
Regular span A-terminal; 5-0 C-terminal; Shark B-terminal. Type-II must be a new
retest, not another fill of Type-I. `complete_type1` is an execution acknowledgment,
not a detector inference that the trade won. The V7 execution bridge itself is
unchanged; rebinding these new grammar IDs belongs to producer integration.

## Elliott

API: `Wave.validate -> ParentPrefix -> ResumeCount -> ElliottBook` per asset.

Supported finite syntax: impulse, zigzag, bounded regular/expanded flat,
contracting triangle, double-three and triple-three. Diagonals, running flats,
barrier/expanding triangles and unresolved/unobserved subdegrees are not
silently approximated. They remain diagnostic until a separately declared profile.

- 1H leaf forms use complete confirmed pivot geometry as the finite resolution.
  This is explicitly not proof of unseen sub-hour subdivision.
- 4H and 1D nodes require adjacent-degree child proofs for **every** completed
  parent leg, with exact time/price endpoints. Motive/corrective child grammar is
  checked (5-3-5-3-5 impulse, 5-3-5 zigzag, 3-3-5 flat, corrective triangle/combination).
- Impulse W2 origin, W4 overlap and W3-not-shortest rules are hard checks.
- W2 resumption requires a certified parent W1; W4 requires W1/W2/W3; post-ABC
  requires the completed motive parent. The correction occupies the named
  parent leg, not an unrelated sequence sharing a few recent pivots.
- Every nested corrective price must preserve the relevant parent boundary.
  The stop equals that boundary; an arbitrary wider stop is rejected.
- All valid interpretations remain in the book. A retained opposing
  interpretation vetoes a long. Identical claim owners aggregate count IDs,
  rather than selecting the latest/highest-degree bullish result.
- Entry requires a later close above the retained corrective highs. Count claims
  are consumed once. Child invalidation cascades to parent count tombstones.
- Source-known forward objectives are checkpoints, not proof of future peaks;
  count/owner structure governs management, with no new 168h limit or extension.

Degrees and flat bounds are declared engineering proxies, not unique Elliott
doctrine. This finite proof contract is stricter and narrower than discretionary
counting. Insufficient child proof returns an explicit diagnostic rejection.

## Wyckoff

API: `RangeCause -> Readiness/PNF -> WyckoffContract`.

Each range has a new immutable cause ID. A historical MARKUP parent can authorize
the **reaccumulation branch**, never contribute old columns, readiness, LPS or
range evidence. Reaccumulation does not demand a fabricated new selling climax.

P&F here is explicitly AKAH logarithmic percentage P&F, not the official fixed-box
arithmetic rule: 1% box and 3-box reversal inherited from the existing registry.
`box(price)=floor(log(price/range_low)/log(1.01))`. Only completed close bars in
complete source event segments count. Missing coverage, old-cause segments,
future bars, or a line not belonging to the current LPS fail closed.

`C = number of columns intersecting the frozen source LPS count line`

`minimum_checkpoint = range_low * 1.01 ** (3*C)`

The entire source segment from new range start to source test is counted without
partial outcome-selected columns. It is not a fitted price target. P&F is a
stop-look-listen checkpoint, never a mandatory TP. At least gross 3R is the
inherited design eligibility rule, not a profitability or cost-adjusted forecast.

Readiness uses actual supplied causal objects, not an `all=True` dictionary:
market eligible, RS > 1, same-range HL/HH, prior falling-high stride broken,
reduced test volume/spread, SOS with demand effort and positive result, later LPS
holding support with diminished supply. Confirmed falling highs precede the new
range; stride is extrapolated deterministically and must remain positive.

Accumulation branch source events: PS/SC/ST/downside-objective-met. Reaccumulation:
historical markup plus a new-range supply test. These are trusted source events
that the later producer adapter must substantiate; this library does not invent
a PS/SC detector. LPS entry exists only at its current completed checkpoint.

Spring stage requires a real below-support raid/reclaim, later higher-low supply
test, then later confirmation, with fresh accumulation context and horizontal
cause. Initial fraction is 50%; later current-cause SOS/LPS can authorize the
remaining 50% within the **same original campaign risk budget**. `lps_add` returns
an instruction, not a funded fill. It cannot reset risk or lower protection.
No-spring LPS and fresh reaccumulation LPS are separate full-entry branches;
mixing these with an existing spring campaign is rejected. Distribution/structure
owns eventual exit; no fixed take profit is introduced.

## Native ICT versus H2 HTF trend owner

API: `AuctionChain -> bind_entry -> OwnedCampaign`.

Raid must occur after a known sell-side level, followed by later MSS/FVG creation,
then later retracement. Same-bar creation/retracement and late stale triggers are
rejected. The producer must prove actual FVG/level formation separately.

| Profile | Pre-entry binding | Management owner | Exit |
|---|---|---|---|
| ICT session | Current complete 1H retracement and native session endpoint | ICT_SESSION / 1H finite | Raid stop, opposing target, native bearish MSS, NY16 |
| H2 HTF | Same causal trigger, prior 1D UP, prior protected 4H level, current completed 4H acceptance | H2_4H_STRUCTURE / 4H trend | Hard structural stop, failed 4H reclaim, confirmed 1D reversal |

H2 is an **AKAH hybrid**, not 'official ICT swing'. NY16/internal 1H bearish MSS
remain diagnostics for its 4H owner; they never disable native ICT's session exit.
Owner/mode are immutable from entry. A winning session position cannot migrate.

V6 protected HL->HH ratchet and two consecutive completed owner closes below the
soft protected level are reused. The hard stop never falls and gives one earned
structural level of breathing room. Hourly execution always sees the stop active
at that bar's **start**; a stop earned at its close applies only to later bars.
Pending exit is absorbing until an execution acknowledgment closes the campaign.
Hard stop output requires actual executable gap-price semantics; it does not
claim a fill at the stop when the market gaps. Shared execution owns prices/fees.

## Four-contract dispatcher integration boundary

New modules are research APIs with new grammar/owner IDs; original V6/V7 allowlists
are deliberately not expanded in this package. Do not impersonate Classical or
native ICT just to pass the old `Binding` checks. Package 2 must bind actual six
detectors/hybrid evidence and execution intents to these contracts, then run
changed-version independent reserve review and historical quantity checks.
No result from an old reserve certifies this version.

## Explicit unchanged/remaining gates

Independent reserve fidelity; historical tick/lot/minimum authority; actual
producer/router integration; shared opportunity value; live broad-market Dow
producer; meaningful-profit evidence; eventual governed economic qualification.
The generic profitable-trade floor remains unjustified. Do not manufacture
distant targets or promise that every trade will produce a large profit.
