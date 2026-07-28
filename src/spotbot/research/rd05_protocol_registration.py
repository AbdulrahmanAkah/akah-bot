"""Frozen RD05 alpha-discovery registry; it intentionally performs no market evaluation."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Final

PROTOCOL_STAGE: Final = "RD05-P0-PROTOCOL-REGISTRATION"
PROTOCOL_DECISION: Final = "RD05_ALPHA_DISCOVERY_PROTOCOL_REGISTERED"
NEXT_STAGE: Final = "RD05-P1-SIGNAL-DATA-CONTRACT-AND-SOURCE-FREEZE"


@dataclass(frozen=True)
class SignalVariant:
    signal_id: str
    family_id: str
    formula_specification: str
    required_sources: tuple[str, ...]
    execution_status: str = "REGISTERED_NOT_EXECUTED"


@dataclass(frozen=True)
class LabelSpec:
    label_id: str
    horizon_days: int
    convention: str
    missing_horizon_handling: str = "EXCLUDE_AND_REPORT"
    execution_status: str = "REGISTERED_NOT_COMPUTED"


SAFETY: Final[dict[str, bool]] = {
    "spot_only": True,
    "long_only": True,
    "no_leverage": True,
    "no_margin": True,
    "no_futures": True,
    "no_shorts": True,
    "no_borrowing": True,
    "no_interest": True,
    "no_dca": True,
    "no_kelly": True,
    "no_averaging_down": True,
    "no_pyramiding": True,
    "test_2025_accessed": False,
    "holdout_2026_accessed": False,
    "point_in_time_universe_research_baseline_authorized": False,
    "portfolio_simulation_authorized": False,
    "production_change_authorized": False,
    "live_ready": False,
    "production_ready": False,
    "ati_v1_authorized": False,
    "trade_logic_changed": False,
}

FAMILY_VARIANTS: Final[dict[str, tuple[tuple[str, str, tuple[str, ...]], ...]]] = {
    "CROSS_SECTIONAL_MOMENTUM": (
        ("XSM_RETURN_7D", "7D close return rank", ("OHLCV_1D",)),
        ("XSM_RETURN_28D", "28D close return rank", ("OHLCV_1D",)),
        ("XSM_RETURN_84D", "84D close return rank", ("OHLCV_1D",)),
        ("XSM_28D_SKIP_1D", "28D return excluding latest 1D", ("OHLCV_1D",)),
    ),
    "TIME_SERIES_TREND": (
        ("TSM_RETURN_28D", "own 28D close return", ("OHLCV_1D",)),
        ("TSM_RETURN_84D", "own 84D close return", ("OHLCV_1D",)),
        ("EMA_20_50_TREND_STATE", "EMA20 minus EMA50 state", ("OHLCV_1D",)),
        ("MULTI_HORIZON_TREND_AGREEMENT", "registered trend-horizon agreement", ("OHLCV_1D",)),
    ),
    "REVERSAL_AND_OVEREXTENSION": (
        ("REVERSAL_1D_VOL_NORMALIZED", "negative 1D return divided by volatility", ("OHLCV_1D",)),
        ("REVERSAL_3D_VOL_NORMALIZED", "negative 3D return divided by volatility", ("OHLCV_1D",)),
        ("DISTANCE_FROM_EMA20_ATR", "negative EMA20 distance in ATR units", ("OHLCV_1D",)),
        ("RSI14_OVEREXTENSION", "negative RSI14 rank", ("OHLCV_1D",)),
    ),
    "BREAKOUT_AND_VOLATILITY_EXPANSION": (
        ("DONCHIAN_20_POSITION", "20D Donchian position", ("OHLCV_1D",)),
        ("DONCHIAN_55_POSITION", "55D Donchian position", ("OHLCV_1D",)),
        ("VOLATILITY_CONTRACTION_BREAKOUT", "causal contraction then breakout", ("OHLCV_1D",)),
        ("ATR_EXPANSION_WITH_POSITIVE_RETURN", "ATR expansion and positive return", ("OHLCV_1D",)),
    ),
    "TREND_QUALITY": (
        ("RETURN_PATH_EFFICIENCY_28D", "net return divided by path length", ("OHLCV_1D",)),
        ("OLS_TREND_TSTAT_28D", "28D OLS trend t-statistic", ("OHLCV_1D",)),
        ("POSITIVE_BAR_BREADTH_28D", "share of positive daily bars", ("OHLCV_1D",)),
        ("DRAWDOWN_ADJUSTED_MOMENTUM_28D", "28D return adjusted by drawdown", ("OHLCV_1D",)),
    ),
    "VOLUME_AND_ATTENTION_PROXY": (
        ("VOLUME_ZSCORE_30D", "30D base-volume z-score", ("OHLCV_1D",)),
        ("VOLUME_ACCELERATION_7D_30D", "7D versus 30D base-volume change", ("OHLCV_1D",)),
        ("PRICE_VOLUME_CONFIRMATION_28D", "28D price-volume confirmation", ("OHLCV_1D",)),
        ("QUOTE_TURNOVER_CHANGE_7D_30D", "7D versus 30D quote turnover", ("QUOTE_TURNOVER_4H",)),
    ),
    "RESIDUAL_AND_MARKET_RELATIVE": (
        ("BTC_RELATIVE_RETURN_28D", "28D asset return minus BTC", ("OHLCV_1D",)),
        (
            "MARKET_RESIDUAL_MOMENTUM_28D",
            "28D residual versus causal market",
            ("OHLCV_1D", "PIT_MEMBERSHIP"),
        ),
        ("BETA_ADJUSTED_MOMENTUM_28D", "28D return adjusted by trailing BTC beta", ("OHLCV_1D",)),
        (
            "IDIOSYNCRATIC_STRENGTH_28D",
            "28D positive residual strength",
            ("OHLCV_1D", "PIT_MEMBERSHIP"),
        ),
    ),
    "RISK_AND_QUALITY_DESCRIPTOR": (
        ("REALIZED_VOLATILITY_28D", "28D realized volatility rank", ("OHLCV_1D",)),
        ("DOWNSIDE_VOLATILITY_28D", "28D downside volatility rank", ("OHLCV_1D",)),
        ("MAX_DRAWDOWN_28D", "28D drawdown resilience rank", ("OHLCV_1D",)),
        ("ILLIQUIDITY_PROXY_30D", "30D return-to-volume illiquidity", ("OHLCV_1D",)),
        ("AGE_OR_TENURE", "causal KuCoin availability tenure", ("AVAILABILITY",)),
    ),
}

SIGNAL_FAMILIES: Final[tuple[dict[str, str], ...]] = tuple(
    {"family_id": family, "execution_status": "REGISTERED_NOT_EXECUTED"}
    for family in FAMILY_VARIANTS
)
SIGNAL_VARIANTS: Final[tuple[SignalVariant, ...]] = tuple(
    SignalVariant(identifier, family, formula, sources)
    for family, variants in FAMILY_VARIANTS.items()
    for identifier, formula, sources in variants
)
LABELS: Final[tuple[LabelSpec, ...]] = (
    LabelSpec("FORWARD_7D_CLOSE_TO_CLOSE_RETURN", 7, "next eligible close-to-close"),
    LabelSpec("FORWARD_1D_RETURN", 1, "next eligible close-to-close"),
    LabelSpec("FORWARD_3D_RETURN", 3, "next eligible close-to-close"),
    LabelSpec("FORWARD_14D_RETURN", 14, "next eligible close-to-close"),
    LabelSpec("FORWARD_28D_RETURN", 28, "next eligible close-to-close"),
    LabelSpec("FORWARD_7D_MAX_FAVOURABLE_EXCURSION", 7, "next eligible high"),
    LabelSpec("FORWARD_7D_MAX_ADVERSE_EXCURSION", 7, "next eligible low"),
)
REGIMES: Final[tuple[dict[str, str], ...]] = (
    {"regime_id": "BTC_TREND_STATE", "threshold_contract": "closed bars only"},
    {
        "regime_id": "BTC_REALIZED_VOLATILITY_TERCILE",
        "threshold_contract": "expanding-history tertiles; min 180 observations",
    },
    {
        "regime_id": "CROSS_SECTIONAL_DISPERSION_TERCILE",
        "threshold_contract": "expanding-history tertiles; min 180 observations",
    },
    {
        "regime_id": "AVERAGE_PAIRWISE_CORRELATION_TERCILE",
        "threshold_contract": "expanding-history tertiles; min 180 observations",
    },
    {
        "regime_id": "MARKET_BREADTH_TERCILE",
        "threshold_contract": "expanding-history tertiles; min 180 observations",
    },
    {
        "regime_id": "PIT_UNIVERSE_SIZE_TERCILE",
        "threshold_contract": "expanding-history tertiles; min 180 observations",
    },
)
STAGES: Final[tuple[str, ...]] = (
    PROTOCOL_STAGE,
    "RD05-P1-SIGNAL-DATA-CONTRACT-AND-SOURCE-FREEZE",
    "RD05-P2-CAUSAL-SYMBOL-TIME-PANEL-BUILD",
    "RD05-S1-PRIMITIVE-SIGNAL-DIAGNOSTIC",
    "RD05-S2-REGIME-CONDITIONAL-REPLICATION",
    "RD05-S3-SIGNAL-ORTHOGONALITY",
    "RD05-S4-ENSEMBLE-PROTOCOL",
    "RD05-M1-MINIMAL-LONG-ONLY-PORTFOLIO",
    "RD05-R1-COST-AND-FOLD-ROBUSTNESS",
    "RD05-FINAL-PRE-HOLDOUT-ADJUDICATION",
)
GATES: Final[dict[str, float | int]] = {
    "mean_rank_ic_minimum": 0.02,
    "ic_information_ratio_minimum": 0.20,
    "positive_ic_period_share_minimum": 0.55,
    "minimum_positive_folds": 2,
    "top_quintile_excess_return_minimum": 0.0,
    "maximum_single_symbol_contribution": 0.25,
    "maximum_missing_label_share": 0.05,
    "adjusted_p_value_maximum": 0.05,
    "minimum_regime_cells_expected_direction": 2,
}
TRIAL_BUDGET: Final[dict[str, int]] = {
    "maximum_primitive_trials": 33,
    "maximum_regime_interactions": 198,
    "maximum_ensemble_candidates": 28,
    "maximum_model_families": 2,
    "total_declared_trial_count": 261,
}


class RD05ProtocolError(ValueError):
    """Raised on unsafe or inconsistent RD05 registration."""


def validate_protocol() -> None:
    identifiers = [variant.signal_id for variant in SIGNAL_VARIANTS]
    if len(identifiers) != 33 or len(set(identifiers)) != 33:
        raise RD05ProtocolError("RD05 requires exactly 33 unique variants")
    if len(LABELS) != 7 or max(label.horizon_days for label in LABELS) != 28:
        raise RD05ProtocolError("future-label registry mismatch")
    if len(REGIMES) != 6 or len(STAGES) != 10:
        raise RD05ProtocolError("regime or stage registry mismatch")
    if TRIAL_BUDGET["total_declared_trial_count"] != 261:
        raise RD05ProtocolError("trial budget mismatch")
    if any(
        SAFETY[key]
        for key in (
            "test_2025_accessed",
            "holdout_2026_accessed",
            "portfolio_simulation_authorized",
        )
    ):
        raise RD05ProtocolError("locked data or portfolio authorization is unsafe")


def variant_by_id(signal_id: str) -> SignalVariant:
    for variant in SIGNAL_VARIANTS:
        if variant.signal_id == signal_id:
            return variant
    raise RD05ProtocolError(f"undeclared signal variant: {signal_id}")


def build_protocol(upstream_hashes: dict[str, str]) -> dict[str, Any]:
    validate_protocol()
    return {
        "schema_version": "ams-rd05-protocol-registration-v1",
        "research_stage": PROTOCOL_STAGE,
        "status": "COMPLETE",
        "decision": {
            "decision": PROTOCOL_DECISION,
            "next_stage": NEXT_STAGE,
            "rd05_signal_data_contract_and_panel_build_authorized": True,
            "portfolio_simulation_authorized": False,
            "production_change_authorized": False,
        },
        "upstream_hashes": upstream_hashes,
        "signal_family_count": len(SIGNAL_FAMILIES),
        "signal_variant_count": len(SIGNAL_VARIANTS),
        "label_count": len(LABELS),
        "regime_count": len(REGIMES),
        "stage_count": len(STAGES),
        "trial_budget": TRIAL_BUDGET,
        "primitive_signal_pass_gate": GATES,
        "early_termination_gate": {
            "decision": "RD05_PRIMITIVE_SIGNAL_EDGE_NOT_CONFIRMED",
            "next_stage": "RD05_RESEARCH_TERMINATION_OR_NEW_DATA_PROTOCOL",
            "portfolio_construction_authorized": False,
        },
        "multiple_testing_controls": [
            "adjusted significance",
            "decision-time clustered bootstrap",
            "DSR when portfolio returns later exist",
            "CSCV/PBO when applicable",
            "all trials ledger",
        ],
        "conditional_ml": {
            "authorized_now": False,
            "model_families": ["regularized_linear", "gradient_boosted_trees"],
        },
        "safety": SAFETY,
        "execution_status": "PROTOCOL_REGISTERED_NO_DATA_EVALUATED",
    }


def variant_rows() -> list[dict[str, Any]]:
    return [asdict(variant) for variant in SIGNAL_VARIANTS]


def label_rows() -> list[dict[str, Any]]:
    return [asdict(label) for label in LABELS]


def text_contract_valid(value: str) -> bool:
    return value.endswith("\n") and all(line == line.rstrip(" \t") for line in value.splitlines())
