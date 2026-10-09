"""Declare the existing finite grammar; do not invent truncated-fifth rules."""

from ..elliott_contract_v8 import ElliottBook as LegacyBook
from ..structural_lifecycle_v6 import ContractError

PROFILE = "NONTRUNCATED_IMPULSE_PROFILE"
UNSUPPORTED = "TRUNCATED_FIFTH_DIAGNOSTIC_ONLY_NOT_IMPLEMENTED"


def check_wave(w):
    if w.kind == "IMPULSE" and len(w.points) == 6:
        s = w.sign
        z = [s * p.price for p in w.points]
        # This is a scope dispatch, NOT relaxed geometry or a tradable count.
        if z[5] <= z[3]:
            raise ContractError("UNSUPPORTED_TRUNCATED_PROFILE_DIAGNOSTIC_ONLY")
    for child in w.children:
        check_wave(child)


def check_count(c):
    check_wave(c.correction)
    for w in c.parent_prefix.children:
        check_wave(w)
    if len(c.parent_prefix.points) == 6:
        ps = c.parent_prefix.points
        sign = 1 if ps[1].price > ps[0].price else -1
        if sign * ps[5].price <= sign * ps[3].price:
            raise ContractError("UNSUPPORTED_TRUNCATED_PROFILE_DIAGNOSTIC_ONLY")


class ElliottBook(LegacyBook):
    profile = PROFILE

    def add(self, count, now):
        check_count(count)
        return super().add(count, now)

    def decide(self, now, close, claim):
        for cid, c in self.counts.items():
            if cid not in self.tombstones:
                check_count(c)
        return super().decide(now, close, claim)
