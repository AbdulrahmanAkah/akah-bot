"""Run the frozen descriptive RD04-D5F membership-exit path diagnostic."""

from __future__ import annotations

import hashlib
import json
import subprocess
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pandas as pd

from spotbot.research.rd04_membership_exit_path_diagnostic import (
    HORIZON_WEEKS,
    MODE_FIXED,
    MODE_PIT,
    MODE_UNION,
    RESEARCH_STAGE,
    SCHEMA_VERSION,
    STATE_ENTRANT,
    STATE_REENTERED,
    STATE_REMOVED,
    STATE_RETAINED,
    MembershipExitPathError,
    MembershipTransition,
    active_trade_at_exit,
    build_pit_map,
    displacement_label,
    horizon_metrics,
    normalized_bars,
    post_exit_contribution,
    price_observation,
    reentry_time,
    transition_rows,
)

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "reports" / "research"

D0C_REPORT = REPORTS / "ams-rd04-d0c-adjudicated-dataset-registration-v1.json"
D2_REPORT = REPORTS / "ams-rd04-d2-universe-membership-attribution-v1.json"
D2_TRADES = REPORTS / "ams-rd04-d2-base-cost-trades-v1.csv"
D2_MEMBERSHIP = REPORTS / "ams-rd04-d2-membership-snapshots-v1.csv"
D0C_CANDIDATES = REPORTS / "ams-rd04-d0c-venue-eligible-weekly-candidates-v1.csv"
D3_REPORT = REPORTS / "ams-rd04-d3-membership-failure-diagnostics-v1.json"
D3_EXPOSURE = REPORTS / "ams-rd04-d3-membership-exposure-v1.csv"
D5C1_REPORT = REPORTS / "ams-rd04-d5c1-idiosyncratic-tail-label-join-v1.json"
D5C1_LINKS = REPORTS / "ams-rd04-d5c1-trade-event-links-v1.csv"
D4_REPORT = REPORTS / "ams-rd04-d4-hypothesis-registry-v1.json"
D5E0_REPORT = REPORTS / "ams-rd04-d5e0-midweek-pullback-diagnostic-v1.json"

REPORT_JSON = REPORTS / "ams-rd04-d5f-membership-exit-path-diagnostic-v1.json"
REPORT_MD = REPORTS / "ams-rd04-d5f-membership-exit-path-diagnostic-v1.md"
EVENTS_CSV = REPORTS / "ams-rd04-d5f-membership-exit-events-v1.csv"
HORIZONS_CSV = REPORTS / "ams-rd04-d5f-post-exit-horizon-metrics-v1.csv"
FOLDS_CSV = REPORTS / "ams-rd04-d5f-fold-metrics-v1.csv"
SYMBOLS_CSV = REPORTS / "ams-rd04-d5f-symbol-metrics-v1.csv"
REENTRY_CSV = REPORTS / "ams-rd04-d5f-membership-reentry-v1.csv"
GAP_CSV = REPORTS / "ams-rd04-d5f-fixed-pit-gap-attribution-v1.csv"
RECONCILIATION_CSV = REPORTS / "ams-rd04-d5f-reconciliation-v1.csv"
FINAL_COPY = ROOT / "RD04_D5F_RESULT_FOR_CHATGPT.md"


class MembershipExitPathRunError(RuntimeError):
    """Raised when live D5F inputs or output evidence are unsafe."""


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise MembershipExitPathRunError(f"expected JSON object: {path}")
    return cast(dict[str, Any], value)


def source_commit() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, encoding="utf-8"
    ).strip()


def utc_now() -> str:
    return datetime.now(tz=UTC).isoformat().replace("+00:00", "Z")


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8", newline="\n")
    temporary.replace(path)


def atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    atomic_text(path, json.dumps(value, indent=2, sort_keys=True, default=str) + "\n")


def write_frame(path: Path, frame: pd.DataFrame) -> None:
    output = frame.copy()
    for column in output.columns:
        if pd.api.types.is_datetime64_any_dtype(output[column].dtype):
            output[column] = pd.to_datetime(output[column], utc=True, errors="coerce").map(
                lambda value: value.isoformat() if pd.notna(value) else ""
            )
    atomic_text(path, output.to_csv(index=False, lineterminator="\n"))


def required_mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise MembershipExitPathRunError(f"missing mapping: {label}")
    return cast(Mapping[str, Any], value)


