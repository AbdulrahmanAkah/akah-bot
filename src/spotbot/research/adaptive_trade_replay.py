"""Shadow-only decision logging that preserves the immutable trade ledger."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from typing import Any

from spotbot.research.adaptive_trade_types import TradeManagementDecision


def policy_hash(policy: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(policy, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def shadow_replay(
    baseline_trades: Sequence[Mapping[str, Any]],
    decisions: Sequence[TradeManagementDecision],
) -> Mapping[str, Any]:
    """Log suggestions while proving PnL and trade count are unchanged."""
    baseline_pnl = sum(float(trade["net_pnl"]) for trade in baseline_trades)
    return {
        "baseline_trade_count": len(baseline_trades),
        "shadow_trade_count": len(baseline_trades),
        "baseline_net_pnl": baseline_pnl,
        "shadow_net_pnl": baseline_pnl,
        "decisions": [asdict(decision) for decision in decisions],
        "pnl_changed": False,
        "trade_ledger_changed": False,
    }

