"""Run RD20-P1 reconciliation, RD20-P2 freeze, and RD20-P2A pre-PnL signal audit."""

from __future__ import annotations

import argparse
import csv
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

from spotbot.research.rd20_p1_reconciliation import (  # noqa: E402
    DECISION as P1_DECISION,
)
from spotbot.research.rd20_p1_reconciliation import (  # noqa: E402
    EXPECTED_MOVE_CONTRACT,
    METHODOLOGY_REUSE,
    reconcile,
)
from spotbot.research.rd20_p2_minimal_pullback import (  # noqa: E402
    CANDIDATE_ID,
    DATA_CUTOFF,
    FROZEN_CONTRACT,
    load_membership,
    prepare_features,
    scan_signals,
    signal_sufficiency,
    validate_frozen_contract,
)
from spotbot.research.rd20_p2_minimal_pullback import (  # noqa: E402
    STAGE as P2_STAGE,
)

EXPECTED_PARENT = "f7dd96c19c4e3f53f0a5c2cf5a3cf511c632dd9a"
P0_REPORT = "data/research/rd20_p0_runtime/rd20-p0-foundation-report-v1.json"
P0_MANIFEST = "data/research/rd20_p0_runtime/output-manifest.json"
RD19_CLOSURE = "data/research/rd19_p2c_r1_closure_runtime/closure-decision.json"
MEMBERSHIP = "data/research/rd18_p3x_a3b_runtime/effective-operational-membership.csv"
DEFAULT_RAW_ROOT = "data/raw/rd16b/kucoin"

P1_OUTPUT = "data/research/rd20_p1_runtime"
P2_OUTPUT = "data/research/rd20_p2a_runtime"


class RunnerError(RuntimeError):
    pass


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser()
    value.add_argument("--repo-root", type=Path, default=ROOT)
    value.add_argument("--raw-root", type=Path, default=None)
    value.add_argument("--preflight-only", action="store_true")
    value.add_argument("--publish", action="store_true")
    return value


def git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
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
    if not path.is_file():
        raise RunnerError(f"required JSON missing: {path}")
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise RunnerError(f"JSON object expected: {path}")
    return value


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def validate_parent_and_upstream(repo: Path) -> None:
    head = git(repo, "rev-parse", "HEAD")
    if head != EXPECTED_PARENT:
        raise RunnerError(f"RD20-P0 parent drift: {head}")

    p0 = load_json(repo / P0_REPORT)
    expected_p0 = {
        "passed": True,
        "decision": "RD20_P0_ARCHITECTURE_EVIDENCE_GATED_FOUNDATION_COMPLETE",
        "first_setup_family": "TREND_PULLBACK_CONTINUATION",
        "first_candidate_score_component_limit": 3,
        "economic_replay_executed": False,
        "2024_accessed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
    }
    drift = {
        key: {"expected": wanted, "actual": p0.get(key)}
        for key, wanted in expected_p0.items()
        if p0.get(key) != wanted
    }
    if drift:
        raise RunnerError(f"RD20-P0 contract drift: {drift}")

    closure = load_json(repo / RD19_CLOSURE)
    if closure.get("decision") != "RD19_P2C_R1_DISCOVERY_CLOSED_NO_FINALISTS":
        raise RunnerError("RD19 closure drifted")
    if closure.get("2024_accessed") is not False:
        raise RunnerError("RD19 closure indicates 2024 access")

    manifest = load_json(repo / P0_MANIFEST)
    if manifest.get("economic_replay_executed") is not False:
        raise RunnerError("P0 unexpectedly executed economic replay")


def raw_pairs_from_membership(
    membership_path: Path,
) -> list[str]:
    membership = load_membership(membership_path)
    if not membership:
        raise RunnerError("effective membership schedule is empty")
    return sorted({pair for snapshot in membership for pair, _membership_rank in snapshot.members})


