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
from spotbot.research.rd16l_architecture import (  # noqa: E402
    engine_cooldowns_respected,
    same_symbol_overlap_absent,
)
from spotbot.research.rd18_p3e_cash_feasibility import (  # noqa: E402
    COST_MULTIPLIERS,
    CashRouteResult,
    route_cash_feasible_candidates,
)
from spotbot.research.rd18_p3e_performance import (  # noqa: E402
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

STAGE = "RD18_P3E_CASH_FEASIBILITY_REMEDIATION"
DECISION = "RD18_P3E_CASH_FEASIBILITY_REMEDIATION_COMPLETE"
NEXT_STAGE = "RD18_P3E_LOYO_AND_LOAO_SENSITIVITY_EXECUTION"
EXPECTED_DRY_REPORT = "9a51c375a9a59ea3d50328a38c518afce4645de378088650cb1286a50850b4fb"
EXPECTED_DRY_MANIFEST = "dd24def921bf5bcc013d2cb38dd6e7fdde6b6cde7099560864f9ff4864f5bfca"
EXPECTED_PRIOR_BASE_REPORT = "d09de5028a163c4ccc9aedec27049fb26014e7119daec505866b4a8a63f161a0"
EXPECTED_PRIOR_BASE_MANIFEST = "010595e2fd8e31438bbc281383ee2d030eca295df2831fc891c0c53ad123b7f1"


class RemediationError(RuntimeError):
    pass


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    result.add_argument("--repo-root", type=Path, default=ROOT)
    result.add_argument(
        "--dry-run-runtime",
        type=Path,
        default=ROOT / "data/research/rd18_p3e_dry_run_runtime",
    )
    result.add_argument(
        "--prior-base-runtime",
        type=Path,
        default=ROOT / "data/research/rd18_p3e_base_runtime",
    )
    result.add_argument(
        "--a3b-runtime",
        type=Path,
        default=ROOT / "data/research/rd18_p3x_a3b_runtime",
    )
    result.add_argument(
        "--output-dir",
        type=Path,
        default=(ROOT / "data/research/rd18_p3e_cash_remediation_runtime"),
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
        raise RemediationError(f"JSON missing: {path}")
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise RemediationError(f"JSON object expected: {path}")
    return value


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise RemediationError(f"CSV missing: {path}")
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
        raise RemediationError(f"empty CSV row set: {path}")
    fields = sorted({str(key) for row in rows for key in row})
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fields,
            extrasaction="raise",
            lineterminator="\n",
        )
        writer.writeheader()
        for row in rows:
            writer.writerow({field: json_ready(row.get(field)) for field in fields})


def verify_manifest(
    root: Path,
    manifest: Mapping[str, object],
) -> None:
    files = manifest.get("files")
    if not isinstance(files, list):
        raise RemediationError("manifest files invalid")
    for raw in files:
        if not isinstance(raw, Mapping):
            raise RemediationError("manifest row invalid")
        path = root / str(raw["path"])
        if not path.is_file():
            raise RemediationError(f"manifest file missing: {raw['path']}")
        if path.stat().st_size != int(cast(int, raw["bytes"])) or sha256(path) != str(
            raw["sha256"]
        ):
            raise RemediationError(f"manifest mismatch: {raw['path']}")


def verify_contract(repo: Path) -> dict[str, Any]:
    contract = load_json(repo / "data/research/rd18_p3r" / "replay-execution-contract.json")
    gates = load_json(repo / "data/research/rd18_p3r" / "performance-gate-registry.json")
    execution = contract.get("execution")
    if not isinstance(execution, Mapping):
        raise RemediationError("P3R execution contract missing")
    if not all(
        (
            execution.get("negative_cash_allowed") is False,
            execution.get("initial_equity") == 100000.0,
            execution.get("fee_rate_per_side") == 0.001,
            execution.get("cost_multipliers") == [1.0, 2.0],
            execution.get("cost_multiplier_is_leverage") is False,
            contract.get("worst_universe_controls_advancement") is True,
            gates.get("thresholds_may_change_after_results") is False,
        )
    ):
        raise RemediationError("P3R cash semantics drifted")
    return gates


def verify_upstream(
    dry: Path,
    prior_base: Path,
) -> dict[str, object]:
    dry_report_path = dry / "rd18-p3e-technical-dry-run-report-v1.json"
    dry_manifest_path = dry / "output-manifest.json"
    base_report_path = prior_base / "rd18-p3e-base-cost-performance-report-v1.json"
    base_manifest_path = prior_base / "output-manifest.json"
    hashes = {
        "dry_report": sha256(dry_report_path),
        "dry_manifest": sha256(dry_manifest_path),
        "prior_base_report": sha256(base_report_path),
        "prior_base_manifest": sha256(base_manifest_path),
    }
    expected = {
        "dry_report": EXPECTED_DRY_REPORT,
        "dry_manifest": EXPECTED_DRY_MANIFEST,
        "prior_base_report": EXPECTED_PRIOR_BASE_REPORT,
        "prior_base_manifest": EXPECTED_PRIOR_BASE_MANIFEST,
    }
    if hashes != expected:
        raise RemediationError(f"upstream hash drift: {hashes}")
    dry_report = load_json(dry_report_path)
    dry_manifest = load_json(dry_manifest_path)
    prior_report = load_json(base_report_path)
    prior_manifest = load_json(base_manifest_path)
    verify_manifest(dry, dry_manifest)
    verify_manifest(prior_base, prior_manifest)
    prior_rows = read_csv(prior_base / "base-run-summary.csv")
    negative = [
        {
            "universe_id": row["universe_id"],
            "cost_multiplier": float(row["cost_multiplier"]),
            "minimum_cash": float(row["minimum_cash"]),
        }
        for row in prior_rows
        if float(row["minimum_cash"]) < 0.0
    ]
    if not all(
        (
            dry_report.get("passed") is True,
            dry_report.get("decision") == "RD18_P3E_TECHNICAL_DRY_RUN_COMPLETE",
            prior_report.get("passed") is True,
            prior_report.get("base_runs") == 6,
            prior_report.get("base_classification", {}).get("base_economic_gates_passed") is False,
            len(negative) == 6,
        )
    ):
        raise RemediationError("upstream cash-violation evidence drifted")
    return {
        "hashes": hashes,
        "prior_negative_cash_runs": negative,
        "prior_base_superseded_for_advancement": True,
        "supersession_reason": (
            "The frozen spot contract disallows negative cash, "
            "but the prior base router did not enforce available cash."
        ),
    }


def evidence_strong_pairs(
    a3b_runtime: Path,
) -> frozenset[str]:
    rows = read_csv(a3b_runtime / "effective-operational-membership.csv")
    pairs = {row["effective_pair"] for row in rows if row["universe_id"] == "D2"}
    if not pairs:
        raise RemediationError("evidence-strong set is empty")
    return frozenset(pairs)


def load_hourly(
    repo: Path,
    candidates: Mapping[str, pd.DataFrame],
) -> dict[str, pd.DataFrame]:
    symbols = sorted(
        {
            str(symbol)
            for frame in candidates.values()
            for symbol in frame["symbol"].astype(str).unique()
        }
    )
    store = ParquetCandleStore(repo / "data/raw/rd16b")
    cutoff = SEALED_CUTOFF.to_pydatetime()
    result: dict[str, pd.DataFrame] = {}
    for index, symbol in enumerate(symbols, start=1):
        path = store.dataset_path(
            exchange_id="kucoin",
            symbol=symbol,
            timeframe="1h",
        )
        metadata = load_json(store.metadata_path(path))
        expected = metadata.get("sha256")
        if not isinstance(expected, str) or sha256(path) != expected:
            raise RemediationError(f"hourly source hash mismatch: {symbol}")
        frame = pd.read_parquet(
            str(path),
            engine="pyarrow",
            filters=[("timestamp", "<", cutoff)],
        )
        result[symbol] = normalize_hourly_bars(frame)
        print(
            f"P3E_CASH_BAR_LOAD={index}/{len(symbols)}:{symbol}:{len(result[symbol])}",
            flush=True,
        )
    return result


def route_summary(
    result: CashRouteResult,
    *,
    universe_id: str,
) -> dict[str, object]:
    decisions = (
        result.evaluated["router_decision"].astype(str).value_counts().sort_index().to_dict()
    )
    checks = {
        "cash_feasible": result.cash_feasible,
        "minimum_cash_nonnegative": result.minimum_cash >= -1e-6,
        "same_symbol_overlap_absent": same_symbol_overlap_absent(result.trades),
        "engine_cooldowns_respected": engine_cooldowns_respected(result.trades),
        "maximum_positions_respected": (result.maximum_positions_observed <= 5),
        "maximum_open_risk_respected": (
            result.maximum_open_risk_fraction_observed <= 0.0225 + 1e-12
        ),
        "cash_decision_present": (result.insufficient_cash_rejections > 0),
    }
    return {
        "schema_version": "rd18-p3e-cash-route-summary-v1",
        "universe_id": universe_id,
        "cost_multiplier": result.cost_multiplier,
        "candidate_rows": len(result.candidates),
        "evaluated_rows": len(result.evaluated),
        "trade_rows": len(result.trades),
        "minimum_cash": result.minimum_cash,
        "final_cash": result.final_cash,
        "insufficient_cash_rejections": (result.insufficient_cash_rejections),
        "maximum_positions_observed": (result.maximum_positions_observed),
        "maximum_open_risk_fraction_observed": (result.maximum_open_risk_fraction_observed),
        "maximum_open_notional_fraction_observed": (result.maximum_open_notional_fraction_observed),
        "router_decision_counts": decisions,
        "checks": checks,
        "passed": all(checks.values()),
    }


def _manifest(root: Path) -> dict[str, object]:
    rows: list[dict[str, object]] = []
    aggregate = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name == "output-manifest.json":
            continue
        relative = path.relative_to(root).as_posix()
        row: dict[str, object] = {
            "path": relative,
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
        }
        if path.suffix == ".parquet":
            row["rows"] = pq.ParquetFile(path).metadata.num_rows
        elif path.suffix == ".csv":
            row["rows"] = len(read_csv(path))
        rows.append(row)
        aggregate.update(relative.encode())
        aggregate.update(b"\0")
        aggregate.update(str(row["sha256"]).encode())
        aggregate.update(b"\n")
    return {
        "schema_version": "rd18-p3e-cash-remediation-manifest-v1",
        "files": rows,
        "deterministic_hash": aggregate.hexdigest(),
        "network_requests": 0,
        "cash_aware_routing_executed": True,
        "cost_specific_routing_executed": True,
        "exit_path_reexecution": False,
        "portfolio_return_calculation_executed": True,
        "performance_reporting_executed": True,
        "loyo_executed": False,
        "loao_executed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
    }


def preflight(
    repo: Path,
    dry: Path,
    prior_base: Path,
    a3b: Path,
) -> dict[str, object]:
    gates = verify_contract(repo)
    upstream = verify_upstream(dry, prior_base)
    evidence = evidence_strong_pairs(a3b)
    candidate_rows: dict[str, int] = {}
    for universe in UNIVERSE_IDS:
        path = dry / "universes" / universe / "v3-candidates.parquet"
        candidate_rows[universe] = pq.ParquetFile(path).metadata.num_rows
    return {
        "schema_version": "rd18-p3e-cash-remediation-preflight-v1",
        "stage": STAGE,
        "passed": True,
        "upstream": upstream,
        "candidate_rows": candidate_rows,
        "evidence_strong_pair_count": len(evidence),
        "gate_registry_schema": gates["schema_version"],
        "cost_multipliers": list(COST_MULTIPLIERS),
        "network_requests": 0,
        "cash_aware_routing_executed": False,
        "portfolio_return_calculation_executed": False,
        "loyo_executed": False,
        "loao_executed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
    }


def materialize(
    repo: Path,
    dry: Path,
    prior_base: Path,
    a3b: Path,
    output: Path,
) -> dict[str, object]:
    gates = verify_contract(repo)
    upstream = verify_upstream(dry, prior_base)
    evidence = evidence_strong_pairs(a3b)
    candidates = {
        universe: pd.read_parquet(dry / "universes" / universe / "v3-candidates.parquet")
        for universe in UNIVERSE_IDS
    }
    hourly = load_hourly(repo, candidates)
    temporary = output.with_name(f".{output.name}.tmp-{os.getpid()}")
    if temporary.exists():
        shutil.rmtree(temporary)
    temporary.mkdir(parents=True)

    routes: dict[tuple[str, float], CashRouteResult] = {}
    runs: dict[tuple[str, float], PerformanceRun] = {}
    route_summaries: list[dict[str, object]] = []
    performance_rows: list[dict[str, object]] = []
    reconciliation: list[dict[str, object]] = []
    try:
        for universe in UNIVERSE_IDS:
            for cost in COST_MULTIPLIERS:
                print(
                    f"P3E_CASH_ROUTE_START={universe}:{cost}x",
                    flush=True,
                )
                route = route_cash_feasible_candidates(
                    candidates[universe],
                    universe_id=universe,
                    cost_multiplier=cost,
                )
                summary = route_summary(
                    route,
                    universe_id=universe,
                )
                if not summary["passed"]:
                    raise RemediationError(f"cash route checks failed: {universe}:{cost}")
                run = build_performance_run(
                    route.trades,
                    universe_id=universe,
                    cost_multiplier=cost,
                    hourly_frames=hourly,
                    evidence_strong_pairs=evidence,
                )
                if not bool(run.metrics["capital_feasible"]):
                    raise RemediationError(
                        f"performance still capital-infeasible: {universe}:{cost}"
                    )
                if float(run.metrics["minimum_cash"]) < -1e-6:
                    raise RemediationError(f"negative metric cash remains: {universe}:{cost}")
                routes[(universe, cost)] = route
                runs[(universe, cost)] = run
                root = temporary / "universes" / universe / f"cost-{int(cost)}x"
                root.mkdir(parents=True)
                route.evaluated.to_parquet(
                    root / "cash-routed-evaluated.parquet",
                    index=False,
                    compression="zstd",
                )
                route.trades.to_parquet(
                    root / "cash-routed-trades.parquet",
                    index=False,
                    compression="zstd",
                )
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
                write_json(root / "cash-route-summary.json", summary)
                route_summaries.append(summary)
                performance_rows.append(run.metrics)
                reconciliation.append(
                    {
                        "universe_id": universe,
                        "cost_multiplier": cost,
                        **run.reconciliation,
                    }
                )
                print(
                    f"P3E_CASH_ROUTE_COMPLETE={universe}:{cost}x:"
                    f"{len(route.trades)}:"
                    f"{route.insufficient_cash_rejections}:"
                    f"{run.metrics['net_return']}:"
                    f"{run.metrics['minimum_cash']}",
                    flush=True,
                )

        universe_gates = []
        for universe in UNIVERSE_IDS:
            technical = {
                "maximum_positions_observed": max(
                    routes[(universe, cost)].maximum_positions_observed for cost in COST_MULTIPLIERS
                ),
                "maximum_open_risk_fraction_observed": max(
                    routes[(universe, cost)].maximum_open_risk_fraction_observed
                    for cost in COST_MULTIPLIERS
                ),
            }
            universe_gates.append(
                evaluate_universe_gates(
                    universe_id=universe,
                    one_x=runs[(universe, 1.0)],
                    two_x=runs[(universe, 2.0)],
                    technical_summary=technical,
                    registry=gates,
                )
            )
        legacy_return = float(
            read_csv(repo / "data/research/rd16m" / "composite-v3-baseline-summary.csv")[0][
                "net_return"
            ]
        )
        cross = evaluate_cross_universe(
            universe_gates=universe_gates,
            runs=runs,
            registry=gates,
            legacy_baseline_net_return=legacy_return,
        )
        classification = base_classification(
            universe_gates=universe_gates,
            cross_universe=cross,
            runs=runs,
            registry=gates,
        )

        write_rows(
            temporary / "cash-route-summary.csv",
            route_summaries,
        )
        write_rows(
            temporary / "corrected-base-run-summary.csv",
            performance_rows,
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
            "schema_version": "rd18-p3e-cash-remediation-report-v1",
            "stage": STAGE,
            "decision": DECISION,
            "passed": True,
            "execution_status": "COMPLETE",
            "prior_base_evidence": upstream,
            "prior_base_superseded_for_advancement": True,
            "cash_aware_routing_executed": True,
            "cost_specific_routing_executed": True,
            "corrected_runs": 6,
            "route_summaries": route_summaries,
            "universe_gates": universe_gates,
            "cross_universe_robustness": cross,
            "corrected_base_classification": classification,
            "network_requests": 0,
            "exit_path_reexecution": False,
            "portfolio_return_calculation_executed": True,
            "performance_reporting_executed": True,
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
            temporary / "rd18-p3e-cash-feasibility-remediation-report-v1.json",
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
            args.prior_base_runtime.resolve(),
            args.a3b_runtime.resolve(),
        )
    else:
        result = materialize(
            repo,
            args.dry_run_runtime.resolve(),
            args.prior_base_runtime.resolve(),
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
    except RemediationError as exc:
        print(f"P3E_CASH_REMEDIATION_ERROR={exc}", file=sys.stderr)
        raise SystemExit(2) from exc