def validate_upstream() -> dict[str, Any]:
    """Verify all registered reports and bytes before any analytical read."""
    d4 = load_json(D4_REPORT)
    d5e0 = load_json(D5E0_REPORT)
    d0c = load_json(D0C_REPORT)
    d2 = load_json(D2_REPORT)
    d3 = load_json(D3_REPORT)
    d5c1 = load_json(D5C1_REPORT)
    if d4.get("status") != "COMPLETE" or d5e0.get("status") != "COMPLETE":
        raise MembershipExitPathRunError("D4 or D5E0 prerequisite is not COMPLETE")
    d5e0_decision = required_mapping(d5e0.get("decision"), "D5E0 decision")
    if d5e0_decision.get("next_stage") != RESEARCH_STAGE:
        raise MembershipExitPathRunError("D5E0 did not authorize D5F as the next stage")
    hypotheses = d4.get("hypotheses")
    if not isinstance(hypotheses, list):
        raise MembershipExitPathRunError("D4 hypotheses are missing")
    hypothesis = next(
        (
            item
            for item in hypotheses
            if isinstance(item, Mapping) and item.get("hypothesis_id") == RESEARCH_STAGE
        ),
        None,
    )
    if (
        not isinstance(hypothesis, Mapping)
        or hypothesis.get("status") != "READY_FOR_DIAGNOSTIC_ONLY"
    ):
        raise MembershipExitPathRunError("D5F is not registered for diagnostic-only research")
    frozen = required_mapping(hypothesis.get("frozen_parameters"), "D5F frozen parameters")
    if frozen.get("new_entry_outside_pit_authorized") is not False:
        raise MembershipExitPathRunError("D5F wrongly authorizes outside-PIT entries")
    if frozen.get("membership_grace_parameter_search_allowed") is not False:
        raise MembershipExitPathRunError("D5F wrongly authorizes a grace search")
    if d0c.get("status") != "PASS" or d2.get("status") != "COMPLETE":
        raise MembershipExitPathRunError("D0C or D2 prerequisite status drifted")
    if d3.get("status") != "COMPLETE" or d5c1.get("status") != "COMPLETE":
        raise MembershipExitPathRunError("D3 or D5C1 prerequisite status drifted")
    d3_inputs = required_mapping(d3.get("input_hashes"), "D3 input hashes")
    source_paths = {
        "d0c_weekly_candidates": D0C_CANDIDATES,
        "d2_base_cost_trades": D2_TRADES,
        "d2_membership_snapshots": D2_MEMBERSHIP,
        "d2_report": D2_REPORT,
    }
    for key, path in source_paths.items():
        expected = d3_inputs.get(key)
        if not isinstance(expected, str) or file_sha256(path) != expected:
            raise MembershipExitPathRunError(f"registered D3 input hash mismatch: {key}")
    datasets = required_mapping(d0c.get("datasets"), "D0C datasets")
    four_hour = required_mapping(datasets.get("four_hour"), "D0C four-hour dataset")
    relative = four_hour.get("path")
    expected_four_hour_hash = four_hour.get("file_sha256")
    if not isinstance(relative, str) or not isinstance(expected_four_hour_hash, str):
        raise MembershipExitPathRunError("D0C four-hour registration is incomplete")
    four_hour_path = ROOT / relative
    if file_sha256(four_hour_path) != expected_four_hour_hash:
        raise MembershipExitPathRunError("registered D0C four-hour hash mismatch")
    return {
        "d4_hypothesis_id": hypothesis.get("hypothesis_id"),
        "d5e0_decision": d5e0_decision.get("decision"),
        "d0c_four_hour_path": relative,
        "d0c_four_hour_sha256": expected_four_hour_hash,
        "input_hashes": {key: file_sha256(path) for key, path in source_paths.items()},
    }


def load_inputs(upstream: Mapping[str, Any]) -> tuple[pd.DataFrame, ...]:
    bars = normalized_bars(pd.read_parquet(ROOT / str(upstream["d0c_four_hour_path"])))
    candidates = pd.read_csv(D0C_CANDIDATES)
    exposure = pd.read_csv(D3_EXPOSURE)
    trades = pd.read_csv(D2_TRADES)
    links = pd.read_csv(D5C1_LINKS)
    for field in ("entry_time", "exit_time"):
        trades[field] = pd.to_datetime(trades[field], utc=True, errors="raise")
    trades["symbol"] = trades["symbol"].astype(str).str.strip().str.upper()
    trades["net_pnl"] = pd.to_numeric(trades["net_pnl"], errors="raise")
    return bars, candidates, exposure, trades, links


