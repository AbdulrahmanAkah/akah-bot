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

from spotbot.research.rd39_trade_conditioned_lifecycle_path import (  # noqa: E402
    CONTROL_POLICY,
    CONTROL_PORTFOLIO,
    DATA_CUTOFF,
    DATA_START,
    DIAGNOSTIC_COST_MULTIPLIER,
    FAILURE_DECISION,
    FAILURE_NEXT,
    FAMILY_ORDER,
    PRIMARY_FAMILIES,
    RECLAIM_CONTROL,
    SUCCESS_DECISION,
    SUCCESS_NEXT,
    UNIVERSES,
    build_markout_ledger,
    events_from_trade_states,
    lifecycle_snapshot,
    normalize_price_frame,
    period_for,
    price_lookup,
    qualification_tables,
    summarize_markouts,
    utc,
    validate_constants,
)

P1_FREEZE = "f615173874ddfaadc92692e66ddbc7d428f9bd08"

P1_PROTOCOL = Path(
    "data/research/rd39_p1/"
    "rd39-p1-kucoin-native-trade-conditioned-lifecycle-path-"
    "information-source-preregistration-v1.json"
)
P1_PROTOCOL_BLOB = "9096ba6bd16824b37e6b9ecf6408b5108cc0a02f"
P1_PROTOCOL_SHA256 = "847e14e778428361a806b63c5ed2dd787119fa9c325f8261b3f59b7ff7c48801"

P1_AUDIT = Path("data/research/rd39_p1/rd39-p1-preregistration-audit-v1.json")
P1_AUDIT_BLOB = "5d309e403c8d3d0f68c4da4852c615b91fa5e4c0"

RD32_TRADES = Path("data/research/rd32_p3_runtime/trade-ledger.csv")
RD32_TRADES_BLOB = "6749de85cb14733388e0f76a6557124d3212398b"
RD32_TRADES_SHA256 = "07f49e0e9235f736f54ee9dd59142c16fc4e7b99e83781b1ee26b9338def117e"

KUCOIN_ROOT = Path("data/raw/rd16b/kucoin")
OUTPUT = Path("data/research/rd39_p2_runtime")

