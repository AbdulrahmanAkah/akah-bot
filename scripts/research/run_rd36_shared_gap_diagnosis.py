from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import subprocess
import zipfile
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]

P1_RESULTS_COMMIT = "c117e31c0bc42fbdc3ea2381894f42d1bc45e1f4"
P1_RUNNER_FREEZE_COMMIT = "bb07a5784467da64a13533f4b477d70b8209a444"

P1_RUNTIME = Path("data/research/rd36_p1_runtime")
P1_REPORT = P1_RUNTIME / ("rd36-p1-binance-spot-flow-feasibility-report-v1.json")
P1_REPORT_SHA256 = "00ab2c659318d9bb8b618aa083006ade32440c42e72aba304b523ee8b448b017"
P1_GATES = P1_RUNTIME / "feasibility-gates.json"
P1_GATES_SHA256 = "33274e14949eca13b53a048c75f7812c281463d1662fcc507e3485f051aa1b26"
P1_SOURCE_AUDIT = P1_RUNTIME / "source-file-audit.csv"
P1_SOURCE_AUDIT_SHA256 = "045661c08fcda7270ec762cc093b69f411185e60ba0058e02284b0a7fe2180ce"
P1_SYMBOLS = P1_RUNTIME / "symbol-feasibility.csv"
P1_SYMBOLS_SHA256 = "16ee4e617cde4c4effda9f5f8e6ce62d977e2d9ce2853a38e3d7ebb9b72b02b9"
P1_MANIFEST = P1_RUNTIME / "output-manifest.json"
P1_MANIFEST_SHA256 = "c42206568b6a1f8c1afe5e58eefb061cbaa281871d9aa624e2ba1405b782b064"

RAW_ROOT = Path("data/raw/rd36/binance_spot_flow")
OUTPUT = Path("data/research/rd36_p1d_runtime")

SYMBOLS = ("BTCUSDT", "ETHUSDT")
MONTH = "2023-03"
EXPECTED_MONTH_HOURS = 744
EXPECTED_FULL_HOURS = 17520

OUTAGE_START = pd.Timestamp("2023-03-24T11:38:00Z")
OUTAGE_END = pd.Timestamp("2023-03-24T14:00:00Z")

GATES = (
    "P1_FAILED_EXACTLY_TWO_CONTINUITY_GATES",
    "P1_OTHER_EIGHT_GATES_PASS",
    "BOTH_SYMBOLS_HAVE_EXACTLY_17519_HOURS",
    "ONLY_2023_03_MONTH_HAS_ONE_ROW_DEFICIT_PER_SYMBOL",
    "EACH_SYMBOL_HAS_EXACTLY_ONE_MISSING_MARCH_HOUR",
    "MISSING_HOUR_IDENTICAL_ACROSS_BTC_ETH",
    "MISSING_HOUR_INTERVAL_OVERLAPS_DOCUMENTED_SPOT_HALT",
    "LOCAL_MARCH_ARCHIVES_MATCH_P1_VERIFIED_SHA256",
    "NO_OTHER_MARCH_DUPLICATES_OR_OUT_OF_RANGE_TIMESTAMPS",
    "NO_2024_OR_LATER_ACCESS",
)

PASS_DECISION = (
    "RD36_SHARED_BINANCE_SPOT_HALT_GAP_CONFIRMED_SOURCE_USABLE_WITH_EXPLICIT_UNAVAILABLE_CLOCK"
)
PASS_NEXT = (
    "RD36_P2_PREREGISTER_CROSS_VENUE_BINANCE_SPOT_FLOW_"
    "KUCOIN_NATIVE_ALPHA_ARCHITECTURE_WITH_GAP_SEMANTICS"
)
FAIL_DECISION = "RD36_ALTERNATE_SPOT_MICROSTRUCTURE_SOURCE_FEASIBILITY_REQUIRED"

OUTPUT_NAMES = (
    "shared-gap-diagnosis.json",
    "gap-neighbor-ledger.csv",
    "rd36-p1d-shared-gap-diagnosis-report-v1.json",
)


