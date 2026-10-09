"""Offline safety tests; real acquisition is never invoked by tests."""

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

SPEC = importlib.util.spec_from_file_location(
    "rnb_acquisition",
    Path(__file__).resolve().parents[2] / "scripts/research/run_rnb_2022_acquisition.py",
)
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


def test_write_is_immutable(tmp_path):
    path = tmp_path / "contract.json"
    runner.write_new(path, {"value": 1})
    with pytest.raises(FileExistsError):
        runner.write_new(path, {"value": 2})
    assert json.loads(path.read_text()) == {"value": 1}


def test_nonempty_root_rejected_before_membership_or_network(tmp_path, monkeypatch):
    runner.write_new(tmp_path / "exists.json", {})
    monkeypatch.setattr(runner, "TARGET", tmp_path)
    monkeypatch.setattr(runner, "pair_scope", lambda: pytest.fail("must not read membership"))
    with pytest.raises(ValueError, match="empty/absent"):
        runner.preflight()


def test_pair_scope_matches_native_window_intersection(monkeypatch):
    def snapshot(universe, year, pair):
        return SimpleNamespace(
            universe_id=universe,
            members=((pair, 1),),
            decision_time=pd.Timestamp(f"{year}-01-01", tz="UTC"),
            effective_end=pd.Timestamp(f"{year + 1}-01-01", tz="UTC"),
        )

    monkeypatch.setattr(runner, "sha", lambda p: runner.MEMBERSHIP_SHA)
    monkeypatch.setattr(
        runner,
        "load_membership",
        lambda p: (
            [snapshot(u, 2022, "ETH-USDT") for u in ("C2", "D2", "E2")]
            + [snapshot("C2", 2023, "OTHER-USDT")]
        ),
    )
    assert runner.pair_scope() == ["BTC-USDT", "ETH-USDT"]


def test_membership_hash_drift_rejected(monkeypatch):
    monkeypatch.setattr(runner, "sha", lambda p: "wrong")
    with pytest.raises(ValueError, match="authority drift"):
        runner.pair_scope()


def test_acquisition_refuses_drift_before_client_creation(tmp_path, monkeypatch):
    runner.write_new(tmp_path / "preflight.json", {"pairs": ["BTC-USDT"]})
    monkeypatch.setattr(runner, "EVIDENCE", tmp_path)
    monkeypatch.setattr(runner, "pair_scope", lambda: ["ETH-USDT"])
    monkeypatch.setattr(runner.ccxt, "kucoin", lambda _: pytest.fail("network client forbidden"))
    with pytest.raises(ValueError, match="scope drift"):
        runner.acquire()
