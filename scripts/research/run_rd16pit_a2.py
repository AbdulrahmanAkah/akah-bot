from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final, cast

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from spotbot.research import rd16m_evaluation as rd16m  # noqa: E402
from spotbot.research import rd16n_evaluation as rd16n  # noqa: E402
from spotbot.research.rd16c_common import (  # noqa: E402
    ROOT,
    dataframe_content_hash,
    read_json_object,
)
from spotbot.research.rd16d_common import (  # noqa: E402
    COST_MULTIPLIERS,
    INITIAL_EQUITY,
)
from spotbot.research.rd16d_metrics import (  # noqa: E402
    build_benchmark_daily,
    build_equity_curve,
    bull_window_rows,
    concentration_row,
    drawdown_episode_rows,
    performance_metrics,
    period_return_rows,
)
from spotbot.research.rd16k_remediation import (  # noqa: E402
    VARIANT_BY_ID,
    route_remediation_candidates,
)
from spotbot.research.rd16l_architecture import (  # noqa: E402
    SOURCE_VARIANT_ID,
    prepare_v3_ledgers,
)
from spotbot.research.rd16l_registration import (  # noqa: E402
    load_source_ledgers,
)

SCHEMA_VERSION: Final = "rd16-pit-a2-dynamic-v3-replay-v1"
SOURCE_COMMIT: Final = "682bf4f4029a04015086c357c645199b6cabf717"
STAGE: Final = "RD16_PIT_A2_DYNAMIC_V3_REPLAY"
ARCHITECTURE_ID: Final = "COMPOSITE_ALPHA_V3_PIT_DYNAMIC"
CONTROL_ID: Final = "COMPOSITE_ALPHA_V3_FROZEN_CONTROL"
SEALED_CUTOFF: Final = pd.Timestamp("2025-01-01T00:00:00Z")

A1B_ROOT: Final = ROOT / "data" / "research" / "rd16pit_a1b"
A2_ROOT: Final = ROOT / "data" / "research" / "rd16pit_a2"
A2_RAW_ROOT: Final = A2_ROOT / "raw"
REPORTS_ROOT: Final = ROOT / "reports" / "research"
RD16M_ROOT: Final = ROOT / "data" / "research" / "rd16m"

PERFORMANCE_FIELDS: Final = (
    "scope",
    "cost_multiplier",
    "trade_count",
    "starting_equity",
    "final_equity",
    "net_return",
    "cagr",
    "monthly_geometric_return",
    "maximum_drawdown",
    "profit_factor",
    "win_rate",
    "total_fees",
    "turnover_on_initial_equity",
    "exposure_fraction",
    "average_gross_exposure",
    "maximum_positions_observed",
    "minimum_cash",
    "minimum_equity",
    "capital_feasible",
)


class A2Error(RuntimeError):
    pass


def timestamp(value: object) -> pd.Timestamp:
    parsed = pd.Timestamp(cast(Any, value))
    if parsed.tzinfo is None:
        return parsed.tz_localize("UTC")
    return parsed.tz_convert("UTC")


def finite(value: object, *, field: str) -> float:
    if isinstance(value, bool):
        raise A2Error(f"{field} cannot be boolean.")
    try:
        numeric = float(cast(str | int | float, value))
    except (TypeError, ValueError) as error:
        raise A2Error(f"{field} must be numeric.") from error
    if not math.isfinite(numeric):
        raise A2Error(f"{field} must be finite.")
    return numeric


def scalar_int(value: object, *, field: str) -> int:
    if isinstance(value, bool):
        raise A2Error(f"{field} cannot be boolean.")
    try:
        return int(cast(str | int | float, value))
    except (TypeError, ValueError) as error:
        raise A2Error(f"{field} must be integer-compatible.") from error


def records(frame: pd.DataFrame) -> list[dict[str, object]]:
    return cast(list[dict[str, object]], frame.to_dict(orient="records"))


def base_symbol(value: object) -> str:
    return str(value).upper().split("/")[0].split("-")[0]


def rebalance_week(value: object) -> pd.Timestamp:
    parsed = timestamp(value).normalize()
    return parsed - pd.Timedelta(days=parsed.weekday())


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            json_safe(dict(payload)),
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )


def json_safe(value: object) -> object:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, np.generic):
        return json_safe(value.item())
    if isinstance(value, pd.Timestamp):
        return timestamp(value).isoformat()
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, Mapping):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [json_safe(item) for item in value]
    return str(value)


