from __future__ import annotations

import argparse
import hashlib
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
    BASE_ROUND_TRIP_COST,
)
from spotbot.research.rd40_transition_dynamics_governor import (  # noqa: E402
    build_governor_timelines,
    governor_state_at,
    normalize_governor_transitions,
)
from spotbot.research.rd41_rcv_terminal_hazard_diagnostic import (  # noqa: E402
    DATA_CUTOFF,
    DATA_START,
    FAILURE_DECISION,
    FAILURE_NEXT,
    FEATURES,
    LANDMARKS_HAZARD,
    LANDMARKS_RCV,
    MAX_HOLD,
    PERIODS,
    SUCCESS_DECISION,
    SUCCESS_NEXT,
    TIME_FAILURE,
    UNIVERSES,
    build_ledgers,
    governor_descriptive_attribution,
    hazard_cell_evaluation,
    normalize_price_frame,
    price_lookup,
    qualify_feature_landmarks,
    rcv_cell_evaluation,
    validate_constants,
)

P3_FREEZE = "a3456ef22d31b8762056e10915ee651bdee3df47"
P3_PROTOCOL = Path(
    "data/research/rd41_p3/"
    "rd41-p3-remaining-control-value-terminal-hazard-"
    "continuous-channel-diagnostic-preregistration-v1.json"
)
P3_PROTOCOL_BLOB = "bc128ac5985c2abc1e8aadabfe4d0eb53da8d8a1"
P3_PROTOCOL_SHA256 = "0551753bbc7b971eca491f11918651060cc79171d17e008b4a9c8f0ba993aa60"
P3_AUDIT = Path("data/research/rd41_p3/rd41-p3-preregistration-audit-v1.json")
P3_AUDIT_BLOB = "686d8706fba4ea2c0dcddfbff6da76eb9a52d15e"

P2_RESULTS = "774d7d9b66dd2580359ee28a76c4819da4b29ced"
P2_RISK_SET = Path("data/research/rd41_p2_runtime/full-control-risk-set-ledger.csv")
P2_RISK_SET_SHA256 = "790329e9f596c9012fbe58d90489c39671682f0951273261182f45952c5b78d2"
P2_AGE = Path("data/research/rd41_p2_runtime/risk-set-by-year-universe-age.csv")
P2_AGE_SHA256 = "aefa17eb86f210ec4c319110d7bfcb4be501e11165920e591b0279a568964b40"
P2_GOVERNOR = Path("data/research/rd41_p2_runtime/risk-set-by-year-universe-governor-state.csv")
P2_GOVERNOR_SHA256 = "4867ce113ba9706da5624c5b3288bb80072efbb1a78a154103a88843650956d5"
P2_TERMINALS = Path("data/research/rd41_p2_runtime/terminal-outcome-archetype-summary.csv")
P2_TERMINALS_SHA256 = "8cdc14652f70173bfcc04fa0db74276cbc0dd83c59f3981d8aea27d3bb6d17ff"

RD31_TRANSITIONS = Path("data/research/rd31_p1_runtime/governor-transition-ledger.csv")
RD31_TRANSITIONS_SHA256 = "46c36f91041912ebcfefdbe2d710bb090d73b3aeea65cabad2be71ad138e640b"

DEFAULT_RAW_ROOT = Path("data/raw/rd16b/kucoin")
OUTPUT = Path("data/research/rd41_p4_runtime")

