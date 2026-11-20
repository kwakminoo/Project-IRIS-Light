"""G18: Explorer file drop on H1 WebEngine lands as composer attachment chips.

Premise (measured): ChatPanel.dropEvent attaches when called directly with a
position over H1, but QWebEngineView AcceptDrops=True swallows sendEvent Drop
(chips stay empty). Fix: host AcceptDrops + view AcceptDrops off; host
forwards to ChatPanel attach path (native Qt, not WebChannel File API).
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from weakref import WeakSet

from iris.ui.qt_bootstrap import ensure_qt_webengine_ready

ensure_qt_webengine_ready()

from PyQt6.QtCore import QEventLoop, QMimeData, QPointF, Qt, QTimer, QUrl
from PyQt6.QtGui import QDragEnterEvent, QDropEvent
from PyQt6.QtWidgets import QApplication, QWidget

_APP = QApplication.instance() or QApplication(sys.argv)

from iris.core.message_parts import TextPart
from iris.ui.chat.chat_panel import ChatPanel
from iris.ui.window.file_drop import arm_widget_tree


def _wait_h1_ready(host, *, rounds: int = 50) -> None:
    app = QApplication.instance()
    assert app is not None
    for _ in range(rounds):
        app.processEvents()
        if host._view is not None and getattr(host, "_page_ready", False):
            return
        loop = QEventLoop()
        QTimer.singleShot(50, loop.quit)
        loop.exec()


def main() -> None:
    panel = ChatPanel()
    panel.resize(640, 480)
    panel.show()
    host = panel.transcript()
    host.append_turn(
        "assistant",
        (TextPart(markdown="h1 drop surface"),),
        msg_id="h1-drop-probe",
    )
    _wait_h1_ready(host)
    view = host._view
    assert view is not None, "H1 WebEngine view missing"
    assert getattr(host, "_page_ready", False) is True

    catcher = host.drop_catcher()
    assert catcher.acceptDrops() is True, "H1 drop catcher must acceptDrops"
    assert host.acceptDrops() is True
    assert view.acceptDrops() is False, "WebEngine must not swallow CF_HDROP"
    assert bool(view.property("irisSkipAcceptDrops")) is True

    # MainWindow arm_widget_tree must not re-enable Chromium AcceptDrops.
    class _Filt(QWidget):
        def eventFilter(self, *_a) -> bool:
            return False

    armed: WeakSet = WeakSet()
    arm_widget_tree(panel, _Filt(), armed)
    assert view.acceptDrops() is False, "arm must keep H1 WebEngine AcceptDrops off"
    assert host.acceptDrops() is True

    tmp = Path(tempfile.gettempdir()) / "iris_h1_drop_attach.txt"
    tmp.write_text("h1-drop", encoding="utf-8")
    try:
        panel._input_area.attachment_strip.clear_paths()
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(tmp))])

        # Premise A: panel path still works when Drop is delivered to ChatPanel.
        h1_pos = QPointF(host.mapTo(panel, host.rect().center()))
        panel_drop = QDropEvent(
            h1_pos,
            Qt.DropAction.CopyAction,
            mime,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        panel.dropEvent(panel_drop)
        chips_panel = panel._input_area.attachment_strip.paths()
        assert any(Path(p).name == tmp.name for p in chips_panel), chips_panel

        # H1 surface: DragEnter + Drop on host / drop_catcher → composer chips.
        panel._input_area.attachment_strip.clear_paths()
        target = catcher
        enter = QDragEnterEvent(
            target.rect().center(),
            Qt.DropAction.CopyAction,
            mime,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        assert _APP.sendEvent(target, enter) is True
        assert enter.isAccepted(), "H1 catcher must accept attachable DragEnter"

        drop = QDropEvent(
            QPointF(target.rect().center()),
            Qt.DropAction.CopyAction,
            mime,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        assert _APP.sendEvent(target, drop) is True
        chips = panel._input_area.attachment_strip.paths()
        assert any(Path(p).name == tmp.name for p in chips), chips
        assert drop.isAccepted()

        # View must not be the attach sink (AcceptDrops off → no swallow path).
        panel._input_area.attachment_strip.clear_paths()
        view_drop = QDropEvent(
            QPointF(view.rect().center()),
            Qt.DropAction.CopyAction,
            mime,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        _APP.sendEvent(view, view_drop)
        assert panel._input_area.attachment_strip.paths() == []
    finally:
        tmp.unlink(missing_ok=True)
        panel.close()

    print("transcript_h1_drop ok", "catcher", catcher.objectName())
    _APP.quit()


if __name__ == "__main__":
    main()
