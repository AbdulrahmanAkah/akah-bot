from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import io
import json
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from spotbot.research.rd36_cross_venue_flow_state import (  # noqa: E402
    DATA_CUTOFF,
    DATA_START,
    FAMILY_ORDER,
    HORIZONS,
    PERIODS,
    SYMBOLS,
    UNIVERSES,
    market_state_frame,
    normalize_target_bars,
    qualification_tables,
    state_entry_ledger,
    summarize_markouts,
    target_markout,
    target_open_lookup,
    validate_constants,
)

SCHEMA_VERSION = "rd36-p3-cross-venue-flow-state-diagnostic-runner-v1"

P2_FREEZE_COMMIT = "31f08d7a2bc438f1a420cd9834e451ff90ff8ba6"
P1D_RESULTS_COMMIT = "90a56b8e6babcc0569a7cfc6a479da18a1c323b5"

P2_PROTOCOL = Path(
    "data/research/rd36_p2/"
    "rd36-p2-cross-venue-binance-flow-kucoin-native-"
    "alpha-architecture-preregistration-v1.json"
)
P2_PROTOCOL_SHA256 = "8fe423b7af921d6592fb06c96f77b2905e7c2a78178facc581a13e8075f7f859"
P2_PROTOCOL_BLOB = "d8a19f97413b016e1cb2b610b4fb778393c605dc"

P2_AUDIT = Path("data/research/rd36_p2/rd36-p2-preregistration-audit-v1.json")
P2_AUDIT_SHA256 = "2e17cc9dfa0b95921d8a883ee2a8528d551f35e13d7511e0b537790124489132"
P2_AUDIT_BLOB = "6d4159314282ddbe4a2f5c9be29c7dc2a14dc8fb"

P1_SOURCE_AUDIT = Path("data/research/rd36_p1_runtime/source-file-audit.csv")
P1_SOURCE_AUDIT_SHA256 = "045661c08fcda7270ec762cc093b69f411185e60ba0058e02284b0a7fe2180ce"

RD31_RUNNER = Path("scripts/research/run_rd31_market_regime_admission_governor.py")
RD31_RUNNER_BLOB = "3b5c6916e34be6c9642702fe2807e42e445ee083"

BINANCE_RAW_ROOT = Path("data/raw/rd36/binance_spot_flow")
KUCOIN_RAW_ROOT = Path("data/raw/rd16b/kucoin")
OUTPUT = Path("data/research/rd36_p3_runtime")

OUTPUT_NAMES = (
    "input-and-conformance-audit.json",
    "source-state-ledger.csv",
    "source-state-summary.csv",
    "target-markout-ledger.csv",
    "target-markout-summary.csv",
    "qualification-evaluation.csv",
    "family-qualification.csv",
    "qualified-cross-venue-flow-states-freeze.json",
    "rd36-p3-cross-venue-flow-state-diagnostic-report-v1.json",
)

SUCCESS_DECISION = "RD36_QUALIFIED_CROSS_VENUE_FLOW_STATES_FREEZE_PRE_EXIT_SHADOW_ABLATION"
SUCCESS_NEXT = "RD36_P4_FREEZE_EXIT_BRAIN_SHADOW_ABLATION_WITH_QUALIFIED_FLOW_STATES"
FAILURE_DECISION = "RD36_CROSS_VENUE_FLOW_ALPHA_UNQUALIFIED_NEXT_SOURCE_REQUIRED"
FAILURE_NEXT = "RD37_PREREGISTER_NEXT_ADAPTIVE_EXIT_INFORMATION_SOURCE"


class RunnerError(RuntimeError):
    pass


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser()
    value.add_argument("--repo-root", type=Path, required=True)
    value.add_argument("--execute", action="store_true")
    value.add_argument("--validate-only", action="store_true")
    value.add_argument("--expected-freeze-commit", default=None)
    return value


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode:
        raise RunnerError(f"git {' '.join(args)} failed: {result.stderr}")
    return result.stdout.strip()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise RunnerError(f"JSON object expected: {path}")
    return value


def write_json(path: Path, value: Any) -> None:
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


