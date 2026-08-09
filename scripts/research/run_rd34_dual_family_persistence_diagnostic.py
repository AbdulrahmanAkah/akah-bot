from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from spotbot.research.rd26_exit_architecture import (  # noqa: E402
    DATA_CUTOFF,
    FAMILY_MOMENTUM_BREAKOUT,
    FAMILY_RELATIVE_STRENGTH_ROTATION,
)
from spotbot.research.rd31_regime_admission_governor import (  # noqa: E402
    REGIME_HYSTERESIS_ADMISSION_GOVERNOR,
)
from spotbot.research.rd34_dual_family_persistence import (  # noqa: E402
    HORIZONS,
    MB_RULE_ORDER,
    PERIODS,
    QUALIFICATION_GATES,
    RS_RULE_ORDER,
    UNIVERSES,
    build_lookups,
    diagnostic_decision,
    full_markouts,
    origin_from_event,
    outcomes_for_origin,
    qualification,
    summarize_markouts,
)

SCHEMA_VERSION = "rd34-dual-family-persistence-diagnostic-runner-v1"

P1_FREEZE_COMMIT = "9b1db409e10aa505c4402485d01d008a1553d62a"
P0_FREEZE_COMMIT = "378464f9ebadd7979b3a94dae252222e8f3a8cca"
RD33_RESULTS_COMMIT = "766eea6a25a2f773c20cf48447f6ef3e7f94f376"

P0_PROTOCOL = Path(
    "data/research/rd34_p0/rd34-p0-dual-family-persistence-diagnostic-protocol-v1.json"
)
P0_PROTOCOL_SHA256 = "3a212bb0b1b65731e8f86f51d001beb4a56a628bfab7dbec607643c375c033f3"
P0_PROTOCOL_BLOB = "9c788d5345bf907b6db7dd128b7db85131a6f5d3"

P0_AUDIT = Path("data/research/rd34_p0/rd34-p0-preregistration-audit-v1.json")
P0_AUDIT_SHA256 = "ddb584f04026543606bce64954a075c6a2cda8fbdb96ac533d188eef23e7fdf3"
P0_AUDIT_BLOB = "949d18dbd9298ea057eb5b617e1d3b2c4ff6c99c"

P1_ENGINE = Path("src/spotbot/research/rd34_dual_family_persistence.py")
P1_ENGINE_SHA256 = "dd6fb3d0b452b9afd0cf3a80b887141e2563c356398828049bd241faace783ce"
P1_ENGINE_BLOB = "9f96404e737a5a106744032c248faef9f00e55c9"

P1_TEST = Path("tests/research/test_rd34_dual_family_persistence.py")
P1_TEST_SHA256 = "c6f540f8bc357e2e0d874b8c99a8bd9766f1565d161b79410cfe5eec811c8059"
P1_TEST_BLOB = "f9668d20e7410e34da87039f40a228196b6b96cc"

P1_AUDIT = Path("data/research/rd34_p1/rd34-p1-dual-family-persistence-engine-freeze-audit-v1.json")
P1_AUDIT_SHA256 = "d49ac152f5ef3bc866d8051c883579c60db405826886a7f37b3d8652ddf76cdd"
P1_AUDIT_BLOB = "ba53bb7aeb8d634fa6351c4a7f0288d9b78b2438"

RD31_RUNNER = Path("scripts/research/run_rd31_market_regime_admission_governor.py")
RD31_RUNNER_BLOB = "3b5c6916e34be6c9642702fe2807e42e445ee083"

DEFAULT_RAW_ROOT = Path("data/raw/rd16b/kucoin")
OUTPUT = Path("data/research/rd34_p3_runtime")

ADMISSION_PORTFOLIO = "UNION_FOCUS"
ADMISSION_POLICY = REGIME_HYSTERESIS_ADMISSION_GOVERNOR

FAMILIES = (
    FAMILY_MOMENTUM_BREAKOUT,
    FAMILY_RELATIVE_STRENGTH_ROTATION,
)
ALL_RULES = (*MB_RULE_ORDER, *RS_RULE_ORDER)

OUTPUT_NAMES = (
    "input-and-conformance-audit.json",
    "admitted-origin-ledger.csv",
    "persistence-outcome-ledger.csv",
    "markout-ledger.csv",
    "markout-summary.csv",
    "qualification-evaluation.csv",
    "family-rule-selection.csv",
    "selected-dual-family-rules-freeze.json",
    "rd34-p3-dual-family-persistence-diagnostic-report-v1.json",
)

