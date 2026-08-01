from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final, cast

import numpy as np
import pandas as pd

from spotbot.research.rd16d_metrics import market_regime_from_row
from spotbot.research.rd16n_signals import (
    ARCHITECTURE_ID,
    NORMAL_HOLDING_BARS,
    STRONG_BULL_HOLDING_BARS,
    SignalHypothesis,
    build_extended_feature_frames,
)

RESEARCH_STAGE: Final = "RD16Q"


class RD16QDomainError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class SignalDomain:
    hypothesis: SignalHypothesis
    allowed_regimes: frozenset[str]
    description: str
    information_domain: str

    @property
    def domain_id(self) -> str:
        return self.hypothesis.hypothesis_id

    def to_record(self) -> dict[str, object]:
        return {
            **self.hypothesis.to_record(),
            "domain_id": self.domain_id,
            "information_domain": self.information_domain,
            "domain_description": self.description,
            "allowed_regimes": "; ".join(sorted(self.allowed_regimes)),
        }


DOMAIN_REGISTRY: Final = (
    SignalDomain(
        hypothesis=SignalHypothesis(
            hypothesis_id="BREADTH_THRUST_LEADER_BREAKOUT",
            engine_id="BREADTH_THRUST_LEADER_ENGINE_V1",
            role="MARKET_INTERNALS",
            description=("Cross-sectional breadth thrust followed by a leader breakout."),
            stop_atr_multiple=1.25,
            cooldown_hours=24,
            engine_priority=40,
            fixed_conditions=(
                "1H breadth >= 67%",
                "6H breadth impulse >= 33 percentage points",
                "24H relative-strength percentile >= 67%",
                "72H relative-strength percentile >= 50%",
                "close above prior 12H high",
                "volume >= 1.20 x 20H median",
                "4H and 1D trend aligned",
            ),
        ),
        allowed_regimes=frozenset({"BULL", "STRONG_BULL"}),
        description=(
            "Tests whether a broad participation impulse creates a cleaner "
            "continuation edge than single-asset momentum."
        ),
        information_domain="CROSS_SECTIONAL_BREADTH",
    ),
    SignalDomain(
        hypothesis=SignalHypothesis(
            hypothesis_id="BTC_TO_ALT_ROTATION_BREAKOUT",
            engine_id="BTC_TO_ALT_ROTATION_ENGINE_V1",
            role="MARKET_INTERNALS",
            description=("Leadership rotation from BTC into a top-ranked non-BTC asset."),
            stop_atr_multiple=1.25,
            cooldown_hours=24,
            engine_priority=41,
            fixed_conditions=(
                "non-BTC symbol only",
                "BTC 24H lead crosses from non-negative to <= -1%",
                "1H breadth >= 50%",
                "24H relative-strength percentile >= 83%",
                "72H relative-strength percentile >= 67%",
                "close above prior 6H high",
                "volume >= 1.10 x 20H median",
                "4H and 1D trend aligned",
            ),
        ),
        allowed_regimes=frozenset({"BULL", "STRONG_BULL"}),
        description=(
            "Tests whether a causal loss of BTC leadership identifies "
            "profitable alt rotation without using derivatives data."
        ),
        information_domain="LEADERSHIP_ROTATION",
    ),
    SignalDomain(
        hypothesis=SignalHypothesis(
            hypothesis_id="DISPERSION_EXPANSION_LEADER",
            engine_id="DISPERSION_EXPANSION_LEADER_ENGINE_V1",
            role="MARKET_INTERNALS",
            description=(
                "Top-ranked leader breakout as cross-sectional return "
                "dispersion expands above a causal threshold."
            ),
            stop_atr_multiple=1.35,
            cooldown_hours=30,
            engine_priority=42,
            fixed_conditions=(
                "24H return dispersion crosses above prior 200H 75th percentile",
                "equal-weight 24H market return > 0",
                "24H relative-strength percentile >= 83%",
                "close above prior 12H high",
                "volume >= 20H median",
                "4H and 1D trend aligned",
            ),
        ),
        allowed_regimes=frozenset({"BULL", "STRONG_BULL"}),
        description=(
            "Tests whether widening cross-sectional opportunity sets contain "
            "an exploitable leader effect."
        ),
        information_domain="RETURN_DISPERSION",
    ),
    SignalDomain(
        hypothesis=SignalHypothesis(
            hypothesis_id="VOLUME_BREADTH_THRUST",
            engine_id="VOLUME_BREADTH_THRUST_ENGINE_V1",
            role="MARKET_INTERNALS",
            description=(
                "Broad spot-volume participation thrust with a top-ranked asset breakout."
            ),
            stop_atr_multiple=1.25,
            cooldown_hours=24,
            engine_priority=43,
            fixed_conditions=(
                "fraction of assets with volume >= 1.25 x median crosses 50%",
                "1H price breadth >= 67%",
                "24H relative-strength percentile >= 67%",
                "close above prior 6H high",
                "close location >= 65%",
                "4H and 1D trend aligned",
            ),
        ),
        allowed_regimes=frozenset({"BULL", "STRONG_BULL"}),
        description=(
            "Tests whether broad spot-volume participation improves the "
            "quality of price-only breakouts."
        ),
        information_domain="VOLUME_BREADTH",
    ),
    SignalDomain(
        hypothesis=SignalHypothesis(
            hypothesis_id="CORRELATION_RELEASE_ROTATION",
            engine_id="CORRELATION_RELEASE_ROTATION_ENGINE_V1",
            role="MARKET_INTERNALS",
            description=(
                "Top-ranked rotation after average pairwise correlation "
                "releases from a high-correlation regime."
            ),
            stop_atr_multiple=1.20,
            cooldown_hours=30,
            engine_priority=44,
            fixed_conditions=(
                "prior 72H average pairwise correlation >= 0.65",
                "current 72H average pairwise correlation <= 0.55",
                "72H relative-strength percentile >= 83%",
                "1H breadth >= 50%",
                "close > EMA20 > EMA50",
                "volume >= 20H median",
                "4H and 1D trend aligned",
            ),
        ),
        allowed_regimes=frozenset({"BULL", "STRONG_BULL"}),
        description=(
            "Tests whether falling market co-movement creates a causal "
            "cross-sectional selection opportunity."
        ),
        information_domain="CORRELATION_REGIME",
    ),
)

