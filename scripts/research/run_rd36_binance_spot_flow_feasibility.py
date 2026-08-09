from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]

SCHEMA_VERSION = "rd36-binance-spot-flow-feasibility-runner-v1"

P0_FREEZE_COMMIT = "f2b57436d771da2c76310c6973201082c11daf64"
RD35_RESULTS_COMMIT = "286d31a5abde73ae28ccb9bc715dc7d1969ef43c"

PROTOCOL = Path(
    "data/research/rd36_p0/rd36-p0-cross-venue-binance-spot-flow-feasibility-protocol-v2.json"
)
PROTOCOL_SHA256 = "05d6d6c5dde54415c61782cda5d34980397c638c34b87f0d93675c1eb7b289b7"
PROTOCOL_BLOB = "fca15e21c0108d6ce7ab7663a1deafd045bbab21"

P0_AUDIT = Path("data/research/rd36_p0/rd36-p0-cross-venue-preregistration-audit-v2.json")
P0_AUDIT_SHA256 = "3072666fe79db9e02612de4dc60b384b4062276204e42842d7bea6dc72ac9979"
P0_AUDIT_BLOB = "795dbcf37ed80007898d4ef90b97a074636ae8ff"

SOURCE_ROOT = "https://data.binance.vision"
RAW_ROOT = Path("data/raw/rd36/binance_spot_flow")
OUTPUT = Path("data/research/rd36_p1_runtime")

SYMBOLS = ("BTCUSDT", "ETHUSDT")
INTERVAL = "1h"
START = pd.Timestamp("2022-01-01T00:00:00Z")
CUTOFF = pd.Timestamp("2024-01-01T00:00:00Z")
EXPECTED_HOURS_PER_SYMBOL = 17520

COLUMNS = (
    "open_time",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "close_time",
    "quote_asset_volume",
    "number_of_trades",
    "taker_buy_base_asset_volume",
    "taker_buy_quote_asset_volume",
    "ignore",
)

GATES = (
    "ALL_48_ARCHIVES_PRESENT",
    "ALL_48_CHECKSUMS_PRESENT_AND_MATCH",
    "CSV_SCHEMA_EXACT_12_COLUMNS",
    "EACH_SYMBOL_EXACT_17520_UNIQUE_HOURLY_OPEN_TIMES",
    "NO_TIMESTAMP_GTE_2024_01_01",
    "NO_DUPLICATE_OR_NON_HOURLY_OPEN_TIMES",
    "NUMBER_OF_TRADES_NONNEGATIVE_INTEGER",
    "QUOTE_AND_TAKER_VOLUMES_FINITE_NONNEGATIVE",
    "TAKER_BUY_QUOTE_LTE_QUOTE_VOLUME",
    "NO_HTTP_ZIP_OR_PARSE_FAILURES",
)

PASS_DECISION = "RD36_P2_PREREGISTER_CROSS_VENUE_BINANCE_SPOT_FLOW_KUCOIN_NATIVE_ALPHA_ARCHITECTURE"
FAIL_DECISION = "RD36_ALTERNATE_SPOT_MICROSTRUCTURE_SOURCE_FEASIBILITY_REQUIRED"

OUTPUT_NAMES = (
    "source-file-audit.csv",
    "symbol-feasibility.csv",
    "feasibility-gates.json",
    "rd36-p1-binance-spot-flow-feasibility-report-v1.json",
)


class FeasibilityError(RuntimeError):
    pass


class EnvironmentalNetworkError(FeasibilityError):
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
        raise FeasibilityError(f"git {' '.join(args)} failed: {result.stderr}")
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
        raise FeasibilityError(f"JSON object expected: {path}")
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


def months() -> tuple[str, ...]:
    result: list[str] = []
    for year in (2022, 2023):
        for month in range(1, 13):
            result.append(f"{year:04d}-{month:02d}")
    return tuple(result)


def expected_month_index(month_id: str) -> pd.DatetimeIndex:
    year, month = (int(value) for value in month_id.split("-"))
    start = pd.Timestamp(
        year=year,
        month=month,
        day=1,
        tz="UTC",
    )
    if month == 12:
        next_start = pd.Timestamp(
            year=year + 1,
            month=1,
            day=1,
            tz="UTC",
        )
    else:
        next_start = pd.Timestamp(
            year=year,
            month=month + 1,
            day=1,
            tz="UTC",
        )
    return pd.date_range(
        start,
        next_start - pd.Timedelta(hours=1),
        freq="h",
        tz="UTC",
    )


