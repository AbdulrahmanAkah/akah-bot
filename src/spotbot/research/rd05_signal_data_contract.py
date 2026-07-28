"""RD05 P1 source-freeze contracts.

This module deliberately contains contracts and integrity helpers only.  It must
not calculate signal values, forward labels, ranks, returns, or portfolios.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from typing import Final

from spotbot.research.rd05_protocol_registration import LABELS, REGIMES, SAFETY, SIGNAL_VARIANTS

RESEARCH_START: Final = datetime(2021, 1, 1, tzinfo=UTC)
RESEARCH_END: Final = datetime(2025, 1, 1, tzinfo=UTC)
P1_STAGE: Final = "RD05-P1-SIGNAL-DATA-CONTRACT-AND-SOURCE-FREEZE"
P2_STAGE: Final = "RD05-P2-CAUSAL-SYMBOL-TIME-PANEL-BUILD"
CRITICAL_SOURCES: Final = ("OHLCV_1D", "OHLCV_4H", "AVAILABILITY", "PIT_MEMBERSHIP")
SUPPORTING_SOURCES: Final = ("OHLCV_8H",)
OPTIONAL_SOURCES: Final = ("QUOTE_TURNOVER_4H",)
MAX_LOOKBACK_DAYS: Final = 84
MAX_FORWARD_HORIZON_DAYS: Final = 28


class P1ContractError(ValueError):
    """Raised if a frozen P1 contract is internally inconsistent."""


@dataclass(frozen=True)
class LabelContract:
    label_id: str
    horizon_days: int
    source_timeframe: str
    end_price_convention: str

    @property
    def last_permissible_decision_time(self) -> datetime:
        return RESEARCH_END - timedelta(days=self.horizon_days)


LABEL_CONTRACTS: Final = tuple(
    LabelContract(
        label_id=label.label_id,
        horizon_days=label.horizon_days,
        source_timeframe="1D",
        end_price_convention=(
            "close"
            if "RETURN" in label.label_id
            else "high"
            if "FAVOURABLE" in label.label_id
            else "low"
        ),
    )
    for label in LABELS
)


def file_sha256(path: Path) -> str:
    """Return the full-file SHA256 used by the registered-source contract."""
    digest = sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1_048_576), b""):
            digest.update(block)
    return digest.hexdigest()


def ensure_research_boundary(
    open_times: Iterable[datetime], close_times: Iterable[datetime]
) -> None:
    """Reject rows that would access locked 2025/2026 bars."""
    for opened, closed in zip(open_times, close_times, strict=True):
        if opened.tzinfo is None or closed.tzinfo is None:
            raise P1ContractError("timestamps must be UTC-aware")
        if opened >= RESEARCH_END or closed > RESEARCH_END:
            raise P1ContractError("research-boundary violation")


def closed_bar_eligible(
    bar_open_time: datetime, bar_close_time: datetime, decision_time: datetime
) -> bool:
    """Implement the frozen decision-time cutoff without looking into a partial bar."""
    return bar_open_time < decision_time and bar_close_time <= decision_time


def expected_label_ids() -> tuple[str, ...]:
    return tuple(item.label_id for item in LABEL_CONTRACTS)


def formula_rows(source_status: dict[str, str]) -> list[dict[str, object]]:
    """Freeze deterministic P2 formulas; no values are calculated here."""
    specifics = {
        "EMA_20_50_TREND_STATE": (
            "EMA(close, span=20/50, adjust=False, min_periods=50): EMA20-EMA50"
        ),
        "MULTI_HORIZON_TREND_AGREEMENT": (
            "BLOCKED_FORMULA_AMBIGUITY: horizon agreement was not frozen in P0"
        ),
        "REVERSAL_1D_VOL_NORMALIZED": "-r1 / sample_std(log_returns, 28, ddof=1)",
        "REVERSAL_3D_VOL_NORMALIZED": "-r3 / sample_std(log_returns, 28, ddof=1)",
        "DISTANCE_FROM_EMA20_ATR": "-(close-EMA20)/Wilder_ATR14",
        "RSI14_OVEREXTENSION": "-Wilder_RSI14(close)",
        "VOLATILITY_CONTRACTION_BREAKOUT": (
            "BLOCKED_FORMULA_AMBIGUITY: contraction and breakout windows absent"
        ),
        "ATR_EXPANSION_WITH_POSITIVE_RETURN": (
            "BLOCKED_FORMULA_AMBIGUITY: ATR comparison window absent"
        ),
        "DRAWDOWN_ADJUSTED_MOMENTUM_28D": "r28 / max(abs(drawdown_28d), 0.01)",
        "PRICE_VOLUME_CONFIRMATION_28D": "sign(r28) * log(mean(volume,7)/mean(volume,30))",
        "MARKET_RESIDUAL_MOMENTUM_28D": (
            "BLOCKED_FORMULA_AMBIGUITY: market construction/beta window absent"
        ),
        "BETA_ADJUSTED_MOMENTUM_28D": "BLOCKED_FORMULA_AMBIGUITY: beta lookback/estimator absent",
        "IDIOSYNCRATIC_STRENGTH_28D": "BLOCKED_FORMULA_AMBIGUITY: residual construction absent",
        "ILLIQUIDITY_PROXY_30D": "mean(abs(daily_return)/base_volume, 30)",
        "AGE_OR_TENURE": "calendar days from causal tradable_from to decision_time",
        "QUOTE_TURNOVER_CHANGE_7D_30D": (
            "mean(native_quote_turnover, 7D) / mean(native_quote_turnover, 30D)-1"
        ),
    }
    rows: list[dict[str, object]] = []
    for variant in SIGNAL_VARIANTS:
        formula = specifics.get(variant.signal_id, variant.formula_specification)
        sources_ready = all(
            source_status.get(source) == "SOURCE_READY" for source in variant.required_sources
        )
        ambiguous = formula.startswith("BLOCKED_FORMULA_AMBIGUITY")
        status = (
            "SOURCE_READY"
            if sources_ready and not ambiguous
            else ("BLOCKED_FORMULA_AMBIGUITY" if ambiguous else "BLOCKED_SOURCE")
        )
        rows.append(
            {
                "signal_id": variant.signal_id,
                "family_id": variant.family_id,
                "economic_direction": "HIGHER_SCORE_PREFERRED",
                "required_sources": "|".join(variant.required_sources),
                "required_raw_columns": "close|high|low|volume|availability as applicable",
                "decision_cutoff": "bar_close_time <= decision_time; bar_open_time < decision_time",
                "lookback_length": "REGISTERED_IN_FORMULA",
                "minimum_observations": "lookback complete",
                "warmup_requirement": "exclude until complete; never impute",
                "missing_input_behavior": "EXCLUDE_AND_REPORT",
                "cross_sectional_or_time_series": (
                    "CROSS_SECTIONAL"
                    if variant.signal_id.startswith("XSM")
                    else "TIME_SERIES_SCORE"
                ),
                "rank_direction": "DESCENDING",
                "tie_handling": "stable symbol ascending secondary key",
                "winsorization": "NONE_REGISTERED",
                "normalization": "NONE_REGISTERED_UNTIL_S1",
                "formula_determinism": formula,
                "source_readiness": status,
                "p2_build_eligibility": status == "SOURCE_READY",
            }
        )
    return rows


def regime_rows() -> list[dict[str, object]]:
    """Register causal regime definitions without calculating a single regime value."""
    formulas = {
        "BTC_TREND_STATE": "BTC close > 84D SMA; < 84D SMA; else NEUTRAL",
        "BTC_REALIZED_VOLATILITY_TERCILE": "28D sample std log returns; expanding tertiles",
        "CROSS_SECTIONAL_DISPERSION_TERCILE": (
            "cross-sectional std of eligible 28D returns; expanding tertiles"
        ),
        "AVERAGE_PAIRWISE_CORRELATION_TERCILE": (
            "28D Pearson daily-return correlations; expanding tertiles"
        ),
        "MARKET_BREADTH_TERCILE": (
            "eligible-symbol share with positive 28D return; expanding tertiles"
        ),
        "PIT_UNIVERSE_SIZE_TERCILE": "count of PIT-eligible symbols; expanding tertiles",
    }
    return [
        {
            "regime_id": item["regime_id"],
            "required_source": "OHLCV_1D|PIT_MEMBERSHIP",
            "formula": formulas[item["regime_id"]],
            "observation_unit": "decision_time",
            "lookback": "28D or 84D as formula states",
            "minimum_180_observation_rule": True,
            "expanding_history_cutoff": "strictly before decision_time",
            "tercile_quantile_convention": "lower inclusive, stable ties by prior threshold",
            "tie_handling": "retain previous state on exact boundary",
            "insufficient_history_state": "INSUFFICIENT_HISTORY",
            "decision_time_causality": "closed bars and known membership only",
        }
        for item in REGIMES
    ]


def validate_contracts() -> None:
    if len(SIGNAL_VARIANTS) != 33 or len(LABEL_CONTRACTS) != 7 or len(REGIMES) != 6:
        raise P1ContractError("P0 registry counts changed")
    if max(contract.horizon_days for contract in LABEL_CONTRACTS) != MAX_FORWARD_HORIZON_DAYS:
        raise P1ContractError("label horizon contract changed")
    if any(SAFETY[key] for key in ("test_2025_accessed", "holdout_2026_accessed")):
        raise P1ContractError("locked data access is unsafe")
