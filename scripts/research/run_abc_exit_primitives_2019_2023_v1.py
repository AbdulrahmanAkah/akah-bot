from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from spotbot.research.abc_exit_primitives_v1 import (
    CANDIDATES,
    build_four_hour_bars,
    concentration_review,
    direct_effect,
    parity_compare,
    replay_overlay,
)
from spotbot.research.rd20_p2_minimal_pullback import load_membership
from spotbot.research.rd26_exit_architecture import (
    prepare_features,
    scan_focus_signals,
    union_events,
)
from spotbot.research.rd27_adaptive_lifecycle import build_market_state_frame
from spotbot.research.rd27_lifecycle_replay import (
    FULL_ADAPTIVE_LIFECYCLE_BRAIN,
    replay_lifecycle_policy,
)

RAW_ROOT = Path("data/raw/rd16b/kucoin")
MEMBERSHIP = Path("data/research/rd18_p3x_a3b_runtime/effective-operational-membership.csv")
OUTPUT = Path("data/research/abc_exit_primitives_2019_2023_v1")
YEARS = (2019, 2020, 2021, 2022, 2023)


class RunnerError(RuntimeError):
    pass


def sha256(p: Path) -> str:
    h=hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""):
            h.update(b)
    return h.hexdigest().upper()


def load_json(p: Path):
    return json.loads(p.read_text(encoding="utf-8-sig"))


def write_json(p: Path, obj):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False,default=str)+"\n",encoding="utf-8")


def year_pairs(membership, year: int):
    ys=pd.Timestamp(f"{year}-01-01T00:00:00Z")
    ye=pd.Timestamp(f"{year+1}-01-01T00:00:00Z")
    pairs=set()
    for s in membership:
        if str(s.universe_id)!="C2":
            continue
        if pd.Timestamp(s.effective_end)<=ys or pd.Timestamp(s.decision_time)>=ye:
            continue
        pairs.update(pair for pair,_ in s.members)
    return sorted(pairs)


def load_year_inputs(repo: Path, membership, year: int):
    ys=pd.Timestamp(f"{year}-01-01T00:00:00Z")
    ye=pd.Timestamp(f"{year+1}-01-01T00:00:00Z")
    pairs=year_pairs(membership,year)
    if not pairs:
        raise RunnerError(f"no C2 pairs {year}")
    raw_by_pair={}
    features={}
    four_hour={}
    for pair in pairs:
        path=repo/RAW_ROOT/pair/"1h.parquet"
        if not path.is_file():
            raise RunnerError(f"raw pair missing {pair}")
        raw=pd.read_parquet(
            path,engine="pyarrow",
            columns=["timestamp","open","high","low","close","volume"],
            filters=[("timestamp","<",ye.to_pydatetime())],
        )
        raw["timestamp"]=pd.to_datetime(raw["timestamp"],utc=True,errors="raise")
        if len(raw) and raw["timestamp"].max()>=ye:
            raise RunnerError(f"sealed cutoff violation {pair} {year}")
        raw_by_pair[pair]=raw
        features[pair]=prepare_features(raw,cutoff=ye)
        four_hour[pair]=build_four_hour_bars(raw,cutoff=ye)

    btc_path=repo/RAW_ROOT/"BTC-USDT"/"1h.parquet"
    btc=pd.read_parquet(
        btc_path,engine="pyarrow",
        columns=["timestamp","open","high","low","close","volume"],
        filters=[("timestamp","<",ye.to_pydatetime())],
    )
    btc["timestamp"]=pd.to_datetime(btc["timestamp"],utc=True,errors="raise")
    if len(btc) and btc["timestamp"].max()>=ye:
        raise RunnerError(f"BTC sealed cutoff violation {year}")
    state_frame=build_market_state_frame(btc,cutoff=ye)

    periods={f"YEAR_{year}":(ys,ye)}
    generated,_=scan_focus_signals(
        membership=membership,features=features,periods=periods,
        data_start=ys,data_cutoff=ye,guard_each_period_hours=None,
    )
    events=union_events(generated,universe_id="C2")
    if len(events):
        events["timestamp"]=pd.to_datetime(events["timestamp"],utc=True,errors="raise")
        entry=events["timestamp"]+pd.Timedelta(hours=1)
        events=events.loc[(entry>=ys)&((entry+pd.Timedelta(hours=168))<ye)].copy()
    return ys,ye,pairs,raw_by_pair,features,four_hour,state_frame,events.reset_index(drop=True)