def verify_source(
    repo: Path,
    relative: Path,
    expected_sha: str,
    expected_blob: str | None,
    label: str,
) -> dict[str, str]:
    path = repo / relative
    if not path.is_file():
        raise RunnerError(f"{label} missing: {relative}")
    actual_sha = sha256(path)
    if actual_sha != expected_sha:
        raise RunnerError(f"{label} SHA drift: {actual_sha} != {expected_sha}")
    result = {"sha256": actual_sha}
    if expected_blob is not None:
        actual_blob = git(
            repo,
            "rev-parse",
            f"HEAD:{relative.as_posix()}",
        )
        if actual_blob != expected_blob:
            raise RunnerError(f"{label} blob drift: {actual_blob} != {expected_blob}")
        result["git_blob"] = actual_blob
    return result


def load_rd31_runner() -> Any:
    path = ROOT / RD31_RUNNER
    spec = importlib.util.spec_from_file_location(
        "_rd31_frozen_membership_for_rd36",
        path,
    )
    if spec is None or spec.loader is None:
        raise RunnerError("cannot load frozen RD31 runner")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def verify_lineage(
    repo: Path,
    expected_freeze_commit: str,
) -> dict[str, Any]:
    if git(repo, "diff", "--cached", "--name-only", "--"):
        raise RunnerError("staged tracked changes exist before RD36-P3 run")
    if git(repo, "diff", "--name-only", "--"):
        raise RunnerError("unstaged tracked changes exist before RD36-P3 run")

    head = git(repo, "rev-parse", "HEAD")
    if head != expected_freeze_commit:
        raise RunnerError(f"RD36-P3 HEAD {head} != freeze {expected_freeze_commit}")
    if git(repo, "rev-parse", "HEAD^") != P2_FREEZE_COMMIT:
        raise RunnerError("RD36-P3 runner-freeze parent is not P2")

    verified = {
        P2_PROTOCOL.as_posix(): verify_source(
            repo,
            P2_PROTOCOL,
            P2_PROTOCOL_SHA256,
            P2_PROTOCOL_BLOB,
            "P2 protocol",
        ),
        P2_AUDIT.as_posix(): verify_source(
            repo,
            P2_AUDIT,
            P2_AUDIT_SHA256,
            P2_AUDIT_BLOB,
            "P2 audit",
        ),
    }
    source_audit_path = repo / P1_SOURCE_AUDIT
    if sha256(source_audit_path) != P1_SOURCE_AUDIT_SHA256:
        raise RunnerError("P1 source audit SHA drifted")

    rd31_blob = git(
        repo,
        "rev-parse",
        f"HEAD:{RD31_RUNNER.as_posix()}",
    )
    if rd31_blob != RD31_RUNNER_BLOB:
        raise RunnerError("RD31 membership runner blob drifted")

    protocol = load_json(repo / P2_PROTOCOL)
    if protocol.get("status") != "FROZEN_PRE_FEATURE_COMPUTATION":
        raise RunnerError("P2 protocol is not frozen")
    if (
        tuple(item["family_id"] for item in protocol.get("frozen_state_families", []))
        != FAMILY_ORDER
    ):
        raise RunnerError("P2 family registry drifted")
    diagnostic = protocol.get("future_diagnostic_design", {})
    if tuple(diagnostic.get("target_horizons_hours", ())) != HORIZONS:
        raise RunnerError("P2 target horizons drifted")
    if tuple(diagnostic.get("universes", ())) != UNIVERSES:
        raise RunnerError("P2 universes drifted")
    if diagnostic.get("source_to_target_minimum_delay_hours") != 1:
        raise RunnerError("P2 cross-venue delay drifted")
    if diagnostic.get("economic_replay") is not False:
        raise RunnerError("P2 unexpectedly permits economic replay")
    if diagnostic.get("2024_access") is not False:
        raise RunnerError("P2 unexpectedly permits 2024 access")

    validate_constants()
    return {
        "runner_freeze_commit": expected_freeze_commit,
        "p2_freeze_commit": P2_FREEZE_COMMIT,
        "p1d_results_commit": P1D_RESULTS_COMMIT,
        "verified_sources": verified,
        "rd31_runner_blob": rd31_blob,
    }


def csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def parse_binance_archive(path: Path) -> pd.DataFrame:
    if not path.is_file():
        raise RunnerError(f"Binance archive missing: {path}")
    with zipfile.ZipFile(path, "r") as archive:
        names = [name for name in archive.namelist() if not name.endswith("/")]
        if len(names) != 1:
            raise RunnerError(f"{path.name}: expected exactly one CSV member")
        raw = archive.read(names[0]).decode("utf-8-sig")

    records: list[dict[str, Any]] = []
    for index, row in enumerate(csv.reader(io.StringIO(raw))):
        if len(row) != 12:
            raise RunnerError(f"{path.name}: row {index} does not have 12 columns")
        try:
            open_time = int(row[0])
        except ValueError:
            if index == 0:
                continue
            raise
        if open_time >= 100_000_000_000_000:
            raise RunnerError(f"{path.name}: unexpected microsecond timestamp")
        records.append(
            {
                "timestamp": pd.to_datetime(open_time, unit="ms", utc=True),
                "quote_volume": float(row[7]),
                "number_of_trades": float(row[8]),
                "taker_buy_quote_volume": float(row[10]),
            }
        )
    return pd.DataFrame.from_records(records)


def load_binance_sources(
    repo: Path,
) -> tuple[dict[str, pd.DataFrame], dict[str, Any]]:
    source_rows = csv_rows(repo / P1_SOURCE_AUDIT)
    frames: dict[str, list[pd.DataFrame]] = {symbol: [] for symbol in SYMBOLS}
    verified_archives = 0

    for symbol in SYMBOLS:
        matches = [
            row
            for row in source_rows
            if row["symbol"] == symbol and row["month"][:4] in {"2022", "2023"}
        ]
        matches = sorted(matches, key=lambda row: row["month"])
        if len(matches) != 24:
            raise RunnerError(f"expected 24 frozen source months for {symbol}")

        for row in matches:
            month = row["month"]
            path = repo / BINANCE_RAW_ROOT / symbol / "1h" / f"{symbol}-1h-{month}.zip"
            actual_sha = sha256(path)
            if actual_sha != row["archive_sha256"]:
                raise RunnerError(
                    f"Binance archive SHA drift {symbol}/{month}: "
                    f"{actual_sha} != {row['archive_sha256']}"
                )
            frame = parse_binance_archive(path)
            if len(frame) != int(row["archive_row_count"]):
                raise RunnerError(f"Binance archive row-count drift {symbol}/{month}")
            frames[symbol].append(frame)
            verified_archives += 1

    combined: dict[str, pd.DataFrame] = {}
    expected = pd.date_range(
        DATA_START,
        DATA_CUTOFF - pd.Timedelta(hours=1),
        freq="h",
        tz="UTC",
    )
    expected_set = set(expected)

    symbol_audit: dict[str, Any] = {}
    for symbol in SYMBOLS:
        frame = (
            pd.concat(frames[symbol], ignore_index=True)
            .sort_values("timestamp", kind="stable")
            .reset_index(drop=True)
        )
        if frame["timestamp"].duplicated().any():
            raise RunnerError(f"duplicate Binance timestamp: {symbol}")
        actual_set = set(pd.to_datetime(frame["timestamp"], utc=True))
        missing = sorted(expected_set - actual_set)
        extra = sorted(actual_set - expected_set)
        if missing != [pd.Timestamp("2023-03-24T13:00:00Z")]:
            raise RunnerError(f"unexpected Binance missing clock {symbol}: {missing}")
        if extra:
            raise RunnerError(f"unexpected Binance out-of-range clocks {symbol}: {extra}")
        if len(frame) != 17519:
            raise RunnerError(f"unexpected Binance full-period row count {symbol}")
        combined[symbol] = frame
        symbol_audit[symbol] = {
            "rows": len(frame),
            "missing_clock": missing[0].isoformat(),
            "first_timestamp": frame["timestamp"].min().isoformat(),
            "last_timestamp": frame["timestamp"].max().isoformat(),
        }

    return combined, {
        "archive_count_verified": verified_archives,
        "symbols": symbol_audit,
        "network_access_performed": False,
    }


