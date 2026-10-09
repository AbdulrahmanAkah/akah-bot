"""Single frozen runner; current invocation is preflight, never economics.

Future economics requires a DIFFERENT active governed task and an explicit
authorization manifest bound to this freeze. No command-line boolean arms it.
"""
from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import time
import ctypes
from collections import Counter, deque
from datetime import timedelta
from heapq import heappop, heappush
from pathlib import Path

import pandas as pd

from .precommit import OUT, PROTOCOL, INPUT_MANIFEST, build, sha, require_ready
from spotbot.research.multi_school_fidelity.akah_foundation_core_v1r1 import raw_frame, load_broad_eligibility, utc
from spotbot.research.multi_school_fidelity.gate3_market_v3 import bounded_sha
from spotbot.research.multi_school_fidelity.integration_v13.historical_inputs import MembershipSource, MembershipSnapshot
from spotbot.research.multi_school_fidelity.integration_v13.guarded_driver import ClosePacket, OpenPacket
from spotbot.research.multi_school_fidelity.integration_v13.research_bridge import ApproximateRule, ResearchScope, ProducerCertificate
from spotbot.research.multi_school_fidelity.integration_v13.scheduler import BoundedScheduler
from spotbot.research.multi_school_fidelity.integration_v14.authority import FUNDED
from spotbot.research.multi_school_fidelity.integration_v14.bridge import ScopedExecution, ScopedPipeline, ScopedRouter
from spotbot.research.multi_school_fidelity.integration_v14.source_provider import ScopedSourceProvider
from spotbot.research.multi_school_fidelity.integration_v14.driver import ScopedDriver
from spotbot.research.multi_school_fidelity.structural_lifecycle_v6 import CompletedBar, ContractError
from spotbot.research.multi_school_fidelity.full_replay_v5 import Portfolio


def memory_usage():
    """Native Windows working-set measurement; no additional dependency."""
    class Counters(ctypes.Structure):
        _fields_ = [("cb", ctypes.c_ulong), ("faults", ctypes.c_ulong)] + [
            (name, ctypes.c_size_t) for name in ("peak", "rss", "peak_paged", "paged",
                "peak_nonpaged", "nonpaged", "pagefile", "peak_pagefile")]
    info = Counters()
    info.cb = ctypes.sizeof(info)
    function = ctypes.windll.psapi.GetProcessMemoryInfo
    function.argtypes = [ctypes.c_void_p, ctypes.POINTER(Counters), ctypes.c_ulong]
    if not function(ctypes.c_void_p(-1), ctypes.byref(info), info.cb):
        raise OSError("Native Windows process memory measurement failed")
    return info.rss, info.peak


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.name not in {"mechanical_smoke.json", "preflight_certificate.json"}:
        raise ContractError("IMMUTABLE_OUTPUT_ALREADY_EXISTS:" + str(path))
    def encode(x):
        return dataclasses.asdict(x) if dataclasses.is_dataclass(x) else str(x)
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, sort_keys=True, indent=2, default=encode)
        stream.write("\n")


def membership(repo, manifest):
    ranking = load_broad_eligibility(repo)
    actual = hashlib.sha256(pd.util.hash_pandas_object(
        ranking[["decision_time", "pair", "eligible", "adjusted_rank"]], index=False).values.tobytes()).hexdigest().upper()
    if actual != manifest["membership_bounded_sha256"]:
        raise ContractError("PIT_MEMBERSHIP_INPUT_DRIFT")
    groups = list(ranking.groupby("decision_time", sort=True))
    snapshots = tuple(MembershipSnapshot(t.to_pydatetime(),
        (groups[i+1][0] if i+1 < len(groups) else utc("2024-01-01")).to_pydatetime(),
        frozenset(g.pair.astype(str)), actual) for i, (t, g) in enumerate(groups))
    return MembershipSource(snapshots)


def hours(frame, start, end):
    for row in frame.itertuples(index=False):
        close = utc(row.timestamp).to_pydatetime()
        begin = close - timedelta(hours=1)
        if begin < utc(start).to_pydatetime() or close >= utc(end).to_pydatetime():
            continue
        yield CompletedBar(begin, close, "1H", float(row.open), float(row.high), float(row.low), float(row.close)), float(row.volume)


def merged(streams):
    """O(rows log available-pairs); no candidate x incumbent/school enumeration."""
    heap = []
    iterators = {p: iter(s) for p, s in streams.items()}
    for pair, stream in iterators.items():
        item = next(stream, None)
        if item is not None:
            heappush(heap, (item[0].start, pair, item))
    while heap:
        at = heap[0][0]
        current = {}
        while heap and heap[0][0] == at:
            _, pair, item = heappop(heap)
            current[pair] = item
        yield at, current
        for pair in current:
            item = next(iterators[pair], None)
            if item is not None:
                heappush(heap, (item[0].start, pair, item))