SUCCESS_DECISION = "RD34_DUAL_FAMILY_PERSISTENCE_RULES_QUALIFIED_FREEZE_BEFORE_ECONOMICS"
FAILURE_DECISION = "RD34_NEW_ALPHA_SOURCE_REQUIRED"
SUCCESS_NEXT = "RD34_P4_FREEZE_SELECTED_DUAL_FAMILY_RULES_PRE_ECONOMIC_REPLAY"
FAILURE_NEXT = "RD35_NEW_ALPHA_SOURCE_DISCOVERY_PREREGISTRATION_REQUIRED"


class RunnerError(RuntimeError):
    pass


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser()
    value.add_argument("--repo-root", type=Path, required=True)
    value.add_argument("--raw-root", type=Path, default=None)
    value.add_argument("--execute", action="store_true")
    value.add_argument("--validate-only", action="store_true")
    value.add_argument("--expected-freeze-commit", default=None)
    return value


def git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if completed.returncode != 0:
        raise RunnerError(f"git {' '.join(args)} failed: {completed.stderr}")
    return completed.stdout.strip()


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


def load_rd31_runner() -> Any:
    path = ROOT / RD31_RUNNER
    spec = importlib.util.spec_from_file_location(
        "_rd31_frozen_runner_for_rd34",
        path,
    )
    if spec is None or spec.loader is None:
        raise RunnerError("cannot load frozen RD31 runner")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def verify_lineage(
    repo: Path,
    expected_freeze_commit: str,
) -> dict[str, Any]:
    if git(repo, "diff", "--cached", "--name-only", "--"):
        raise RunnerError("staged tracked changes exist before RD34 diagnostic")
    if git(repo, "diff", "--name-only", "--"):
        raise RunnerError("unstaged tracked changes exist before RD34 diagnostic")

    head = git(repo, "rev-parse", "HEAD")
    if head != expected_freeze_commit:
        raise RunnerError(f"RD34 diagnostic HEAD {head} != freeze {expected_freeze_commit}")
    if git(repo, "rev-parse", "HEAD^") != P1_FREEZE_COMMIT:
        raise RunnerError("RD34 diagnostic runner-freeze parent is not P1")
    if git(repo, "rev-parse", "HEAD^^") != P0_FREEZE_COMMIT:
        raise RunnerError("RD34 diagnostic runner-freeze grandparent is not P0")

    checks = (
        (
            P0_PROTOCOL,
            P0_PROTOCOL_SHA256,
            P0_PROTOCOL_BLOB,
            "P0 protocol",
        ),
        (
            P0_AUDIT,
            P0_AUDIT_SHA256,
            P0_AUDIT_BLOB,
            "P0 audit",
        ),
        (
            P1_ENGINE,
            P1_ENGINE_SHA256,
            P1_ENGINE_BLOB,
            "P1 engine",
        ),
        (
            P1_TEST,
            P1_TEST_SHA256,
            P1_TEST_BLOB,
            "P1 tests",
        ),
        (
            P1_AUDIT,
            P1_AUDIT_SHA256,
            P1_AUDIT_BLOB,
            "P1 audit",
        ),
    )
    verified: dict[str, dict[str, str]] = {}
    for relative, expected_sha, expected_blob, label in checks:
        path = repo / relative
        if not path.is_file():
            raise RunnerError(f"{label} missing: {path}")
        actual_sha = sha256(path)
        if actual_sha != expected_sha:
            raise RunnerError(f"{label} SHA drifted: {actual_sha} != {expected_sha}")
        actual_blob = git(
            repo,
            "rev-parse",
            f"HEAD:{relative.as_posix()}",
        )
        if actual_blob != expected_blob:
            raise RunnerError(f"{label} blob drifted: {actual_blob} != {expected_blob}")
        verified[relative.as_posix()] = {
            "sha256": actual_sha,
            "git_blob": actual_blob,
        }

    rd31_blob = git(
        repo,
        "rev-parse",
        f"HEAD:{RD31_RUNNER.as_posix()}",
    )
    if rd31_blob != RD31_RUNNER_BLOB:
        raise RunnerError(f"RD31 runner blob drifted: {rd31_blob} != {RD31_RUNNER_BLOB}")

    protocol = load_json(repo / P0_PROTOCOL)
    if protocol.get("status") != "FROZEN_PRE_DIAGNOSTIC_EXECUTION":
        raise RunnerError("RD34 P0 protocol is not frozen")
    scope = protocol.get("scope")
    if not isinstance(scope, dict):
        raise RunnerError("RD34 P0 scope missing")
    if scope.get("portfolio_economics_in_this_diagnostic") is not False:
        raise RunnerError("RD34 protocol unexpectedly permits portfolio economics")
    if scope.get("2024_access_allowed") is not False:
        raise RunnerError("RD34 protocol unexpectedly permits 2024")

    if tuple(protocol.get("mb_rule_order", ())[i]["rule_id"] for i in range(2)) != MB_RULE_ORDER:
        raise RunnerError("RD34 MB rule order drifted")
    if tuple(protocol.get("rs_rule_order", ())[i]["rule_id"] for i in range(2)) != RS_RULE_ORDER:
        raise RunnerError("RD34 RS rule order drifted")

    markouts = protocol.get("diagnostic_markouts")
    if not isinstance(markouts, dict):
        raise RunnerError("RD34 markout contract missing")
    if tuple(markouts.get("horizons_hours", [])) != HORIZONS:
        raise RunnerError("RD34 markout horizon registry drifted")

    qualification_contract = protocol.get("rule_qualification")
    if not isinstance(qualification_contract, dict):
        raise RunnerError("RD34 qualification contract missing")
    if (
        tuple(
            qualification_contract.get(
                "all_conditions_required_for_every_universe_and_both_years",
                [],
            )
        )
        != QUALIFICATION_GATES
    ):
        raise RunnerError("RD34 qualification gates drifted")

    p1 = load_json(repo / P1_AUDIT)
    if p1.get("status") != "PASS":
        raise RunnerError("RD34 P1 audit is not PASS")
    for field in (
        "raw_market_data_loaded",
        "diagnostic_executed",
        "economic_execution_performed",
        "candidate_results_observed",
        "2024_accessed",
        "post_2024_accessed",
        "production_authorized",
    ):
        if p1.get(field) is not False:
            raise RunnerError(f"RD34 P1 prohibited flag true: {field}")

    return {
        "runner_freeze_commit": expected_freeze_commit,
        "p1_freeze_commit": P1_FREEZE_COMMIT,
        "p0_freeze_commit": P0_FREEZE_COMMIT,
        "rd33_results_commit": RD33_RESULTS_COMMIT,
        "verified_sources": verified,
        "rd31_runner_blob": RD31_RUNNER_BLOB,
        "admission_policy": ADMISSION_POLICY,
        "admission_portfolio": ADMISSION_PORTFOLIO,
        "families": list(FAMILIES),
        "rules": list(ALL_RULES),
        "universes": list(UNIVERSES),
        "periods": list(PERIODS),
        "horizons_hours": list(HORIZONS),
        "qualification_gates": list(QUALIFICATION_GATES),
    }


