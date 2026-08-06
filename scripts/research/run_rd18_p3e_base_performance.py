from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, cast

import pandas as pd
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from spotbot.data.store import ParquetCandleStore  # noqa: E402
from spotbot.research.rd18_p3e_performance import (  # noqa: E402
    COST_MULTIPLIERS,
    UNIVERSE_IDS,
    PerformanceRun,
    base_classification,
    build_performance_run,
    evaluate_cross_universe,
    evaluate_universe_gates,
)
from spotbot.research.rd18_p3e_replay import (  # noqa: E402
    SEALED_CUTOFF,
    normalize_hourly_bars,
)

STAGE = "RD18_P3E_BASE_COST_AND_PERFORMANCE_EVALUATION"
DECISION = "RD18_P3E_BASE_COST_AND_PERFORMANCE_EVALUATION_COMPLETE"
NEXT_STAGE = "RD18_P3E_LOYO_AND_LOAO_SENSITIVITY_EXECUTION"

P3R_HASHES = {
    "frozen-strategy-candidate.json": (
        "b3748664aefa334c702c36a8e34ae8b0d339e265b15b0cdb99eeec06bb37a3b6"
    ),
    "performance-gate-registry.json": (
        "033a955c3d13826886692a20690bfb74b6029fedd7778dd7e7d25fea5dd50105"
    ),
    "replay-execution-contract.json": (
        "31ee2bf443332826bbd5a0b8b470bc4dec686d758d91f0d6328dddc7af6d967a"
    ),
}
EXPECTED_DRY_RUN_MANIFEST_SHA256 = (
    "dd24def921bf5bcc013d2cb38dd6e7fdde6b6cde7099560864f9ff4864f5bfca"
)
EXPECTED_DRY_RUN_REPORT_SHA256 = "9a51c375a9a59ea3d50328a38c518afce4645de378088650cb1286a50850b4fb"


class BasePerformanceError(RuntimeError):
    """Raised when base performance inputs or outputs are invalid."""


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    result.add_argument("--repo-root", type=Path, default=ROOT)
    result.add_argument(
        "--dry-run-runtime",
        type=Path,
        default=ROOT / "data/research/rd18_p3e_dry_run_runtime",
    )
    result.add_argument(
        "--a3b-runtime",
        type=Path,
        default=ROOT / "data/research/rd18_p3x_a3b_runtime",
    )
    result.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "data/research/rd18_p3e_base_runtime",
    )
    result.add_argument("--preflight-only", action="store_true")
    result.add_argument("--write-results", action="store_true")
    return result


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise BasePerformanceError(f"JSON missing: {path}")
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise BasePerformanceError(f"JSON object expected: {path}")
    return value


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise BasePerformanceError(f"CSV missing: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def json_ready(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_ready(item) for item in value]
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if hasattr(value, "item"):
        return json_ready(cast(Any, value).item())
    if isinstance(value, float) and not pd.notna(value):
        return None
    return value


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            json_ready(value),
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )


def write_rows(
    path: Path,
    rows: Sequence[Mapping[str, object]],
) -> None:
    if not rows:
        raise BasePerformanceError(f"empty CSV row set: {path}")
    fields = sorted({str(key) for row in rows for key in row})
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fields,
            lineterminator="\n",
            extrasaction="raise",
        )
        writer.writeheader()
        for row in rows:
            writer.writerow({key: json_ready(row.get(key)) for key in fields})


def verify_manifest_files(
    root: Path,
    manifest: Mapping[str, object],
) -> None:
    files = manifest.get("files")
    if not isinstance(files, list):
        raise BasePerformanceError("manifest files are invalid")
    for raw in files:
        if not isinstance(raw, Mapping):
            raise BasePerformanceError("manifest row is invalid")
        relative = str(raw["path"])
        path = root / relative
        if not path.is_file():
            raise BasePerformanceError(f"manifest file missing: {relative}")
        if path.stat().st_size != int(cast(int, raw["bytes"])) or sha256(path) != str(
            raw["sha256"]
        ):
            raise BasePerformanceError(f"manifest mismatch: {relative}")


