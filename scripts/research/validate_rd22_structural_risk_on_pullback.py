from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = Path("data/research/rd22_p2_runtime")
EXPECTED_FILES = {
    "input-and-conformance-audit.json",
    "btc-daily-ema200-regime.csv",
    "candidate-metrics.csv",
    "year-metrics.csv",
    "routing-summary.csv",
    "trade-ledger.csv",
    "daily-equity.csv",
    "concentration-diagnostics.csv",
    "leave-one-asset-out.csv",
    "leave-one-year-out.csv",
    "break-even-cost-multiplier.csv",
    "candidate-hard-gates.csv",
    "finalist-freeze.json",
    "rd22-p2-discovery-report-v1.json",
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
    report = load_json(output / "rd22-p2-discovery-report-v1.json")
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

    allowed = {
        "RD22_P2_STRUCTURAL_RISK_ON_PULLBACK_FINALIST_SELECTED",
        "RD22_P2_STRUCTURAL_RISK_ON_PULLBACK_REJECTED_CLOSE_TREND_PULLBACK_FAMILY",
    }
    if report.get("decision") not in allowed:
        raise ValidationError("report decision invalid")
    if finalist.get("decision") != report.get("decision"):
        raise ValidationError("finalist/report decision mismatch")
    if report.get("fixed_horizon_hours") != 168:
        raise ValidationError("fixed horizon drifted")
    if report.get("market_regime_gate") != "BTC_COMPLETED_DAILY_CLOSE_GT_EMA200":
        raise ValidationError("market regime gate drifted")
    if report.get("ema_span_days") != 200:
        raise ValidationError("EMA span drifted")
    if report.get("parameter_search_dimensions") != 1:
        raise ValidationError("unexpected research-dimension count")
    if report.get("selection_data") != "DISCOVERY_2019_2021_ONLY":
        raise ValidationError("selection-data declaration drifted")
    if report.get("2022_2023_used_for_selection") is not False:
        raise ValidationError("2022/2023 used for selection")
    if report.get("2024_accessed") is not False:
        raise ValidationError("2024 accessed")
    if report.get("post_2024_accessed") is not False:
        raise ValidationError("post-2024 accessed")
    if report.get("production_authorized") is not False:
        raise ValidationError("production authorized")
    if audit.get("2022_2023_used_for_selection") is not False:
        raise ValidationError("audit says 2022/2023 used for selection")
    if audit.get("2024_accessed") is not False:
        raise ValidationError("audit says 2024 accessed")

    metrics = pd.read_csv(output / "candidate-metrics.csv", low_memory=False)
    years = pd.read_csv(output / "year-metrics.csv", low_memory=False)
    trades = pd.read_csv(output / "trade-ledger.csv", low_memory=False)
    daily = pd.read_csv(output / "daily-equity.csv", low_memory=False)
    gates = pd.read_csv(output / "candidate-hard-gates.csv", low_memory=False)
    regime = pd.read_csv(output / "btc-daily-ema200-regime.csv", low_memory=False)

    if set(metrics["horizon_hours"].astype(int).unique()) != {168}:
        raise ValidationError("metric horizon differs from 168")
    if len(metrics) != 6:
        raise ValidationError(f"expected 6 metric rows, found {len(metrics)}")
    if set(metrics["universe_id"].astype(str).unique()) != {"C2", "D2", "E2"}:
        raise ValidationError("universe set drifted")
    if set(metrics["cost_multiplier"].astype(float).unique()) != {1.0, 2.0}:
        raise ValidationError("cost matrix drifted")
    if bool(truth_series(metrics["negative_cash_observed"]).any()):
        raise ValidationError("negative cash observed")

    if len(years) and int(pd.to_numeric(years["year"], errors="raise").max()) > 2021:
        raise ValidationError("year metrics crossed into 2022")
    for frame, column in (
        (trades, "entry_time"),
        (trades, "exit_time"),
        (daily, "timestamp"),
    ):
        values = pd.to_datetime(frame[column], utc=True, errors="raise")
        if bool((values >= pd.Timestamp("2022-01-01T00:00:00Z")).any()):
            raise ValidationError(f"{column} crossed into 2022")

    available = pd.to_datetime(regime["available_time"], utc=True, errors="raise")
    if bool((available >= pd.Timestamp("2022-01-01T00:00:00Z")).any()):
        raise ValidationError("regime schedule crossed into 2022")
    if not bool(truth_series(regime["regime_ready"]).any()):
        raise ValidationError("regime never became ready")
    if not bool(truth_series(regime["regime_on"]).any()):
        raise ValidationError("regime never became risk-on")

    gate_pass = bool(truth_series(gates["passed"]).all())
    if bool(report.get("hard_gates_passed")) != gate_pass:
        raise ValidationError("report/gate decision mismatch")
    selected = finalist.get("selected_horizon_hours")
    if report["decision"] == "RD22_P2_STRUCTURAL_RISK_ON_PULLBACK_FINALIST_SELECTED":
        if selected != 168:
            raise ValidationError("selected finalist horizon must be 168")
        if not gate_pass:
            raise ValidationError("finalist selected despite failed hard gate")
    else:
        if selected is not None:
            raise ValidationError("rejected candidate contains selected horizon")
        if gate_pass:
            raise ValidationError("candidate rejected despite passing hard gates")
        if report.get("next_stage") != "RD23_INDEPENDENT_SETUP_FAMILY_REQUIRED":
            raise ValidationError("rejected family did not advance to independent setup")

    if manifest.get("2022_2023_used_for_selection") is not False:
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
        "hard_gates_passed": gate_pass,
        "candidate_metric_rows": len(metrics),
        "trade_ledger_rows": len(trades),
        "2022_2023_used_for_selection": False,
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
        print(f"RD22_VALIDATION_ERROR={exc}", file=sys.stderr)
        raise SystemExit(2) from exc