DOMAIN_BY_ID: Final = {domain.domain_id: domain for domain in DOMAIN_REGISTRY}
DOMAIN_IDS: Final = tuple(domain.domain_id for domain in DOMAIN_REGISTRY)

INTERNAL_COLUMNS: Final = (
    "return24_rank_pct_q",
    "return72_rank_pct_q",
    "market_breadth_q",
    "breadth_1h_q",
    "breadth_impulse6_q",
    "volume_ratio20_q",
    "volume_breadth_q",
    "previous_volume_breadth_q",
    "dispersion24_q",
    "previous_dispersion24_q",
    "prior_dispersion_q75_200_q",
    "previous_prior_dispersion_q75_200_q",
    "market_return24_q",
    "btc_alt_gap24_q",
    "previous_btc_alt_gap24_q",
    "average_corr72_q",
    "previous_average_corr72_q",
    "ema20_distance_atr_q",
)


def _timestamp(value: object) -> pd.Timestamp:
    parsed = pd.Timestamp(cast(Any, value))
    if parsed.tzinfo is None:
        return parsed.tz_localize("UTC")
    return parsed.tz_convert("UTC")


def _safe_divide(
    numerator: pd.Series,
    denominator: pd.Series,
) -> pd.Series:
    result = numerator / denominator.replace(0.0, np.nan)
    return result.replace([np.inf, -np.inf], np.nan)


