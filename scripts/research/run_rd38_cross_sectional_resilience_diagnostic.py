from __future__ import annotations

import argparse
import hashlib
import importlib.util
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

from spotbot.research.rd38_cross_sectional_resilience import (  # noqa: E402
    DATA_CUTOFF,
    DATA_START,
    FAILURE_DECISION,
    FAILURE_NEXT,
    FAMILY_ORDER,
    PERIODS,
    PRIMARY_FAMILIES,
    RECLAIM_CONTROL,
    SOURCE_HISTORY_START,
    SUCCESS_DECISION,
    SUCCESS_NEXT,
    UNIVERSES,
    build_markout_ledger,
    events_from_state_rows,
    normalize_price_frame,
    price_lookup,
    qualification_tables,
    snapshot_state_rows,
    summarize_markouts,
    utc,
    validate_constants,
)

P1B_FREEZE_COMMIT = "497ac1cd79f703d461894e77bfbf7dc0200f3033"
ORIGINAL_P2_FREEZE_COMMIT = "3e6cef3c3580fd9d00d4a4c1842f9de8c9a8c807"
P1_FREEZE_COMMIT = "0f7818c6d2794275be0109403e1410b410ce3d52"

P1_PROTOCOL = Path(
    "data/research/rd38_p1/"
    "rd38-p1-kucoin-native-cross-sectional-resilience-"
    "information-source-preregistration-v1.json"
)
P1_PROTOCOL_SHA256 = "2d9875180b0d21e113e8c136ad787298d4a4b6423d8f3ec6a10c5e2a17e0c313"
P1_PROTOCOL_BLOB = "17e38ddf8c693d7d634be4df7166b40dbf440549"

P1B_AMENDMENT = Path(
    "data/research/rd38_p1b/rd38-p1b-cross-sectional-cardinality-contract-amendment-v1.json"
)
P1B_AMENDMENT_SHA256 = "177455ce5fca1a6e2606b0c13ce234eb03d4ee7d20096c593f888ebee0496fe7"
P1B_AMENDMENT_BLOB = "dd50699f894045699249ca0a8be4f69e2acec803"

P1B_AUDIT = Path("data/research/rd38_p1b/rd38-p1b-amendment-audit-v1.json")
P1B_AUDIT_BLOB = "2d4ef0a3a5b2acf48158cb63ad6793ffd15026ba"

MEMBERSHIP = Path("data/research/rd18_p3x_a3b_runtime/effective-operational-membership.csv")
MEMBERSHIP_SHA256 = "f7d6012ce8cd691583b9b6276ddf36371bfe0bbd9b28f810b676ad0177fb559e"
MEMBERSHIP_LOADER = Path("src/spotbot/research/rd20_p2_minimal_pullback.py")
MEMBERSHIP_LOADER_BLOB = "904a02ccec3db8c2c23a30200ba63a3a84cb4524"

KUCOIN_ROOT = Path("data/raw/rd16b/kucoin")
OUTPUT = Path("data/research/rd38_p2_runtime")

OUTPUT_NAMES = (
    "input-and-conformance-audit.json",
    "cross-sectional-hour-summary.csv",
    "event-ledger.csv",
    "event-summary.csv",
    "target-markout-ledger.csv",
    "target-markout-summary.csv",
    "qualification-evaluation.csv",
    "family-qualification.csv",
    "positive-control-evaluation.csv",
    "qualified-resilience-states-freeze.json",
    "rd38-p2-cross-sectional-resilience-diagnostic-report-v1.json",
)


class RunnerError(RuntimeError):
    pass


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser()
    value.add_argument(
        "--repo-root",
        type=Path,
        required=True,
    )
    value.add_argument(
        "--execute",
        action="store_true",
    )
    value.add_argument(
        "--validate-only",
        action="store_true",
    )
    value.add_argument(
        "--expected-freeze-commit",
        default=None,
    )
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


def load_json(
    path: Path,
) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise RunnerError(f"JSON object expected: {path}")
    return value