class DiagnosisError(RuntimeError):
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
        raise DiagnosisError(f"git {' '.join(args)} failed: {result.stderr}")
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
        raise DiagnosisError(f"JSON object expected: {path}")
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


def csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def verify_p1_artifacts(repo: Path) -> None:
    for relative, expected in (
        (P1_REPORT, P1_REPORT_SHA256),
        (P1_GATES, P1_GATES_SHA256),
        (P1_SOURCE_AUDIT, P1_SOURCE_AUDIT_SHA256),
        (P1_SYMBOLS, P1_SYMBOLS_SHA256),
        (P1_MANIFEST, P1_MANIFEST_SHA256),
    ):
        path = repo / relative
        if not path.is_file():
            raise DiagnosisError(f"P1 artifact missing: {relative}")
        actual = sha256(path)
        if actual != expected:
            raise DiagnosisError(f"P1 artifact SHA drift: {relative}: {actual} != {expected}")


def verify_lineage(
    repo: Path,
    expected_freeze_commit: str,
) -> None:
    if git(repo, "diff", "--cached", "--name-only", "--"):
        raise DiagnosisError("staged tracked changes exist")
    if git(repo, "diff", "--name-only", "--"):
        raise DiagnosisError("unstaged tracked changes exist")

    head = git(repo, "rev-parse", "HEAD")
    if head != expected_freeze_commit:
        raise DiagnosisError(f"HEAD {head} != P1D freeze {expected_freeze_commit}")
    if git(repo, "rev-parse", "HEAD^") != P1_RESULTS_COMMIT:
        raise DiagnosisError("P1D freeze parent is not P1 results")
    verify_p1_artifacts(repo)


def expected_march_index() -> pd.DatetimeIndex:
    return pd.date_range(
        "2023-03-01T00:00:00Z",
        "2023-03-31T23:00:00Z",
        freq="h",
        tz="UTC",
    )


def parse_open_times(path: Path) -> pd.DatetimeIndex:
    if not path.is_file():
        raise DiagnosisError(f"raw March archive missing: {path}")

    with zipfile.ZipFile(path, "r") as archive:
        names = [name for name in archive.namelist() if not name.endswith("/")]
        if len(names) != 1:
            raise DiagnosisError(f"{path.name}: expected one CSV member")
        raw = archive.read(names[0]).decode("utf-8-sig")

    reader = csv.reader(io.StringIO(raw))
    open_times: list[int] = []
    for index, row in enumerate(reader):
        if len(row) != 12:
            raise DiagnosisError(f"{path.name}: row {index} does not have 12 columns")
        try:
            value = int(row[0])
        except ValueError:
            if index == 0:
                continue
            raise
        if value >= 100_000_000_000_000:
            raise DiagnosisError(f"{path.name}: unexpected microsecond-era timestamp")
        open_times.append(value)

    timestamps = pd.to_datetime(
        pd.Series(open_times, dtype="int64"),
        unit="ms",
        utc=True,
        errors="raise",
    )
    return pd.DatetimeIndex(timestamps)


def archive_audit_row(
    source_rows: list[dict[str, str]],
    symbol: str,
) -> dict[str, str]:
    matches = [row for row in source_rows if row["symbol"] == symbol and row["month"] == MONTH]
    if len(matches) != 1:
        raise DiagnosisError(f"expected one P1 March row for {symbol}")
    return matches[0]


def missing_interval_overlaps_outage(
    missing_open: pd.Timestamp,
) -> bool:
    bar_start = missing_open
    bar_end = missing_open + pd.Timedelta(hours=1)
    return bool(bar_start < OUTAGE_END and bar_end > OUTAGE_START)


