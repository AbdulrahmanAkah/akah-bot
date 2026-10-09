"""Bounded derived-ledger authority adjudication; no market reads or replay."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DOWNLOADS = Path("C:/Users/abdul/Downloads")
OUT = ROOT / "governance/p43_transition_exact_authority"
TASK = (
    "FINAL_EXIT_BRAIN_PRE_2024_ARCHITECTURE_P43_PREEXISTING_EVENT_LEVEL_"
    "TRANSITION_AUTHORITY_SCHEMA_ADJUDICATION_V1_RETRY_V1"
)
P13 = DOWNLOADS / "AKAH_P33_RETRY_V3_P31_SANDBOX/p13_baseline_replay_capture/candidate_trades.csv"
P19 = DOWNLOADS / (
    "EAA_EXIT_BRAIN_P19_2022_TRANSITION_ADMISSION_COMPONENT_ABLATION_"
    "CANONICAL_RESULT_20260914_010117.json"
)
OBSERVER = (
    DOWNLOADS / "EAA_EXIT_BRAIN_P19_2022_TRANSITION_ADMISSION_ABLATION_OBSERVER_20260914_040044.py"
)
TOL = 1e-8  # CSV/binary-float reconciliation only, never a trading threshold.


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def read_bound(path, expected):
    if sha(path) != expected:
        raise ValueError(f"AUTHORITY_SHA_DRIFT:{path}")
    return pd.read_csv(path, float_precision="round_trip")


def key(frame):
    if "event_key" in frame.columns:
        assert frame.event_key.notna().all()
        return frame.event_key.astype(str)
    return (
        frame.period_id.astype(str)
        + "|"
        + pd.to_datetime(frame.signal_time, utc=True).map(lambda t: t.isoformat())
        + "|"
        + frame.pair.astype(str)
    )


def validate():
    trades = read_bound(P13, "AC2EBBB85692CBE0E4692BB045755A6C703A4B809682FFBB0B875E9FF24BA67A")
    if sha(P19) != "221CC3BCF5E062CE36CE2BEE10E3A9EE22448A8A8E4EF54F01DAF331E8B52DE7":
        raise ValueError("P19_RESULT_DRIFT")
    if sha(OBSERVER) != "1CB8F15E04A2A7A19C7003024B2F56743EBCF23256CE0E1C2FAAB70CE82405CC":
        raise ValueError("P19_OBSERVER_DRIFT")
    authority = json.loads(P19.read_text())
    item = authority["artifacts"]["treatment_event_trace"]
    trace_path = Path(item["path"])
    trace = read_bound(trace_path, item["sha256"])
    identity = ["pair", "entry_time"]
    assert not trades[identity].isna().any().any()
    assert not trades.duplicated(identity).any()
    assert trades.pair.duplicated().any()
    assert not key(trades).duplicated().any() and not key(trace).duplicated().any()
    assert pd.to_datetime(trades.entry_time, utc=True).dt.year.eq(2022).all()
    assert len(trades) == 215
    assert abs(math.fsum(trades.net_pnl) - (-4248.200575640512)) < TOL
    direct_keys = set(key(trace.loc[trace.decision.eq("TRANSITION_ADMISSION_ABLATED")]))
    direct = trades.loc[key(trades).isin(direct_keys)].copy()
    assert direct.entry_market_state.eq("TRANSITION").all()
    assert len(direct) == 173 and abs(math.fsum(direct.net_pnl) + 8163.217282531882) < TOL
    excluded = trades.loc[
        trades.entry_market_state.eq("TRANSITION") & ~key(trades).isin(direct_keys)
    ].copy()
    decisions = dict(zip(key(trace), trace.decision, strict=True))
    excluded["treatment_decision"] = key(excluded).map(decisions)
    p38 = next(
        (ROOT / "governance").glob(
            "*p38*retry_v1_retry_v1_retry_v1_retry_v1/source_2023_replication_result.json"
        )
    )
    assert sha(p38) == "2C18FDD45FBD4DD4163689DDC3CC27425479ABD95D5B722513BFAFF3548E2F7B"
    p38_value = json.loads(p38.read_text())
    paths = {
        name: {**v, "exists": Path(v["path"]).exists()}
        for name, v in p38_value["artifacts"].items()
    }
    p42 = next((ROOT / "governance").glob("*p42*authority_audit_v1/canonical_result.json"))
    census = json.loads(p42.read_text())
    control_candidates = [
        row
        for row in census["all_structured_rowset_audits"]
        if row["schema"]["row_count"] == 237 and "net_pnl" in row["schema"]["keys"]
    ]
    preserved_p38 = [
        row
        for row in census["all_candidate_file_inventory"]
        if row["sha256"] in {v["sha256"] for v in paths.values()}
    ]
    assert not control_candidates and not preserved_p38
    result = {
        "task_id": TASK,
        "status": "PASS",
        "identity": identity,
        "lineage_join_key": ["period_id", "signal_time_utc_iso", "pair"],
        "identity_role": "RESEARCH_LINEAGE_ONLY",
        "identity_nulls": 0,
        "duplicate_identity": 0,
        "schema": list(trades.columns),
        "pnl_column": "net_pnl",
        "pnl_reconciliation_abs_tolerance": TOL,
        "p13_count": len(trades),
        "p13_net_pnl": math.fsum(trades.net_pnl),
        "all_entry_transition_count": int(trades.entry_market_state.eq("TRANSITION").sum()),
        "all_entry_transition_pnl": math.fsum(
            trades.loc[trades.entry_market_state.eq("TRANSITION"), "net_pnl"]
        ),
        "direct_count": len(direct),
        "direct_pnl": math.fsum(direct.net_pnl),
        "direct_definition": (
            "P19 treatment decision TRANSITION_ADMISSION_ABLATED intersect control event keys; "
            "require entry_market_state TRANSITION"
        ),
        "excluded_transition_rows": excluded[
            ["pair", "entry_time", "signal_time", "net_pnl", "treatment_decision"]
        ].to_dict("records"),
        "2022_direct_set_proven": True,
        "2023_direct_set_proven": False,
        "2023_recorded_export_paths": paths,
        "2023_control_rowset_in_full_p42_census": control_candidates,
        "p38_export_hash_matches_in_full_p42_census": preserved_p38,
        "p42_rowsets_checked": len(census["all_structured_rowset_audits"]),
        "absence_claim_scope": (
            "P38 recorded paths and complete existing P42 derived-artifact census"
        ),
        "scientific_conclusion": "NONE_CROSS_YEAR_DIAGNOSIS_REQUIRES_2023_EXPORT",
        "minimum_export": ["control trades", "treatment trades", "treatment event trace"],
        "export_requirement": (
            "Frozen P38 observer control/treatment plus exact P38 metrics parity; "
            "do not alter decisions"
        ),
        "authorities": [
            {"path": str(p), "sha256": sha(p)} for p in [P13, P19, OBSERVER, trace_path, p38, p42]
        ],
        "replay_executed": False,
        "market_rows_read": False,
        "2024_access": False,
        "2025_access": False,
    }
    return result, trades, direct, trace


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["preflight", "execute"])
    args = parser.parse_args()
    result, trades, direct, trace = validate()
    if args.mode == "execute":
        active = json.loads((ROOT / ".akah_bot/active_task.json").read_text())
        assert active["task_id"] == TASK
        OUT.mkdir(exist_ok=False)
        shutil.copyfile(P13, OUT / "p13_control_trades.csv")
        direct.to_csv(OUT / "direct_2022.csv", index=False, float_format="%.17g")
        trace.to_csv(OUT / "treatment_trace_2022.csv", index=False, float_format="%.17g")
        result["artifacts"] = [
            {"path": str(p.relative_to(ROOT)), "sha256": sha(p)} for p in sorted(OUT.glob("*.csv"))
        ]
        (OUT / "canonical_result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
