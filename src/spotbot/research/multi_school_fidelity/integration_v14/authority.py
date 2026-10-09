"""User-authorized quarantine, conservative context and immutable receipt DAG."""
from __future__ import annotations

import json
from collections.abc import MutableMapping
from dataclasses import asdict, dataclass
from datetime import timedelta

from ..school_contract_common_v8 import clock, digest, valid_sha
from ..structural_lifecycle_v6 import ContractError, instant

FUNDED = ("FS_ICT_SESSION_OWNER_V8", "FS_CLASSICAL_FULL_LONG", "HYB_FAILED_AUCTION_HTF_OWNER_V8")
QUARANTINED = {
    "FS_WYCKOFF_FRESH_CAUSE_V8": "WY_ACCUMULATION_SOURCE/WY_CONTEXT_REACCUMULATION/WY_DISTRIBUTION_MANAGEMENT",
    "HYB_MARKUP_CONTINUATION": "H1_MARKUP_PARENT",
    "FS_HARMONIC_CAUSAL_ADAPTATION_V8": "EXACT_VERSION_RESERVE_NOT_CERTIFIED",
    "FS_ELLIOTT_PROOF_RESUMPTION_V8": "RECURSIVE_HISTORICAL_OBJECTIVE_OWNER_NOT_CERTIFIED",
    "HYB_CORRECTIVE_PROOF_LOCATION_V9": "UNFUNDED_PARENT_GRAMMARS",
    "FS_DOW_CRYPTO_ADAPTED_LONG": "CONTEXT_ONLY_NO_OWNER_STOP",
}


def funded(grammar):
    if grammar not in FUNDED:
        raise ContractError("QUARANTINED_OR_UNBOUND_GRAMMAR:" + str(grammar))


@dataclass(frozen=True)
class DowPermission:
    direction: str
    complete: bool
    members_sha256: str
    available_at: object
    valid_until: object
    reason: str

    def permits(self, now):
        return (self.complete and self.direction in {"UP", "BALANCED"}
                and clock(self.available_at) <= clock(now) < instant(self.valid_until))


def dow_permission(required, observed, now, direction, *, context_at=None):
    """Missing one member is enough; no coverage fraction or permissive carry."""
    now = clock(now)
    required = frozenset(required)
    complete = bool(required) and required <= observed.keys() and all(
        clock(observed[p]) == now for p in required
    )
    at = clock(context_at or now)
    fresh = at <= now < at + timedelta(hours=4)
    allowed = direction if complete and fresh else "UNKNOWN"
    if allowed not in {"UP", "DOWN", "BALANCED", "UNKNOWN"}:
        raise ContractError("DOW_CONTEXT_DOMAIN")
    return DowPermission(allowed, complete and fresh, digest(sorted(required)), now,
                         min(now + timedelta(hours=1), at + timedelta(hours=4)),
                         "COMPLETE_FRAME" if complete and fresh else "INCOMPLETE_OR_EXPIRED_FRAME")


@dataclass(frozen=True)
class Receipt:
    receipt_id: str
    kind: str
    parents: tuple[str, ...]
    source_sha256: str
    config_sha256: str
    checkpoint: str
    available_at: str
    payload_json: str
    payload_sha256: str


class ReceiptStore(MutableMapping):
    """Replacement/deletion invalidates cached ancestry, append does not."""
    def __init__(self):
        self.data, self.epoch = {}, 0

    def __getitem__(self, key):
        return self.data[key]

    def __setitem__(self, key, value):
        if key in self.data and self.data[key] != value:
            self.epoch += 1
        self.data[key] = value

    def __delitem__(self, key):
        self.epoch += 1
        del self.data[key]

    def __iter__(self):
        return iter(self.data)

    def __len__(self):
        return len(self.data)


