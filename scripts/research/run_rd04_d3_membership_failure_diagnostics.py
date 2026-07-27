"""Run RD04-D3 membership failure diagnostics from frozen RD04 evidence."""

from __future__ import annotations

import hashlib
import json
import subprocess
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
from ams_md01_common import atomic_json, atomic_text, load_registered_data

from spotbot.research.rd04_membership_failure_diagnostics import (
    DECISION_ALL,
    DECISION_ENTRANT,
    DECISION_ENTRANT_PATH,
    DECISION_ENTRANT_REMOVAL,
    DECISION_INCONCLUSIVE,
    DECISION_INVALID,
    DECISION_PATH,
    DECISION_REMOVAL,
    DECISION_REMOVAL_PATH,
    EXPECTED_PIT_ROWS,
    EXPECTED_SNAPSHOTS,
    FIXED_UNIVERSE_SIZE,
    MODE_FIXED,
    MODE_INTERSECTION,
    MODE_PIT,
    MODE_UNION,
    MODES,
    ROLE_COMMON,
    ROLE_ENTRANT,
    ROLE_OUTSIDE,
    ROLE_REMOVED,
    SCHEMA_VERSION,
    annotate_trades,
    build_diagnostic_decision,
    build_membership_exposure,
    common_path_comparison,
    normalize_symbols,
    role_totals,
    split_symbols,
    summarize_trade_groups,
    validate_candidates,
    weekly_pit_map,
)

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "reports" / "research"
D2_REPORT = REPORTS / "ams-rd04-d2-universe-membership-attribution-v1.json"
D2_TRADES = REPORTS / "ams-rd04-d2-base-cost-trades-v1.csv"
D2_MEMBERSHIP = REPORTS / "ams-rd04-d2-membership-snapshots-v1.csv"
D0C_CANDIDATES = REPORTS / "ams-rd04-d0c-venue-eligible-weekly-candidates-v1.csv"

EXPOSURE_CSV = REPORTS / "ams-rd04-d3-membership-exposure-v1.csv"
ANNOTATED_TRADES_CSV = REPORTS / "ams-rd04-d3-trade-membership-attribution-v1.csv"
ROLE_SUMMARY_CSV = REPORTS / "ams-rd04-d3-role-summary-v1.csv"
SYMBOL_CSV = REPORTS / "ams-rd04-d3-symbol-diagnostics-v1.csv"
ENTRANT_CSV = REPORTS / "ams-rd04-d3-entrant-trade-diagnostics-v1.csv"
REMOVED_CSV = REPORTS / "ams-rd04-d3-removed-survivor-opportunity-v1.csv"
RANK_TENURE_CSV = REPORTS / "ams-rd04-d3-rank-tenure-diagnostics-v1.csv"
COMMON_PATH_CSV = REPORTS / "ams-rd04-d3-common-path-comparison-v1.csv"
REPORT_JSON = REPORTS / "ams-rd04-d3-membership-failure-diagnostics-v1.json"
REPORT_MD = REPORTS / "ams-rd04-d3-membership-failure-diagnostics-v1.md"
FINAL_COPY = ROOT / "RD04_D3_RESULT_FOR_CHATGPT.md"

VALID_DECISIONS = {
    DECISION_ALL,
    DECISION_ENTRANT_REMOVAL,
    DECISION_ENTRANT_PATH,
    DECISION_REMOVAL_PATH,
    DECISION_ENTRANT,
    DECISION_REMOVAL,
    DECISION_PATH,
    DECISION_INCONCLUSIVE,
    DECISION_INVALID,
}


class MembershipDiagnosticRunError(RuntimeError):
    """Raised when live RD04-D3 evidence is structurally unsafe."""


def utc_now() -> str:
    return datetime.now(tz=UTC).isoformat().replace("+00:00", "Z")


def source_commit() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
    ).strip()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise MembershipDiagnosticRunError(f"Expected JSON object: {path}")
    return payload


