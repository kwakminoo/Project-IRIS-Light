"""Windows logon warm task uses Iris Agent and retires the old task."""

import unittest
from unittest.mock import patch

from iris.system import iris_agent_login_warm as warm


class IrisAgentLoginWarmTests(unittest.TestCase):
    def test_cli_and_task_are_iris_owned(self):
        self.assertEqual(warm.cli_script().name, "iris_agent_login_warm_cli.py")
        self.assertTrue(warm.cli_script().is_file())
        self.assertEqual(warm.TASK_NAME, r"\IrisLight\IrisAgentWarm")

    def test_sync_retires_legacy_task_before_registering(self):
        calls = []

        def fake_run(args):
            calls.append(args)
            if "/Query" in args:
                return 1, "cannot find"
            return 0, ""

        with (
            patch.object(warm, "is_supported", return_value=True),
            patch.object(warm, "_run", side_effect=fake_run),
            patch.object(warm, "python_runner", return_value=warm.cli_script()),
        ):
            result = warm.sync(True)
        self.assertTrue(result.registered)
        self.assertIn(["schtasks", "/Delete", "/TN", r"\IrisLight\HermesGatewayWarm", "/F"], calls)
        self.assertTrue(any("/Create" in call and warm.TASK_NAME in call for call in calls))


if __name__ == "__main__":
    unittest.main()
