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

P1D_RESULTS_COMMIT = "f8279dfdd3ce78ec51bbb2b9b35912490f9f9730"

P1D_DIAG = Path("data/research/rd37_p1d_runtime/shared-maintenance-window-diagnosis.json")
P1D_ANOMALIES = Path("data/research/rd37_p1d_runtime/close-time-anomaly-ledger.csv")
P1D_REPORT = Path(
    "data/research/rd37_p1d_runtime/rd37-p1d-shared-maintenance-window-diagnosis-report-v1.json"
)

RAW_ROOT = Path("data/raw/rd37/binance_spot_1m")
OUTPUT = Path("data/research/rd37_p1e_runtime")

SYMBOLS = ("BTCUSDT", "ETHUSDT")
MONTH = "2023-03"
INTERVAL = "1m"

OUTAGE_START_MS = int(datetime(2023, 3, 24, 11, 38, tzinfo=UTC).timestamp() * 1000)
LAST_PRE_GAP_OPEN_MS = int(datetime(2023, 3, 24, 12, 39, tzinfo=UTC).timestamp() * 1000)
GAP_START_MS = int(datetime(2023, 3, 24, 12, 40, tzinfo=UTC).timestamp() * 1000)
RESUME_OPEN_MS = int(datetime(2023, 3, 24, 14, 0, tzinfo=UTC).timestamp() * 1000)
MINUTE_MS = 60_000

GATES = (
    "P1D_FAILED_EXACTLY_LITERAL_CLOSE_TIME_IDENTITY_GATE",
    "EACH_SYMBOL_HAS_EXACTLY_ONE_CLOSE_TIME_ANOMALY",
    "ANOMALIES_SHARE_SAME_1239_OPEN_MINUTE",
    "BOTH_ANOMALY_ROWS_HAVE_ZERO_MARKET_ACTIVITY",
    "BOTH_ANOMALIES_ARE_TRUNCATED_WITHIN_SAME_1239_MINUTE",
    "ALL_OBSERVED_MAINTENANCE_ROWS_1138_1239_HAVE_ZERO_ACTIVITY",
    "BOTH_SYMBOLS_MISSING_EXACTLY_1240_THROUGH_1359",
    "BOTH_SYMBOLS_RESUME_AT_1400",
    "FIRST_1400_ROWS_HAVE_STANDARD_ONE_MINUTE_CLOSE",
    "NO_2024_OR_LATER_ACCESS",
)

SUCCESS_DECISION = "RD37_BINANCE_SPOT_1M_SOURCE_USABLE_WITH_EXPLICIT_MAINTENANCE_BLACKOUT_SEMANTICS"
SUCCESS_NEXT = (
    "RD37_P2_PREREGISTER_CAUSAL_1M_TO_HOUR_STRESS_TRANSFORMS_AND_THRESHOLDS_WITH_GAP_SEMANTICS"
)
FAILURE_DECISION = "RD37_BINANCE_SPOT_1M_SOURCE_FINAL_REJECTION_AFTER_SEMANTIC_DIAGNOSIS"
FAILURE_NEXT = "RD38_PREREGISTER_NEXT_SPOT_ONLY_ADAPTIVE_EXIT_INFORMATION_SOURCE"


class SemanticDiagnosisError(RuntimeError):
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
        raise SemanticDiagnosisError(f"JSON object expected: {path}")
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


def read_march_rows(
    path: Path,
) -> dict[int, dict[str, Any]]:
    rows: dict[int, dict[str, Any]] = {}
    with zipfile.ZipFile(path, "r") as archive:
        names = [name for name in archive.namelist() if not name.endswith("/")]
        if len(names) != 1:
            raise SemanticDiagnosisError(f"expected one CSV member in {path.name}")
        with archive.open(names[0], "r") as binary:
            reader = csv.reader(io.TextIOWrapper(binary, encoding="utf-8-sig", newline=""))
            for index, row in enumerate(reader):
                if index == 0 and row and not row[0].isdigit():
                    continue
                if len(row) != 12:
                    raise SemanticDiagnosisError(f"unexpected schema width in {path.name}")
                open_ms = int(row[0])
                if open_ms in rows:
                    raise SemanticDiagnosisError(f"duplicate open time in {path.name}: {open_ms}")
                rows[open_ms] = {
                    "open_ms": open_ms,
                    "close_ms": int(row[6]),
                    "quote_volume": float(row[7]),
                    "number_of_trades": int(row[8]),
                    "taker_buy_quote_volume": float(row[10]),
                }
    return rows


