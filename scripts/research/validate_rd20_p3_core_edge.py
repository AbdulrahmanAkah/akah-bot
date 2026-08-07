from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from spotbot.research.rd20_p3_core_edge import (  # noqa: E402
    CANDIDATE_ID,
    INITIAL_EQUITY,
)

OUTPUT = Path("data/research/rd20_p3_runtime")
EXPECTED_FILES = {
    "input-and-conformance-audit.json",
    "forward-horizon-diagnostics.csv",
    "run-metrics.csv",
    "year-metrics.csv",
    "partition-metrics.csv",
    "routing-summary.csv",
    "trade-ledger.csv",
    "daily-equity.csv",
    "concentration-diagnostics.csv",
    "leave-one-asset-out.csv",
    "leave-one-year-out.csv",
    "break-even-cost-multiplier.csv",
    "hard-gate-evaluation.csv",
    "rd20-p3-core-edge-report-v1.json",
}


class ValidationError(RuntimeError):
    pass


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser()
    value.add_argument("--repo-root", type=Path, required=True)
    value.add_argument("--expected-freeze-commit", required=True)
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


def _truth(values: pd.Series) -> pd.Series:
    if pd.api.types.is_bool_dtype(values):
        return values.astype(bool)
    normalized = values.astype(str).str.strip().str.lower()
    allowed = {"true", "false", "1", "0"}
    if bool(~normalized.isin(allowed).any()):
        raise ValidationError("invalid boolean column")
    return normalized.isin({"true", "1"})


