import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from iris.system import _check_fpr13_runner as fpr13


class EvidenceTests(unittest.TestCase):
    def test_scope_of_existing_checks(self):
        scenarios = {row["id"]: row for row in fpr13.SCENARIOS}
        self.assertEqual(scenarios["l01_general_chat"]["layer"], "L3")
        self.assertEqual(scenarios["doctor_startup"]["layer"], "diagnostic")
        self.assertEqual(scenarios["control_http_contract"]["layer"], "L2")
        self.assertEqual(scenarios["l04_shell_model"]["layer"], "L3")
        self.assertEqual(scenarios["ide_product_control"]["command"][-1], "iris.ui._check_local_vibe_smoke")
        self.assertEqual(scenarios["ide_product_control"]["layer"], "L4")
        self.assertEqual(scenarios["wiki_browser_gui"]["layer"], "L5")
        self.assertEqual(scenarios["wiki_browser_gui"]["command"][-2:], ["iris.ui._check_fpr_product_gui", "browser"])
        self.assertEqual(scenarios["process_approval_gui"]["layer"], "L5")
        self.assertEqual(scenarios["process_approval_gui"]["command"][-2:], ["iris.ui._check_fpr_product_gui", "process"])
        self.assertEqual(scenarios["installer_lifecycle"]["layer"], "L6")
        self.assertEqual(scenarios["installer_lifecycle"]["kind"], "lifecycle")
        self.assertEqual(scenarios["installer_lifecycle"]["command"][-1], "iris.system._check_owned_lifecycle")

    def test_contracts_only_retains_unverified_product_and_live_rows(self):
        executed = []

        def run_contract(_py, scenario, _log_dir, **_kwargs):
            executed.append(scenario["kind"])
            return dict(scenario, status="PASS", exit_code=0)

        with (
            tempfile.TemporaryDirectory() as target,
            patch.dict(os.environ, {fpr13.LIVE_ENV: "1"}),
            patch.object(fpr13, "_run_one", side_effect=run_contract),
        ):
            self.assertEqual(fpr13.main(["--contracts-only", "--out-dir", target]), 0)
            summary = json.loads((Path(target) / "results.json").read_text(encoding="utf-8"))["summary"]
        self.assertEqual(set(executed), {"contract"})
        for layer in ("L3", "L4", "L5", "L6"):
            self.assertEqual(summary["by_layer"][layer]["PASS"], 0)
            self.assertGreater(summary["by_layer"][layer]["UNVERIFIED"], 0)

    def test_include_lifecycle_runs_without_contracts_only(self):
        executed = []

        def run_one(_py, scenario, _log_dir, **_kwargs):
            executed.append(scenario["id"])
            return dict(scenario, status="PASS", exit_code=0)

        with (
            tempfile.TemporaryDirectory() as target,
            patch.object(fpr13, "_run_one", side_effect=run_one),
        ):
            self.assertEqual(
                fpr13.main(["--contracts-only", "--include-lifecycle", "--out-dir", target]),
                0,
            )
            # contracts-only still wins: lifecycle stays UNVERIFIED
            rows = {r["id"]: r for r in json.loads((Path(target) / "results.json").read_text(encoding="utf-8"))["scenarios"]}
            self.assertEqual(rows["installer_lifecycle"]["status"], "UNVERIFIED")
            self.assertNotIn("installer_lifecycle", executed)

        executed.clear()
        with (
            tempfile.TemporaryDirectory() as target,
            patch.object(fpr13, "_run_one", side_effect=run_one),
        ):
            self.assertEqual(fpr13.main(["--include-lifecycle", "--out-dir", target]), 0)
            self.assertIn("installer_lifecycle", executed)