def period_id_for(timestamp: pd.Timestamp) -> str:
    value = pd.Timestamp(timestamp)
    value = value.tz_localize("UTC") if value.tzinfo is None else value.tz_convert("UTC")
    if value.year == 2022:
        return "ROBUSTNESS_2022"
    if value.year == 2023:
        return "ROBUSTNESS_2023"
    raise RunnerError(f"diagnostic origin outside 2022-2023: {value}")


def _origin_key(
    universe_id: str,
    timestamp: Any,
    pair: str,
) -> tuple[str, int, str]:
    value = pd.Timestamp(timestamp)
    value = value.tz_localize("UTC") if value.tzinfo is None else value.tz_convert("UTC")
    return str(universe_id), int(value.value), str(pair)


def admitted_union_keys(
    admission_ledger: pd.DataFrame,
) -> set[tuple[str, int, str]]:
    required = {
        "policy_id",
        "portfolio_id",
        "universe_id",
        "signal_time",
        "pair",
        "admission_outcome",
    }
    missing = sorted(required.difference(admission_ledger.columns))
    if missing:
        raise RunnerError(f"RD31 admission ledger missing fields: {missing}")

    subset = admission_ledger.loc[
        (admission_ledger["policy_id"].astype(str) == ADMISSION_POLICY)
        & (admission_ledger["portfolio_id"].astype(str) == ADMISSION_PORTFOLIO)
    ].copy()
    if subset.empty:
        raise RunnerError("RD31 UNION_FOCUS hysteresis admission ledger is empty")

    keys = [
        _origin_key(
            row["universe_id"],
            row["signal_time"],
            row["pair"],
        )
        for row in subset.to_dict(orient="records")
    ]
    if len(keys) != len(set(keys)):
        raise RunnerError("RD31 UNION_FOCUS admission keys are not unique")

    admitted = {
        _origin_key(
            row["universe_id"],
            row["signal_time"],
            row["pair"],
        )
        for row in subset.to_dict(orient="records")
        if str(row["admission_outcome"]) == "ADMIT"
    }
    if not admitted:
        raise RunnerError("RD31 UNION_FOCUS hysteresis admitted no origins")
    return admitted


