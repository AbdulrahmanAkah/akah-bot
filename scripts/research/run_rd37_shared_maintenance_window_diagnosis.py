from __future__ import annotations

import csv
import hashlib
import io
import json
import sys
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

P1_RESULTS_COMMIT = "4aa19f0bbe9323b345ebb5510537e4a798bdec06"
P1_RUNTIME = Path("data/research/rd37_p1_runtime")
P1_GATES = P1_RUNTIME / "feasibility-gates.json"
P1_SHARED = P1_RUNTIME / "shared-gap-ledger.csv"
P1_SOURCE_AUDIT = P1_RUNTIME / "source-file-audit.csv"
P1_SYMBOLS = P1_RUNTIME / "symbol-feasibility.csv"
RD36_DIAG = Path("data/research/rd36_p1d_runtime/shared-gap-diagnosis.json")
RAW_ROOT = Path("data/raw/rd37/binance_spot_1m")
OUTPUT = Path("data/research/rd37_p1d_runtime")

SYMBOLS = ("BTCUSDT", "ETHUSDT")
MONTH = "2023-03"
INTERVAL = "1m"

OUTAGE_START_MS = int(datetime(2023, 3, 24, 11, 38, tzinfo=UTC).timestamp() * 1000)
OUTAGE_END_MS = int(datetime(2023, 3, 24, 14, 0, tzinfo=UTC).timestamp() * 1000)
MINUTE_MS = 60_000

GATES = (
    "P1_FAILED_EXACTLY_SCHEMA_NAMED_GATE",
    "P1_OTHER_NINE_GATES_PASS",
    "ALL_48_ARCHIVES_HAVE_TRUE_SCHEMA_PASS",
    "CLOSE_TIME_FAILURE_CONFINED_TO_BTC_ETH_2023_03",
    "SHARED_80_MINUTE_GAP_IDENTICAL_BTC_ETH",
    "LOCAL_MARCH_ARCHIVES_MATCH_P1_VERIFIED_SHA256",
    "CLOSE_TIME_ANOMALIES_IDENTICAL_BTC_ETH",
    "CLOSE_TIME_ANOMALIES_CONFINED_TO_DOCUMENTED_MAINTENANCE_WINDOW",
    "NO_OTHER_MARCH_CLOCK_OR_SCHEMA_CORRUPTION",
    "NO_2024_OR_LATER_ACCESS",
)

SUCCESS_DECISION = "RD37_BINANCE_SPOT_1M_SOURCE_USABLE_WITH_EXPLICIT_MAINTENANCE_CLOCK_SEMANTICS"
SUCCESS_NEXT = (
    "RD37_P2_PREREGISTER_CAUSAL_1M_TO_HOUR_STRESS_TRANSFORMS_AND_THRESHOLDS_WITH_GAP_SEMANTICS"
)
FAILURE_DECISION = "RD37_BINANCE_SPOT_1M_SOURCE_REJECTED_AFTER_MAINTENANCE_DIAGNOSIS"
FAILURE_NEXT = "RD38_PREREGISTER_NEXT_SPOT_ONLY_ADAPTIVE_EXIT_INFORMATION_SOURCE"


class DiagnosisError(RuntimeError):
    pass


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


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            value,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )


def iso_ms(value: int) -> str:
    return datetime.fromtimestamp(
        value / 1000,
        tz=UTC,
    ).isoformat()


