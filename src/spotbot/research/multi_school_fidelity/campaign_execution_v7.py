"""Source-owned staged/partial campaign bridge. Research-only, no market readers.

This closes execution mechanics, not missing full-school doctrine or profitability.
V4/V5/V6 are immutable authorities; unsupported source branches remain unfunded.
"""

from __future__ import annotations

import copy
import math
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_FLOOR, Decimal

from . import full_replay_v5 as v5
from .lifecycle_execution_v6 import LifecycleExecution
from .structural_lifecycle_v6 import (
    H3,
    HA,
    WY,
    Binding,
    ContractError,
    Mode,
    Objective,
    Phase,
    StructuralManager,
    instant,
)


@dataclass(frozen=True)
class PartialPlan:
    first: Objective
    final: Objective
    lifecycle: str

    def validate(self, binding: Binding, now: datetime, entry: float, mode: Mode) -> None:
        if binding.grammar != HA or mode != Mode.FINITE:
            raise ContractError("PARTIAL_PLAN_REQUIRES_NATIVE_HARMONIC_OWNER")
        if self.lifecycle not in {"TYPE_I", "TYPE_II"}:
            raise ContractError("PARTIAL_LIFECYCLE_SOURCE_REQUIRED")
        for objective in (self.first, self.final):
            objective.validate()
            if (
                objective.structure_id != binding.structure_id
                or instant(objective.available_at) > now
            ):
                raise ContractError("PARTIAL_OBJECTIVE_OWNER_OR_CLOCK")
        if not entry < self.first.price < self.final.price:
            raise ContractError("PARTIAL_TARGET_GEOMETRY")


@dataclass(frozen=True)
class AddEvidence:
    event_id: str
    structure_id: str
    available_at: datetime
    lps_low: float
    source_sha256: str

    def validate(self, binding: Binding, original_at: datetime, now: datetime, entry: float):
        if (
            not self.event_id
            or self.structure_id != binding.structure_id
            or not original_at < instant(self.available_at) <= now
            or len(self.source_sha256) != 64
            or any(c not in "0123456789abcdefABCDEF" for c in self.source_sha256)
            or not math.isfinite(self.lps_low)
            or not 0 < self.lps_low < entry
        ):
            raise ContractError("FRESH_SAME_OWNER_LPS_SOURCE_REQUIRED")


@dataclass
class PartialState:
    plan: PartialPlan
    initial_qty: float
    first_required: float
    first_sold: float = 0.0
    first_disabled: bool = False
    first_reached: bool = False


