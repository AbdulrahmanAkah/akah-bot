"""Actual research-kernel bridge for V6. Synthetic certification only by default.

No automatic replay, raw data reader, production hook or V5 output mutation.
Hard stops always precede finite targets. Soft breaks execute only at later OPEN.
"""

from __future__ import annotations

import copy
import math
from dataclasses import asdict
from datetime import datetime
from decimal import ROUND_FLOOR, Decimal

from . import full_replay_v5 as v5
from .structural_lifecycle_v6 import (
    H3,
    Binding,
    CompletedBar,
    ContractError,
    Decision,
    Mode,
    Objective,
    OwnerFailure,
    Phase,
    Pivot,
    StructuralManager,
    instant,
)


class LifecycleExecution:
    def __init__(self, portfolio: v5.Portfolio):
        self.portfolio = portfolio
        self.managers: dict[int, StructuralManager] = {}
        self.pending: dict[int, Decision] = {}
        self.decision_ledger: list[dict] = []
        self.last_execution_close: dict[int, datetime] = {}
        self.seen_structures: set[tuple[str, str, str]] = set()

    def admit(
        self,
        row: dict,
        binding: Binding,
        now: datetime,
        entry: float,
        capacity: float,
        campaign_id: str,
        *,
        mode: Mode,
        objectives: tuple[Objective, ...],
        research_authorized: bool = False,
        prices: dict[str, float] | None = None,
    ):
        if not research_authorized:
            raise ContractError("EXPERIMENTAL_MANAGEMENT_NOT_AUTOMATICALLY_ARMED")
        if self.pending or self.portfolio.pending:
            return False, "PENDING_EXIT_NO_NEW_RISK"
        if row.get("owner_grammar") != binding.grammar:
            raise ContractError("ENTRY_GRAMMAR_MISMATCH")
        prices = dict(prices or {})
        prices[row["pair"]] = entry
        held = {p["episode"]["pair"] for p in self.portfolio.k.positions.values()}
        if not held <= prices.keys() or any(
            not math.isfinite(v) or v <= 0 for v in prices.values()
        ):
            raise ContractError("CURRENT_ALL_ASSET_MARKS_REQUIRED")
        manager = StructuralManager(
            binding,
            now,
            entry,
            mode,
            self.portfolio.k.exit_cost_rate,
            self.portfolio.k.exit_cost_rate,
            objectives,
        )
        key = (binding.owner, binding.structure_id, row["pair"])
        if key in self.seen_structures:
            return False, "OWNER_STRUCTURE_NO_RESURRECTION"
        r = copy.deepcopy(row)
        if binding.grammar == H3 and not r.get("count_id"):
            raise ContractError("H3_COUNT_OWNER_REQUIRED")
        if binding.grammar == H3 and binding.structure_id != r["count_id"]:
            raise ContractError("H3_COUNT_STRUCTURE_MISMATCH")
        if r.get("owner_structure_id") != binding.structure_id and binding.grammar != H3:
            raise ContractError("ENTRY_STRUCTURE_MISMATCH")
        # Do not inherit the old Harmonic dispatcher for H3 count-owned campaigns.
        if binding.grammar == H3:
            r["supporting_projection_id"] = r.get("projection_id")
        r.update(
            management_owner=binding.owner,
            owner_structure_id=binding.structure_id,
            stop=manager.hard_stop,
            entry_open=entry,
            management_degree=binding.timeframe,
            management_contract="AKAH_OWNER_LINKED_STRUCTURAL_MANAGEMENT_V6",
            campaign_mode=str(mode),
            target=None,
            finite_objective=(manager.finite_objective.price if manager.finite_objective else None),
        )
        rule = self.portfolio.rules[r["pair"]]
        before = set(self.portfolio.k.positions)
        ok, reason = self.portfolio.k.admit(
            r,
            lambda pair, at: prices[pair],
            now,
            capacity,
            rule.normalize,
            campaign_id,
            funded_ready=True,
        )
        if ok:
            created = set(self.portfolio.k.positions) - before
            if len(created) != 1:
                raise ContractError("POSITION_CREATION_PARITY")
            tid = created.pop()
            self.managers[tid] = manager
            self.seen_structures.add(key)
            self.portfolio.k.fills[-1]["execution_phase"] = "OPEN"
        return ok, reason

    def _clean_closed(self, tid: int) -> None:
        if tid not in self.portfolio.k.positions and tid in self.managers:
            self.managers[tid].mark_closed()
            self.pending.pop(tid, None)
            self.portfolio.pending.pop(tid, None)

    def _tracked_exit(self, tid, price, at, capacity, reason):
        self.portfolio.sell(tid, price, at, capacity, reason)
        if tid in self.portfolio.k.positions:
            m = self.managers[tid]
            m.phase = Phase.BROKEN
            self.pending[tid] = Decision(
                instant(at),
                instant(at),
                Phase.BROKEN,
                "EXIT_NEXT_OPEN",
                reason,
                m.hard_stop,
                m.hard_stop,
                m.protected_low,
            )
        self._clean_closed(tid)

    def on_open(self, at: datetime, prices: dict[str, float], capacity: dict[str, float]):
        at = instant(at)
        self.portfolio.phase = "OPEN"
        for tid, manager in self.managers.items():
            manager.assert_invariants()
            if tid in self.portfolio.k.positions and at < self.last_execution_close.get(
                tid, manager.entry_at
            ):
                raise ContractError("EXECUTION_OPEN_CLOCK_REVERSED")
        for tid, manager in list(self.managers.items()):
            if tid not in self.portfolio.k.positions:
                continue
            p = self.portfolio.k.positions[tid]
            pair = p["episode"]["pair"]
            price = prices.get(pair)
            if price is None or not math.isfinite(price) or price <= 0:
                self.portfolio.risk_pass = False
                continue
            if price <= manager.hard_stop:
                self._tracked_exit(tid, price, at, capacity, "HARD_STOP_GAP")
            elif tid in self.pending:
                d = self.pending[tid]
                if at < d.applies_from:
                    raise ContractError("EXIT_BEFORE_AVAILABLE")
                self._tracked_exit(tid, price, at, capacity, d.reason)
            elif tid in self.portfolio.pending:
                self._tracked_exit(tid, price, at, capacity, self.portfolio.pending[tid])
            elif manager.finite_objective and price >= manager.finite_objective.price:
                self._tracked_exit(
                    tid, manager.finite_objective.price, at, capacity, "FINITE_OBJECTIVE_GAP"
                )

    def on_completed_hour(
        self,
        tid: int,
        hour: CompletedBar,
        capacity: dict[str, float],
        *,
        owner_bar: CompletedBar | None = None,
        pivots: tuple[Pivot, ...] = (),
        objectives: tuple[Objective, ...] = (),
        native_failure: OwnerFailure | None = None,
    ):
        hour.validate()
        if hour.timeframe != "1H":
            raise ContractError("EXECUTION_HOUR_REQUIRED")
        manager = self.managers[tid]
        manager.assert_invariants()
        if tid not in self.portfolio.k.positions:
            raise ContractError("CLOSED_POSITION_NO_RESURRECTION")
        at = instant(hour.end)
        if instant(hour.start) < manager.entry_at:
            raise ContractError("EXECUTION_BEFORE_ENTRY")
        previous = self.last_execution_close.get(tid, manager.entry_at)
        if instant(hour.start) != previous:
            raise ContractError("EXECUTION_HOUR_REPEATED_OR_COVERAGE_GAP")
        if owner_bar is not None:
            owner_bar.validate()
            if instant(owner_bar.end) != at:
                raise ContractError("OWNER_CLOSE_NOT_THIS_COMPLETED_HOUR")
        if native_failure is not None:
            if not isinstance(native_failure, OwnerFailure):
                raise ContractError("SOURCE_BOUND_FAILURE_EVENT_REQUIRED")
            native_failure.validate(manager.binding, at)
        # Validate/project all owner-state transitions before any cash mutation.
        projected = copy.deepcopy(manager)
        d = (
            projected.on_close(
                owner_bar, pivots=pivots, objectives=objectives, native_failure=native_failure
            )
            if owner_bar is not None
            else projected.on_native_failure(native_failure, at)
            if native_failure is not None
            else None
        )
        self.last_execution_close[tid] = at
        # Levels standing BEFORE this hour only. New ratchet cannot hit old lows.
        self.portfolio.phase = "INTRABAR_OR_COMPLETED_CLOSE"
        if hour.open <= manager.hard_stop:
            self.portfolio.phase = "OPEN"
            self._tracked_exit(tid, hour.open, instant(hour.start), capacity, "HARD_STOP_GAP")
            return None
        if hour.low <= manager.hard_stop:
            self._tracked_exit(tid, manager.hard_stop, at, capacity, "HARD_STRUCTURAL_STOP")
            return None
        if manager.finite_objective and hour.high >= manager.finite_objective.price:
            self._tracked_exit(
                tid, manager.finite_objective.price, at, capacity, "FINITE_OBJECTIVE"
            )
            return None
        if d is None:
            return None
        manager.__dict__.update(projected.__dict__)
        self.portfolio.k.positions[tid]["current_stop"] = manager.hard_stop
        self.portfolio.k.positions[tid]["episode"]["lifecycle_state"] = str(manager.phase)
        self.decision_ledger.append(
            {
                "identity": self.portfolio.k.positions[tid]["episode"]["identity"],
                "campaign_id": self.portfolio.k.positions[tid]["campaign_id"],
                "owner": manager.binding.owner,
                "structure_id": manager.binding.structure_id,
                **asdict(d),
            }
        )
        if d.action == "EXIT_NEXT_OPEN":
            self.pending[tid] = d
        return d

    def restore_risk_at_open(
        self, at: datetime, prices: dict[str, float], capacity: dict[str, float]
    ) -> bool:
        """Target breached assets first; then maximum stop-risk removed per dollar.

        Same hard caps, no credit for correlated longs. Capacity limits remain binding.
        No outcome/entry-score preference, no proportional sale of unaffected assets.
        """
        from . import akah_native_replay_engine_v1 as eng

        at = instant(at)
        self.portfolio.phase = "OPEN"
        k = self.portfolio.k
        rate = k.exit_cost_rate

        def marks(pair, now):
            return prices.get(pair)

        def state():
            return k.snapshot(marks, at)

        def reduce(tid, dollars):
            p = k.positions[tid]
            price = prices[p["episode"]["pair"]]
            lot = self.portfolio.rules[p["episode"]["pair"]].lot
            retained = max(0.0, p["qty_current"] - dollars / price)
            units = (Decimal(str(retained)) / lot).to_integral_value(rounding=ROUND_FLOOR)
            retained = float(max(Decimal(0), units - 2) * lot)
            qty = p["qty_current"] - retained
            self.portfolio.sell(
                tid, price, at, capacity, "TARGETED_RISK_REDUCTION", qty / p["qty_current"]
            )
            self._clean_closed(tid)

        s = state()
        if not s["valid"]:
            self.portfolio.risk_pass = False
            return False
        for tid in list(k.positions):
            s = state()
            p = k.positions.get(tid)
            if p is None:
                continue
            pair = p["episode"]["pair"]
            excess = s["asset"][pair] - 0.18 * s["equity"]
            if excess > 1e-9:
                reduce(tid, excess / (1 - 0.18 * rate))

        # Iterate over each actual position at most once; no retry-until-looks-good loop.
        def risk_efficiency(tid):
            p = k.positions[tid]
            price = prices[p["episode"]["pair"]]
            return max(0.0, 1 - p["current_stop"] * (1 - rate) / price)

        order = sorted(k.positions, key=lambda tid: (-risk_efficiency(tid), str(tid)))
        for tid in order:
            if tid not in k.positions:
                continue
            s = state()
            risk_excess = s["open_stop_risk"] - 0.025 * s["equity"]
            gross_excess = s["gross"] - 0.90 * s["equity"]
            if risk_excess <= 1e-9 and gross_excess <= 1e-9:
                break
            d = risk_efficiency(tid) - 0.025 * rate
            risk_sale = risk_excess / d if risk_excess > 1e-9 and d > 0 else 0.0
            gross_sale = gross_excess / (1 - 0.90 * rate) if gross_excess > 1e-9 else 0.0
            if max(risk_sale, gross_sale) > 0:
                reduce(tid, max(risk_sale, gross_sale))
        ok = eng.current_mtm_limits_ok(state())
        if not ok:
            self.portfolio.risk_pass = False
        k.risk_breach_unresolved = not ok
        return ok
