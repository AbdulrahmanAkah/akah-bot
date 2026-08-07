from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]

OUTPUT = Path("data/research/rd21_p2_runtime")
EXPECTED_FILES = {
    "input-and-conformance-audit.json",
    "variant-metrics.csv",
    "year-metrics.csv",
    "routing-summary.csv",
    "trade-ledger.csv",
    "daily-equity.csv",
    "concentration-diagnostics.csv",
    "leave-one-asset-out.csv",
    "leave-one-year-out.csv",
    "break-even-cost-multiplier.csv",
    "variant-hard-gates.csv",
    "selection-ranking.csv",
    "finalist-freeze.json",
    "rd21-p2-discovery-report-v1.json",
}


class ValidationError(RuntimeError):
    pass


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser()
    value.add_argument("--repo-root", type=Path, default=ROOT)
    value.add_argument("--offline", action="store_true")
    return value


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValidationError(f"JSON object expected: {path}")
    return value


def truth_series(values: pd.Series) -> pd.Series:
    if pd.api.types.is_bool_dtype(values):
        return values.astype(bool)
    normalized = values.astype(str).str.strip().str.lower()
    if bool(~normalized.isin({"true", "false", "1", "0"}).any()):
        raise ValidationError("invalid boolean series")
    return normalized.isin({"true", "1"})