def build_admitted_origins(
    events: pd.DataFrame,
    admission_ledger: pd.DataFrame,
) -> pd.DataFrame:
    admitted = admitted_union_keys(admission_ledger)
    required = {
        "family_id",
        "universe_id",
        "timestamp",
        "pair",
        "membership_rank",
    }
    missing = sorted(required.difference(events.columns))
    if missing:
        raise RunnerError(f"signal ledger missing origin fields: {missing}")

    family_events = events.loc[events["family_id"].astype(str).isin(FAMILIES)].copy()
    family_events["timestamp"] = pd.to_datetime(
        family_events["timestamp"],
        utc=True,
        errors="raise",
    )

    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str, int, str]] = set()
    for row in family_events.to_dict(orient="records"):
        key = _origin_key(
            row["universe_id"],
            row["timestamp"],
            row["pair"],
        )
        if key not in admitted:
            continue

        family = str(row["family_id"])
        unique = (
            family,
            str(row["universe_id"]),
            int(pd.Timestamp(row["timestamp"]).value),
            str(row["pair"]),
        )
        if unique in seen:
            raise RunnerError(f"duplicate admitted family origin: {unique}")
        seen.add(unique)

        normalized = {
            "family_id": family,
            "universe_id": str(row["universe_id"]),
            "period_id": period_id_for(pd.Timestamp(row["timestamp"])),
            "pair": str(row["pair"]),
            "timestamp": pd.Timestamp(row["timestamp"]),
            "membership_rank": int(row["membership_rank"]),
        }
        if family == FAMILY_MOMENTUM_BREAKOUT:
            if "aux_value" not in row:
                raise RunnerError("MB signal ledger lost frozen aux_value")
            normalized["aux_value"] = row["aux_value"]

        origin = origin_from_event(normalized)
        rows.append(
            {
                "family_id": origin.family_id,
                "universe_id": origin.universe_id,
                "period_id": origin.period_id,
                "pair": origin.pair,
                "signal_time": origin.signal_time,
                "membership_rank": origin.membership_rank,
                "breakout_reference": (origin.breakout_reference),
                "rd31_admission_policy": ADMISSION_POLICY,
                "rd31_admission_portfolio": ADMISSION_PORTFOLIO,
            }
        )

    if not rows:
        raise RunnerError("no RD31-admitted MB/RS origins")
    return (
        pd.DataFrame.from_records(rows)
        .sort_values(
            [
                "signal_time",
                "universe_id",
                "membership_rank",
                "pair",
                "family_id",
            ],
            kind="stable",
        )
        .reset_index(drop=True)
    )


def _membership_at(
    rd31: Any,
    membership: list[Any],
    *,
    universe_id: str,
    timestamp: pd.Timestamp,
) -> tuple[tuple[str, int], ...]:
    members = rd31.membership_at(
        membership,
        universe_id=universe_id,
        timestamp=timestamp,
    )
    return tuple((str(pair), int(rank)) for pair, rank in members)


