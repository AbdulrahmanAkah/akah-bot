from __future__ import annotations

from pathlib import Path

from scripts.research.run_ams_v4_trial import load_object, write_json_atomically


def test_atomic_json_writer_replaces_only_valid_json(tmp_path: Path) -> None:
    path = tmp_path / "ledger.json"
    write_json_atomically(path, {"status": "REGISTERED_NOT_EXECUTED", "trials": 24})

    assert load_object(path) == {"status": "REGISTERED_NOT_EXECUTED", "trials": 24}
    assert not list(tmp_path.glob("*.tmp"))


def test_trial_accounting_invariant_is_detectable() -> None:
    accounting = {"authorized_trials": 24, "executed_trials": 1, "remaining_trials": 23}
    assert (
        accounting["executed_trials"] + accounting["remaining_trials"]
        == accounting["authorized_trials"]
    )
    accounting["remaining_trials"] = 24
    assert (
        accounting["executed_trials"] + accounting["remaining_trials"]
        != accounting["authorized_trials"]
    )
