from __future__ import annotations

import csv
import json
import shutil
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final, cast

import pandas as pd

from spotbot.research.rd16c_common import (
    BRANCH,
    ROOT,
    SEALED_CUTOFF,
    dataframe_content_hash,
    read_json_object,
    sha256_path,
)
from spotbot.research.rd16i_architecture import (
    ARCHITECTURE_ID,
    BASE_RISK_PER_TRADE_FRACTION,
    COMPRESSION_COOLDOWN_HOURS,
    COMPRESSION_ENGINE_ID,
    EXPANDED_RISK_PER_TRADE_FRACTION,
    MAXIMUM_OPEN_RISK_FRACTION,
    MAXIMUM_POSITIONS,
    SOURCE_ARCHITECTURE_ID,
    SOURCE_VARIANT_ID,
    TREND_COOLDOWN_HOURS,
    TREND_ENGINE_ID,
    diagnostic_metrics,
    engine_cooldowns_respected,
    maximum_open_risk_respected,
    maximum_positions_respected,
    position_capacity_rows,
    route_v2_candidates,
    same_symbol_overlap_absent,
)

SCHEMA_VERSION: Final = "rd16i-registered-composite-alpha-v2-v1"
DECISION: Final = "RD16I_REGISTERED_COMPOSITE_ALPHA_V2_ARCHITECTURE_COMPLETED"
EVIDENCE_CLASSIFICATION: Final = "READY_FOR_FIXED_COMPOSITE_ALPHA_V2_BASELINE"
NEXT_STAGE: Final = "RD16J_FIXED_COMPOSITE_ALPHA_V2_BASELINE_EVALUATION"

RD16H_ROOT: Final = ROOT / "data" / "research" / "rd16h"
RD16H_LOCAL_ROOT: Final = ROOT / "data" / "raw" / "rd16h"
RD16I_ROOT: Final = ROOT / "data" / "research" / "rd16i"
RD16I_LOCAL_ROOT: Final = ROOT / "data" / "raw" / "rd16i"
REPORTS_ROOT: Final = ROOT / "reports" / "research"

REGISTRATION_FIELDS: Final = (
    "architecture_id",
    "source_architecture_id",
    "source_variant_id",
    "trend_engine_id",
    "compression_engine_id",
    "trend_cooldown_hours",
    "compression_cooldown_hours",
    "base_risk_per_trade_fraction",
    "expanded_risk_per_trade_fraction",
    "maximum_open_risk_fraction",
    "maximum_positions",
    "previous_maximum_positions",
    "capacity_change_source",
)
PROVENANCE_FIELDS: Final = (
    "source_variant_id",
    "rd16h_decision",
    "carry_forward",
    "verified",
    "source_candidate_count",
    "source_candidate_content_sha256",
)
CONSTRAINT_FIELDS: Final = (
    "architecture_id",
    "spot_only",
    "long_only",
    "no_leverage",
    "no_margin",
    "no_short",
    "no_derivatives",
    "no_dca",
    "no_kelly",
    "no_pyramiding",
    "no_averaging_down",
    "same_symbol_overlap_absent",
    "engine_cooldowns_respected",
    "maximum_positions_configured",
    "maximum_positions_observed",
    "maximum_positions_respected",
    "maximum_open_risk_fraction_configured",
    "maximum_open_risk_fraction_observed",
    "maximum_open_risk_respected",
    "outcome_based_routing",
    "sealed_cutoff_respected",
)
ROUTING_FIELDS: Final = (
    "architecture_id",
    "engine_id",
    "router_decision",
    "candidate_count",
    "fraction_of_engine_candidates",
)
CAPACITY_FIELDS: Final = (
    "architecture_id",
    "positions_before",
    "router_decision",
    "candidate_count",
)


class RD16IRegistrationError(RuntimeError):
    pass


def _write_json(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(dict(payload), indent=2, sort_keys=True, allow_nan=False, default=str) + "\n",
        encoding="utf-8",
    )


def _write_csv(
    path: Path,
    rows: Sequence[Mapping[str, object]],
    *,
    fieldnames: Sequence[str],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(fieldnames),
            extrasaction="ignore",
            lineterminator="\n",
        )
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field) for field in fieldnames})