def canonical_trade_sort(df: pd.DataFrame):
    if df.empty:
        return df.copy()
    return df.sort_values(["entry_time","pair","exit_time"],kind="stable").reset_index(drop=True)


def candidate_status(rows):
    # rows = list of yearly matrix records for one candidate.
    if any(r["validity_pass"] is False for r in rows):
        return "INVALID / BLOCKED"
    evaluable=sum(int(r["direct_evaluable_lifecycles"]) for r in rows)
    executed=sum(int(r["direct_executed_interventions"]) for r in rows)
    if evaluable==0:
        return "INSUFFICIENT_EVALUABLE_OPPORTUNITY"
    if executed==0:
        return "REDUNDANT"
    negative_dominance=all(
        float(r["delta_pnl_total_effect"])<=0.0 and float(r["delta_mdd"])>=0.0 for r in rows
    )
    strict=any(
        float(r["delta_pnl_total_effect"])<0.0 or float(r["delta_mdd"])>0.0 for r in rows
    )
    if negative_dominance and strict:
        return "REJECT"
    return "RETAIN_FOR_CAUSAL_REVIEW"


def run(repo: Path, expected_freeze_commit: str, freeze_manifest: Path):
    if (repo/OUTPUT).exists():
        raise RunnerError(f"output exists: {OUTPUT}")
    if subprocess_run(repo,["git","rev-parse","HEAD"]) != expected_freeze_commit:
        raise RunnerError("HEAD != implementation freeze commit")
    freeze=load_json(freeze_manifest)
    for rec in freeze["frozen_files"]:
        p=repo/rec["path"]
        if sha256(p)!=rec["sha256"]:
            raise RunnerError(f"frozen file hash drift: {rec['path']}")

    membership=load_membership(repo/MEMBERSHIP)
    controls={}
    year_inputs={}
    parity_records=[]

    # Complete ALL Control and adapter parity gates before opening candidate C.
    for year in YEARS:
        ys,ye,pairs,raw,features,h4,state,events=load_year_inputs(repo,membership,year)
        if events.empty:
            raise RunnerError(f"no annual events {year}")
        native_t,native_d,native_m,native_c=replay_lifecycle_policy(
            policy_id=FULL_ADAPTIVE_LIFECYCLE_BRAIN,
            portfolio_id="UNION_FOCUS",universe_id="C2",cost_multiplier=1.0,
            events=events,frames=features,state_frame=state,
            replay_start=ys,replay_cutoff=ye,
        )
        overlay_t,overlay_d,overlay_m,overlay_c,_=replay_overlay(
            candidate_id=None,events=events,frames=features,state_frame=state,four_hour=h4,
            replay_start=ys,replay_cutoff=ye,
        )
        parity=parity_compare(
            canonical_trade_sort(native_t),native_m,
            canonical_trade_sort(overlay_t),overlay_m,
        )
        parity_records.append({"year":year,**parity})
        if not parity["pass"]:
            raise RunnerError(f"control adapter parity failed {year}: {parity['differences'][:5]}")
        controls[year]=(native_t,native_d,native_m,native_c)
        year_inputs[year]=(ys,ye,pairs,raw,features,h4,state,events)
        print(
            f"CONTROL_PARITY_{year}=PASS trades={native_m['trade_count']} "
            f"net_pnl={native_m['net_pnl']:.12f} mdd={native_m['maximum_drawdown']:.12f}",
            flush=True,
        )

    output=repo/OUTPUT
    output.mkdir(parents=True,exist_ok=False)
    pd.DataFrame(parity_records).to_json(output/"control-adapter-parity.json",orient="records",indent=2)

    matrix=[]
    all_control=[]
    all_candidate=[]
    all_direct=[]
    all_interventions=[]
    candidate_summaries={}

    for candidate in CANDIDATES:  # frozen C -> A -> B
        candidate_rows=[]
        print(f"ABC_CANDIDATE_BEGIN={candidate}",flush=True)
        for year in YEARS:
            ys,ye,pairs,raw,features,h4,state,events=year_inputs[year]
            control_t,control_d,control_m,control_c=controls[year]
            cand_t,cand_d,cand_m,cand_c,interventions=replay_overlay(
                candidate_id=candidate,events=events,frames=features,state_frame=state,
                four_hour=h4,replay_start=ys,replay_cutoff=ye,
            )
            direct_rows,direct_summary=direct_effect(
                candidate_id=candidate,control_trades=control_t,
                hourly_by_pair=raw,four_hour_by_pair=h4,cost_multiplier=1.0,
            )
            total=float(cand_m["net_pnl"])-float(control_m["net_pnl"])
            direct=float(direct_summary["direct_effect"])
            residual=total-direct
            delta_mdd=float(cand_m["maximum_drawdown"])-float(control_m["maximum_drawdown"])
            validity = not bool(
                (interventions.get("preemption_reason",pd.Series(dtype=str))=="NO_VALID_EXECUTION_PRICE").any()
                if len(interventions) else False
            )
            row={
                "candidate_id":candidate,"year":year,"validity_pass":bool(validity),
                "control_trade_count":int(control_m["trade_count"]),
                "candidate_trade_count":int(cand_m["trade_count"]),
                "control_net_pnl":float(control_m["net_pnl"]),
                "candidate_net_pnl":float(cand_m["net_pnl"]),
                "delta_pnl_total_effect":total,
                "direct_effect":direct,
                "portfolio_path_residual":residual,
                "control_mdd":float(control_m["maximum_drawdown"]),
                "candidate_mdd":float(cand_m["maximum_drawdown"]),
                "delta_mdd":delta_mdd,
                "control_profit_factor":float(control_m["profit_factor"]),
                "candidate_profit_factor":float(cand_m["profit_factor"]),
                "control_win_rate":float(control_m["win_rate"]),
                "candidate_win_rate":float(cand_m["win_rate"]),
                "direct_control_lifecycles":int(direct_summary["control_lifecycle_count"]),
                "direct_evaluable_lifecycles":int(direct_summary["evaluable_lifecycle_count"]),
                "direct_candidate_signals":int(direct_summary["candidate_signal_count"]),
                "direct_executed_interventions":int(direct_summary["executed_intervention_count"]),
                "direct_native_preempted":int(direct_summary["native_preempted_count"]),
                "direct_mean_lead_hours":float(direct_summary["mean_lead_hours_executed"]),
                "portfolio_candidate_signals":int(cand_c["candidate_signals"]),
                "portfolio_candidate_executed":int(cand_c["candidate_executed"]),
                "portfolio_native_preempted":int(cand_c["candidate_native_preempted"]),
                "portfolio_native_tie_priority":int(cand_c["candidate_native_tie_priority"]),
            }
            matrix.append(row); candidate_rows.append(row)

            ct=control_t.copy(); ct.insert(0,"year",year); all_control.append(ct)
            kt=cand_t.copy(); kt.insert(0,"year",year); kt.insert(0,"candidate_id",candidate); all_candidate.append(kt)
            dr=direct_rows.copy(); dr.insert(0,"year",year); all_direct.append(dr)
            if len(interventions):
                ir=interventions.copy(); ir.insert(0,"year",year); all_interventions.append(ir)

            print(
                f"ABC_RESULT candidate={candidate} year={year} "
                f"total={total:.12f} direct={direct:.12f} residual={residual:.12f} "
                f"delta_mdd={delta_mdd:.12f} direct_exec={direct_summary['executed_intervention_count']}",
                flush=True,
            )

        status=candidate_status(candidate_rows)
        direct_cat=pd.concat(
            [x for x in all_direct if len(x) and str(x["candidate_id"].iloc[0])==candidate],
            ignore_index=True,
        ) if any(len(x) and str(x["candidate_id"].iloc[0])==candidate for x in all_direct) else pd.DataFrame()
        candidate_summaries[candidate]={
            "status":status,
            "five_year_total_effect":float(sum(r["delta_pnl_total_effect"] for r in candidate_rows)),
            "five_year_direct_effect":float(sum(r["direct_effect"] for r in candidate_rows)),
            "five_year_portfolio_path_residual":float(sum(r["portfolio_path_residual"] for r in candidate_rows)),
            "executed_interventions":int(sum(r["direct_executed_interventions"] for r in candidate_rows)),
            "evaluable_lifecycles":int(sum(r["direct_evaluable_lifecycles"] for r in candidate_rows)),
            "concentration_review":concentration_review(direct_cat),
        }
        print(f"ABC_CANDIDATE_COMPLETE={candidate} STATUS={status}",flush=True)

    matrix_df=pd.DataFrame(matrix)
    matrix_df.to_csv(output/"yearly-matrix.csv",index=False,lineterminator="\n")
    pd.concat(all_control,ignore_index=True).drop_duplicates(
        subset=["year","portfolio_id","pair","entry_time","exit_time"]
    ).to_csv(output/"control-trades.csv",index=False,lineterminator="\n")
    pd.concat(all_candidate,ignore_index=True).to_csv(output/"candidate-portfolio-trades.csv",index=False,lineterminator="\n")
    pd.concat(all_direct,ignore_index=True).to_csv(output/"direct-effect-attribution.csv",index=False,lineterminator="\n")
    if all_interventions:
        pd.concat(all_interventions,ignore_index=True).to_csv(output/"candidate-interventions.csv",index=False,lineterminator="\n")
    else:
        pd.DataFrame().to_csv(output/"candidate-interventions.csv",index=False,lineterminator="\n")

    report={
        "schema_version":"abc-exit-primitives-2019-2023-execution-v1",
        "status":"PASS",
        "execution_order":["C","A","B"],
        "years":list(YEARS),
        "primary_control":"FULL_ADAPTIVE_LIFECYCLE_BRAIN:UNION_FOCUS:C2:1X",
        "candidate_summaries":candidate_summaries,
        "no_ranking":True,
        "automatic_winner":False,
        "mandatory_causal_review_required":True,
        "2024_accessed":False,"2025_accessed":False,"production_authorized":False,
        "next_bottleneck":"ABC_2019_2023_MANDATORY_CAUSAL_REVIEW_V1",
    }
    write_json(output/"execution-report.json",report)

    files=[]
    for p in sorted(output.iterdir()):
        if p.is_file():
            files.append({"path":p.name,"bytes":p.stat().st_size,"sha256":sha256(p)})
    write_json(output/"output-manifest.json",{
        "schema_version":"abc-exit-primitives-output-manifest-v1",
        "files":files,
        "candidate_summaries":candidate_summaries,
    })
    return report


def subprocess_run(repo: Path, args):
    import subprocess
    cp=subprocess.run(args,cwd=str(repo),text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,encoding="utf-8",errors="replace")
    if cp.returncode:
        raise RunnerError(f"command failed {' '.join(args)} :: {cp.stderr}")
    return cp.stdout.strip()


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--repo-root",type=Path,required=True)
    p.add_argument("--expected-freeze-commit",required=True)
    p.add_argument("--freeze-manifest",type=Path,required=True)
    args=p.parse_args()
    report=run(args.repo_root.resolve(),args.expected_freeze_commit,args.freeze_manifest.resolve())
    print(json.dumps(report,indent=2,sort_keys=True))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
