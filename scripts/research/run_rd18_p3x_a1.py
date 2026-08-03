from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from spotbot.research.rd18_p3x_a1 import (  # noqa: E402
    NEXT_ASSET_GATE,
    PLAN_FIELDS,
    STAGE,
    asset_gate_audit,
    build_acquisition_plan,
    decision_for_plan,
    deterministic_manifest,
    iso,
    lineage_hashes,
    load_c2_requirements,
    load_checkpoint,
    load_json,
    load_source_manifest,
    parse_timestamp,
    reconcile_inputs,
    summarize_plan,
    symbol_to_pair,
    write_csv,
    write_json,
)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Run RD18-P3X-A1 planning, acquisition, or six-symbol control parity."
    )
    result.add_argument("--repo-root", type=Path, default=ROOT)
    result.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "data/research/rd18_p3x_a1_runtime",
    )
    result.add_argument("--offline", action="store_true")
    subparsers = result.add_subparsers(dest="mode", required=True)

    plan = subparsers.add_parser("plan")
    plan.add_argument(
        "--probe-current-markets",
        action="store_true",
        help="Query current KuCoin Spot inventory; omitted by default.",
    )

    control = subparsers.add_parser("control")
    control.add_argument(
        "--write-ledgers",
        action="store_true",
        help="Required acknowledgement that local parity parquet outputs will be written.",
    )

    download = subparsers.add_parser("download")
    download.add_argument("--max-pairs", type=int, default=1)
    download.add_argument("--pair", action="append", default=[])
    download.add_argument("--retries", type=int, default=3)
    download.add_argument(
        "--execute-network",
        action="store_true",
        help="Required acknowledgement for public KuCoin network access.",
    )
    return result


def _paths(repo_root: Path, output_dir: Path) -> dict[str, Path]:
    return {
        "coverage": repo_root / "data/research/rd18_p1r2/corrected-daily-coverage-audit.csv",
        "source_manifest": repo_root / "data/research/rd16b/source-manifest-v1.json",
        "checkpoint": output_dir / "acquisition-checkpoint.json",
        "corporate_actions": (
            repo_root / "data/research/rd18_p3x_a1/corporate-action-registry-v1.json"
        ),
        "control_report": output_dir / "control/control-parity-report.json",
    }


def _environment_probe() -> dict[str, object]:
    try:
        import pandas as pd
        import pyarrow

        return {
            "ready": True,
            "pandas_version": pd.__version__,
            "pyarrow_version": pyarrow.__version__,
            "error_type": "",
            "error": "",
        }
    except Exception as exc:  # noqa: BLE001 - environment diagnostic boundary
        return {
            "ready": False,
            "pandas_version": "",
            "pyarrow_version": "",
            "error_type": type(exc).__name__,
            "error": str(exc),
        }


def _load_current_spot_symbols() -> set[str]:
    from spotbot.data.ccxt_adapter import CCXTExchangeAdapter

    adapter = CCXTExchangeAdapter("kucoin")
    markets = adapter.load_markets()
    symbols: set[str] = set()
    for raw_symbol, raw_market in markets.items():
        symbol = str(raw_symbol)
        market = dict(raw_market)
        if not symbol.endswith("/USDT") or ":" in symbol:
            continue
        if market.get("spot") is not True:
            continue
        symbols.add(symbol)
    return symbols


def _control_passed(control_report: Path) -> bool:
    if not control_report.is_file():
        return False
    return load_json(control_report).get("passed") is True


