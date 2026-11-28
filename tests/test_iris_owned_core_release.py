"""Release contracts for the bundled, IRIS-owned engine."""

import json
import os
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest.mock import patch

from iris.engine._home import engine_python
from iris.infrastructure.agent_runtime import ENGINE_SELECTION_FILE, iris_agent_repo_dir, read_engine_selection
from iris.system._check_iris_agent_repo_dir import write_owned_slot_fixture
from iris.system import iris_agent_install as install


ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / "vendor" / "iris-agent-core"


class OwnedCoreReleaseTests(unittest.TestCase):
    def test_unverified_engine_is_never_executable(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            legacy = home / "hermes-agent"
            legacy.mkdir()
            self.assertEqual(iris_agent_repo_dir(home), home / "iris-agent")
            python = legacy / ("venv/Scripts/python.exe" if sys.platform == "win32" else "venv/bin/python")
            python.parent.mkdir(parents=True)
            python.touch()
            (home / ENGINE_SELECTION_FILE).write_text(json.dumps({"active": legacy.name}), encoding="utf-8")
            self.assertIsNone(engine_python(home))
            canonical = home / "iris-agent"
            legacy.rename(canonical)
            (home / ENGINE_SELECTION_FILE).write_text("broken JSON", encoding="utf-8")
            self.assertIsNone(engine_python(home))

    def test_shipped_lock_identifies_owned_package(self):
        project = tomllib.loads((VENDOR / "pyproject.toml").read_text(encoding="utf-8"))["project"]
        lock_path = VENDOR / "uv.lock"
        lock = tomllib.loads(lock_path.read_text(encoding="utf-8"))
        root_package, = [pkg for pkg in lock["package"] if pkg["source"] == {"editable": "."}]
        self.assertEqual((root_package["name"], root_package["version"]), (project["name"], project["version"]))
        self.assertTrue({"iris-agent", "hermes-agent"}.isdisjoint(pkg["name"] for pkg in lock["package"]))
        self.assertEqual(project["scripts"]["iris-agent"], "iris_agent_cli.main:main")
        if (ROOT / ".git").exists():
            # Pass the mapping explicitly so Windows preserves empty Git config values.
            ignored = subprocess.run(
                ["git", "check-ignore", str(lock_path)], cwd=ROOT,
                env=os.environ.copy(), capture_output=True,
            )
            self.assertEqual(
                ignored.returncode, 1, (ignored.stdout + ignored.stderr).decode(errors="replace")
            )

    def test_windows_payload_includes_engine_and_provenance(self):
        build = (ROOT / "scripts" / "build_iris_setup.ps1").read_text(encoding="utf-8-sig")
        for entry in ("vendor/iris-agent-core", "vendor/iris-agent-runtime", "THIRD_PARTY_NOTICES.md"):
            self.assertIn(entry, build)

    def test_failed_locked_sync_never_activates_or_tries_pip(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            staging = home / "candidate"
            staging.mkdir()
            (staging / "uv.lock").write_text("lock", encoding="utf-8")
            live = home / "iris-agent"
            live.mkdir()
            (live / "marker").touch()
            with (
                patch.object(install, "_run_dep", return_value=subprocess.CompletedProcess([], 1, "", "lock mismatch")) as run,
                patch.object(install, "_run", side_effect=AssertionError("must use locked uv sync only")),
            ):
                result = install._finish_staged_install(
                    staging=staging, home=home, py=Path(sys.executable), uv="uv",
                    log=[], emit=lambda _: None, fail=lambda kind, message, body: install.InstallResult(False, body, kind),
                    run_streamed=None, should_abort=None,
                )
            self.assertFalse(result.ok)
            self.assertIn("lock mismatch", result.message)
            self.assertIn("--locked", run.call_args.args[0])
            self.assertTrue((live / "marker").is_file())

    def test_activation_preserves_absolute_paths_and_previous_engine(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            previous = home / "iris-agent"
            write_owned_slot_fixture(previous)
            (previous / "old-file").touch()
            candidate = home / "iris-agent.slot-0123456789abcdef"
            write_owned_slot_fixture(candidate)
            (candidate / "new-file").touch()
            ok, detail = install._activate_staged(home, candidate)
            self.assertTrue(ok, detail)
            self.assertEqual(iris_agent_repo_dir(home), candidate)
            self.assertTrue((candidate / "new-file").is_file())
            self.assertTrue((previous / "old-file").is_file())
            self.assertEqual(read_engine_selection(home), (candidate, previous))
            interrupted = home / "iris-agent.slot-1111111111111111"
            interrupted.mkdir()
            self.assertEqual(iris_agent_repo_dir(home), candidate)

            with patch.object(install.os, "replace", side_effect=PermissionError("busy")):
                ok, detail = install._activate_staged(home, interrupted)
            self.assertFalse(ok)
            self.assertIn("busy", detail)
            self.assertEqual(read_engine_selection(home), (candidate, previous))

    def test_install_lock_rejects_concurrent_writer_and_releases_on_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            with self.assertRaisesRegex(RuntimeError, "simulated shutdown"):
                with install.iris_agent_install_lock(home):
                    with self.assertRaises(install.InstallBusy):
                        with install.iris_agent_install_lock(home):
                            self.fail("a second writer entered the installation")
                    raise RuntimeError("simulated shutdown")
            with install.iris_agent_install_lock(home) as lock:
                self.assertTrue(lock.is_file())

    def test_source_corruption_refuses_install_before_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            vendor = home / "vendor"
            vendor.mkdir()
            (vendor / "SOURCE_MANIFEST.json").write_text("{}", encoding="utf-8")
            (vendor / "pyproject.toml").write_text("[project]", encoding="utf-8")
            (vendor / "run_agent.py").touch()
            (vendor / "iris_agent_cli").mkdir()
            with patch.object(install, "vendor_iris_agent_core_root", return_value=vendor):
                result = install._materialize_owned_core(home / "candidate")
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((home / "candidate").exists())

    def test_setup_button_only_uses_owned_installer(self):
        from iris.system.setup_protocol import SetupProtocol

        setup = object.__new__(SetupProtocol)
        setup._abort = False
        setup.agent_command = "iris-agent"
        setup._iris_agent_prefer_bypass = setup._iris_agent_official_failed = False
        setup._state = {}
        setup._hermes_done = lambda message: message
        setup._emit_stream = lambda *_a, **_kw: None
        with (
            patch("iris.system.setup_protocol.probe_iris_agent_runtime", return_value=(False, "missing")),
            patch("iris.system.setup_protocol.iris_agent_executable", return_value=None),
            patch("iris.infrastructure.agent_runtime.iris_agent_repo_dir", return_value=ROOT / "does-not-exist"),
            patch.object(install, "install_iris_agent_with_system_python", return_value=install.InstallResult(True, "owned ready")) as owned,
            patch.object(setup, "_run_streamed", side_effect=AssertionError("must not use an upstream setup script")),
        ):
            self.assertEqual(setup._install_iris_agent(), "owned ready")
        owned.assert_called_once()

    def test_existing_soul_is_preserved(self):
        from iris.system import iris_agent_soul_sync as soul

        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            template = home / "template.md"
            template.write_text("# IRIS Light Persona\nDefault identity\n", encoding="utf-8")
            identity = home / "SOUL.md"
            identity.write_text("My custom identity\n", encoding="utf-8")
            with patch.object(soul, "repo_soul_path", return_value=template):
                soul.ensure_soul(home)
                self.assertEqual(identity.read_text(encoding="utf-8"), "My custom identity\n")