OUTPUT_NAMES = (
    "target-ledger.csv",
    "feature-ledger.csv",
    "rcv-cell-evaluation.csv",
    "rcv-feature-landmark-qualification.csv",
    "hazard-cell-evaluation.csv",
    "hazard-feature-landmark-qualification.csv",
    "governor-descriptive-attribution.csv",
    "qualified-continuous-evidence-freeze.json",
    "rd41-p4-remaining-control-value-terminal-hazard-diagnostic-report-v1.json",
)


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
        raise RunnerError("staged changes before RD41-P4")
    if git(repo, "diff", "--name-only", "--"):
        raise RunnerError("unstaged tracked changes before RD41-P4")

    head = git(repo, "rev-parse", "HEAD")
    if head != expected_freeze_commit:
        raise RunnerError(f"RD41-P4 HEAD {head} != freeze {expected_freeze_commit}")
    if git(repo, "rev-parse", "HEAD^") != P3_FREEZE:
        raise RunnerError("RD41-P4 freeze parent is not P3")

    for path, blob, label in (
        (P3_PROTOCOL, P3_PROTOCOL_BLOB, "P3 protocol"),
        (P3_AUDIT, P3_AUDIT_BLOB, "P3 audit"),
    ):
        verify_blob(repo, path, blob, label)

    if sha256(repo / P3_PROTOCOL) != P3_PROTOCOL_SHA256:
        raise RunnerError("P3 protocol SHA drifted")
    for path, expected, label in (
        (P2_RISK_SET, P2_RISK_SET_SHA256, "P2 risk set"),
        (P2_AGE, P2_AGE_SHA256, "P2 age support"),
        (P2_GOVERNOR, P2_GOVERNOR_SHA256, "P2 governor support"),
        (P2_TERMINALS, P2_TERMINALS_SHA256, "P2 terminals"),
        (RD31_TRANSITIONS, RD31_TRANSITIONS_SHA256, "RD31 transitions"),
    ):
        if sha256(repo / path) != expected:
            raise RunnerError(f"{label} SHA drifted")

    protocol = load_json(repo / P3_PROTOCOL)
    audit = load_json(repo / P3_AUDIT)
    if protocol.get("status") != "FROZEN_PRE_TARGET_PRE_FEATURE_DIAGNOSTIC":
        raise RunnerError("P3 protocol status drifted")
    if protocol.get("next_stage") != (
        "RD41_P4_FREEZE_AND_RUN_REMAINING_CONTROL_VALUE_"
        "TERMINAL_HAZARD_CONTINUOUS_CHANNEL_DIAGNOSTIC_ONCE"
    ):
        raise RunnerError("P3 next-stage drifted")
    if audit.get("protocol_sha256") != P3_PROTOCOL_SHA256:
        raise RunnerError("P3 audit protocol SHA drifted")

    for field in (
        "raw_market_data_loaded_in_p3",
        "target_values_computed_in_p3",
        "feature_values_computed_in_p3",
        "rcv_results_observed_in_p3",
        "hazard_results_observed_in_p3",
        "governor_predictive_results_observed_in_p3",
        "economic_action_executed",
        "parameter_search_used",
        "threshold_optimization_used",
        "winner_selection_used",
        "2024_accessed",
        "post_2024_accessed",
        "production_authorized",
    ):
        if audit.get(field) is not False:
            raise RunnerError(f"P3 pre-exposure flag drifted: {field}")

    validate_constants()
    return {
        "runner_freeze_commit": expected_freeze_commit,
        "p3_freeze_commit": P3_FREEZE,
        "p3_protocol_git_blob": P3_PROTOCOL_BLOB,
        "p3_protocol_sha256": P3_PROTOCOL_SHA256,
        "p3_audit_git_blob": P3_AUDIT_BLOB,
        "p2_results_commit": P2_RESULTS,
        "p2_risk_set_sha256": P2_RISK_SET_SHA256,
        "p2_age_support_sha256": P2_AGE_SHA256,
        "p2_governor_support_sha256": P2_GOVERNOR_SHA256,
        "p2_terminal_summary_sha256": P2_TERMINALS_SHA256,
        "rd31_transition_ledger_sha256": RD31_TRANSITIONS_SHA256,
    }


def load_risk_set(repo: Path) -> pd.DataFrame:
    frame = pd.read_csv(repo / P2_RISK_SET, low_memory=False)
    required = {
        "control_position_id",
        "universe_id",
        "period_id",
        "pair",
        "signal_time",
        "entry_time",
        "exit_time",
        "exit_reason",
        "entry_price",
        "exit_price",
        "quantity",
        "risk_set_class",
    }
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise RunnerError(f"P2 risk set missing columns: {missing}")

    for column in ("signal_time", "entry_time", "exit_time"):
        frame[column] = pd.to_datetime(
            frame[column],
            utc=True,
            errors="raise",
        ).dt.as_unit("ns")
    for column in ("entry_price", "exit_price", "quantity"):
        frame[column] = pd.to_numeric(
            frame[column],
            errors="raise",
        ).astype(float)

    if len(frame) != 512:
        raise RunnerError(f"risk set count {len(frame)} != 512")
    if set(frame["risk_set_class"].astype(str)) != {"RESOLVED_CONTROL_OUTCOME"}:
        raise RunnerError("P4 expected all 512 positions resolved")
    if set(frame["exit_reason"].astype(str)) != {TIME_FAILURE, MAX_HOLD}:
        raise RunnerError("terminal reason registry drifted")
    if frame["entry_time"].min() < DATA_START:
        raise RunnerError("pre-2022 position entered P4")
    if frame["exit_time"].max() >= DATA_CUTOFF:
        raise RunnerError("2024+ control exit entered P4")
    return frame