def _verify_rd16h_ready() -> dict[str, Any]:
    report = read_json_object(RD16H_ROOT / "rd16h-final-report-v1.json")
    expected = {
        "decision": (
            "RD16H_COMPOSITE_ALPHA_RETURN_EXPANSION_AND_BULL_CAPTURE_REMEDIATION_COMPLETED"
        ),
        "technical_status": "COMPLETED",
        "evidence_classification": "RETURN_EXPANSION_EVIDENCE_EXTRACTED",
        "architecture_id": SOURCE_ARCHITECTURE_ID,
        "variants_evaluated": 10,
        "retained_variant_count": 3,
        "strategic_objective_met_count": 0,
        "next_stage": "RD16I_REGISTERED_COMPOSITE_ALPHA_V2_ARCHITECTURE",
    }
    for key, expected_value in expected.items():
        if report.get(key) != expected_value:
            raise RD16IRegistrationError(
                f"RD16-H readiness mismatch for {key}: {report.get(key)!r}"
            )
    retained = report.get("retained_variants")
    if not isinstance(retained, list) or SOURCE_VARIANT_ID not in retained:
        raise RD16IRegistrationError(f"RD16-H did not retain {SOURCE_VARIANT_ID}.")
    technical = report.get("technical_gates")
    if not isinstance(technical, dict):
        raise RD16IRegistrationError("RD16-H technical_gates is missing.")
    for key in (
        "rd16g_ready",
        "rd16g_outputs_verified",
        "rd16f_local_ledgers_verified",
        "rd16e_component_ledgers_verified",
        "deterministic_replay_match",
        "frozen_inputs_unchanged",
        "sealed_cutoff_respected",
        "same_symbol_overlap_prohibited",
        "risk_multipliers_non_compounding",
        "maximum_positions_three",
        "spot_only",
        "long_only",
    ):
        if technical.get(key) is not True:
            raise RD16IRegistrationError(f"RD16-H technical gate failed: {key}")
    for key in (
        "test_2025_accessed",
        "holdout_2026_accessed",
        "dune_api_called",
        "optimization_performed",
        "winner_selected",
        "production_authorized",
    ):
        if technical.get(key) is True:
            raise RD16IRegistrationError(f"RD16-H forbidden flag is true: {key}")
    return report


def _verify_rd16h_tracked_outputs() -> dict[str, str]:
    manifest = read_json_object(RD16H_ROOT / "output-hashes.json")
    verified: dict[str, str] = {}
    for raw_name, raw_digest in sorted(manifest.items()):
        if not isinstance(raw_name, str) or not isinstance(raw_digest, str):
            raise RD16IRegistrationError("RD16-H output hash manifest is invalid.")
        data_path = RD16H_ROOT / raw_name
        report_path = REPORTS_ROOT / raw_name
        if data_path.is_file():
            path = data_path
        elif report_path.is_file():
            path = report_path
        else:
            raise RD16IRegistrationError(f"Missing RD16-H output: {raw_name}")
        actual = sha256_path(path)
        if actual != raw_digest:
            raise RD16IRegistrationError(
                f"RD16-H output hash mismatch for {raw_name}: {actual} != {raw_digest}"
            )
        verified[f"rd16h:{raw_name}"] = actual
    return verified


def _component_decision() -> dict[str, str]:
    path = RD16H_ROOT / "component-decisions.csv"
    if not path.is_file():
        raise RD16IRegistrationError(f"Missing RD16-H component decisions: {path}")
    with path.open("r", encoding="utf-8", newline="") as handle:
        for raw in csv.DictReader(handle):
            if raw.get("variant_id") == SOURCE_VARIANT_ID:
                return {str(key): "" if value is None else str(value) for key, value in raw.items()}
    raise RD16IRegistrationError(f"Missing RD16-H decision row for {SOURCE_VARIANT_ID}.")


def _source_candidate_entry() -> dict[str, object]:
    manifest = read_json_object(RD16H_ROOT / "local-output-manifest-v1.json")
    raw_variants = manifest.get("variants")
    if not isinstance(raw_variants, dict):
        raise RD16IRegistrationError("RD16-H local manifest variants are invalid.")
    raw_variant = cast(dict[str, object], raw_variants).get(SOURCE_VARIANT_ID)
    if not isinstance(raw_variant, dict):
        raise RD16IRegistrationError(f"RD16-H local manifest is missing {SOURCE_VARIANT_ID}.")
    raw_candidates = cast(dict[str, object], raw_variant).get("candidates")
    if not isinstance(raw_candidates, dict):
        raise RD16IRegistrationError("RD16-H source candidate entry is missing.")
    return cast(dict[str, object], raw_candidates)


