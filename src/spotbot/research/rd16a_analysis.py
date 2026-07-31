from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any, cast

import numpy as np
import pandas as pd

from spotbot.research.rd16a_common import (
    SEALED_CUTOFF,
    CohortData,
    RD16AInputError,
    _bool_series,
    _finite_float,
    _numeric,
    _require_columns,
)


def _yearly_strategy_returns(metrics: Mapping[str, Any]) -> dict[int, float]:
    raw = metrics.get("yearly_returns")
    if not isinstance(raw, dict):
        raise RD16AInputError("RD15 metrics yearly_returns is missing.")
    result: dict[int, float] = {}
    for raw_timestamp, raw_return in raw.items():
        timestamp = pd.Timestamp(str(raw_timestamp))
        result[int(timestamp.year)] = _finite_float(
            raw_return,
            field=f"yearly_returns[{raw_timestamp}]",
        )
    return result


def _load_market_frames(
    *,
    assets: tuple[str, ...],
    long_history: bool,
) -> dict[str, pd.DataFrame]:
    from spotbot.research import rd14_scored_breakout as rd14

    frames = rd14._align_frames(assets, long_history=long_history)
    normalized: dict[str, pd.DataFrame] = {}
    for symbol, frame in frames.items():
        _require_columns(
            frame,
            ("timestamp", "open", "high", "low", "close", "volume"),
            name=f"{symbol} market frame",
        )
        item = frame.copy()
        item["timestamp"] = pd.to_datetime(item["timestamp"], utc=True, errors="raise")
        if bool((item["timestamp"] >= SEALED_CUTOFF).any()):
            raise RD16AInputError(f"Sealed 2025+ market data detected for {symbol}.")
        normalized[symbol] = item.sort_values("timestamp", kind="stable").reset_index(drop=True)
    return normalized


def _evaluation_start(config: Mapping[str, Any]) -> pd.Timestamp:
    raw = config.get("evaluation_start")
    if not isinstance(raw, str):
        raise RD16AInputError("RD15 config evaluation_start is missing.")
    value = pd.Timestamp(raw)
    value = value.tz_localize("UTC") if value.tzinfo is None else value.tz_convert("UTC")
    if value >= SEALED_CUTOFF:
        raise RD16AInputError("Evaluation start is inside sealed data.")
    return value


def _benchmark_curve(
    frames: Mapping[str, pd.DataFrame],
    *,
    evaluation_start: pd.Timestamp,
) -> pd.DataFrame:
    if "BTC/USDT" not in frames:
        raise RD16AInputError("BTC/USDT is required for the benchmark.")
    close_by_asset: dict[str, pd.Series] = {}
    for symbol, frame in frames.items():
        source = frame.loc[frame["timestamp"] >= evaluation_start, ["timestamp", "close"]].copy()
        source["close"] = pd.to_numeric(source["close"], errors="coerce")
        source = source.dropna(subset=["close"])
        if source.empty:
            raise RD16AInputError(f"No benchmark rows remain for {symbol}.")
        indexed = source.set_index("timestamp")["close"].astype("float64")
        first = float(indexed.iloc[0])
        if first <= 0:
            raise RD16AInputError(f"Invalid benchmark start price for {symbol}.")
        close_by_asset[symbol] = indexed / first

    wide = pd.DataFrame(close_by_asset).dropna(how="any")
    if wide.empty:
        raise RD16AInputError("Benchmark alignment produced no common rows.")
    result = pd.DataFrame(index=wide.index)
    result["equal_weight"] = wide.mean(axis=1)
    result["btc"] = wide["BTC/USDT"]
    return result.reset_index(names="timestamp")


def _yearly_returns_from_curve(curve: pd.DataFrame, column: str) -> dict[int, float]:
    timestamps = pd.to_datetime(curve["timestamp"], utc=True, errors="raise")
    values = pd.to_numeric(curve[column], errors="raise").astype("float64")
    frame = pd.DataFrame({"timestamp": timestamps, "value": values})
    frame["year"] = frame["timestamp"].dt.year
    year_ends = frame.groupby("year", sort=True)["value"].last()
    result: dict[int, float] = {}
    previous = 1.0
    for raw_year, raw_value in year_ends.items():
        year = int(str(raw_year))
        value = float(raw_value)
        result[year] = value / previous - 1.0
        previous = value
    return result


