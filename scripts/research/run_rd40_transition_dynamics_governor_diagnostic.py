from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from spotbot.research.rd40_transition_dynamics_governor import (  # noqa: E402
    CAUTION,
    CONTROL_POLICY,
    CONTROL_PORTFOLIO,
    DATA_CUTOFF,
    DATA_START,
    DIAGNOSTIC_COST_MULTIPLIER,
    FAILURE_DECISION,
    FAILURE_NEXT,
    FAMILY_ORDER,
    GOVERNOR_POLICY,
    GOVERNOR_STATES,
    LANE_ORDER,
    PERIODS,
    RECLAIM_VETO,
    SUCCESS_DECISION,
    SUCCESS_NEXT,
    UNIVERSES,
    build_cell_outcomes,
    build_governor_timelines,
    build_markout_ledger,
    events_from_state_rows,
    governor_state_at,
    lane_diagnostic_summary,
    lifecycle_snapshot,
    negative_family_qualification,
    normalize_governor_transitions,
    normalize_price_frame,
    period_for,
    price_lookup,
    recovery_veto_qualification,
    summarize_markouts,
    utc,
    validate_constants,
)

P1_FREEZE = "f24387521076622b1d13334b3c30d9a7ee2e42d1"

P1_PROTOCOL = Path(
    "data/research/rd40_p1/"
    "rd40-p1-trade-transition-dynamics-x-rd31-governor-"
    "preregistration-v1.json"
)
P1_PROTOCOL_BLOB = "c7b3aa8fb143033948769f63257599a8c153e03a"
P1_PROTOCOL_SHA256 = "799d8f0b05e420c81fe297ba6d46e6199192ebe12613aeeb831746bc9f3cc949"
P1_AUDIT = Path("data/research/rd40_p1/rd40-p1-preregistration-audit-v1.json")
P1_AUDIT_BLOB = "9c0609af178a55404672ccfbe1249e18f61054ae"

RD32_TRADES = Path("data/research/rd32_p3_runtime/trade-ledger.csv")
RD32_TRADES_BLOB = "6749de85cb14733388e0f76a6557124d3212398b"
RD32_TRADES_SHA256 = "07f49e0e9235f736f54ee9dd59142c16fc4e7b99e83781b1ee26b9338def117e"

RD31_TRANSITIONS = Path("data/research/rd31_p1_runtime/governor-transition-ledger.csv")
RD31_TRANSITIONS_SHA256 = "46c36f91041912ebcfefdbe2d710bb090d73b3aeea65cabad2be71ad138e640b"
RD31_OCCUPANCY = Path("data/research/rd31_p1_runtime/governor-clock-hour-occupancy.csv")
RD31_OCCUPANCY_SHA256 = "634b0d316b4e6792971053e4907a554e3f50f6c79c60db87f8c3406b8f538985"

KUCOIN_ROOT = Path("data/raw/rd16b/kucoin")
OUTPUT = Path("data/research/rd40_p2_runtime")

OUTPUT_NAMES = (
    "input-and-conformance-audit.json",
    "data-completeness-summary.csv",
    "governor-occupancy-parity.csv",
    "lifecycle-hour-summary.csv",
    "event-ledger.csv",
    "event-summary.csv",
    "target-markout-ledger.csv",
    "target-markout-summary.csv",
    "cell-outcome-evaluation.csv",
    "negative-family-qualification.csv",
    "locked-vs-open-contrast.csv",
    "recovery-veto-evaluation.csv",
    "lane-diagnostic-summary.csv",
    "qualified-transition-evidence-freeze.json",
    "rd40-p2-transition-dynamics-x-governor-diagnostic-report-v1.json",
)


class RunnerError(RuntimeError):
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
        raise RunnerError(f"git {' '.join(args)} failed: {result.stderr}")
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
        raise RunnerError(f"JSON object expected: {path}")
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


def verify_blob(
    repo: Path,
    path: Path,
    expected: str,
    label: str,
) -> None:
    actual = git(repo, "rev-parse", f"HEAD:{path.as_posix()}")
    if actual != expected:
        raise RunnerError(f"{label} blob drift: {actual} != {expected}")