def selection_membership(
    rd31: Any,
    repo: Path,
) -> list[Any]:
    source = repo / rd31.MEMBERSHIP
    if sha256(source) != rd31.MEMBERSHIP_SHA256:
        raise RunnerError("PIT membership SHA drifted")
    snapshots = rd31.load_membership(source)
    selected = rd31.selection_membership(snapshots)
    if not selected:
        raise RunnerError("no PIT membership overlaps RD36-P3 window")
    return selected


def required_pairs(snapshots: list[Any]) -> list[str]:
    pairs: set[str] = set()
    for snapshot in snapshots:
        for pair, _rank in snapshot.members:
            pairs.add(str(pair))
    if not pairs:
        raise RunnerError("PIT membership produced no target pairs")
    return sorted(pairs)


def membership_at(
    rd31: Any,
    snapshots: list[Any],
    *,
    universe_id: str,
    timestamp: pd.Timestamp,
) -> tuple[tuple[str, int], ...]:
    members = rd31.membership_at(
        snapshots,
        universe_id=universe_id,
        timestamp=timestamp,
    )
    return tuple((str(pair), int(rank)) for pair, rank in members)


def load_target_frames(
    repo: Path,
    pairs: list[str],
) -> dict[str, pd.DataFrame]:
    frames: dict[str, pd.DataFrame] = {}
    cutoff = DATA_CUTOFF.to_pydatetime()
    for index, pair in enumerate(pairs, start=1):
        path = repo / KUCOIN_RAW_ROOT / pair / "1h.parquet"
        if not path.is_file():
            raise RunnerError(f"KuCoin target source missing: {path}")
        raw = pd.read_parquet(
            path,
            columns=["timestamp", "open"],
            engine="pyarrow",
            filters=[("timestamp", "<", cutoff)],
        )
        frame = normalize_target_bars(raw, pair=pair)
        frames[pair] = frame
        print(
            "RD36_P3_TARGET_SOURCE="
            f"{index}/{len(pairs)}:{pair}:{len(frame)}:"
            f"cutoff={DATA_CUTOFF.date()}",
            flush=True,
        )
    return frames


