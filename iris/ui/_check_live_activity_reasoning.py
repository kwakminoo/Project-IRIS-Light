"""Live Activity reasoning button and tool-use line.

Run: .venv\\Scripts\\python.exe -m iris.ui._check_live_activity_reasoning
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QPlainTextEdit, QPushButton, QWidget

from iris.engine import (
    EngineHome,
    InternalSidecar,
    ReasoningDelta,
    ToolProgress,
    TurnFinished,
)
from iris.engine._sidecar import parse_turn_event
from iris.engine._sidecar_main import tool_use_label
from iris.infrastructure.iris_agent_client import IrisAgentInferenceTarget
from iris.ui.monitor.live_activity_panel import LiveActivityPanel, _PANEL_MAX_HEIGHT, _THINK_PREVIEW
from iris.ui.workers.iris_agent_workers import IrisAgentChatWorker


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


class _Engine:
    def __init__(self, text: str) -> None:
        self.source = InternalSidecar(home=EngineHome(Path(".")))
        self._text = text

    def run_turn(self, _turn: object):
        yield ReasoningDelta(self._text)
        yield ToolProgress("[IRIS tool use: read_file]")
        yield TurnFinished("ok")


def _worker_check() -> None:
    full = "R" * 60
    assert parse_turn_event({"t": "think", "text": full}) == ReasoningDelta(full)
    engine = _Engine(full)
    worker = IrisAgentChatWorker(
        "llama",
        [{"role": "user", "content": "hi"}],
        target=IrisAgentInferenceTarget(model="llama", provider="custom"),
    )
    reasons: list[str] = []
    tools: list[str] = []
    worker.reasoning.connect(reasons.append)
    worker.tool_progress.connect(tools.append)
    with (
        patch.object(IrisAgentChatWorker, "_wire_native_speak_tools", lambda self: None),
        patch("iris.ui.workers.iris_agent_workers.shared_engine", return_value=engine),
        patch("iris.ui.workers.iris_agent_workers._engine_source", return_value=engine.source),
    ):
        worker.run()
    assert reasons == [full]
    assert tools == ["[IRIS tool use: read_file]"]


def main() -> None:
    app = QApplication.instance() or QApplication(sys.argv)
    _panel_check(app)
    _begin_turn_header_check(app)
    _scroll_hold_check(app)
    _worker_check()
    print("live activity reasoning ok")


if __name__ == "__main__":
    main()
