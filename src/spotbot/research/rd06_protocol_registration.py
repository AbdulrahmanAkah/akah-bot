"""Frozen RD06 intraweek alpha-discovery protocol."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

GridId = Literal["PRIMARY_GRID", "REPLICATION_A", "REPLICATION_B"]
SignalClass = Literal["CONFIRMATORY_NOVEL", "POST_HOC_DIRECTIONAL_REPLICATION"]


@dataclass(frozen=True)
class SignalSpec:
    signal_id: str
    family: str
    signal_class: SignalClass
    minimum_bars: int


SIGNALS: Final[tuple[SignalSpec, ...]] = (
    SignalSpec("REVERSAL_1BAR_VOL_NORMALIZED", "REVERSAL", "CONFIRMATORY_NOVEL", 43),
    SignalSpec("REVERSAL_3BAR_VOL_NORMALIZED", "REVERSAL", "CONFIRMATORY_NOVEL", 43),
    SignalSpec("REVERSAL_6BAR_VOL_NORMALIZED", "REVERSAL", "CONFIRMATORY_NOVEL", 43),
    SignalSpec("DISTANCE_FROM_EMA20_ATR_4H", "REVERSAL", "CONFIRMATORY_NOVEL", 20),
    SignalSpec("RETURN_6BAR", "CONTINUATION", "CONFIRMATORY_NOVEL", 7),
    SignalSpec("RETURN_18BAR", "CONTINUATION", "CONFIRMATORY_NOVEL", 19),
    SignalSpec("RETURN_42BAR", "CONTINUATION", "CONFIRMATORY_NOVEL", 43),
    SignalSpec("XSM_18BAR_SKIP_1BAR", "CONTINUATION", "CONFIRMATORY_NOVEL", 20),
    SignalSpec("DONCHIAN_42_POSITION", "BREAKOUT", "CONFIRMATORY_NOVEL", 43),
    SignalSpec("PATH_EFFICIENCY_42BAR", "PATH_QUALITY", "CONFIRMATORY_NOVEL", 43),
    SignalSpec(
        "VOLATILITY_CONTRACTION_BREAKOUT_4H",
        "VOLATILITY",
        "CONFIRMATORY_NOVEL",
        142,
    ),
    SignalSpec("QUOTE_TURNOVER_ACCELERATION_6_42", "TURNOVER", "CONFIRMATORY_NOVEL", 42),
    SignalSpec("PRICE_TURNOVER_CONFIRMATION_18", "TURNOVER", "CONFIRMATORY_NOVEL", 42),
    SignalSpec(
        "LOW_REALIZED_VOLATILITY_42",
        "QUALITY_REPLICATION",
        "POST_HOC_DIRECTIONAL_REPLICATION",
        43,
    ),
    SignalSpec(
        "DRAWDOWN_RESILIENCE_42",
        "QUALITY_REPLICATION",
        "POST_HOC_DIRECTIONAL_REPLICATION",
        42,
    ),
)
SIGNAL_IDS: Final = tuple(item.signal_id for item in SIGNALS)
CONFIRMATORY_IDS: Final = tuple(
    item.signal_id for item in SIGNALS if item.signal_class == "CONFIRMATORY_NOVEL"
)
POST_HOC_IDS: Final = tuple(
    item.signal_id for item in SIGNALS if item.signal_class == "POST_HOC_DIRECTIONAL_REPLICATION"
)
LABEL_IDS: Final = (
    "FORWARD_24H_RETURN",
    "FORWARD_72H_RETURN",
    "FORWARD_7D_RETURN",
    "FORWARD_24H_MFE",
    "FORWARD_24H_MAE",
)
REGIME_IDS: Final = (
    "BTC_TREND_STATE",
    "BTC_REALIZED_VOLATILITY_TERCILE",
    "CROSS_SECTIONAL_DISPERSION_TERCILE",
    "AVERAGE_PAIRWISE_CORRELATION_TERCILE",
    "MARKET_BREADTH_TERCILE",
    "PIT_UNIVERSE_SIZE_TERCILE",
)
GRIDS: Final[dict[GridId, int]] = {
    "PRIMARY_GRID": 0,
    "REPLICATION_A": 8,
    "REPLICATION_B": 16,
}
TRIAL_COUNT: Final = 15
BOOTSTRAP_REPLICATIONS: Final = 10_000
BOOTSTRAP_BLOCK_LENGTH: Final = 7


def validate_protocol() -> None:
    if len(SIGNALS) != 15 or len(set(SIGNAL_IDS)) != 15:
        raise ValueError("RD06 must contain exactly 15 unique trials")
    if len(CONFIRMATORY_IDS) != 13 or len(POST_HOC_IDS) != 2:
        raise ValueError("RD06 trial classes do not reconcile")
    if len(LABEL_IDS) != 5 or len(REGIME_IDS) != 6 or len(GRIDS) != 3:
        raise ValueError("RD06 registry count mismatch")