def _load_source_candidates() -> tuple[pd.DataFrame, dict[str, object]]:
    entry = _source_candidate_entry()
    relative = entry.get("logical_path")
    rows = entry.get("rows")
    file_hash = entry.get("file_sha256")
    content_hash = entry.get("content_sha256")
    if not isinstance(relative, str):
        raise RD16IRegistrationError("Invalid RD16-H candidate path.")
    path = RD16H_LOCAL_ROOT / relative
    if not path.is_file():
        raise RD16IRegistrationError(f"Missing RD16-H local candidates: {path}")
    actual_file_hash = sha256_path(path)
    if not isinstance(file_hash, str) or actual_file_hash != file_hash:
        raise RD16IRegistrationError("RD16-H candidate file hash mismatch.")
    frame = pd.read_parquet(str(path))
    if not isinstance(rows, int) or len(frame) != rows:
        raise RD16IRegistrationError("RD16-H candidate row count mismatch.")
    actual_content_hash = dataframe_content_hash(frame)
    if not isinstance(content_hash, str) or actual_content_hash != content_hash:
        raise RD16IRegistrationError("RD16-H candidate content hash mismatch.")
    return frame, {
        "logical_path": relative,
        "rows": rows,
        "file_sha256": actual_file_hash,
        "content_sha256": actual_content_hash,
    }


def _frozen_input_hashes(source_info: Mapping[str, object]) -> dict[str, str]:
    tracked = {
        "rd16h/rd16h-protocol-v1.json": RD16H_ROOT / "rd16h-protocol-v1.json",
        "rd16h/rd16h-final-report-v1.json": RD16H_ROOT / "rd16h-final-report-v1.json",
        "rd16h/validation-report.json": RD16H_ROOT / "validation-report.json",
        "rd16h/output-hashes.json": RD16H_ROOT / "output-hashes.json",
        "rd16h/component-decisions.csv": RD16H_ROOT / "component-decisions.csv",
        "rd16h/local-output-manifest-v1.json": (RD16H_ROOT / "local-output-manifest-v1.json"),
    }
    hashes: dict[str, str] = {}
    for name, path in tracked.items():
        if not path.is_file():
            raise RD16IRegistrationError(f"Frozen RD16-I input missing: {path}")
        hashes[name] = sha256_path(path)
    hashes.update(_verify_rd16h_tracked_outputs())
    source_file_hash = source_info.get("file_sha256")
    if not isinstance(source_file_hash, str):
        raise RD16IRegistrationError("Source candidate file hash is invalid.")
    hashes[f"local:rd16h:{SOURCE_VARIANT_ID}:candidates"] = source_file_hash
    return dict(sorted(hashes.items()))


def _sealed_cutoff_respected(*frames: pd.DataFrame) -> bool:
    cutoff = pd.Timestamp(SEALED_CUTOFF)
    for frame in frames:
        for column in ("signal_close", "entry_open_time", "exit_bar_close"):
            if column not in frame.columns or frame.empty:
                continue
            parsed = pd.to_datetime(frame[column], utc=True, errors="raise")
            if bool((parsed >= cutoff).any()):
                return False
    return True


def _routing_rows(evaluated: pd.DataFrame) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for raw_engine, engine in evaluated.groupby("engine_id", sort=True):
        total = len(engine)
        for raw_decision, group in engine.groupby("router_decision", sort=True):
            rows.append(
                {
                    "architecture_id": ARCHITECTURE_ID,
                    "engine_id": str(raw_engine),
                    "router_decision": str(raw_decision),
                    "candidate_count": len(group),
                    "fraction_of_engine_candidates": (len(group) / total if total else None),
                }
            )
    return rows


def _local_entry(path: Path, frame: pd.DataFrame) -> dict[str, object]:
    return {
        "logical_path": str(path.relative_to(RD16I_LOCAL_ROOT)).replace("\\", "/"),
        "rows": len(frame),
        "file_sha256": sha256_path(path),
        "content_sha256": dataframe_content_hash(frame),
    }


def _save_local_outputs(
    candidates: pd.DataFrame,
    evaluated: pd.DataFrame,
    trades: pd.DataFrame,
) -> dict[str, object]:
    if RD16I_LOCAL_ROOT.exists():
        shutil.rmtree(RD16I_LOCAL_ROOT)
    RD16I_LOCAL_ROOT.mkdir(parents=True, exist_ok=True)
    entries: dict[str, object] = {}
    for name, frame in (
        ("candidates", candidates),
        ("evaluated", evaluated),
        ("trades", trades),
    ):
        path = RD16I_LOCAL_ROOT / f"composite-v2-{name}.parquet"
        frame.to_parquet(path, index=False, engine="pyarrow")
        entries[name] = _local_entry(path, frame)
    return {
        "schema_version": SCHEMA_VERSION,
        "root_committed": False,
        "architecture_id": ARCHITECTURE_ID,
        "source_variant_id": SOURCE_VARIANT_ID,
        "entries": entries,
    }


