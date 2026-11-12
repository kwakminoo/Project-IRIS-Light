from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QPlainTextEdit, QPushButton, QWidget

from iris.engine._sidecar_main import tool_use_label
from iris.ui.monitor.live_activity_panel import LiveActivityPanel, _PANEL_MAX_HEIGHT, _THINK_PREVIEW


def _panel_check(app: QApplication) -> None:
    full = "R" * 60
    host = QWidget()
    panel = LiveActivityPanel(host)
    host.resize(480, 420)
    host.show()
    app.processEvents()

    button = panel.findChild(QPushButton, "LiveActivityThink")
    body = panel.findChild(QPlainTextEdit, "LiveActivityThinkBody")
    assert button is not None and body is not None
    assert not button.isVisible()

    panel.append_reasoning(full)
    app.processEvents()
    assert button.isVisible()
    assert button.text() == full[:50]
    assert len(button.text()) == 50

    button.click()
    app.processEvents()
    assert body.isVisible()
    assert body.toPlainText() == full
    assert panel.maximumHeight() > _PANEL_MAX_HEIGHT

    panel.append_reasoning("MORE")
    app.processEvents()
    assert button.text() == (full + "MORE")[:50]
    assert body.toPlainText() == full + "MORE"

    button.click()
    app.processEvents()
    assert not body.isVisible()
    assert panel.maximumHeight() == _PANEL_MAX_HEIGHT

    label = tool_use_label("tool.started", "read_file")
    assert label == "[IRIS tool use: read_file]"
    panel.append_instant_line(label or "")
    app.processEvents()
    log = panel.findChild(QPlainTextEdit, "LiveActivityLog")
    assert log is not None
    assert "[IRIS tool use: read_file]" in log.toPlainText()

    panel.clear_for_idle()
    app.processEvents()
    assert not button.isVisible()
    assert button.text() == ""
    assert panel.maximumHeight() == _PANEL_MAX_HEIGHT
    host.close()


def _begin_turn_header_check(app: QApplication) -> None:
    host = QWidget()
    panel = LiveActivityPanel(host)
    host.resize(480, 420)
    host.show()
    app.processEvents()

    button = panel.findChild(QPushButton, "LiveActivityThink")
    body = panel.findChild(QPlainTextEdit, "LiveActivityThinkBody")
    assert button is not None and body is not None

    panel.append_reasoning("OLD stale reasoning that must not stick")
    app.processEvents()
    assert "OLD" in button.text()

    request = "새 요청입니다 " + ("가" * 40)
    panel.begin_turn(request)
    app.processEvents()
    expected = request[:_THINK_PREVIEW]
    assert button.isVisible()
    assert button.text() == expected
    assert "OLD" not in button.text()
    assert body.toPlainText() == ""
    assert not body.isVisible()
    assert panel.maximumHeight() == _PANEL_MAX_HEIGHT

    panel.begin_turn("요청")
    panel.append_reasoning("The user said hello")
    app.processEvents()
    assert button.text() == "요청"[:_THINK_PREVIEW]
    assert "The user said hello" in body.toPlainText()
    host.close()


def _scroll_hold_check(app: QApplication) -> None:
    host = QWidget()
    panel = LiveActivityPanel(host)
    host.resize(480, 420)
    panel.setMaximumHeight(120)
    panel._editor.setMaximumHeight(72)
    host.show()
    app.processEvents()

    for i in range(60):
        panel.append_instant_line(f"line-{i} " + ("x" * 48))
    app.processEvents()

    bar = panel._editor.verticalScrollBar()
    assert bar.maximum() > 10
    hold = max(0, bar.maximum() // 3)
    bar.setValue(hold)
    panel._note_user_log_scroll(hold)
    app.processEvents()
    assert panel._scroll_user_hold
    assert panel._scroll_hold_value == hold

    for i in range(25):
        panel.append_instant_line(f"more-{i} " + ("y" * 48))
    app.processEvents()

    assert abs(bar.value() - hold) <= 2
    assert bar.value() < bar.maximum() - 2
    host.close()


def main() -> None:
    app = QApplication.instance() or QApplication(sys.argv)
    _panel_check(app)
    _begin_turn_header_check(app)
    _scroll_hold_check(app)
    print("live activity reasoning ok")


if __name__ == "__main__":
    main()
