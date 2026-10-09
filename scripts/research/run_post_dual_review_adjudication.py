# ruff: noqa: E501 -- long evidence-bound adjudication descriptions, not runtime rules
"""Bounded Gate2 source adjudication. Never imports or runs an economic replay."""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import shutil
from collections import Counter
from pathlib import Path

import pandas as pd

from spotbot.research.multi_school_fidelity import akah_census_fastpath_v1 as fast
from spotbot.research.multi_school_fidelity import akah_full_fidelity_runtime_v1 as rt
from spotbot.research.multi_school_fidelity import akah_replay_ready_detectors_v1 as det
from spotbot.research.multi_school_fidelity import fidelity_pipeline as pipe
from spotbot.research.multi_school_fidelity import gate3_precommit as gate3
from spotbot.research.multi_school_fidelity import operational_ai_review as review
from spotbot.research.multi_school_fidelity.akah_foundation_core_v1r1 import utc
from spotbot.research.multi_school_fidelity.review_validation import ROLES

TASK = "AKAH_POST_DUAL_REVIEW_GATE2_ADJUDICATION_PRE_GATE3_CLOSURE_V2"
OUT = Path("governance/post_dual_review_gate2_adjudication_pre_gate3_closure_v2")
CORPUS = "199C3725355E8757E93815286DF01273AF22BF73277588313F945EE27FCD99AC"


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8"
    )