def _rolling_average_pairwise_correlation(
    returns: pd.DataFrame,
    *,
    window: int = 72,
    minimum_periods: int = 48,
) -> pd.Series:
    symbols = [str(column) for column in returns.columns]
    correlations: list[pd.Series] = []
    for left_index, left in enumerate(symbols):
        for right in symbols[left_index + 1 :]:
            correlations.append(
                returns[left].rolling(window, min_periods=minimum_periods).corr(returns[right])
            )
    if not correlations:
        raise RD16QDomainError("At least two symbols are required for correlation internals.")
    return pd.concat(correlations, axis=1).mean(axis=1, skipna=True)


def build_market_internal_feature_frames(
    feature_frames: Mapping[str, pd.DataFrame],
) -> dict[str, pd.DataFrame]:
    if "BTC/USDT" not in feature_frames:
        raise RD16QDomainError("BTC/USDT is required for leadership internals.")
    if len(feature_frames) < 2:
        raise RD16QDomainError("At least two symbols are required.")

    extended = build_extended_feature_frames(feature_frames)
    indexed: dict[str, pd.DataFrame] = {}
    for symbol, raw in extended.items():
        frame = raw.copy()
        timestamps = pd.to_datetime(
            frame["timestamp"],
            utc=True,
            errors="raise",
        ).astype("datetime64[ns, UTC]")
        frame["timestamp"] = timestamps
        indexed[symbol] = frame.set_index("timestamp")

    return24 = pd.concat(
        {
            symbol: pd.to_numeric(frame["return24"], errors="raise")
            for symbol, frame in indexed.items()
        },
        axis=1,
    )
    return72 = pd.concat(
        {
            symbol: pd.to_numeric(frame["return72"], errors="raise")
            for symbol, frame in indexed.items()
        },
        axis=1,
    )
    close_matrix = pd.concat(
        {
            symbol: pd.to_numeric(frame["close"], errors="raise")
            for symbol, frame in indexed.items()
        },
        axis=1,
    )
    one_hour_returns = close_matrix.pct_change(fill_method=None)

    rank24 = return24.rank(axis=1, pct=True, method="average")
    rank72 = return72.rank(axis=1, pct=True, method="average")
    market_return24 = return24.mean(axis=1, skipna=True)
    alt_columns = [column for column in return24.columns if str(column) != "BTC/USDT"]
    alt_return24 = return24.loc[:, alt_columns].mean(axis=1, skipna=True)
    btc_alt_gap24 = return24["BTC/USDT"] - alt_return24

    breadth_1h_components = pd.concat(
        {
            symbol: (
                pd.to_numeric(frame["close"], errors="raise")
                > pd.to_numeric(frame["ema20"], errors="raise")
            )
            for symbol, frame in indexed.items()
        },
        axis=1,
    )
    breadth_4h_components = pd.concat(
        {
            symbol: (
                pd.to_numeric(frame["4h_close"], errors="raise")
                > pd.to_numeric(frame["4h_ema20"], errors="raise")
            )
            for symbol, frame in indexed.items()
        },
        axis=1,
    )
    breadth_1d_components = pd.concat(
        {
            symbol: (
                pd.to_numeric(frame["1d_close"], errors="raise")
                > pd.to_numeric(frame["1d_ema50"], errors="raise")
            )
            for symbol, frame in indexed.items()
        },
        axis=1,
    )
    breadth_1h = breadth_1h_components.astype(float).mean(
        axis=1,
        skipna=True,
    )
    market_breadth = pd.concat(
        (
            breadth_1h_components.astype(float),
            breadth_4h_components.astype(float),
            breadth_1d_components.astype(float),
        ),
        axis=1,
    ).mean(axis=1, skipna=True)
    breadth_impulse6 = breadth_1h - breadth_1h.shift(6)

    volume_ratios = pd.concat(
        {
            symbol: _safe_divide(
                pd.to_numeric(frame["volume"], errors="raise"),
                pd.to_numeric(frame["volume_median20"], errors="raise"),
            )
            for symbol, frame in indexed.items()
        },
        axis=1,
    )
    volume_breadth = (
        (volume_ratios >= 1.25)
        .astype(float)
        .mean(
            axis=1,
            skipna=True,
        )
    )

    dispersion24 = return24.std(axis=1, ddof=0, skipna=True)
    prior_dispersion_q75 = dispersion24.shift(1).rolling(200, min_periods=120).quantile(0.75)
    average_corr72 = _rolling_average_pairwise_correlation(one_hour_returns)

    result: dict[str, pd.DataFrame] = {}
    for symbol, frame in indexed.items():
        local = frame.copy()
        local["return24_rank_pct_q"] = rank24[symbol].reindex(local.index)
        local["return72_rank_pct_q"] = rank72[symbol].reindex(local.index)
        local["market_breadth_q"] = market_breadth.reindex(local.index)
        local["breadth_1h_q"] = breadth_1h.reindex(local.index)
        local["breadth_impulse6_q"] = breadth_impulse6.reindex(local.index)
        local["volume_ratio20_q"] = volume_ratios[symbol].reindex(local.index)
        local["volume_breadth_q"] = volume_breadth.reindex(local.index)
        local["previous_volume_breadth_q"] = volume_breadth.shift(1).reindex(local.index)
        local["dispersion24_q"] = dispersion24.reindex(local.index)
        local["previous_dispersion24_q"] = dispersion24.shift(1).reindex(local.index)
        local["prior_dispersion_q75_200_q"] = prior_dispersion_q75.reindex(local.index)
        local["previous_prior_dispersion_q75_200_q"] = prior_dispersion_q75.shift(1).reindex(
            local.index
        )
        local["market_return24_q"] = market_return24.reindex(local.index)
        local["btc_alt_gap24_q"] = btc_alt_gap24.reindex(local.index)
        local["previous_btc_alt_gap24_q"] = btc_alt_gap24.shift(1).reindex(local.index)
        local["average_corr72_q"] = average_corr72.reindex(local.index)
        local["previous_average_corr72_q"] = average_corr72.shift(1).reindex(local.index)
        local["ema20_distance_atr_q"] = _safe_divide(
            pd.to_numeric(local["close"], errors="raise")
            - pd.to_numeric(local["ema20"], errors="raise"),
            pd.to_numeric(local["atr14"], errors="raise"),
        )
        local = local.replace([np.inf, -np.inf], np.nan)
        result[symbol] = local.reset_index()
    return result