def expected_full_index() -> pd.DatetimeIndex:
    return pd.date_range(
        START,
        CUTOFF - pd.Timedelta(hours=1),
        freq="h",
        tz="UTC",
    )


def archive_spec(symbol: str, month_id: str) -> dict[str, str]:
    if symbol not in SYMBOLS:
        raise FeasibilityError(f"unsupported symbol: {symbol}")
    if month_id not in months():
        raise FeasibilityError(f"unsupported month: {month_id}")
    filename = f"{symbol}-{INTERVAL}-{month_id}.zip"
    relative = f"data/spot/monthly/klines/{symbol}/{INTERVAL}/{filename}"
    return {
        "symbol": symbol,
        "month": month_id,
        "filename": filename,
        "zip_url": f"{SOURCE_ROOT}/{relative}",
        "checksum_url": f"{SOURCE_ROOT}/{relative}.CHECKSUM",
    }


def verify_lineage(
    repo: Path,
    expected_freeze_commit: str,
) -> dict[str, Any]:
    if git(repo, "diff", "--cached", "--name-only", "--"):
        raise FeasibilityError("staged tracked changes exist")
    if git(repo, "diff", "--name-only", "--"):
        raise FeasibilityError("unstaged tracked changes exist")

    head = git(repo, "rev-parse", "HEAD")
    if head != expected_freeze_commit:
        raise FeasibilityError(f"HEAD {head} != runner freeze {expected_freeze_commit}")
    if git(repo, "rev-parse", "HEAD^") != P0_FREEZE_COMMIT:
        raise FeasibilityError("runner-freeze parent is not RD36 P0 freeze")

    for relative, expected_sha, expected_blob, label in (
        (
            PROTOCOL,
            PROTOCOL_SHA256,
            PROTOCOL_BLOB,
            "RD36 P0 protocol",
        ),
        (
            P0_AUDIT,
            P0_AUDIT_SHA256,
            P0_AUDIT_BLOB,
            "RD36 P0 audit",
        ),
    ):
        path = repo / relative
        if not path.is_file():
            raise FeasibilityError(f"{label} missing")
        actual_sha = sha256(path)
        if actual_sha != expected_sha:
            raise FeasibilityError(f"{label} SHA drift: {actual_sha}")
        actual_blob = git(
            repo,
            "rev-parse",
            f"HEAD:{relative.as_posix()}",
        )
        if actual_blob != expected_blob:
            raise FeasibilityError(f"{label} blob drift: {actual_blob}")

    protocol = load_json(repo / PROTOCOL)
    audit = load_json(repo / P0_AUDIT)

    if protocol.get("status") != "FROZEN_PRE_ACQUISITION":
        raise FeasibilityError("P0 protocol is not frozen")
    if tuple(protocol.get("feasibility_gates", ())) != GATES:
        raise FeasibilityError("P0 feasibility gates drifted")
    if protocol.get("next_stage") != (
        "RD36_P1_EXECUTE_BINANCE_SPOT_FLOW_SOURCE_FEASIBILITY_2022_2023"
    ):
        raise FeasibilityError("P0 next-stage drifted")

    cross = protocol.get("cross_venue_contract", {})
    exact = {
        "target_execution_venue": "KUCOIN_SPOT",
        "target_forward_return_source": "KUCOIN_SPOT",
        "target_portfolio_economics_source": "KUCOIN_SPOT",
        "external_information_venue": "BINANCE_SPOT",
        "external_information_role": ("EXOGENOUS_MARKET_STATE_INFORMATION_ONLY"),
        "same_bar_cross_venue_use": "FORBIDDEN",
        "binance_forward_returns_for_selection": "FORBIDDEN",
    }
    for key, expected in exact.items():
        if cross.get(key) != expected:
            raise FeasibilityError(f"cross-venue contract drift: {key}")

    if audit.get("status") != "PASS":
        raise FeasibilityError("P0 audit is not PASS")
    for field in (
        "network_access_performed",
        "raw_market_data_loaded",
        "source_availability_observed",
        "alpha_features_computed",
        "alpha_results_observed",
        "diagnostic_executed",
        "economic_execution_performed",
        "binance_forward_returns_observed",
        "kucoin_forward_returns_observed_in_rd36_feasibility",
        "2024_accessed",
        "post_2024_accessed",
        "production_authorized",
    ):
        if audit.get(field) is not False:
            raise FeasibilityError(f"P0 prohibited flag true: {field}")

    return {
        "runner_freeze_commit": expected_freeze_commit,
        "p0_freeze_commit": P0_FREEZE_COMMIT,
        "rd35_results_commit": RD35_RESULTS_COMMIT,
        "protocol_sha256": PROTOCOL_SHA256,
        "protocol_git_blob": PROTOCOL_BLOB,
        "p0_audit_sha256": P0_AUDIT_SHA256,
        "p0_audit_git_blob": P0_AUDIT_BLOB,
    }


