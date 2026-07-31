from __future__ import annotations

import shutil
from collections.abc import Mapping
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
from spotbot.research.rd16d_common import write_csv, write_json
from spotbot.research.rd16l_architecture import (
    ARCHITECTURE_ID,
    BASE_RISK_PER_TRADE_FRACTION,
    COMPRESSION_COOLDOWN_HOURS,
    COMPRESSION_ENGINE_ID,
    EXPANDED_RISK_PER_TRADE_FRACTION,
    MAXIMUM_OPEN_RISK_FRACTION,
    MAXIMUM_POSITIONS,
    NORMAL_HOLDING_BARS,
    SOURCE_ARCHITECTURE_ID,
    SOURCE_VARIANT_ID,
    STRONG_BULL_HOLDING_BARS,
    TREND_COOLDOWN_HOURS,
    TREND_ENGINE_ID,
    diagnostic_metrics,
    engine_cooldowns_respected,
    holding_policy_respected,
    holding_policy_rows,
    maximum_open_risk_respected,
    maximum_positions_respected,
    prepare_v3_ledgers,
    routing_decision_rows,
    same_symbol_overlap_absent,
)

SCHEMA_VERSION: Final = "rd16l-registered-composite-alpha-v3-v1"
DECISION: Final = "RD16L_REGISTERED_COMPOSITE_ALPHA_V3_ARCHITECTURE_COMPLETED"
EVIDENCE_CLASSIFICATION: Final = "READY_FOR_FIXED_COMPOSITE_ALPHA_V3_BASELINE"
NEXT_STAGE: Final = "RD16M_FIXED_COMPOSITE_ALPHA_V3_BASELINE_EVALUATION"

RD16K_ROOT: Final = ROOT / "data" / "research" / "rd16k"
RD16L_ROOT: Final = ROOT / "data" / "research" / "rd16l"
RD16K_LOCAL_ROOT: Final = ROOT / "data" / "raw" / "rd16k"
RD16L_LOCAL_ROOT: Final = ROOT / "data" / "raw" / "rd16l"
REPORTS_ROOT: Final = ROOT / "reports" / "research"

SOURCE_LEDGER_NAMES: Final = ("candidates", "evaluated", "trades")


class RD16LRegistrationError(RuntimeError):
    pass


def _verify_rd16k_output_hashes() -> dict[str, str]:
    manifest = read_json_object(RD16K_ROOT / "output-hashes.json")
    verified: dict[str, str] = {}
    for raw_name, raw_digest in sorted(manifest.items()):
        if not isinstance(raw_name, str) or not isinstance(raw_digest, str):
            raise RD16LRegistrationError("RD16-K output hash manifest is invalid.")
        path = REPORTS_ROOT / raw_name if raw_name.endswith(".md") else RD16K_ROOT / raw_name
        if not path.is_file():
            raise RD16LRegistrationError(f"RD16-K output is missing: {path}")
        actual = sha256_path(path)
        if actual != raw_digest:
            raise RD16LRegistrationError(
                f"RD16-K output hash mismatch for {raw_name}: expected {raw_digest}, got {actual}"
            )
        verified[f"rd16k:{raw_name}"] = actual
    return verified


def verify_rd16k_ready() -> dict[str, Any]:
    report = read_json_object(RD16K_ROOT / "rd16k-final-report-v1.json")
    expected = {
        "decision": (
            "RD16K_COMPOSITE_ALPHA_V2_CAPITAL_EFFICIENCY_AND_BULL_CAPTURE_REMEDIATION_COMPLETED"
        ),
        "technical_status": "COMPLETED",
        "evidence_classification": ("CAPITAL_EFFICIENCY_AND_BULL_CAPTURE_EVIDENCE_EXTRACTED"),
        "next_stage": "RD16L_REGISTERED_COMPOSITE_ALPHA_V3_ARCHITECTURE",
        "retained_variant_count": 1,
        "retained_variants": [SOURCE_VARIANT_ID],
        "strategic_objective_met_count": 0,
    }
    for key, expected_value in expected.items():
        if report.get(key) != expected_value:
            raise RD16LRegistrationError(
                f"RD16-K readiness mismatch for {key}: {report.get(key)!r}"
            )
    if report.get("optimization_performed") is True:
        raise RD16LRegistrationError("RD16-K optimization flag cannot be true.")
    if report.get("production_authorized") is True:
        raise RD16LRegistrationError("RD16-K production authorization flag cannot be true.")
    _verify_rd16k_output_hashes()
    return report


