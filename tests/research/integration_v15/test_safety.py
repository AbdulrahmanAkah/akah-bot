"""No market reader: long DAGs, live veto, partial capacity and runner boundaries."""
import copy
import importlib.util
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from spotbot.research.multi_school_fidelity.integration_v15.authority import ReceiptGraph
from spotbot.research.multi_school_fidelity.structural_lifecycle_v6 import ContractError


def setup():
    path = Path(__file__).parent / "test_closure.py"
    spec = importlib.util.spec_from_file_location("v15_safety_fixture", path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    helpers = m.helpers.__wrapped__()
    f, lineage = m.f.__wrapped__(helpers)
    source, issue, h, price = m.source_arm(f, lineage, m.FUNDED[0])
    m.permit(source, f, h)
    return m, helpers, f, source, issue, h, price, m.make(helpers, f, source)


def test_long_receipt_chain_no_recursion_and_ancestor_tamper():
    at = datetime(2023, 1, 1, tzinfo=timezone.utc)
    graph = ReceiptGraph("a"*64, "b"*64)
    root = graph.append("SOURCE", {}, at)
    parent = root
    for n in range(2500):
        parent = graph.append("OWNER", {"n": n}, at+timedelta(hours=n+1), (parent,))
    graph.verify(parent, at+timedelta(hours=2500))
    graph.nodes[root] = replace(graph.nodes[root], payload_json="bad")
    with pytest.raises(ContractError, match="TAMPER"):
        graph.verify(parent, at+timedelta(hours=2500))


def test_dow_death_after_preview_vetoes_actual_fill(monkeypatch):
    m, helpers, f, source, issue, h, price, consumer = setup()
    original = consumer.pipeline._bind
    def change(candidate, now, *args, **kwargs):
        result = original(candidate, now, *args, **kwargs)
        assert result[0]
        source.permission = replace(source.permission, complete=False, direction="UNKNOWN")
        return result
    monkeypatch.setattr(consumer.pipeline, "_bind", change)
    with pytest.raises(ContractError, match="DOW_CONTEXT_CHANGED"):
        consumer.on_open(helpers.open_packet(f, h, price))
    assert not consumer.pipeline.execution.portfolio.k.fills


def test_kernel_cannot_bypass_owned_source_guard():
    m, helpers, f, source, issue, h, price, consumer = setup()
    with pytest.raises(ContractError, match="CAPABILITY"):
        consumer.pipeline.execution.portfolio.k.admit({"owner_grammar": m.FUNDED[0], "identity": "forged"})


def test_source_preserving_preview_has_isolated_book():
    m, helpers, f, source, issue, h, price, consumer = setup()
    execution = consumer.pipeline.execution
    preview = copy.deepcopy(execution)
    assert preview.receipt_graph is execution.receipt_graph
    assert preview.portfolio.k is not execution.portfolio.k
    assert preview.context_validator is execution.context_validator
    preview.portfolio.k.cash = 0
    assert execution.portfolio.k.cash == 100000


def test_capacity_partial_stop_receipts_and_pending_exit():
    m, helpers, f, source, issue, h, price, consumer = setup()
    assert consumer.on_open(helpers.open_packet(f, h, price, 1000))[0]
    # Entry consumed all capacity. A stop touch cannot fabricate a full close.
    stop = consumer.pipeline.execution.managers[1].hard_stop
    consumer.on_completed_hour(helpers.close_packet(f, f.bar(h, price, price+1, stop-1, stop)))
    assert consumer.pipeline.execution.portfolio.k.positions
    m.permit(source, f, h+1)
    source.queue = ()
    consumer.on_open(helpers.open_packet(f, h+1, stop, 200))
    fills = consumer.pipeline.execution.portfolio.k.fills
    assert fills[-1]["side"] == "SELL" and fills[-1]["qty"] < fills[0]["qty"]
    assert consumer.pipeline.execution.portfolio.k.positions
    consumer.on_completed_hour(helpers.close_packet(f, f.bar(h+1, stop, stop+1, stop-1, stop)))
    assert consumer.trace.verify(list(consumer.trace.nodes)[-1], f.at(h+2))


def test_native_windows_memory_measurement():
    from scripts.research.integration_v15.runner import memory_usage
    rss, peak = memory_usage()
    assert 0 < rss <= peak


def test_e2e_receipts_are_deterministic_across_fresh_instances():
    path = Path(__file__).parent / "test_closure.py"
    spec = importlib.util.spec_from_file_location("v15_deterministic_fixture", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    helpers = module.helpers.__wrapped__()
    outputs = []
    for _ in range(2):
        f, lineage = module.f.__wrapped__(helpers)
        consumer, result = module.run_arm(helpers, f, lineage, module.FUNDED[0])
        outputs.append(result["receipt_graph"])
    assert outputs[0] == outputs[1]


def test_runner_current_mission_cannot_execute(monkeypatch, tmp_path):
    from scripts.research.integration_v15 import runner
    # Even with fake readiness, a missing/new-task authorization fails BEFORE
    # the data loader. This exercises the barrier, not any portfolio outcome.
    (tmp_path/runner.OUT).mkdir(parents=True)
    (tmp_path/".akah_bot").mkdir()
    import json
    (tmp_path/runner.OUT/"gate3_precommit.json").write_text(json.dumps({"precommit_sha256": "frozen"}))
    (tmp_path/runner.OUT/"readiness_certificate.json").write_text("{}")
    (tmp_path/".akah_bot/active_task.json").write_text(json.dumps({"task_id": "AKAH_FINAL_AUTHORITY_GAPS_TO_REPLAY_READY_MISSION_V1"}))
    monkeypatch.setattr(runner, "preflight", lambda *_a: None)
    monkeypatch.setattr(runner, "raw_frame", lambda *_a, **_k: pytest.fail("market read"))
    with pytest.raises(ContractError, match="EXPLICIT_FROZEN_REPLAY"):
        runner.execute_authorized(tmp_path, {"explicit_user_replay_authorization": True}, tmp_path/"governance/new_run")