class CampaignExecutionV7(LifecycleExecution):
    def __init__(self, portfolio):
        super().__init__(portfolio)
        self.partial: dict[int, PartialState] = {}
        self.campaign_owner: dict[str, Binding] = {}
        self.campaign_entry: dict[str, datetime] = {}
        self.staged_campaigns: set[str] = set()
        self.used_add_events: set[str] = set()

    def admit_owned(
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
        now = instant(now)
        if now.year not in {2022, 2023}:
            raise ContractError("PROTECTED_OR_UNAUTHORIZED_PERIOD")
        mode = Mode(mode)
        if not research_authorized:
            raise ContractError("EXPERIMENTAL_MANAGEMENT_NOT_AUTOMATICALLY_ARMED")
        if self.pending or self.portfolio.pending:
            return False, "PENDING_EXIT_NO_NEW_RISK"
        is_add = add_evidence is not None
        if staged and (binding.grammar != WY or is_add):
            raise ContractError("STAGED_ENTRY_REQUIRES_NATIVE_WYCKOFF")
        if is_add:
            if (
                campaign_id not in self.staged_campaigns
                or self.campaign_owner[campaign_id] != binding
            ):
                raise ContractError("ADD_CAMPAIGN_OWNER_MISMATCH")
            add_evidence.validate(binding, self.campaign_entry[campaign_id], now, entry)
            if add_evidence.event_id in self.used_add_events:
                raise ContractError("ADD_EVENT_NO_RESURRECTION")
            parent_ids = [
                tid
                for tid, p in self.portfolio.k.positions.items()
                if p["campaign_id"] == campaign_id
            ]
            if not parent_ids or any(
                self.managers[tid].phase in {Phase.BREAK_PENDING, Phase.BROKEN, Phase.CLOSED}
                for tid in parent_ids
            ):
                return False, "ADD_PARENT_NOT_ACTIVE"
            # Once cash has been taken out, no staged risk can resurrect the campaign.
            if any(
                f["campaign_id"] == campaign_id and f["side"] == "SELL"
                for f in self.portfolio.k.fills
            ):
                return False, "ADD_AFTER_REDUCTION_FORBIDDEN"
            old_stop = max(self.managers[tid].hard_stop for tid in parent_ids)
            if add_evidence.lps_low < old_stop:
                return False, "ADD_WOULD_LOWER_PROTECTION"
        if row.get("owner_grammar") != binding.grammar:
            raise ContractError("ENTRY_GRAMMAR_MISMATCH")
        structure = row.get("count_id") if binding.grammar == H3 else row.get("owner_structure_id")
        if not structure or structure != binding.structure_id:
            raise ContractError("ENTRY_STRUCTURE_MISMATCH")
        key = (binding.owner, binding.structure_id, row["pair"])
        if not is_add and key in self.seen_structures:
            return False, "OWNER_STRUCTURE_NO_RESURRECTION"
        if partial_plan is not None:
            partial_plan.validate(binding, now, entry, mode)
            objectives = (partial_plan.final,)
        manager = StructuralManager(
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
        held = {p["episode"]["pair"] for p in self.portfolio.k.positions.values()}
        if not held <= marks.keys() or any(not math.isfinite(v) or v <= 0 for v in marks.values()):
            raise ContractError("CURRENT_ALL_ASSET_MARKS_REQUIRED")
        r = copy.deepcopy(row)
        if binding.grammar == H3:
            r["supporting_projection_id"] = r.get("projection_id")
        if is_add:
            manager.hard_stop = manager.protected_low = add_evidence.lps_low
            manager._minimum_hard_stop = manager._minimum_protected_low = add_evidence.lps_low
        r.update(
            entry_open=entry,
            stop=manager.hard_stop,
            management_owner=binding.owner,
            owner_structure_id=binding.structure_id,
            management_degree=binding.timeframe,
            campaign_mode=str(mode),
            target=None,
            management_contract="AKAH_CAMPAIGN_EXECUTION_V7",
            finite_objective=manager.finite_objective.price if manager.finite_objective else None,
        )
        before = set(self.portfolio.k.positions)
        rule = self.portfolio.rules[r["pair"]]
        ok, reason = self.portfolio.k.admit(
            r,
            lambda pair, at: marks[pair],
            now,
            capacity,
            rule.normalize,
            campaign_id,
            funded_ready=True,
            is_add=is_add,
            staged=staged,
        )
        if not ok:
            return ok, reason
        (tid,) = set(self.portfolio.k.positions) - before
        self.managers[tid] = manager
        self.seen_structures.add(key)
        self.portfolio.k.fills[-1]["execution_phase"] = "OPEN"
        if not is_add:
            self.campaign_owner[campaign_id] = binding
            self.campaign_entry[campaign_id] = now
            if staged:
                self.staged_campaigns.add(campaign_id)
        else:
            self.used_add_events.add(add_evidence.event_id)
            # A source-owned LPS ratchets every tranche, without resetting B0.
            for other in parent_ids:
                m = self.managers[other]
                m.hard_stop = max(m.hard_stop, add_evidence.lps_low)
                m.protected_low = max(m.protected_low, add_evidence.lps_low)
                m._minimum_hard_stop = m.hard_stop
                m._minimum_protected_low = m.protected_low
                self.portfolio.k.positions[other]["current_stop"] = m.hard_stop
        if partial_plan is not None:
            quantity = self.portfolio.k.positions[tid]["qty_current"]
            half = float(
                (Decimal(str(quantity)) / 2 / rule.lot).to_integral_value(rounding=ROUND_FLOOR)
                * rule.lot
            )
            rate = self.portfolio.k.exit_cost_rate
            disabled = (
                v5.target_net_per_unit(entry, partial_plan.first.price, rate) <= 0 or half <= 0
            )
            self.partial[tid] = PartialState(partial_plan, quantity, half, first_disabled=disabled)
        position = self.portfolio.k.positions[tid]
        self.decision_ledger.append(
            {
                "campaign_id": campaign_id,
                "known_at": now,
                "reason": "SOURCE_OBJECTIVE_ECONOMICS_AT_ACTUAL_FILL",
                "owner": binding.owner,
                "structure_id": binding.structure_id,
                "mode": str(mode),
                "entry_notional": position["qty_current"] * entry,
                "objectives": manager.objective_economics(position["qty_current"] * entry),
                "expected_profit": "UNKNOWN_NOT_A_FORECAST",
            }
        )
        return ok, reason

    def _first_fill(self, tid, at, capacity):
        state = self.partial[tid]
        if state.first_disabled or state.first_sold >= state.first_required - 1e-10:
            return
        p = self.portfolio.k.positions[tid]
        before = p["qty_current"]
        need = state.first_required - state.first_sold
        self.portfolio.sell(
            tid, state.plan.first.price, at, capacity, "TGT1", min(1.0, need / before)
        )
        after = self.portfolio.k.positions.get(tid, {}).get("qty_current", 0.0)
        state.first_sold += before - after
        if state.first_sold > state.first_required + 1e-9:
            raise ContractError("PARTIAL_FIXED_INITIAL_QUANTITY_EXCEEDED")

    def on_open(self, at, prices, capacity):
        if instant(at).year not in {2022, 2023}:
            raise ContractError("PROTECTED_OR_UNAUTHORIZED_PERIOD")
        # STOP/pending/finite final goal takes precedence over a first-target fill.
        super().on_open(at, prices, capacity)
        for tid, state in self.partial.items():
            if tid not in self.portfolio.k.positions or tid in self.pending:
                continue
            p = self.portfolio.k.positions[tid]
            if prices.get(p["episode"]["pair"], 0) >= state.plan.first.price:
                state.first_reached = True
                self._first_fill(tid, instant(at), capacity)

    def on_completed_hour(self, tid, hour, capacity, **kwargs):
        if instant(hour.end).year not in {2022, 2023}:
            raise ContractError("PROTECTED_COMPLETED_BAR")
        self.preview_close(tid, hour, **kwargs)
        state = self.partial.get(tid)
        if state is None:
            return super().on_completed_hour(tid, hour, capacity, **kwargs)
        # Owner-state validation above must precede first-target cash changes.
        result = None
        manager = self.managers[tid]
        # Existing hard protection wins a same-bar stop/target collision.
        if hour.low <= manager.hard_stop:
            return super().on_completed_hour(tid, hour, capacity, **kwargs)
        if hour.high >= state.plan.first.price:
            state.first_reached = True
            self.portfolio.phase = "INTRABAR_OR_COMPLETED_CLOSE"
            self._first_fill(tid, instant(hour.end), capacity)
        if tid not in self.portfolio.k.positions:
            self._clean_closed(tid)
            return result
        result = super().on_completed_hour(tid, hour, capacity, **kwargs)
        if (
            tid in self.portfolio.k.positions
            and tid not in self.pending
            and not state.first_disabled
            and state.first_sold >= state.first_required - 1e-10
        ):
            p = self.portfolio.k.positions[tid]
            cid = p["campaign_id"]
            remaining = sum(
                z["qty_current"]
                for z in self.portfolio.k.positions.values()
                if z["campaign_id"] == cid
            )
            be = v5.campaign_breakeven(
                self.portfolio.k.fills, cid, remaining, self.portfolio.k.exit_cost_rate
            )
            m = self.managers[tid]
            if be is not None and m.hard_stop < be < hour.close:
                old = m.hard_stop
                m.hard_stop = m._minimum_hard_stop = be
                # Finite native Harmonic protection is a cash breakeven floor,
                # not a claim that price printed a new structural higher low.
                m.protected_low = max(m.protected_low, be)
                m._minimum_protected_low = m.protected_low
                p["current_stop"] = be
                self.decision_ledger.append(
                    {
                        "campaign_id": cid,
                        "known_at": instant(hour.end),
                        "applies_from": instant(hour.end),
                        "reason": "CAMPAIGN_BREAKEVEN_NEXT_BAR",
                        "hard_stop_before": old,
                        "hard_stop_after": be,
                    }
                )
        return result

    def preview_close(
        self, tid, hour, *, owner_bar=None, pivots=(), objectives=(), native_failure=None
    ):
        """Bounded owner-state projection; never copy cumulative fills/portfolio history."""
        hour.validate()
        if instant(hour.end).year not in {2022, 2023} or hour.timeframe != "1H":
            raise ContractError("PROTECTED_OR_INVALID_EXECUTION_BAR")
        m = self.managers[tid]
        m.assert_invariants()
        if tid not in self.portfolio.k.positions:
            raise ContractError("CLOSED_POSITION_NO_RESURRECTION")
        if instant(hour.start) != self.last_execution_close.get(tid, m.entry_at):
            raise ContractError("EXECUTION_HOUR_REPEATED_OR_COVERAGE_GAP")
        if owner_bar is not None:
            owner_bar.validate()
            if instant(owner_bar.end) != instant(hour.end):
                raise ContractError("OWNER_CLOSE_NOT_THIS_COMPLETED_HOUR")
        elif pivots or objectives:
            raise ContractError("OWNER_BAR_REQUIRED_FOR_OWNER_STATE_UPDATE")
        if native_failure is not None:
            native_failure.validate(m.binding, instant(hour.end))
        projected = copy.deepcopy(m)
        if owner_bar is not None:
            projected.on_close(
                owner_bar, pivots=pivots, objectives=objectives, native_failure=native_failure
            )
        elif native_failure is not None:
            projected.on_native_failure(native_failure, instant(hour.end))


def authority_is_historical(rule, now):
    """A prospective numerical rule cannot become historical through unit tests."""
    if getattr(rule, "authority_kind", None) != "HISTORICAL_PIT_EXCHANGE_RULE":
        return False
    try:
        return (
            instant(rule.available_at) <= instant(now)
            and instant(rule.effective_from) <= instant(now) < instant(rule.effective_until)
            and len(rule.source_sha256) == 64
            and all(c in "0123456789abcdefABCDEF" for c in rule.source_sha256)
            and rule.lot > 0
            and rule.price_tick > 0
            and rule.min_quantity >= 0
            and rule.min_notional >= 0
        )
    except (AttributeError, TypeError, ValueError, ArithmeticError):
        return False
