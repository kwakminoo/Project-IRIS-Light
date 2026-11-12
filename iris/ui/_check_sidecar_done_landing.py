"""Sidecar Turn ended → host done → worker finished_ok → DB assistant.

Hermes can wedge after logging Turn ended before run_conversation returns.
The host pipe must still see a terminal done (or fail) so Iris lands the turn.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from iris.engine import TurnFinished
from iris.engine._home import engine_python
from iris.engine._sidecar import encode_host_command, parse_turn_event
from iris.engine.runtime import _read_terminal_file_impl
from iris.engine.types import EngineHome
from iris.infrastructure.agent_runtime import iris_agent_home
from iris.storage.conversations import history_dicts
from iris.system.win_subprocess import no_window_kwargs

_ROOT = Path(__file__).resolve().parents[2]
_SIDECAR_MAIN = _ROOT / "iris" / "engine" / "_sidecar_main.py"
_HANG_MODULE = "iris_engine_hang_after_turn_ended_agent"
_TESTS_DIR = str(_ROOT / "tests")


def _child_env() -> dict[str, str]:
    env = os.environ.copy()
    env.pop("IRIS_ENGINE_GUI_PYTHON", None)
    env.pop("IRIS_ENGINE_ALLOW_GUI", None)
    env.pop("IRIS_ENGINE_LOG", None)
    env["PYTHONUNBUFFERED"] = "1"
    env["IRIS_ENGINE_GUI_PYTHON"] = str(_ROOT / "not-the-gui-python")
    env["IRIS_ENGINE_AGENT_MODULE"] = _HANG_MODULE
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = _TESTS_DIR if not existing else _TESTS_DIR + os.pathsep + existing
    return env


def _sidecar_python() -> str:
    # Match product spawn: engine venv has Hermes ``tools``; Iris .venv does not.
    return str(engine_python(EngineHome(iris_agent_home())))


def _readline(stream, timeout: float) -> str:
    box: list[str] = []

    def _read() -> None:
        try:
            box.append(stream.readline())
        except Exception:
            box.append("")

    worker = threading.Thread(target=_read, daemon=True)
    worker.start()
    worker.join(timeout)
    if worker.is_alive() or not box:
        return ""
    return box[0]


def _bind_check_udp() -> tuple[socket.socket, int]:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 0))
    sock.settimeout(0.2)
    return sock, int(sock.getsockname()[1])


def _parse_terminal_line(line: str):
    raw = json.loads(line.strip().splitlines()[0])
    return parse_turn_event(raw)


def _check_hang_after_turn_ended_emits_done() -> None:
    """Turn ended then hang: host must still receive done (UDP or terminal file)."""
    udp_sock, udp_port = _bind_check_udp()
    env = _child_env()
    env["IRIS_TERMINAL_UDP_PORT"] = str(udp_port)
    proc = subprocess.Popen(
        [_sidecar_python(), str(_SIDECAR_MAIN)],
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
    try:
        assert proc.stdout is not None and proc.stdin is not None
        hello = _readline(proc.stdout, 5.0)
        assert hello, "sidecar hello timed out"
        hello_obj = json.loads(hello)
        assert hello_obj.get("t") == "hello" and hello_obj.get("ok") is True, hello
        try:
            hello_pid = int(hello_obj.get("pid") or 0) or None
        except (TypeError, ValueError):
            hello_pid = None
        proc.stdin.write(
            encode_host_command(
                "turn",
                messages=[{"role": "user", "content": "ping"}],
                model="fake",
                provider="custom",
                terminal_udp_port=udp_port,
            )
        )
        proc.stdin.flush()
        texts: list[str] = []
        done_text = None
        deadline = time.monotonic() + 8.0
        while time.monotonic() < deadline and done_text is None:
            try:
                data, _addr = udp_sock.recvfrom(65535)
            except socket.timeout:
                data = b""
            except OSError:
                data = b""
            if data:
                line = data.decode("utf-8", errors="replace")
                event = _parse_terminal_line(line)
                if isinstance(event, TurnFinished):
                    done_text = event.text
                    break
            line = _readline(proc.stdout, 0.15)
            if line:
                event = parse_turn_event(json.loads(line))
                if isinstance(event, TurnFinished):
                    done_text = event.text
                    break
                text = getattr(event, "text", "") or ""
                if text:
                    texts.append(text)
            file_line = _read_terminal_file_impl(hello_pid)
            if file_line:
                event = _parse_terminal_line(file_line)
                if isinstance(event, TurnFinished):
                    done_text = event.text
                    break
        assert done_text is not None, f"no done after Turn ended hang; deltas={texts!r}"
        assert "hang-answer" in (done_text or "".join(texts)), (done_text, texts)
    finally:
        try:
            udp_sock.close()
        except OSError:
            pass
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=5)
        for stream in (proc.stdin, proc.stdout, proc.stderr):
            if stream is None:
                continue
            try:
                stream.close()
            except OSError:
                continue


def _check_worker_turn_finished_emits_finished_ok() -> None:
    from iris.engine import EngineHome, InternalSidecar
    from iris.infrastructure.iris_agent_client import IrisAgentInferenceTarget
    from iris.ui.workers.iris_agent_workers import IrisAgentChatWorker

    class _StubEngine:
        def __init__(self, events):
            self._events = list(events)
            self.source = InternalSidecar(
                home=EngineHome(Path.home() / ".iris-light" / "engine")
            )

        def run_turn(self, turn):
            yield from self._events

    engine = _StubEngine([TurnFinished("landed-from-done")])
    worker = IrisAgentChatWorker(
        "gemma4:26b-a4b-it-qat",
        [{"role": "user", "content": "hi"}],
        target=IrisAgentInferenceTarget(model="gemma4:26b-a4b-it-qat", provider="custom"),
    )
    ok: list[str] = []
    failed: list[str] = []
    worker.finished_ok.connect(ok.append)
    worker.failed.connect(failed.append)
    with (
        patch("iris.ui.workers.iris_agent_workers.shared_engine", return_value=engine),
        patch(
            "iris.ui.workers.iris_agent_workers._engine_source",
            return_value=engine.source,
        ),
        patch.object(IrisAgentChatWorker, "_wire_native_speak_tools", lambda self: None),
    ):
        worker.run()
    assert failed == [], failed
    assert ok == ["landed-from-done"], ok

    engine2 = _StubEngine([TurnFinished("")])
    worker2 = IrisAgentChatWorker(
        "gemma4:26b-a4b-it-qat",
        [{"role": "user", "content": "hi"}],
        target=IrisAgentInferenceTarget(model="gemma4:26b-a4b-it-qat", provider="custom"),
    )
    ok2: list[str] = []
    failed2: list[str] = []
    worker2.finished_ok.connect(ok2.append)
    worker2.failed.connect(failed2.append)
    with (
        patch("iris.ui.workers.iris_agent_workers.shared_engine", return_value=engine2),
        patch(
            "iris.ui.workers.iris_agent_workers._engine_source",
            return_value=engine2.source,
        ),
        patch.object(IrisAgentChatWorker, "_wire_native_speak_tools", lambda self: None),
    ):
        worker2.run()
    assert failed2 == [], failed2
    assert ok2 == [""], ok2


def _check_empty_finished_persists_placeholder(app: QApplication) -> None:
    from iris.ui.window.main_window import MainWindow

    win = MainWindow(test_mode=True)
    win.show()
    app.processEvents()
    cid = int(win._conversation_id)
    win._record_history("user", "empty-done-user")
    turn_id = "turn-empty-done"
    win._turn_gate.begin(turn_id)
    win._turn_gate.arm()
    win._turn_worker_meta[turn_id] = cid
    win._on_chat_finished_for_turn("", turn_id)
    app.processEvents()
    texts = [r["content"] for r in history_dicts(win._db, cid)]
    assert "empty-done-user" in texts, texts
    assert "(빈 응답)" in texts, texts
    win.close()
    app.processEvents()


def main() -> None:
    _check_hang_after_turn_ended_emits_done()
    _check_worker_turn_finished_emits_finished_ok()
    app = QApplication.instance() or QApplication(sys.argv)
    _check_empty_finished_persists_placeholder(app)
    print("sidecar done landing ok")


if __name__ == "__main__":
    main()
