"""채팅 영역 높이 드래그 자검 — overlay 없이 패널 자체가 커진다."""

from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QSizePolicy, QVBoxLayout, QWidget

from iris.ui.chat.chat_panel import ChatPanel


def _host(app: QApplication) -> tuple[QWidget, QWidget, ChatPanel]:
    host = QWidget()
    host.resize(480, 720)
    lay = QVBoxLayout(host)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(10)
    above = QWidget()
    above.setMinimumHeight(80)
    above.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    lay.addWidget(above, 2)
    panel = ChatPanel()
    lay.addWidget(panel, 3)
    host.show()
    app.processEvents()
    return host, above, panel


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    host, above, panel = _host(app)

    assert panel._height_handle.objectName() == "ChatHeightHandle"
    assert not hasattr(panel, "open_full_view")
    assert not hasattr(panel._log, "reading_requested")
    overlays = [w for w in app.allWidgets() if w.objectName() == "MessageReadingOverlay"]
    assert overlays == [], overlays

    h0 = panel.height()
    a0 = above.height()
    log0 = panel._log.height()
    assert a0 > 80, a0
    assert h0 > 120, h0

    panel._begin_height_drag(400)
    panel._on_height_drag(220)
    app.processEvents()
    extra = panel._extra_h
    assert extra == 180, extra
    assert not panel._is_fully_expanded()
    assert panel.height() > h0, (h0, panel.height())
    assert panel._log.height() > log0, (log0, panel._log.height())
    assert above.height() < a0, (a0, above.height())
    assert not panel.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    panel._on_height_drag(400)
    app.processEvents()
    assert panel._extra_h == 0, panel._extra_h
    assert panel.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    assert abs(panel.height() - h0) <= 12, (h0, panel.height())

    panel._apply_chat_extra(10_000)
    app.processEvents()
    max_h = panel.height()
    assert max_h >= host.height() - 4, (max_h, host.height())
    assert panel._is_fully_expanded()
    assert (not above.isVisible()) or above.height() == 0, (above.isVisible(), above.height())

    panel._apply_chat_extra(0)
    app.processEvents()
    assert panel._extra_h == 0
    assert above.isVisible()

    print("chat resize ok", h0, "-> extra 180 / max", max_h)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
