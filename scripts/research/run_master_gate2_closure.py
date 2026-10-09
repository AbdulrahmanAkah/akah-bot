# ruff: noqa: E501 -- generated report/HTML literals.
"""One bounded, offline fidelity census. No economic simulation or PnL computation."""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import subprocess
import sys
import traceback
import zipfile
from pathlib import Path

import pandas as pd

from spotbot.research.multi_school_fidelity import akah_census_fastpath_v1 as fast
from spotbot.research.multi_school_fidelity import akah_full_fidelity_runtime_v1 as rt
from spotbot.research.multi_school_fidelity import akah_native_management_adapters_v1 as mgmt
from spotbot.research.multi_school_fidelity import akah_native_replay_engine_v1 as engine
from spotbot.research.multi_school_fidelity import akah_replay_ready_detectors_v1 as det
from spotbot.research.multi_school_fidelity import akah_thesis_engine_foundation_v1 as thesis
from spotbot.research.multi_school_fidelity import blind_review as blind
from spotbot.research.multi_school_fidelity import fidelity_pipeline as pipe
from spotbot.research.multi_school_fidelity import gate3_precommit as gate3
from spotbot.research.multi_school_fidelity.akah_foundation_core_v1r1 import DATA_CUTOFF, utc

TASK = "AKAH_MASTER_GATE2_CLOSURE_GATE3_PRECOMMIT_FREEZE_MEGA_V1"
AUTHORITY_START = "6f6dbd69b9469a684f73d196df8c773808cd65e6"
CHARTER_START = "0D7E9DF3B559CA252F4FEB1C57BD5D2B3FD37026A95484204789CE9795AAC129"


