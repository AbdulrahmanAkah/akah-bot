from __future__ import annotations

import csv
import hashlib
import json
import shutil
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final, cast

import pandas as pd

from spotbot.data.store import ParquetCandleStore
from spotbot.research.rd16c_common import (
    BRANCH,
    CONTEXT_TIMEFRAMES,
    EXCHANGE_ID,
    LOCAL_INPUT_ROOT,
    PILOT_SYMBOLS,
    ROOT,
    SEALED_CUTOFF,
    SIGNAL_TIMEFRAME,
    dataframe_content_hash,
    read_json_object,
    sha256_path,
)
from spotbot.research.rd16c_features import build_feature_frame
from spotbot.research.rd16d_common import write_csv, write_json
from spotbot.research.rd16e_components import apply_variant, attach_signal_features
from spotbot.research.rd16f_architecture import (
    ARCHITECTURE_ID,
    ENGINE_REGISTRY,
    MAXIMUM_OPEN_RISK_FRACTION,
    MAXIMUM_POSITIONS,
    SOURCE_COMPONENT_IDS,
    SOURCE_VARIANT,
    build_composite_candidates,
    diagnostic_metrics,
    global_cooldown_respected,
    route_composite_candidates,
    same_symbol_overlap_absent,
)

SCHEMA_VERSION: Final = "rd16f-registered-composite-alpha-v1"
DECISION_COMPLETED: Final = "RD16F_REGISTERED_INTRADAY_COMPOSITE_ALPHA_ARCHITECTURE_COMPLETED"
DECISION_REMEDIATE: Final = "RD16F_COMPOSITE_ALPHA_ARCHITECTURE_REMEDIATION_REQUIRED"
EVIDENCE_READY: Final = "READY_FOR_FIXED_COMPOSITE_BASELINE"
EVIDENCE_REMEDIATE: Final = "REMEDIATION_REQUIRED"
NEXT_READY: Final = "RD16G_FIXED_COMPOSITE_ALPHA_BASELINE_EVALUATION"
NEXT_REMEDIATE: Final = "RD16F_COMPOSITE_ALPHA_ARCHITECTURE_REMEDIATION"

RD16D_ROOT: Final = ROOT / "data" / "research" / "rd16d"
RD16E_ROOT: Final = ROOT / "data" / "research" / "rd16e"
RD16F_ROOT: Final = ROOT / "data" / "research" / "rd16f"
RD16D_LOCAL_ROOT: Final = ROOT / "data" / "raw" / "rd16d"
RD16F_LOCAL_ROOT: Final = ROOT / "data" / "raw" / "rd16f"
REPORTS_ROOT: Final = ROOT / "reports" / "research"

REGISTRATION_FIELDS: Final = (
    "architecture_id",
    "engine_id",
    "source_family_id",
    "source_variant_id",
    "source_component_id",
    "priority",
    "role",
    "fixed_rules",
)
COVERAGE_FIELDS: Final = (
    "engine_id",
    "symbol",
    "candidate_count",
    "admitted_trade_count",
    "first_signal_close",
    "last_signal_close",
)
ROUTING_FIELDS: Final = (
    "engine_id",
    "router_decision",
    "candidate_count",
    "fraction_of_engine_candidates",
)
PROVENANCE_FIELDS: Final = (
    "source_component_id",
    "rd16e_decision",
    "carry_forward",
    "verified",
)
CONSTRAINT_FIELDS: Final = (
    "architecture_id",
    "spot_only",
    "long_only",
    "no_leverage",
    "no_margin",
    "no_short",
    "no_dca",
    "no_kelly",
    "no_pyramiding",
    "no_averaging_down",
    "maximum_positions_respected",
    "maximum_open_risk_respected",
    "same_symbol_overlap_absent",
    "global_cooldown_respected",
    "exit_before_entry",
    "outcome_based_routing",
)


class RD16FRegistrationError(RuntimeError):
    pass


def _timestamp(value: object) -> pd.Timestamp:
    parsed = pd.Timestamp(cast(Any, value))
    if parsed.tzinfo is None:
        return parsed.tz_localize("UTC")
    return parsed.tz_convert("UTC")


