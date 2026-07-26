"""Resume and execute the registered AMS V5R1 matrix only."""

from __future__ import annotations

import json

from ams_v5r1_native_common import load_registered_panel
from run_ams_v5r1_trial import LEDGER, run_trial


def main() -> None:
    panel, _hashes = load_registered_panel()
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    for trial in ledger["trial_plan"]:
        if trial["trial_status"] == "REGISTERED_NOT_EXECUTED":
            path = run_trial(
                trial["configuration_id"],
                trial["portfolio_profile_id"],
                panel=panel,
            )
            print(f"{trial['trial_id']}={path.name}", flush=True)


if __name__ == "__main__":
    main()