def write_json(path, obj):
    path.write_text(json.dumps(obj, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def write_csv(path, rows, columns=None):
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns or list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def zip_directory(root, destination):
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(root.rglob("*")):
            if p.is_file():
                z.write(p, p.relative_to(root))


def prefix(frame, checkpoint, limit, reference):
    x = frame.loc[frame.timestamp <= checkpoint].tail(limit).copy()
    if x.empty or x.timestamp.max() > checkpoint or x.timestamp.max() >= DATA_CUTOFF:
        raise ValueError("BLIND_PREFIX_INVALID")
    x["rel_bar"] = range(1 - len(x), 1)
    x["hours_before_checkpoint"] = (x.timestamp - checkpoint).dt.total_seconds() / 3600
    for col in ("open", "high", "low", "close"):
        x[col] = x[col].astype(float) * 100 / reference
    return x


def make_packet(output, chosen, cache, corpus_sha):
    primary = [r for r in chosen if not r["reserve"]]
    reserve = [r for r in chosen if r["reserve"]]
    sealed = []
    for batch, rows in (("PRIMARY", primary), ("RESERVE", reserve)):
        visible = []
        directories = [
            output / f"{batch}_{reviewer}"
            for reviewer in ("USER_MANUAL_TRADER", "INDEPENDENT_DOMAIN_REVIEWER")
        ]
        for d in directories:
            (d / "images").mkdir(parents=True)
            (d / "prefixes").mkdir()
        for number, case in enumerate(rows, 1):
            cid = f"G2-{batch[0]}-{number:04d}"
            pair, t = case["pair"], utc(case["time"])
            raw, h4, d1 = cache.get(pair)
            reference = float(raw.loc[raw.timestamp <= t, "close"].iloc[-1])
            asset_prefixes = [
                prefix(f, t, n, reference)
                for f, n in zip((raw, h4, d1), (480, 300, 240), strict=True)
            ]
            btc = cache.get("BTC-USDT")
            btc_ref = float(btc[0].loc[btc[0].timestamp <= t, "close"].iloc[-1])
            for directory in directories:
                for label, f in zip(("1H", "4H", "1D"), asset_prefixes, strict=True):
                    blind.make_plot(
                        f, directory / "images" / f"{cid}_{label}.svg", f"{cid} — {label} prefix"
                    )
                    f.drop(columns="timestamp").to_csv(
                        directory / "prefixes" / f"{cid}_{label}.csv", index=False
                    )
                blind.make_plot(
                    asset_prefixes[1],
                    directory / "images" / f"{cid}_4H_VOLUME.svg",
                    f"{cid} — volume",
                    volume=True,
                )
                for label, f, n in zip(("1H", "4H", "1D"), btc, (480, 300, 240), strict=True):
                    benchmark = prefix(f, t, n, btc_ref)
                    benchmark.drop(columns="timestamp").to_csv(
                        directory / "prefixes" / f"{cid}_BENCHMARK_{label}.csv", index=False
                    )
                    blind.make_plot(
                        benchmark,
                        directory / "images" / f"{cid}_BENCHMARK_{label}.svg",
                        f"{cid} — market {label}",
                    )
                # Matched market-relative path, all observations <= checkpoint.
                a = asset_prefixes[0][["timestamp", "close"]]
                b = prefix(btc[0], t, 480, btc_ref)[["timestamp", "close"]]
                rs = a.merge(b, on="timestamp", suffixes=("_asset", "_benchmark"))
                rs["relative_ratio"] = rs.close_asset / rs.close_benchmark
                rs["hours_before_checkpoint"] = (rs.timestamp - t).dt.total_seconds() / 3600
                rs[["hours_before_checkpoint", "relative_ratio"]].to_csv(
                    directory / "prefixes" / f"{cid}_RS.csv", index=False
                )
            v = {"case_id": cid, "school": case["system_id"].split("_")[1]}
            if v["school"] == "ICT":
                ny = t.tz_convert("America/New_York")
                v.update(ny_weekday=ny.day_name(), ny_time=ny.strftime("%H:%M"))
            visible.append(v)
            sealed.append(
                {
                    "case_id": cid,
                    **case,
                    "prefix_maxima": [str(f.timestamp.max()) for f in asset_prefixes],
                }
            )
        for reviewer, directory in zip(
            ("USER_MANUAL_TRADER", "INDEPENDENT_DOMAIN_REVIEWER"), directories, strict=True
        ):
            html = blind.build_review_html(visible, reviewer)
            # Add causal market context; no engine trace or sampling-category display.
            for case in visible:
                cid = case["case_id"]
                marker = f"<h2>{cid} — {case['school']}</h2>"
                html = html.replace(
                    marker,
                    marker
                    + f'<p>Normalized OHLCV and RS: <a href="prefixes/{cid}_RS.csv">RS prefix</a></p>'
                    + "".join(
                        f'<img src="images/{cid}_BENCHMARK_{tf}.svg">' for tf in ("1D", "4H")
                    ),
                )
            html = html.replace("reviewer_id:", "reviewer_id:")
            html = html.replace(
                "responses:rows",
                f"corpus_sha256:{json.dumps(corpus_sha)},locked:true,locked_at:new Date().toISOString(),responses:rows",
            )
            # Do not allow a blank export to masquerade as locked review.
            html = html.replace(
                " const blob=new Blob",
                " if(rows.some(r=>!r.human_action || ['context','structure','location','trigger','invalidation','management'].some(k=>!r[k]?.trim()))){alert('Complete every field; use explicit UNRESOLVED reasons where necessary.');return;}\n const blob=new Blob",
            )
            (directory / "REVIEW.html").write_text(html, encoding="utf-8")
            (directory / "README.txt").write_text(
                f"Protocol AKAH_BLIND_TRANSLATION_FIDELITY_V1\nCorpus SHA256 {corpus_sha}\n"
                "PRIMARY only: judge the chart prefix before any future or engine trace.\n"
                "Reserve is pre-drawn, separate, and must not be reviewed until a versioned discovery change is locked.\n"
                "Do not open sealed traces. Complete every field and export LOCKED_RESPONSES.json.\n"
                "Independent reviewer must be a distinct human domain reviewer; no assistant impersonation.\n"
                "ACCEPT means the displayed prefix satisfies the frozen school scope, not approval of an economic policy.\n"
                "Differences: CONTEXT, STRUCTURE, LOCATION, TRIGGER, INVALIDATION, MANAGEMENT.\n"
                "Allowed dispositions after both locks: IMPLEMENTATION_BUG, SPEC_AMBIGUITY, DOCTRINE_SCOPE_GAP, MANUAL_PREFERENCE_NOT_IN_SPEC, INSUFFICIENT_VIEW.\n"
                "No majority-vote or percentage-agreement shortcut; material disagreements must be closed.\n",
                encoding="utf-8",
            )
        if batch == "PRIMARY":
            for directory, name in zip(
                directories,
                ("07_GATE2_BLIND_USER_PACKET.zip", "08_GATE2_BLIND_SECOND_REVIEWER_PACKET.zip"),
                strict=True,
            ):
                zip_directory(directory, output / name)
        else:
            for directory in directories:
                zip_directory(directory, output / f"{directory.name}.zip")
    trace = output / "SEALED_DO_NOT_OPEN_BEFORE_BOTH_REVIEWS"
    trace.mkdir()
    write_json(trace / "CASE_MAP_AND_ENGINE_TRACE.json", sealed)
    zip_directory(trace, output / "09_GATE2_SEALED_ENGINE_TRACE.zip")
    return len(primary), len(reserve)


def prepare(output, repo, args):
    token = json.loads((repo / ".akah_bot/active_task.json").read_text())
    if token["task_id"] != TASK or token["starting_head"] != AUTHORITY_START:
        raise ValueError("MISSION_START_AUTHORITY_DRIFT")
    charter = repo / "governance/AKAH_BOT_SYSTEM_CHARTER.json"
    if pipe.source_hash(charter) != CHARTER_START:
        raise ValueError("CHARTER_AUTHORITY_DRIFT")
    if output.exists():
        raise FileExistsError("DO_NOT_OVERWRITE_HISTORICAL_OUTPUT")
    output.mkdir(parents=True)
    authorities = {}
    for name in (
        "AKAH_GATE1_STAGE_B_ENGINE_AND_MANAGEMENT_CLOSURE_V1R1.zip",
        "AKAH_GATE1_TARGETED_REPAIR_STAGE_A_OUT_20261002_041916.zip",
        "AKAH_EXPERT_DEEP_MULTI_SCHOOL_REVIEW_HANDOFF_V1.zip",
        "AKAH_GATE2_BLIND_TRANSLATION_FIDELITY_BUILDER_V1R1.zip",
    ):
        path = args.downloads / name
        authorities[str(path)] = pipe.source_hash(path)
    write_json(
        output / "01_PREMISSION_AUTHORITY.json",
        {
            "task": TASK,
            "token": token,
            "charter_sha256": CHARTER_START,
            "authorities": authorities,
            "git_status_at_run": subprocess.check_output(
                ["git", "status", "--porcelain"], cwd=repo, text=True
            ),
        },
    )
    (output / "02_ROOT_CAUSE_REPORT.md").write_text(
        "# Root cause\nThe original builder returned load_broad_eligibility(repo), a DataFrame. "
        "Its eligible column is a Series. Each detector requires BroadEligibilityIndex.eligible(pair,t). "
        "Canonical working callers first call BroadEligibilityIndex.build(ranking). "
        "The new adapter follows that API, with no lambda substitute.\n"
        "Two swallowed-exception layers previously converted detector failures to empty results and PASS. "
        "The maintained census has no detector catch; CLI preserves full traceback and invalidates the packet.\n"
        "Stage B's guarded simulator was not an event-driven portfolio executor. "
        "It remains disabled; the separate kernel is synthetic-tested, not economic-qualified.\n",
        encoding="utf-8",
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--downloads", type=Path, default=Path(r"C:\Users\abdul\Downloads"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-pairs", type=int, default=12)
    parser.add_argument("--smoke-only", action="store_true")
    args = parser.parse_args()
    if not 2 <= args.max_pairs <= 120:
        raise ValueError("BOUNDED_PAIR_BUDGET_REQUIRED")
    output = args.output.resolve()
    repo = args.repo.resolve()
    prepare(output, repo, args)
    with (output / "18_FULL_LOG.txt").open("w", encoding="utf-8") as log:

        class Tee:
            def __init__(self, original):
                self.original = original

            def write(self, s):
                log.write(s)
                self.original.write(s)

            def flush(self):
                log.flush()
                self.original.flush()

        original = sys.stdout
        sys.stdout = Tee(original)
        try:
            run(args, repo, output)
        except BaseException:
            traceback.print_exc(file=log)
            write_json(
                output / "17_FINAL_PRE_REPLAY_CERTIFICATE.json",
                {
                    "GATE2_PIPELINE": "FAIL",
                    "GATE2_SAMPLE_VALID": "NO",
                    "READY_FOR_SINGLE_GATE3_REPLAY": "NO",
                    "ECONOMIC_REPLAY_EXECUTED": "NO",
                    "GATE2_STATUS": "FAIL",
                },
            )
            raise
        finally:
            sys.stdout = original


def run(args, repo, output):
    sources = {}
    for module in (rt, det, engine, mgmt, thesis, pipe, gate3, fast, blind):
        p = Path(module.__file__).resolve()
        if not p.is_relative_to(repo / "src/spotbot/research/multi_school_fidelity"):
            raise ValueError("STALE_IMPORTED_SOURCE")
        sources[module.__name__] = {"path": str(p), "sha256": pipe.source_hash(p)}
    eligibility, api_proof = pipe.eligibility_adapter(repo)
    print("ELIGIBILITY_API=" + json.dumps(api_proof), flush=True)
    fast.install(det, rt)
    cache = pipe.FrameCache(repo)
    btc = cache.get("BTC-USDT")
    eth = cache.get("ETH-USDT")
    dow_path = (
        args.downloads
        / "AKAH_FULL_UNIVERSE_STATE_CENSUS_V1_OUT_20261001_134333/dow_market_state_census.csv"
    )
    # Frozen derived context; no raw or economic columns.
    dow_frame = pd.read_csv(
        dow_path,
        usecols=[
            "decision_time",
            "btc_primary_trend",
            "secondary_trend",
            "confirmed",
            "volume_confirms",
            "breadth",
            "equal_weight_return",
        ],
    )
    dow = pipe.scan_dow_context(dow_frame, eligibility)
    dow_binding = {
        "path": str(dow_path),
        "sha256": pipe.source_hash(dow_path),
        "type": "FROZEN_NON_ECONOMIC_CONTEXT_INPUT",
    }
    mtr, _, _, _ = det.scan_wyckoff("BTC-USDT", btc[1], btc[0], btc[0], eligibility, None, True)
    results = {}
    pools = {}
    smoke = []
    for pair in ("BTC-USDT", "ETH-USDT"):
        fast.clear_pair_caches()
        results[pair] = pipe.scan_pair(pair, cache.get(pair), btc[0], eth[0], eligibility, mtr, dow)
        for sid, data in results[pair].items():
            smoke.append(
                {
                    "pair": pair,
                    "school": sid,
                    "transitions_count": len(data["transitions"]),
                    "events_count": len(data["events"]),
                    "intents_count": len(data["intents"]),
                    "error_count": 0,
                    "scope": data["summary"].get("scope", "CURRENT_DETECTOR"),
                }
            )
        write_json(
            output / "05_GATE2_PIPELINE_PROOF.json",
            {
                "status": "BTC_ONLY_PASS" if pair == "BTC-USDT" else "TWO_PAIR_PASS",
                "api": api_proof,
                "imported_authority": sources,
                "smoke": smoke,
                "dow_input_binding": dow_binding,
                "readers": cache.audit,
            },
        )
        pipe.append_pools(pools, pair, cache.get(pair), results[pair], eligibility)
    print("TWO_PAIR_FAIL_FAST=PASS", flush=True)
    if args.smoke_only:
        return
    all_members = sorted(set().union(*eligibility.sets))
    available = [
        p for p in all_members if (repo / "data/raw/rd16b/kucoin" / p / "1h.parquet").is_file()
    ]
    additional = sorted(
        (p for p in available if p not in results),
        key=lambda p: pipe.digest([pipe.SEED, "PAIR", p]),
    )
    for pair in additional[: args.max_pairs - 2]:
        fast.clear_pair_caches()
        results[pair] = pipe.scan_pair(pair, cache.get(pair), btc[0], eth[0], eligibility, mtr, dow)
        pipe.append_pools(pools, pair, cache.get(pair), results[pair], eligibility)
        print(f"BOUNDED_PAIR_SCAN={len(results)}/{args.max_pairs}:{pair}", flush=True)
        # All categories must still exist after cross-category week exclusion.
        _, audit = pipe.select_cases(pools, reserve=True)
        if all(
            c["shortage"] == 0 and c["reserve"] >= c["selected"]
            for a in audit
            if a["system_id"] != pipe.SYSTEMS[-1]
            for c in a["categories"].values()
        ):
            break
    selected, audit = pipe.select_cases(pools, reserve=True)
    repeated, _ = pipe.select_cases(pools, reserve=True)
    if selected != repeated:
        raise ValueError("NONDETERMINISTIC_SAMPLING")
    corpus_sha = pipe.digest(selected).upper()
    count, reserve = make_packet(output, selected, cache, corpus_sha)
    write_json(
        output / "06_GATE2_SAMPLING_AUDIT.json",
        {
            "seed": pipe.SEED,
            "corpus_sha256": corpus_sha,
            "cells": audit,
            "case_count": count,
            "reserve_count": reserve,
            "scanned_pairs": list(results),
            "sampling_frame": "HASH_ORDERED_BOUNDED_PIT_MEMBERSHIP_PANEL",
            "exhaustive_universe_scarcity_proven": False,
            "dow_context_frame_exhausted": True,
            "unscanned_pairs": len(available) - len(results),
            "no_outcomes_used": True,
            "week_exclusion": "ALL_CATEGORIES_AND_RESERVE",
            "repeatability": "PASS",
            "readers": cache.audit,
        },
    )
    blockers = [
        "TWO_GENUINE_HUMAN_REVIEWS_AND_DISPOSITIONS_REQUIRED",
        "HISTORICAL_PIT_TICK_LOT_MIN_NOTIONAL_NORMALIZER_UNRESOLVED",
        "ROUTER_PHASE_TO_FUNDED_GRAMMAR_AND_EVIDENCE_GRAPH_RUNTIME_BINDING_NOT_FULLY_CLOSED",
        "FULL_EVENT_DRIVEN_MARKET_EXECUTION_ADAPTER_NOT_ARMED_OR_CERTIFIED",
    ]
    matrix = []
    for sid in pipe.SYSTEMS:
        reason = {
            pipe.SYSTEMS[0]: "PNF_COUNT_LINE_SEGMENT_AND_DOWNSIDE_STRIDE_UNRESOLVED",
            pipe.SYSTEMS[2]: "FAMILY_DIRECTION_RATIO_STOP_MANAGEMENT_MATRIX_UNRESOLVED",
            pipe.SYSTEMS[4]: "PARENT_CHILD_OWNER_COUNT_UNRESOLVED",
            pipe.SYSTEMS[5]: "PROTECTIVE_STOP_UNRESOLVED",
        }.get(sid, "HUMAN_FIDELITY_NORMALIZER_AND_RUNTIME_BINDINGS_REQUIRED")
        matrix.append(
            {
                "grammar": sid,
                "funded_ready": False,
                "status": "UNFUNDED_DIAGNOSTIC",
                "blockers": reason,
            }
        )
    write_csv(output / "11_FUNDED_SCOPE_AND_UNRESOLVED_MATRIX.csv", matrix)
    spec = gate3.specification()
    write_json(output / "12_GATE3_PRECOMMIT_SPEC.json", spec)
    write_csv(
        output / "13_GATE3_PRIMARY_CLAIM_REGISTRY.csv",
        [
            {
                "claim_id": sid + "_2X_MEAN_DAILY_LOG_RETURN",
                "grammar": sid,
                "scenario": "2X",
                "estimand": "MEAN_DAILY_NET_MTM_LOG_RETURN",
                "status": "PROSPECTIVE_BLOCKED",
                "family_size": 2,
            }
            for sid in gate3.PRIMARY_GRAMMARS
        ],
    )
    write_csv(
        output / "14_GATE3_ROLE_ABLATION_REGISTRY.csv",
        [
            {
                "role": "PROTECTIVE_STOP_AND_CAPITAL_LIMITS",
                "type": "HARD_SAFETY",
                "ablation": "NEVER",
            },
            {
                "role": "OWNER_STRUCTURE_LOCATION_TRIGGER_MANAGEMENT",
                "type": "DEFINING_ROLE",
                "ablation": "ALTERNATE_GRAMMAR_REQUIRES_SEPARATE_PRECOMMIT",
            },
            {
                "role": "ADDITIONAL_SCHOOL_VOTES",
                "type": "NOT_ENABLED",
                "ablation": "NOT_APPLICABLE",
            },
            {
                "role": "ALPHA_OR_RISK_OPTIONAL_ROLES",
                "type": "UNRESOLVED",
                "ablation": "NO_UNBOUND_ABLATION_AUTHORIZED",
            },
        ],
    )
    manifest = {
        str(p.relative_to(repo)): pipe.source_hash(p)
        for p in sorted((repo / "src/spotbot/research/multi_school_fidelity").glob("*.py"))
    }
    manifest[str(Path(__file__).resolve().relative_to(repo))] = pipe.source_hash(Path(__file__))
    write_json(
        output / "15_GATE3_FROZEN_HASH_MANIFEST.json",
        {
            "source_files": manifest,
            "config_sha256": gate3.config_hash(spec),
            "corpus_sha256": corpus_sha,
            "bound_inputs": cache.audit,
            "unresolved_components": "EXPLICITLY_UNFUNDED",
        },
    )
    shutil.copyfile(Path(gate3.__file__), output / "16_GATE3_REPLAY_RUNNER_DISABLED.py")
    write_json(
        output / "03_GATE1_INTEGRATION_REPORT.json",
        {
            "imported_authorities": sources,
            "isolated_research_only": True,
            "source_provenance": "governance/master_gate2_gate3_precommit_v1/source_provenance.json",
            "synthetic_suite": "tests/research/test_multi_school_fidelity.py",
            "legacy_simulator_disabled": True,
            "economic_executor_complete": False,
            "all_doctrine_bindings_closed": False,
            "additional_fixes": [
                "Harmonic hard invalidation while awaiting Type I",
                "Harmonic absorbing lifecycle invalidation",
                "Classical strictly later retest",
                "Dow recovery reversal priority and restart",
                "protected reader rejects overbroad cutoff before backend call",
            ],
        },
    )
    locked = list(args.downloads.glob("*GATE2*LOCKED*RESPONSES*.json"))
    # Existence alone never confers a lock, identity, corpus binding or fidelity pass.
    primary_locked = second_locked = False
    if locked:
        write_json(
            output / "10_GATE2_REVIEW_RECONCILIATION.json",
            {
                "status": "REVIEW_FILES_REQUIRE_SCHEMA_CORPUS_IDENTITY_DISPOSITION_VALIDATION",
                "files": [str(p) for p in locked],
                "gate2_pass": False,
            },
        )
        blockers.append("EXISTING_REVIEW_FILES_NOT_YET_ADJUDICATED")
    certificate = {
        "GATE1_FUNDED_SCOPE": "FAIL",
        "GATE1_ENGINE_CONTRACTS": "PASS",
        "GATE2_PIPELINE": "PASS",
        "GATE2_SAMPLE_VALID": "YES",
        "GATE2_PRIMARY_REVIEW_LOCKED": "YES" if primary_locked else "NO",
        "GATE2_SECOND_REVIEW_LOCKED": "YES" if second_locked else "NO",
        "GATE2_MATERIAL_IMPLEMENTATION_BUGS_OPEN": None,
        "GATE2_MATERIAL_SPEC_AMBIGUITIES_IN_FUNDED_SCOPE": None,
        "review_defect_counts_status": "NOT_ADJUDICATED_NO_HUMAN_LOCKS",
        "GATE2_STATUS": "HUMAN_REVIEW_REQUIRED",
        "ALL_SCHOOL_DOCTRINE_BINDINGS_CLOSED": "NO",
        "FUNDED_GRAMMARS": [],
        "UNFUNDED_DIAGNOSTIC_GRAMMARS": list(pipe.SYSTEMS),
        "GATE3_TECHNICAL_PRECONDITIONS": "FAIL",
        "GATE3_PRECOMMIT_SPEC": "PASS",
        "GATE3_CONFIG_HASH": gate3.config_hash(spec),
        "GATE3_RUNNER_BUILT": "YES_DISABLED_VALIDATOR_ONLY",
        "GATE3_RUNNER_SYNTHETIC_TESTS": "PENDING_FINAL_TEST_EVIDENCE",
        "2024_ROWS_ACCESSED": "NO",
        "2025_ROWS_ACCESSED": "NO",
        "ECONOMIC_REPLAY_EXECUTED": "NO",
        "PNL_QUALIFICATION_EXECUTED": "NO",
        "GATE3_DATA_REPLAY_EXECUTED": "NO",
        "PRODUCTION_PROMOTION": "NO",
        "PUSH": "NO",
        "READY_FOR_SINGLE_GATE3_REPLAY": "NO",
        "blockers": blockers,
        "sample_count": count,
        "reserve_count": reserve,
        "qualification_claim": "EXPOSED_RESEARCH_ONLY",
        "economic_replay_authorized_by_this_task": False,
    }
    write_json(output / "17_FINAL_PRE_REPLAY_CERTIFICATE.json", certificate)
    print(json.dumps(certificate, indent=2), flush=True)


if __name__ == "__main__":
    main()