def _btc_regime(frames: Mapping[str, pd.DataFrame]) -> pd.DataFrame:
    source = frames["BTC/USDT"].loc[:, ["timestamp", "close"]].copy()
    source["close"] = pd.to_numeric(source["close"], errors="raise").astype("float64")
    source["ema_50"] = source["close"].ewm(span=50, adjust=False).mean()
    source["ema_200"] = source["close"].ewm(span=200, adjust=False).mean()
    bull = (source["close"] > source["ema_200"]) & (source["ema_50"] > source["ema_200"])
    bear = (source["close"] < source["ema_200"]) & (source["ema_50"] < source["ema_200"])
    source["regime"] = np.select(
        [bull, bear],
        ["BULL", "BEAR"],
        default="SIDEWAYS_TRANSITION",
    )
    return source.loc[:, ["timestamp", "regime"]]


def _bull_capture_rows(
    cohort: CohortData,
    frames: Mapping[str, pd.DataFrame],
) -> list[dict[str, Any]]:
    start = _evaluation_start(cohort.config)
    curve = _benchmark_curve(frames, evaluation_start=start)
    strategy = _yearly_strategy_returns(cohort.metrics)
    equal_weight = _yearly_returns_from_curve(curve, "equal_weight")
    btc = _yearly_returns_from_curve(curve, "btc")
    years = sorted(set(strategy).intersection(equal_weight).intersection(btc))
    rows: list[dict[str, Any]] = []
    for year in years:
        strategy_return = strategy[year]
        equal_return = equal_weight[year]
        btc_return = btc[year]
        equal_capture = strategy_return / equal_return if equal_return > 0 else None
        btc_capture = strategy_return / btc_return if btc_return > 0 else None
        high_opportunity = equal_return > 2.0
        adequate = (
            not high_opportunity
            or strategy_return >= 1.0
            or (equal_capture is not None and equal_capture >= 0.40)
        )
        rows.append(
            {
                "cohort": cohort.paths.cohort_id,
                "year": year,
                "strategy_return": strategy_return,
                "equal_weight_return": equal_return,
                "btc_return": btc_return,
                "equal_weight_upside_capture": equal_capture,
                "btc_upside_capture": btc_capture,
                "high_opportunity_year": high_opportunity,
                "bull_adequacy_pass": adequate,
            }
        )
    return rows


def _trade_concentration_rows(cohort: CohortData) -> list[dict[str, Any]]:
    pnl = _numeric(cohort.trades, "net_pnl").dropna().sort_values(ascending=False)
    total = float(pnl.sum())
    rows: list[dict[str, Any]] = []
    for count in (1, 2, 3, 5):
        selected = pnl.head(count)
        selected_total = float(selected.sum())
        rows.append(
            {
                "cohort": cohort.paths.cohort_id,
                "top_trade_count": count,
                "selected_trade_pnl": selected_total,
                "share_of_total_net_pnl": selected_total / total if total > 0 else None,
                "net_pnl_after_arithmetic_removal": total - selected_total,
                "total_net_pnl": total,
            }
        )
    return rows


def _exit_reason_rows(cohort: CohortData) -> list[dict[str, Any]]:
    frame = cohort.trades.copy()
    frame["net_pnl"] = _numeric(frame, "net_pnl")
    rows: list[dict[str, Any]] = []
    for reason, group in frame.groupby("exit_reason", sort=True, dropna=False):
        pnl = group["net_pnl"].dropna().astype("float64")
        if pnl.empty:
            continue
        winners = int((pnl > 0).sum())
        largest_winner = float(pnl.max()) if bool((pnl > 0).any()) else 0.0
        rows.append(
            {
                "cohort": cohort.paths.cohort_id,
                "exit_reason": str(reason),
                "trade_count": int(len(pnl)),
                "winner_count": winners,
                "win_rate": winners / len(pnl),
                "net_pnl": float(pnl.sum()),
                "average_pnl": float(pnl.mean()),
                "median_pnl": float(pnl.median()),
                "best_trade": float(pnl.max()),
                "worst_trade": float(pnl.min()),
                "largest_winner": largest_winner,
                "net_pnl_excluding_largest_winner": float(pnl.sum()) - largest_winner,
            }
        )
    return rows