def run_diagnostic(
    *,
    rd31: Any,
    events: pd.DataFrame,
    frames: dict[str, pd.DataFrame],
    state_frame: pd.DataFrame,
    membership: list[Any],
) -> tuple[
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    dict[str, Any],
]:
    admission = rd31.build_admission_diagnostic_ledger(
        events=events,
        frames=frames,
        state_frame=state_frame,
        membership=membership,
    )
    origins = build_admitted_origins(events, admission)
    lookups = build_lookups(frames)

    outcome_rows: list[dict[str, Any]] = []
    markout_rows: list[dict[str, Any]] = []

    for row in origins.to_dict(orient="records"):
        event = {
            "family_id": row["family_id"],
            "universe_id": row["universe_id"],
            "period_id": row["period_id"],
            "pair": row["pair"],
            "timestamp": row["signal_time"],
            "membership_rank": row["membership_rank"],
        }
        if row["family_id"] == FAMILY_MOMENTUM_BREAKOUT:
            event["aux_value"] = row["breakout_reference"]

        origin = origin_from_event(event)
        members_t1 = None
        members_t2 = None
        if origin.family_id == FAMILY_RELATIVE_STRENGTH_ROTATION:
            members_t1 = _membership_at(
                rd31,
                membership,
                universe_id=origin.universe_id,
                timestamp=(origin.signal_time + pd.Timedelta(hours=1)),
            )
            members_t2 = _membership_at(
                rd31,
                membership,
                universe_id=origin.universe_id,
                timestamp=(origin.signal_time + pd.Timedelta(hours=2)),
            )

        outcomes = outcomes_for_origin(
            origin,
            frames,
            lookups,
            members_t1,
            members_t2,
        )
        for outcome in outcomes:
            outcome_rows.append(
                {
                    "family_id": outcome.family_id,
                    "rule_id": outcome.rule_id,
                    "universe_id": outcome.universe_id,
                    "period_id": outcome.period_id,
                    "pair": outcome.pair,
                    "signal_time": outcome.signal_time,
                    "confirmed": outcome.confirmed,
                    "reason": outcome.reason,
                    "entry_time": outcome.entry_time,
                    "value_t1": outcome.value_t1,
                    "value_t2": outcome.value_t2,
                    "breakout_reference": (origin.breakout_reference),
                }
            )
            markout_rows.extend(
                full_markouts(
                    outcome,
                    frames,
                    lookups,
                )
            )

    outcomes_frame = pd.DataFrame.from_records(outcome_rows)
    if outcomes_frame.empty:
        raise RunnerError("diagnostic produced no rule outcomes")

    markout_columns = [
        "family_id",
        "rule_id",
        "universe_id",
        "period_id",
        "pair",
        "signal_time",
        "entry_time",
        "horizon_hours",
        "exit_time",
        "entry_price",
        "exit_price",
        "gross_markout",
        "net_markout",
    ]
    markouts = pd.DataFrame.from_records(
        markout_rows,
        columns=markout_columns,
    )
    summary = summarize_markouts(markouts)

    qualification_rows: list[dict[str, Any]] = []
    selection_rows: list[dict[str, Any]] = []
    for family, rules in (
        (FAMILY_MOMENTUM_BREAKOUT, MB_RULE_ORDER),
        (
            FAMILY_RELATIVE_STRENGTH_ROTATION,
            RS_RULE_ORDER,
        ),
    ):
        evaluations = [qualification(summary, family, rule) for rule in rules]
        for evaluation in evaluations:
            for cell in evaluation["cells"]:
                qualification_rows.append(
                    {
                        "family_id": family,
                        "rule_id": evaluation["rule_id"],
                        **cell,
                    }
                )

    decision = diagnostic_decision(summary)
    for family_key in ("mb", "rs"):
        family_result = decision[family_key]
        selection_rows.append(
            {
                "family_id": family_result["family_id"],
                "selected_rule": (family_result["selected_rule"]),
                "priority_order": "|".join(family_result["priority_order"]),
                "return_ranking_used": (family_result["return_ranking_used"]),
                "family_qualified": (family_result["selected_rule"] is not None),
            }
        )

    qualifications = pd.DataFrame.from_records(qualification_rows)
    selections = pd.DataFrame.from_records(selection_rows)
    if len(qualifications) != 24:
        raise RunnerError(f"qualification evaluation row count {len(qualifications)} != 24")
    if len(selections) != 2:
        raise RunnerError("family selection row count must be 2")

    return (
        origins,
        outcomes_frame,
        markouts,
        summary,
        qualifications,
        selections,
        decision,
    )


