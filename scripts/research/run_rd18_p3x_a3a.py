from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from spotbot.research.rd18_p3x_a3a_membership import (  # noqa: E402
    apply_hysteresis,
    build_replacement_ledger,
    coverage_fraction,
    historical_gap_rows,
    inventory_maps,
    materialize_committed_membership,
    normalize_ranking,
)

STAGE = "RD18_P3X_A3A_CANONICAL_MEMBERSHIP_BUILD"
NEXT_STAGE = "RD18_P3X_A3B_CONTROL_AND_COMPLETED_BAR_AUDIT_AUTHORIZATION"

INPUT_NAMES = (
    "c2-operational-membership.csv",
    "d2-operational-membership.csv",
    "e2-operational-membership.csv",
    "legacy-six-asset-control-parity.json",
    "selected-member-evaluation-coverage.json",
    "historical-gap-membership-resolution.json",
    "omission-replacement-readiness.json",
)


class A3ARunnerError(RuntimeError):
    """Raised when A3A inputs cannot be materialized safely."""


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    result.add_argument("--repo-root", type=Path, default=ROOT)
    result.add_argument(
        "--a1-runtime",
        type=Path,
        default=ROOT / "data/research/rd18_p3x_a1_runtime",
    )
    result.add_argument(
        "--a2-runtime",
        type=Path,
        default=ROOT / "data/research/rd18_p3x_a2_runtime",
    )
    result.add_argument(
        "--input-dir",
        type=Path,
        default=ROOT / "data/research/rd18_p3x_a3_inputs",
    )
    result.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "data/research/rd18_p3x_a3a_runtime",
    )
    result.add_argument("--preflight-only", action="store_true")
    result.add_argument("--write-inputs", action="store_true")
    return result


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise A3ARunnerError(f"required JSON is missing: {path}")
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise A3ARunnerError(f"JSON object expected: {path}")
    return value


def write_json(path: Path, value: object) -> None:
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


