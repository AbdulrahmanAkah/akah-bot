from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, cast

import pandas as pd
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from spotbot.research.rd18_p3e_cash_feasibility import (  # noqa: E402
    route_cash_feasible_candidates,
)
from spotbot.research.rd18_p3e_replay import (  # noqa: E402
    build_v3_replay_ledgers,
)
from spotbot.research.rd18_p3e_sensitivity import (  # noqa: E402
    COST_MULTIPLIERS,
    NAMED_OMISSIONS,
    OMITTED_YEARS,
    UNIVERSE_IDS,
    A2CandidateCache,
    CounterfactualMembershipBuilder,
    HourlyBarCache,
    IntervalReadinessCache,
    SensitivityError,
    execute_sensitivity,
    filter_loyo_candidates,
    frame_content_hash,
    generated_pairs,
    normalize_base_membership,
    normalize_omission_readiness,
    pair_symbol_map,
    select_counterfactual_a2_candidates,
    sensitivity_gate_summary,
)
from spotbot.research.rd18_p3x_a3b_audit import (  # noqa: E402
    build_full_rankings,
)

STAGE = "RD18_P3E_LOYO_AND_LOAO_SENSITIVITY_EXECUTION"
DECISION = "RD18_P3E_LOYO_AND_LOAO_SENSITIVITY_COMPLETE"
NEXT_STAGE = "RD18_P3E_FINAL_DECISION_AND_PUBLICATION"

EXPECTED_HASHES = {
    "dry_report": ("9a51c375a9a59ea3d50328a38c518afce4645de378088650cb1286a50850b4fb"),
    "dry_manifest": ("dd24def921bf5bcc013d2cb38dd6e7fdde6b6cde7099560864f9ff4864f5bfca"),
    "cash_report": ("d918bf20c44e3ca2e422933b201105ae6b57b2e8fb8595be3fed7ecc837f74e4"),
    "cash_manifest": ("8836b397e594eaaa696523cf9c2dfc5b475ab3cbd81a2a7cf36e8b4a5c0bcca9"),
    "a3b_manifest": ("82f6fcd05dd8d5d0f7cf726829d319af3d18f8b7534660d37ce317f38bbb807c"),
    "a3b_effective_membership": (
        "f7d6012ce8cd691583b9b6276ddf36371bfe0bbd9b28f810b676ad0177fb559e"
    ),
    "a3b_omission_readiness": ("fef806b8ba79619a39e7420084227f6595c566086cf6251719577dec8c5a82c8"),
}
P3R_HASHES = {
    "performance-gate-registry.json": (
        "033a955c3d13826886692a20690bfb74b6029fedd7778dd7e7d25fea5dd50105"
    ),
    "replay-execution-contract.json": (
        "31ee2bf443332826bbd5a0b8b470bc4dec686d758d91f0d6328dddc7af6d967a"
    ),
}


class RunnerError(RuntimeError):
    """Raised when the sensitivity runner cannot continue."""


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
        "--a3b-runtime",
        type=Path,
        default=ROOT / "data/research/rd18_p3x_a3b_runtime",
    )
    result.add_argument(
        "--dry-run-runtime",
        type=Path,
        default=ROOT / "data/research/rd18_p3e_dry_run_runtime",
    )
    result.add_argument(
        "--cash-runtime",
        type=Path,
        default=(ROOT / "data/research/rd18_p3e_cash_remediation_runtime"),
    )
    result.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "data/research/rd18_p3e_sensitivity_runtime",
    )
    result.add_argument("--preflight-only", action="store_true")
    result.add_argument("--execute", action="store_true")
    result.add_argument("--resume", action="store_true")
    return result


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise RunnerError(f"JSON missing: {path}")
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise RunnerError(f"JSON object expected: {path}")
    return value


