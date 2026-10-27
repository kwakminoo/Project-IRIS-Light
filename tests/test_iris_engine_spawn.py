from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from iris.engine import (
    Engine,
    EngineErrorCode,
    EngineFailed,
    EngineHome,
    EngineReady,
    InternalSidecar,
)


def _child_pids() -> set[int]:
    try:
        import psutil
    except ImportError:
        return set()
    return {child.pid for child in psutil.Process().children(recursive=True)}


def _pid_alive(pid: int) -> bool:
    try:
        import psutil
    except ImportError:
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return True
    return psutil.pid_exists(pid)


def _wait_pid_gone(pid: int, timeout: float = 5.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not _pid_alive(pid):
            return True
        time.sleep(0.05)
    return not _pid_alive(pid)


def _write_cmd(home: Path, name: str, body: str) -> Path:
    if sys.platform == "win32":
        scripts = home / "hermes-agent" / "venv" / "Scripts"
        scripts.mkdir(parents=True, exist_ok=True)
        path = scripts / name
        path.write_text(body.replace("\n", "\r\n"), encoding="utf-8")
        return path
    bin_dir = home / "hermes-agent" / "venv" / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    path = bin_dir / "python"
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)
    return path


def _hello_waiter_python(home: Path) -> Path:
    waiter = (
        "import json,sys;"
        "print(json.dumps({'t':'hello','ok':True}), flush=True);"
        "sys.stdin.read()"
    )
    if sys.platform == "win32":
        return _write_cmd(
            home,
            "python.cmd",
            f'@echo off\n"{sys.executable}" -c "{waiter}"\n',
        )
    return _write_cmd(
        home,
        "python",
        "#!/bin/sh\n"
        f"exec '{sys.executable}' -c '{waiter}'\n",
    )


def _exit_2_python(home: Path) -> Path:
    if sys.platform == "win32":
        return _write_cmd(home, "python.cmd", "@echo off\nexit /b 2\n")
    return _write_cmd(home, "python", "#!/bin/sh\nexit 2\n")


def _no_hello_python(home: Path) -> Path:
    if sys.platform == "win32":
        return _write_cmd(home, "python.cmd", "@echo off\necho not-hello\nexit /b 0\n")
    return _write_cmd(home, "python", "#!/bin/sh\necho not-hello\nexit 0\n")


class EngineSpawnTests(TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.home = EngineHome(Path(self._tmp.name))
        self.engine = Engine(InternalSidecar(home=self.home))
        self._probe = patch("iris.engine.runtime.probe_engine_python", return_value=None)
        self._probe.start()
        self.addCleanup(self._probe.stop)
        self.addCleanup(self.engine.shutdown)

    def tearDown(self) -> None:
        self.engine.shutdown()
        self._tmp.cleanup()

    def test_hello_child_is_ready_and_second_ensure_does_not_respawn(self) -> None:
        _hello_waiter_python(Path(self.home))
        before = _child_pids()
        first = self.engine.ensure_ready()
        self.assertIsInstance(first, EngineReady)
        child = self.engine._child
        self.assertIsNotNone(child)
        assert child is not None
        self.assertIsNone(child.poll())
        after_first = _child_pids()
        self.assertTrue(after_first - before)
        second = self.engine.ensure_ready()
        self.assertIsInstance(second, EngineReady)
        self.assertIs(self.engine._child, child)
        self.assertEqual(self.engine._child.pid, child.pid)
        self.assertEqual(_child_pids(), after_first)

    def test_shutdown_kills_the_child(self) -> None:
        _hello_waiter_python(Path(self.home))
        before = _child_pids()
        result = self.engine.ensure_ready()
        self.assertIsInstance(result, EngineReady)
        child = self.engine._child
        self.assertIsNotNone(child)
        assert child is not None
        pid = child.pid
        self.engine.shutdown()
        self.assertIsNone(self.engine._child)
        self.assertTrue(_wait_pid_gone(pid), f"pid {pid} still alive")
        self.assertEqual(_child_pids(), before)

    def test_shutdown_twice_does_not_raise(self) -> None:
        _hello_waiter_python(Path(self.home))
        result = self.engine.ensure_ready()
        self.assertIsInstance(result, EngineReady)
        self.engine.shutdown()
        self.engine.shutdown()
        self.assertIsNone(self.engine._child)

    def test_exit_2_is_failed_and_leaves_no_child(self) -> None:
        _exit_2_python(Path(self.home))
        before = _child_pids()
        result = self.engine.ensure_ready()
        self.assertIsInstance(result, EngineFailed)
        assert isinstance(result, EngineFailed)
        self.assertEqual(result.error.code, EngineErrorCode.WRONG_PYTHON)
        self.assertIsNone(self.engine._child)
        self.assertEqual(_child_pids(), before)

    def test_no_hello_is_failed_and_leaves_no_child(self) -> None:
        _no_hello_python(Path(self.home))
        before = _child_pids()
        result = self.engine.ensure_ready()
        self.assertIsInstance(result, EngineFailed)
        assert isinstance(result, EngineFailed)
        self.assertIn(
            result.error.code,
            {EngineErrorCode.SPAWN_FAILED, EngineErrorCode.WRONG_PYTHON},
        )
        self.assertIsNone(self.engine._child)
        self.assertEqual(_child_pids(), before)
