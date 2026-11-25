"""H1 chat zoomFactor must return to 1.0 after browser-workspace leave.

Chromium Ctrl+wheel changes QWebEngineView.zoomFactor; setHtml/hide do not
clear it. Product resets via reset_page_zoom (also on show/loadFinished).

Run: .venv\\Scripts\\python.exe -m iris.ui.chat._check_chat_zoom_restore
"""

from __future__ import annotations

import sys

from PyQt6.QtCore import QEventLoop, QTimer
from PyQt6.QtWidgets import QApplication

from iris.core.message_parts import TextPart
from iris.ui.chat.transcript_h1 import H1TranscriptHost
from iris.ui.qt_bootstrap import ensure_qt_webengine_ready

_ZOOMED = 1.5


def _wait_h1_ready(host: H1TranscriptHost, timeout_ms: int = 15000) -> None:
    view = host._view
    assert view is not None
    loaded = {"done": False, "ok": False}
    loop = QEventLoop()

    def on_finished(ok: bool) -> None:
        loaded["ok"] = bool(ok)
        loaded["done"] = True
        loop.quit()

    view.loadFinished.connect(on_finished)
    host.append_turn("assistant", [TextPart("zoom restore probe")], msg_id="zoom-restore")
    QTimer.singleShot(timeout_ms, loop.quit)
    if not loaded["done"]:
        loop.exec()
    try:
        view.loadFinished.disconnect(on_finished)
    except TypeError:
        pass
    assert loaded["done"] and loaded["ok"], "H1 loadFinished failed"


def main() -> None:
    ensure_qt_webengine_ready()
    app = QApplication.instance() or QApplication(sys.argv)

    h1 = H1TranscriptHost()
    h1.show()
    h1.resize(640, 480)
    h1._ensure_view()
    _wait_h1_ready(h1)
    view = h1._view
    assert view is not None

    assert abs(float(view.zoomFactor()) - 1.0) < 0.02

    view.setZoomFactor(_ZOOMED)
    app.processEvents()
    assert abs(float(view.zoomFactor()) - _ZOOMED) < 0.02

    # Public restore path (browser workspace leave calls this).
    h1.reset_page_zoom()
    app.processEvents()
    z_reset = float(view.zoomFactor())
    assert abs(z_reset - 1.0) < 0.02, f"reset_page_zoom must pin to 1.0; got {z_reset}"

    # showEvent path (companion leave without hide still uses explicit reset;
    # hide/show recovers when chat is remounted).
    view.setZoomFactor(_ZOOMED)
    app.processEvents()
    h1.hide()
    h1.show()
    app.processEvents()
    z_show = float(view.zoomFactor())
    assert abs(z_show - 1.0) < 0.02, f"showEvent must restore zoom; got {z_show}"

    # Fresh setHtml loadFinished pins zoom (first paint path).
    view.setZoomFactor(_ZOOMED)
    app.processEvents()
    host_ready = {"done": False}
    loop = QEventLoop()

    def on_load(ok: bool) -> None:
        if ok:
            host_ready["done"] = True
            loop.quit()

    # Force full setHtml by clearing page-ready (same as first paint).
    h1._page_ready = False
    view.loadFinished.connect(on_load)
    h1.append_turn("assistant", [TextPart("after reload")], msg_id="zoom-reload")
    QTimer.singleShot(15000, loop.quit)
    if not host_ready["done"]:
        loop.exec()
    try:
        view.loadFinished.disconnect(on_load)
    except TypeError:
        pass
    app.processEvents()
    z_load = float(view.zoomFactor())
    assert abs(z_load - 1.0) < 0.02, f"loadFinished must restore zoom; got {z_load}"

    print("chat_zoom_restore ok", {"reset": z_reset, "show": z_show, "load": z_load})


if __name__ == "__main__":
    main()
