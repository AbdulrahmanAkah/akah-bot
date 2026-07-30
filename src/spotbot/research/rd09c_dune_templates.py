"""Local-only validation for frozen RD09C parameterized Dune SQL templates."""

from __future__ import annotations

import csv
import hashlib
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

REPOSITORY_ROOT: Final = Path(__file__).resolve().parents[3]
SOURCE_DIRECTORY: Final = REPOSITORY_ROOT / "reports" / "research" / "rd09b-v2-queries"
TEMPLATE_DIRECTORY: Final = REPOSITORY_ROOT / "reports" / "research" / "rd09c-dune-templates"
DATA_DIRECTORY: Final = REPOSITORY_ROOT / "data" / "research" / "rd09c"

MINIMUM_START: Final = "2021-01-01T00:00:00Z"
MAXIMUM_END_EXCLUSIVE: Final = "2025-01-01T00:00:00Z"
MAXIMUM_SINGLE_RANGE_DAYS: Final = 366
PARAMETER_NAMES: Final[tuple[str, str]] = ("start_date", "end_date")
EXPECTED_COLUMNS: Final[tuple[str, ...]] = (
    "day",
    "successful_transaction_count",
    "unique_sending_addresses",
    "unique_receiving_addresses",
    "unique_active_addresses",
    "native_fees_paid",
    "block_count",
    "native_transfer_count",
)
PARAMETER_PATTERN: Final = re.compile(r"\{\{([a-z_]+)\}\}")
BOUNDS_PATTERN: Final = re.compile(r"WITH bounds AS \(.*?\),\r?\n", re.DOTALL)
COMMENT_PATTERN: Final = re.compile(r"(?m)^--.*(?:\r?\n|$)")


@dataclass(frozen=True)
class DuneTemplateSpec:
    """Immutable local contract for one native-chain daily SQL template."""

    sequence: int
    namespace: str
    asset: str
    canonical_dune_name: str
    source_filename: str
    template_filename: str
    required_tables: tuple[str, ...]
    expected_columns: tuple[str, ...]
    optional_columns: tuple[str, ...]
    template_sha256: str
    minimum_start: str = MINIMUM_START
    maximum_end_exclusive: str = MAXIMUM_END_EXCLUSIVE

    @property
    def source_path(self) -> Path:
        return SOURCE_DIRECTORY / self.source_filename

    @property
    def template_path(self) -> Path:
        return TEMPLATE_DIRECTORY / self.template_filename


@dataclass(frozen=True)
class TemplateValidationResult:
    """Deterministic local validation result for one template."""

    namespace: str
    source_sha256: str
    template_sha256: str
    normalized_logic_match: bool
    parameter_count: int
    start_parameter_present: bool
    end_parameter_present: bool
    forbidden_literal_date_count: int
    required_table_match: bool
    final_schema_match: bool
    status: str
    failure_reason: str


_SPECS: Final[tuple[DuneTemplateSpec, ...]] = (
    DuneTemplateSpec(
        1,
        "bitcoin",
        "BTC",
        "AKAH_NATIVE_BITCOIN_DAILY",
        "bitcoin_2022_03.sql",
        "bitcoin_daily.sql",
        ("bitcoin.transactions", "bitcoin.blocks"),
        EXPECTED_COLUMNS,
        ("unique_sending_addresses", "unique_receiving_addresses", "unique_active_addresses"),
        "",
    ),
    DuneTemplateSpec(
        2,
        "ethereum",
        "ETH",
        "AKAH_NATIVE_ETHEREUM_DAILY",
        "ethereum_2022_03.sql",
        "ethereum_daily.sql",
        ("ethereum.transactions", "ethereum.blocks"),
        EXPECTED_COLUMNS,
        (),
        "",
    ),
    DuneTemplateSpec(
        3,
        "cardano",
        "ADA",
        "AKAH_NATIVE_CARDANO_DAILY",
        "cardano_2022_03.sql",
        "cardano_daily.sql",
        ("cardano.transaction", "cardano.block"),
        EXPECTED_COLUMNS,
        ("unique_sending_addresses", "unique_receiving_addresses", "unique_active_addresses"),
        "",
    ),
    DuneTemplateSpec(
        4,
        "avalanche_c",
        "AVAX",
        "AKAH_NATIVE_AVALANCHE_C_DAILY",
        "avalanche_c_2022_03.sql",
        "avalanche_c_daily.sql",
        ("avalanche_c.transactions", "avalanche_c.blocks"),
        EXPECTED_COLUMNS,
        (),
        "",
    ),
    DuneTemplateSpec(
        5,
        "polkadot",
        "DOT",
        "AKAH_NATIVE_POLKADOT_DAILY",
        "polkadot_2022_03.sql",
        "polkadot_daily.sql",
        ("polkadot.extrinsics", "polkadot.blocks"),
        EXPECTED_COLUMNS,
        ("unique_receiving_addresses", "unique_active_addresses"),
        "",
    ),
)


