from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from unittest import TestCase

from iris.engine.types import (
    ContentDelta,
    EngineErrorCode,
    ToolProgress,
    TurnCancelled,
    TurnFailed,
    TurnFinished,
)
from iris.engine._sidecar import parse_turn_event

_ROOT = Path(__file__).resolve().parents[1]
_SIDECAR_MAIN = _ROOT / "iris" / "engine" / "_sidecar_main.py"
_CREATE = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _child_env(**overrides: str) -> dict[str, str]:
    env = os.environ.copy()
    env.pop("IRIS_ENGINE_GUI_PYTHON", None)
    env.pop("IRIS_ENGINE_ALLOW_GUI", None)
    env.pop("IRIS_ENGINE_LOG", None)
    env["PYTHONUNBUFFERED"] = "1"
    env.update(overrides)
    return env


def _run_sidecar_main(env: dict[str, str], *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(_SIDECAR_MAIN), *extra],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(_ROOT),
        timeout=10,
        creationflags=_CREATE,
    )


class ParseTurnEventTests(TestCase):
    def test_unknown_name_is_protocol_and_does_not_raise(self) -> None:
        try:
            event = parse_turn_event({"t": "nope"})
        except Exception as exc:
            self.fail(f"parse_turn_event raised {exc!r}")
        self.assertIsInstance(event, TurnFailed)
        assert isinstance(event, TurnFailed)
        self.assertEqual(event.error.code, EngineErrorCode.PROTOCOL)

    def test_missing_name_or_non_dict_is_protocol(self) -> None:
        missing = parse_turn_event({})
        self.assertIsInstance(missing, TurnFailed)
        assert isinstance(missing, TurnFailed)
        self.assertEqual(missing.error.code, EngineErrorCode.PROTOCOL)
        broken = parse_turn_event("not-a-dict")  # type: ignore[arg-type]
        self.assertIsInstance(broken, TurnFailed)
        assert isinstance(broken, TurnFailed)
        self.assertEqual(broken.error.code, EngineErrorCode.PROTOCOL)

    def test_parse_delta_done_cancel_fail(self) -> None:
        self.assertEqual(parse_turn_event({"t": "delta", "text": "hi"}), ContentDelta("hi"))
        self.assertEqual(parse_turn_event({"t": "done", "text": "bye"}), TurnFinished("bye"))
        self.assertEqual(parse_turn_event({"t": "cancel"}), TurnCancelled())
        failed = parse_turn_event({"t": "fail", "code": "spawn_failed", "detail": "boom"})
        self.assertIsInstance(failed, TurnFailed)
        assert isinstance(failed, TurnFailed)
        self.assertEqual(failed.error.code, EngineErrorCode.SPAWN_FAILED)
        self.assertEqual(failed.error.detail, "boom")

    def test_tool_aliases_and_unknown_fail_code(self) -> None:
        self.assertEqual(parse_turn_event({"t": "tool", "label": "read"}), ToolProgress("read"))
        self.assertEqual(
            parse_turn_event({"t": "tool_progress", "label": "read"}),
            ToolProgress("read"),
        )
        failed = parse_turn_event({"t": "fail", "code": "nope", "detail": "x"})
        self.assertIsInstance(failed, TurnFailed)
        assert isinstance(failed, TurnFailed)
        self.assertEqual(failed.error.code, EngineErrorCode.UNKNOWN)


class SidecarMainTests(TestCase):
    def test_gui_python_exits_2(self) -> None:
        proc = _run_sidecar_main(_child_env(IRIS_ENGINE_GUI_PYTHON=sys.executable))
        self.assertEqual(proc.returncode, 2)
        self.assertNotIn('"t": "hello"', proc.stdout)
        self.assertNotIn('"t":"hello"', proc.stdout)

    def test_hello_when_not_gui_python(self) -> None:
        proc = _run_sidecar_main(_child_env())
        self.assertEqual(proc.returncode, 0, proc.stderr)
        lines = [line for line in proc.stdout.splitlines() if line.strip()]
        self.assertTrue(lines, "stdout must carry the hello line")
        first = lines[0]
        self.assertEqual(json.loads(first), {"t": "hello", "ok": True})

    def test_hello_when_gui_python_is_a_different_path(self) -> None:
        proc = _run_sidecar_main(_child_env(IRIS_ENGINE_GUI_PYTHON=str(_ROOT / "not-python")))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        first = proc.stdout.splitlines()[0]
        self.assertEqual(json.loads(first), {"t": "hello", "ok": True})


class SidecarExportTests(TestCase):
    def test_private_names_stay_off_all(self) -> None:
        import iris.engine as engine

        self.assertNotIn("IRIS_ENGINE_TOOLS", engine.__all__)
        self.assertNotIn("_sidecar", engine.__all__)
        self.assertNotIn("parse_turn_event", engine.__all__)
        self.assertFalse(hasattr(engine, "parse_turn_event"))