def load_prices(
    *,
    raw_root: Path,
    pairs: list[str],
) -> dict[str, dict[int, tuple[float, float, float, float]]]:
    lookups = {}
    for index, pair in enumerate(pairs, start=1):
        path = raw_root / pair / "1h.parquet"
        if not path.is_file():
            raise RunnerError(f"KuCoin source missing: {path}")
        raw = pd.read_parquet(
            path,
            columns=["timestamp", "open", "high", "low", "close"],
            engine="pyarrow",
            filters=[
                ("timestamp", ">=", DATA_START.to_pydatetime()),
                ("timestamp", "<", DATA_CUTOFF.to_pydatetime()),
            ],
        )
        frame = normalize_price_frame(raw, pair=pair)
        lookups[pair] = price_lookup(frame)
        print(
            f"RD41_P4_SOURCE={index}/{len(pairs)}:{pair}:rows={len(frame)}",
            flush=True,
        )
    return lookups


def governor_getter(repo: Path) -> Any:
    raw = pd.read_csv(repo / RD31_TRANSITIONS, low_memory=False)
    transitions = normalize_governor_transitions(raw)
    timelines = build_governor_timelines(transitions)

    def get(*, universe: str, decision_time: Any) -> str:
        return governor_state_at(
            timelines,
            universe=universe,
            decision_time=decision_time,
        )

    return get


def verify_target_count_parity(
    targets: pd.DataFrame,
    frozen_age: pd.DataFrame,
) -> pd.DataFrame:
    records = []
    for row in frozen_age.to_dict(orient="records"):
        period = str(row["period_id"])
        universe = str(row["universe_id"])
        age = int(row["landmark_age_hours"])
        expected = int(row["decision_row_count"])
        observed = int(
            len(
                targets.loc[
                    (targets["period_id"].astype(str) == period)
                    & (targets["universe_id"].astype(str) == universe)
                    & (targets["landmark_age_hours"] == age)
                ]
            )
        )
        records.append(
            {
                "period_id": period,
                "universe_id": universe,
                "landmark_age_hours": age,
                "frozen_p2_decision_count": expected,
                "p4_target_decision_count": observed,
                "count_delta": observed - expected,
                "parity_pass": observed == expected,
            }
        )
    result = pd.DataFrame.from_records(records)
    if len(result) != 36 or not bool(result["parity_pass"].all()):
        raise RunnerError("P4 target count parity vs P2 failed")
    return result


def verify_governor_count_parity(
    targets: pd.DataFrame,
    frozen_governor: pd.DataFrame,
) -> pd.DataFrame:
    records = []
    for row in frozen_governor.to_dict(orient="records"):
        period = str(row["period_id"])
        universe = str(row["universe_id"])
        age = int(row["landmark_age_hours"])
        state = str(row["governor_state"])
        expected = int(row["decision_row_count"])
        observed = int(
            len(
                targets.loc[
                    (targets["period_id"].astype(str) == period)
                    & (targets["universe_id"].astype(str) == universe)
                    & (targets["landmark_age_hours"] == age)
                    & (targets["governor_state"].astype(str) == state)
                ]
            )
        )
        records.append(
            {
                "period_id": period,
                "universe_id": universe,
                "landmark_age_hours": age,
                "governor_state": state,
                "frozen_p2_decision_count": expected,
                "p4_target_decision_count": observed,
                "count_delta": observed - expected,
                "parity_pass": observed == expected,
            }
        )
    result = pd.DataFrame.from_records(records)
    if len(result) != 108 or not bool(result["parity_pass"].all()):
        raise RunnerError("P4 governor count parity vs P2 failed")
    return result


