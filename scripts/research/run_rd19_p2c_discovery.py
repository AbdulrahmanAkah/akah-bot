"""Execute the authorized frozen RD19-P2C 216-run historical matrix."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, cast

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from spotbot.research import rd19_p2a_engine as p2a  # noqa: E402
from spotbot.research.rd19_p2a_engine import resolve_variants  # noqa: E402
from spotbot.research.rd19_p2c_discovery import (  # noqa: E402
    CANDIDATE_ID,
    DATA_CUTOFF,
    DECISION,
    EXPECTED_RUNS,
    STAGE,
    MembershipIndex,
    P2CExecutionError,
    chain_equity_curves,
    execute_run,
    load_json_object,
    maximum_drawdown,
    prepare_feature_frame,
    profit_factor,
    sha256,
    top_trade_share,
    verify_checkpoint,
    write_json,
    write_run_result,
)

EXPECTED_PARENT = "7d102fbad54c54deeaf26de62604b3f6dc7d18b4"
P2_PROTOCOL = "data/research/rd19_p2_runtime/rd19-p2-discovery-protocol-v1.json"
EXECUTION_ORDER = "data/research/rd19_p2_runtime/execution-order.csv"
MEMBERSHIP = "data/research/rd18_p3x_a3b_runtime/effective-operational-membership.csv"
P2B_RUNTIME = "data/research/rd19_p2b_runtime"

EXPECTED_P2B_HASHES = {
    "authorization-decision.json": (
        "850be39afcda00c1866f6e500b94594c5570d758efcb7a6a9f34fbf78b3f0bf2"
    ),
    "execution-contract.json": ("f04d46f7d98179a9ff5079bbf1689f0c8c1d4ea9dc4fd48ad0b208f3dbfcbba2"),
    "authorization-checks.csv": (
        "99c984303b501144a6de80e767488c9d1431f5fda89e7ef42e386317598fa920"
    ),
    "lineage-hash-manifest.csv": (
        "acbd997b9a62d5786f5411a810c7c01650cac4e20694305b16a5cf857a450ab7"
    ),
    "output-manifest.json": ("07dc0cf23c820f301e2ff8fe82816d0a4cb6ebe81a3a9e83bca7c62af6bf1f73"),
}
PARTITIONS = {
    "DISCOVERY_CORE": (
        pd.Timestamp("2019-01-01T00:00:00Z"),
        pd.Timestamp("2021-12-31T23:00:00Z"),
    ),
    "VALIDATION_2022": (
        pd.Timestamp("2022-01-01T00:00:00Z"),
        pd.Timestamp("2022-12-31T23:00:00Z"),
    ),
    "STRESS_2023": (
        pd.Timestamp("2023-01-01T00:00:00Z"),
        pd.Timestamp("2023-12-31T23:00:00Z"),
    ),
}


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    result.add_argument("--repo-root", type=Path, default=ROOT)
    result.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "data/research/rd19_p2c_runtime",
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


def verify_authorization(repo: Path) -> dict[str, Any]:
    for name, expected in EXPECTED_P2B_HASHES.items():
        path = repo / P2B_RUNTIME / name
        if not path.is_file() or sha256(path) != expected:
            raise P2CExecutionError(f"P2B authorization hash drift: {name}")
    decision = load_json_object(repo / P2B_RUNTIME / "authorization-decision.json")
    contract = load_json_object(repo / P2B_RUNTIME / "execution-contract.json")
    expected = {
        "passed": True,
        "decision": "RD19_P2B_DISCOVERY_EXECUTION_AUTHORIZED",
        "authorized": True,
        "technical_valid": True,
        "blockers": [],
        "expected_run_count": 216,
        "historical_discovery_execution_authorized": True,
        "historical_discovery_execution_executed": False,
        "2024_access_authorized": False,
        "post_2024_access_authorized": False,
        "production_authorized": False,
        "next_stage": "RD19_P2C_EXECUTE_FROZEN_DISCOVERY_MATRIX_2019_2023",
    }
    drift = {
        key: {"expected": wanted, "actual": decision.get(key)}
        for key, wanted in expected.items()
        if decision.get(key) != wanted
    }
    if drift:
        raise P2CExecutionError(f"P2B authorization semantic drift: {drift}")
    if contract.get("status") != "AUTHORIZED_NOT_EXECUTED":
        raise P2CExecutionError("P2B execution contract status drifted")
    scope = cast(dict[str, Any], contract["authorized_scope"])
    if scope.get("expected_run_count") != EXPECTED_RUNS:
        raise P2CExecutionError("P2B authorized run count drifted")
    return contract


def verify_lineage(repo: Path, contract: dict[str, Any]) -> None:
    lineage = pd.read_csv(repo / P2B_RUNTIME / "lineage-hash-manifest.csv")
    for raw in lineage.to_dict(orient="records"):
        raw_path = Path(str(raw["path"]))
        path = raw_path if raw_path.is_absolute() else repo / raw_path
        if not path.is_file():
            raise P2CExecutionError(f"lineage file missing: {path}")
        if sha256(path) != str(raw["sha256"]):
            raise P2CExecutionError(f"lineage hash drift: {path}")
    frozen = cast(dict[str, Any], contract["frozen_hashes"])
    if sha256(repo / EXECUTION_ORDER) != str(frozen["execution_order_sha256"]):
        raise P2CExecutionError("execution-order frozen hash drifted")
    if sha256(repo / MEMBERSHIP) != str(frozen["membership_sha256"]):
        raise P2CExecutionError("membership frozen hash drifted")
    if sha256(repo / "src/spotbot/research/rd19_p2a_engine.py") != str(frozen["p2a_engine_sha256"]):
        raise P2CExecutionError("P2A engine frozen hash drifted")


def verify_execution_order(frame: pd.DataFrame) -> None:
    if len(frame) != EXPECTED_RUNS:
        raise P2CExecutionError(f"execution-order rows drifted: {len(frame)}")
    expected = list(range(1, EXPECTED_RUNS + 1))
    observed = (
        pd.to_numeric(
            frame["execution_order"],
            errors="raise",
        )
        .astype(int)
        .tolist()
    )
    if observed != expected:
        raise P2CExecutionError("execution order is not exactly 1..216")
    if bool(
        frame[
            [
                "variant_id",
                "partition_id",
                "universe_id",
                "cost_multiplier",
            ]
        ]
        .duplicated()
        .any()
    ):
        raise P2CExecutionError("execution order contains duplicate run identities")


def load_raw_frames(
    raw_root: Path,
    pairs: list[str],
) -> dict[str, pd.DataFrame]:
    frames: dict[str, pd.DataFrame] = {}
    cutoff = DATA_CUTOFF.to_pydatetime()
    for index, pair in enumerate(pairs, start=1):
        path = raw_root / pair / "1h.parquet"
        if not path.is_file():
            raise P2CExecutionError(f"sealed hourly source missing: {path}")
        frame = pd.read_parquet(
            path,
            engine="pyarrow",
            filters=[("timestamp", "<", cutoff)],
        )
        normalized = p2a.normalize_bars(frame)
        if bool(
            (
                pd.to_datetime(
                    normalized["timestamp"],
                    utc=True,
                    errors="raise",
                )
                >= DATA_CUTOFF
            ).any()
        ):
            raise P2CExecutionError(f"2024 market row entered memory: {pair}")
        frames[pair] = normalized
        print(
            f"RD19_P2C_SOURCE={index}/{len(pairs)}:{pair}:{len(normalized)}",
            flush=True,
        )
    return frames


def run_metrics_path(
    output: Path,
    execution_order: int,
    run_id: str,
) -> Path:
    return output / "runs" / f"{execution_order:03d}" / run_id / "run-metrics.json"


def run_dir(
    output: Path,
    execution_order: int,
    run_id: str,
) -> Path:
    return output / "runs" / f"{execution_order:03d}" / run_id


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
        raise P2CExecutionError("run metrics do not cover all 216 executions")

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
                    raise P2CExecutionError("combined metric partition coverage drift")
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
                        raise P2CExecutionError("run year_returns missing")
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


def recursive_manifest(output: Path) -> dict[str, object]:
    files: list[dict[str, object]] = []
    for path in sorted(output.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(output).as_posix()
        if relative == "output-manifest.json":
            continue
        files.append(
            {
                "path": relative,
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
        )
    return {
        "schema_version": "rd19-p2c-output-manifest-v1",
        "stage": STAGE,
        "files": files,
        "file_count": len(files),
        "historical_discovery_execution_authorized": True,
        "historical_discovery_execution_executed": True,
        "completed_run_count": EXPECTED_RUNS,
        "candidate_backtest_executed": True,
        "portfolio_routing_executed": True,
        "exit_simulation_executed": True,
        "performance_reporting_executed": True,
        "2024_market_data_accessed": False,
        "post_2024_accessed": False,
        "network_requests": 0,
        "production_authorized": False,
    }


def main() -> int:
    args = parser().parse_args()
    repo = args.repo_root.resolve()
    output = args.output_dir.resolve()

    contract = verify_authorization(repo)
    verify_lineage(repo, contract)

    p2_protocol = load_json_object(repo / P2_PROTOCOL)
    variants = {str(row["variant_id"]): row for row in resolve_variants(p2_protocol)}
    execution = pd.read_csv(repo / EXECUTION_ORDER)
    verify_execution_order(execution)

    membership_frame = pd.read_csv(repo / MEMBERSHIP)
    membership = MembershipIndex(membership_frame)

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
                    "decision": "RD19_P2C_PREFLIGHT_COMPLETE",
                    "authorized_run_count": len(execution),
                    "variant_count": len(variants),
                    "required_pair_count": len(required_pairs),
                    "2024_market_data_accessed": False,
                    "post_2024_accessed": False,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    if not args.execute:
        raise P2CExecutionError("use --execute after successful preflight")

    if output.exists() and not args.resume:
        raise P2CExecutionError("P2C output already exists; use --resume")
    output.mkdir(parents=True, exist_ok=True)

    raw_frames = load_raw_frames(
        args.raw_root.resolve(),
        required_pairs,
    )

    current_variant = ""
    features: dict[str, pd.DataFrame] = {}
    completed = 0

    for raw in execution.to_dict(orient="records"):
        variant_id = str(raw["variant_id"])
        execution_order = int(raw["execution_order"])
        partition_id = str(raw["partition_id"])
        universe_id = str(raw["universe_id"])
        cost_multiplier = float(raw["cost_multiplier"])
        run_id = (
            f"{execution_order:03d}_{variant_id}_{partition_id}_"
            f"{universe_id}_{cost_multiplier:.0f}x"
        )
        directory = run_dir(output, execution_order, run_id)

        if (directory / "checkpoint.json").is_file():
            verify_checkpoint(directory)
            completed += 1
            print(
                f"RD19_P2C_RESUME_SKIP={execution_order}/{EXPECTED_RUNS}:{run_id}",
                flush=True,
            )
            continue
        if directory.exists():
            raise P2CExecutionError(f"partial run without valid checkpoint: {directory}")

        if variant_id != current_variant:
            config = variants[variant_id]
            features = {}
            for index, (pair, frame) in enumerate(
                sorted(raw_frames.items()),
                start=1,
            ):
                features[pair] = prepare_feature_frame(
                    frame,
                    config,
                )
                if index % 10 == 0 or index == len(raw_frames):
                    print(
                        f"RD19_P2C_FEATURE_BUILD={variant_id}:{index}/{len(raw_frames)}",
                        flush=True,
                    )
            current_variant = variant_id

        config = variants[variant_id]
        start, end = PARTITIONS[partition_id]
        result = execute_run(
            run_row=raw,
            config=config,
            features=features,
            membership=membership,
            partition_start=start,
            partition_end=end,
        )
        write_run_result(directory, result)
        completed += 1
        metrics = cast(dict[str, object], result["metrics"])
        print(
            "RD19_P2C_RUN="
            f"{completed}/{EXPECTED_RUNS}:{run_id}:"
            f"return={float(metrics['net_return']):.8f}:"
            f"trades={int(metrics['trade_count'])}:"
            f"dd={float(metrics['maximum_drawdown']):.8f}:"
            f"turnover={float(metrics['turnover_on_initial_equity']):.4f}",
            flush=True,
        )

    if completed != EXPECTED_RUNS:
        raise P2CExecutionError(f"completed run count drifted: {completed}")

    run_metrics, combined, gates = aggregate_results(
        output,
        execution,
    )
    finalists = rank_finalists(gates)

    run_metrics.to_csv(
        output / "run-metrics.csv",
        index=False,
        lineterminator="\n",
    )
    combined.to_csv(
        output / "combined-2019-2023-metrics.csv",
        index=False,
        lineterminator="\n",
    )
    gates.to_csv(
        output / "variant-gate-evaluation.csv",
        index=False,
        lineterminator="\n",
    )
    finalists.to_csv(
        output / "finalist-ranking.csv",
        index=False,
        lineterminator="\n",
    )

    finalist_count = len(finalists)
    selected = (
        finalists.loc[
            finalists["selected_for_2024"].astype(bool),
            "variant_id",
        ]
        .astype(str)
        .tolist()
        if finalist_count
        else []
    )
    next_stage = (
        "RD19_P2D_INTERNAL_CONFIRMATION_AUTHORIZATION"
        if selected
        else "RD19_P2C_NO_FINALISTS_DISCOVERY_REJECTION_REVIEW"
    )
    report = {
        "schema_version": "rd19-p2c-discovery-report-v1",
        "stage": STAGE,
        "decision": DECISION,
        "passed": True,
        "parent_commit": EXPECTED_PARENT,
        "selected_candidate_id": CANDIDATE_ID,
        "authorized_run_count": EXPECTED_RUNS,
        "completed_run_count": EXPECTED_RUNS,
        "variant_count": 12,
        "combined_metric_rows": len(combined),
        "hard_gate_pass_variant_count": int(gates["passed_all_hard_gates"].astype(bool).sum()),
        "ranked_finalist_count": finalist_count,
        "selected_for_2024_count": len(selected),
        "selected_for_2024_variants": selected,
        "2024_internal_confirmation_executed": False,
        "2024_market_data_accessed": False,
        "post_2024_accessed": False,
        "network_requests": 0,
        "production_authorized": False,
        "next_stage": next_stage,
    }
    write_json(
        output / "rd19-p2c-discovery-report-v1.json",
        report,
    )
    manifest = recursive_manifest(output)
    write_json(output / "output-manifest.json", manifest)

    print(
        json.dumps(
            {
                "status": "PASS",
                "decision": DECISION,
                "completed_run_count": EXPECTED_RUNS,
                "hard_gate_pass_variant_count": report["hard_gate_pass_variant_count"],
                "selected_for_2024_variants": selected,
                "next_stage": next_stage,
                "output_dir": str(output),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
