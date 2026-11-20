"""Ctrl+Tab 채팅 목록 자검."""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QApplication, QLabel, QWidget

from iris.runtime.chat_session import ChatSession
from iris.storage.conversations import append_message, start_new_conversation
from iris.storage.database import Database
from iris.ui.chat.chat_switch_picker import (
    ChatSwitchPicker,
    ChatSwitchRow,
    chat_switch_rows,
    install_chat_switch_shortcut,
)
from iris.ui.workspaces.iris_ide_window import IrisIdeWindow


def _conversation_count(db: Database) -> int:
    row = db._execute("SELECT COUNT(*) AS n FROM chat_conversations").fetchone()
    assert row is not None
    return int(row["n"])


def _assert_child_frame(picker: ChatSwitchPicker, host: QWidget) -> None:
    assert picker.parentWidget() is host
    flags = picker.windowFlags()
    for flag in (
        Qt.WindowType.Window,
        Qt.WindowType.Popup,
        Qt.WindowType.Tool,
        Qt.WindowType.Dialog,
    ):
        assert not flags & flag, (flags, flag)


def _press(app: QApplication, target: QWidget, key: Qt.Key) -> None:
    event = QKeyEvent(QEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier)
    app.sendEvent(target, event)
    app.processEvents()


def _check_rows_and_picker(app: QApplication, db: Database) -> None:
    session = ChatSession(db)
    recorded = int(session.conversation_id)
    other = start_new_conversation(db, force=True)
    append_message(db, other, "user", "other")
    assert int(session.conversation_id) == recorded
    before = _conversation_count(db)
    rows = chat_switch_rows(session)
    assert _conversation_count(db) == before
    assert int(session.conversation_id) == recorded
    current_at = [i for i, row in enumerate(rows) if row.current]
    assert current_at == [i for i, row in enumerate(rows) if row.conversation_id == recorded]
    assert len(current_at) == 1
    assert current_at[0] != 0, rows
    other_at = next(i for i, row in enumerate(rows) if not row.current)

    host = QWidget()
    host.resize(800, 600)
    host.show()
    app.processEvents()
    emitted: list[int] = []
    hidden: list[str] = []
    picker = ChatSwitchPicker(host, on_dismiss=lambda: hidden.append("hide"))
    picker.conversation_chosen.connect(emitted.append)
    _assert_child_frame(picker, host)
    picker.dismiss()
    assert hidden == []
    assert emitted == []

    picker.toggle(rows)
    app.processEvents()
    assert picker.is_open()
    assert picker._index == current_at[0]
    assert hidden == []
    assert emitted == []
    _assert_child_frame(picker, host)
    start = picker._index
    _press(app, picker, Qt.Key.Key_Up)
    assert picker._index == (start - 1) % len(rows)
    _press(app, picker, Qt.Key.Key_Down)
    assert picker._index == start

    picker.toggle(())
    app.processEvents()
    assert not picker.is_open()
    assert emitted == []
    assert hidden == ["hide"]
    assert int(session.conversation_id) == recorded

    hidden.clear()
    picker.toggle(rows)
    app.processEvents()
    assert picker.is_open()
    _press(app, picker, Qt.Key.Key_Escape)
    assert not picker.is_open()
    assert emitted == []
    assert hidden == ["hide"]
    assert int(session.conversation_id) == recorded

    hidden.clear()
    picker.toggle(rows)
    app.processEvents()
    _press(app, picker, Qt.Key.Key_Down if picker._index != other_at else Qt.Key.Key_Up)
    if picker._index != other_at:
        for _ in range(len(rows)):
            if picker._index == other_at:
                break
            _press(app, picker, Qt.Key.Key_Down)
    assert picker._index == other_at
    target = rows[other_at].conversation_id
    before_hide = len(hidden)
    _press(app, picker, Qt.Key.Key_Return)
    assert emitted == [target]
    assert not picker.is_open()
    assert hidden[before_hide:] == ["hide"]
    assert int(session.conversation_id) == recorded
    picker.dismiss()
    assert emitted == [target]
    assert int(session.conversation_id) == recorded

    emitted.clear()
    picker.toggle(())
    app.processEvents()
    assert picker.is_open()
    assert picker._index == -1
    empty = picker.findChild(QLabel, "ChatSwitchEmpty")
    assert empty is not None and empty.text() == "대화 없음" and not empty.isEnabled()
    _press(app, picker, Qt.Key.Key_Return)
    assert emitted == []
    assert picker.is_open()
    picker.dismiss()
    host.close()


def _fire_ctrl_tab(app: QApplication, target: QWidget) -> None:
    for typ in (QEvent.Type.ShortcutOverride, QEvent.Type.KeyPress):
        event = QKeyEvent(typ, Qt.Key.Key_Tab, Qt.KeyboardModifier.ControlModifier)
        app.sendEvent(target, event)
        app.processEvents()


def _check_shortcut_fires(app: QApplication) -> None:
    hits: list[str] = []
    host = QWidget()
    host.resize(640, 480)
    host.show()
    shortcut = install_chat_switch_shortcut(host, lambda: hits.append("main"))
    assert shortcut.context() == Qt.ShortcutContext.WindowShortcut
    app.processEvents()
    edit_focus = QWidget(host)
    edit_focus.setFocus()
    app.processEvents()
    _fire_ctrl_tab(app, edit_focus)
    assert hits == ["main"], hits

    ide_hits: list[str] = []
    ide = IrisIdeWindow()
    ide.bind_chat_switch_shortcut(lambda: ide_hits.append("ide"))
    ide.show()
    ide.raise_()
    ide.activateWindow()
    app.processEvents()
    child = QWidget(ide)
    child.setFocus()
    app.processEvents()
    _fire_ctrl_tab(app, child)
    assert ide_hits == ["ide"], ide_hits
    assert ide._chat_switch_shortcut is not None
    assert ide._chat_switch_shortcut.context() == Qt.ShortcutContext.WindowShortcut
    ide.close()
    host.close()


def _check_second_ctrl_tab_closes(app: QApplication) -> None:
    host = QWidget()
    host.resize(640, 480)
    host.show()
    picker = ChatSwitchPicker(host)
    row = ChatSwitchRow(1, "현재", True)
    hits: list[str] = []

    def toggle() -> None:
        hits.append("key")
        picker.toggle((row,))

    install_chat_switch_shortcut(host, toggle)
    child = QWidget(host)
    child.setFocus()
    app.processEvents()
    _fire_ctrl_tab(app, child)
    assert hits == ["key"], hits
    assert picker.is_open()
    picker.setFocus()
    app.processEvents()
    _fire_ctrl_tab(app, picker)
    assert hits == ["key", "key"], hits
    assert not picker.is_open()
    host.close()


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    tmp = tempfile.mkdtemp()
    try:
        db = Database(Path(tmp) / "chat.db")
        _check_rows_and_picker(app, db)
        try:
            db.close()
        except Exception:
            pass
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    _check_shortcut_fires(app)
    _check_second_ctrl_tab_closes(app)
    print("chat switch shortcut OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
