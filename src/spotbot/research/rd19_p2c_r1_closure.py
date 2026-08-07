"""RD19-P2C-R1 no-finalists discovery closure helpers."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any, Final, cast

import pandas as pd

SCHEMA_VERSION: Final = "rd19-p2c-r1-closure-v1"
STAGE: Final = "RD19_P2C_R1_DISCOVERY_CLOSURE"
DECISION: Final = "RD19_P2C_R1_DISCOVERY_CLOSED_NO_FINALISTS"
CANDIDATE_ID: Final = "RD19_COST_AWARE_CROSS_SECTIONAL_TREND_CONVEXITY_V1"
CANDIDATE_DISPOSITION: Final = "RD19_CURRENT_FROZEN_DESIGN_REJECTED_NO_FINALISTS"
NEXT_STAGE: Final = "RD19_P2C_R1_CLOSED_NO_ADVANCEMENT"
RECOMMENDED_FOLLOWUP: Final = "NEW_PREREGISTERED_CANDIDATE_REQUIRED_AFTER_REVIEW"
EXPECTED_PARENT: Final = "7bb8273ea3e6da404e79a7296e0fd57602276c31"
EXPECTED_VARIANT_COUNT: Final = 12
EXPECTED_RUN_COUNT: Final = 216

AUTHORITATIVE_RUNTIME_HASHES: Final = {
    "combined-2019-2023-metrics.csv": (
        "32a371d367b5fc13c16f965721f24ce41cd781f92d2518aeb3a09683c93124c1"
    ),
    "correction-audit.json": ("5049a30eb550e013cda07545c2c93836286d31b91f86672035327c751a9e5744"),
    "finalist-ranking.csv": ("bf8aab855e712336170f06e9f424a1efe1a2e34be405166e2fdde6efacb3d4d3"),
    "local-evidence-manifest.csv": (
        "deb05dbab8b841ddd7657f5b677527b2ae236d54b03b01392aec7bacef7168dc"
    ),
    "output-manifest.json": ("6ab35a38b26289a33bc4af1bdcaf8ffc28751cb0d5c78d41fa399edc2b2436f7"),
    "rd19-p2c-r1-correction-report-v1.json": (
        "fcedcf54c87d943cb5a5dac21f251c6c0b636eb4b90cd0dff5307f4b1bda02ab"
    ),
    "run-metrics.csv": ("48cef5ef9e331497229f543d83f06bb6ff61b824a1385953e756d365a3ee543d"),
    "signal-funnel.csv": ("d55bffaa5bb6541ad745075feb64ddb0a5fc47b314e006a803d90580ef80d75f"),
    "timing-report.json": ("0823ec2f02e13bf697141f28627916d1f82dd1cc8f1dc560cf078a791caae4a3"),
    "variant-gate-evaluation.csv": (
        "c3d2d5d7298f3075addb8ec98376ac68c84dd10579a7443c5fa592518bdfdcd6"
    ),
}


class P2CR1ClosureError(RuntimeError):
    """Raised when RD19-P2C-R1 cannot be closed safely."""


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def load_json_object(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise P2CR1ClosureError(f"JSON missing: {path}")
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise P2CR1ClosureError(f"JSON object expected: {path}")
    return cast(dict[str, Any], value)


def write_json(path: Path, value: object) -> None:
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


def verify_authoritative_runtime(runtime_dir: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for name, expected in sorted(AUTHORITATIVE_RUNTIME_HASHES.items()):
        path = runtime_dir / name
        if not path.is_file():
            raise P2CR1ClosureError(f"authoritative runtime file missing: {name}")
        actual = sha256(path)
        if actual != expected:
            raise P2CR1ClosureError(f"authoritative runtime hash drift: {name}: {actual}")
        rows.append(
            {
                "path": name,
                "sha256": actual,
                "bytes": path.stat().st_size,
                "role": "AUTHORITATIVE_P2C_R1_EVIDENCE",
            }
        )
    return rows


def verify_authoritative_semantics(
    runtime_dir: Path,
) -> tuple[dict[str, Any], pd.DataFrame, pd.DataFrame]:
    report = load_json_object(runtime_dir / "rd19-p2c-r1-correction-report-v1.json")
    expected_report = {
        "passed": True,
        "decision": "RD19_P2C_R1_CONFORMANCE_CORRECTION_REPLAY_COMPLETE",
        "selected_candidate_id": CANDIDATE_ID,
        "authorized_run_count": EXPECTED_RUN_COUNT,
        "completed_run_count": EXPECTED_RUN_COUNT,
        "variant_count": EXPECTED_VARIANT_COUNT,
        "hard_gate_pass_variant_count": 0,
        "ranked_finalist_count": 0,
        "selected_for_2024_count": 0,
        "selected_for_2024_variants": [],
        "parameter_changes": 0,
        "matrix_changes": 0,
        "hard_gate_changes": 0,
        "original_p2c_result_disposition": ("INVALIDATED_FOR_IMPLEMENTATION_NONCONFORMANCE"),
        "2024_internal_confirmation_executed": False,
        "2024_market_data_accessed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
        "next_stage": "RD19_P2C_R1_NO_FINALISTS_DISCOVERY_REJECTION_REVIEW",
    }
    drift = {
        key: {"expected": wanted, "actual": report.get(key)}
        for key, wanted in expected_report.items()
        if report.get(key) != wanted
    }
    if drift:
        raise P2CR1ClosureError(f"authoritative report semantic drift: {drift}")

    gates = pd.read_csv(runtime_dir / "variant-gate-evaluation.csv")
    if len(gates) != EXPECTED_VARIANT_COUNT:
        raise P2CR1ClosureError(f"gate row count drift: expected 12, got {len(gates)}")
    if gates["variant_id"].astype(str).nunique() != EXPECTED_VARIANT_COUNT:
        raise P2CR1ClosureError("gate variant identities are not unique")
    if bool(gates["passed_all_hard_gates"].astype(bool).any()):
        raise P2CR1ClosureError("closure blocked: at least one variant passed all hard gates")
    if bool((pd.to_numeric(gates["failure_count"], errors="raise") <= 0).any()):
        raise P2CR1ClosureError("closure blocked: a rejected variant has no recorded gate failure")

    finalists = pd.read_csv(runtime_dir / "finalist-ranking.csv")
    if not finalists.empty:
        raise P2CR1ClosureError("closure blocked: finalist-ranking.csv is not empty")
    return report, gates, finalists


def build_variant_disposition(gates: pd.DataFrame) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for raw in gates.sort_values("variant_id", kind="stable").to_dict(orient="records"):
        rows.append(
            {
                "variant_id": str(raw["variant_id"]),
                "disposition": "REJECTED_HARD_GATES",
                "advancement_eligible": False,
                "failure_count": int(raw["failure_count"]),
                "worst_universe_2x_monthly_geometric_return": float(
                    raw["worst_universe_2x_monthly_geometric_return"]
                ),
                "worst_universe_2x_profit_factor": float(raw["worst_universe_2x_profit_factor"]),
                "worst_universe_2x_maximum_drawdown": float(
                    raw["worst_universe_2x_maximum_drawdown"]
                ),
                "maximum_turnover_across_combined_runs": float(
                    raw["maximum_turnover_across_combined_runs"]
                ),
                "failures_json": str(raw["failures_json"]),
            }
        )
    return rows


def closure_checks() -> list[dict[str, object]]:
    check_ids = (
        "AUTHORITATIVE_CORRECTION_REPORT_PASS",
        "AUTHORITATIVE_RUN_COUNT_216",
        "AUTHORITATIVE_VARIANT_COUNT_12",
        "NO_VARIANT_PASSED_ALL_HARD_GATES",
        "FINALIST_RANKING_EMPTY",
        "SELECTED_FOR_2024_EMPTY",
        "PARAMETER_CHANGES_ZERO",
        "MATRIX_CHANGES_ZERO",
        "HARD_GATE_CHANGES_ZERO",
        "ORIGINAL_NONCONFORMING_P2C_INVALIDATED",
        "2024_INTERNAL_CONFIRMATION_NOT_EXECUTED",
        "2024_MARKET_DATA_NOT_ACCESSED",
        "POST_2024_NOT_ACCESSED",
        "PRODUCTION_NOT_AUTHORIZED",
        "CLOSURE_EXECUTES_NO_BACKTEST",
        "CLOSURE_EXECUTES_NO_PORTFOLIO_ROUTING",
        "CLOSURE_EXECUTES_NO_EXIT_SIMULATION",
        "CLOSURE_CHANGES_NO_PARAMETERS",
    )
    return [{"check_id": check_id, "passed": True, "blocking": True} for check_id in check_ids]


def write_csv(path: Path, rows: Iterable[Mapping[str, object]]) -> int:
    records = [dict(row) for row in rows]
    if not records:
        raise P2CR1ClosureError(f"refusing to write empty CSV: {path}")
    frame = pd.DataFrame.from_records(records)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, lineterminator="\n")
    return len(frame)


def build_manifest(
    output_dir: Path,
    *,
    rows_by_file: Mapping[str, int | None],
) -> dict[str, object]:
    files: list[dict[str, object]] = []
    for path in sorted(output_dir.iterdir()):
        if not path.is_file() or path.name == "output-manifest.json":
            continue
        row: dict[str, object] = {
            "path": path.name,
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
        }
        count = rows_by_file.get(path.name)
        if count is not None:
            row["rows"] = count
        files.append(row)

    deterministic = hashlib.sha256(
        json.dumps(files, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return {
        "schema_version": "rd19-p2c-r1-closure-manifest-v1",
        "stage": STAGE,
        "decision": DECISION,
        "deterministic_hash": deterministic,
        "files": files,
        "p2c_r1_closed": True,
        "final_advancement_eligible": False,
        "closure_backtest_executed": False,
        "closure_portfolio_routing_executed": False,
        "closure_exit_simulation_executed": False,
        "closure_parameter_changes": 0,
        "2024_accessed": False,
        "post_2024_accessed": False,
        "network_requests": 0,
        "production_authorized": False,
    }