def _verify_rd16e_ready() -> dict[str, Any]:
    report = read_json_object(RD16E_ROOT / "rd16e-final-report-v1.json")
    expected = {
        "decision": ("RD16E_INTRADAY_FAMILY_REMEDIATION_AND_COMPONENT_EXTRACTION_COMPLETED"),
        "technical_status": "COMPLETED",
        "evidence_classification": "COMPONENT_EVIDENCE_EXTRACTED",
        "families_evaluated": 4,
        "variants_evaluated": 40,
        "winner_selected": False,
        "optimization_performed": False,
        "production_authorized": False,
        "next_stage": "RD16F_REGISTERED_INTRADAY_COMPOSITE_ALPHA_ARCHITECTURE",
    }
    for key, expected_value in expected.items():
        if report.get(key) != expected_value:
            raise RD16FRegistrationError(
                f"RD16-E readiness mismatch for {key}: {report.get(key)!r}"
            )
    technical = report.get("technical_gates")
    if not isinstance(technical, dict):
        raise RD16FRegistrationError("RD16-E technical_gates is missing.")
    for key in (
        "all_four_families_evaluated",
        "all_ten_variants_evaluated_per_family",
        "deterministic_replay_match",
        "frozen_inputs_unchanged",
        "causal_signal_time_filters_only",
        "spot_only",
        "long_only",
    ):
        if technical.get(key) is not True:
            raise RD16FRegistrationError(f"RD16-E technical gate failed: {key}")
    for key in (
        "test_2025_accessed",
        "holdout_2026_accessed",
        "dune_api_called",
        "optimization_performed",
        "winner_selected",
    ):
        if technical.get(key) is True:
            raise RD16FRegistrationError(f"RD16-E forbidden flag is true: {key}")
    return report


def _verify_rd16e_tracked_outputs() -> dict[str, str]:
    manifest = read_json_object(RD16E_ROOT / "output-hashes.json")
    verified: dict[str, str] = {}
    for raw_name, raw_digest in sorted(manifest.items()):
        if not isinstance(raw_name, str) or not isinstance(raw_digest, str):
            raise RD16FRegistrationError("RD16-E output hash manifest is invalid.")
        path = RD16E_ROOT / raw_name
        if not path.is_file():
            report_path = REPORTS_ROOT / raw_name
            if not report_path.is_file():
                raise RD16FRegistrationError(f"Missing RD16-E output: {raw_name}")
            path = report_path
        actual = sha256_path(path)
        if actual != raw_digest:
            raise RD16FRegistrationError(
                f"RD16-E output hash mismatch for {raw_name}: {actual} != {raw_digest}"
            )
        verified[f"rd16e:{raw_name}"] = actual
    return verified


def _component_decisions() -> dict[str, dict[str, str]]:
    path = RD16E_ROOT / "component-decisions.csv"
    if not path.is_file():
        raise RD16FRegistrationError(f"Missing RD16-E component decisions: {path}")
    decisions: dict[str, dict[str, str]] = {}
    with path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            component_id = row.get("component_id")
            if component_id:
                decisions[component_id] = {
                    str(key): "" if value is None else str(value) for key, value in row.items()
                }
    return decisions


def _provenance_rows() -> tuple[list[dict[str, object]], bool]:
    decisions = _component_decisions()
    rows: list[dict[str, object]] = []
    all_verified = True
    for component_id in sorted(SOURCE_COMPONENT_IDS):
        row = decisions.get(component_id)
        decision = row.get("decision", "") if row is not None else ""
        carry = row.get("carry_forward", "") if row is not None else ""
        verified = decision == "RETAIN_FOR_COMPOSITE_RESEARCH" and carry == "True"
        all_verified = all_verified and verified
        rows.append(
            {
                "source_component_id": component_id,
                "rd16e_decision": decision,
                "carry_forward": carry,
                "verified": verified,
            }
        )
    return rows, all_verified