def mechanical_smoke(repo):
    repo = Path(repo).resolve()
    frozen = build(repo)
    protocol = json.loads((repo / PROTOCOL).read_text())
    manifest = json.loads((repo / INPUT_MANIFEST).read_text())
    memberships = membership(repo, manifest)
    started = time.perf_counter()
    peak = memory_usage()[0]
    data = [{} for _ in protocol["preflight_windows"]]
    source_shas, observed = {}, []
    for i, record in enumerate(manifest["pairs"]):
        frame = raw_frame(repo, record["pair"])
        if bounded_sha(frame) != record["bounded_sha256"]:
            raise ContractError("BOUNDED_SOURCE_SHA_DRIFT:" + record["pair"])
        source_shas[record["pair"]] = record["bounded_sha256"]
        observed.append({"pair": record["pair"], "rows_hashed": len(frame),
                         "sha256": record["bounded_sha256"]})
        for j, window in enumerate(protocol["preflight_windows"]):
            selected = frame.loc[(frame.timestamp >= utc(window["start"])) &
                                 (frame.timestamp < utc(window["end_exclusive"]))].copy()
            data[j][record["pair"]] = selected
        peak = max(peak, memory_usage()[0])
        if i % 50 == 0:
            print("BOUNDED_INPUT_SHA_VERIFIED=" + str(i+1), flush=True)
    counts, diagnostic, windows = Counter(), Counter(), []
    checkpoints = 0
    for j, window in enumerate(protocol["preflight_windows"]):
        provider = ScopedSourceProvider(source_shas, memberships, frozen["source_version_sha256"])
        streams = {p: hours(frame, window["start"], window["end_exclusive"]) for p, frame in data[j].items()}
        pair_ticks, ready, window_checkpoints = 0, 0, 0
        for at, items in merged(streams):
            packet = ClosePacket(tuple((p, x[0]) for p, x in sorted(items.items())),
                                 tuple((p, x[1]) for p, x in sorted(items.items())))
            provider.on_completed_hour(packet)
            now = next(iter(items.values()))[0].end
            # Drain ready events even in warmup, so no unbounded stale queue.
            produced = tuple(provider.queue.pop(now, ()))
            if at >= utc(window["count_from"]).to_pydatetime():
                pair_ticks += len(items)
                ready += len(produced)
                counts.update(r.issue.event["system_id"] for r in produced)
            checkpoints += len(items)
            window_checkpoints += len(items)
            if at.hour == 0:
                peak = max(peak, memory_usage()[0])
                print("MECHANICAL_CHECKPOINT=" + str(at), flush=True)
        diagnostic.update(provider.diagnostics)
        windows.append({**window, "pair_checkpoints": window_checkpoints,
                        "counted_pair_checkpoints": pair_ticks, "ready_candidates": ready,
                        "feed_count": len(provider.feeds)})
        del provider
    report = {"source_version_sha256": frozen["source_version_sha256"], "complete": True,
              "pairs_inspected": len(observed), "available_pairs": len(manifest["pairs"]),
              "eligible_pairs": manifest["eligible_pairs"], "missing_raw_pairs": manifest["missing_raw_pairs"],
              "checkpoint_count": checkpoints, "ready_candidate_count": sum(counts.values()),
              "ready_by_grammar": dict(counts), "diagnostics": dict(diagnostic), "windows": windows,
              "input_authorities": observed, "wall_seconds": time.perf_counter()-started,
              "peak_rss_bytes": peak, "peak_working_set_bytes": memory_usage()[1],
              "execution_fills": 0, "portfolio_created": False, "qualification_calculated": False,
              "economic_replay_executed": False, "pnl_read": False,
              "2024_rows_accessed": False, "2025_rows_accessed": False,
              "membership_source_sha256": manifest["membership_bounded_sha256"],
              "clock": "CLOSE_TIMESTAMP_AUTHORITY; OPEN=PRIOR_HOUR; CANONICAL_COMPLETE_BUCKETS",
              "protected_payloads": "Never whole-file hash/read; canonical pre-2024 predicate only",
              "interpretation": "Mechanics/scalability evidence only; NOT trade frequency or profitability evidence"}
    save(repo / OUT / "mechanical_smoke.json", report)
    return report


