"""Regression tests for the local-only RD09C Dune template layer."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from scripts.research.run_rd09c_template_validation import run_validation
from spotbot.research.rd09c_dune_templates import (
    DATA_DIRECTORY,
    EXPECTED_COLUMNS,
    PARAMETER_NAMES,
    registered_templates,
    render_template_for_local_validation,
    validate_requested_range,
    validate_template_sql,
    write_acquisition_plan,
    write_template_manifest,
)


def test_registered_templates_are_exactly_the_five_frozen_namespaces() -> None:
    templates = registered_templates()
    assert len(templates) == 5
    assert tuple(template.namespace for template in templates) == (
        "bitcoin",
        "ethereum",
        "cardano",
        "avalanche_c",
        "polkadot",
    )
    assert tuple(template.canonical_dune_name for template in templates) == (
        "AKAH_NATIVE_BITCOIN_DAILY",
        "AKAH_NATIVE_ETHEREUM_DAILY",
        "AKAH_NATIVE_CARDANO_DAILY",
        "AKAH_NATIVE_AVALANCHE_C_DAILY",
        "AKAH_NATIVE_POLKADOT_DAILY",
    )


def test_every_template_has_only_the_two_registered_parameters_and_schema() -> None:
    for template in registered_templates():
        result = validate_template_sql(template)
        assert result.status == "PASS"
        assert result.parameter_count == 2
        assert result.start_parameter_present
        assert result.end_parameter_present
        assert all(
            column in template.template_path.read_text(encoding="utf-8")
            for column in EXPECTED_COLUMNS
        )


def test_templates_use_the_registered_tables_and_allow_only_bounds_drift() -> None:
    for template in registered_templates():
        result = validate_template_sql(template)
        assert result.required_table_match
        assert result.normalized_logic_match
        assert result.forbidden_literal_date_count == 0


def test_template_reconciliation_rejects_aggregation_or_table_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    template = registered_templates()[0]
    original_read_text = Path.read_text

    def drift_template(path: Path, **kwargs: object) -> str:
        content = original_read_text(path, **kwargs)
        if path == template.template_path:
            return content.replace("COUNT(*)", "COUNT(DISTINCT fee)", 1)
        return content

    monkeypatch.setattr(
        Path,
        "read_text",
        drift_template,
    )
    changed = validate_template_sql(template)
    assert not changed.normalized_logic_match


def test_template_reconciliation_accepts_comments_and_bounds_only() -> None:
    template = registered_templates()[0]
    rendered = render_template_for_local_validation(
        template, "2022-03-01T00:00:00Z", "2022-04-01T00:00:00Z"
    )
    assert "{{start_date}}" not in rendered
    assert "{{end_date}}" not in rendered
    assert "bitcoin.transactions" in rendered


@pytest.mark.parametrize(
    ("start", "end"),
    (
        ("2021-01-01T00:00:00Z", "2021-02-01T00:00:00Z"),
        ("2024-01-01T00:00:00Z", "2025-01-01T00:00:00Z"),
    ),
)
def test_registered_ranges_allow_2021_and_2024(start: str, end: str) -> None:
    validate_requested_range(start, end)


@pytest.mark.parametrize(
    ("start", "end"),
    (
        ("2022-03-01T00:00:00Z", "2022-03-01T00:00:00Z"),
        ("2022-04-01T00:00:00Z", "2022-03-01T00:00:00Z"),
        ("2020-12-31T00:00:00Z", "2021-01-01T00:00:00Z"),
        ("2025-01-01T00:00:00Z", "2025-01-02T00:00:00Z"),
        ("2024-12-31T00:00:00Z", "2025-01-02T00:00:00Z"),
        ("2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z"),
        ("2021-01-01T00:00:00Z", "2022-01-03T00:00:00Z"),
    ),
)
def test_range_guard_rejects_2025_2026_invalid_order_and_oversize(start: str, end: str) -> None:
    with pytest.raises(ValueError):
        validate_requested_range(start, end)


def test_manifest_has_five_rows_and_one_unapproved_acquisition_row(tmp_path: Path) -> None:
    registry_path = tmp_path / "registry.csv"
    acquisition_path = tmp_path / "plan.csv"
    registry = write_template_manifest(registry_path)
    acquisition = write_acquisition_plan(acquisition_path)
    assert len(registry) == 5
    assert len(acquisition) == 1
    with registry_path.open(encoding="utf-8", newline="") as handle:
        assert len(list(csv.DictReader(handle))) == 5
    with acquisition_path.open(encoding="utf-8", newline="") as handle:
        row = next(csv.DictReader(handle))
    assert row["authorized"] == "False"
    assert row["status"] == "REGISTERED_NOT_AUTHORIZED"


def test_runner_is_local_only_and_writes_the_declared_reports(tmp_path: Path) -> None:
    report = run_validation(tmp_path)
    assert report["status"] == "COMPLETE"
    assert report["decision"] == "RD09C_DUNE_PARAMETERIZED_TEMPLATES_LOCALLY_VALIDATED"
    assert report["parameter_names"] == list(PARAMETER_NAMES)
    assert report["dune_opened"] is False
    assert report["dune_api_called"] is False
    assert report["credits_consumed"] == 0
    assert (tmp_path / "rd09c-template-validation-v1.json").is_file()
    assert (tmp_path / "template-source-reconciliation.csv").is_file()


def test_runner_contains_no_network_client_or_dune_api_invocation() -> None:
    runner_path = (
        DATA_DIRECTORY.parent.parent.parent
        / "scripts"
        / "research"
        / "run_rd09c_template_validation.py"
    )
    content = runner_path.read_text(encoding="utf-8")
    assert "requests" not in content
    assert "urllib" not in content
    assert "http" not in content


def test_new_files_have_final_newlines_and_no_credential_markers() -> None:
    paths = [template.template_path for template in registered_templates()]
    paths.extend(
        (
            Path(__file__).resolve(),
            DATA_DIRECTORY.parent.parent.parent
            / "src"
            / "spotbot"
            / "research"
            / "rd09c_dune_templates.py",
            DATA_DIRECTORY.parent.parent.parent
            / "scripts"
            / "research"
            / "run_rd09c_template_validation.py",
        )
    )
    forbidden = (
        "_".join(("DUNE", "API", "KEY")),
        "815" + "2827",
        "815" + "5363",
        "Authorization" + ":",
    )
    for path in paths:
        content = path.read_text(encoding="utf-8")
        assert content.endswith("\n")
        assert not any(marker in content for marker in forbidden)