def json_ready(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_ready(item) for item in value]
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if hasattr(value, "item"):
        return json_ready(cast(Any, value).item())
    if isinstance(value, float) and not pd.notna(value):
        return None
    return value


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    temporary.write_text(
        json.dumps(
            json_ready(value),
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.replace(temporary, path)


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise RunnerError(f"CSV missing: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def csv_value(value: object) -> object:
    ready = json_ready(value)
    if isinstance(ready, (dict, list)):
        return json.dumps(
            ready,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        )
    return ready


def write_rows(
    path: Path,
    rows: Sequence[Mapping[str, object]],
) -> None:
    if not rows:
        raise RunnerError(f"empty CSV rows: {path}")
    fields = sorted({str(key) for row in rows for key in row})
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    with temporary.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fields,
            extrasaction="raise",
            lineterminator="\n",
        )
        writer.writeheader()
        for row in rows:
            writer.writerow({field: csv_value(row.get(field)) for field in fields})
    os.replace(temporary, path)


def verify_manifest(
    root: Path,
    manifest: Mapping[str, object],
) -> None:
    files = manifest.get("files")
    if not isinstance(files, list):
        raise RunnerError(f"manifest file list invalid: {root}")
    for raw in files:
        if not isinstance(raw, Mapping):
            raise RunnerError(f"manifest row invalid: {root}")
        relative = str(raw["path"])
        path = root / relative
        if not path.is_file():
            raise RunnerError(f"manifest target missing: {path}")
        if path.stat().st_size != int(cast(int, raw["bytes"])) or sha256(path) != str(
            raw["sha256"]
        ):
            raise RunnerError(f"manifest target drifted: {path}")


def verify_p3r(repo: Path) -> dict[str, Any]:
    root = repo / "data/research/rd18_p3r"
    for name, expected in P3R_HASHES.items():
        path = root / name
        if not path.is_file() or sha256(path) != expected:
            raise RunnerError(f"P3R hash drifted: {name}")
    contract = load_json(root / "replay-execution-contract.json")
    gates = load_json(root / "performance-gate-registry.json")
    execution = contract.get("execution")
    required_runs = contract.get("required_runs")
    sensitivity = gates.get("sensitivity_gates")
    if not isinstance(execution, Mapping):
        raise RunnerError("P3R execution section missing")
    if not isinstance(required_runs, Mapping):
        raise RunnerError("P3R required-runs section missing")
    if not isinstance(sensitivity, Mapping):
        raise RunnerError("P3R sensitivity section missing")
    if not all(
        (
            execution.get("negative_cash_allowed") is False,
            execution.get("cost_multipliers") == [1.0, 2.0],
            execution.get("cost_multiplier_is_leverage") is False,
            required_runs.get("leave_one_year_out") == "6 omitted years x 3 universes x 2 costs",
            required_runs.get("named_omissions") == ["BCHSV-USDT", "PEPE-USDT"],
            sensitivity.get("leave_one_year_out_method")
            == (
                "Disable new admissions whose signal_close falls "
                "in the omitted calendar year; preserve chronology "
                "and normal exits for pre-existing positions."
            ),
            sensitivity.get("leave_one_asset_out_method")
            == (
                "Remove the asset before universe boundary rules "
                "and hysteresis, refill deterministically from the "
                "ranking, regenerate candidates and rerun the router; "
                "never delete trades post hoc."
            ),
            gates.get("thresholds_may_change_after_results") is False,
        )
    ):
        raise RunnerError("P3R sensitivity semantics drifted")
    return gates


def verify_upstream(
    *,
    repo: Path,
    a3b: Path,
    dry: Path,
    cash: Path,
) -> dict[str, object]:
    paths = {
        "dry_report": (dry / "rd18-p3e-technical-dry-run-report-v1.json"),
        "dry_manifest": dry / "output-manifest.json",
        "cash_report": (cash / "rd18-p3e-cash-feasibility-remediation-report-v1.json"),
        "cash_manifest": cash / "output-manifest.json",
        "a3b_manifest": a3b / "output-manifest.json",
        "a3b_effective_membership": (a3b / "effective-operational-membership.csv"),
        "a3b_omission_readiness": (a3b / "omission-replacement-readiness.csv"),
    }
    observed = {key: sha256(path) for key, path in paths.items()}
    if observed != EXPECTED_HASHES:
        raise RunnerError(f"upstream hash drift: {observed}")
    dry_manifest = load_json(paths["dry_manifest"])
    cash_manifest = load_json(paths["cash_manifest"])
    a3b_manifest = load_json(paths["a3b_manifest"])
    verify_manifest(dry, dry_manifest)
    verify_manifest(cash, cash_manifest)
    verify_manifest(a3b, a3b_manifest)
    dry_report = load_json(paths["dry_report"])
    cash_report = load_json(paths["cash_report"])
    if not all(
        (
            dry_report.get("passed") is True,
            dry_report.get("decision") == "RD18_P3E_TECHNICAL_DRY_RUN_COMPLETE",
            cash_report.get("passed") is True,
            cash_report.get("decision") == ("RD18_P3E_CASH_FEASIBILITY_REMEDIATION_COMPLETE"),
            cash_report.get("corrected_runs") == 6,
            cash_report.get("prior_base_superseded_for_advancement") is True,
            cash_report.get("loyo_executed") is False,
            cash_report.get("loao_executed") is False,
            cash_report.get("post_2024_accessed") is False,
            cash_report.get(
                "corrected_base_classification",
                {},
            ).get("base_economic_gates_passed")
            is False,
            cash_report.get("next_stage") == ("RD18_P3E_LOYO_AND_LOAO_SENSITIVITY_EXECUTION"),
        )
    ):
        raise RunnerError("upstream stage semantics drifted")
    return {
        "hashes": observed,
        "dry_manifest_deterministic_hash": dry_manifest["deterministic_hash"],
        "cash_manifest_deterministic_hash": cash_manifest["deterministic_hash"],
        "a3b_manifest_deterministic_hash": a3b_manifest["deterministic_hash"],
        "corrected_base_classification": cash_report["corrected_base_classification"],
    }


def _trade_pairs(
    cash: Path,
    *,
    universe_id: str,
    cost: int,
) -> set[str]:
    path = cash / "universes" / universe_id / f"cost-{cost}x" / "cash-routed-trades.parquet"
    return set(
        pd.read_parquet(
            path,
            columns=["pair"],
        )["pair"].astype(str)
    )


def build_applicability(
    *,
    cash: Path,
    membership: pd.DataFrame,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for universe_id in UNIVERSE_IDS:
        one = _trade_pairs(
            cash,
            universe_id=universe_id,
            cost=1,
        )
        two = _trade_pairs(
            cash,
            universe_id=universe_id,
            cost=2,
        )
        universe_membership = membership.loc[membership["universe_id"] == universe_id]
        original_counts = universe_membership["original_pair"].astype(str).value_counts().to_dict()
        effective_counts = (
            universe_membership["effective_pair"].astype(str).value_counts().to_dict()
        )
        pairs = one | two
        for named in NAMED_OMISSIONS:
            if int(original_counts.get(named, 0)) > 0 or int(effective_counts.get(named, 0)) > 0:
                pairs.add(named)
        for pair in sorted(pairs):
            named = pair in NAMED_OMISSIONS
            basis = []
            if pair in one or pair in two:
                basis.append("TRADED_CORRECTED_BASE")
            if named:
                basis.append("NAMED_OMISSION")
            rows.append(
                {
                    "universe_id": universe_id,
                    "omitted_pair": pair,
                    "traded_1x": pair in one,
                    "traded_2x": pair in two,
                    "named_omission": named,
                    "original_membership_occurrences": int(original_counts.get(pair, 0)),
                    "effective_membership_occurrences": int(effective_counts.get(pair, 0)),
                    "applicability_basis": "|".join(basis),
                }
            )
    observed_named = {row["omitted_pair"] for row in rows if bool(row["named_omission"])}
    if observed_named != set(NAMED_OMISSIONS):
        raise RunnerError(f"named omission applicability drifted: {sorted(observed_named)}")
    return rows


def _compare_frames(
    left: pd.DataFrame,
    right: pd.DataFrame,
    *,
    id_column: str,
    numeric_columns: Sequence[str],
    exact_columns: Sequence[str],
    tolerance: float = 1e-9,
) -> dict[str, object]:
    left_work = left.copy()
    right_work = right.copy()
    left_work[id_column] = left_work[id_column].astype(str)
    right_work[id_column] = right_work[id_column].astype(str)
    left_work = left_work.sort_values(
        id_column,
        kind="stable",
    ).reset_index(drop=True)
    right_work = right_work.sort_values(
        id_column,
        kind="stable",
    ).reset_index(drop=True)
    checks: dict[str, bool] = {
        "row_count": len(left_work) == len(right_work),
        "identity": (left_work[id_column].tolist() == right_work[id_column].tolist()),
    }
    if checks["row_count"] and checks["identity"]:
        for column in numeric_columns:
            delta = (
                pd.to_numeric(
                    left_work[column],
                    errors="raise",
                )
                - pd.to_numeric(
                    right_work[column],
                    errors="raise",
                )
            ).abs()
            checks[f"numeric:{column}"] = bool((delta <= tolerance).all())
        for column in exact_columns:
            left_values = left_work[column]
            right_values = right_work[column]
            if pd.api.types.is_datetime64_any_dtype(left_values):
                left_values = pd.to_datetime(
                    left_values,
                    utc=True,
                    errors="raise",
                ).astype(str)
                right_values = pd.to_datetime(
                    right_values,
                    utc=True,
                    errors="raise",
                ).astype(str)
            else:
                left_values = left_values.astype(str)
                right_values = right_values.astype(str)
            checks[f"exact:{column}"] = left_values.tolist() == right_values.tolist()
    return {
        "checks": checks,
        "passed": all(checks.values()),
    }


def base_parity(
    *,
    a2: Path,
    dry: Path,
    cash: Path,
    membership: pd.DataFrame,
    a2_cache: A2CandidateCache,
    hourly_cache: HourlyBarCache,
) -> dict[str, object]:
    rows: dict[str, object] = {}
    for universe_id in UNIVERSE_IDS:
        selected_membership = membership.loc[membership["universe_id"] == universe_id]
        source = select_counterfactual_a2_candidates(
            membership=selected_membership,
            universe_id=universe_id,
            cache=a2_cache,
        )
        stored_source = pd.read_parquet(
            dry / "universes" / universe_id / "source-candidates.parquet"
        )
        source_parity = _compare_frames(
            source,
            stored_source,
            id_column="candidate_id",
            numeric_columns=(
                "entry_price",
                "atr14_at_signal",
            ),
            exact_columns=(
                "signal_close",
                "entry_open_time",
                "symbol",
                "family_id",
                "engine_id",
            ),
        )
        frames = hourly_cache.frames_for_candidates(source)
        rebuilt = build_v3_replay_ledgers(
            source,
            hourly_frames=frames,
        )
        stored_candidates = pd.read_parquet(
            dry / "universes" / universe_id / "v3-candidates.parquet"
        )
        candidate_parity = _compare_frames(
            rebuilt.candidates,
            stored_candidates,
            id_column="v3_candidate_id",
            numeric_columns=(
                "entry_price",
                "exit_price",
                "risk_budget",
                "quantity",
                "notional",
                "gross_pnl",
                "fees",
                "net_pnl",
            ),
            exact_columns=(
                "signal_close",
                "entry_open_time",
                "exit_bar_close",
                "symbol",
                "engine_id",
                "exit_reason",
                "bars_held",
            ),
        )
        cost_rows: dict[str, object] = {}
        for cost in COST_MULTIPLIERS:
            route = route_cash_feasible_candidates(
                stored_candidates,
                universe_id=universe_id,
                cost_multiplier=cost,
            )
            stored_trades = pd.read_parquet(
                cash
                / "universes"
                / universe_id
                / f"cost-{int(cost)}x"
                / "cash-routed-trades.parquet"
            )
            route_parity = _compare_frames(
                route.trades,
                stored_trades,
                id_column="source_cash_router_candidate_id",
                numeric_columns=(
                    "quantity",
                    "notional",
                    "risk_budget",
                    "entry_price",
                    "exit_price",
                    "cash_before_entry",
                    "cash_after_entry",
                ),
                exact_columns=(
                    "signal_close",
                    "entry_open_time",
                    "exit_bar_close",
                    "symbol",
                    "engine_id",
                ),
            )
            cost_rows[f"{int(cost)}x"] = {
                **route_parity,
                "minimum_cash": route.minimum_cash,
                "trade_rows": len(route.trades),
            }
        row = {
            "source_candidate_parity": source_parity,
            "v3_candidate_parity": candidate_parity,
            "cash_route_parity": cost_rows,
        }
        row["passed"] = bool(
            source_parity["passed"]
            and candidate_parity["passed"]
            and all(bool(value["passed"]) for value in cost_rows.values())
        )
        rows[universe_id] = row
    return {
        "universes": rows,
        "passed": all(bool(row["passed"]) for row in rows.values()),
    }


def _checkpoint_valid(
    path: Path,
    *,
    run_type: str,
    universe_id: str,
    omitted_value: str,
    cost_multiplier: float,
    candidate_sha256: str,
    cash_manifest_sha256: str,
) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    record = load_json(path)
    expected = (
        record.get("run_type") == run_type
        and record.get("universe_id") == universe_id
        and record.get("omitted_value") == omitted_value
        and float(record.get("cost_multiplier")) == cost_multiplier
        and record.get("candidate_sha256") == candidate_sha256
        and record.get("cash_manifest_sha256") == cash_manifest_sha256
        and record.get("capital_feasible") is True
        and float(record.get("minimum_cash")) >= -1e-6
        and record.get("post_2024_accessed") is False
    )
    return record if expected else None


def execute_checkpoint(
    *,
    path: Path,
    candidates: pd.DataFrame,
    universe_id: str,
    cost_multiplier: float,
    run_type: str,
    omitted_value: str,
    hourly_cache: HourlyBarCache,
    cash_manifest_sha256: str,
    resume: bool,
) -> dict[str, Any]:
    candidate_hash = frame_content_hash(
        candidates,
        columns=(
            "v3_candidate_id",
            "signal_close",
            "entry_open_time",
            "symbol",
            "engine_id",
            "risk_budget",
            "quantity",
            "notional",
            "exit_bar_close",
            "exit_price",
        ),
        sort_by=(
            "entry_open_time",
            "symbol",
            "signal_close",
            "v3_candidate_id",
        ),
    )
    if resume:
        existing = _checkpoint_valid(
            path,
            run_type=run_type,
            universe_id=universe_id,
            omitted_value=omitted_value,
            cost_multiplier=cost_multiplier,
            candidate_sha256=candidate_hash,
            cash_manifest_sha256=cash_manifest_sha256,
        )
        if existing is not None:
            print(
                f"P3E_SENSITIVITY_RESUME={run_type}:"
                f"{universe_id}:{omitted_value}:"
                f"{cost_multiplier}x",
                flush=True,
            )
            return existing
    print(
        f"P3E_SENSITIVITY_RUN_START={run_type}:{universe_id}:{omitted_value}:{cost_multiplier}x",
        flush=True,
    )
    executed = execute_sensitivity(
        candidates=candidates,
        universe_id=universe_id,
        cost_multiplier=cost_multiplier,
        hourly_cache=hourly_cache,
        run_type=run_type,
        omitted_value=omitted_value,
    )
    record = dict(executed.record)
    record["cash_manifest_sha256"] = cash_manifest_sha256
    write_json(path, record)
    print(
        f"P3E_SENSITIVITY_RUN_COMPLETE={run_type}:"
        f"{universe_id}:{omitted_value}:{cost_multiplier}x:"
        f"{record['trade_count']}:{record['net_return']}:"
        f"{record['profit_factor']}:{record['minimum_cash']}",
        flush=True,
    )
    return record


def _run_dir_name(pair: str) -> str:
    return pair.replace("/", "_").replace(":", "_")


def load_or_build_loao_candidates(
    *,
    root: Path,
    builder: CounterfactualMembershipBuilder,
    universe_id: str,
    omitted_pair: str,
    a2_cache: A2CandidateCache,
    hourly_cache: HourlyBarCache,
    resume: bool,
) -> tuple[pd.DataFrame, dict[str, object]]:
    run_root = root / "loao-candidates" / universe_id / _run_dir_name(omitted_pair)
    candidate_path = run_root / "v3-candidates.parquet"
    membership_path = run_root / "counterfactual-membership.parquet"
    resolution_path = run_root / "membership-resolution.csv"
    metadata_path = run_root / "candidate-metadata.json"

    counterfactual = builder.build(
        universe_id=universe_id,
        omitted_pair=omitted_pair,
    )
    if (
        resume
        and candidate_path.is_file()
        and membership_path.is_file()
        and resolution_path.is_file()
        and metadata_path.is_file()
    ):
        metadata = load_json(metadata_path)
        if (
            metadata.get("membership_sha256") == counterfactual.membership_sha256
            and metadata.get("omitted_pair") == omitted_pair
            and metadata.get("universe_id") == universe_id
            and sha256(candidate_path) == metadata.get("candidate_file_sha256")
        ):
            candidates = pd.read_parquet(candidate_path)
            observed_hash = frame_content_hash(
                candidates,
                columns=(
                    "v3_candidate_id",
                    "signal_close",
                    "entry_open_time",
                    "symbol",
                    "engine_id",
                    "risk_budget",
                    "quantity",
                    "notional",
                    "exit_bar_close",
                    "exit_price",
                ),
                sort_by=(
                    "entry_open_time",
                    "symbol",
                    "signal_close",
                    "v3_candidate_id",
                ),
            )
            if observed_hash == metadata.get("candidate_content_sha256"):
                return candidates, metadata

    source = select_counterfactual_a2_candidates(
        membership=counterfactual.membership,
        universe_id=universe_id,
        cache=a2_cache,
    )
    frames = hourly_cache.frames_for_candidates(source)
    ledgers = build_v3_replay_ledgers(
        source,
        hourly_frames=frames,
    )
    candidates = ledgers.candidates
    run_root.mkdir(parents=True, exist_ok=True)
    candidates.to_parquet(
        candidate_path,
        index=False,
        compression="zstd",
    )
    counterfactual.membership.to_parquet(
        membership_path,
        index=False,
        compression="zstd",
    )
    write_rows(
        resolution_path,
        counterfactual.resolution_rows,
    )
    candidate_content_hash = frame_content_hash(
        candidates,
        columns=(
            "v3_candidate_id",
            "signal_close",
            "entry_open_time",
            "symbol",
            "engine_id",
            "risk_budget",
            "quantity",
            "notional",
            "exit_bar_close",
            "exit_price",
        ),
        sort_by=(
            "entry_open_time",
            "symbol",
            "signal_close",
            "v3_candidate_id",
        ),
    )
    metadata: dict[str, object] = {
        "schema_version": "rd18-p3e-loao-candidate-metadata-v1",
        "universe_id": universe_id,
        "omitted_pair": omitted_pair,
        "membership_sha256": counterfactual.membership_sha256,
        "membership_rows": len(counterfactual.membership),
        "source_candidate_rows": len(source),
        "v3_candidate_rows": len(candidates),
        "candidate_content_sha256": candidate_content_hash,
        "candidate_file_sha256": sha256(candidate_path),
        "affected_decisions": counterfactual.affected_decisions,
        "replacement_decisions": (counterfactual.replacement_decisions),
        "capacity_reduction_decisions": (counterfactual.capacity_reduction_decisions),
        "post_2024_accessed": False,
    }
    write_json(metadata_path, metadata)
    return candidates, metadata


def deterministic_manifest(root: Path) -> dict[str, object]:
    rows: list[dict[str, object]] = []
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name == "output-manifest.json":
            continue
        relative = path.relative_to(root).as_posix()
        row: dict[str, object] = {
            "path": relative,
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
        }
        if path.suffix == ".parquet":
            row["rows"] = pq.ParquetFile(path).metadata.num_rows
        elif path.suffix == ".csv":
            row["rows"] = len(read_csv(path))
        rows.append(row)
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(row["sha256"]).encode("ascii"))
        digest.update(b"\n")
    return {
        "schema_version": "rd18-p3e-sensitivity-manifest-v1",
        "files": rows,
        "deterministic_hash": digest.hexdigest(),
        "network_requests": 0,
        "cash_aware_routing_executed": True,
        "loyo_executed": True,
        "loao_executed": True,
        "portfolio_return_calculation_executed": True,
        "performance_reporting_executed": True,
        "thresholds_changed_after_results": False,
        "per_universe_tuning": False,
        "post_2024_accessed": False,
        "production_authorized": False,
    }


def preflight(
    *,
    repo: Path,
    a1: Path,
    a2: Path,
    a3b: Path,
    dry: Path,
    cash: Path,
) -> dict[str, object]:
    gates = verify_p3r(repo)
    upstream = verify_upstream(
        repo=repo,
        a3b=a3b,
        dry=dry,
        cash=cash,
    )
    membership = normalize_base_membership(
        pd.read_csv(
            a3b / "effective-operational-membership.csv",
            low_memory=False,
        )
    )
    omissions = normalize_omission_readiness(
        pd.read_csv(
            a3b / "omission-replacement-readiness.csv",
            low_memory=False,
        )
    )
    applicability = build_applicability(
        cash=cash,
        membership=membership,
    )
    symbols = pair_symbol_map(a1)
    generated = generated_pairs(a2)
    checks = {
        "membership_rows": len(membership) == 5418,
        "omission_rows": len(omissions) == 5418,
        "generated_pairs": len(generated) == 339,
        "symbol_mappings_present": len(symbols) >= 339,
        "loyo_runs": (len(OMITTED_YEARS) * len(UNIVERSE_IDS) * len(COST_MULTIPLIERS) == 36),
        "loao_applicability_nonempty": bool(applicability),
        "named_bchsv_applicable": any(row["omitted_pair"] == "BCHSV-USDT" for row in applicability),
        "named_pepe_applicable": any(row["omitted_pair"] == "PEPE-USDT" for row in applicability),
    }
    return {
        "schema_version": "rd18-p3e-sensitivity-preflight-v1",
        "stage": STAGE,
        "passed": all(checks.values()),
        "checks": checks,
        "upstream": upstream,
        "gate_registry_schema": gates["schema_version"],
        "loyo_run_count": 36,
        "loao_applicability_rows": len(applicability),
        "loao_cost_run_count": (len(applicability) * len(COST_MULTIPLIERS)),
        "applicability_by_universe": {
            universe_id: sum(row["universe_id"] == universe_id for row in applicability)
            for universe_id in UNIVERSE_IDS
        },
        "network_requests": 0,
        "loyo_executed": False,
        "loao_executed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
        "next_stage": "RD18_P3E_SENSITIVITY_MATERIALIZATION",
    }


def execute(
    *,
    repo: Path,
    a1: Path,
    a2: Path,
    a3b: Path,
    dry: Path,
    cash: Path,
    output: Path,
    resume: bool,
) -> dict[str, object]:
    gates = verify_p3r(repo)
    upstream = verify_upstream(
        repo=repo,
        a3b=a3b,
        dry=dry,
        cash=cash,
    )
    output.mkdir(parents=True, exist_ok=True)
    membership = normalize_base_membership(
        pd.read_csv(
            a3b / "effective-operational-membership.csv",
            low_memory=False,
        )
    )
    omissions = normalize_omission_readiness(
        pd.read_csv(
            a3b / "omission-replacement-readiness.csv",
            low_memory=False,
        )
    )
    applicability = build_applicability(
        cash=cash,
        membership=membership,
    )
    write_rows(output / "loao-applicability.csv", applicability)

    symbol_map = pair_symbol_map(a1)
    generated = generated_pairs(a2)
    a2_cache = A2CandidateCache(a2)
    hourly_cache = HourlyBarCache(
        repo=repo,
        symbol_by_pair=symbol_map,
    )
    readiness = IntervalReadinessCache(
        repo=repo,
        symbol_by_pair=symbol_map,
        generated=generated,
    )
    builder = CounterfactualMembershipBuilder(
        base_membership=membership,
        omission_readiness=omissions,
        rankings=build_full_rankings(repo),
        generated=generated,
        readiness=readiness,
    )

    parity = base_parity(
        a2=a2,
        dry=dry,
        cash=cash,
        membership=membership,
        a2_cache=a2_cache,
        hourly_cache=hourly_cache,
    )
    if not parity["passed"]:
        raise RunnerError("base replay parity failed")
    write_json(output / "base-parity.json", parity)

    cash_manifest_hash = EXPECTED_HASHES["cash_manifest"]
    loyo_rows: list[dict[str, Any]] = []
    for universe_id in UNIVERSE_IDS:
        base_candidates = pd.read_parquet(dry / "universes" / universe_id / "v3-candidates.parquet")
        for year in OMITTED_YEARS:
            candidates = filter_loyo_candidates(
                base_candidates,
                omitted_year=year,
            )
            for cost in COST_MULTIPLIERS:
                checkpoint = (
                    output
                    / "checkpoints"
                    / "loyo"
                    / universe_id
                    / str(year)
                    / f"cost-{int(cost)}x.json"
                )
                loyo_rows.append(
                    execute_checkpoint(
                        path=checkpoint,
                        candidates=candidates,
                        universe_id=universe_id,
                        cost_multiplier=cost,
                        run_type="LOYO",
                        omitted_value=str(year),
                        hourly_cache=hourly_cache,
                        cash_manifest_sha256=cash_manifest_hash,
                        resume=resume,
                    )
                )

    loao_rows: list[dict[str, Any]] = []
    loao_metadata_rows: list[dict[str, object]] = []
    for applicability_row in applicability:
        universe_id = str(applicability_row["universe_id"])
        omitted_pair = str(applicability_row["omitted_pair"])
        candidates, metadata = load_or_build_loao_candidates(
            root=output,
            builder=builder,
            universe_id=universe_id,
            omitted_pair=omitted_pair,
            a2_cache=a2_cache,
            hourly_cache=hourly_cache,
            resume=resume,
        )
        loao_metadata_rows.append(metadata)
        for cost in COST_MULTIPLIERS:
            checkpoint = (
                output
                / "checkpoints"
                / "loao"
                / universe_id
                / _run_dir_name(omitted_pair)
                / f"cost-{int(cost)}x.json"
            )
            record = execute_checkpoint(
                path=checkpoint,
                candidates=candidates,
                universe_id=universe_id,
                cost_multiplier=cost,
                run_type="LOAO",
                omitted_value=omitted_pair,
                hourly_cache=hourly_cache,
                cash_manifest_sha256=cash_manifest_hash,
                resume=resume,
            )
            record["named_omission"] = bool(applicability_row["named_omission"])
            record["membership_sha256"] = metadata["membership_sha256"]
            record["affected_decisions"] = metadata["affected_decisions"]
            record["replacement_decisions"] = metadata["replacement_decisions"]
            record["capacity_reduction_decisions"] = metadata["capacity_reduction_decisions"]
            loao_rows.append(record)

    corrected_base_rows = read_csv(cash / "corrected-base-run-summary.csv")
    named_rows = [row for row in loao_rows if str(row["omitted_value"]) in NAMED_OMISSIONS]
    sensitivity = sensitivity_gate_summary(
        loyo_rows=loyo_rows,
        loao_rows=loao_rows,
        named_rows=named_rows,
        corrected_base_rows=corrected_base_rows,
    )
    base_classification = upstream["corrected_base_classification"]
    if not isinstance(base_classification, Mapping):
        raise RunnerError("corrected base classification invalid")
    precedence_outcome = (
        "WORST_UNIVERSE_ECONOMIC_FAILURE"
        if base_classification.get("base_economic_gates_passed") is False
        else (
            "SENSITIVITY_CONCENTRATION_FAILURE"
            if sensitivity["passed"] is False
            else "ROBUSTNESS_PASS"
        )
    )

    write_rows(output / "loyo-results.csv", loyo_rows)
    write_rows(output / "loao-results.csv", loao_rows)
    write_rows(
        output / "loao-candidate-metadata.csv",
        loao_metadata_rows,
    )
    write_json(
        output / "sensitivity-gate-evaluation.json",
        sensitivity,
    )
    report = {
        "schema_version": "rd18-p3e-sensitivity-report-v1",
        "stage": STAGE,
        "decision": DECISION,
        "passed": True,
        "execution_status": "COMPLETE",
        "upstream": upstream,
        "base_parity": parity,
        "loyo_run_count": len(loyo_rows),
        "loao_applicability_rows": len(applicability),
        "loao_run_count": len(loao_rows),
        "loyo_executed": True,
        "loao_executed": True,
        "cash_aware_routing_executed": True,
        "portfolio_return_calculation_executed": True,
        "performance_reporting_executed": True,
        "sensitivity_gate_evaluation": sensitivity,
        "corrected_base_classification": base_classification,
        "gate_registry_schema": gates["schema_version"],
        "decision_precedence_outcome": precedence_outcome,
        "final_advancement_eligible": False,
        "final_decision_ready": True,
        "final_decision_made": False,
        "thresholds_changed_after_results": False,
        "per_universe_tuning": False,
        "post_hoc_trade_deletion": False,
        "network_requests": 0,
        "post_2024_accessed": False,
        "production_authorized": False,
        "next_stage": NEXT_STAGE,
    }
    write_json(
        output / "rd18-p3e-loyo-loao-sensitivity-report-v1.json",
        report,
    )
    write_json(
        output / "output-manifest.json",
        deterministic_manifest(output),
    )
    return report


def main() -> int:
    args = parser().parse_args()
    if not args.preflight_only and not args.execute:
        raise SystemExit("Use --preflight-only or --execute")
    repo = args.repo_root.resolve()
    common = {
        "repo": repo,
        "a1": args.a1_runtime.resolve(),
        "a2": args.a2_runtime.resolve(),
        "a3b": args.a3b_runtime.resolve(),
        "dry": args.dry_run_runtime.resolve(),
        "cash": args.cash_runtime.resolve(),
    }
    if args.preflight_only:
        result = preflight(**common)
    else:
        result = execute(
            **common,
            output=args.output_dir.resolve(),
            resume=bool(args.resume),
        )
    print(
        json.dumps(
            json_ready(result),
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
        )
    )
    return 0 if result.get("passed") is True else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RunnerError, SensitivityError) as exc:
        print(f"P3E_SENSITIVITY_ERROR={exc}", file=sys.stderr)
        raise SystemExit(2) from exc
