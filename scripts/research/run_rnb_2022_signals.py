"""Offline input construction and readiness audit; never calls native replay."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

from spotbot.research import rd26_exit_architecture as rd26
from spotbot.research.rd20_p2_minimal_pullback import load_membership
from spotbot.research.rd27_adaptive_lifecycle import build_market_state_frame
from spotbot.research.rd27_lifecycle_replay import build_state_lookup
from spotbot.research.rnb_signal_2022 import CUTOFF, START, construct

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "data/research/reconstructed_native_baseline_pre2023"
EVIDENCE = ROOT / "governance/rnb_signals"
MEMBERSHIP = ROOT / "data/research/rd18_p3x_a3b_runtime/effective-operational-membership.csv"
MANIFEST = ROOT / "governance/rnb_acquisition/verified_manifest.json"
STRATA = ROOT / (
    "governance/reconstructed_native_baseline_rd26_signal_source_and_1h_manifest_"
    "human_decision_v1/full_native_matrix_strata_contract.json"
)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def write_new(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(value, indent=2, sort_keys=True, default=str) + "\n")


def main():
    if sha(MANIFEST) != "E0E67858BCB9BF5377D7CA548182214B53C7DBC9D186C49CDE1DE9F35B54BA70":
        raise ValueError("manifest drift")
    if sha(MEMBERSHIP) != "F7D6012CE8CD691583B9B6276DDF36371BFE0BBD9B28F810B676AD0177FB559E":
        raise ValueError("membership drift")
    if (OUTPUT / "signal-events-2022-v1.csv").exists():
        raise ValueError("immutable signal output exists")
    authority = json.loads(MANIFEST.read_text(encoding="utf-8"))
    frames, state_frame = {}, None
    for record in authority["files"]:
        path = ROOT / record["path"]
        if OUTPUT.resolve() not in path.resolve().parents or sha(path) != record["sha256"]:
            raise ValueError("authorized input drift before row-open")
        raw = pd.read_parquet(path)
        if not raw.timestamp.between(START, CUTOFF, inclusive="left").all():
            raise ValueError("isolated authority violation")
        frames[record["pair"]] = rd26.prepare_features(raw, cutoff=CUTOFF)
        if record["pair"] == "BTC-USDT":
            state_frame = build_market_state_frame(raw, cutoff=CUTOFF)
        print(f"FEATURES_READY={record['pair']}", flush=True)
    membership = load_membership(MEMBERSHIP)
    hashes = []
    for run in (1, 2):
        print(f"SIGNAL_CONSTRUCTION_RUN={run}:START", flush=True)
        events, _funnel = construct(membership, frames)
        payload = events.to_csv(index=False, lineterminator="\n").encode("utf-8")
        hashes.append(hashlib.sha256(payload).hexdigest().upper())
        print(
            f"SIGNAL_CONSTRUCTION_RUN={run}:PASS count={len(events)} sha={hashes[-1]}", flush=True
        )
    if hashes[0] != hashes[1]:
        raise ValueError("signal nondeterminism")
    required = {
        "timestamp",
        "universe_id",
        "period_id",
        "family_id",
        "pair",
        "membership_rank",
        "atr24_at_signal",
    }
    forbidden = {
        "exit_time",
        "exit_price",
        "exit_reason",
        "pnl",
        "net_pnl",
        "gross_pnl",
        "return_fraction",
        "mae",
        "mfe",
        "holding_hours",
    }
    if not required.issubset(events.columns) or forbidden.intersection(events.columns):
        raise ValueError("signal schema firewall violation")
    # return_72h is an existing backward-looking native feature, never future return/PnL.
    with (OUTPUT / "signal-events-2022-v1.csv").open("xb") as stream:
        stream.write(payload)
    lookup = build_state_lookup(state_frame)
    missing = events.loc[~events.timestamp.map(lambda t: int(t.value) in lookup)]
    strata = json.loads(STRATA.read_text(encoding="utf-8"))["strata"]
    strata_records = []
    for stratum in strata:
        if stratum["signal_constructor"] == "union_events":
            selected = rd26.union_events(events, universe_id=stratum["universe_id"])
        else:
            selected = rd26.standalone_events(
                events, universe_id=stratum["universe_id"], family_id=stratum["family_id"]
            )
        strata_records.append(
            {
                **stratum,
                "signal_count": len(selected),
                "pair_count": selected.pair.nunique(),
                "state_unavailable_count": sum(
                    int(t.value) not in lookup for t in selected.timestamp
                ),
            }
        )
    audit = {
        "signal_status": "PASS",
        "signal_sha256": hashes[0],
        "determinism_sha_run2": hashes[1],
        "signal_count": len(events),
        "signal_pair_count": events.pair.nunique(),
        "signal_min_time": events.timestamp.min(),
        "signal_max_time": events.timestamp.max(),
        "signal_schema": list(events.columns),
        "membership_sha256": sha(MEMBERSHIP),
        "one_hour_manifest_sha256": sha(MANIFEST),
        "strata": strata_records,
        "policy_id": "rd27.FULL_ADAPTIVE_LIFECYCLE_BRAIN",
        "cost_multiplier": 1.0,
        "state_ready_first_time": state_frame.loc[state_frame.state_ready, "timestamp"].min(),
        "state_unavailable_signal_count": len(missing),
        "state_unavailable_unique_times": missing.timestamp.nunique(),
        "state_unavailable_signals": missing[list(sorted(required))].to_dict("records"),
        "state_input_status": "FAIL_CLOSED" if len(missing) else "PASS",
        "cohort_frozen": False,
        "ready_for_native_replay": False,
        "native_replay_executed": False,
        "economic_analysis": False,
        "protected_year_rows_read": 0,
        "window_binding": "Native bytecode/private cutoff=2023; native globals unchanged",
    }
    write_new(EVIDENCE / "construction_and_state_audit.json", audit)
    print(
        f"NATIVE_STATE_SIGNAL_COVERAGE={'FAIL_CLOSED' if len(missing) else 'PASS'} "
        f"missing={len(missing)}",
        flush=True,
    )


if __name__ == "__main__":
    main()
