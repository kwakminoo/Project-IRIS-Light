"""채팅 착지 계약: 스트림 5xx 복구 뒤 TurnFinished 텍스트가 DB에 남고 user는 유지."""

from __future__ import annotations

import os
import sys
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from iris.engine import EngineError, EngineErrorCode, TurnFailed, TurnFinished
from iris.storage.conversations import history_dicts


def _check_fail_keeps_user(app: QApplication) -> None:
    from iris.ui.window.main_window import MainWindow

    win = MainWindow(test_mode=True)
    win.show()
    app.processEvents()
    cid = int(win._conversation_id)
    win._record_history("user", "keep-me-on-fail")
    before = [r["content"] for r in history_dicts(win._db, cid)]
    assert "keep-me-on-fail" in before

    turn_id = "turn-fail-keep"
    win._turn_gate.begin(turn_id)
    win._turn_gate.arm()
    win._turn_worker_meta[turn_id] = cid
    assert win._runs.owning(turn_id) is not None
    win._on_chat_failed_for_turn(
        "HTTP 500: stream failed then recovered upstream", turn_id
    )
    app.processEvents()

    after = [r["content"] for r in history_dicts(win._db, cid)]
    assert "keep-me-on-fail" in after, after
    win.close()
    app.processEvents()


def _check_finished_records_assistant(app: QApplication) -> None:
    from iris.ui.window.main_window import MainWindow

    win = MainWindow(test_mode=True)
    win.show()
    app.processEvents()
    cid = int(win._conversation_id)
    win._record_history("user", "hello-land")
    turn_id = "turn-land-ok"
    win._turn_gate.begin(turn_id)
    win._turn_gate.arm()
    win._turn_worker_meta[turn_id] = cid
    win._on_chat_finished_for_turn("복구된 답변입니다", turn_id)
    app.processEvents()
    texts = [r["content"] for r in history_dicts(win._db, cid)]
    assert "복구된 답변입니다" in texts, texts
    win.close()
    app.processEvents()


def _check_orphan_without_meta_still_lands(app: QApplication) -> None:
    from iris.ui.window.main_window import MainWindow

    win = MainWindow(test_mode=True)
    win.show()
    app.processEvents()
    cid = int(win._conversation_id)
    win._record_history("user", "orphan-meta-miss")
    orphan_tid = "turn-orphan-nometa"
    win._turn_gate.begin("other-turn")
    win._turn_gate.arm()
    assert win._runs.owning(orphan_tid) is None
    assert orphan_tid not in win._turn_worker_meta
    reply = "orphan without meta must land on active cid"
    win._on_chat_finished_for_turn(reply, orphan_tid)
    app.processEvents()
    texts = [r["content"] for r in history_dicts(win._db, cid)]
    assert reply in texts, texts
    win.close()
    app.processEvents()


def _check_fail_then_finish_lands(app: QApplication) -> None:
    """스트림 5xx fail 직후 복구 TurnFinished: user 유지 + assistant 착지."""
    from iris.ui.window.main_window import MainWindow

    win = MainWindow(test_mode=True)
    win.show()
    app.processEvents()
    cid = int(win._conversation_id)
    win._record_history("user", "race-user")
    turn_id = "turn-race-5xx"
    reply = "streaming 5xx recovered answer"
    win._turn_gate.begin(turn_id)
    win._turn_gate.arm()
    win._turn_worker_meta[turn_id] = cid
    win._on_chat_failed_for_turn("HTTP 500: llama-server 0xc0000409", turn_id)
    app.processEvents()
    win._on_chat_finished_for_turn(reply, turn_id)
    app.processEvents()
    texts = [r["content"] for r in history_dicts(win._db, cid)]
    assert "race-user" in texts, texts
    assert reply in texts, texts
    win.close()
    app.processEvents()