def make_report(
    *,
    freeze_commit: str,
    signal_event_count: int,
    membership_snapshot_count: int,
    required_pair_count: int,
    origins: pd.DataFrame,
    outcomes: pd.DataFrame,
    markouts: pd.DataFrame,
    summary: pd.DataFrame,
    qualifications: pd.DataFrame,
    decision: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    selected_mb = decision["selected_mb_rule"]
    selected_rs = decision["selected_rs_rule"]
    if decision["both_families_qualified"]:
        final_decision = SUCCESS_DECISION
        next_stage = SUCCESS_NEXT
    else:
        final_decision = FAILURE_DECISION
        next_stage = FAILURE_NEXT

    freeze = {
        "schema_version": ("rd34-p3-selected-dual-family-rules-freeze-v1"),
        "decision": final_decision,
        "next_stage": next_stage,
        "selected_mb_rule": selected_mb,
        "selected_rs_rule": selected_rs,
        "selection_method": (
            "FIRST_QUALIFIED_RULE_IN_PREREGISTERED_FAMILY_PRIORITY_ORDER_NO_RETURN_RANKING"
        ),
        "runner_freeze_commit": freeze_commit,
        "admission_policy": ADMISSION_POLICY,
        "admission_portfolio": ADMISSION_PORTFOLIO,
        "qualification_gate_count": len(QUALIFICATION_GATES),
        "2024_accessed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
    }

    report = {
        "schema_version": ("rd34-p3-dual-family-persistence-diagnostic-report-v1"),
        "stage": ("RD34_P3_DUAL_FAMILY_PERSISTENCE_DIAGNOSTIC_2022_2023"),
        "status": "PASS",
        "decision": final_decision,
        "next_stage": next_stage,
        "runner_freeze_commit": freeze_commit,
        "admission_policy": ADMISSION_POLICY,
        "admission_portfolio": ADMISSION_PORTFOLIO,
        "signal_event_count_2022_2023": (signal_event_count),
        "membership_snapshot_count": (membership_snapshot_count),
        "required_pit_feature_pair_count": (required_pair_count),
        "admitted_origin_count": len(origins),
        "persistence_outcome_count": len(outcomes),
        "complete_markout_row_count": len(markouts),
        "markout_summary_row_count": len(summary),
        "qualification_evaluation_row_count": (len(qualifications)),
        "selected_mb_rule": selected_mb,
        "selected_rs_rule": selected_rs,
        "both_families_qualified": (decision["both_families_qualified"]),
        "return_ranking_used": False,
        "portfolio_economics_executed": False,
        "economic_execution_performed": False,
        "candidate_parameters_changed_after_diagnostic": (False),
        "research_logic_changed_after_diagnostic": False,
        "2024_accessed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
    }
    return report, freeze


def output_manifest(
    output: Path,
    *,
    decision: str,
    freeze_commit: str,
) -> dict[str, Any]:
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
    return {
        "schema_version": "rd34-p3-output-manifest-v1",
        "decision": decision,
        "runner_freeze_commit": freeze_commit,
        "file_count": len(files),
        "files": files,
        "deterministic_hash": hashlib.sha256(canonical).hexdigest(),
    }


def validate_outputs(repo: Path) -> dict[str, Any]:
    output = repo / OUTPUT
    if not output.is_dir():
        raise RunnerError(f"RD34 diagnostic output missing: {output}")
    observed = sorted(path.name for path in output.iterdir() if path.is_file())
    expected = sorted((*OUTPUT_NAMES, "output-manifest.json"))
    if observed != expected:
        raise RunnerError(f"RD34 output set drifted: {observed} != {expected}")

    origins = pd.read_csv(
        output / "admitted-origin-ledger.csv",
        low_memory=False,
    )
    outcomes = pd.read_csv(
        output / "persistence-outcome-ledger.csv",
        low_memory=False,
    )
    markouts = pd.read_csv(
        output / "markout-ledger.csv",
        low_memory=False,
    )
    summary = pd.read_csv(
        output / "markout-summary.csv",
        low_memory=False,
    )
    qualifications = pd.read_csv(
        output / "qualification-evaluation.csv",
        low_memory=False,
    )
    selections = pd.read_csv(
        output / "family-rule-selection.csv",
        low_memory=False,
    )

    if origins.empty:
        raise RunnerError("RD34 admitted origins are empty")
    if outcomes.empty:
        raise RunnerError("RD34 outcomes are empty")
    if set(origins["family_id"].astype(str)) != set(FAMILIES):
        raise RunnerError("RD34 origin family registry drifted")
    if set(origins["universe_id"].astype(str)) != set(UNIVERSES):
        raise RunnerError("RD34 origin universe registry drifted")
    if set(origins["period_id"].astype(str)) != set(PERIODS):
        raise RunnerError("RD34 origin period registry drifted")
    if set(outcomes["rule_id"].astype(str)) != set(ALL_RULES):
        raise RunnerError("RD34 outcome rule registry drifted")

    expected_outcomes = len(origins) * 2
    if len(outcomes) != expected_outcomes:
        raise RunnerError(f"RD34 outcome count {len(outcomes)} != 2 * origins {expected_outcomes}")

    if len(qualifications) != 24:
        raise RunnerError("RD34 qualification row count drifted")
    if set(qualifications["rule_id"].astype(str)) != set(ALL_RULES):
        raise RunnerError("RD34 qualification rule registry drifted")
    if set(qualifications["universe_id"].astype(str)) != set(UNIVERSES):
        raise RunnerError("RD34 qualification universe registry drifted")
    if set(qualifications["period_id"].astype(str)) != set(PERIODS):
        raise RunnerError("RD34 qualification period registry drifted")
    if len(selections) != 2:
        raise RunnerError("RD34 family selection row count drifted")
    if set(selections["family_id"].astype(str)) != set(FAMILIES):
        raise RunnerError("RD34 family selection registry drifted")
    if any(selections["return_ranking_used"].astype(str).str.lower().eq("true")):
        raise RunnerError("RD34 selection illegally used return ranking")

    for frame, columns in (
        (origins, ("signal_time",)),
        (
            outcomes,
            ("signal_time", "entry_time"),
        ),
        (
            markouts,
            (
                "signal_time",
                "entry_time",
                "exit_time",
            ),
        ),
    ):
        for column in columns:
            if column not in frame.columns:
                continue
            timestamps = pd.to_datetime(
                frame[column],
                utc=True,
                errors="coerce",
            ).dropna()
            if bool((timestamps >= DATA_CUTOFF).any()):
                raise RunnerError(f"RD34 {column} crossed sealed cutoff")

    report = load_json(output / "rd34-p3-dual-family-persistence-diagnostic-report-v1.json")
    if report.get("status") != "PASS":
        raise RunnerError("RD34 diagnostic report not PASS")
    if report.get("decision") not in (
        SUCCESS_DECISION,
        FAILURE_DECISION,
    ):
        raise RunnerError("RD34 diagnostic decision drifted")
    if report.get("return_ranking_used") is not False:
        raise RunnerError("RD34 report used return ranking")
    for field in (
        "portfolio_economics_executed",
        "economic_execution_performed",
        "candidate_parameters_changed_after_diagnostic",
        "research_logic_changed_after_diagnostic",
        "2024_accessed",
        "post_2024_accessed",
        "production_authorized",
    ):
        if report.get(field) is not False:
            raise RunnerError(f"RD34 prohibited report flag true: {field}")

    selected_freeze = load_json(output / "selected-dual-family-rules-freeze.json")
    if selected_freeze.get("decision") != report.get("decision"):
        raise RunnerError("RD34 freeze/report decision mismatch")
    if selected_freeze.get("selected_mb_rule") != report.get(
        "selected_mb_rule"
    ) or selected_freeze.get("selected_rs_rule") != report.get("selected_rs_rule"):
        raise RunnerError("RD34 freeze/report rule mismatch")

    manifest = load_json(output / "output-manifest.json")
    if manifest.get("file_count") != len(OUTPUT_NAMES):
        raise RunnerError("RD34 manifest file count drifted")
    if set(manifest.get("files", {})) != set(OUTPUT_NAMES):
        raise RunnerError("RD34 manifest registry drifted")
    canonical: dict[str, dict[str, Any]] = {}
    for name in OUTPUT_NAMES:
        path = output / name
        record = manifest["files"][name]
        actual_sha = sha256(path)
        actual_bytes = path.stat().st_size
        if record.get("sha256") != actual_sha:
            raise RunnerError(f"RD34 manifest SHA mismatch: {name}")
        if int(record.get("bytes", -1)) != actual_bytes:
            raise RunnerError(f"RD34 manifest bytes mismatch: {name}")
        canonical[name] = {
            "sha256": actual_sha,
            "bytes": actual_bytes,
        }
    deterministic = hashlib.sha256(
        json.dumps(
            canonical,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
    ).hexdigest()
    if manifest.get("deterministic_hash") != deterministic:
        raise RunnerError("RD34 manifest deterministic hash drifted")

    return {
        "status": "PASS",
        "decision": report["decision"],
        "next_stage": report["next_stage"],
        "selected_mb_rule": report["selected_mb_rule"],
        "selected_rs_rule": report["selected_rs_rule"],
        "admitted_origin_count": len(origins),
        "persistence_outcome_count": len(outcomes),
        "complete_markout_row_count": len(markouts),
        "markout_summary_row_count": len(summary),
        "qualification_evaluation_rows": len(qualifications),
        "manifest_deterministic_hash": (manifest["deterministic_hash"]),
        "portfolio_economics_executed": False,
        "economic_execution_performed": False,
        "2024_accessed": False,
        "post_2024_accessed": False,
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
            )
        )
        return 0

    if not args.execute:
        raise RunnerError("diagnostic execution requires explicit --execute")
    if not args.expected_freeze_commit:
        raise RunnerError("--expected-freeze-commit is required")

    lineage = verify_lineage(
        repo,
        args.expected_freeze_commit,
    )
    rd31 = load_rd31_runner()

    raw_root = (
        args.raw_root.resolve()
        if args.raw_root is not None
        else (repo / DEFAULT_RAW_ROOT).resolve()
    )
    events = rd31.load_signal_events(repo)
    membership = rd31.selection_membership(rd31.load_membership(repo / rd31.MEMBERSHIP))
    coverage = rd31.validate_signal_membership_coverage(
        events,
        membership,
    )
    pairs = rd31.required_feature_pairs(
        events,
        membership,
    )
    frames = rd31.load_feature_frames(
        raw_root=raw_root,
        pairs=pairs,
    )
    state_frame = rd31.load_state_frame(raw_root)

    output = repo / OUTPUT
    output.mkdir(
        parents=True,
        exist_ok=False,
    )
    write_json(
        output / "input-and-conformance-audit.json",
        {
            "schema_version": ("rd34-p3-input-conformance-audit-v1"),
            "stage": ("RD34_P3_DUAL_FAMILY_PERSISTENCE_DIAGNOSTIC_2022_2023"),
            "lineage": lineage,
            "signal_event_count": len(events),
            "membership_snapshot_count": len(membership),
            "required_pit_feature_pair_count": len(pairs),
            "required_pit_feature_pairs": pairs,
            "membership_signal_coverage": coverage,
            "admission_policy": ADMISSION_POLICY,
            "admission_portfolio": ADMISSION_PORTFOLIO,
            "diagnostic_execution_performed": True,
            "portfolio_economics_executed": False,
            "economic_execution_performed": False,
            "2024_accessed": False,
            "post_2024_accessed": False,
            "production_authorized": False,
        },
    )

    (
        origins,
        outcomes,
        markouts,
        summary,
        qualifications,
        selections,
        decision,
    ) = run_diagnostic(
        rd31=rd31,
        events=events,
        frames=frames,
        state_frame=state_frame,
        membership=membership,
    )

    report, selected_freeze = make_report(
        freeze_commit=args.expected_freeze_commit,
        signal_event_count=len(events),
        membership_snapshot_count=len(membership),
        required_pair_count=len(pairs),
        origins=origins,
        outcomes=outcomes,
        markouts=markouts,
        summary=summary,
        qualifications=qualifications,
        decision=decision,
    )

    origins.to_csv(
        output / "admitted-origin-ledger.csv",
        index=False,
        lineterminator="\n",
    )
    outcomes.to_csv(
        output / "persistence-outcome-ledger.csv",
        index=False,
        lineterminator="\n",
    )
    markouts.to_csv(
        output / "markout-ledger.csv",
        index=False,
        lineterminator="\n",
    )
    summary.to_csv(
        output / "markout-summary.csv",
        index=False,
        lineterminator="\n",
    )
    qualifications.to_csv(
        output / "qualification-evaluation.csv",
        index=False,
        lineterminator="\n",
    )
    selections.to_csv(
        output / "family-rule-selection.csv",
        index=False,
        lineterminator="\n",
    )
    write_json(
        output / "selected-dual-family-rules-freeze.json",
        selected_freeze,
    )
    write_json(
        output / "rd34-p3-dual-family-persistence-diagnostic-report-v1.json",
        report,
    )

    manifest = output_manifest(
        output,
        decision=report["decision"],
        freeze_commit=args.expected_freeze_commit,
    )
    write_json(
        output / "output-manifest.json",
        manifest,
    )

    print(
        json.dumps(
            validate_outputs(repo),
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"RD34_P3_ERROR={exc}", file=sys.stderr)
        raise
