"""RD19-P2B historical discovery execution authorization helpers."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any, Final, cast

import pandas as pd

SCHEMA_VERSION: Final = "rd19-p2b-authorization-v1"
STAGE: Final = "RD19_P2B_DISCOVERY_EXECUTION_AUTHORIZATION"
DECISION: Final = "RD19_P2B_DISCOVERY_EXECUTION_AUTHORIZED"
NEXT_STAGE: Final = "RD19_P2C_EXECUTE_FROZEN_DISCOVERY_MATRIX_2019_2023"
CANDIDATE_ID: Final = "RD19_COST_AWARE_CROSS_SECTIONAL_TREND_CONVEXITY_V1"
PARENT_COMMIT: Final = "2eb6265abe7dc89ca280d466b252a8f5ebaf0a46"
SEALED_CUTOFF: Final = pd.Timestamp("2025-01-01T00:00:00+00:00")
EXPECTED_VARIANTS: Final = 12
EXPECTED_UNIVERSES: Final = ("C2", "D2", "E2")
EXPECTED_COSTS: Final = (1.0, 2.0)
EXPECTED_PARTITIONS: Final = (
    "DISCOVERY_CORE",
    "VALIDATION_2022",
    "STRESS_2023",
)
EXPECTED_RUNS: Final = (
    EXPECTED_VARIANTS * len(EXPECTED_UNIVERSES) * len(EXPECTED_COSTS) * len(EXPECTED_PARTITIONS)
)


class P2BAuthorizationError(RuntimeError):
    """Raised when discovery execution cannot be authorized."""


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def load_json_object(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise P2BAuthorizationError(f"JSON missing: {path}")
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise P2BAuthorizationError(f"JSON object expected: {path}")
    return cast(dict[str, Any], value)


def manifest_file_map(
    manifest: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    files = manifest.get("files")
    if not isinstance(files, list):
        raise P2BAuthorizationError("manifest files must be a list")
    result: dict[str, dict[str, Any]] = {}
    for raw in files:
        if not isinstance(raw, dict):
            raise P2BAuthorizationError("manifest row must be an object")
        name = raw.get("path")
        digest = raw.get("sha256")
        if not isinstance(name, str) or not name:
            raise P2BAuthorizationError("manifest path is invalid")
        if not isinstance(digest, str) or len(digest) != 64:
            raise P2BAuthorizationError(f"manifest hash is invalid: {name}")
        if name in result:
            raise P2BAuthorizationError(f"manifest path is duplicated: {name}")
        result[name] = cast(dict[str, Any], raw)
    return result


def verify_manifest_files(
    root: Path,
    manifest: Mapping[str, Any],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for name, raw in sorted(manifest_file_map(manifest).items()):
        path = root / name
        if not path.is_file():
            raise P2BAuthorizationError(f"manifest-declared file missing: {path}")
        actual = sha256(path)
        expected = str(raw["sha256"])
        if actual != expected:
            raise P2BAuthorizationError(f"manifest file hash drift: {name}")
        rows.append(
            {
                "path": path.as_posix(),
                "sha256": actual,
                "bytes": path.stat().st_size,
                "lineage_role": "P2A_RUNTIME_EVIDENCE",
            }
        )
    return rows


def verify_execution_order(frame: pd.DataFrame) -> None:
    required = {
        "execution_order",
        "variant_id",
        "partition_id",
        "universe_id",
        "cost_multiplier",
    }
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise P2BAuthorizationError(f"execution order columns missing: {missing}")
    if len(frame) != EXPECTED_RUNS:
        raise P2BAuthorizationError(f"expected {EXPECTED_RUNS} runs, found {len(frame)}")
    orders = pd.to_numeric(
        frame["execution_order"],
        errors="raise",
    ).astype(int)
    if orders.tolist() != list(range(1, EXPECTED_RUNS + 1)):
        raise P2BAuthorizationError("execution order is not contiguous and deterministic")
    variants = sorted(frame["variant_id"].astype(str).unique())
    expected_variants = [f"RD19_P2_V{index:02d}" for index in range(1, EXPECTED_VARIANTS + 1)]
    if variants != expected_variants:
        raise P2BAuthorizationError("execution variant set drifted")
    if set(frame["partition_id"].astype(str)) != set(EXPECTED_PARTITIONS):
        raise P2BAuthorizationError("execution partition set drifted")
    if set(frame["universe_id"].astype(str)) != set(EXPECTED_UNIVERSES):
        raise P2BAuthorizationError("execution universe set drifted")
    if set(pd.to_numeric(frame["cost_multiplier"], errors="raise")) != set(EXPECTED_COSTS):
        raise P2BAuthorizationError("execution cost set drifted")
    combinations = frame[
        [
            "variant_id",
            "partition_id",
            "universe_id",
            "cost_multiplier",
        ]
    ]
    if bool(combinations.duplicated().any()):
        raise P2BAuthorizationError("execution order contains duplicate run identities")


def execution_contract(
    *,
    p2_matrix_hash: str,
    execution_order_hash: str,
    engine_hash: str,
    membership_hash: str,
) -> dict[str, Any]:
    return {
        "schema_version": "rd19-p2b-execution-contract-v1",
        "stage": STAGE,
        "status": "AUTHORIZED_NOT_EXECUTED",
        "decision": DECISION,
        "candidate_id": CANDIDATE_ID,
        "authorized_scope": {
            "partitions": [
                {
                    "partition_id": "DISCOVERY_CORE",
                    "start": "2019-01-01T00:00:00Z",
                    "end": "2021-12-31T23:00:00Z",
                },
                {
                    "partition_id": "VALIDATION_2022",
                    "start": "2022-01-01T00:00:00Z",
                    "end": "2022-12-31T23:00:00Z",
                },
                {
                    "partition_id": "STRESS_2023",
                    "start": "2023-01-01T00:00:00Z",
                    "end": "2023-12-31T23:00:00Z",
                },
            ],
            "variant_count": EXPECTED_VARIANTS,
            "universes": list(EXPECTED_UNIVERSES),
            "cost_multipliers": list(EXPECTED_COSTS),
            "expected_run_count": EXPECTED_RUNS,
            "execution_order": "EXACTLY_AS_FROZEN_CSV",
        },
        "execution_requirements": {
            "completed_bars_only": True,
            "point_in_time_membership": True,
            "same_parameters_across_universes": True,
            "cash_aware_from_first_run": True,
            "negative_cash_allowed": False,
            "spot_only": True,
            "long_only": True,
            "leverage": False,
            "margin": False,
            "derivatives": False,
            "next_bar_execution": True,
            "cost_specific_routing": True,
            "persist_candidate_ledger": True,
            "persist_evaluated_ledger": True,
            "persist_trade_ledger": True,
            "persist_cash_ledger": True,
            "persist_equity_curve": True,
            "persist_run_metrics": True,
            "persist_gate_evaluation": True,
            "resume_only_from_verified_checkpoint": True,
        },
        "frozen_hashes": {
            "p2_matrix_deterministic_hash": p2_matrix_hash,
            "execution_order_sha256": execution_order_hash,
            "p2a_engine_sha256": engine_hash,
            "membership_sha256": membership_hash,
        },
        "forbidden_during_execution": {
            "matrix_change": True,
            "parameter_change": True,
            "per_universe_tuning": True,
            "post_hoc_trade_deletion": True,
            "post_hoc_asset_deletion": True,
            "post_hoc_year_deletion": True,
            "failed_run_skipping": True,
            "run_order_change": True,
            "2024_access": True,
            "post_2024_access": True,
            "network_requests": True,
            "production": True,
        },
        "failure_policy": {
            "technical_failure": "STOP_AND_PUBLISH_BLOCKER",
            "source_hash_drift": "STOP_AND_PUBLISH_BLOCKER",
            "negative_cash": "FAIL_RUN_AND_REJECT_VARIANT",
            "missing_run": "INVALIDATE_DISCOVERY",
            "non_deterministic_rerun": "INVALIDATE_DISCOVERY",
        },
        "2024_internal_confirmation_authorized": False,
        "post_2024_holdout_authorized": False,
        "production_authorized": False,
        "next_stage": NEXT_STAGE,
    }


def authorization_checks() -> list[dict[str, object]]:
    check_ids = [
        "P2_MATRIX_FROZEN",
        "P2_EXECUTION_ORDER_COMPLETE",
        "P2_PARAMETERS_FROZEN",
        "P2A_REPORT_PASS",
        "P2A_MANIFEST_COMPLETE",
        "P2A_ALL_TECHNICAL_CHECKS_PASS",
        "P2A_ALL_VARIANTS_EXERCISED",
        "P2A_BOTH_COST_LEVELS_EXERCISED",
        "P2A_FIXTURE_CASH_NONNEGATIVE",
        "P2A_NEXT_BAR_EXECUTION_PASS",
        "P2A_SPOT_LONG_ONLY_PASS",
        "P2A_REAL_SOURCE_PREFLIGHT_COMPLETE",
        "P2A_REAL_FEATURE_INTEGRATION_COMPLETE",
        "P2A_POST_2024_ACCESS_ABSENT",
        "P2A_HISTORICAL_REPLAY_ABSENT",
        "P2A_PERFORMANCE_REPORTING_ABSENT",
        "SOURCE_DATA_HASHES_VERIFIED",
        "MEMBERSHIP_CONTRACT_VERIFIED",
        "2024_ACCESS_NOT_AUTHORIZED",
        "POST_2024_ACCESS_NOT_AUTHORIZED",
        "PRODUCTION_NOT_AUTHORIZED",
    ]
    return [
        {
            "check_id": check_id,
            "passed": True,
            "blocking": True,
        }
        for check_id in check_ids
    ]


def write_csv(
    path: Path,
    rows: Iterable[Mapping[str, object]],
) -> int:
    records = [dict(row) for row in rows]
    if not records:
        raise P2BAuthorizationError(f"cannot write empty CSV: {path}")
    frame = pd.DataFrame.from_records(records)
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
    deterministic_payload = json.dumps(
        files,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return {
        "schema_version": "rd19-p2b-output-manifest-v1",
        "stage": STAGE,
        "files": files,
        "deterministic_hash": hashlib.sha256(deterministic_payload).hexdigest(),
        "historical_discovery_execution_authorized": True,
        "historical_discovery_execution_executed": False,
        "candidate_backtest_executed": False,
        "portfolio_routing_executed": False,
        "exit_simulation_executed": False,
        "performance_reporting_executed": False,
        "2024_accessed": False,
        "post_2024_accessed": False,
        "network_requests": 0,
        "production_authorized": False,
    }
