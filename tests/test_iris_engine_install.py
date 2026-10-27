from __future__ import annotations

import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from iris.engine import Engine, EngineError, EngineErrorCode, EngineFailed, EngineHome, InternalSidecar
from iris.engine._home import (
    ENGINE_HERMES_SHA,
    _probe_imports,
    engine_python,
    install_into,
    probe_engine_python,
)


def _child_pids() -> set[int]:
    try:
        import psutil
    except ImportError:
        return set()
    return {child.pid for child in psutil.Process().children(recursive=True)}


def _write_fake_python(home: Path, *, ok: bool) -> Path:
    if sys.platform == "win32":
        scripts = home / "hermes-agent" / "venv" / "Scripts"
        scripts.mkdir(parents=True)
        path = scripts / "python.cmd"
        if ok:
            path.write_text("@echo off\r\necho ok\r\nexit /b 0\r\n", encoding="utf-8")
        else:
            path.write_text(
                "@echo off\r\necho No module named 'hermes_cli' 1>&2\r\nexit /b 1\r\n",
                encoding="utf-8",
            )
        return path
    bin_dir = home / "hermes-agent" / "venv" / "bin"
    bin_dir.mkdir(parents=True)
    path = bin_dir / "python"
    if ok:
        path.write_text("#!/bin/sh\necho ok\nexit 0\n", encoding="utf-8")
    else:
        path.write_text(
            "#!/bin/sh\necho \"No module named 'hermes_cli'\" >&2\nexit 1\n",
            encoding="utf-8",
        )
    path.chmod(0o755)
    return path


class EngineHomePinTests(TestCase):
    def test_engine_hermes_sha_is_the_how_pin(self) -> None:
        self.assertEqual(ENGINE_HERMES_SHA, "4787e4d56fc8d9265d4c7d3c0fe5accee86b4078")

    def test_home_helpers_stay_private(self) -> None:
        import iris.engine as engine

        self.assertNotIn("_home", engine.__all__)
        self.assertNotIn("ENGINE_HERMES_SHA", engine.__all__)
        self.assertNotIn("probe_engine_python", engine.__all__)
        self.assertFalse(hasattr(engine, "probe_engine_python"))


class ProbeEnginePythonTests(TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.home = EngineHome(Path(self._tmp.name))

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_empty_home_is_not_installed(self) -> None:
        error = probe_engine_python(self.home)
        self.assertIsInstance(error, EngineError)
        assert isinstance(error, EngineError)
        self.assertEqual(error.code, EngineErrorCode.NOT_INSTALLED)
        self.assertIsNone(engine_python(self.home))

    def test_iris_interpreter_is_wrong_python(self) -> None:
        error = _probe_imports(Path(sys.executable))
        self.assertIsInstance(error, EngineError)
        assert isinstance(error, EngineError)
        self.assertEqual(error.code, EngineErrorCode.WRONG_PYTHON)

    def test_missing_path_is_not_installed(self) -> None:
        error = _probe_imports(Path(self.home) / "missing-python")
        self.assertIsInstance(error, EngineError)
        assert isinstance(error, EngineError)
        self.assertEqual(error.code, EngineErrorCode.NOT_INSTALLED)

    def test_fake_venv_import_fail_is_wrong_python(self) -> None:
        _write_fake_python(Path(self.home), ok=False)
        before = _child_pids()
        error = probe_engine_python(self.home)
        self.assertEqual(_child_pids(), before)
        self.assertIsInstance(error, EngineError)
        assert isinstance(error, EngineError)
        self.assertEqual(error.code, EngineErrorCode.WRONG_PYTHON)

    def test_probe_does_not_raise(self) -> None:
        try:
            probe_engine_python(self.home)
            _probe_imports(Path(self.home) / "nope")
            _probe_imports(Path(sys.executable))
        except Exception as exc:
            self.fail(f"probe raised {exc!r}")


class EnsureReadyInstallTests(TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.home = EngineHome(Path(self._tmp.name))

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_empty_home_does_not_spawn(self) -> None:
        engine = Engine(InternalSidecar(home=self.home))
        before = _child_pids()
        result = engine.ensure_ready()
        self.assertEqual(_child_pids(), before)
        self.assertIsInstance(result, EngineFailed)
        assert isinstance(result, EngineFailed)
        self.assertEqual(result.error.code, EngineErrorCode.NOT_INSTALLED)
        self.assertIsNone(engine._child)

    def test_wrong_python_does_not_spawn(self) -> None:
        _write_fake_python(Path(self.home), ok=False)
        engine = Engine(InternalSidecar(home=self.home))
        before = _child_pids()
        result = engine.ensure_ready()
        self.assertEqual(_child_pids(), before)
        self.assertIsInstance(result, EngineFailed)
        assert isinstance(result, EngineFailed)
        self.assertEqual(result.error.code, EngineErrorCode.WRONG_PYTHON)
        self.assertIsNone(engine._child)

    def test_probe_ok_does_not_spawn(self) -> None:
        _write_fake_python(Path(self.home), ok=True)
        engine = Engine(InternalSidecar(home=self.home))
        before = _child_pids()
        result = engine.ensure_ready()
        self.assertEqual(_child_pids(), before)
        self.assertIsInstance(result, EngineFailed)
        assert isinstance(result, EngineFailed)
        self.assertEqual(result.error.code, EngineErrorCode.SPAWN_FAILED)
        self.assertEqual(result.error.detail, "sidecar spawn is not wired")
        self.assertIsNone(engine._child)

    def test_install_into_without_runner_does_not_clone(self) -> None:
        install_into(self.home)
        self.assertEqual(list(Path(self.home).iterdir()), [])