def _write_runtime_bundle(
    output_dir: Path,
    *,
    plan_rows: list[dict[str, object]],
    input_reconciliation: dict[str, object],
    lineage: dict[str, object],
    asset_gate: dict[str, object],
    environment: dict[str, object],
    control_parity_passed: bool,
) -> dict[str, object]:
    summary = summarize_plan(plan_rows)
    decision, next_stage = decision_for_plan(
        input_ready=bool(input_reconciliation["passed"]),
        environment_ready=bool(environment["ready"]),
        control_parity_passed=control_parity_passed,
        all_data_ready=bool(summary["all_ready"]),
        broad_asset_gate_ready=False,
    )
    report = {
        "schema_version": "rd18-p3x-a1-runtime-report-v1",
        "stage": STAGE,
        "decision": decision,
        "next_stage": next_stage,
        "input_reconciliation": input_reconciliation,
        "lineage": lineage,
        "asset_gate": asset_gate,
        "environment": environment,
        "control_parity_passed": control_parity_passed,
        "acquisition": summary,
        "authorizations": {
            "public_kucoin_spot_acquisition": True,
            "six_symbol_control_regeneration": True,
            "broad_c2_candidate_generation": False,
            "three_universe_candidate_dry_run": False,
            "strategy_replay": False,
            "return_calculation": False,
            "production": False,
        },
        "constraints": {
            "spot_only": True,
            "long_only": True,
            "sealed_cutoff": "2025-01-01T00:00:00+00:00",
            "post_2024_access": False,
            "optimization": False,
            "silent_missing_data_as_no_signal": False,
        },
        "broad_generation_block": {
            "decision": "RD18_P3X_A1_ASSET_GATE_GENERALIZATION_REQUIRED",
            "next_stage": NEXT_ASSET_GATE,
            "reason": (
                "RD16E ALLOWED_ASSETS is a pilot-only static gate.  It is preserved "
                "for exact legacy parity but cannot be applied or removed across C2 "
                "without a preregistered causal rule."
            ),
        },
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(output_dir / "full-c2-hourly-acquisition-plan.csv", plan_rows, PLAN_FIELDS)
    write_json(output_dir / "input-reconciliation.json", input_reconciliation)
    write_json(output_dir / "lineage-hashes.json", lineage)
    write_json(output_dir / "asset-gate-audit.json", asset_gate)
    write_json(output_dir / "environment-readiness.json", environment)
    write_json(output_dir / "rd18-p3x-a1-runtime-report-v1.json", report)
    write_json(
        output_dir / "request-manifest.json",
        {
            "schema_version": "rd18-p3x-a1-runtime-request-manifest-v1",
            "network_requests": 0,
            "requests": [],
        },
    )
    names = (
        "asset-gate-audit.json",
        "environment-readiness.json",
        "full-c2-hourly-acquisition-plan.csv",
        "input-reconciliation.json",
        "lineage-hashes.json",
        "rd18-p3x-a1-runtime-report-v1.json",
        "request-manifest.json",
    )
    manifest = deterministic_manifest(output_dir, names)
    write_json(output_dir / "output-manifest.json", manifest)
    return report


def run_plan(
    repo_root: Path,
    output_dir: Path,
    *,
    probe_current_markets: bool,
) -> dict[str, object]:
    paths = _paths(repo_root, output_dir)
    requirements = load_c2_requirements(paths["coverage"])
    sources = load_source_manifest(paths["source_manifest"])
    checkpoint = load_checkpoint(paths["checkpoint"])
    current_symbols = _load_current_spot_symbols() if probe_current_markets else None
    plan_rows = build_acquisition_plan(
        repo_root,
        requirements,
        sources,
        checkpoint,
        current_market_symbols=current_symbols,
    )
    return _write_runtime_bundle(
        output_dir,
        plan_rows=plan_rows,
        input_reconciliation=reconcile_inputs(repo_root),
        lineage=lineage_hashes(repo_root),
        asset_gate=asset_gate_audit(repo_root),
        environment=_environment_probe(),
        control_parity_passed=_control_passed(paths["control_report"]),
    )


def _checkpoint_payload(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {
            "schema_version": "rd18-p3x-a1-acquisition-checkpoint-v1",
            "updated_at": "",
            "pairs": {},
        }
    return load_json(path)


def _update_checkpoint(
    path: Path,
    pair: str,
    *,
    state: str,
    detail: Mapping[str, object],
) -> None:
    payload = _checkpoint_payload(path)
    raw_pairs = payload.setdefault("pairs", {})
    if not isinstance(raw_pairs, dict):
        raise RuntimeError("checkpoint pairs object is invalid")
    raw_pairs[symbol_to_pair(pair)] = {
        "state": state,
        "updated_at": iso(parse_timestamp(detail.get("updated_at"))),
        **{key: value for key, value in detail.items() if key != "updated_at"},
    }
    payload["updated_at"] = iso(parse_timestamp(detail.get("updated_at")))
    write_json(path, payload)


class HistoricalSourceRequiredError(RuntimeError):
    """Raised when current KuCoin history cannot satisfy the frozen start boundary."""


def _load_corporate_action_registry(
    path: Path,
) -> dict[str, dict[str, object]]:
    payload = load_json(path)
    if payload.get("schema_version") != "rd18-p3x-a1-corporate-action-registry-v1":
        raise RuntimeError("unsupported corporate-action registry schema")
    raw_events = payload.get("events")
    if not isinstance(raw_events, dict):
        raise RuntimeError("corporate-action registry events object is invalid")

    events: dict[str, dict[str, object]] = {}
    for raw_pair, raw_event in raw_events.items():
        if not isinstance(raw_event, dict):
            raise RuntimeError(f"invalid corporate-action event: {raw_pair}")
        pair = symbol_to_pair(str(raw_pair))
        events[pair] = dict(raw_event)
    return events


def _matches_registered_corporate_action(
    exc: Exception,
    event: Mapping[str, object],
) -> bool:
    raw_report = event.get("expected_integrity_report")
    if not isinstance(raw_report, dict):
        return False

    message = str(exc)
    observed: dict[str, int] = {}
    for field in ("duplicates", "missing", "invalid"):
        match = re.search(rf"\b{field}=(\d+)\b", message)
        if match is None:
            return False
        observed[field] = int(match.group(1))

    for field, value in observed.items():
        expected = raw_report.get(field)
        if isinstance(expected, bool) or not isinstance(expected, int):
            return False
        if value != expected:
            return False
    return True


DISCOVERY_PAGE_LIMIT = 1_000


def _discover_current_api_first_open(
    adapter: object,
    *,
    symbol: str,
    since: datetime,
    until: datetime,
) -> datetime:
    # Scan contiguous bounded windows; never jump over an unknown interval.
    probe = since
    step = timedelta(hours=DISCOVERY_PAGE_LIMIT)

    while probe < until:
        raw_rows = adapter.fetch_ohlcv(
            symbol,
            "1h",
            since=int(probe.timestamp() * 1_000),
            limit=DISCOVERY_PAGE_LIMIT,
        )
        if raw_rows:
            timestamps: list[float] = []
            for row in raw_rows:
                if not isinstance(row, (list, tuple)) or not row:
                    raise RuntimeError(f"Invalid history discovery row for {symbol}")
                raw_timestamp = row[0]
                if isinstance(raw_timestamp, bool) or not isinstance(
                    raw_timestamp,
                    (int, float),
                ):
                    raise RuntimeError(f"Invalid history discovery timestamp for {symbol}")
                timestamps.append(float(raw_timestamp))

            discovered = datetime.fromtimestamp(
                min(timestamps) / 1_000,
                tz=UTC,
            )
            if discovered < probe:
                raise RuntimeError(f"History discovery moved before its probe for {symbol}")
            if discovered >= until:
                break
            return discovered

        probe += step

    raise HistoricalSourceRequiredError(
        f"{symbol} current API has no hourly history before {until.isoformat()}"
    )


def _now() -> str:
    from datetime import UTC, datetime

    return datetime.now(tz=UTC).isoformat()


def _download_pairs(
    repo_root: Path,
    output_dir: Path,
    *,
    max_pairs: int,
    requested_pairs: list[str],
    retries: int,
) -> dict[str, object]:
    if max_pairs <= 0:
        raise ValueError("--max-pairs must be positive")
    if retries <= 0:
        raise ValueError("--retries must be positive")

    from spotbot.data.ccxt_adapter import CCXTExchangeAdapter
    from spotbot.data.provider import CCXTSpotDataProvider, DataIntegrityError
    from spotbot.data.store import ParquetCandleStore
    from spotbot.research.rd16b_hourly_readiness import (
        _acquire_hourly,
        analyze_hourly_frame,
    )

    paths = _paths(repo_root, output_dir)
    requirements = load_c2_requirements(paths["coverage"])
    sources = load_source_manifest(paths["source_manifest"])
    checkpoint = load_checkpoint(paths["checkpoint"])
    corporate_actions = _load_corporate_action_registry(paths["corporate_actions"])

    adapter = CCXTExchangeAdapter("kucoin")
    current_symbols = _load_current_spot_symbols()
    plan_rows = build_acquisition_plan(
        repo_root,
        requirements,
        sources,
        checkpoint,
        current_market_symbols=current_symbols,
    )
    requested = {symbol_to_pair(value) for value in requested_pairs}
    eligible = [
        row
        for row in plan_rows
        if row["action"] == "DOWNLOAD_OR_BACKFILL_CURRENT_API"
        and (not requested or str(row["pair"]) in requested)
    ][:max_pairs]

    provider = CCXTSpotDataProvider(adapter)
    store = ParquetCandleStore(repo_root / "data/raw/rd16b")
    results: list[dict[str, object]] = []

    for row in eligible:
        pair = str(row["pair"])
        symbol = str(row["symbol"])
        corporate_action = corporate_actions.get(pair)
        _update_checkpoint(
            paths["checkpoint"],
            pair,
            state="IN_PROGRESS",
            detail={"updated_at": _now(), "symbol": symbol},
        )
        last_error = ""
        completed = False
        for attempt in range(1, retries + 1):
            frame = None
            acquisition = None
            try:
                until = parse_timestamp(row["required_until_exclusive"])
                required_since_open = parse_timestamp(row["required_since_open"])
                discovered_first_open = _discover_current_api_first_open(
                    adapter,
                    symbol=symbol,
                    since=required_since_open,
                    until=until,
                )
                frame, acquisition = _acquire_hourly(
                    adapter=adapter,
                    provider=provider,
                    store=store,
                    exchange_id="kucoin",
                    symbol=symbol,
                    since=discovered_first_open,
                    until=until,
                    download=True,
                )
                required_first_close = required_since_open + timedelta(hours=1)
                actual_first_close = parse_timestamp(frame.iloc[0]["timestamp"])
                actual_first_open = actual_first_close - timedelta(hours=1)
                same_applicable_utc_day = actual_first_open.date() == required_since_open.date()
                leading_inactive_hours = max(
                    0,
                    int((actual_first_open - required_since_open).total_seconds() // 3_600),
                )
                if actual_first_close > required_first_close and not same_applicable_utc_day:
                    raise HistoricalSourceRequiredError(
                        f"{symbol} current API history starts at "
                        f"{actual_first_close.isoformat()}, after required "
                        f"{required_first_close.isoformat()}"
                    )
                boundary_status = (
                    "EXACT_HOURLY_START"
                    if actual_first_close <= required_first_close
                    else ("INTRADAY_LISTING_WITHIN_DAILY_APPLICABLE_START")
                )
                analysis = analyze_hourly_frame(
                    symbol=symbol,
                    source=frame,
                    cutoff=until,
                )
                readiness = dict(analysis["readiness"])
                if readiness.get("status") != "PASS":
                    raise RuntimeError(f"hourly causal readiness failed for {symbol}: {readiness}")
                raw_derived = analysis["derived_frames"]
                if not isinstance(raw_derived, dict):
                    raise RuntimeError(f"derived frames are invalid for {symbol}")
                derived_hashes: dict[str, str] = {}
                for timeframe, derived in sorted(raw_derived.items()):
                    stored = store.save(
                        derived,
                        exchange_id="kucoin",
                        symbol=symbol,
                        timeframe=str(timeframe),
                        overwrite=True,
                    )
                    derived_hashes[str(timeframe)] = stored.sha256
                result = {
                    "pair": pair,
                    "symbol": symbol,
                    "state": "COMPLETE",
                    "attempt": attempt,
                    "acquisition_status": acquisition["status"],
                    "boundary_status": boundary_status,
                    "required_since_open": required_since_open.isoformat(),
                    "effective_since_open": actual_first_open.isoformat(),
                    "leading_inactive_hours": leading_inactive_hours,
                    "rows": len(frame),
                    "first_close": str(frame.iloc[0]["timestamp"]),
                    "last_close": str(frame.iloc[-1]["timestamp"]),
                    "sha256": acquisition["sha256"],
                    "logical_path": str(row["logical_path"]),
                    "discovered_first_open": acquisition["discovered_first_open"],
                    "derived_sha256": derived_hashes,
                    "aligned_rows": readiness["aligned_rows"],
                    "updated_at": _now(),
                }
                _update_checkpoint(
                    paths["checkpoint"],
                    pair,
                    state="COMPLETE",
                    detail=result,
                )
                results.append(result)
                completed = True
                break

            except DataIntegrityError as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                if corporate_action is None or not _matches_registered_corporate_action(
                    exc,
                    corporate_action,
                ):
                    if attempt < retries:
                        time.sleep(min(2 ** (attempt - 1), 8))
                    continue

                result = {
                    "pair": pair,
                    "symbol": symbol,
                    "state": "CORPORATE_ACTION_POLICY_REQUIRED",
                    "attempt": attempt,
                    "error": last_error,
                    "event_id": str(corporate_action.get("event_id", "")),
                    "event_type": str(corporate_action.get("event_type", "")),
                    "expected_missing_intervals": int(
                        dict(corporate_action["expected_integrity_report"])["missing"]
                    ),
                    "raw_series_policy": str(corporate_action.get("raw_series_policy", "")),
                    "strategy_use_authorized": False,
                    "normalization_policy_status": "PREREGISTRATION_REQUIRED",
                    "required_next_protocol": str(
                        corporate_action.get("required_next_protocol", "")
                    ),
                    "registry_path": str(paths["corporate_actions"].relative_to(repo_root)),
                    "updated_at": _now(),
                }
                _update_checkpoint(
                    paths["checkpoint"],
                    pair,
                    state="CORPORATE_ACTION_POLICY_REQUIRED",
                    detail=result,
                )
                results.append(result)
                completed = True
                break
            except HistoricalSourceRequiredError as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                result: dict[str, object] = {
                    "pair": pair,
                    "symbol": symbol,
                    "state": "HISTORICAL_SOURCE_REQUIRED",
                    "error": last_error,
                    "boundary_status": ("HISTORICAL_SOURCE_GAP_AFTER_APPLICABLE_DAY"),
                    "required_since_open": str(row["required_since_open"]),
                    "partial_current_api": False,
                    "updated_at": _now(),
                }
                if frame is not None and acquisition is not None:
                    first_close = parse_timestamp(frame.iloc[0]["timestamp"])
                    effective_open = first_close - timedelta(hours=1)
                    required_open = parse_timestamp(row["required_since_open"])
                    result.update(
                        {
                            "partial_current_api": True,
                            "rows": len(frame),
                            "first_close": str(frame.iloc[0]["timestamp"]),
                            "last_close": str(frame.iloc[-1]["timestamp"]),
                            "sha256": acquisition["sha256"],
                            "logical_path": str(row["logical_path"]),
                            "discovered_first_open": acquisition["discovered_first_open"],
                            "effective_since_open": (effective_open.isoformat()),
                            "leading_inactive_hours": max(
                                0,
                                int((effective_open - required_open).total_seconds() // 3_600),
                            ),
                        }
                    )
                _update_checkpoint(
                    paths["checkpoint"],
                    pair,
                    state="HISTORICAL_SOURCE_REQUIRED",
                    detail=result,
                )
                results.append(result)
                completed = True
                break
            except Exception as exc:  # noqa: BLE001 - per-pair acquisition boundary
                last_error = f"{type(exc).__name__}: {exc}"
                if attempt < retries:
                    time.sleep(min(2 ** (attempt - 1), 8))
        if not completed:
            result = {
                "pair": pair,
                "symbol": symbol,
                "state": "FAILED_RETRYABLE",
                "error": last_error,
                "updated_at": _now(),
            }
            _update_checkpoint(
                paths["checkpoint"],
                pair,
                state="FAILED_RETRYABLE",
                detail=result,
            )
            results.append(result)

    return {
        "schema_version": "rd18-p3x-a1-acquisition-batch-v1",
        "selected_pairs": len(eligible),
        "results": results,
        "network_requests": "PUBLIC_KUCOIN_CCXT_ONLY",
        "post_2024_access": False,
    }


def main() -> int:
    args = parser().parse_args()
    repo_root = args.repo_root.resolve()
    output_dir = args.output_dir.resolve()

    if args.mode == "plan":
        if args.probe_current_markets and args.offline:
            raise SystemExit("--offline conflicts with --probe-current-markets")
        report = run_plan(
            repo_root,
            output_dir,
            probe_current_markets=bool(args.probe_current_markets),
        )
    elif args.mode == "control":
        if not args.write_ledgers:
            raise SystemExit("control mode requires --write-ledgers")
        from spotbot.research.rd18_p3x_a1_control import run_control_parity

        report = run_control_parity(repo_root, output_dir / "control")
        run_plan(repo_root, output_dir, probe_current_markets=False)
    elif args.mode == "download":
        if args.offline or not args.execute_network:
            raise SystemExit("download mode requires --execute-network and prohibits --offline")
        try:
            report = _download_pairs(
                repo_root,
                output_dir,
                max_pairs=int(args.max_pairs),
                requested_pairs=list(args.pair),
                retries=int(args.retries),
            )
        except Exception as exc:  # noqa: BLE001 - environment boundary
            environment = _environment_probe()
            if not environment["ready"]:
                report = {
                    "schema_version": "rd18-p3x-a1-acquisition-batch-v1",
                    "decision": "RD18_P3X_A1_ENVIRONMENT_BLOCKED",
                    "environment": environment,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "network_requests": 0,
                }
                write_json(output_dir / "acquisition-environment-block.json", report)
            else:
                raise
        run_plan(repo_root, output_dir, probe_current_markets=False)
    else:
        raise AssertionError(args.mode)

    print(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