def verify_lineage(
    repo: Path,
    expected_freeze_commit: str,
) -> dict[str, Any]:
    if git(repo, "diff", "--cached", "--name-only", "--"):
        raise RunnerError("staged tracked changes before RD40 P2")
    if git(repo, "diff", "--name-only", "--"):
        raise RunnerError("unstaged tracked changes before RD40 P2")

    head = git(repo, "rev-parse", "HEAD")
    if head != expected_freeze_commit:
        raise RunnerError(f"RD40 P2 HEAD {head} != freeze {expected_freeze_commit}")
    if git(repo, "rev-parse", "HEAD^") != P1_FREEZE:
        raise RunnerError("RD40 P2 freeze parent is not P1")

    for path, blob, label in (
        (P1_PROTOCOL, P1_PROTOCOL_BLOB, "P1 protocol"),
        (P1_AUDIT, P1_AUDIT_BLOB, "P1 audit"),
        (RD32_TRADES, RD32_TRADES_BLOB, "RD32 trade ledger"),
    ):
        verify_blob(repo, path, blob, label)

    if sha256(repo / P1_PROTOCOL) != P1_PROTOCOL_SHA256:
        raise RunnerError("P1 protocol SHA drifted")
    if sha256(repo / RD32_TRADES) != RD32_TRADES_SHA256:
        raise RunnerError("RD32 trade-ledger SHA drifted")
    if sha256(repo / RD31_TRANSITIONS) != RD31_TRANSITIONS_SHA256:
        raise RunnerError("RD31 transition-ledger SHA drifted")
    if sha256(repo / RD31_OCCUPANCY) != RD31_OCCUPANCY_SHA256:
        raise RunnerError("RD31 occupancy SHA drifted")

    protocol = load_json(repo / P1_PROTOCOL)
    audit = load_json(repo / P1_AUDIT)
    if protocol.get("status") != "FROZEN_PRE_DATA_DIAGNOSTIC":
        raise RunnerError("P1 protocol not frozen")
    if protocol.get("next_stage") != (
        "RD40_P2_FREEZE_AND_RUN_TRANSITION_DYNAMICS_X_RD31_GOVERNOR_DIAGNOSTIC_2022_2023_ONCE"
    ):
        raise RunnerError("P1 next-stage drifted")
    if audit.get("protocol_sha256") != P1_PROTOCOL_SHA256:
        raise RunnerError("P1 audit protocol SHA drifted")

    for field in (
        "control_trade_rows_loaded",
        "raw_market_data_loaded",
        "rd31_transition_rows_loaded_for_analysis",
        "temporal_path_features_computed",
        "events_observed",
        "forward_returns_computed",
        "economic_execution_performed",
        "2024_accessed",
    ):
        if audit.get(field) is not False:
            raise RunnerError(f"P1 pre-data flag drifted: {field}")

    validate_constants()
    return {
        "runner_freeze_commit": expected_freeze_commit,
        "p1_freeze_commit": P1_FREEZE,
        "p1_protocol_git_blob": P1_PROTOCOL_BLOB,
        "p1_protocol_sha256": P1_PROTOCOL_SHA256,
        "p1_audit_git_blob": P1_AUDIT_BLOB,
        "rd32_trade_ledger_git_blob": RD32_TRADES_BLOB,
        "rd32_trade_ledger_sha256": RD32_TRADES_SHA256,
        "rd31_transition_ledger_sha256": RD31_TRANSITIONS_SHA256,
        "rd31_occupancy_sha256": RD31_OCCUPANCY_SHA256,
    }


def load_control_trades(repo: Path) -> pd.DataFrame:
    frame = pd.read_csv(repo / RD32_TRADES, low_memory=False)
    required = {
        "policy_id",
        "portfolio_id",
        "universe_id",
        "cost_multiplier",
        "pair",
        "entry_time",
        "exit_time",
        "entry_price",
        "exit_reason",
        "period_id",
    }
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise RunnerError(f"RD32 trade ledger missing fields: {missing}")

    frame = frame.loc[
        (frame["policy_id"].astype(str) == CONTROL_POLICY)
        & (frame["portfolio_id"].astype(str) == CONTROL_PORTFOLIO)
        & frame["universe_id"].astype(str).isin(UNIVERSES)
        & np.isclose(
            pd.to_numeric(frame["cost_multiplier"], errors="coerce"),
            DIAGNOSTIC_COST_MULTIPLIER,
        )
    ].copy()
    if frame.empty:
        raise RunnerError("RD40 frozen 1x control trade set is empty")

    for column in ("entry_time", "exit_time"):
        frame[column] = pd.to_datetime(
            frame[column],
            utc=True,
            errors="raise",
        ).dt.as_unit("ns")

    frame["entry_price"] = pd.to_numeric(
        frame["entry_price"],
        errors="raise",
    ).astype(float)

    if frame["entry_time"].min() < DATA_START:
        raise RunnerError("pre-2022 control trade entered RD40")
    if frame["exit_time"].max() >= DATA_CUTOFF:
        raise RunnerError("2024+ control trade entered RD40")
    if not bool((frame["entry_time"] < frame["exit_time"]).all()):
        raise RunnerError("invalid control trade interval")
    if bool((frame["entry_price"] <= 0.0).any()):
        raise RunnerError("non-positive frozen entry price")

    frame = frame.sort_values(
        ["universe_id", "entry_time", "pair", "exit_time"],
        kind="stable",
    ).reset_index(drop=True)
    frame["control_trade_id"] = np.arange(len(frame), dtype=np.int64)
    return frame


