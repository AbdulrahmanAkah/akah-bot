from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd

OUTPUT = Path("data/research/rd24_p2_runtime")
PROTOCOL = Path("data/research/rd24_p2/rd24-p2-parallel-minimal-portfolio-protocol-v1.json")
QUALIFIED_FAMILIES = (
    "MOMENTUM_BREAKOUT",
    "VOLATILITY_EXPANSION",
    "RELATIVE_STRENGTH_ROTATION",
    "MOMENTUM_ACCELERATION",
)
EXPECTED_OUTPUTS = (
    "input-and-conformance-audit.json",
    "portfolio-run-metrics.csv",
    "portfolio-period-metrics.csv",
    "routing-summary.csv",
    "trade-ledger.csv",
    "daily-equity.csv",
    "concentration-diagnostics.csv",
    "break-even-cost-multiplier.csv",
    "hard-gate-evaluation.csv",
    "family-attribution.csv",
    "union-leave-one-family-out.csv",
    "portfolio-qualified-family-freeze.json",
    "rd24-p2-parallel-minimal-portfolio-report-v1.json",
)


class ValidationError(RuntimeError):
    pass


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser()
    value.add_argument("--repo-root", type=Path, required=True)
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


def _bool_series(frame: pd.DataFrame, column: str) -> pd.Series:
    value = frame[column]
    if value.dtype == bool:
        return value
    normalized = value.astype(str).str.strip().str.lower()
    if bool(~normalized.isin({"true", "false"}).any()):
        raise ValidationError(f"invalid boolean column {column}")
    return normalized == "true"


def validate_manifest(repo: Path) -> dict[str, Any]:
    output = repo / OUTPUT
    manifest = load_json(output / "output-manifest.json")
    if manifest.get("schema_version") != "rd24-p2-output-manifest-v1":
        raise ValidationError("manifest schema drifted")
    files = manifest.get("files")
    if not isinstance(files, list):
        raise ValidationError("manifest files missing")
    by_name = {str(item["path"]): item for item in files if isinstance(item, dict)}
    if set(by_name) != set(EXPECTED_OUTPUTS):
        raise ValidationError("manifest output set drifted")
    for name in EXPECTED_OUTPUTS:
        path = output / name
        if not path.is_file():
            raise ValidationError(f"output missing: {path}")
        item = by_name[name]
        if path.stat().st_size != int(item["bytes"]):
            raise ValidationError(f"output byte size drifted: {name}")
        if sha256(path) != str(item["sha256"]):
            raise ValidationError(f"output hash drifted: {name}")
    return manifest


def validate_trade_ledger(trades: pd.DataFrame) -> None:
    if trades.empty:
        raise ValidationError("trade ledger is empty")
    required = {
        "portfolio_id",
        "universe_id",
        "cost_multiplier",
        "pair",
        "signal_time",
        "entry_time",
        "exit_time",
        "holding_hours",
        "entry_notional",
        "exit_notional",
        "entry_cost",
        "exit_cost",
        "gross_pnl",
        "net_pnl",
        "support_families",
    }
    missing = sorted(required.difference(trades.columns))
    if missing:
        raise ValidationError(f"trade ledger columns missing: {missing}")
    signal = pd.to_datetime(trades["signal_time"], utc=True, errors="raise")
    entry = pd.to_datetime(trades["entry_time"], utc=True, errors="raise")
    exit_ = pd.to_datetime(trades["exit_time"], utc=True, errors="raise")
    if bool((signal >= pd.Timestamp("2022-01-01T00:00:00Z")).any()):
        raise ValidationError("trade signal crossed into 2022")
    if bool((entry >= pd.Timestamp("2022-01-01T00:00:00Z")).any()):
        raise ValidationError("trade entry crossed into 2022")
    if bool((exit_ > pd.Timestamp("2022-01-01T00:00:00Z")).any()):
        raise ValidationError("trade exit crossed beyond RD24 selection boundary")
    if bool(((entry - signal) != pd.Timedelta(hours=1)).any()):
        raise ValidationError("entry is not exact next-hour open")
    if bool(((exit_ - entry) != pd.Timedelta(hours=168)).any()):
        raise ValidationError("holding horizon is not exactly 168h")
    if bool((pd.to_numeric(trades["holding_hours"], errors="raise") != 168).any()):
        raise ValidationError("holding_hours column drifted")
    gross = pd.to_numeric(trades["gross_pnl"], errors="raise").astype(float)
    entry_cost = pd.to_numeric(trades["entry_cost"], errors="raise").astype(float)
    exit_cost = pd.to_numeric(trades["exit_cost"], errors="raise").astype(float)
    net = pd.to_numeric(trades["net_pnl"], errors="raise").astype(float)
    if not bool(
        np_allclose(
            net.to_numpy(),
            (gross - entry_cost - exit_cost).to_numpy(),
        )
    ):
        raise ValidationError("trade net PnL arithmetic drifted")
    costs = sorted(set(pd.to_numeric(trades["cost_multiplier"], errors="raise").astype(float)))
    if costs != [1.0, 2.0]:
        raise ValidationError(f"cost multiplier set drifted: {costs}")


def np_allclose(left: Any, right: Any) -> bool:
    import numpy as np

    return bool(np.allclose(left, right, rtol=1e-10, atol=1e-8))