def fixed_symbol_set(exposure: pd.DataFrame) -> frozenset[str]:
    required = {"symbol", "fixed_survivor_member"}
    if not required.issubset(exposure.columns):
        raise MembershipExitPathRunError("D3 exposure lacks fixed membership fields")
    symbols = frozenset(
        exposure.loc[exposure["fixed_survivor_member"].astype(bool), "symbol"]
        .astype(str)
        .str.strip()
        .str.upper()
    )
    if len(symbols) != 30:
        raise MembershipExitPathRunError("D3 fixed survivor set is not 30 symbols")
    return symbols


def event_row(
    transition: MembershipTransition,
    *,
    pit_map: Mapping[pd.Timestamp, frozenset[str]],
    bars_by_symbol: Mapping[str, pd.DataFrame],
    links: pd.DataFrame,
    trades: pd.DataFrame,
) -> dict[str, Any]:
    symbol_bars = bars_by_symbol.get(transition.symbol)
    if symbol_bars is None:
        raise MembershipExitPathRunError(f"removed symbol has no D0C 4H data: {transition.symbol}")
    row = price_observation(transition, bars=symbol_bars, links=links)
    next_reentry = reentry_time(pit_map, symbol=transition.symbol, after=transition.decision_time)
    end = next_reentry if next_reentry is not None else pd.Timestamp("2025-01-01T00:00:00Z")
    fixed_active = active_trade_at_exit(
        trades,
        symbol=transition.symbol,
        decision_time=transition.decision_time,
        modes=frozenset({MODE_FIXED, MODE_UNION}),
    )
    pit_active = active_trade_at_exit(
        trades,
        symbol=transition.symbol,
        decision_time=transition.decision_time,
        modes=frozenset({MODE_PIT}),
    )
    fixed_count, fixed_pnl = post_exit_contribution(
        trades,
        symbol=transition.symbol,
        start=transition.decision_time,
        end=end,
        mode=MODE_FIXED,
    )
    union_count, union_pnl = post_exit_contribution(
        trades,
        symbol=transition.symbol,
        start=transition.decision_time,
        end=end,
        mode=MODE_UNION,
    )
    row.update(
        {
            "reentered_pit_later": next_reentry is not None,
            "reentry_time": next_reentry,
            "fixed_or_union_position_active_at_exit": not fixed_active.empty,
            "pit_position_active_at_exit": not pit_active.empty,
            "strategy_exit_time_if_any": (
                pit_active.iloc[0]["exit_time"] if not pit_active.empty else pd.NaT
            ),
            "strategy_exit_reason": (
                str(pit_active.iloc[0]["exit_reason"]) if not pit_active.empty else ""
            ),
            "fixed_post_exit_trade_count": fixed_count,
            "fixed_post_exit_net_pnl": fixed_pnl,
            "union_post_exit_trade_count": union_count,
            "union_post_exit_net_pnl": union_pnl,
        }
    )
    return row


def comparator_rows(
    transitions: Sequence[MembershipTransition],
    *,
    bars_by_symbol: Mapping[str, pd.DataFrame],
    links: pd.DataFrame,
) -> list[dict[str, Any]]:
    """Build retained and entrant descriptive observations without trading treatment."""
    rows: list[dict[str, Any]] = []
    for transition in transitions:
        if transition.state not in {STATE_RETAINED, STATE_ENTRANT}:
            continue
        symbol_bars = bars_by_symbol.get(transition.symbol)
        if symbol_bars is None:
            continue
        row = price_observation(transition, bars=symbol_bars, links=links)
        row["population"] = (
            "PIT_RETAINED_MEMBERS" if transition.state == STATE_RETAINED else "PIT_ENTRANTS"
        )
        rows.append(row)
    return rows


def frame_from_rows(rows: Sequence[Mapping[str, Any]]) -> pd.DataFrame:
    return pd.DataFrame([dict(row) for row in rows])


