from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import shutil
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from spotbot.data.store import ParquetCandleStore  # noqa: E402
from spotbot.research.rd16l_architecture import (  # noqa: E402
    engine_cooldowns_respected,
    same_symbol_overlap_absent,
)
from spotbot.research.rd18_p3e_replay import (  # noqa: E402
    ARCHITECTURE_ID,
    PRIMARY_START,
    SEALED_CUTOFF,
    UNIVERSE_IDS,
    ReplayLedgers,
    build_v3_replay_ledgers,
    normalize_hourly_bars,
    select_universe_candidates,
    validate_effective_membership,
)

EXPECTED_BUILD_REPORT_SHA256 = "40c3ebcbd0817542d93ce4be148f377e516d755118101e0200d718d44bca7ef8"
EXPECTED_BUILD_MANIFEST_SHA256 = "ac07d150d241dea5efb1aa888522bdaeacc295dfd3f9b27dd1492d0f4b49b959"
MAXIMUM_POSITIONS = 5
MAXIMUM_OPEN_RISK_FRACTION = 0.0225
NORMAL_HOLDING_BARS = 48
STRONG_BULL_HOLDING_BARS = 96


class DryRunError(RuntimeError):
    pass


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description=(
            "Execute full C2/D2/E2 technical ledgers without equity curves "
            "or aggregate performance reporting."
        )
    )
    result.add_argument("--repo-root", type=Path, default=ROOT)
    result.add_argument(
        "--a2-runtime",
        type=Path,
        default=ROOT / "data/research/rd18_p3x_a2_runtime",
    )
    result.add_argument(
        "--a3-runtime",
        type=Path,
        default=ROOT / "data/research/rd18_p3x_a3_runtime",
    )
    result.add_argument(
        "--a3b-runtime",
        type=Path,
        default=ROOT / "data/research/rd18_p3x_a3b_runtime",
    )
    result.add_argument(
        "--build-runtime",
        type=Path,
        default=ROOT / "data/research/rd18_p3e_build_runtime",
    )
    result.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "data/research/rd18_p3e_dry_run_runtime",
    )
    result.add_argument("--preflight-only", action="store_true")
    result.add_argument("--write-ledgers", action="store_true")
    return result


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise DryRunError(f"required JSON missing: {path}")
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise DryRunError(f"JSON object expected: {path}")
    return value


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