OUTPUT_NAMES = (
    "input-and-conformance-audit.json",
    "lifecycle-hour-summary.csv",
    "event-ledger.csv",
    "event-summary.csv",
    "target-markout-ledger.csv",
    "target-markout-summary.csv",
    "qualification-evaluation.csv",
    "family-qualification.csv",
    "positive-control-evaluation.csv",
    "qualified-lifecycle-states-freeze.json",
    "rd39-p2-trade-conditioned-lifecycle-path-diagnostic-report-v1.json",
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
        raise RunnerError("staged tracked changes before P2")
    if git(repo, "diff", "--name-only", "--"):
        raise RunnerError("unstaged tracked changes before P2")

    head = git(repo, "rev-parse", "HEAD")
    if head != expected_freeze_commit:
        raise RunnerError(f"P2 HEAD {head} != engine freeze {expected_freeze_commit}")
    if git(repo, "rev-parse", "HEAD^") != P1_FREEZE:
        raise RunnerError("P2 engine-freeze parent is not P1")

    for path, blob, label in (
        (P1_PROTOCOL, P1_PROTOCOL_BLOB, "P1 protocol"),
        (P1_AUDIT, P1_AUDIT_BLOB, "P1 audit"),
        (RD32_TRADES, RD32_TRADES_BLOB, "RD32 trade ledger"),
    ):
        verify_blob(repo, path, blob, label)

    if sha256(repo / P1_PROTOCOL) != P1_PROTOCOL_SHA256:
        raise RunnerError("P1 protocol SHA drifted")
    if sha256(repo / RD32_TRADES) != RD32_TRADES_SHA256:
        raise RunnerError("RD32 trade-ledger frozen SHA drifted")

    protocol = load_json(repo / P1_PROTOCOL)
    audit = load_json(repo / P1_AUDIT)
    if protocol.get("status") != "FROZEN_PRE_DATA_DIAGNOSTIC":
        raise RunnerError("P1 protocol not frozen")
    if protocol.get("next_stage") != (
        "RD39_P2_FREEZE_AND_RUN_TRADE_CONDITIONED_LIFECYCLE_PATH_DIAGNOSTIC_2022_2023_ONCE"
    ):
        raise RunnerError("P1 next-stage drifted")
    if audit.get("protocol_sha256") != P1_PROTOCOL_SHA256:
        raise RunnerError("P1 audit protocol SHA drifted")
    if audit.get("control_trade_rows_loaded") is not False:
        raise RunnerError("P1 trade-row seal drifted")
    if audit.get("raw_market_data_loaded") is not False:
        raise RunnerError("P1 market-data seal drifted")

    validate_constants()
    return {
        "runner_freeze_commit": expected_freeze_commit,
        "p1_freeze_commit": P1_FREEZE,
        "p1_protocol_git_blob": P1_PROTOCOL_BLOB,
        "p1_protocol_sha256": P1_PROTOCOL_SHA256,
        "p1_audit_git_blob": P1_AUDIT_BLOB,
        "rd32_trade_ledger_git_blob": RD32_TRADES_BLOB,
        "rd32_trade_ledger_sha256": RD32_TRADES_SHA256,
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
        "support_families",
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
        raise RunnerError("RD39 frozen 1x control trade set is empty")

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
        raise RunnerError("pre-2022 control trade entered RD39")
    if frame["exit_time"].max() >= DATA_CUTOFF:
        raise RunnerError("2024+ control trade entered RD39")
    if not bool((frame["entry_time"] < frame["exit_time"]).all()):
        raise RunnerError("invalid control trade interval")
    if bool((frame["entry_price"] <= 0.0).any()):
        raise RunnerError("non-positive frozen entry price")
    if not bool((frame["entry_time"] == frame["entry_time"].dt.floor("h")).all()):
        raise RunnerError("non-hourly frozen entry time")
    if not bool((frame["exit_time"] == frame["exit_time"].dt.floor("h")).all()):
        raise RunnerError("non-hourly frozen exit time")

    frame = frame.sort_values(
        [
            "universe_id",
            "entry_time",
            "pair",
            "exit_time",
        ],
        kind="stable",
    ).reset_index(drop=True)
    frame["control_trade_id"] = np.arange(len(frame), dtype=np.int64)
    return frame


def required_pairs(control: pd.DataFrame) -> list[str]:
    pairs = sorted(control["pair"].astype(str).unique())
    if not pairs:
        raise RunnerError("no required KuCoin pairs")
    return pairs


def load_prices(
    repo: Path,
    pairs: list[str],
) -> dict[str, dict[int, tuple[float, float, float, float]]]:
    lookups: dict[str, dict[int, tuple[float, float, float, float]]] = {}
    start = DATA_START.to_pydatetime()
    cutoff = DATA_CUTOFF.to_pydatetime()

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
        lookups[pair] = price_lookup(frame)
        print(
            f"RD39_P2_SOURCE={index}/{len(pairs)}:{pair}:rows={len(frame)}",
            flush=True,
        )
    return lookups


def build_states(
    control: pd.DataFrame,
    lookups: dict[str, dict[int, tuple[float, float, float, float]]],
) -> tuple[list[dict[str, Any]], pd.DataFrame]:
    state_rows: list[dict[str, Any]] = []
    counts: dict[tuple[str, str], dict[str, int]] = {
        (universe, period): {
            "eligible_decision_hour_count": 0,
            "evaluable_decision_hour_count": 0,
            "unevaluable_decision_hour_count": 0,
        }
        for universe in UNIVERSES
        for period in ("ROBUSTNESS_2022", "ROBUSTNESS_2023")
    }

    trades = control.to_dict(orient="records")
    for index, trade in enumerate(trades, start=1):
        trade_id = int(trade["control_trade_id"])
        universe = str(trade["universe_id"])
        pair = str(trade["pair"])
        entry = utc(trade["entry_time"])
        control_exit = utc(trade["exit_time"])
        first = entry + pd.Timedelta(hours=24)
        last = control_exit - pd.Timedelta(hours=24)

        decisions = (
            list(
                pd.date_range(
                    first,
                    last,
                    freq="h",
                    tz="UTC",
                )
            )
            if first <= last
            else []
        )

        lookup = lookups[pair]
        previous_decision: pd.Timestamp | None = None

        for decision in decisions:
            period = period_for(decision)
            cell = counts[(universe, period)]
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
                previous_decision = None
                continue

            # Any unobserved/ineligible gap resets state to unknown.
            if previous_decision is not None and decision != previous_decision + pd.Timedelta(
                hours=1
            ):
                previous_decision = None

            cell["evaluable_decision_hour_count"] += 1
            state_rows.append(
                {
                    "control_trade_id": trade_id,
                    "universe_id": universe,
                    "period_id": period,
                    "pair": pair,
                    "entry_time": entry,
                    "control_exit_time": control_exit,
                    "entry_price": float(trade["entry_price"]),
                    **snapshot,
                }
            )
            previous_decision = decision

        print(
            f"RD39_P2_TRADE={index}/{len(trades)}:"
            f"{universe}:{pair}:eligible_hours={len(decisions)}",
            flush=True,
        )

    summary_rows: list[dict[str, Any]] = []
    for universe in UNIVERSES:
        for period in ("ROBUSTNESS_2022", "ROBUSTNESS_2023"):
            cell = counts[(universe, period)]
            eligible = cell["eligible_decision_hour_count"]
            evaluable = cell["evaluable_decision_hour_count"]
            summary_rows.append(
                {
                    "universe_id": universe,
                    "period_id": period,
                    **cell,
                    "evaluable_share": (evaluable / eligible if eligible else np.nan),
                    "missing_path_imputation_used": False,
                    "gap_preserves_event_state": False,
                }
            )
    return state_rows, pd.DataFrame.from_records(summary_rows)


def event_summary(events: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for family in FAMILY_ORDER:
        for universe in UNIVERSES:
            for period in ("ROBUSTNESS_2022", "ROBUSTNESS_2023"):
                cell = events.loc[
                    (events["family_id"] == family)
                    & (events["universe_id"] == universe)
                    & (events["period_id"] == period)
                ]
                rows.append(
                    {
                        "family_id": family,
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
        raise RunnerError("RD39 P2 runtime already exists; preserve and recover/validate")

    control = load_control_trades(repo)
    pairs = required_pairs(control)
    lookups = load_prices(repo, pairs)
    state_rows, hour_summary = build_states(control, lookups)
    events = events_from_trade_states(state_rows)
    del state_rows

    markouts = build_markout_ledger(events, lookups)
    summary = summarize_markouts(markouts)
    qualification, families, positive_control = qualification_tables(summary)

    qualified = list(
        families.loc[
            families["advances_to_mapping_freeze"].astype(bool),
            "family_id",
        ].astype(str)
    )
    success = bool(qualified)
    decision = SUCCESS_DECISION if success else FAILURE_DECISION
    next_stage = SUCCESS_NEXT if success else FAILURE_NEXT

    output = repo / OUTPUT
    output.mkdir(parents=True, exist_ok=False)

    audit = {
        "schema_version": "rd39-p2-input-and-conformance-audit-v1",
        "stage": ("RD39_P2_TRADE_CONDITIONED_LIFECYCLE_PATH_DIAGNOSTIC_2022_2023"),
        "status": "PASS",
        "lineage": lineage,
        "control_policy": CONTROL_POLICY,
        "control_portfolio": CONTROL_PORTFOLIO,
        "diagnostic_cost_multiplier": DIAGNOSTIC_COST_MULTIPLIER,
        "control_trade_count": len(control),
        "required_pair_count": len(pairs),
        "required_pairs": pairs,
        "feature_clock": "COMPLETED_BAR_t_minus_1",
        "target_clock": "KUCOIN_SPOT_1H_OPEN_t",
        "minimum_holding_age_hours": 24,
        "primary_event_remaining_hours": 24,
        "missing_path_imputation_used": False,
        "forward_fill_used": False,
        "backfill_used": False,
        "unobserved_gap_preserves_event_state": False,
        "control_exit_reason_used_in_feature_logic": False,
        "control_exit_time_used_only_as_eligibility_boundary": True,
        "control_trade_rows_loaded": True,
        "raw_market_data_loaded": True,
        "path_features_computed": True,
        "events_observed": True,
        "forward_returns_computed": True,
        "economic_execution_performed": False,
        "shadow_exit_execution_performed": False,
        "portfolio_accounting_performed": False,
        "capital_reuse_performed": False,
        "rd37_or_rd38_family_rescue_used": False,
        "parameter_search_used": False,
        "threshold_optimization_used": False,
        "return_ranking_used_for_selection": False,
        "winner_selection_used": False,
        "2024_accessed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
    }
    write_json(output / "input-and-conformance-audit.json", audit)

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
    summary.to_csv(
        output / "target-markout-summary.csv",
        index=False,
        lineterminator="\n",
    )
    qualification.to_csv(
        output / "qualification-evaluation.csv",
        index=False,
        lineterminator="\n",
    )
    families.to_csv(
        output / "family-qualification.csv",
        index=False,
        lineterminator="\n",
    )
    positive_control.to_csv(
        output / "positive-control-evaluation.csv",
        index=False,
        lineterminator="\n",
    )

    family_freeze = {
        "schema_version": "rd39-p2-qualified-lifecycle-states-freeze-v1",
        "status": "PASS",
        "qualified_primary_families": qualified,
        "qualified_primary_count": len(qualified),
        "positive_control_family": RECLAIM_CONTROL,
        "positive_control_selection_eligible": False,
        "decision": decision,
        "next_stage": next_stage,
        "failed_family_rescue_used": False,
        "return_ranking_used_for_selection": False,
        "winner_selection_used": False,
        "parameter_search_used": False,
        "threshold_optimization_used": False,
        "economic_execution_performed": False,
        "production_authorized": False,
    }
    write_json(
        output / "qualified-lifecycle-states-freeze.json",
        family_freeze,
    )

    report = {
        "schema_version": ("rd39-p2-trade-conditioned-lifecycle-path-diagnostic-report-v1"),
        "stage": ("RD39_P2_TRADE_CONDITIONED_LIFECYCLE_PATH_DIAGNOSTIC_2022_2023"),
        "status": "PASS",
        "runner_freeze_commit": expected_freeze_commit,
        "source_p1_freeze_commit": P1_FREEZE,
        "control_trade_count": len(control),
        "event_count": int(len(events)),
        "target_markout_count": int(len(markouts)),
        "primary_families": list(PRIMARY_FAMILIES),
        "positive_control_family": RECLAIM_CONTROL,
        "qualified_primary_families": qualified,
        "decision": decision,
        "next_stage": next_stage,
        "missing_path_imputation_used": False,
        "unobserved_gap_preserves_event_state": False,
        "control_exit_reason_used_in_feature_logic": False,
        "economic_execution_performed": False,
        "shadow_exit_execution_performed": False,
        "portfolio_accounting_performed": False,
        "capital_reuse_performed": False,
        "parameter_search_used": False,
        "threshold_optimization_used": False,
        "return_ranking_used_for_selection": False,
        "winner_selection_used": False,
        "2024_accessed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
    }
    write_json(
        output / "rd39-p2-trade-conditioned-lifecycle-path-diagnostic-report-v1.json",
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
            "schema_version": "rd39-p2-output-manifest-v1",
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
        raise RunnerError("RD39 P2 runtime missing")

    expected = sorted((*OUTPUT_NAMES, "output-manifest.json"))
    observed = sorted(path.name for path in output.iterdir() if path.is_file())
    if observed != expected:
        raise RunnerError(f"RD39 P2 output registry drift: {observed} != {expected}")

    report = load_json(
        output / "rd39-p2-trade-conditioned-lifecycle-path-diagnostic-report-v1.json"
    )
    family_freeze = load_json(output / "qualified-lifecycle-states-freeze.json")
    hours = pd.read_csv(
        output / "lifecycle-hour-summary.csv",
        low_memory=False,
    )
    events = pd.read_csv(
        output / "event-ledger.csv",
        low_memory=False,
    )
    summary = pd.read_csv(
        output / "target-markout-summary.csv",
        low_memory=False,
    )
    qualification = pd.read_csv(
        output / "qualification-evaluation.csv",
        low_memory=False,
    )
    families = pd.read_csv(
        output / "family-qualification.csv",
        low_memory=False,
    )
    control = pd.read_csv(
        output / "positive-control-evaluation.csv",
        low_memory=False,
    )

    if len(hours) != 6:
        raise RunnerError("lifecycle-hour summary must have six cells")
    if len(summary) != 72:
        raise RunnerError("target summary must have 72 cells")
    if len(qualification) != 18:
        raise RunnerError("negative qualification must have 18 cells")
    if len(families) != 3:
        raise RunnerError("family qualification must have 3 rows")
    if len(control) != 6:
        raise RunnerError("positive-control evaluation must have 6 rows")

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
            raise RunnerError("event outside 2022-2023")
        if exits.max() >= DATA_CUTOFF:
            raise RunnerError("event references 2024+ control exit")
        ages = (decisions - entries).dt.total_seconds() / 3600.0
        remaining = (exits - decisions).dt.total_seconds() / 3600.0
        if bool((ages < 24.0).any()) or bool((remaining < 24.0).any()):
            raise RunnerError("event violates frozen lifecycle window")

    qualified = list(
        families.loc[
            families["advances_to_mapping_freeze"].astype(bool),
            "family_id",
        ].astype(str)
    )
    success = bool(qualified)
    expected_decision = SUCCESS_DECISION if success else FAILURE_DECISION
    expected_next = SUCCESS_NEXT if success else FAILURE_NEXT

    if report.get("qualified_primary_families") != qualified:
        raise RunnerError("qualified-family report mismatch")
    if report.get("decision") != expected_decision:
        raise RunnerError("report decision mismatch")
    if report.get("next_stage") != expected_next:
        raise RunnerError("report next-stage mismatch")
    if family_freeze.get("decision") != expected_decision:
        raise RunnerError("family freeze decision mismatch")

    for field in (
        "missing_path_imputation_used",
        "unobserved_gap_preserves_event_state",
        "control_exit_reason_used_in_feature_logic",
        "economic_execution_performed",
        "shadow_exit_execution_performed",
        "portfolio_accounting_performed",
        "capital_reuse_performed",
        "parameter_search_used",
        "threshold_optimization_used",
        "return_ranking_used_for_selection",
        "winner_selection_used",
        "2024_accessed",
        "post_2024_accessed",
        "production_authorized",
    ):
        if report.get(field) is not False:
            raise RunnerError(f"prohibited RD39 P2 flag: {field}")

    manifest = load_json(output / "output-manifest.json")
    if manifest.get("file_count") != len(OUTPUT_NAMES):
        raise RunnerError("manifest file count drifted")
    if manifest.get("decision") != expected_decision:
        raise RunnerError("manifest decision drifted")

    family_compact = []
    for row in families.to_dict(orient="records"):
        family_compact.append(
            {
                "family_id": row["family_id"],
                "qualified_universes_2022": int(row["qualified_universes_2022"]),
                "qualified_universes_2023": int(row["qualified_universes_2023"]),
                "qualified": bool(row["qualified"]),
            }
        )

    control_compact = []
    for row in control.to_dict(orient="records"):
        control_compact.append(
            {
                "universe_id": row["universe_id"],
                "period_id": row["period_id"],
                "event_count_24h": int(row["event_count_24h"]),
                "trade_count_24h": int(row["trade_count_24h"]),
                "mean_24h": float(row["mean_24h"]),
                "median_24h": float(row["median_24h"]),
                "control_cell_pass": bool(row["control_cell_pass"]),
            }
        )

    return {
        "status": "PASS",
        "decision": expected_decision,
        "next_stage": expected_next,
        "control_trade_count": int(report["control_trade_count"]),
        "event_count": int(report["event_count"]),
        "target_markout_count": int(report["target_markout_count"]),
        "qualified_primary_families": qualified,
        "family_qualification": family_compact,
        "positive_control_24h": control_compact,
        "missing_path_imputation_used": False,
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
        raise RunnerError("P2 requires explicit --execute")
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