def _asset_rows(cohort: CohortData) -> list[dict[str, Any]]:
    frame = cohort.trades.copy()
    frame["net_pnl"] = _numeric(frame, "net_pnl")
    total = float(frame["net_pnl"].sum())
    rows: list[dict[str, Any]] = []
    for symbol, group in frame.groupby("symbol", sort=True):
        pnl = group["net_pnl"].dropna().astype("float64")
        rows.append(
            {
                "cohort": cohort.paths.cohort_id,
                "symbol": str(symbol),
                "trade_count": int(len(pnl)),
                "win_rate": float((pnl > 0).mean()) if not pnl.empty else 0.0,
                "net_pnl": float(pnl.sum()),
                "share_of_total_net_pnl": float(pnl.sum()) / total if total > 0 else None,
                "average_pnl": float(pnl.mean()) if not pnl.empty else 0.0,
            }
        )
    return rows


def _spearman(x: pd.Series, y: pd.Series) -> float | None:
    frame = pd.DataFrame({"x": x, "y": y}).dropna()
    if len(frame) < 3 or frame["x"].nunique() < 2 or frame["y"].nunique() < 2:
        return None
    value = frame["x"].rank(method="average").corr(frame["y"].rank(method="average"))
    return float(value) if value is not None and math.isfinite(float(value)) else None


def _score_rows(cohort: CohortData) -> list[dict[str, Any]]:
    frame = cohort.candidates.copy()
    frame["score"] = _numeric(frame, "total_entry_score")
    frame["forward_return"] = _numeric(frame, "forward_20_bar_return")
    frame["accepted"] = _bool_series(frame, "accepted_for_entry")
    rows: list[dict[str, Any]] = []
    bins = [-np.inf, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0, np.inf]
    labels = ("LT_50", "50_60", "60_70", "70_80", "80_90", "90_100", "GT_100")
    frame["score_bin"] = pd.cut(frame["score"], bins=bins, labels=labels, right=False)

    for scope, scoped in (
        ("ALL_CANDIDATES", frame),
        ("ACCEPTED", frame.loc[frame["accepted"]]),
    ):
        correlation = _spearman(scoped["score"], scoped["forward_return"])
        rows.append(
            {
                "cohort": cohort.paths.cohort_id,
                "scope": scope,
                "score_bin": "ALL",
                "candidate_count": int(len(scoped)),
                "accepted_count": int(scoped["accepted"].sum()),
                "mean_score": float(scoped["score"].mean()) if not scoped.empty else None,
                "mean_forward_20_bar_return": (
                    float(scoped["forward_return"].mean()) if not scoped.empty else None
                ),
                "positive_forward_return_rate": (
                    float((scoped["forward_return"] > 0).mean()) if not scoped.empty else None
                ),
                "spearman_score_forward_20": correlation,
            }
        )
        for label in labels:
            group = scoped.loc[scoped["score_bin"].astype(str) == label]
            rows.append(
                {
                    "cohort": cohort.paths.cohort_id,
                    "scope": scope,
                    "score_bin": label,
                    "candidate_count": int(len(group)),
                    "accepted_count": int(group["accepted"].sum()),
                    "mean_score": float(group["score"].mean()) if not group.empty else None,
                    "mean_forward_20_bar_return": (
                        float(group["forward_return"].mean()) if not group.empty else None
                    ),
                    "positive_forward_return_rate": (
                        float((group["forward_return"] > 0).mean()) if not group.empty else None
                    ),
                    "spearman_score_forward_20": None,
                }
            )
    return rows


