"""Exact six native schools plus three distinct hybrids; no scope substitution."""
from ..integration_v14.authority import ReceiptGraph, dow_permission
from ..integration_v13.guarded_driver import GRAMMARS as EIGHT
from ..structural_lifecycle_v6 import DO, ContractError

FUNDED = (*EIGHT, DO)
QUARANTINED = {}

def funded(grammar):
    if grammar not in FUNDED:
        raise ContractError("UNBOUND_GRAMMAR_OUTSIDE_EXACT_NINE:" + str(grammar))
    return grammar
