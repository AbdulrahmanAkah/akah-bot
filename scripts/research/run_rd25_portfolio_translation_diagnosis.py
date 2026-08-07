from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from spotbot.research.rd24_minimal_portfolio import (  # noqa: E402
    DATA_CUTOFF,
    concentration_diagnostics,
    normalize_economic_bars,
    period_metrics,
    prepare_frozen_events,
    replay_portfolio,
    union_events,
)

EXPECTED_PARENT = "78592564dfd7a454c2842b096cb2bc54db320502"
DEFAULT_RAW_ROOT = Path("data/raw/rd16b/kucoin")
RD23_SIGNALS = Path("data/research/rd23_p2_runtime/signal-events.csv")
RD24_OUTPUT = Path("data/research/rd24_p2_runtime")
PROTOCOL = Path("data/research/rd25_p1/rd25-p1-portfolio-translation-diagnosis-v1.json")
OUTPUT = Path("data/research/rd25_p1_runtime")

EXPECTED_INPUT_HASHES = {
    RD24_OUTPUT / "output-manifest.json": (
        "888fb9eb1b6951e348f52996f24fda6c0ae0a8c0af2d723d50b4354c14d4bb2c"
    ),
    RD24_OUTPUT / "rd24-p2-parallel-minimal-portfolio-report-v1.json": (
        "755c4cef6c00f424257908655859f99b60550df17082269e00b43ab2362432a3"
    ),
    RD24_OUTPUT / "trade-ledger.csv": (
        "4981d51afdb59867b1f7e2c995cac584d7cda212b2055e145a2b5f0d3e31a388"
    ),
    RD24_OUTPUT / "daily-equity.csv": (
        "5c4ae06a45f2b53110e7898bd804a901e894181ed58f4bc9d76975a33ad7ce42"
    ),
    RD24_OUTPUT / "routing-summary.csv": (
        "35f4ac0a77c48335671ed9f2f3a8932bdb12730b879007f7951b2880d32851f6"
    ),
    RD24_OUTPUT / "hard-gate-evaluation.csv": (
        "d55de429c6a4c0da038e12fb567cc9ecdb68894728e79420f95654e16c5b6ecb"
    ),
    RD24_OUTPUT / "portfolio-run-metrics.csv": (
        "6ba29e18ebd558dced379787fe33c5737c8f6927b7819eec80a543acd866b998"
    ),
    RD24_OUTPUT / "portfolio-period-metrics.csv": (
        "acc5ce258c286b40df5243c7a7b22cdc7fa4e97a56999e1739d53815b3afab6f"
    ),
    RD24_OUTPUT / "concentration-diagnostics.csv": (
        "68e79ed894277569eb2b7054ff8c1600e6a451dfdb2a6cdaedf38820a5bb4a92"
    ),
}

FOCUS_FAMILIES = (
    "MOMENTUM_BREAKOUT",
    "RELATIVE_STRENGTH_ROTATION",
)
SECONDARY_FAMILIES = (
    "VOLATILITY_EXPANSION",
    "MOMENTUM_ACCELERATION",
)
UNIVERSES = ("C2", "D2", "E2")
COST_MULTIPLIERS = (1.0, 2.0)
SCALAR_GRID = (0.10, 0.125, 0.15, 0.20, 0.25, 0.50, 1.0)
INITIAL_EQUITY = 100_000.0

OUTPUT_NAMES = (
    "input-and-conformance-audit.json",
    "failure-taxonomy.csv",
    "drawdown-episodes.csv",
    "routing-pressure.csv",
    "fixed-route-exposure-scaling.csv",
    "trade-path-excursions.csv",
    "excursion-summary.csv",
    "focus-pair-union-run-metrics.csv",
    "focus-pair-union-period-metrics.csv",
    "focus-pair-union-routing.csv",
    "focus-pair-union-concentration.csv",
    "diagnosis.json",
)


class RD25Error(RuntimeError):
    pass


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser()
    value.add_argument("--repo-root", type=Path, required=True)
    value.add_argument("--raw-root", type=Path, default=None)
    value.add_argument("--preflight-only", action="store_true")
    value.add_argument("--execute", action="store_true")
    value.add_argument("--validate-only", action="store_true")
    value.add_argument("--expected-freeze-commit", default=None)
    return value