def download_exact(
    url: str,
    destination: Path,
    *,
    allow_missing: bool,
) -> tuple[bool, str | None, bool]:
    if not url.startswith(SOURCE_ROOT + "/data/spot/monthly/klines/"):
        raise FeasibilityError(f"forbidden source URL: {url}")
    if any(token in url for token in ("2024-", "2025-", "2026-")):
        raise FeasibilityError(f"2024+ URL construction blocked: {url}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_file() and destination.stat().st_size > 0:
        return True, None, True

    temporary = destination.with_suffix(destination.suffix + ".part")
    if temporary.exists():
        temporary.unlink()

    request = urllib.request.Request(
        url,
        headers={"User-Agent": ("akah-bot-rd36-source-feasibility/1.0")},
        method="GET",
    )

    last_error: BaseException | None = None
    for attempt in range(1, 4):
        try:
            with urllib.request.urlopen(
                request,
                timeout=60,
            ) as response:
                if int(response.status) != 200:
                    raise EnvironmentalNetworkError(
                        f"unexpected HTTP status {response.status}: {url}"
                    )
                with temporary.open("wb") as handle:
                    while chunk := response.read(1024 * 1024):
                        handle.write(chunk)
            if temporary.stat().st_size <= 0:
                raise EnvironmentalNetworkError(f"empty HTTP body: {url}")
            temporary.replace(destination)
            return True, None, False
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code == 404 and allow_missing:
                return False, f"HTTP_404:{url}", False
            if attempt < 3 and 500 <= exc.code <= 599:
                time.sleep(attempt * 2)
                continue
            raise EnvironmentalNetworkError(f"HTTP_{exc.code}:{url}") from exc
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as exc:
            last_error = exc
            if attempt < 3:
                time.sleep(attempt * 2)
                continue
            raise EnvironmentalNetworkError(
                f"transport failure after retries: {url}: {exc}"
            ) from exc
        finally:
            if temporary.exists() and destination.exists():
                temporary.unlink()

    raise EnvironmentalNetworkError(f"unreachable download state: {url}: {last_error}")


def parse_checksum(
    text: str,
    expected_filename: str,
) -> str:
    parts = text.strip().split()
    if len(parts) < 2:
        raise FeasibilityError("malformed CHECKSUM content")
    digest = parts[0].strip().lower()
    filename = parts[-1].strip().lstrip("*")
    if len(digest) != 64:
        raise FeasibilityError("CHECKSUM digest is not SHA256")
    if any(char not in "0123456789abcdef" for char in digest):
        raise FeasibilityError("CHECKSUM digest is not hex")
    if filename != expected_filename:
        raise FeasibilityError(f"CHECKSUM filename {filename} != {expected_filename}")
    return digest


def normalize_header(value: str) -> str:
    return value.strip().lower().replace(" ", "_").replace("-", "_")


def parse_archive(
    path: Path,
    *,
    symbol: str,
    month_id: str,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    expected_rows = len(expected_month_index(month_id))
    with zipfile.ZipFile(path, "r") as archive:
        names = [name for name in archive.namelist() if not name.endswith("/")]
        if len(names) != 1:
            raise FeasibilityError(f"{path.name}: expected one CSV member, got {names}")
        member = names[0]
        if not member.lower().endswith(".csv"):
            raise FeasibilityError(f"{path.name}: archive member is not CSV")
        raw = archive.read(member)

    reader = csv.reader(io.StringIO(raw.decode("utf-8-sig")))
    rows = list(reader)
    if not rows:
        raise FeasibilityError(f"{path.name}: empty CSV")

    header_present = False
    first = rows[0]
    if len(first) == 12:
        try:
            int(first[0])
        except ValueError:
            header_present = True

    if header_present:
        normalized = tuple(normalize_header(value) for value in first)
        if normalized != COLUMNS:
            raise FeasibilityError(f"{path.name}: unexpected CSV header {normalized}")
        rows = rows[1:]

    schema_exact = bool(rows) and all(len(row) == 12 for row in rows)
    if not schema_exact:
        raise FeasibilityError(f"{path.name}: non-12-column CSV row")

    frame = pd.DataFrame.from_records(
        rows,
        columns=COLUMNS,
    )

    integer_open = pd.to_numeric(
        frame["open_time"],
        errors="raise",
    ).astype("int64")
    if bool((integer_open >= 100_000_000_000_000).any()):
        raise FeasibilityError(f"{path.name}: unexpected microsecond-era timestamp")
    frame["timestamp"] = pd.to_datetime(
        integer_open,
        unit="ms",
        utc=True,
        errors="raise",
    )

    numeric = (
        "open",
        "high",
        "low",
        "close",
        "volume",
        "close_time",
        "quote_asset_volume",
        "number_of_trades",
        "taker_buy_base_asset_volume",
        "taker_buy_quote_asset_volume",
        "ignore",
    )
    for column in numeric:
        frame[column] = pd.to_numeric(
            frame[column],
            errors="raise",
        )

    actual_index = pd.DatetimeIndex(frame["timestamp"])
    expected_index = expected_month_index(month_id)
    month_exact = (
        len(actual_index) == expected_rows
        and actual_index.is_unique
        and actual_index.equals(expected_index)
    )

    info = {
        "symbol": symbol,
        "month": month_id,
        "archive_row_count": len(frame),
        "expected_month_hours": expected_rows,
        "month_exact_hourly_coverage": bool(month_exact),
        "header_present": header_present,
        "schema_exact_12_columns": True,
        "first_open_time": (frame["timestamp"].iloc[0].isoformat() if len(frame) else None),
        "last_open_time": (frame["timestamp"].iloc[-1].isoformat() if len(frame) else None),
    }
    return frame, info


def symbol_checks(
    frame: pd.DataFrame | None,
    *,
    symbol: str,
) -> dict[str, Any]:
    if frame is None or frame.empty:
        return {
            "symbol": symbol,
            "row_count": 0,
            "unique_hour_count": 0,
            "exact_17520_unique_hourly_open_times": False,
            "no_timestamp_gte_2024": False,
            "no_duplicate_or_non_hourly_open_times": False,
            "number_of_trades_nonnegative_integer": False,
            "quote_and_taker_volumes_finite_nonnegative": False,
            "taker_buy_quote_lte_quote_volume": False,
            "normalized_parquet_path": None,
            "normalized_parquet_sha256": None,
        }

    ordered = frame.sort_values(
        "timestamp",
        kind="stable",
    ).reset_index(drop=True)
    timestamps = pd.DatetimeIndex(ordered["timestamp"])
    expected = expected_full_index()

    exact_hours = (
        len(timestamps) == EXPECTED_HOURS_PER_SYMBOL
        and timestamps.is_unique
        and timestamps.equals(expected)
    )
    no_2024 = bool(len(timestamps) and timestamps.min() >= START and timestamps.max() < CUTOFF)

    differences = timestamps.to_series().diff().dropna()
    hourly = bool(timestamps.is_unique and (differences == pd.Timedelta(hours=1)).all())

    trades = pd.to_numeric(
        ordered["number_of_trades"],
        errors="raise",
    ).astype(float)
    trades_integer = bool(
        np.isfinite(trades.to_numpy(dtype=float)).all()
        and (trades >= 0.0).all()
        and np.equal(trades, np.floor(trades)).all()
    )

    volume_columns = (
        "quote_asset_volume",
        "taker_buy_base_asset_volume",
        "taker_buy_quote_asset_volume",
    )
    volumes = ordered.loc[:, volume_columns].astype(float)
    finite_nonnegative = bool(
        np.isfinite(volumes.to_numpy(dtype=float)).all() and (volumes >= 0.0).all().all()
    )

    quote = ordered["quote_asset_volume"].astype(float)
    taker_quote = ordered["taker_buy_quote_asset_volume"].astype(float)
    tolerance = np.maximum(
        1e-8,
        np.abs(quote.to_numpy(dtype=float)) * 1e-12,
    )
    taker_lte = bool(
        np.all(taker_quote.to_numpy(dtype=float) <= quote.to_numpy(dtype=float) + tolerance)
    )

    return {
        "symbol": symbol,
        "row_count": int(len(ordered)),
        "unique_hour_count": int(timestamps.nunique()),
        "exact_17520_unique_hourly_open_times": exact_hours,
        "no_timestamp_gte_2024": no_2024,
        "no_duplicate_or_non_hourly_open_times": hourly,
        "number_of_trades_nonnegative_integer": trades_integer,
        "quote_and_taker_volumes_finite_nonnegative": (finite_nonnegative),
        "taker_buy_quote_lte_quote_volume": taker_lte,
        "normalized_parquet_path": None,
        "normalized_parquet_sha256": None,
    }


def output_manifest(output: Path) -> dict[str, Any]:
    files: dict[str, dict[str, Any]] = {}
    for name in OUTPUT_NAMES:
        path = output / name
        if not path.is_file():
            raise FeasibilityError(f"manifest input missing: {name}")
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
        "schema_version": "rd36-p1-output-manifest-v1",
        "file_count": len(files),
        "files": files,
        "deterministic_hash": hashlib.sha256(canonical).hexdigest(),
    }


def validate_outputs(repo: Path) -> dict[str, Any]:
    output = repo / OUTPUT
    if not output.is_dir():
        raise FeasibilityError("RD36 P1 runtime missing")

    expected_names = sorted((*OUTPUT_NAMES, "output-manifest.json"))
    observed_names = sorted(path.name for path in output.iterdir() if path.is_file())
    if observed_names != expected_names:
        raise FeasibilityError(f"RD36 P1 output registry drifted: {observed_names}")

    with (output / "source-file-audit.csv").open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as handle:
        file_rows = list(csv.DictReader(handle))
    with (output / "symbol-feasibility.csv").open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as handle:
        symbol_rows = list(csv.DictReader(handle))

    if len(file_rows) != 48:
        raise FeasibilityError(f"source-file audit rows {len(file_rows)} != 48")
    if len(symbol_rows) != 2:
        raise FeasibilityError(f"symbol feasibility rows {len(symbol_rows)} != 2")
    if {(row["symbol"], row["month"]) for row in file_rows} != {
        (symbol, month_id) for symbol in SYMBOLS for month_id in months()
    }:
        raise FeasibilityError("source-file audit registry drifted")
    if [row["symbol"] for row in symbol_rows] != list(SYMBOLS):
        raise FeasibilityError("symbol feasibility registry drifted")

    gates = load_json(output / "feasibility-gates.json")
    if tuple(gates.get("gate_order", ())) != GATES:
        raise FeasibilityError("feasibility gate order drifted")
    gate_values = gates.get("gates", {})
    if set(gate_values) != set(GATES):
        raise FeasibilityError("feasibility gate set drifted")
    passed_all = all(gate_values[gate] is True for gate in GATES)
    if gates.get("all_gates_passed") is not passed_all:
        raise FeasibilityError("all_gates_passed mismatch")

    report = load_json(output / "rd36-p1-binance-spot-flow-feasibility-report-v1.json")
    if report.get("status") != "PASS":
        raise FeasibilityError("RD36 P1 report is not PASS")
    if report.get("feasibility_passed") is not passed_all:
        raise FeasibilityError("report feasibility mismatch")

    expected_decision = PASS_DECISION if passed_all else FAIL_DECISION
    if report.get("decision") != expected_decision:
        raise FeasibilityError("RD36 P1 decision mismatch")
    if report.get("next_stage") != expected_decision:
        raise FeasibilityError("RD36 P1 next-stage mismatch")

    required_true = (
        "network_access_performed",
        "raw_market_data_loaded",
        "source_availability_observed",
    )
    for field in required_true:
        if report.get(field) is not True:
            raise FeasibilityError(f"RD36 P1 expected true flag missing: {field}")

    required_false = (
        "alpha_features_computed",
        "alpha_results_observed",
        "diagnostic_executed",
        "economic_execution_performed",
        "binance_forward_returns_observed",
        "kucoin_forward_returns_observed_in_rd36_feasibility",
        "2024_accessed",
        "post_2024_accessed",
        "production_authorized",
    )
    for field in required_false:
        if report.get(field) is not False:
            raise FeasibilityError(f"RD36 P1 prohibited flag true: {field}")

    if report.get("target_execution_venue") != "KUCOIN_SPOT":
        raise FeasibilityError("KuCoin target venue drifted")
    if report.get("external_information_venue") != "BINANCE_SPOT":
        raise FeasibilityError("Binance info venue drifted")
    if report.get("cross_venue_role") != ("BINANCE_INFORMATION_ONLY_KUCOIN_ECONOMICS_ONLY"):
        raise FeasibilityError("cross-venue role drifted")

    manifest = load_json(output / "output-manifest.json")
    if int(manifest.get("file_count", -1)) != len(OUTPUT_NAMES):
        raise FeasibilityError("manifest file_count drifted")
    if set(manifest.get("files", {})) != set(OUTPUT_NAMES):
        raise FeasibilityError("manifest registry drifted")

    canonical: dict[str, dict[str, Any]] = {}
    for name in OUTPUT_NAMES:
        path = output / name
        actual = {
            "sha256": sha256(path),
            "bytes": path.stat().st_size,
        }
        if manifest["files"][name] != actual:
            raise FeasibilityError(f"manifest mismatch: {name}")
        canonical[name] = actual
    deterministic = hashlib.sha256(
        json.dumps(
            canonical,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
    ).hexdigest()
    if manifest.get("deterministic_hash") != deterministic:
        raise FeasibilityError("manifest deterministic hash drifted")

    return {
        "status": "PASS",
        "feasibility_passed": passed_all,
        "decision": expected_decision,
        "next_stage": expected_decision,
        "source_file_rows": len(file_rows),
        "symbol_rows": len(symbol_rows),
        "gates_passed": sum(gate_values[gate] is True for gate in GATES),
        "gate_count": len(GATES),
        "manifest_deterministic_hash": deterministic,
        "report_sha256": sha256(output / "rd36-p1-binance-spot-flow-feasibility-report-v1.json"),
        "manifest_sha256": sha256(output / "output-manifest.json"),
        "alpha_results_observed": False,
        "economic_execution_performed": False,
        "2024_accessed": False,
    }


def execute(
    *,
    repo: Path,
    expected_freeze_commit: str,
) -> dict[str, Any]:
    lineage = verify_lineage(
        repo,
        expected_freeze_commit,
    )
    output = repo / OUTPUT
    if output.exists():
        raise FeasibilityError("RD36 P1 runtime already exists; validate/recover instead")

    raw_root = repo / RAW_ROOT
    raw_root.mkdir(parents=True, exist_ok=True)

    audit_rows: list[dict[str, Any]] = []
    parsed_by_symbol: dict[str, list[pd.DataFrame]] = {symbol: [] for symbol in SYMBOLS}
    any_network_request = False
    any_market_rows_parsed = False
    source_availability_observed = False
    http_or_parse_failures = False

    specs = [archive_spec(symbol, month_id) for symbol in SYMBOLS for month_id in months()]
    if len(specs) != 48:
        raise FeasibilityError("archive specification count drifted")

    for index, spec in enumerate(specs, start=1):
        symbol = spec["symbol"]
        month_id = spec["month"]
        destination_dir = raw_root / symbol / INTERVAL
        zip_path = destination_dir / spec["filename"]
        checksum_path = destination_dir / (spec["filename"] + ".CHECKSUM")

        row: dict[str, Any] = {
            "symbol": symbol,
            "month": month_id,
            "zip_url": spec["zip_url"],
            "checksum_url": spec["checksum_url"],
            "archive_present": False,
            "checksum_present": False,
            "checksum_match": False,
            "archive_reused": False,
            "checksum_reused": False,
            "archive_sha256": None,
            "expected_archive_sha256": None,
            "archive_bytes": None,
            "schema_exact_12_columns": False,
            "archive_row_count": 0,
            "expected_month_hours": len(expected_month_index(month_id)),
            "month_exact_hourly_coverage": False,
            "header_present": None,
            "first_open_time": None,
            "last_open_time": None,
            "parse_ok": False,
            "error": None,
        }

        print(
            f"RD36_SOURCE_FILE={index}/48:{symbol}:{month_id}",
            flush=True,
        )

        try:
            any_network_request = True
            checksum_ok, checksum_error, checksum_reused = download_exact(
                spec["checksum_url"],
                checksum_path,
                allow_missing=True,
            )
            row["checksum_present"] = checksum_ok
            row["checksum_reused"] = checksum_reused
            if checksum_error is not None:
                row["error"] = checksum_error
                http_or_parse_failures = True
            if checksum_ok:
                source_availability_observed = True

            any_network_request = True
            archive_ok, archive_error, archive_reused = download_exact(
                spec["zip_url"],
                zip_path,
                allow_missing=True,
            )
            row["archive_present"] = archive_ok
            row["archive_reused"] = archive_reused
            if archive_error is not None:
                row["error"] = f"{row['error']};{archive_error}" if row["error"] else archive_error
                http_or_parse_failures = True
            if archive_ok:
                source_availability_observed = True
                row["archive_bytes"] = zip_path.stat().st_size
                row["archive_sha256"] = sha256(zip_path)

            if not checksum_ok or not archive_ok:
                audit_rows.append(row)
                continue

            expected_digest = parse_checksum(
                checksum_path.read_text(encoding="utf-8-sig"),
                spec["filename"],
            )
            row["expected_archive_sha256"] = expected_digest
            row["checksum_match"] = row["archive_sha256"] == expected_digest
            if not row["checksum_match"]:
                row["error"] = "CHECKSUM_MISMATCH"
                http_or_parse_failures = True
                audit_rows.append(row)
                continue

            frame, parse_info = parse_archive(
                zip_path,
                symbol=symbol,
                month_id=month_id,
            )
            any_market_rows_parsed = True
            parsed_by_symbol[symbol].append(frame)
            row.update(parse_info)
            row["parse_ok"] = True
        except EnvironmentalNetworkError:
            raise
        except (
            FeasibilityError,
            ValueError,
            UnicodeError,
            zipfile.BadZipFile,
            pd.errors.ParserError,
        ) as exc:
            row["error"] = f"{type(exc).__name__}:{exc}"
            http_or_parse_failures = True

        audit_rows.append(row)

    if not any_network_request:
        raise FeasibilityError("no network request was attempted")
    if not source_availability_observed:
        raise EnvironmentalNetworkError("no Binance source availability could be observed")

    file_audit = pd.DataFrame.from_records(audit_rows)
    if len(file_audit) != 48:
        raise FeasibilityError("file audit row count drifted")

    symbol_frames: dict[str, pd.DataFrame | None] = {}
    symbol_rows: list[dict[str, Any]] = []

    for symbol in SYMBOLS:
        frames = parsed_by_symbol[symbol]
        combined = pd.concat(frames, ignore_index=True) if frames else None
        symbol_frames[symbol] = combined
        checks = symbol_checks(
            combined,
            symbol=symbol,
        )

        all_symbol_months_parsed = len(frames) == 24 and bool(
            file_audit.loc[
                file_audit["symbol"] == symbol,
                "parse_ok",
            ].all()
        )
        can_write_parquet = bool(
            all_symbol_months_parsed
            and checks["exact_17520_unique_hourly_open_times"]
            and checks["no_timestamp_gte_2024"]
            and checks["no_duplicate_or_non_hourly_open_times"]
        )
        if can_write_parquet and combined is not None:
            normalized = (
                combined.sort_values(
                    "timestamp",
                    kind="stable",
                )
                .reset_index(drop=True)
                .loc[
                    :,
                    [
                        "timestamp",
                        "open_time",
                        "open",
                        "high",
                        "low",
                        "close",
                        "volume",
                        "close_time",
                        "quote_asset_volume",
                        "number_of_trades",
                        "taker_buy_base_asset_volume",
                        "taker_buy_quote_asset_volume",
                        "ignore",
                    ],
                ]
            )
            parquet_path = raw_root / symbol / (f"{symbol}-1h-2022-2023.parquet")
            normalized.to_parquet(
                parquet_path,
                engine="pyarrow",
                index=False,
            )
            checks["normalized_parquet_path"] = str(parquet_path.relative_to(repo)).replace(
                "\\", "/"
            )
            checks["normalized_parquet_sha256"] = sha256(parquet_path)
        symbol_rows.append(checks)

    symbol_table = pd.DataFrame.from_records(symbol_rows)

    gate_values = {
        "ALL_48_ARCHIVES_PRESENT": bool(
            len(file_audit) == 48 and file_audit["archive_present"].all()
        ),
        "ALL_48_CHECKSUMS_PRESENT_AND_MATCH": bool(
            len(file_audit) == 48
            and file_audit["checksum_present"].all()
            and file_audit["checksum_match"].all()
        ),
        "CSV_SCHEMA_EXACT_12_COLUMNS": bool(
            len(file_audit) == 48 and file_audit["schema_exact_12_columns"].all()
        ),
        "EACH_SYMBOL_EXACT_17520_UNIQUE_HOURLY_OPEN_TIMES": bool(
            symbol_table["exact_17520_unique_hourly_open_times"].all()
        ),
        "NO_TIMESTAMP_GTE_2024_01_01": bool(symbol_table["no_timestamp_gte_2024"].all()),
        "NO_DUPLICATE_OR_NON_HOURLY_OPEN_TIMES": bool(
            symbol_table["no_duplicate_or_non_hourly_open_times"].all()
        ),
        "NUMBER_OF_TRADES_NONNEGATIVE_INTEGER": bool(
            symbol_table["number_of_trades_nonnegative_integer"].all()
        ),
        "QUOTE_AND_TAKER_VOLUMES_FINITE_NONNEGATIVE": bool(
            symbol_table["quote_and_taker_volumes_finite_nonnegative"].all()
        ),
        "TAKER_BUY_QUOTE_LTE_QUOTE_VOLUME": bool(
            symbol_table["taker_buy_quote_lte_quote_volume"].all()
        ),
        "NO_HTTP_ZIP_OR_PARSE_FAILURES": bool(
            not http_or_parse_failures and len(file_audit) == 48 and file_audit["parse_ok"].all()
        ),
    }
    if tuple(gate_values) != GATES:
        raise FeasibilityError("gate evaluation order drifted")

    all_passed = all(gate_values.values())
    decision = PASS_DECISION if all_passed else FAIL_DECISION

    output.mkdir(parents=True, exist_ok=False)
    file_audit.to_csv(
        output / "source-file-audit.csv",
        index=False,
        lineterminator="\n",
    )
    symbol_table.to_csv(
        output / "symbol-feasibility.csv",
        index=False,
        lineterminator="\n",
    )
    write_json(
        output / "feasibility-gates.json",
        {
            "schema_version": "rd36-p1-feasibility-gates-v1",
            "gate_order": list(GATES),
            "gates": gate_values,
            "all_gates_passed": all_passed,
            "passed_gate_count": sum(gate_values.values()),
            "gate_count": len(GATES),
        },
    )

    report = {
        "schema_version": ("rd36-p1-binance-spot-flow-feasibility-report-v1"),
        "stage": ("RD36_P1_BINANCE_SPOT_FLOW_SOURCE_FEASIBILITY_2022_2023"),
        "status": "PASS",
        "lineage": lineage,
        "feasibility_passed": all_passed,
        "decision": decision,
        "next_stage": decision,
        "target_execution_venue": "KUCOIN_SPOT",
        "target_universe_source": ("EXISTING_KUCOIN_POINT_IN_TIME_EFFECTIVE_MEMBERSHIP"),
        "target_price_source": "KUCOIN_SPOT",
        "target_cost_source": ("EXISTING_FROZEN_KUCOIN_SPOT_MODEL"),
        "target_forward_return_source": "KUCOIN_SPOT",
        "target_portfolio_economics_source": "KUCOIN_SPOT",
        "external_information_venue": "BINANCE_SPOT",
        "external_information_role": ("EXOGENOUS_MARKET_STATE_INFORMATION_ONLY"),
        "cross_venue_role": ("BINANCE_INFORMATION_ONLY_KUCOIN_ECONOMICS_ONLY"),
        "minimum_cross_venue_delay": "t+1h_OR_LATER",
        "source_symbols": list(SYMBOLS),
        "source_interval": INTERVAL,
        "source_month_count": 24,
        "source_file_count": 48,
        "expected_hours_per_symbol": (EXPECTED_HOURS_PER_SYMBOL),
        "network_access_performed": True,
        "raw_market_data_loaded": any_market_rows_parsed,
        "source_availability_observed": (source_availability_observed),
        "alpha_features_computed": False,
        "alpha_results_observed": False,
        "diagnostic_executed": False,
        "economic_execution_performed": False,
        "binance_forward_returns_observed": False,
        "kucoin_forward_returns_observed_in_rd36_feasibility": (False),
        "same_bar_cross_venue_use": False,
        "binance_universe_substitution": False,
        "binance_execution_price_substitution": False,
        "binance_cost_model_substitution": False,
        "2024_accessed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
    }
    write_json(
        output / "rd36-p1-binance-spot-flow-feasibility-report-v1.json",
        report,
    )
    write_json(
        output / "output-manifest.json",
        output_manifest(output),
    )
    return validate_outputs(repo)


def main() -> int:
    args = parser().parse_args()
    repo = args.repo_root.resolve()
    if not (repo / ".git").exists():
        raise FeasibilityError(f"not a git repository: {repo}")

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
        raise FeasibilityError("source feasibility requires explicit --execute")
    if not args.expected_freeze_commit:
        raise FeasibilityError("--expected-freeze-commit is required")

    result = execute(
        repo=repo,
        expected_freeze_commit=args.expected_freeze_commit,
    )
    print(
        json.dumps(
            result,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(
            f"RD36_P1_RUNNER_ERROR={exc}",
            file=sys.stderr,
        )
        raise