def domain_signal_mask(
    frame: pd.DataFrame,
    domain_id: str,
    *,
    symbol: str,
) -> pd.Series:
    if domain_id == "BREADTH_THRUST_LEADER_BREAKOUT":
        raw = (
            (frame["breadth_1h_q"] >= 0.67)
            & (frame["breadth_impulse6_q"] >= 0.33)
            & (frame["return24_rank_pct_q"] >= 0.67)
            & (frame["return72_rank_pct_q"] >= 0.50)
            & (frame["close"] > frame["prior_high12"])
            & (frame["volume_ratio20_q"] >= 1.20)
            & (frame["close_location"] >= 0.70)
            & (frame["4h_close"] > frame["4h_ema20"])
            & (frame["1d_close"] > frame["1d_ema50"])
        )
    elif domain_id == "BTC_TO_ALT_ROTATION_BREAKOUT":
        raw = (
            (symbol != "BTC/USDT")
            & (frame["previous_btc_alt_gap24_q"] >= 0.0)
            & (frame["btc_alt_gap24_q"] <= -0.01)
            & (frame["breadth_1h_q"] >= 0.50)
            & (frame["return24_rank_pct_q"] >= 0.83)
            & (frame["return72_rank_pct_q"] >= 0.67)
            & (frame["close"] > frame["prior_high6"])
            & (frame["volume_ratio20_q"] >= 1.10)
            & (frame["close"] > frame["ema20"])
            & (frame["4h_close"] > frame["4h_ema20"])
            & (frame["1d_close"] > frame["1d_ema50"])
        )
    elif domain_id == "DISPERSION_EXPANSION_LEADER":
        raw = (
            (frame["previous_dispersion24_q"] <= frame["previous_prior_dispersion_q75_200_q"])
            & (frame["dispersion24_q"] > frame["prior_dispersion_q75_200_q"])
            & (frame["market_return24_q"] > 0.0)
            & (frame["return24_rank_pct_q"] >= 0.83)
            & (frame["close"] > frame["prior_high12"])
            & (frame["volume_ratio20_q"] >= 1.00)
            & (frame["4h_close"] > frame["4h_ema20"])
            & (frame["1d_close"] > frame["1d_ema50"])
        )
    elif domain_id == "VOLUME_BREADTH_THRUST":
        raw = (
            (frame["previous_volume_breadth_q"] < 0.50)
            & (frame["volume_breadth_q"] >= 0.50)
            & (frame["breadth_1h_q"] >= 0.67)
            & (frame["return24_rank_pct_q"] >= 0.67)
            & (frame["close"] > frame["prior_high6"])
            & (frame["close_location"] >= 0.65)
            & (frame["4h_close"] > frame["4h_ema20"])
            & (frame["1d_close"] > frame["1d_ema50"])
        )
    elif domain_id == "CORRELATION_RELEASE_ROTATION":
        raw = (
            (frame["previous_average_corr72_q"] >= 0.65)
            & (frame["average_corr72_q"] <= 0.55)
            & (frame["return72_rank_pct_q"] >= 0.83)
            & (frame["breadth_1h_q"] >= 0.50)
            & (frame["close"] > frame["ema20"])
            & (frame["ema20"] > frame["ema50"])
            & (frame["volume_ratio20_q"] >= 1.00)
            & (frame["4h_close"] > frame["4h_ema20"])
            & (frame["1d_close"] > frame["1d_ema50"])
        )
    else:
        raise KeyError(f"Unknown RD16-Q domain ID: {domain_id}")

    normalized = raw.fillna(False).astype(bool)
    previous = normalized.shift(1, fill_value=False).astype(bool)
    return normalized & ~previous