def git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if completed.returncode != 0:
        raise RD25Error(f"git {' '.join(args)} failed: {completed.stderr}")
    return completed.stdout.strip()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise RD25Error(f"JSON object expected: {path}")
    return value


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            value,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
            default=str,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )


def verify_inputs(
    repo: Path,
    raw_root: Path,
    *,
    executing: bool,
    expected_freeze_commit: str | None,
) -> dict[str, Any]:
    head = git(repo, "rev-parse", "HEAD")
    if executing:
        if not expected_freeze_commit:
            raise RD25Error("execution requires --expected-freeze-commit")
        if head != expected_freeze_commit:
            raise RD25Error(f"RD25 execution HEAD {head} != freeze {expected_freeze_commit}")
    elif head != EXPECTED_PARENT:
        raise RD25Error(f"RD25 preflight HEAD {head} != expected parent {EXPECTED_PARENT}")

    for relative, expected in EXPECTED_INPUT_HASHES.items():
        path = repo / relative
        if not path.is_file():
            raise RD25Error(f"RD24 input missing: {path}")
        actual = sha256(path)
        if actual != expected:
            raise RD25Error(f"RD24 input hash drift: {relative}: {actual} != {expected}")

    report = load_json(repo / RD24_OUTPUT / "rd24-p2-parallel-minimal-portfolio-report-v1.json")
    if report.get("decision") != (
        "RD24_RAW_EDGE_DID_NOT_TRANSLATE_TO_MINIMAL_PORTFOLIO_"
        "EXECUTION_ARCHITECTURE_DIAGNOSIS_REQUIRED"
    ):
        raise RD25Error("RD24 decision does not authorize translation diagnosis")
    if report.get("2022_2023_used_for_selection") is not False:
        raise RD25Error("RD24 indicates 2022/2023 selection access")
    if report.get("2024_accessed") is not False:
        raise RD25Error("RD24 indicates 2024 access")

    gates = pd.read_csv(repo / RD24_OUTPUT / "hard-gate-evaluation.csv")
    gate_bool = gates["passed"]
    if gate_bool.dtype != bool:
        normalized = gate_bool.astype(str).str.strip().str.lower()
        if bool(~normalized.isin({"true", "false"}).any()):
            raise RD25Error("RD24 hard-gate boolean encoding invalid")
        gates["passed"] = normalized == "true"

    expected_dd_only = set(FOCUS_FAMILIES)
    observed_dd_only: set[str] = set()
    for family in (*FOCUS_FAMILIES, *SECONDARY_FAMILIES):
        subset = gates.loc[gates["portfolio_id"] == family]
        failed = set(subset.loc[~subset["passed"], "gate_id"].astype(str))
        if failed == {"STRESS_2X_MAX_DRAWDOWN_LTE_20PCT"}:
            observed_dd_only.add(family)
    if observed_dd_only != expected_dd_only:
        raise RD25Error(f"RD24 DD-only family set drifted: {sorted(observed_dd_only)}")

    signal_path = repo / RD23_SIGNALS
    if not signal_path.is_file():
        raise RD25Error("RD23 signal ledger missing")
    events = prepare_frozen_events(pd.read_csv(signal_path, low_memory=False))
    pairs = sorted(set(events["pair"].astype(str)))
    missing = [pair for pair in pairs if not (raw_root / pair / "1h.parquet").is_file()]
    if missing:
        raise RD25Error(f"raw source missing for RD25: {missing[:20]}")

    return {
        "schema_version": "rd25-p1-input-conformance-audit-v1",
        "head": head,
        "source_commit": EXPECTED_PARENT,
        "rd24_input_hashes": {
            str(path): expected for path, expected in EXPECTED_INPUT_HASHES.items()
        },
        "focus_families": list(FOCUS_FAMILIES),
        "secondary_families": list(SECONDARY_FAMILIES),
        "qualified_pair_count": len(pairs),
        "qualified_pairs": pairs,
        "selection_window": "2019-01-01_THROUGH_2021-12-31_ONLY",
        "strong_pair_union_status": "POST_RESULT_DIAGNOSTIC_NOT_CANDIDATE",
        "fixed_route_scaling_status": "NON_ROUTED_DIAGNOSTIC_NOT_CANDIDATE",
        "architecture_selection_authorized": False,
        "2022_2023_accessed": False,
        "2024_accessed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
    }