def markdown_report(report: Mapping[str, Any]) -> str:
    summary = required_mapping(report["summary"], "summary")
    decision = required_mapping(report["decision"], "decision")
    return "\n".join(
        [
            "# RD04-D5F Membership Exit Path Diagnostic",
            "",
            "## Descriptive result",
            "",
            f"- Status: `{report['status']}`",
            f"- Decision: `{decision['decision']}`",
            f"- Removed-from-PIT events: `{summary['membership_exit_event_count']}`",
            f"- Unique removed symbols: `{summary['unique_removed_symbol_count']}`",
            f"- Fixed post-exit contribution: `{summary['fixed_post_exit_net_pnl']}`",
            f"- Union post-exit contribution: `{summary['union_post_exit_net_pnl']}`",
            f"- Fixed-vs-PIT diagnostic gap share: `{summary['fixed_pit_gap_share_attributed']}`",
            f"- Later PIT re-entry share: `{summary['later_pit_reentry_share']}`",
            "",
            "## Frozen boundary",
            "",
            "- Observational post-removal horizons are fixed at 1, 2, 4, and 8 weeks.",
            "- No counterfactual portfolio, holding rule, cost treatment, or position sizing ran.",
            "- No entry, exit, ranking, universe, or production change is authorized.",
            "- `test_2025_accessed=false`; `holdout_2026_accessed=false`.",
            "",
        ]
    )