def preflight(repo):
    repo = Path(repo).resolve()
    frozen = json.loads((repo / OUT / "gate3_precommit.json").read_text())
    certificate = json.loads((repo / OUT / "readiness_certificate.json").read_text())
    require_ready(repo, frozen, certificate)
    return {"GATE3_REPLAY_PREFLIGHT": "PASS", "FUNDED_GRAMMARS": list(FUNDED),
            "READY_FOR_SINGLE_GATE3_REPLAY": "YES", "ECONOMIC_REPLAY_EXECUTED": "NO",
            "source_version_sha256": frozen["source_version_sha256"],
            "precommit_sha256": frozen["precommit_sha256"]}


def execute_authorized(repo, authorization, output):
    """Built but NOT executed in closure; refuses this mission's active task."""
    repo = Path(repo).resolve()
    preflight(repo)
    frozen = json.loads((repo / OUT / "gate3_precommit.json").read_text())
    ready = json.loads((repo / OUT / "readiness_certificate.json").read_text())
    active = json.loads((repo / ".akah_bot/active_task.json").read_text())
    required_task = "AKAH_SINGLE_FROZEN_GATE3_REPLAY_V14"
    if (authorization.get("task_id") != required_task or active.get("task_id") != required_task
            or authorization.get("explicit_user_replay_authorization") is not True
            or authorization.get("precommit_sha256") != frozen["precommit_sha256"]):
        raise ContractError("NEW_GOVERNED_TASK_AND_EXPLICIT_FROZEN_REPLAY_AUTHORIZATION_REQUIRED")
    # Hard forbid output outside the research output directory or reuse of a run.
    output = Path(output).resolve()
    if not output.is_relative_to((repo / "governance").resolve()) or output.exists():
        raise ContractError("FRESH_RESEARCH_OUTPUT_DIRECTORY_REQUIRED")
    manifest = json.loads((repo / INPUT_MANIFEST).read_text())
    memberships = membership(repo, manifest)
    inputs = {r["pair"]: r["bounded_sha256"] for r in manifest["pairs"]}
    scope = ResearchScope(frozen["source_hashes"][PROTOCOL], frozen["source_version_sha256"])
    certificates = tuple(ProducerCertificate(g, scope.source_version_sha256, scope.protocol_sha256,
        ready["evidence"]["synthetic_results.xml"]["sha256"], "SOURCE_BOUND_RESEARCH_IMPLEMENTATION_PASS",
        "SYNTHETIC_IMPLEMENTATION_READINESS_NOT_HISTORICAL_CERTIFICATION") for g in FUNDED)
    # One arm at a time; input streams bounded individually, no legacy V5 replay.
    for arm in frozen["contract"]["arms"]:
        scenario = arm.split("|")[1]
        provider = ScopedSourceProvider(inputs, memberships, frozen["source_version_sha256"])
        execution = ScopedExecution(Portfolio(frozen["contract"]["costs_round_trip"][scenario],
                        {p: ApproximateRule(p, scope) for p in inputs}))
        provider.attach_execution(execution)
        pipeline = ScopedPipeline(execution, ScopedRouter(scope, certificates))
        consumer = ScopedDriver(repo, frozen, pipeline, provider, arm=arm,
            readiness_receipt=ready, certificate_provider=lambda now, f, g: (
                next(c for c in certificates if c.grammar == g),))
        def stream(record):
            frame = raw_frame(repo, record["pair"])
            if bounded_sha(frame) != record["bounded_sha256"]:
                raise ContractError("BOUNDED_SOURCE_DRIFT")
            yield from hours(frame, "2021-09-01", "2024-01-01")
        streams = {r["pair"]: stream(r) for r in manifest["pairs"]}
        from spotbot.research.multi_school_fidelity.integration_v14.scheduler import ScopedScheduler
        result = ScopedScheduler(streams).run(consumer)
        save(output / (arm.replace("|", "_") + ".json"), result)
    save(output / "run_manifest.json", {"authorization": authorization,
         "precommit_sha256": frozen["precommit_sha256"], "arms": frozen["contract"]["arms"],
         "qualification": "NOT_AUTOMATICALLY_CERTIFIED; retain ledgers for fixed qualification evaluator"})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mechanical-smoke", action="store_true")
    args = parser.parse_args()
    report = mechanical_smoke(Path.cwd()) if args.mechanical_smoke else preflight(Path.cwd())
    print(json.dumps({k: v for k, v in report.items() if k in {
        "GATE3_REPLAY_PREFLIGHT", "READY_FOR_SINGLE_GATE3_REPLAY", "ECONOMIC_REPLAY_EXECUTED",
        "pairs_inspected", "checkpoint_count", "ready_candidate_count", "wall_seconds", "peak_rss_bytes"}}, indent=2))


if __name__ == "__main__":
    main()
