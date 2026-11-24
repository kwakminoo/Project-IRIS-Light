"""A failed Iris Agent replacement leaves the previous checkout usable."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from iris.system import iris_agent_install as install


class IrisAgentInstallRollbackTests(unittest.TestCase):
    def test_failed_swap_restores_legacy_checkout_to_legacy_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            legacy = home / "hermes-agent"
            legacy.mkdir()
            (legacy / "sentinel").write_text("old")
            ok, _detail = install._swap_in_staging(home, home / "missing-staging", "failed")
            self.assertFalse(ok)
            self.assertEqual((legacy / "sentinel").read_text(), "old")
            self.assertFalse((home / "iris-agent").exists())

    def test_failed_probe_preserves_legacy_checkout(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            legacy = home / "hermes-agent"
            legacy.mkdir()
            (legacy / "sentinel").write_text("old")
            staging = home / "iris-agent.staging-probe"
            staging.mkdir()
            with patch.object(install, "_probe_venv", return_value=(False, "probe failed")):
                ok, _detail = install._activate_staged(
                    home, staging, "probe", "iris-agent", probe_gateway=False
                )
            self.assertFalse(ok)
            self.assertEqual((legacy / "sentinel").read_text(), "old")
            self.assertFalse((home / "iris-agent").exists())

    def test_failed_probe_does_not_remove_other_legacy_checkout(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            (home / "iris-agent").mkdir()
            legacy = home / "hermes-agent"
            legacy.mkdir()
            (legacy / "sentinel").write_text("old")
            staging = home / "iris-agent.staging-probe"
            staging.mkdir()
            with patch.object(install, "_probe_venv", return_value=(False, "probe failed")):
                ok, _detail = install._activate_staged(
                    home, staging, "probe", "iris-agent", probe_gateway=False
                )
            self.assertFalse(ok)
            self.assertTrue((home / "iris-agent").is_dir())
            self.assertEqual((legacy / "sentinel").read_text(), "old")

    def test_successful_probe_retires_other_legacy_checkout(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            (home / "iris-agent").mkdir()
            (home / "hermes-agent").mkdir()
            staging = home / "iris-agent.staging-probe"
            staging.mkdir()
            with patch.object(install, "_probe_venv", return_value=(True, "ready")):
                ok, _detail = install._activate_staged(
                    home, staging, "probe", "iris-agent", probe_gateway=False
                )
            self.assertTrue(ok)
            self.assertTrue((home / "iris-agent").is_dir())
            self.assertFalse((home / "hermes-agent").exists())


if __name__ == "__main__":
    unittest.main()