def execute(
    repo: Path,
    expected_freeze_commit: str,
) -> dict[str, Any]:
    verify_lineage(repo, expected_freeze_commit)

    if (repo / OUTPUT).exists():
        raise DiagnosisError("P1D runtime already exists; validate/recover instead")

    gates_p1 = load_json(repo / P1_GATES)
    gate_map = gates_p1["gates"]
    p1_failed = [name for name, value in gate_map.items() if value is not True]
    expected_failed = {
        "EACH_SYMBOL_EXACT_17520_UNIQUE_HOURLY_OPEN_TIMES",
        "NO_DUPLICATE_OR_NON_HOURLY_OPEN_TIMES",
    }

    symbol_rows = csv_rows(repo / P1_SYMBOLS)
    source_rows = csv_rows(repo / P1_SOURCE_AUDIT)

    diagnosis: dict[str, Any] = {
        "schema_version": "rd36-p1d-shared-gap-diagnosis-v1",
        "source_p1_results_commit": P1_RESULTS_COMMIT,
        "p1_failed_gates": sorted(p1_failed),
        "documented_outage_window": {
            "start_utc": OUTAGE_START.isoformat(),
            "end_utc": OUTAGE_END.isoformat(),
            "source_basis": [
                {
                    "publisher": "CoinDesk",
                    "event": ("Binance suspended spot markets at 11:38 UTC on 2023-03-24"),
                },
                {
                    "publisher": "TechCrunch",
                    "event": (
                        "Binance spot trading outage caused by matching-engine bug on 2023-03-24"
                    ),
                },
            ],
        },
        "symbols": {},
    }

    neighbor_rows: list[dict[str, Any]] = []
    missing_by_symbol: dict[str, list[pd.Timestamp]] = {}
    local_sha_match: dict[str, bool] = {}
    march_integrity: dict[str, bool] = {}

    expected = expected_march_index()
    expected_set = set(expected)

    for symbol in SYMBOLS:
        audit = archive_audit_row(source_rows, symbol)
        raw_path = repo / RAW_ROOT / symbol / "1h" / f"{symbol}-1h-{MONTH}.zip"

        actual_sha = sha256(raw_path)
        expected_sha = audit["archive_sha256"]
        local_sha_match[symbol] = actual_sha == expected_sha

        timestamps = parse_open_times(raw_path)
        timestamp_set = set(timestamps)
        missing = sorted(expected_set - timestamp_set)
        extra = sorted(timestamp_set - expected_set)
        duplicates = int(timestamps.duplicated().sum())

        missing_by_symbol[symbol] = missing
        march_integrity[symbol] = bool(
            len(timestamps) == EXPECTED_MONTH_HOURS - 1
            and len(missing) == 1
            and not extra
            and duplicates == 0
        )

        missing_value = missing[0] if len(missing) == 1 else None
        if missing_value is not None:
            previous_candidates = timestamps[timestamps < missing_value]
            next_candidates = timestamps[timestamps > missing_value]
            previous = previous_candidates.max() if len(previous_candidates) else None
            following = next_candidates.min() if len(next_candidates) else None
            neighbor_rows.append(
                {
                    "symbol": symbol,
                    "missing_open_time": missing_value.isoformat(),
                    "previous_observed_open_time": (
                        previous.isoformat() if previous is not None else None
                    ),
                    "next_observed_open_time": (
                        following.isoformat() if following is not None else None
                    ),
                    "missing_hour_overlaps_documented_outage": (
                        missing_interval_overlaps_outage(missing_value)
                    ),
                }
            )

        diagnosis["symbols"][symbol] = {
            "p1_full_period_row_count": next(
                int(row["row_count"]) for row in symbol_rows if row["symbol"] == symbol
            ),
            "p1_march_archive_row_count": int(audit["archive_row_count"]),
            "p1_march_expected_hours": int(audit["expected_month_hours"]),
            "local_archive_sha256": actual_sha,
            "p1_verified_archive_sha256": expected_sha,
            "local_archive_matches_p1_sha256": (local_sha_match[symbol]),
            "march_observed_rows": len(timestamps),
            "march_unique_rows": int(timestamps.nunique()),
            "march_duplicate_count": duplicates,
            "march_extra_timestamps": [value.isoformat() for value in extra],
            "march_missing_timestamps": [value.isoformat() for value in missing],
        }

    deficit_rows = [
        row
        for row in source_rows
        if int(row["archive_row_count"]) != int(row["expected_month_hours"])
    ]
    deficit_registry = {(row["symbol"], row["month"]) for row in deficit_rows}

    symbol_17519 = {
        row["symbol"]: int(row["row_count"]) == EXPECTED_FULL_HOURS - 1 for row in symbol_rows
    }

    btc_missing = missing_by_symbol["BTCUSDT"]
    eth_missing = missing_by_symbol["ETHUSDT"]
    shared_missing = bool(
        len(btc_missing) == 1 and len(eth_missing) == 1 and btc_missing[0] == eth_missing[0]
    )
    shared_value = btc_missing[0] if shared_missing else None

    gate_values = {
        "P1_FAILED_EXACTLY_TWO_CONTINUITY_GATES": (set(p1_failed) == expected_failed),
        "P1_OTHER_EIGHT_GATES_PASS": (
            len(gate_map) == 10 and sum(value is True for value in gate_map.values()) == 8
        ),
        "BOTH_SYMBOLS_HAVE_EXACTLY_17519_HOURS": all(
            symbol_17519.get(symbol, False) for symbol in SYMBOLS
        ),
        "ONLY_2023_03_MONTH_HAS_ONE_ROW_DEFICIT_PER_SYMBOL": (
            deficit_registry
            == {
                ("BTCUSDT", "2023-03"),
                ("ETHUSDT", "2023-03"),
            }
            and all(
                int(row["expected_month_hours"]) - int(row["archive_row_count"]) == 1
                for row in deficit_rows
            )
        ),
        "EACH_SYMBOL_HAS_EXACTLY_ONE_MISSING_MARCH_HOUR": all(
            len(missing_by_symbol[symbol]) == 1 for symbol in SYMBOLS
        ),
        "MISSING_HOUR_IDENTICAL_ACROSS_BTC_ETH": shared_missing,
        "MISSING_HOUR_INTERVAL_OVERLAPS_DOCUMENTED_SPOT_HALT": (
            shared_value is not None and missing_interval_overlaps_outage(shared_value)
        ),
        "LOCAL_MARCH_ARCHIVES_MATCH_P1_VERIFIED_SHA256": all(local_sha_match.values()),
        "NO_OTHER_MARCH_DUPLICATES_OR_OUT_OF_RANGE_TIMESTAMPS": all(march_integrity.values()),
        "NO_2024_OR_LATER_ACCESS": all(
            all(value < pd.Timestamp("2024-01-01T00:00:00Z") for value in missing_by_symbol[symbol])
            for symbol in SYMBOLS
        ),
    }
    if tuple(gate_values) != GATES:
        raise DiagnosisError("P1D gate order drifted")

    all_passed = all(gate_values.values())
    decision = PASS_DECISION if all_passed else FAIL_DECISION
    next_stage = PASS_NEXT if all_passed else FAIL_DECISION

    diagnosis["gate_order"] = list(GATES)
    diagnosis["gates"] = gate_values
    diagnosis["all_gates_passed"] = all_passed
    diagnosis["shared_missing_open_time"] = (
        shared_value.isoformat() if shared_value is not None else None
    )
    diagnosis["decision"] = decision
    diagnosis["next_stage"] = next_stage

    output = repo / OUTPUT
    output.mkdir(parents=True, exist_ok=False)

    write_json(
        output / "shared-gap-diagnosis.json",
        diagnosis,
    )
    pd.DataFrame.from_records(neighbor_rows).to_csv(
        output / "gap-neighbor-ledger.csv",
        index=False,
        lineterminator="\n",
    )

    report = {
        "schema_version": ("rd36-p1d-shared-gap-diagnosis-report-v1"),
        "stage": "RD36_P1D_SHARED_SPOT_HALT_GAP_DIAGNOSIS",
        "status": "PASS",
        "source_p1_results_commit": P1_RESULTS_COMMIT,
        "runner_freeze_commit": expected_freeze_commit,
        "diagnosis_passed": all_passed,
        "decision": decision,
        "next_stage": next_stage,
        "shared_missing_open_time": (
            shared_value.isoformat() if shared_value is not None else None
        ),
        "passed_gate_count": sum(gate_values.values()),
        "gate_count": len(GATES),
        "source_gap_semantics_if_pass": {
            "missing_binance_hour_state": "BINANCE_INFO_UNAVAILABLE",
            "imputation": "FORBIDDEN",
            "forward_fill": "FORBIDDEN",
            "carry_forward_flow": "FORBIDDEN",
            "same_bar_cross_venue_use": "FORBIDDEN",
            "future_feature_warmup": (
                "A feature with lookback L requires L consecutive observed "
                "Binance bars after any source gap before becoming valid."
            ),
            "kucoin_target_execution_venue": "KUCOIN_SPOT",
        },
        "network_access_performed": False,
        "alpha_features_computed": False,
        "alpha_results_observed": False,
        "binance_forward_returns_observed": False,
        "kucoin_forward_returns_observed": False,
        "economic_execution_performed": False,
        "2024_accessed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
    }
    write_json(
        output / "rd36-p1d-shared-gap-diagnosis-report-v1.json",
        report,
    )

    return validate_outputs(repo)