def validate_freeze_and_gates(
    *,
    freeze: dict[str, Any],
    gates: pd.DataFrame,
    report: dict[str, Any],
) -> None:
    qualified = freeze.get("portfolio_qualified_families")
    if not isinstance(qualified, list):
        raise ValidationError("portfolio-qualified family list missing")
    if any(family not in QUALIFIED_FAMILIES for family in qualified):
        raise ValidationError("unexpected portfolio-qualified family")
    if qualified != report.get("portfolio_qualified_families"):
        raise ValidationError("report/freeze qualified family mismatch")

    gates = gates.copy()
    gates["passed"] = _bool_series(gates, "passed")
    standalone = gates.loc[gates["portfolio_id"].isin(QUALIFIED_FAMILIES)]
    computed: list[str] = []
    for family in QUALIFIED_FAMILIES:
        family_rows = standalone.loc[standalone["portfolio_id"] == family]
        if len(family_rows) != 33:
            raise ValidationError(
                f"standalone hard-gate cardinality drifted for {family}: {len(family_rows)}"
            )
        if bool(family_rows["passed"].all()):
            computed.append(family)
    if computed != qualified:
        raise ValidationError(f"portfolio-qualified freeze mismatch: {computed} != {qualified}")

    union_expected = len(qualified) >= 2
    if freeze.get("qualified_union_executed") is not union_expected:
        raise ValidationError("qualified union execution flag drifted")

    union_pass = freeze.get("qualified_union_hard_gates_passed")
    if union_expected:
        union_rows = gates.loc[gates["portfolio_id"] == "UNION_PORTFOLIO_QUALIFIED"]
        if len(union_rows) != 36:
            raise ValidationError("qualified union hard-gate cardinality drifted")
        if union_pass is not bool(union_rows["passed"].all()):
            raise ValidationError("qualified union gate result drifted")
    elif union_pass is not False:
        raise ValidationError("union pass cannot be true without two families")


def main() -> int:
    args = parser().parse_args()
    if not args.offline:
        raise ValidationError("--offline is required")
    repo = args.repo_root.resolve()
    output = repo / OUTPUT

    if not (repo / PROTOCOL).is_file():
        raise ValidationError("RD24 frozen protocol missing")
    protocol = load_json(repo / PROTOCOL)
    if protocol.get("starting_commit") != ("f0120353dac3a3ac47ad44039c749c4e46cf2069"):
        raise ValidationError("protocol parent drifted")

    manifest = validate_manifest(repo)
    report = load_json(output / "rd24-p2-parallel-minimal-portfolio-report-v1.json")
    freeze = load_json(output / "portfolio-qualified-family-freeze.json")

    if manifest.get("decision") != report.get("decision"):
        raise ValidationError("manifest/report decision mismatch")
    if report.get("passed") is not True:
        raise ValidationError("RD24 report did not pass technical validation")
    for field in (
        "2022_2023_used_for_selection",
        "2024_accessed",
        "post_2024_accessed",
        "production_authorized",
    ):
        if report.get(field) is not False:
            raise ValidationError(f"prohibited report flag is true: {field}")

    metrics = pd.read_csv(output / "portfolio-run-metrics.csv")
    periods = pd.read_csv(output / "portfolio-period-metrics.csv")
    routing = pd.read_csv(output / "routing-summary.csv")
    trades = pd.read_csv(output / "trade-ledger.csv", low_memory=False)
    daily = pd.read_csv(output / "daily-equity.csv", low_memory=False)
    gates = pd.read_csv(output / "hard-gate-evaluation.csv")

    if metrics.empty or periods.empty or routing.empty or daily.empty:
        raise ValidationError("required RD24 metric output is empty")
    validate_trade_ledger(trades)

    daily_time = pd.to_datetime(daily["timestamp"], utc=True, errors="raise")
    if bool((daily_time >= pd.Timestamp("2022-01-01T00:00:00Z")).any()):
        raise ValidationError("daily equity crossed into 2022")
    cash = pd.to_numeric(daily["cash"], errors="raise").astype(float)
    if bool((cash < -1e-8).any()):
        raise ValidationError("negative daily cash observed")

    expected_standalone_runs = len(QUALIFIED_FAMILIES) * 3 * 2
    standalone_metrics = metrics.loc[metrics["portfolio_id"].isin(QUALIFIED_FAMILIES)]
    if len(standalone_metrics) != expected_standalone_runs:
        raise ValidationError("standalone run count drifted")
    validate_freeze_and_gates(freeze=freeze, gates=gates, report=report)

    if freeze.get("qualified_union_executed"):
        lofo = pd.read_csv(output / "union-leave-one-family-out.csv")
        qualified = freeze["portfolio_qualified_families"]
        expected_lofo = len(qualified) * 3 * 2
        if len(lofo) != expected_lofo:
            raise ValidationError("leave-one-family-out run count drifted")

    print(
        json.dumps(
            {
                "status": "PASS",
                "decision": report["decision"],
                "portfolio_qualified_families": report["portfolio_qualified_families"],
                "qualified_union_hard_gates_passed": report["qualified_union_hard_gates_passed"],
                "trade_ledger_rows": len(trades),
                "2022_2023_used_for_selection": False,
                "2024_accessed": False,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValidationError as exc:
        print(f"RD24_VALIDATION_ERROR={exc}", file=sys.stderr)
        raise SystemExit(2) from exc