def _source_manifest() -> dict[str, Any]:
    manifest = read_json_object(RD16K_ROOT / "local-output-manifest-v1.json")
    variants = manifest.get("variants")
    if not isinstance(variants, dict):
        raise RD16LRegistrationError("RD16-K local manifest variants are invalid.")
    raw_variant = variants.get(SOURCE_VARIANT_ID)
    if not isinstance(raw_variant, dict):
        raise RD16LRegistrationError(f"RD16-K manifest is missing {SOURCE_VARIANT_ID}.")
    return cast(dict[str, Any], raw_variant)


def load_source_ledgers() -> dict[str, pd.DataFrame]:
    variant_manifest = _source_manifest()
    frames: dict[str, pd.DataFrame] = {}
    for name in SOURCE_LEDGER_NAMES:
        raw_entry = variant_manifest.get(name)
        if not isinstance(raw_entry, dict):
            raise RD16LRegistrationError(f"RD16-K source manifest is missing {name}.")
        entry = cast(dict[str, Any], raw_entry)
        relative = entry.get("logical_path")
        file_hash = entry.get("file_sha256")
        content_hash = entry.get("content_sha256")
        rows = entry.get("rows")
        if not isinstance(relative, str):
            raise RD16LRegistrationError(f"Missing source path for {name}.")
        path = RD16K_LOCAL_ROOT / relative
        if not path.is_file():
            raise RD16LRegistrationError(f"Source ledger is missing: {path}")
        if not isinstance(file_hash, str) or sha256_path(path) != file_hash:
            raise RD16LRegistrationError(f"Source file hash mismatch: {name}")
        frame = pd.read_parquet(str(path))
        if not isinstance(rows, int) or len(frame) != rows:
            raise RD16LRegistrationError(f"Source row mismatch: {name}")
        if not isinstance(content_hash, str) or dataframe_content_hash(frame) != content_hash:
            raise RD16LRegistrationError(f"Source content hash mismatch: {name}")
        frames[name] = frame
    return frames


def frozen_input_hashes() -> dict[str, str]:
    tracked = {
        "rd16k/rd16k-final-report-v1.json": (RD16K_ROOT / "rd16k-final-report-v1.json"),
        "rd16k/validation-report.json": (RD16K_ROOT / "validation-report.json"),
        "rd16k/output-hashes.json": RD16K_ROOT / "output-hashes.json",
        "rd16k/local-output-manifest-v1.json": (RD16K_ROOT / "local-output-manifest-v1.json"),
        "rd16k/component-decisions.csv": (RD16K_ROOT / "component-decisions.csv"),
        "rd16k/variant-summary.csv": RD16K_ROOT / "variant-summary.csv",
    }
    hashes: dict[str, str] = {}
    for name, path in tracked.items():
        if not path.is_file():
            raise RD16LRegistrationError(f"Frozen input is missing: {path}")
        hashes[name] = sha256_path(path)
    hashes.update(_verify_rd16k_output_hashes())

    variant_manifest = _source_manifest()
    for name in SOURCE_LEDGER_NAMES:
        entry = cast(dict[str, Any], variant_manifest[name])
        relative = cast(str, entry["logical_path"])
        path = RD16K_LOCAL_ROOT / relative
        hashes[f"local:{SOURCE_VARIANT_ID}:{name}"] = sha256_path(path)
    return dict(sorted(hashes.items()))


def _write_local_ledgers(
    frames: Mapping[str, pd.DataFrame],
) -> dict[str, Any]:
    if RD16L_LOCAL_ROOT.exists():
        shutil.rmtree(RD16L_LOCAL_ROOT)
    RD16L_LOCAL_ROOT.mkdir(parents=True, exist_ok=True)

    entries: dict[str, dict[str, object]] = {}
    for name in SOURCE_LEDGER_NAMES:
        frame = frames[name]
        relative = f"composite-v3-{name}.parquet"
        path = RD16L_LOCAL_ROOT / relative
        frame.to_parquet(path, index=False)
        entries[name] = {
            "logical_path": relative,
            "rows": len(frame),
            "file_sha256": sha256_path(path),
            "content_sha256": dataframe_content_hash(frame),
        }
    return {
        "schema_version": SCHEMA_VERSION,
        "architecture_id": ARCHITECTURE_ID,
        "source_variant_id": SOURCE_VARIANT_ID,
        "root_committed": False,
        "entries": entries,
    }


