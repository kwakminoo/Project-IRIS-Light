"""생성 중 대화 전환 — 워커는 계속되고, 토큰은 그 대화에만 붙는다."""

from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from iris.runtime.chat_run_slot import ChatRunMap
from iris.runtime.turn_followthrough import CAP
from iris.storage.conversations import history_dicts


class _Worker:
    def __init__(self) -> None:
        self.cancelled = False

    def request_cancel(self) -> None:
        self.cancelled = True

    def isRunning(self) -> bool:  # noqa: N802
        return True

    def wait(self, _ms: int = 0) -> bool:
        return True


def _assistant(db, cid: int) -> str:
    parts = [
        item["content"]
        for item in history_dicts(db, cid)
        if item["role"] == "assistant"
    ]
    return "\n".join(parts)


def main() -> None:
    from iris.ui.window.main_window import MainWindow

    app = QApplication.instance() or QApplication(sys.argv)
    win = MainWindow(test_mode=True)
    assert isinstance(win._runs, ChatRunMap)
    assert win._runs.slot(win._conversation_id).conversation_id == win._conversation_id
    assert CAP == 8
    win.show()
    app.processEvents()

    session = win._chat_session
    a = win._conversation_id
    win._record_history("user", "과일을 주제로 짧은 설명")
    win._chat.begin_stream_message("Iris", speech_sync=False)
    win._chat.append_stream_chunk("1. 과일 설명\n")
    worker = _Worker()
    win._chat_worker = worker
    gate = win._turn_gate
    gate.begin("turn-a")
    gate.arm()

    b = session.start_new()
    assert b != a
    win._on_conversation_selected(b)
    app.processEvents()

    assert not worker.cancelled
    assert win._conversation_id == b
    assert win._runs.slot(a).gate.is_current("turn-a")
    assert win._runs.slot(a).gate.busy
    assert not win._busy
    assert "과일" not in win._chat._log.toPlainText()

    before_b = history_dicts(win._db, b)
    win._on_content_chunk_for_turn("HIDDEN-TOKEN", "turn-a")
    app.processEvents()
    assert "HIDDEN-TOKEN" not in win._chat._log.toPlainText()
    assert "HIDDEN-TOKEN" in win._runs.slot(a).pending_partial
    assert history_dicts(win._db, b) == before_b

    win._on_chat_finished_for_turn("A의 끝난 답", "turn-a")
    app.processEvents()
    assert not worker.cancelled
    assert history_dicts(win._db, b) == before_b
    assert "A의 끝난 답" in _assistant(win._db, a)
    assert "A의 끝난 답" not in win._chat._log.toPlainText()
    assert not win._runs.slot(a).gate.busy
    assert win._conversation_id == b

    win._runs.slot(a).followthrough_count = 4
    win._runs.slot(b).followthrough_count = 1
    win._on_conversation_selected(a)
    app.processEvents()
    assert win._followthrough_count == 4
    assert win._runs.slot(b).followthrough_count == 1
    shown = win._chat._log.toPlainText()
    assert "A의 끝난 답" in shown
    assert "HIDDEN-TOKEN" not in shown

    other = _Worker()
    win._runs.slot(b).worker = other
    win._runs.slot(b).gate.begin("turn-b")
    win._runs.slot(b).gate.arm()
    win._on_chat_stop()
    app.processEvents()
    assert not other.cancelled
    assert win._runs.slot(b).gate.busy

    win.close()
    app.processEvents()
    print("conversation switch keeps background run ok")


if __name__ == "__main__":
    main()