def write_json(
    path: Path,
    value: Any,
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
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
    actual = git(
        repo,
        "rev-parse",
        f"HEAD:{path.as_posix()}",
    )
    if actual != expected:
        raise RunnerError(f"{label} blob drift: {actual} != {expected}")


def verify_lineage(
    repo: Path,
    expected_freeze_commit: str,
) -> dict[str, Any]:
    if git(
        repo,
        "diff",
        "--cached",
        "--name-only",
        "--",
    ):
        raise RunnerError("staged tracked changes before P2")
    if git(
        repo,
        "diff",
        "--name-only",
        "--",
    ):
        raise RunnerError("unstaged tracked changes before P2")

    head = git(
        repo,
        "rev-parse",
        "HEAD",
    )
    if head != expected_freeze_commit:
        raise RunnerError(f"P2 HEAD {head} != freeze {expected_freeze_commit}")
    if (
        git(
            repo,
            "rev-parse",
            "HEAD^",
        )
        != ORIGINAL_P2_FREEZE_COMMIT
    ):
        raise RunnerError("P2 recovery-freeze parent is not original P2 freeze")

    for path, blob, label in (
        (
            P1_PROTOCOL,
            P1_PROTOCOL_BLOB,
            "P1 protocol",
        ),
        (
            P1B_AMENDMENT,
            P1B_AMENDMENT_BLOB,
            "P1B amendment",
        ),
        (
            P1B_AUDIT,
            P1B_AUDIT_BLOB,
            "P1B audit",
        ),
        (
            MEMBERSHIP_LOADER,
            MEMBERSHIP_LOADER_BLOB,
            "membership loader",
        ),
    ):
        verify_blob(
            repo,
            path,
            blob,
            label,
        )

    if sha256(repo / P1_PROTOCOL) != P1_PROTOCOL_SHA256:
        raise RunnerError("P1 protocol SHA drifted")
    if sha256(repo / P1B_AMENDMENT) != P1B_AMENDMENT_SHA256:
        raise RunnerError("P1B amendment SHA drifted")
    if not (repo / MEMBERSHIP).is_file():
        raise RunnerError(f"PIT membership missing: {MEMBERSHIP}")
    if sha256(repo / MEMBERSHIP) != MEMBERSHIP_SHA256:
        raise RunnerError("PIT membership SHA drifted")

    protocol = load_json(repo / P1_PROTOCOL)
    amendment = load_json(repo / P1B_AMENDMENT)
    if protocol.get("status") != ("FROZEN_PRE_DATA_DIAGNOSTIC"):
        raise RunnerError("P1 protocol not frozen")
    if amendment.get("status") != ("FROZEN_PRE_DATA_DIAGNOSTIC_AMENDMENT"):
        raise RunnerError("P1B amendment not frozen")
    if (
        amendment.get(
            "effective_amendment",
            {},
        ).get("missing_data_semantics.minimum_valid_cross_section_members")
        != 6
    ):
        raise RunnerError("P1B effective cardinality drifted")
    if (
        amendment.get(
            "effective_amendment",
            {},
        ).get("partial_cross_section_ranking")
        != "FORBIDDEN"
    ):
        raise RunnerError("P1B partial-ranking rule drifted")

    validate_constants()
    return {
        "runner_freeze_commit": (expected_freeze_commit),
        "p1b_freeze_commit": (P1B_FREEZE_COMMIT),
        "p1_freeze_commit": (P1_FREEZE_COMMIT),
        "p1_protocol_sha256": (P1_PROTOCOL_SHA256),
        "p1b_amendment_sha256": (P1B_AMENDMENT_SHA256),
        "membership_sha256": (MEMBERSHIP_SHA256),
        "membership_loader_git_blob": (MEMBERSHIP_LOADER_BLOB),
    }


def load_membership_loader(
    repo: Path,
) -> Any:
    path = repo / MEMBERSHIP_LOADER
    spec = importlib.util.spec_from_file_location(
        "_rd20_membership_for_rd38",
        path,
    )
    if spec is None or spec.loader is None:
        raise RunnerError("cannot load frozen membership loader")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(spec.name, None)
        raise
    return module


def selected_snapshots(
    module: Any,
    repo: Path,
) -> list[Any]:
    snapshots = module.load_membership(repo / MEMBERSHIP)
    selected: list[Any] = []
    for snapshot in snapshots:
        if str(snapshot.universe_id) not in UNIVERSES:
            continue
        start = utc(snapshot.decision_time)
        end = utc(snapshot.effective_end)
        if end <= DATA_START or start >= DATA_CUTOFF:
            continue
        if len(snapshot.members) != 6:
            raise RunnerError("selected PIT snapshot does not have six members")
        selected.append(snapshot)

    if not selected:
        raise RunnerError("no PIT snapshots overlap P2")

    for universe in UNIVERSES:
        count = sum(str(snapshot.universe_id) == universe for snapshot in selected)
        if count == 0:
            raise RunnerError(f"no snapshots for {universe}")
    return selected


def required_pairs(
    snapshots: list[Any],
) -> list[str]:
    pairs: set[str] = set()
    for snapshot in snapshots:
        for pair, _rank in snapshot.members:
            pairs.add(str(pair))
    if not pairs:
        raise RunnerError("PIT membership produced no pairs")
    return sorted(pairs)


def load_prices(
    repo: Path,
    pairs: list[str],
) -> dict[
    str,
    dict[int, tuple[float, float]],
]:
    start = SOURCE_HISTORY_START.to_pydatetime()
    cutoff = DATA_CUTOFF.to_pydatetime()
    lookups: dict[
        str,
        dict[int, tuple[float, float]],
    ] = {}

    for index, pair in enumerate(
        pairs,
        start=1,
    ):
        path = repo / KUCOIN_ROOT / pair / "1h.parquet"
        if not path.is_file():
            raise RunnerError(f"KuCoin source missing: {path}")

        raw = pd.read_parquet(
            path,
            columns=[
                "timestamp",
                "open",
                "close",
            ],
            engine="pyarrow",
            filters=[
                (
                    "timestamp",
                    ">=",
                    start,
                ),
                (
                    "timestamp",
                    "<",
                    cutoff,
                ),
            ],
        )
        frame = normalize_price_frame(
            raw,
            pair=pair,
        )
        lookups[pair] = price_lookup(frame)
        print(
            f"RD38_P2_SOURCE={index}/{len(pairs)}:{pair}:rows={len(frame)}",
            flush=True,
        )
    return lookups


def snapshot_hours(
    snapshot: Any,
) -> list[pd.Timestamp]:
    start = max(
        utc(snapshot.decision_time),
        DATA_START,
    )
    end = min(
        utc(snapshot.effective_end),
        DATA_CUTOFF,
    )
    if start >= end:
        return []
    if start != start.floor("h") or end != end.floor("h"):
        raise RunnerError("membership boundary not hourly")
    return list(
        pd.date_range(
            start,
            end - pd.Timedelta(hours=1),
            freq="h",
            tz="UTC",
        )
    )


def build_states(
    snapshots: list[Any],
    lookups: dict[
        str,
        dict[int, tuple[float, float]],
    ],
) -> tuple[
    list[dict[str, Any]],
    pd.DataFrame,
]:
    state_rows: list[dict[str, Any]] = []
    summary_counts: dict[
        tuple[str, str],
        dict[str, int],
    ] = {
        (
            universe,
            period,
        ): {
            "decision_hour_count": 0,
            "evaluable_hour_count": 0,
            "unevaluable_hour_count": 0,
        }
        for universe in UNIVERSES
        for period in PERIODS
    }
    seen_hours: set[tuple[str, int]] = set()

    total_snapshots = len(snapshots)
    for snapshot_index, snapshot in enumerate(
        snapshots,
        start=1,
    ):
        universe = str(snapshot.universe_id)
        members = tuple(
            (
                str(pair),
                int(rank),
            )
            for pair, rank in snapshot.members
        )
        hours = snapshot_hours(snapshot)

        for decision in hours:
            key = (
                universe,
                int(decision.as_unit("ns").value),
            )
            if key in seen_hours:
                raise RunnerError(f"overlapping PIT membership at {universe}/{decision}")
            seen_hours.add(key)

            period = (
                "ROBUSTNESS_2022"
                if decision < pd.Timestamp("2023-01-01T00:00:00Z")
                else "ROBUSTNESS_2023"
            )
            counters = summary_counts[(universe, period)]
            counters["decision_hour_count"] += 1

            rows = snapshot_state_rows(
                universe_id=universe,
                decision_time=decision,
                members=members,
                lookups=lookups,
            )
            if rows is None:
                counters["unevaluable_hour_count"] += 1
                continue
            if len(rows) != 6:
                raise RunnerError("evaluable cross section does not have six rows")
            counters["evaluable_hour_count"] += 1
            state_rows.extend(rows)

        print(
            f"RD38_P2_MEMBERSHIP={snapshot_index}/{total_snapshots}:{universe}:hours={len(hours)}",
            flush=True,
        )

    summary_rows: list[dict[str, Any]] = []
    for universe in UNIVERSES:
        for period in PERIODS:
            counters = summary_counts[(universe, period)]
            decision_count = counters["decision_hour_count"]
            evaluable_count = counters["evaluable_hour_count"]
            summary_rows.append(
                {
                    "universe_id": universe,
                    "period_id": period,
                    **counters,
                    "evaluable_share": (
                        evaluable_count / decision_count if decision_count else np.nan
                    ),
                    "required_cross_section_size": 6,
                    "partial_ranking_used": False,
                }
            )

    return (
        state_rows,
        pd.DataFrame.from_records(summary_rows),
    )


def event_summary(
    events: pd.DataFrame,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for family in FAMILY_ORDER:
        for universe in UNIVERSES:
            for period in PERIODS:
                cell = events.loc[
                    (events["family_id"] == family)
                    & (events["universe_id"] == universe)
                    & (events["period_id"] == period)
                ]
                rows.append(
                    {
                        "family_id": family,
                        "universe_id": (universe),
                        "period_id": period,
                        "event_count": int(len(cell)),
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
    lineage = verify_lineage(
        repo,
        expected_freeze_commit,
    )
    if (repo / OUTPUT).exists():
        raise RunnerError("P2 runtime already exists; preserve and recover/validate")

    module = load_membership_loader(repo)
    snapshots = selected_snapshots(
        module,
        repo,
    )
    pairs = required_pairs(snapshots)
    lookups = load_prices(
        repo,
        pairs,
    )

    state_rows, hour_summary = build_states(
        snapshots,
        lookups,
    )
    events = events_from_state_rows(state_rows)
    del state_rows

    markouts = build_markout_ledger(
        events,
        lookups,
    )
    summary = summarize_markouts(markouts)
    qualification, families, control = qualification_tables(summary)

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
    output.mkdir(
        parents=True,
        exist_ok=False,
    )

    audit = {
        "schema_version": ("rd38-p2-input-and-conformance-audit-v1"),
        "stage": ("RD38_P2_KUCOIN_NATIVE_CROSS_SECTIONAL_RESILIENCE_DIAGNOSTIC_2022_2023"),
        "status": "PASS",
        "lineage": lineage,
        "source_type": ("KUCOIN_SPOT_POINT_IN_TIME_CROSS_SECTIONAL_RELATIVE_RESILIENCE"),
        "membership_snapshot_count": len(snapshots),
        "required_pair_count": len(pairs),
        "required_pairs": pairs,
        "cross_section_size": 6,
        "all_six_members_required": True,
        "partial_cross_section_ranking_used": False,
        "source_history_start": str(SOURCE_HISTORY_START),
        "source_cutoff_exclusive": str(DATA_CUTOFF),
        "feature_clock": ("COMPLETED_BAR_t_minus_1"),
        "target_clock": ("KUCOIN_SPOT_1H_OPEN_t"),
        "event_semantics": ("FALSE_TO_TRUE_STATE_ENTRY_ONLY"),
        "initial_true_without_observed_false_counted": False,
        "raw_market_data_loaded": True,
        "kucoin_prices_loaded": True,
        "features_computed": True,
        "events_observed": True,
        "forward_returns_computed": True,
        "economic_execution_performed": False,
        "portfolio_accounting_performed": False,
        "shadow_pnl_computed": False,
        "rd37_data_used": False,
        "parameter_search_used": False,
        "threshold_optimization_used": False,
        "return_ranking_used_for_selection": False,
        "winner_selection_used": False,
        "2024_accessed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
    }
    write_json(
        output / "input-and-conformance-audit.json",
        audit,
    )

    hour_summary.to_csv(
        output / "cross-sectional-hour-summary.csv",
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
    control.to_csv(
        output / "positive-control-evaluation.csv",
        index=False,
        lineterminator="\n",
    )

    freeze = {
        "schema_version": ("rd38-p2-qualified-resilience-states-freeze-v1"),
        "status": "PASS",
        "qualified_primary_families": qualified,
        "qualified_primary_count": len(qualified),
        "positive_control_family": (RECLAIM_CONTROL),
        "positive_control_selection_eligible": False,
        "return_ranking_used_for_selection": False,
        "winner_selection_used": False,
        "parameter_search_used": False,
        "threshold_optimization_used": False,
        "failed_family_rescue_used": False,
        "decision": decision,
        "next_stage": next_stage,
        "economic_execution_performed": False,
        "production_authorized": False,
    }
    write_json(
        output / "qualified-resilience-states-freeze.json",
        freeze,
    )

    report = {
        "schema_version": ("rd38-p2-cross-sectional-resilience-diagnostic-report-v1"),
        "stage": ("RD38_P2_KUCOIN_NATIVE_CROSS_SECTIONAL_RESILIENCE_DIAGNOSTIC_2022_2023"),
        "status": "PASS",
        "runner_freeze_commit": (expected_freeze_commit),
        "source_p1b_freeze_commit": (P1B_FREEZE_COMMIT),
        "primary_families": list(PRIMARY_FAMILIES),
        "positive_control_family": (RECLAIM_CONTROL),
        "event_count": int(len(events)),
        "target_markout_count": int(len(markouts)),
        "qualified_primary_families": (qualified),
        "decision": decision,
        "next_stage": next_stage,
        "all_six_members_required": True,
        "partial_cross_section_ranking_used": False,
        "raw_market_data_loaded": True,
        "features_computed": True,
        "events_observed": True,
        "forward_returns_computed": True,
        "economic_execution_performed": False,
        "portfolio_accounting_performed": False,
        "shadow_pnl_computed": False,
        "rd37_data_used": False,
        "parameter_search_used": False,
        "threshold_optimization_used": False,
        "return_ranking_used_for_selection": False,
        "winner_selection_used": False,
        "2024_accessed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
    }
    write_json(
        output / ("rd38-p2-cross-sectional-resilience-diagnostic-report-v1.json"),
        report,
    )

    files: dict[
        str,
        dict[str, Any],
    ] = {}
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
            "schema_version": ("rd38-p2-output-manifest-v1"),
            "file_count": len(files),
            "files": files,
            "deterministic_hash": hashlib.sha256(canonical).hexdigest(),
            "decision": decision,
            "runner_freeze_commit": (expected_freeze_commit),
        },
    )

    return validate_outputs(repo)


def validate_outputs(
    repo: Path,
) -> dict[str, Any]:
    output = repo / OUTPUT
    if not output.is_dir():
        raise RunnerError("P2 runtime missing")

    expected = sorted(
        (
            *OUTPUT_NAMES,
            "output-manifest.json",
        )
    )
    observed = sorted(path.name for path in output.iterdir() if path.is_file())
    if observed != expected:
        raise RunnerError(f"P2 output registry drift: {observed} != {expected}")

    report = load_json(output / ("rd38-p2-cross-sectional-resilience-diagnostic-report-v1.json"))
    freeze = load_json(output / "qualified-resilience-states-freeze.json")
    hours = pd.read_csv(
        output / "cross-sectional-hour-summary.csv",
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
        raise RunnerError("hour summary must have six cells")
    if len(summary) != 72:
        raise RunnerError("target summary must have 72 cells")
    if len(qualification) != 18:
        raise RunnerError("negative qualification must have 18 cells")
    if len(families) != 3:
        raise RunnerError("family qualification must have 3 rows")
    if len(control) != 6:
        raise RunnerError("positive control must have 6 cells")

    if len(events):
        decision = pd.to_datetime(
            events["decision_time"],
            utc=True,
            errors="raise",
        )
        if decision.min() < DATA_START:
            raise RunnerError("pre-2022 event entered P2")
        if decision.max() >= DATA_CUTOFF:
            raise RunnerError("2024 event entered P2")

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
        raise RunnerError("qualified family mismatch")
    if report.get("decision") != expected_decision:
        raise RunnerError("report decision mismatch")
    if report.get("next_stage") != expected_next:
        raise RunnerError("report next-stage mismatch")
    if freeze.get("decision") != expected_decision:
        raise RunnerError("freeze decision mismatch")

    if not bool((hours["required_cross_section_size"].astype(int) == 6).all()):
        raise RunnerError("cross-section cardinality drift")
    if bool(hours["partial_ranking_used"].astype(bool).any()):
        raise RunnerError("partial ranking observed")

    for field in (
        "economic_execution_performed",
        "portfolio_accounting_performed",
        "shadow_pnl_computed",
        "rd37_data_used",
        "parameter_search_used",
        "threshold_optimization_used",
        "return_ranking_used_for_selection",
        "winner_selection_used",
        "2024_accessed",
        "post_2024_accessed",
        "production_authorized",
    ):
        if report.get(field) is not False:
            raise RunnerError(f"prohibited P2 flag: {field}")

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
                "mean_24h": float(row["mean_24h"]),
                "median_24h": float(row["median_24h"]),
                "control_cell_pass": bool(row["control_cell_pass"]),
            }
        )

    return {
        "status": "PASS",
        "decision": expected_decision,
        "next_stage": expected_next,
        "event_count": int(report["event_count"]),
        "target_markout_count": int(report["target_markout_count"]),
        "qualified_primary_families": (qualified),
        "family_qualification": (family_compact),
        "positive_control_24h": (control_compact),
        "all_six_members_required": True,
        "partial_cross_section_ranking_used": False,
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
            execute(
                repo,
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
