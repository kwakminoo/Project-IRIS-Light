"""같은 대화의 중지·오류·늦은 신호·재시작 복원·종료 시 워커 취소.

대화 전환 중단 시나리오는 여기 넣지 않는다.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWidgets import QApplication

from iris.runtime.chat_session import ChatSession
from iris.storage.database import Database


def _texts(history: list[dict[str, str]]) -> list[str]:
    return [item["content"] for item in history]


def _check_reopen(path: Path) -> None:
    db = Database(path)
    session = ChatSession(db)
    assert session.record("user", "저장할 질문") is None
    assert session.record("assistant", "저장할 답") is None
    cid = session.conversation_id
    other = session.start_new()
    session.activate(other)
    session.activate(cid)
    assert _texts(session.history) == ["저장할 질문", "저장할 답"]
    db._conn.close()

    again = ChatSession(Database(path))
    assert again.conversation_id == cid
    assert _texts(again.history) == ["저장할 질문", "저장할 답"]
    again.db._conn.close()


class _SigWorker(QThread):
    connecting = pyqtSignal(str, str)
    content_chunk = pyqtSignal(str)
    finished_ok = pyqtSignal(str)
    failed = pyqtSignal(str)

    def start(self, priority: QThread.Priority = QThread.Priority.InheritPriority) -> None:  # noqa: N802
        self.starts = getattr(self, "starts", 0) + 1

    def request_cancel(self) -> None:
        self.cancelled = True


class _RunningWorker:
    def __init__(self) -> None:
        self.cancelled = False
        self.waited = False

    def isRunning(self) -> bool:  # noqa: N802
        return True

    def request_cancel(self) -> None:
        self.cancelled = True

    def wait(self, _ms: int = 0) -> bool:
        self.waited = True
        return True


def _check_window(app: QApplication) -> None:
    from iris.ui.window.main_window import MainWindow

    win = MainWindow(test_mode=True)
    win.show()
    app.processEvents()
    win._chat_session.clear_messages()
    win._record_history("user", "첫 질문")
    win._chat.begin_stream_message("Iris", speech_sync=False)
    win._chat.append_stream_chunk("여기까지")
    win._turn_gate.begin("turn-1")
    win._turn_gate.arm()
    win._on_chat_stop()
    app.processEvents()
    assert not win._busy
    assert win._active_turn_id == ""
    assert _texts(win._history) == ["첫 질문", "여기까지"], _texts(win._history)
    assert "대화 전환으로" not in win._history[-1]["content"]

    win._record_history("user", "중지 다음")
    win._turn_gate.begin("turn-2")
    win._turn_gate.arm()
    before = list(win._history)
    win._on_chat_finished_for_turn("첫 턴의 늦은 완료", "turn-1")
    win._on_chat_failed_for_turn("첫 턴의 늦은 오류", "turn-1")
    app.processEvents()
    assert win._history == before
    assert win._turn_gate.is_current("turn-2") and win._busy
    win._on_chat_finished_for_turn("둘째 답", "turn-2")
    app.processEvents()
    assert _texts(win._history)[-1] == "둘째 답"
    assert not win._busy

    win._record_history("user", "실패할 질문")
    win._turn_gate.begin("turn-3")
    win._turn_gate.arm()
    win._on_chat_failed_for_turn("연결 거절", "turn-3")
    app.processEvents()
    assert _texts(win._history)[-1] == "둘째 답"
    assert not any(item["content"] == "실패할 질문" for item in win._history)
    assert not win._busy
    win._record_history("user", "오류 다음")
    win._turn_gate.begin("turn-4")
    win._turn_gate.arm()
    win._on_chat_failed_for_turn("또 거절", "turn-3")
    app.processEvents()
    assert _texts(win._history)[-1] == "오류 다음"
    assert win._turn_gate.is_current("turn-4") and win._busy
    win._turn_gate.finish("turn-4")

    worker = _SigWorker()
    win._turn_gate.begin("turn-5")
    win._turn_gate.arm()
    win._start_chat_worker(worker, "turn-5")
    win._start_chat_worker(worker, "turn-5")
    assert worker.starts == 2
    win._record_history("user", "중복 연결")
    worker.finished_ok.emit("한 번만")
    app.processEvents()
    assert _texts(win._history).count("한 번만") == 1
    assert not win._busy

    running = _RunningWorker()
    win._chat_worker = running
    win.close()
    app.processEvents()
    assert running.cancelled and running.waited


def main() -> None:
    tmp = tempfile.mkdtemp()
    try:
        _check_reopen(Path(tmp) / "chat.db")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    app = QApplication.instance() or QApplication(sys.argv)
    _check_window(app)
    print("turn followup ok")


if __name__ == "__main__":
    main()