def load_frames(raw_root: Path, pairs: list[str]) -> dict[str, pd.DataFrame]:
    frames: dict[str, pd.DataFrame] = {}
    cutoff = DATA_CUTOFF.to_pydatetime()
    for index, pair in enumerate(pairs, start=1):
        raw = pd.read_parquet(
            raw_root / pair / "1h.parquet",
            engine="pyarrow",
            filters=[("timestamp", "<", cutoff)],
        )
        frame = normalize_economic_bars(raw)
        prior_close = frame["close"].shift(1)
        true_range = pd.concat(
            [
                frame["high"] - frame["low"],
                (frame["high"] - prior_close).abs(),
                (frame["low"] - prior_close).abs(),
            ],
            axis=1,
        ).max(axis=1)
        frame["atr24"] = true_range.rolling(24, min_periods=24).mean()
        frames[pair] = frame
        print(f"RD25_RAW_SOURCE={index}/{len(pairs)}:{pair}:{len(frame)}", flush=True)
    return frames


def _lookup(frame: pd.DataFrame) -> dict[int, int]:
    times = pd.to_datetime(frame["timestamp"], utc=True, errors="raise").dt.as_unit("ns")
    return {int(value): int(index) for index, value in enumerate(times.astype("int64").to_numpy())}


def failure_taxonomy(gates: pd.DataFrame) -> pd.DataFrame:
    frame = gates.copy()
    passed = frame["passed"]
    if passed.dtype != bool:
        frame["passed"] = passed.astype(str).str.strip().str.lower() == "true"
    rows: list[dict[str, Any]] = []
    for family in (*FOCUS_FAMILIES, *SECONDARY_FAMILIES):
        subset = frame.loc[frame["portfolio_id"] == family]
        for universe in UNIVERSES:
            group = subset.loc[subset["universe_id"] == universe]
            failed = sorted(group.loc[~group["passed"], "gate_id"].astype(str))
            rows.append(
                {
                    "family_id": family,
                    "universe_id": universe,
                    "failed_gate_count": len(failed),
                    "failed_gates": "|".join(failed),
                    "dd_only_failure": failed == ["STRESS_2X_MAX_DRAWDOWN_LTE_20PCT"],
                }
            )
    return pd.DataFrame.from_records(rows)


def drawdown_episodes(daily: pd.DataFrame) -> pd.DataFrame:
    frame = daily.copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, errors="raise")
    rows: list[dict[str, Any]] = []
    wanted = {*FOCUS_FAMILIES, *SECONDARY_FAMILIES, "UNION_ALL_RAW_QUALIFIED"}
    subset = frame.loc[frame["portfolio_id"].isin(wanted) & (frame["cost_multiplier"] == 2.0)]
    for (portfolio, universe), group in subset.groupby(["portfolio_id", "universe_id"], sort=True):
        group = group.sort_values("timestamp", kind="stable").reset_index(drop=True)
        equity = pd.to_numeric(group["equity"], errors="raise").astype(float).to_numpy()
        peak = np.maximum.accumulate(equity)
        dd = np.divide(
            peak - equity,
            peak,
            out=np.zeros_like(equity),
            where=peak > 0.0,
        )
        trough_i = int(np.argmax(dd))
        peak_i = int(np.argmax(equity[: trough_i + 1]))
        peak_equity = float(equity[peak_i])
        recovery_i: int | None = None
        for idx in range(trough_i + 1, len(equity)):
            if float(equity[idx]) >= peak_equity:
                recovery_i = idx
                break
        rows.append(
            {
                "portfolio_id": portfolio,
                "universe_id": universe,
                "cost_multiplier": 2.0,
                "daily_close_maximum_drawdown": float(dd[trough_i]),
                "peak_time": group.iloc[peak_i]["timestamp"],
                "trough_time": group.iloc[trough_i]["timestamp"],
                "recovery_time": (
                    group.iloc[recovery_i]["timestamp"] if recovery_i is not None else None
                ),
                "peak_equity": peak_equity,
                "trough_equity": float(equity[trough_i]),
                "average_gross_exposure_fraction": float(group["gross_exposure_fraction"].mean()),
                "median_gross_exposure_fraction": float(group["gross_exposure_fraction"].median()),
                "share_days_four_or_more_positions": float((group["open_positions"] >= 4).mean()),
                "share_days_five_positions": float((group["open_positions"] == 5).mean()),
            }
        )
    return pd.DataFrame.from_records(rows)


