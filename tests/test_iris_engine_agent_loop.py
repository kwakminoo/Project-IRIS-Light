from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from iris.engine import ContentDelta, EngineErrorCode, TurnFailed, TurnFinished
from iris.engine._sidecar import encode_host_command, parse_turn_event
from iris.system.win_subprocess import no_window_kwargs

_ROOT = Path(__file__).resolve().parents[1]
_SIDECAR_MAIN = _ROOT / "iris" / "engine" / "_sidecar_main.py"
_FAKE_MODULE = "iris_engine_fake_agent"
_TESTS_DIR = str(_ROOT / "tests")


def _child_env(**overrides: str) -> dict[str, str]:
    env = os.environ.copy()
    env.pop("IRIS_ENGINE_GUI_PYTHON", None)
    env.pop("IRIS_ENGINE_ALLOW_GUI", None)
    env.pop("IRIS_ENGINE_LOG", None)
    env.pop("IRIS_ENGINE_AGENT_MODULE", None)
    env.pop("IRIS_ENGINE_AGENT_RECORD", None)
    env["PYTHONUNBUFFERED"] = "1"
    env["IRIS_ENGINE_GUI_PYTHON"] = str(_ROOT / "not-the-gui-python")
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = _TESTS_DIR if not existing else _TESTS_DIR + os.pathsep + existing
    env.update(overrides)
    return env


def _spawn(env: dict[str, str]) -> subprocess.Popen[str]:
    return subprocess.Popen(
        [sys.executable, str(_SIDECAR_MAIN)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        cwd=str(_ROOT),
        **no_window_kwargs(),
    )


def _read_hello(proc: subprocess.Popen[str]) -> None:
    assert proc.stdout is not None
    line = proc.stdout.readline()
    raw = json.loads(line)
    if raw != {"t": "hello", "ok": True}:
        raise AssertionError(f"hello was not valid: {line!r}")


def _read_event(proc: subprocess.Popen[str]):
    assert proc.stdout is not None
    return parse_turn_event(json.loads(proc.stdout.readline()))


def _system_user_turn() -> str:
    return encode_host_command(
        "turn",
        messages=[
            {"role": "system", "content": "IRIS control"},
            {"role": "user", "content": "write list.txt"},
        ],
        model="llama3.2",
        provider="custom",
        base_url="http://127.0.0.1:11434/v1",
    )


def _assistant_tail_turn() -> str:
    return encode_host_command(
        "turn",
        messages=[
            {"role": "system", "content": "IRIS control"},
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
        ],
        model="llama3.2",
        provider="custom",
    )


def _load_record(path: Path) -> dict:
    if not path.is_file():
        return {"ctors": [], "runs": []}
    return json.loads(path.read_text(encoding="utf-8"))


class SidecarAgentLoopTests(TestCase):
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

    def _start_fake(self, record: Path) -> subprocess.Popen[str]:
        self._proc = _spawn(
            _child_env(
                IRIS_ENGINE_AGENT_MODULE=_FAKE_MODULE,
                IRIS_ENGINE_AGENT_RECORD=str(record),
            )
        )
        _read_hello(self._proc)
        return self._proc

    def test_system_user_turn_streams_then_stays_alive_for_a_second_turn(self) -> None:
        with TemporaryDirectory() as tmp:
            record = Path(tmp) / "agent.json"
            proc = self._start_fake(record)
            assert proc.stdin is not None
            proc.stdin.write(_system_user_turn())
            proc.stdin.flush()
            first = _read_event(proc)
            second = _read_event(proc)
            done = _read_event(proc)
            self.assertEqual(first, ContentDelta("Hel"))
            self.assertEqual(second, ContentDelta("lo"))
            self.assertEqual(done, TurnFinished("Hello"))
            self.assertIsNone(proc.poll())
            proc.stdin.write(_system_user_turn())
            proc.stdin.flush()
            self.assertEqual(_read_event(proc), ContentDelta("Hel"))
            self.assertEqual(_read_event(proc), ContentDelta("lo"))
            self.assertEqual(_read_event(proc), TurnFinished("Hello"))
            self.assertIsNone(proc.poll())
            saved = _load_record(record)
            self.assertEqual(len(saved["runs"]), 2)
            self.assertEqual(saved["runs"][0]["user_message"], "write list.txt")
            self.assertEqual(
                saved["runs"][0]["conversation_history"],
                [{"role": "system", "content": "IRIS control"}],
            )

    def test_fake_ctor_disables_hermes_persist(self) -> None:
        with TemporaryDirectory() as tmp:
            record = Path(tmp) / "agent.json"
            proc = self._start_fake(record)
            assert proc.stdin is not None
            proc.stdin.write(_system_user_turn())
            proc.stdin.flush()
            _read_event(proc)
            _read_event(proc)
            _read_event(proc)
            saved = _load_record(record)
            self.assertTrue(saved["ctors"], "fake AIAgent was not constructed")
            ctor = saved["ctors"][0]
            self.assertIs(ctor.get("skip_memory"), True)
            self.assertIsNone(ctor.get("session_db"))
            self.assertIs(ctor.get("quiet_mode"), True)
            self.assertEqual(ctor.get("base_url"), "http://127.0.0.1:11434/v1")
            self.assertTrue(saved["runs"][0]["persist_disabled"])

    def test_last_message_not_user_fails_without_run_conversation(self) -> None:
        with TemporaryDirectory() as tmp:
            record = Path(tmp) / "agent.json"
            proc = self._start_fake(record)
            assert proc.stdin is not None
            proc.stdin.write(_assistant_tail_turn())
            proc.stdin.flush()
            event = _read_event(proc)
            self.assertIsInstance(event, TurnFailed)
            assert isinstance(event, TurnFailed)
            self.assertEqual(event.error.code, EngineErrorCode.NO_USER_UTTERANCE)
            self.assertIsNone(proc.poll())
            saved = _load_record(record)
            self.assertEqual(saved["ctors"], [])
            self.assertEqual(saved["runs"], [])

    def test_missing_agent_module_stays_unwired(self) -> None:
        self._proc = _spawn(
            _child_env(IRIS_ENGINE_AGENT_MODULE="iris_engine_missing_agent")
        )
        _read_hello(self._proc)
        assert self._proc.stdin is not None
        self._proc.stdin.write(_system_user_turn())
        self._proc.stdin.flush()
        event = _read_event(self._proc)
        self.assertIsInstance(event, TurnFailed)
        assert isinstance(event, TurnFailed)
        self.assertEqual(event.error.code, EngineErrorCode.UNKNOWN)
        self.assertEqual(event.error.detail, "agent loop is not wired")
        self.assertIsNone(self._proc.poll())