def verify_hazard_labels(
    targets: pd.DataFrame,
    terminal_summary: pd.DataFrame,
) -> None:
    for period in PERIODS:
        for universe in UNIVERSES:
            terminal = terminal_summary.loc[
                (terminal_summary["period_id"].astype(str) == period)
                & (terminal_summary["universe_id"].astype(str) == universe)
            ]
            expected_event = int(
                terminal.loc[
                    terminal["terminal_outcome_archetype"].astype(str) == TIME_FAILURE,
                    "control_position_count",
                ].sum()
            )
            expected_nonevent = int(
                terminal.loc[
                    terminal["terminal_outcome_archetype"].astype(str) == MAX_HOLD,
                    "control_position_count",
                ].sum()
            )
            for age in LANDMARKS_HAZARD:
                cell = targets.loc[
                    (targets["period_id"].astype(str) == period)
                    & (targets["universe_id"].astype(str) == universe)
                    & (targets["landmark_age_hours"] == age)
                    & targets["hazard_eligible"].astype(bool)
                ]
                observed_event = int((cell["time_failure_event"] == 1).sum())
                observed_nonevent = int((cell["time_failure_event"] == 0).sum())
                if observed_event != expected_event or observed_nonevent != expected_nonevent:
                    raise RunnerError(
                        "hazard label parity failed "
                        f"{period}/{universe}/{age}: "
                        f"{observed_event}/{observed_nonevent} != "
                        f"{expected_event}/{expected_nonevent}"
                    )


def compact_qualification(frame: pd.DataFrame) -> list[dict[str, Any]]:
    rows = []
    for row in frame.to_dict(orient="records"):
        rows.append(
            {
                "target_id": str(row["target_id"]),
                "feature_id": str(row["feature_id"]),
                "landmark_age_hours": int(row["landmark_age_hours"]),
                "qualified_universes_2022": int(row["qualified_universes_2022"]),
                "qualified_universes_2023": int(row["qualified_universes_2023"]),
                "reversed_universes_2022": int(row["reversed_universes_2022"]),
                "reversed_universes_2023": int(row["reversed_universes_2023"]),
                "qualified": bool(row["qualified"]),
                "regime_direction_reversal": bool(row["regime_direction_reversal"]),
            }
        )
    return rows


