"""Chat transcript scrollbar chrome stays fully transparent."""

from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from iris.ui.qt_bootstrap import ensure_qt_webengine_ready

ensure_qt_webengine_ready()

from PyQt6.QtWidgets import QApplication

_APP = QApplication.instance() or QApplication(sys.argv)

from iris.ui.chat.chat_panel import ChatPanel
from iris.ui.chat.transcript_h1 import _page_css


def main() -> int:
    css = _page_css()
    assert "::-webkit-scrollbar-thumb" in css
    # Thumb + hover must not use visible slate fills.
    assert "rgba(148, 163, 184" not in css.split("::-webkit-scrollbar-thumb")[1].split("::selection")[0], (
        "H1 scrollbar thumb must stay transparent"
    )
    assert "background: transparent" in css

    panel = ChatPanel()
    bar_css = panel._log.verticalScrollBar().styleSheet()
    assert "QScrollBar::handle:vertical" in bar_css
    assert "background: transparent" in bar_css
    assert "rgba(148, 163, 184" not in bar_css, "ChatLog handle must stay transparent"

    print("scrollbar_transparent ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