def load_and_verify_governor(
    repo: Path,
) -> tuple[
    pd.DataFrame,
    dict[str, tuple[list[int], list[str]]],
    pd.DataFrame,
]:
    raw = pd.read_csv(repo / RD31_TRANSITIONS, low_memory=False)
    transitions = normalize_governor_transitions(raw)
    timelines = build_governor_timelines(transitions)

    occupancy = pd.read_csv(repo / RD31_OCCUPANCY, low_memory=False)
    required = {
        "policy_id",
        "portfolio_id",
        "universe_id",
        "governor_state",
        "clock_hour_count",
        "clock_hour_fraction",
    }
    missing = sorted(required.difference(occupancy.columns))
    if missing:
        raise RunnerError(f"RD31 occupancy missing fields: {missing}")

    frozen = occupancy.loc[
        (occupancy["policy_id"].astype(str) == GOVERNOR_POLICY)
        & (occupancy["portfolio_id"].astype(str) == CONTROL_PORTFOLIO)
        & occupancy["universe_id"].astype(str).isin(UNIVERSES)
        & occupancy["governor_state"].astype(str).isin(GOVERNOR_STATES)
    ].copy()

    hours = pd.date_range(
        DATA_START,
        DATA_CUTOFF - pd.Timedelta(hours=1),
        freq="h",
        tz="UTC",
    )
    parity_rows: list[dict[str, Any]] = []
    for universe in UNIVERSES:
        reconstructed = [
            governor_state_at(
                timelines,
                universe=universe,
                decision_time=timestamp,
            )
            for timestamp in hours
        ]
        for state in GOVERNOR_STATES:
            observed = int(sum(value == state for value in reconstructed))
            cell = frozen.loc[
                (frozen["universe_id"].astype(str) == universe)
                & (frozen["governor_state"].astype(str) == state)
            ]
            if len(cell) != 1:
                raise RunnerError(f"expected one frozen occupancy cell: {universe}/{state}")
            expected = int(cell.iloc[0]["clock_hour_count"])
            parity_rows.append(
                {
                    "universe_id": universe,
                    "governor_state": state,
                    "frozen_clock_hour_count": expected,
                    "reconstructed_clock_hour_count": observed,
                    "count_delta": observed - expected,
                    "parity_pass": observed == expected,
                    "causal_state_rule": ("LATEST_NEXT_STATE_WITH_ACTION_TIME_LE_DECISION_T"),
                }
            )
    parity = pd.DataFrame.from_records(parity_rows)
    if not bool(parity["parity_pass"].all()):
        raise RunnerError("RD31 governor occupancy reconstruction parity failed")

    return transitions, timelines, parity


def required_pairs(control: pd.DataFrame) -> list[str]:
    pairs = sorted(control["pair"].astype(str).unique())
    if not pairs:
        raise RunnerError("no required KuCoin pairs")
    return pairs