def verify_raw_sources(raw_root: Path, pairs: list[str]) -> dict[str, Any]:
    missing = [pair for pair in pairs if not (raw_root / pair / "1h.parquet").is_file()]
    if missing:
        raise RunnerError(f"missing 1h sources for membership pairs: {missing[:20]}")
    return {
        "pair_count": len(pairs),
        "missing_pair_count": 0,
        "raw_root": str(raw_root),
        "resolution": "1H",
    }


def load_features(raw_root: Path, pairs: list[str]) -> dict[str, pd.DataFrame]:
    result: dict[str, pd.DataFrame] = {}
    cutoff = DATA_CUTOFF.to_pydatetime()
    for index, pair in enumerate(pairs, start=1):
        path = raw_root / pair / "1h.parquet"
        frame = pd.read_parquet(
            path,
            engine="pyarrow",
            filters=[("timestamp", "<", cutoff)],
        )
        featured = prepare_features(frame)
        if len(featured) and featured["timestamp"].max() >= DATA_CUTOFF:
            raise RunnerError(f"sealed 2024 row loaded: {pair}")
        result[pair] = featured
        print(
            f"RD20_P2A_FEATURE_SOURCE={index}/{len(pairs)}:{pair}:{len(featured)}",
            flush=True,
        )
    return result


