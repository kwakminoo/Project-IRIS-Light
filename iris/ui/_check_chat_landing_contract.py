"""채팅 착지 계약: 스트림 5xx 복구 뒤 TurnFinished 텍스트가 DB에 남고 user는 유지."""

from __future__ import annotations

import os
import sys
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from iris.engine import EngineError, EngineErrorCode, TurnFailed, TurnFinished
from iris.storage.conversations import (
    CANCELLED_NOTE,
    INTERRUPTED_NOTE,
    SYSTEM_ERROR_PREFIX,
    history_dicts,
)


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
    assert any(SYSTEM_ERROR_PREFIX in (r.get("content") or "") for r in history_dicts(win._db, cid)), after
    win.close()
    app.processEvents()


def _check_fail_lands_system_error_row(app: QApplication) -> None:
    """TOOL_ERROR_BUDGET / fail → DB-visible system-error land; user kept."""
    from iris.ui.window.main_window import MainWindow

    win = MainWindow(test_mode=True)
    win.show()
    app.processEvents()
    cid = int(win._conversation_id)
    win._record_history("user", "budget-fail-user")
    turn_id = "turn-tool-budget"
    win._turn_gate.begin(turn_id)
    win._turn_gate.arm()
    win._turn_worker_meta[turn_id] = cid
    budget_msg = EngineError(EngineErrorCode.TOOL_ERROR_BUDGET, "Stopped after 10").user_message
    win._runs.slot(cid).pending_partial = "partial before budget"
    win._on_chat_failed_for_turn(budget_msg, turn_id)
    app.processEvents()
    rows = history_dicts(win._db, cid)
    texts = [r["content"] for r in rows]
    assert "budget-fail-user" in texts, texts
    land = next((t for t in texts if SYSTEM_ERROR_PREFIX in t), "")
    assert land, texts
    assert "partial before budget" in land, land
    assert budget_msg in land or "도구 오류" in land, land
    assert not any(
        r["role"] == "assistant"
        and SYSTEM_ERROR_PREFIX not in (r.get("content") or "")
        and "partial before budget" == (r.get("content") or "").strip()
        for r in rows
    )
    win.close()
    app.processEvents()


def _check_away_fail_lands_db(app: QApplication) -> None:
    """Background conversation fail still writes a system-error row for that cid."""
    from iris.storage.conversations import append_message, create_conversation
    from iris.ui.window.main_window import MainWindow

    win = MainWindow(test_mode=True)
    win.show()
    app.processEvents()
    foreground = int(win._conversation_id)
    win._record_history("user", "fg-user")
    away_cid = int(create_conversation(win._db).id)
    win._runs.slot(away_cid)
    append_message(win._db, away_cid, "user", "away-user")
    turn_id = "turn-away-fail"
    slot = win._runs.slot(away_cid)
    slot.gate.begin(turn_id)
    slot.gate.arm()
    slot.pending_partial = "away-partial"
    win._turn_worker_meta[turn_id] = away_cid
    assert win._conversation_id == foreground
    win._on_chat_failed_for_turn("away stream died", turn_id)
    app.processEvents()
    away_texts = [r["content"] for r in history_dicts(win._db, away_cid)]
    assert "away-user" in away_texts, away_texts
    land = next((t for t in away_texts if SYSTEM_ERROR_PREFIX in t), "")
    assert land and "away-partial" in land, away_texts
    fg_texts = [r["content"] for r in history_dicts(win._db, foreground)]
    assert not any(SYSTEM_ERROR_PREFIX in t for t in fg_texts), fg_texts
    win.close()
    app.processEvents()


