"""Staging failures and rollback preserve a selectable engine."""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from iris.infrastructure.agent_runtime import iris_agent_repo_dir, read_engine_selection
from iris.system import iris_agent_install as install
from iris.system._check_iris_agent_repo_dir import write_owned_slot_fixture


class IrisAgentInstallRollbackTests(unittest.TestCase):
    def test_ready_or_model_failure_keeps_previous_engine(self):
        for ready, model_error in (((False, "import failed"), None), ((False, "ready failed"), None), ((True, "ok"), RuntimeError("model incompatible"))):
            with self.subTest(ready=ready, model_error=model_error), tempfile.TemporaryDirectory() as tmp:
                home = Path(tmp)
                previous = home / "hermes-agent"
                previous.mkdir()
                (previous / "sentinel").write_text("working", encoding="utf-8")
                staging = home / "iris-agent.slot-0123456789abcdef"
                staging.mkdir()
                (staging / "uv.lock").touch()
                def validate_model(_path):
                    if model_error:
                        raise model_error
                with (
                    patch.object(install, "_run_dep", return_value=subprocess.CompletedProcess([], 0, "", "")),
                    patch.object(install, "_probe_owned_slot", return_value=ready),
                ):
                    result = install._finish_staged_install(
                        staging=staging, home=home, py=Path(sys.executable), uv="uv", log=[],
                        emit=lambda _: None, fail=lambda kind, message, body: install.InstallResult(False, body, kind),
                        run_streamed=None, should_abort=None, model_check=validate_model,
                    )
                self.assertFalse(result.ok)
                self.assertIn(str(model_error) if model_error else ready[1], result.message)
                self.assertFalse(staging.exists())
                self.assertEqual(read_engine_selection(home), (None, None))
                self.assertEqual(iris_agent_repo_dir(home), home / "iris-agent")
                self.assertEqual((previous / "sentinel").read_text(encoding="utf-8"), "working")

    def test_rollback_refuses_reference_as_product_engine(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            legacy = home / "hermes-agent"
            current = home / "iris-agent.slot-0123456789abcdef"
            legacy.mkdir()
            write_owned_slot_fixture(current)
            install._write_engine_selection(home, current, legacy)
            with (
                patch("iris.engine._home.checkout_python", return_value=Path(sys.executable)),
                patch("iris.engine._home._probe_imports", return_value=None),
            ):
                with self.assertRaisesRegex(RuntimeError, "Owned recovery"):
                    install.rollback_iris_agent(home)
            self.assertEqual(read_engine_selection(home), (current, legacy))
            self.assertTrue(current.is_dir())

    def test_rollback_probes_owned_recovery_before_writing_selection(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            current = home / "iris-agent.slot-0123456789abcdef"
            previous = home / "iris-agent.slot-1111111111111111"
            write_owned_slot_fixture(current)
            write_owned_slot_fixture(previous)
            install._write_engine_selection(home, current, previous)
            with patch.object(install, "_probe_owned_slot", return_value=(False, "bad runtime")):
                with self.assertRaisesRegex(RuntimeError, "bad runtime"):
                    install.rollback_iris_agent(home)
            self.assertEqual(read_engine_selection(home), (current, previous))
            with patch.object(install, "_probe_owned_slot", return_value=(True, "ready")):
                self.assertEqual(install.rollback_iris_agent(home), previous.name)
            self.assertEqual(read_engine_selection(home), (previous, current))

    def test_copy_failure_has_no_effect_on_active_engine(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            current = home / "iris-agent"
            current.mkdir()
            staging = home / "iris-agent.slot-0123456789abcdef"
            with patch.object(install.shutil, "copytree", side_effect=OSError("source copy failed")):
                result = install._materialize_owned_core(staging)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("source copy failed", result.stderr)
            self.assertEqual(iris_agent_repo_dir(home), current)


if __name__ == "__main__":
    unittest.main()