def manifest_digest(files: list[dict[str, object]]) -> str:
    digest = hashlib.sha256()
    for row in sorted(files, key=lambda value: str(value["path"])):
        digest.update(str(row["path"]).encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(row["sha256"]).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def main() -> int:
    args = parser().parse_args()
    repo = args.repo_root.resolve()
    output = repo / OUTPUT
    manifest = load_json(output / "output-manifest.json")
    report = load_json(output / "rd20-p3-core-edge-report-v1.json")
    audit = load_json(output / "input-and-conformance-audit.json")

    raw_files = manifest.get("files")
    if not isinstance(raw_files, list):
        raise ValidationError("manifest files invalid")
    names = {str(row.get("path", "")) for row in raw_files if isinstance(row, dict)}
    if names != EXPECTED_FILES:
        raise ValidationError(
            f"manifest output set drift: expected={sorted(EXPECTED_FILES)} observed={sorted(names)}"
        )
    normalized = []
    for row in raw_files:
        if not isinstance(row, dict):
            raise ValidationError("manifest row invalid")
        name = str(row["path"])
        path = output / name
        if not path.is_file():
            raise ValidationError(f"manifest output missing: {path}")
        if path.stat().st_size != int(row["bytes"]):
            raise ValidationError(f"manifest byte mismatch: {name}")
        if sha256(path) != str(row["sha256"]):
            raise ValidationError(f"manifest hash mismatch: {name}")
        normalized.append(
            {
                "path": name,
                "bytes": int(row["bytes"]),
                "sha256": str(row["sha256"]),
            }
        )
    if manifest.get("deterministic_hash") != manifest_digest(normalized):
        raise ValidationError("manifest deterministic hash mismatch")
    if manifest.get("candidate_id") != CANDIDATE_ID:
        raise ValidationError("manifest candidate drift")
    for key in ("2024_accessed", "post_2024_accessed", "production_authorized"):
        if manifest.get(key) is not False:
            raise ValidationError(f"manifest sealed/production flag drift: {key}")

    if report.get("candidate_id") != CANDIDATE_ID:
        raise ValidationError("report candidate drift")
    if report.get("freeze_commit") != args.expected_freeze_commit:
        raise ValidationError("report freeze commit drift")
    if report.get("economic_replay_executed") is not True:
        raise ValidationError("economic replay flag false")
    if report.get("return_calculation_executed") is not True:
        raise ValidationError("return calculation flag false")
    if report.get("2024_accessed") is not False:
        raise ValidationError("report says 2024 accessed")
    if report.get("post_2024_accessed") is not False:
        raise ValidationError("report says post-2024 accessed")
    if report.get("production_authorized") is not False:
        raise ValidationError("production unexpectedly authorized")

    parity = audit.get("signal_event_feature_parity")
    if not isinstance(parity, dict) or parity.get("full_signal_event_feature_parity") is not True:
        raise ValidationError("full frozen signal parity is not true")
    if int(parity.get("signal_rows_checked", -1)) != 24560:
        raise ValidationError("signal parity row count drift")

    metrics = pd.read_csv(output / "run-metrics.csv")
    routes = pd.read_csv(output / "routing-summary.csv")
    trades = pd.read_csv(output / "trade-ledger.csv")
    daily = pd.read_csv(output / "daily-equity.csv")
    gates = pd.read_csv(output / "hard-gate-evaluation.csv")
    concentration = pd.read_csv(output / "concentration-diagnostics.csv")
    break_even = pd.read_csv(output / "break-even-cost-multiplier.csv")
    forward = pd.read_csv(output / "forward-horizon-diagnostics.csv")
    years = pd.read_csv(output / "year-metrics.csv")
    partitions = pd.read_csv(output / "partition-metrics.csv")

    if len(metrics) != 6:
        raise ValidationError(f"expected 6 run metrics, found {len(metrics)}")
    identities = set(
        zip(
            metrics["universe_id"].astype(str),
            pd.to_numeric(metrics["cost_multiplier"]).astype(float),
            strict=True,
        )
    )
    expected_identities = {
        (universe, multiplier) for universe in ("C2", "D2", "E2") for multiplier in (1.0, 2.0)
    }
    if identities != expected_identities:
        raise ValidationError("run metric identities drift")
    if bool(_truth(metrics["negative_cash_observed"]).any()):
        raise ValidationError("negative cash observed")
    if bool(pd.to_numeric(routes["min_cash"], errors="raise").lt(-1e-7).any()):
        raise ValidationError("routing min cash below zero")
    if bool(
        pd.to_numeric(routes["max_admission_gross_fraction"], errors="raise").gt(0.900000001).any()
    ):
        raise ValidationError("admission gross exposure exceeded 90%")

    trades["entry_time"] = pd.to_datetime(trades["entry_time"], utc=True, errors="raise")
    trades["exit_time"] = pd.to_datetime(trades["exit_time"], utc=True, errors="raise")
    daily["timestamp"] = pd.to_datetime(daily["timestamp"], utc=True, errors="raise")
    if bool((trades["entry_time"] >= pd.Timestamp("2024-01-01T00:00:00Z")).any()):
        raise ValidationError("2024 trade entry detected")
    if bool((trades["exit_time"] >= pd.Timestamp("2024-01-01T00:00:00Z")).any()):
        raise ValidationError("2024 trade exit detected")
    if bool((daily["timestamp"] >= pd.Timestamp("2024-01-01T00:00:00Z")).any()):
        raise ValidationError("2024 daily equity detected")

    for raw in metrics.to_dict(orient="records"):
        run_id = str(raw["run_id"])
        ledger = trades.loc[trades["run_id"].astype(str) == run_id]
        if len(ledger) != int(raw["trade_count"]):
            raise ValidationError(f"trade count mismatch: {run_id}")
        pnl = float(pd.to_numeric(ledger["net_pnl"], errors="raise").sum())
        final_equity = float(raw["final_equity"])
        if not math.isclose(
            final_equity,
            INITIAL_EQUITY + pnl,
            rel_tol=1e-9,
            abs_tol=1e-5,
        ):
            raise ValidationError(f"final equity / closed trade PnL mismatch: {run_id}")

    hard_pass = bool(_truth(gates["passed"]).all())
    if bool(report.get("hard_gates_passed")) != hard_pass:
        raise ValidationError("report hard-gate decision mismatch")
    cross_review = bool(
        concentration.loc[
            pd.to_numeric(concentration["cost_multiplier"]) == 2.0,
            "cross_venue_trade_review_triggered",
        ]
        .pipe(_truth)
        .any()
    )
    if bool(report.get("cross_venue_contribution_review_required")) != cross_review:
        raise ValidationError("report cross-venue trigger mismatch")

    decision = str(report.get("decision"))
    if hard_pass and cross_review:
        expected_decision = "RD20_P3_CORE_EDGE_CONFIRMED_CROSS_VENUE_REVIEW_REQUIRED"
        expected_p4 = False
    elif hard_pass:
        expected_decision = "RD20_P3_CORE_EDGE_CONFIRMED_P4_AUTHORIZED"
        expected_p4 = True
    else:
        expected_decision = "RD20_P3_CORE_EDGE_REJECTED_NO_ADVANCEMENT"
        expected_p4 = False
    if decision != expected_decision:
        raise ValidationError(f"decision mismatch: {decision} != {expected_decision}")
    if bool(report.get("p4_authorized")) != expected_p4:
        raise ValidationError("P4 authorization mismatch")

    if len(break_even) != 3:
        raise ValidationError("break-even diagnostics do not cover three universes")
    if len(forward) != 3 * 3 * 3 * 2:
        raise ValidationError(f"forward diagnostic grid expected 54 rows, found {len(forward)}")
    if len(partitions) != 6 * 3:
        raise ValidationError("partition metrics expected 18 rows")
    if len(years) < 6 * 3:
        raise ValidationError("year metrics unexpectedly sparse")

    print(
        json.dumps(
            {
                "status": "PASS",
                "decision": decision,
                "hard_gates_passed": hard_pass,
                "cross_venue_review_required": cross_review,
                "p4_authorized": expected_p4,
                "trade_rows": len(trades),
                "2024_accessed": False,
                "production_authorized": False,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
