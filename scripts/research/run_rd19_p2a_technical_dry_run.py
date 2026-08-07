"""Run the RD19-P2A engine implementation and technical dry run."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import sys
from pathlib import Path
from typing import Any, cast

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from spotbot.research.rd19_p2a_engine import (  # noqa: E402
    CANDIDATE_ID,
    DECISION,
    NEXT_STAGE,
    SCHEMA_VERSION,
    SEALED_CUTOFF,
    STAGE,
    dry_run_variant,
    feature_frame,
    load_json_object,
    normalize_bars,
    resolve_variants,
    sha256,
)

EXPECTED_PARENT = "e83c25bc4800f144ab0741273a45363e7d768cf9"
EXPECTED_P2_REPORT_SHA256 = "7ca3a7d78b62ca6d13ea3c76c87bf44660529d41d5cc61da4acc4bc01cd04908"
EXPECTED_P2_PROTOCOL_SHA256 = "b5a54bca6d9d918bb84934edd7b6512b026a0774c2abd001b2575698d459d7ab"
EXPECTED_P2_MANIFEST_SHA256 = "906bbad55c632a03d06e76191c91d39176915eb3e7a1e0d09d114cbeb7897036"
EXPECTED_P2_MATRIX_SHA256 = "cf993514a8db0155a06a542617d504e6ba68523f4fa1ea0579b86a929f1753aa"
EXPECTED_P2_LEVELS_SHA256 = "51eed81cfb83b3c353b336238601f09db8304bde9efeb404072332102c6e3e67"

EXPECTED_MEMBERSHIP_ROWS = 5418
EXPECTED_UNIVERSES = {"C2", "D2", "E2"}
EXPECTED_DECISIONS_PER_UNIVERSE = 301
EXPECTED_MEMBERS_PER_DECISION = 6

P2_PATHS = {
    "report": ("data/research/rd19_p2_runtime/rd19-p2-discovery-freeze-report-v1.json"),
    "protocol": ("data/research/rd19_p2_runtime/rd19-p2-discovery-protocol-v1.json"),
    "manifest": "data/research/rd19_p2_runtime/output-manifest.json",
    "matrix": "data/research/rd19_p2_runtime/variant-matrix.csv",
    "levels": "data/research/rd19_p2_runtime/parameter-levels.csv",
}


class P2ARunnerError(RuntimeError):
    pass


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description=(
            "Implement and technically dry-run the frozen RD19-P2 engine "
            "without executing the historical discovery matrix."
        )
    )
    result.add_argument("--repo-root", type=Path, default=ROOT)
    result.add_argument(
        "--membership",
        type=Path,
        default=(ROOT / "data/research/rd18_p3x_a3b_runtime/effective-operational-membership.csv"),
    )
    result.add_argument(
        "--raw-root",
        type=Path,
        default=ROOT / "data/raw/rd16b/kucoin",
    )
    result.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "data/research/rd19_p2a_runtime",
    )
    result.add_argument("--preflight-only", action="store_true")
    result.add_argument("--publish", action="store_true")
    return result


def _write_json(path: Path, value: object) -> None:
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


def _write_csv(path: Path, rows: list[dict[str, object]]) -> int:
    if not rows:
        raise P2ARunnerError(f"cannot write an empty CSV: {path}")
    fields = tuple(rows[0].keys())
    for row in rows:
        if tuple(row.keys()) != fields:
            raise P2ARunnerError(f"CSV field drift in {path.name}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fields,
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def _verify_hash(path: Path, expected: str, *, label: str) -> None:
    if not path.is_file():
        raise P2ARunnerError(f"{label} missing: {path}")
    actual = sha256(path)
    if actual != expected:
        raise P2ARunnerError(f"{label} hash drift: expected={expected}, actual={actual}")


def verify_p2(repo: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    report_path = repo / P2_PATHS["report"]
    protocol_path = repo / P2_PATHS["protocol"]
    manifest_path = repo / P2_PATHS["manifest"]
    matrix_path = repo / P2_PATHS["matrix"]
    levels_path = repo / P2_PATHS["levels"]

    _verify_hash(report_path, EXPECTED_P2_REPORT_SHA256, label="P2 report")
    _verify_hash(protocol_path, EXPECTED_P2_PROTOCOL_SHA256, label="P2 protocol")
    _verify_hash(manifest_path, EXPECTED_P2_MANIFEST_SHA256, label="P2 manifest")
    _verify_hash(matrix_path, EXPECTED_P2_MATRIX_SHA256, label="P2 matrix")
    _verify_hash(levels_path, EXPECTED_P2_LEVELS_SHA256, label="P2 levels")

    report = load_json_object(report_path)
    protocol = load_json_object(protocol_path)
    expected_report = {
        "passed": True,
        "decision": "RD19_P2_DISCOVERY_PROTOCOL_AND_MATRIX_FROZEN",
        "selected_candidate_id": CANDIDATE_ID,
        "design_type": "PLACKETT_BURMAN_12_RUN_MAIN_EFFECT_SCREEN",
        "variant_count": 12,
        "matrix_frozen": True,
        "parameters_frozen_for_p2": True,
        "p2_execution_authorized_now": False,
        "implementation_and_dry_run_authorized": True,
        "candidate_backtest_executed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
        "next_stage": ("RD19_P2A_DISCOVERY_ENGINE_IMPLEMENTATION_AND_TECHNICAL_DRY_RUN"),
    }
    drift = {
        key: {"expected": wanted, "actual": report.get(key)}
        for key, wanted in expected_report.items()
        if report.get(key) != wanted
    }
    if drift:
        raise P2ARunnerError(f"P2 report semantic drift: {drift}")

    expected_protocol = {
        "candidate_id": CANDIDATE_ID,
        "variant_count": 12,
        "matrix_frozen": True,
        "parameters_frozen_for_p2": True,
        "p2_execution_authorized_now": False,
        "implementation_and_dry_run_authorized": True,
        "post_2024_holdout_status": "SEALED",
        "candidate_backtest_executed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
    }
    protocol_drift = {
        key: {"expected": wanted, "actual": protocol.get(key)}
        for key, wanted in expected_protocol.items()
        if protocol.get(key) != wanted
    }
    if protocol_drift:
        raise P2ARunnerError(f"P2 protocol semantic drift: {protocol_drift}")
    return report, protocol


def _normalize_membership(path: Path) -> pd.DataFrame:
    if not path.is_file():
        raise P2ARunnerError(f"membership missing: {path}")
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
        raise P2ARunnerError(f"membership columns missing: {missing}")
    if len(frame) != EXPECTED_MEMBERSHIP_ROWS:
        raise P2ARunnerError(f"membership row count drift: {len(frame)}")
    result = frame.copy()
    result["universe_id"] = result["universe_id"].astype(str)
    result["effective_pair"] = result["effective_pair"].astype(str)
    result["decision_time"] = pd.to_datetime(
        result["decision_time"],
        utc=True,
        errors="raise",
    )
    result["effective_end"] = pd.to_datetime(
        result["effective_end"],
        utc=True,
        errors="raise",
    )
    result["effective_rank"] = pd.to_numeric(
        result["effective_rank"],
        errors="raise",
    ).astype(int)
    if set(result["universe_id"].unique()) != EXPECTED_UNIVERSES:
        raise P2ARunnerError("membership universe set drifted")
    if bool((result["effective_end"] <= result["decision_time"]).any()):
        raise P2ARunnerError("membership interval is non-positive")
    if bool((result["effective_end"] > SEALED_CUTOFF).any()):
        raise P2ARunnerError("membership crosses the sealed cutoff")
    for universe_id in sorted(EXPECTED_UNIVERSES):
        universe = result.loc[result["universe_id"] == universe_id]
        if universe["decision_time"].nunique() != EXPECTED_DECISIONS_PER_UNIVERSE:
            raise P2ARunnerError(f"{universe_id} decision count drifted")
        sizes = universe.groupby("decision_time", sort=True).size()
        if not bool((sizes == EXPECTED_MEMBERS_PER_DECISION).all()):
            raise P2ARunnerError(f"{universe_id} membership width drifted")
    return result.sort_values(
        ["universe_id", "decision_time", "effective_rank", "effective_pair"],
        kind="stable",
    ).reset_index(drop=True)


def _metadata_path(raw_root: Path, pair: str) -> Path:
    return raw_root / pair / "1h.metadata.json"


def _parquet_path(raw_root: Path, pair: str) -> Path:
    return raw_root / pair / "1h.parquet"


def real_source_preflight(
    membership: pd.DataFrame,
    *,
    raw_root: Path,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for pair in sorted(membership["effective_pair"].unique()):
        metadata_path = _metadata_path(raw_root, pair)
        data_path = _parquet_path(raw_root, pair)
        if not metadata_path.is_file():
            raise P2ARunnerError(f"sealed metadata missing for {pair}: {metadata_path}")
        if not data_path.is_file():
            raise P2ARunnerError(f"sealed parquet missing for {pair}: {data_path}")
        metadata = load_json_object(metadata_path)
        expected_hash = metadata.get("sha256")
        if not isinstance(expected_hash, str) or len(expected_hash) != 64:
            raise P2ARunnerError(f"sealed metadata SHA invalid for {pair}")
        if metadata.get("exchange_id") != "kucoin":
            raise P2ARunnerError(f"sealed exchange identity drift for {pair}")
        if metadata.get("timeframe") != "1h":
            raise P2ARunnerError(f"sealed timeframe identity drift for {pair}")
        rows.append(
            {
                "pair": pair,
                "symbol": str(metadata.get("symbol")),
                "rows": int(metadata.get("rows", 0)),
                "first_timestamp": str(metadata.get("first_timestamp")),
                "last_timestamp": str(metadata.get("last_timestamp")),
                "parquet_bytes": data_path.stat().st_size,
                "metadata_sha256": sha256(metadata_path),
                "declared_parquet_sha256": expected_hash,
                "data_exists": True,
                "metadata_exists": True,
            }
        )
    if not rows:
        raise P2ARunnerError("membership produced no real source rows")
    return rows


def _sample_pairs(source_rows: list[dict[str, object]]) -> list[str]:
    available = {str(row["pair"]) for row in source_rows}
    preferred = [
        "BTC-USDT",
        "ETH-USDT",
        "SOL-USDT",
        "LINK-USDT",
        "AVAX-USDT",
        "ADA-USDT",
    ]
    selected = [pair for pair in preferred if pair in available]
    if len(selected) < 6:
        selected.extend(pair for pair in sorted(available) if pair not in selected)
    return selected[:6]


def feature_integration_preflight(
    source_rows: list[dict[str, object]],
    variants: list[dict[str, object]],
    *,
    raw_root: Path,
) -> list[dict[str, object]]:
    representative: dict[str, dict[str, object]] = {}
    for variant in variants:
        family = str(variant["entry_family"])
        representative.setdefault(family, variant)
    if set(representative) != {
        "CONFIRMED_PULLBACK",
        "VOLATILITY_CONTRACTION_BREAKOUT",
    }:
        raise P2ARunnerError("both entry families were not resolved")

    rows: list[dict[str, object]] = []
    cutoff = SEALED_CUTOFF.to_pydatetime()
    for pair in _sample_pairs(source_rows):
        frame = pd.read_parquet(
            _parquet_path(raw_root, pair),
            engine="pyarrow",
            filters=[("timestamp", "<", cutoff)],
        )
        normalized = normalize_bars(frame.tail(2600))
        if len(normalized) < 2200:
            raise P2ARunnerError(f"insufficient sealed bars for feature preflight: {pair}")
        for family, variant in sorted(representative.items()):
            featured = feature_frame(normalized, variant)
            numeric = featured[
                [
                    "momentum_fast",
                    "momentum_slow",
                    "trend_persistence",
                    "atr",
                    "atr_percent",
                ]
            ].dropna()
            if numeric.empty:
                raise P2ARunnerError(f"feature preflight produced no valid rows: {pair}/{family}")
            maximum_timestamp = pd.Timestamp(featured["timestamp"].max())
            if maximum_timestamp >= SEALED_CUTOFF:
                raise P2ARunnerError(f"post-2024 row entered feature memory: {pair}")
            rows.append(
                {
                    "pair": pair,
                    "entry_family": family,
                    "variant_id": str(variant["variant_id"]),
                    "source_rows_loaded": len(normalized),
                    "valid_feature_rows": len(numeric),
                    "maximum_timestamp": maximum_timestamp.isoformat(),
                    "post_2024_accessed": False,
                }
            )
    return rows


def variant_contract_rows(
    variants: list[dict[str, object]],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for variant in variants:
        rows.append(
            {
                "variant_id": str(variant["variant_id"]),
                "entry_family": str(variant["entry_family"]),
                "top_k": int(variant["top_k"]),
                "maximum_positions": int(variant["maximum_positions"]),
                "momentum_fast_bars": int(variant["momentum_fast_bars"]),
                "momentum_slow_bars": int(variant["momentum_slow_bars"]),
                "trail_activation_r": float(variant["trail_activation_r"]),
                "trail_atr": float(variant["trail_atr"]),
                "market_gate": str(variant["market_gate_strictness_level_id"]),
                "cost_hurdle": str(variant["cost_hurdle_level_level_id"]),
                "cost_hurdle_ratio": float(variant["minimum_atr_to_effective_round_trip_cost"]),
                "parameters_frozen": True,
            }
        )
    return rows


def fixture_dry_run(
    variants: list[dict[str, object]],
) -> tuple[list[dict[str, object]], pd.DataFrame, pd.DataFrame]:
    summary_rows: list[dict[str, object]] = []
    candidate_frames: list[pd.DataFrame] = []
    trade_frames: list[pd.DataFrame] = []

    for variant in variants:
        for cost_multiplier in (1.0, 2.0):
            candidates, trades = dry_run_variant(
                variant,
                cost_multiplier=cost_multiplier,
            )
            candidates = candidates.copy()
            candidates["cost_multiplier"] = cost_multiplier
            candidate_frames.append(candidates)
            trade_frames.append(trades)

            entry_times = pd.to_datetime(
                trades["entry_time"],
                utc=True,
                errors="raise",
            )
            signal_times = pd.to_datetime(
                trades["signal_time"],
                utc=True,
                errors="raise",
            )
            next_bar = bool((entry_times - signal_times == pd.Timedelta(hours=1)).all())
            summary_rows.append(
                {
                    "variant_id": str(variant["variant_id"]),
                    "entry_family": str(variant["entry_family"]),
                    "cost_multiplier": cost_multiplier,
                    "candidate_rows": len(candidates),
                    "trade_rows": len(trades),
                    "minimum_cash": float(
                        pd.to_numeric(
                            trades["minimum_cash"],
                            errors="raise",
                        ).min()
                    ),
                    "maximum_positions_contract": int(variant["maximum_positions"]),
                    "next_bar_execution": next_bar,
                    "spot_only": set(trades["instrument_type"].astype(str)) == {"SPOT"},
                    "long_only": set(trades["side"].astype(str)) == {"LONG"},
                    "post_2024_accessed": False,
                    "performance_gate_evaluated": False,
                }
            )

    return (
        summary_rows,
        pd.concat(candidate_frames, ignore_index=True),
        pd.concat(trade_frames, ignore_index=True),
    )


def technical_checks(
    *,
    variants: list[dict[str, object]],
    source_rows: list[dict[str, object]],
    feature_rows: list[dict[str, object]],
    fixture_rows: list[dict[str, object]],
    fixture_candidates: pd.DataFrame,
    fixture_trades: pd.DataFrame,
) -> list[dict[str, object]]:
    fixture = pd.DataFrame.from_records(fixture_rows)
    checks = {
        "variant_count_is_12": len(variants) == 12,
        "variant_ids_unique": (len({str(row["variant_id"]) for row in variants}) == 12),
        "both_entry_families_exercised": (
            set(fixture["entry_family"].astype(str))
            == {
                "CONFIRMED_PULLBACK",
                "VOLATILITY_CONTRACTION_BREAKOUT",
            }
        ),
        "both_cost_multipliers_exercised": (
            set(pd.to_numeric(fixture["cost_multiplier"])) == {1.0, 2.0}
        ),
        "all_fixture_variants_nonempty": bool(
            (pd.to_numeric(fixture["candidate_rows"]) > 0).all()
            and (pd.to_numeric(fixture["trade_rows"]) > 0).all()
        ),
        "fixture_next_bar_execution": bool(fixture["next_bar_execution"].astype(bool).all()),
        "fixture_cash_nonnegative": bool((pd.to_numeric(fixture["minimum_cash"]) >= 0.0).all()),
        "fixture_spot_only": bool(fixture["spot_only"].astype(bool).all()),
        "fixture_long_only": bool(fixture["long_only"].astype(bool).all()),
        "fixture_candidate_ids_present": bool(
            fixture_candidates["variant_id"].astype(str).str.strip().ne("").all()
        ),
        "fixture_trade_ids_present": bool(
            fixture_trades["variant_id"].astype(str).str.strip().ne("").all()
        ),
        "real_sources_nonempty": len(source_rows) > 0,
        "real_feature_preflight_complete": len(feature_rows) == 12,
        "real_feature_preflight_before_cutoff": all(
            pd.Timestamp(cast(str, row["maximum_timestamp"])) < SEALED_CUTOFF
            for row in feature_rows
        ),
        "post_2024_access_absent": all(
            row["post_2024_accessed"] is False for row in [*feature_rows, *fixture_rows]
        ),
        "real_historical_strategy_replay_absent": True,
        "real_historical_exit_simulation_absent": True,
        "performance_reporting_absent": True,
        "production_authorization_absent": True,
    }
    return [
        {
            "check_id": key,
            "passed": bool(value),
            "blocking": True,
        }
        for key, value in sorted(checks.items())
    ]


def output_manifest(
    output_dir: Path,
    rows_by_file: dict[str, int | None],
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
        json.dumps(
            files,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    return {
        "schema_version": "rd19-p2a-output-manifest-v1",
        "stage": STAGE,
        "deterministic_hash": deterministic,
        "files": files,
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


def publication(report: dict[str, object]) -> str:
    return "\n".join(
        [
            "# RD19-P2A Engine Technical Dry Run",
            "",
            f"- Decision: `{report['decision']}`",
            f"- Candidate: `{report['selected_candidate_id']}`",
            f"- Variants implemented: **{report['variant_count']}**",
            "- Synthetic contract fixture: **PASS**",
            "- Real sealed feature integration: **PASS**",
            "- Historical discovery replay: **Not executed**",
            "- Historical performance metrics: **Not calculated**",
            "- Post-2024 access: **No**",
            "",
            "The frozen twelve-variant engine now has causal feature, "
            "cross-sectional ranking, market-gate, entry-family, cost-hurdle, "
            "cash-sizing and convex-exit implementations. P2A exercised the "
            "contracts on deterministic synthetic fixtures and verified "
            "integration with sealed real candle sources without running the "
            "2019-2023 discovery matrix.",
            "",
            f"Next stage: `{report['next_stage']}`",
            "",
        ]
    )


def main() -> int:
    args = parser().parse_args()
    repo = args.repo_root.resolve()
    output = args.output_dir.resolve()

    p2_report, p2_protocol = verify_p2(repo)
    variants = resolve_variants(p2_protocol)
    membership = _normalize_membership(args.membership.resolve())
    source_rows = real_source_preflight(
        membership,
        raw_root=args.raw_root.resolve(),
    )
    feature_rows = feature_integration_preflight(
        source_rows,
        variants,
        raw_root=args.raw_root.resolve(),
    )
    fixture_rows, fixture_candidates, fixture_trades = fixture_dry_run(variants)
    checks = technical_checks(
        variants=variants,
        source_rows=source_rows,
        feature_rows=feature_rows,
        fixture_rows=fixture_rows,
        fixture_candidates=fixture_candidates,
        fixture_trades=fixture_trades,
    )
    failed = [str(row["check_id"]) for row in checks if row["passed"] is not True]
    if failed:
        raise P2ARunnerError(f"P2A technical checks failed: {failed}")

    if args.preflight_only:
        print(
            json.dumps(
                {
                    "status": "PASS",
                    "decision": DECISION,
                    "selected_candidate_id": CANDIDATE_ID,
                    "variant_count": len(variants),
                    "real_source_count": len(source_rows),
                    "fixture_run_count": len(fixture_rows),
                    "next_stage": NEXT_STAGE,
                    "post_2024_accessed": False,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    if not args.publish:
        raise P2ARunnerError("use --publish or --preflight-only")

    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True, exist_ok=False)

    rows_by_file: dict[str, int | None] = {}
    contract = {
        "schema_version": SCHEMA_VERSION,
        "stage": STAGE,
        "candidate_id": CANDIDATE_ID,
        "p2_matrix_hash": p2_protocol["matrix_deterministic_hash"],
        "variant_count": len(variants),
        "implementation_scope": [
            "causal hourly feature calculation",
            "cross-sectional percentile ranking",
            "market trend and breadth gate",
            "confirmed pullback entry",
            "volatility contraction breakout entry",
            "pre-entry transaction cost hurdle",
            "next-bar spot execution",
            "cash-constrained risk sizing",
            "immutable initial protective stop",
            "structural ATR trailing exit",
            "maximum holding safeguard",
        ],
        "historical_discovery_execution": False,
        "performance_gate_evaluation": False,
        "post_2024_access": False,
        "production_authorized": False,
    }
    _write_json(output / "implementation-contract.json", contract)
    rows_by_file["implementation-contract.json"] = None
    rows_by_file["variant-contract-ledger.csv"] = _write_csv(
        output / "variant-contract-ledger.csv",
        variant_contract_rows(variants),
    )
    rows_by_file["real-source-preflight.csv"] = _write_csv(
        output / "real-source-preflight.csv",
        source_rows,
    )
    rows_by_file["feature-integration-preflight.csv"] = _write_csv(
        output / "feature-integration-preflight.csv",
        feature_rows,
    )
    rows_by_file["fixture-dry-run-summary.csv"] = _write_csv(
        output / "fixture-dry-run-summary.csv",
        fixture_rows,
    )
    fixture_candidates.to_parquet(
        output / "fixture-candidates.parquet",
        index=False,
        engine="pyarrow",
    )
    rows_by_file["fixture-candidates.parquet"] = len(fixture_candidates)
    fixture_trades.to_parquet(
        output / "fixture-trades.parquet",
        index=False,
        engine="pyarrow",
    )
    rows_by_file["fixture-trades.parquet"] = len(fixture_trades)
    rows_by_file["technical-checks.csv"] = _write_csv(
        output / "technical-checks.csv",
        checks,
    )

    report: dict[str, object] = {
        "schema_version": "rd19-p2a-technical-dry-run-report-v1",
        "stage": STAGE,
        "decision": DECISION,
        "passed": True,
        "parent_commit": EXPECTED_PARENT,
        "upstream_decision": p2_report["decision"],
        "selected_candidate_id": CANDIDATE_ID,
        "variant_count": len(variants),
        "real_source_count": len(source_rows),
        "real_feature_preflight_rows": len(feature_rows),
        "fixture_run_count": len(fixture_rows),
        "fixture_candidate_rows": len(fixture_candidates),
        "fixture_trade_rows": len(fixture_trades),
        "technical_check_count": len(checks),
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
        "holdout_2025_accessed": False,
        "holdout_2026_accessed": False,
        "network_requests": 0,
        "production_authorized": False,
        "next_stage": NEXT_STAGE,
        "recommended_action": (
            "REVIEW_P2A_TECHNICAL_EVIDENCE_AND_AUTHORIZE_OR_BLOCK_HISTORICAL_DISCOVERY_EXECUTION"
        ),
        "input_hashes": {key: sha256(repo / relative) for key, relative in P2_PATHS.items()},
    }
    _write_json(
        output / "rd19-p2a-technical-dry-run-report-v1.json",
        report,
    )
    rows_by_file["rd19-p2a-technical-dry-run-report-v1.json"] = None
    (output / "rd19-p2a-technical-dry-run-v1.md").write_text(
        publication(report),
        encoding="utf-8",
        newline="\n",
    )
    rows_by_file["rd19-p2a-technical-dry-run-v1.md"] = None

    manifest = output_manifest(output, rows_by_file)
    _write_json(output / "output-manifest.json", manifest)

    print(
        json.dumps(
            {
                "status": "PASS",
                "decision": DECISION,
                "selected_candidate_id": CANDIDATE_ID,
                "variant_count": len(variants),
                "real_source_count": len(source_rows),
                "fixture_run_count": len(fixture_rows),
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
