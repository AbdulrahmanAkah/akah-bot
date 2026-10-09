"""Research-only event accounting kernel. No market reader or replay entrypoint."""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_FLOOR
from functools import reduce

from . import akah_native_replay_engine_v1 as engine
from .akah_thesis_engine_foundation_v1 import CampaignRecord


@dataclass
class PortfolioKernel:
    cash: float
    positions: dict
    campaigns: dict[str, CampaignRecord]
    exit_cost_rate: float
    risk_breach_unresolved: bool = False
    fills: list = field(default_factory=list)

    def snapshot(self, marks: Callable, now):
        return engine.current_mtm_state(self.cash, self.positions, marks, now, self.exit_cost_rate)

    def reduce_common(self, marks: Callable, now, capacity: dict[str, float], normalizer: Callable):
        lam, state = engine.proportional_risk_reduction_lambda(
            self.cash, self.positions, marks, now, self.exit_cost_rate
        )
        if lam is None:
            self.risk_breach_unresolved = True
            return False
        # Prospective discrete contract: the largest common retained fraction
        # below the continuous safety bound. Never round different survivors.
        rules = getattr(normalizer, "quantity_rules", None)
        lattice_units = {}
        lattice_retained = None
        if rules and self.positions:
            units = []
            for tid, p in self.positions.items():
                rule = rules[p['episode']['pair']]
                n = Decimal(str(p['qty_current'])) / rule.lot
                units.append(int(n.to_integral_value()))
                lattice_units[tid]=units[-1]
            divisor = reduce(math.gcd, units)
            if divisor <= 0:
                self.risk_breach_unresolved = True
                return False
            lattice_retained=int((Decimal(str(lam))*divisor).to_integral_value(rounding=ROUND_FLOOR))
            lam = lattice_retained/divisor
        reductions = {}
        required_capacity = {}
        for tid, p in self.positions.items():
            pair = p["episode"]["pair"]
            qty = (1 - lam) * p["qty_current"]
            if lattice_retained is not None:
                rule=rules[pair]
                qty=float(Decimal(lattice_units[tid]*(divisor-lattice_retained)//divisor)*rule.lot)
            mark = state["marks"][tid]
            if qty == 0:
                reductions[tid] = 0.0
                continue
            # A lattice that cannot express identical retained fractions must not silently
            # change the rule into score-based or independently-rounded survivors.
            normalized = normalizer(pair, qty, mark, now)
            if not math.isfinite(normalized) or not math.isclose(
                normalized, qty, rel_tol=1e-12, abs_tol=1e-12
            ):
                self.risk_breach_unresolved = True
                return False
            reductions[tid] = qty
            required_capacity[pair] = required_capacity.get(pair, 0.0) + qty * mark
        for pair, amount in required_capacity.items():
            cap = capacity.get(pair)
            if cap is None or not math.isfinite(cap) or cap < amount:
                self.risk_breach_unresolved = True
                return False
        for tid, qty in reductions.items():
            if qty > 0:
                pair=self.positions[tid]['episode']['pair']
                price=rules[pair].price(state['marks'][tid],buy=False) if rules else state['marks'][tid]
                self.partial_exit(tid, qty, price, now=now, reason='COMMON_RISK_REDUCTION')
        self.positions = {tid: p for tid, p in self.positions.items() if p["qty_current"] > 1e-12}
        self.risk_breach_unresolved = not engine.current_mtm_limits_ok(self.snapshot(marks, now))
        return not self.risk_breach_unresolved

    def admit(
        self,
        row,
        marks: Callable,
        now,
        capacity: float | None,
        normalizer: Callable,
        campaign_id: str,
        *,
        funded_ready: bool,
        is_add: bool = False,
        staged=False,
    ):
        if not funded_ready or self.risk_breach_unresolved:
            return False, "NO_NEW_RISK"
        if capacity is None or not math.isfinite(capacity) or capacity <= 0:
            return False, "UNKNOWN_OR_ZERO_CAPACITY"
        state = self.snapshot(marks, now)
        if not engine.current_mtm_limits_ok(state):
            return False, "RISK_BREACH_UNRESOLVED"
        pair, entry, stop = row["pair"], row["entry_open"], row["stop"]
        if not all(math.isfinite(v) for v in (entry, stop)) or not 0 < stop < entry:
            return False, "VALID_PROTECTIVE_STOP_REQUIRED"
        if pair in state["asset"] and not is_add:
            return False, "SAME_ASSET_OWNERSHIP_CONFLICT"
        if pair not in state["asset"] and len(state["asset"]) >= 5:
            return False, "MAX_DISTINCT_ASSETS"
        if is_add:
            campaign = self.campaigns.get(campaign_id)
            owners = {
                p["campaign_id"] for p in self.positions.values() if p["episode"]["pair"] == pair
            }
            if campaign is None or owners != {campaign_id} or campaign.add_count >= 1:
                return False, "ADD_PARENT_OR_OWNERSHIP_INVALID"
        else:
            if campaign_id in self.campaigns:
                return False, "CAMPAIGN_RESURRECTION_FORBIDDEN"
            campaign = CampaignRecord(campaign_id, row["identity"], pair, 0.005 * state["equity"])
        stage_budget = campaign.initial_risk_budget * (0.5 if staged or is_add else 1)
        available = min(
            stage_budget,
            campaign.initial_risk_budget - campaign.committed_risk,
            0.005 * state["equity"] - campaign.committed_risk,
        )
        rate = self.exit_cost_rate
        per_unit = engine.entry_risk_per_unit(entry, stop, rate, rate)
        if available <= 0 or not math.isfinite(per_unit):
            return False, "CAMPAIGN_RISK_EXHAUSTED"
        quantity = min(available / per_unit, capacity / entry, self.cash / (entry * (1 + rate)))
        # Bounds include purchase fees' effect on current equity.
        e = state["equity"]
        quantity = min(
            quantity,
            max(0, (0.90 * e - state["gross"]) / (entry * (1 + 0.90 * rate))),
            max(0, (0.18 * e - state["asset"].get(pair, 0)) / (entry * (1 + 0.18 * rate))),
            max(
                0,
                (0.025 * e - state["open_stop_risk"])
                / (entry - stop * (1 - rate) + 0.025 * entry * rate),
            ),
        )
        quantity = normalizer(pair, quantity, entry, now)
        if not math.isfinite(quantity) or quantity <= 0:
            return False, "QUANTITY_NORMALIZATION_REJECTED"
        risk = quantity * per_unit
        if not campaign.can_commit(risk, e, stage_budget):
            return False, "CAMPAIGN_B0_EXCEEDED"
        cash_after = self.cash - quantity * entry * (1 + rate)
        tid = max(self.positions, default=0) + 1
        position = {
            "episode": row,
            "qty_current": quantity,
            "current_stop": stop,
            "campaign_id": campaign_id,
        }
        proposed = {**self.positions, tid: position}
        # Do not trust a normalizer that increases quantity past cash, capacity or limits.
        if cash_after < -1e-9 or quantity * entry > capacity + 1e-9:
            return False, "NORMALIZER_INCREASED_INFEASIBLE_QUANTITY"
        new_state = engine.current_mtm_state(cash_after, proposed, marks, now, rate)
        if not engine.current_mtm_limits_ok(new_state):
            return False, "POST_FILL_RISK_LIMIT_REJECTED"
        campaign.commit(risk, e, stage_budget, is_add=is_add)
        self.campaigns[campaign_id] = campaign
        self.positions, self.cash = proposed, cash_after
        self.fills.append({'time':str(now),'side':'BUY','campaign_id':campaign_id,'pair':pair,
            'identity':row['identity'],'qty':quantity,'price':entry,'fee':quantity*entry*rate,
            'cash_delta':-quantity*entry*(1+rate),'reason':'STAGED_ADD' if is_add else 'ENTRY'})
        return True, "FILLED"

    def partial_exit(self, tid: int, quantity: float, price: float, *, now=None, reason='EXIT'):
        p = self.positions[tid]
        if not 0 < quantity <= p["qty_current"] or price <= 0:
            raise ValueError("INVALID_PARTIAL_FILL")
        self.cash += quantity * price * (1 - self.exit_cost_rate)
        self.fills.append({'time':str(now),'side':'SELL','campaign_id':p['campaign_id'],
            'pair':p['episode']['pair'],'identity':p['episode'].get('identity','fixture'),
            'qty':quantity,'price':price,'fee':quantity*price*self.exit_cost_rate,
            'cash_delta':quantity*price*(1-self.exit_cost_rate),'reason':reason})
        p["qty_current"] -= quantity
        if p["qty_current"] <= 1e-12:
            del self.positions[tid]
        # Campaign committed risk deliberately remains unchanged.
