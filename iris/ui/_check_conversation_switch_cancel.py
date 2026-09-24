"""생성 중 대화 전환 — A는 중단 표시, 늦은 신호는 B와 새 턴을 바꾸지 않는다."""

from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from iris.storage.conversations import history_dicts


class _Worker:
    def __init__(self) -> None:
        self.cancelled = False

    def request_cancel(self) -> None:
        self.cancelled = True


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
    win.show()
    app.processEvents()

    session = win._chat_session
    gate = win._turn_gate
    a = win._conversation_id
    win._record_history("user", "과일을 주제로 짧은 설명 50개")
    win._chat.begin_stream_message("Iris", speech_sync=False)
    win._chat.append_stream_chunk("".join(f"{i}. 과일 설명\n" for i in range(1, 10)))
    worker = _Worker()
    win._chat_worker = worker
    gate.begin("turn-a")
    gate.arm()

    b = session.start_new()
    assert b != a
    win._on_conversation_selected(b)
    app.processEvents()

    assert worker.cancelled, "전환 시 A 워커 취소를 호출하지 않았다"
    assert win._chat_session is session
    assert win._turn_gate is gate
    assert win._conversation_id == b
    assert gate.active_id == ""
    assert not gate.busy
    assert "과일" not in _assistant(win._db, b)
    saved_a = _assistant(win._db, a)
    assert "9. 과일 설명" in saved_a
    assert "대화 전환으로 응답을 중단했습니다." in saved_a
    assert "10." not in saved_a

    before_b = history_dicts(win._db, b)
    before_a = history_dicts(win._db, a)
    win._on_chat_finished_for_turn("10. 늦게 온 완료\n50. 끝", "turn-a")
    win._on_chat_failed_for_turn("늦은 오류", "turn-a")
    app.processEvents()
    assert history_dicts(win._db, b) == before_b
    assert history_dicts(win._db, a) == before_a
    assert win._conversation_id == b
    assert not gate.busy
    assert gate.active_id == ""

    gate.begin("turn-b")
    gate.arm()
    win._on_chat_finished_for_turn("A의 나머지", "turn-a")
    win._on_chat_failed_for_turn("A 오류", "turn-a")
    app.processEvents()
    assert gate.is_current("turn-b")
    assert gate.busy
    assert history_dicts(win._db, b) == before_b

    gate.finish("turn-b")
    win._on_conversation_selected(a)
    app.processEvents()
    shown = win._chat._log.toPlainText()
    assert "과일 설명" in shown
    assert "대화 전환으로 응답을 중단했습니다." in shown
    assert "늦게" not in shown
    assert "10." not in _assistant(win._db, a)
    assert not gate.busy
    assert win._conversation_id == a

    win.close()
    app.processEvents()
    print("conversation switch cancel ok")


if __name__ == "__main__":
    main()
