"""Affected-scope non-economic recertification; preserve the original evidence."""

from __future__ import annotations

import argparse
import json
import shutil
import zipfile
from pathlib import Path

from run_master_gate2_closure import make_packet, write_json

from spotbot.research.multi_school_fidelity import akah_replay_ready_detectors_v1 as det
from spotbot.research.multi_school_fidelity import fidelity_pipeline as pipe
from spotbot.research.multi_school_fidelity import gate3_precommit as gate3
from spotbot.research.multi_school_fidelity.akah_foundation_core_v1r1 import utc


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    repo = Path.cwd()
    destination = output / "ICT_RECERTIFICATION_V2"
    destination.mkdir()  # Never overwrite an existing recertification.
    original = output / "PRE_ICT_REPAIR"
    original.mkdir()
    audit = json.loads((output / "06_GATE2_SAMPLING_AUDIT.json").read_text())
    with zipfile.ZipFile(output / "09_GATE2_SEALED_ENGINE_TRACE.zip") as archive:
        prior = json.loads(archive.read("CASE_MAP_AND_ENGINE_TRACE.json"))
    # Only retained non-ICT samples are reused, NOT re-detected or reinterpreted.
    pools = {}
    for r in prior:
        if r["system_id"] == pipe.SYSTEMS[1]:
            continue
        r = {k: v for k, v in r.items() if k not in {"case_id", "prefix_maxima", "reserve"}}
        r["time"] = utc(r["time"])
        pools.setdefault((r["system_id"], r["time"].year, r["kind"]), []).append(r)
    eligibility, api = pipe.eligibility_adapter(repo)
    cache = pipe.FrameCache(repo)
    btc, eth = cache.get("BTC-USDT"), cache.get("ETH-USDT")
    summaries = []
    for pair in audit["scanned_pairs"]:
        frames = cache.get(pair)
        tr, ev, it, summary = det.scan_ict(pair, *frames, btc[0], eth[0], eligibility)
        pipe.append_pools(
            pools,
            pair,
            frames,
            {pipe.SYSTEMS[1]: {"transitions": tr, "events": ev, "intents": it}},
            eligibility,
        )
        summaries.append(
            {
                "pair": pair,
                "transitions_count": len(tr),
                "events_count": len(ev),
                "intents_count": len(it),
                "error_count": 0,
                "summary": summary,
            }
        )
        print("ICT_RECERTIFIED=" + json.dumps(summaries[-1], default=str), flush=True)
    chosen, cells = pipe.select_cases(pools, reserve=True)
    repeated, _ = pipe.select_cases(pools, reserve=True)
    if chosen != repeated:
        raise RuntimeError("NONDETERMINISTIC_REPAIR_SAMPLE")

    def non_ict_identity(rows):
        return sorted(
            (r["system_id"], r["pair"], str(utc(r["time"])), r["kind"], r["reserve"])
            for r in rows
            if r["system_id"] != pipe.SYSTEMS[1]
        )

    if non_ict_identity(chosen) != non_ict_identity(prior):
        raise RuntimeError("UNAFFECTED_SAMPLE_CHANGED")
    old_cells = {(r["system_id"], r["year"]): r for r in audit["cells"]}
    for cell in cells:
        if cell["system_id"] != pipe.SYSTEMS[1]:
            for kind in cell["categories"]:
                cell["categories"][kind]["available"] = old_cells[
                    (cell["system_id"], cell["year"])
                ]["categories"][kind]["available"]
    corpus_sha = pipe.digest(chosen).upper()
    count, reserve = make_packet(destination, chosen, cache, corpus_sha)
    files = [p for p in destination.iterdir() if p.suffix == ".zip"]
    bindings = {p.name: pipe.source_hash(output / p.name) for p in files}
    for p in files:
        shutil.copyfile(output / p.name, original / p.name)
        shutil.copyfile(p, output / p.name)
    for name in (
        "06_GATE2_SAMPLING_AUDIT.json",
        "12_GATE3_PRECOMMIT_SPEC.json",
        "15_GATE3_FROZEN_HASH_MANIFEST.json",
        "17_FINAL_PRE_REPLAY_CERTIFICATE.json",
    ):
        shutil.copyfile(output / name, original / name)
    audit.update(
        corpus_sha256=corpus_sha,
        cells=cells,
        case_count=count,
        reserve_count=reserve,
        affected_scope_recertification="ICT_ONLY_NO_OTHER_DETECTOR_RERUN",
        version=2,
        readers_recertification=cache.audit,
    )
    write_json(output / "06_GATE2_SAMPLING_AUDIT.json", audit)
    write_json(output / "12_GATE3_PRECOMMIT_SPEC.json", gate3.specification())
    manifest = json.loads((output / "15_GATE3_FROZEN_HASH_MANIFEST.json").read_text())
    manifest["config_sha256"] = gate3.config_hash(gate3.specification())
    manifest["corpus_sha256"] = corpus_sha
    write_json(output / "15_GATE3_FROZEN_HASH_MANIFEST.json", manifest)
    cert = json.loads((output / "17_FINAL_PRE_REPLAY_CERTIFICATE.json").read_text())
    cert["GATE3_CONFIG_HASH"] = gate3.config_hash(gate3.specification())
    write_json(output / "17_FINAL_PRE_REPLAY_CERTIFICATE.json", cert)
    proof = json.loads((output / "05_GATE2_PIPELINE_PROOF.json").read_text())
    proof["ict_affected_scope_recertification"] = {
        "api": api,
        "scope": audit["scanned_pairs"],
        "results": summaries,
        "detector_source_sha256": pipe.source_hash(Path(det.__file__)),
        "runtime_source_sha256": pipe.source_hash(Path(det.rt.__file__)),
        "readers": cache.audit,
        "error_count": 0,
    }
    write_json(output / "05_GATE2_PIPELINE_PROOF.json", proof)
    delta = {
        "version": 2,
        "economic_data_used": False,
        "semantic_change": (
            "Every later completed ICT bar invalidates pending raid on low<=raid_low "
            "BEFORE MSS/FVG; no old-raid resurrection"
        ),
        "affected_detector": pipe.SYSTEMS[1],
        "unaffected_sample_identity": "PASS",
        "old_corpus_sha256": json.loads((original / "06_GATE2_SAMPLING_AUDIT.json").read_text())[
            "corpus_sha256"
        ],
        "new_corpus_sha256": corpus_sha,
        "old_packet_sha256": bindings,
        "new_packet_sha256": {p.name: pipe.source_hash(p) for p in files},
        "case_count": count,
        "reserve_count": reserve,
        "prior_reviews_exist": False,
        "gate3_replay_executed": False,
    }
    write_json(output / "ICT_SEMANTIC_DELTA_AND_RECERTIFICATION_V2.json", delta)
    with (output / "18_FULL_LOG.txt").open("a", encoding="utf-8") as log:
        log.write("\nICT_SCOPE_RECERTIFICATION_V2=" + json.dumps(delta, default=str) + "\n")
        log.write(json.dumps(summaries, default=str) + "\n")
    print("PRIMARY=" + str(count) + ":RESERVE=" + str(reserve))


if __name__ == "__main__":
    main()