def _content_hashes_match(
    first: Mapping[str, pd.DataFrame],
    second: Mapping[str, pd.DataFrame],
) -> bool:
    return all(
        dataframe_content_hash(first[name]) == dataframe_content_hash(second[name])
        for name in ("candidates", "evaluated", "trades")
    )


def _write_reports(
    *,
    final_report: Mapping[str, object],
    routing_rows: Sequence[Mapping[str, object]],
    capacity_rows: Sequence[Mapping[str, object]],
) -> tuple[Path, Path]:
    results_path = REPORTS_ROOT / "rd16i-composite-alpha-v2-registration-results-v1.md"
    audit_path = REPORTS_ROOT / "rd16i-causality-capacity-audit-v1.md"

    results = [
        "# RD16-I Composite Alpha V2 Registration Results v1",
        "",
        f"- Architecture: `{ARCHITECTURE_ID}`",
        f"- Source variant: `{SOURCE_VARIANT_ID}`",
        f"- Candidate count: {final_report['candidate_count']}",
        f"- Admitted trade count: {final_report['admitted_trade_count']}",
        f"- Maximum positions configured: {MAXIMUM_POSITIONS}",
        (f"- Maximum positions observed: {final_report['maximum_positions_observed']}"),
        (
            "- Maximum open-risk fraction observed: "
            f"{final_report['maximum_open_risk_fraction_observed']}"
        ),
        "",
        "This is registration evidence only. Economic performance is diagnostic and "
        "is not a pass gate.",
        "",
        f"Next stage: `{NEXT_STAGE}`",
    ]
    results_path.write_text("\n".join(results).rstrip() + "\n", encoding="utf-8")

    audit = [
        "# RD16-I Causality and Capacity Audit v1",
        "",
        "## User-directed capacity change",
        "",
        "- Previous maximum positions: 3",
        f"- Registered maximum positions: {MAXIMUM_POSITIONS}",
        "- Maximum open-risk fraction remains 2.25%.",
        "- Position capacity and open-risk capacity are independent gates.",
        "",
        "## Routing decisions",
        "",
        "| Engine | Decision | Candidates |",
        "|---|---|---:|",
    ]
    for row in routing_rows:
        audit.append(
            f"| {row['engine_id']} | {row['router_decision']} | {row['candidate_count']} |"
        )
    audit.extend(
        [
            "",
            "## Capacity states",
            "",
            "| Positions before | Decision | Candidates |",
            "|---:|---|---:|",
        ]
    )
    for row in capacity_rows:
        audit.append(
            f"| {row['positions_before']} | {row['router_decision']} | {row['candidate_count']} |"
        )
    audit.extend(
        [
            "",
            "Realized PnL, MFE, MAE, holding duration, and exit reason were not used "
            "to admit or reject candidates.",
        ]
    )
    audit_path.write_text("\n".join(audit).rstrip() + "\n", encoding="utf-8")
    return results_path, audit_path


def _output_hashes(paths: Sequence[Path]) -> dict[str, str]:
    return {path.name: sha256_path(path) for path in sorted(paths)}


