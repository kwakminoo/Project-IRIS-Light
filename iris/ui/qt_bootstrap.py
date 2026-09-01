"""PyQt6 WebEngine startup contract — must run before QApplication.

IRIS IDE (Theia QWebEngineView) + email HTML viewer share one Chromium stack.
Importing WebEngine after QApplication without AA_ShareOpenGLContexts crashes Windows
(작업이 중단되었습니다 / exit 0xC0000409).

Creating QWebEngineView during MainWindow.__init__ blocks the UI thread for tens of
seconds (Windows shows 응답하지 않음). Defer view construction until first use.
"""

from __future__ import annotations

import os


def _apply_chromium_flags() -> None:
    # ponytail: Windows GPU Chromium init can freeze the GUI for minutes on first paint.
    extra = "--disable-gpu --disable-gpu-compositing"
    cur = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "").strip()
    if "--disable-gpu" not in cur:
        os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = f"{cur} {extra}".strip() if cur else extra


def ensure_qt_webengine_ready() -> bool:
    """Set ShareOpenGLContexts before QApplication. Do not init Chromium here."""
    _apply_chromium_flags()
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QApplication

    if QApplication.instance() is None:
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)
    return True


def _self_check() -> None:
    import sys

    from PyQt6.QtWidgets import QApplication

    ensure_qt_webengine_ready()
    app = QApplication.instance() or QApplication(sys.argv)
    from iris.ui.window.main_window import MainWindow

    win = MainWindow(test_mode=True)
    assert win.windowTitle()
    print("qt_bootstrap ok")


if __name__ == "__main__":
    _self_check()