def finite(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): finite(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [finite(item) for item in value]
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if hasattr(value, "item") and callable(value.item):
        return finite(value.item())
    if isinstance(value, float) and (value != value or value in {float("inf"), float("-inf")}):
        return None
    return value


def write_csv(path: Path, frame: pd.DataFrame) -> None:
    output = frame.copy()
    for column in output.columns:
        if pd.api.types.is_datetime64_any_dtype(output[column].dtype):
            output[column] = pd.to_datetime(
                output[column],
                utc=True,
                errors="coerce",
            ).map(lambda value: value.isoformat() if pd.notna(value) else "")
        elif output[column].map(lambda value: isinstance(value, (dict, list, tuple, set))).any():
            output[column] = output[column].map(
                lambda value: (
                    json.dumps(
                        finite(value),
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                    if isinstance(value, (dict, list, tuple, set))
                    else value
                )
            )
    atomic_text(path, output.to_csv(index=False, lineterminator="\n"))


def required_input_hashes() -> dict[str, str]:
    paths = {
        "d2_report": D2_REPORT,
        "d2_base_cost_trades": D2_TRADES,
        "d2_membership_snapshots": D2_MEMBERSHIP,
        "d0c_weekly_candidates": D0C_CANDIDATES,
    }
    missing = [str(path) for path in paths.values() if not path.is_file()]
    if missing:
        raise MembershipDiagnosticRunError(
            "Required diagnostic evidence is missing: " + ",".join(missing)
        )
    return {name: file_sha256(path) for name, path in paths.items()}


def validate_d2_report(report: Mapping[str, Any]) -> dict[str, bool]:
    decision_raw = report.get("decision")
    validation_raw = report.get("validation")
    safety_raw = report.get("safety")
    if not isinstance(decision_raw, Mapping):
        raise MembershipDiagnosticRunError("D2 decision is missing.")
    if not isinstance(validation_raw, Mapping):
        raise MembershipDiagnosticRunError("D2 validation is missing.")
    if not isinstance(safety_raw, Mapping):
        raise MembershipDiagnosticRunError("D2 safety section is missing.")

    return {
        "d2_status_complete": report.get("status") == "COMPLETE",
        "d2_decision_mixed_membership_failure": (
            decision_raw.get("decision") == "MIXED_MEMBERSHIP_FAILURE"
        ),
        "d2_authorized_d3": (decision_raw.get("rd04_d3_diagnostic_research_authorized") is True),
        "d2_validation_complete": validation_raw.get("status") == "COMPLETE",
        "d2_fixed_replay_match": (validation_raw.get("fixed_base_replay_matches_d1") is True),
        "d2_pit_replay_match": (validation_raw.get("pit_base_replay_matches_d1") is True),
        "d2_decomposition_exact": (validation_raw.get("all_decompositions_exact") is True),
        "d2_no_2025_access": safety_raw.get("test_2025_accessed") is False,
        "d2_no_2026_access": safety_raw.get("holdout_2026_accessed") is False,
        "d2_no_parameter_optimisation": (safety_raw.get("parameter_optimisation_used") is False),
        "d2_no_candidate_universe": (safety_raw.get("candidate_universe_created") is False),
        "d2_trade_logic_unchanged": safety_raw.get("trade_logic_changed") is False,
    }


def fixed_symbols_and_hashes(
    d2_report: Mapping[str, Any],
) -> tuple[frozenset[str], dict[str, str], bool]:
    frames, hashes = load_registered_data()
    symbols = (
        set(frames["four_hour"]["symbol"].astype(str).str.upper())
        & set(frames["eight_hour"]["symbol"].astype(str).str.upper())
        & set(frames["daily"]["symbol"].astype(str).str.upper())
        & set(frames["availability"]["symbol"].astype(str).str.upper())
    )
    fixed = normalize_symbols(
        tuple(symbols),
        expected_count=FIXED_UNIVERSE_SIZE,
    )
    expected_raw = d2_report.get("dataset_hashes")
    expected_original = (
        expected_raw.get("original_registered") if isinstance(expected_raw, Mapping) else None
    )
    match = isinstance(expected_original, Mapping) and all(
        hashes.get(name) == expected_original.get(name)
        for name in ("four_hour", "eight_hour", "daily", "availability")
    )
    return fixed, hashes, match


def validate_membership_snapshots(
    membership: pd.DataFrame,
    candidates: pd.DataFrame,
    fixed: frozenset[str],
) -> dict[str, Any]:
    required = {
        "rebalance_time",
        "fixed_count",
        "pit_count",
        "entrant_count",
        "removed_survivor_count",
        "entrants",
        "removed_survivors",
    }
    missing = sorted(required.difference(membership.columns))
    if missing:
        raise MembershipDiagnosticRunError(f"D2 membership snapshots lack columns: {missing}")
    frame = membership.copy()
    frame["rebalance_time"] = pd.to_datetime(
        frame["rebalance_time"],
        utc=True,
        errors="raise",
    )
    pit_map = weekly_pit_map(candidates)
    mismatch_count = 0
    for row in frame.itertuples(index=False):
        timestamp = pd.Timestamp(row.rebalance_time)
        pit = pit_map.get(timestamp)
        if pit is None:
            mismatch_count += 1
            continue
        entrants = pit.difference(fixed)
        removed = fixed.difference(pit)
        if any(
            (
                int(row.fixed_count) != len(fixed),
                int(row.pit_count) != len(pit),
                int(row.entrant_count) != len(entrants),
                int(row.removed_survivor_count) != len(removed),
                split_symbols(row.entrants) != entrants,
                split_symbols(row.removed_survivors) != removed,
            )
        ):
            mismatch_count += 1
    return {
        "passed": len(frame) == EXPECTED_SNAPSHOTS and mismatch_count == 0,
        "row_count": len(frame),
        "mismatch_count": mismatch_count,
    }


def expected_trade_metrics(
    d2_report: Mapping[str, Any],
) -> dict[str, dict[str, float]]:
    aggregates_raw = d2_report.get("aggregate_metrics")
    if not isinstance(aggregates_raw, Mapping):
        raise MembershipDiagnosticRunError("D2 aggregate metrics are missing.")
    result: dict[str, dict[str, float]] = {}
    for mode in MODES:
        mode_raw = aggregates_raw.get(mode)
        base_raw = mode_raw.get("BASE_COST") if isinstance(mode_raw, Mapping) else None
        if not isinstance(base_raw, Mapping):
            raise MembershipDiagnosticRunError(f"D2 BASE_COST aggregate is missing: {mode}")
        trade_count = float(base_raw.get("trade_count", -1))
        expectancy = float(base_raw.get("expectancy", float("nan")))
        result[mode] = {
            "trade_count": trade_count,
            "net_pnl": trade_count * expectancy,
        }
    return result


def validate_trade_totals(
    annotated: pd.DataFrame,
    expected: Mapping[str, Mapping[str, float]],
) -> dict[str, Any]:
    mismatches: list[str] = []
    observed: dict[str, dict[str, float]] = {}
    for mode in MODES:
        group = annotated.loc[annotated["universe_mode"].eq(mode)]
        trade_count = float(group["trade_id"].nunique())
        net_pnl = float(group["net_pnl"].sum())
        observed[mode] = {"trade_count": trade_count, "net_pnl": net_pnl}
        expected_mode = expected[mode]
        if trade_count != float(expected_mode["trade_count"]):
            mismatches.append(f"{mode}:trade_count")
        if abs(net_pnl - float(expected_mode["net_pnl"])) > 1e-7:
            mismatches.append(f"{mode}:net_pnl")
    return {
        "passed": not mismatches,
        "mismatches": mismatches,
        "observed": observed,
    }


def validate_mode_roles(annotated: pd.DataFrame) -> dict[str, Any]:
    allowed = {
        MODE_FIXED: {ROLE_COMMON, ROLE_REMOVED},
        MODE_PIT: {ROLE_COMMON, ROLE_ENTRANT},
        MODE_UNION: {ROLE_COMMON, ROLE_ENTRANT, ROLE_REMOVED},
        MODE_INTERSECTION: {ROLE_COMMON},
    }
    invalid_rows = 0
    for mode, roles in allowed.items():
        observed = set(
            annotated.loc[
                annotated["universe_mode"].eq(mode),
                "entry_membership_role",
            ].astype(str)
        )
        invalid_rows += len(observed.difference(roles))
    invalid_rows += int(annotated["entry_membership_role"].eq(ROLE_OUTSIDE).sum())
    return {"passed": invalid_rows == 0, "invalid_role_count": invalid_rows}


def symbol_diagnostics(
    annotated: pd.DataFrame,
    exposure: pd.DataFrame,
) -> pd.DataFrame:
    summary = summarize_trade_groups(
        annotated,
        ["symbol", "universe_mode", "entry_membership_role"],
    )
    return (
        summary.merge(
            exposure,
            on="symbol",
            how="left",
            validate="many_to_one",
        )
        .sort_values(
            ["pit_entrant_symbol", "symbol", "universe_mode", "entry_membership_role"],
            ascending=[False, True, True, True],
            kind="stable",
        )
        .reset_index(drop=True)
    )


def common_path_frame(
    annotated: pd.DataFrame,
    comparison: Mapping[str, Any],
) -> pd.DataFrame:
    common = annotated.loc[annotated["entry_membership_role"].eq(ROLE_COMMON)].copy()
    per_mode = summarize_trade_groups(common, ["universe_mode"])
    rows = per_mode.to_dict(orient="records")
    rows.append(
        {
            "universe_mode": "PAIRWISE_DELTAS",
            "trade_count": None,
            "net_pnl": None,
            "mean_trade_pnl": None,
            "win_rate": None,
            "profit_factor": None,
            **dict(comparison),
        }
    )
    return pd.DataFrame(rows)


def markdown(report: Mapping[str, Any]) -> str:
    decision = report["decision"]
    lines = [
        "# AMS RD04-D3 — Membership Failure Diagnostics",
        "",
        "## Executive result",
        "",
        f"- Status: `{report['status']}`",
        f"- Decision: `{decision['decision']}`",
        f"- Reason: `{decision['reason']}`",
        "- Variant: `MD01-M05`",
        (f"- Entrant net PnL in UNION: `{decision['entrant_union_net_pnl']:.6f}`"),
        f"- Entrant net PnL in PIT: `{decision['entrant_pit_net_pnl']:.6f}`",
        (
            "- Removed-survivor net PnL in FIXED: "
            f"`{decision['removed_survivor_fixed_net_pnl']:.6f}`"
        ),
        (
            "- Removed-survivor net PnL in UNION: "
            f"`{decision['removed_survivor_union_net_pnl']:.6f}`"
        ),
        (
            "- Common-member UNION minus FIXED PnL: "
            f"`{decision['union_minus_fixed_common_net_pnl']:.6f}`"
        ),
        (
            "- Common-member PIT minus INTERSECTION PnL: "
            f"`{decision['pit_minus_intersection_common_net_pnl']:.6f}`"
        ),
        (
            "- RD04-D4 hypothesis registration authorized: "
            f"`{decision['rd04_d4_hypothesis_registration_research_authorized']}`"
        ),
        "- Point-in-time universe baseline authorized: `False`",
        "- Candidate universe authorized: `False`",
        "- Universe change authorized: `False`",
        "- Trade logic changed: `False`",
        "- ATI-V1 authorized: `False`",
        "",
        "## Diagnostic contract",
        "",
        "- No portfolio simulation is rerun in D3.",
        "- D3 consumes only frozen D0C, D1, and D2 evidence.",
        "- Every trade is classified by its active Monday membership state.",
        "- Entrants, removed survivors, and common-member path effects are separated.",
        "- Rank and tenure buckets are descriptive and are not optimized.",
        "",
        "## Safety boundary",
        "",
        "- No universe, rank, weight, entry, exit, fill, cost, or cash rule changes.",
        "- No candidate universe or parameter optimization is created.",
        "- No 2025 test data or 2026 holdout data are accessed.",
        "- No production, live, Kelly, leverage, pyramiding, or averaging down.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    input_hashes_before = required_input_hashes()
    d2_report = load_json(D2_REPORT)
    d2_checks = validate_d2_report(d2_report)
    if not all(d2_checks.values()):
        failed = sorted(key for key, value in d2_checks.items() if not value)
        raise MembershipDiagnosticRunError("D2 prerequisite validation failed: " + ",".join(failed))

    fixed, registered_hashes, registered_hashes_match = fixed_symbols_and_hashes(d2_report)
    candidates = pd.read_csv(D0C_CANDIDATES)
    candidate_validation = validate_candidates(candidates)
    if candidate_validation["passed"] is not True:
        raise MembershipDiagnosticRunError(
            f"D0C candidate validation failed: {candidate_validation}"
        )
    membership = pd.read_csv(D2_MEMBERSHIP)
    membership_validation = validate_membership_snapshots(
        membership,
        candidates,
        fixed,
    )
    if membership_validation["passed"] is not True:
        raise MembershipDiagnosticRunError(
            f"D2 membership validation failed: {membership_validation}"
        )

    trades = pd.read_csv(D2_TRADES)
    annotated = annotate_trades(trades, candidates, tuple(fixed))
    trade_validation = validate_trade_totals(
        annotated,
        expected_trade_metrics(d2_report),
    )
    mode_role_validation = validate_mode_roles(annotated)

    exposure = build_membership_exposure(candidates, tuple(fixed))
    role_summary = summarize_trade_groups(
        annotated,
        ["universe_mode", "fold_id", "entry_membership_role", "alignment_tier"],
    )
    symbol_summary = symbol_diagnostics(annotated, exposure)
    entrants = annotated.loc[
        annotated["entry_membership_role"].eq(ROLE_ENTRANT)
        & annotated["universe_mode"].isin([MODE_UNION, MODE_PIT])
    ].copy()
    removed = annotated.loc[
        annotated["entry_membership_role"].eq(ROLE_REMOVED)
        & annotated["universe_mode"].isin([MODE_FIXED, MODE_UNION])
    ].copy()
    rank_tenure = summarize_trade_groups(
        entrants,
        [
            "universe_mode",
            "fold_id",
            "entry_market_cap_rank_bucket",
            "entry_pit_tenure_bucket",
            "alignment_tier",
        ],
    )
    common_path = common_path_comparison(annotated)
    common_path_table = common_path_frame(annotated, common_path)
    pnl_by_role = role_totals(annotated)

    entries = pd.to_datetime(annotated["entry_time"], utc=True, errors="raise")
    exits = pd.to_datetime(annotated["exit_time"], utc=True, errors="raise")
    input_hashes_after = required_input_hashes()
    structural_checks = {
        **d2_checks,
        "registered_dataset_hashes_match_d2": registered_hashes_match,
        "candidate_schedule_valid": candidate_validation["passed"] is True,
        "membership_snapshots_match_candidates": (membership_validation["passed"] is True),
        "trade_totals_match_d2": trade_validation["passed"] is True,
        "mode_roles_valid": mode_role_validation["passed"] is True,
        "annotated_trade_count_matches": len(annotated) == len(trades),
        "no_outside_membership_trades": not bool(
            annotated["entry_membership_role"].eq(ROLE_OUTSIDE).any()
        ),
        "no_2025_entries": bool((entries < pd.Timestamp("2025-01-01T00:00:00Z")).all()),
        "no_post_lock_exits": bool((exits <= pd.Timestamp("2025-01-01T00:00:00Z")).all()),
        "input_hashes_invariant": input_hashes_before == input_hashes_after,
        "no_portfolio_simulation_executed": True,
    }
    decision = build_diagnostic_decision(
        role_pnl=pnl_by_role,
        common_path=common_path,
        structural_checks=structural_checks,
    )

    d2_base_raw = d2_report.get("base_cost_return_attribution")
    d2_base = dict(d2_base_raw) if isinstance(d2_base_raw, Mapping) else {}
    validation = {
        "status": "COMPLETE" if all(structural_checks.values()) else "INVALID",
        **structural_checks,
        "fixed_symbol_count": len(fixed),
        "pit_candidate_row_count": len(candidates),
        "pit_snapshot_count": int(candidate_validation["snapshot_count"]),
        "annotated_trade_count": len(annotated),
        "entrant_trade_count": len(entrants),
        "removed_survivor_trade_count": len(removed),
    }
    if validation["status"] != "COMPLETE":
        raise MembershipDiagnosticRunError(
            "D3 structural validation failed before evidence publication."
        )

    write_csv(EXPOSURE_CSV, exposure)
    write_csv(ANNOTATED_TRADES_CSV, annotated)
    write_csv(ROLE_SUMMARY_CSV, role_summary)
    write_csv(SYMBOL_CSV, symbol_summary)
    write_csv(ENTRANT_CSV, entrants)
    write_csv(REMOVED_CSV, removed)
    write_csv(RANK_TENURE_CSV, rank_tenure)
    write_csv(COMMON_PATH_CSV, common_path_table)

    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "research_stage": "RD04-D3",
        "variant_id": "MD01-M05",
        "status": "COMPLETE",
        "generated_at": utc_now(),
        "source_commit": source_commit(),
        "upstream": {
            "rd04_d2_decision": d2_report.get("decision", {}).get("decision")
            if isinstance(d2_report.get("decision"), Mapping)
            else None,
            "rd04_d2_source_commit": d2_report.get("source_commit"),
            "rd04_d2_report": D2_REPORT.relative_to(ROOT).as_posix(),
            "rd04_d2_base_cost_trades": D2_TRADES.relative_to(ROOT).as_posix(),
            "rd04_d0c_weekly_candidates": D0C_CANDIDATES.relative_to(ROOT).as_posix(),
        },
        "input_hashes": input_hashes_before,
        "registered_dataset_hashes": registered_hashes,
        "d2_base_cost_return_attribution": d2_base,
        "candidate_validation": candidate_validation,
        "membership_validation": membership_validation,
        "trade_validation": trade_validation,
        "mode_role_validation": mode_role_validation,
        "membership_summary": {
            "fixed_symbol_count": len(fixed),
            "pit_ever_symbol_count": int(exposure["pit_ever_member"].astype(bool).sum()),
            "pit_entrant_symbol_count": int(exposure["pit_entrant_symbol"].astype(bool).sum()),
            "fixed_only_symbol_count": int(
                (
                    exposure["fixed_survivor_member"].astype(bool)
                    & ~exposure["pit_ever_member"].astype(bool)
                ).sum()
            ),
            "snapshot_count": EXPECTED_SNAPSHOTS,
            "candidate_row_count": EXPECTED_PIT_ROWS,
        },
        "role_pnl": {
            f"{mode}|{role}": value for (mode, role), value in sorted(pnl_by_role.items())
        },
        "common_path_comparison": common_path,
        "decision": decision,
        "validation": validation,
        "outputs": {
            "membership_exposure": EXPOSURE_CSV.relative_to(ROOT).as_posix(),
            "trade_membership_attribution": (ANNOTATED_TRADES_CSV.relative_to(ROOT).as_posix()),
            "role_summary": ROLE_SUMMARY_CSV.relative_to(ROOT).as_posix(),
            "symbol_diagnostics": SYMBOL_CSV.relative_to(ROOT).as_posix(),
            "entrant_trade_diagnostics": ENTRANT_CSV.relative_to(ROOT).as_posix(),
            "removed_survivor_opportunity": REMOVED_CSV.relative_to(ROOT).as_posix(),
            "rank_tenure_diagnostics": RANK_TENURE_CSV.relative_to(ROOT).as_posix(),
            "common_path_comparison": COMMON_PATH_CSV.relative_to(ROOT).as_posix(),
        },
        "authorizations": {
            "rd04_d4_hypothesis_registration_research_authorized": decision[
                "rd04_d4_hypothesis_registration_research_authorized"
            ],
            "point_in_time_universe_research_baseline_authorized": False,
            "candidate_universe_authorized": False,
            "universe_change_authorized": False,
            "ranking_change_authorized": False,
            "weight_change_authorized": False,
            "entry_change_authorized": False,
            "exit_change_authorized": False,
            "ati_v1_authorized": False,
            "production_ready": False,
            "live_ready": False,
        },
        "safety": {
            "portfolio_simulation_executed": False,
            "portfolio_simulation_changed": False,
            "trade_logic_changed": False,
            "parameter_optimisation_used": False,
            "candidate_universe_created": False,
            "test_2025_accessed": False,
            "holdout_2026_accessed": False,
            "leverage_used": False,
            "kelly_used": False,
            "pyramiding_authorized": False,
            "averaging_down_authorized": False,
        },
    }
    atomic_json(REPORT_JSON, finite(report))
    report_text = markdown(report)
    atomic_text(REPORT_MD, report_text)
    atomic_text(FINAL_COPY, report_text)

    print("RD04_D3_STATUS=COMPLETE")
    print(f"DECISION={decision['decision']}")
    print(f"ENTRANT_UNION_NET_PNL={decision['entrant_union_net_pnl']}")
    print(f"ENTRANT_PIT_NET_PNL={decision['entrant_pit_net_pnl']}")
    print(f"REMOVED_SURVIVOR_FIXED_NET_PNL={decision['removed_survivor_fixed_net_pnl']}")
    print(f"REMOVED_SURVIVOR_UNION_NET_PNL={decision['removed_survivor_union_net_pnl']}")
    print(f"COMMON_UNION_MINUS_FIXED_NET_PNL={decision['union_minus_fixed_common_net_pnl']}")
    print(
        f"COMMON_PIT_MINUS_INTERSECTION_NET_PNL={decision['pit_minus_intersection_common_net_pnl']}"
    )
    print(
        "RD04_D4_HYPOTHESIS_REGISTRATION_RESEARCH_AUTHORIZED="
        f"{decision['rd04_d4_hypothesis_registration_research_authorized']}"
    )
    print("POINT_IN_TIME_UNIVERSE_RESEARCH_BASELINE_AUTHORIZED=False")
    print("CANDIDATE_UNIVERSE_AUTHORIZED=False")
    print("UNIVERSE_CHANGE_AUTHORIZED=False")
    print("TRADE_LOGIC_CHANGED=False")
    print("ATI_V1_AUTHORIZED=False")


if __name__ == "__main__":
    main()