class ReceiptGraph:
    """Receipts authenticate retained lineage, not profitability or doctrine."""
    def __init__(self, source_sha256, config_sha256):
        valid_sha(source_sha256)
        valid_sha(config_sha256)
        self.source_sha256, self.config_sha256 = source_sha256, config_sha256
        self.nodes = ReceiptStore()
        self._dead = set()
        self._verified = {}

    @property
    def dead(self):
        return frozenset(self._dead)

    def append(self, kind, payload, now, parents=(), *, available_at=None):
        at, available = clock(now), clock(available_at or now)
        if available > at:
            raise ContractError("FUTURE_RECEIPT")
        for parent in parents:
            self.verify(parent, at)
        # Explicit stable JSON prevents mutable dictionary aliasing.
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        body = dict(kind=kind, parents=tuple(parents), source_sha256=self.source_sha256,
                    config_sha256=self.config_sha256, checkpoint=at.isoformat(),
                    available_at=available.isoformat(), payload_json=raw,
                    payload_sha256=digest(raw))
        rid = digest(body)
        receipt = Receipt(rid, **body)
        if rid in self.dead:
            raise ContractError("RECEIPT_NO_RESURRECTION")
        if rid in self.nodes and self.nodes[rid] != receipt:
            raise ContractError("RECEIPT_IMMUTABLE")
        self.nodes[rid] = receipt
        return rid

    def verify(self, rid, now, seen=None):
        # Iterative ancestry avoids recursion limits for multi-week winners.
        pending, visited, checked = [rid], set(), []
        epoch = self.nodes.epoch
        while pending:
            current = pending.pop()
            if current in visited:
                continue
            visited.add(current)
            if current in self._dead or current not in self.nodes:
                raise ContractError("RECEIPT_DEAD_OR_MISSING")
            receipt = self.nodes[current]
            if clock(receipt.checkpoint) > clock(now):
                raise ContractError("RECEIPT_TAMPER_OR_CLOCK")
            cache = (epoch, receipt, self.source_sha256, self.config_sha256)
            if self._verified.get(current) == cache:
                continue
            body = asdict(receipt)
            body.pop("receipt_id")
            if (digest(body) != current or receipt.receipt_id != current
                    or digest(receipt.payload_json) != receipt.payload_sha256
                    or receipt.source_sha256 != self.source_sha256
                    or receipt.config_sha256 != self.config_sha256
                    or clock(receipt.available_at) > clock(receipt.checkpoint)):
                raise ContractError("RECEIPT_TAMPER_OR_CLOCK")
            checked.append((current, receipt))
            for parent in receipt.parents:
                if parent not in self.nodes:
                    raise ContractError("RECEIPT_DEAD_OR_MISSING")
                if clock(self.nodes[parent].checkpoint) > clock(receipt.checkpoint):
                    raise ContractError("RECEIPT_PARENT_FROM_FUTURE")
                pending.append(parent)
        for current, receipt in checked:
            self._verified[current] = (epoch, receipt, self.source_sha256, self.config_sha256)
        return self.nodes[rid]

    def terminate(self, rid):
        if rid not in self.nodes or rid in self.dead:
            raise ContractError("RECEIPT_UNKNOWN_OR_TERMINAL")
        self._dead.add(rid)
        self.nodes.epoch += 1

    def export(self):
        return {"source_sha256": self.source_sha256, "config_sha256": self.config_sha256,
                "receipts": [asdict(r) for r in self.nodes.values()], "terminated": sorted(self.dead)}

    @classmethod
    def restore(cls, payload):
        graph = cls(payload["source_sha256"], payload["config_sha256"])
        for row in payload["receipts"]:
            row = dict(row)
            row["parents"] = tuple(row["parents"])
            receipt = Receipt(**row)
            if receipt.receipt_id in graph.nodes:
                raise ContractError("DUPLICATE_RECEIPT")
            graph.nodes[receipt.receipt_id] = receipt
        graph._dead = set(payload["terminated"])
        for receipt in graph.nodes.values():
            if receipt.receipt_id not in graph.dead:
                graph.verify(receipt.receipt_id, receipt.checkpoint)
        return graph