def _load_rd16d_enriched() -> tuple[dict[str, pd.DataFrame], dict[str, str]]:
    manifest = read_json_object(RD16D_ROOT / "local-output-manifest-v1.json")
    raw_families = manifest.get("families")
    if not isinstance(raw_families, dict):
        raise RD16FRegistrationError("RD16-D local output manifest is invalid.")
    families = cast(dict[str, object], raw_families)
    frames: dict[str, pd.DataFrame] = {}
    hashes: dict[str, str] = {}
    for registration in ENGINE_REGISTRY:
        family_id = registration.source_family_id
        raw_family = families.get(family_id)
        if not isinstance(raw_family, dict):
            raise RD16FRegistrationError(f"Missing RD16-D local family: {family_id}")
        family = cast(dict[str, object], raw_family)
        raw_entry = family.get("enriched_trades")
        if not isinstance(raw_entry, dict):
            raise RD16FRegistrationError(f"Missing enriched trades: {family_id}")
        entry = cast(dict[str, object], raw_entry)
        relative = entry.get("logical_path")
        file_hash = entry.get("file_sha256")
        content_hash = entry.get("content_sha256")
        rows = entry.get("rows")
        if not isinstance(relative, str):
            raise RD16FRegistrationError(f"Invalid local path: {family_id}")
        path = RD16D_LOCAL_ROOT / relative
        if not path.is_file():
            raise RD16FRegistrationError(f"Missing local enriched trades: {path}")
        actual_file_hash = sha256_path(path)
        if not isinstance(file_hash, str) or actual_file_hash != file_hash:
            raise RD16FRegistrationError(f"Local file hash mismatch: {family_id}")
        frame = pd.read_parquet(str(path))
        if not isinstance(rows, int) or len(frame) != rows:
            raise RD16FRegistrationError(f"Local row mismatch: {family_id}")
        if not isinstance(content_hash, str) or dataframe_content_hash(frame) != content_hash:
            raise RD16FRegistrationError(f"Local content hash mismatch: {family_id}")
        frames[family_id] = frame
        hashes[f"local:rd16d:{family_id}:enriched_trades"] = actual_file_hash
    return frames, hashes


def _frozen_input_hashes() -> dict[str, str]:
    tracked = {
        "config/assets.yaml": ROOT / "config" / "assets.yaml",
        "rd16e/rd16e-protocol-v1.json": RD16E_ROOT / "rd16e-protocol-v1.json",
        "rd16e/rd16e-final-report-v1.json": RD16E_ROOT / "rd16e-final-report-v1.json",
        "rd16e/validation-report.json": RD16E_ROOT / "validation-report.json",
        "rd16e/output-hashes.json": RD16E_ROOT / "output-hashes.json",
        "rd16e/component-decisions.csv": RD16E_ROOT / "component-decisions.csv",
        "rd16d/local-output-manifest-v1.json": (RD16D_ROOT / "local-output-manifest-v1.json"),
    }
    hashes: dict[str, str] = {}
    for name, path in tracked.items():
        if not path.is_file():
            raise RD16FRegistrationError(f"Frozen RD16-F input missing: {path}")
        hashes[name] = sha256_path(path)
    hashes.update(_verify_rd16e_tracked_outputs())
    _, local_hashes = _load_rd16d_enriched()
    hashes.update(local_hashes)
    return dict(sorted(hashes.items()))


def _load_feature_frames() -> dict[str, pd.DataFrame]:
    store = ParquetCandleStore(LOCAL_INPUT_ROOT)
    result: dict[str, pd.DataFrame] = {}
    for symbol in PILOT_SYMBOLS:
        frames = {
            timeframe: store.load(
                exchange_id=EXCHANGE_ID,
                symbol=symbol,
                timeframe=timeframe,
                verify_integrity=True,
            )
            for timeframe in (SIGNAL_TIMEFRAME, *CONTEXT_TIMEFRAMES)
        }
        result[symbol] = build_feature_frame(frames, symbol=symbol)
    return result


def _filtered_source_frames(
    enriched: Mapping[str, pd.DataFrame],
    *,
    feature_frames: Mapping[str, pd.DataFrame],
) -> dict[str, pd.DataFrame]:
    result: dict[str, pd.DataFrame] = {}
    for registration in ENGINE_REGISTRY:
        family_id = registration.source_family_id
        attached = attach_signal_features(enriched[family_id], feature_frames=feature_frames)
        result[family_id] = apply_variant(
            attached,
            family_id=family_id,
            variant_id=SOURCE_VARIANT,
        )
    return result


