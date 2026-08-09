from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import io
import json
import subprocess
import sys
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from spotbot.research.rd37_microstructure_stress import (  # noqa: E402
    DATA_CUTOFF,
    FAMILY_ORDER,
    FAMILY_PARTICIPATION,
    HORIZONS,
    PERIODS,
    PRIMARY_FAMILIES,
    UNIVERSES,
    episode_ledger,
    family_evaluable_hours,
    market_state_frame,
    normalize_target_bars,
    participation_interaction_summary,
    qualification_tables,
    summarize_signal_markouts,
    target_markout,
    target_open_lookup,
    validate_constants,
)

P2_FREEZE_COMMIT = "8fedf7a7b42678daca132b7b3956a9dc6323cb7d"
P2_PROTOCOL = Path(
    "data/research/rd37_p2/"
    "rd37-p2-causal-1m-to-hour-stress-transforms-and-thresholds-"
    "preregistration-v1.json"
)
P2_PROTOCOL_SHA256 = "9d4318ce924f2177bcc70d1b1ccf91602883defd1c8bb6f007efcf5bcd1b578c"
P2_AUDIT = Path("data/research/rd37_p2/rd37-p2-preregistration-audit-v1.json")
P2_AUDIT_SHA256 = "896b62a707e650e6339c5b395fba73b9415a415dff9efff11fcbd08895e3de23"

P1_SOURCE_AUDIT = Path("data/research/rd37_p1_runtime/source-file-audit.csv")
P1_SOURCE_AUDIT_BLOB = "da9fbf2b70cd4f648d7acf71be31f5efdc9eb77a"

RD31_RUNNER = Path("scripts/research/run_rd31_market_regime_admission_governor.py")
RD31_RUNNER_BLOB = "3b5c6916e34be6c9642702fe2807e42e445ee083"

BINANCE_RAW_ROOT = Path("data/raw/rd37/binance_spot_1m")
KUCOIN_RAW_ROOT = Path("data/raw/rd16b/kucoin")
OUTPUT = Path("data/research/rd37_p3_runtime")

OUTPUT_NAMES = (
    "input-and-conformance-audit.json",
    "hourly-market-state-ledger.csv",
    "episode-ledger.csv",
    "source-state-summary.csv",
    "unconditional-baseline-summary.csv",
    "target-markout-ledger.csv",
    "target-markout-summary.csv",
    "participation-interaction-summary.csv",
    "qualification-evaluation.csv",
    "family-qualification.csv",
    "qualified-stress-states-freeze.json",
    "rd37-p3-microstructure-stress-diagnostic-report-v1.json",
)

SUCCESS_DECISION = "RD37_QUALIFIED_MICROSTRUCTURE_STRESS_STATES_FREEZE_PRE_EXIT_SHADOW_ABLATION"
SUCCESS_NEXT = (
    "RD37_P4_FREEZE_KUCOIN_NATIVE_EXIT_BRAIN_SHADOW_ABLATION_WITH_QUALIFIED_STRESS_STATES"
)
FAILURE_DECISION = "RD37_MICROSTRUCTURE_STRESS_ALPHA_UNQUALIFIED_NEXT_SOURCE_REQUIRED"
FAILURE_NEXT = "RD38_PREREGISTER_NEXT_SPOT_ONLY_ADAPTIVE_EXIT_INFORMATION_SOURCE"


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


def csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def verify_lineage(
    repo: Path,
    expected_freeze_commit: str,
) -> dict[str, Any]:
    if git(repo, "diff", "--cached", "--name-only", "--"):
        raise RunnerError("staged tracked changes exist before P3 run")
    if git(repo, "diff", "--name-only", "--"):
        raise RunnerError("unstaged tracked changes exist before P3 run")

    head = git(repo, "rev-parse", "HEAD")
    if head != expected_freeze_commit:
        raise RunnerError(f"P3 HEAD {head} != freeze {expected_freeze_commit}")
    if git(repo, "rev-parse", "HEAD^") != P2_FREEZE_COMMIT:
        raise RunnerError("P3 runner-freeze parent is not P2")

    if sha256(repo / P2_PROTOCOL) != P2_PROTOCOL_SHA256:
        raise RunnerError("P2 protocol SHA drifted")
    if sha256(repo / P2_AUDIT) != P2_AUDIT_SHA256:
        raise RunnerError("P2 audit SHA drifted")

    source_blob = git(
        repo,
        "rev-parse",
        f"HEAD:{P1_SOURCE_AUDIT.as_posix()}",
    )
    if source_blob != P1_SOURCE_AUDIT_BLOB:
        raise RunnerError("P1 source audit blob drifted")

    rd31_blob = git(
        repo,
        "rev-parse",
        f"HEAD:{RD31_RUNNER.as_posix()}",
    )
    if rd31_blob != RD31_RUNNER_BLOB:
        raise RunnerError("RD31 runner blob drifted")

    protocol = load_json(repo / P2_PROTOCOL)
    if protocol.get("status") != "FROZEN_PRE_FEATURE_COMPUTATION":
        raise RunnerError("P2 protocol is not frozen")
    if (
        tuple(item["family_id"] for item in protocol.get("frozen_state_families", []))
        != FAMILY_ORDER
    ):
        raise RunnerError("P2 family registry drifted")

    future = protocol.get("future_p3_diagnostic", {})
    if tuple(future.get("target_horizons_hours", ())) != HORIZONS:
        raise RunnerError("P2 horizons drifted")
    if future.get("primary_horizon_hours") != 6:
        raise RunnerError("P2 primary horizon drifted")
    if tuple(future.get("universes", ())) != UNIVERSES:
        raise RunnerError("P2 universes drifted")
    if future.get("economic_replay") is not False:
        raise RunnerError("P2 unexpectedly permits economics")
    if future.get("2024_access") is not False:
        raise RunnerError("P2 unexpectedly permits 2024")

    validate_constants()
    return {
        "runner_freeze_commit": expected_freeze_commit,
        "p2_freeze_commit": P2_FREEZE_COMMIT,
        "p2_protocol_sha256": P2_PROTOCOL_SHA256,
        "p2_audit_sha256": P2_AUDIT_SHA256,
        "p1_source_audit_blob": source_blob,
        "rd31_runner_blob": rd31_blob,
    }


def parse_archive(path: Path) -> pd.DataFrame:
    with zipfile.ZipFile(path, "r") as archive:
        names = [name for name in archive.namelist() if not name.endswith("/")]
        if len(names) != 1:
            raise RunnerError(f"{path.name}: expected exactly one CSV member")
        raw = archive.read(names[0]).decode("utf-8-sig")

    records: list[dict[str, Any]] = []
    for index, row in enumerate(csv.reader(io.StringIO(raw))):
        if index == 0 and row and not row[0].isdigit():
            continue
        if len(row) != 12:
            raise RunnerError(f"{path.name}: row {index} does not have 12 columns")
        open_ms = int(row[0])
        if open_ms >= 100_000_000_000_000:
            raise RunnerError(f"{path.name}: unexpected microsecond timestamp")
        records.append(
            {
                "timestamp": pd.to_datetime(open_ms, unit="ms", utc=True),
                "open": float(row[1]),
                "high": float(row[2]),
                "low": float(row[3]),
                "close": float(row[4]),
                "quote_volume": float(row[7]),
                "number_of_trades": float(row[8]),
                "taker_buy_quote_volume": float(row[10]),
            }
        )
    return pd.DataFrame.from_records(records)


