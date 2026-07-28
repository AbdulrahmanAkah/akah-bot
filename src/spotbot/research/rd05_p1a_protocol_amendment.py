"""Frozen RD05 P1A coverage and formula amendment, registered before P2."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Final

from spotbot.research.rd05_protocol_registration import SIGNAL_VARIANTS, TRIAL_BUDGET

STAGE: Final = "RD05-P1A-PROTOCOL-AMENDMENT"
DECISION: Final = "RD05_PROTOCOL_AMENDMENT_REGISTERED"
NEXT_STAGE: Final = "RD05-P1-RE-ADJUDICATION"


@dataclass(frozen=True)
class AmendedFold:
    fold_id: str
    train_start: str
    train_end: str
    validation_start: str
    validation_end: str


FOLDS: Final = (
    AmendedFold("WF01", "2022-01-03", "2022-11-28", "2023-01-02", "2023-06-26"),
    AmendedFold("WF02", "2022-01-03", "2023-05-29", "2023-07-03", "2023-12-25"),
    AmendedFold("WF03", "2022-01-03", "2023-11-27", "2024-01-01", "2024-12-23"),
)

FORMULAS: Final[dict[str, str]] = {
    "MULTI_HORIZON_TREND_AGREEMENT": "(sign(r7)+sign(r28)+sign(r84))/3; complete 84D",
    "VOLATILITY_CONTRACTION_BREAKOUT": (
        "Wilder ATR14; 60D median normalized prior ATR; prior 20D high"
    ),
    "ATR_EXPANSION_WITH_POSITIVE_RETURN": "Wilder ATR14 / prior 20 ATR mean -1 times max(r1,0)",
    "MARKET_RESIDUAL_MOMENTUM_28D": (
        "84 paired OLS intercept market model; 60 min; sum last 28 residuals"
    ),
    "BETA_ADJUSTED_MOMENTUM_28D": (
        "84 paired OLS intercept BTC beta; 60 min; 28D asset less beta BTC"
    ),
    "IDIOSYNCRATIC_STRENGTH_28D": "market residual sum 28 / (sample std residual84 * sqrt(28))",
}


def timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=UTC)


def validate_amendment() -> None:
    if len(SIGNAL_VARIANTS) != 33 or len(FORMULAS) != 6:
        raise ValueError("RD05 P1A formula registry mismatch")
    if TRIAL_BUDGET["total_declared_trial_count"] != 261:
        raise ValueError("trial budget changed")
    for fold in FOLDS:
        if (timestamp(fold.validation_start) - timestamp(fold.train_end)).days < 28:
            raise ValueError(f"purge/embargo is too short: {fold.fold_id}")


def amendment_document() -> dict[str, object]:
    validate_amendment()
    return {
        "schema_version": "ams-rd05-p1a-protocol-amendment-v1",
        "research_stage": STAGE,
        "status": "COMPLETE",
        "decision": {"decision": DECISION, "next_stage": NEXT_STAGE},
        "folds": [asdict(fold) | {"timezone": "UTC", "purge_embargo_days": 28} for fold in FOLDS],
        "membership_contract": {
            "first_pit_decision": "2022-01-03T00:00:00Z",
            "no_synthetic_2021_membership": True,
            "2021_ohlcv_warmup_only": True,
        },
        "regime_amendment": {
            "btc_trend_minimum_completed_daily_bars": 84,
            "tercile_minimum_prior_weekly_decisions": 52,
            "quantiles": [1 / 3, 2 / 3],
            "quantile_method": "linear",
            "history_cutoff": "strictly before decision_time",
        },
        "formula_resolutions": FORMULAS,
        "trial_budget": TRIAL_BUDGET,
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
    }
