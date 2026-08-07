"""Run RD19-P2C-R1 conformance correction and optimized replay."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import shutil
import sys
import time
from pathlib import Path
from typing import Any, cast

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from spotbot.research import rd19_p2a_engine as p2a  # noqa: E402
from spotbot.research import rd19_p2c_discovery as p2c  # noqa: E402
from spotbot.research.rd19_p2a_engine import resolve_variants  # noqa: E402
from spotbot.research.rd19_p2c_r1_engine import (  # noqa: E402
    CANDIDATE_ID,
    DATA_CUTOFF,
    DECISION,
    EXPECTED_RUNS,
    PARTITIONS,
    REPAIR_IDS,
    STAGE,
    P2CR1Error,
    build_candidate_plans,
    build_daily_rank_cache,
    build_feature_store,
    execute_run_fast,
    feature_signature,
    write_run_result_atomic,
)

EXPECTED_PARENT = "d94a62f53dab8c7f8da5a030df76e70ec5feef85"
P2_PROTOCOL = "data/research/rd19_p2_runtime/rd19-p2-discovery-protocol-v1.json"
EXECUTION_ORDER = "data/research/rd19_p2_runtime/execution-order.csv"
MEMBERSHIP = "data/research/rd18_p3x_a3b_runtime/effective-operational-membership.csv"
ORIGINAL_P2C_REPORT = "data/research/rd19_p2c_runtime/rd19-p2c-discovery-report-v1.json"
ORIGINAL_P2C_MODULE = "src/spotbot/research/rd19_p2c_discovery.py"

EXPECTED_P2_PROTOCOL_SHA256 = "b5a54bca6d9d918bb84934edd7b6512b026a0774c2abd001b2575698d459d7ab"
EXPECTED_EXECUTION_ORDER_SHA256 = "84139d2c714b198b3324d47d45507c5e861131e47adbe4b574b8de9dada22150"
EXPECTED_ORIGINAL_REPORT_SHA256 = "28511a8954a499918031d6efe1e360fafec16c39ddf22fce2d0f959aab4699be"

PLAN_START = pd.Timestamp("2019-01-01T00:00:00Z")
PLAN_END = pd.Timestamp("2023-12-31T23:00:00Z")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    result.add_argument("--repo-root", type=Path, default=ROOT)
    result.add_argument(
        "--summary-output-dir",
        type=Path,
        default=ROOT / "data/research/rd19_p2c_r1_runtime",
    )
    result.add_argument(
        "--evidence-output-dir",
        type=Path,
        default=(ROOT / "data/research/rd18_p3x_a1_runtime/logs/rd19-p2c-r1-local-evidence-v1"),
    )
    result.add_argument(
        "--raw-root",
        type=Path,
        default=ROOT / "data/raw/rd16b/kucoin",
    )
    result.add_argument("--preflight-only", action="store_true")
    result.add_argument("--execute", action="store_true")
    result.add_argument("--resume", action="store_true")
    return result


def sha256(path: Path) -> str:
    return p2c.sha256(path)


def load_json_object(path: Path) -> dict[str, Any]:
    return p2c.load_json_object(path)


def verify_execution_order(frame: pd.DataFrame) -> None:
    if len(frame) != EXPECTED_RUNS:
        raise P2CR1Error(f"execution-order rows drifted: {len(frame)}")
    observed = (
        pd.to_numeric(
            frame["execution_order"],
            errors="raise",
        )
        .astype(int)
        .tolist()
    )
    if observed != list(range(1, EXPECTED_RUNS + 1)):
        raise P2CR1Error("execution order is not exactly the frozen 1..216 order")
    identity = frame[
        [
            "variant_id",
            "partition_id",
            "universe_id",
            "cost_multiplier",
        ]
    ]
    if bool(identity.duplicated().any()):
        raise P2CR1Error("execution order contains duplicate run identities")


def audit_original_nonconformance(repo: Path) -> dict[str, Any]:
    path = repo / ORIGINAL_P2C_MODULE
    source = path.read_text(encoding="utf-8-sig")
    tree = ast.parse(source, filename=str(path))
    function_sources: dict[str, str] = {}
    lines = source.splitlines()
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            function_sources[node.name] = "\n".join(lines[node.lineno - 1 : node.end_lineno])

    entry = function_sources.get("entry_pass", "")
    ranked = function_sources.get("ranked_pairs", "")
    execute = function_sources.get("execute_run", "")

    checks = {
        "pullback_lookback_parameter_not_used": ("pullback_lookback_bars" not in entry),
        "contraction_uses_breakout_bar_atr": (
            'row["atr"]' in entry and 'row["atr_reference"]' in entry and "prior_atr" not in entry
        ),
        "market_gate_applied_inside_daily_rank_refresh": ("market_gate_pass(" in ranked),
        "top_k_applied_before_hourly_entry_and_cost_filters": (
            '.head(int(config["top_k"]))' in ranked
        ),
        "thesis_invalidation_exits_same_bar_close": (
            'exit_reason = "THESIS_INVALIDATION"' in execute and "exit_price = close" in execute
        ),
        "trail_updated_before_current_bar_low_stop_test": (
            execute.find('position["active_stop"] = max(') < execute.find("if low <= active_stop:")
        ),
    }
    if not all(checks.values()):
        raise P2CR1Error(f"original P2C defect audit drifted: {checks}")
    return {
        "original_commit": EXPECTED_PARENT,
        "original_result_disposition": ("INVALIDATED_FOR_IMPLEMENTATION_NONCONFORMANCE"),
        "confirmed_defects": checks,
        "repair_ids": list(REPAIR_IDS),
        "parameter_changes": 0,
        "matrix_changes": 0,
        "hard_gate_changes": 0,
        "2024_access_authorized": False,
    }


def verify_frozen_inputs(
    repo: Path,
) -> tuple[dict[str, Any], pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    protocol_path = repo / P2_PROTOCOL
    order_path = repo / EXECUTION_ORDER
    report_path = repo / ORIGINAL_P2C_REPORT

    expected_hashes = {
        protocol_path: EXPECTED_P2_PROTOCOL_SHA256,
        order_path: EXPECTED_EXECUTION_ORDER_SHA256,
        report_path: EXPECTED_ORIGINAL_REPORT_SHA256,
    }
    for path, expected in expected_hashes.items():
        if not path.is_file():
            raise P2CR1Error(f"frozen input missing: {path}")
        actual = sha256(path)
        if actual != expected:
            raise P2CR1Error(f"frozen input hash drift: {path.name}: {actual}")

    protocol = load_json_object(protocol_path)
    expected_protocol = {
        "decision": "RD19_P2_DISCOVERY_PROTOCOL_AND_MATRIX_FROZEN",
        "candidate_id": CANDIDATE_ID,
        "variant_count": 12,
        "matrix_frozen": True,
        "parameters_frozen_for_p2": True,
        "post_2024_accessed": False,
        "production_authorized": False,
    }
    drift = {
        key: {"expected": wanted, "actual": protocol.get(key)}
        for key, wanted in expected_protocol.items()
        if protocol.get(key) != wanted
    }
    if drift:
        raise P2CR1Error(f"frozen P2 protocol drift: {drift}")

    execution = pd.read_csv(order_path)
    verify_execution_order(execution)

    membership = pd.read_csv(repo / MEMBERSHIP)
    if len(membership) != 5418:
        raise P2CR1Error(f"membership row count drifted: {len(membership)}")

    original_report = load_json_object(report_path)
    if original_report.get("completed_run_count") != EXPECTED_RUNS:
        raise P2CR1Error("original P2C did not complete 216 runs")
    if original_report.get("hard_gate_pass_variant_count") != 0:
        raise P2CR1Error("original P2C result no longer matches reviewed state")
    if original_report.get("selected_for_2024_variants") != []:
        raise P2CR1Error("original P2C selected finalists unexpectedly")
    if original_report.get("2024_market_data_accessed") is not False:
        raise P2CR1Error("original P2C accessed 2024 unexpectedly")

    audit = audit_original_nonconformance(repo)
    return protocol, execution, membership, audit


def load_raw_frames(
    raw_root: Path,
    pairs: list[str],
) -> dict[str, pd.DataFrame]:
    frames: dict[str, pd.DataFrame] = {}
    cutoff = DATA_CUTOFF.to_pydatetime()
    for index, pair in enumerate(pairs, start=1):
        path = raw_root / pair / "1h.parquet"
        if not path.is_file():
            raise P2CR1Error(f"sealed hourly source missing: {path}")
        frame = pd.read_parquet(
            path,
            engine="pyarrow",
            filters=[("timestamp", "<", cutoff)],
        )
        normalized = p2a.normalize_bars(frame)
        maximum = pd.to_datetime(
            normalized["timestamp"],
            utc=True,
            errors="raise",
        ).max()
        if maximum >= DATA_CUTOFF:
            raise P2CR1Error(f"2024 market row entered memory: {pair}")
        frames[pair] = normalized
        print(
            f"RD19_P2C_R1_SOURCE={index}/{len(pairs)}:{pair}:{len(normalized)}",
            flush=True,
        )
    return frames


def run_dir(
    output: Path,
    execution_order: int,
    run_id: str,
) -> Path:
    return output / "runs" / f"{execution_order:03d}" / run_id


# Aliases required by the frozen aggregation implementation below.
verify_checkpoint = p2c.verify_checkpoint
chain_equity_curves = p2c.chain_equity_curves
profit_factor = p2c.profit_factor
maximum_drawdown = p2c.maximum_drawdown
top_trade_share = p2c.top_trade_share


def aggregate_results(
    output: Path,
    execution: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    run_rows: list[dict[str, object]] = []
    run_dirs: dict[
        tuple[str, str, str, float],
        Path,
    ] = {}
    for raw in execution.to_dict(orient="records"):
        run_id = (
            f"{int(raw['execution_order']):03d}_"
            f"{raw['variant_id']}_{raw['partition_id']}_"
            f"{raw['universe_id']}_{float(raw['cost_multiplier']):.0f}x"
        )
        directory = run_dir(
            output,
            int(raw["execution_order"]),
            run_id,
        )
        verify_checkpoint(directory)
        metrics = load_json_object(directory / "run-metrics.json")
        run_rows.append(metrics)
        run_dirs[
            (
                str(raw["variant_id"]),
                str(raw["universe_id"]),
                str(raw["partition_id"]),
                float(raw["cost_multiplier"]),
            )
        ] = directory
    run_metrics = pd.DataFrame.from_records(run_rows)
    if len(run_metrics) != EXPECTED_RUNS:
        raise P2CR1Error("run metrics do not cover all 216 executions")

    combined_rows: list[dict[str, object]] = []
    for variant_id in sorted(run_metrics["variant_id"].unique()):
        for universe_id in ("C2", "D2", "E2"):
            for cost_multiplier in (1.0, 2.0):
                subset = run_metrics.loc[
                    (run_metrics["variant_id"] == variant_id)
                    & (run_metrics["universe_id"] == universe_id)
                    & (pd.to_numeric(run_metrics["cost_multiplier"]) == cost_multiplier)
                ].copy()
                if len(subset) != 3:
                    raise P2CR1Error("combined metric partition coverage drift")
                subset["_partition_order"] = subset["partition_id"].map(
                    {
                        "DISCOVERY_CORE": 1,
                        "VALIDATION_2022": 2,
                        "STRESS_2023": 3,
                    }
                )
                subset = subset.sort_values(
                    "_partition_order",
                    kind="stable",
                )
                compounded = float(
                    np.prod(
                        1.0
                        + pd.to_numeric(
                            subset["net_return"],
                            errors="raise",
                        )
                    )
                    - 1.0
                )
                curves: list[pd.DataFrame] = []
                trades: list[pd.DataFrame] = []
                positive_years = 0
                year_map: dict[str, float] = {}
                for raw in subset.to_dict(orient="records"):
                    directory = run_dirs[
                        (
                            variant_id,
                            universe_id,
                            str(raw["partition_id"]),
                            cost_multiplier,
                        )
                    ]
                    curve = pd.read_parquet(directory / "equity-curve.parquet")
                    curves.append(curve)
                    trade = pd.read_parquet(directory / "trades.parquet")
                    trades.append(trade)
                    years = raw.get("year_returns")
                    if not isinstance(years, dict):
                        raise P2CR1Error("run year_returns missing")
                    for year, value in years.items():
                        year_map[str(year)] = float(value)
                        if float(value) > 0.0:
                            positive_years += 1
                chained = chain_equity_curves(curves)
                all_trades = pd.concat(
                    trades,
                    ignore_index=True,
                )
                pnl = (
                    pd.to_numeric(
                        all_trades["net_pnl"],
                        errors="raise",
                    )
                    if not all_trades.empty
                    else pd.Series(dtype=float)
                )
                pf = profit_factor(pnl) if not pnl.empty else None
                monthly = (
                    (1.0 + compounded) ** (1.0 / 60.0) - 1.0 if 1.0 + compounded > 0.0 else -1.0
                )
                combined_rows.append(
                    {
                        "variant_id": variant_id,
                        "universe_id": universe_id,
                        "cost_multiplier": cost_multiplier,
                        "net_return": compounded,
                        "monthly_geometric_return": monthly,
                        "profit_factor": pf,
                        "maximum_drawdown": maximum_drawdown(chained["chained_equity"]),
                        "trade_count": int(
                            pd.to_numeric(
                                subset["trade_count"],
                                errors="raise",
                            ).sum()
                        ),
                        "positive_year_count": positive_years,
                        "year_returns_json": json.dumps(
                            year_map,
                            sort_keys=True,
                        ),
                        "minimum_cash": float(
                            pd.to_numeric(
                                subset["minimum_cash"],
                                errors="raise",
                            ).min()
                        ),
                        "turnover_on_initial_equity": float(
                            pd.to_numeric(
                                subset["turnover_on_initial_equity"],
                                errors="raise",
                            ).sum()
                        ),
                        "total_fees": float(
                            pd.to_numeric(
                                subset["total_fees"],
                                errors="raise",
                            ).sum()
                        ),
                    }
                )
    combined = pd.DataFrame.from_records(combined_rows)

    gate_rows: list[dict[str, object]] = []
    for variant_id in sorted(combined["variant_id"].unique()):
        variant = combined.loc[combined["variant_id"] == variant_id].copy()
        failures: list[str] = []
        for universe_id in ("C2", "D2", "E2"):
            two = variant.loc[
                (variant["universe_id"] == universe_id)
                & (pd.to_numeric(variant["cost_multiplier"]) == 2.0)
            ].iloc[0]
            pf_raw = two["profit_factor"]
            pf = float(pf_raw) if pd.notna(pf_raw) else 0.0
            tests = {
                f"{universe_id}_2X_NET_RETURN_GT_0": (float(two["net_return"]) > 0.0),
                f"{universe_id}_2X_PF_GTE_1_05": pf >= 1.05,
                f"{universe_id}_2X_DD_LTE_0_30": (float(two["maximum_drawdown"]) <= 0.30),
                f"{universe_id}_2X_MONTHLY_GTE_0_02": (
                    float(two["monthly_geometric_return"]) >= 0.02
                ),
                f"{universe_id}_2X_TRADES_GTE_75": (int(two["trade_count"]) >= 75),
                f"{universe_id}_2X_POSITIVE_YEARS_GTE_3": (int(two["positive_year_count"]) >= 3),
            }
            failures.extend(key for key, passed in tests.items() if not passed)
            for cost_multiplier in (1.0, 2.0):
                row = variant.loc[
                    (variant["universe_id"] == universe_id)
                    & (pd.to_numeric(variant["cost_multiplier"]) == cost_multiplier)
                ].iloc[0]
                if float(row["minimum_cash"]) < -1e-7:
                    failures.append(f"{universe_id}_{cost_multiplier:.0f}X_NEGATIVE_CASH")
                if float(row["turnover_on_initial_equity"]) > 240.0:
                    failures.append(f"{universe_id}_{cost_multiplier:.0f}X_TURNOVER_GT_240")

        two_x = variant.loc[pd.to_numeric(variant["cost_multiplier"]) == 2.0]
        all_two_x_trades: list[pd.DataFrame] = []
        for partition_id in PARTITIONS:
            for universe_id in ("C2", "D2", "E2"):
                all_two_x_trades.append(
                    pd.read_parquet(
                        run_dirs[
                            (
                                variant_id,
                                universe_id,
                                partition_id,
                                2.0,
                            )
                        ]
                        / "trades.parquet"
                    )
                )
        top_share = top_trade_share(
            pd.concat(
                all_two_x_trades,
                ignore_index=True,
            )
        )
        gate_rows.append(
            {
                "variant_id": variant_id,
                "passed_all_hard_gates": len(failures) == 0,
                "failure_count": len(failures),
                "failures_json": json.dumps(sorted(failures)),
                "worst_universe_2x_monthly_geometric_return": float(
                    two_x["monthly_geometric_return"].min()
                ),
                "worst_universe_2x_profit_factor": float(two_x["profit_factor"].fillna(0.0).min()),
                "worst_universe_2x_maximum_drawdown": float(two_x["maximum_drawdown"].max()),
                "maximum_turnover_across_combined_runs": float(
                    variant["turnover_on_initial_equity"].max()
                ),
                "top_5_trade_share_of_positive_pnl": top_share,
            }
        )
    gates = pd.DataFrame.from_records(gate_rows)
    return run_metrics, combined, gates


def rank_finalists(gates: pd.DataFrame) -> pd.DataFrame:
    passed = gates.loc[gates["passed_all_hard_gates"].astype(bool)].copy()
    if passed.empty:
        passed["finalist_rank"] = pd.Series(dtype=int)
        passed["selected_for_2024"] = pd.Series(dtype=bool)
        return passed
    passed = passed.sort_values(
        [
            "worst_universe_2x_monthly_geometric_return",
            "worst_universe_2x_profit_factor",
            "worst_universe_2x_maximum_drawdown",
            "maximum_turnover_across_combined_runs",
            "top_5_trade_share_of_positive_pnl",
            "variant_id",
        ],
        ascending=[False, False, True, True, True, True],
        kind="stable",
    ).reset_index(drop=True)
    passed["finalist_rank"] = range(1, len(passed) + 1)
    passed["selected_for_2024"] = passed["finalist_rank"] <= 2
    return passed


def build_local_evidence_manifest(
    evidence_output: Path,
    execution: pd.DataFrame,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for raw in execution.to_dict(orient="records"):
        execution_order = int(raw["execution_order"])
        run_id = (
            f"{execution_order:03d}_"
            f"{raw['variant_id']}_{raw['partition_id']}_"
            f"{raw['universe_id']}_{float(raw['cost_multiplier']):.0f}x"
        )
        directory = run_dir(
            evidence_output,
            execution_order,
            run_id,
        )
        checkpoint = p2c.verify_checkpoint(directory)
        files = checkpoint.get("files")
        if not isinstance(files, list):
            raise P2CR1Error(f"checkpoint file list invalid: {run_id}")
        for item in files:
            if not isinstance(item, dict):
                raise P2CR1Error(f"checkpoint row invalid: {run_id}")
            relative = directory.relative_to(evidence_output) / str(item["path"])
            path = evidence_output / relative
            rows.append(
                {
                    "run_id": run_id,
                    "execution_order": execution_order,
                    "path": relative.as_posix(),
                    "bytes": path.stat().st_size,
                    "sha256": str(item["sha256"]),
                    "evidence_role": "RUN_ARTIFACT",
                }
            )
        checkpoint_path = directory / "checkpoint.json"
        rows.append(
            {
                "run_id": run_id,
                "execution_order": execution_order,
                "path": checkpoint_path.relative_to(evidence_output).as_posix(),
                "bytes": checkpoint_path.stat().st_size,
                "sha256": sha256(checkpoint_path),
                "evidence_role": "RUN_CHECKPOINT",
            }
        )
    frame = pd.DataFrame.from_records(rows)
    expected_rows = EXPECTED_RUNS * 7
    if len(frame) != expected_rows:
        raise P2CR1Error(
            f"local evidence manifest row count drifted: {len(frame)} != {expected_rows}"
        )
    return frame


def write_summary_manifest(
    summary_output: Path,
) -> dict[str, object]:
    files: list[dict[str, object]] = []
    for path in sorted(summary_output.iterdir()):
        if not path.is_file() or path.name == "output-manifest.json":
            continue
        files.append(
            {
                "path": path.name,
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
        )
    deterministic = hashlib.sha256(
        json.dumps(
            files,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    manifest = {
        "schema_version": "rd19-p2c-r1-summary-manifest-v1",
        "stage": STAGE,
        "files": files,
        "file_count": len(files),
        "deterministic_hash": deterministic,
        "raw_evidence_committed_to_git": False,
        "raw_evidence_local_and_hashed": True,
        "historical_discovery_execution_executed": True,
        "completed_run_count": EXPECTED_RUNS,
        "2024_market_data_accessed": False,
        "post_2024_accessed": False,
        "network_requests": 0,
        "production_authorized": False,
    }
    p2c.write_json(
        summary_output / "output-manifest.json",
        manifest,
    )
    return manifest


def main() -> int:
    args = parser().parse_args()
    repo = args.repo_root.resolve()
    summary_output = args.summary_output_dir.resolve()
    evidence_output = args.evidence_output_dir.resolve()

    protocol, execution, membership_frame, audit = verify_frozen_inputs(repo)
    variants_list = resolve_variants(protocol)
    variants = {str(row["variant_id"]): row for row in variants_list}
    signatures = {feature_signature(row) for row in variants_list}
    if len(signatures) != 2:
        raise P2CR1Error(f"expected exactly 2 feature signatures, found {len(signatures)}")

    required_pairs = sorted(
        set(
            membership_frame.loc[
                pd.to_datetime(
                    membership_frame["decision_time"],
                    utc=True,
                    errors="raise",
                )
                < DATA_CUTOFF,
                "effective_pair",
            ].astype(str)
        )
        | {"BTC-USDT"}
    )

    if args.preflight_only:
        print(
            json.dumps(
                {
                    "status": "PASS",
                    "decision": "RD19_P2C_R1_PREFLIGHT_COMPLETE",
                    "original_result_disposition": audit["original_result_disposition"],
                    "confirmed_defect_count": len(audit["confirmed_defects"]),
                    "frozen_variant_count": len(variants),
                    "frozen_run_count": len(execution),
                    "feature_signature_count": len(signatures),
                    "required_pair_count": len(required_pairs),
                    "parameter_changes": 0,
                    "matrix_changes": 0,
                    "2024_market_data_accessed": False,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    if not args.execute:
        raise P2CR1Error("use --execute after successful correction preflight")

    if evidence_output.exists() and not args.resume:
        raise P2CR1Error("local evidence output exists; use --resume")
    evidence_output.mkdir(
        parents=True,
        exist_ok=True,
    )

    timing: dict[str, object] = {
        "schema_version": "rd19-p2c-r1-timing-v1",
        "started_monotonic": time.perf_counter(),
        "feature_store_target_count": 2,
        "daily_rank_cache_target_count": 6,
        "candidate_plan_target_count": 36,
        "historical_run_count": EXPECTED_RUNS,
        "hot_loop_pandas_snapshot_builds": 0,
        "raw_evidence_committed_to_git": False,
    }

    t0 = time.perf_counter()
    raw_frames = load_raw_frames(
        args.raw_root.resolve(),
        required_pairs,
    )
    timing["raw_load_seconds"] = time.perf_counter() - t0

    membership = p2c.MembershipIndex(membership_frame)

    store_cache: dict[tuple[object, ...], Any] = {}
    rank_cache: dict[
        tuple[tuple[object, ...], str],
        dict[int, tuple[dict[str, object], ...]],
    ] = {}
    plan_cache: dict[
        tuple[str, str],
        dict[float, dict[int, tuple[dict[str, object], ...]]],
    ] = {}
    funnel_rows: list[dict[str, object]] = []

    feature_build_seconds = 0.0
    rank_build_seconds = 0.0
    plan_build_seconds = 0.0
    feature_cache_hits = 0

    def ensure_plan(
        variant_id: str,
        universe_id: str,
    ) -> dict[
        float,
        dict[int, tuple[dict[str, object], ...]],
    ]:
        nonlocal feature_build_seconds
        nonlocal rank_build_seconds
        nonlocal plan_build_seconds
        nonlocal feature_cache_hits

        plan_key = (variant_id, universe_id)
        if plan_key in plan_cache:
            return plan_cache[plan_key]

        config = variants[variant_id]
        signature = feature_signature(config)
        store = store_cache.get(signature)
        if store is None:
            start_build = time.perf_counter()
            store = build_feature_store(
                raw_frames,
                config,
            )
            feature_build_seconds += time.perf_counter() - start_build
            store_cache[signature] = store
            print(
                f"RD19_P2C_R1_FEATURE_STORE=built:{len(store_cache)}/2:variant={variant_id}",
                flush=True,
            )
        else:
            feature_cache_hits += 1

        rank_key = (signature, universe_id)
        daily = rank_cache.get(rank_key)
        if daily is None:
            start_rank = time.perf_counter()
            daily = build_daily_rank_cache(
                store,
                membership,
                universe_id,
                config,
                PLAN_START,
                PLAN_END,
            )
            rank_build_seconds += time.perf_counter() - start_rank
            rank_cache[rank_key] = daily

        start_plan = time.perf_counter()
        plans, rows = build_candidate_plans(
            store,
            membership,
            universe_id,
            config,
            daily,
            PLAN_START,
            PLAN_END,
        )
        plan_build_seconds += time.perf_counter() - start_plan
        plan_cache[plan_key] = plans
        funnel_rows.extend(rows)
        print(
            "RD19_P2C_R1_PLAN="
            f"{variant_id}:{universe_id}:"
            f"1x_hours={len(plans[1.0])}:"
            f"2x_hours={len(plans[2.0])}",
            flush=True,
        )
        return plans

    # Freeze every corrected candidate plan before portfolio execution. This
    # prevents portfolio outcomes from altering later signal generation.
    for variant_id in sorted(variants):
        for universe_id in ("C2", "D2", "E2"):
            ensure_plan(variant_id, universe_id)

    timing["feature_build_seconds"] = feature_build_seconds
    timing["daily_rank_build_seconds"] = rank_build_seconds
    timing["candidate_plan_build_seconds"] = plan_build_seconds
    timing["feature_store_build_count"] = len(store_cache)
    timing["feature_store_cache_hits"] = feature_cache_hits
    timing["daily_rank_cache_count"] = len(rank_cache)
    timing["candidate_plan_count"] = len(plan_cache)

    t_exec = time.perf_counter()
    completed = 0
    skipped = 0
    for raw in execution.to_dict(orient="records"):
        execution_order = int(raw["execution_order"])
        variant_id = str(raw["variant_id"])
        universe_id = str(raw["universe_id"])
        partition_id = str(raw["partition_id"])
        cost_multiplier = float(raw["cost_multiplier"])
        run_id = (
            f"{execution_order:03d}_"
            f"{variant_id}_{partition_id}_"
            f"{universe_id}_{cost_multiplier:.0f}x"
        )
        directory = run_dir(
            evidence_output,
            execution_order,
            run_id,
        )

        if (directory / "checkpoint.json").is_file():
            p2c.verify_checkpoint(directory)
            completed += 1
            skipped += 1
            print(
                f"RD19_P2C_R1_RESUME_SKIP={completed}/{EXPECTED_RUNS}:{run_id}",
                flush=True,
            )
            continue
        if directory.exists():
            raise P2CR1Error(f"partial non-atomic run directory exists: {directory}")

        config = variants[variant_id]
        signature = feature_signature(config)
        store = store_cache[signature]
        plans = plan_cache[(variant_id, universe_id)]
        start, end = PARTITIONS[partition_id]
        result = execute_run_fast(
            run_row=raw,
            config=config,
            store=store,
            membership=membership,
            candidate_plan=plans[cost_multiplier],
            partition_start=start,
            partition_end=end,
        )
        write_run_result_atomic(
            directory,
            result,
        )
        completed += 1
        metrics = cast(
            dict[str, object],
            result["metrics"],
        )
        print(
            "RD19_P2C_R1_RUN="
            f"{completed}/{EXPECTED_RUNS}:{run_id}:"
            f"return={float(metrics['net_return']):.8f}:"
            f"trades={int(metrics['trade_count'])}:"
            f"dd={float(metrics['maximum_drawdown']):.8f}:"
            f"turnover={float(metrics['turnover_on_initial_equity']):.4f}",
            flush=True,
        )

    if completed != EXPECTED_RUNS:
        raise P2CR1Error(f"corrected completed run count drifted: {completed}")
    timing["execution_seconds"] = time.perf_counter() - t_exec
    timing["resume_skipped_run_count"] = skipped

    t_aggregate = time.perf_counter()
    run_metrics, combined, gates = aggregate_results(
        evidence_output,
        execution,
    )
    finalists = rank_finalists(gates)
    timing["aggregation_seconds"] = time.perf_counter() - t_aggregate

    funnel = pd.DataFrame.from_records(funnel_rows)
    if len(funnel) != EXPECTED_RUNS:
        raise P2CR1Error(f"signal funnel row count drifted: {len(funnel)}")

    selected = (
        finalists.loc[
            finalists["selected_for_2024"].astype(bool),
            "variant_id",
        ]
        .astype(str)
        .tolist()
        if not finalists.empty
        else []
    )
    if len(selected) > 2:
        raise P2CR1Error("corrected replay selected more than two finalists")

    next_stage = (
        "RD19_P2D_INTERNAL_CONFIRMATION_AUTHORIZATION"
        if selected
        else "RD19_P2C_R1_NO_FINALISTS_DISCOVERY_REJECTION_REVIEW"
    )

    if summary_output.exists():
        shutil.rmtree(summary_output)
    summary_output.mkdir(
        parents=True,
        exist_ok=False,
    )

    run_metrics.to_csv(
        summary_output / "run-metrics.csv",
        index=False,
        lineterminator="\n",
    )
    combined.to_csv(
        summary_output / "combined-2019-2023-metrics.csv",
        index=False,
        lineterminator="\n",
    )
    gates.to_csv(
        summary_output / "variant-gate-evaluation.csv",
        index=False,
        lineterminator="\n",
    )
    finalists.to_csv(
        summary_output / "finalist-ranking.csv",
        index=False,
        lineterminator="\n",
    )
    funnel.to_csv(
        summary_output / "signal-funnel.csv",
        index=False,
        lineterminator="\n",
    )

    evidence_manifest = build_local_evidence_manifest(
        evidence_output,
        execution,
    )
    evidence_manifest.to_csv(
        summary_output / "local-evidence-manifest.csv",
        index=False,
        lineterminator="\n",
    )

    timing["local_evidence_file_count"] = len(evidence_manifest)
    timing["local_evidence_bytes"] = int(
        pd.to_numeric(
            evidence_manifest["bytes"],
            errors="raise",
        ).sum()
    )
    timing["total_seconds_before_validation"] = time.perf_counter() - float(
        timing["started_monotonic"]
    )
    timing.pop("started_monotonic", None)
    p2c.write_json(
        summary_output / "timing-report.json",
        timing,
    )
    p2c.write_json(
        summary_output / "correction-audit.json",
        audit,
    )

    report = {
        "schema_version": "rd19-p2c-r1-correction-report-v1",
        "stage": STAGE,
        "decision": DECISION,
        "passed": True,
        "parent_commit": EXPECTED_PARENT,
        "selected_candidate_id": CANDIDATE_ID,
        "original_p2c_result_disposition": ("INVALIDATED_FOR_IMPLEMENTATION_NONCONFORMANCE"),
        "repair_ids": list(REPAIR_IDS),
        "frozen_p2_protocol_sha256": EXPECTED_P2_PROTOCOL_SHA256,
        "frozen_execution_order_sha256": (EXPECTED_EXECUTION_ORDER_SHA256),
        "parameter_changes": 0,
        "matrix_changes": 0,
        "hard_gate_changes": 0,
        "authorized_run_count": EXPECTED_RUNS,
        "completed_run_count": EXPECTED_RUNS,
        "variant_count": 12,
        "feature_signature_count": len(store_cache),
        "daily_rank_cache_count": len(rank_cache),
        "candidate_plan_count": len(plan_cache),
        "combined_metric_rows": len(combined),
        "signal_funnel_rows": len(funnel),
        "hard_gate_pass_variant_count": int(gates["passed_all_hard_gates"].astype(bool).sum()),
        "ranked_finalist_count": len(finalists),
        "selected_for_2024_count": len(selected),
        "selected_for_2024_variants": selected,
        "raw_evidence_committed_to_git": False,
        "raw_evidence_local_and_hashed": True,
        "local_evidence_relative_path": (
            evidence_output.relative_to(repo).as_posix()
            if evidence_output.is_relative_to(repo)
            else str(evidence_output)
        ),
        "2024_internal_confirmation_executed": False,
        "2024_market_data_accessed": False,
        "post_2024_accessed": False,
        "network_requests": 0,
        "production_authorized": False,
        "next_stage": next_stage,
    }
    p2c.write_json(
        summary_output / "rd19-p2c-r1-correction-report-v1.json",
        report,
    )
    write_summary_manifest(summary_output)

    print(
        json.dumps(
            {
                "status": "PASS",
                "decision": DECISION,
                "completed_run_count": EXPECTED_RUNS,
                "hard_gate_pass_variant_count": report["hard_gate_pass_variant_count"],
                "selected_for_2024_variants": selected,
                "feature_store_build_count": timing["feature_store_build_count"],
                "candidate_plan_count": timing["candidate_plan_count"],
                "execution_seconds": timing["execution_seconds"],
                "total_seconds_before_validation": timing["total_seconds_before_validation"],
                "next_stage": next_stage,
                "summary_output_dir": str(summary_output),
                "evidence_output_dir": str(evidence_output),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