def _hash_tracked_outputs(paths: list[Path]) -> dict[str, str]:
    return {path.name: sha256_path(path) for path in paths}


def _report_text(
    *,
    final_report: Mapping[str, object],
    constraints: list[dict[str, object]],
    holding_rows: list[dict[str, object]],
) -> tuple[str, str]:
    diagnostics = cast(
        dict[str, object],
        final_report["diagnostic_only"],
    )
    maximum_open_risk_observed = cast(
        float,
        final_report["maximum_open_risk_fraction_observed"],
    )
    diagnostic_net_return = cast(
        float,
        diagnostics["diagnostic_net_return"],
    )
    diagnostic_profit_factor = cast(
        float,
        diagnostics["diagnostic_profit_factor"],
    )
    results = [
        "# RD16-L COMPOSITE_ALPHA_V3 Registration Results",
        "",
        f"- Decision: `{final_report['decision']}`",
        f"- Architecture: `{final_report['architecture_id']}`",
        f"- Source variant: `{final_report['source_variant_id']}`",
        f"- Candidates: {final_report['candidate_count']}",
        f"- Admitted trades: {final_report['admitted_trade_count']}",
        (
            "- Maximum positions: "
            f"{final_report['maximum_positions_observed']} observed / "
            f"{final_report['maximum_positions_configured']} configured"
        ),
        (f"- Maximum open risk observed: {maximum_open_risk_observed:.2%}"),
        (f"- Diagnostic net return: {diagnostic_net_return:.2%}"),
        (f"- Diagnostic profit factor: {diagnostic_profit_factor:.3f}"),
        "",
        "Registration is not an economic pass gate or production authorization.",
        "",
        f"Next: `{final_report['next_stage']}`",
        "",
    ]
    audit = [
        "# RD16-L Causality and Holding-Policy Audit",
        "",
        "## Constraints",
        "",
    ]
    for row in constraints:
        audit.append(f"- `{row['constraint']}`: **{row['passed']}** — {row['detail']}")
    audit.extend(["", "## Holding policy", ""])
    for row in holding_rows:
        audit.append(
            "- "
            f"`{row['market_regime']}`: {row['trade_count']} trades, "
            f"configured max {row['configured_maximum_holding_bars']} bars, "
            f"observed max {row['maximum_bars_held']} bars."
        )
    audit.append("")
    return "\n".join(results), "\n".join(audit)