def verify_p3r(repo: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    root = repo / "data/research/rd18_p3r"
    for name, expected in P3R_HASHES.items():
        path = root / name
        if not path.is_file() or sha256(path) != expected:
            raise BasePerformanceError(f"P3R hash drift: {name}")
    frozen = load_json(root / "frozen-strategy-candidate.json")
    gates = load_json(root / "performance-gate-registry.json")
    contract = load_json(root / "replay-execution-contract.json")
    if not all(
        (
            frozen.get("architecture_id") == "COMPOSITE_ALPHA_V3",
            frozen.get("source_variant_id") == "STRONG_BULL_HOLD_96",
            gates.get("thresholds_may_change_after_results") is False,
            contract.get("execution", {}).get("cost_multipliers") == [1.0, 2.0],
            contract.get("execution", {}).get("cost_multiplier_is_leverage") is False,
            contract.get("strategy", {}).get("parameter_changes_allowed") is False,
            contract.get("strategy", {}).get("per_universe_tuning_allowed") is False,
        )
    ):
        raise BasePerformanceError("P3R semantics drifted")
    return frozen, gates


def verify_dry_run(
    runtime: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    report_path = runtime / "rd18-p3e-technical-dry-run-report-v1.json"
    manifest_path = runtime / "output-manifest.json"
    if sha256(report_path) != EXPECTED_DRY_RUN_REPORT_SHA256:
        raise BasePerformanceError("dry-run report hash drifted")
    if sha256(manifest_path) != EXPECTED_DRY_RUN_MANIFEST_SHA256:
        raise BasePerformanceError("dry-run manifest hash drifted")
    report = load_json(report_path)
    manifest = load_json(manifest_path)
    verify_manifest_files(runtime, manifest)
    if not all(
        (
            report.get("passed") is True,
            report.get("decision") == "RD18_P3E_TECHNICAL_DRY_RUN_COMPLETE",
            report.get("universe_count") == 3,
            report.get("all_universe_checks_passed") is True,
            report.get("strategy_replay_executed") is True,
            report.get("portfolio_routing_executed") is True,
            report.get("exit_simulation_executed") is True,
            report.get("portfolio_return_calculation_executed") is False,
            report.get("post_2024_accessed") is False,
            report.get("network_requests") == 0,
            manifest.get("cost_stress_executed") is False,
            manifest.get("loyo_executed") is False,
            manifest.get("loao_executed") is False,
        )
    ):
        raise BasePerformanceError("dry-run evidence drifted")
    return report, manifest


def _close(
    left: object,
    right: object,
    *,
    tolerance: float = 1e-12,
) -> bool:
    return abs(float(cast(Any, left)) - float(cast(Any, right))) <= tolerance


def verify_legacy_baseline(
    repo: Path,
    frozen: Mapping[str, object],
    a3b_runtime: Path,
) -> dict[str, object]:
    root = repo / "data/research/rd16m"
    hashes = load_json(root / "output-hashes.json")
    immutable = frozen.get("immutable_hashes")
    if not isinstance(immutable, Mapping):
        raise BasePerformanceError("frozen immutable hashes missing")
    required_hashes = {
        "annual-performance.csv": immutable["rd16m_annual_performance"],
        "concentration-analysis.csv": immutable["rd16m_concentration"],
        "cost-stress.csv": immutable["rd16m_cost_stress"],
        "rd16m-final-report-v1.json": immutable["rd16m_final_report"],
        "rd16m-protocol-v1.json": immutable["rd16m_protocol"],
        "validation-report.json": immutable["rd16m_validation"],
    }
    hash_checks: dict[str, bool] = {}
    for name, expected in required_hashes.items():
        path = root / name
        hash_checks[name] = bool(
            path.is_file() and hashes.get(name) == expected and sha256(path) == expected
        )
    summary_rows = read_csv(root / "composite-v3-baseline-summary.csv")
    cost_rows = read_csv(root / "cost-stress.csv")
    if len(summary_rows) != 1:
        raise BasePerformanceError("legacy summary row count drifted")
    one = summary_rows[0]
    two = next(
        (row for row in cost_rows if float(row["cost_multiplier"]) == 2.0),
        None,
    )
    if two is None:
        raise BasePerformanceError("legacy 2x row missing")
    reference_one = frozen.get("baseline_reference_1x")
    reference_two = frozen.get("baseline_reference_2x_transaction_cost")
    if not isinstance(reference_one, Mapping) or not isinstance(
        reference_two,
        Mapping,
    ):
        raise BasePerformanceError("legacy reference metrics missing")
    metric_checks = {
        "one_x_net_return": _close(
            one["net_return"],
            reference_one["net_return"],
        ),
        "one_x_monthly": _close(
            one["monthly_geometric_return"],
            reference_one["monthly_geometric_return"],
        ),
        "one_x_drawdown": _close(
            one["maximum_drawdown"],
            reference_one["maximum_drawdown"],
        ),
        "one_x_profit_factor": _close(
            one["profit_factor"],
            reference_one["profit_factor"],
        ),
        "one_x_minimum_cash": _close(
            one["minimum_cash"],
            reference_one["minimum_cash"],
        ),
        "one_x_trade_count": (
            int(one["trade_count"]) == int(cast(int, reference_one["trade_count"]))
        ),
        "two_x_net_return": _close(
            two["net_return"],
            reference_two["net_return"],
        ),
        "two_x_drawdown": _close(
            two["maximum_drawdown"],
            reference_two["maximum_drawdown"],
        ),
        "two_x_profit_factor": _close(
            two["profit_factor"],
            reference_two["profit_factor"],
        ),
        "two_x_minimum_cash": _close(
            two["minimum_cash"],
            reference_two["minimum_cash"],
        ),
    }
    a3b = load_json(a3b_runtime / "rd18-p3x-a3b-runtime-report-v1.json")
    parity_checks = {
        "a3b_passed": a3b.get("passed") is True,
        "control_parity_executed": (a3b.get("control_parity_executed") is True),
        "control_rows": a3b.get("control_rows")
        == {
            "candidates": 688,
            "evaluated": 688,
            "trades": 567,
        },
    }
    checks = {
        **{f"hash:{key}": value for key, value in hash_checks.items()},
        **{f"metric:{key}": value for key, value in metric_checks.items()},
        **{f"parity:{key}": value for key, value in parity_checks.items()},
    }
    if not all(checks.values()):
        failed = sorted(key for key, value in checks.items() if not value)
        raise BasePerformanceError(f"legacy baseline checks failed: {failed}")
    return {
        "passed": True,
        "checks": dict(sorted(checks.items())),
        "legacy_one_x_net_return": float(one["net_return"]),
        "legacy_two_x_net_return": float(two["net_return"]),
    }


def evidence_strong_pairs(
    a3b_runtime: Path,
) -> frozenset[str]:
    rows = read_csv(a3b_runtime / "effective-operational-membership.csv")
    pairs = {row["effective_pair"] for row in rows if row["universe_id"] == "D2"}
    if not pairs:
        raise BasePerformanceError("D2 evidence-strong set is empty")
    return frozenset(pairs)


def load_hourly(
    repo: Path,
    trade_frames: Mapping[str, pd.DataFrame],
) -> dict[str, pd.DataFrame]:
    symbols = sorted(
        {
            str(symbol)
            for frame in trade_frames.values()
            for symbol in frame["symbol"].astype(str).unique()
        }
    )
    store = ParquetCandleStore(repo / "data/raw/rd16b")
    cutoff = SEALED_CUTOFF.to_pydatetime()
    result: dict[str, pd.DataFrame] = {}
    for index, symbol in enumerate(symbols, start=1):
        data_path = store.dataset_path(
            exchange_id="kucoin",
            symbol=symbol,
            timeframe="1h",
        )
        metadata_path = store.metadata_path(data_path)
        metadata = load_json(metadata_path)
        expected = metadata.get("sha256")
        if not isinstance(expected, str):
            raise BasePerformanceError(f"hourly metadata hash missing: {symbol}")
        if sha256(data_path) != expected:
            raise BasePerformanceError(f"hourly source hash mismatch: {symbol}")
        frame = pd.read_parquet(
            str(data_path),
            engine="pyarrow",
            filters=[("timestamp", "<", cutoff)],
        )
        normalized = normalize_hourly_bars(frame)
        result[symbol] = normalized
        print(
            f"P3E_BASE_BAR_LOAD={index}/{len(symbols)}:{symbol}:{len(normalized)}",
            flush=True,
        )
    return result


def preflight(
    repo: Path,
    dry_run_runtime: Path,
    a3b_runtime: Path,
) -> dict[str, object]:
    frozen, gates = verify_p3r(repo)
    dry_report, dry_manifest = verify_dry_run(dry_run_runtime)
    legacy = verify_legacy_baseline(
        repo,
        frozen,
        a3b_runtime,
    )
    evidence_pairs = evidence_strong_pairs(a3b_runtime)
    trade_rows: dict[str, int] = {}
    trade_symbols: dict[str, int] = {}
    for universe in UNIVERSE_IDS:
        path = dry_run_runtime / "universes" / universe / "v3-trades.parquet"
        parquet = pq.ParquetFile(path)
        trade_rows[universe] = parquet.metadata.num_rows
        trade_symbols[universe] = int(
            pd.read_parquet(
                path,
                columns=["symbol"],
            )["symbol"]
            .astype(str)
            .nunique()
        )
    return {
        "schema_version": "rd18-p3e-base-preflight-v1",
        "stage": STAGE,
        "passed": True,
        "dry_run_decision": dry_report["decision"],
        "dry_run_manifest_sha256": sha256(dry_run_runtime / "output-manifest.json"),
        "dry_run_manifest_deterministic_hash": dry_manifest["deterministic_hash"],
        "legacy_baseline": legacy,
        "evidence_strong_pair_count": len(evidence_pairs),
        "trade_rows": trade_rows,
        "trade_symbol_counts": trade_symbols,
        "cost_multipliers": list(COST_MULTIPLIERS),
        "gate_registry_schema": gates["schema_version"],
        "network_requests": 0,
        "portfolio_return_calculation_executed": False,
        "performance_reporting_executed": False,
        "cost_stress_executed": False,
        "loyo_executed": False,
        "loao_executed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
    }


def _manifest(
    root: Path,
) -> dict[str, object]:
    rows: list[dict[str, object]] = []
    aggregate = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name == "output-manifest.json":
            continue
        relative = path.relative_to(root).as_posix()
        entry: dict[str, object] = {
            "path": relative,
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
        }
        if path.suffix == ".parquet":
            entry["rows"] = pq.ParquetFile(path).metadata.num_rows
        elif path.suffix == ".csv":
            entry["rows"] = len(read_csv(path))
        rows.append(entry)
        aggregate.update(relative.encode("utf-8"))
        aggregate.update(b"\0")
        aggregate.update(str(entry["sha256"]).encode("ascii"))
        aggregate.update(b"\n")
    return {
        "schema_version": "rd18-p3e-base-manifest-v1",
        "files": rows,
        "deterministic_hash": aggregate.hexdigest(),
        "network_requests": 0,
        "strategy_replay_executed": True,
        "strategy_replay_reexecuted_in_this_stage": False,
        "portfolio_routing_executed": True,
        "portfolio_routing_reexecuted_in_this_stage": False,
        "exit_simulation_executed": True,
        "exit_simulation_reexecuted_in_this_stage": False,
        "return_calculation_executed": True,
        "portfolio_return_calculation_executed": True,
        "performance_reporting_executed": True,
        "cost_stress_executed": True,
        "loyo_executed": False,
        "loao_executed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
    }


def materialize(
    repo: Path,
    dry_run_runtime: Path,
    a3b_runtime: Path,
    output: Path,
) -> dict[str, object]:
    frozen, registry = verify_p3r(repo)
    dry_report, dry_manifest = verify_dry_run(dry_run_runtime)
    legacy = verify_legacy_baseline(
        repo,
        frozen,
        a3b_runtime,
    )
    evidence_pairs = evidence_strong_pairs(a3b_runtime)
    base_trades = {
        universe: pd.read_parquet(dry_run_runtime / "universes" / universe / "v3-trades.parquet")
        for universe in UNIVERSE_IDS
    }
    technical = {
        universe: load_json(dry_run_runtime / "universes" / universe / "technical-summary.json")
        for universe in UNIVERSE_IDS
    }
    hourly = load_hourly(repo, base_trades)

    temporary = output.with_name(f".{output.name}.tmp-{os.getpid()}")
    if temporary.exists():
        shutil.rmtree(temporary)
    temporary.mkdir(parents=True)

    runs: dict[tuple[str, float], PerformanceRun] = {}
    summaries: list[dict[str, object]] = []
    annual: list[dict[str, object]] = []
    monthly: list[dict[str, object]] = []
    asset: list[dict[str, object]] = []
    engine: list[dict[str, object]] = []
    regime: list[dict[str, object]] = []
    exits: list[dict[str, object]] = []
    holding: list[dict[str, object]] = []
    cohorts: list[dict[str, object]] = []
    named: list[dict[str, object]] = []
    concentration: list[dict[str, object]] = []
    rolling: list[dict[str, object]] = []
    drawdowns: list[dict[str, object]] = []
    reconciliation: list[dict[str, object]] = []

    try:
        for universe in UNIVERSE_IDS:
            for multiplier in COST_MULTIPLIERS:
                print(
                    f"P3E_BASE_RUN_START={universe}:{multiplier}x",
                    flush=True,
                )
                run = build_performance_run(
                    base_trades[universe],
                    universe_id=universe,
                    cost_multiplier=multiplier,
                    hourly_frames=hourly,
                    evidence_strong_pairs=evidence_pairs,
                )
                runs[(universe, multiplier)] = run
                root = temporary / "universes" / universe / f"cost-{int(multiplier)}x"
                root.mkdir(parents=True)
                run.adjusted_trades.to_parquet(
                    root / "adjusted-trades.parquet",
                    index=False,
                    compression="zstd",
                )
                run.equity_curve.to_parquet(
                    root / "equity-curve.parquet",
                    index=False,
                    compression="zstd",
                )
                summaries.append(run.metrics)
                annual.extend(run.annual_rows)
                monthly.extend(run.monthly_rows)
                asset.extend(run.asset_rows)
                engine.extend(run.engine_rows)
                regime.extend(run.regime_rows)
                exits.extend(run.exit_rows)
                holding.extend(run.holding_rows)
                cohorts.extend(run.cohort_rows)
                named.extend(run.named_asset_rows)
                concentration.append(run.concentration)
                rolling.extend(run.rolling_rows)
                drawdowns.extend(run.drawdown_rows)
                reconciliation.append(
                    {
                        "universe_id": universe,
                        "cost_multiplier": multiplier,
                        **run.reconciliation,
                    }
                )
                print(
                    f"P3E_BASE_RUN_COMPLETE={universe}:"
                    f"{multiplier}x:"
                    f"{run.metrics['net_return']}:"
                    f"{run.metrics['profit_factor']}:"
                    f"{run.metrics['maximum_drawdown']}:"
                    f"{run.metrics['minimum_cash']}",
                    flush=True,
                )

        universe_gates = [
            evaluate_universe_gates(
                universe_id=universe,
                one_x=runs[(universe, 1.0)],
                two_x=runs[(universe, 2.0)],
                technical_summary=technical[universe],
                registry=registry,
            )
            for universe in UNIVERSE_IDS
        ]
        cross = evaluate_cross_universe(
            universe_gates=universe_gates,
            runs=runs,
            registry=registry,
            legacy_baseline_net_return=float(legacy["legacy_one_x_net_return"]),
        )
        classification = base_classification(
            universe_gates=universe_gates,
            cross_universe=cross,
            runs=runs,
            registry=registry,
        )

        write_rows(temporary / "base-run-summary.csv", summaries)
        write_rows(temporary / "annual-performance.csv", annual)
        write_rows(temporary / "monthly-performance.csv", monthly)
        write_rows(temporary / "asset-attribution.csv", asset)
        write_rows(temporary / "engine-attribution.csv", engine)
        write_rows(temporary / "regime-attribution.csv", regime)
        write_rows(temporary / "exit-attribution.csv", exits)
        write_rows(temporary / "holding-attribution.csv", holding)
        write_rows(temporary / "cohort-attribution.csv", cohorts)
        write_rows(
            temporary / "named-asset-attribution.csv",
            named,
        )
        write_rows(
            temporary / "concentration-analysis.csv",
            concentration,
        )
        write_rows(
            temporary / "rolling-window-analysis.csv",
            rolling,
        )
        if drawdowns:
            write_rows(
                temporary / "drawdown-episodes.csv",
                drawdowns,
            )
        write_json(
            temporary / "cash-equity-reconciliation.json",
            reconciliation,
        )
        write_json(
            temporary / "universe-gate-evaluation.json",
            universe_gates,
        )
        write_json(
            temporary / "cross-universe-robustness.json",
            cross,
        )
        report = {
            "schema_version": "rd18-p3e-base-report-v1",
            "stage": STAGE,
            "decision": DECISION,
            "passed": True,
            "execution_status": "COMPLETE",
            "dry_run_upstream": {
                "decision": dry_report["decision"],
                "report_sha256": sha256(
                    dry_run_runtime / "rd18-p3e-technical-dry-run-report-v1.json"
                ),
                "manifest_sha256": sha256(dry_run_runtime / "output-manifest.json"),
                "manifest_deterministic_hash": dry_manifest["deterministic_hash"],
            },
            "legacy_baseline_metric_match": legacy,
            "base_runs": len(runs),
            "universes": list(UNIVERSE_IDS),
            "cost_multipliers": list(COST_MULTIPLIERS),
            "universe_gates": universe_gates,
            "cross_universe_robustness": cross,
            "base_classification": classification,
            "network_requests": 0,
            "strategy_replay_executed": True,
            "strategy_replay_reexecuted_in_this_stage": False,
            "portfolio_routing_executed": True,
            "portfolio_routing_reexecuted_in_this_stage": False,
            "exit_simulation_executed": True,
            "exit_simulation_reexecuted_in_this_stage": False,
            "return_calculation_executed": True,
            "portfolio_return_calculation_executed": True,
            "performance_reporting_executed": True,
            "cost_stress_executed": True,
            "loyo_executed": False,
            "loao_executed": False,
            "final_advancement_decision_made": False,
            "thresholds_changed_after_results": False,
            "per_universe_tuning": False,
            "post_2024_accessed": False,
            "production_authorized": False,
            "next_stage": NEXT_STAGE,
        }
        write_json(
            temporary / "rd18-p3e-base-cost-performance-report-v1.json",
            report,
        )
        write_json(
            temporary / "output-manifest.json",
            _manifest(temporary),
        )
        if output.exists():
            shutil.rmtree(output)
        os.replace(temporary, output)
        return report
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise


def main() -> int:
    args = parser().parse_args()
    if not args.preflight_only and not args.write_results:
        raise SystemExit("Use --preflight-only or --write-results")
    repo = args.repo_root.resolve()
    if args.preflight_only:
        result = preflight(
            repo,
            args.dry_run_runtime.resolve(),
            args.a3b_runtime.resolve(),
        )
    else:
        result = materialize(
            repo,
            args.dry_run_runtime.resolve(),
            args.a3b_runtime.resolve(),
            args.output_dir.resolve(),
        )
    print(
        json.dumps(
            json_ready(result),
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BasePerformanceError as exc:
        print(f"P3E_BASE_PERFORMANCE_ERROR={exc}", file=sys.stderr)
        raise SystemExit(2) from exc