def execute(
    repo: Path,
    raw_root: Path,
    expected_freeze_commit: str,
) -> dict[str, Any]:
    lineage = verify_lineage(repo, expected_freeze_commit)
    if (repo / OUTPUT).exists():
        raise RunnerError("RD41-P4 runtime exists; preserve and validate/recover")

    risk = load_risk_set(repo)
    pairs = sorted(risk["pair"].astype(str).unique())
    lookups = load_prices(raw_root=raw_root, pairs=pairs)
    get_governor = governor_getter(repo)

    exit_side_cost = BASE_ROUND_TRIP_COST / 2.0
    targets, features = build_ledgers(
        risk_set=risk,
        lookups=lookups,
        governor_state_getter=get_governor,
        exit_side_cost=exit_side_cost,
    )

    frozen_age = pd.read_csv(repo / P2_AGE, low_memory=False)
    frozen_governor = pd.read_csv(repo / P2_GOVERNOR, low_memory=False)
    frozen_terminals = pd.read_csv(
        repo / P2_TERMINALS,
        low_memory=False,
    )
    target_parity = verify_target_count_parity(targets, frozen_age)
    governor_parity = verify_governor_count_parity(
        targets,
        frozen_governor,
    )
    verify_hazard_labels(targets, frozen_terminals)

    if not bool(targets["target_evaluable"].all()):
        raise RunnerError("RCV decision-open target missing in frozen global risk set")

    rcv_cells = rcv_cell_evaluation(targets, features)
    rcv_qualification = qualify_feature_landmarks(
        rcv_cells,
        landmarks=LANDMARKS_RCV,
        target_id="REMAINING_CONTROL_VALUE",
    )
    hazard_cells = hazard_cell_evaluation(targets, features)
    hazard_qualification = qualify_feature_landmarks(
        hazard_cells,
        landmarks=LANDMARKS_HAZARD,
        target_id="TIME_FAILURE_72H_TERMINAL_HAZARD",
    )
    governor_attr = governor_descriptive_attribution(
        targets,
        features,
    )

    qualified_rcv = rcv_qualification.loc[rcv_qualification["qualified"].astype(bool)][
        ["feature_id", "landmark_age_hours"]
    ]
    qualified_hazard = hazard_qualification.loc[hazard_qualification["qualified"].astype(bool)][
        ["feature_id", "landmark_age_hours"]
    ]

    qualified_rcv_pairs = [
        {
            "feature_id": str(row["feature_id"]),
            "landmark_age_hours": int(row["landmark_age_hours"]),
        }
        for row in qualified_rcv.to_dict(orient="records")
    ]
    qualified_hazard_pairs = [
        {
            "feature_id": str(row["feature_id"]),
            "landmark_age_hours": int(row["landmark_age_hours"]),
        }
        for row in qualified_hazard.to_dict(orient="records")
    ]

    success = bool(qualified_rcv_pairs or qualified_hazard_pairs)
    decision = SUCCESS_DECISION if success else FAILURE_DECISION
    next_stage = SUCCESS_NEXT if success else FAILURE_NEXT

    output = repo / OUTPUT
    output.mkdir(parents=True, exist_ok=False)

    targets.to_csv(
        output / "target-ledger.csv",
        index=False,
        lineterminator="\n",
    )
    features.to_csv(
        output / "feature-ledger.csv",
        index=False,
        lineterminator="\n",
    )
    rcv_cells.to_csv(
        output / "rcv-cell-evaluation.csv",
        index=False,
        lineterminator="\n",
    )
    rcv_qualification.to_csv(
        output / "rcv-feature-landmark-qualification.csv",
        index=False,
        lineterminator="\n",
    )
    hazard_cells.to_csv(
        output / "hazard-cell-evaluation.csv",
        index=False,
        lineterminator="\n",
    )
    hazard_qualification.to_csv(
        output / "hazard-feature-landmark-qualification.csv",
        index=False,
        lineterminator="\n",
    )
    governor_attr.to_csv(
        output / "governor-descriptive-attribution.csv",
        index=False,
        lineterminator="\n",
    )

    freeze = {
        "schema_version": ("rd41-p4-qualified-continuous-evidence-freeze-v1"),
        "status": "PASS",
        "decision": decision,
        "next_stage": next_stage,
        "qualified_rcv_feature_landmark_pairs": qualified_rcv_pairs,
        "qualified_hazard_feature_landmark_pairs": qualified_hazard_pairs,
        "qualified_rcv_pair_count": len(qualified_rcv_pairs),
        "qualified_hazard_pair_count": len(qualified_hazard_pairs),
        "all_qualifying_pairs_advance": True,
        "best_feature_selection_used": False,
        "best_landmark_selection_used": False,
        "failed_channel_rescue_used": False,
        "governor_selection_used": False,
        "parameter_search_used": False,
        "threshold_optimization_used": False,
        "economic_action_executed": False,
        "production_authorized": False,
    }
    write_json(
        output / "qualified-continuous-evidence-freeze.json",
        freeze,
    )

    report = {
        "schema_version": ("rd41-p4-remaining-control-value-terminal-hazard-diagnostic-report-v1"),
        "stage": ("RD41_P4_REMAINING_CONTROL_VALUE_TERMINAL_HAZARD_CONTINUOUS_CHANNEL_DIAGNOSTIC"),
        "status": "PASS",
        "runner_freeze_commit": expected_freeze_commit,
        "source_p3_freeze_commit": P3_FREEZE,
        "lineage": lineage,
        "full_control_position_count": int(len(risk)),
        "target_decision_count": int(len(targets)),
        "feature_row_count": int(len(features)),
        "target_count_parity_pass": bool(target_parity["parity_pass"].all()),
        "governor_count_parity_pass": bool(governor_parity["parity_pass"].all()),
        "hazard_label_parity_pass": True,
        "qualified_rcv_feature_landmark_pairs": qualified_rcv_pairs,
        "qualified_hazard_feature_landmark_pairs": qualified_hazard_pairs,
        "rcv_qualification": compact_qualification(rcv_qualification),
        "hazard_qualification": compact_qualification(hazard_qualification),
        "decision": decision,
        "next_stage": next_stage,
        "right_censored_position_count": 0,
        "governor_selection_eligible": False,
        "best_feature_selection_used": False,
        "best_landmark_selection_used": False,
        "failed_channel_rescue_used": False,
        "parameter_search_used": False,
        "threshold_optimization_used": False,
        "economic_action_executed": False,
        "full_liquidation_performed": False,
        "partial_derisk_performed": False,
        "portfolio_replay_performed": False,
        "capital_reuse_performed": False,
        "2024_accessed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
    }
    write_json(
        output / "rd41-p4-remaining-control-value-terminal-hazard-diagnostic-report-v1.json",
        report,
    )

    files = {}
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
            "schema_version": "rd41-p4-output-manifest-v1",
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
        raise RunnerError("RD41-P4 runtime missing")

    expected = sorted((*OUTPUT_NAMES, "output-manifest.json"))
    observed = sorted(path.name for path in output.iterdir() if path.is_file())
    if observed != expected:
        raise RunnerError(f"RD41-P4 output registry drift: {observed} != {expected}")

    report = load_json(
        output / "rd41-p4-remaining-control-value-terminal-hazard-diagnostic-report-v1.json"
    )
    freeze = load_json(output / "qualified-continuous-evidence-freeze.json")
    targets = pd.read_csv(
        output / "target-ledger.csv",
        low_memory=False,
    )
    features = pd.read_csv(
        output / "feature-ledger.csv",
        low_memory=False,
    )
    rcv_cells = pd.read_csv(
        output / "rcv-cell-evaluation.csv",
        low_memory=False,
    )
    rcv_q = pd.read_csv(
        output / "rcv-feature-landmark-qualification.csv",
        low_memory=False,
    )
    hazard_cells = pd.read_csv(
        output / "hazard-cell-evaluation.csv",
        low_memory=False,
    )
    hazard_q = pd.read_csv(
        output / "hazard-feature-landmark-qualification.csv",
        low_memory=False,
    )
    governor = pd.read_csv(
        output / "governor-descriptive-attribution.csv",
        low_memory=False,
    )

    if len(rcv_cells) != 108:
        raise RunnerError("RCV cell table must contain 108 rows")
    if len(rcv_q) != 18:
        raise RunnerError("RCV qualification must contain 18 rows")
    if len(hazard_cells) != 36:
        raise RunnerError("hazard cell table must contain 36 rows")
    if len(hazard_q) != 6:
        raise RunnerError("hazard qualification must contain 6 rows")
    if len(governor) != 324:
        raise RunnerError("governor attribution must contain 324 rows")
    if len(features) != len(targets) * len(FEATURES):
        raise RunnerError("feature/target cardinality mismatch")
    if not bool(targets["target_evaluable"].astype(bool).all()):
        raise RunnerError("unexpected target unevaluability")
    if bool(targets["right_censored"].astype(bool).any()):
        raise RunnerError("P4 unexpectedly contains censored target")

    qualified_rcv = [
        {
            "feature_id": str(row["feature_id"]),
            "landmark_age_hours": int(row["landmark_age_hours"]),
        }
        for row in rcv_q.loc[rcv_q["qualified"].astype(bool)][
            ["feature_id", "landmark_age_hours"]
        ].to_dict(orient="records")
    ]
    qualified_hazard = [
        {
            "feature_id": str(row["feature_id"]),
            "landmark_age_hours": int(row["landmark_age_hours"]),
        }
        for row in hazard_q.loc[hazard_q["qualified"].astype(bool)][
            ["feature_id", "landmark_age_hours"]
        ].to_dict(orient="records")
    ]

    success = bool(qualified_rcv or qualified_hazard)
    expected_decision = SUCCESS_DECISION if success else FAILURE_DECISION
    expected_next = SUCCESS_NEXT if success else FAILURE_NEXT

    if report.get("decision") != expected_decision:
        raise RunnerError("report decision mismatch")
    if report.get("next_stage") != expected_next:
        raise RunnerError("report next-stage mismatch")
    if report.get("qualified_rcv_feature_landmark_pairs") != qualified_rcv:
        raise RunnerError("report RCV qualified-pair mismatch")
    if report.get("qualified_hazard_feature_landmark_pairs") != qualified_hazard:
        raise RunnerError("report hazard qualified-pair mismatch")
    if freeze.get("decision") != expected_decision:
        raise RunnerError("freeze decision mismatch")
    if freeze.get("qualified_rcv_feature_landmark_pairs") != qualified_rcv:
        raise RunnerError("freeze RCV qualified-pair mismatch")
    if freeze.get("qualified_hazard_feature_landmark_pairs") != qualified_hazard:
        raise RunnerError("freeze hazard qualified-pair mismatch")

    for field in (
        "best_feature_selection_used",
        "best_landmark_selection_used",
        "failed_channel_rescue_used",
        "parameter_search_used",
        "threshold_optimization_used",
        "economic_action_executed",
        "full_liquidation_performed",
        "partial_derisk_performed",
        "portfolio_replay_performed",
        "capital_reuse_performed",
        "2024_accessed",
        "post_2024_accessed",
        "production_authorized",
    ):
        if report.get(field) is not False:
            raise RunnerError(f"prohibited P4 flag: {field}")

    manifest = load_json(output / "output-manifest.json")
    if manifest.get("file_count") != len(OUTPUT_NAMES):
        raise RunnerError("manifest file count drifted")
    if manifest.get("decision") != expected_decision:
        raise RunnerError("manifest decision drifted")

    rcv_compact = []
    for row in rcv_q.to_dict(orient="records"):
        rcv_compact.append(
            {
                "feature_id": str(row["feature_id"]),
                "landmark_age_hours": int(row["landmark_age_hours"]),
                "q2022": int(row["qualified_universes_2022"]),
                "q2023": int(row["qualified_universes_2023"]),
                "r2022": int(row["reversed_universes_2022"]),
                "r2023": int(row["reversed_universes_2023"]),
                "qualified": bool(row["qualified"]),
                "regime_direction_reversal": bool(row["regime_direction_reversal"]),
            }
        )

    hazard_compact = []
    for row in hazard_q.to_dict(orient="records"):
        hazard_compact.append(
            {
                "feature_id": str(row["feature_id"]),
                "landmark_age_hours": int(row["landmark_age_hours"]),
                "q2022": int(row["qualified_universes_2022"]),
                "q2023": int(row["qualified_universes_2023"]),
                "r2022": int(row["reversed_universes_2022"]),
                "r2023": int(row["reversed_universes_2023"]),
                "qualified": bool(row["qualified"]),
                "regime_direction_reversal": bool(row["regime_direction_reversal"]),
            }
        )

    return {
        "status": "PASS",
        "decision": expected_decision,
        "next_stage": expected_next,
        "target_decision_count": int(len(targets)),
        "feature_row_count": int(len(features)),
        "qualified_rcv_feature_landmark_pairs": qualified_rcv,
        "qualified_hazard_feature_landmark_pairs": qualified_hazard,
        "rcv_feature_landmark_qualification": rcv_compact,
        "hazard_feature_landmark_qualification": hazard_compact,
        "target_count_parity_pass": bool(report["target_count_parity_pass"]),
        "governor_count_parity_pass": bool(report["governor_count_parity_pass"]),
        "hazard_label_parity_pass": bool(report["hazard_label_parity_pass"]),
        "best_feature_selection_used": False,
        "best_landmark_selection_used": False,
        "economic_action_executed": False,
        "2024_accessed": False,
        "production_authorized": False,
    }


def main() -> int:
    args = parser().parse_args()
    repo = args.repo_root.resolve()
    raw_root = (
        args.raw_root.resolve()
        if args.raw_root is not None
        else (repo / DEFAULT_RAW_ROOT).resolve()
    )
    if not (repo / ".git").exists():
        raise RunnerError(f"not a git repository: {repo}")
    if int(args.execute) + int(args.validate_only) != 1:
        raise RunnerError("choose exactly one runner mode")

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

    if not args.expected_freeze_commit:
        raise RunnerError("--expected-freeze-commit is required")

    print(
        json.dumps(
            execute(
                repo,
                raw_root,
                args.expected_freeze_commit,
            ),
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