def load_prices(
    repo: Path,
    pairs: list[str],
) -> tuple[
    dict[str, dict[int, tuple[float, float, float, float]]],
    pd.DataFrame,
]:
    lookups: dict[str, dict[int, tuple[float, float, float, float]]] = {}
    completeness_rows: list[dict[str, Any]] = []
    start = DATA_START.to_pydatetime()
    cutoff = DATA_CUTOFF.to_pydatetime()
    expected_hours = int((DATA_CUTOFF - DATA_START).total_seconds() // 3600)

    for index, pair in enumerate(pairs, start=1):
        path = repo / KUCOIN_ROOT / pair / "1h.parquet"
        if not path.is_file():
            raise RunnerError(f"KuCoin source missing: {path}")

        raw = pd.read_parquet(
            path,
            columns=["timestamp", "open", "high", "low", "close"],
            engine="pyarrow",
            filters=[
                ("timestamp", ">=", start),
                ("timestamp", "<", cutoff),
            ],
        )
        frame = normalize_price_frame(raw, pair=pair)
        lookup = price_lookup(frame)
        lookups[pair] = lookup

        observed = len(frame)
        completeness_rows.append(
            {
                "pair": pair,
                "period_start": DATA_START,
                "period_end_exclusive": DATA_CUTOFF,
                "expected_clock_hour_count": expected_hours,
                "observed_valid_count": observed,
                "zero_activity_during_known_halt_count": 0,
                "missing_count": expected_hours - observed,
                "data_completeness_class_for_present_rows": "OBSERVED_VALID",
                "zero_activity_inferred_from_flat_ohlc": False,
                "imputation_used": False,
                "forward_fill_used": False,
                "backfill_used": False,
                "synthetic_bar_used": False,
            }
        )
        print(
            f"RD40_P2_SOURCE={index}/{len(pairs)}:{pair}:rows={observed}",
            flush=True,
        )

    return lookups, pd.DataFrame.from_records(completeness_rows)


def build_states(
    control: pd.DataFrame,
    lookups: dict[str, dict[int, tuple[float, float, float, float]]],
    timelines: dict[str, tuple[list[int], list[str]]],
) -> tuple[list[dict[str, Any]], pd.DataFrame]:
    state_rows: list[dict[str, Any]] = []
    counters: dict[tuple[str, str], dict[str, int]] = {
        (universe, period): {
            "eligible_decision_hour_count": 0,
            "evaluable_decision_hour_count": 0,
            "unevaluable_decision_hour_count": 0,
            "evaluable_open_count": 0,
            "evaluable_caution_count": 0,
            "evaluable_locked_count": 0,
        }
        for universe in UNIVERSES
        for period in PERIODS
    }

    trades = control.to_dict(orient="records")
    for trade in trades:
        trade_id = int(trade["control_trade_id"])
        universe = str(trade["universe_id"])
        pair = str(trade["pair"])
        entry = utc(trade["entry_time"])
        control_exit = utc(trade["exit_time"])
        first = entry + pd.Timedelta(hours=48)
        last = control_exit - pd.Timedelta(hours=24)
        decisions = list(pd.date_range(first, last, freq="h", tz="UTC")) if first <= last else []

        lookup = lookups[pair]
        for decision in decisions:
            period = period_for(decision)
            cell = counters[(universe, period)]
            cell["eligible_decision_hour_count"] += 1

            snapshot = lifecycle_snapshot(
                lookup,
                entry_time=entry,
                entry_price=float(trade["entry_price"]),
                control_exit_time=control_exit,
                decision_time=decision,
            )
            if snapshot is None:
                cell["unevaluable_decision_hour_count"] += 1
                continue

            governor_state = governor_state_at(
                timelines,
                universe=universe,
                decision_time=decision,
            )
            cell["evaluable_decision_hour_count"] += 1
            if governor_state == "OPEN":
                cell["evaluable_open_count"] += 1
            elif governor_state == "CAUTION":
                cell["evaluable_caution_count"] += 1
            elif governor_state == "LOCKED":
                cell["evaluable_locked_count"] += 1
            else:
                raise RunnerError(f"unexpected governor state: {governor_state}")

            state_rows.append(
                {
                    "control_trade_id": trade_id,
                    "universe_id": universe,
                    "period_id": period,
                    "pair": pair,
                    "entry_time": entry,
                    "control_exit_time": control_exit,
                    "entry_price": float(trade["entry_price"]),
                    "governor_state": governor_state,
                    **snapshot,
                }
            )

    summary_rows: list[dict[str, Any]] = []
    for universe in UNIVERSES:
        for period in PERIODS:
            cell = counters[(universe, period)]
            eligible = cell["eligible_decision_hour_count"]
            evaluable = cell["evaluable_decision_hour_count"]
            summary_rows.append(
                {
                    "universe_id": universe,
                    "period_id": period,
                    **cell,
                    "evaluable_share": (evaluable / eligible if eligible else np.nan),
                    "missing_path_imputation_used": False,
                    "event_state_preserved_across_unevaluable_gap": False,
                }
            )

    return state_rows, pd.DataFrame.from_records(summary_rows)


def event_summary(events: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for family in FAMILY_ORDER:
        for lane in LANE_ORDER:
            for universe in UNIVERSES:
                for period in PERIODS:
                    cell = events.loc[
                        (events["family_id"] == family)
                        & (events["lane_id"] == lane)
                        & (events["universe_id"] == universe)
                        & (events["period_id"] == period)
                    ]
                    rows.append(
                        {
                            "family_id": family,
                            "lane_id": lane,
                            "universe_id": universe,
                            "period_id": period,
                            "event_count": int(len(cell)),
                            "trade_count": int(cell["control_trade_id"].nunique()),
                            "pair_count": int(cell["pair"].astype(str).nunique()),
                            "signal_day_count": int(
                                pd.to_datetime(
                                    cell["decision_time"],
                                    utc=True,
                                    errors="coerce",
                                )
                                .dt.floor("D")
                                .nunique()
                            ),
                        }
                    )
    return pd.DataFrame.from_records(rows)


def execute(
    repo: Path,
    expected_freeze_commit: str,
) -> dict[str, Any]:
    lineage = verify_lineage(repo, expected_freeze_commit)
    if (repo / OUTPUT).exists():
        raise RunnerError("RD40 P2 runtime already exists; preserve and validate/recover")

    # Governor parity is checked before market-price feature computation.
    transitions, timelines, governor_parity = load_and_verify_governor(repo)
    control = load_control_trades(repo)
    pairs = required_pairs(control)
    lookups, completeness = load_prices(repo, pairs)

    state_rows, hour_summary = build_states(
        control,
        lookups,
        timelines,
    )
    events = events_from_state_rows(state_rows)
    del state_rows

    markouts = build_markout_ledger(events, lookups)
    markout_summary = summarize_markouts(markouts)
    cells = build_cell_outcomes(markout_summary)
    negative_qualification, contrast = negative_family_qualification(cells)
    recovery_veto = recovery_veto_qualification(cells)
    lane_summary = lane_diagnostic_summary(cells)

    advancing = []
    for row in negative_qualification.to_dict(orient="records"):
        if bool(row["advances_to_action_mapping"]):
            advancing.append(
                {
                    "family_id": str(row["family_id"]),
                    "modes": str(row["advancing_modes"]).split("|"),
                }
            )

    recovery_veto_qualified = bool(recovery_veto["recovery_veto_candidate_qualified"].iloc[0])
    success = bool(advancing)
    decision = SUCCESS_DECISION if success else FAILURE_DECISION
    next_stage = SUCCESS_NEXT if success else FAILURE_NEXT

    output = repo / OUTPUT
    output.mkdir(parents=True, exist_ok=False)

    audit = {
        "schema_version": "rd40-p2-input-and-conformance-audit-v1",
        "stage": "RD40_P2_TRANSITION_DYNAMICS_X_RD31_GOVERNOR_DIAGNOSTIC",
        "status": "PASS",
        "lineage": lineage,
        "control_policy": CONTROL_POLICY,
        "control_portfolio": CONTROL_PORTFOLIO,
        "governor_policy": GOVERNOR_POLICY,
        "diagnostic_cost_multiplier": DIAGNOSTIC_COST_MULTIPLIER,
        "control_trade_count": len(control),
        "required_pair_count": len(pairs),
        "required_pairs": pairs,
        "governor_transition_row_count": len(transitions),
        "governor_occupancy_parity_pass": bool(governor_parity["parity_pass"].all()),
        "governor_state_reestimated_or_refit": False,
        "calendar_year_used_as_feature_or_rule": False,
        "feature_clock": "COMPLETED_BAR_t_minus_1",
        "decision_clock": "KUCOIN_SPOT_1H_OPEN_t",
        "decision_open_required": True,
        "minimum_holding_age_hours": 48,
        "primary_event_remaining_hours": 24,
        "missing_path_imputation_used": False,
        "forward_fill_used": False,
        "backfill_used": False,
        "synthetic_bar_used": False,
        "zero_activity_inferred_from_flat_ohlc": False,
        "rd39_family_state_reused": False,
        "rd39_event_ledger_loaded": False,
        "control_exit_reason_used_in_feature_logic": False,
        "control_exit_time_used_only_as_eligibility_boundary": True,
        "control_trade_rows_loaded": True,
        "raw_market_data_loaded": True,
        "rd31_transition_rows_loaded_for_analysis": True,
        "temporal_path_features_computed": True,
        "global_events_observed": True,
        "governor_conditioned_events_observed": True,
        "forward_returns_computed": True,
        "economic_execution_performed": False,
        "full_liquidation_performed": False,
        "partial_derisk_performed": False,
        "shadow_pnl_computed": False,
        "portfolio_accounting_performed": False,
        "capital_reuse_performed": False,
        "parameter_search_used": False,
        "threshold_optimization_used": False,
        "best_lane_selection_used": False,
        "winner_selection_used": False,
        "sensitivity_merge_used_for_qualification": False,
        "caution_threshold_relaxation_used": False,
        "2024_accessed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
    }
    write_json(output / "input-and-conformance-audit.json", audit)

    completeness.to_csv(
        output / "data-completeness-summary.csv",
        index=False,
        lineterminator="\n",
    )
    governor_parity.to_csv(
        output / "governor-occupancy-parity.csv",
        index=False,
        lineterminator="\n",
    )
    hour_summary.to_csv(
        output / "lifecycle-hour-summary.csv",
        index=False,
        lineterminator="\n",
    )
    events.to_csv(
        output / "event-ledger.csv",
        index=False,
        lineterminator="\n",
    )
    event_summary(events).to_csv(
        output / "event-summary.csv",
        index=False,
        lineterminator="\n",
    )
    markouts.to_csv(
        output / "target-markout-ledger.csv",
        index=False,
        lineterminator="\n",
    )
    markout_summary.to_csv(
        output / "target-markout-summary.csv",
        index=False,
        lineterminator="\n",
    )
    cells.to_csv(
        output / "cell-outcome-evaluation.csv",
        index=False,
        lineterminator="\n",
    )
    negative_qualification.to_csv(
        output / "negative-family-qualification.csv",
        index=False,
        lineterminator="\n",
    )
    contrast.to_csv(
        output / "locked-vs-open-contrast.csv",
        index=False,
        lineterminator="\n",
    )
    recovery_veto.to_csv(
        output / "recovery-veto-evaluation.csv",
        index=False,
        lineterminator="\n",
    )
    lane_summary.to_csv(
        output / "lane-diagnostic-summary.csv",
        index=False,
        lineterminator="\n",
    )

    freeze = {
        "schema_version": "rd40-p2-qualified-transition-evidence-freeze-v1",
        "status": "PASS",
        "advancing_negative_evidence": advancing,
        "advancing_negative_family_count": len(advancing),
        "recovery_veto_candidate": RECLAIM_VETO,
        "recovery_veto_candidate_qualified": recovery_veto_qualified,
        "recovery_veto_direct_exit_selection_eligible": False,
        "decision": decision,
        "next_stage": next_stage,
        "caution_low_support_expected_before_execution": True,
        "caution_threshold_relaxation_used": False,
        "sensitivity_merge_used_for_qualification": False,
        "rd39_failed_family_rescue_used": False,
        "best_lane_selection_used": False,
        "winner_selection_used": False,
        "parameter_search_used": False,
        "threshold_optimization_used": False,
        "economic_execution_performed": False,
        "production_authorized": False,
    }
    write_json(
        output / "qualified-transition-evidence-freeze.json",
        freeze,
    )

    report = {
        "schema_version": ("rd40-p2-transition-dynamics-x-governor-diagnostic-report-v1"),
        "stage": "RD40_P2_TRANSITION_DYNAMICS_X_RD31_GOVERNOR_DIAGNOSTIC",
        "status": "PASS",
        "runner_freeze_commit": expected_freeze_commit,
        "source_p1_freeze_commit": P1_FREEZE,
        "control_trade_count": len(control),
        "governor_transition_row_count": len(transitions),
        "event_count": int(len(events)),
        "target_markout_count": int(len(markouts)),
        "advancing_negative_evidence": advancing,
        "recovery_veto_candidate_qualified": recovery_veto_qualified,
        "regime_direction_reversal_families": negative_qualification.loc[
            negative_qualification["regime_direction_reversal_pattern"].astype(bool),
            "family_id",
        ]
        .astype(str)
        .tolist(),
        "decision": decision,
        "next_stage": next_stage,
        "governor_occupancy_parity_pass": True,
        "caution_low_support_expected_before_execution": True,
        "caution_threshold_relaxation_used": False,
        "sensitivity_merge_used_for_qualification": False,
        "rd39_failed_family_rescue_used": False,
        "calendar_year_used_as_feature_or_rule": False,
        "economic_execution_performed": False,
        "full_liquidation_performed": False,
        "partial_derisk_performed": False,
        "shadow_pnl_computed": False,
        "portfolio_accounting_performed": False,
        "capital_reuse_performed": False,
        "parameter_search_used": False,
        "threshold_optimization_used": False,
        "best_lane_selection_used": False,
        "winner_selection_used": False,
        "2024_accessed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
    }
    write_json(
        output / "rd40-p2-transition-dynamics-x-governor-diagnostic-report-v1.json",
        report,
    )

    files: dict[str, dict[str, Any]] = {}
    for name in OUTPUT_NAMES:
        path = output / name
        if not path.is_file():
            raise RunnerError(f"manifest source missing: {name}")
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
    write_json(
        output / "output-manifest.json",
        {
            "schema_version": "rd40-p2-output-manifest-v1",
            "file_count": len(files),
            "files": files,
            "deterministic_hash": hashlib.sha256(canonical).hexdigest(),
            "decision": decision,
            "runner_freeze_commit": expected_freeze_commit,
        },
    )
    return validate_outputs(repo)


def validate_outputs(repo: Path) -> dict[str, Any]:
    output = repo / OUTPUT
    if not output.is_dir():
        raise RunnerError("RD40 P2 runtime missing")

    expected = sorted((*OUTPUT_NAMES, "output-manifest.json"))
    observed = sorted(path.name for path in output.iterdir() if path.is_file())
    if observed != expected:
        raise RunnerError(f"RD40 P2 output registry drift: {observed} != {expected}")

    report = load_json(output / "rd40-p2-transition-dynamics-x-governor-diagnostic-report-v1.json")
    freeze = load_json(output / "qualified-transition-evidence-freeze.json")
    parity = pd.read_csv(
        output / "governor-occupancy-parity.csv",
        low_memory=False,
    )
    hours = pd.read_csv(
        output / "lifecycle-hour-summary.csv",
        low_memory=False,
    )
    events = pd.read_csv(
        output / "event-ledger.csv",
        low_memory=False,
    )
    markout_summary = pd.read_csv(
        output / "target-markout-summary.csv",
        low_memory=False,
    )
    cells = pd.read_csv(
        output / "cell-outcome-evaluation.csv",
        low_memory=False,
    )
    negative = pd.read_csv(
        output / "negative-family-qualification.csv",
        low_memory=False,
    )
    contrast = pd.read_csv(
        output / "locked-vs-open-contrast.csv",
        low_memory=False,
    )
    veto = pd.read_csv(
        output / "recovery-veto-evaluation.csv",
        low_memory=False,
    )
    lane_summary = pd.read_csv(
        output / "lane-diagnostic-summary.csv",
        low_memory=False,
    )

    if len(parity) != 9 or not bool(parity["parity_pass"].all()):
        raise RunnerError("governor occupancy parity invalid")
    if len(hours) != 6:
        raise RunnerError("lifecycle-hour summary must have six cells")
    if len(markout_summary) != 432:
        raise RunnerError("target markout summary must have 432 cells")
    if len(cells) != 144:
        raise RunnerError("cell outcome evaluation must have 144 rows")
    if len(negative) != 3:
        raise RunnerError("negative qualification must have three rows")
    if len(contrast) != 18:
        raise RunnerError("contrast table must have 18 rows")
    if len(veto) != 6:
        raise RunnerError("recovery veto evaluation must have six rows")
    if len(lane_summary) != 48:
        raise RunnerError("lane diagnostic summary must have 48 rows")

    if len(events):
        decisions = pd.to_datetime(
            events["decision_time"],
            utc=True,
            errors="raise",
        )
        exits = pd.to_datetime(
            events["control_exit_time"],
            utc=True,
            errors="raise",
        )
        entries = pd.to_datetime(
            events["entry_time"],
            utc=True,
            errors="raise",
        )
        if decisions.min() < DATA_START or decisions.max() >= DATA_CUTOFF:
            raise RunnerError("event outside frozen 2022-2023 range")
        if exits.max() >= DATA_CUTOFF:
            raise RunnerError("event references 2024+ control exit")
        ages = (decisions - entries).dt.total_seconds() / 3600.0
        remaining = (exits - decisions).dt.total_seconds() / 3600.0
        if bool((ages < 48.0).any()) or bool((remaining < 24.0).any()):
            raise RunnerError("event violates frozen lifecycle window")

    advancing = []
    for row in negative.to_dict(orient="records"):
        if bool(row["advances_to_action_mapping"]):
            advancing.append(
                {
                    "family_id": str(row["family_id"]),
                    "modes": str(row["advancing_modes"]).split("|"),
                }
            )

    veto_qualified = bool(veto["recovery_veto_candidate_qualified"].iloc[0])
    success = bool(advancing)
    expected_decision = SUCCESS_DECISION if success else FAILURE_DECISION
    expected_next = SUCCESS_NEXT if success else FAILURE_NEXT

    if report.get("advancing_negative_evidence") != advancing:
        raise RunnerError("advancing evidence report mismatch")
    if report.get("decision") != expected_decision:
        raise RunnerError("report decision mismatch")
    if report.get("next_stage") != expected_next:
        raise RunnerError("report next-stage mismatch")
    if freeze.get("decision") != expected_decision:
        raise RunnerError("freeze decision mismatch")
    if freeze.get("advancing_negative_evidence") != advancing:
        raise RunnerError("freeze advancing evidence mismatch")
    if bool(report.get("recovery_veto_candidate_qualified")) != veto_qualified:
        raise RunnerError("recovery veto report mismatch")

    for field in (
        "caution_threshold_relaxation_used",
        "sensitivity_merge_used_for_qualification",
        "rd39_failed_family_rescue_used",
        "calendar_year_used_as_feature_or_rule",
        "economic_execution_performed",
        "full_liquidation_performed",
        "partial_derisk_performed",
        "shadow_pnl_computed",
        "portfolio_accounting_performed",
        "capital_reuse_performed",
        "parameter_search_used",
        "threshold_optimization_used",
        "best_lane_selection_used",
        "winner_selection_used",
        "2024_accessed",
        "post_2024_accessed",
        "production_authorized",
    ):
        if report.get(field) is not False:
            raise RunnerError(f"prohibited RD40 P2 flag: {field}")

    manifest = load_json(output / "output-manifest.json")
    if manifest.get("file_count") != len(OUTPUT_NAMES):
        raise RunnerError("manifest file count drifted")
    if manifest.get("decision") != expected_decision:
        raise RunnerError("manifest decision drifted")

    negative_compact = []
    for row in negative.to_dict(orient="records"):
        negative_compact.append(
            {
                "family_id": str(row["family_id"]),
                "global_2022": int(row["global_qualified_universes_2022"]),
                "global_2023": int(row["global_qualified_universes_2023"]),
                "global_reversed_2022": int(row["global_reversed_universes_2022"]),
                "global_reversed_2023": int(row["global_reversed_universes_2023"]),
                "global_qualified": bool(row["global_qualified"]),
                "locked_2022": int(row["locked_qualified_universes_2022"]),
                "locked_2023": int(row["locked_qualified_universes_2023"]),
                "locked_negative_qualified": bool(row["locked_negative_qualified"]),
                "contrast_2022": int(row["locked_vs_open_contrast_passes_2022"]),
                "contrast_2023": int(row["locked_vs_open_contrast_passes_2023"]),
                "locked_conditioned_qualified": bool(row["locked_conditioned_qualified"]),
                "regime_direction_reversal_pattern": bool(row["regime_direction_reversal_pattern"]),
                "advancing_modes": str(row["advancing_modes"]),
            }
        )

    caution = lane_summary.loc[lane_summary["lane_id"].astype(str) == CAUTION]
    caution_compact = []
    for row in caution.to_dict(orient="records"):
        caution_compact.append(
            {
                "family_id": str(row["family_id"]),
                "period_id": str(row["period_id"]),
                "support_pass_cell_count": int(row["support_pass_cell_count"]),
                "insufficient_support_cell_count": int(row["insufficient_support_cell_count"]),
            }
        )

    return {
        "status": "PASS",
        "decision": expected_decision,
        "next_stage": expected_next,
        "control_trade_count": int(report["control_trade_count"]),
        "governor_transition_row_count": int(report["governor_transition_row_count"]),
        "event_count": int(report["event_count"]),
        "target_markout_count": int(report["target_markout_count"]),
        "advancing_negative_evidence": advancing,
        "negative_family_qualification": negative_compact,
        "recovery_veto_candidate_qualified": veto_qualified,
        "regime_direction_reversal_families": report["regime_direction_reversal_families"],
        "caution_support_diagnostic": caution_compact,
        "governor_occupancy_parity_pass": True,
        "caution_threshold_relaxation_used": False,
        "sensitivity_merge_used_for_qualification": False,
        "economic_execution_performed": False,
        "2024_accessed": False,
        "production_authorized": False,
    }


def main() -> int:
    args = parser().parse_args()
    repo = args.repo_root.resolve()
    if not (repo / ".git").exists():
        raise RunnerError(f"not a git repository: {repo}")

    if args.validate_only:
        print(
            json.dumps(
                validate_outputs(repo),
                indent=2,
                sort_keys=True,
                allow_nan=False,
            )
        )
        return 0

    if not args.execute:
        raise RunnerError("RD40 P2 requires explicit --execute")
    if not args.expected_freeze_commit:
        raise RunnerError("--expected-freeze-commit is required")

    print(
        json.dumps(
            execute(repo, args.expected_freeze_commit),
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
