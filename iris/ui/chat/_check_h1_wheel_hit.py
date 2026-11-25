"""H1TranscriptHost must scroll DOM when QWheelEvent lands on the host wrapper.

Half-width IdeUnifiedShell + companion ChatPanel: Chromium child scrolls, but
sendEvent to H1TranscriptHost / ChatPanel / QWebEngineView wrapper leaves
body.scrollTop unchanged. Host.wheelEvent bridges that gap.

Run: .venv\\Scripts\\python.exe -m iris.ui.chat._check_h1_wheel_hit
"""

from __future__ import annotations

import sys

from iris.ui.qt_bootstrap import ensure_qt_webengine_ready

ensure_qt_webengine_ready()

from PyQt6.QtCore import QEventLoop, QPoint, QPointF, Qt, QTimer
from PyQt6.QtGui import QWheelEvent
from PyQt6.QtWidgets import QApplication, QWidget

from iris.core.message_parts import TextPart
from iris.ui.chat.chat_panel import ChatPanel
from iris.ui.workspaces.ide_companion_page import IdeCompanionPage, IdeUnifiedShell

_TALL = "# Wheel\n\n" + ("tall line for body scroll height.\n\n" * 60)
_SHELL_W = 960
_SHELL_H = 900


def _settle(ms: int = 200) -> None:
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def _wait_load(view, timeout_ms: int = 15000) -> None:
    loaded = {"ok": False, "done": False}
    loop = QEventLoop()

    def _on_finished(ok: bool) -> None:
        loaded["ok"] = bool(ok)
        loaded["done"] = True
        loop.quit()

    view.loadFinished.connect(_on_finished)
    QTimer.singleShot(timeout_ms, loop.quit)
    if not loaded["done"]:
        loop.exec()
    try:
        view.loadFinished.disconnect(_on_finished)
    except TypeError:
        pass
    assert loaded["done"] and loaded["ok"], "H1 loadFinished failed"


def _wheel_on(target, *, angle_y: int = -120) -> None:
    """Deliver a wheel notch to a wrapper (host or QWebEngineView), not Chromium child."""
    center = target.rect().center()
    global_pos = target.mapToGlobal(center)
    event = QWheelEvent(
        QPointF(center),
        QPointF(global_pos),
        QPoint(0, 0),
        QPoint(0, int(angle_y)),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase,
        False,
    )
    app = QApplication.instance()
    assert app is not None
    app.sendEvent(target, event)


def _check_host_wheel_moves_scroll(app: QApplication) -> None:
    del app
    shell = IdeUnifiedShell()
    shell.resize(_SHELL_W, _SHELL_H)
    shell.show()

    companion = IdeCompanionPage()
    panel = ChatPanel()
    spacer = QWidget()
    spacer.setMinimumHeight(120)
    spacer.setMaximumHeight(120)
    live = QWidget()
    live.setMinimumHeight(60)
    live.setMaximumHeight(60)

    companion.mount(
        orb_spacer=spacer,
        live_activity=live,
        chat=panel,
        orb_height=120,
        activity_height=60,
    )
    left = QWidget()
    left.setObjectName("FakeBrowserHost")
    shell.mount(left, companion, total_w=_SHELL_W)
    shell.show()
    _settle(80)

    host = panel.transcript()
    view = host.view()
    assert view is not None

    for i in range(5):
        host.append_turn(
            "assistant",
            [TextPart(markdown=_TALL)],
            msg_id=f"wheel-tall-{i}",
        )
    _wait_load(view)
    _settle(300)

    host.scroll_to_bottom()
    _settle(80)
    max_y = host.scroll_y()
    assert max_y > 80, f"content not tall enough: max_y={max_y}"

    hold = max(0, max_y // 3)
    host.set_scroll_y(hold)
    _settle(80)
    before = host.scroll_y()
    assert abs(before - hold) <= 8, f"mid scroll setup failed: want~{hold} got={before}"

    # Negative angleDelta.y → scroll down → scrollTop should increase.
    _wheel_on(host, angle_y=-120)
    _settle(120)
    after_host = host.scroll_y()
    assert after_host != before, (
        f"H1TranscriptHost.wheelEvent must move body.scrollTop; "
        f"before={before} after={after_host} (half-width companion {_SHELL_W}x{_SHELL_H})"
    )
    assert after_host > before, (
        f"wheel down should increase scrollTop; before={before} after={after_host}"
    )

    before_view = after_host
    _wheel_on(view, angle_y=-120)
    _settle(120)
    after_view = host.scroll_y()
    assert after_view > before_view, (
        f"QWebEngineView wrapper wheel must move body.scrollTop; "
        f"before={before_view} after={after_view}"
    )

    print(
        "h1_wheel_hit host+view wrapper ok",
        {
            "before": before,
            "after_host": after_host,
            "after_view": after_view,
            "max_y": max_y,
            "shell_w": _SHELL_W,
        },
    )
    shell.close()


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    _check_host_wheel_moves_scroll(app)
    print("h1_wheel_hit ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
