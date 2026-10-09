"""Research event bridge, synthetically certified; market authority is supplied by the gated runner."""

from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import ROUND_FLOOR, ROUND_CEILING, Decimal

import pandas as pd

from . import akah_full_fidelity_runtime_v1 as runtime
from . import akah_native_replay_engine_v1 as engine
from .akah_foundation_core_v1r1 import DATA_CUTOFF, utc
from .evidence_selector import EvidenceStore, Feasibility, select_prebatch
from .portfolio_kernel import PortfolioKernel
from .owned_runtime_v3 import classical_manage_v3


@dataclass(frozen=True)
class QuantityRule:
    pair: str
    available_at: object
    effective_from: object
    effective_until: object
    lot: Decimal
    min_quantity: Decimal
    min_notional: Decimal
    source_sha256: str
    authority_kind: str
    price_tick: Decimal = Decimal('0.00000001')

    def price(self, price, *, buy):
        return float((Decimal(str(price))/self.price_tick).to_integral_value(
            rounding=ROUND_CEILING if buy else ROUND_FLOOR)*self.price_tick)

    def normalize_exit(self, pair, quantity, price, now):
        from dataclasses import replace
        return replace(self,min_notional=Decimal(0)).normalize(pair,quantity,price,now)

    def normalize(self, pair, quantity, price, now):
        if (
            pair != self.pair
            or not self.source_sha256
            # A prospective simulation assumption is not a claimed historical
            # exchange observation. Its 2026 declaration date is preserved.
            or (self.authority_kind != 'PROSPECTIVE_DESIGN_CHOICE_NOT_HISTORICAL_EXCHANGE_RULE'
                and utc(self.available_at) > utc(now))
            or not utc(self.effective_from) <= utc(now) < utc(self.effective_until)
            or self.lot <= 0
            or min(self.min_quantity, self.min_notional) < 0
            or not all(math.isfinite(v) and v > 0 for v in (quantity, price))
        ):
            return 0.0
        qty = (Decimal(str(quantity)) / self.lot).to_integral_value(rounding=ROUND_FLOOR) * self.lot
        if qty < self.min_quantity or qty * Decimal(str(price)) < self.min_notional:
            return 0.0
        return float(qty)


@dataclass(frozen=True)
class CompletedBar:
    pair: str
    open_at: object
    close_at: object
    open: float
    high: float
    low: float
    close: float

    def validate(self, now):
        if (
            utc(self.close_at) != utc(now)
            or utc(now) >= DATA_CUTOFF
            or utc(self.open_at) + pd.Timedelta(hours=1) != utc(now)
            or not all(
                math.isfinite(v) and v > 0 for v in (self.open, self.high, self.low, self.close)
            )
            or self.low > min(self.open, self.close)
            or self.high < max(self.open, self.close)
            or self.high < self.low
        ):
            raise ValueError("COMPLETED_CAUSAL_BAR_REQUIRED")