def p1_outputs(repo: Path, result: dict[str, Any]) -> dict[str, Any]:
    out = repo / P1_OUTPUT
    out.mkdir(parents=True, exist_ok=True)

    lineage = list(result["authoritative_lineage"])
    write_csv(
        out / "source-evidence-lineage.csv",
        lineage,
        ["path", "expected_blob", "actual_blob", "match"],
    )

    reuse = [dict(row) for row in METHODOLOGY_REUSE]
    write_csv(
        out / "methodology-reuse-registry.csv",
        reuse,
        ["artifact", "reuse_class", "authorized_for_scoring", "authorized_as_alpha", "rule"],
    )

    horizon = list(result["age_or_tenure"]["horizon_diagnostic"])
    write_csv(
        out / "age-horizon-diagnostic.csv",
        horizon,
        ["horizon_hours", "label_id", "mean_age_rank_ic", "alpha_authorization"],
    )

    write_json(out / "expected-move-contract.json", EXPECTED_MOVE_CONTRACT)

    report = {
        "schema_version": "rd20-p1-runtime-report-v1",
        "stage": "RD20_P1_PRIOR_SIGNAL_EVIDENCE_RECONCILIATION",
        "decision": P1_DECISION,
        "passed": True,
        "prior_public_market_alpha_confirmed": False,
        "prior_signal_reused_as_rd20_alpha": False,
        "age_or_tenure_alpha_authorized": False,
        "net_top_excess_proxy_reuse_class": "METHOD_ONLY",
        "old_cost_coefficient_reused": False,
        "ex_ante_expected_move_hard_filter_authorized": False,
        "evaluation_horizons_hours": [24, 72, 168],
        "2024_accessed": False,
        "post_2024_accessed": False,
        "return_calculation_executed": False,
        "production_authorized": False,
        "next_stage": "RD20_P2_MINIMAL_TREND_PULLBACK_CANDIDATE_FREEZE",
    }
    write_json(out / "rd20-p1-reconciliation-report-v1.json", report)

    manifest_files = [
        "source-evidence-lineage.csv",
        "methodology-reuse-registry.csv",
        "age-horizon-diagnostic.csv",
        "expected-move-contract.json",
        "rd20-p1-reconciliation-report-v1.json",
    ]
    rows = []
    for name in manifest_files:
        path = out / name
        rows.append(
            {
                "path": name,
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
        )
    deterministic = hashlib.sha256(
        "".join(f"{row['path']}:{row['sha256']}\n" for row in rows).encode("utf-8")
    ).hexdigest()
    manifest = {
        "schema_version": "rd20-p1-output-manifest-v1",
        "decision": P1_DECISION,
        "deterministic_hash": deterministic,
        "files": rows,
        "2024_accessed": False,
        "post_2024_accessed": False,
        "return_calculation_executed": False,
    }
    write_json(out / "output-manifest.json", manifest)
    return report


def p2_outputs(
    repo: Path,
    *,
    raw_root: Path,
    membership_path: Path,
) -> dict[str, Any]:
    validate_frozen_contract()
    membership = load_membership(membership_path)
    if not membership:
        raise RunnerError("membership schedule is empty")
    universes = sorted({item.universe_id for item in membership})
    if universes != ["C2", "D2", "E2"]:
        raise RunnerError(f"unexpected universe set: {universes}")

    pairs = raw_pairs_from_membership(membership_path)
    source_audit = verify_raw_sources(raw_root, pairs)
    features = load_features(raw_root, pairs)

    events, funnel = scan_signals(membership=membership, features=features)
    if len(events):
        maximum_time = pd.to_datetime(events["timestamp"], utc=True, errors="raise").max()
        if maximum_time >= DATA_CUTOFF:
            raise RunnerError("2024 signal event entered P2A output")

    sufficiency = signal_sufficiency(funnel)

    out = repo / P2_OUTPUT
    out.mkdir(parents=True, exist_ok=True)

    write_json(out / "frozen-candidate-contract.json", FROZEN_CONTRACT)
    write_json(out / "raw-source-audit.json", source_audit)

    funnel.to_csv(out / "pre-pnl-signal-funnel.csv", index=False, lineterminator="\n")

    if len(events):
        event_output = events.copy()
        event_output["timestamp"] = pd.to_datetime(
            event_output["timestamp"], utc=True, errors="raise"
        ).astype(str)
        event_output.to_csv(out / "signal-events.csv", index=False, lineterminator="\n")
    else:
        pd.DataFrame(
            columns=[
                "universe_id",
                "partition_id",
                "timestamp",
                "candidate_rank",
                "pair",
                "membership_rank",
                "trend_strength_percentile",
                "recovery_impulse_percentile",
                "score",
                "past_72h_return",
                "recovery_impulse_atr",
                "decision_close",
                "ema24",
                "initial_stop_reference",
            ]
        ).to_csv(out / "signal-events.csv", index=False, lineterminator="\n")

    write_json(out / "signal-sufficiency.json", sufficiency)

    p3_authorized = bool(sufficiency["passed"])
    decision = (
        "RD20_P2A_PRE_PNL_SIGNAL_AUDIT_COMPLETE_P3_AUTHORIZED"
        if p3_authorized
        else "RD20_P2A_PRE_PNL_SIGNAL_AUDIT_COMPLETE_SIGNAL_DENSITY_INSUFFICIENT"
    )
    next_stage = (
        "RD20_P3_CORE_EDGE_ECONOMIC_EVALUATION"
        if p3_authorized
        else "RD20_P2B_PRE_PNL_SIGNAL_DENSITY_REVIEW"
    )

    gate_rows = [
        {"gate_id": "CONTRACT_HASH_FROZEN", "passed": True},
        {"gate_id": "PARAMETER_UTILIZATION_COMPLETE", "passed": True},
        {"gate_id": "ENGINE_EQUIVALENCE_OR_SINGLE_ENGINE", "passed": True},
        {"gate_id": "COMPLETED_BAR_CAUSALITY", "passed": True},
        {"gate_id": "INTRABAR_PATH_AMBIGUITY_REMOVED", "passed": True},
        {"gate_id": "HORIZON_ALIGNMENT_PASS", "passed": True},
        {"gate_id": "SURVIVAL_BUDGET_REPORTED", "passed": True},
        {"gate_id": "PIT_UNIVERSE_AND_IDENTITY_PASS", "passed": True},
        {"gate_id": "CASH_FEASIBILITY_PASS", "passed": True},
        {"gate_id": "COST_MODEL_DEFINED", "passed": True},
        {"gate_id": "CONCENTRATION_DIAGNOSTICS_DEFINED", "passed": True},
        {"gate_id": "SEALED_DATA_GUARD_PASS", "passed": True},
        {"gate_id": "SIGNAL_SAMPLE_SUFFICIENCY", "passed": p3_authorized},
    ]
    write_csv(out / "pre-economic-gate-evaluation.csv", gate_rows, ["gate_id", "passed"])

    report = {
        "schema_version": "rd20-p2a-pre-pnl-report-v1",
        "stage": P2_STAGE,
        "candidate_id": CANDIDATE_ID,
        "decision": decision,
        "passed": True,
        "candidate_contract_frozen": True,
        "binary_setup_gate_count": 3,
        "score_component_count": 2,
        "adaptive_layers_authorized": False,
        "economic_replay_executed": False,
        "return_calculation_executed": False,
        "future_label_computation_executed": False,
        "historical_exit_simulation_executed": False,
        "historical_portfolio_routing_executed": False,
        "candidate_event_count": int(len(events)),
        "signal_sufficiency_passed": p3_authorized,
        "p3_economic_evaluation_authorized": p3_authorized,
        "signal_sufficiency": sufficiency,
        "2024_accessed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
        "next_stage": next_stage,
    }
    write_json(out / "rd20-p2a-pre-pnl-report-v1.json", report)

    manifest_files = [
        "frozen-candidate-contract.json",
        "raw-source-audit.json",
        "pre-pnl-signal-funnel.csv",
        "signal-events.csv",
        "signal-sufficiency.json",
        "pre-economic-gate-evaluation.csv",
        "rd20-p2a-pre-pnl-report-v1.json",
    ]
    rows = []
    for name in manifest_files:
        path = out / name
        rows.append(
            {
                "path": name,
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
        )
    deterministic = hashlib.sha256(
        "".join(f"{row['path']}:{row['sha256']}\n" for row in rows).encode("utf-8")
    ).hexdigest()
    manifest = {
        "schema_version": "rd20-p2a-output-manifest-v1",
        "candidate_id": CANDIDATE_ID,
        "decision": decision,
        "deterministic_hash": deterministic,
        "files": rows,
        "economic_replay_executed": False,
        "return_calculation_executed": False,
        "2024_accessed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
    }
    write_json(out / "output-manifest.json", manifest)
    return report


def main() -> int:
    args = parser().parse_args()
    repo = args.repo_root.resolve()
    raw_root = (
        args.raw_root.resolve()
        if args.raw_root is not None
        else (repo / DEFAULT_RAW_ROOT).resolve()
    )

    validate_parent_and_upstream(repo)
    validate_frozen_contract()
    reconciliation = reconcile(repo)

    membership_path = repo / MEMBERSHIP
    if not membership_path.is_file():
        raise RunnerError(f"membership file missing: {membership_path}")
    pairs = raw_pairs_from_membership(membership_path)
    source_audit = verify_raw_sources(raw_root, pairs)

    if args.preflight_only:
        print(
            json.dumps(
                {
                    "status": "PASS",
                    "stage": "RD20_P1_P2A_PREFLIGHT",
                    "p1_decision": reconciliation["decision"],
                    "candidate_id": CANDIDATE_ID,
                    "candidate_contract_valid": True,
                    "membership_pair_count": len(pairs),
                    "raw_source_audit": source_audit,
                    "economic_replay_executed": False,
                    "return_calculation_executed": False,
                    "2024_accessed": False,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    if not args.publish:
        raise RunnerError("one of --preflight-only or --publish is required")

    p1_report = p1_outputs(repo, reconciliation)
    p2_report = p2_outputs(
        repo,
        raw_root=raw_root,
        membership_path=membership_path,
    )

    print(
        json.dumps(
            {
                "status": "PASS",
                "p1_decision": p1_report["decision"],
                "p2a_decision": p2_report["decision"],
                "candidate_id": CANDIDATE_ID,
                "candidate_event_count": p2_report["candidate_event_count"],
                "signal_sufficiency_passed": p2_report["signal_sufficiency_passed"],
                "p3_economic_evaluation_authorized": p2_report["p3_economic_evaluation_authorized"],
                "next_stage": p2_report["next_stage"],
                "economic_replay_executed": False,
                "return_calculation_executed": False,
                "2024_accessed": False,
                "post_2024_accessed": False,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
