from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from iris.engine import (
    CancelToken,
    ChatTranscript,
    Engine,
    EngineErrorCode,
    EngineHome,
    EngineReady,
    InternalSidecar,
    StatelessTurn,
    TurnFailed,
)
from iris.engine._sidecar import encode_host_command, parse_turn_event
from iris.engine.runtime import _sidecar_env
from iris.infrastructure.hermes_client import HermesInferenceTarget
from iris.system.win_subprocess import no_window_kwargs

_ROOT = Path(__file__).resolve().parents[1]
_SIDECAR_MAIN = _ROOT / "iris" / "engine" / "_sidecar_main.py"


def _turn() -> StatelessTurn:
    return StatelessTurn(
        transcript=ChatTranscript.parse([{"role": "user", "content": "hi"}]),
        model=HermesInferenceTarget(model="llama3.2", provider="custom"),
        cancel=CancelToken(),
    )


def _child_env(**overrides: str) -> dict[str, str]:
    env = os.environ.copy()
    env.pop("IRIS_ENGINE_GUI_PYTHON", None)
    env.pop("IRIS_ENGINE_ALLOW_GUI", None)
    env.pop("IRIS_ENGINE_LOG", None)
    env["PYTHONUNBUFFERED"] = "1"
    env["IRIS_ENGINE_GUI_PYTHON"] = str(_ROOT / "not-the-gui-python")
    env.update(overrides)
    return env


def _spawn_real_sidecar() -> subprocess.Popen[str]:
    return subprocess.Popen(
        [sys.executable, str(_SIDECAR_MAIN)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=_child_env(),
        cwd=str(_ROOT),
        **no_window_kwargs(),
    )


def _read_hello(proc: subprocess.Popen[str]) -> dict:
    assert proc.stdout is not None
    line = proc.stdout.readline()
    raw = json.loads(line)
    if raw != {"t": "hello", "ok": True}:
        raise AssertionError(f"hello was not valid: {line!r}")
    return raw


def _write_cmd(home: Path, body: str) -> Path:
    if sys.platform == "win32":
        scripts = home / "hermes-agent" / "venv" / "Scripts"
        scripts.mkdir(parents=True, exist_ok=True)
        path = scripts / "python.cmd"
        path.write_text(body.replace("\n", "\r\n"), encoding="utf-8")
        return path
    bin_dir = home / "hermes-agent" / "venv" / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    path = bin_dir / "python"
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)
    return path


def _iris_python_wrapper(home: Path) -> Path:
    if sys.platform == "win32":
        return _write_cmd(home, f'@echo off\n"{sys.executable}" %*\n')
    return _write_cmd(
        home,
        "#!/bin/sh\n"
        f"exec '{sys.executable}' \"$@\"\n",
    )


def _safe_sidecar_env(home: EngineHome, python: Path) -> dict[str, str]:
    env = _sidecar_env(home, python)
    env["IRIS_ENGINE_GUI_PYTHON"] = str(Path(home) / "not-the-gui-python")
    return env


class SidecarTurnPipeTests(TestCase):
    def tearDown(self) -> None:
        proc = getattr(self, "_proc", None)
        if proc is None:
            return
        if proc.poll() is None:
            if proc.stdin is not None:
                try:
                    proc.stdin.close()
                except OSError:
                    pass
            proc.kill()
            proc.wait(timeout=5)
        for stream in (proc.stdin, proc.stdout, proc.stderr):
            if stream is None:
                continue
            try:
                stream.close()
            except OSError:
                continue

    def test_turn_fails_unknown_then_stop_exits_0(self) -> None:
        self._proc = _spawn_real_sidecar()
        _read_hello(self._proc)
        assert self._proc.stdin is not None
        assert self._proc.stdout is not None
        self._proc.stdin.write(encode_host_command("turn"))
        self._proc.stdin.flush()
        event = parse_turn_event(json.loads(self._proc.stdout.readline()))
        self.assertIsInstance(event, TurnFailed)
        assert isinstance(event, TurnFailed)
        self.assertEqual(event.error.code, EngineErrorCode.UNKNOWN)
        self.assertEqual(event.error.detail, "agent loop is not wired")
        self.assertIsNone(self._proc.poll())
        self._proc.stdin.write(encode_host_command("stop"))
        self._proc.stdin.flush()
        self.assertEqual(self._proc.wait(timeout=5), 0)

    def test_unknown_command_is_protocol_and_child_stays_up(self) -> None:
        self._proc = _spawn_real_sidecar()
        _read_hello(self._proc)
        assert self._proc.stdin is not None
        assert self._proc.stdout is not None
        self._proc.stdin.write(encode_host_command("nope"))
        self._proc.stdin.flush()
        event = parse_turn_event(json.loads(self._proc.stdout.readline()))
        self.assertIsInstance(event, TurnFailed)
        assert isinstance(event, TurnFailed)
        self.assertEqual(event.error.code, EngineErrorCode.PROTOCOL)
        self.assertIsNone(self._proc.poll())
        self._proc.stdin.close()
        self.assertEqual(self._proc.wait(timeout=5), 0)

    def test_stdin_close_exits_0(self) -> None:
        self._proc = _spawn_real_sidecar()
        _read_hello(self._proc)
        assert self._proc.stdin is not None
        self._proc.stdin.close()
        self.assertEqual(self._proc.wait(timeout=5), 0)


class EngineTurnPipeTests(TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.home = EngineHome(Path(self._tmp.name))
        _iris_python_wrapper(Path(self.home))
        self.engine = Engine(InternalSidecar(home=self.home))
        self._probe = patch("iris.engine.runtime.probe_engine_python", return_value=None)
        self._env = patch(
            "iris.engine.runtime._sidecar_env",
            side_effect=_safe_sidecar_env,
        )
        self._probe.start()
        self._env.start()
        self.addCleanup(self._probe.stop)
        self.addCleanup(self._env.stop)
        self.addCleanup(self.engine.shutdown)

    def tearDown(self) -> None:
        self.engine.shutdown()
        self._tmp.cleanup()

    def test_two_turns_keep_the_same_child(self) -> None:
        ready = self.engine.ensure_ready()
        self.assertIsInstance(ready, EngineReady)
        child = self.engine._child
        self.assertIsNotNone(child)
        assert child is not None
        first_pid = child.pid
        first = list(self.engine.run_turn(_turn()))
        self.assertEqual(len(first), 1)
        self.assertIsInstance(first[0], TurnFailed)
        assert isinstance(first[0], TurnFailed)
        self.assertEqual(first[0].error.code, EngineErrorCode.UNKNOWN)
        self.assertEqual(first[0].error.detail, "agent loop is not wired")
        self.assertIs(self.engine._child, child)
        self.assertIsNone(child.poll())
        second = list(self.engine.run_turn(_turn()))
        self.assertEqual(len(second), 1)
        self.assertIsInstance(second[0], TurnFailed)
        assert isinstance(second[0], TurnFailed)
        self.assertEqual(second[0].error.code, EngineErrorCode.UNKNOWN)
        self.assertEqual(second[0].error.detail, "agent loop is not wired")
        again = self.engine.ensure_ready()
        self.assertIsInstance(again, EngineReady)
        self.assertIs(self.engine._child, child)
        self.assertEqual(self.engine._child.pid, first_pid)
        self.assertIsNone(child.poll())