def write_frame(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix == ".parquet":
        frame.to_parquet(path, index=False)
    elif path.suffix == ".csv":
        frame.to_csv(path, index=False, lineterminator="\n")
    else:
        raise A2Error(f"Unsupported frame output: {path}")


def validate_no_sealed_rows(frame: pd.DataFrame) -> None:
    for column in (
        "signal_close",
        "entry_open_time",
        "entry_bar_close",
        "exit_bar_close",
    ):
        if column not in frame.columns or frame.empty:
            continue
        values = pd.to_datetime(cast(Any, frame[column]), utc=True, errors="raise")
        if bool(values.ge(SEALED_CUTOFF).any()):
            raise A2Error(f"Sealed cutoff violation in {column}.")


def load_membership() -> tuple[pd.DataFrame, pd.DataFrame]:
    membership_path = A1B_ROOT / "weekly-membership-2019-2024.csv"
    snapshot_path = A1B_ROOT / "weekly-snapshot-summary.csv"
    if not membership_path.is_file() or not snapshot_path.is_file():
        raise A2Error("Corrected A1B membership outputs are missing.")
    membership = pd.read_csv(membership_path)
    snapshots = pd.read_csv(snapshot_path)
    required_membership = {
        "rebalance_time",
        "canonical_symbol",
        "market_cap_rank",
        "top6_member",
    }
    missing = sorted(required_membership.difference(membership.columns))
    if missing:
        raise A2Error(f"A1B membership columns missing: {missing}")
    membership["rebalance_time"] = pd.to_datetime(
        cast(Any, membership["rebalance_time"]),
        utc=True,
        errors="raise",
    )
    membership["canonical_symbol"] = membership["canonical_symbol"].astype(str).str.upper()
    membership["market_cap_rank"] = pd.to_numeric(
        membership["market_cap_rank"],
        errors="raise",
    ).astype(int)
    snapshots["rebalance_time"] = pd.to_datetime(
        cast(Any, snapshots["rebalance_time"]),
        utc=True,
        errors="raise",
    )
    snapshots["snapshot_complete"] = snapshots["snapshot_complete"].astype(bool)
    if not bool(snapshots["snapshot_complete"].all()):
        raise A2Error("A2 requires all A1B weekly snapshots to be complete.")
    return membership, snapshots


def annotate_candidate_membership(
    candidates: pd.DataFrame,
    membership: pd.DataFrame,
    snapshots: pd.DataFrame,
) -> pd.DataFrame:
    result = candidates.copy()
    result["candidate_base_symbol"] = result["symbol"].map(base_symbol)
    result["pit_rebalance_time"] = pd.to_datetime(
        cast(Any, result["entry_open_time"]),
        utc=True,
        errors="raise",
    ).map(rebalance_week)

    rank_lookup = {
        (timestamp(row["rebalance_time"]), str(row["canonical_symbol"])): scalar_int(
            row["market_cap_rank"],
            field="market_cap_rank",
        )
        for row in records(membership)
    }
    complete_weeks = {
        timestamp(row["rebalance_time"])
        for row in records(snapshots)
        if bool(row["snapshot_complete"])
    }

    ranks: list[int | None] = []
    methods: list[str] = []
    eligible: list[bool] = []
    for row in records(result):
        week = timestamp(row["pit_rebalance_time"])
        symbol = str(row["candidate_base_symbol"])
        rank = rank_lookup.get((week, symbol))
        if rank is not None:
            ranks.append(rank)
            methods.append("EXACT_TOP30_RANK")
            eligible.append(rank <= 6)
        elif week in complete_weeks:
            ranks.append(31)
            methods.append("COMPLETE_TOP30_ABSENCE")
            eligible.append(False)
        else:
            ranks.append(None)
            methods.append("UNRESOLVED_WEEKLY_SNAPSHOT")
            eligible.append(False)

    result["pit_market_cap_rank_lower_bound"] = ranks
    result["pit_rank_resolution_method"] = methods
    result["pit_top6_eligible"] = eligible
    unresolved = result["pit_rank_resolution_method"].eq("UNRESOLVED_WEEKLY_SNAPSHOT")
    if bool(unresolved.any()):
        raise A2Error(
            "Candidate PIT membership unresolved for "
            f"{scalar_int(cast(Any, unresolved.sum()), field='unresolved_count')} rows."
        )
    return result


def with_recomputed_conflict_rank(candidates: pd.DataFrame) -> pd.DataFrame:
    working = candidates.copy()
    for column in (
        "signal_close",
        "entry_open_time",
        "entry_bar_close",
        "exit_bar_close",
    ):
        working[column] = pd.to_datetime(
            cast(Any, working[column]),
            utc=True,
            errors="raise",
        )
    working = working.sort_values(
        by=[
            "entry_open_time",
            "engine_priority",
            "symbol",
            "signal_close",
            "source_trade_id",
        ],
        kind="stable",
    ).reset_index(drop=True)
    if "conflict_rank" in working.columns:
        working = working.drop(columns=["conflict_rank"])
    working["conflict_rank"] = working.groupby(
        ["entry_open_time", "symbol"],
        sort=False,
    ).cumcount()
    return working


def control_replay(
    source: Mapping[str, pd.DataFrame],
) -> tuple[dict[str, pd.DataFrame], dict[str, bool]]:
    variant = VARIANT_BY_ID[SOURCE_VARIANT_ID]
    routed = route_remediation_candidates(
        with_recomputed_conflict_rank(source["candidates"]),
        variant=variant,
    )
    registered = prepare_v3_ledgers(
        routed.candidates,
        routed.evaluated,
        routed.trades,
    )
    replay = {
        "candidates": registered.candidates,
        "evaluated": registered.evaluated,
        "trades": registered.trades,
    }
    frozen, _ = rd16n._load_v3_ledgers()
    exact = {
        name: dataframe_content_hash(replay[name]) == dataframe_content_hash(frozen[name])
        for name in ("candidates", "evaluated", "trades")
    }
    if not all(exact.values()):
        raise A2Error(f"Frozen V3 control replay mismatch: {exact}")
    return replay, exact


def route_pit_candidates(
    annotated: pd.DataFrame,
) -> dict[str, pd.DataFrame]:
    eligible = annotated.loc[annotated["pit_top6_eligible"].astype(bool)].copy()
    if eligible.empty:
        raise A2Error("PIT Top-6 filter produced no candidates.")
    variant = VARIANT_BY_ID[SOURCE_VARIANT_ID]
    routed = route_remediation_candidates(
        with_recomputed_conflict_rank(eligible),
        variant=variant,
    )
    registered = prepare_v3_ledgers(
        routed.candidates,
        routed.evaluated,
        routed.trades,
    )
    result = {
        "candidates": registered.candidates,
        "evaluated": registered.evaluated,
        "trades": registered.trades,
    }
    for frame in result.values():
        validate_no_sealed_rows(frame)
    return result


def evaluate_scope(
    trades: pd.DataFrame,
    *,
    scope: str,
    hourly_frames: Mapping[str, pd.DataFrame],
    timeline: pd.DatetimeIndex,
) -> tuple[dict[float, pd.DataFrame], dict[float, dict[str, object]], pd.DataFrame]:
    curves: dict[float, pd.DataFrame] = {}
    metrics: dict[float, dict[str, object]] = {}
    rows: list[dict[str, object]] = []
    for multiplier in COST_MULTIPLIERS:
        curve = build_equity_curve(
            trades,
            hourly_frames=hourly_frames,
            timeline=timeline,
            cost_multiplier=multiplier,
        )
        metric = performance_metrics(
            curve,
            trades,
            cost_multiplier=multiplier,
        )
        curves[multiplier] = curve
        metrics[multiplier] = metric
        rows.append(
            {
                "scope": scope,
                **{field: metric[field] for field in PERFORMANCE_FIELDS if field != "scope"},
            }
        )
    return curves, metrics, pd.DataFrame(rows, columns=PERFORMANCE_FIELDS)


def summarize_group(
    trades: pd.DataFrame,
    *,
    column: str,
    output_column: str,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for value, group in trades.groupby(column, sort=True, dropna=False):
        pnl = pd.to_numeric(cast(Any, group["net_pnl"]), errors="raise")
        risk = pd.to_numeric(cast(Any, group["risk_budget"]), errors="raise")
        gross_profit = finite(
            cast(Any, pnl[pnl > 0.0].sum()),
            field="gross_profit",
        )
        gross_loss = abs(
            finite(
                cast(Any, pnl[pnl < 0.0].sum()),
                field="gross_loss",
            )
        )
        net_pnl = finite(cast(Any, pnl.sum()), field="group_net_pnl")
        rows.append(
            {
                output_column: str(value),
                "trade_count": len(group),
                "net_pnl": net_pnl,
                "return_on_initial_equity": net_pnl / INITIAL_EQUITY,
                "win_rate": finite(
                    cast(Any, (pnl > 0.0).mean()),
                    field="group_win_rate",
                ),
                "profit_factor": (gross_profit / gross_loss if gross_loss > 0.0 else None),
                "average_r": finite(
                    cast(Any, (pnl / risk).mean()),
                    field="average_r",
                ),
                "median_r": finite(
                    cast(Any, (pnl / risk).median()),
                    field="median_r",
                ),
            }
        )
    return pd.DataFrame(rows)


def router_summary(evaluated: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for decision, group in evaluated.groupby("router_decision", sort=True):
        pnl = pd.to_numeric(cast(Any, group["net_pnl"]), errors="raise")
        net_pnl = finite(
            cast(Any, pnl.sum()),
            field="router_hypothetical_net_pnl",
        )
        rows.append(
            {
                "router_decision": str(decision),
                "candidate_count": len(group),
                "hypothetical_net_pnl": net_pnl,
                "hypothetical_return_on_initial": net_pnl / INITIAL_EQUITY,
            }
        )
    return pd.DataFrame(rows)


def admission_changes(
    frozen_trades: pd.DataFrame,
    dynamic_trades: pd.DataFrame,
    dynamic_evaluated: pd.DataFrame,
) -> pd.DataFrame:
    original_ids = set(frozen_trades["source_v2_candidate_id"].astype(str))
    dynamic_ids = set(dynamic_trades["source_v2_candidate_id"].astype(str))
    decision_lookup = {
        str(row["source_v2_candidate_id"]): str(row["router_decision"])
        for row in records(dynamic_evaluated)
    }
    pnl_lookup = {
        str(row["source_v2_candidate_id"]): finite(
            row["net_pnl"],
            field="net_pnl",
        )
        for row in records(dynamic_evaluated)
    }
    rows: list[dict[str, object]] = []
    for candidate_id in sorted(original_ids | dynamic_ids):
        originally_admitted = candidate_id in original_ids
        dynamically_admitted = candidate_id in dynamic_ids
        if originally_admitted and dynamically_admitted:
            change = "RETAINED_ADMISSION"
        elif originally_admitted:
            change = "DROPPED_OR_INELIGIBLE"
        else:
            change = "NEWLY_ADMITTED_AFTER_REROUTE"
        rows.append(
            {
                "source_v2_candidate_id": candidate_id,
                "admission_change": change,
                "originally_admitted": originally_admitted,
                "dynamically_admitted": dynamically_admitted,
                "dynamic_router_decision": decision_lookup.get(
                    candidate_id,
                    "NOT_PIT_ELIGIBLE",
                ),
                "candidate_net_pnl": pnl_lookup.get(candidate_id),
            }
        )
    return pd.DataFrame(rows)


def weekly_universe_coverage(
    membership: pd.DataFrame,
    candidate_symbols: set[str],
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    top6 = membership.loc[
        pd.to_numeric(cast(Any, membership["market_cap_rank"]), errors="raise").le(6)
    ]
    for week, group in top6.groupby("rebalance_time", sort=True):
        symbols = set(group["canonical_symbol"].astype(str))
        represented = symbols & candidate_symbols
        missing = symbols - candidate_symbols
        rows.append(
            {
                "rebalance_time": timestamp(week),
                "true_top6_count": len(symbols),
                "represented_top6_count": len(represented),
                "coverage_ratio": len(represented) / 6.0,
                "full_top6_coverage": len(represented) == 6,
                "represented_symbols": "|".join(sorted(represented)),
                "missing_symbols": "|".join(sorted(missing)),
            }
        )
    return pd.DataFrame(rows)


def mean_high_opportunity_capture(rows: Sequence[Mapping[str, object]]) -> float:
    values = [
        finite(row["capture_ratio"], field="capture_ratio")
        for row in rows
        if bool(row["high_opportunity_window"]) and row.get("capture_ratio") is not None
    ]
    return sum(values) / len(values) if values else 0.0


def classify_replay(
    dynamic_1x: Mapping[str, object],
    dynamic_2x: Mapping[str, object],
    baseline_1x: Mapping[str, object],
    *,
    full_top6_coverage_fraction: float,
) -> tuple[str, str, dict[str, bool]]:
    dynamic_return = finite(dynamic_1x["net_return"], field="dynamic_return")
    dynamic_pf = finite(dynamic_1x["profit_factor"], field="dynamic_pf")
    dynamic_dd = finite(
        dynamic_1x["maximum_drawdown"],
        field="dynamic_drawdown",
    )
    dynamic_2x_return = finite(
        dynamic_2x["net_return"],
        field="dynamic_2x_return",
    )
    dynamic_2x_pf = finite(
        dynamic_2x["profit_factor"],
        field="dynamic_2x_pf",
    )
    baseline_return = finite(
        baseline_1x["net_return"],
        field="baseline_return",
    )
    baseline_dd = finite(
        baseline_1x["maximum_drawdown"],
        field="baseline_drawdown",
    )
    retention = dynamic_return / baseline_return if baseline_return > 0.0 else 0.0

    gates = {
        "one_x_positive": dynamic_return > 0.0,
        "one_x_profit_factor_gte_1": dynamic_pf >= 1.0,
        "one_x_capital_feasible": bool(dynamic_1x["capital_feasible"]),
        "two_x_positive": dynamic_2x_return > 0.0,
        "two_x_profit_factor_gte_1": dynamic_2x_pf >= 1.0,
        "two_x_capital_feasible": bool(dynamic_2x["capital_feasible"]),
        "return_retention_gte_50pct": retention >= 0.50,
        "return_retention_gte_80pct": retention >= 0.80,
        "drawdown_not_worse_by_more_than_5pp": dynamic_dd <= baseline_dd + 0.05,
        "full_top6_candidate_coverage_gte_95pct": (full_top6_coverage_fraction >= 0.95),
    }

    if not gates["one_x_capital_feasible"] or not gates["two_x_capital_feasible"]:
        decision = "PIT_DYNAMIC_REPLAY_CAPITAL_INFEASIBLE"
        next_stage = "RD16_PIT_STOP_AND_REASSESS_BASELINE"
    elif not all(
        gates[key]
        for key in (
            "one_x_positive",
            "one_x_profit_factor_gte_1",
            "two_x_positive",
            "two_x_profit_factor_gte_1",
        )
    ):
        decision = "PIT_DYNAMIC_REPLAY_INVALIDATES_V3"
        next_stage = "RD16_PIT_STOP_AND_REASSESS_BASELINE"
    elif (
        not gates["return_retention_gte_50pct"] or not gates["drawdown_not_worse_by_more_than_5pp"]
    ):
        decision = "PIT_DYNAMIC_REPLAY_SEVERE_DEGRADATION"
        next_stage = "RD16_PIT_A3_ARCHITECTURE_REASSESSMENT"
    elif not gates["return_retention_gte_80pct"]:
        decision = "PIT_DYNAMIC_REPLAY_MATERIAL_DEGRADATION"
        next_stage = "RD16_PIT_A3_ROBUSTNESS_AND_CAPACITY_AUDIT"
    else:
        decision = "PIT_DYNAMIC_REPLAY_SURVIVES"
        next_stage = "RD16_PIT_A3_ROBUSTNESS_AND_CAPACITY_AUDIT"

    if (
        next_stage != "RD16_PIT_STOP_AND_REASSESS_BASELINE"
        and not gates["full_top6_candidate_coverage_gte_95pct"]
    ):
        next_stage = "RD16_PIT_A2B_FULL_TOP6_SIGNAL_DATA_EXPANSION"
    return decision, next_stage, gates


def metrics_comparison(
    baseline: Mapping[str, object],
    dynamic: Mapping[str, object],
) -> pd.DataFrame:
    fields = (
        "trade_count",
        "net_return",
        "monthly_geometric_return",
        "profit_factor",
        "maximum_drawdown",
        "minimum_cash",
        "minimum_equity",
        "total_fees",
        "turnover_on_initial_equity",
        "maximum_positions_observed",
    )
    rows: list[dict[str, object]] = []
    for field in fields:
        left = finite(baseline[field], field=f"baseline_{field}")
        right = finite(dynamic[field], field=f"dynamic_{field}")
        rows.append(
            {
                "metric": field,
                "frozen_v3": left,
                "pit_dynamic": right,
                "absolute_delta": right - left,
                "relative_delta": ((right - left) / abs(left) if left != 0.0 else None),
            }
        )
    return pd.DataFrame(rows)


def output_manifest(paths: Sequence[Path]) -> dict[str, object]:
    entries: dict[str, object] = {}
    for path in paths:
        entries[path.relative_to(ROOT).as_posix()] = {
            "sha256": sha256_file(path),
            "bytes": path.stat().st_size,
        }
    return {
        "schema_version": "rd16-pit-a2-output-manifest-v1",
        "entries": entries,
    }


def write_reports(final: Mapping[str, object]) -> None:
    dynamic_return = finite(
        final["dynamic_net_return"],
        field="dynamic_net_return",
    )
    dynamic_pf = finite(
        final["dynamic_profit_factor"],
        field="dynamic_profit_factor",
    )
    dynamic_drawdown = finite(
        final["dynamic_maximum_drawdown"],
        field="dynamic_maximum_drawdown",
    )
    dynamic_cash = finite(
        final["dynamic_minimum_cash"],
        field="dynamic_minimum_cash",
    )
    dynamic_two_x_return = finite(
        final["dynamic_two_x_net_return"],
        field="dynamic_two_x_net_return",
    )
    dynamic_two_x_pf = finite(
        final["dynamic_two_x_profit_factor"],
        field="dynamic_two_x_profit_factor",
    )
    coverage = finite(
        final["full_top6_candidate_coverage_fraction"],
        field="coverage",
    )
    result_lines = [
        "# RD16-PIT-A2 Dynamic V3 Replay Results",
        "",
        f"- Decision: `{final['decision']}`",
        f"- Validation scope: `{final['validation_scope']}`",
        f"- Frozen V3 trades: {final['baseline_trade_count']}",
        f"- PIT dynamic trades: {final['dynamic_trade_count']}",
        f"- PIT eligible candidates: {final['pit_eligible_candidate_count']}",
        f"- Newly admitted after reroute: {final['newly_admitted_trade_count']}",
        f"- Dynamic net return: {dynamic_return:.6%}",
        f"- Dynamic profit factor: {dynamic_pf:.6f}",
        f"- Dynamic maximum drawdown: {dynamic_drawdown:.6%}",
        f"- Dynamic minimum cash: {dynamic_cash:,.2f}",
        f"- 2x-cost net return: {dynamic_two_x_return:.6%}",
        f"- 2x-cost profit factor: {dynamic_two_x_pf:.6f}",
        f"- Full Top-6 candidate coverage fraction: {coverage:.6%}",
        "",
        "The 2x scenario doubles transaction costs only. It does not use leverage.",
    ]
    decision_lines = [
        "# RD16-PIT-A2 Decision",
        "",
        f"Decision: **{final['decision']}**",
        "",
        f"Next stage: `{final['next_stage']}`",
        "",
        "This stage re-executed the frozen V3 router after causal PIT Top-6 filtering.",
        "It was not a ledger-only deletion exercise.",
        "",
        "Full-market validation is not claimed unless the registered signal universe",
        "covers at least 95% of weekly true Top-6 snapshots.",
        "",
        "RD16-U remains stopped and production remains unauthorized.",
    ]
    (REPORTS_ROOT / "rd16-pit-a2-results-v1.md").write_text(
        "\n".join(result_lines) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    (REPORTS_ROOT / "rd16-pit-a2-decisions-v1.md").write_text(
        "\n".join(decision_lines) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def run_a2() -> dict[str, object]:
    A2_ROOT.mkdir(parents=True, exist_ok=True)
    A2_RAW_ROOT.mkdir(parents=True, exist_ok=True)
    REPORTS_ROOT.mkdir(parents=True, exist_ok=True)

    a1b_report = read_json_object(A1B_ROOT / "rd16pit-a1b-final-report-v1.json")
    if a1b_report.get("decision") != "PIT_MATERIAL_DEGRADATION":
        raise A2Error("A2 requires corrected A1B PIT_MATERIAL_DEGRADATION.")
    if (
        finite(
            a1b_report.get("membership_resolved_trade_ratio"),
            field="a1b_membership_resolved_trade_ratio",
        )
        != 1.0
    ):
        raise A2Error("A2 requires 100% A1B membership resolution.")

    source = load_source_ledgers()
    for frame in source.values():
        validate_no_sealed_rows(frame)
    frozen_control, control_exact = control_replay(source)
    baseline_trades = frozen_control["trades"]
    if len(baseline_trades) != 567:
        raise A2Error(f"Expected 567 frozen V3 trades, found {len(baseline_trades)}.")

    membership, snapshots = load_membership()
    annotated = annotate_candidate_membership(
        source["candidates"],
        membership,
        snapshots,
    )
    if len(annotated) != 688:
        raise A2Error(f"Expected 688 V3 candidates, found {len(annotated)}.")
    dynamic = route_pit_candidates(annotated)
    dynamic_trades = dynamic["trades"]

    hourly_frames, daily_frames = rd16m._load_market_frames()
    timeline = rd16m._timeline(hourly_frames)
    baseline_curves, baseline_metrics, baseline_performance = evaluate_scope(
        baseline_trades,
        scope="FROZEN_V3_CONTROL",
        hourly_frames=hourly_frames,
        timeline=timeline,
    )
    dynamic_curves, dynamic_metrics, dynamic_performance = evaluate_scope(
        dynamic_trades,
        scope="PIT_DYNAMIC_REROUTE",
        hourly_frames=hourly_frames,
        timeline=timeline,
    )

    frozen_report = read_json_object(RD16M_ROOT / "rd16m-final-report-v1.json")
    control_metric_match = all(
        math.isclose(
            finite(baseline_metrics[1.0][key], field=f"control_{key}"),
            finite(frozen_report[key], field=f"frozen_{key}"),
            rel_tol=0.0,
            abs_tol=1e-12,
        )
        for key in (
            "net_return",
            "monthly_geometric_return",
            "profit_factor",
            "maximum_drawdown",
        )
    ) and all(
        math.isclose(
            finite(baseline_metrics[2.0][target], field=f"control_2x_{target}"),
            finite(frozen_report[source_key], field=f"frozen_2x_{source_key}"),
            rel_tol=0.0,
            abs_tol=1e-12,
        )
        for target, source_key in (
            ("net_return", "two_x_net_return"),
            ("profit_factor", "two_x_profit_factor"),
            ("minimum_cash", "two_x_minimum_cash"),
        )
    )
    if not control_metric_match:
        raise A2Error("Control replay economics do not match frozen RD16-M.")

    candidate_symbols = set(annotated["candidate_base_symbol"].astype(str))
    coverage = weekly_universe_coverage(membership, candidate_symbols)
    full_coverage_fraction = finite(
        cast(Any, coverage["full_top6_coverage"].astype(bool).mean()),
        field="full_top6_coverage_fraction",
    )
    average_coverage = finite(
        cast(
            Any,
            pd.to_numeric(
                cast(Any, coverage["coverage_ratio"]),
                errors="raise",
            ).mean(),
        ),
        field="average_top6_coverage",
    )

    changes = admission_changes(
        baseline_trades,
        dynamic_trades,
        dynamic["evaluated"],
    )
    newly_admitted = scalar_int(
        cast(
            Any,
            changes["admission_change"].eq("NEWLY_ADMITTED_AFTER_REROUTE").sum(),
        ),
        field="newly_admitted",
    )
    dropped = scalar_int(
        cast(
            Any,
            changes["admission_change"].eq("DROPPED_OR_INELIGIBLE").sum(),
        ),
        field="dropped_admissions",
    )
    retained = scalar_int(
        cast(
            Any,
            changes["admission_change"].eq("RETAINED_ADMISSION").sum(),
        ),
        field="retained_admissions",
    )

    benchmark = build_benchmark_daily(daily_frames)
    bull_rows = bull_window_rows(
        {ARCHITECTURE_ID: dynamic_curves[1.0]},
        benchmark,
    )
    mean_capture = mean_high_opportunity_capture(bull_rows)
    annual = pd.DataFrame(
        period_return_rows(
            dynamic_curves[1.0],
            dynamic_trades,
            family_id=ARCHITECTURE_ID,
            period="year",
        )
    )
    asset = summarize_group(dynamic_trades, column="symbol", output_column="symbol")
    engine = summarize_group(
        dynamic_trades,
        column="engine_id",
        output_column="engine_id",
    )
    router = router_summary(dynamic["evaluated"])
    concentration = pd.DataFrame([concentration_row(dynamic_trades, family_id=ARCHITECTURE_ID)])
    drawdowns = pd.DataFrame(
        drawdown_episode_rows(
            dynamic_curves[1.0],
            family_id=ARCHITECTURE_ID,
        )
    )
    comparison = metrics_comparison(
        baseline_metrics[1.0],
        dynamic_metrics[1.0],
    )
    performance = pd.concat(
        [baseline_performance, dynamic_performance],
        ignore_index=True,
    )

    decision, next_stage, gates = classify_replay(
        dynamic_metrics[1.0],
        dynamic_metrics[2.0],
        baseline_metrics[1.0],
        full_top6_coverage_fraction=full_coverage_fraction,
    )
    baseline_return = finite(
        baseline_metrics[1.0]["net_return"],
        field="baseline_net_return",
    )
    dynamic_return = finite(
        dynamic_metrics[1.0]["net_return"],
        field="dynamic_net_return",
    )

    output_frames = {
        A2_ROOT / "candidate-membership.csv": annotated,
        A2_ROOT / "performance-summary.csv": performance,
        A2_ROOT / "economic-comparison.csv": comparison,
        A2_ROOT / "annual-returns.csv": annual,
        A2_ROOT / "asset-attribution.csv": asset,
        A2_ROOT / "engine-attribution.csv": engine,
        A2_ROOT / "router-decisions.csv": router,
        A2_ROOT / "admission-changes.csv": changes,
        A2_ROOT / "weekly-universe-coverage.csv": coverage,
        A2_ROOT / "concentration.csv": concentration,
        A2_ROOT / "drawdown-episodes.csv": drawdowns,
        A2_ROOT / "bull-window-capture.csv": pd.DataFrame(bull_rows),
        A2_RAW_ROOT / "pit-dynamic-candidates.parquet": dynamic["candidates"],
        A2_RAW_ROOT / "pit-dynamic-evaluated.parquet": dynamic["evaluated"],
        A2_RAW_ROOT / "pit-dynamic-trades.parquet": dynamic_trades,
        A2_RAW_ROOT / "pit-dynamic-equity-1x.parquet": dynamic_curves[1.0],
        A2_RAW_ROOT / "pit-dynamic-equity-2x.parquet": dynamic_curves[2.0],
    }
    for path, frame in output_frames.items():
        write_frame(path, frame)

    validation = {
        "schema_version": "rd16-pit-a2-validation-v1",
        "control_ledger_exact": control_exact,
        "control_replay_exact": all(control_exact.values()),
        "control_metric_match": control_metric_match,
        "router_reexecuted": True,
        "ledger_filter_only": False,
        "dynamic_v3_replay_performed": True,
        "registered_candidate_universe_only": True,
        "full_market_signal_regeneration": False,
        "candidate_membership_unresolved_count": scalar_int(
            cast(
                Any,
                annotated["pit_rank_resolution_method"].eq("UNRESOLVED_WEEKLY_SNAPSHOT").sum(),
            ),
            field="candidate_membership_unresolved_count",
        ),
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
        "optimization_performed": False,
        "production_authorized": False,
        "rd16_u_authorized": False,
    }
    write_json(A2_ROOT / "validation-report.json", validation)

    final: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "stage": STAGE,
        "source_commit": SOURCE_COMMIT,
        "decision": decision,
        "next_stage": next_stage,
        "validation_scope": "RESTRICTED_REGISTERED_CANDIDATE_UNIVERSE",
        "full_dynamic_validation_claimed": False,
        "control_replay_exact": all(control_exact.values()),
        "control_metric_match": control_metric_match,
        "baseline_candidate_count": len(annotated),
        "pit_eligible_candidate_count": scalar_int(
            cast(Any, annotated["pit_top6_eligible"].astype(bool).sum()),
            field="pit_eligible_candidate_count",
        ),
        "pit_ineligible_candidate_count": scalar_int(
            cast(
                Any,
                (~annotated["pit_top6_eligible"].astype(bool)).sum(),
            ),
            field="pit_ineligible_candidate_count",
        ),
        "candidate_membership_resolved_ratio": 1.0,
        "baseline_trade_count": len(baseline_trades),
        "dynamic_trade_count": len(dynamic_trades),
        "retained_original_admission_count": retained,
        "dropped_original_admission_count": dropped,
        "newly_admitted_trade_count": newly_admitted,
        "baseline_net_return": baseline_return,
        "dynamic_net_return": dynamic_return,
        "return_retention_ratio": (
            dynamic_return / baseline_return if baseline_return > 0.0 else None
        ),
        "dynamic_monthly_geometric_return": dynamic_metrics[1.0]["monthly_geometric_return"],
        "dynamic_profit_factor": dynamic_metrics[1.0]["profit_factor"],
        "dynamic_maximum_drawdown": dynamic_metrics[1.0]["maximum_drawdown"],
        "dynamic_minimum_cash": dynamic_metrics[1.0]["minimum_cash"],
        "dynamic_minimum_equity": dynamic_metrics[1.0]["minimum_equity"],
        "dynamic_capital_feasible": dynamic_metrics[1.0]["capital_feasible"],
        "dynamic_maximum_positions_observed": dynamic_metrics[1.0]["maximum_positions_observed"],
        "dynamic_two_x_net_return": dynamic_metrics[2.0]["net_return"],
        "dynamic_two_x_profit_factor": dynamic_metrics[2.0]["profit_factor"],
        "dynamic_two_x_minimum_cash": dynamic_metrics[2.0]["minimum_cash"],
        "dynamic_two_x_capital_feasible": dynamic_metrics[2.0]["capital_feasible"],
        "two_x_definition": "TRANSACTION_COST_MULTIPLIER_NOT_LEVERAGE",
        "mean_high_opportunity_capture": mean_capture,
        "candidate_universe_symbol_count": len(candidate_symbols),
        "candidate_universe_symbols": sorted(candidate_symbols),
        "average_true_top6_candidate_coverage": average_coverage,
        "full_top6_candidate_coverage_fraction": full_coverage_fraction,
        "decision_gates": gates,
        "router_reexecuted": True,
        "ledger_filter_only": False,
        "dynamic_v3_replay_performed": True,
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
        "optimization_performed": False,
        "production_authorized": False,
        "rd16_u_authorized": False,
    }
    write_json(A2_ROOT / "rd16pit-a2-final-report-v1.json", final)
    write_reports(final)

    manifest_paths = [
        *output_frames.keys(),
        A2_ROOT / "validation-report.json",
        A2_ROOT / "rd16pit-a2-final-report-v1.json",
        REPORTS_ROOT / "rd16-pit-a2-results-v1.md",
        REPORTS_ROOT / "rd16-pit-a2-decisions-v1.md",
    ]
    write_json(A2_ROOT / "output-manifest.json", output_manifest(manifest_paths))

    print(json.dumps(json_safe(final), indent=2, sort_keys=True))
    return final


def main() -> None:
    parser = argparse.ArgumentParser(description="Run RD16-PIT-A2 dynamic V3 replay.")
    parser.add_argument("--repo", required=True, type=Path)
    arguments = parser.parse_args()
    repo = arguments.repo.resolve()
    if repo != ROOT.resolve():
        raise A2Error(f"Repository mismatch: expected {ROOT.resolve()}, found {repo}.")
    run_a2()


if __name__ == "__main__":
    main()
