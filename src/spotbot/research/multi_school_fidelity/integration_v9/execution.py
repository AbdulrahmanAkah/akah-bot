"""Distinct V8 owners on the actual V5 risk/accounting kernel and V7 mechanics.

No legacy alias impersonation, production hook, raw reader or funding authority.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass

from ..campaign_execution_v7 import CampaignExecutionV7, PartialPlan
from ..ict_h2_contract_v8 import SESSION, TREND
from ..school_contract_common_v8 import DEGREES, SchoolThesis, clock
from ..structural_lifecycle_v6 import (
    Binding,
    ContractError,
    Mode,
    OwnerFailure,
    StructuralManager,
    instant,
)
from .producers import ELLIOTT, H3, HARMONIC, WYCKOFF

PROFILES = {
    HARMONIC: (frozenset({"HARMONIC_TYPE_I", "HARMONIC_TYPE_II"}), "FINITE_REACTION"),
    ELLIOTT: (frozenset({"ELLIOTT_COMMON_COUNT_OWNER"}), "TREND_CHECKPOINTS"),
    WYCKOFF: (frozenset({"WYCKOFF_RANGE_OWNER"}), "TREND_CHECKPOINTS"),
    SESSION: (frozenset({"ICT_SESSION"}), "FINITE_REACTION"),
    TREND: (frozenset({"H2_4H_STRUCTURE"}), "TREND_CHECKPOINTS"),
    H3: (frozenset({"ELLIOTT_COMMON_COUNT_OWNER"}), "TREND_CHECKPOINTS"),
}


@dataclass(frozen=True)
class ContractBinding(Binding):
    thesis: SchoolThesis

    def validate(self, entry_at, entry):
        t = self.thesis
        t.validate_entry(entry_at, entry)
        if t.side != "LONG":
            raise ContractError("SPOT_SHORT_NOT_EXECUTABLE")
        owners, mode = PROFILES.get(t.grammar, ((), None))
        if t.owner not in owners or t.mode != mode:
            raise ContractError("NEW_PROFILE_OWNER_MODE_MISMATCH")
        if (
            self.grammar,
            self.owner,
            self.structure_id,
            self.source_sha256,
            self.timeframe,
            self.available_at,
            self.initial_invalidation,
        ) != (
            t.grammar,
            t.owner,
            t.structure_id,
            t.source_sha256,
            t.management_degree,
            t.available_at,
            t.initial_invalidation,
        ):
            raise ContractError("THESIS_BINDING_MUTATED")
        if self.invalidation_source not in t.parents:
            raise ContractError("INITIAL_INVALIDATION_PROVENANCE_REQUIRED")
        if (
            t.grammar == SESSION
            and self.timeframe != "1H"
            or t.grammar == TREND
            and self.timeframe != "4H"
        ):
            raise ContractError("PROFILE_MANAGEMENT_DEGREE_MISMATCH")


@dataclass(frozen=True)
class NativeFailureV9(OwnerFailure):
    def validate(self, binding, now):
        from ..school_contract_common_v8 import valid_sha

        allowed = {
            "WYCKOFF_RANGE_OWNER": {"ASSET_DISTRIBUTION", "MARKET_DISTRIBUTION_RS_LOSS"},
            "ICT_SESSION": {"NY16", "BEARISH_MSS"},
            "H2_4H_STRUCTURE": {"CONFIRMED_1D_DOWN"},
            "HARMONIC_TYPE_I": {"FAMILY_INVALIDATED"},
            "HARMONIC_TYPE_II": {"FAMILY_INVALIDATED"},
            "ELLIOTT_COMMON_COUNT_OWNER": {"COUNT_INVALIDATED"},
        }
        valid_sha(self.source_sha256)
        if (
            not self.event_id
            or self.owner != binding.owner
            or self.structure_id != binding.structure_id
            or self.kind not in allowed.get(binding.owner, ())
            or instant(self.available_at) > clock(now)
        ):
            raise ContractError("WRONG_UNBOUND_OR_FUTURE_V9_OWNER_FAILURE")


@dataclass(frozen=True)
class PartialPlanV9(PartialPlan):
    def validate(self, binding, now, entry, mode):
        if binding.grammar != HARMONIC or mode != Mode.FINITE:
            raise ContractError("V9_PARTIAL_REQUIRES_NATIVE_FAMILY_OWNER")
        if binding.owner != "HARMONIC_" + self.lifecycle or self.lifecycle not in {
            "TYPE_I",
            "TYPE_II",
        }:
            raise ContractError("TYPE_SPECIFIC_EXECUTION_OWNER_REQUIRED")
        for x in (self.first, self.final):
            x.validate()
            if x.structure_id != binding.structure_id or instant(x.available_at) > instant(now):
                raise ContractError("V9_PARTIAL_SOURCE_OR_CLOCK")
        if (
            self.first.price,
            self.final.price,
        ) != binding.thesis.objectives or not entry < self.first.price < self.final.price:
            raise ContractError("V9_PARTIAL_TARGET_GEOMETRY")


class ExecutionV9(CampaignExecutionV7):
    def __init__(self, portfolio):
        super().__init__(portfolio)
        self.session_ends = {}

    def admit_owned(self, row, binding, now, entry, capacity, campaign_id, **kwargs):
        now = clock(now)
        before = set(self.portfolio.k.positions)
        if isinstance(binding, ContractBinding):
            if kwargs.get("add_evidence") is None:
                binding.thesis.executable_at(now, binding.available_at, entry)
            elif instant(kwargs["add_evidence"].available_at) != now:
                raise ContractError("CURRENT_SOURCE_ADD_CHECKPOINT_REQUIRED")
            binding.validate(now, entry)
            expected = Mode.FINITE if binding.thesis.mode == "FINITE_REACTION" else Mode.TREND
            if Mode(kwargs["mode"]) != expected:
                raise ContractError("EXECUTION_MODE_CANNOT_CONVERT_OWNER")
            if binding.grammar == SESSION:
                session_end = row.get("session_end")
                if session_end is None or now >= instant(session_end):
                    raise ContractError("NATIVE_SESSION_ENDPOINT_REQUIRED")
            if kwargs.get("staged"):
                return self._stage(row, binding, now, entry, capacity, campaign_id, **kwargs)
        result = super().admit_owned(row, binding, now, entry, capacity, campaign_id, **kwargs)
        if result[0]:
            (tid,) = set(self.portfolio.k.positions) - before
            self._reset_lifetime(tid, keep_partial=kwargs.get("partial_plan") is not None)
            if binding.grammar == SESSION:
                self.session_ends[tid] = instant(row["session_end"])
        return result

    def _reset_lifetime(self, tid, *, keep_partial=False):
        # The inherited kernel's integer IDs may be reused after the last open
        # position closes. They are not lifecycle identity. Clear old clocks and
        # owner-specific state only AFTER successful creation of a new position.
        self.last_execution_close.pop(tid, None)
        self.pending.pop(tid, None)
        self.portfolio.pending.pop(tid, None)
        self.session_ends.pop(tid, None)
        if not keep_partial:
            self.partial.pop(tid, None)

    def _stage(
        self,
        row,
        binding,
        now,
        entry,
        capacity,
        campaign_id,
        *,
        mode,
        objectives=(),
        research_authorized=False,
        prices=None,
        staged=False,
        partial_plan=None,
        add_evidence=None,
    ):
        if not research_authorized:
            raise ContractError("SYNTHETIC_OR_GOVERNED_EXECUTION_AUTHORITY_REQUIRED")
        if binding.grammar != WYCKOFF or not staged or add_evidence or partial_plan:
            raise ContractError("V9_STAGING_REQUIRES_NATIVE_SPRING_OWNER")
        if not binding.thesis.management_rule.startswith("STAGE_50_PERCENT"):
            raise ContractError("NO_STAGING_OF_FULL_LPS_ENTRY")
        if now.year not in {2022, 2023}:
            raise ContractError("UNAUTHORIZED_EXECUTION_PERIOD")
        if self.pending or self.portfolio.pending:
            return False, "PENDING_EXIT_NO_NEW_RISK"
        if (
            row.get("owner_grammar") != binding.grammar
            or row.get("owner_structure_id") != binding.structure_id
        ):
            raise ContractError("STAGE_ENTRY_OWNER_MISMATCH")
        key = (binding.owner, binding.structure_id, row["pair"])
        if key in self.seen_structures:
            return False, "OWNER_STRUCTURE_NO_RESURRECTION"
        m = StructuralManager(
            binding,
            now,
            entry,
            mode,
            self.portfolio.k.exit_cost_rate,
            self.portfolio.k.exit_cost_rate,
            tuple(objectives),
        )
        marks = dict(prices or {})
        marks[row["pair"]] = entry
        from ..school_contract_common_v8 import price

        held = {p["episode"]["pair"] for p in self.portfolio.k.positions.values()}
        if not held <= marks.keys():
            raise ContractError("CURRENT_ALL_ASSET_MARKS_REQUIRED")
        for value in marks.values():
            price(value)
        r = copy.deepcopy(row)
        r.update(
            entry_open=entry,
            stop=m.hard_stop,
            management_owner=binding.owner,
            owner_structure_id=binding.structure_id,
            management_degree=binding.timeframe,
            campaign_mode=str(mode),
            target=None,
            finite_objective=None,
            management_contract="AKAH_EXPLICIT_PROFILE_EXECUTION_V9",
        )
        before = set(self.portfolio.k.positions)
        ok, reason = self.portfolio.k.admit(
            r,
            lambda pair, at: marks[pair],
            now,
            capacity,
            self.portfolio.rules[r["pair"]].normalize,
            campaign_id,
            funded_ready=True,
            staged=True,
        )
        if ok:
            (tid,) = set(self.portfolio.k.positions) - before
            self._reset_lifetime(tid)
            self.managers[tid] = m
            self.seen_structures.add(key)
            self.campaign_owner[campaign_id] = binding
            self.campaign_entry[campaign_id] = now
            self.staged_campaigns.add(campaign_id)
            self.portfolio.k.fills[-1]["execution_phase"] = "OPEN"
            self.decision_ledger.append(
                {
                    "campaign_id": campaign_id,
                    "known_at": now,
                    "reason": "V9_SOURCE_SPRING_HALF_ORIGINAL_CAMPAIGN_BUDGET",
                }
            )
        return ok, reason

    def _session_failure(self, tid, hour, supplied):
        if (
            supplied is not None
            or tid not in self.session_ends
            or self.managers[tid].binding.grammar != SESSION
            or instant(hour.end) < self.session_ends[tid]
        ):
            return supplied
        b = self.managers[tid].binding
        return NativeFailureV9(
            f"{tid}:NY16:{self.session_ends[tid].isoformat()}",
            b.owner,
            b.structure_id,
            "NY16",
            self.session_ends[tid],
            b.source_sha256,
        )

    def preview_close(self, tid, hour, **kwargs):
        b = self.managers[tid].binding
        if isinstance(b, ContractBinding):
            for p in kwargs.get("pivots", ()):
                step = DEGREES[b.timeframe]
                if (
                    instant(p.observed_at).timestamp() % step.total_seconds()
                    or instant(p.available_at) < instant(p.observed_at) + 2 * step
                ):
                    raise ContractError("V9_OWNER_PIVOT_TWO_RIGHT_CLOSES_REQUIRED")
            kwargs["native_failure"] = self._session_failure(
                tid, hour, kwargs.get("native_failure")
            )
        return super().preview_close(tid, hour, **kwargs)

    def on_completed_hour(self, tid, hour, capacity, **kwargs):
        if isinstance(self.managers[tid].binding, ContractBinding):
            kwargs["native_failure"] = self._session_failure(
                tid, hour, kwargs.get("native_failure")
            )
        return super().on_completed_hour(tid, hour, capacity, **kwargs)