def validate_outputs(repo: Path) -> dict[str, Any]:
    output = repo / OUTPUT
    if not output.is_dir():
        raise DiagnosisError("P1D runtime missing")
    observed = sorted(path.name for path in output.iterdir() if path.is_file())
    if observed != sorted(OUTPUT_NAMES):
        raise DiagnosisError(f"P1D output registry drifted: {observed}")

    diagnosis = load_json(output / "shared-gap-diagnosis.json")
    report = load_json(output / "rd36-p1d-shared-gap-diagnosis-report-v1.json")
    neighbors = csv_rows(output / "gap-neighbor-ledger.csv")

    if tuple(diagnosis.get("gate_order", ())) != GATES:
        raise DiagnosisError("P1D gate order drifted")
    gate_values = diagnosis.get("gates", {})
    if set(gate_values) != set(GATES):
        raise DiagnosisError("P1D gate set drifted")
    all_passed = all(gate_values[gate] is True for gate in GATES)
    if diagnosis.get("all_gates_passed") is not all_passed:
        raise DiagnosisError("P1D all-gates mismatch")

    if len(neighbors) != 2:
        raise DiagnosisError("P1D neighbor rows must be exactly 2")
    if [row["symbol"] for row in neighbors] != list(SYMBOLS):
        raise DiagnosisError("P1D neighbor symbol registry drifted")

    expected_decision = PASS_DECISION if all_passed else FAIL_DECISION
    expected_next = PASS_NEXT if all_passed else FAIL_DECISION
    if report.get("decision") != expected_decision:
        raise DiagnosisError("P1D report decision mismatch")
    if report.get("next_stage") != expected_next:
        raise DiagnosisError("P1D report next-stage mismatch")
    if report.get("diagnosis_passed") is not all_passed:
        raise DiagnosisError("P1D diagnosis_passed mismatch")

    for field in (
        "network_access_performed",
        "alpha_features_computed",
        "alpha_results_observed",
        "binance_forward_returns_observed",
        "kucoin_forward_returns_observed",
        "economic_execution_performed",
        "2024_accessed",
        "post_2024_accessed",
        "production_authorized",
    ):
        if report.get(field) is not False:
            raise DiagnosisError(f"P1D prohibited flag true: {field}")

    return {
        "status": "PASS",
        "diagnosis_passed": all_passed,
        "decision": expected_decision,
        "next_stage": expected_next,
        "shared_missing_open_time": report.get("shared_missing_open_time"),
        "passed_gate_count": sum(gate_values.values()),
        "gate_count": len(GATES),
        "network_access_performed": False,
        "alpha_results_observed": False,
        "economic_execution_performed": False,
        "2024_accessed": False,
    }


def main() -> int:
    args = parser().parse_args()
    repo = args.repo_root.resolve()
    if not (repo / ".git").exists():
        raise DiagnosisError(f"not a git repository: {repo}")

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
        raise DiagnosisError("shared-gap diagnosis requires explicit --execute")
    if not args.expected_freeze_commit:
        raise DiagnosisError("--expected-freeze-commit is required")

    print(
        json.dumps(
            execute(
                repo,
                args.expected_freeze_commit,
            ),
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