def _check_user_stop_lands_cancel_envelope(app: QApplication) -> None:
    """user_stop → DB system-error cancel land; user kept; not INTERRUPTED_NOTE."""
    from iris.ui.window.main_window import MainWindow

    win = MainWindow(test_mode=True)
    win.show()
    app.processEvents()
    cid = int(win._conversation_id)
    win._record_history("user", "stop-user")
    turn_id = "turn-user-stop"
    win._turn_gate.begin(turn_id)
    win._turn_gate.arm()
    win._turn_worker_meta[turn_id] = cid
    win._chat.begin_stream_message("Iris", speech_sync=False)
    win._chat.append_stream_chunk("partial stop text")
    win._on_chat_stop()
    app.processEvents()
    rows = history_dicts(win._db, cid)
    texts = [r["content"] for r in rows]
    assert "stop-user" in texts, texts
    land = next((t for t in texts if SYSTEM_ERROR_PREFIX in t), "")
    assert land, texts
    assert "partial stop text" in land, land
    assert CANCELLED_NOTE in land, land
    assert INTERRUPTED_NOTE not in land, land
    # Idempotent: second cancel / late orphan must not add another assistant row.
    before_n = sum(1 for r in rows if r["role"] == "assistant")
    win._land_cancelled_turn(
        turn_id, land, win._runs.slot(cid)
    )
    win._persist_orphan_finished(turn_id, "late model prose after cancel")
    app.processEvents()
    after = history_dicts(win._db, cid)
    after_n = sum(1 for r in after if r["role"] == "assistant")
    assert after_n == before_n, (before_n, after_n, [r["content"] for r in after])
    assert not any("late model prose" in (r.get("content") or "") for r in after)
    win.close()
    app.processEvents()


def _check_interrupt_lands_interrupted_envelope(app: QApplication) -> None:
    """conversation_switch cancel keeps INTERRUPTED_NOTE inside system envelope."""
    from iris.ui.window.main_window import MainWindow

    win = MainWindow(test_mode=True)
    win.show()
    app.processEvents()
    cid = int(win._conversation_id)
    win._record_history("user", "switch-user")
    turn_id = "turn-switch-cancel"
    win._turn_gate.begin(turn_id)
    win._turn_gate.arm()
    win._turn_worker_meta[turn_id] = cid
    win._chat.begin_stream_message("Iris", speech_sync=False)
    win._chat.append_stream_chunk("partial switch text")
    win._cancel_current_turn(
        reason="conversation_switch", preserve_partial_response=True
    )
    app.processEvents()
    texts = [r["content"] for r in history_dicts(win._db, cid)]
    assert "switch-user" in texts, texts
    land = next((t for t in texts if SYSTEM_ERROR_PREFIX in t), "")
    assert land and INTERRUPTED_NOTE in land, texts
    assert "partial switch text" in land, land
    assert CANCELLED_NOTE not in land, land
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


def _check_current_supports_tools() -> None:
    """Hermes finish path reads ChatPanel.current_supports_tools — must exist."""
    import inspect

    from iris.ui.chat.chat_panel import ChatPanel
    from iris.ui.window.main_window import MainWindow

    panel = ChatPanel()
    assert callable(getattr(panel, "current_supports_tools", None)), (
        "ChatPanel.current_supports_tools missing — UI land swallows AttributeError"
    )
    assert isinstance(panel.current_supports_tools(), bool)
    src = inspect.getsource(MainWindow._on_chat_finished)
    assert "current_supports_tools()" in src
    panel.close()


def main() -> None:
    _check_soft_sse_recovers_content()
    _check_worker_done_after_stream_fail_shape()
    _check_hanging_native_invoke_cannot_block_finished_ok()
    app = QApplication.instance() or QApplication(sys.argv)
    _check_current_supports_tools()
    _check_fail_keeps_user(app)
    _check_fail_lands_system_error_row(app)
    _check_away_fail_lands_db(app)
    _check_user_stop_lands_cancel_envelope(app)
    _check_interrupt_lands_interrupted_envelope(app)
    _check_finished_records_assistant(app)
    _check_orphan_without_meta_still_lands(app)
    _check_fail_then_finish_lands(app)
    print("chat landing contract ok")


if __name__ == "__main__":
    main()