def source_state_summary(states: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for family in FAMILY_ORDER:
        for period_id in PERIODS:
            subset = states.loc[
                (states["family_id"] == family) & (states["period_id"] == period_id)
            ]
            rows.append(
                {
                    "family_id": family,
                    "period_id": period_id,
                    "source_state_count": int(len(subset)),
                    "signal_day_count": int(
                        pd.to_datetime(
                            subset["reference_time"],
                            utc=True,
                            errors="coerce",
                        )
                        .dt.floor("D")
                        .nunique()
                    ),
                    "participation_elevated_count": int(
                        subset["participation_elevated"].fillna(False).astype(bool).sum()
                    ),
                }
            )
    return pd.DataFrame.from_records(rows)


def build_markouts(
    *,
    rd31: Any,
    snapshots: list[Any],
    states: pd.DataFrame,
    targets: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    lookups = {pair: target_open_lookup(frame) for pair, frame in targets.items()}
    rows: list[dict[str, Any]] = []

    for state in states.to_dict(orient="records"):
        reference_time = pd.Timestamp(state["reference_time"])
        for universe in UNIVERSES:
            members = membership_at(
                rd31,
                snapshots,
                universe_id=universe,
                timestamp=reference_time,
            )
            for pair, rank in members:
                lookup = lookups.get(pair)
                if lookup is None:
                    raise RunnerError(f"membership pair target frame missing: {pair}")
                for horizon in HORIZONS:
                    markout = target_markout(
                        pair=pair,
                        reference_time=reference_time,
                        horizon_hours=horizon,
                        lookup=lookup,
                    )
                    if markout is None:
                        continue
                    rows.append(
                        {
                            "family_id": state["family_id"],
                            "universe_id": universe,
                            "period_id": state["period_id"],
                            "pair": pair,
                            "membership_rank": rank,
                            "source_time": state["source_time"],
                            "reference_time": reference_time,
                            "horizon_hours": horizon,
                            "exit_time": markout["exit_time"],
                            "entry_price": markout["entry_price"],
                            "exit_price": markout["exit_price"],
                            "forward_return": markout["forward_return"],
                            "participation_elevated": state["participation_elevated"],
                        }
                    )

    columns = [
        "family_id",
        "universe_id",
        "period_id",
        "pair",
        "membership_rank",
        "source_time",
        "reference_time",
        "horizon_hours",
        "exit_time",
        "entry_price",
        "exit_price",
        "forward_return",
        "participation_elevated",
    ]
    result = pd.DataFrame.from_records(rows, columns=columns)
    if not result.empty:
        result = result.sort_values(
            [
                "reference_time",
                "family_id",
                "universe_id",
                "membership_rank",
                "pair",
                "horizon_hours",
            ],
            kind="stable",
        ).reset_index(drop=True)
    return result


def output_manifest(
    output: Path,
    *,
    decision: str,
    freeze_commit: str,
) -> dict[str, Any]:
    files: dict[str, dict[str, Any]] = {}
    for name in OUTPUT_NAMES:
        path = output / name
        if not path.is_file():
            raise RunnerError(f"manifest source missing: {name}")
        files[name] = {
            "sha256": sha256(path),
            "bytes": path.stat().st_size,
        }
    canonical = json.dumps(
        files,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return {
        "schema_version": "rd36-p3-output-manifest-v1",
        "decision": decision,
        "runner_freeze_commit": freeze_commit,
        "file_count": len(files),
        "files": files,
        "deterministic_hash": hashlib.sha256(canonical).hexdigest(),
    }


def execute(
    repo: Path,
    expected_freeze_commit: str,
) -> dict[str, Any]:
    lineage = verify_lineage(repo, expected_freeze_commit)
    if (repo / OUTPUT).exists():
        raise RunnerError("RD36-P3 runtime already exists; validate/recover instead")

    sources, source_audit = load_binance_sources(repo)
    market = market_state_frame(
        sources["BTCUSDT"],
        sources["ETHUSDT"],
    )
    states = state_entry_ledger(market)
    source_summary = source_state_summary(states)

    rd31 = load_rd31_runner()
    snapshots = selection_membership(rd31, repo)
    pairs = required_pairs(snapshots)
    targets = load_target_frames(repo, pairs)
    markouts = build_markouts(
        rd31=rd31,
        snapshots=snapshots,
        states=states,
        targets=targets,
    )
    summary = summarize_markouts(markouts)
    qualifications, families = qualification_tables(summary)

    qualified_primary = list(
        families.loc[
            families["advances_to_shadow_ablation"],
            "family_id",
        ].astype(str)
    )
    qualified_control = list(
        families.loc[
            (~families["primary_exit_candidate"]) & families["qualified"],
            "family_id",
        ].astype(str)
    )
    success = bool(qualified_primary)
    decision = SUCCESS_DECISION if success else FAILURE_DECISION
    next_stage = SUCCESS_NEXT if success else FAILURE_NEXT

    output = repo / OUTPUT
    output.mkdir(parents=True, exist_ok=False)

    first_validity: dict[str, Any] = {}
    for column in (
        "market_pressure_6",
        "market_pressure_24",
        "market_pressure_72",
        "market_participation_shock",
    ):
        post_gap = market.loc[market["timestamp"] > pd.Timestamp("2023-03-24T13:00:00Z")]
        valid = post_gap.loc[post_gap[column].notna(), "timestamp"]
        first_validity[column] = valid.iloc[0].isoformat() if len(valid) else None

    input_audit = {
        "schema_version": "rd36-p3-input-and-conformance-audit-v1",
        "stage": "RD36_P3_CROSS_VENUE_FLOW_STATE_DIAGNOSTIC_2022_2023",
        "lineage": lineage,
        "binance_source_audit": source_audit,
        "binance_fields_loaded": [
            "timestamp",
            "quote_volume",
            "number_of_trades",
            "taker_buy_quote_volume",
        ],
        "binance_ohlc_loaded": False,
        "known_gap": "2023-03-24T13:00:00+00:00",
        "gap_state": "BINANCE_INFO_UNAVAILABLE",
        "post_gap_first_valid_feature_times": first_validity,
        "source_state_event_semantics": "FALSE_TO_TRUE_ENTRY_ONLY",
        "source_to_target_delay_hours": 1,
        "target_reference_price": "KUCOIN_1H_OPEN_AT_T_PLUS_1H",
        "target_exit_price": "KUCOIN_1H_OPEN_AT_REFERENCE_PLUS_HORIZON",
        "target_horizons_hours": list(HORIZONS),
        "target_pair_count": len(pairs),
        "target_pairs": pairs,
        "pit_membership_snapshot_count": len(snapshots),
        "universes": list(UNIVERSES),
        "periods": list(PERIODS),
        "raw_market_data_loaded": True,
        "network_access_performed": False,
        "2024_accessed": False,
        "post_2024_accessed": False,
        "economic_execution_performed": False,
        "production_authorized": False,
    }
    write_json(output / "input-and-conformance-audit.json", input_audit)
    states.to_csv(
        output / "source-state-ledger.csv",
        index=False,
        lineterminator="\n",
    )
    source_summary.to_csv(
        output / "source-state-summary.csv",
        index=False,
        lineterminator="\n",
    )
    markouts.to_csv(
        output / "target-markout-ledger.csv",
        index=False,
        lineterminator="\n",
    )
    summary.to_csv(
        output / "target-markout-summary.csv",
        index=False,
        lineterminator="\n",
    )
    qualifications.to_csv(
        output / "qualification-evaluation.csv",
        index=False,
        lineterminator="\n",
    )
    families.to_csv(
        output / "family-qualification.csv",
        index=False,
        lineterminator="\n",
    )

    freeze = {
        "schema_version": ("rd36-p3-qualified-cross-venue-flow-states-freeze-v1"),
        "status": "PASS",
        "qualified_primary_families": qualified_primary,
        "qualified_control_families": qualified_control,
        "qualified_primary_count": len(qualified_primary),
        "return_ranking_used": False,
        "winner_selection_used": False,
        "parameter_search_used": False,
        "threshold_optimization_used": False,
        "decision": decision,
        "next_stage": next_stage,
        "economic_execution_performed": False,
        "production_authorized": False,
    }
    write_json(
        output / "qualified-cross-venue-flow-states-freeze.json",
        freeze,
    )

    report = {
        "schema_version": ("rd36-p3-cross-venue-flow-state-diagnostic-report-v1"),
        "stage": "RD36_P3_CROSS_VENUE_FLOW_STATE_DIAGNOSTIC_2022_2023",
        "status": "PASS",
        "runner_freeze_commit": expected_freeze_commit,
        "source_p2_freeze_commit": P2_FREEZE_COMMIT,
        "family_order": list(FAMILY_ORDER),
        "source_state_count": len(states),
        "target_markout_count": len(markouts),
        "qualified_primary_families": qualified_primary,
        "qualified_control_families": qualified_control,
        "decision": decision,
        "next_stage": next_stage,
        "raw_market_data_loaded": True,
        "alpha_features_computed": True,
        "forward_returns_computed": True,
        "alpha_results_observed": True,
        "return_ranking_used": False,
        "winner_selection_used": False,
        "parameter_search_used": False,
        "threshold_optimization_used": False,
        "economic_execution_performed": False,
        "network_access_performed": False,
        "2024_accessed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
    }
    write_json(
        output / "rd36-p3-cross-venue-flow-state-diagnostic-report-v1.json",
        report,
    )

    manifest = output_manifest(
        output,
        decision=decision,
        freeze_commit=expected_freeze_commit,
    )
    write_json(output / "output-manifest.json", manifest)

    return validate_outputs(repo)


def validate_outputs(repo: Path) -> dict[str, Any]:
    output = repo / OUTPUT
    if not output.is_dir():
        raise RunnerError("RD36-P3 runtime missing")

    expected = sorted((*OUTPUT_NAMES, "output-manifest.json"))
    observed = sorted(path.name for path in output.iterdir() if path.is_file())
    if observed != expected:
        raise RunnerError(f"RD36-P3 output registry drifted: {observed} != {expected}")

    report = load_json(output / "rd36-p3-cross-venue-flow-state-diagnostic-report-v1.json")
    freeze = load_json(output / "qualified-cross-venue-flow-states-freeze.json")
    input_audit = load_json(output / "input-and-conformance-audit.json")
    source_states = pd.read_csv(
        output / "source-state-ledger.csv",
        low_memory=False,
    )
    markouts = pd.read_csv(
        output / "target-markout-ledger.csv",
        low_memory=False,
    )
    summary = pd.read_csv(
        output / "target-markout-summary.csv",
        low_memory=False,
    )
    qualifications = pd.read_csv(
        output / "qualification-evaluation.csv",
        low_memory=False,
    )
    families = pd.read_csv(
        output / "family-qualification.csv",
        low_memory=False,
    )

    if len(summary) != 72:
        raise RunnerError("RD36-P3 markout summary must have 72 rows")
    if len(qualifications) != 24:
        raise RunnerError("RD36-P3 qualification table must have 24 rows")
    if len(families) != 4:
        raise RunnerError("RD36-P3 family table must have 4 rows")
    if list(families["family_id"].astype(str)) != list(FAMILY_ORDER):
        raise RunnerError("RD36-P3 family order drifted")

    if len(source_states):
        references = pd.to_datetime(
            source_states["reference_time"],
            utc=True,
            errors="raise",
        )
        if references.max() >= DATA_CUTOFF:
            raise RunnerError("2024 source reference entered output")
    if len(markouts):
        exits = pd.to_datetime(
            markouts["exit_time"],
            utc=True,
            errors="raise",
        )
        if exits.max() >= DATA_CUTOFF:
            raise RunnerError("2024 target exit entered output")

    qualified_primary = list(
        families.loc[
            families["advances_to_shadow_ablation"].astype(bool),
            "family_id",
        ].astype(str)
    )
    if report.get("qualified_primary_families") != qualified_primary:
        raise RunnerError("qualified-primary report mismatch")
    success = bool(qualified_primary)
    expected_decision = SUCCESS_DECISION if success else FAILURE_DECISION
    expected_next = SUCCESS_NEXT if success else FAILURE_NEXT
    if report.get("decision") != expected_decision:
        raise RunnerError("RD36-P3 decision mismatch")
    if report.get("next_stage") != expected_next:
        raise RunnerError("RD36-P3 next-stage mismatch")
    if freeze.get("decision") != expected_decision:
        raise RunnerError("RD36-P3 freeze decision mismatch")

    for field in (
        "economic_execution_performed",
        "network_access_performed",
        "2024_accessed",
        "post_2024_accessed",
        "production_authorized",
    ):
        if report.get(field) is not False:
            raise RunnerError(f"RD36-P3 prohibited report flag: {field}")
    if input_audit.get("binance_ohlc_loaded") is not False:
        raise RunnerError("Binance OHLC unexpectedly entered P3")

    manifest = load_json(output / "output-manifest.json")
    if manifest.get("file_count") != len(OUTPUT_NAMES):
        raise RunnerError("RD36-P3 manifest file count drifted")
    if manifest.get("decision") != expected_decision:
        raise RunnerError("RD36-P3 manifest decision mismatch")

    return {
        "status": "PASS",
        "decision": expected_decision,
        "next_stage": expected_next,
        "source_state_count": len(source_states),
        "target_markout_count": len(markouts),
        "qualified_primary_families": qualified_primary,
        "qualified_control_families": report.get("qualified_control_families", []),
        "family_count": len(FAMILY_ORDER),
        "summary_cell_count": len(summary),
        "qualification_cell_count": len(qualifications),
        "economic_execution_performed": False,
        "network_access_performed": False,
        "2024_accessed": False,
        "production_authorized": False,
    }


def main() -> int:
    args = parser().parse_args()
    repo = args.repo_root.resolve()
    if not (repo / ".git").exists():
        raise RunnerError(f"not a git repository: {repo}")

    if args.validate_only:
        print(
            json.dumps(
                validate_outputs(repo),
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    if not args.execute:
        raise RunnerError("RD36-P3 requires explicit --execute")
    if not args.expected_freeze_commit:
        raise RunnerError("--expected-freeze-commit is required")

    print(
        json.dumps(
            execute(repo, args.expected_freeze_commit),
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
