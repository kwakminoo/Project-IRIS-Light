"""Ctrl+N / force 새 채팅 자검."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeySequence
from PyQt6.QtWidgets import QApplication, QWidget
from PyQt6.QtGui import QShortcut

from iris.runtime.chat_session import ChatSession
from iris.storage.conversations import (
    append_message,
    start_new_conversation,
)
from iris.storage.database import Database


def _check_force_new(db: Database) -> None:
    session = ChatSession(db)
    first = session.conversation_id
    same = start_new_conversation(db)
    assert same == first, (same, first)
    forced = start_new_conversation(db, force=True)
    assert forced != first, (forced, first)
    session.activate(forced)
    again = session.start_new(force=True)
    assert again != forced, (again, forced)


def _check_shortcut_fires(app: QApplication) -> None:
    from PyQt6.QtCore import QEvent
    from PyQt6.QtGui import QKeyEvent

    from iris.ui.workspaces.iris_ide_window import IrisIdeWindow

    hits: list[str] = []
    host = QWidget()
    host.show()
    sc = QShortcut(QKeySequence("Ctrl+N"), host)
    sc.setContext(Qt.ShortcutContext.WindowShortcut)
    sc.activated.connect(lambda: hits.append("main"))
    app.processEvents()
    edit_focus = QWidget(host)
    edit_focus.setFocus()
    app.processEvents()
    for typ in (QEvent.Type.ShortcutOverride, QEvent.Type.KeyPress):
        ev = QKeyEvent(typ, Qt.Key.Key_N, Qt.KeyboardModifier.ControlModifier, "n")
        app.sendEvent(edit_focus, ev)
        app.processEvents()
    assert hits == ["main"], hits

    ide_hits: list[str] = []
    ide = IrisIdeWindow()
    ide.bind_new_chat_shortcut(lambda: ide_hits.append("ide"))
    ide.show()
    ide.raise_()
    ide.activateWindow()
    app.processEvents()
    child = QWidget(ide)
    child.setFocus()
    app.processEvents()
    for typ in (QEvent.Type.ShortcutOverride, QEvent.Type.KeyPress):
        ev = QKeyEvent(typ, Qt.Key.Key_N, Qt.KeyboardModifier.ControlModifier, "n")
        app.sendEvent(child, ev)
        app.processEvents()
    assert ide_hits == ["ide"], ide_hits
    assert ide._new_chat_shortcut is not None
    assert ide._new_chat_shortcut.context() == Qt.ShortcutContext.WindowShortcut
    ide.close()


def _check_session_with_messages_opens(db: Database) -> None:
    session = ChatSession(db)
    append_message(db, session.conversation_id, "user", "hello")
    session.history = [{"role": "user", "content": "hello"}]
    before = session.conversation_id
    cid = session.start_new(force=True)
    assert cid != before
    session.activate(cid)
    assert session.conversation_id == cid
    assert session.history == []


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    tmp = tempfile.mkdtemp()
    try:
        db = Database(Path(tmp) / "chat.db")
        _check_force_new(db)
        _check_session_with_messages_opens(db)
        try:
            db.close()
        except Exception:
            pass
    finally:
        import shutil

        shutil.rmtree(tmp, ignore_errors=True)
    _check_shortcut_fires(app)
    print("new chat shortcut OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