def write_csv(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(
        path,
        index=False,
        encoding="utf-8",
        lineterminator="\n",
    )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def merge_committed_rank(
    committed: pd.DataFrame,
    ranking: pd.DataFrame,
) -> pd.DataFrame:
    time_column = "decision_time"
    canonical_column = (
        "canonical_asset_id"
        if "canonical_asset_id" in committed.columns
        else "canonical_product_id"
    )
    working = committed.copy()
    working[time_column] = pd.to_datetime(
        working[time_column],
        utc=True,
        errors="raise",
    )
    working[canonical_column] = working[canonical_column].astype(str).str.strip()
    rank_lookup = ranking.loc[
        :,
        ["decision_time", "canonical_asset_id", "rank"],
    ].copy()
    merged = working.merge(
        rank_lookup,
        left_on=[time_column, canonical_column],
        right_on=["decision_time", "canonical_asset_id"],
        how="left",
        validate="many_to_one",
    )
    if merged["rank"].isna().any():
        missing = merged.loc[
            merged["rank"].isna(),
            [time_column, canonical_column],
        ].head(20)
        raise A3ARunnerError(
            "committed C2 membership rows lack ranking matches: "
            + missing.to_json(orient="records", date_format="iso")
        )
    return merged


def membership_decision_count(frame: pd.DataFrame) -> int:
    return int(
        pd.to_datetime(
            frame["decision_time"],
            utc=True,
            errors="raise",
        ).nunique()
    )


def source_hashes(repo: Path) -> dict[str, str]:
    paths = {
        "c2_hysteresis": ("data/research/rd18_p1r2/corrected-hysteresis.csv"),
        "c2_rankings": ("data/research/rd18_p1r2/corrected-weekly-rankings.csv"),
        "inventory": ("data/research/rd18_p1r2/raw-inventory-classification.csv"),
        "e2_hysteresis": ("data/research/rd18_p2u2/e10-hysteresis.csv"),
        "e2_rankings": ("data/research/rd18_p2u2/weekly-e10-ranking.csv"),
        "frozen_candidate": ("data/research/rd18_p3r/frozen-strategy-candidate.json"),
    }
    result: dict[str, str] = {}
    for name, relative in paths.items():
        path = repo / relative
        if not path.is_file():
            raise A3ARunnerError(f"required source missing: {path}")
        result[name] = sha256(path)
    return result


def output_manifest(
    base: Path,
    names: list[str],
) -> dict[str, object]:
    rows: list[dict[str, object]] = []
    aggregate = hashlib.sha256()
    for name in sorted(names):
        path = base / name
        digest = sha256(path)
        rows.append(
            {
                "path": name,
                "bytes": path.stat().st_size,
                "sha256": digest,
            }
        )
        aggregate.update(name.encode("utf-8"))
        aggregate.update(b"\0")
        aggregate.update(digest.encode("ascii"))
        aggregate.update(b"\n")
    return {
        "schema_version": "rd18-p3x-a3a-output-manifest-v1",
        "files": rows,
        "deterministic_hash": aggregate.hexdigest(),
        "network_requests": 0,
        "strategy_replay_executed": False,
        "return_calculation_executed": False,
        "post_2024_accessed": False,
    }


def build(
    repo: Path,
    a1_runtime: Path,
    a2_runtime: Path,
) -> dict[str, object]:
    inventory = pd.read_csv(
        repo / "data/research/rd18_p1r2/raw-inventory-classification.csv",
        low_memory=False,
    )
    mapping, c2_pairs, d2_pairs = inventory_maps(inventory)

    c2_source = pd.read_csv(
        repo / "data/research/rd18_p1r2/corrected-hysteresis.csv",
        low_memory=False,
    )
    c2_ranking_source = pd.read_csv(
        repo / "data/research/rd18_p1r2/corrected-weekly-rankings.csv",
        low_memory=False,
    )
    c2_ranking = normalize_ranking(
        c2_ranking_source,
        mapping=mapping,
        universe_id="C2",
        allowed_pairs=c2_pairs,
        recompute_rank=False,
        include_warmup=True,
    )

    c2_committed = merge_committed_rank(
        c2_source,
        c2_ranking,
    )
    c2 = materialize_committed_membership(
        c2_committed,
        mapping=mapping,
        universe_id="C2",
        source=("RD18_P1R2_CORRECTED_COMMITTED_TOP6_TOP8_HYSTERESIS"),
    )
    c2_rebuilt = apply_hysteresis(
        c2_ranking,
        universe_id="C2",
        source="RD18_P1R2_RANKING_REBUILD",
    )
    c2_keys = set(
        zip(
            c2.membership["decision_time"].astype(str),
            c2.membership["pair"].astype(str),
            strict=True,
        )
    )
    rebuilt_keys = set(
        zip(
            c2_rebuilt.membership["decision_time"].astype(str),
            c2_rebuilt.membership["pair"].astype(str),
            strict=True,
        )
    )
    if c2_keys != rebuilt_keys:
        raise A3ARunnerError("C2 committed hysteresis does not reproduce from rankings")

    d2_ranking = normalize_ranking(
        c2_ranking_source,
        mapping=mapping,
        universe_id="D2",
        allowed_pairs=d2_pairs,
        recompute_rank=True,
    )
    d2 = apply_hysteresis(
        d2_ranking,
        universe_id="D2",
        source=("RD18_P1R2_CORRECTED_RANKING_FILTERED_TO_RD18_P2R2_EVIDENCE_STRONG_INVENTORY"),
    )

    e2_source = pd.read_csv(
        repo / "data/research/rd18_p2u2/e10-hysteresis.csv",
        low_memory=False,
    )
    e2_ranking_source = pd.read_csv(
        repo / "data/research/rd18_p2u2/weekly-e10-ranking.csv",
        low_memory=False,
    )
    e2_ranking = normalize_ranking(
        e2_ranking_source,
        mapping=mapping,
        universe_id="E2",
        allowed_pairs=c2_pairs,
        recompute_rank=False,
    )
    e2 = materialize_committed_membership(
        e2_source,
        mapping=mapping,
        universe_id="E2",
        source="RD18_P2U2_COMMITTED_E10_TOP6_TOP8_HYSTERESIS",
    )

    memberships = pd.concat(
        [c2.membership, d2.membership, e2.membership],
        ignore_index=True,
    )
    rankings = pd.concat(
        [c2.ranking, d2.ranking, e2_ranking],
        ignore_index=True,
    )

    a1_plan = pd.read_csv(
        a1_runtime / "full-c2-hourly-acquisition-plan.csv",
        low_memory=False,
    )
    actions = a1_plan["action"].astype(str)
    ready_pairs = frozenset(a1_plan.loc[actions == "READY_LOCAL", "pair"].astype(str).tolist())
    historical_pairs = frozenset(
        a1_plan.loc[
            actions.isin(
                {
                    "NETWORK_MARKET_PROBE_REQUIRED",
                    "HISTORICAL_MARKET_SOURCE_REQUIRED",
                }
            ),
            "pair",
        ]
        .astype(str)
        .tolist()
    )
    corporate_pairs = frozenset(
        a1_plan.loc[
            actions == "CORPORATE_ACTION_POLICY_REQUIRED",
            "pair",
        ]
        .astype(str)
        .tolist()
    )
    if len(ready_pairs) != 341:
        raise A3ARunnerError(f"expected 341 READY_LOCAL pairs, found {len(ready_pairs)}")
    if len(historical_pairs) != 21:
        raise A3ARunnerError(f"expected 21 historical-source pairs, found {len(historical_pairs)}")
    if len(corporate_pairs) != 2:
        raise A3ARunnerError(f"expected 2 corporate-action pairs, found {len(corporate_pairs)}")

    symbol_summary = pd.read_csv(
        a2_runtime / "symbol-generation-summary.csv",
        low_memory=False,
    )
    generated_pairs = frozenset(
        symbol_summary.loc[
            symbol_summary["generation_status"].astype(str) == "GENERATED",
            "pair",
        ]
        .astype(str)
        .tolist()
    )
    if len(generated_pairs) != 339:
        raise A3ARunnerError(f"expected 339 generated A2 pairs, found {len(generated_pairs)}")

    top6_fraction, covered_slots, total_slots = coverage_fraction(
        memberships,
        generated_pairs=generated_pairs,
    )
    replacement = build_replacement_ledger(
        memberships,
        rankings,
        ready_pairs=ready_pairs,
        excluded_pairs=corporate_pairs,
    )
    replacement_ready = bool(replacement["replacement_ready"].astype(bool).all())
    gap_frame = historical_gap_rows(
        memberships,
        historical_pairs=historical_pairs,
    )
    gaps_complete = gap_frame.empty

    frozen = load_json(repo / "data/research/rd18_p3r/frozen-strategy-candidate.json")
    immutable = frozen.get("immutable_hashes")
    if not isinstance(immutable, dict):
        raise A3ARunnerError("frozen candidate immutable hashes are missing")

    control = {
        "schema_version": ("rd18-p3x-a3a-legacy-control-parity-v1"),
        "status": "CONTROL_ONLY_REPLAY_NOT_EXECUTED",
        "candidate_hash_match": False,
        "evaluated_hash_match": False,
        "trade_hash_match": False,
        "reference_candidate_count": 688,
        "reference_trade_count": 567,
        "reference_hashes": {
            "candidates_content_sha256": immutable.get("candidates_content_sha256"),
            "evaluated_content_sha256": immutable.get("evaluated_content_sha256"),
            "trades_content_sha256": immutable.get("trades_content_sha256"),
        },
        "reason": (
            "Exact trade-ledger parity requires a bounded six-asset "
            "control replay. A3A membership materialization does not "
            "misclassify that operation as no-replay."
        ),
        "control_only_replay_authorization_required": True,
        "strategy_replay_executed": False,
        "return_calculation_executed": False,
    }
    coverage = {
        "schema_version": ("rd18-p3x-a3a-selected-member-coverage-v1"),
        "full_top6_candidate_coverage_fraction": top6_fraction,
        "covered_top6_membership_slots": covered_slots,
        "total_top6_membership_slots": total_slots,
        "member_evaluation_audit_coverage": 0.0,
        "member_evaluation_audit_status": ("COMPLETED_BAR_NO_SIGNAL_AUDIT_NOT_MATERIALIZED"),
        "reason": (
            "A2 validates pre-router signal rows, not every completed "
            "signal bar for every operational member."
        ),
    }
    gap_resolution = {
        "schema_version": ("rd18-p3x-a3a-historical-gap-resolution-v1"),
        "complete": gaps_complete,
        "historical_pair_count": len(historical_pairs),
        "affected_pair_universe_rows": len(gap_frame),
        "affected_pairs": sorted(gap_frame["pair"].astype(str).unique().tolist())
        if not gap_frame.empty
        else [],
        "policy": (
            "Complete only when no historical-source pair enters any "
            "canonical operational membership."
        ),
    }
    omission = {
        "schema_version": ("rd18-p3x-a3a-omission-replacement-readiness-v1"),
        "ready": replacement_ready,
        "replacement_rows": len(replacement),
        "unready_rows": int((~replacement["replacement_ready"].astype(bool)).sum()),
        "named_omissions": ["BCHSV-USDT", "PEPE-USDT"],
        "policy": (
            "Highest-ranked READY_LOCAL nonmember at the same decision "
            "is the deterministic single-asset replacement."
        ),
    }

    return {
        "memberships": {
            "C2": c2.membership,
            "D2": d2.membership,
            "E2": e2.membership,
        },
        "rankings": rankings,
        "replacement": replacement,
        "gap_frame": gap_frame,
        "control": control,
        "coverage": coverage,
        "gap_resolution": gap_resolution,
        "omission": omission,
        "report": {
            "schema_version": "rd18-p3x-a3a-runtime-report-v1",
            "stage": STAGE,
            "passed": True,
            "membership_decisions": {
                "C2": membership_decision_count(c2.membership),
                "D2": membership_decision_count(d2.membership),
                "E2": membership_decision_count(e2.membership),
            },
            "membership_rows": {
                "C2": len(c2.membership),
                "D2": len(d2.membership),
                "E2": len(e2.membership),
            },
            "full_top6_candidate_coverage_fraction": top6_fraction,
            "member_evaluation_audit_coverage": 0.0,
            "historical_gap_resolution_complete": gaps_complete,
            "omission_replacement_ready": replacement_ready,
            "control_parity_executed": False,
            "next_stage": NEXT_STAGE,
            "source_hashes": source_hashes(repo),
            "network_requests": 0,
            "strategy_replay_executed": False,
            "return_calculation_executed": False,
            "post_2024_accessed": False,
        },
    }


def main() -> int:
    args = parser().parse_args()
    if not args.preflight_only and not args.write_inputs:
        raise SystemExit("A3A requires --write-inputs")

    repo = args.repo_root.resolve()
    built = build(
        repo,
        args.a1_runtime.resolve(),
        args.a2_runtime.resolve(),
    )
    report = built["report"]
    assert isinstance(report, dict)
    if args.preflight_only:
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0

    input_dir = args.input_dir.resolve()
    output_dir = args.output_dir.resolve()
    input_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    memberships = built["memberships"]
    assert isinstance(memberships, dict)
    write_csv(
        input_dir / "c2-operational-membership.csv",
        memberships["C2"],
    )
    write_csv(
        input_dir / "d2-operational-membership.csv",
        memberships["D2"],
    )
    write_csv(
        input_dir / "e2-operational-membership.csv",
        memberships["E2"],
    )
    for name, key in (
        ("legacy-six-asset-control-parity.json", "control"),
        (
            "selected-member-evaluation-coverage.json",
            "coverage",
        ),
        (
            "historical-gap-membership-resolution.json",
            "gap_resolution",
        ),
        (
            "omission-replacement-readiness.json",
            "omission",
        ),
    ):
        write_json(input_dir / name, built[key])

    replacement = built["replacement"]
    gap_frame = built["gap_frame"]
    assert isinstance(replacement, pd.DataFrame)
    assert isinstance(gap_frame, pd.DataFrame)
    write_csv(
        output_dir / "omission-replacement-ledger.csv",
        replacement,
    )
    write_csv(
        output_dir / "historical-gap-membership-ledger.csv",
        gap_frame,
    )
    write_json(
        output_dir / "rd18-p3x-a3a-runtime-report-v1.json",
        report,
    )

    input_manifest = output_manifest(
        input_dir,
        list(INPUT_NAMES),
    )
    write_json(input_dir / "output-manifest.json", input_manifest)
    runtime_manifest = output_manifest(
        output_dir,
        [
            "omission-replacement-ledger.csv",
            "historical-gap-membership-ledger.csv",
            "rd18-p3x-a3a-runtime-report-v1.json",
        ],
    )
    write_json(output_dir / "output-manifest.json", runtime_manifest)

    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