def _coverage_rows(
    candidates: pd.DataFrame,
    trades: pd.DataFrame,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for registration in ENGINE_REGISTRY:
        engine_candidates = candidates.loc[candidates["engine_id"] == registration.engine_id]
        engine_trades = trades.loc[trades["engine_id"] == registration.engine_id]
        for symbol in sorted(engine_candidates["symbol"].astype(str).unique().tolist()):
            source = engine_candidates.loc[engine_candidates["symbol"] == symbol]
            admitted = engine_trades.loc[engine_trades["symbol"] == symbol]
            signals = pd.to_datetime(source["signal_close"], utc=True, errors="raise")
            rows.append(
                {
                    "engine_id": registration.engine_id,
                    "symbol": symbol,
                    "candidate_count": len(source),
                    "admitted_trade_count": len(admitted),
                    "first_signal_close": _timestamp(signals.min()).isoformat(),
                    "last_signal_close": _timestamp(signals.max()).isoformat(),
                }
            )
    return rows


def _routing_rows(evaluated: pd.DataFrame) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for engine_id, engine in evaluated.groupby("engine_id", sort=True):
        total = len(engine)
        for decision, group in engine.groupby("router_decision", sort=True):
            rows.append(
                {
                    "engine_id": str(engine_id),
                    "router_decision": str(decision),
                    "candidate_count": len(group),
                    "fraction_of_engine_candidates": len(group) / total if total else None,
                }
            )
    return rows


def _hash_frames(frames: Mapping[str, pd.DataFrame]) -> str:
    payload = {name: dataframe_content_hash(frame) for name, frame in sorted(frames.items())}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def _local_manifest_entry(path: Path, frame: pd.DataFrame) -> dict[str, object]:
    return {
        "logical_path": str(path.relative_to(RD16F_LOCAL_ROOT)).replace("\\", "/"),
        "rows": len(frame),
        "file_sha256": sha256_path(path),
        "content_sha256": dataframe_content_hash(frame),
    }


def _save_local_outputs(
    candidates: pd.DataFrame,
    evaluated: pd.DataFrame,
    trades: pd.DataFrame,
) -> dict[str, object]:
    if RD16F_LOCAL_ROOT.exists():
        shutil.rmtree(RD16F_LOCAL_ROOT)
    RD16F_LOCAL_ROOT.mkdir(parents=True, exist_ok=True)
    entries: dict[str, object] = {}
    for name, frame in (
        ("candidates", candidates),
        ("evaluated", evaluated),
        ("trades", trades),
    ):
        path = RD16F_LOCAL_ROOT / f"composite-{name}.parquet"
        frame.to_parquet(path, index=False, engine="pyarrow")
        entries[name] = _local_manifest_entry(path, frame)
    return {
        "schema_version": SCHEMA_VERSION,
        "root_committed": False,
        "architecture_id": ARCHITECTURE_ID,
        "entries": entries,
    }


def _write_reports(
    *,
    report: Mapping[str, object],
    coverage_rows: Sequence[Mapping[str, object]],
    routing_rows: Sequence[Mapping[str, object]],
    provenance_rows: Sequence[Mapping[str, object]],
) -> None:
    REPORTS_ROOT.mkdir(parents=True, exist_ok=True)
    diagnostics = cast(Mapping[str, object], report["diagnostic_only"])
    result_lines = [
        "# RD16-F Composite Architecture Registration Results v1",
        "",
        f"- Architecture: `{ARCHITECTURE_ID}`",
        f"- Engines registered: {report['engines_registered']}",
        f"- Composite candidates: {report['candidate_count']}",
        f"- Admitted trades: {report['admitted_trade_count']}",
        (
            "- Diagnostic-only frozen-stream return: "
            f"{float(cast(float, diagnostics['diagnostic_net_return'])) * 100.0:.2f}%"
        ),
        "- Economic baseline performed: no",
        f"- Evidence classification: `{report['evidence_classification']}`",
        "",
        "## Engine coverage",
        "",
        "| Engine | Symbol | Candidates | Admitted | First | Last |",
        "|---|---|---:|---:|---|---|",
    ]
    for row in coverage_rows:
        result_lines.append(
            "| "
            + " | ".join(
                (
                    str(row["engine_id"]),
                    str(row["symbol"]),
                    str(row["candidate_count"]),
                    str(row["admitted_trade_count"]),
                    str(row["first_signal_close"]),
                    str(row["last_signal_close"]),
                )
            )
            + " |"
        )
    (REPORTS_ROOT / "rd16f-composite-architecture-results-v1.md").write_text(
        "\n".join(result_lines).rstrip() + "\n",
        encoding="utf-8",
        newline="\n",
    )

    routing_lines = [
        "# RD16-F Composite Routing Causality Audit v1",
        "",
        "Routing is fixed, deterministic, and does not use realized outcomes.",
        "",
        "| Engine | Decision | Count | Fraction |",
        "|---|---|---:|---:|",
    ]
    for row in routing_rows:
        routing_lines.append(
            "| "
            + " | ".join(
                (
                    str(row["engine_id"]),
                    str(row["router_decision"]),
                    str(row["candidate_count"]),
                    f"{float(cast(float, row['fraction_of_engine_candidates'])):.4f}",
                )
            )
            + " |"
        )
    routing_lines.extend(
        (
            "",
            "## Fixed ordering",
            "",
            "- Trend priority: 10.",
            "- Compression priority: 20.",
            "- Same-symbol simultaneous candidates are coalesced before admission.",
            "- Exits at the entry timestamp are treated as completed before admission.",
            "- Global cooldown and portfolio limits use only information available by entry time.",
        )
    )
    (REPORTS_ROOT / "rd16f-composite-routing-causality-audit-v1.md").write_text(
        "\n".join(routing_lines).rstrip() + "\n",
        encoding="utf-8",
        newline="\n",
    )

    provenance_lines = [
        "# RD16-F Component Provenance and Constraint Audit v1",
        "",
        "## RD16-E source components",
        "",
        "| Component | RD16-E decision | Carry forward | Verified |",
        "|---|---|---|---|",
    ]
    for row in provenance_rows:
        provenance_lines.append(
            "| "
            + " | ".join(
                (
                    str(row["source_component_id"]),
                    str(row["rd16e_decision"]),
                    str(row["carry_forward"]),
                    str(row["verified"]),
                )
            )
            + " |"
        )
    provenance_lines.extend(
        (
            "",
            "## Constraints",
            "",
            "- Spot only and Long only.",
            (
                "- No leverage, margin, shorting, derivatives, DCA, Kelly, "
                "pyramiding, or averaging down."
            ),
            "- Maximum three positions and 1.5% frozen open risk.",
            "- No concurrent same-symbol positions and a global 24-hour cooldown.",
            "- 2025 and 2026 remain sealed.",
            "- No production authorization or economic baseline is issued by RD16-F.",
        )
    )
    (REPORTS_ROOT / "rd16f-component-provenance-constraint-audit-v1.md").write_text(
        "\n".join(provenance_lines).rstrip() + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _output_hashes() -> dict[str, str]:
    data_names = (
        "architecture-registration.csv",
        "engine-coverage.csv",
        "routing-decision-summary.csv",
        "component-provenance.csv",
        "constraint-audit.csv",
        "local-ledger-manifest-v1.json",
        "frozen-input-hashes.json",
        "rd16f-final-report-v1.json",
        "validation-report.json",
    )
    report_names = (
        "rd16f-composite-architecture-methodology-v1.md",
        "rd16f-composite-architecture-results-v1.md",
        "rd16f-composite-routing-causality-audit-v1.md",
        "rd16f-component-provenance-constraint-audit-v1.md",
    )
    hashes = {name: sha256_path(RD16F_ROOT / name) for name in data_names}
    hashes.update({name: sha256_path(REPORTS_ROOT / name) for name in report_names})
    return dict(sorted(hashes.items()))


def run_rd16f() -> dict[str, Any]:
    _verify_rd16e_ready()
    provenance_rows, provenance_verified = _provenance_rows()
    frozen_before = _frozen_input_hashes()
    enriched, _ = _load_rd16d_enriched()
    feature_frames = _load_feature_frames()
    filtered = _filtered_source_frames(enriched, feature_frames=feature_frames)

    first_candidates = build_composite_candidates(filtered)
    first = route_composite_candidates(first_candidates)
    replay_candidates = build_composite_candidates(filtered)
    replay = route_composite_candidates(replay_candidates)
    deterministic_replay_match = _hash_frames(
        {
            "candidates": first.candidates,
            "evaluated": first.evaluated,
            "trades": first.trades,
        }
    ) == _hash_frames(
        {
            "candidates": replay.candidates,
            "evaluated": replay.evaluated,
            "trades": replay.trades,
        }
    )
    frozen_after = _frozen_input_hashes()
    frozen_inputs_unchanged = frozen_before == frozen_after

    sealed_cutoff_respected = bool(
        (
            pd.to_datetime(first.candidates["signal_close"], utc=True, errors="raise")
            < pd.Timestamp(SEALED_CUTOFF)
        ).all()
    )
    overlap_absent = same_symbol_overlap_absent(first.trades)
    cooldown_respected = global_cooldown_respected(first.trades)
    duplicate_trade_ids_absent = not bool(first.trades["trade_id"].duplicated().any())
    source_engine_candidates = {
        registration.engine_id: int((first.candidates["engine_id"] == registration.engine_id).sum())
        for registration in ENGINE_REGISTRY
    }
    source_engine_admitted = {
        registration.engine_id: int((first.trades["engine_id"] == registration.engine_id).sum())
        for registration in ENGINE_REGISTRY
    }
    both_have_candidates = all(count > 0 for count in source_engine_candidates.values())
    both_have_admitted = all(count > 0 for count in source_engine_admitted.values())
    maximum_positions_respected = first.maximum_positions_observed <= MAXIMUM_POSITIONS
    maximum_open_risk_respected = (
        first.maximum_open_risk_fraction <= MAXIMUM_OPEN_RISK_FRACTION + 1e-12
    )
    conflicts = first.evaluated.loc[
        first.evaluated["router_decision"] == "REJECTED_ENGINE_CONFLICT"
    ]
    conflicts_resolved = bool((pd.to_numeric(conflicts["conflict_rank"], errors="raise") > 0).all())

    technical_pass = all(
        (
            len(ENGINE_REGISTRY) == 2,
            provenance_verified,
            both_have_candidates,
            both_have_admitted,
            deterministic_replay_match,
            frozen_inputs_unchanged,
            maximum_positions_respected,
            maximum_open_risk_respected,
            overlap_absent,
            cooldown_respected,
            conflicts_resolved,
            duplicate_trade_ids_absent,
            sealed_cutoff_respected,
        )
    )
    evidence = EVIDENCE_READY if technical_pass else EVIDENCE_REMEDIATE
    decision = DECISION_COMPLETED if technical_pass else DECISION_REMEDIATE
    next_stage = NEXT_READY if technical_pass else NEXT_REMEDIATE
    coverage_rows = _coverage_rows(first.candidates, first.trades)
    routing_rows = _routing_rows(first.evaluated)
    diagnostics = diagnostic_metrics(first.trades)
    local_manifest = _save_local_outputs(first.candidates, first.evaluated, first.trades)

    technical_gates: dict[str, object] = {
        "two_registered_engines": len(ENGINE_REGISTRY) == 2,
        "source_components_verified_retained": provenance_verified,
        "both_registered_engines_have_candidates": both_have_candidates,
        "both_registered_engines_have_admitted_trades": both_have_admitted,
        "deterministic_replay_match": deterministic_replay_match,
        "frozen_inputs_unchanged": frozen_inputs_unchanged,
        "maximum_positions_respected": maximum_positions_respected,
        "maximum_open_risk_respected": maximum_open_risk_respected,
        "same_symbol_overlap_absent": overlap_absent,
        "global_cooldown_respected": cooldown_respected,
        "simultaneous_conflicts_resolved_deterministically": conflicts_resolved,
        "duplicate_composite_trade_ids_absent": duplicate_trade_ids_absent,
        "sealed_cutoff_respected": sealed_cutoff_respected,
        "spot_only": True,
        "long_only": True,
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
        "dune_api_called": False,
        "optimization_performed": False,
        "winner_selected": False,
        "economic_baseline_performed": False,
        "production_authorized": False,
    }
    final: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "branch": BRANCH,
        "architecture_id": ARCHITECTURE_ID,
        "decision": decision,
        "technical_status": "COMPLETED" if technical_pass else "FAILED",
        "evidence_classification": evidence,
        "engines_registered": len(ENGINE_REGISTRY),
        "source_components_verified": len(provenance_rows),
        "candidate_count": len(first.candidates),
        "admitted_trade_count": len(first.trades),
        "engine_candidate_counts": source_engine_candidates,
        "engine_admitted_counts": source_engine_admitted,
        "maximum_positions_observed": first.maximum_positions_observed,
        "maximum_open_risk_fraction": first.maximum_open_risk_fraction,
        "diagnostic_only": diagnostics,
        "strategic_monthly_target": 0.24,
        "strategic_objective_evaluated": False,
        "winner_selected": False,
        "optimization_performed": False,
        "economic_baseline_performed": False,
        "production_authorized": False,
        "next_stage": next_stage,
        "technical_gates": technical_gates,
        "limitations": [
            "RD16-F is a registration and smoke-test stage, not an economic baseline.",
            "Both engines use filtered frozen RD16-D admitted trades.",
            "Previously rejected family candidates are not re-admitted.",
            "Diagnostic PnL is not a pass gate and does not authorize production.",
            "2025 and 2026 remain sealed and were not accessed.",
        ],
    }
    validation: dict[str, Any] = {
        "status": "PASS" if technical_pass else "FAIL",
        **technical_gates,
    }
    constraint_row = {
        "architecture_id": ARCHITECTURE_ID,
        "spot_only": True,
        "long_only": True,
        "no_leverage": True,
        "no_margin": True,
        "no_short": True,
        "no_dca": True,
        "no_kelly": True,
        "no_pyramiding": True,
        "no_averaging_down": True,
        "maximum_positions_respected": maximum_positions_respected,
        "maximum_open_risk_respected": maximum_open_risk_respected,
        "same_symbol_overlap_absent": overlap_absent,
        "global_cooldown_respected": cooldown_respected,
        "exit_before_entry": True,
        "outcome_based_routing": False,
    }

    RD16F_ROOT.mkdir(parents=True, exist_ok=True)
    write_csv(
        RD16F_ROOT / "architecture-registration.csv",
        [registration.to_record() for registration in ENGINE_REGISTRY],
        fieldnames=REGISTRATION_FIELDS,
    )
    write_csv(
        RD16F_ROOT / "engine-coverage.csv",
        coverage_rows,
        fieldnames=COVERAGE_FIELDS,
    )
    write_csv(
        RD16F_ROOT / "routing-decision-summary.csv",
        routing_rows,
        fieldnames=ROUTING_FIELDS,
    )
    write_csv(
        RD16F_ROOT / "component-provenance.csv",
        provenance_rows,
        fieldnames=PROVENANCE_FIELDS,
    )
    write_csv(
        RD16F_ROOT / "constraint-audit.csv",
        [constraint_row],
        fieldnames=CONSTRAINT_FIELDS,
    )
    write_json(RD16F_ROOT / "local-ledger-manifest-v1.json", local_manifest)
    write_json(RD16F_ROOT / "frozen-input-hashes.json", frozen_before)
    write_json(RD16F_ROOT / "rd16f-final-report-v1.json", final)
    write_json(RD16F_ROOT / "validation-report.json", validation)
    _write_reports(
        report=final,
        coverage_rows=coverage_rows,
        routing_rows=routing_rows,
        provenance_rows=provenance_rows,
    )
    write_json(RD16F_ROOT / "output-hashes.json", _output_hashes())
    return final


__all__ = [
    "DECISION_COMPLETED",
    "EVIDENCE_READY",
    "NEXT_READY",
    "RD16FRegistrationError",
    "RD16F_ROOT",
    "SCHEMA_VERSION",
    "run_rd16f",
]