def load_binance_minutes(
    repo: Path,
) -> tuple[dict[str, pd.DataFrame], dict[str, Any]]:
    audits = csv_rows(repo / P1_SOURCE_AUDIT)
    by_symbol: dict[str, list[pd.DataFrame]] = {symbol: [] for symbol in ("BTCUSDT", "ETHUSDT")}
    verified = 0

    for symbol in by_symbol:
        rows = sorted(
            [
                row
                for row in audits
                if row["symbol"] == symbol and row["month"][:4] in {"2022", "2023"}
            ],
            key=lambda row: row["month"],
        )
        if len(rows) != 24:
            raise RunnerError(f"expected 24 P1-audited months for {symbol}")

        for row in rows:
            month = row["month"]
            path = repo / BINANCE_RAW_ROOT / symbol / "1m" / f"{symbol}-1m-{month}.zip"
            if not path.is_file():
                raise RunnerError(f"raw source missing: {path}")
            actual_sha = sha256(path)
            if actual_sha != row["archive_sha256"]:
                raise RunnerError(f"raw archive SHA drift {symbol}/{month}")
            frame = parse_archive(path)
            if len(frame) != int(row["row_count"]):
                raise RunnerError(f"raw archive row-count drift {symbol}/{month}")
            by_symbol[symbol].append(frame)
            verified += 1
            print(
                f"RD37_P3_SOURCE={verified}/48:{symbol}:{month}:rows={len(frame)}",
                flush=True,
            )

    combined = {
        symbol: (
            pd.concat(parts, ignore_index=True)
            .sort_values("timestamp", kind="stable")
            .reset_index(drop=True)
        )
        for symbol, parts in by_symbol.items()
    }
    return combined, {
        "verified_archive_count": verified,
        "raw_source": "BINANCE_SPOT_1M_KLINES",
        "network_access_performed": False,
    }


def load_rd31_runner() -> Any:
    path = ROOT / RD31_RUNNER
    spec = importlib.util.spec_from_file_location(
        "_rd31_for_rd37_p3",
        path,
    )
    if spec is None or spec.loader is None:
        raise RunnerError("cannot load frozen RD31 runner")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def selection_membership(rd31: Any, repo: Path) -> list[Any]:
    source = repo / rd31.MEMBERSHIP
    if sha256(source) != rd31.MEMBERSHIP_SHA256:
        raise RunnerError("PIT membership SHA drifted")
    snapshots = rd31.load_membership(source)
    selected = rd31.selection_membership(snapshots)
    if not selected:
        raise RunnerError("no PIT membership overlaps P3")
    return selected


def required_pairs(snapshots: list[Any]) -> list[str]:
    pairs: set[str] = set()
    for snapshot in snapshots:
        for pair, _rank in snapshot.members:
            pairs.add(str(pair))
    if not pairs:
        raise RunnerError("membership produced no pairs")
    return sorted(pairs)


def membership_at(
    rd31: Any,
    snapshots: list[Any],
    *,
    universe_id: str,
    timestamp: pd.Timestamp,
) -> tuple[tuple[str, int], ...]:
    members = rd31.membership_at(
        snapshots,
        universe_id=universe_id,
        timestamp=timestamp,
    )
    return tuple((str(pair), int(rank)) for pair, rank in members)


def load_targets(
    repo: Path,
    pairs: list[str],
) -> dict[str, pd.DataFrame]:
    cutoff = DATA_CUTOFF.to_pydatetime()
    result: dict[str, pd.DataFrame] = {}
    for index, pair in enumerate(pairs, start=1):
        path = repo / KUCOIN_RAW_ROOT / pair / "1h.parquet"
        if not path.is_file():
            raise RunnerError(f"KuCoin target missing: {path}")
        raw = pd.read_parquet(
            path,
            columns=["timestamp", "open"],
            engine="pyarrow",
            filters=[("timestamp", "<", cutoff)],
        )
        result[pair] = normalize_target_bars(raw, pair=pair)
        print(
            f"RD37_P3_TARGET={index}/{len(pairs)}:{pair}:rows={len(result[pair])}",
            flush=True,
        )
    return result