def write_csv(
    path: Path,
    rows: list[dict[str, object]],
    fields: tuple[str, ...],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fields,
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def verify_upstream(
    build_runtime: Path,
    a3_runtime: Path,
) -> dict[str, object]:
    report_path = build_runtime / "rd18-p3e-implementation-build-report-v1.json"
    manifest_path = build_runtime / "output-manifest.json"
    if sha256(report_path) != EXPECTED_BUILD_REPORT_SHA256:
        raise DryRunError("implementation build report hash drifted")
    if sha256(manifest_path) != EXPECTED_BUILD_MANIFEST_SHA256:
        raise DryRunError("implementation build manifest hash drifted")

    report = load_json(report_path)
    authorization = load_json(a3_runtime / "authorization-decision.json")
    if not all(
        (
            report.get("passed") is True,
            report.get("decision") == "RD18_P3E_IMPLEMENTATION_BUILD_COMPLETE",
            report.get("next_stage") == "RD18_P3E_TECHNICAL_DRY_RUN",
            authorization.get("authorized") is True,
            authorization.get("technical_valid") is True,
            authorization.get("decision") == "RD18_P3X_A3_REPLAY_AUTHORIZED",
            authorization.get("blockers") == [],
        )
    ):
        raise DryRunError("upstream P3E/A3 authorization drifted")
    return {
        "build_decision": report.get("decision"),
        "build_report_sha256": sha256(report_path),
        "build_manifest_sha256": sha256(manifest_path),
        "a3_decision": authorization.get("decision"),
    }


def _count(values: pd.Series) -> dict[str, int]:
    return dict(sorted(Counter(values.astype(str).tolist()).items()))


def _before_cutoff(frame: pd.DataFrame) -> bool:
    for column in (
        "signal_close",
        "entry_open_time",
        "entry_bar_close",
        "exit_bar_close",
    ):
        if column not in frame.columns or frame.empty:
            continue
        values = pd.to_datetime(frame[column], utc=True, errors="raise")
        if bool((values >= SEALED_CUTOFF).any()):
            return False
    return True


def _after_start(frame: pd.DataFrame) -> bool:
    values = pd.to_datetime(
        frame["signal_close"],
        utc=True,
        errors="raise",
    )
    return bool((values >= PRIMARY_START).all())


def _positive_finite(
    frame: pd.DataFrame,
    columns: tuple[str, ...],
) -> bool:
    if frame.empty:
        return False
    for column in columns:
        values = pd.to_numeric(frame[column], errors="raise")
        if bool((values <= 0.0).any()):
            return False
        if not all(math.isfinite(float(value)) for value in values):
            return False
    return True


def technical_checks(
    selected: pd.DataFrame,
    ledgers: ReplayLedgers,
) -> dict[str, bool]:
    candidates = ledgers.candidates
    evaluated = ledgers.evaluated
    trades = ledgers.trades
    candidate_ids = candidates["source_v2_candidate_id"].astype(str)
    evaluated_ids = evaluated["source_v2_candidate_id"].astype(str)
    trade_ids = trades["source_v2_candidate_id"].astype(str)
    admitted = evaluated.loc[evaluated["router_decision"].astype(str) == "ADMITTED"]
    bars = pd.to_numeric(trades["bars_held"], errors="raise")
    strong = trades["market_regime"].astype(str) == "STRONG_BULL"

    return dict(
        sorted(
            {
                "source_candidates_nonempty": not selected.empty,
                "candidates_nonempty": not candidates.empty,
                "evaluated_nonempty": not evaluated.empty,
                "trades_nonempty": not trades.empty,
                "architecture_fixed": set(candidates["architecture_id"].astype(str))
                == {ARCHITECTURE_ID},
                "source_start_respected": _after_start(selected),
                "source_cutoff_respected": _before_cutoff(selected),
                "candidate_cutoff_respected": _before_cutoff(candidates),
                "evaluated_cutoff_respected": _before_cutoff(evaluated),
                "trade_cutoff_respected": _before_cutoff(trades),
                "candidate_ids_unique": not bool(candidate_ids.duplicated().any()),
                "evaluated_ids_unique": not bool(evaluated_ids.duplicated().any()),
                "trade_ids_unique": not bool(trade_ids.duplicated().any()),
                "candidate_evaluated_identity_parity": set(candidate_ids) == set(evaluated_ids),
                "trade_identity_subset": set(trade_ids).issubset(set(candidate_ids)),
                "admitted_trade_count_parity": len(admitted) == len(trades),
                "admitted_trade_identity_parity": set(
                    admitted["source_v2_candidate_id"].astype(str)
                )
                == set(trade_ids),
                "same_symbol_overlap_absent": same_symbol_overlap_absent(trades),
                "engine_cooldowns_respected": engine_cooldowns_respected(trades),
                "holding_policy_respected": bool(
                    (bars > 0).all()
                    and (bars[strong] <= STRONG_BULL_HOLDING_BARS).all()
                    and (bars[~strong] <= NORMAL_HOLDING_BARS).all()
                ),
                "maximum_positions_respected": (
                    ledgers.maximum_positions_observed <= MAXIMUM_POSITIONS
                ),
                "maximum_open_risk_respected": (
                    ledgers.maximum_open_risk_fraction_observed
                    <= MAXIMUM_OPEN_RISK_FRACTION + 1e-12
                ),
                "spot_only": set(trades["instrument_type"].astype(str)) == {"SPOT"},
                "long_only": set(trades["side"].astype(str)) == {"LONG"},
                "positive_trade_size": _positive_finite(
                    trades,
                    (
                        "entry_price",
                        "exit_price",
                        "risk_per_unit",
                        "risk_budget",
                        "quantity",
                        "notional",
                    ),
                ),
                "router_decisions_present": not bool(
                    evaluated["router_decision"].astype(str).str.strip().eq("").any()
                ),
            }.items()
        )
    )


def universe_summary(
    universe_id: str,
    selected: pd.DataFrame,
    ledgers: ReplayLedgers,
) -> dict[str, object]:
    checks = technical_checks(selected, ledgers)
    failed = sorted(key for key, value in checks.items() if not value)
    if failed:
        raise DryRunError(f"{universe_id} technical checks failed: {failed}")
    signals = pd.to_datetime(
        selected["signal_close"],
        utc=True,
        errors="raise",
    )
    trades = ledgers.trades
    return {
        "schema_version": "rd18-p3e-technical-universe-summary-v1",
        "universe_id": universe_id,
        "source_candidate_rows": len(selected),
        "source_pair_count": selected["pair"].astype(str).nunique(),
        "source_symbol_count": selected["symbol"].astype(str).nunique(),
        "source_signal_start": signals.min().isoformat(),
        "source_signal_end": signals.max().isoformat(),
        "candidate_rows": len(ledgers.candidates),
        "evaluated_rows": len(ledgers.evaluated),
        "trade_rows": len(trades),
        "router_decision_counts": _count(ledgers.evaluated["router_decision"]),
        "engine_candidate_counts": _count(ledgers.candidates["engine_id"]),
        "engine_trade_counts": _count(trades["engine_id"]),
        "exit_reason_counts": _count(trades["exit_reason"]),
        "market_regime_trade_counts": _count(trades["market_regime"]),
        "maximum_positions_observed": ledgers.maximum_positions_observed,
        "maximum_open_risk_fraction_observed": (ledgers.maximum_open_risk_fraction_observed),
        "strong_bull_extension_observed": bool(
            (
                (trades["market_regime"].astype(str) == "STRONG_BULL")
                & (
                    pd.to_numeric(
                        trades["bars_held"],
                        errors="raise",
                    )
                    > NORMAL_HOLDING_BARS
                )
            ).any()
        ),
        "checks": checks,
        "performance_metrics_reported": False,
        "equity_curve_built": False,
        "portfolio_return_calculation_executed": False,
    }


def select_universes(
    a2_runtime: Path,
    membership: pd.DataFrame,
) -> dict[str, pd.DataFrame]:
    result: dict[str, pd.DataFrame] = {}
    for universe_id in UNIVERSE_IDS:
        frame = select_universe_candidates(
            a2_runtime,
            membership,
            universe_id=universe_id,
        )
        result[universe_id] = frame
        print(
            f"P3E_DRY_RUN_SELECTED={universe_id}:{len(frame)}:{frame['symbol'].nunique()}",
            flush=True,
        )
    return result


def load_hourly(
    repo: Path,
    selected: dict[str, pd.DataFrame],
) -> dict[str, pd.DataFrame]:
    symbols = sorted(
        {
            str(symbol)
            for frame in selected.values()
            for symbol in frame["symbol"].astype(str).unique()
        }
    )
    store = ParquetCandleStore(repo / "data/raw/rd16b")
    frames: dict[str, pd.DataFrame] = {}
    cutoff = SEALED_CUTOFF.to_pydatetime()

    for index, symbol in enumerate(symbols, start=1):
        data_path = store.dataset_path(
            exchange_id="kucoin",
            symbol=symbol,
            timeframe="1h",
        )
        metadata_path = store.metadata_path(data_path)
        if not data_path.is_file():
            raise DryRunError(f"sealed 1h source missing: {data_path}")
        if not metadata_path.is_file():
            raise DryRunError(f"sealed 1h metadata missing: {metadata_path}")

        metadata = load_json(metadata_path)
        expected_hash = metadata.get("sha256")
        if not isinstance(expected_hash, str):
            raise DryRunError(f"sealed 1h metadata SHA missing: {symbol}")
        actual_hash = sha256(data_path)
        if actual_hash != expected_hash:
            raise DryRunError(f"sealed 1h source hash mismatch: {symbol}")
        if not all(
            (
                metadata.get("exchange_id") == "kucoin",
                metadata.get("symbol") == symbol,
                metadata.get("timeframe") == "1h",
            )
        ):
            raise DryRunError(f"sealed 1h metadata identity drift: {symbol}")

        frame = pd.read_parquet(
            str(data_path),
            engine="pyarrow",
            filters=[("timestamp", "<", cutoff)],
        )
        normalized = normalize_hourly_bars(frame)
        if normalized.empty:
            raise DryRunError(f"sealed 1h filtered source is empty: {symbol}")
        timestamps = pd.to_datetime(
            normalized["timestamp"],
            utc=True,
            errors="raise",
        )
        if bool((timestamps >= SEALED_CUTOFF).any()):
            raise DryRunError(f"post-2024 row entered memory: {symbol}")

        frames[symbol] = normalized
        print(
            "P3E_DRY_RUN_BAR_LOAD="
            f"{index}/{len(symbols)}:{symbol}:"
            f"{len(normalized)}:"
            f"{timestamps.iloc[0].isoformat()}:"
            f"{timestamps.iloc[-1].isoformat()}",
            flush=True,
        )
    return frames


def output_manifest(root: Path) -> dict[str, object]:
    rows: list[dict[str, object]] = []
    aggregate = hashlib.sha256()
    for path in sorted(
        item for item in root.rglob("*") if item.is_file() and item.name != "output-manifest.json"
    ):
        relative = path.relative_to(root).as_posix()
        digest = sha256(path)
        rows.append(
            {
                "path": relative,
                "bytes": path.stat().st_size,
                "sha256": digest,
            }
        )
        aggregate.update(relative.encode("utf-8"))
        aggregate.update(b"\0")
        aggregate.update(digest.encode("ascii"))
        aggregate.update(b"\n")
    return {
        "schema_version": "rd18-p3e-technical-dry-run-manifest-v1",
        "files": rows,
        "deterministic_hash": aggregate.hexdigest(),
        "network_requests": 0,
        "strategy_replay_executed": True,
        "portfolio_routing_executed": True,
        "exit_simulation_executed": True,
        "per_trade_pnl_fields_materialized": True,
        "portfolio_return_calculation_executed": False,
        "performance_reporting_executed": False,
        "cost_stress_executed": False,
        "loyo_executed": False,
        "loao_executed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
    }


def materialize(
    output: Path,
    selected: dict[str, pd.DataFrame],
    hourly: dict[str, pd.DataFrame],
    upstream: dict[str, object],
) -> dict[str, object]:
    temporary = output.with_name(f".{output.name}.tmp-{os.getpid()}")
    if temporary.exists():
        shutil.rmtree(temporary)
    temporary.mkdir(parents=True)
    index_rows: list[dict[str, object]] = []
    summaries: list[dict[str, object]] = []
    try:
        for universe_id in UNIVERSE_IDS:
            print(
                f"P3E_DRY_RUN_REPLAY_START={universe_id}:{len(selected[universe_id])}",
                flush=True,
            )
            ledgers = build_v3_replay_ledgers(
                selected[universe_id],
                hourly_frames=hourly,
            )
            summary = universe_summary(
                universe_id,
                selected[universe_id],
                ledgers,
            )
            root = temporary / "universes" / universe_id
            root.mkdir(parents=True)
            frames = {
                "source-candidates.parquet": selected[universe_id],
                "v3-candidates.parquet": ledgers.candidates,
                "v3-evaluated.parquet": ledgers.evaluated,
                "v3-trades.parquet": ledgers.trades,
            }
            for name, frame in frames.items():
                path = root / name
                frame.to_parquet(
                    path,
                    index=False,
                    compression="zstd",
                )
                index_rows.append(
                    {
                        "universe_id": universe_id,
                        "ledger": name,
                        "rows": len(frame),
                        "bytes": path.stat().st_size,
                        "sha256": sha256(path),
                    }
                )
            write_json(root / "technical-summary.json", summary)
            summaries.append(summary)
            print(
                f"P3E_DRY_RUN_REPLAY_COMPLETE={universe_id}:"
                f"{summary['trade_rows']}:"
                f"{summary['maximum_positions_observed']}:"
                f"{summary['maximum_open_risk_fraction_observed']}",
                flush=True,
            )

        write_csv(
            temporary / "technical-ledger-index.csv",
            index_rows,
            (
                "universe_id",
                "ledger",
                "rows",
                "bytes",
                "sha256",
            ),
        )
        report = {
            "schema_version": "rd18-p3e-technical-dry-run-report-v1",
            "stage": "RD18_P3E_TECHNICAL_DRY_RUN",
            "decision": "RD18_P3E_TECHNICAL_DRY_RUN_COMPLETE",
            "passed": True,
            "upstream": upstream,
            "universes": summaries,
            "universe_count": len(summaries),
            "all_universe_checks_passed": all(
                all(summary["checks"].values()) for summary in summaries
            ),
            "performance_metrics_reported": False,
            "equity_curve_built": False,
            "network_requests": 0,
            "strategy_replay_executed": True,
            "portfolio_routing_executed": True,
            "exit_simulation_executed": True,
            "per_trade_pnl_fields_materialized": True,
            "return_calculation_executed": True,
            "portfolio_return_calculation_executed": False,
            "performance_reporting_executed": False,
            "cost_stress_executed": False,
            "loyo_executed": False,
            "loao_executed": False,
            "post_2024_accessed": False,
            "production_authorized": False,
            "next_stage": ("RD18_P3E_BASE_COST_AND_PERFORMANCE_EVALUATION"),
        }
        write_json(
            temporary / "rd18-p3e-technical-dry-run-report-v1.json",
            report,
        )
        write_json(
            temporary / "output-manifest.json",
            output_manifest(temporary),
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
    if not args.preflight_only and not args.write_ledgers:
        raise SystemExit("use --preflight-only or --write-ledgers")
    upstream = verify_upstream(
        args.build_runtime.resolve(),
        args.a3_runtime.resolve(),
    )
    membership = validate_effective_membership(
        pd.read_csv(args.a3b_runtime.resolve() / "effective-operational-membership.csv")
    )
    selected = select_universes(
        args.a2_runtime.resolve(),
        membership,
    )
    preflight = {
        "schema_version": "rd18-p3e-technical-dry-run-preflight-v1",
        "stage": "RD18_P3E_TECHNICAL_DRY_RUN",
        "passed": True,
        "upstream": upstream,
        "membership_rows": len(membership),
        "selected_candidate_rows": {
            universe_id: len(frame) for universe_id, frame in selected.items()
        },
        "selected_symbol_counts": {
            universe_id: frame["symbol"].nunique() for universe_id, frame in selected.items()
        },
        "network_requests": 0,
        "strategy_replay_executed": False,
        "portfolio_routing_executed": False,
        "exit_simulation_executed": False,
        "return_calculation_executed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
    }
    if args.preflight_only:
        print(json.dumps(preflight, indent=2, sort_keys=True))
        return 0

    hourly = load_hourly(args.repo_root.resolve(), selected)
    report = materialize(
        args.output_dir.resolve(),
        selected,
        hourly,
        upstream,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"P3E_TECHNICAL_DRY_RUN_ERROR={exc}", file=sys.stderr)
        raise SystemExit(2) from exc