def build_domain_candidates(
    feature_frames: Mapping[str, pd.DataFrame],
    *,
    domain: SignalDomain,
) -> pd.DataFrame:
    records: list[dict[str, object]] = []
    for symbol in sorted(feature_frames):
        frame = feature_frames[symbol]
        mask = domain_signal_mask(
            frame,
            domain.domain_id,
            symbol=symbol,
        )
        for position, active in enumerate(mask.tolist()):
            if not bool(active):
                continue
            next_position = position + 1
            if next_position >= len(frame):
                continue
            signal_row = frame.iloc[position]
            next_row = frame.iloc[next_position]
            signal_close = _timestamp(signal_row["timestamp"])
            entry_bar_close = _timestamp(next_row["timestamp"])
            if entry_bar_close - signal_close != pd.Timedelta(hours=1):
                continue

            signal_mapping = {str(key): value for key, value in signal_row.to_dict().items()}
            market_regime = market_regime_from_row(signal_mapping)
            if market_regime not in domain.allowed_regimes:
                continue
            holding_bars = (
                STRONG_BULL_HOLDING_BARS if market_regime == "STRONG_BULL" else NORMAL_HOLDING_BARS
            )
            symbol_token = symbol.replace("/", "-")
            candidate_id = f"RD16Q-{domain.domain_id}-{symbol_token}-{signal_close.isoformat()}"
            records.append(
                {
                    "architecture_id": ARCHITECTURE_ID,
                    "research_stage": RESEARCH_STAGE,
                    "hypothesis_id": domain.domain_id,
                    "engine_id": domain.hypothesis.engine_id,
                    "engine_priority": domain.hypothesis.engine_priority,
                    "engine_role": domain.hypothesis.role,
                    "cooldown_hours": domain.hypothesis.cooldown_hours,
                    "candidate_id": candidate_id,
                    "source_trade_id": candidate_id,
                    "symbol": symbol,
                    "signal_close": signal_close,
                    "entry_open_time": signal_close,
                    "entry_bar_close": entry_bar_close,
                    "entry_price": float(next_row["open"]),
                    "atr14_at_signal": float(signal_row["atr14"]),
                    "stop_atr_multiple": (domain.hypothesis.stop_atr_multiple),
                    "maximum_holding_bars": holding_bars,
                    "market_regime": market_regime,
                    "market_breadth_at_signal": float(signal_row["market_breadth_q"]),
                    "return24_rank_at_signal": float(signal_row["return24_rank_pct_q"]),
                    "return72_rank_at_signal": float(signal_row["return72_rank_pct_q"]),
                    "volume_ratio_at_signal": float(signal_row["volume_ratio20_q"]),
                    "ema20_distance_atr_at_signal": float(signal_row["ema20_distance_atr_q"]),
                    "breadth_1h_at_signal": float(signal_row["breadth_1h_q"]),
                    "breadth_impulse6_at_signal": float(signal_row["breadth_impulse6_q"]),
                    "volume_breadth_at_signal": float(signal_row["volume_breadth_q"]),
                    "dispersion24_at_signal": float(signal_row["dispersion24_q"]),
                    "average_corr72_at_signal": float(signal_row["average_corr72_q"]),
                    "btc_alt_gap24_at_signal": float(signal_row["btc_alt_gap24_q"]),
                    "4h_context_close": _timestamp(signal_row["4h_timestamp"]),
                    "1d_context_close": _timestamp(signal_row["1d_timestamp"]),
                    "1w_context_close": _timestamp(signal_row["1w_timestamp"]),
                }
            )

    columns = [
        "architecture_id",
        "research_stage",
        "hypothesis_id",
        "engine_id",
        "engine_priority",
        "engine_role",
        "cooldown_hours",
        "candidate_id",
        "source_trade_id",
        "symbol",
        "signal_close",
        "entry_open_time",
        "entry_bar_close",
        "entry_price",
        "atr14_at_signal",
        "stop_atr_multiple",
        "maximum_holding_bars",
        "market_regime",
        "market_breadth_at_signal",
        "return24_rank_at_signal",
        "return72_rank_at_signal",
        "volume_ratio_at_signal",
        "ema20_distance_atr_at_signal",
        "breadth_1h_at_signal",
        "breadth_impulse6_at_signal",
        "volume_breadth_at_signal",
        "dispersion24_at_signal",
        "average_corr72_at_signal",
        "btc_alt_gap24_at_signal",
        "4h_context_close",
        "1d_context_close",
        "1w_context_close",
    ]
    if not records:
        return pd.DataFrame(columns=columns)
    return (
        pd.DataFrame.from_records(records, columns=columns)
        .sort_values(
            by=[
                "entry_open_time",
                "engine_priority",
                "symbol",
                "signal_close",
                "candidate_id",
            ],
            kind="stable",
        )
        .reset_index(drop=True)
    )


def domain_registry_rows() -> list[dict[str, object]]:
    return [domain.to_record() for domain in DOMAIN_REGISTRY]


__all__ = [
    "DOMAIN_BY_ID",
    "DOMAIN_IDS",
    "DOMAIN_REGISTRY",
    "INTERNAL_COLUMNS",
    "RD16QDomainError",
    "RESEARCH_STAGE",
    "SignalDomain",
    "build_domain_candidates",
    "build_market_internal_feature_frames",
    "domain_registry_rows",
    "domain_signal_mask",
]