def register_composite_alpha_v2() -> dict[str, object]:
    RD16I_ROOT.mkdir(parents=True, exist_ok=True)
    RD16I_LOCAL_ROOT.parent.mkdir(parents=True, exist_ok=True)

    rd16h_report = _verify_rd16h_ready()
    decision_row = _component_decision()
    source_verified = (
        decision_row.get("decision") == "RETAIN_FOR_COMPOSITE_V2_REGISTRATION"
        and decision_row.get("carry_forward") == "True"
    )
    if not source_verified:
        raise RD16IRegistrationError(f"RD16-H source decision is not retained: {decision_row}")

    source_candidates, source_info = _load_source_candidates()
    frozen_hashes = _frozen_input_hashes(source_info)

    first = route_v2_candidates(source_candidates)
    second = route_v2_candidates(source_candidates)
    deterministic = _content_hashes_match(
        {
            "candidates": first.candidates,
            "evaluated": first.evaluated,
            "trades": first.trades,
        },
        {
            "candidates": second.candidates,
            "evaluated": second.evaluated,
            "trades": second.trades,
        },
    )
    sealed = _sealed_cutoff_respected(
        first.candidates,
        first.evaluated,
        first.trades,
    )
    overlap_absent = same_symbol_overlap_absent(first.trades)
    cooldowns_ok = engine_cooldowns_respected(first.trades)
    positions_ok = maximum_positions_respected(first.evaluated)
    risk_ok = maximum_open_risk_respected(first.evaluated)

    diagnostics = diagnostic_metrics(first.trades)
    routing_rows = _routing_rows(first.evaluated)
    raw_capacity_rows = position_capacity_rows(first.evaluated)
    capacity_rows = [{"architecture_id": ARCHITECTURE_ID, **row} for row in raw_capacity_rows]

    registration_row = {
        "architecture_id": ARCHITECTURE_ID,
        "source_architecture_id": SOURCE_ARCHITECTURE_ID,
        "source_variant_id": SOURCE_VARIANT_ID,
        "trend_engine_id": TREND_ENGINE_ID,
        "compression_engine_id": COMPRESSION_ENGINE_ID,
        "trend_cooldown_hours": TREND_COOLDOWN_HOURS,
        "compression_cooldown_hours": COMPRESSION_COOLDOWN_HOURS,
        "base_risk_per_trade_fraction": BASE_RISK_PER_TRADE_FRACTION,
        "expanded_risk_per_trade_fraction": EXPANDED_RISK_PER_TRADE_FRACTION,
        "maximum_open_risk_fraction": MAXIMUM_OPEN_RISK_FRACTION,
        "maximum_positions": MAXIMUM_POSITIONS,
        "previous_maximum_positions": 3,
        "capacity_change_source": "explicit_user_instruction",
    }
    provenance_row = {
        "source_variant_id": SOURCE_VARIANT_ID,
        "rd16h_decision": decision_row.get("decision"),
        "carry_forward": decision_row.get("carry_forward"),
        "verified": source_verified,
        "source_candidate_count": len(source_candidates),
        "source_candidate_content_sha256": source_info["content_sha256"],
    }
    constraint_row = {
        "architecture_id": ARCHITECTURE_ID,
        "spot_only": True,
        "long_only": True,
        "no_leverage": True,
        "no_margin": True,
        "no_short": True,
        "no_derivatives": True,
        "no_dca": True,
        "no_kelly": True,
        "no_pyramiding": True,
        "no_averaging_down": True,
        "same_symbol_overlap_absent": overlap_absent,
        "engine_cooldowns_respected": cooldowns_ok,
        "maximum_positions_configured": MAXIMUM_POSITIONS,
        "maximum_positions_observed": first.maximum_positions_observed,
        "maximum_positions_respected": positions_ok,
        "maximum_open_risk_fraction_configured": MAXIMUM_OPEN_RISK_FRACTION,
        "maximum_open_risk_fraction_observed": (first.maximum_open_risk_fraction),
        "maximum_open_risk_respected": risk_ok,
        "outcome_based_routing": False,
        "sealed_cutoff_respected": sealed,
    }

    technical_gates = {
        "rd16h_ready": True,
        "rd16h_outputs_verified": True,
        "rd16h_local_source_verified": True,
        "source_variant_retained": source_verified,
        "deterministic_replay_match": deterministic,
        "frozen_inputs_unchanged": True,
        "sealed_cutoff_respected": sealed,
        "same_symbol_overlap_absent": overlap_absent,
        "engine_cooldowns_respected": cooldowns_ok,
        "maximum_positions_respected": positions_ok,
        "maximum_open_risk_respected": risk_ok,
        "maximum_positions_increased_above_three": MAXIMUM_POSITIONS > 3,
        "spot_only": True,
        "long_only": True,
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
        "dune_api_called": False,
        "optimization_performed": False,
        "winner_selected": False,
        "production_authorized": False,
        "economic_baseline_performed": False,
    }
    if not all(
        bool(technical_gates[key])
        for key in (
            "rd16h_ready",
            "rd16h_outputs_verified",
            "rd16h_local_source_verified",
            "source_variant_retained",
            "deterministic_replay_match",
            "frozen_inputs_unchanged",
            "sealed_cutoff_respected",
            "same_symbol_overlap_absent",
            "engine_cooldowns_respected",
            "maximum_positions_respected",
            "maximum_open_risk_respected",
            "maximum_positions_increased_above_three",
            "spot_only",
            "long_only",
        )
    ):
        raise RD16IRegistrationError(f"RD16-I technical gate failure: {technical_gates}")

    local_manifest = _save_local_outputs(
        first.candidates,
        first.evaluated,
        first.trades,
    )

    _write_csv(
        RD16I_ROOT / "architecture-registration.csv",
        [registration_row],
        fieldnames=REGISTRATION_FIELDS,
    )
    _write_csv(
        RD16I_ROOT / "source-provenance.csv",
        [provenance_row],
        fieldnames=PROVENANCE_FIELDS,
    )
    _write_csv(
        RD16I_ROOT / "constraint-audit.csv",
        [constraint_row],
        fieldnames=CONSTRAINT_FIELDS,
    )
    _write_csv(
        RD16I_ROOT / "routing-decision-summary.csv",
        routing_rows,
        fieldnames=ROUTING_FIELDS,
    )
    _write_csv(
        RD16I_ROOT / "position-capacity-audit.csv",
        capacity_rows,
        fieldnames=CAPACITY_FIELDS,
    )
    _write_json(RD16I_ROOT / "frozen-input-hashes.json", frozen_hashes)
    _write_json(
        RD16I_ROOT / "local-ledger-manifest-v1.json",
        local_manifest,
    )

    final_report: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "branch": BRANCH,
        "decision": DECISION,
        "technical_status": "COMPLETED",
        "evidence_classification": EVIDENCE_CLASSIFICATION,
        "architecture_id": ARCHITECTURE_ID,
        "source_architecture_id": SOURCE_ARCHITECTURE_ID,
        "source_variant_id": SOURCE_VARIANT_ID,
        "source_variant_verified": source_verified,
        "user_directed_capacity_change": True,
        "previous_maximum_positions": 3,
        "maximum_positions_configured": MAXIMUM_POSITIONS,
        "maximum_positions_observed": first.maximum_positions_observed,
        "maximum_open_risk_fraction_configured": MAXIMUM_OPEN_RISK_FRACTION,
        "maximum_open_risk_fraction_observed": (first.maximum_open_risk_fraction),
        "candidate_count": len(first.candidates),
        "admitted_trade_count": len(first.trades),
        "diagnostic_only": diagnostics,
        "economic_baseline_performed": False,
        "strategic_monthly_target": 0.24,
        "strategic_objective_evaluated": False,
        "optimization_performed": False,
        "winner_selected": False,
        "production_authorized": False,
        "technical_gates": technical_gates,
        "limitations": [
            "RD16-I is a registration and deterministic smoke-test stage.",
            (
                "The maximum position count increase from three to five is "
                "user-directed and was not validated in RD16-H."
            ),
            (
                "The unchanged 2.25% open-risk cap may reject a fourth or fifth "
                "position before the position-count limit is reached."
            ),
            "Diagnostic PnL is not an economic pass gate.",
            "2025 and 2026 remain sealed and were not accessed.",
        ],
        "next_stage": NEXT_STAGE,
        "rd16h_source_report_decision": rd16h_report["decision"],
    }

    results_path, audit_path = _write_reports(
        final_report=final_report,
        routing_rows=routing_rows,
        capacity_rows=capacity_rows,
    )
    _write_json(RD16I_ROOT / "rd16i-final-report-v1.json", final_report)

    validation_report = {
        "schema_version": SCHEMA_VERSION,
        "status": "PASS",
        "checks": technical_gates,
    }
    _write_json(RD16I_ROOT / "validation-report.json", validation_report)

    tracked_outputs = [
        RD16I_ROOT / "architecture-registration.csv",
        RD16I_ROOT / "source-provenance.csv",
        RD16I_ROOT / "constraint-audit.csv",
        RD16I_ROOT / "routing-decision-summary.csv",
        RD16I_ROOT / "position-capacity-audit.csv",
        RD16I_ROOT / "frozen-input-hashes.json",
        RD16I_ROOT / "local-ledger-manifest-v1.json",
        RD16I_ROOT / "rd16i-final-report-v1.json",
        RD16I_ROOT / "validation-report.json",
        results_path,
        audit_path,
    ]
    _write_json(
        RD16I_ROOT / "output-hashes.json",
        _output_hashes(tracked_outputs),
    )
    return final_report


__all__ = [
    "DECISION",
    "EVIDENCE_CLASSIFICATION",
    "NEXT_STAGE",
    "RD16IRegistrationError",
    "SCHEMA_VERSION",
    "register_composite_alpha_v2",
]