def _check_worker_done_after_stream_fail_shape() -> None:
    """비스트림 복구 형태(델타 없이 TurnFinished 텍스트)면 finished_ok."""
    from pathlib import Path

    from iris.engine import EngineHome, InternalSidecar
    from iris.infrastructure.iris_agent_client import IrisAgentInferenceTarget
    from iris.ui.workers.iris_agent_workers import IrisAgentChatWorker

    class _StubEngine:
        def __init__(self, events):
            self._events = list(events)
            self.source = InternalSidecar(home=EngineHome(Path.home() / ".iris-light" / "engine"))
            self.turns = []

        def run_turn(self, turn):
            self.turns.append(turn)
            yield from self._events

    def _run(events):
        engine = _StubEngine(events)
        worker = IrisAgentChatWorker(
            "gemma4:26b-a4b-it-qat",
            [{"role": "user", "content": "안녕"}],
            target=IrisAgentInferenceTarget(
                model="gemma4:26b-a4b-it-qat", provider="custom"
            ),
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
        return ok, failed

    ok, failed = _run([TurnFinished("안녕 복구됨")])
    assert failed == [], failed
    assert ok == ["안녕 복구됨"], ok

    ok2, failed2 = _run(
        [TurnFailed(EngineError(EngineErrorCode.UNKNOWN, "stream 500"))]
    )
    assert ok2 == []
    assert failed2, failed2


def _check_hanging_native_invoke_cannot_block_finished_ok() -> None:
    """매달린 invoke_native_tool 이 run()의 finished_ok 를 막지 못한다."""
    import threading
    from pathlib import Path

    from PyQt6.QtCore import Qt

    from iris.engine import EngineHome, InternalSidecar
    from iris.infrastructure.iris_agent_client import IrisAgentInferenceTarget
    from iris.ui.workers.iris_agent_workers import IrisAgentChatWorker

    class _StubEngine:
        def __init__(self, events):
            self._events = list(events)
            self.source = InternalSidecar(
                home=EngineHome(Path.home() / ".iris-light" / "engine")
            )
            self.turns = []

        def run_turn(self, turn):
            self.turns.append(turn)
            yield from self._events

    hang = threading.Event()

    def _hang_invoke(name: str, args=None):
        hang.wait(timeout=30)
        return {"ok": False, "error": "hung"}

    engine = _StubEngine([TurnFinished("wire must not block")])
    worker = IrisAgentChatWorker(
        "gemma4:26b-a4b-it-qat",
        [{"role": "user", "content": "안녕"}],
        target=IrisAgentInferenceTarget(
            model="gemma4:26b-a4b-it-qat", provider="custom"
        ),
    )
    ok: list[str] = []
    failed: list[str] = []
    # DirectConnection: slot runs in emitter thread (no event-loop queue).
    worker.finished_ok.connect(ok.append, Qt.ConnectionType.DirectConnection)
    worker.failed.connect(failed.append, Qt.ConnectionType.DirectConnection)
    # Real _wire_native_speak_tools (no patch). Hanging invoke must not be on hot path.
    os.environ.pop("IRIS_WIRE_NATIVE_SPEAK_TOOLS", None)
    with (
        patch("iris.ui.workers.iris_agent_workers.shared_engine", return_value=engine),
        patch(
            "iris.ui.workers.iris_agent_workers._engine_source",
            return_value=engine.source,
        ),
        patch.object(IrisAgentChatWorker, "invoke_native_tool", staticmethod(_hang_invoke)),
    ):
        done = threading.Event()

        def _run():
            try:
                worker.run()
            finally:
                done.set()

        t = threading.Thread(target=_run, daemon=True)
        t.start()
        assert done.wait(timeout=5.0), "IrisAgentChatWorker.run blocked before engine"
    hang.set()
    assert failed == [], failed
    assert ok == ["wire must not block"], ok
    assert engine.turns, "run() never reached shared_engine.run_turn"


def _check_soft_sse_recovers_content() -> None:
    """같은 SSE에서 error 후 content+[DONE]이면 raise하지 않고 텍스트를 낸다."""
    import json

    from iris.infrastructure.iris_agent_client import IrisAgentClient

    soft_lines = [
        b"data: " + json.dumps({"error": {"message": "llama-server 500"}}).encode() + b"\n",
        b"\n",
        b"data: "
        + json.dumps({"choices": [{"delta": {"content": "hi"}}]}).encode()
        + b"\n",
        b"\n",
        b"data: [DONE]\n",
    ]

    class _FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    client = IrisAgentClient("http://127.0.0.1:9/v1", api_key="x")
    with (
        patch("iris.infrastructure.iris_agent_client.urlopen", return_value=_FakeResp()),
        patch(
            "iris.infrastructure.iris_agent_client._iter_response_raw_lines",
            return_value=iter(soft_lines),
        ),
    ):
        evs = list(client.stream_chat("m", [{"role": "user", "content": "a"}]))
    assert any(e.get("content") == "hi" for e in evs), evs
    assert evs[-1].get("done") is True


def main() -> None:
    _check_soft_sse_recovers_content()
    _check_worker_done_after_stream_fail_shape()
    _check_hanging_native_invoke_cannot_block_finished_ok()
    app = QApplication.instance() or QApplication(sys.argv)
    _check_fail_keeps_user(app)
    _check_finished_records_assistant(app)
    _check_orphan_without_meta_still_lands(app)
    _check_fail_then_finish_lands(app)
    print("chat landing contract ok")


if __name__ == "__main__":
    main()