def template_sha256(path: Path) -> str:
    """Return the SHA-256 of a UTF-8 SQL template without modifying it."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def registered_templates() -> tuple[DuneTemplateSpec, ...]:
    """Return the five registered specs with current local template hashes."""
    return tuple(
        replace(spec, template_sha256=template_sha256(spec.template_path)) for spec in _SPECS
    )


def _utc_timestamp(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include a timezone")
    return parsed.astimezone(UTC)


def validate_requested_range(start: str | datetime, end: str | datetime) -> None:
    """Fail closed for any local rendering range outside the frozen research lock."""
    start_utc = _utc_timestamp(start)
    end_utc = _utc_timestamp(end)
    minimum = _utc_timestamp(MINIMUM_START)
    maximum = _utc_timestamp(MAXIMUM_END_EXCLUSIVE)
    if start_utc >= end_utc:
        raise ValueError("start must be before end")
    if start_utc < minimum:
        raise ValueError("start precedes the allowed research interval")
    if start_utc >= maximum:
        raise ValueError("start is in the prohibited 2025-or-later interval")
    if end_utc > maximum:
        raise ValueError("end exceeds the exclusive 2025 research boundary")
    if (end_utc - start_utc).total_seconds() / 86400 > MAXIMUM_SINGLE_RANGE_DAYS:
        raise ValueError("requested range exceeds the 366-day acquisition maximum")


def render_template_for_local_validation(
    spec: DuneTemplateSpec, start: str | datetime, end: str | datetime
) -> str:
    """Render a copy for text validation only; this function never executes SQL."""
    validate_requested_range(start, end)
    rendered = spec.template_path.read_text(encoding="utf-8")
    start_text = _utc_timestamp(start).strftime("%Y-%m-%d %H:%M:%S")
    end_text = _utc_timestamp(end).strftime("%Y-%m-%d %H:%M:%S")
    return rendered.replace("{{start_date}}", start_text).replace("{{end_date}}", end_text)


def _normalise_sql_logic(sql: str) -> str:
    without_comments = COMMENT_PATTERN.sub("", sql.replace("\r\n", "\n"))
    without_bounds = BOUNDS_PATTERN.sub(
        "WITH bounds AS (<RD09C_BOUNDS>),\n", without_comments, count=1
    )
    return without_bounds.strip()


def _bounds_block(sql: str) -> str:
    match = BOUNDS_PATTERN.search(sql)
    if match is None:
        return ""
    return match.group(0)


def validate_template_sql(spec: DuneTemplateSpec) -> TemplateValidationResult:
    """Validate permitted bounds-only drift from the immutable RD09B source SQL."""
    source_sql = spec.source_path.read_text(encoding="utf-8")
    template_sql = spec.template_path.read_text(encoding="utf-8")
    parameters = tuple(PARAMETER_PATTERN.findall(template_sql))
    expected_parameter_block = (
        "CAST('{{start_date}}' AS TIMESTAMP) AS start_utc" in template_sql
        and "CAST('{{end_date}}' AS TIMESTAMP) AS end_utc" in template_sql
    )
    forbidden_literals = len(
        re.findall(r"TIMESTAMP\s+'20(?:22|23|24)-\d{2}-\d{2}", _bounds_block(template_sql))
    )
    logic_match = _normalise_sql_logic(source_sql) == _normalise_sql_logic(template_sql)
    table_match = all(table in template_sql for table in spec.required_tables)
    schema_match = all(column in template_sql for column in spec.expected_columns)
    checks = (
        logic_match,
        parameters == PARAMETER_NAMES,
        expected_parameter_block,
        forbidden_literals == 0,
        table_match,
        schema_match,
    )
    failures: list[str] = []
    if not logic_match:
        failures.append("NON_BOUNDS_SQL_LOGIC_DRIFT")
    if parameters != PARAMETER_NAMES:
        failures.append("INVALID_PARAMETER_SET")
    if not expected_parameter_block:
        failures.append("INVALID_BOUNDS_CAST")
    if forbidden_literals != 0:
        failures.append("HARDCODED_PILOT_DATE_IN_BOUNDS")
    if not table_match:
        failures.append("REQUIRED_TABLE_MISMATCH")
    if not schema_match:
        failures.append("FINAL_SCHEMA_MISMATCH")
    return TemplateValidationResult(
        namespace=spec.namespace,
        source_sha256=template_sha256(spec.source_path),
        template_sha256=template_sha256(spec.template_path),
        normalized_logic_match=logic_match,
        parameter_count=len(parameters),
        start_parameter_present="start_date" in parameters,
        end_parameter_present="end_date" in parameters,
        forbidden_literal_date_count=forbidden_literals,
        required_table_match=table_match,
        final_schema_match=schema_match,
        status="PASS" if all(checks) else "FAIL",
        failure_reason="" if all(checks) else ";".join(failures),
    )


def source_reconciliation_rows() -> list[dict[str, str | int | bool]]:
    """Produce the fixed five-row reconciliation report without external access."""
    rows: list[dict[str, str | int | bool]] = []
    for spec in registered_templates():
        result = validate_template_sql(spec)
        rows.append(
            {
                "namespace": spec.namespace,
                "source_sql_path": spec.source_path.as_posix(),
                "template_sql_path": spec.template_path.as_posix(),
                "source_sha256": result.source_sha256,
                "template_sha256": result.template_sha256,
                "normalized_logic_match": result.normalized_logic_match,
                "parameter_count": result.parameter_count,
                "start_parameter_present": result.start_parameter_present,
                "end_parameter_present": result.end_parameter_present,
                "forbidden_literal_date_count": result.forbidden_literal_date_count,
                "required_table_match": result.required_table_match,
                "final_schema_match": result.final_schema_match,
                "status": result.status,
                "failure_reason": result.failure_reason,
            }
        )
    return rows


def _write_csv(
    path: Path,
    fieldnames: tuple[str, ...],
    rows: Sequence[Mapping[str, object]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_template_manifest(path: Path | None = None) -> list[dict[str, object]]:
    """Write the local five-row template registry with no Dune identifiers."""
    destination = path or DATA_DIRECTORY / "dune-template-registry-v1.csv"
    rows: list[dict[str, object]] = []
    for spec in registered_templates():
        result = validate_template_sql(spec)
        rows.append(
            {
                "sequence": spec.sequence,
                "namespace": spec.namespace,
                "asset": spec.asset,
                "canonical_dune_name": spec.canonical_dune_name,
                "template_path": spec.template_path.as_posix(),
                "template_sha256": spec.template_sha256,
                "required_tables": ";".join(spec.required_tables),
                "expected_columns": ";".join(spec.expected_columns),
                "optional_columns": ";".join(spec.optional_columns),
                "minimum_start": spec.minimum_start,
                "maximum_end_exclusive": spec.maximum_end_exclusive,
                "maximum_single_range_days": MAXIMUM_SINGLE_RANGE_DAYS,
                "parameter_names": ";".join(PARAMETER_NAMES),
                "local_validation_status": result.status,
                "dune_query_id": "",
                "dune_url": "",
                "browser_creation_status": "NOT_STARTED",
                "browser_execution_status": "NOT_STARTED",
            }
        )
    fields = (
        "sequence",
        "namespace",
        "asset",
        "canonical_dune_name",
        "template_path",
        "template_sha256",
        "required_tables",
        "expected_columns",
        "optional_columns",
        "minimum_start",
        "maximum_end_exclusive",
        "maximum_single_range_days",
        "parameter_names",
        "local_validation_status",
        "dune_query_id",
        "dune_url",
        "browser_creation_status",
        "browser_execution_status",
    )
    _write_csv(destination, fields, rows)
    return rows


def write_source_reconciliation(path: Path | None = None) -> list[dict[str, str | int | bool]]:
    """Write the deterministic source/template reconciliation report."""
    destination = path or DATA_DIRECTORY / "template-source-reconciliation.csv"
    rows = source_reconciliation_rows()
    fields = (
        "namespace",
        "source_sql_path",
        "template_sql_path",
        "source_sha256",
        "template_sha256",
        "normalized_logic_match",
        "parameter_count",
        "start_parameter_present",
        "end_parameter_present",
        "forbidden_literal_date_count",
        "required_table_match",
        "final_schema_match",
        "status",
        "failure_reason",
    )
    _write_csv(destination, fields, rows)
    return rows


def write_acquisition_plan(path: Path | None = None) -> list[dict[str, object]]:
    """Register exactly one unapproved local browser-validation request."""
    destination = path or DATA_DIRECTORY / "acquisition-plan-v1.csv"
    fields = (
        "sequence",
        "request_id",
        "namespace",
        "start",
        "end_exclusive",
        "expected_day_count",
        "authorized",
        "status",
        "dune_query_id",
        "credits_before",
        "credits_after",
        "credits_consumed",
        "result_path",
    )
    rows: list[dict[str, object]] = [
        {
            "sequence": 1,
            "request_id": "bitcoin_2022_03_browser_validation",
            "namespace": "bitcoin",
            "start": "2022-03-01T00:00:00Z",
            "end_exclusive": "2022-04-01T00:00:00Z",
            "expected_day_count": 31,
            "authorized": False,
            "status": "REGISTERED_NOT_AUTHORIZED",
            "dune_query_id": "",
            "credits_before": "",
            "credits_after": "",
            "credits_consumed": "",
            "result_path": "data/research/rd09c/browser-pilot/bitcoin_2022_03.csv",
        }
    ]
    _write_csv(destination, fields, rows)
    return rows