def validate(repo: Path) -> dict[str, Any]:
    output = repo / OUTPUT
    manifest = load_json(output / "output-manifest.json")
    report = load_json(output / "rd21-p2-discovery-report-v1.json")
    finalist = load_json(output / "finalist-freeze.json")
    audit = load_json(output / "input-and-conformance-audit.json")

    files = manifest.get("files")
    if not isinstance(files, list):
        raise ValidationError("manifest files invalid")
    names = {str(row.get("path")) for row in files if isinstance(row, dict)}
    if names != EXPECTED_FILES:
        raise ValidationError(
            f"manifest files differ: expected={sorted(EXPECTED_FILES)}, observed={sorted(names)}"
        )
    for row in files:
        if not isinstance(row, dict):
            raise ValidationError("manifest row invalid")
        name = str(row["path"])
        path = output / name
        if sha256(path) != str(row["sha256"]):
            raise ValidationError(f"manifest hash mismatch: {name}")
        if path.stat().st_size != int(row["bytes"]):
            raise ValidationError(f"manifest byte count mismatch: {name}")

    allowed_decisions = {
        "RD21_P2_HORIZON_DISCOVERY_CLOSED_NO_FINALIST",
        "RD21_P2_HORIZON_DISCOVERY_FINALIST_SELECTED",
    }
    if report.get("decision") not in allowed_decisions:
        raise ValidationError("report decision invalid")
    if finalist.get("decision") != report.get("decision"):
        raise ValidationError("finalist/report decision mismatch")
    if report.get("selection_data") != "DISCOVERY_2019_2021_ONLY":
        raise ValidationError("selection-data declaration drifted")
    if report.get("2022_2023_used_for_variant_selection") is not False:
        raise ValidationError("2022/2023 used for discovery selection")
    if report.get("2024_accessed") is not False:
        raise ValidationError("2024 accessed")
    if report.get("post_2024_accessed") is not False:
        raise ValidationError("post-2024 accessed")
    if report.get("production_authorized") is not False:
        raise ValidationError("production authorized")
    if report.get("variant_count") != 3:
        raise ValidationError("variant count drifted")
    if report.get("screened_values_hours") != [24, 72, 168]:
        raise ValidationError("screened horizon values drifted")
    if report.get("parameter_search_dimensions") != 1:
        raise ValidationError("more than one search dimension entered discovery")
    if audit.get("2022_2023_used_for_variant_selection") is not False:
        raise ValidationError("audit says 2022/2023 used for selection")
    if audit.get("2024_accessed") is not False:
        raise ValidationError("audit says 2024 accessed")

    metrics = pd.read_csv(output / "variant-metrics.csv", low_memory=False)
    years = pd.read_csv(output / "year-metrics.csv", low_memory=False)
    trades = pd.read_csv(output / "trade-ledger.csv", low_memory=False)
    daily = pd.read_csv(output / "daily-equity.csv", low_memory=False)
    gates = pd.read_csv(output / "variant-hard-gates.csv", low_memory=False)
    ranking = pd.read_csv(output / "selection-ranking.csv", low_memory=False)

    if set(metrics["horizon_hours"].astype(int).unique()) != {24, 72, 168}:
        raise ValidationError("metric horizon matrix differs")
    expected_runs = 3 * 3 * 2
    if len(metrics) != expected_runs:
        raise ValidationError(f"expected {expected_runs} metric rows, found {len(metrics)}")
    if set(metrics["universe_id"].astype(str).unique()) != {"C2", "D2", "E2"}:
        raise ValidationError("universe set drifted")
    if set(metrics["cost_multiplier"].astype(float).unique()) != {1.0, 2.0}:
        raise ValidationError("cost matrix drifted")
    if bool(truth_series(metrics["negative_cash_observed"]).any()):
        raise ValidationError("negative cash observed")

    if len(years) and int(pd.to_numeric(years["year"], errors="raise").max()) > 2021:
        raise ValidationError("year metrics crossed into 2022")
    for frame, column in ((trades, "entry_time"), (trades, "exit_time"), (daily, "timestamp")):
        values = pd.to_datetime(frame[column], utc=True, errors="raise")
        if bool((values >= pd.Timestamp("2022-01-01T00:00:00Z")).any()):
            raise ValidationError(f"{column} crossed into 2022")

    if len(ranking) != 3:
        raise ValidationError("selection ranking must have exactly three rows")
    if set(ranking["horizon_hours"].astype(int)) != {24, 72, 168}:
        raise ValidationError("selection ranking horizon set differs")
    pass_map = {
        int(row.horizon_hours): str(row.hard_gates_passed).strip().lower() in {"true", "1"}
        for row in ranking.itertuples(index=False)
    }
    gate_pass_map = {
        horizon: bool(
            truth_series(
                gates.loc[
                    gates["horizon_hours"].astype(int) == horizon,
                    "passed",
                ]
            ).all()
        )
        for horizon in (24, 72, 168)
    }
    if pass_map != gate_pass_map:
        raise ValidationError("ranking hard-gate flags disagree with gate ledger")

    selected = finalist.get("selected_horizon_hours")
    if report["decision"] == "RD21_P2_HORIZON_DISCOVERY_FINALIST_SELECTED":
        if selected not in {24, 72, 168}:
            raise ValidationError("selected finalist horizon invalid")
        top = ranking.iloc[0]
        if str(top["hard_gates_passed"]).strip().lower() not in {"true", "1"}:
            raise ValidationError("selected ranking leader did not pass hard gates")
        if int(top["horizon_hours"]) != int(selected):
            raise ValidationError("selected finalist differs from ranking leader")
    else:
        if selected is not None:
            raise ValidationError("no-finalist decision contains selected horizon")
        if bool(truth_series(ranking["hard_gates_passed"]).any()):
            raise ValidationError("no-finalist decision despite a passing horizon")

    if manifest.get("2022_2023_used_for_variant_selection") is not False:
        raise ValidationError("manifest selection contamination flag drifted")
    if manifest.get("2024_accessed") is not False:
        raise ValidationError("manifest says 2024 accessed")
    if manifest.get("post_2024_accessed") is not False:
        raise ValidationError("manifest says post-2024 accessed")
    if manifest.get("production_authorized") is not False:
        raise ValidationError("manifest says production authorized")

    return {
        "passed": True,
        "decision": report["decision"],
        "selected_horizon_hours": selected,
        "variant_metric_rows": len(metrics),
        "trade_ledger_rows": len(trades),
        "2022_2023_used_for_variant_selection": False,
        "2024_accessed": False,
        "production_authorized": False,
    }


def main() -> int:
    args = parser().parse_args()
    result = validate(args.repo_root.resolve())
    print(json.dumps(result, indent=2, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValidationError as exc:
        print(f"RD21_VALIDATION_ERROR={exc}", file=sys.stderr)
        raise SystemExit(2) from exc