class EventExecutionBridge:
    """Use executable opens; stop/target collision is stop-first; close actions next-open.

    This interface consumes events, not precomputed lifecycle outcome rows. It is
    Market arming requires an explicitly verified contract. The enclosing runner
    also requires the next governed task and explicit economic authorization.
    Prospective rules never become historical quantity authority through tests.
    """

    def __init__(
        self, kernel: PortfolioKernel, evidence: EvidenceStore, rules: dict, *, synthetic_fixture,
        market_contract=None
    ):
        self.market = synthetic_fixture is not True
        self.funded_scope = frozenset((market_contract or {}).get('funded_grammars',
            ('FS_ICT_2022_CORE_CRYPTO_LONG','FS_CLASSICAL_FULL_LONG') if not self.market else ()))
        if self.market and (not market_contract or not market_contract.get('source_hash_verified')
            or not self.funded_scope or not self.funded_scope <= {
                'FS_ICT_2022_CORE_CRYPTO_LONG','FS_CLASSICAL_FULL_LONG'}):
            raise PermissionError('MARKET_ADAPTER_NOT_ARMED_IN_THIS_MISSION')
        kind='PROSPECTIVE_DESIGN_CHOICE_NOT_HISTORICAL_EXCHANGE_RULE' if self.market else 'SYNTHETIC_FIXTURE'
        if any(r.authority_kind != kind for r in rules.values()):
            raise ValueError('QUANTITY_AUTHORITY_KIND_MISMATCH')
        self.kernel, self.evidence, self.rules = kernel, evidence, rules
        self.pending_exit = {}
        self.last_open = None
        self.last_close = None
        self.trace = []
        self.capacity_remaining = {}

    def _exit(self, tid, price, now, reason, capacity):
        p = self.kernel.positions[tid]
        pair = p["episode"]["pair"]
        if self.market: price=self.rules[pair].price(price,buy=False)
        cap = capacity.get(pair)
        if cap is None or not math.isfinite(cap) or cap < p["qty_current"] * price:
            # No synthetic, unlimited-liquidity liquidation of an infeasible exit.
            self.kernel.risk_breach_unresolved = True
            self.pending_exit[tid] = reason
            self.trace.append(
                {"time": str(now), "action": "EXIT_CAPACITY_BLOCKED", "reason": reason}
            )
            return False
        qty = self.rules[pair].normalize_exit(pair, p["qty_current"], price, now)
        if not math.isclose(qty, p["qty_current"], rel_tol=1e-12, abs_tol=1e-12):
            self.kernel.risk_breach_unresolved = True
            self.pending_exit[tid] = reason
            return False
        capacity[pair] -= qty * price
        self.kernel.partial_exit(tid, qty, price, now=now, reason=reason)
        self.trace.append(
            {"time": str(now), "action": "EXIT", "reason": reason, "price": price, "quantity": qty}
        )
        self.pending_exit.pop(tid, None)
        return True

    def on_open(self, now, prices: dict[str, float], capacity: dict[str, float], requests=()):
        now = utc(now)
        if now >= DATA_CUTOFF or self.last_open is not None and now <= self.last_open:
            raise ValueError("OPEN_CLOCK_OR_PROTECTED_BOUNDARY")
        if self.market and self.last_open is not None and (
            self.last_close != now or self.last_open + pd.Timedelta(hours=1) != now
        ):
            raise ValueError('MARKET_OPEN_REQUIRES_PREVIOUS_COMPLETED_BAR')
        if not all(math.isfinite(v) and v > 0 for v in prices.values()):
            raise ValueError("EXECUTABLE_OPEN_INVALID")
        capacity = dict(capacity)
        for tid, position in list(self.kernel.positions.items()):
            pair = position["episode"]["pair"]
            if pair not in prices:
                self.kernel.risk_breach_unresolved = True
                raise ValueError("MISSING_POSITION_OPEN")
            px = prices[pair]
            if px <= max(position['current_stop'],position['episode'].get('owner_stop',position['current_stop'])):
                self._exit(tid, px, now, "STRUCTURAL_STOP_GAP", capacity)
            elif px >= position["episode"]["target"]:
                self._exit(tid, position["episode"]["target"], now, "TARGET_GAP", capacity)
            elif tid in self.pending_exit:
                self._exit(tid, px, now, self.pending_exit[tid], capacity)
        owners = {
            p["episode"]["pair"]: p["episode"]["owner_structure_id"]
            for p in self.kernel.positions.values()
        }

        def marks(pair, t):
            return prices[pair]

        if not engine.current_mtm_limits_ok(self.kernel.snapshot(marks, now)):
            before = self.kernel.snapshot(marks, now)["asset"]
            def normalize_reduction(pair,qty,px,at):
                return self.rules[pair].normalize_exit(pair,qty,px,at) if pair in self.rules else 0.0
            if self.market: normalize_reduction.quantity_rules=self.rules
            fill_before=len(self.kernel.fills)
            if self.kernel.reduce_common(
                marks,
                now,
                capacity,
                normalize_reduction,
            ):
                after = self.kernel.snapshot(marks, now)["asset"]
                for pair, value in before.items():
                    capacity[pair] -= value - after.get(pair, 0.0)
            # All safety exits are explicit fills and can be reconciled. No silent fees.
            self.trace.extend(self.kernel.fills[fill_before:])
        if self.kernel.risk_breach_unresolved:
            raise ValueError('RISK_BREACH_UNRESOLVED')
        candidates = [r[0] for r in requests]
        if any(not isinstance(c, Feasibility) for c in candidates):
            raise ValueError("BOUND_FEASIBILITY_REQUIRED")
        selected, rejected = select_prebatch(candidates, self.evidence, now, owners)
        lookup = {r[0].thesis.thesis_id: r for r in requests}
        if len(lookup) != len(requests):
            raise ValueError("DUPLICATE_REQUEST")
        for thesis in selected:
            feasibility, row, campaign = lookup[thesis.thesis_id]
            if (
                row["pair"] != thesis.pair
                or row["owner_grammar"] != thesis.owner_grammar
                or row["owner_structure_id"] != thesis.owner_structure_id
                or thesis.ready_at != now
                or thesis.pair not in prices
                or thesis.pair not in self.rules
                or row["owner_grammar"]
                not in self.funded_scope
            ):
                rejected[thesis.thesis_id] = "OWNED_NEXT_OPEN_BINDING_INVALID"
                continue
            rule = self.rules[thesis.pair]
            entry=rule.price(prices[thesis.pair],buy=True) if self.market else prices[thesis.pair]
            stop=rule.price(row['stop'],buy=False) if self.market else row['stop']
            if not 0 < stop < entry < row['target']:
                rejected[thesis.thesis_id]='OPEN_OUTSIDE_FROZEN_GEOMETRY'; continue
            row = {**row, "entry_open": entry, 'owner_stop':row['stop'], 'stop':stop}
            ok, reason = self.kernel.admit(
                row,
                lambda pair, t: prices[pair],
                now,
                capacity.get(thesis.pair),
                rule.normalize,
                campaign,
                funded_ready=feasibility.thesis.funded_ready,
                is_add=thesis.action_class == "ADD",
                staged=row.get("staged", False),
            )
            if ok:
                # Participation is charged at actual executable cash notional,
                # not the (slightly different) unrounded mark of the position.
                fill=self.kernel.fills[-1]
                capacity[thesis.pair] -= fill['qty']*fill['price']
            else:
                rejected[thesis.thesis_id] = reason
        self.last_open = now
        self.capacity_remaining=capacity
        return rejected

    def on_close(self, now, bars: dict[str, CompletedBar], native_events: dict[str, dict]):
        now = utc(now)
        if self.last_open is None or self.last_open + pd.Timedelta(hours=1) != now:
            raise ValueError("CLOSE_REQUIRES_MATCHING_OPEN")
        if self.last_close is not None and now <= self.last_close:
            raise ValueError("DUPLICATE_CLOSE")
        for bar in bars.values():
            bar.validate(now)
        shared_capacity = {}
        for event in native_events.values():
            if event and ("known_at" not in event or utc(event["known_at"]) > now):
                raise ValueError("NATIVE_EVENT_AVAILABILITY_UNBOUND")
        for p in self.kernel.positions.values():
            row = p["episode"]
            if row["pair"] not in bars:
                raise ValueError("MISSING_POSITION_BAR")
            cap = self.capacity_remaining.get(row['pair']) if self.market else native_events.get(row["identity"], {}).get("exit_capacity")
            if row["pair"] not in shared_capacity:
                shared_capacity[row["pair"]] = cap
            elif cap != shared_capacity[row["pair"]]:
                raise ValueError("INCONSISTENT_SAME_ASSET_CAPACITY")
        for tid, p in list(self.kernel.positions.items()):
            row = p["episode"]
            pair = row["pair"]
            if pair not in bars:
                raise ValueError("MISSING_POSITION_BAR")
            b, event = bars[pair], native_events.get(row["identity"], {})
            cap = shared_capacity
            if b.low <= max(p["current_stop"],row.get('owner_stop',p['current_stop'])):
                self._exit(tid, p["current_stop"], now, "STRUCTURAL_STOP", cap)
                continue
            if b.high >= row["target"]:
                self._exit(tid, row["target"], now, "OBJECTIVE_REACHED", cap)
                continue
            if row["owner_grammar"] == "FS_ICT_2022_CORE_CRYPTO_LONG":
                action = runtime.ict_manage_active(
                    t=now,
                    raid_time=utc(row["raid_time"]),
                    bar_low=b.low,
                    bar_high=b.high,
                    raid_low=p["current_stop"],
                    target=row["target"],
                    bearish_mss=event.get("bearish_mss", False),
                )
                if action in {"BEARISH_MSS_EXIT_NEXT_OPEN", "NY_1600_DAY_BOUNDARY"}:
                    self.pending_exit[tid] = action
            elif row["owner_grammar"] == "FS_CLASSICAL_FULL_LONG":
                manage=classical_manage_v3 if self.market else runtime.classical_management_update
                extra={'entry_price':row['entry_open']} if self.market else {}
                decision = manage(
                    **extra,
                    price=b.close,
                    target=row["target"],
                    current_stop=p["current_stop"],
                    confirmed_higher_low=event.get("confirmed_higher_low"),
                    primary_trend="DOWN" if event.get("confirmed_primary_down") else "UP",
                    pattern_failed=event.get("pattern_failed", False),
                )
                # New completed-bar stop is not tested retroactively in this bar.
                p["current_stop"] = max(p["current_stop"], decision["stop"])
                if decision["action"] in {"EXIT_PRIMARY_TREND_REVERSAL", "EXIT_PATTERN_FAILURE"}:
                    self.pending_exit[tid] = decision["action"]
            else:
                raise ValueError("UNBOUND_NATIVE_MANAGEMENT_OWNER")
        self.last_close = now
        self.capacity_remaining=shared_capacity