def table(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        raise ValueError("EMPTY_AUDIT_TABLE")
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def authorities(repo, downloads):
    packet = downloads / "AKAH_MASTER_GATE2_GATE3_PRECOMMIT_V1_20261002_FINAL"
    extra = downloads / "AKAH_GATE2_REQUIRED_REVIEW_INPUTS_FOR_CODEX"
    ids = {f"G2-P-{i:04}" for i in range(1, 99)}
    a = review.locked_ai(
        downloads / "AKAH_GATE2_CODEX_AI_DIAGNOSTIC_REVIEW_20261002.json", "proxy", ids, CORPUS
    )
    b = review.locked_ai(
        extra / "AKAH_GATE2_INDEPENDENT_DOMAIN_REVIEWER_LOCKED_RESPONSES_AI_V1.json",
        "independent",
        ids,
        CORPUS,
    )
    claim_path = extra / "AKAH_GATE2_DUAL_AI_REVIEW_RECONCILIATION_V1/03_RECONCILIATION.json"
    if (
        pipe.source_hash(claim_path)
        != "8D74D8EA90DC2F276003A27D69348F339DAB0079BAF4A00555FDCE4DF0F00D81"
    ):
        raise ValueError("RECONCILIATION_HASH_DRIFT")
    claimed = json.loads(claim_path.read_text(encoding="utf-8"))
    delta = json.loads((packet / "ICT_SEMANTIC_DELTA_AND_RECERTIFICATION_V2.json").read_text())
    trace_sha = delta["new_packet_sha256"]["09_GATE2_SEALED_ENGINE_TRACE.zip"]
    rows, proof = review.bound_trace(
        packet / "09_GATE2_SEALED_ENGINE_TRACE.zip", trace_sha, a, b, claimed
    )
    bindings = {
        str(p): pipe.source_hash(p)
        for p in (
            Path(a["path"]),
            Path(b["path"]),
            claim_path,
            packet / "09_GATE2_SEALED_ENGINE_TRACE.zip",
            packet / "06_GATE2_SAMPLING_AUDIT.json",
            packet / "12_GATE3_PRECOMMIT_SPEC.json",
            packet / "ICT_SEMANTIC_DELTA_AND_RECERTIFICATION_V2.json",
        )
    }
    spec = json.loads((packet / "12_GATE3_PRECOMMIT_SPEC.json").read_text())
    if gate3.config_hash(spec) != gate3.config_hash(gate3.specification()):
        raise ValueError("FROZEN_GATE3_SPEC_DRIFT")
    source_proof = json.loads((packet / "05_GATE2_PIPELINE_PROOF.json").read_text())
    ic = source_proof["ict_affected_scope_recertification"]
    for module, key in ((det, "detector_source_sha256"), (rt, "runtime_source_sha256")):
        if pipe.source_hash(Path(module.__file__)) != ic[key]:
            raise ValueError("RECERTIFIED_DETECTOR_SOURCE_DRIFT")
    proof["quarantined_stale_extracted_trace"] = {
        "path": str(
            packet / "SEALED_DO_NOT_OPEN_BEFORE_BOTH_REVIEWS/CASE_MAP_AND_ENGINE_TRACE.json"
        ),
        "sha256": pipe.source_hash(
            packet / "SEALED_DO_NOT_OPEN_BEFORE_BOTH_REVIEWS/CASE_MAP_AND_ENGINE_TRACE.json"
        ),
        "reason": "Root extraction predates ICT recertification; use hash-bound ZIP member only",
    }
    return a, b, rows, proof, spec, bindings


def adjudicate(repo, a, b, trace, spec, output):
    scoped = {r["case_id"]: r for r in trace if not r["reserve"]}
    second = {r["case_id"]: r for r in b["responses"]}
    trace_sha = "3F1598E606495AD62A5F11DD9CA2612D4125A4F5F052CDC418A5E9EB12984789"
    runtime_path = "src/spotbot/research/multi_school_fidelity/akah_full_fidelity_runtime_v1.py"
    detector_path = "src/spotbot/research/multi_school_fidelity/akah_replay_ready_detectors_v1.py"
    scope_path = "C:/Users/abdul/Downloads/AKAH_MASTER_GATE2_GATE3_PRECOMMIT_V1_20261002_FINAL/11_FUNDED_SCOPE_AND_UNRESOLVED_MATRIX.csv"
    decisions, display = {}, []
    priority = {
        "G2-P-0014",
        "G2-P-0087",
        "G2-P-0091",
        "G2-P-0093",
        "G2-P-0094",
        "G2-P-0052",
        "G2-P-0007",
        "G2-P-0057",
        "G2-P-0058",
        "G2-P-0060",
        "G2-P-0095",
        "G2-P-0098",
        "G2-P-0096",
        "G2-P-0097",
    }
    for r in a["responses"]:
        case, s = r["case_id"], scoped[r["case_id"]]
        other = second[case]
        er = s["engine_row"] or {}
        event = er.get("event", "")
        school = r["school"]
        material = (
            r["human_action"] != other["human_action"]
            or "UNRESOLVED" in (r["human_action"], other["human_action"])
            or bool(r["differences"] or other["differences"])
            or case in priority
        )
        category = "INSUFFICIENT_VIEW"
        closed = not material
        explanation = "Comments retained verbatim; aggregate agreement is not source/runtime fidelity certification. No unobserved anchors are imputed."
        if school == "ELLIOTT":
            category, closed = "DOCTRINE_SCOPE_GAP", True
            explanation = "Count consensus is explicitly diagnostic and funded_ready=false. Parent-child and owner-count grammar remain unresolved; quarantined from all funding."
        elif school == "HARMONIC":
            category, closed = "DOCTRINE_SCOPE_GAP", True
            explanation = "Family/direction/ratio/stop/management authority remains unresolved. Neither a ratio-looking chart nor an AI vote completes this matrix. Quarantined."
        elif school == "DOW":
            category, closed = "DOCTRINE_SCOPE_GAP", True
            explanation = "RECONFIRMED_BULL is CONTEXT with funded_ready=false, not a complete long setup. Protective-stop ownership is unresolved. Frozen context is exhausted separately, not generalized to other assets."
        elif school == "WYCKOFF":
            category, closed = "DOCTRINE_SCOPE_GAP", True
            explanation = "P&F count line/segment and downside stride source authority remain unresolved. No funded Wyckoff grammar is inferred from review acceptance."
            if case in {"G2-P-0087", "G2-P-0091"}:
                category, closed = "IMPLEMENTATION_BUG", False
                explanation = "API permits E_MARKUP entry at later timestamps with no LPS identity/availability/invalidation/consumption check. Detector re-evaluates readiness every 4H. This proves stale intents are possible, NOT that this particular LPS was violated; checkpoint-specific lifecycle recertification is still required. Do not invent an LPS TTL."
            elif case == "G2-P-0014":
                category, closed = "IMPLEMENTATION_BUG", False
                explanation = "HIGHER_LEVEL_RANGE_FORMS replaces context with prior_markup/range, deleting SC/AR/ST/sc_time. Reaccumulation readiness still requires PS_SC_ST and P&F from sc_time, so the no-spring/reaccumulation entry branch is unreachable under that state transition. This is a code-level defect, not proof that reviewers' exact checkpoint must be traded. Repair requires source-bound reaccumulation cause/readiness ownership."
        elif school == "CLASSICAL" and material:
            category, closed = "SPEC_AMBIGUITY", False
            explanation = "Frozen runtime accepts later low<=boundary and close>boundary (or later confirmed HL); 10-day expiry exists but no pre-entry pattern-support invalidation rule is bound. A deep correction is not rejected by that formula. Source does not authorize a depth threshold from these cases; no tightening performed."
            if case in {"G2-P-0007", "G2-P-0057", "G2-P-0058", "G2-P-0060"}:
                category = "INSUFFICIENT_VIEW"
                explanation = "Reviewers selected different visible local structures or could not identify the owner boundary. The trace owns a 4H SYMM_TRIANGLE/BASE_BREAKOUT, whereas comments often discuss a local 1H base/flag. Provide owner-neutral confirmed pivot/formation/breakout anchors; disagreement does not authorize changing the frozen parent grammar. Pre-entry invalidation ambiguity remains a separate scope blocker."
        elif school == "ICT" and material:
            category, closed = "INSUFFICIENT_VIEW", False
            explanation = "Trace binds raid<MSS/FVG creation<retrace; same-bar activation/retracement is forbidden. Review disagreement is not a demonstrated provenance bug. Review needs source-neutral past raid/structure/array anchors and expanded locked coverage."
        elif not material:
            category = "MANUAL_PREFERENCE_NOT_IN_SPEC"
            explanation = "No material reviewer difference asserted in six comments for this case; not an economic or grammar qualification claim."
        if school == "WYCKOFF" and case in {"G2-P-0093", "G2-P-0094"}:
            category, closed = "SPEC_AMBIGUITY", False
            explanation = "SPRING_TEST branch name is assigned at SPRING_RECLAIM; entry eligibility does not require a separately owned later reduced-supply spring-test event. A reviewer may require that later test while the frozen implementation does not. Source binding for the intended spring-test sequence must be completed before changing semantics; no rule is added from this disagreement."
        d = {
            "case_id": case,
            "school": school,
            "engine_kind": s["kind"],
            "engine_event": event,
            "proxy_action": r["human_action"],
            "independent_action": other["human_action"],
            "disposition": category,
            "closed": closed,
            "material": material,
            "resolution": "UNFUNDED_QUARANTINE"
            if closed and material
            else "NO_SEMANTIC_REPAIR_OR_PASS_CLAIM",
            "explanation": explanation,
            "roles_reviewed": list(ROLES),
            "comments": {
                "proxy": {k: r[k] for k in ROLES},
                "independent": {k: other[k] for k in ROLES},
            },
            "source_paths": [runtime_path, detector_path, scope_path],
            "source_shas": {
                p: pipe.source_hash(repo / p if not p.startswith("C:") else Path(p))
                for p in (runtime_path, detector_path, scope_path)
            },
            "primary_review_sha256": a["sha256"],
            "second_review_sha256": b["sha256"],
            "engine_trace_sha256": trace_sha,
            "spec_sha256": gate3.config_hash(spec),
        }
        if closed:
            d["resolution_evidence_sha256"] = pipe.digest(
                {
                    "source_shas": d["source_shas"],
                    "resolution": d["resolution"],
                    "explanation": explanation,
                }
            ).upper()
        decisions[case] = d
        display.append(
            {
                k: d[k]
                for k in (
                    "case_id",
                    "school",
                    "engine_kind",
                    "engine_event",
                    "proxy_action",
                    "independent_action",
                    "disposition",
                    "closed",
                    "explanation",
                )
            }
        )
    save(output / "case_adjudications.json", decisions)
    table(output / "case_adjudications.csv", display)
    result = review.operational_disposition_gate(a, b, decisions)
    save(output / "operational_review_disposition_result.json", result)
    return result


def dow_exhaustion(repo, downloads, output):
    path = (
        downloads
        / "AKAH_FULL_UNIVERSE_STATE_CENSUS_V1_OUT_20261001_134333/dow_market_state_census.csv"
    )
    expected = "DAA08D2688093D5C40FAF2D0C7356FDBEC01E8C077BC273F33E9D4C74A4B06F6"
    if pipe.source_hash(path) != expected:
        raise ValueError("FROZEN_DOW_FRAME_HASH_DRIFT")
    frame = pd.read_csv(
        path,
        usecols=[
            "decision_time",
            "btc_primary_trend",
            "secondary_trend",
            "confirmed",
            "volume_confirms",
            "breadth",
        ],
    )
    eligibility, _ = pipe.eligibility_adapter(repo)
    result = pipe.scan_dow_context(frame, eligibility)
    counts = Counter(utc(r["timestamp"]).year for r in result["intents"])
    proof = {
        "path": str(path),
        "sha256": expected,
        "rows_exhausted": len(frame),
        "positive_by_year": dict(counts),
        "scope": "FROZEN_BTC_CONTEXT_FRAME_ONLY",
        "global_other_grammar_scarcity_claimed": False,
        "funded_ready": False,
    }
    save(output / "dow_frozen_frame_exhaustion.json", proof)
    return proof


def supplement(repo, downloads, trace, output, count_limit=None):
    """Non-economic detector census only. Never alters locked primary/reserve identities."""
    packet = downloads / "AKAH_MASTER_GATE2_GATE3_PRECOMMIT_V1_20261002_FINAL"
    prior = json.loads((packet / "06_GATE2_SAMPLING_AUDIT.json").read_text())
    eligibility, _ = pipe.eligibility_adapter(repo)
    fast.install(det, rt)
    cache = pipe.FrameCache(repo)
    btc, eth = cache.get("BTC-USDT"), cache.get("ETH-USDT")
    market, _, _, _ = det.scan_wyckoff("BTC-USDT", btc[1], btc[0], btc[0], eligibility, None, True)
    used = {pipe.week_key(r) for r in trace}
    original = Counter(
        (r["system_id"], utc(r["time"]).year)
        for r in trace
        if not r["reserve"] and r["kind"] == "POSITIVE"
    )
    needs = {
        (sid, year): max(0, 5 - original[sid, year])
        for sid in pipe.SYSTEMS[:2]
        for year in (2022, 2023)
    }
    selected, scans, missing_raw = [], [], []
    members = set().union(*eligibility.sets)
    available = sorted(
        members - set(prior["scanned_pairs"]), key=lambda p: pipe.digest(["AKAH_GATE2_V1", p])
    )
    source_path = (
        downloads
        / "AKAH_FULL_UNIVERSE_STATE_CENSUS_V1_OUT_20261001_134333/base_thesis_intent_ledger.csv.gz"
    )
    # Existing events guide *sampling work only*, not runtime selection or profitability.
    donors = pd.read_csv(source_path, usecols=["system_id", "pair", "timestamp"])
    useful = set(donors.loc[donors.system_id.isin(pipe.SYSTEMS[:2]), "pair"])
    available = [p for p in available if p in useful] + [p for p in available if p not in useful]
    for pair in available:
        if not any(needs.values()):
            break
        if count_limit is not None and len(scans) >= count_limit:
            break
        if not (repo / "data/raw/rd16b/kucoin" / pair / "1h.parquet").is_file():
            missing_raw.append(pair)
            continue
        fast.clear_pair_caches()
        frames = cache.get(pair)
        local = []
        for sid in pipe.SYSTEMS[:2]:
            if not any(needs[sid, y] for y in (2022, 2023)):
                continue
            if sid == pipe.SYSTEMS[0]:
                _, _, intents, summary = det.scan_wyckoff(
                    pair, frames[1], frames[0], btc[0], eligibility, market, False
                )
            else:
                _, _, intents, summary = det.scan_ict(pair, *frames, btc[0], eth[0], eligibility)
            rows = [
                {
                    "system_id": sid,
                    "pair": pair,
                    "time": utc(r["timestamp"]),
                    "kind": "POSITIVE",
                    "engine_row": r,
                }
                for r in intents
                if r["broad_eligible"] and 2022 <= utc(r["timestamp"]).year <= 2023
            ]
            table_or_empty = output / "supplemental_cache" / f"{pair}.{sid}.json"
            save(
                table_or_empty,
                {
                    "source_hash": pipe.source_hash(Path(det.__file__)),
                    "bounded_input": cache.audit[pair],
                    "summary": summary,
                    "rows": rows,
                },
            )
            for row in sorted(rows, key=pipe.sampling_key):
                key = (sid, row["time"].year)
                if needs[key] and pipe.week_key(row) not in used:
                    used.add(pipe.week_key(row))
                    needs[key] -= 1
                    row["supplemental_case_id"] = f"G2-S-{len(selected) + 1:04}"
                    selected.append(row)
                    local.append(row["supplemental_case_id"])
        scans.append({"pair": pair, "selected": local})
        print("SUPPLEMENTAL_PAIR=" + pair + ":REMAINING=" + str(sum(needs.values())), flush=True)
        cache.frames.pop(pair, None)
        save(
            output / "supplemental_progress.json",
            {
                "scans": scans,
                "needs": {f"{k[0]}:{k[1]}": v for k, v in needs.items()},
                "selected": selected,
                "readers": cache.audit,
                "reviews_locked": False,
            },
        )
    proof = {
        "new_positive_cases": len(selected),
        "new_pair_scans": len(scans),
        "scanned": scans,
        "source_donor_role": "NON_ECONOMIC_SAMPLING_GUIDANCE_ONLY_NOT_FIDELITY_AUTHORITY",
        "positive_shortage": {f"{k[0]}:{k[1]}": v for k, v in needs.items()},
        "scope_exhausted": len(scans) + len(missing_raw) == len(available),
        "missing_raw": missing_raw,
        "protected_rows_loaded": 0,
        "reviews_locked": False,
        "old_primary_and_reserve_unchanged": True,
        "reader_audit": cache.audit,
        "all_positive_targets_met": not any(needs.values()),
    }
    save(output / "supplemental_positive_cases.json", selected)
    save(output / "supplemental_sampling_audit.json", proof)
    return proof


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--downloads", type=Path, default=Path("C:/Users/abdul/Downloads"))
    parser.add_argument("--supplement", action="store_true")
    parser.add_argument("--max-pairs", type=int)
    args = parser.parse_args()
    repo = Path.cwd()
    token = json.loads((repo / ".akah_bot/active_task.json").read_text())
    if token["task_id"] != TASK or token["starting_charter_revision"] != 772:
        raise ValueError("TASK_AUTHORITY_DRIFT")
    output = repo / OUT
    output.mkdir(exist_ok=True)
    a, b, trace, proof, spec, bindings = authorities(repo, args.downloads)
    save(
        output / "authority_verification.json",
        {
            "proof": proof,
            "input_sha256": bindings,
            "review_identities": [
                {k: r[k] for k in ("reviewer_id", "reviewer_type", "human_attestation", "sha256")}
                for r in (a, b)
            ],
        },
    )
    result = adjudicate(repo, a, b, trace, spec, output)
    dow = dow_exhaustion(repo, args.downloads, output)
    shutil.copyfile(
        Path("C:/Users/abdul/AppData/Local/Temp/akah_post_dual_review_v2_protocol.json"),
        output / "research_protocol.json",
    )
    old_spec_path = (
        args.downloads
        / "AKAH_MASTER_GATE2_GATE3_PRECOMMIT_V1_20261002_FINAL/12_GATE3_PRECOMMIT_SPEC.json"
    )
    shutil.copyfile(old_spec_path, output / "gate3_spec_UNARMED_UNCHANGED.json")
    save(
        output / "closure_checkpoint.json",
        {
            "task": TASK,
            "counts": [98, 50, 48, 15],
            "operational_dispositions": result,
            "dow": dow,
            "arch_dependency_available": importlib.util.find_spec("arch") is not None,
            "funded_grammars": [],
            "economic_replay": False,
            "pnl_read": False,
            "2024_access": False,
            "2025_access": False,
            "push": False,
        },
    )
    if args.supplement:
        supplement(repo, args.downloads, trace, output, args.max_pairs)
    print("AUTHORITY_AND_SOURCE_ADJUDICATION_COMPLETE; NO_ECONOMIC_REPLAY", flush=True)


if __name__ == "__main__":
    main()
