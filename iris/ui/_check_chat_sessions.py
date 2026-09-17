"""대화 세션 UI 자검 — CHATS 패널 · 트랜스크립트 복원 · 사이드바 배치."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QFrame, QLabel, QLineEdit, QPushButton

from iris.storage.conversations import (
    append_message,
    create_conversation,
    list_conversations,
)
from iris.storage.database import Database
from iris.ui.chat.chat_panel import ChatPanel
from iris.ui.monitor.chat_history_panel import ChatHistoryPanel
from iris.ui.sidebar.left_sidebar_panel import LeftSidebarPanel


def _check_history_panel(app: QApplication, db: Database) -> None:
    first = create_conversation(db)
    append_message(db, first.id, "user", "IRIS 구조 알려줘")
    append_message(db, first.id, "assistant", "ui/system/infrastructure로 나뉩니다.")
    second = create_conversation(db)
    append_message(db, second.id, "user", "새 채팅 기능 붙여줘")

    panel = ChatHistoryPanel()
    panel.set_conversations(list_conversations(db), active_id=second.id)
    app.processEvents()

    opened: list[int] = []
    deleted: list[int] = []
    created: list[int] = []
    renamed: list[tuple[int, str]] = []
    panel.conversation_selected.connect(opened.append)
    panel.conversation_delete_requested.connect(deleted.append)
    panel.conversation_rename_requested.connect(lambda i, t: renamed.append((i, t)))
    panel.new_chat_requested.connect(lambda: created.append(1))

    rows = [
        f for f in panel._inner.findChildren(QFrame) if f.objectName() == "HudChatRow"
    ]
    assert len(rows) == 2, f"대화 행 2개를 기대했다: {len(rows)}"

    buttons = panel.findChildren(QPushButton)
    titles = {b.toolTip() for b in buttons}
    assert "IRIS 구조 알려줘" in titles, titles
    assert "새 채팅 기능 붙여줘" in titles, titles
    assert "새 채팅" in titles, "새 채팅(+) 버튼이 없다"
    assert "제목 수정" in titles, "제목 수정 버튼이 없다"

    for b in buttons:
        if b.toolTip() == "IRIS 구조 알려줘":
            b.click()
        elif b.toolTip() == "대화 삭제: 새 채팅 기능 붙여줘":
            b.click()
        elif b.toolTip() == "새 채팅":
            b.click()
    app.processEvents()

    assert opened == [first.id], opened
    assert deleted == [second.id], deleted
    assert created == [1], created

    panel.set_conversations(list_conversations(db), active_id=first.id)
    app.processEvents()
    live_rows = []
    for i in range(panel._inner_lay.count()):
        w = panel._inner_lay.itemAt(i).widget()
        if w is not None and w.objectName() == "HudChatRow":
            live_rows.append(w)
    first_row = next(row for row in live_rows if getattr(row, "_conv_id", None) == first.id)
    first_row._btn.click()
    edits = [e for e in panel.findChildren(QLineEdit, "ChatTitleEdit") if not e.isHidden()]
    assert len(edits) == 1, "활성 제목 클릭 후 편집칸이 없다"
    edits[0].setText("직접 지은 제목")
    edits[0].returnPressed.emit()
    app.processEvents()
    assert renamed == [(first.id, "직접 지은 제목")], renamed

    for i in range(panel._inner_lay.count()):
        row = panel._inner_lay.itemAt(i).widget()
        if row is not None and getattr(row, "_conv_id", None) == second.id:
            row._begin_edit()
            row._edit.setText("취소될 제목")
            from PyQt6.QtCore import QEvent, Qt
            from PyQt6.QtGui import QKeyEvent

            ev = QKeyEvent(
                QEvent.Type.KeyPress,
                Qt.Key.Key_Escape,
                Qt.KeyboardModifier.NoModifier,
            )
            row.eventFilter(row._edit, ev)
            app.processEvents()
            break
    assert renamed == [(first.id, "직접 지은 제목")], renamed

    panel.set_conversations([], active_id=0)
    app.processEvents()
    hints = [
        lab.text().lower()
        for lab in panel._inner.findChildren(QLabel)
        if lab.text().strip()
    ]
    assert any("no chats yet" in h for h in hints), hints


def _check_transcript_restore(app: QApplication) -> None:
    chat = ChatPanel()
    chat.append_message_instant("You", "첫 세션 질문")
    chat.append_message_instant("Iris", "첫 세션 답변")
    app.processEvents()
    assert "첫 세션 질문" in chat._log.toPlainText()

    chat.clear_transcript()
    app.processEvents()
    assert chat._log.toPlainText().strip() == "", "세션 전환 후 로그가 남았다"
    assert not chat._log._tool_blocks
    assert not chat._stream_active

    chat.restore_messages(
        [
            {"role": "user", "content": "복원된 질문"},
            {"role": "assistant", "content": "복원된 답변"},
            {"role": "system", "content": "무시되어야 함"},
        ]
    )
    app.processEvents()
    body = chat._log.toPlainText()
    assert "복원된 질문" in body and "복원된 답변" in body, body
    assert "무시되어야 함" not in body, "system 메시지가 화면에 새어 나왔다"


def _check_sidebar_modes(app: QApplication) -> None:
    sidebar = LeftSidebarPanel()
    app.processEvents()
    assert sidebar._top_stack.currentWidget() is sidebar.chat_history
    assert not hasattr(sidebar, "window_list")

    sidebar.set_workspace_mode("email")
    app.processEvents()
    assert sidebar._top_stack.currentWidget() is sidebar.email_folder

    sidebar.set_workspace_mode("assistant")
    app.processEvents()
    assert sidebar._top_stack.currentWidget() is sidebar.chat_history
    assert sidebar.chat_history.isVisible()


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        db = Database(Path(tmp) / "chat_sessions_check.db")
        try:
            _check_history_panel(app, db)
        finally:
            db._conn.close()
    _check_transcript_restore(app)
    _check_sidebar_modes(app)
    print("chat sessions ui OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
