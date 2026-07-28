"""Frozen RD07 cross-venue spot-flow protocol."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

SignalClass = Literal["CONFIRMATORY", "POST_HOC_EXTERNAL_REPLICATION"]


@dataclass(frozen=True)
class SignalSpec:
    signal_id: str
    family: str
    signal_class: SignalClass
    minimum_bars: int


SIGNALS: Final[tuple[SignalSpec, ...]] = (
    SignalSpec("BN_TAKER_BUY_IMBALANCE_1", "TAKER_FLOW", "CONFIRMATORY", 1),
    SignalSpec("BN_TAKER_BUY_IMBALANCE_6", "TAKER_FLOW", "CONFIRMATORY", 6),
    SignalSpec("BN_TAKER_BUY_IMBALANCE_18", "TAKER_FLOW", "CONFIRMATORY", 18),
    SignalSpec("BN_TAKER_BUY_IMBALANCE_ACCEL_6_42", "TAKER_FLOW", "CONFIRMATORY", 42),
    SignalSpec("BN_TRADE_COUNT_ZSCORE_42", "TRADE_ACTIVITY", "CONFIRMATORY", 42),
    SignalSpec("BN_TRADE_COUNT_ACCEL_6_42", "TRADE_ACTIVITY", "CONFIRMATORY", 42),
    SignalSpec("BN_AVG_TRADE_SIZE_ACCEL_6_42", "TRADE_ACTIVITY", "CONFIRMATORY", 42),
    SignalSpec("BN_FLOW_PRICE_CONFIRMATION_6", "FLOW_PRICE", "CONFIRMATORY", 6),
    SignalSpec("BN_KC_RETURN_DIVERGENCE_1", "LEAD_LAG", "CONFIRMATORY", 2),
    SignalSpec("BN_KC_RETURN_DIVERGENCE_6", "LEAD_LAG", "CONFIRMATORY", 7),
    SignalSpec("BN_KC_PRICE_BASIS_REVERSION_42", "PRICE_BASIS", "CONFIRMATORY", 42),
    SignalSpec("BN_KC_TURNOVER_SHARE_ACCEL_6_42", "TURNOVER_SHARE", "CONFIRMATORY", 42),
    SignalSpec("BN_LOG_MEDIAN_QUOTE_TURNOVER_42", "LIQUIDITY", "CONFIRMATORY", 42),
    SignalSpec(
        "BN_LOW_REALIZED_VOLATILITY_42",
        "QUALITY",
        "POST_HOC_EXTERNAL_REPLICATION",
        42,
    ),
)
SIGNAL_IDS: Final = tuple(item.signal_id for item in SIGNALS)
CONFIRMATORY_IDS: Final = tuple(
    item.signal_id for item in SIGNALS if item.signal_class == "CONFIRMATORY"
)
POST_HOC_IDS: Final = tuple(
    item.signal_id for item in SIGNALS if item.signal_class == "POST_HOC_EXTERNAL_REPLICATION"
)
BH_FAMILY_COUNT: Final = 14


def validate_protocol() -> None:
    if len(SIGNALS) != 14 or len(set(SIGNAL_IDS)) != 14:
        raise ValueError("RD07 requires 14 unique trials")
    if len(CONFIRMATORY_IDS) != 13 or len(POST_HOC_IDS) != 1:
        raise ValueError("RD07 signal classes do not reconcile")
