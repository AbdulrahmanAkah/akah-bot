"""Synthetic administration only: no market rows, replay, or real Git changes."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import finish_frozen_v15 as admin
from spotbot.governance import task_completion_gate as gate


class AdministrativeCloseout(unittest.TestCase):
    def exercise(self, failed):
        with tempfile.TemporaryDirectory(prefix="v15_admin_fixture_", dir=Path(__file__).parent) as directory:
            repo = Path(directory)
            root = repo / "governance/single_frozen_all_nine_gate3_replay_v15"
            root.mkdir(parents=True)
            local = repo / ".akah_bot"
            local.mkdir()
            task = "SYNTHETIC_NOT_A_REAL_GOVERNED_TASK"
            gate.save_json(local / "active_task.json", {"task_id":task,"starting_head":"fixture","starting_charter_revision":787})
            freeze = repo / "governance/all_nine_eighteen_arm_readiness_v15/gate3_precommit.json"
            gate.save_json(freeze, {"synthetic":True})
            gate.save_json(repo / gate.CHARTER_REL, {"synthetic":True})
            arms = [f"FIXTURE_{i}|{cost}" for i in range(9) for cost in ("1X","2X")]
            failures = {arms[0]:{"error":"FIXTURE_TECHNICAL_FAILURE"}} if failed else {}
            complete = [arm for arm in arms if arm not in failures]
            gate.save_json(root / "run_manifest.json", {"arms":arms,"completed_arms":complete,"technical_failures":failures,"precommit_sha256":"fixture"})
            gate.save_json(root / "qualification.json", {"decisions": {"FIXTURE":"ECONOMIC_NOT_QUALIFIED"},"production_authorized":False})
            for arm in complete:
                gate.save_json(root / (arm.replace("|","_")+"_metrics.json"), {"net":-10,"terminal_equity":99990,
                    "mdd":.01,"annual_net":{"2022":-5,"2023":-5},"campaigns":[],"risk_pass":True})
            staged = []
            def git(_repo, *args):
                if args[:2] == ("rev-parse","HEAD"):
                    return "fixture"
                if args[0] == "add":
                    staged.extend(args[2:])
                if args[:3] == ("diff","--cached","--name-only"):
                    return "\n".join(staged)
                return ""
            with patch.object(gate,"git",side_effect=git), patch.object(gate,"ensure_clean"), \
                    patch.object(gate,"cmd_complete") as completed, patch.object(gate,"cmd_verify") as verified, \
                    patch.object(admin.subprocess,"run") as sync, \
                    patch.object(admin.subprocess,"check_output", side_effect=lambda args,cwd: (cwd/args[-1][1:]).read_bytes()):
                admin.finish(repo,{"task_id":task,"governance_remote_parent":"fixture", "closeout_sha256":admin.sha(admin.__file__)})
                self.assertEqual(completed.call_args.args[0].outcome,"FAIL_CLOSED" if failed else "PASS")
                verified.assert_called_once()
                sync.assert_called_once()
            result = json.loads((root / "canonical_result.json").read_text())
            self.assertEqual(len(result["arm_summary"]),18)
            self.assertFalse(result["qualification"]["production_authorized"])
            self.assertEqual(result["qualification"]["decisions"]["FIXTURE"],"ECONOMIC_NOT_QUALIFIED")
            self.assertEqual(len(result["completed_arms"]),17 if failed else 18)
            self.assertNotIn(b"\r", (root / "canonical_result.json").read_bytes())
            self.assertNotIn(b"\r", (root / "eighteen_arm_summary.csv").read_bytes())

    def test_completed_replay_not_relabelled_as_profitable(self):
        self.exercise(False)

    def test_technical_failure_preserved_and_closed_fail_closed(self):
        self.exercise(True)


if __name__ == "__main__":
    unittest.main()
