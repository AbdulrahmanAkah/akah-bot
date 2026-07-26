"""Execute only the pending, pre-registered AMS V4 trial matrix."""

from __future__ import annotations

import json

from scripts.research.run_ams_v4_trial import LEDGER_PATH, load_panel, run_trial


def main() -> None:
    ledger = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
    panel = load_panel()
    completed: list[str] = []
    for trial in ledger["trial_plan"]:
        if trial["trial_status"] != "REGISTERED_NOT_EXECUTED":
            continue
        report = run_trial(trial["configuration_id"], trial["portfolio_profile_id"], panel=panel)
        completed.append(str(report))
    print(json.dumps({"completed": completed}, indent=2))


if __name__ == "__main__":
    main()
