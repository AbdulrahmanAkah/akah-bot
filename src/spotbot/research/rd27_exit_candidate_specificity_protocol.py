"""Frozen non-economic protocol and pure schema/arithmetic helpers only.

No loader, replay, empirical runner, policy mutation, or exit authority. Calling
these helpers on synthetic fixtures does not establish empirical selectivity.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass, fields
from typing import Any, Final

import pandas as pd

PROTOCOL_ID: Final = (
    "CAUSAL_EXIT_BRAIN_SHADOW_EXIT_CANDIDATE_BEHAVIORAL_SPECIFICITY_PROTOCOL_V1"
)
CANDIDATE_FORMULA: Final = "MEMORY_SEEN_AND_NEWLY_LATCHED_STRICTLY_LATER_TRIGGER"
MEMORY_FORMULA: Final = "COMPLETED_4H_CLOSE_BREAKS_PRIOR_POST_ENTRY_STRUCTURAL_HIGH"
TRIGGER_FORMULA: Final = "CURRENT_COMPLETED_4H_CLOSE_BELOW_PREVIOUS_COMPLETED_4H_LOW"
CONTROL_PATH: Final = "reports/research/ams-rd04-d5c1-labelled-pit-control-trades-v1.csv"
CONTROL_SHA256: Final = "782CEA4D8037E6D2C72FBE7B37FF69F10E66DC728396E6B4B58C28559BEEB225"
CONTROL_IDENTITY_COUNT: Final = 153
SAFE_CONTROL_FIELDS: Final = (
    "candidate_id", "canonical_symbol", "entry_price", "entry_time", "fold_id",
    "portfolio_mode", "position_id", "previous_position_id", "quantity", "symbol",
    "trade_id", "universe_mode",
)
FORBIDDEN_FIELDS: Final = (
    "exit_price", "exit_reason", "exit_time", "gross_pnl", "net_pnl", "pnl",
    "holding_hours", "holding_duration", "future_holding_duration", "mfe", "mae",
    "return_fraction", "alignment_tier", "all_categories", "event_association",
    "event_count", "event_ids", "natural_reselection_sequence", "primary_categories",
    "timing_labels",
)
REGIMES: Final = ("RISK_ON", "TRANSITION", "RISK_OFF")


class SpecificityProtocolError(ValueError):
    """A schema, identity, causal, or denominator contract failed closed."""


@dataclass(frozen=True, init=False)
class ProtocolConfig:
    protocol_id: str = PROTOCOL_ID
    candidate_formula: str = CANDIDATE_FORMULA
    memory_formula: str = MEMORY_FORMULA
    trigger_formula: str = TRIGGER_FORMULA
    parameter_count: int = 0
    empirical_execution: bool = False
    outcome_fields_allowed: bool = False
    economic_metrics_allowed: bool = False
    threshold_optimization_allowed: bool = False
    actual_exit_authority: bool = False
    timing_descriptive_only: bool = True
    regime_descriptive_only: bool = True
    symbol_concentration_descriptive_only: bool = True
    trade_parity_required: bool = True
    selectivity_status: str = "SELECTIVITY_NOT_YET_EXECUTED"


def validate_control_projection_fields(names: Iterable[str]) -> tuple[str, ...]:
    """Validate a projection BEFORE loading values; deny unknown names as well.

    This is deliberately not a function that loads a whole row then drops PnL.
    The later authorized loader must never materialize prohibited columns.
    """
    names = tuple(names)
    if len(set(names)) != len(names) or any(n not in SAFE_CONTROL_FIELDS for n in names):
        raise SpecificityProtocolError("forbidden, unknown or duplicate control field")
    return tuple(sorted(names))


def _utc(value: pd.Timestamp) -> pd.Timestamp:
    if not isinstance(value, pd.Timestamp) or pd.isna(value):
        raise SpecificityProtocolError("explicit non-NaT causal timestamp required")
    return value.tz_localize("UTC") if value.tzinfo is None else value.tz_convert("UTC")


@dataclass(frozen=True)
class CausalRegime:
    name: str
    available_at: pd.Timestamp

    def __post_init__(self) -> None:
        if self.name not in REGIMES:
            raise SpecificityProtocolError("unrecognized regime; use None for unavailable")
        object.__setattr__(self, "available_at", _utc(self.available_at))


@dataclass(frozen=True)
class LifecycleObservation:
    """Eligible-lifecycle diagnostic projection, never a historical trade row.

    observed_through is the last causal evaluation boundary from the authorized
    observation ledger, not imported eventual exit_time or holding duration.
    Eligibility and exposure must already be frozen without candidate/outcome use.
    """

    lifecycle_id: str
    trade_id: str
    symbol: str
    entry_time: pd.Timestamp
    observed_through: pd.Timestamp
    first_memory_time: pd.Timestamp | None = None
    raw_trigger_times: tuple[pd.Timestamp, ...] = ()
    latched_trigger_time: pd.Timestamp | None = None
    candidate_times: tuple[pd.Timestamp, ...] = ()
    memory_episodes_at_candidate: int | None = None
    causal_snapshot_evidence_verified: bool = False
    entry_regime: CausalRegime | None = None
    memory_regime: CausalRegime | None = None
    trigger_regime: CausalRegime | None = None

    def __post_init__(self) -> None:
        for value in (self.lifecycle_id, self.trade_id, self.symbol):
            if not isinstance(value, str) or not value.strip():
                raise SpecificityProtocolError("exact lifecycle/trade/symbol identity required")
        for name in ("entry_time", "observed_through", "first_memory_time", "latched_trigger_time"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, _utc(value))
        if self.entry_time is None or self.observed_through is None:
            raise SpecificityProtocolError("causal observation interval required")
        for name in ("raw_trigger_times", "candidate_times"):
            if type(getattr(self, name)) is not tuple:
                raise SpecificityProtocolError("immutable timestamp tuple required")
            values = tuple(_utc(t) for t in getattr(self, name))
            # Raw transport repetitions deduplicate; multiple candidate emissions
            # are an invariant failure, even if their timestamps are identical.
            object.__setattr__(self, name, tuple(sorted(set(values))) if name == "raw_trigger_times"
                               else tuple(sorted(values)))
        if type(self.causal_snapshot_evidence_verified) is not bool:
            raise SpecificityProtocolError("snapshot evidence flag must be boolean")
        count = self.memory_episodes_at_candidate
        if count is not None and (type(count) is not int or count < 1):
            raise SpecificityProtocolError("candidate episode count must be a positive integer")
        for context in (self.entry_regime, self.memory_regime, self.trigger_regime):
            if context is not None and not isinstance(context, CausalRegime):
                raise SpecificityProtocolError("typed causal regime evidence required")


@dataclass(frozen=True)
class StructuralInvariantResult:
    passed: bool
    violations: tuple[str, ...]


def inspect_invariants(row: LifecycleObservation) -> StructuralInvariantResult:
    failures = []
    memory, latch = row.first_memory_time, row.latched_trigger_time
    if row.entry_time > row.observed_through:
        failures.append("INVALID_CAUSAL_OBSERVATION_INTERVAL")
    if not row.causal_snapshot_evidence_verified:
        failures.append("CAUSAL_SNAPSHOT_UNAVAILABLE_OR_UNVERIFIED")
    if len(row.candidate_times) > 1:
        failures.append("MORE_THAN_ONE_CANDIDATE_PER_LIFECYCLE")
    events = row.raw_trigger_times + row.candidate_times
    events += tuple(t for t in (memory, latch) if t is not None)
    if any(not row.entry_time <= t <= row.observed_through for t in events):
        failures.append("EVENT_OUTSIDE_CAUSAL_LIFECYCLE")
    if latch is not None and (memory is None or latch <= memory):
        failures.append("LATCH_WITHOUT_STRICTLY_PRIOR_MEMORY")
    if row.candidate_times != (() if latch is None else (latch,)):
        failures.append("CANDIDATE_NOT_EXACT_NEW_LATCH_EVENT")
    eligible_raw = tuple(t for t in row.raw_trigger_times if memory is not None and t > memory)
    if latch != (eligible_raw[0] if eligible_raw else None):
        failures.append("LATCH_NOT_FIRST_VALID_RAW_TRIGGER")
    if bool(row.candidate_times) != (row.memory_episodes_at_candidate is not None):
        failures.append("CANDIDATE_EPISODE_EVIDENCE_MISMATCH")
    for context, timestamp in ((row.entry_regime, row.entry_time),
                               (row.memory_regime, memory), (row.trigger_regime, latch)):
        if context is not None and (timestamp is None or context.available_at > timestamp):
            failures.append("NONCAUSAL_CONTEXT")
    return StructuralInvariantResult(not failures, tuple(sorted(set(failures))))


def lifecycle_from_mapping(values: Mapping[str, Any]) -> LifecycleObservation:
    """Strict diagnostic schema: never silently drop an outcome or unknown field."""
    allowed = {f.name for f in fields(LifecycleObservation)}
    if not isinstance(values, Mapping) or set(values) - allowed:
        raise SpecificityProtocolError("forbidden or unknown lifecycle diagnostic field")
    try:
        row = LifecycleObservation(**values)
    except TypeError as exc:
        raise SpecificityProtocolError("incomplete lifecycle diagnostic schema") from exc
    result = inspect_invariants(row)
    if not result.passed:
        raise SpecificityProtocolError(";".join(result.violations))
    return row


def validate_unique_lifecycles(rows: Iterable[LifecycleObservation]) -> None:
    ids, trades = set(), set()
    for row in rows:
        if not isinstance(row, LifecycleObservation):
            raise SpecificityProtocolError("typed lifecycle diagnostics required")
        if row.lifecycle_id in ids or row.trade_id in trades:
            raise SpecificityProtocolError("duplicated lifecycle or ambiguous trade identity")
        ids.add(row.lifecycle_id)
        trades.add(row.trade_id)
        result = inspect_invariants(row)
        if not result.passed:
            raise SpecificityProtocolError(";".join(result.violations))


def normalize_lifecycle_transport(
    rows: Iterable[LifecycleObservation],
) -> tuple[LifecycleObservation, ...]:
    """Identical transport copies deduplicate before strict denominator validation."""
    unique = {}
    for row in rows:
        if not isinstance(row, LifecycleObservation):
            raise SpecificityProtocolError("typed lifecycle diagnostics required")
        if row.lifecycle_id in unique and unique[row.lifecycle_id] != row:
            raise SpecificityProtocolError("conflicting duplicate lifecycle identity")
        unique[row.lifecycle_id] = row
    result = tuple(unique[key] for key in sorted(unique))
    validate_unique_lifecycles(result)
    return result


@dataclass(frozen=True)
class CohortCounters:
    eligible: int
    memory: int
    raw_trigger: int
    latched_trigger: int
    candidate: int
    trigger_before_memory: int
    eligible_controls: int
    control_candidates: int

    def __post_init__(self) -> None:
        if any(type(v) is not int or v < 0 for v in asdict(self).values()):
            raise SpecificityProtocolError("nonnegative integer counts required")
        if not (self.candidate == self.latched_trigger <= min(self.memory, self.raw_trigger)
                and max(self.memory, self.raw_trigger, self.eligible_controls) <= self.eligible
                and self.trigger_before_memory <= self.raw_trigger
                and self.control_candidates <= min(self.eligible_controls, self.candidate)
                and self.candidate - self.control_candidates
                <= self.eligible - self.eligible_controls
                and self.eligible_controls <= CONTROL_IDENTITY_COUNT):
            raise SpecificityProtocolError("cohort subset/denominator invariant failed")


@dataclass(frozen=True)
class Rate:
    numerator: int
    denominator: int
    value: float | None
    status: str


def _rate(numerator: int, denominator: int) -> Rate:
    return Rate(numerator, denominator, numerator / denominator if denominator else None,
                "DEFINED" if denominator else "UNDEFINED_ZERO_DENOMINATOR")


@dataclass(frozen=True)
class SpecificityMetrics:
    memory_incidence: Rate
    raw_trigger_incidence: Rate
    latched_trigger_incidence: Rate
    candidate_incidence: Rate
    candidate_free_fraction: Rate
    conditional_candidate_incidence_after_memory: Rate
    trigger_before_memory_incidence: Rate
    control_candidate_incidence: Rate


def specificity_metrics(c: CohortCounters) -> SpecificityMetrics:
    """Pure arithmetic over independently validated counts; no adjudication cutoff."""
    return SpecificityMetrics(
        _rate(c.memory, c.eligible), _rate(c.raw_trigger, c.eligible),
        _rate(c.latched_trigger, c.eligible), _rate(c.candidate, c.eligible),
        _rate(c.eligible - c.candidate, c.eligible), _rate(c.candidate, c.memory),
        _rate(c.trigger_before_memory, c.eligible),
        _rate(c.control_candidates, c.eligible_controls),
    )


@dataclass(frozen=True)
class DescriptiveDistribution:
    count: int
    minimum: float | None
    q25: float | None
    median: float | None
    q75: float | None
    p90: float | None
    maximum: float | None


def descriptive_distribution(values: Iterable[float]) -> DescriptiveDistribution:
    values = tuple(values)
    if any(isinstance(v, bool) or not isinstance(v, (int, float))
           or not math.isfinite(v) or v < 0 for v in values):
        raise SpecificityProtocolError("finite nonnegative descriptive values required")
    ordered = sorted(values)
    if not ordered:
        return DescriptiveDistribution(0, None, None, None, None, None, None)

    def quantile(p: float) -> float:
        index = (len(ordered) - 1) * p
        lo, hi = math.floor(index), math.ceil(index)
        return float(ordered[lo] + (ordered[hi] - ordered[lo]) * (index - lo))

    return DescriptiveDistribution(len(ordered), float(ordered[0]), quantile(.25),
                                   quantile(.5), quantile(.75), quantile(.9), float(ordered[-1]))


@dataclass(frozen=True)
class CausalTiming:
    memory_to_trigger_hours: float | None
    entry_to_memory_hours: float | None
    entry_to_candidate_hours: float | None


def causal_timing(row: LifecycleObservation) -> CausalTiming:
    validate_unique_lifecycles((row,))
    memory, candidate = row.first_memory_time, row.latched_trigger_time
    hour = pd.Timedelta(hours=1)
    return CausalTiming(
        float((candidate - memory) / hour) if candidate is not None else None,
        float((memory - row.entry_time) / hour) if memory is not None else None,
        float((candidate - row.entry_time) / hour) if candidate is not None else None,
    )


def protocol_summary() -> dict[str, Any]:
    """Fresh deterministic JSON-compatible definitions, never empirical results."""
    return {
        **asdict(ProtocolConfig()),
        "cohorts": {
            "A": "All unique lifecycles in separately authorized window with unambiguous identity, "
                 "causal primitive coverage and at least one full post-entry completed "
                 "4H snapshot; "
                 "freeze eligibility before events and report first-bar/no-prior unavailability",
            "B": "A with first memory established",
            "C": "A with at least one raw trigger candidate",
            "D": "A with generic strictly-later trigger latch", "E": "A with one-shot candidate",
            "F": "A intersect immutable canonical control roster, joined exactly on trade_id",
        },
        "control_authority": {
            "path": CONTROL_PATH, "sha256": CONTROL_SHA256,
            "roster_identity_count": CONTROL_IDENTITY_COUNT, "join_identity": "trade_id",
            "membership": "ALL_PIT_TRADES_REPORTED_UNCHANGED; universe_mode=PIT_UNIVERSE "
                          "and portfolio_mode=CONTROL; no label/outcome/candidate selection",
            "not_a_false_positive_label": True,
            "eligible_denominator": "Measured |F|, not automatically 153; "
                                    "report all 153 identities "
                                    "as eligible, out-of-window or predeclared coverage exclusion",
            "binding": "Charter latest_async_ready_state_control_denominator_authority_audit; "
                       "latest_async_ready_state_control_identity_semantics_authority_audit; "
                       "latest_async_ready_state_control_hourly_evidence_authority_gap_closure_v2",
        },
        "primary_metrics": {
            "memory_incidence": "|B| / |A|", "raw_trigger_incidence": "|C| / |A|",
            "latched_trigger_incidence": "|D| / |A|", "candidate_incidence": "|E| / |A|",
            "candidate_free_fraction": "(|A| - |E|) / |A| = 1 - candidate_incidence when defined",
            "conditional_candidate_incidence_after_memory": "|E| / |B|",
            "trigger_before_memory_incidence": "|lifecycles in A with raw trigger before first "
                                               "memory, including never-memory lifecycles| / |A|",
            "control_candidate_incidence": "|E intersect F| / |F|",
        },
        "zero_denominator": "value=null, status=UNDEFINED_ZERO_DENOMINATOR; not zero or perfect",
        "timing_distributions": {
            "memory_to_trigger": "candidate time - first memory time, E only",
            "entry_to_memory": "first memory time - entry time, B only",
            "entry_to_candidate": "candidate time - entry time, E only",
            "unit": "fractional UTC hours; no rounding before calculation",
            "statistics": ["count", "minimum", "q25", "median", "q75", "p90", "maximum"],
            "quantiles": "linear interpolation at (n-1)*p; empty count=0 and all statistics null",
            "eligibility_dependency": False,
        },
        "episode_distributions": {
            "memory_episodes_at_candidate": "generic episode count captured in candidate, E only",
            "raw_candidates_before_latch": "count of distinct raw trigger timestamps < latch, D",
            "triggers_before_memory": "raw times < first memory; all raw if never memory, A",
            "same_time_rejections": "raw time == first memory, separate from before-memory, A",
            "repeated_deterioration_after_candidate": "raw times > candidate time, E",
            "one_shot": "candidate events per lifecycle must be 0 or 1; D and E must coincide",
        },
        "regime_context": {
            "source": "separately SHA-bound causal RD27 state-frame manifest; "
                      "availability <= event",
            "labels": list(REGIMES) + ["UNAVAILABLE"],
            "counts": "candidate counts by regime at first memory and at latched trigger",
            "incidence": "by regime at entry: E in entry group / A in same entry group; "
                         "conditional memory-group incidence: E / B with same first-memory regime",
            "invalid_denominator": "No candidate-time regime incidence using candidate-only counts",
            "unavailable": "retain explicit unknown category and report coverage; never backfill",
            "eligibility_dependency": False,
        },
        "symbol_concentration": {
            "counts": "|E_symbol| and |A_symbol|; incidence = |E_symbol| / |A_symbol|",
            "share": "|E_symbol| / |E|; report all symbols, descending candidate count then symbol",
            "top_shares": "cumulative share for every rank k, including ties with lexical order; "
                          "no selected top-k cutoff, eligibility gate or economic ranking",
            "eligibility_dependency": False,
        },
        "allowed_control_fields": list(SAFE_CONTROL_FIELDS),
        "allowed_observable_schema": [
            "symbol", "source_exchange", "source_symbol", "bar_open_time", "bar_close_time",
            "open", "high", "low", "close", "volume",
        ],
        "allowed_diagnostic_schema": [f.name for f in fields(LifecycleObservation)],
        "observable_contract": "4H completed snapshots only: bar_open_time >= lifecycle entry "
                               "and bar_close_time <= decision boundary; exclude entry-spanning "
                               "bars. Preserve existing UTC, identity and duplicate semantics.",
        "forbidden_fields": list(FORBIDDEN_FIELDS),
        "field_firewall": "Exact allowlists; unknown names denied. Project before values are read. "
                          "No outcome/posthoc field may define cohort, state, "
                          "censoring or judgment.",
        "structural_fail_conditions": [
            "candidate without memory or valid generic latch", "candidate <= first memory",
            "candidate timestamp not exactly first latch", "more than one candidate per lifecycle",
            "event outside causal lifecycle or study boundary",
            "ambiguous control/position identity",
            "outcome-field dependency", "causal snapshot unavailable for attempted eligible row",
            "conflicting duplicate identity", "equivalent input ordering changes results",
            "native parity failure", "unaccounted roster identities",
            "post-event eligibility change",
            "noncausal context", "missing required execution evidence",
        ],
        "adjudication": {
            "initial": "SELECTIVITY_NOT_YET_EXECUTED",
            "structural_failure": "FAIL_CLOSED; no selectivity or actionability conclusion",
            "structurally_valid_nonempty": "SELECTIVITY_OBSERVABLE; raw measurements only; "
                                          "CONTROL_DISCRIMINATION_UNRESOLVED until governed review",
            "empty": "INSUFFICIENT_ELIGIBLE_DENOMINATOR; retain null metrics",
            "prohibited_labels": "No NEAR_UNIVERSAL or NONTRIVIALLY_SELECTIVE cutoff is authorized",
            "pass_meaning": "Protocol/software conformance only, not sufficient selectivity, "
                            "profitability, deployment or permission for an execution study",
        },
        "later_execution_requirements": [
            "Separate admission and input manifest: exact hashes, years, window, "
            "lifecycle identity "
            "mapping, completed primitive coverage, and frozen observation/censoring convention",
            "Reverify canonical roster SHA and 153 unique trade_id values "
            "using permitted projection; "
            "do not assume this protocol read or certified current CSV bytes",
            "Register all window-eligible admissions before candidate calculation, including "
            "no-memory/no-trigger lifecycles; publish predeclared exclusions "
            "without event filtering",
            "Master cohort and control complement must be declared independently; if A=F, report "
            "that equality and do not claim target/control discrimination or invent new controls",
            "Observation ends at the last authorized causal boundary, limited by online native "
            "lifecycle-close notification if applicable; never import historical exit_time, "
            "exit_reason or holding duration to truncate exposure. "
            "No candidate-dependent censoring",
            "Retain exposure/coverage ledger; partial coverage cannot be silently counted as a "
            "candidate-free lifecycle. Coverage loss after eligibility fails closed",
            "Run existing adapter/memory/trigger/candidate unchanged, fully post-entry completed "
            "4H bars only; no external substitute predicate events or temporal backfill",
            "Prove native parity via isolated synthetic regression/opaque parity certificate, "
            "not by importing economic trade columns into this protocol",
            "Bind generic latch and snapshot evidence, one-shot state, exact trade-to-lifecycle "
            "mapping, causal regime availability and complete per-lifecycle diagnostics",
            "Prove identical runs, shuffled equivalent rows, exact duplicate deduplication, "
            "conflict rejection, unique post-normalization IDs and position isolation",
            "No implicit protected-year, real-row, economic, threshold, formula-change or exit "
            "authorization follows from naming the next execution task",
        ],
    }