def source_state_summary(
    market: pd.DataFrame,
    episodes: pd.DataFrame,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for family in FAMILY_ORDER:
        evaluable_column = f"{family}_evaluable"
        for period_id, (start, end) in PERIODS.items():
            reference = market["hour"] + pd.Timedelta(hours=1)
            period_mask = (reference >= start) & (reference < end)
            evaluable = market.loc[
                period_mask & market[evaluable_column].fillna(False).astype(bool)
            ]
            active = market.loc[period_mask & market[family].fillna(False).astype(bool)]
            if family in PRIMARY_FAMILIES:
                event_count = int(
                    episodes.loc[
                        (episodes["family_id"] == family) & (episodes["period_id"] == period_id),
                        "reference_time",
                    ].nunique()
                )
            else:
                event_count = 0
            rows.append(
                {
                    "family_id": family,
                    "period_id": period_id,
                    "evaluable_hour_count": int(len(evaluable)),
                    "active_hour_count": int(len(active)),
                    "episode_event_count": event_count,
                    "role": (
                        "PRIMARY_EXIT_RISK_EVIDENCE"
                        if family in PRIMARY_FAMILIES
                        else "CONTEXT_AMPLIFIER_ONLY"
                    ),
                }
            )
    return pd.DataFrame.from_records(rows)


def build_baselines(
    *,
    rd31: Any,
    snapshots: list[Any],
    market: pd.DataFrame,
    lookups: dict[str, dict[int, float]],
) -> pd.DataFrame:
    accum: dict[
        tuple[str, str, str, int],
        list[float],
    ] = defaultdict(list)
    pair_sets: dict[
        tuple[str, str, str, int],
        set[str],
    ] = defaultdict(set)
    hour_sets: dict[
        tuple[str, str, str, int],
        set[pd.Timestamp],
    ] = defaultdict(set)

    membership_cache: dict[
        tuple[str, int],
        tuple[tuple[str, int], ...],
    ] = {}

    for family in PRIMARY_FAMILIES:
        eligible = family_evaluable_hours(market, family=family)
        for row in eligible.itertuples(index=False):
            reference_time = pd.Timestamp(row.reference_time)
            period_id = str(row.period_id)
            ref_key = int(reference_time.as_unit("ns").value)
            for universe in UNIVERSES:
                cache_key = (universe, ref_key)
                members = membership_cache.get(cache_key)
                if members is None:
                    members = membership_at(
                        rd31,
                        snapshots,
                        universe_id=universe,
                        timestamp=reference_time,
                    )
                    membership_cache[cache_key] = members
                for pair, _rank in members:
                    lookup = lookups.get(pair)
                    if lookup is None:
                        raise RunnerError(f"missing target lookup for {pair}")
                    for horizon in HORIZONS:
                        markout = target_markout(
                            reference_time=reference_time,
                            horizon_hours=horizon,
                            lookup=lookup,
                        )
                        if markout is None:
                            continue
                        key = (
                            family,
                            universe,
                            period_id,
                            horizon,
                        )
                        accum[key].append(float(markout["forward_return"]))
                        pair_sets[key].add(pair)
                        hour_sets[key].add(reference_time)

    rows: list[dict[str, Any]] = []
    for family in PRIMARY_FAMILIES:
        for universe in UNIVERSES:
            for period_id in PERIODS:
                for horizon in HORIZONS:
                    key = (
                        family,
                        universe,
                        period_id,
                        horizon,
                    )
                    values = accum.get(key, [])
                    rows.append(
                        {
                            "family_id": family,
                            "universe_id": universe,
                            "period_id": period_id,
                            "horizon_hours": horizon,
                            "family_evaluable_reference_hour_count": len(hour_sets.get(key, set())),
                            "pair_count": len(pair_sets.get(key, set())),
                            "markout_count": len(values),
                            "baseline_mean_forward_return": (
                                float(np.mean(values)) if values else np.nan
                            ),
                            "baseline_definition": (
                                "FAMILY_EVALUABLE_HOURS_UNCONDITIONAL_ON_FAMILY_STATE"
                            ),
                        }
                    )
    return pd.DataFrame.from_records(rows)


def build_signal_markouts(
    *,
    rd31: Any,
    snapshots: list[Any],
    episodes: pd.DataFrame,
    lookups: dict[str, dict[int, float]],
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    membership_cache: dict[
        tuple[str, int],
        tuple[tuple[str, int], ...],
    ] = {}

    for event in episodes.to_dict(orient="records"):
        reference_time = pd.Timestamp(event["reference_time"])
        ref_key = int(reference_time.as_unit("ns").value)
        for universe in UNIVERSES:
            cache_key = (universe, ref_key)
            members = membership_cache.get(cache_key)
            if members is None:
                members = membership_at(
                    rd31,
                    snapshots,
                    universe_id=universe,
                    timestamp=reference_time,
                )
                membership_cache[cache_key] = members
            for pair, rank in members:
                lookup = lookups.get(pair)
                if lookup is None:
                    raise RunnerError(f"missing target lookup for {pair}")
                for horizon in HORIZONS:
                    markout = target_markout(
                        reference_time=reference_time,
                        horizon_hours=horizon,
                        lookup=lookup,
                    )
                    if markout is None:
                        continue
                    rows.append(
                        {
                            "family_id": event["family_id"],
                            "universe_id": universe,
                            "period_id": event["period_id"],
                            "pair": pair,
                            "membership_rank": rank,
                            "source_hour": event["source_hour"],
                            "reference_time": reference_time,
                            "horizon_hours": horizon,
                            "exit_time": markout["exit_time"],
                            "entry_price": markout["entry_price"],
                            "exit_price": markout["exit_price"],
                            "forward_return": markout["forward_return"],
                            "participation_burst_active": bool(event["participation_burst_active"]),
                        }
                    )
    columns = [
        "family_id",
        "universe_id",
        "period_id",
        "pair",
        "membership_rank",
        "source_hour",
        "reference_time",
        "horizon_hours",
        "exit_time",
        "entry_price",
        "exit_price",
        "forward_return",
        "participation_burst_active",
    ]
    result = pd.DataFrame.from_records(rows, columns=columns)
    if not result.empty:
        result = result.sort_values(
            [
                "reference_time",
                "family_id",
                "universe_id",
                "membership_rank",
                "pair",
                "horizon_hours",
            ],
            kind="stable",
        ).reset_index(drop=True)
    return result


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
        "schema_version": "rd37-p3-output-manifest-v1",
        "decision": decision,
        "runner_freeze_commit": freeze_commit,
        "file_count": len(files),
        "files": files,
        "deterministic_hash": hashlib.sha256(canonical).hexdigest(),
    }


def execute(
    repo: Path,
    expected_freeze_commit: str,
) -> dict[str, Any]:
    lineage = verify_lineage(repo, expected_freeze_commit)
    if (repo / OUTPUT).exists():
        raise RunnerError("P3 runtime already exists; preserve and validate/recover")

    minutes, source_audit = load_binance_minutes(repo)
    market = market_state_frame(
        minutes["BTCUSDT"],
        minutes["ETHUSDT"],
    )
    del minutes

    episodes = episode_ledger(market)
    state_summary = source_state_summary(market, episodes)

    rd31 = load_rd31_runner()
    snapshots = selection_membership(rd31, repo)
    pairs = required_pairs(snapshots)
    targets = load_targets(repo, pairs)
    lookups = {pair: target_open_lookup(frame) for pair, frame in targets.items()}
    del targets

    baselines = build_baselines(
        rd31=rd31,
        snapshots=snapshots,
        market=market,
        lookups=lookups,
    )
    markouts = build_signal_markouts(
        rd31=rd31,
        snapshots=snapshots,
        episodes=episodes,
        lookups=lookups,
    )
    summary = summarize_signal_markouts(
        markouts,
        baselines,
    )
    interaction = participation_interaction_summary(markouts)
    qualification, families = qualification_tables(summary)

    qualified = list(
        families.loc[
            families["advances_to_shadow_ablation"].astype(bool),
            "family_id",
        ].astype(str)
    )
    success = bool(qualified)
    decision = SUCCESS_DECISION if success else FAILURE_DECISION
    next_stage = SUCCESS_NEXT if success else FAILURE_NEXT

    output = repo / OUTPUT
    output.mkdir(parents=True, exist_ok=False)

    audit = {
        "schema_version": "rd37-p3-input-and-conformance-audit-v1",
        "stage": "RD37_P3_MICROSTRUCTURE_STRESS_DIAGNOSTIC_2022_2023",
        "lineage": lineage,
        "source_audit": source_audit,
        "source_frequency": "1m",
        "decision_frequency": "1h",
        "target_venue": "KUCOIN_SPOT",
        "target_horizons_hours": list(HORIZONS),
        "primary_horizon_hours": 6,
        "baseline_definition": (
            "For each primary family, period, universe, and horizon: "
            "unconditional KuCoin forward-return mean across the same "
            "family-evaluable source hours, without conditioning on "
            "the family state."
        ),
        "qualification_event": "EPISODE_ENTRY_ONLY",
        "maintenance_blackout_start": "2023-03-24T11:38:00+00:00",
        "maintenance_blackout_end_exclusive": ("2023-03-24T14:00:00+00:00"),
        "maintenance_blackout_rows_used": False,
        "target_pair_count": len(pairs),
        "target_pairs": pairs,
        "pit_membership_snapshot_count": len(snapshots),
        "raw_market_data_loaded": True,
        "feature_computation_performed": True,
        "forward_returns_computed": True,
        "alpha_results_observed": True,
        "parameter_search_used": False,
        "threshold_optimization_used": False,
        "winner_selection_used": False,
        "economic_execution_performed": False,
        "network_access_performed": False,
        "2024_accessed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
    }
    write_json(output / "input-and-conformance-audit.json", audit)

    market.to_csv(
        output / "hourly-market-state-ledger.csv",
        index=False,
        lineterminator="\n",
    )
    episodes.to_csv(
        output / "episode-ledger.csv",
        index=False,
        lineterminator="\n",
    )
    state_summary.to_csv(
        output / "source-state-summary.csv",
        index=False,
        lineterminator="\n",
    )
    baselines.to_csv(
        output / "unconditional-baseline-summary.csv",
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
    interaction.to_csv(
        output / "participation-interaction-summary.csv",
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

    freeze = {
        "schema_version": "rd37-p3-qualified-stress-states-freeze-v1",
        "status": "PASS",
        "qualified_primary_families": qualified,
        "qualified_primary_count": len(qualified),
        "participation_burst_is_context_only": True,
        "participation_context_used_to_rescue_failure": False,
        "return_ranking_used": False,
        "winner_selection_used": False,
        "parameter_search_used": False,
        "threshold_optimization_used": False,
        "decision": decision,
        "next_stage": next_stage,
        "economic_execution_performed": False,
        "production_authorized": False,
    }
    write_json(
        output / "qualified-stress-states-freeze.json",
        freeze,
    )

    report = {
        "schema_version": ("rd37-p3-microstructure-stress-diagnostic-report-v1"),
        "stage": "RD37_P3_MICROSTRUCTURE_STRESS_DIAGNOSTIC_2022_2023",
        "status": "PASS",
        "runner_freeze_commit": expected_freeze_commit,
        "source_p2_freeze_commit": P2_FREEZE_COMMIT,
        "primary_families": list(PRIMARY_FAMILIES),
        "context_only_family": FAMILY_PARTICIPATION,
        "completed_market_hour_count": len(market),
        "episode_event_count": len(episodes),
        "target_markout_count": len(markouts),
        "qualified_primary_families": qualified,
        "decision": decision,
        "next_stage": next_stage,
        "baseline_adjusted_diagnostic_performed": True,
        "participation_interaction_reported": True,
        "raw_market_data_loaded": True,
        "feature_computation_performed": True,
        "forward_returns_computed": True,
        "alpha_results_observed": True,
        "parameter_search_used": False,
        "threshold_optimization_used": False,
        "winner_selection_used": False,
        "economic_execution_performed": False,
        "network_access_performed": False,
        "2024_accessed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
    }
    write_json(
        output / "rd37-p3-microstructure-stress-diagnostic-report-v1.json",
        report,
    )

    manifest = output_manifest(
        output,
        decision=decision,
        freeze_commit=expected_freeze_commit,
    )
    write_json(output / "output-manifest.json", manifest)

    return validate_outputs(repo)


def validate_outputs(repo: Path) -> dict[str, Any]:
    output = repo / OUTPUT
    if not output.is_dir():
        raise RunnerError("P3 runtime missing")

    expected = sorted((*OUTPUT_NAMES, "output-manifest.json"))
    observed = sorted(path.name for path in output.iterdir() if path.is_file())
    if observed != expected:
        raise RunnerError(f"P3 output registry drifted: {observed} != {expected}")

    report = load_json(output / "rd37-p3-microstructure-stress-diagnostic-report-v1.json")
    freeze = load_json(output / "qualified-stress-states-freeze.json")
    market = pd.read_csv(
        output / "hourly-market-state-ledger.csv",
        low_memory=False,
    )
    episodes = pd.read_csv(
        output / "episode-ledger.csv",
        low_memory=False,
    )
    baselines = pd.read_csv(
        output / "unconditional-baseline-summary.csv",
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
    interaction = pd.read_csv(
        output / "participation-interaction-summary.csv",
        low_memory=False,
    )

    if len(baselines) != 54:
        raise RunnerError("baseline summary must have 54 cells")
    if len(summary) != 54:
        raise RunnerError("target summary must have 54 cells")
    if len(interaction) != 54:
        raise RunnerError("interaction summary must have 54 cells")
    if len(qualification) != 18:
        raise RunnerError("qualification table must have 18 cells")
    if len(families) != 3:
        raise RunnerError("family qualification must have 3 rows")

    hours = pd.to_datetime(market["hour"], utc=True, errors="raise")
    if len(hours) and hours.max() >= DATA_CUTOFF:
        raise RunnerError("2024 source hour entered P3")

    if len(episodes):
        refs = pd.to_datetime(episodes["reference_time"], utc=True, errors="raise")
        if refs.max() >= DATA_CUTOFF:
            raise RunnerError("2024 episode reference entered P3")

    qualified = list(
        families.loc[
            families["advances_to_shadow_ablation"].astype(bool),
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

    for field in (
        "parameter_search_used",
        "threshold_optimization_used",
        "winner_selection_used",
        "economic_execution_performed",
        "network_access_performed",
        "2024_accessed",
        "post_2024_accessed",
        "production_authorized",
    ):
        if report.get(field) is not False:
            raise RunnerError(f"prohibited report flag: {field}")

    manifest = load_json(output / "output-manifest.json")
    if manifest.get("file_count") != len(OUTPUT_NAMES):
        raise RunnerError("manifest file count drifted")
    if manifest.get("decision") != expected_decision:
        raise RunnerError("manifest decision mismatch")

    return {
        "status": "PASS",
        "decision": expected_decision,
        "next_stage": expected_next,
        "completed_market_hour_count": len(market),
        "episode_event_count": len(episodes),
        "qualified_primary_families": qualified,
        "primary_family_count": 3,
        "baseline_cell_count": len(baselines),
        "summary_cell_count": len(summary),
        "qualification_cell_count": len(qualification),
        "participation_interaction_cell_count": len(interaction),
        "baseline_adjusted_diagnostic_performed": True,
        "economic_execution_performed": False,
        "network_access_performed": False,
        "2024_accessed": False,
        "production_authorized": False,
    }


def main() -> int:
    args = parser().parse_args()
    repo = args.repo_root.resolve()
    if not (repo / ".git").exists():
        raise RunnerError(f"not a git repository: {repo}")

    if args.validate_only:
        print(json.dumps(validate_outputs(repo), indent=2, sort_keys=True))
        return 0

    if not args.execute:
        raise RunnerError("P3 requires explicit --execute")
    if not args.expected_freeze_commit:
        raise RunnerError("--expected-freeze-commit is required")

    print(
        json.dumps(
            execute(repo, args.expected_freeze_commit),
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