def register_composite_alpha_v3() -> dict[str, object]:
    source_report = verify_rd16k_ready()
    source = load_source_ledgers()
    registered = prepare_v3_ledgers(
        source["candidates"],
        source["evaluated"],
        source["trades"],
    )

    cutoff = pd.Timestamp(SEALED_CUTOFF)
    signal_max = pd.to_datetime(
        registered.candidates["signal_close"],
        utc=True,
        errors="raise",
    ).max()
    sealed_cutoff_respected = bool(signal_max < cutoff)

    constraints = [
        {
            "constraint": "source_variant_retained",
            "passed": source_report.get("retained_variants") == [SOURCE_VARIANT_ID],
            "detail": "RD16-K retained exactly STRONG_BULL_HOLD_96.",
        },
        {
            "constraint": "same_symbol_overlap_absent",
            "passed": same_symbol_overlap_absent(registered.trades),
            "detail": "No concurrent positions share a symbol.",
        },
        {
            "constraint": "engine_cooldowns_respected",
            "passed": engine_cooldowns_respected(registered.trades),
            "detail": "Trend 12h and Compression 24h cooldowns are preserved.",
        },
        {
            "constraint": "maximum_positions_respected",
            "passed": maximum_positions_respected(registered.evaluated),
            "detail": "Configured position capacity remains five.",
        },
        {
            "constraint": "maximum_open_risk_respected",
            "passed": maximum_open_risk_respected(registered.evaluated),
            "detail": "Open risk remains capped at 2.25% of initial equity.",
        },
        {
            "constraint": "holding_policy_respected",
            "passed": holding_policy_respected(registered.trades),
            "detail": "Strong Bull uses 96 bars; all other regimes use 48.",
        },
        {
            "constraint": "sealed_cutoff_respected",
            "passed": sealed_cutoff_respected,
            "detail": "No candidate signal reaches the sealed cutoff.",
        },
        {
            "constraint": "spot_long_only_preserved",
            "passed": True,
            "detail": "No leverage, margin, short, or derivative path exists.",
        },
    ]
    failed = [row for row in constraints if row["passed"] is not True]
    if failed:
        raise RD16LRegistrationError(f"V3 registration constraints failed: {failed}")

    diagnostics = diagnostic_metrics(registered.trades)
    holding_rows = holding_policy_rows(registered.trades)
    routing_rows = routing_decision_rows(registered.evaluated)

    position_rows: list[dict[str, object]] = []
    for positions, group in registered.evaluated.groupby(
        "positions_before",
        sort=True,
    ):
        position_rows.append(
            {
                "architecture_id": ARCHITECTURE_ID,
                "positions_before": int(cast(int, positions)),
                "candidate_count": len(group),
            }
        )

    local_manifest = _write_local_ledgers(
        {
            "candidates": registered.candidates,
            "evaluated": registered.evaluated,
            "trades": registered.trades,
        }
    )

    RD16L_ROOT.mkdir(parents=True, exist_ok=True)
    REPORTS_ROOT.mkdir(parents=True, exist_ok=True)

    architecture_rows = [
        {
            "architecture_id": ARCHITECTURE_ID,
            "source_architecture_id": SOURCE_ARCHITECTURE_ID,
            "source_variant_id": SOURCE_VARIANT_ID,
            "trend_engine_id": TREND_ENGINE_ID,
            "compression_engine_id": COMPRESSION_ENGINE_ID,
            "maximum_positions": MAXIMUM_POSITIONS,
            "maximum_open_risk_fraction": MAXIMUM_OPEN_RISK_FRACTION,
            "base_risk_per_trade_fraction": BASE_RISK_PER_TRADE_FRACTION,
            "expanded_risk_per_trade_fraction": (EXPANDED_RISK_PER_TRADE_FRACTION),
            "trend_cooldown_hours": TREND_COOLDOWN_HOURS,
            "compression_cooldown_hours": COMPRESSION_COOLDOWN_HOURS,
            "normal_holding_bars": NORMAL_HOLDING_BARS,
            "strong_bull_holding_bars": STRONG_BULL_HOLDING_BARS,
        }
    ]
    provenance_rows = [
        {
            "architecture_id": ARCHITECTURE_ID,
            "source_architecture_id": SOURCE_ARCHITECTURE_ID,
            "source_variant_id": SOURCE_VARIANT_ID,
            "source_candidate_count": len(source["candidates"]),
            "source_evaluated_count": len(source["evaluated"]),
            "source_trade_count": len(source["trades"]),
            "source_stage_decision": source_report["decision"],
        }
    ]

    write_csv(
        RD16L_ROOT / "architecture-registration.csv",
        architecture_rows,
        fieldnames=tuple(architecture_rows[0]),
    )
    write_csv(
        RD16L_ROOT / "constraint-audit.csv",
        constraints,
        fieldnames=tuple(constraints[0]),
    )
    write_csv(
        RD16L_ROOT / "holding-policy-audit.csv",
        holding_rows,
        fieldnames=tuple(holding_rows[0]),
    )
    write_csv(
        RD16L_ROOT / "routing-decision-summary.csv",
        routing_rows,
        fieldnames=tuple(routing_rows[0]),
    )
    write_csv(
        RD16L_ROOT / "position-capacity-audit.csv",
        position_rows,
        fieldnames=tuple(position_rows[0]),
    )
    write_csv(
        RD16L_ROOT / "source-provenance.csv",
        provenance_rows,
        fieldnames=tuple(provenance_rows[0]),
    )
    write_json(RD16L_ROOT / "frozen-input-hashes.json", frozen_input_hashes())
    write_json(RD16L_ROOT / "local-ledger-manifest-v1.json", local_manifest)

    final_report: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "branch": BRANCH,
        "decision": DECISION,
        "technical_status": "COMPLETED",
        "evidence_classification": EVIDENCE_CLASSIFICATION,
        "architecture_id": ARCHITECTURE_ID,
        "source_architecture_id": SOURCE_ARCHITECTURE_ID,
        "source_variant_id": SOURCE_VARIANT_ID,
        "candidate_count": len(registered.candidates),
        "admitted_trade_count": len(registered.trades),
        "maximum_positions_configured": MAXIMUM_POSITIONS,
        "maximum_positions_observed": registered.maximum_positions_observed,
        "maximum_open_risk_fraction_configured": (MAXIMUM_OPEN_RISK_FRACTION),
        "maximum_open_risk_fraction_observed": (registered.maximum_open_risk_fraction_observed),
        "normal_holding_bars": NORMAL_HOLDING_BARS,
        "strong_bull_holding_bars": STRONG_BULL_HOLDING_BARS,
        "diagnostic_only": diagnostics,
        "economic_baseline_performed": False,
        "strategic_objective_evaluated": False,
        "optimization_performed": False,
        "winner_selected": False,
        "production_authorized": False,
        "next_stage": NEXT_STAGE,
        "limitations": [
            "RD16-L is a registration and deterministic smoke-test stage.",
            "Diagnostic PnL is not an economic pass gate.",
            "The 96-bar Strong-Bull hold remains in-sample evidence.",
            "2025 and 2026 remain sealed and were not accessed.",
        ],
        "technical_gates": {
            "rd16k_ready": True,
            "rd16k_outputs_verified": True,
            "rd16k_local_source_verified": True,
            "source_variant_retained": True,
            "deterministic_identifier_mapping": True,
            "same_symbol_overlap_absent": True,
            "engine_cooldowns_respected": True,
            "maximum_positions_respected": True,
            "maximum_open_risk_respected": True,
            "holding_policy_respected": True,
            "sealed_cutoff_respected": sealed_cutoff_respected,
            "spot_only": True,
            "long_only": True,
            "test_2025_accessed": False,
            "holdout_2026_accessed": False,
            "dune_api_called": False,
            "optimization_performed": False,
            "winner_selected": False,
            "production_authorized": False,
            "economic_baseline_performed": False,
        },
    }
    write_json(RD16L_ROOT / "rd16l-final-report-v1.json", final_report)
    write_json(
        RD16L_ROOT / "validation-report.json",
        {
            "schema_version": SCHEMA_VERSION,
            "status": "PASS",
            "checks": constraints,
            "candidate_count": len(registered.candidates),
            "trade_count": len(registered.trades),
        },
    )

    results_text, audit_text = _report_text(
        final_report=final_report,
        constraints=constraints,
        holding_rows=holding_rows,
    )
    results_path = REPORTS_ROOT / "rd16l-composite-alpha-v3-registration-results-v1.md"
    audit_path = REPORTS_ROOT / "rd16l-causality-holding-audit-v1.md"
    results_path.write_text(results_text, encoding="utf-8", newline="\n")
    audit_path.write_text(audit_text, encoding="utf-8", newline="\n")

    tracked_outputs = [
        RD16L_ROOT / "architecture-registration.csv",
        RD16L_ROOT / "constraint-audit.csv",
        RD16L_ROOT / "holding-policy-audit.csv",
        RD16L_ROOT / "routing-decision-summary.csv",
        RD16L_ROOT / "position-capacity-audit.csv",
        RD16L_ROOT / "source-provenance.csv",
        RD16L_ROOT / "frozen-input-hashes.json",
        RD16L_ROOT / "local-ledger-manifest-v1.json",
        RD16L_ROOT / "rd16l-final-report-v1.json",
        RD16L_ROOT / "validation-report.json",
        results_path,
        audit_path,
    ]
    write_json(
        RD16L_ROOT / "output-hashes.json",
        _hash_tracked_outputs(tracked_outputs),
    )
    return final_report


__all__ = [
    "DECISION",
    "EVIDENCE_CLASSIFICATION",
    "NEXT_STAGE",
    "RD16LRegistrationError",
    "frozen_input_hashes",
    "load_source_ledgers",
    "register_composite_alpha_v3",
    "verify_rd16k_ready",
]