def routing_pressure(routing: pd.DataFrame) -> pd.DataFrame:
    frame = routing.loc[routing["cost_multiplier"] == 2.0].copy()
    frame["admission_fraction"] = np.divide(
        frame["admitted_entries"],
        frame["signal_events"],
        out=np.zeros(len(frame), dtype=float),
        where=frame["signal_events"].to_numpy() > 0,
    )
    frame["same_pair_open_fraction"] = np.divide(
        frame["same_pair_open"],
        frame["signal_events"],
        out=np.zeros(len(frame), dtype=float),
        where=frame["signal_events"].to_numpy() > 0,
    )
    frame["slot_full_fraction"] = np.divide(
        frame["position_slots_full"],
        frame["signal_events"],
        out=np.zeros(len(frame), dtype=float),
        where=frame["signal_events"].to_numpy() > 0,
    )
    return frame


def fixed_route_scaling(daily: pd.DataFrame) -> pd.DataFrame:
    frame = daily.copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, errors="raise")
    wanted = {*FOCUS_FAMILIES, "UNION_ALL_RAW_QUALIFIED"}
    subset = frame.loc[frame["portfolio_id"].isin(wanted) & (frame["cost_multiplier"] == 2.0)]
    rows: list[dict[str, Any]] = []
    for (portfolio, universe), group in subset.groupby(["portfolio_id", "universe_id"], sort=True):
        group = group.sort_values("timestamp", kind="stable")
        original = pd.to_numeric(group["equity"], errors="raise").astype(float).to_numpy()
        for scalar in SCALAR_GRID:
            scaled = INITIAL_EQUITY + scalar * (original - INITIAL_EQUITY)
            running_peak = np.maximum.accumulate(scaled)
            dd = np.divide(
                running_peak - scaled,
                running_peak,
                out=np.zeros_like(scaled),
                where=running_peak > 0.0,
            )
            rows.append(
                {
                    "portfolio_id": portfolio,
                    "universe_id": universe,
                    "scalar_of_realized_rd24_pnl_path": scalar,
                    "final_net_return": float(scaled[-1] / INITIAL_EQUITY - 1.0),
                    "daily_close_maximum_drawdown": float(dd.max()),
                    "meets_20pct_daily_close_dd": bool(float(dd.max()) <= 0.20),
                    "method": (
                        "FIXED_ROUTE_FIXED_REALIZED_PNL_SCALAR_NO_REROUTING_NOT_A_CANDIDATE"
                    ),
                }
            )
    return pd.DataFrame.from_records(rows)


