# ruff: noqa
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from spotbot.research.ams_v4_active_conviction_swing import file_sha256
from spotbot.research.ams_v5_active_pullback_reacceleration import (
    build_configuration_grid,
    portfolio_profiles,
)

ROOT = Path.cwd()
REPORTS = ROOT / "reports/research"


def write(path: Path, value: dict[str, Any]) -> None:
    text = json.dumps(value, indent=2, sort_keys=True) + "\n"
    handle, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(text)
        os.replace(temporary, path)
    except BaseException:
        if os.path.exists(temporary): os.unlink(temporary)
        raise


def main() -> None:
    source = json.loads((REPORTS / "ams-v3-4h-dataset-registration-v1.json").read_text())
    for record in source["datasets"].values():
        if file_sha256(ROOT / record["path"]) != record["file_sha256"]:
            raise RuntimeError("Registered dataset hash mismatch")
    configurations = list(build_configuration_grid())
    profiles = [profile.__dict__ for profile in portfolio_profiles()]
    trial_plan = [
        {"trial_id": f"AMS-V5-T{i:02d}", "configuration_id": c["configuration_id"], "portfolio_profile_id": p["profile_id"], "trial_status": "REGISTERED_NOT_EXECUTED"}
        for i, (c, p) in enumerate(((c, p) for c in configurations for p in profiles), 1)
    ]
    protocol = {"schema_version":"ams-v5-active-pullback-protocol-v1","protocol_id":"AMS-V5-ACTIVE-PULLBACK-REACCELERATION","research_window":{"start":"2021-01-01","end_exclusive":"2025-01-01"},"execution_rule":"SIGNAL_CLOSE_NEXT_BAR_OPEN","threshold_selection":"TRAIN_ONLY_50_OR_55","runner_only":True,"trial_budget":{"authorized_trials":24,"executed_trials":0,"remaining_trials":24},"test_2025_accessed":False,"holdout_2026_accessed":False}
    ledger = {"schema_version":"ams-v5-experiment-ledger-v1","protocol_id":protocol["protocol_id"],"data_registration":source["datasets"],"alpha_configurations":configurations,"portfolio_profiles":profiles,"trial_plan":trial_plan,"trial_accounting":{"authorized_trials":24,"executed_trials":0,"remaining_trials":24,"test_2025_accessed":False,"holdout_2026_accessed":False}}
    readiness = {"schema_version":"ams-v5-data-readiness-v1","status":"READY_FOR_AMS_V5_TRIALS","dataset_hashes":{k:v["file_sha256"] for k,v in source["datasets"].items()},"test_2025_accessed":False,"holdout_2026_accessed":False,"next_action":"RUN_AMS_V5_T01"}
    matrix = {"schema_version":"ams-v5-trial-matrix-v1","status":"REGISTERED_NOT_EXECUTED","authorized_trials":24,"executed_trials":0,"remaining_trials":24,"matrix":trial_plan,"test_2025_accessed":False,"holdout_2026_accessed":False}
    write(REPORTS / "ams-v5-active-pullback-protocol-v1.json", protocol); write(REPORTS / "ams-v5-experiment-ledger-v1.json", ledger); write(REPORTS / "ams-v5-data-readiness-v1.json", readiness); write(REPORTS / "ams-v5-trial-matrix-registration-v1.json", matrix)


if __name__ == "__main__": main()