def run() -> dict[str, Any]:
    upstream = validate_upstream()
    bars, candidates, exposure, trades, links = load_inputs(upstream)
    pit_map = build_pit_map(candidates)
    fixed = fixed_symbol_set(exposure)
    transitions = transition_rows(pit_map, fixed_symbols=fixed)
    bars_by_symbol = {
        str(symbol): group.reset_index(drop=True)
        for symbol, group in bars.groupby("symbol", sort=False)
    }
    removed = [transition for transition in transitions if transition.state == STATE_REMOVED]
    events = [
        event_row(
            transition,
            pit_map=pit_map,
            bars_by_symbol=bars_by_symbol,
            links=links,
            trades=trades,
        )
        for transition in removed
    ]
    event_frame = frame_from_rows(events)
    if event_frame.empty:
        raise MembershipExitPathRunError("D5F found no causal membership exits")
    event_frame["population"] = event_frame["fixed_survivor"].map(
        {True: "REMOVED_SURVIVORS", False: "REMOVED_PIT_ENTRANTS"}
    )
    comparators = comparator_rows(transitions, bars_by_symbol=bars_by_symbol, links=links)
    all_observations = pd.concat([event_frame, frame_from_rows(comparators)], ignore_index=True)
    horizon_frame = horizon_metrics(all_observations)
    removed_horizons = horizon_frame.loc[horizon_frame["population"] == "REMOVED_SURVIVORS"]
    four_week = removed_horizons.loc[
        (removed_horizons["fold_id"] == "ALL") & (removed_horizons["horizon_weeks"] == 4)
    ]
    positive_share_4w = (
        float(four_week.iloc[0]["positive_return_share"]) if not four_week.empty else None
    )
    fixed_post_exit_pnl = float(event_frame["fixed_post_exit_net_pnl"].sum())
    union_post_exit_pnl = float(event_frame["union_post_exit_net_pnl"].sum())
    fixed_total = float(trades.loc[trades["universe_mode"].eq(MODE_FIXED), "net_pnl"].sum())
    pit_total = float(trades.loc[trades["universe_mode"].eq(MODE_PIT), "net_pnl"].sum())
    fixed_pit_gap = fixed_total - pit_total
    gap_share = fixed_post_exit_pnl / fixed_pit_gap if fixed_pit_gap > 0.0 else None
    classification = displacement_label(
        fixed_post_exit_pnl=fixed_post_exit_pnl,
        gap_share=gap_share or 0.0,
        positive_share_4w=positive_share_4w,
    )
    fold_frame = (
        event_frame.groupby("fold_id", sort=True)
        .agg(
            membership_exit_event_count=("symbol", "size"),
            unique_removed_symbol_count=("symbol", "nunique"),
            fixed_post_exit_net_pnl=("fixed_post_exit_net_pnl", "sum"),
            union_post_exit_net_pnl=("union_post_exit_net_pnl", "sum"),
            later_pit_reentry_count=("reentered_pit_later", "sum"),
            terminal_event_count=(
                "event_label",
                lambda value: int((value == "TERMINAL_IMPAIRMENT").sum()),
            ),
            missing_data_count=(
                "measurement_status",
                lambda value: int((value == "MISSING_DATA_OR_RECONCILIATION_FAILURE").sum()),
            ),
        )
        .reset_index()
    )
    symbol_frame = (
        event_frame.groupby(["symbol", "population"], sort=True)
        .agg(
            membership_exit_event_count=("fold_id", "size"),
            fixed_post_exit_net_pnl=("fixed_post_exit_net_pnl", "sum"),
            union_post_exit_net_pnl=("union_post_exit_net_pnl", "sum"),
            mean_return_4w=("return_4w", "mean"),
            mean_mfe_8w=("mfe_8w", "mean"),
            mean_mae_8w=("mae_8w", "mean"),
            reentered_pit_later=("reentered_pit_later", "max"),
        )
        .reset_index()
    )
    reentry_rows: list[dict[str, Any]] = []
    reentry_records = event_frame.loc[event_frame["reentered_pit_later"]].to_dict("records")
    for row in reentry_records:
        time = pd.Timestamp(str(row["reentry_time"]))
        symbol = str(row["symbol"])
        symbol_bars = bars_by_symbol[symbol]
        reentry_observation = price_observation(
            MembershipTransition(
                STATE_REENTERED,
                symbol,
                time,
                time,
                0,
                bool(row["fixed_survivor"]),
            ),
            bars=symbol_bars,
            links=links,
        )
        reentry_open = reentry_observation["price_at_membership_exit"]
        before = float(reentry_open) / float(row["price_at_membership_exit"]) - 1.0
        reentry_rows.append(
            {
                "fold_id": row["fold_id"],
                "symbol": symbol,
                "membership_exit_decision_time": row["membership_exit_decision_time"],
                "reentry_time": time,
                "return_before_reentry": before,
                "return_4w_after_reentry": reentry_observation["return_4w"],
                "event_label": row["event_label"],
            }
        )
    reentry_frame = frame_from_rows(reentry_rows)
    gap_frame = pd.DataFrame(
        [
            {
                "fixed_total_net_pnl": fixed_total,
                "pit_total_net_pnl": pit_total,
                "fixed_minus_pit_net_pnl": fixed_pit_gap,
                "removed_survivor_fixed_post_exit_net_pnl": fixed_post_exit_pnl,
                "removed_survivor_union_post_exit_net_pnl": union_post_exit_pnl,
                "fixed_pit_gap_share_attributed": gap_share,
                "attribution_is_diagnostic_not_counterfactual": True,
            }
        ]
    )
    reconciliation = pd.DataFrame(
        [
            {
                "check": "d5f_transition_events_unique",
                "passed": not event_frame.duplicated(
                    ["symbol", "membership_exit_decision_time"]
                ).any(),
            },
            {
                "check": "d5f_removed_events_are_causal",
                "passed": bool((event_frame["observation_state"] == STATE_REMOVED).all()),
            },
            {
                "check": "d5f_four_hour_before_2025",
                "passed": bool(
                    (bars["bar_open_time"] < pd.Timestamp("2025-01-01T00:00:00Z")).all()
                ),
            },
            {
                "check": "d5f_no_post_lock_close",
                "passed": bool(
                    (bars["bar_close_time"] <= pd.Timestamp("2025-01-01T00:00:00Z")).all()
                ),
            },
            {"check": "d5f_fixed_set_count", "passed": len(fixed) == 30},
            {"check": "d5f_event_count_positive", "passed": len(event_frame) > 0},
        ]
    )
    if not bool(reconciliation["passed"].all()):
        raise MembershipExitPathRunError("D5F reconciliation failed")
    summary = {
        "membership_exit_event_count": len(event_frame),
        "unique_removed_symbol_count": int(event_frame["symbol"].nunique()),
        "counts_by_fold": {
            str(row["fold_id"]): int(row["membership_exit_event_count"])
            for row in fold_frame.to_dict("records")
        },
        "fixed_post_exit_net_pnl": fixed_post_exit_pnl,
        "union_post_exit_net_pnl": union_post_exit_pnl,
        "fixed_pit_gap_share_attributed": gap_share,
        "later_pit_reentry_count": int(event_frame["reentered_pit_later"].sum()),
        "later_pit_reentry_share": float(event_frame["reentered_pit_later"].mean()),
        "terminal_event_count": int((event_frame["event_label"] == "TERMINAL_IMPAIRMENT").sum()),
        "missing_data_count": int(
            (event_frame["measurement_status"] == "MISSING_DATA_OR_RECONCILIATION_FAILURE").sum()
        ),
        "terminal_data_end_count": int(
            (event_frame["measurement_status"] == "TERMINAL_DATA_END").sum()
        ),
        "mean_mfe_8w": float(event_frame["mfe_8w"].mean()),
        "mean_mae_8w": float(event_frame["mae_8w"].mean()),
    }
    decision = {
        "decision": "MEMBERSHIP_EXIT_PATH_DIAGNOSTIC_COMPLETE",
        "descriptive_classification": classification,
        "next_research_stage": "NO_D5F_TREATMENT_AUTHORIZED",
        "counterfactual_portfolio_simulation_executed": False,
        "point_in_time_universe_research_baseline_authorized": False,
        "production_change_authorized": False,
        "universe_change_authorized": False,
        "ranking_change_authorized": False,
        "entry_change_authorized": False,
        "exit_change_authorized": False,
        "weight_change_authorized": False,
        "trade_logic_changed": False,
        "ati_v1_authorized": False,
    }
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "research_stage": RESEARCH_STAGE,
        "status": "COMPLETE",
        "generated_at_utc": utc_now(),
        "source_commit": source_commit(),
        "upstream": upstream,
        "contract": {
            "diagnostic_only": True,
            "post_exit_horizons_weeks": list(HORIZON_WEEKS),
            "membership_event_definition": "PREVIOUS_PIT_MEMBER_AND_CURRENT_WEEK_NOT_MEMBER",
            "price_measurement": "DECISION_OPEN_TO_HORIZON_FINAL_4H_CLOSE",
            "mfe_mae_window": "FIRST_EIGHT_WEEKS_AFTER_DECISION",
            "classification_definition": "PREDECLARED_DESCRIPTIVE_ONLY",
        },
        "summary": summary,
        "decision": decision,
        "safety": {
            "spot_only": True,
            "long_only": True,
            "no_leverage": True,
            "no_margin": True,
            "no_futures": True,
            "no_shorts": True,
            "no_borrowing": True,
            "no_interest": True,
            "no_dca": True,
            "no_kelly": True,
            "no_averaging_down": True,
            "no_pyramiding": True,
            "test_2025_accessed": False,
            "holdout_2026_accessed": False,
        },
        "output_hashes": {},
    }
    write_frame(EVENTS_CSV, event_frame)
    write_frame(HORIZONS_CSV, horizon_frame)
    write_frame(FOLDS_CSV, fold_frame)
    write_frame(SYMBOLS_CSV, symbol_frame)
    write_frame(REENTRY_CSV, reentry_frame)
    write_frame(GAP_CSV, gap_frame)
    write_frame(RECONCILIATION_CSV, reconciliation)
    outputs = (
        EVENTS_CSV,
        HORIZONS_CSV,
        FOLDS_CSV,
        SYMBOLS_CSV,
        REENTRY_CSV,
        GAP_CSV,
        RECONCILIATION_CSV,
    )
    report["output_hashes"] = {
        path.relative_to(ROOT).as_posix(): file_sha256(path) for path in outputs
    }
    atomic_json(REPORT_JSON, report)
    rendered = markdown_report(report)
    atomic_text(REPORT_MD, rendered)
    atomic_text(FINAL_COPY, rendered)
    return report


def main() -> None:
    try:
        report = run()
    except (MembershipExitPathError, MembershipExitPathRunError) as error:
        raise SystemExit(f"RD04-D5F FAILED: {error}") from error
    summary = required_mapping(report["summary"], "summary")
    decision = required_mapping(report["decision"], "decision")
    print("RD04_D5F_STATUS=COMPLETE")
    print(f"DECISION={decision['decision']}")
    print(f"MEMBERSHIP_EXIT_EVENT_COUNT={summary['membership_exit_event_count']}")
    print(f"DESCRIPTIVE_CLASSIFICATION={decision['descriptive_classification']}")
    print("TEST_2025_ACCESSED=false")
    print("HOLDOUT_2026_ACCESSED=false")


if __name__ == "__main__":
    main()