def trade_excursions(
    trades: pd.DataFrame,
    frames: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    focus = trades.loc[
        trades["portfolio_id"].isin(FOCUS_FAMILIES) & (trades["cost_multiplier"] == 2.0)
    ].copy()
    lookups = {pair: _lookup(frame) for pair, frame in frames.items()}
    rows: list[dict[str, Any]] = []
    for number, raw in enumerate(focus.to_dict(orient="records"), start=1):
        pair = str(raw["pair"])
        frame = frames[pair]
        lookup = lookups[pair]
        signal_time = pd.Timestamp(raw["signal_time"])
        entry_time = pd.Timestamp(raw["entry_time"])
        exit_time = pd.Timestamp(raw["exit_time"])
        signal_i = lookup.get(int(signal_time.value))
        entry_i = lookup.get(int(entry_time.value))
        exit_i = lookup.get(int(exit_time.value))
        if signal_i is None or entry_i is None or exit_i is None:
            raise RD25Error(f"trade path timestamp missing: {pair} {entry_time}")
        if exit_i <= entry_i:
            raise RD25Error("trade excursion exit index is not after entry")
        atr = float(frame.iloc[signal_i]["atr24"])
        if not math.isfinite(atr) or atr <= 0.0:
            raise RD25Error(f"ATR24 unavailable at frozen signal: {pair} {signal_time}")

        window = frame.iloc[entry_i : exit_i + 1]
        entry_price = float(raw["entry_price"])
        lows = pd.to_numeric(window["low"], errors="raise").astype(float)
        highs = pd.to_numeric(window["high"], errors="raise").astype(float)
        min_pos = int(lows.to_numpy().argmin())
        max_pos = int(highs.to_numpy().argmax())
        min_low = float(lows.iloc[min_pos])
        max_high = float(highs.iloc[max_pos])
        mae_return = min_low / entry_price - 1.0
        mfe_return = max_high / entry_price - 1.0
        gross_final = float(raw["exit_price"]) / entry_price - 1.0
        net_final = float(raw["net_pnl"]) / float(raw["entry_notional"])
        mfe_atr = (max_high - entry_price) / atr
        mae_atr = (entry_price - min_low) / atr

        checkpoints: dict[str, float | None] = {}
        for horizon in (24, 72, 168):
            checkpoint_i = lookup.get(int((entry_time + pd.Timedelta(hours=horizon)).value))
            checkpoints[f"open_return_{horizon}h"] = (
                float(frame.iloc[checkpoint_i]["open"]) / entry_price - 1.0
                if checkpoint_i is not None
                else None
            )

        giveback = (mfe_return - gross_final) / mfe_return if mfe_return > 0.0 else math.nan
        row = {
            "portfolio_id": str(raw["portfolio_id"]),
            "universe_id": str(raw["universe_id"]),
            "pair": pair,
            "period_id": str(raw["period_id"]),
            "signal_time": signal_time,
            "entry_time": entry_time,
            "exit_time": exit_time,
            "entry_price": entry_price,
            "atr24_at_signal": atr,
            "net_final_return": net_final,
            "gross_final_return": gross_final,
            "winner": bool(float(raw["net_pnl"]) > 0.0),
            "mae_return": mae_return,
            "mfe_return": mfe_return,
            "mae_atr": mae_atr,
            "mfe_atr": mfe_atr,
            "hours_to_mae": float(
                (pd.Timestamp(window.iloc[min_pos]["timestamp"]) - entry_time).total_seconds()
                / 3600.0
            ),
            "hours_to_mfe": float(
                (pd.Timestamp(window.iloc[max_pos]["timestamp"]) - entry_time).total_seconds()
                / 3600.0
            ),
            "mfe_giveback_fraction_at_168h": giveback,
            "hit_minus_1atr": bool(mae_atr >= 1.0),
            "hit_minus_2atr": bool(mae_atr >= 2.0),
            "hit_minus_3atr": bool(mae_atr >= 3.0),
            "hit_plus_1atr": bool(mfe_atr >= 1.0),
            "hit_plus_2atr": bool(mfe_atr >= 2.0),
            "hit_plus_3atr": bool(mfe_atr >= 3.0),
            **checkpoints,
        }
        rows.append(row)
        if number % 500 == 0:
            print(f"RD25_EXCURSION_PROGRESS={number}/{len(focus)}", flush=True)
    return pd.DataFrame.from_records(rows)


def excursion_summary(excursions: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    grouped = excursions.groupby(
        ["portfolio_id", "universe_id", "period_id", "winner"],
        sort=True,
    )
    for keys, group in grouped:
        portfolio, universe, period, winner = keys
        giveback = pd.to_numeric(group["mfe_giveback_fraction_at_168h"], errors="coerce").replace(
            [np.inf, -np.inf], np.nan
        )
        rows.append(
            {
                "portfolio_id": portfolio,
                "universe_id": universe,
                "period_id": period,
                "winner": bool(winner),
                "trade_count": len(group),
                "mean_net_final_return": float(group["net_final_return"].mean()),
                "median_mae_atr": float(group["mae_atr"].median()),
                "p75_mae_atr": float(group["mae_atr"].quantile(0.75)),
                "median_mfe_atr": float(group["mfe_atr"].median()),
                "p75_mfe_atr": float(group["mfe_atr"].quantile(0.75)),
                "share_hit_minus_1atr": float(group["hit_minus_1atr"].mean()),
                "share_hit_minus_2atr": float(group["hit_minus_2atr"].mean()),
                "share_hit_minus_3atr": float(group["hit_minus_3atr"].mean()),
                "share_hit_plus_2atr": float(group["hit_plus_2atr"].mean()),
                "median_hours_to_mae": float(group["hours_to_mae"].median()),
                "median_hours_to_mfe": float(group["hours_to_mfe"].median()),
                "median_mfe_giveback_fraction": (
                    float(giveback.median()) if bool(giveback.notna().any()) else None
                ),
            }
        )
    return pd.DataFrame.from_records(rows)


def focus_pair_union_diagnostic(
    events: pd.DataFrame,
    frames: dict[str, pd.DataFrame],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    metric_rows: list[dict[str, Any]] = []
    trade_sets: list[pd.DataFrame] = []
    routing_rows: list[dict[str, Any]] = []
    concentration_rows: list[dict[str, Any]] = []
    portfolio_id = "POST_RESULT_DIAGNOSTIC_BREAKOUT_PLUS_RELATIVE_STRENGTH"

    for universe in UNIVERSES:
        union = union_events(
            events,
            universe_id=universe,
            families=FOCUS_FAMILIES,
        )
        for cost in COST_MULTIPLIERS:
            trade_frame, _daily, metrics, counters = replay_portfolio(
                portfolio_id=portfolio_id,
                universe_id=universe,
                cost_multiplier=cost,
                events=union,
                frames=frames,
            )
            metric_rows.append(metrics)
            trade_sets.append(trade_frame)
            routing_rows.append(
                {
                    "portfolio_id": portfolio_id,
                    "universe_id": universe,
                    "cost_multiplier": cost,
                    **counters,
                }
            )
            concentration_rows.append(
                {
                    "portfolio_id": portfolio_id,
                    "universe_id": universe,
                    "cost_multiplier": cost,
                    **concentration_diagnostics(trade_frame),
                }
            )
            print(
                "RD25_FOCUS_UNION="
                f"{universe}:{cost}x:"
                f"net={metrics['net_return']:.6f}:"
                f"pf={metrics['profit_factor']:.6f}:"
                f"dd={metrics['maximum_drawdown']:.6f}",
                flush=True,
            )

    metrics = pd.DataFrame.from_records(metric_rows)
    trades = pd.concat(trade_sets, ignore_index=True)
    return (
        metrics,
        period_metrics(trades),
        pd.DataFrame.from_records(routing_rows),
        pd.DataFrame.from_records(concentration_rows),
    )


def diagnosis_payload(
    *,
    taxonomy: pd.DataFrame,
    scaling: pd.DataFrame,
    focus_metrics: pd.DataFrame,
    excursion_summary_frame: pd.DataFrame,
) -> dict[str, Any]:
    family_dd_only = (
        taxonomy.groupby("family_id", sort=True)["dd_only_failure"]
        .agg(["count", "all"])
        .reset_index()
    )
    dd_only = sorted(
        family_dd_only.loc[
            (family_dd_only["count"] == len(UNIVERSES)) & family_dd_only["all"],
            "family_id",
        ].astype(str)
    )
    multi_failure = sorted(set((*FOCUS_FAMILIES, *SECONDARY_FAMILIES)).difference(dd_only))
    scaling_2x: dict[str, dict[str, float | None]] = {}
    for family in (*FOCUS_FAMILIES, "UNION_ALL_RAW_QUALIFIED"):
        family_rows = scaling.loc[scaling["portfolio_id"] == family]
        per_universe: dict[str, float | None] = {}
        for universe in UNIVERSES:
            subset = family_rows.loc[
                (family_rows["universe_id"] == universe) & family_rows["meets_20pct_daily_close_dd"]
            ]
            per_universe[universe] = (
                float(subset["scalar_of_realized_rd24_pnl_path"].max()) if len(subset) else None
            )
        scaling_2x[family] = per_universe

    union_2x = focus_metrics.loc[focus_metrics["cost_multiplier"] == 2.0]
    union_summary = {
        str(row["universe_id"]): {
            "net_return": float(row["net_return"]),
            "profit_factor": float(row["profit_factor"]),
            "maximum_drawdown": float(row["maximum_drawdown"]),
            "trade_count": int(row["trade_count"]),
        }
        for row in union_2x.to_dict(orient="records")
    }

    winners = excursion_summary_frame.loc[excursion_summary_frame["winner"]].copy()
    losers = excursion_summary_frame.loc[~excursion_summary_frame["winner"]].copy()

    return {
        "schema_version": "rd25-p1-portfolio-translation-diagnosis-v1",
        "stage": "RD25_PORTFOLIO_TRANSLATION_DIAGNOSIS",
        "decision": "RD25_DIAGNOSIS_COMPLETE_ARCHITECTURE_PREREGISTRATION_REQUIRED",
        "dd_only_failure_families": dd_only,
        "multi_failure_families": multi_failure,
        "focus_families": list(FOCUS_FAMILIES),
        "fixed_route_daily_close_max_scalar_meeting_20pct_dd": scaling_2x,
        "focus_pair_union_status": "POST_RESULT_DIAGNOSTIC_NOT_CANDIDATE",
        "focus_pair_union_2x_metrics": union_summary,
        "winner_excursion_summary_rows": len(winners),
        "loser_excursion_summary_rows": len(losers),
        "interpretation_guardrails": [
            "NO_RD25_COUNTERFACTUAL_IS_A_FINALIST",
            "NO_ARCHITECTURE_PARAMETER_IS_SELECTED_IN_RD25",
            "FOCUS_PAIR_UNION_IS_RESULT_INFORMED_DIAGNOSTIC_ONLY",
            "FIXED_ROUTE_SCALING_DOES_NOT_REROUTE_OR_RESIZE_TRADES",
            "TRADE_EXCURSIONS_DESCRIBE_EXISTING_RD24_TRADES_ONLY",
        ],
        "next_stage": "RD26_ARCHITECTURE_PREREGISTRATION_PRE_2022_2023",
        "2022_2023_accessed": False,
        "2024_accessed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
    }


def output_manifest(output: Path, decision: str) -> dict[str, Any]:
    rows = []
    for name in OUTPUT_NAMES:
        path = output / name
        rows.append(
            {
                "path": name,
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
        )
    deterministic = hashlib.sha256(
        "".join(f"{item['path']}:{item['sha256']}\n" for item in rows).encode("utf-8")
    ).hexdigest()
    return {
        "schema_version": "rd25-p1-output-manifest-v1",
        "decision": decision,
        "deterministic_hash": deterministic,
        "files": rows,
        "architecture_selection_executed": False,
        "2022_2023_accessed": False,
        "2024_accessed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
    }


def validate_outputs(repo: Path) -> dict[str, Any]:
    output = repo / OUTPUT
    manifest_path = output / "output-manifest.json"
    if not manifest_path.is_file():
        raise RD25Error("RD25 output manifest missing")
    manifest = load_json(manifest_path)
    by_name = {
        str(item["path"]): item for item in manifest.get("files", []) if isinstance(item, dict)
    }
    if set(by_name) != set(OUTPUT_NAMES):
        raise RD25Error("RD25 manifest output set drifted")
    for name in OUTPUT_NAMES:
        path = output / name
        if not path.is_file():
            raise RD25Error(f"RD25 output missing: {name}")
        item = by_name[name]
        if path.stat().st_size != int(item["bytes"]):
            raise RD25Error(f"RD25 byte-size drift: {name}")
        if sha256(path) != str(item["sha256"]):
            raise RD25Error(f"RD25 hash drift: {name}")

    diagnosis = load_json(output / "diagnosis.json")
    if diagnosis.get("decision") != (
        "RD25_DIAGNOSIS_COMPLETE_ARCHITECTURE_PREREGISTRATION_REQUIRED"
    ):
        raise RD25Error("RD25 diagnosis decision drifted")
    for field in (
        "2022_2023_accessed",
        "2024_accessed",
        "post_2024_accessed",
        "production_authorized",
    ):
        if diagnosis.get(field) is not False:
            raise RD25Error(f"prohibited RD25 flag is true: {field}")

    excursions = pd.read_csv(output / "trade-path-excursions.csv", low_memory=False)
    if excursions.empty:
        raise RD25Error("RD25 excursion ledger is empty")
    entry = pd.to_datetime(excursions["entry_time"], utc=True, errors="raise")
    exit_ = pd.to_datetime(excursions["exit_time"], utc=True, errors="raise")
    if bool((entry >= DATA_CUTOFF).any()) or bool((exit_ > DATA_CUTOFF).any()):
        raise RD25Error("RD25 excursion crossed 2022 boundary")
    if set(excursions["portfolio_id"].astype(str)) != set(FOCUS_FAMILIES):
        raise RD25Error("RD25 excursion family set drifted")

    return {
        "status": "PASS",
        "decision": diagnosis["decision"],
        "focus_families": diagnosis["focus_families"],
        "excursion_rows": len(excursions),
        "manifest_hash": sha256(manifest_path),
        "2022_2023_accessed": False,
        "2024_accessed": False,
    }


def main() -> int:
    args = parser().parse_args()
    repo = args.repo_root.resolve()
    raw_root = (
        args.raw_root.resolve()
        if args.raw_root is not None
        else (repo / DEFAULT_RAW_ROOT).resolve()
    )

    mode_count = sum(
        int(value) for value in (args.preflight_only, args.execute, args.validate_only)
    )
    if mode_count != 1:
        raise RD25Error("choose exactly one mode")

    if args.validate_only:
        print(json.dumps(validate_outputs(repo), indent=2, sort_keys=True))
        return 0

    audit = verify_inputs(
        repo,
        raw_root,
        executing=args.execute,
        expected_freeze_commit=args.expected_freeze_commit,
    )

    if args.preflight_only:
        print(
            json.dumps(
                {
                    "status": "PASS",
                    "stage": "RD25_PORTFOLIO_TRANSLATION_DIAGNOSIS_PREFLIGHT",
                    "focus_families": list(FOCUS_FAMILIES),
                    "architecture_selection_authorized": False,
                    "2022_2023_accessed": False,
                    "2024_accessed": False,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    output = repo / OUTPUT
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "input-and-conformance-audit.json", audit)

    gates = pd.read_csv(repo / RD24_OUTPUT / "hard-gate-evaluation.csv")
    daily = pd.read_csv(repo / RD24_OUTPUT / "daily-equity.csv", low_memory=False)
    routing = pd.read_csv(repo / RD24_OUTPUT / "routing-summary.csv")
    trades = pd.read_csv(repo / RD24_OUTPUT / "trade-ledger.csv", low_memory=False)

    taxonomy = failure_taxonomy(gates)
    drawdowns = drawdown_episodes(daily)
    pressure = routing_pressure(routing)
    scaling = fixed_route_scaling(daily)

    raw_events = prepare_frozen_events(pd.read_csv(repo / RD23_SIGNALS, low_memory=False))
    pairs = sorted(set(raw_events["pair"].astype(str)))
    frames = load_frames(raw_root, pairs)

    excursions = trade_excursions(trades, frames)
    excursion_agg = excursion_summary(excursions)

    focus_metrics, focus_periods, focus_routing, focus_concentration = focus_pair_union_diagnostic(
        raw_events, frames
    )

    diagnosis = diagnosis_payload(
        taxonomy=taxonomy,
        scaling=scaling,
        focus_metrics=focus_metrics,
        excursion_summary_frame=excursion_agg,
    )

    taxonomy.to_csv(output / "failure-taxonomy.csv", index=False, lineterminator="\n")
    drawdowns.to_csv(output / "drawdown-episodes.csv", index=False, lineterminator="\n")
    pressure.to_csv(output / "routing-pressure.csv", index=False, lineterminator="\n")
    scaling.to_csv(
        output / "fixed-route-exposure-scaling.csv",
        index=False,
        lineterminator="\n",
    )
    excursions.to_csv(
        output / "trade-path-excursions.csv",
        index=False,
        lineterminator="\n",
    )
    excursion_agg.to_csv(
        output / "excursion-summary.csv",
        index=False,
        lineterminator="\n",
    )
    focus_metrics.to_csv(
        output / "focus-pair-union-run-metrics.csv",
        index=False,
        lineterminator="\n",
    )
    focus_periods.to_csv(
        output / "focus-pair-union-period-metrics.csv",
        index=False,
        lineterminator="\n",
    )
    focus_routing.to_csv(
        output / "focus-pair-union-routing.csv",
        index=False,
        lineterminator="\n",
    )
    focus_concentration.to_csv(
        output / "focus-pair-union-concentration.csv",
        index=False,
        lineterminator="\n",
    )
    write_json(output / "diagnosis.json", diagnosis)
    write_json(output / "output-manifest.json", output_manifest(output, diagnosis["decision"]))

    result = validate_outputs(repo)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RD25Error as exc:
        print(f"RD25_ERROR={exc}", file=sys.stderr)
        raise SystemExit(2) from exc
