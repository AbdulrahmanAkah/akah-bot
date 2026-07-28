"""Frozen RD08 market-state timing protocol."""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class SignalSpec:
    signal_id: str
    signal_class: str
    required_source: str


SIGNALS = (
    SignalSpec("MKT_PIT_EW_RETURN_6BAR", "CONFIRMATORY", "KUCOIN"),
    SignalSpec("MKT_PIT_EW_RETURN_18BAR", "CONFIRMATORY", "KUCOIN"),
    SignalSpec("MKT_PIT_EW_RETURN_42BAR", "CONFIRMATORY", "KUCOIN"),
    SignalSpec("MKT_BREADTH_POSITIVE_6BAR", "CONFIRMATORY", "KUCOIN"),
    SignalSpec("MKT_BREADTH_THRUST_6_42", "CONFIRMATORY", "KUCOIN"),
    SignalSpec("MKT_BREADTH_ABOVE_EMA20", "CONFIRMATORY", "KUCOIN"),
    SignalSpec("MKT_CROSS_SECTIONAL_DISPERSION_42", "CONFIRMATORY", "KUCOIN"),
    SignalSpec("MKT_DISPERSION_ACCEL_18_42", "CONFIRMATORY", "KUCOIN"),
    SignalSpec("MKT_AVG_PAIRWISE_CORRELATION_42", "CONFIRMATORY", "KUCOIN"),
    SignalSpec("MKT_CORRELATION_CHANGE_18_42", "CONFIRMATORY", "KUCOIN"),
    SignalSpec("MKT_AGG_QUOTE_TURNOVER_ACCEL_6_42", "CONFIRMATORY", "KUCOIN"),
    SignalSpec("MKT_BN_AGG_TAKER_IMBALANCE_6", "CONFIRMATORY", "BINANCE"),
    SignalSpec("MKT_BN_KC_RETURN_DIVERGENCE_6", "CONFIRMATORY", "CROSS_VENUE"),
    SignalSpec(
        "MKT_LOW_REALIZED_VOLATILITY_42",
        "POST_HOC_MARKET_LEVEL_REPLICATION",
        "KUCOIN",
    ),
)

LABELS = (
    "PIT_EQUAL_WEIGHT_FORWARD_24H_RETURN",
    "BTC_SPOT_FORWARD_24H_RETURN",
    "BINANCE_MATCHED_EQUAL_WEIGHT_FORWARD_24H_RETURN",
    "PIT_EQUAL_WEIGHT_FORWARD_72H_RETURN",
    "PIT_EQUAL_WEIGHT_FORWARD_7D_RETURN",
    "BTC_SPOT_FORWARD_72H_RETURN",
    "BTC_SPOT_FORWARD_7D_RETURN",
    "BINANCE_MATCHED_EQUAL_WEIGHT_FORWARD_72H_RETURN",
    "BINANCE_MATCHED_EQUAL_WEIGHT_FORWARD_7D_RETURN",
)

PROHIBITED_SIGNAL_CLASSES = (
    "individual-asset momentum",
    "individual-asset reversal",
    "individual-asset low volatility",
    "individual-asset age",
    "individual-asset turnover",
    "individual-asset taker imbalance",
    "individual-asset cross-venue divergence",
)


def protocol_payload() -> dict[str, object]:
    return {
        "stage": "RD08-P0-MARKET-STATE-TIMING-PROTOCOL",
        "status": "COMPLETE",
        "decision": "RD08_MARKET_STATE_TIMING_PROTOCOL_REGISTERED",
        "next_stage": "RD08-P1-MARKET-STATE-CAUSAL-PANEL",
        "panel_grain": "decision_time|grid_id",
        "signal_count": len(SIGNALS),
        "confirmatory_trials": 13,
        "post_hoc_trials": 1,
        "bh_family_count": 14,
        "additional_parameter_variants": 0,
        "signals": [asdict(item) for item in SIGNALS],
        "labels": list(LABELS),
        "cross_sectional_price_volume_flow_space_closed": True,
        "prohibited_signal_classes": list(PROHIBITED_SIGNAL_CLASSES),
        "portfolio_simulation_authorized": False,
        "portfolio_construction_authorized": False,
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
    }