def main() -> int:
    if len(sys.argv) != 3 or sys.argv[1] != "--repo-root":
        raise SemanticDiagnosisError("usage: runner.py --repo-root PATH")
    repo = Path(sys.argv[2]).resolve()

    p1d = load_json(repo / P1D_DIAG)
    p1d_report = load_json(repo / P1D_REPORT)
    anomalies = load_csv(repo / P1D_ANOMALIES)

    failed_p1d_gates = [gate for gate, value in p1d.get("gates", {}).items() if value is False]

    anomaly_by_symbol = {row["symbol"]: row for row in anomalies}

    raw: dict[str, dict[int, dict[str, Any]]] = {}
    raw_sha: dict[str, str] = {}
    for symbol in SYMBOLS:
        path = repo / RAW_ROOT / symbol / INTERVAL / f"{symbol}-{INTERVAL}-{MONTH}.zip"
        if not path.is_file():
            raise SemanticDiagnosisError(f"missing raw source: {path}")
        raw_sha[symbol] = sha256(path)
        raw[symbol] = read_march_rows(path)

    exact_expected_gap = set(range(GAP_START_MS, RESUME_OPEN_MS, MINUTE_MS))

    each_one = (
        len(anomalies) == 2
        and set(anomaly_by_symbol) == set(SYMBOLS)
        and all(int(p1d["anomaly_count_per_symbol"][symbol]) == 1 for symbol in SYMBOLS)
    )

    same_open = each_one and all(
        anomaly_by_symbol[symbol]["open_time"] == "2023-03-24T12:39:00+00:00" for symbol in SYMBOLS
    )

    zero_anomaly_activity = each_one and all(
        float(anomaly_by_symbol[symbol]["quote_volume"]) == 0.0
        and int(anomaly_by_symbol[symbol]["number_of_trades"]) == 0
        and float(anomaly_by_symbol[symbol]["taker_buy_quote_volume"]) == 0.0
        for symbol in SYMBOLS
    )

    truncated_same_minute = True
    for symbol in SYMBOLS:
        row = raw[symbol].get(LAST_PRE_GAP_OPEN_MS)
        if row is None:
            truncated_same_minute = False
            continue
        expected_close = LAST_PRE_GAP_OPEN_MS + MINUTE_MS - 1
        if not (LAST_PRE_GAP_OPEN_MS <= row["close_ms"] < expected_close):
            truncated_same_minute = False

    maintenance_zero = True
    observed_counts: dict[str, int] = {}
    for symbol in SYMBOLS:
        observed = [
            row
            for open_ms, row in raw[symbol].items()
            if OUTAGE_START_MS <= open_ms <= LAST_PRE_GAP_OPEN_MS
        ]
        observed_counts[symbol] = len(observed)
        if len(observed) != 62:
            maintenance_zero = False
        if any(
            row["quote_volume"] != 0.0
            or row["number_of_trades"] != 0
            or row["taker_buy_quote_volume"] != 0.0
            for row in observed
        ):
            maintenance_zero = False

    exact_gap = True
    missing_by_symbol: dict[str, list[int]] = {}
    for symbol in SYMBOLS:
        observed = set(raw[symbol])
        missing = sorted(open_ms for open_ms in exact_expected_gap if open_ms not in observed)
        missing_by_symbol[symbol] = missing
        if set(missing) != exact_expected_gap:
            exact_gap = False

    resumes_1400 = all(RESUME_OPEN_MS in raw[symbol] for symbol in SYMBOLS)

    standard_1400 = True
    resume_rows: dict[str, dict[str, Any]] = {}
    for symbol in SYMBOLS:
        row = raw[symbol].get(RESUME_OPEN_MS)
        if row is None:
            standard_1400 = False
            continue
        resume_rows[symbol] = row
        if row["close_ms"] != RESUME_OPEN_MS + MINUTE_MS - 1:
            standard_1400 = False

    p1d_failed_exact = (
        failed_p1d_gates == ["CLOSE_TIME_ANOMALIES_IDENTICAL_BTC_ETH"]
        and p1d_report.get("diagnosis_passed") is False
        and p1d_report.get("passed_gate_count") == 9
    )

    no_2024 = all(
        max(raw[symbol]) < int(datetime(2024, 1, 1, tzinfo=UTC).timestamp() * 1000)
        for symbol in SYMBOLS
    )

    gate_values = {
        "P1D_FAILED_EXACTLY_LITERAL_CLOSE_TIME_IDENTITY_GATE": (p1d_failed_exact),
        "EACH_SYMBOL_HAS_EXACTLY_ONE_CLOSE_TIME_ANOMALY": each_one,
        "ANOMALIES_SHARE_SAME_1239_OPEN_MINUTE": same_open,
        "BOTH_ANOMALY_ROWS_HAVE_ZERO_MARKET_ACTIVITY": (zero_anomaly_activity),
        "BOTH_ANOMALIES_ARE_TRUNCATED_WITHIN_SAME_1239_MINUTE": (truncated_same_minute),
        "ALL_OBSERVED_MAINTENANCE_ROWS_1138_1239_HAVE_ZERO_ACTIVITY": (maintenance_zero),
        "BOTH_SYMBOLS_MISSING_EXACTLY_1240_THROUGH_1359": exact_gap,
        "BOTH_SYMBOLS_RESUME_AT_1400": resumes_1400,
        "FIRST_1400_ROWS_HAVE_STANDARD_ONE_MINUTE_CLOSE": standard_1400,
        "NO_2024_OR_LATER_ACCESS": no_2024,
    }
    if tuple(gate_values) != GATES:
        raise SemanticDiagnosisError("gate registry drifted")

    all_passed = all(gate_values.values())
    decision = SUCCESS_DECISION if all_passed else FAILURE_DECISION
    next_stage = SUCCESS_NEXT if all_passed else FAILURE_NEXT

    output = repo / OUTPUT
    output.mkdir(parents=True, exist_ok=False)

    evidence = {
        "schema_version": "rd37-p1e-semantic-maintenance-evidence-v1",
        "source_p1d_results_commit": P1D_RESULTS_COMMIT,
        "p1d_failed_gates": failed_p1d_gates,
        "anomaly_rows": anomalies,
        "raw_archive_sha256": raw_sha,
        "maintenance_observed_row_count": observed_counts,
        "expected_zero_activity_window": {
            "start_utc": "2023-03-24T11:38:00+00:00",
            "last_observed_open_utc": "2023-03-24T12:39:00+00:00",
            "expected_observed_minute_count_per_symbol": 62,
        },
        "shared_missing_window": {
            "start_utc": "2023-03-24T12:40:00+00:00",
            "end_utc_inclusive": "2023-03-24T13:59:00+00:00",
            "expected_missing_minutes_per_symbol": 80,
            "btc_missing_count": len(missing_by_symbol["BTCUSDT"]),
            "eth_missing_count": len(missing_by_symbol["ETHUSDT"]),
        },
        "resume_open_utc": "2023-03-24T14:00:00+00:00",
        "resume_rows": {
            symbol: {
                "close_time": iso_ms(resume_rows[symbol]["close_ms"])
                if symbol in resume_rows
                else None,
                "standard_close": (
                    symbol in resume_rows
                    and resume_rows[symbol]["close_ms"] == RESUME_OPEN_MS + MINUTE_MS - 1
                ),
                "quote_volume": (
                    resume_rows[symbol]["quote_volume"] if symbol in resume_rows else None
                ),
                "number_of_trades": (
                    resume_rows[symbol]["number_of_trades"] if symbol in resume_rows else None
                ),
            }
            for symbol in SYMBOLS
        },
        "gates": gate_values,
        "all_gates_passed": all_passed,
        "decision": decision,
        "next_stage": next_stage,
    }
    write_json(
        output / "semantic-maintenance-evidence.json",
        evidence,
    )

    report = {
        "schema_version": ("rd37-p1e-semantic-maintenance-diagnosis-report-v1"),
        "stage": "RD37_P1E_SEMANTIC_MAINTENANCE_DIAGNOSIS",
        "status": "PASS",
        "diagnosis_passed": all_passed,
        "decision": decision,
        "next_stage": next_stage,
        "source_p1d_results_commit": P1D_RESULTS_COMMIT,
        "passed_gate_count": sum(gate_values.values()),
        "gate_count": len(GATES),
        "failed_gates": [gate for gate, value in gate_values.items() if not value],
        "maintenance_blackout_start": ("2023-03-24T11:38:00+00:00"),
        "maintenance_blackout_end_exclusive": ("2023-03-24T14:00:00+00:00"),
        "source_semantics_if_pass": {
            "state": "BINANCE_INFO_UNAVAILABLE",
            "observed_rows_inside_blackout_usable": False,
            "imputation": "FORBIDDEN",
            "forward_fill": "FORBIDDEN",
            "backfill": "FORBIDDEN",
            "carry_forward": "FORBIDDEN",
            "same_bar_cross_venue_use": "FORBIDDEN",
            "feature_warmup": (
                "Lookback L requires L consecutive observed post-blackout "
                "1m bars beginning at or after 14:00 UTC."
            ),
        },
        "feature_computation_performed": False,
        "forward_returns_computed": False,
        "alpha_results_observed": False,
        "economic_execution_performed": False,
        "network_access_performed": False,
        "2024_accessed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
        "final_rd37_source_integrity_diagnosis": True,
    }
    write_json(
        output / "rd37-p1e-semantic-maintenance-diagnosis-report-v1.json",
        report,
    )

    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