def _rejection_rows(cohort: CohortData) -> list[dict[str, Any]]:
    frame = cohort.candidates.copy()
    frame["accepted"] = _bool_series(frame, "accepted_for_entry")
    rejected = frame.loc[~frame["accepted"]].copy()
    for horizon in (5, 10, 20, 30):
        rejected[f"forward_{horizon}"] = _numeric(rejected, f"forward_{horizon}_bar_return")
    rejected["rejection_reason"] = rejected["rejection_reason"].fillna("").astype(str)
    rejected.loc[rejected["rejection_reason"].str.len() == 0, "rejection_reason"] = "UNSPECIFIED"
    rejected["market_regime"] = rejected["market_regime"].fillna("UNKNOWN").astype(str)

    rows: list[dict[str, Any]] = []
    for (reason, regime), group in rejected.groupby(
        ["rejection_reason", "market_regime"], sort=True
    ):
        forward_20 = group["forward_20"].dropna().astype("float64")
        rows.append(
            {
                "cohort": cohort.paths.cohort_id,
                "rejection_reason": str(reason),
                "market_regime": str(regime),
                "candidate_count": int(len(group)),
                "mean_forward_5": float(group["forward_5"].mean()),
                "mean_forward_10": float(group["forward_10"].mean()),
                "mean_forward_20": float(group["forward_20"].mean()),
                "mean_forward_30": float(group["forward_30"].mean()),
                "positive_forward_20_rate": (
                    float((forward_20 > 0).mean()) if not forward_20.empty else None
                ),
                "forward_20_gt_20pct_count": int((forward_20 > 0.20).sum()),
                "forward_20_gt_50pct_count": int((forward_20 > 0.50).sum()),
            }
        )
    return rows


def _regime_exposure_rows(
    cohort: CohortData,
    frames: Mapping[str, pd.DataFrame],
) -> list[dict[str, Any]]:
    equity = cohort.equity.copy()
    equity["equity"] = _numeric(equity, "equity")
    equity["cash"] = _numeric(equity, "cash")
    equity["market_value"] = _numeric(equity, "market_value")
    equity["exposure"] = np.where(
        equity["equity"] > 0,
        equity["market_value"] / equity["equity"],
        np.nan,
    )
    merged = equity.merge(_btc_regime(frames), on="timestamp", how="left", validate="one_to_one")
    if bool(merged["regime"].isna().any()):
        raise RD16AInputError(f"{cohort.paths.cohort_id}: regime alignment failed for equity rows.")
    rows: list[dict[str, Any]] = []
    for regime, group in merged.groupby("regime", sort=True):
        exposure = group["exposure"].dropna().astype("float64")
        rows.append(
            {
                "cohort": cohort.paths.cohort_id,
                "market_regime": str(regime),
                "bar_count": int(len(group)),
                "mean_exposure": float(exposure.mean()) if not exposure.empty else None,
                "median_exposure": float(exposure.median()) if not exposure.empty else None,
                "time_in_cash": 1.0 - float(exposure.mean()) if not exposure.empty else None,
                "bull_participation_pass": (
                    float(exposure.mean()) >= 0.35
                    if str(regime) == "BULL" and not exposure.empty
                    else None
                ),
            }
        )
    return rows


def _same_bar_stop_rows(cohort: CohortData) -> list[dict[str, Any]]:
    frame = cohort.trades.copy()
    frame["holding_bars"] = pd.to_numeric(frame["holding_bars"], errors="coerce")
    same_bar = frame.loc[frame["holding_bars"] == 0]
    rows: list[dict[str, Any]] = []
    for row in cast(list[dict[str, Any]], same_bar.to_dict(orient="records")):
        rows.append(
            {
                "cohort": cohort.paths.cohort_id,
                "trade_id": str(row["trade_id"]),
                "symbol": str(row["symbol"]),
                "entry_timestamp": pd.Timestamp(row["entry_timestamp"]).isoformat(),
                "exit_timestamp": pd.Timestamp(row["exit_timestamp"]).isoformat(),
                "exit_reason": str(row["exit_reason"]),
                "net_pnl": _finite_float(row["net_pnl"], field="same_bar_stop.net_pnl"),
                "audit_status": "REQUIRES_INTRABAR_PATH_ASSUMPTION_REVIEW",
            }
        )
    return rows