def parse_march(
    symbol: str,
    path: Path,
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    dict[str, Any],
]:
    anomalies: list[dict[str, Any]] = []
    neighbors: list[dict[str, Any]] = []
    opens: list[int] = []
    parse_errors = 0
    schema_errors = 0
    duplicate_count = 0
    non_increasing_count = 0
    out_of_range_count = 0
    negative_flow_count = 0

    start_ms = int(datetime(2023, 3, 1, tzinfo=UTC).timestamp() * 1000)
    end_ms = int(datetime(2023, 4, 1, tzinfo=UTC).timestamp() * 1000)

    with zipfile.ZipFile(path, "r") as archive:
        names = [name for name in archive.namelist() if not name.endswith("/")]
        if len(names) != 1:
            raise DiagnosisError(f"{symbol}: expected one CSV member, found {names}")
        with archive.open(names[0], "r") as binary:
            reader = csv.reader(
                io.TextIOWrapper(
                    binary,
                    encoding="utf-8-sig",
                    newline="",
                )
            )
            previous: int | None = None
            seen: set[int] = set()

            for index, row in enumerate(reader):
                if index == 0 and row and not row[0].isdigit():
                    continue
                if len(row) != 12:
                    schema_errors += 1
                    continue

                try:
                    open_ms = int(row[0])
                    close_ms = int(row[6])
                    quote_volume = float(row[7])
                    trades = int(row[8])
                    taker_quote = float(row[10])
                except (ValueError, TypeError, OverflowError):
                    parse_errors += 1
                    continue

                opens.append(open_ms)
                if open_ms in seen:
                    duplicate_count += 1
                seen.add(open_ms)

                if previous is not None and open_ms <= previous:
                    non_increasing_count += 1
                previous = open_ms

                if not (start_ms <= open_ms < end_ms):
                    out_of_range_count += 1

                if quote_volume < 0 or trades < 0 or taker_quote < 0:
                    negative_flow_count += 1

                expected_close = open_ms + MINUTE_MS - 1
                if close_ms != expected_close:
                    anomalies.append(
                        {
                            "symbol": symbol,
                            "open_time": iso_ms(open_ms),
                            "close_time": iso_ms(close_ms),
                            "expected_close_time": iso_ms(expected_close),
                            "open_ms": open_ms,
                            "close_ms": close_ms,
                            "expected_close_ms": expected_close,
                            "close_extension_ms": (close_ms - expected_close),
                            "quote_volume": quote_volume,
                            "number_of_trades": trades,
                            "taker_buy_quote_volume": taker_quote,
                            "inside_documented_maintenance": (
                                OUTAGE_START_MS <= open_ms < OUTAGE_END_MS
                                and close_ms < OUTAGE_END_MS
                            ),
                        }
                    )

                if OUTAGE_START_MS - 5 * MINUTE_MS <= open_ms < OUTAGE_END_MS + 5 * MINUTE_MS:
                    neighbors.append(
                        {
                            "symbol": symbol,
                            "open_time": iso_ms(open_ms),
                            "close_time": iso_ms(close_ms),
                            "expected_close_time": iso_ms(expected_close),
                            "close_time_standard": (close_ms == expected_close),
                            "quote_volume": quote_volume,
                            "number_of_trades": trades,
                            "taker_buy_quote_volume": taker_quote,
                        }
                    )

    expected = set(range(start_ms, end_ms, MINUTE_MS))
    observed = set(opens)
    missing = sorted(expected - observed)
    extras = sorted(observed - expected)

    checks = {
        "symbol": symbol,
        "row_count": len(opens),
        "unique_open_count": len(observed),
        "schema_error_count": schema_errors,
        "parse_error_count": parse_errors,
        "duplicate_count": duplicate_count,
        "non_increasing_count": non_increasing_count,
        "out_of_range_count": out_of_range_count,
        "negative_flow_count": negative_flow_count,
        "missing_open_count": len(missing),
        "missing_first": iso_ms(missing[0]) if missing else None,
        "missing_last": iso_ms(missing[-1]) if missing else None,
        "extra_open_count": len(extras),
        "anomaly_count": len(anomalies),
    }
    return anomalies, neighbors, checks


