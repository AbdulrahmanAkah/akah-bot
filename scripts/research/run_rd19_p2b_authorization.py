"""Review RD19-P2A evidence and authorize frozen discovery execution."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any, cast

import pandas as pd

from spotbot.research.rd19_p2b_authorization import (
    CANDIDATE_ID,
    DECISION,
    EXPECTED_RUNS,
    NEXT_STAGE,
    PARENT_COMMIT,
    SCHEMA_VERSION,
    SEALED_CUTOFF,
    STAGE,
    P2BAuthorizationError,
    authorization_checks,
    build_manifest,
    execution_contract,
    load_json_object,
    sha256,
    verify_execution_order,
    verify_manifest_files,
    write_csv,
)

EXPECTED_HASHES = {
    "src/spotbot/research/rd19_p2a_engine.py": (
        "ca9ac0a81c09a346e462295f75ae19c0a1e230fe3e670afff8f046d20339b70d"
    ),
    "scripts/research/run_rd19_p2a_technical_dry_run.py": (
        "dc9a3b7e8a16cb471aea57abbdb96762f9289868aaa62bc5e4828ac75daa8ed5"
    ),
    "scripts/research/validate_rd19_p2a_technical_dry_run.py": (
        "f185c8aa5e1249595adb96f5c2ff225580a4ace084a4e536c9ad8a8083dfe70e"
    ),
    "tests/research/test_rd19_p2a_engine.py": (
        "265ddac91bb643c6d3084f10806bff1ebb889e7d61795989b1b9cdfab9339d11"
    ),
    (
        "data/research/rd19_p2a/rd19-p2a-technical-dry-run-protocol-v1.json"
    ): "e89e61d128117cfc39adc1d83e61e6dcc849a605939f6d66f72002911ea844e4",
    (
        "data/research/rd19_p2a_runtime/rd19-p2a-technical-dry-run-report-v1.json"
    ): "883e735bbf0457a8a11cca754a96c353b1fc983639d8256a17c8ca8bc2daabbb",
    "data/research/rd19_p2a_runtime/output-manifest.json": (
        "64af2118749ea4704752c5a19c02ffe3e69a236da2d460677fe0db7b8b60b82b"
    ),
    "data/research/rd19_p2a_runtime/implementation-contract.json": (
        "dba886d473b85e0c965bb10e56448977c8495e959c70999bc9000dbdea2dfe13"
    ),
    "data/research/rd19_p2a_runtime/technical-checks.csv": (
        "cce9314a8d7901c1a33a9ae9a1195a8780a55334d24a542b64c7421eee4bfd6a"
    ),
    "data/research/rd19_p2a_runtime/variant-contract-ledger.csv": (
        "6775ff7d640304194fd7f42ce471766f2e0d0801518ccce5ac969ecc9f3737b8"
    ),
    "data/research/rd19_p2a_runtime/feature-integration-preflight.csv": (
        "dee11e719616430e878b562c6235053bfad9a19cf4315025d7515147f86807f1"
    ),
    "data/research/rd19_p2a_runtime/real-source-preflight.csv": (
        "5bbc6a9fb67ede7640d824aabb0e9b8315520c12772085e6a3c68003948d4f0f"
    ),
    "data/research/rd19_p2a_runtime/fixture-dry-run-summary.csv": (
        "6e20b2dd7a6fbbe408c917e4b48a6f632cd7411ad53aad6a724e7645eb86ba83"
    ),
}

P2_RUNTIME = "data/research/rd19_p2_runtime"
P2A_RUNTIME = "data/research/rd19_p2a_runtime"
MEMBERSHIP_PATH = "data/research/rd18_p3x_a3b_runtime/effective-operational-membership.csv"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument(
        "--raw-root",
        type=Path,
        default=None,
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--preflight-only", action="store_true")
    return parser.parse_args()


def verify_expected_hashes(repo: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for relative, expected in EXPECTED_HASHES.items():
        path = repo / relative
        if not path.is_file():
            raise P2BAuthorizationError(f"authoritative P2A file missing: {relative}")
        actual = sha256(path)
        if actual != expected:
            raise P2BAuthorizationError(f"authoritative P2A hash drift: {relative}")
        rows.append(
            {
                "path": relative,
                "sha256": actual,
                "bytes": path.stat().st_size,
                "lineage_role": "P2A_FROZEN_IMPLEMENTATION_OR_EVIDENCE",
            }
        )
    return rows


def verify_p2_and_p2a(
    repo: Path,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, object]]]:
    p2_report = load_json_object(repo / P2_RUNTIME / "rd19-p2-discovery-freeze-report-v1.json")
    p2_protocol = load_json_object(repo / P2_RUNTIME / "rd19-p2-discovery-protocol-v1.json")
    p2a_report = load_json_object(repo / P2A_RUNTIME / "rd19-p2a-technical-dry-run-report-v1.json")
    p2a_manifest = load_json_object(repo / P2A_RUNTIME / "output-manifest.json")

    p2_expected = {
        "passed": True,
        "decision": "RD19_P2_DISCOVERY_PROTOCOL_AND_MATRIX_FROZEN",
        "selected_candidate_id": CANDIDATE_ID,
        "variant_count": 12,
        "matrix_frozen": True,
        "parameters_frozen_for_p2": True,
        "p2_execution_authorized_now": False,
        "implementation_and_dry_run_authorized": True,
        "candidate_backtest_executed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
    }
    p2_drift = {
        key: {"expected": wanted, "actual": p2_report.get(key)}
        for key, wanted in p2_expected.items()
        if p2_report.get(key) != wanted
    }
    if p2_drift:
        raise P2BAuthorizationError(f"P2 report drift: {p2_drift}")

    p2a_expected = {
        "passed": True,
        "decision": ("RD19_P2A_ENGINE_IMPLEMENTATION_AND_TECHNICAL_DRY_RUN_COMPLETE"),
        "selected_candidate_id": CANDIDATE_ID,
        "variant_count": 12,
        "fixture_run_count": 24,
        "technical_check_count": 19,
        "engine_implementation_executed": True,
        "synthetic_fixture_executed": True,
        "real_historical_feature_preflight_executed": True,
        "candidate_backtest_executed": False,
        "real_historical_strategy_replay_executed": False,
        "real_historical_portfolio_routing_executed": False,
        "real_historical_exit_simulation_executed": False,
        "performance_reporting_executed": False,
        "portfolio_return_calculation_executed": False,
        "p2_execution_authorized": False,
        "post_2024_accessed": False,
        "production_authorized": False,
        "next_stage": "RD19_P2B_DISCOVERY_EXECUTION_AUTHORIZATION",
    }
    p2a_drift = {
        key: {"expected": wanted, "actual": p2a_report.get(key)}
        for key, wanted in p2a_expected.items()
        if p2a_report.get(key) != wanted
    }
    if p2a_drift:
        raise P2BAuthorizationError(f"P2A report drift: {p2a_drift}")

    manifest_expected = {
        "engine_implementation_executed": True,
        "synthetic_fixture_executed": True,
        "real_historical_feature_preflight_executed": True,
        "candidate_backtest_executed": False,
        "real_historical_strategy_replay_executed": False,
        "real_historical_portfolio_routing_executed": False,
        "real_historical_exit_simulation_executed": False,
        "performance_reporting_executed": False,
        "portfolio_return_calculation_executed": False,
        "post_2024_accessed": False,
        "network_requests": 0,
        "production_authorized": False,
    }
    manifest_drift = {
        key: {"expected": wanted, "actual": p2a_manifest.get(key)}
        for key, wanted in manifest_expected.items()
        if p2a_manifest.get(key) != wanted
    }
    if manifest_drift:
        raise P2BAuthorizationError(f"P2A manifest drift: {manifest_drift}")

    lineage = verify_expected_hashes(repo)
    lineage.extend(verify_manifest_files(repo / P2A_RUNTIME, p2a_manifest))
    return p2_protocol, p2a_report, lineage


def verify_evidence_tables(repo: Path) -> None:
    checks = pd.read_csv(repo / P2A_RUNTIME / "technical-checks.csv")
    if len(checks) != 19:
        raise P2BAuthorizationError("technical check count drifted")
    if not bool(checks["passed"].astype(bool).all()):
        raise P2BAuthorizationError("P2A contains failed technical checks")
    if not bool(checks["blocking"].astype(bool).all()):
        raise P2BAuthorizationError("P2A check blocking policy drifted")

    variants = pd.read_csv(repo / P2A_RUNTIME / "variant-contract-ledger.csv")
    if len(variants) != 12 or variants["variant_id"].nunique() != 12:
        raise P2BAuthorizationError("variant contract coverage drifted")
    if not bool(variants["parameters_frozen"].astype(bool).all()):
        raise P2BAuthorizationError("variant parameters are not frozen")

    fixture = pd.read_csv(repo / P2A_RUNTIME / "fixture-dry-run-summary.csv")
    if len(fixture) != 24:
        raise P2BAuthorizationError("fixture run count drifted")
    if fixture["variant_id"].nunique() != 12:
        raise P2BAuthorizationError("fixture variant coverage drifted")
    if set(pd.to_numeric(fixture["cost_multiplier"])) != {1.0, 2.0}:
        raise P2BAuthorizationError("fixture cost coverage drifted")
    if not bool((pd.to_numeric(fixture["candidate_rows"]) > 0).all()):
        raise P2BAuthorizationError("fixture contains empty candidates")
    if not bool((pd.to_numeric(fixture["trade_rows"]) > 0).all()):
        raise P2BAuthorizationError("fixture contains empty trades")
    if not bool((pd.to_numeric(fixture["minimum_cash"]) >= 0.0).all()):
        raise P2BAuthorizationError("fixture contains negative cash")
    for column in ("next_bar_execution", "spot_only", "long_only"):
        if not bool(fixture[column].astype(bool).all()):
            raise P2BAuthorizationError(f"fixture contract failed: {column}")

    features = pd.read_csv(repo / P2A_RUNTIME / "feature-integration-preflight.csv")
    if len(features) != 12 or features["pair"].nunique() != 6:
        raise P2BAuthorizationError("feature integration coverage drifted")
    if set(features["entry_family"].astype(str)) != {
        "CONFIRMED_PULLBACK",
        "VOLATILITY_CONTRACTION_BREAKOUT",
    }:
        raise P2BAuthorizationError("feature integration entry-family coverage drifted")
    maximum = pd.to_datetime(
        features["maximum_timestamp"],
        utc=True,
        errors="raise",
    ).max()
    if maximum >= SEALED_CUTOFF:
        raise P2BAuthorizationError("feature integration crossed the sealed cutoff")
    if bool(features["post_2024_accessed"].astype(bool).any()):
        raise P2BAuthorizationError("feature integration reports post-2024 access")


def verify_membership(repo: Path) -> tuple[str, dict[str, object]]:
    path = repo / MEMBERSHIP_PATH
    if not path.is_file():
        raise P2BAuthorizationError("membership file is missing")
    frame = pd.read_csv(path)
    required = {
        "universe_id",
        "decision_time",
        "effective_end",
        "effective_pair",
        "effective_rank",
    }
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise P2BAuthorizationError(f"membership columns missing: {missing}")
    if len(frame) != 5418:
        raise P2BAuthorizationError(f"membership row count drifted: {len(frame)}")
    frame["decision_time"] = pd.to_datetime(
        frame["decision_time"],
        utc=True,
        errors="raise",
    )
    frame["effective_end"] = pd.to_datetime(
        frame["effective_end"],
        utc=True,
        errors="raise",
    )
    if bool((frame["effective_end"] > SEALED_CUTOFF).any()):
        raise P2BAuthorizationError("membership crosses the sealed cutoff")
    if set(frame["universe_id"].astype(str)) != {"C2", "D2", "E2"}:
        raise P2BAuthorizationError("membership universe set drifted")
    return sha256(path), {
        "path": MEMBERSHIP_PATH,
        "sha256": sha256(path),
        "bytes": path.stat().st_size,
        "lineage_role": "POINT_IN_TIME_MEMBERSHIP",
    }


def verify_real_sources(
    repo: Path,
    raw_root: Path,
) -> list[dict[str, object]]:
    ledger = pd.read_csv(repo / P2A_RUNTIME / "real-source-preflight.csv")
    if len(ledger) != 35 or ledger["pair"].nunique() != 35:
        raise P2BAuthorizationError("real source coverage drifted")

    rows: list[dict[str, object]] = []
    for raw in ledger.to_dict(orient="records"):
        pair = str(raw["pair"])
        data_path = raw_root / pair / "1h.parquet"
        metadata_path = raw_root / pair / "1h.metadata.json"
        if not data_path.is_file() or not metadata_path.is_file():
            raise P2BAuthorizationError(f"real source file missing: {pair}")
        metadata = load_json_object(metadata_path)
        expected = metadata.get("sha256")
        if not isinstance(expected, str):
            raise P2BAuthorizationError(f"source metadata hash missing: {pair}")
        actual = sha256(data_path)
        if actual != expected:
            raise P2BAuthorizationError(f"real source hash drift: {pair}")
        last = pd.Timestamp(cast(Any, metadata["last_timestamp"]))
        last = last.tz_localize("UTC") if last.tzinfo is None else last.tz_convert("UTC")
        if last > SEALED_CUTOFF:
            raise P2BAuthorizationError(f"real source extends beyond sealed boundary: {pair}")
        rows.extend(
            [
                {
                    "path": data_path.relative_to(repo).as_posix(),
                    "sha256": actual,
                    "bytes": data_path.stat().st_size,
                    "lineage_role": "SEALED_HOURLY_PARQUET",
                },
                {
                    "path": metadata_path.relative_to(repo).as_posix(),
                    "sha256": sha256(metadata_path),
                    "bytes": metadata_path.stat().st_size,
                    "lineage_role": "SEALED_HOURLY_METADATA",
                },
            ]
        )
    return rows


def publication(decision: dict[str, object]) -> str:
    return "\n".join(
        [
            "# RD19-P2B Discovery Execution Authorization",
            "",
            f"- Decision: `{decision['decision']}`",
            f"- Authorized: **{decision['authorized']}**",
            f"- Frozen historical runs: **{decision['expected_run_count']}**",
            "- Authorized data: **2019-01-01 through 2023-12-31**",
            "- 2024 access: **Not authorized**",
            "- Post-2024 access: **Not authorized**",
            "- Production authorization: **No**",
            "",
            "The frozen twelve-variant matrix, P2A implementation, point-in-"
            "time membership and sealed hourly sources passed the authorization "
            "review. P2C may execute only the published 216-run order. Any "
            "parameter change, skipped run, negative-cash concealment or access "
            "to 2024 or later invalidates the discovery.",
            "",
            f"Next stage: `{decision['next_stage']}`",
            "",
        ]
    )


def main() -> int:
    args = parse_args()
    repo = args.repo_root.resolve()
    raw_root = (
        args.raw_root.resolve() if args.raw_root is not None else repo / "data/raw/rd16b/kucoin"
    )
    output = args.output_dir.resolve()

    p2_protocol, p2a_report, lineage = verify_p2_and_p2a(repo)
    verify_evidence_tables(repo)

    execution_path = repo / P2_RUNTIME / "execution-order.csv"
    execution = pd.read_csv(execution_path)
    verify_execution_order(execution)
    lineage.append(
        {
            "path": execution_path.relative_to(repo).as_posix(),
            "sha256": sha256(execution_path),
            "bytes": execution_path.stat().st_size,
            "lineage_role": "FROZEN_EXECUTION_ORDER",
        }
    )

    membership_hash, membership_row = verify_membership(repo)
    lineage.append(membership_row)
    lineage.extend(verify_real_sources(repo, raw_root))

    checks = authorization_checks()
    contract = execution_contract(
        p2_matrix_hash=str(p2_protocol["matrix_deterministic_hash"]),
        execution_order_hash=sha256(execution_path),
        engine_hash=sha256(repo / "src/spotbot/research/rd19_p2a_engine.py"),
        membership_hash=membership_hash,
    )

    if args.preflight_only:
        print(
            json.dumps(
                {
                    "status": "PASS",
                    "decision": DECISION,
                    "authorized": True,
                    "expected_run_count": EXPECTED_RUNS,
                    "lineage_rows": len(lineage),
                    "next_stage": NEXT_STAGE,
                    "post_2024_accessed": False,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    if not args.publish:
        raise P2BAuthorizationError("use --publish or --preflight-only")

    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True, exist_ok=False)

    rows_by_file: dict[str, int | None] = {}
    rows_by_file["lineage-hash-manifest.csv"] = write_csv(
        output / "lineage-hash-manifest.csv",
        lineage,
    )
    rows_by_file["authorization-checks.csv"] = write_csv(
        output / "authorization-checks.csv",
        checks,
    )
    (output / "execution-contract.json").write_text(
        json.dumps(contract, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    rows_by_file["execution-contract.json"] = None

    decision: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "stage": STAGE,
        "decision": DECISION,
        "passed": True,
        "authorized": True,
        "technical_valid": True,
        "blockers": [],
        "parent_commit": PARENT_COMMIT,
        "upstream_decision": p2a_report["decision"],
        "selected_candidate_id": CANDIDATE_ID,
        "authorization_status": "AUTHORIZED_NOT_EXECUTED",
        "authorized_period_start": "2019-01-01T00:00:00Z",
        "authorized_period_end": "2023-12-31T23:00:00Z",
        "variant_count": 12,
        "partition_count": 3,
        "universe_count": 3,
        "cost_multiplier_count": 2,
        "expected_run_count": EXPECTED_RUNS,
        "authorization_check_count": len(checks),
        "lineage_hash_rows": len(lineage),
        "historical_discovery_execution_authorized": True,
        "historical_discovery_execution_executed": False,
        "candidate_backtest_executed": False,
        "portfolio_routing_executed": False,
        "exit_simulation_executed": False,
        "performance_reporting_executed": False,
        "2024_access_authorized": False,
        "2024_accessed": False,
        "post_2024_access_authorized": False,
        "post_2024_accessed": False,
        "network_requests": 0,
        "production_authorized": False,
        "next_stage": NEXT_STAGE,
        "recommended_action": ("EXECUTE_EXACT_FROZEN_216_RUN_DISCOVERY_ORDER_2019_2023"),
    }
    (output / "authorization-decision.json").write_text(
        json.dumps(decision, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    rows_by_file["authorization-decision.json"] = None

    (output / "rd19-p2b-authorization-v1.md").write_text(
        publication(decision),
        encoding="utf-8",
        newline="\n",
    )
    rows_by_file["rd19-p2b-authorization-v1.md"] = None

    manifest = build_manifest(output, rows_by_file=rows_by_file)
    (output / "output-manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    print(
        json.dumps(
            {
                "status": "PASS",
                "decision": DECISION,
                "authorized": True,
                "expected_run_count": EXPECTED_RUNS,
                "lineage_rows": len(lineage),
                "next_stage": NEXT_STAGE,
                "output_dir": str(output),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
