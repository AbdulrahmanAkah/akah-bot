"""Typed explainability contracts for AdaptiveTradeIntelligenceV1."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

import pandas as pd


class ManagementMode(StrEnum):
    BREATHE = "BREATHE"
    STANDARD = "STANDARD"
    PROTECT = "PROTECT"
    EXIT = "EXIT"
    BLOCK_NEW_ENTRY = "BLOCK_NEW_ENTRY"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class PortfolioRiskState(StrEnum):
    NORMAL = "NORMAL"
    CAUTIOUS = "CAUTIOUS"
    DEFENSIVE = "DEFENSIVE"
    EMERGENCY = "EMERGENCY"
    DATA_BLOCKED = "DATA_BLOCKED"


class TargetMode(StrEnum):
    TRAIL_ONLY = "TRAIL_ONLY"
    STRUCTURE_TARGET = "STRUCTURE_TARGET"
    VOLATILITY_TARGET = "VOLATILITY_TARGET"
    PARTIAL_TARGET_THEN_TRAIL = "PARTIAL_TARGET_THEN_TRAIL"
    NO_FIXED_TARGET = "NO_FIXED_TARGET"


@dataclass(frozen=True)
class TradeMarketContext:
    timestamp: pd.Timestamp
    trend_persistence: float
    volatility_percentile: float
    liquidity_quality: float
    gap_risk: float
    breadth: float
    correlation: float
    data_confidence: float


@dataclass(frozen=True)
class TradeRegimeContext:
    support: float
    cash_flight_confirmed: bool
    timeframe_alignment: float
    data_quality: str


@dataclass(frozen=True)
class OpenPositionState:
    trade_id: str
    entry_price: float
    current_price: float
    initial_stop: float
    current_stop: float
    mfe_r: float
    mae_r: float
    bars_held: int
    structure_intact: bool


@dataclass(frozen=True)
class TradeManagementDecision:
    timestamp: pd.Timestamp
    trade_id: str
    continuation_score: float
    trade_quality_score: float
    regime_support_score: float
    liquidity_quality_score: float
    structure_quality_score: float
    profit_protection_score: float
    portfolio_risk_score: float
    data_confidence_score: float
    management_mode: ManagementMode
    suggested_size_multiplier: float
    current_stop: float
    suggested_stop: float
    target_mode: TargetMode
    reason_codes: tuple[str, ...]


@dataclass(frozen=True)
class PositionSizingDecision:
    baseline_notional: float
    effective_notional: float
    relative_size_multiplier: float
    rejected: bool
    reason_codes: tuple[str, ...]


@dataclass(frozen=True)
class StopDecision:
    action: str
    selected_stop: float | None
    stop_distance: float | None
    rejected_candidates: tuple[str, ...]
    reason_codes: tuple[str, ...]