def main() -> int:
    if len(sys.argv) != 3 or sys.argv[1] != "--repo-root":
        raise DiagnosisError("usage: runner.py --repo-root PATH")
    repo = Path(sys.argv[2]).resolve()

    gates_payload = load_json(repo / P1_GATES)
    gate_rows = gates_payload.get("gates", [])
    failed = [str(row.get("gate")) for row in gate_rows if row.get("passed") is False]
    passed_count = sum(row.get("passed") is True for row in gate_rows)

    source_rows = load_csv(repo / P1_SOURCE_AUDIT)
    symbol_rows = load_csv(repo / P1_SYMBOLS)
    shared_rows = load_csv(repo / P1_SHARED)
    rd36 = load_json(repo / RD36_DIAG)

    source_by_key = {(row["symbol"], row["month"]): row for row in source_rows}

    schema_true_all = len(source_rows) == 48 and all(
        row["schema_pass"] == "True" for row in source_rows
    )

    close_failures = sorted(
        (row["symbol"], row["month"]) for row in source_rows if row["close_time_pass"] != "True"
    )
    expected_close_failures = [
        ("BTCUSDT", "2023-03"),
        ("ETHUSDT", "2023-03"),
    ]

    shared_gap_ok = (
        len(shared_rows) == 1
        and shared_rows[0]["shared_gap_start"] == "2023-03-24T12:40:00+00:00"
        and shared_rows[0]["shared_gap_end"] == "2023-03-24T13:59:00+00:00"
        and int(shared_rows[0]["shared_missing_minute_count"]) == 80
        and shared_rows[0]["exact_range_match"] == "True"
    )

    anomalies_by_symbol: dict[str, list[dict[str, Any]]] = {}
    neighbors_all: list[dict[str, Any]] = []
    march_checks: dict[str, Any] = {}
    sha_match_all = True

    for symbol in SYMBOLS:
        audit = source_by_key[(symbol, MONTH)]
        path = repo / RAW_ROOT / symbol / INTERVAL / f"{symbol}-{INTERVAL}-{MONTH}.zip"
        if not path.is_file():
            raise DiagnosisError(f"raw March archive missing: {path}")

        actual_sha = sha256(path)
        expected_sha = audit["archive_sha256"]
        sha_ok = actual_sha == expected_sha
        sha_match_all = sha_match_all and sha_ok

        anomalies, neighbors, checks = parse_march(
            symbol,
            path,
        )
        anomalies_by_symbol[symbol] = anomalies
        neighbors_all.extend(neighbors)

        checks["archive_sha256"] = actual_sha
        checks["p1_archive_sha256"] = expected_sha
        checks["archive_sha_matches_p1"] = sha_ok
        march_checks[symbol] = checks

    btc_pattern = [
        (
            item["open_ms"],
            item["close_ms"],
            item["expected_close_ms"],
        )
        for item in anomalies_by_symbol["BTCUSDT"]
    ]
    eth_pattern = [
        (
            item["open_ms"],
            item["close_ms"],
            item["expected_close_ms"],
        )
        for item in anomalies_by_symbol["ETHUSDT"]
    ]

    anomaly_pattern_identical = bool(btc_pattern) and btc_pattern == eth_pattern

    all_anomalies = anomalies_by_symbol["BTCUSDT"] + anomalies_by_symbol["ETHUSDT"]
    anomalies_confined = bool(all_anomalies) and all(
        bool(item["inside_documented_maintenance"]) for item in all_anomalies
    )

    no_other_march_corruption = all(
        checks["schema_error_count"] == 0
        and checks["parse_error_count"] == 0
        and checks["duplicate_count"] == 0
        and checks["non_increasing_count"] == 0
        and checks["out_of_range_count"] == 0
        and checks["negative_flow_count"] == 0
        and checks["extra_open_count"] == 0
        and checks["missing_open_count"] == 80
        and checks["missing_first"] == "2023-03-24T12:40:00+00:00"
        and checks["missing_last"] == "2023-03-24T13:59:00+00:00"
        for checks in march_checks.values()
    )

    rd36_window = rd36.get(
        "documented_outage_window",
        {},
    )
    outage_frozen_ok = (
        rd36_window.get("start_utc") == "2023-03-24T11:38:00+00:00"
        and rd36_window.get("end_utc") == "2023-03-24T14:00:00+00:00"
    )

    no_2024 = all(row["last_open_time"] < "2024-01-01" for row in symbol_rows) and outage_frozen_ok

    gate_values = {
        "P1_FAILED_EXACTLY_SCHEMA_NAMED_GATE": (
            failed == ["ALL_ROWS_PARSE_TO_EXPECTED_1M_KLINE_SCHEMA"]
        ),
        "P1_OTHER_NINE_GATES_PASS": (passed_count == 9 and len(gate_rows) == 10),
        "ALL_48_ARCHIVES_HAVE_TRUE_SCHEMA_PASS": (schema_true_all),
        "CLOSE_TIME_FAILURE_CONFINED_TO_BTC_ETH_2023_03": (
            close_failures == expected_close_failures
        ),
        "SHARED_80_MINUTE_GAP_IDENTICAL_BTC_ETH": (shared_gap_ok),
        "LOCAL_MARCH_ARCHIVES_MATCH_P1_VERIFIED_SHA256": (sha_match_all),
        "CLOSE_TIME_ANOMALIES_IDENTICAL_BTC_ETH": (anomaly_pattern_identical),
        "CLOSE_TIME_ANOMALIES_CONFINED_TO_DOCUMENTED_MAINTENANCE_WINDOW": (
            anomalies_confined and outage_frozen_ok
        ),
        "NO_OTHER_MARCH_CLOCK_OR_SCHEMA_CORRUPTION": (no_other_march_corruption),
        "NO_2024_OR_LATER_ACCESS": no_2024,
    }

    if tuple(gate_values) != GATES:
        raise DiagnosisError("P1D gate registry drifted")

    all_passed = all(gate_values.values())
    decision = SUCCESS_DECISION if all_passed else FAILURE_DECISION
    next_stage = SUCCESS_NEXT if all_passed else FAILURE_NEXT

    output = repo / OUTPUT
    output.mkdir(parents=True, exist_ok=False)

    anomaly_rows: list[dict[str, Any]] = []
    for symbol in SYMBOLS:
        for item in anomalies_by_symbol[symbol]:
            anomaly_rows.append(
                {
                    key: value
                    for key, value in item.items()
                    if key
                    not in {
                        "open_ms",
                        "close_ms",
                        "expected_close_ms",
                    }
                }
            )

    with (output / "close-time-anomaly-ledger.csv").open(
        "w",
        encoding="utf-8",
        newline="",
    ) as handle:
        fields = [
            "symbol",
            "open_time",
            "close_time",
            "expected_close_time",
            "close_extension_ms",
            "quote_volume",
            "number_of_trades",
            "taker_buy_quote_volume",
            "inside_documented_maintenance",
        ]
        writer = csv.DictWriter(
            handle,
            fieldnames=fields,
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(anomaly_rows)

    with (output / "maintenance-neighbor-ledger.csv").open(
        "w",
        encoding="utf-8",
        newline="",
    ) as handle:
        fields = [
            "symbol",
            "open_time",
            "close_time",
            "expected_close_time",
            "close_time_standard",
            "quote_volume",
            "number_of_trades",
            "taker_buy_quote_volume",
        ]
        writer = csv.DictWriter(
            handle,
            fieldnames=fields,
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(neighbors_all)

    diagnosis = {
        "schema_version": ("rd37-p1d-shared-maintenance-window-diagnosis-v1"),
        "source_p1_results_commit": P1_RESULTS_COMMIT,
        "documented_maintenance_window": {
            "start_utc": "2023-03-24T11:38:00+00:00",
            "end_utc_exclusive": "2023-03-24T14:00:00+00:00",
            "source": "FROZEN_RD36_P1D_DIAGNOSIS",
        },
        "p1_failed_gates": failed,
        "p1_passed_gate_count": passed_count,
        "p1_gate_count": len(gate_rows),
        "shared_gap": (shared_rows[0] if len(shared_rows) == 1 else shared_rows),
        "close_time_failures": [
            {"symbol": symbol, "month": month} for symbol, month in close_failures
        ],
        "march_checks": march_checks,
        "anomaly_pattern_identical_btc_eth": (anomaly_pattern_identical),
        "anomaly_count_per_symbol": {
            symbol: len(anomalies_by_symbol[symbol]) for symbol in SYMBOLS
        },
        "gates": gate_values,
        "gate_order": list(GATES),
        "all_gates_passed": all_passed,
        "decision": decision,
        "next_stage": next_stage,
        "source_semantics_if_pass": {
            "state": "BINANCE_INFO_UNAVAILABLE",
            "unavailable_start_utc": ("2023-03-24T11:38:00+00:00"),
            "unavailable_end_utc_exclusive": ("2023-03-24T14:00:00+00:00"),
            "observed_rows_inside_window_usable": False,
            "imputation": "FORBIDDEN",
            "forward_fill": "FORBIDDEN",
            "backfill": "FORBIDDEN",
            "carry_forward": "FORBIDDEN",
            "same_bar_cross_venue_use": "FORBIDDEN",
            "future_feature_warmup": (
                "Feature lookback L requires L consecutive "
                "observed post-maintenance 1m bars after "
                "14:00 UTC."
            ),
        },
    }
    write_json(
        output / "shared-maintenance-window-diagnosis.json",
        diagnosis,
    )

    report = {
        "schema_version": ("rd37-p1d-shared-maintenance-window-diagnosis-report-v1"),
        "stage": ("RD37_P1D_SHARED_MAINTENANCE_WINDOW_DIAGNOSIS"),
        "status": "PASS",
        "diagnosis_passed": all_passed,
        "decision": decision,
        "next_stage": next_stage,
        "source_p1_results_commit": P1_RESULTS_COMMIT,
        "passed_gate_count": sum(gate_values.values()),
        "gate_count": len(GATES),
        "p1_failed_gate": (failed[0] if len(failed) == 1 else failed),
        "all_48_schema_pass_true": schema_true_all,
        "close_time_failure_archive_count": (len(close_failures)),
        "shared_gap_start": ("2023-03-24T12:40:00+00:00"),
        "shared_gap_end": ("2023-03-24T13:59:00+00:00"),
        "shared_gap_minutes": 80,
        "maintenance_unavailable_start": ("2023-03-24T11:38:00+00:00"),
        "maintenance_unavailable_end_exclusive": ("2023-03-24T14:00:00+00:00"),
        "feature_computation_performed": False,
        "forward_returns_computed": False,
        "alpha_results_observed": False,
        "economic_execution_performed": False,
        "network_access_performed": False,
        "2024_accessed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
    }
    write_json(
        output / ("rd37-p1d-shared-maintenance-window-diagnosis-report-v1.json"),
        report,
    )

    print(
        json.dumps(
            report,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
